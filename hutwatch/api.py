"""HTTP API server for exposing local sensor data to remote HutWatch instances."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from aiohttp import web

from . import __version__
from .ble.sensor_store import SensorStore
from .db import Database
from .models import AppConfig
from .weather import WeatherFetcher

if TYPE_CHECKING:
    from .remote import RemotePoller

logger = logging.getLogger(__name__)


def build_status_payload(
    config: AppConfig,
    store: SensorStore,
    db: Database,
    weather: Optional[WeatherFetcher],
) -> dict:
    """Build the local status JSON payload.

    Shared by GET /status response and POST /sync outgoing data.
    """
    now = datetime.now()
    readings = store.get_all_latest()
    devices = db.get_all_devices()

    sensors = []
    for d in sorted(devices, key=lambda x: x.display_order):
        reading = readings.get(d.mac)
        sensor_config = config.get_sensor_by_mac(d.mac)
        name = d.get_display_name()
        if not name or name == d.mac:
            name = sensor_config.name if sensor_config else d.mac

        entry: dict = {
            "name": name,
            "mac": d.mac,
            "type": d.sensor_type,
            "order": d.display_order,
        }

        if reading:
            age = (now - reading.timestamp).total_seconds()
            entry["temperature"] = reading.temperature
            entry["humidity"] = reading.humidity
            entry["battery_percent"] = reading.battery_percent
            entry["battery_voltage"] = reading.battery_voltage
            entry["timestamp"] = reading.timestamp.strftime("%Y-%m-%d %H:%M:%S")
            entry["age_seconds"] = int(age)
        else:
            entry["temperature"] = None
            entry["age_seconds"] = None

        sensors.append(entry)

    site_name = db.get_setting("site_name") or None

    output: dict = {
        "timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
        "site_name": site_name,
        "sensors": sensors,
    }

    if weather and weather.latest:
        w = weather.latest
        output["weather"] = {
            "temperature": w.temperature,
            "humidity": w.humidity,
            "pressure": w.pressure,
            "wind_speed": w.wind_speed,
            "wind_direction": w.wind_direction,
            "precipitation": w.precipitation,
            "cloud_cover": w.cloud_cover,
            "symbol_code": w.symbol_code,
            "timestamp": w.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            "location": weather.location_name,
        }

    return output


class ApiServer:
    """aiohttp web server exposing sensor and weather data as JSON."""

    def __init__(
        self,
        config: AppConfig,
        store: SensorStore,
        db: Database,
        weather: Optional[WeatherFetcher],
        port: int,
    ) -> None:
        self._config = config
        self._store = store
        self._db = db
        self._weather = weather
        self._port = port
        self._runner: Optional[web.AppRunner] = None
        self._remote: Optional[RemotePoller] = None

    def set_weather(self, weather: WeatherFetcher) -> None:
        """Update weather fetcher reference (called from app.setup_weather)."""
        self._weather = weather

    def set_remote_poller(self, remote: RemotePoller) -> None:
        """Set remote poller for receiving incoming peer data via sync."""
        self._remote = remote

    async def start(self) -> None:
        """Start the API server."""
        app = web.Application()
        app.router.add_get("/api/v1/status", self._handle_status)
        app.router.add_get("/api/v1/health", self._handle_health)
        app.router.add_post("/api/v1/sync", self._handle_sync)

        self._runner = web.AppRunner(app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, "0.0.0.0", self._port)
        await site.start()
        logger.info("API server started on port %d", self._port)

    async def stop(self) -> None:
        """Stop the API server."""
        if self._runner:
            await self._runner.cleanup()
            self._runner = None
            logger.info("API server stopped")

    async def _handle_health(self, request: web.Request) -> web.Response:
        """Health check endpoint."""
        return web.json_response({"status": "ok", "version": __version__})

    async def _handle_status(self, request: web.Request) -> web.Response:
        """Return current sensor readings and weather as JSON."""
        output = build_status_payload(self._config, self._store, self._db, self._weather)
        return web.json_response(output)

    async def _handle_sync(self, request: web.Request) -> web.Response:
        """Bidirectional peer sync: receive peer data, return own data.

        The peer POSTs its local status; we store it and return ours.
        """
        try:
            peer_data = await request.json()
        except Exception:
            return web.json_response({"error": "invalid JSON"}, status=400)

        # Store the incoming peer data
        peer_site_name = peer_data.get("site_name") or "unknown"
        if self._remote:
            self._remote.receive_peer_data(peer_site_name, peer_data)
            logger.debug("Received sync from peer: %s", peer_site_name)

        # Return our own status
        output = build_status_payload(self._config, self._store, self._db, self._weather)
        return web.json_response(output)
