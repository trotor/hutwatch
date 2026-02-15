"""Data models for HutWatch."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class SensorType(Enum):
    """Supported sensor types."""

    RUUVI = "ruuvi"
    XIAOMI = "xiaomi"


@dataclass
class SensorConfig:
    """Configuration for a single sensor."""

    mac: str
    name: str
    type: SensorType

    def __post_init__(self) -> None:
        self.mac = self.mac.upper()
        if isinstance(self.type, str):
            self.type = SensorType(self.type)


@dataclass
class SensorReading:
    """A single sensor reading."""

    mac: str
    timestamp: datetime
    temperature: float
    humidity: Optional[float] = None
    battery_voltage: Optional[float] = None
    battery_percent: Optional[int] = None
    pressure: Optional[float] = None
    rssi: Optional[int] = None

    def __post_init__(self) -> None:
        self.mac = self.mac.upper()


@dataclass
class TelegramConfig:
    """Telegram bot configuration."""

    token: str
    chat_id: int
    report_interval: int = 3600


@dataclass
class WeatherConfig:
    """Weather API configuration."""

    latitude: float
    longitude: float
    location_name: str = "Sää"


@dataclass
class WeatherData:
    """Current weather data."""

    timestamp: datetime
    temperature: float
    humidity: Optional[float] = None
    pressure: Optional[float] = None
    wind_speed: Optional[float] = None
    wind_direction: Optional[float] = None
    precipitation: Optional[float] = None
    cloud_cover: Optional[float] = None
    symbol_code: Optional[str] = None


@dataclass
class RemoteSiteConfig:
    """Configuration for a remote HutWatch instance."""

    name: str
    url: str
    poll_interval: int = 30


@dataclass
class AppConfig:
    """Application configuration."""

    sensors: list[SensorConfig] = field(default_factory=list)
    telegram: Optional[TelegramConfig] = None
    weather: Optional[WeatherConfig] = None
    language: str = "fi"
    api_port: Optional[int] = None
    remote_sites: list[RemoteSiteConfig] = field(default_factory=list)

    def get_sensor_by_mac(self, mac: str) -> Optional[SensorConfig]:
        """Get sensor config by MAC address."""
        mac = mac.upper()
        for sensor in self.sensors:
            if sensor.mac == mac:
                return sensor
        return None

    def get_sensor_macs(self) -> set[str]:
        """Get all configured sensor MAC addresses."""
        return {s.mac for s in self.sensors}

    def add_sensor(self, mac: str, name: str, sensor_type: SensorType) -> SensorConfig:
        """Add a dynamically discovered sensor."""
        mac = mac.upper()
        existing = self.get_sensor_by_mac(mac)
        if existing:
            return existing
        sensor = SensorConfig(mac=mac, name=name, type=sensor_type)
        self.sensors.append(sensor)
        return sensor


@dataclass
class DeviceInfo:
    """Device information from database."""

    mac: str
    alias: Optional[str]
    display_order: int
    sensor_type: str
    config_name: Optional[str] = None

    def __post_init__(self) -> None:
        self.mac = self.mac.upper()

    def get_display_name(self) -> str:
        """Get the name to display for this device.

        Priority: alias > config_name > MAC address
        """
        if self.alias:
            return self.alias
        if self.config_name:
            return self.config_name
        return self.mac

    def get_full_display_name(self) -> str:
        """Get full display name with original name in parentheses if aliased."""
        if self.alias and self.config_name:
            return f"{self.alias} ({self.config_name})"
        return self.get_display_name()
