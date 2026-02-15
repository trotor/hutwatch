"""Console reporter for displaying sensor readings without Telegram."""

from __future__ import annotations

import asyncio
import logging
import sys
from datetime import datetime
from typing import Optional

from .ble.sensor_store import SensorStore
from .db import Database
from .i18n import t
from .models import AppConfig

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL_SECONDS = 30


class ConsoleReporter:
    """Prints sensor readings to the console.

    Supports two modes:
    - Timed mode (interval > 0): prints automatically every N seconds
    - Keypress mode (interval == 0): prints when Enter is pressed
    """

    def __init__(
        self,
        config: AppConfig,
        store: SensorStore,
        db: Database,
        interval: int = DEFAULT_INTERVAL_SECONDS,
        remote: Optional[object] = None,
    ) -> None:
        self._config = config
        self._store = store
        self._db = db
        self._interval = interval
        self._remote = remote
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Start the console reporter."""
        self._running = True

        if self._interval == 0:
            self._task = asyncio.create_task(self._run_keypress(), name="console_reporter")
            logger.info("Console reporter started (keypress mode)")
        else:
            self._task = asyncio.create_task(self._run_timed(), name="console_reporter")
            logger.info("Console reporter started (every %ds)", self._interval)

    async def stop(self) -> None:
        """Stop the console reporter."""
        self._running = False

        # Remove stdin reader if active
        try:
            loop = asyncio.get_running_loop()
            loop.remove_reader(sys.stdin)
        except (ValueError, NotImplementedError):
            pass

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _run_timed(self) -> None:
        """Print readings at a fixed interval."""
        await asyncio.sleep(5)  # Wait for initial data

        while self._running:
            try:
                self._print_readings()
            except Exception as e:
                logger.warning("Console reporter error: %s", e)

            await asyncio.sleep(self._interval)

    async def _run_keypress(self) -> None:
        """Print readings when Enter is pressed."""
        print(t("console_press_enter"))
        await asyncio.sleep(3)  # Wait for initial data

        loop = asyncio.get_running_loop()
        event = asyncio.Event()

        def _on_stdin() -> None:
            sys.stdin.readline()
            event.set()

        try:
            loop.add_reader(sys.stdin, _on_stdin)
        except NotImplementedError:
            # Fallback for platforms without add_reader (e.g. Windows)
            logger.warning("Keypress mode not supported on this platform, using 30s interval")
            await self._run_timed()
            return

        while self._running:
            event.clear()
            await event.wait()
            if self._running:
                try:
                    self._print_readings()
                except Exception as e:
                    logger.warning("Console reporter error: %s", e)

    def _print_readings(self) -> None:
        """Print current sensor readings as a formatted table."""
        readings = self._store.get_all_latest()
        if not readings:
            print(f"\n[{datetime.now().strftime('%H:%M:%S')}] {t('console_no_data_yet')}")
            return

        now = datetime.now()
        devices = self._db.get_all_devices()
        device_map = {d.mac: d for d in devices}

        # Build rows
        rows: list[tuple[str, str, str, str, str]] = []
        for mac, reading in sorted(readings.items()):
            device = device_map.get(mac)
            name = device.get_display_name() if device else mac

            temp = f"{reading.temperature:.1f}C"
            humidity = f"{reading.humidity:.0f}%" if reading.humidity is not None else "-"

            if reading.battery_percent is not None:
                battery = f"{reading.battery_percent}%"
            elif reading.battery_voltage is not None:
                battery = f"{reading.battery_voltage:.2f}V"
            else:
                battery = "-"

            age = (now - reading.timestamp).total_seconds()
            if age < 60:
                age_str = t("time_ago_seconds", n=int(age))
            else:
                age_str = t("time_ago_minutes", n=int(age / 60))

            rows.append((name, temp, humidity, battery, age_str))

        # Print table
        col_sensor = t("console_col_sensor")
        col_temp = t("console_col_temp")
        col_hum = t("console_col_humidity")
        col_batt = t("console_col_battery")
        col_age = t("console_col_age")

        name_w = max(len(r[0]) for r in rows)
        name_w = max(name_w, len(col_sensor))

        header = f"{col_sensor:<{name_w}}  {col_temp:>7}  {col_hum:>5}  {col_batt:>6}  {col_age:>7}"
        separator = "-" * len(header)

        lines = [
            "",
            f"[{now.strftime('%H:%M:%S')}] {t('console_header', count=len(rows))}",
            separator,
            header,
            separator,
        ]
        for name, temp, hum, batt, age in rows:
            lines.append(f"{name:<{name_w}}  {temp:>7}  {hum:>5}  {batt:>6}  {age:>7}")
        lines.append(separator)

        print("\n".join(lines))

        # Print remote sites
        if self._remote:
            for site_name, site_data in self._remote.get_all_site_data().items():
                self._print_remote_site(site_name, site_data)

    def _print_remote_site(self, site_name: str, site_data: object) -> None:
        """Print a remote site's sensor readings."""
        now = datetime.now()

        if not site_data.online:
            print(f"\n  [{site_data.site_name}] {t('remote_offline')}")
            return

        if not site_data.sensors:
            return

        rows: list[tuple[str, str, str, str, str]] = []
        for s in site_data.sensors:
            if s.temperature is None:
                continue

            temp = f"{s.temperature:.1f}C"
            humidity = f"{s.humidity:.0f}%" if s.humidity is not None else "-"

            if s.battery_percent is not None:
                battery = f"{s.battery_percent}%"
            elif s.battery_voltage is not None:
                battery = f"{s.battery_voltage:.2f}V"
            else:
                battery = "-"

            # Effective age = sensor age + time since fetch
            effective_age = s.age_seconds or 0
            if site_data.last_fetch:
                effective_age += (now - site_data.last_fetch).total_seconds()
            if effective_age < 60:
                age_str = t("time_ago_seconds", n=int(effective_age))
            else:
                age_str = t("time_ago_minutes", n=int(effective_age / 60))

            rows.append((s.name, temp, humidity, battery, age_str))

        if not rows:
            return

        col_sensor = t("console_col_sensor")
        col_temp = t("console_col_temp")
        col_hum = t("console_col_humidity")
        col_batt = t("console_col_battery")
        col_age = t("console_col_age")

        name_w = max(len(r[0]) for r in rows)
        name_w = max(name_w, len(col_sensor))

        fetch_info = ""
        if site_data.last_fetch:
            fetch_age = (now - site_data.last_fetch).total_seconds()
            fetch_info = f" ({t('remote_fetched_ago', age=f'{int(fetch_age)}s')})"

        header = f"{col_sensor:<{name_w}}  {col_temp:>7}  {col_hum:>5}  {col_batt:>6}  {col_age:>7}"
        separator = "-" * len(header)

        output = [
            "",
            f"[{site_data.site_name}] {len(rows)} sensors{fetch_info}",
            separator,
            header,
            separator,
        ]
        for name, temp, hum, batt, age in rows:
            output.append(f"{name:<{name_w}}  {temp:>7}  {hum:>5}  {batt:>6}  {age:>7}")
        output.append(separator)

        print("\n".join(output))
