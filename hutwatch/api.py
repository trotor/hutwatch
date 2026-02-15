"""HTTP API server for exposing local sensor data to remote HutWatch instances."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from aiohttp import web

from . import __version__
from .ble.sensor_store import SensorStore
from .db import Database
from .models import AppConfig
from .weather import WeatherFetcher

logger = logging.getLogger(__name__)


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

    def set_weather(self, weather: WeatherFetcher) -> None:
        """Update weather fetcher reference (called from app.setup_weather)."""
        self._weather = weather

    async def start(self) -> None:
        """Start the API server."""
        app = web.Application()
        app.router.add_get("/api/v1/status", self._handle_status)
        app.router.add_get("/api/v1/health", self._handle_health)

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
        now = datetime.now()
        readings = self._store.get_all_latest()
        devices = self._db.get_all_devices()
        device_map = {d.mac: d for d in devices}

        sensors = []
        for d in sorted(devices, key=lambda x: x.display_order):
            reading = readings.get(d.mac)
            sensor_config = self._config.get_sensor_by_mac(d.mac)
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

        site_name = self._db.get_setting("site_name") or None

        output: dict = {
            "timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
            "site_name": site_name,
            "sensors": sensors,
        }

        if self._weather and self._weather.latest:
            w = self._weather.latest
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
                "location": self._weather.location_name,
            }

        return web.json_response(output)
