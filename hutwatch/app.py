"""Main application coordinator."""

from __future__ import annotations

import asyncio
import logging
import signal
from pathlib import Path
from typing import Optional

from .aggregator import Aggregator
from .ble.scanner import BleScanner
from .ble.sensor_store import SensorStore
from .config import load_config
from .db import Database
from .models import AppConfig
from .telegram.bot import TelegramBot
from .weather import WeatherFetcher

logger = logging.getLogger(__name__)


class HutWatchApp:
    """Main application that coordinates all components."""

    def __init__(self, config_path: Path, db_path: Optional[Path] = None) -> None:
        self._config_path = config_path
        self._db_path = db_path or config_path.parent / "hutwatch.db"
        self._config: Optional[AppConfig] = None
        self._store: Optional[SensorStore] = None
        self._db: Optional[Database] = None
        self._scanner: Optional[BleScanner] = None
        self._aggregator: Optional[Aggregator] = None
        self._weather: Optional[WeatherFetcher] = None
        self._bot: Optional[TelegramBot] = None
        self._running = False
        self._shutdown_event: Optional[asyncio.Event] = None
        self._scanner_task: Optional[asyncio.Task] = None
        self._bot_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Start all components."""
        logger.info("Starting HutWatch...")

        # Load configuration
        self._config = load_config(self._config_path)

        # Initialize database
        self._db = Database(self._db_path)
        self._db.connect()

        # Sync devices from config to database
        self._db.sync_devices_from_config(self._config.sensors)

        # Initialize weather fetcher if configured
        if self._config.weather:
            self._weather = WeatherFetcher(self._config.weather)
            await self._weather.start()
            logger.info(
                "Weather configured for %s (%.4f, %.4f)",
                self._config.weather.location_name,
                self._config.weather.latitude,
                self._config.weather.longitude,
            )

        # Initialize components
        self._store = SensorStore()
        self._scanner = BleScanner(self._config, self._store)
        self._aggregator = Aggregator(self._config, self._store, self._db, self._weather)

        if self._config.telegram:
            self._bot = TelegramBot(self._config, self._store, self._db, self._weather)

        # Start aggregator (does not need restart loop)
        await self._aggregator.start()

        # Start scanner with restart loop in background task
        self._scanner_task = asyncio.create_task(
            self._scanner.run_with_restart(),
            name="ble_scanner",
        )

        # Start bot with restart loop in background task
        if self._bot:
            self._bot_task = asyncio.create_task(
                self._bot.run_with_restart(),
                name="telegram_bot",
            )
            # Wait briefly for bot to start before sending message
            await asyncio.sleep(2)

        self._running = True
        logger.info("HutWatch started successfully")

    async def stop(self) -> None:
        """Stop all components."""
        if not self._running:
            return

        logger.info("Stopping HutWatch...")
        self._running = False

        # Send shutdown message
        if self._bot:
            try:
                await self._bot.send_message("🔴 *HutWatch pysähtyy*")
            except Exception:
                pass

        # Cancel background tasks
        if self._bot_task:
            self._bot_task.cancel()
            try:
                await self._bot_task
            except asyncio.CancelledError:
                pass
            self._bot_task = None

        if self._scanner_task:
            self._scanner_task.cancel()
            try:
                await self._scanner_task
            except asyncio.CancelledError:
                pass
            self._scanner_task = None

        # Stop components in reverse order
        if self._bot:
            await self._bot.stop()

        if self._aggregator:
            await self._aggregator.stop()

        if self._scanner:
            await self._scanner.stop()

        if self._weather:
            await self._weather.stop()

        if self._db:
            self._db.close()

        logger.info("HutWatch stopped")

    async def run(self) -> None:
        """Run the application until shutdown signal."""
        # Create shutdown event in async context
        self._shutdown_event = asyncio.Event()

        # Setup signal handlers
        loop = asyncio.get_running_loop()

        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(
                sig,
                lambda: asyncio.create_task(self._handle_shutdown()),
            )

        try:
            await self.start()

            # Wait for shutdown while monitoring background tasks
            while not self._shutdown_event.is_set():
                # Check background tasks for unexpected failures
                await self._monitor_tasks()
                await asyncio.sleep(5)

        finally:
            await self.stop()

    async def _monitor_tasks(self) -> None:
        """Monitor background tasks and log any failures."""
        if self._scanner_task and self._scanner_task.done():
            try:
                # Get exception if any
                exc = self._scanner_task.exception()
                if exc:
                    logger.error("BLE scanner task failed: %s", exc)
            except asyncio.CancelledError:
                pass

        if self._bot_task and self._bot_task.done():
            try:
                exc = self._bot_task.exception()
                if exc:
                    logger.error("Telegram bot task failed: %s", exc)
            except asyncio.CancelledError:
                pass

    async def _handle_shutdown(self) -> None:
        """Handle shutdown signal."""
        logger.info("Shutdown signal received")
        self._shutdown_event.set()
