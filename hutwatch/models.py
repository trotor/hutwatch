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
class AppConfig:
    """Application configuration."""

    sensors: list[SensorConfig] = field(default_factory=list)
    telegram: Optional[TelegramConfig] = None

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
