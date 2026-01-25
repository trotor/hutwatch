"""Configuration loading from YAML."""

import logging
from pathlib import Path

import yaml

from .models import AppConfig, SensorConfig, SensorType, TelegramConfig

logger = logging.getLogger(__name__)


def load_config(config_path: Path) -> AppConfig:
    """Load configuration from a YAML file."""
    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not data:
        raise ValueError("Configuration file is empty")

    sensors = []
    for sensor_data in data.get("sensors", []):
        try:
            sensor = SensorConfig(
                mac=sensor_data["mac"],
                name=sensor_data["name"],
                type=SensorType(sensor_data["type"]),
            )
            sensors.append(sensor)
            logger.debug("Loaded sensor: %s (%s)", sensor.name, sensor.mac)
        except (KeyError, ValueError) as e:
            logger.warning("Invalid sensor configuration: %s - %s", sensor_data, e)

    telegram_config = None
    if "telegram" in data:
        tg_data = data["telegram"]
        try:
            telegram_config = TelegramConfig(
                token=tg_data["token"],
                chat_id=tg_data["chat_id"],
                report_interval=tg_data.get("report_interval", 3600),
            )
            logger.debug("Loaded Telegram configuration")
        except KeyError as e:
            logger.warning("Invalid Telegram configuration: missing %s", e)

    config = AppConfig(sensors=sensors, telegram=telegram_config)
    logger.info("Loaded configuration with %d sensors", len(sensors))
    return config
