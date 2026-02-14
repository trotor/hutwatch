"""BLE scanner using Bleak with periodic restart."""

from __future__ import annotations

import asyncio
import logging
import subprocess
import sys
from datetime import datetime
from typing import Callable, Optional

from bleak import BleakScanner as BleakScannerLib
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

from ..models import AppConfig, SensorReading, SensorType
from .parsers import RuuviParser, XiaomiParser
from .sensor_store import SensorStore

logger = logging.getLogger(__name__)

IS_MACOS = sys.platform == "darwin"


class BleScanner:
    """BLE scanner that detects and parses sensor advertisements.

    Restarts periodically to work around BlueZ/Bleak issues on Linux.
    """

    # Proactive restart interval
    # BlueZ often silently stops after ~30-60s; macOS Core Bluetooth is more stable
    RESTART_INTERVAL_SECONDS = 300 if IS_MACOS else 60

    # Watchdog timeout - force restart if no data received
    WATCHDOG_TIMEOUT_SECONDS = 120 if IS_MACOS else 45

    # Timeout for stop() operation - don't let it hang forever
    STOP_TIMEOUT_SECONDS = 10

    def __init__(
        self,
        config: AppConfig,
        store: SensorStore,
        db: Optional[object] = None,
        on_reading: Optional[Callable[[SensorReading], None]] = None,
    ) -> None:
        self._config = config
        self._store = store
        self._db = db
        self._on_reading = on_reading
        self._scanner: Optional[BleakScannerLib] = None
        self._running = False
        self._last_data_time: Optional[datetime] = None

        # Initialize parsers
        self._ruuvi_parser = RuuviParser()
        self._xiaomi_parser = XiaomiParser()
        self._parsers = [
            (self._ruuvi_parser, SensorType.RUUVI),
            (self._xiaomi_parser, SensorType.XIAOMI),
        ]

        # Track configured MACs for filtering
        self._configured_macs = config.get_sensor_macs()
        self._discovered_macs: set[str] = set()

        logger.info(
            "BLE Scanner initialized with %d configured sensors (discovery always on)",
            len(self._configured_macs),
        )

    def _detection_callback(
        self,
        device: BLEDevice,
        advertisement_data: AdvertisementData,
    ) -> None:
        """Handle detected BLE advertisement.

        Known MACs are parsed with their configured sensor type.
        Unknown MACs are tried against all parsers for auto-discovery.
        """
        mac = device.address.upper()

        try:
            # Fast path: known sensor with configured type
            sensor_config = self._config.get_sensor_by_mac(mac)
            if sensor_config:
                reading: Optional[SensorReading] = None

                if sensor_config.type == SensorType.RUUVI:
                    reading = self._ruuvi_parser.parse(device, advertisement_data)
                elif sensor_config.type == SensorType.XIAOMI:
                    reading = self._xiaomi_parser.parse(device, advertisement_data)

                if reading:
                    reading.rssi = advertisement_data.rssi
                    self._store.add_reading(reading)
                    self._last_data_time = datetime.now()

                    if self._on_reading:
                        self._on_reading(reading)

                    logger.debug(
                        "Received reading from %s (%s): %.1f°C",
                        sensor_config.name,
                        mac,
                        reading.temperature,
                    )
                return

            # Discovery: try each parser for unknown MACs
            if mac in self._discovered_macs:
                return  # Already registered via discovery

            for parser, sensor_type in self._parsers:
                if not parser.can_parse(device, advertisement_data):
                    continue

                # Auto-register new sensor
                self._discovered_macs.add(mac)
                name = f"{sensor_type.value}_{mac.replace(':', '')[-6:]}"
                self._config.add_sensor(mac, name, sensor_type)
                self._configured_macs = self._config.get_sensor_macs()

                if self._db:
                    self._db.sync_devices_from_config(self._config.sensors)

                logger.info(
                    "Discovered %s sensor: %s (%s)",
                    sensor_type.value,
                    name,
                    mac,
                )

                reading = parser.parse(device, advertisement_data)
                if reading:
                    reading.rssi = advertisement_data.rssi
                    self._store.add_reading(reading)
                    self._last_data_time = datetime.now()

                    if self._on_reading:
                        self._on_reading(reading)

                    logger.debug(
                        "Received reading from %s (%s): %.1f°C",
                        name,
                        mac,
                        reading.temperature,
                    )
                break

        except Exception as e:
            logger.warning("Error parsing data from %s: %s", mac, e)

    async def _create_scanner(self) -> BleakScannerLib:
        """Create a fresh scanner instance."""
        return BleakScannerLib(
            detection_callback=self._detection_callback,
        )

    async def _stop_scanner_safe(self) -> None:
        """Stop scanner with timeout protection."""
        if self._scanner is None:
            return

        try:
            await asyncio.wait_for(
                self._scanner.stop(),
                timeout=self.STOP_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            logger.warning("Scanner stop() timed out after %ds", self.STOP_TIMEOUT_SECONDS)
        except Exception as e:
            logger.debug("Error stopping scanner: %s", e)
        finally:
            self._scanner = None

    async def _reset_bluetooth_adapter(self) -> None:
        """Reset Bluetooth adapter to recover from stuck state.

        Uses bluetoothctl (D-Bus) which works without sudo when user
        is in bluetooth group, or hciconfig with CAP_NET_ADMIN.
        Skipped on macOS where Core Bluetooth manages the adapter.
        """
        if IS_MACOS:
            logger.debug("Skipping adapter reset on macOS")
            return

        # Try bluetoothctl first (works via D-Bus, no sudo needed)
        try:
            # Power off
            subprocess.run(
                ["bluetoothctl", "power", "off"],
                capture_output=True,
                timeout=5,
            )
            # Wait for adapter to power off
            await asyncio.sleep(1)

            # Power on
            subprocess.run(
                ["bluetoothctl", "power", "on"],
                capture_output=True,
                timeout=5,
            )
            # Wait for adapter to fully power on
            await asyncio.sleep(2)

            logger.info("Bluetooth adapter power cycled via bluetoothctl")
            return
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as e:
            logger.debug("bluetoothctl failed: %s", e)

        # Fallback to hciconfig (requires CAP_NET_ADMIN or sudo)
        try:
            result = subprocess.run(
                ["hciconfig", "hci0", "reset"],
                capture_output=True,
                timeout=10,
            )
            if result.returncode == 0:
                logger.info("Bluetooth adapter reset via hciconfig")
                await asyncio.sleep(2)  # Wait for adapter
            else:
                logger.debug("hciconfig reset failed: %s", result.stderr.decode().strip())
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as e:
            logger.debug("hciconfig failed: %s", e)

    @property
    def is_running(self) -> bool:
        """Check if scanner is running."""
        return self._running

    async def start(self) -> None:
        """Start BLE scanning."""
        if self._running:
            logger.warning("Scanner already running")
            return

        logger.info("Starting BLE scanner...")
        self._running = True
        self._scanner = await self._create_scanner()
        await self._scanner.start()
        self._last_data_time = datetime.now()
        logger.info("BLE scanner started")

    async def stop(self) -> None:
        """Stop BLE scanning."""
        if not self._running:
            return

        logger.info("Stopping BLE scanner...")
        self._running = False
        await self._stop_scanner_safe()
        logger.info("BLE scanner stopped")

    def _should_restart(self) -> tuple[bool, str]:
        """Check if scanner should be restarted.

        Returns (should_restart, reason).
        """
        now = datetime.now()

        # Check watchdog - no data received
        if self._last_data_time:
            elapsed = (now - self._last_data_time).total_seconds()
            if elapsed > self.WATCHDOG_TIMEOUT_SECONDS:
                return True, f"no data for {elapsed:.0f}s"

        return False, ""

    async def run_with_restart(self) -> None:
        """Run scanner with periodic restarts.

        Restarts every RESTART_INTERVAL_SECONDS to work around
        BlueZ issues, and also restarts on watchdog timeout.
        """
        restart_count = 0

        while True:
            try:
                restart_count += 1
                logger.info(
                    "Starting BLE scanner (cycle %d)...",
                    restart_count,
                )

                # Reset adapter before starting (helps with stuck state)
                if restart_count > 1:
                    await self._reset_bluetooth_adapter()

                # Create fresh scanner instance
                self._scanner = await self._create_scanner()
                await self._scanner.start()
                self._last_data_time = datetime.now()
                self._running = True

                logger.info("BLE scanner running (cycle %d)", restart_count)

                # Run until restart interval or watchdog triggers
                cycle_start = datetime.now()
                check_interval = 10  # Check every 10 seconds

                while self._running:
                    await asyncio.sleep(check_interval)

                    # Check proactive restart interval
                    cycle_elapsed = (datetime.now() - cycle_start).total_seconds()
                    if cycle_elapsed >= self.RESTART_INTERVAL_SECONDS:
                        logger.info(
                            "Proactive restart after %.0fs",
                            cycle_elapsed,
                        )
                        break

                    # Check watchdog
                    should_restart, reason = self._should_restart()
                    if should_restart:
                        logger.warning("Watchdog restart: %s", reason)
                        break

                # Stop current scanner
                await self._stop_scanner_safe()

                # If we're shutting down, exit
                if not self._running:
                    logger.info("BLE scanner stopped")
                    return

                # Brief pause before restart
                await asyncio.sleep(1)

            except asyncio.CancelledError:
                logger.info("BLE scanner cancelled")
                await self._stop_scanner_safe()
                return

            except Exception as e:
                logger.error("BLE scanner error: %s", e)
                await self._stop_scanner_safe()

                # Error recovery - reset adapter and wait
                await self._reset_bluetooth_adapter()
                await asyncio.sleep(3)

    async def run_forever(self) -> None:
        """Run scanner indefinitely (legacy method)."""
        await self.run_with_restart()
