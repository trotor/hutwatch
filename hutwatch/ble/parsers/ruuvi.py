"""RuuviTag BLE advertisement parser for Data Formats 3 and 5."""

import logging
import struct
from datetime import datetime
from typing import Optional

from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

from ...models import SensorReading
from .base import BaseParser

logger = logging.getLogger(__name__)

# RuuviTag manufacturer ID
RUUVI_MANUFACTURER_ID = 0x0499


class RuuviParser(BaseParser):
    """Parser for RuuviTag Data Format 3 (RAWv1) and Data Format 5 (RAWv2)."""

    def can_parse(
        self,
        device: BLEDevice,
        advertisement_data: AdvertisementData,
    ) -> bool:
        """Check if this is a RuuviTag advertisement."""
        if RUUVI_MANUFACTURER_ID not in advertisement_data.manufacturer_data:
            return False

        data = advertisement_data.manufacturer_data[RUUVI_MANUFACTURER_ID]
        if len(data) < 1:
            return False

        # Check for supported data formats
        data_format = data[0]
        return data_format in (3, 5)

    def parse(
        self,
        device: BLEDevice,
        advertisement_data: AdvertisementData,
    ) -> Optional[SensorReading]:
        """Parse RuuviTag advertisement data."""
        if not self.can_parse(device, advertisement_data):
            return None

        data = advertisement_data.manufacturer_data[RUUVI_MANUFACTURER_ID]
        data_format = data[0]

        if data_format == 3:
            return self._parse_df3(device.address, data)
        elif data_format == 5:
            return self._parse_df5(device.address, data)

        return None

    def _parse_df3(self, mac: str, data: bytes) -> Optional[SensorReading]:
        """
        Parse Data Format 3 (RAWv1).

        Format:
        - Byte 0: Data format (0x03)
        - Byte 1: Humidity (0.5% per unit)
        - Byte 2: Temperature (integer part, signed)
        - Byte 3: Temperature (fraction, 1/100)
        - Bytes 4-5: Pressure (unsigned, 50000 Pa added)
        - Bytes 6-7: Acceleration X
        - Bytes 8-9: Acceleration Y
        - Bytes 10-11: Acceleration Z
        - Bytes 12-13: Battery voltage (mV)
        """
        if len(data) < 14:
            logger.warning("DF3 data too short: %d bytes", len(data))
            return None

        try:
            humidity = data[1] * 0.5

            # Temperature: signed integer + fraction
            temp_int = data[2]
            if temp_int > 127:
                temp_int -= 256
            temp_frac = data[3] / 100.0
            temperature = temp_int + (temp_frac if temp_int >= 0 else -temp_frac)

            # Pressure in Pa, add 50000 and convert to hPa
            pressure_raw = struct.unpack(">H", data[4:6])[0]
            pressure = (pressure_raw + 50000) / 100.0

            # Battery voltage in mV
            battery_mv = struct.unpack(">H", data[12:14])[0]
            battery_voltage = battery_mv / 1000.0

            return SensorReading(
                mac=mac,
                timestamp=datetime.now(),
                temperature=temperature,
                humidity=humidity,
                pressure=pressure,
                battery_voltage=battery_voltage,
            )

        except Exception as e:
            logger.warning("Error parsing DF3: %s", e)
            return None

    def _parse_df5(self, mac: str, data: bytes) -> Optional[SensorReading]:
        """
        Parse Data Format 5 (RAWv2).

        Format:
        - Byte 0: Data format (0x05)
        - Bytes 1-2: Temperature (0.005 degree per unit, signed)
        - Bytes 3-4: Humidity (0.0025% per unit)
        - Bytes 5-6: Pressure (unsigned, 50000 Pa added)
        - Bytes 7-8: Acceleration X
        - Bytes 9-10: Acceleration Y
        - Bytes 11-12: Acceleration Z
        - Bytes 13-14: Power info (11 bits voltage, 5 bits TX power)
        - Byte 15: Movement counter
        - Bytes 16-17: Measurement sequence
        """
        if len(data) < 18:
            logger.warning("DF5 data too short: %d bytes", len(data))
            return None

        try:
            # Temperature: signed 16-bit, 0.005°C per unit
            temp_raw = struct.unpack(">h", data[1:3])[0]
            temperature = temp_raw * 0.005

            # Check for invalid temperature
            if temp_raw == -32768:
                logger.debug("DF5: Invalid temperature value")
                return None

            # Humidity: unsigned 16-bit, 0.0025% per unit
            humidity_raw = struct.unpack(">H", data[3:5])[0]
            humidity = humidity_raw * 0.0025

            # Check for invalid humidity
            if humidity_raw == 65535:
                humidity = None

            # Pressure: unsigned 16-bit, add 50000 Pa, convert to hPa
            pressure_raw = struct.unpack(">H", data[5:7])[0]
            if pressure_raw == 65535:
                pressure = None
            else:
                pressure = (pressure_raw + 50000) / 100.0

            # Power info: 11 bits voltage + 5 bits TX power
            power_raw = struct.unpack(">H", data[13:15])[0]
            voltage_raw = power_raw >> 5
            if voltage_raw == 2047:
                battery_voltage = None
            else:
                battery_voltage = (voltage_raw + 1600) / 1000.0

            return SensorReading(
                mac=mac,
                timestamp=datetime.now(),
                temperature=temperature,
                humidity=humidity,
                pressure=pressure,
                battery_voltage=battery_voltage,
            )

        except Exception as e:
            logger.warning("Error parsing DF5: %s", e)
            return None
