"""Remote site poller for fetching data from other HutWatch instances."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Callable, Optional

import aiohttp

from .models import RemoteSiteConfig

logger = logging.getLogger(__name__)


@dataclass
class RemoteSensor:
    """Cached sensor data from a remote site."""

    name: str
    mac: str
    type: str
    order: int
    temperature: Optional[float] = None
    humidity: Optional[float] = None
    battery_percent: Optional[int] = None
    battery_voltage: Optional[float] = None
    battery_low: Optional[bool] = None
    timestamp: Optional[str] = None
    age_seconds: Optional[int] = None


@dataclass
class RemoteWeather:
    """Cached weather data from a remote site."""

    temperature: float
    humidity: Optional[float] = None
    pressure: Optional[float] = None
    wind_speed: Optional[float] = None
    wind_direction: Optional[float] = None
    precipitation: Optional[float] = None
    cloud_cover: Optional[float] = None
    symbol_code: Optional[str] = None
    location: Optional[str] = None


@dataclass
class RemoteSiteData:
    """Cached data for one remote site."""

    site_name: str
    sensors: list[RemoteSensor] = field(default_factory=list)
    weather: Optional[RemoteWeather] = None
    last_fetch: Optional[datetime] = None
    last_error: Optional[str] = None
    online: bool = False


def _parse_site_data(data: dict, site_name: str) -> RemoteSiteData:
    """Parse a status JSON payload into RemoteSiteData."""
    sensors = []
    for s in data.get("sensors", []):
        sensors.append(RemoteSensor(
            name=s.get("name", "?"),
            mac=s.get("mac", ""),
            type=s.get("type", ""),
            order=s.get("order", 0),
            temperature=s.get("temperature"),
            humidity=s.get("humidity"),
            battery_percent=s.get("battery_percent"),
            battery_voltage=s.get("battery_voltage"),
            battery_low=s.get("battery_low"),
            timestamp=s.get("timestamp"),
            age_seconds=s.get("age_seconds"),
        ))

    weather = None
    if "weather" in data:
        w = data["weather"]
        weather = RemoteWeather(
            temperature=w["temperature"],
            humidity=w.get("humidity"),
            pressure=w.get("pressure"),
            wind_speed=w.get("wind_speed"),
            wind_direction=w.get("wind_direction"),
            precipitation=w.get("precipitation"),
            cloud_cover=w.get("cloud_cover"),
            symbol_code=w.get("symbol_code"),
            location=w.get("location"),
        )

    return RemoteSiteData(
        site_name=data.get("site_name") or site_name,
        sensors=sensors,
        weather=weather,
        last_fetch=datetime.now(),
        online=True,
    )


class RemotePoller:
    """Polls remote HutWatch instances for sensor/weather data.

    Supports two modes:
    - remote_sites: read-only GET /api/v1/status (backward compatible)
    - peers: bidirectional POST /api/v1/sync (sends own data, receives peer data)
    """

    def __init__(
        self,
        remote_sites: Optional[list[RemoteSiteConfig]] = None,
        peers: Optional[list[RemoteSiteConfig]] = None,
        db=None,
        local_status_fn: Optional[Callable[[], dict]] = None,
        watchdog_threshold: int = 900,
        watchdog_interval: int = 60,
        watchdog_callback: Optional[Callable[[str, bool, Optional[datetime]], None]] = None,
    ) -> None:
        self._remote_sites = remote_sites or []
        self._peers = peers or []
        self._db = db
        self._local_status_fn = local_status_fn
        self._watchdog_threshold = watchdog_threshold
        self._watchdog_interval = watchdog_interval
        self._watchdog_callback = watchdog_callback
        self._data: dict[str, RemoteSiteData] = {}
        self._offline_alerted: set[str] = set()
        self._session: Optional[aiohttp.ClientSession] = None
        self._tasks: list[asyncio.Task] = []
        # Buffer of remote sensor samples awaiting 5-min aggregation, keyed by MAC.
        self._reading_buffer: dict[str, list[dict]] = {}

        # Initialize data entries for configured sites/peers
        for site in self._remote_sites + self._peers:
            self._data[site.name] = RemoteSiteData(site_name=site.name)

        # Load cached data from database on startup
        for site in self._remote_sites + self._peers:
            self._load_cache_from_db(site.name)

    def get_all_site_data(self) -> dict[str, RemoteSiteData]:
        """Return snapshot of all remote site data."""
        return dict(self._data)

    def is_peer(self, site_name: str) -> bool:
        """Check if a site is a bidirectional peer (vs read-only remote)."""
        return any(p.name == site_name for p in self._peers)

    def is_incoming_peer(self, site_name: str) -> bool:
        """Check if a site was received via incoming sync (not configured locally)."""
        configured = {s.name for s in self._remote_sites + self._peers}
        return site_name in self._data and site_name not in configured

    def receive_peer_data(self, site_name: str, data: dict) -> None:
        """Receive and store data from an incoming peer sync request.

        Called by ApiServer when POST /api/v1/sync is received.
        """
        try:
            site_data = _parse_site_data(data, site_name)
            self._data[site_name] = site_data
            self._save_cache_to_db(site_name)
            self._sync_remote_devices(site_name, data.get("sensors", []))
            self._buffer_sensor_readings(site_data)
            logger.debug("Stored incoming peer data: %s (%d sensors)",
                         site_name, len(site_data.sensors))
        except Exception as e:
            logger.warning("Failed to parse incoming peer data from %s: %s", site_name, e)

    def _load_cache_from_db(self, site_name: str) -> None:
        """Load cached remote site data from database settings table."""
        if not self._db:
            return
        raw = self._db.get_setting(f"remote_cache_{site_name}")
        if not raw:
            return
        try:
            cached = json.loads(raw)
            sensors = [
                RemoteSensor(**s) for s in cached.get("sensors", [])
            ]
            weather = None
            if cached.get("weather"):
                weather = RemoteWeather(**cached["weather"])
            last_fetch = None
            if cached.get("last_fetch"):
                last_fetch = datetime.fromisoformat(cached["last_fetch"])
            self._data[site_name] = RemoteSiteData(
                site_name=cached.get("site_name", site_name),
                sensors=sensors,
                weather=weather,
                last_fetch=last_fetch,
                online=False,
            )
            logger.info("Loaded cached data for remote site %s", site_name)
        except Exception as e:
            logger.warning("Failed to load cache for remote site %s: %s", site_name, e)

    def _sync_remote_devices(self, site_name: str, sensors: list[dict]) -> None:
        """Sync remote device names into devices table."""
        if self._db and hasattr(self._db, "sync_remote_devices"):
            self._db.sync_remote_devices(site_name, sensors)

    def _buffer_sensor_readings(self, site_data: RemoteSiteData) -> None:
        """Append the latest snapshot of each remote sensor to the aggregation buffer."""
        now = datetime.now()
        for s in site_data.sensors:
            if s.temperature is None or not s.mac:
                continue
            mac = s.mac.upper()
            self._reading_buffer.setdefault(mac, []).append({
                "ts": now,
                "temperature": s.temperature,
                "humidity": s.humidity,
                "battery_voltage": s.battery_voltage,
                "battery_percent": s.battery_percent,
            })

    def flush_readings_to_db(self, bucket_ts: datetime) -> int:
        """Aggregate buffered remote samples and write one row per MAC.

        Called by the local Aggregator on its 5-min tick so remote readings
        land in the same bucket boundary as local sensors.
        """
        if not self._db or not self._reading_buffer:
            return 0

        saved = 0
        for mac, samples in self._reading_buffer.items():
            if not samples:
                continue
            temps = [s["temperature"] for s in samples]
            humidities = [s["humidity"] for s in samples if s["humidity"] is not None]
            latest = samples[-1]
            try:
                self._db.save_aggregated_reading(
                    mac=mac,
                    timestamp=bucket_ts,
                    temp_avg=sum(temps) / len(temps),
                    temp_min=min(temps),
                    temp_max=max(temps),
                    humidity_avg=(sum(humidities) / len(humidities)) if humidities else None,
                    pressure_avg=None,
                    battery_voltage=latest["battery_voltage"],
                    battery_percent=latest["battery_percent"],
                    sample_count=len(samples),
                )
                saved += 1
            except Exception as e:
                logger.warning("Failed to save remote readings for %s: %s", mac, e)

        self._reading_buffer.clear()
        return saved

    def _save_cache_to_db(self, site_name: str) -> None:
        """Save remote site data to database settings table."""
        if not self._db:
            return
        site_data = self._data.get(site_name)
        if not site_data:
            return
        try:
            cache = {
                "site_name": site_data.site_name,
                "sensors": [asdict(s) for s in site_data.sensors],
                "weather": asdict(site_data.weather) if site_data.weather else None,
                "last_fetch": site_data.last_fetch.isoformat() if site_data.last_fetch else None,
            }
            self._db.set_setting(f"remote_cache_{site_name}", json.dumps(cache))
        except Exception as e:
            logger.warning("Failed to save cache for remote site %s: %s", site_name, e)

    async def start(self) -> None:
        """Start polling all remote sites and peers."""
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=15),
        )

        # Start polling tasks for read-only remote sites
        for site in self._remote_sites:
            task = asyncio.create_task(
                self._poll_loop(site, sync=False),
                name=f"remote_poll_{site.name}",
            )
            self._tasks.append(task)

        # Start polling tasks for bidirectional peers
        for peer in self._peers:
            task = asyncio.create_task(
                self._poll_loop(peer, sync=True),
                name=f"peer_sync_{peer.name}",
            )
            self._tasks.append(task)

        # Start watchdog task if configured
        if self._watchdog_threshold > 0 and self._watchdog_interval > 0:
            self._tasks.append(asyncio.create_task(
                self._watchdog_loop(),
                name="peer_watchdog",
            ))

        total = len(self._remote_sites) + len(self._peers)
        if total > 0:
            logger.info(
                "Remote poller started: %d remote site(s), %d peer(s)",
                len(self._remote_sites), len(self._peers),
            )

    async def stop(self) -> None:
        """Stop polling and close session."""
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._tasks.clear()

        if self._session:
            await self._session.close()
            self._session = None
        logger.info("Remote poller stopped")

    async def _poll_loop(self, site: RemoteSiteConfig, sync: bool) -> None:
        """Poll a single remote site repeatedly."""
        while True:
            if sync:
                await self._sync_peer(site)
            else:
                await self._fetch_site(site)
            await asyncio.sleep(site.poll_interval)

    async def _watchdog_loop(self) -> None:
        """Periodically check peer freshness and emit offline/recovery events."""
        # Brief grace period after startup so peers have a chance to sync first
        await asyncio.sleep(min(self._watchdog_interval, 30))
        while True:
            try:
                self._check_freshness()
            except Exception as e:
                logger.warning("Watchdog check failed: %s", e)
            await asyncio.sleep(self._watchdog_interval)

    def _check_freshness(self) -> None:
        """Inspect each tracked site and fire callbacks on state transitions."""
        if not self._watchdog_callback:
            return
        now = datetime.now()
        for name, site_data in self._data.items():
            last = site_data.last_fetch
            stale = last is None or (now - last).total_seconds() > self._watchdog_threshold
            alerted = name in self._offline_alerted
            if stale and not alerted:
                self._offline_alerted.add(name)
                site_data.online = False
                logger.warning("Peer %s offline (last seen: %s)", name, last)
                try:
                    self._watchdog_callback(name, False, last)
                except Exception as e:
                    logger.error("Watchdog offline callback failed: %s", e)
            elif not stale and alerted:
                self._offline_alerted.discard(name)
                logger.info("Peer %s recovered", name)
                try:
                    self._watchdog_callback(name, True, last)
                except Exception as e:
                    logger.error("Watchdog recovery callback failed: %s", e)

    async def _fetch_site(self, site: RemoteSiteConfig) -> None:
        """Fetch status from a remote site (read-only GET)."""
        url = f"{site.url}/api/v1/status"
        headers = {"X-HutWatch-Token": site.token} if site.token else None
        try:
            async with self._session.get(url, headers=headers) as resp:
                if resp.status != 200:
                    self._data[site.name].online = False
                    self._data[site.name].last_error = f"HTTP {resp.status}"
                    logger.warning("Remote site %s returned HTTP %d", site.name, resp.status)
                    return

                data = await resp.json()

            self._data[site.name] = _parse_site_data(data, site.name)
            self._save_cache_to_db(site.name)
            self._sync_remote_devices(site.name, data.get("sensors", []))
            self._buffer_sensor_readings(self._data[site.name])
            logger.debug("Fetched remote site %s: %d sensors",
                         site.name, len(self._data[site.name].sensors))

        except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as e:
            self._data[site.name].online = False
            self._data[site.name].last_error = str(e)
            logger.warning("Remote site %s unreachable: %s", site.name, e)
        except Exception as e:
            self._data[site.name].online = False
            self._data[site.name].last_error = str(e)
            logger.warning("Error fetching remote site %s: %s", site.name, e)

    async def _sync_peer(self, site: RemoteSiteConfig) -> None:
        """Bidirectional sync with a peer (POST own data, receive theirs).

        Falls back to read-only GET if POST /sync returns 404 (old version).
        """
        url = f"{site.url}/api/v1/sync"
        local_data = self._local_status_fn() if self._local_status_fn else {}
        headers = {"X-HutWatch-Token": site.token} if site.token else None

        try:
            async with self._session.post(url, json=local_data, headers=headers) as resp:
                if resp.status == 404:
                    # Peer doesn't support sync yet — fall back to GET
                    logger.info("Peer %s doesn't support sync, falling back to GET", site.name)
                    await self._fetch_site(site)
                    return

                if resp.status != 200:
                    self._data[site.name].online = False
                    self._data[site.name].last_error = f"HTTP {resp.status}"
                    logger.warning("Peer %s sync returned HTTP %d", site.name, resp.status)
                    return

                data = await resp.json()

            self._data[site.name] = _parse_site_data(data, site.name)
            self._save_cache_to_db(site.name)
            self._sync_remote_devices(site.name, data.get("sensors", []))
            self._buffer_sensor_readings(self._data[site.name])
            logger.debug("Synced with peer %s: %d sensors",
                         site.name, len(self._data[site.name].sensors))

        except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as e:
            self._data[site.name].online = False
            self._data[site.name].last_error = str(e)
            logger.warning("Peer %s unreachable: %s", site.name, e)
        except Exception as e:
            self._data[site.name].online = False
            self._data[site.name].last_error = str(e)
            logger.warning("Error syncing peer %s: %s", site.name, e)
