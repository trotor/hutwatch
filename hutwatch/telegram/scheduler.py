"""Scheduled message sending for Telegram bot."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from telegram.ext import ContextTypes

from ..ble.sensor_store import SensorStore
from ..formatting import format_age_long
from ..i18n import t
from ..models import AppConfig

if TYPE_CHECKING:
    from ..remote import RemotePoller
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
        remote: Optional["RemotePoller"] = None,
    ) -> None:
        self._config = config
        self._store = store
        self._commands = commands
        self._weather = weather
        self._remote = remote

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

        # Add remote site data
        if self._remote:
            now = datetime.now()
            for site_name, site_data in self._remote.get_all_site_data().items():
                if not site_data.sensors:
                    continue

                is_peer = self._remote.is_peer(site_name) or self._remote.is_incoming_peer(site_name)
                direction = "⇄" if is_peer else "→"
                offline_str = f" _{t('remote_offline')}_" if not site_data.online else ""
                lines.append("")
                lines.append(f"{direction} *{site_data.site_name}*{offline_str}")

                for s in site_data.sensors:
                    if s.temperature is None:
                        continue
                    line = f"  *{s.name}*: {s.temperature:.1f}°C"
                    if s.humidity is not None:
                        line += f", {s.humidity:.0f}%"
                    lines.append(line)

        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text="\n".join(lines),
                parse_mode="Markdown",
            )
            logger.info("Sent scheduled report to chat %d", chat_id)
        except Exception as e:
            logger.error("Failed to send scheduled report: %s", e)
