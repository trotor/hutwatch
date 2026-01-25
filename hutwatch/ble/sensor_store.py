"""In-memory storage for sensor readings with 24h history."""

from __future__ import annotations

import logging
from collections import deque
from datetime import datetime, timedelta
from threading import Lock
from typing import Optional

from ..models import SensorReading

logger = logging.getLogger(__name__)

# Keep readings for 24 hours
HISTORY_DURATION = timedelta(hours=24)
# Maximum readings per sensor (assuming ~1 reading per minute = 1440 per day)
MAX_READINGS_PER_SENSOR = 2000


class SensorStore:
    """Thread-safe storage for sensor readings."""

    def __init__(self) -> None:
        self._latest: dict[str, SensorReading] = {}
        self._history: dict[str, deque[SensorReading]] = {}
        self._lock = Lock()

    def add_reading(self, reading: SensorReading) -> None:
        """Add a new sensor reading."""
        mac = reading.mac.upper()

        with self._lock:
            self._latest[mac] = reading

            if mac not in self._history:
                self._history[mac] = deque(maxlen=MAX_READINGS_PER_SENSOR)

            self._history[mac].append(reading)
            self._cleanup_old_readings(mac)

        logger.debug(
            "Stored reading: %s = %.1f°C",
            mac,
            reading.temperature,
        )

    def _cleanup_old_readings(self, mac: str) -> None:
        """Remove readings older than HISTORY_DURATION. Must be called with lock held."""
        if mac not in self._history:
            return

        cutoff = datetime.now() - HISTORY_DURATION
        history = self._history[mac]

        while history and history[0].timestamp < cutoff:
            history.popleft()

    def get_latest(self, mac: str) -> Optional[SensorReading]:
        """Get the latest reading for a sensor."""
        mac = mac.upper()
        with self._lock:
            return self._latest.get(mac)

    def get_all_latest(self) -> dict[str, SensorReading]:
        """Get the latest readings for all sensors."""
        with self._lock:
            return dict(self._latest)

    def get_history(
        self,
        mac: str,
        hours: int = 24,
    ) -> list[SensorReading]:
        """Get reading history for a sensor."""
        mac = mac.upper()
        cutoff = datetime.now() - timedelta(hours=hours)

        with self._lock:
            if mac not in self._history:
                return []

            return [r for r in self._history[mac] if r.timestamp >= cutoff]

    def get_sensor_macs(self) -> set[str]:
        """Get all MAC addresses that have readings."""
        with self._lock:
            return set(self._latest.keys())

    def get_reading_age(self, mac: str) -> Optional[timedelta]:
        """Get the age of the latest reading for a sensor."""
        reading = self.get_latest(mac)
        if reading:
            return datetime.now() - reading.timestamp
        return None
