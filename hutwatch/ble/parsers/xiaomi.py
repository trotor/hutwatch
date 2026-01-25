"""Xiaomi LYWSD03MMC parser for ATC and PVVX custom firmware."""

import logging
import struct
from datetime import datetime
from typing import Optional

from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

from ...models import SensorReading
from .base import BaseParser

logger = logging.getLogger(__name__)

# Service data UUIDs for Xiaomi sensors with custom firmware
# ATC firmware uses 0x181A (Environmental Sensing)
ATC_SERVICE_UUID = "0000181a-0000-1000-8000-00805f9b34fb"
# PVVX firmware can also use a custom UUID
PVVX_SERVICE_UUID = "0000181a-0000-1000-8000-00805f9b34fb"


class XiaomiParser(BaseParser):
    """Parser for Xiaomi LYWSD03MMC with ATC or PVVX custom firmware."""

    def can_parse(
        self,
        device: BLEDevice,
        advertisement_data: AdvertisementData,
    ) -> bool:
        """Check if this is a Xiaomi sensor with custom firmware."""
        service_data = advertisement_data.service_data

        # Check for ATC/PVVX service UUID
        if ATC_SERVICE_UUID in service_data:
            data = service_data[ATC_SERVICE_UUID]
            # ATC format is 13 bytes, PVVX format is 15-17 bytes
            return len(data) in (13, 15, 16, 17)

        return False

    def parse(
        self,
        device: BLEDevice,
        advertisement_data: AdvertisementData,
    ) -> Optional[SensorReading]:
        """Parse Xiaomi sensor advertisement data."""
        if not self.can_parse(device, advertisement_data):
            return None

        data = advertisement_data.service_data[ATC_SERVICE_UUID]

        if len(data) == 13:
            return self._parse_atc(device.address, data)
        elif len(data) >= 15:
            return self._parse_pvvx(device.address, data)

        return None

    def _parse_atc(self, mac: str, data: bytes) -> Optional[SensorReading]:
        """
        Parse ATC firmware format (13 bytes).

        Format (atc1441 firmware):
        - Bytes 0-5: MAC address
        - Bytes 6-7: Temperature (int16, 0.01°C per unit, big-endian)
        - Byte 8: Humidity (%)
        - Byte 9: Battery (%)
        - Bytes 10-11: Battery voltage (mV, big-endian)
        - Byte 12: Frame counter
        """
        if len(data) < 13:
            logger.warning("ATC data too short: %d bytes", len(data))
            return None

        try:
            # Temperature: signed 16-bit big-endian, 0.01°C per unit
            temp_raw = struct.unpack(">h", data[6:8])[0]
            temperature = temp_raw / 10.0

            # Humidity: single byte percentage
            humidity = float(data[8])

            # Battery percentage
            battery_percent = data[9]

            # Battery voltage in mV
            battery_mv = struct.unpack(">H", data[10:12])[0]
            battery_voltage = battery_mv / 1000.0

            return SensorReading(
                mac=mac,
                timestamp=datetime.now(),
                temperature=temperature,
                humidity=humidity,
                battery_voltage=battery_voltage,
                battery_percent=battery_percent,
            )

        except Exception as e:
            logger.warning("Error parsing ATC format: %s", e)
            return None

    def _parse_pvvx(self, mac: str, data: bytes) -> Optional[SensorReading]:
        """
        Parse PVVX firmware format (15-17 bytes).

        Format (pvvx firmware, custom format):
        - Bytes 0-5: MAC address (reversed)
        - Bytes 6-7: Temperature (int16, 0.01°C per unit, little-endian)
        - Bytes 8-9: Humidity (uint16, 0.01% per unit, little-endian)
        - Bytes 10-11: Battery voltage (mV, little-endian)
        - Byte 12: Battery (%)
        - Byte 13: Counter
        - Byte 14: Flags
        - Bytes 15-16: Optional extended data
        """
        if len(data) < 15:
            logger.warning("PVVX data too short: %d bytes", len(data))
            return None

        try:
            # Temperature: signed 16-bit little-endian, 0.01°C per unit
            temp_raw = struct.unpack("<h", data[6:8])[0]
            temperature = temp_raw / 100.0

            # Humidity: unsigned 16-bit little-endian, 0.01% per unit
            humidity_raw = struct.unpack("<H", data[8:10])[0]
            humidity = humidity_raw / 100.0

            # Battery voltage in mV
            battery_mv = struct.unpack("<H", data[10:12])[0]
            battery_voltage = battery_mv / 1000.0

            # Battery percentage
            battery_percent = data[12]

            return SensorReading(
                mac=mac,
                timestamp=datetime.now(),
                temperature=temperature,
                humidity=humidity,
                battery_voltage=battery_voltage,
                battery_percent=battery_percent,
            )

        except Exception as e:
            logger.warning("Error parsing PVVX format: %s", e)
            return None
