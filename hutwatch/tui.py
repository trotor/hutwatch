"""ASCII TUI dashboard for local monitoring."""

from __future__ import annotations

import asyncio
import logging
import os
import re
import signal
import shutil
import sys
from datetime import datetime
from typing import Optional

try:
    import termios
    import tty
    _HAS_TERMIOS = True
except ImportError:
    _HAS_TERMIOS = False

from .ble.sensor_store import SensorStore
from .db import Database
from .formatting import (
    create_ascii_graph,
    format_age,
    parse_time_arg,
    resolve_device,
)
from .i18n import t, wind_direction_text
from .models import AppConfig, DeviceInfo
from .weather import WeatherFetcher, get_weather_emoji

logger = logging.getLogger(__name__)

# ANSI escape codes
CLEAR_SCREEN = "\033[2J\033[H"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"

# Refresh interval for auto-update (seconds)
AUTO_REFRESH_SECONDS = 10

# Keys that execute instantly without Enter
_INSTANT_KEYS = frozenset('qtydr')
# Keys that start input mode (may need arguments, confirmed with Enter)
_INPUT_KEYS = frozenset('hsgnpw')


def _format_age(seconds: float) -> str:
    """Format age in seconds to human-readable string."""
    return format_age(seconds)


class TuiDashboard:
    """Terminal-based dashboard showing sensor data, weather, and status.

    Views:
      dashboard  - current readings, weather, status (default)
      history    - min/max/avg per sensor over time period
      stats      - detailed statistics from database
      devices    - device list with MAC, type, alias
      graph      - ASCII temperature graph for a sensor

    Input modes:
      Instant keys (no Enter needed):
        q          - quit
        t          - toggle status section visibility
        y          - toggle summary mode (inline min-max / expanded)
        d          - devices list
        r          - refresh current view
        Enter      - refresh / back to dashboard

      Input mode (type + Enter, ESC to cancel, Backspace to edit):
        h [period] - history (e.g. h, h 1d, h 7d)
        s [period] - stats (e.g. s, s 7d)
        g <n> [period] - graph for sensor n (e.g. g 1, g 1 7d)
        n <n> <name>   - rename device (e.g. n 1 Olohuone)
        n <n> -              - clear device alias
        p <name>             - name this site (e.g. p Mökki)
        p -                  - clear site name
        w <place>            - set weather by place name (geocoding)
        w <lat> <lon> [name] - set weather by coordinates
        wr                   - refresh weather now
    """

    def __init__(
        self,
        config: AppConfig,
        store: SensorStore,
        db: Database,
        weather: Optional[WeatherFetcher] = None,
        app: Optional[object] = None,
        remote: Optional[object] = None,
    ) -> None:
        self._config = config
        self._store = store
        self._db = db
        self._weather = weather
        self._app = app  # HutWatchApp reference for dynamic setup
        self._remote = remote  # RemotePoller reference
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._start_time = datetime.now()

        # Pending async actions (set by sync command handler, executed in async loop)
        self._pending_weather: Optional[tuple[float, float, str]] = None
        self._pending_geocode: Optional[str] = None
        self._pending_weather_refresh = False

        # View state
        self._view = "dashboard"
        self._view_hours: Optional[int] = None  # for history/stats/graph
        self._view_days: Optional[int] = None
        self._graph_mac: Optional[str] = None  # for graph view
        self._graph_name: Optional[str] = None
        self._status_msg: Optional[str] = None  # one-shot feedback message
        self._show_status: bool = True  # toggle with 't' command
        self._show_summary: bool = False  # toggle with 'y': False=inline min-max, True=expanded
        self._input_mode = False  # True when building a command line
        self._input_buffer = ""   # Accumulated input in input mode
        self._old_term_settings = None  # Saved terminal settings for cbreak restore

    def set_weather(self, weather: WeatherFetcher) -> None:
        """Update weather fetcher reference (called by app after dynamic setup)."""
        self._weather = weather

    async def start(self) -> None:
        """Start the TUI dashboard."""
        self._running = True
        self._task = asyncio.create_task(self._run(), name="tui_dashboard")
        logger.info("TUI dashboard started")

    def _restore_terminal(self) -> None:
        """Restore terminal settings from cbreak mode."""
        if self._old_term_settings is not None:
            try:
                termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self._old_term_settings)
                self._old_term_settings = None
            except (termios.error, OSError):
                pass

    async def stop(self) -> None:
        """Stop the TUI dashboard."""
        self._running = False

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

        self._restore_terminal()

        # Show cursor again
        sys.stdout.write("\033[?25h")
        sys.stdout.flush()

    async def _run(self) -> None:
        """Main loop: render dashboard and handle input.

        Uses cbreak mode for instant single-key commands (q, t, y, d, r).
        Commands that take arguments (h, s, g, n, p, w) enter input mode
        where characters accumulate and Enter executes the command.
        """
        loop = asyncio.get_running_loop()
        input_event = asyncio.Event()
        input_cmd = ""
        quit_requested = False

        # Try to set cbreak mode for instant single-key commands
        cbreak_ok = False
        if _HAS_TERMIOS and sys.stdin.isatty():
            try:
                self._old_term_settings = termios.tcgetattr(sys.stdin)
                tty.setcbreak(sys.stdin.fileno())
                cbreak_ok = True
            except (termios.error, OSError):
                self._old_term_settings = None

        if cbreak_ok:
            def _on_stdin() -> None:
                nonlocal input_cmd, quit_requested
                ch = sys.stdin.read(1)
                if not ch:
                    return

                if not self._input_mode:
                    # Idle mode: single keypress handling
                    key = ch.lower()
                    if ch == '\n':
                        # Enter = refresh / back to dashboard
                        input_cmd = ""
                        input_event.set()
                    elif key == 'q':
                        quit_requested = True
                        input_event.set()
                    elif key in _INSTANT_KEYS:
                        input_cmd = key
                        input_event.set()
                    elif key in _INPUT_KEYS:
                        # Enter input mode: accumulate chars until Enter
                        self._input_mode = True
                        self._input_buffer = key
                        self._render()
                    # else: ignore unknown keys
                else:
                    # Input mode: accumulate characters, Enter to execute
                    if ch == '\n':
                        input_cmd = self._input_buffer
                        self._input_mode = False
                        self._input_buffer = ""
                        input_event.set()
                    elif ch == '\x1b':
                        # ESC = cancel input
                        self._input_mode = False
                        self._input_buffer = ""
                        self._render()
                    elif ch in ('\x7f', '\b'):
                        # Backspace
                        if len(self._input_buffer) > 1:
                            self._input_buffer = self._input_buffer[:-1]
                        else:
                            self._input_mode = False
                            self._input_buffer = ""
                        self._render()
                    elif ch >= ' ':
                        # Printable character
                        self._input_buffer += ch
                        self._render()
        else:
            # Fallback: readline-based input (no cbreak support)
            def _on_stdin() -> None:
                nonlocal input_cmd, quit_requested
                line = sys.stdin.readline().strip()
                input_cmd = line
                if line.lower() in ("q", "quit"):
                    quit_requested = True
                input_event.set()

        try:
            loop.add_reader(sys.stdin, _on_stdin)
        except NotImplementedError:
            pass

        # Hide cursor
        sys.stdout.write("\033[?25l")
        sys.stdout.flush()

        # Wait for initial data
        await asyncio.sleep(3)

        try:
            while self._running:
                self._render()
                input_event.clear()

                try:
                    await asyncio.wait_for(input_event.wait(), timeout=AUTO_REFRESH_SECONDS)
                except asyncio.TimeoutError:
                    self._status_msg = None
                    continue

                if quit_requested:
                    self._running = False
                    os.kill(os.getpid(), signal.SIGINT)
                    return

                self._handle_command(input_cmd)
                input_cmd = ""

                # Handle pending async actions
                if self._pending_geocode:
                    query = self._pending_geocode
                    self._pending_geocode = None
                    result = await self._geocode(query)
                    if result:
                        lat, lon, display_name = result
                        try:
                            await self._app.setup_weather(lat, lon, display_name)
                            self._status_msg = t("tui_weather_set", name=display_name, lat=f"{lat:.4f}", lon=f"{lon:.4f}")
                        except Exception as e:
                            self._status_msg = t("tui_weather_set_error", error=e)
                    # else: error status already set by _geocode

                if self._pending_weather_refresh:
                    self._pending_weather_refresh = False
                    try:
                        ok = await self._app.refresh_weather()
                        self._status_msg = t("tui_weather_refreshed") if ok else t("tui_weather_refresh_failed")
                    except Exception as e:
                        self._status_msg = t("tui_weather_error", error=e)

                if self._pending_weather:
                    lat, lon, name = self._pending_weather
                    self._pending_weather = None
                    try:
                        await self._app.setup_weather(lat, lon, name)
                        self._status_msg = t("tui_weather_set", name=name, lat=lat, lon=lon)
                    except Exception as e:
                        self._status_msg = t("tui_weather_set_error", error=e)
        finally:
            self._restore_terminal()

    # ── Command handling ──────────────────────────────────────────────

    def _handle_command(self, line: str) -> None:
        """Parse and execute a user command."""
        self._status_msg = None
        parts = line.split()

        if not parts:
            # Empty Enter = refresh, go back to dashboard
            self._view = "dashboard"
            return

        cmd = parts[0].lower()

        if cmd == "r":
            # Refresh current view
            return

        if cmd == "t":
            self._show_status = not self._show_status
            self._status_msg = t("tui_status_toggle_visible") if self._show_status else t("tui_status_toggle_hidden")
            return

        if cmd == "y":
            self._show_summary = not self._show_summary
            self._status_msg = t("tui_summary_toggle_expanded") if self._show_summary else t("tui_summary_toggle_inline")
            return

        if cmd == "h":
            self._view = "history"
            self._view_hours = 6
            self._view_days = None
            if len(parts) > 1:
                self._parse_time_arg(parts[1])
            return

        if cmd == "s":
            self._view = "stats"
            self._view_hours = None
            self._view_days = 1
            if len(parts) > 1:
                self._parse_time_arg(parts[1])
            return

        if cmd == "d":
            self._view = "devices"
            return

        if cmd == "g":
            self._handle_graph_cmd(parts[1:])
            return

        if cmd == "n":
            self._handle_rename_cmd(parts[1:])
            return

        if cmd == "p":
            self._handle_site_name_cmd(parts[1:])
            return

        if cmd == "w":
            self._handle_weather_cmd(parts[1:])
            return

        if cmd == "wr":
            if self._weather and self._app:
                self._pending_weather_refresh = True
                self._status_msg = t("tui_weather_refreshing")
            else:
                self._status_msg = t("tui_weather_not_available")
            return

        self._status_msg = t("tui_unknown_command", cmd=cmd)

    def _parse_time_arg(self, arg: str) -> None:
        """Parse time argument like '6', '6h', '7d' into _view_hours/_view_days."""
        hours, days = parse_time_arg(arg)
        if hours is not None or days is not None:
            self._view_hours = hours
            self._view_days = days

    def _handle_graph_cmd(self, args: list[str]) -> None:
        """Handle graph command: g <sensor_num> [period]."""
        if not args:
            self._status_msg = t("tui_graph_usage")
            return

        # Check for weather graph
        if args[0].lower() in ("saa", "sää", "weather"):
            if not self._weather:
                self._status_msg = t("tui_graph_weather_not_available")
                return
            self._view = "graph"
            self._graph_mac = None
            self._graph_name = self._weather.location_name if self._weather else t("common_weather_default_name")
            self._view_hours = 24
            self._view_days = None
            if len(args) > 1:
                self._parse_time_arg(args[1])
            return

        device = self._resolve_device(args[0])
        if not device:
            self._status_msg = t("tui_sensor_not_found", identifier=args[0])
            return

        self._view = "graph"
        self._graph_mac = device.mac
        self._graph_name = device.get_display_name()
        self._view_hours = 24
        self._view_days = None
        if len(args) > 1:
            self._parse_time_arg(args[1])

    def _handle_rename_cmd(self, args: list[str]) -> None:
        """Handle rename command: n <device_num> <new_name> or n <device_num> -."""
        if len(args) < 2:
            self._status_msg = t("tui_rename_usage")
            return

        device = self._resolve_device(args[0])
        if not device:
            self._status_msg = t("tui_sensor_not_found", identifier=args[0])
            return

        new_name = " ".join(args[1:])
        if new_name == "-":
            # Clear alias
            self._db.set_device_alias(device.mac, None)
            old_name = device.get_display_name()
            self._status_msg = t("tui_rename_alias_cleared", name=old_name)
        else:
            old_name = device.get_display_name()
            self._db.set_device_alias(device.mac, new_name)
            self._status_msg = t("tui_rename_success", old=old_name, new=new_name)

    def _handle_site_name_cmd(self, args: list[str]) -> None:
        """Handle site name command: p <name> or p - (clear)."""
        if not args:
            current = self._get_site_name()
            if current:
                self._status_msg = t("tui_site_name_current", name=current)
            else:
                self._status_msg = t("tui_site_name_usage")
            return

        name = " ".join(args)
        if name == "-":
            self._db.set_setting("site_name", "")
            self._status_msg = t("tui_site_name_cleared")
        else:
            self._db.set_setting("site_name", name)
            self._status_msg = t("tui_site_name_set", name=name)

    def _handle_weather_cmd(self, args: list[str]) -> None:
        """Handle weather location command.

        Supports:
          w <lat> <lon> [name]  - set by coordinates
          w <place name>        - search by place name (geocoding)
        """
        if not self._app:
            self._status_msg = t("tui_weather_cmd_not_supported")
            return

        if not args:
            self._status_msg = t("tui_weather_cmd_usage")
            return

        # Try to parse first two args as coordinates
        if len(args) >= 2:
            try:
                lat = float(args[0])
                lon = float(args[1])
                if (-90 <= lat <= 90) and (-180 <= lon <= 180):
                    name = " ".join(args[2:]) if len(args) > 2 else t("common_weather_default_name")
                    self._pending_weather = (lat, lon, name)
                    self._status_msg = t("tui_weather_setting", name=name)
                    return
            except ValueError:
                pass  # Not coordinates, treat as place name

        # Place name search via geocoding
        query = " ".join(args)
        self._pending_geocode = query
        self._status_msg = t("tui_weather_searching", query=query)

    async def _geocode(self, query: str) -> Optional[tuple[float, float, str]]:
        """Geocode a place name using Nominatim (OpenStreetMap).

        Returns (lat, lon, display_name) or None on failure.
        """
        import aiohttp

        url = "https://nominatim.openstreetmap.org/search"
        from . import __version__
        params = {
            "q": query,
            "format": "json",
            "limit": "1",
        }
        headers = {"User-Agent": f"HutWatch/{__version__}"}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status != 200:
                        self._status_msg = t("tui_geocode_failed", status=resp.status)
                        return None
                    results = await resp.json()

            if not results:
                self._status_msg = t("tui_geocode_not_found", query=query)
                return None

            result = results[0]
            lat = float(result["lat"])
            lon = float(result["lon"])
            display_name = result.get("display_name", query)

            # Shorten display name: take first 1-2 parts
            parts = display_name.split(", ")
            if len(parts) >= 2:
                short_name = f"{parts[0]}, {parts[1]}"
            else:
                short_name = parts[0]

            return lat, lon, short_name

        except Exception as e:
            self._status_msg = t("tui_geocode_error", error=e)
            return None

    def _resolve_device(self, identifier: str) -> Optional[DeviceInfo]:
        """Resolve device by order number, alias, config name, or MAC."""
        return resolve_device(identifier, self._db, self._config)

    # ── Shared helpers ────────────────────────────────────────────────

    def _get_ordered_devices(self) -> tuple[
        list[str],
        dict[str, "DeviceInfo"],
        dict[str, object],
    ]:
        """Get ordered MAC list, device map, and readings map."""
        readings = self._store.get_all_latest()
        devices = self._db.get_all_devices()
        device_map = {d.mac: d for d in devices}

        # Populate config names
        for d in devices:
            sensor_config = self._config.get_sensor_by_mac(d.mac)
            if sensor_config:
                d.config_name = sensor_config.name

        ordered_macs: list[str] = []
        for d in sorted(devices, key=lambda x: x.display_order):
            ordered_macs.append(d.mac)
        for mac in sorted(readings.keys()):
            if mac not in ordered_macs:
                ordered_macs.append(mac)

        return ordered_macs, device_map, readings

    def _time_str(self) -> str:
        """Get display string for current time period."""
        if self._view_days:
            return f"{self._view_days}d"
        if self._view_hours:
            return f"{self._view_hours}h"
        return "24h"

    def _effective_hours(self) -> int:
        """Get effective hours for DB queries."""
        if self._view_days:
            return self._view_days * 24
        return self._view_hours or 24

    # ── Rendering ─────────────────────────────────────────────────────

    def _render(self) -> None:
        """Render the current view."""
        cols = shutil.get_terminal_size().columns
        cols = min(cols, 140)

        lines: list[str] = []
        self._render_header(lines, cols)

        if self._view == "dashboard":
            self._render_dashboard(lines, cols)
        elif self._view == "history":
            self._render_history(lines, cols)
        elif self._view == "stats":
            self._render_stats(lines, cols)
        elif self._view == "devices":
            self._render_devices(lines, cols)
        elif self._view == "graph":
            self._render_graph(lines, cols)

        self._render_footer(lines, cols)

        output = CLEAR_SCREEN + "\n".join(lines) + "\n"
        sys.stdout.write(output)
        sys.stdout.flush()

    def _get_site_name(self) -> Optional[str]:
        """Get the configured site name from database."""
        name = self._db.get_setting("site_name")
        return name if name else None

    def _render_header(self, lines: list[str], cols: int) -> None:
        """Render common header."""
        now = datetime.now()
        from . import __version__
        site_name = self._get_site_name()
        title = f"HutWatch v{__version__} — {site_name}" if site_name else f"HutWatch v{__version__}"
        view_label = {
            "dashboard": "",
            "history": f" / {t('tui_view_history')} ({self._time_str()})",
            "stats": f" / {t('tui_view_stats')} ({self._time_str()})",
            "devices": f" / {t('tui_view_devices')}",
            "graph": f" / {t('tui_view_graph')} ({self._time_str()})",
        }.get(self._view, "")

        # Peer sync indicator
        peer_indicator = ""
        peer_indicator_visible = ""
        if self._remote:
            all_sites = self._remote.get_all_site_data()
            if all_sites:
                online = sum(1 for s in all_sites.values() if s.online)
                total = len(all_sites)
                status_text = t("remote_peers_status", online=online, total=total)
                if status_text:
                    color = GREEN if online == total else (YELLOW if online > 0 else RED)
                    peer_indicator = f" {color}{status_text}{RESET}"
                    peer_indicator_visible = f" {status_text}"

        timestamp = now.strftime("%d.%m. %H:%M:%S")
        left = f"{BOLD}{title}{RESET}{peer_indicator}{DIM}{view_label}{RESET}"
        # Calculate visible length (without ANSI codes)
        left_visible = len(title) + len(peer_indicator_visible) + len(view_label)
        padding = cols - left_visible - len(timestamp)
        lines.append(f"{left}{' ' * max(padding, 2)}{DIM}{timestamp}{RESET}")
        lines.append("=" * cols)

    def _render_footer(self, lines: list[str], cols: int) -> None:
        """Render common footer with status message and help."""
        lines.append("")
        lines.append("=" * cols)

        if self._status_msg:
            lines.append(f"  {YELLOW}{self._status_msg}{RESET}")

        if self._input_mode:
            lines.append(f"  > {self._input_buffer}█")
            return

        if self._view == "dashboard":
            cmds = [t("tui_cmd_history"), t("tui_cmd_stats"), t("tui_cmd_devices"), t("tui_cmd_graph")]
            cmds.append(t("tui_cmd_status_toggle"))
            cmds.append(t("tui_cmd_summary_toggle"))
            cmds.append(t("tui_cmd_rename"))
            cmds.append(t("tui_cmd_site_name"))
            if self._weather:
                cmds.append(t("tui_cmd_weather_refresh"))
            else:
                cmds.append(t("tui_cmd_weather_set"))
            cmds.append(t("tui_cmd_quit"))
            help_line = "  ".join(cmds)
        else:
            help_line = t("tui_cmd_back")

        lines.append(f"  {DIM}{help_line}{RESET}")

    # ── Dashboard view ────────────────────────────────────────────────

    def _render_dashboard(self, lines: list[str], cols: int) -> None:
        """Render the main dashboard with temps, weather, and status.

        Wide layout (cols >= 110): sensors+summary on left, weather+status on right.
        Narrow layout (< 110): stacked vertically as before.
        """
        now = datetime.now()
        ordered_macs, device_map, readings = self._get_ordered_devices()

        if cols >= 110:
            self._render_dashboard_wide(lines, cols, now, ordered_macs, device_map, readings)
        else:
            self._render_dashboard_narrow(lines, cols, now, ordered_macs, device_map, readings)

    def _render_sensor_lines(
        self,
        cols: int,
        now: datetime,
        ordered_macs: list[str],
        device_map: dict[str, DeviceInfo],
        readings: dict,
    ) -> list[str]:
        """Render sensor reading lines (without ANSI-aware padding)."""
        result: list[str] = []
        site_name = self._get_site_name()
        section_title = f"{t('tui_temperatures')} — {site_name}" if site_name else t("tui_temperatures")
        result.append(f"{BOLD}{section_title}{RESET}")

        if not readings:
            result.append(f"{DIM}{t('tui_no_sensor_data')}{RESET}")
        else:
            for i, mac in enumerate(ordered_macs, 1):
                reading = readings.get(mac)
                device = device_map.get(mac)
                name = device.get_display_name() if device else mac

                if reading is None:
                    result.append(f"{RED}✗{RESET} {i}. {name}: {DIM}{t('common_no_connection')}{RESET}")
                    continue

                temp = f"{reading.temperature:.1f}°C"
                humidity = (
                    f"{reading.humidity:.0f}%"
                    if reading.humidity is not None
                    else ""
                )
                age = (now - reading.timestamp).total_seconds()
                age_str = _format_age(age)

                if age < 300:
                    dot = f"{GREEN}●{RESET}"
                elif age < 600:
                    dot = f"{YELLOW}●{RESET}"
                else:
                    dot = f"{RED}●{RESET}"

                parts = [f"{dot} {i}. {name}: {BOLD}{temp}{RESET}"]
                if humidity:
                    parts.append(humidity)
                parts.append(f"{DIM}{age_str}{RESET}")

                # Inline 24h min-max when summary is not expanded
                if not self._show_summary:
                    stats = self._db.get_stats(mac, hours=24)
                    if stats:
                        parts.append(f"{DIM}↕ {stats['temp_min']:.1f}–{stats['temp_max']:.1f}{RESET}")

                result.append("  ".join(parts))

        return result

    def _render_24h_summary_lines(
        self,
        ordered_macs: list[str],
        device_map: dict[str, DeviceInfo],
    ) -> list[str]:
        """Render 24h summary as standalone lines (no leading indent)."""
        result: list[str] = []
        has_stats = False

        for i, mac in enumerate(ordered_macs, 1):
            stats = self._db.get_stats(mac, hours=24)
            if not stats:
                continue
            if not has_stats:
                has_stats = True
                result.append("")
                result.append(f"{BOLD}{t('tui_24h_summary')}{RESET}")

            device = device_map.get(mac)
            name = device.get_display_name() if device else mac
            result.append(
                f"{i}. {name}: "
                f"min {stats['temp_min']:.1f}, "
                f"max {stats['temp_max']:.1f}, "
                f"{t('common_avg_abbr')} {stats['temp_avg']:.1f}°C"
            )

        if self._weather:
            w_stats = self._db.get_weather_stats(hours=24)
            if w_stats:
                location = self._weather.location_name
                line = (
                    f"{location}: "
                    f"min {w_stats['temp_min']:.1f}, "
                    f"max {w_stats['temp_max']:.1f}, "
                    f"{t('common_avg_abbr')} {w_stats['temp_avg']:.1f}°C"
                )
                if w_stats.get("precipitation_total") and w_stats["precipitation_total"] > 0:
                    line += f", {t('common_precipitation')} {w_stats['precipitation_total']:.1f} mm"
                result.append(line)

        return result

    def _render_weather_lines(self, now: datetime) -> list[str]:
        """Render weather as standalone lines (no leading indent)."""
        result: list[str] = []
        if not self._weather:
            return result
        weather = self._weather.latest
        if not weather:
            return result

        emoji = get_weather_emoji(weather.symbol_code)
        location = self._weather.location_name

        last_fetch = self._weather.last_fetch
        if last_fetch:
            age = (now - last_fetch).total_seconds()
            fetch_str = f" {DIM}({t('time_ago_suffix', age=_format_age(age))}){RESET}"
        else:
            fetch_str = ""

        result.append(f"{BOLD}{emoji} {location}{RESET}{fetch_str}")

        label = f"{t('weather_temperature')}:"
        result.append(f"{label:<13}{BOLD}{weather.temperature:.1f}°C{RESET}")
        if weather.humidity is not None:
            label = f"{t('weather_humidity')}:"
            result.append(f"{label:<13}{weather.humidity:.0f}%")
        if weather.wind_speed is not None:
            wind_dir = wind_direction_text(weather.wind_direction)
            wind = f"{weather.wind_speed:.1f} m/s"
            if wind_dir:
                wind += f" {wind_dir}"
            label = f"{t('weather_wind')}:"
            result.append(f"{label:<13}{wind}")
        if weather.pressure is not None:
            label = f"{t('weather_pressure')}:"
            result.append(f"{label:<13}{weather.pressure:.0f} hPa")
        if weather.precipitation is not None and weather.precipitation > 0:
            label = f"{t('weather_precipitation_1h')}:"
            result.append(f"{label:<13}{weather.precipitation:.1f} mm")
        if weather.cloud_cover is not None:
            label = f"{t('weather_cloud_cover')}:"
            result.append(f"{label:<13}{weather.cloud_cover:.0f}%")

        return result

    def _render_status_lines(
        self,
        now: datetime,
        ordered_macs: list[str],
        device_map: dict[str, DeviceInfo],
        readings: dict,
    ) -> list[str]:
        """Render status section as standalone lines (no leading indent)."""
        if not self._show_status:
            return []

        result: list[str] = []
        result.append("")
        result.append(f"{BOLD}{t('tui_status_label')}{RESET}")

        active = 0
        total = len(ordered_macs)
        for mac in ordered_macs:
            reading = readings.get(mac)
            if reading:
                age = (now - reading.timestamp).total_seconds()
                if age < 600:
                    active += 1

        sensors_label = t('tui_sensors_label')
        if total > 0:
            result.append(f"{sensors_label:<13}{t('tui_sensors_active', active=active, total=total)}")
        else:
            result.append(f"{sensors_label:<13}{DIM}{t('tui_sensors_not_configured')}{RESET}")

        for mac in ordered_macs:
            reading = readings.get(mac)
            if reading is None:
                continue
            device = device_map.get(mac)
            name = device.get_display_name() if device else mac
            parts = [f"  {name}:"]
            if reading.rssi is not None:
                parts.append(f"RSSI {reading.rssi} dBm")
            if reading.battery_percent is not None:
                parts.append(f"{t('tui_battery')} {reading.battery_percent}%")
            elif reading.battery_voltage is not None:
                parts.append(f"{t('tui_battery')} {reading.battery_voltage:.2f}V")
            if len(parts) > 1:
                result.append(", ".join(parts))

        uptime = now - self._start_time
        total_secs = int(uptime.total_seconds())
        days = total_secs // 86400
        hours = (total_secs % 86400) // 3600
        mins = (total_secs % 3600) // 60

        if days > 0:
            uptime_str = t("time_uptime_dhm", d=days, h=hours, m=mins)
        elif hours > 0:
            uptime_str = t("time_uptime_hm", h=hours, m=mins)
        else:
            uptime_str = t("time_uptime_m", m=mins)

        uptime_label = t('tui_uptime_label')
        result.append(f"{uptime_label:<13}{uptime_str}")
        return result

    def _render_remote_site_lines(
        self,
        site_name: str,
        site_data: object,
        now: datetime,
    ) -> list[str]:
        """Render remote site sensor lines for wide layout."""
        result: list[str] = []
        result.append("")

        # Site header with fetch age or last seen age
        if site_data.online and site_data.last_fetch:
            fetch_age = (now - site_data.last_fetch).total_seconds()
            fetch_str = f" {DIM}({t('remote_fetched_ago', age=_format_age(fetch_age))}){RESET}"
        elif not site_data.online and site_data.last_fetch and site_data.sensors:
            last_seen_age = (now - site_data.last_fetch).total_seconds()
            fetch_str = f" {RED}({t('remote_offline')}){RESET} {DIM}({t('remote_last_seen', age=_format_age(last_seen_age))}){RESET}"
        else:
            fetch_str = ""

        # Show sync direction: ⇄ for bidirectional peer, → for read-only remote
        if self._remote and (self._remote.is_peer(site_name) or self._remote.is_incoming_peer(site_name)):
            direction = f"{GREEN}⇄{RESET} "
        else:
            direction = f"{DIM}→{RESET} "

        result.append(f"{direction}{BOLD}{site_data.site_name}{RESET}{fetch_str}")

        if not site_data.online and not site_data.sensors:
            result.append(f"{RED}{t('remote_offline')}{RESET}")
            return result

        if not site_data.sensors:
            result.append(f"{DIM}{t('tui_no_sensor_data')}{RESET}")
            return result

        for s in site_data.sensors:
            if s.temperature is None:
                result.append(f"{RED}✗{RESET} {s.order}. {s.name}: {DIM}{t('common_no_connection')}{RESET}")
                continue

            temp = f"{s.temperature:.1f}°C"
            humidity = f"{s.humidity:.0f}%" if s.humidity is not None else ""

            # Effective age = sensor age + time since last fetch
            effective_age = s.age_seconds or 0
            if site_data.last_fetch:
                effective_age += (now - site_data.last_fetch).total_seconds()
            age_str = _format_age(effective_age)

            # Force red dot when offline (cached data)
            if not site_data.online:
                dot = f"{RED}●{RESET}"
            elif effective_age < 300:
                dot = f"{GREEN}●{RESET}"
            elif effective_age < 600:
                dot = f"{YELLOW}●{RESET}"
            else:
                dot = f"{RED}●{RESET}"

            parts = [f"{dot} {s.order}. {s.name}: {BOLD}{temp}{RESET}"]
            if humidity:
                parts.append(humidity)
            parts.append(f"{DIM}{age_str}{RESET}")
            result.append("  ".join(parts))

        return result

    def _render_remote_weather_lines(
        self,
        site_data: object,
        now: datetime,
    ) -> list[str]:
        """Render remote site weather lines for wide layout."""
        result: list[str] = []
        if not site_data.weather:
            return result

        w = site_data.weather
        from .weather import get_weather_emoji
        emoji = get_weather_emoji(w.symbol_code)
        location = w.location or site_data.site_name

        cached_str = f" {DIM}({t('remote_cached')}){RESET}" if not site_data.online else ""

        result.append("")
        result.append(f"{BOLD}{emoji} {location}{RESET}{cached_str}")

        label = f"{t('weather_temperature')}:"
        result.append(f"{label:<13}{BOLD}{w.temperature:.1f}°C{RESET}")
        if w.humidity is not None:
            label = f"{t('weather_humidity')}:"
            result.append(f"{label:<13}{w.humidity:.0f}%")
        if w.wind_speed is not None:
            wind = f"{w.wind_speed:.1f} m/s"
            if w.wind_direction is not None:
                wind += f" {wind_direction_text(w.wind_direction)}"
            label = f"{t('weather_wind')}:"
            result.append(f"{label:<13}{wind}")

        return result

    @staticmethod
    def _visible_len(s: str) -> int:
        """Calculate visible length of a string (excluding ANSI escape codes)."""
        return len(re.sub(r'\033\[[0-9;]*m', '', s))

    def _render_side_by_side(
        self,
        left_lines: list[str],
        right_lines: list[str],
        cols: int,
    ) -> list[str]:
        """Merge two lists of lines side by side with a vertical separator."""
        col_width = (cols - 3) // 2  # 3 chars for " │ " separator
        result: list[str] = []
        max_rows = max(len(left_lines), len(right_lines))

        for i in range(max_rows):
            left = left_lines[i] if i < len(left_lines) else ""
            right = right_lines[i] if i < len(right_lines) else ""

            # Pad left side to col_width (accounting for ANSI codes)
            visible = self._visible_len(left)
            padding = max(col_width - visible, 0)
            result.append(f"  {left}{' ' * padding} │ {right}")

        return result

    def _render_dashboard_wide(
        self,
        lines: list[str],
        cols: int,
        now: datetime,
        ordered_macs: list[str],
        device_map: dict[str, DeviceInfo],
        readings: dict,
    ) -> None:
        """Render dashboard in wide two-column layout (cols >= 110)."""
        # Left column: all sensors (local + remote), then expanded summary if toggled
        left = self._render_sensor_lines(cols, now, ordered_macs, device_map, readings)

        # Right column: weather (local + remote) + status
        right = self._render_weather_lines(now)

        # Remote sites: sensors on left, weather on right
        if self._remote:
            for name, site_data in self._remote.get_all_site_data().items():
                left.extend(self._render_remote_site_lines(name, site_data, now))
                right.extend(self._render_remote_weather_lines(site_data, now))

        # Expanded summary below all sensors (only when toggled)
        if self._show_summary:
            left.extend(self._render_24h_summary_lines(ordered_macs, device_map))

        right.extend(self._render_status_lines(now, ordered_macs, device_map, readings))

        lines.append("")
        lines.extend(self._render_side_by_side(left, right, cols))

    def _render_dashboard_narrow(
        self,
        lines: list[str],
        cols: int,
        now: datetime,
        ordered_macs: list[str],
        device_map: dict[str, DeviceInfo],
        readings: dict,
    ) -> None:
        """Render dashboard in narrow stacked layout (cols < 110)."""
        # Sensor readings
        site_name = self._get_site_name()
        section_title = f"{t('tui_temperatures')} — {site_name}" if site_name else t("tui_temperatures")
        lines.append("")
        lines.append(f"{BOLD}  {section_title}{RESET}")
        lines.append(f"  {'-' * (cols - 4)}")

        if not readings:
            lines.append(f"  {DIM}{t('tui_no_sensor_data')}{RESET}")
        else:
            for i, mac in enumerate(ordered_macs, 1):
                reading = readings.get(mac)
                device = device_map.get(mac)
                name = device.get_display_name() if device else mac

                if reading is None:
                    lines.append(
                        f"  {RED}✗{RESET} {i}. {name}: {DIM}{t('common_no_connection')}{RESET}"
                    )
                    continue

                temp = f"{reading.temperature:.1f}°C"
                humidity = (
                    f"{reading.humidity:.0f}%"
                    if reading.humidity is not None
                    else ""
                )
                age = (now - reading.timestamp).total_seconds()
                age_str = _format_age(age)

                if age < 300:
                    status = f"{GREEN}●{RESET}"
                elif age < 600:
                    status = f"{YELLOW}●{RESET}"
                else:
                    status = f"{RED}●{RESET}"

                parts = [f"  {status} {i}. {name}: {BOLD}{temp}{RESET}"]
                if humidity:
                    parts.append(humidity)
                parts.append(f"{DIM}{age_str}{RESET}")

                # Inline 24h min-max when summary is not expanded
                if not self._show_summary:
                    stats = self._db.get_stats(mac, hours=24)
                    if stats:
                        parts.append(f"{DIM}↕ {stats['temp_min']:.1f}–{stats['temp_max']:.1f}{RESET}")

                lines.append("  ".join(parts))

        # Remote sites (sensors only, grouped with local sensors)
        if self._remote:
            for name, site_data in self._remote.get_all_site_data().items():
                remote_lines = self._render_remote_site_lines(name, site_data, now)
                for rl in remote_lines:
                    lines.append(f"  {rl}" if rl else "")

        # Expanded 24h summary (only when toggled)
        if self._show_summary:
            self._render_24h_summary(lines, cols, ordered_macs, device_map)

        # Weather (local)
        self._render_weather(lines, cols)

        # Remote weather
        if self._remote:
            for name, site_data in self._remote.get_all_site_data().items():
                remote_weather = self._render_remote_weather_lines(site_data, now)
                for rw in remote_weather:
                    lines.append(f"  {rw}" if rw else "")

        # Status
        if self._show_status:
            self._render_status(lines, cols, ordered_macs, device_map, readings, now)

    def _render_24h_summary(
        self,
        lines: list[str],
        cols: int,
        ordered_macs: list[str],
        device_map: dict[str, DeviceInfo],
    ) -> None:
        """Render 24h min/max/avg inline on the dashboard."""
        has_stats = False
        stat_lines: list[str] = []

        for i, mac in enumerate(ordered_macs, 1):
            stats = self._db.get_stats(mac, hours=24)
            if not stats:
                continue
            if not has_stats:
                has_stats = True
                stat_lines.append("")
                stat_lines.append(f"{BOLD}  {t('tui_24h_summary')}{RESET}")
                stat_lines.append(f"  {'-' * (cols - 4)}")

            device = device_map.get(mac)
            name = device.get_display_name() if device else mac
            stat_lines.append(
                f"  {i}. {name}: "
                f"min {stats['temp_min']:.1f}°C, "
                f"max {stats['temp_max']:.1f}°C, "
                f"{t('common_avg_abbr')} {stats['temp_avg']:.1f}°C"
            )

        # Weather 24h stats
        if self._weather:
            w_stats = self._db.get_weather_stats(hours=24)
            if w_stats:
                location = self._weather.location_name
                stat_line = (
                    f"  {location}: "
                    f"min {w_stats['temp_min']:.1f}°C, "
                    f"max {w_stats['temp_max']:.1f}°C, "
                    f"{t('common_avg_abbr')} {w_stats['temp_avg']:.1f}°C"
                )
                if w_stats.get("precipitation_total") and w_stats["precipitation_total"] > 0:
                    stat_line += f", {t('common_precipitation')} {w_stats['precipitation_total']:.1f} mm"
                stat_lines.append(stat_line)

        if has_stats:
            lines.extend(stat_lines)

    def _render_weather(self, lines: list[str], cols: int) -> None:
        """Render current weather section."""
        if not self._weather:
            return
        weather = self._weather.latest
        if not weather:
            return

        emoji = get_weather_emoji(weather.symbol_code)
        location = self._weather.location_name

        # Show when weather was last fetched
        last_fetch = self._weather.last_fetch
        if last_fetch:
            age = (datetime.now() - last_fetch).total_seconds()
            fetch_str = f" {DIM}({t('time_fetched_ago', age=_format_age(age))}){RESET}"
        else:
            fetch_str = ""

        lines.append("")
        lines.append(f"{BOLD}  {emoji} {location}{RESET}{fetch_str}")
        lines.append(f"  {'-' * (cols - 4)}")

        label = f"{t('weather_temperature')}:"
        lines.append(f"  {label:<13}{BOLD}{weather.temperature:.1f}°C{RESET}")

        if weather.humidity is not None:
            label = f"{t('weather_humidity')}:"
            lines.append(f"  {label:<13}{weather.humidity:.0f}%")

        if weather.wind_speed is not None:
            wind_dir = wind_direction_text(weather.wind_direction)
            wind = f"{weather.wind_speed:.1f} m/s"
            if wind_dir:
                wind += f" {wind_dir}"
            label = f"{t('weather_wind')}:"
            lines.append(f"  {label:<13}{wind}")

        if weather.pressure is not None:
            label = f"{t('weather_pressure')}:"
            lines.append(f"  {label:<13}{weather.pressure:.0f} hPa")

        if weather.precipitation is not None and weather.precipitation > 0:
            label = f"{t('weather_precipitation_1h')}:"
            lines.append(f"  {label:<13}{weather.precipitation:.1f} mm")

        if weather.cloud_cover is not None:
            label = f"{t('weather_cloud_cover')}:"
            lines.append(f"  {label:<13}{weather.cloud_cover:.0f}%")

    def _render_status(
        self,
        lines: list[str],
        cols: int,
        ordered_macs: list[str],
        device_map: dict[str, DeviceInfo],
        readings: dict,
        now: datetime,
    ) -> None:
        """Render status section with connectivity and uptime."""
        lines.append("")
        lines.append(f"{BOLD}  {t('tui_status_label')}{RESET}")
        lines.append(f"  {'-' * (cols - 4)}")

        active = 0
        total = len(ordered_macs)
        for mac in ordered_macs:
            reading = readings.get(mac)
            if reading:
                age = (now - reading.timestamp).total_seconds()
                if age < 600:
                    active += 1

        sensors_label = t('tui_sensors_label')
        if total > 0:
            lines.append(f"  {sensors_label:<13}{t('tui_sensors_active', active=active, total=total)}")
        else:
            lines.append(f"  {sensors_label:<13}{DIM}{t('tui_sensors_not_configured')}{RESET}")

        for mac in ordered_macs:
            reading = readings.get(mac)
            if reading is None:
                continue
            device = device_map.get(mac)
            name = device.get_display_name() if device else mac
            parts = [f"    {name}:"]
            if reading.rssi is not None:
                parts.append(f"RSSI {reading.rssi} dBm")
            if reading.battery_percent is not None:
                parts.append(f"{t('tui_battery')} {reading.battery_percent}%")
            elif reading.battery_voltage is not None:
                parts.append(f"{t('tui_battery')} {reading.battery_voltage:.2f}V")
            if len(parts) > 1:
                lines.append(", ".join(parts))

        # Uptime
        uptime = now - self._start_time
        total_secs = int(uptime.total_seconds())
        days = total_secs // 86400
        hours = (total_secs % 86400) // 3600
        mins = (total_secs % 3600) // 60

        if days > 0:
            uptime_str = t("time_uptime_dhm", d=days, h=hours, m=mins)
        elif hours > 0:
            uptime_str = t("time_uptime_hm", h=hours, m=mins)
        else:
            uptime_str = t("time_uptime_m", m=mins)

        uptime_label = t('tui_uptime_label')
        lines.append(f"  {uptime_label:<13}{uptime_str}")

    # ── History view ──────────────────────────────────────────────────

    def _render_history(self, lines: list[str], cols: int) -> None:
        """Render history view with min/max/avg per sensor."""
        ordered_macs, device_map, readings = self._get_ordered_devices()

        lines.append("")
        lines.append(f"{BOLD}  {t('tui_view_history')} ({self._time_str()}){RESET}")
        lines.append(f"  {'-' * (cols - 4)}")

        hours = self._effective_hours()
        has_data = False

        for i, mac in enumerate(ordered_macs, 1):
            device = device_map.get(mac)
            name = device.get_display_name() if device else mac

            # Try in-memory data for short periods
            if hours <= 24:
                sensor_readings = self._store.get_history(mac)
                if sensor_readings:
                    temps = [r.temperature for r in sensor_readings]
                    lines.append(
                        f"  {i}. {BOLD}{name}{RESET}: "
                        f"min {min(temps):.1f}°C, "
                        f"max {max(temps):.1f}°C, "
                        f"{t('common_avg_abbr')} {sum(temps)/len(temps):.1f}°C "
                        f"{DIM}({t('tui_history_readings', n=len(temps))}){RESET}"
                    )
                    has_data = True
                    continue

            # Fall back to database
            stats = self._db.get_stats(
                mac,
                hours=self._view_hours,
                days=self._view_days,
            )
            if stats:
                lines.append(
                    f"  {i}. {BOLD}{name}{RESET}: "
                    f"min {stats['temp_min']:.1f}°C, "
                    f"max {stats['temp_max']:.1f}°C, "
                    f"{t('common_avg_abbr')} {stats['temp_avg']:.1f}°C "
                    f"{DIM}({t('tui_history_datapoints', n=stats['sample_count'])}){RESET}"
                )
                has_data = True
            else:
                lines.append(
                    f"  {i}. {name}: {DIM}{t('common_no_data')}{RESET}"
                )

        # Weather history
        if self._weather:
            w_stats = self._db.get_weather_stats(
                hours=self._view_hours,
                days=self._view_days,
            )
            if w_stats:
                location = self._weather.location_name
                line = (
                    f"  {get_weather_emoji(None)} {BOLD}{location}{RESET}: "
                    f"min {w_stats['temp_min']:.1f}°C, "
                    f"max {w_stats['temp_max']:.1f}°C, "
                    f"{t('common_avg_abbr')} {w_stats['temp_avg']:.1f}°C"
                )
                if w_stats.get("precipitation_total") and w_stats["precipitation_total"] > 0:
                    line += f", {t('common_precipitation')} {w_stats['precipitation_total']:.1f} mm"
                lines.append(line)
                has_data = True

        if not has_data:
            lines.append(f"  {DIM}{t('tui_history_no_data_period')}{RESET}")

        lines.append("")
        lines.append(f"  {DIM}{t('tui_history_period_hint')}{RESET}")

    # ── Stats view ────────────────────────────────────────────────────

    def _render_stats(self, lines: list[str], cols: int) -> None:
        """Render detailed statistics view."""
        ordered_macs, device_map, _ = self._get_ordered_devices()

        lines.append("")
        lines.append(f"{BOLD}  {t('tui_view_stats')} ({self._time_str()}){RESET}")
        lines.append(f"  {'-' * (cols - 4)}")

        has_data = False

        for i, mac in enumerate(ordered_macs, 1):
            device = device_map.get(mac)
            name = device.get_display_name() if device else mac

            stats = self._db.get_stats(
                mac,
                hours=self._view_hours,
                days=self._view_days,
            )
            if not stats:
                lines.append(f"  {i}. {name}: {DIM}{t('common_no_data')}{RESET}")
                continue

            has_data = True
            lines.append(f"  {i}. {BOLD}{name}{RESET}:")
            lines.append(
                f"     {t('tui_stats_temp_label')}  min {stats['temp_min']:.1f}°C, "
                f"max {stats['temp_max']:.1f}°C, "
                f"{t('common_avg_abbr')} {stats['temp_avg']:.1f}°C"
            )
            if stats.get("humidity_avg") is not None:
                lines.append(f"     {t('tui_stats_humidity_label')}    {t('common_avg_abbr')} {stats['humidity_avg']:.0f}%")
            lines.append(
                f"     {t('tui_stats_data_label')}       {t('tui_stats_points', n=stats['sample_count'])}"
            )

        # Weather stats
        if self._weather:
            w_stats = self._db.get_weather_stats(
                hours=self._view_hours,
                days=self._view_days,
            )
            if w_stats:
                has_data = True
                location = self._weather.location_name
                lines.append(f"  {get_weather_emoji(None)} {BOLD}{location}{RESET}:")
                lines.append(
                    f"     {t('tui_stats_temp_label')}  min {w_stats['temp_min']:.1f}°C, "
                    f"max {w_stats['temp_max']:.1f}°C, "
                    f"{t('common_avg_abbr')} {w_stats['temp_avg']:.1f}°C"
                )
                if w_stats.get("humidity_avg") is not None:
                    lines.append(f"     {t('tui_stats_humidity_label')}    {t('common_avg_abbr')} {w_stats['humidity_avg']:.0f}%")
                if w_stats.get("wind_avg") is not None:
                    lines.append(f"     {t('tui_stats_wind_label')}      {t('common_avg_abbr')} {w_stats['wind_avg']:.1f} m/s")
                if w_stats.get("precipitation_total") and w_stats["precipitation_total"] > 0:
                    lines.append(f"     {t('tui_stats_precip_label')}       {w_stats['precipitation_total']:.1f} mm")

        if not has_data:
            lines.append(f"  {DIM}{t('tui_stats_no_data_period')}{RESET}")

        lines.append("")
        lines.append(f"  {DIM}{t('tui_stats_period_hint')}{RESET}")

    # ── Devices view ──────────────────────────────────────────────────

    def _render_devices(self, lines: list[str], cols: int) -> None:
        """Render device list with MAC, type, alias, and order."""
        devices = self._db.get_all_devices()

        lines.append("")
        lines.append(f"{BOLD}  {t('tui_view_devices')}{RESET}")
        lines.append(f"  {'-' * (cols - 4)}")

        if not devices:
            lines.append(f"  {DIM}{t('tui_devices_no_devices')}{RESET}")
        else:
            # Column headers
            lines.append(
                f"  {DIM}{t('tui_devices_col_num'):<4}{t('tui_devices_col_name'):<16}{t('tui_devices_col_alias'):<16}{t('tui_devices_col_mac'):<20}{t('tui_devices_col_type'):<8}{RESET}"
            )
            lines.append(f"  {DIM}{'-' * (cols - 4)}{RESET}")

            for d in sorted(devices, key=lambda x: x.display_order):
                sensor_config = self._config.get_sensor_by_mac(d.mac)
                config_name = sensor_config.name if sensor_config else "-"
                alias = d.alias or "-"
                order = str(d.display_order)
                sensor_type = d.sensor_type or "-"

                lines.append(
                    f"  {order:<4}{config_name:<16}{alias:<16}{d.mac:<20}{sensor_type:<8}"
                )

        lines.append("")
        lines.append(f"  {DIM}{t('tui_devices_rename_hint')}{RESET}")

    # ── Graph view ────────────────────────────────────────────────────

    def _render_graph(self, lines: list[str], cols: int) -> None:
        """Render ASCII temperature graph for a sensor or weather."""
        name = self._graph_name or "?"
        hours = self._effective_hours()

        if self._graph_mac:
            data = self._db.get_graph_data(self._graph_mac, hours)
        else:
            # Weather graph
            data = self._db.get_weather_graph_data(hours)

        lines.append("")
        lines.append(f"{BOLD}  {name} - {t('tui_view_graph')} ({self._time_str()}){RESET}")
        lines.append(f"  {'-' * (cols - 4)}")

        if not data:
            lines.append(f"  {DIM}{t('tui_graph_no_data')}{RESET}")
            lines.append("")
            sensor_hint = self._graph_mac or "saa"
            lines.append(f"  {DIM}{t('tui_graph_period_hint', sensor=sensor_hint)}{RESET}")
            return

        # Determine graph dimensions
        graph_width = min(cols - 14, 60)  # leave room for labels
        if hours <= 24:
            graph_width = min(graph_width, 24)
        elif hours <= 72:
            graph_width = min(graph_width, 36)
        else:
            graph_width = min(graph_width, 48)
        graph_height = 8

        graph_str, timeline = self._create_ascii_graph(data, graph_width, graph_height)
        temps = [v for _, v in data]

        # Indent the graph
        for graph_line in graph_str.split("\n"):
            lines.append(f"  {graph_line}")
        lines.append(f"  {timeline}")

        lines.append("")
        lines.append(
            f"  Min: {BOLD}{min(temps):.1f}°C{RESET} | "
            f"Max: {BOLD}{max(temps):.1f}°C{RESET} | "
            f"{t('common_avg_abbr').capitalize()}: {BOLD}{sum(temps)/len(temps):.1f}°C{RESET}"
        )
        lines.append("")
        sensor_hint = self._graph_mac or "saa"
        lines.append(f"  {DIM}{t('tui_graph_period_hint', sensor=sensor_hint)}{RESET}")

    def _create_ascii_graph(
        self,
        data: list[tuple[datetime, float]],
        width: int = 24,
        height: int = 8,
    ) -> tuple[str, str]:
        """Create ASCII art graph from data points."""
        return create_ascii_graph(
            data, width, height, no_data_message=t("tui_graph_no_data")
        )
