"""Scheduled message sending for Telegram bot."""

import logging
from datetime import datetime

from telegram.ext import ContextTypes

from ..ble.sensor_store import SensorStore
from ..models import AppConfig

logger = logging.getLogger(__name__)


class ReportScheduler:
    """Handles scheduled temperature reports."""

    def __init__(self, config: AppConfig, store: SensorStore) -> None:
        self._config = config
        self._store = store

    async def send_report(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Send scheduled temperature report."""
        if not self._config.telegram:
            return

        chat_id = self._config.telegram.chat_id
        lines = [f"📊 *Lämpötilaraportti* ({datetime.now().strftime('%H:%M')})\n"]

        has_data = False
        for sensor_config in self._config.sensors:
            reading = self._store.get_latest(sensor_config.mac)

            if reading:
                has_data = True
                line = f"*{sensor_config.name}*: {reading.temperature:.1f}°C"
                if reading.humidity is not None:
                    line += f", {reading.humidity:.0f}%"
            else:
                line = f"*{sensor_config.name}*: _ei dataa_"

            lines.append(line)

        if not has_data:
            logger.warning("No sensor data available for scheduled report")
            return

        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text="\n".join(lines),
                parse_mode="Markdown",
            )
            logger.info("Sent scheduled report to chat %d", chat_id)
        except Exception as e:
            logger.error("Failed to send scheduled report: %s", e)
