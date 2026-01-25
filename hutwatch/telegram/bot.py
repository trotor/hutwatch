"""Telegram bot for HutWatch."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
)

from ..ble.sensor_store import SensorStore
from ..models import AppConfig, TelegramConfig
from .commands import CommandHandlers
from .scheduler import ReportScheduler

if TYPE_CHECKING:
    from ..db import Database

logger = logging.getLogger(__name__)


class TelegramBot:
    """Telegram bot for temperature monitoring."""

    def __init__(
        self,
        config: AppConfig,
        store: SensorStore,
        db: Optional[Database] = None,
    ) -> None:
        self._config = config
        self._store = store
        self._db = db
        self._app: Optional[Application] = None
        self._commands = CommandHandlers(config, store, db)
        self._scheduler = ReportScheduler(config, store, self._commands)

        if not config.telegram:
            raise ValueError("Telegram configuration is required")

        self._tg_config: TelegramConfig = config.telegram

    async def start(self) -> None:
        """Start the Telegram bot."""
        logger.info("Starting Telegram bot...")

        self._app = (
            Application.builder()
            .token(self._tg_config.token)
            .build()
        )

        # Register command handlers
        self._app.add_handler(CommandHandler("temps", self._commands.temps))
        self._app.add_handler(CommandHandler("status", self._commands.status))
        self._app.add_handler(CommandHandler("history", self._commands.history))
        self._app.add_handler(CommandHandler("stats", self._commands.stats))
        self._app.add_handler(CommandHandler("graph", self._commands.graph))
        self._app.add_handler(CommandHandler("report", self._commands.report))
        self._app.add_handler(CommandHandler("help", self._commands.help))
        self._app.add_handler(CommandHandler("start", self._commands.help))

        # Setup scheduled reports
        if self._tg_config.report_interval > 0:
            job_queue = self._app.job_queue
            if job_queue:
                job_queue.run_repeating(
                    self._scheduler.send_report,
                    interval=self._tg_config.report_interval,
                    first=self._tg_config.report_interval,
                    name="temperature_report",
                )
                logger.info(
                    "Scheduled reports every %d seconds",
                    self._tg_config.report_interval,
                )

        # Initialize and start
        await self._app.initialize()
        await self._app.start()
        await self._app.updater.start_polling(allowed_updates=Update.ALL_TYPES)

        logger.info("Telegram bot started")

    async def stop(self) -> None:
        """Stop the Telegram bot."""
        if self._app:
            logger.info("Stopping Telegram bot...")
            await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()
            self._app = None
            logger.info("Telegram bot stopped")

    async def send_message(self, text: str, parse_mode: str = "Markdown") -> None:
        """Send a message to the configured chat."""
        if not self._app:
            logger.warning("Bot not running, cannot send message")
            return

        try:
            await self._app.bot.send_message(
                chat_id=self._tg_config.chat_id,
                text=text,
                parse_mode=parse_mode,
            )
        except Exception as e:
            logger.error("Failed to send message: %s", e)
