"""Main application coordinator."""

from __future__ import annotations

import asyncio
import logging
import signal
from pathlib import Path
from typing import Optional

from .aggregator import Aggregator
from .api import ApiServer, build_status_payload
from .ble.scanner import BleScanner
from .ble.sensor_store import SensorStore
from .config import load_config
from .console import ConsoleReporter
from .db import Database
from .i18n import t
from .models import AppConfig, WeatherConfig
from .remote import RemotePoller
from .tui import TuiDashboard
from .weather import WeatherFetcher

try:
    from .telegram.bot import TelegramBot

    _HAS_TELEGRAM = True
except ImportError:
    TelegramBot = None  # type: ignore[assignment,misc]
    _HAS_TELEGRAM = False

logger = logging.getLogger(__name__)


class HutWatchApp:
    """Main application that coordinates all components."""

    def __init__(
        self,
        config_path: Path,
        db_path: Optional[Path] = None,
        console_interval: Optional[int] = None,
        use_tui: bool = False,
        api_port: Optional[int] = None,
    ) -> None:
        self._config_path = config_path
        self._db_path = db_path or config_path.parent / "hutwatch.db"
        self._console_interval = console_interval
        self._use_tui = use_tui
        self._api_port = api_port
        self._config: Optional[AppConfig] = None
        self._store: Optional[SensorStore] = None
        self._db: Optional[Database] = None
        self._scanner: Optional[BleScanner] = None
        self._aggregator: Optional[Aggregator] = None
        self._weather: Optional[WeatherFetcher] = None
        self._bot: Optional["TelegramBot"] = None
        self._console: Optional[ConsoleReporter] = None
        self._tui: Optional[TuiDashboard] = None
        self._api: Optional[ApiServer] = None
        self._remote: Optional[RemotePoller] = None
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
        if not self._config.weather:
            # Try loading weather location from database
            lat_str = self._db.get_setting("weather_lat")
            lon_str = self._db.get_setting("weather_lon")
            if lat_str and lon_str:
                try:
                    name = self._db.get_setting("weather_name") or t("common_weather_default_name")
                    self._config.weather = WeatherConfig(
                        latitude=float(lat_str),
                        longitude=float(lon_str),
                        location_name=name,
                    )
                    logger.info("Weather location loaded from database")
                except ValueError:
                    pass

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
        self._scanner = BleScanner(self._config, self._store, db=self._db)
        self._aggregator = Aggregator(self._config, self._store, self._db, self._weather)

        # Start API server if configured (CLI --api-port wins over config)
        api_port = self._api_port or self._config.api_port
        if api_port:
            self._api = ApiServer(self._config, self._store, self._db, self._weather, api_port)
            await self._api.start()

        # Start remote poller if remote_sites, peers, or api_port configured
        # (api_port alone enables receiving incoming peer sync requests)
        needs_remote = bool(self._config.remote_sites) or bool(self._config.peers) or bool(api_port)
        if needs_remote:
            def _build_local_status() -> dict:
                return build_status_payload(self._config, self._store, self._db, self._weather)

            self._remote = RemotePoller(
                remote_sites=self._config.remote_sites,
                peers=self._config.peers,
                db=self._db,
                local_status_fn=_build_local_status,
            )
            await self._remote.start()

            # Connect API server to remote poller for incoming sync
            if self._api:
                self._api.set_remote_poller(self._remote)

        # Determine local mode (--console or --tui skip Telegram)
        _local_mode = self._use_tui or self._console_interval is not None

        if not _local_mode and self._config.telegram and _HAS_TELEGRAM:
            self._bot = TelegramBot(self._config, self._store, self._db, self._weather, remote=self._remote)
        elif _local_mode and self._config.telegram:
            logger.info("Local mode active, skipping Telegram bot")
        elif self._config.telegram and not _HAS_TELEGRAM:
            logger.warning(
                "Telegram configured but python-telegram-bot not installed. "
                "Install with: pip install hutwatch[telegram]"
            )

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
        else:
            # No Telegram — use TUI or console output
            if self._use_tui:
                self._tui = TuiDashboard(
                    self._config, self._store, self._db, self._weather,
                    app=self, remote=self._remote,
                )
                await self._tui.start()
            else:
                interval = self._console_interval if self._console_interval is not None else 30
                self._console = ConsoleReporter(
                    self._config, self._store, self._db, interval=interval,
                    remote=self._remote,
                )
                await self._console.start()

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
                await self._bot.send_message(t("tg_shutdown_message"))
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

        # Stop remote poller and API server first
        if self._remote:
            await self._remote.stop()

        if self._api:
            await self._api.stop()

        # Stop components in reverse order
        if self._tui:
            await self._tui.stop()

        if self._console:
            await self._console.stop()

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

    async def setup_weather(self, lat: float, lon: float, name: str = "") -> None:
        """Set up weather fetching dynamically (e.g. from TUI)."""
        if not name:
            name = t("common_weather_default_name")
        weather_config = WeatherConfig(latitude=lat, longitude=lon, location_name=name)
        self._config.weather = weather_config

        self._weather = WeatherFetcher(weather_config)
        await self._weather.start()

        # Tell aggregator to start periodic weather fetching
        if self._aggregator:
            self._aggregator.set_weather(self._weather)

        # Update TUI reference
        if self._tui:
            self._tui.set_weather(self._weather)

        # Update API server reference
        if self._api:
            self._api.set_weather(self._weather)

        # Persist to database for next startup
        if self._db:
            self._db.set_setting("weather_lat", str(lat))
            self._db.set_setting("weather_lon", str(lon))
            self._db.set_setting("weather_name", name)

        logger.info("Weather configured for %s (%.4f, %.4f)", name, lat, lon)

    async def refresh_weather(self) -> bool:
        """Fetch weather on demand. Returns True if successful."""
        if self._aggregator:
            return await self._aggregator.fetch_weather_now()
        return False

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
