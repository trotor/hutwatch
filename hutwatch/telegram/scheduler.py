"""Scheduled message sending for Telegram bot."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from telegram.ext import ContextTypes

from ..ble.sensor_store import SensorStore
from ..i18n import t
from ..models import AppConfig

if TYPE_CHECKING:
    from ..weather import WeatherFetcher
    from .commands import CommandHandlers

logger = logging.getLogger(__name__)


class ReportScheduler:
    """Handles scheduled temperature reports."""

    def __init__(
        self,
        config: AppConfig,
        store: SensorStore,
        commands: "CommandHandlers",
        weather: Optional["WeatherFetcher"] = None,
    ) -> None:
        self._config = config
        self._store = store
        self._commands = commands
        self._weather = weather

    async def send_report(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Send scheduled temperature report."""
        if not self._config.telegram:
            return

        # Check if reports are enabled
        if not self._commands.reports_enabled:
            logger.debug("Scheduled report skipped - reports disabled")
            return

        chat_id = self._config.telegram.chat_id
        lines = [t("scheduler_report_header", timestamp=datetime.now().strftime('%d.%m. %H:%M'))]

        has_data = False
        for sensor_config in self._config.sensors:
            reading = self._store.get_latest(sensor_config.mac)

            if reading:
                has_data = True
                line = f"*{sensor_config.name}*: {reading.temperature:.1f}°C"
                if reading.humidity is not None:
                    line += f", {reading.humidity:.0f}%"
            else:
                line = f"*{sensor_config.name}*: {t('common_no_data_md')}"

            lines.append(line)

        if not has_data:
            logger.warning("No sensor data available for scheduled report")
            return

        # Add weather info if available
        if self._weather and self._weather.latest:
            from ..weather import get_weather_emoji

            w = self._weather.latest
            emoji = get_weather_emoji(w.symbol_code)
            lines.append("")
            weather_line = f"{emoji} *{self._weather.location_name}*: {w.temperature:.1f}°C"
            if w.humidity is not None:
                weather_line += f", {w.humidity:.0f}%"
            lines.append(weather_line)

        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text="\n".join(lines),
                parse_mode="Markdown",
            )
            logger.info("Sent scheduled report to chat %d", chat_id)
        except Exception as e:
            logger.error("Failed to send scheduled report: %s", e)
