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
    site_name = data.get("site_name")
    if site_name is not None:
        site_name = str(site_name)

    api_port = data.get("api_port")
    if api_port is not None:
        try:
            api_port = int(api_port)
        except (ValueError, TypeError):
            logger.warning("Invalid api_port value: %s", api_port)
            api_port = None

    api_bind = str(data.get("api_bind", "0.0.0.0"))
    api_token = data.get("api_token")
    if api_token is not None:
        api_token = str(api_token)

    watchdog_data = data.get("peer_watchdog") or {}
    try:
        peer_watchdog_threshold = int(watchdog_data.get("threshold_seconds", 900))
    except (ValueError, TypeError):
        logger.warning("Invalid peer_watchdog.threshold_seconds; using default")
        peer_watchdog_threshold = 900
    try:
        peer_watchdog_interval = int(watchdog_data.get("check_interval_seconds", 60))
    except (ValueError, TypeError):
        logger.warning("Invalid peer_watchdog.check_interval_seconds; using default")
        peer_watchdog_interval = 60

    remote_sites = []
    for site_data in data.get("remote_sites", []):
        try:
            site = RemoteSiteConfig(
                name=site_data["name"],
                url=site_data["url"].rstrip("/"),
                poll_interval=int(site_data.get("poll_interval", 30)),
                token=site_data.get("token"),
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
                token=peer_data.get("token"),
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
        site_name=site_name,
        api_port=api_port,
        api_bind=api_bind,
        api_token=api_token,
        peer_watchdog_threshold=peer_watchdog_threshold,
        peer_watchdog_interval=peer_watchdog_interval,
        remote_sites=remote_sites,
        peers=peers,
    )
    logger.info("Loaded configuration with %d sensors", len(sensors))
    return config
