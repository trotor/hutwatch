"""Remote site poller for fetching data from other HutWatch instances."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

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


class RemotePoller:
    """Polls remote HutWatch instances for sensor/weather data."""

    def __init__(self, sites: list[RemoteSiteConfig]) -> None:
        self._sites = sites
        self._data: dict[str, RemoteSiteData] = {
            site.name: RemoteSiteData(site_name=site.name) for site in sites
        }
        self._session: Optional[aiohttp.ClientSession] = None
        self._tasks: list[asyncio.Task] = []

    def get_all_site_data(self) -> dict[str, RemoteSiteData]:
        """Return snapshot of all remote site data."""
        return dict(self._data)

    async def start(self) -> None:
        """Start polling all remote sites."""
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=15),
        )
        for site in self._sites:
            task = asyncio.create_task(
                self._poll_loop(site),
                name=f"remote_poll_{site.name}",
            )
            self._tasks.append(task)
        logger.info("Remote poller started for %d site(s)", len(self._sites))

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

    async def _poll_loop(self, site: RemoteSiteConfig) -> None:
        """Poll a single remote site repeatedly."""
        while True:
            await self._fetch_site(site)
            await asyncio.sleep(site.poll_interval)

    async def _fetch_site(self, site: RemoteSiteConfig) -> None:
        """Fetch status from a remote site and update cached data."""
        url = f"{site.url}/api/v1/status"
        try:
            async with self._session.get(url) as resp:
                if resp.status != 200:
                    self._data[site.name].online = False
                    self._data[site.name].last_error = f"HTTP {resp.status}"
                    logger.warning("Remote site %s returned HTTP %d", site.name, resp.status)
                    return

                data = await resp.json()

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

            self._data[site.name] = RemoteSiteData(
                site_name=data.get("site_name") or site.name,
                sensors=sensors,
                weather=weather,
                last_fetch=datetime.now(),
                online=True,
            )
            logger.debug("Fetched remote site %s: %d sensors", site.name, len(sensors))

        except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as e:
            self._data[site.name].online = False
            self._data[site.name].last_error = str(e)
            logger.warning("Remote site %s unreachable: %s", site.name, e)
        except Exception as e:
            self._data[site.name].online = False
            self._data[site.name].last_error = str(e)
            logger.warning("Error fetching remote site %s: %s", site.name, e)
