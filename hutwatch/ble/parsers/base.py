"""Base parser class for BLE advertisements."""

from abc import ABC, abstractmethod
from typing import Optional

from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

from ...models import SensorReading


class BaseParser(ABC):
    """Abstract base class for BLE advertisement parsers."""

    @abstractmethod
    def parse(
        self,
        device: BLEDevice,
        advertisement_data: AdvertisementData,
    ) -> Optional[SensorReading]:
        """
        Parse BLE advertisement data and return a SensorReading if valid.

        Args:
            device: BLE device information
            advertisement_data: Advertisement data from the device

        Returns:
            SensorReading if successfully parsed, None otherwise
        """
        pass

    @abstractmethod
    def can_parse(
        self,
        device: BLEDevice,
        advertisement_data: AdvertisementData,
    ) -> bool:
        """
        Check if this parser can handle the given advertisement.

        Args:
            device: BLE device information
            advertisement_data: Advertisement data from the device

        Returns:
            True if this parser can handle the data
        """
        pass
