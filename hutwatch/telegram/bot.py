"""Telegram bot for HutWatch."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

from telegram import Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
)

from ..ble.sensor_store import SensorStore
from ..models import AppConfig, TelegramConfig
from .commands import CommandHandlers
from .scheduler import ReportScheduler

if TYPE_CHECKING:
    from ..db import Database
    from ..weather import WeatherFetcher

logger = logging.getLogger(__name__)


class TelegramBot:
    """Telegram bot for temperature monitoring."""

    def __init__(
        self,
        config: AppConfig,
        store: SensorStore,
        db: Optional["Database"] = None,
        weather: Optional["WeatherFetcher"] = None,
        remote: Optional[object] = None,
    ) -> None:
        self._config = config
        self._store = store
        self._db = db
        self._weather = weather
        self._app: Optional[Application] = None
        self._commands = CommandHandlers(config, store, db, weather, remote=remote)
        self._scheduler = ReportScheduler(config, store, self._commands, weather, remote=remote)

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
        self._app.add_handler(CommandHandler("devices", self._commands.devices))
        self._app.add_handler(CommandHandler("laitteet", self._commands.devices))
        self._app.add_handler(CommandHandler("rename", self._commands.rename))
        self._app.add_handler(CommandHandler("nimea", self._commands.rename))
        self._app.add_handler(CommandHandler("weather", self._commands.weather))
        self._app.add_handler(CommandHandler("saa", self._commands.weather))
        self._app.add_handler(CommandHandler("menu", self._commands.menu))
        self._app.add_handler(CommandHandler("help", self._commands.help))
        self._app.add_handler(CommandHandler("start", self._commands.menu))

        # Callback query handler for inline buttons
        self._app.add_handler(CallbackQueryHandler(self._commands.button_callback))

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

    async def run_with_restart(
        self,
        restart_delay: float = 5.0,
        max_restart_delay: float = 60.0,
    ) -> None:
        """Run bot with automatic restart on failure.

        Uses exponential backoff for restart delays.
        """
        import asyncio

        current_delay = restart_delay

        while True:
            try:
                logger.info("Starting Telegram bot with restart support...")
                await self.start()

                # Reset delay on successful start
                current_delay = restart_delay

                # Run until stopped - bot runs via polling
                while self._app:
                    await asyncio.sleep(1)

                # Clean exit
                logger.info("Telegram bot stopped cleanly")
                break

            except asyncio.CancelledError:
                logger.info("Telegram bot cancelled")
                break

            except Exception as e:
                logger.error("Telegram bot error: %s", e)

                # Clean up
                try:
                    await self.stop()
                except Exception:
                    pass

                # Wait before restart with exponential backoff
                logger.info(
                    "Restarting Telegram bot in %.1f seconds...",
                    current_delay,
                )
                await asyncio.sleep(current_delay)

                # Increase delay for next failure (exponential backoff)
                current_delay = min(current_delay * 2, max_restart_delay)

        # Final cleanup
        await self.stop()
