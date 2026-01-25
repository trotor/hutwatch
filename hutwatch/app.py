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
        self._bot: Optional[TelegramBot] = None
        self._running = False
        self._shutdown_event: Optional[asyncio.Event] = None

    async def start(self) -> None:
        """Start all components."""
        logger.info("Starting HutWatch...")

        # Load configuration
        self._config = load_config(self._config_path)

        # Initialize database
        self._db = Database(self._db_path)
        self._db.connect()

        # Initialize components
        self._store = SensorStore()
        self._scanner = BleScanner(self._config, self._store)
        self._aggregator = Aggregator(self._config, self._store, self._db)

        if self._config.telegram:
            self._bot = TelegramBot(self._config, self._store, self._db)

        # Start components
        await self._scanner.start()
        await self._aggregator.start()

        if self._bot:
            await self._bot.start()

        self._running = True
        logger.info("HutWatch started successfully")

        # Send startup message
        if self._bot:
            sensor_count = len(self._config.sensors)
            await self._bot.send_message(
                f"🟢 *HutWatch käynnistyi*\n"
                f"Seurataan {sensor_count} anturia"
            )

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

        # Stop components in reverse order
        if self._bot:
            await self._bot.stop()

        if self._aggregator:
            await self._aggregator.stop()

        if self._scanner:
            await self._scanner.stop()

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
            await self._shutdown_event.wait()
        finally:
            await self.stop()

    async def _handle_shutdown(self) -> None:
        """Handle shutdown signal."""
        logger.info("Shutdown signal received")
        self._shutdown_event.set()
