"""Data aggregator for periodic database storage."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

from .ble.sensor_store import SensorStore
from .db import Database
from .models import AppConfig

logger = logging.getLogger(__name__)

# Aggregation interval in seconds (5 minutes)
AGGREGATION_INTERVAL = 300


class Aggregator:
    """Aggregates sensor data and saves to database periodically."""

    def __init__(
        self,
        config: AppConfig,
        store: SensorStore,
        db: Database,
    ) -> None:
        self._config = config
        self._store = store
        self._db = db
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._last_aggregation: dict[str, datetime] = {}

    async def start(self) -> None:
        """Start the aggregator."""
        if self._running:
            return

        logger.info("Starting data aggregator (interval: %ds)", AGGREGATION_INTERVAL)
        self._running = True
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        """Stop the aggregator."""
        if not self._running:
            return

        logger.info("Stopping data aggregator")
        self._running = False

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _run(self) -> None:
        """Main aggregation loop."""
        while self._running:
            try:
                await asyncio.sleep(AGGREGATION_INTERVAL)
                await self._aggregate()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Aggregation error: %s", e)

    async def _aggregate(self) -> None:
        """Aggregate and save data for all sensors."""
        now = datetime.now()
        # Round to 5-minute boundary
        timestamp = now.replace(
            minute=(now.minute // 5) * 5,
            second=0,
            microsecond=0,
        )

        for sensor_config in self._config.sensors:
            mac = sensor_config.mac

            # Get recent readings from store
            readings = self._store.get_history(mac, hours=1)

            # Filter to last 5 minutes
            cutoff = now - timedelta(seconds=AGGREGATION_INTERVAL)
            recent = [r for r in readings if r.timestamp >= cutoff]

            if not recent:
                continue

            # Calculate aggregates
            temps = [r.temperature for r in recent]
            temp_avg = sum(temps) / len(temps)
            temp_min = min(temps)
            temp_max = max(temps)

            humidity_avg = None
            humidities = [r.humidity for r in recent if r.humidity is not None]
            if humidities:
                humidity_avg = sum(humidities) / len(humidities)

            pressure_avg = None
            pressures = [r.pressure for r in recent if r.pressure is not None]
            if pressures:
                pressure_avg = sum(pressures) / len(pressures)

            # Get latest battery info
            latest = recent[-1]
            battery_voltage = latest.battery_voltage
            battery_percent = latest.battery_percent

            # Save to database
            self._db.save_aggregated_reading(
                mac=mac,
                timestamp=timestamp,
                temp_avg=temp_avg,
                temp_min=temp_min,
                temp_max=temp_max,
                humidity_avg=humidity_avg,
                pressure_avg=pressure_avg,
                battery_voltage=battery_voltage,
                battery_percent=battery_percent,
                sample_count=len(recent),
            )

            logger.debug(
                "Aggregated %d readings for %s: %.1f°C (min=%.1f, max=%.1f)",
                len(recent),
                sensor_config.name,
                temp_avg,
                temp_min,
                temp_max,
            )
