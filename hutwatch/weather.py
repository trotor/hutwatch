"""Weather data fetcher using MET Norway API (yr.no)."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Optional

import aiohttp

from .models import WeatherConfig, WeatherData

logger = logging.getLogger(__name__)

# MET Norway API base URL
API_URL = "https://api.met.no/weatherapi/locationforecast/2.0/compact"

# User-Agent is required by MET Norway API
USER_AGENT = "HutWatch/0.1.0 github.com/hutwatch"

# Weather symbol code to emoji mapping
WEATHER_SYMBOLS = {
    "clearsky": "☀️",
    "fair": "🌤️",
    "partlycloudy": "⛅",
    "cloudy": "☁️",
    "fog": "🌫️",
    "lightrain": "🌦️",
    "rain": "🌧️",
    "heavyrain": "🌧️",
    "lightrainshowers": "🌦️",
    "rainshowers": "🌧️",
    "heavyrainshowers": "🌧️",
    "lightsleet": "🌨️",
    "sleet": "🌨️",
    "heavysleet": "🌨️",
    "lightsnow": "🌨️",
    "snow": "❄️",
    "heavysnow": "❄️",
    "lightsnowshowers": "🌨️",
    "snowshowers": "❄️",
    "heavysnowshowers": "❄️",
    "thunder": "⛈️",
    "lightrainandthunder": "⛈️",
    "rainandthunder": "⛈️",
    "heavyrainandthunder": "⛈️",
    "sleetandthunder": "⛈️",
    "snowandthunder": "⛈️",
}


def get_weather_emoji(symbol_code: Optional[str]) -> str:
    """Get emoji for weather symbol code."""
    if not symbol_code:
        return "🌡️"
    # Remove day/night suffix (e.g., clearsky_day -> clearsky)
    base_symbol = symbol_code.split("_")[0]
    return WEATHER_SYMBOLS.get(base_symbol, "🌡️")


class WeatherFetcher:
    """Fetches weather data from MET Norway API."""

    def __init__(self, config: WeatherConfig) -> None:
        self._config = config
        self._session: Optional[aiohttp.ClientSession] = None
        self._latest: Optional[WeatherData] = None
        self._last_fetch: Optional[datetime] = None

    @property
    def latest(self) -> Optional[WeatherData]:
        """Get the latest weather data."""
        return self._latest

    @property
    def last_fetch(self) -> Optional[datetime]:
        """Get the timestamp of the last successful fetch."""
        return self._last_fetch

    @property
    def location_name(self) -> str:
        """Get the location name."""
        return self._config.location_name

    async def start(self) -> None:
        """Initialize the HTTP session."""
        if self._session is None:
            self._session = aiohttp.ClientSession(
                headers={"User-Agent": USER_AGENT}
            )

    async def stop(self) -> None:
        """Close the HTTP session."""
        if self._session:
            await self._session.close()
            self._session = None

    async def fetch(self) -> Optional[WeatherData]:
        """Fetch current weather data from API."""
        if not self._session:
            await self.start()

        url = f"{API_URL}?lat={self._config.latitude}&lon={self._config.longitude}"

        try:
            async with self._session.get(url) as response:
                if response.status != 200:
                    logger.error(
                        "Weather API error: %s %s",
                        response.status,
                        await response.text(),
                    )
                    return None

                data = await response.json()
                weather = self._parse_response(data)
                if weather:
                    self._latest = weather
                    self._last_fetch = datetime.now()
                    logger.debug(
                        "Weather fetched: %.1f°C, %s",
                        weather.temperature,
                        weather.symbol_code,
                    )
                return weather

        except asyncio.TimeoutError:
            logger.error("Weather API timeout")
            return None
        except aiohttp.ClientError as e:
            logger.error("Weather API client error: %s", e)
            return None
        except Exception as e:
            logger.error("Weather fetch error: %s", e)
            return None

    def _parse_response(self, data: dict) -> Optional[WeatherData]:
        """Parse API response into WeatherData."""
        try:
            timeseries = data.get("properties", {}).get("timeseries", [])
            if not timeseries:
                logger.warning("No weather timeseries data")
                return None

            # Get the first (current) entry
            current = timeseries[0]
            instant = current.get("data", {}).get("instant", {}).get("details", {})
            next_1h = current.get("data", {}).get("next_1_hours", {})

            # Parse timestamp
            time_str = current.get("time")
            if time_str:
                timestamp = datetime.fromisoformat(time_str.replace("Z", "+00:00"))
            else:
                timestamp = datetime.now()

            # Get symbol code from forecast
            symbol_code = next_1h.get("summary", {}).get("symbol_code")

            # Get precipitation from forecast
            precipitation = next_1h.get("details", {}).get("precipitation_amount")

            return WeatherData(
                timestamp=timestamp,
                temperature=instant.get("air_temperature"),
                humidity=instant.get("relative_humidity"),
                pressure=instant.get("air_pressure_at_sea_level"),
                wind_speed=instant.get("wind_speed"),
                wind_direction=instant.get("wind_from_direction"),
                precipitation=precipitation,
                cloud_cover=instant.get("cloud_area_fraction"),
                symbol_code=symbol_code,
            )

        except (KeyError, ValueError, TypeError) as e:
            logger.error("Error parsing weather data: %s", e)
            return None
