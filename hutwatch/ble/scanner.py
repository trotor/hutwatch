"""BLE scanner using Bleak."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Callable, Optional

from bleak import BleakScanner as BleakScannerLib
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

from ..models import AppConfig, SensorReading, SensorType
from .parsers import RuuviParser, XiaomiParser
from .sensor_store import SensorStore

logger = logging.getLogger(__name__)


class BleScanner:
    """BLE scanner that detects and parses sensor advertisements."""

    def __init__(
        self,
        config: AppConfig,
        store: SensorStore,
        on_reading: Optional[Callable[[SensorReading], None]] = None,
    ) -> None:
        self._config = config
        self._store = store
        self._on_reading = on_reading
        self._scanner: Optional[BleakScannerLib] = None
        self._running = False

        # Initialize parsers
        self._ruuvi_parser = RuuviParser()
        self._xiaomi_parser = XiaomiParser()

        # Track configured MACs for filtering
        self._configured_macs = config.get_sensor_macs()

        logger.info(
            "BLE Scanner initialized with %d configured sensors",
            len(self._configured_macs),
        )

    def _detection_callback(
        self,
        device: BLEDevice,
        advertisement_data: AdvertisementData,
    ) -> None:
        """Handle detected BLE advertisement."""
        mac = device.address.upper()

        # Only process configured sensors
        if mac not in self._configured_macs:
            return

        sensor_config = self._config.get_sensor_by_mac(mac)
        if not sensor_config:
            return

        reading: Optional[SensorReading] = None

        try:
            if sensor_config.type == SensorType.RUUVI:
                reading = self._ruuvi_parser.parse(device, advertisement_data)
            elif sensor_config.type == SensorType.XIAOMI:
                reading = self._xiaomi_parser.parse(device, advertisement_data)

            if reading:
                # Add RSSI from advertisement
                reading.rssi = advertisement_data.rssi
                self._store.add_reading(reading)

                if self._on_reading:
                    self._on_reading(reading)

                logger.debug(
                    "Received reading from %s (%s): %.1f°C",
                    sensor_config.name,
                    mac,
                    reading.temperature,
                )

        except Exception as e:
            logger.warning("Error parsing data from %s: %s", mac, e)

    async def start(self) -> None:
        """Start BLE scanning."""
        if self._running:
            logger.warning("Scanner already running")
            return

        logger.info("Starting BLE scanner...")
        self._running = True

        self._scanner = BleakScannerLib(
            detection_callback=self._detection_callback,
        )

        await self._scanner.start()
        logger.info("BLE scanner started")

    async def stop(self) -> None:
        """Stop BLE scanning."""
        if not self._running:
            return

        logger.info("Stopping BLE scanner...")
        self._running = False

        if self._scanner:
            await self._scanner.stop()
            self._scanner = None

        logger.info("BLE scanner stopped")

    @property
    def is_running(self) -> bool:
        """Check if scanner is running."""
        return self._running

    async def run_forever(self) -> None:
        """Run scanner indefinitely."""
        await self.start()
        try:
            while self._running:
                await asyncio.sleep(1)
        finally:
            await self.stop()
