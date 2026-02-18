"""Configuration loading from YAML."""

import logging
from pathlib import Path

import yaml

from .i18n import t
from .models import AppConfig, RemoteSiteConfig, SensorConfig, SensorType, TelegramConfig, WeatherConfig

logger = logging.getLogger(__name__)


def load_config(config_path: Path) -> AppConfig:
    """Load configuration from a YAML file."""
    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not data:
        data = {}

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

    weather_config = None
    if "weather" in data:
        w_data = data["weather"]
        try:
            weather_config = WeatherConfig(
                latitude=float(w_data["latitude"]),
                longitude=float(w_data["longitude"]),
                location_name=w_data.get("location_name", t("common_weather_default_name")),
            )
            logger.debug(
                "Loaded weather configuration: %s (%.4f, %.4f)",
                weather_config.location_name,
                weather_config.latitude,
                weather_config.longitude,
            )
        except (KeyError, ValueError) as e:
            logger.warning("Invalid weather configuration: %s", e)

    language = data.get("language", "fi")

    api_port = data.get("api_port")
    if api_port is not None:
        try:
            api_port = int(api_port)
        except (ValueError, TypeError):
            logger.warning("Invalid api_port value: %s", api_port)
            api_port = None

    remote_sites = []
    for site_data in data.get("remote_sites", []):
        try:
            site = RemoteSiteConfig(
                name=site_data["name"],
                url=site_data["url"].rstrip("/"),
                poll_interval=int(site_data.get("poll_interval", 30)),
            )
            remote_sites.append(site)
            logger.debug("Loaded remote site: %s (%s)", site.name, site.url)
        except (KeyError, ValueError) as e:
            logger.warning("Invalid remote site configuration: %s - %s", site_data, e)

    peers = []
    for peer_data in data.get("peers", []):
        try:
            peer = RemoteSiteConfig(
                name=peer_data["name"],
                url=peer_data["url"].rstrip("/"),
                poll_interval=int(peer_data.get("poll_interval", 30)),
            )
            peers.append(peer)
            logger.debug("Loaded peer: %s (%s)", peer.name, peer.url)
        except (KeyError, ValueError) as e:
            logger.warning("Invalid peer configuration: %s - %s", peer_data, e)

    config = AppConfig(
        sensors=sensors,
        telegram=telegram_config,
        weather=weather_config,
        language=language,
        api_port=api_port,
        remote_sites=remote_sites,
        peers=peers,
    )
    logger.info("Loaded configuration with %d sensors", len(sensors))
    return config
