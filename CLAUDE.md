# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Workflow

Tasks are managed through **GitHub issues**. When planning new features or fixes:
1. Create a GitHub issue with description and acceptance criteria (`/issue` skill or `gh issue create`)
2. Reference the issue number in commits (`Fixes #N`)
3. Close the issue when the work is complete (`gh issue close N`)

Larger features get a design/implementation plan under `docs/plans/` (`YYYY-MM-DD-<topic>-design.md`).

Project skills in `.claude/commands/`: `/issue`, `/lint`, `/add-string`, `/add-command`, `/bump-version`, `/release`.

## Project Overview

HutWatch is a BLE (Bluetooth Low Energy) temperature monitoring system with three UI modes: Telegram bot, TUI dashboard, and console output. It reads temperature/humidity data from RuuviTag and Xiaomi LYWSD03MMC sensors, fetches weather from MET Norway API (yr.no), and stores data in SQLite. Multiple instances can sync with each other (peer sync / central hub).

**Language**: Python 3.10+ (async/await throughout)
**Platform**: Linux with Bluetooth adapter (tested Ubuntu 20.04/22.04), macOS (Core Bluetooth)
**UI Language**: Bilingual Finnish/English via `t()` translation system
**Documentation**: English (README.md), Finnish (LUEMINUT.md)

## Installation

```bash
python3 -m venv venv

# Without Telegram (console output only)
./venv/bin/pip install -e .

# With Telegram bot (also pulls matplotlib for PNG graphs)
./venv/bin/pip install -e ".[telegram]"
```

## Static Checks (there is no test suite)

There are no automated tests. Verification is the four static checks below plus running `--demo`.
Run them all with the `/lint` skill, or manually:

```bash
./venv/bin/python -m py_compile hutwatch/**/*.py scripts/*.py   # syntax
./venv/bin/python scripts/check_i18n.py                          # fi/en string keys match
./venv/bin/python scripts/check_version_sync.py                  # __init__.py == pyproject.toml
./venv/bin/python -c "from hutwatch.app import HutWatchApp"       # imports cleanly
./venv/bin/python -m hutwatch --demo                             # smoke-test the TUI
```

`.claude/hooks.json` runs these automatically as PostToolUse hooks: editing `hutwatch/strings_*` triggers
`check_i18n.py`, editing `hutwatch/__init__.py` or `pyproject.toml` triggers `check_version_sync.py`, and
any `hutwatch/**.py` edit triggers `py_compile`.

**Version lives in two files** — `hutwatch/__init__.py` (`__version__`) and `pyproject.toml` (`version`).
Always change both (use `/bump-version`); `/release` chains bump → lint → commit → tag → `gh release create`.

## Running the Application

```bash
# TUI dashboard (recommended for local use)
./venv/bin/python -m hutwatch -c config.yaml --tui

# TUI in English
./venv/bin/python -m hutwatch -c config.yaml --tui --lang en

# Demo mode (no config/BLE/network needed, in-memory SQLite)
./venv/bin/python -m hutwatch --demo

# Console output every 60s / on Enter keypress
./venv/bin/python -m hutwatch -c config.yaml --console 60
./venv/bin/python -m hutwatch -c config.yaml --console

# Telegram bot (default when telegram configured)
./venv/bin/python -m hutwatch -c config.yaml -v

# Systemd service
sudo systemctl status hutwatch
sudo journalctl -u hutwatch -f
```

Other CLI flags: `--api-port PORT` (override config `api_port`), `--show-hidden` (include hidden devices in console output).

## Architecture

```
HutWatchApp (app.py) - Main coordinator, signals, component lifecycle, alert routing
    ├── BleScanner (ble/scanner.py) - Continuous BLE scanning with always-on discovery
    │   └── SensorStore (ble/sensor_store.py) - Thread-safe 24h in-memory cache
    ├── Aggregator (aggregator.py) - 5-min sensor aggregation + 1h weather fetch,
    │                                 flushes remote readings, evaluates alerts
    ├── AlertManager (alerts.py) - Threshold rules (temperature, battery, silence),
    │                                trigger/recovery/reminder state
    ├── UI (one of, selected by CLI flags):
    │   ├── TelegramBot (telegram/bot.py) - Polling-based bot with auto-restart
    │   │   ├── CommandHandlers (telegram/commands.py) - All /command handlers
    │   │   ├── plot.py - Optional matplotlib PNG temperature graphs
    │   │   └── ReportScheduler (telegram/scheduler.py) - Periodic reports
    │   ├── TuiDashboard (tui.py) - Interactive ASCII terminal dashboard
    │   └── ConsoleReporter (console.py) - Simple periodic/keypress output
    ├── ApiServer (api.py) - aiohttp REST API + peer sync endpoint
    ├── RemotePoller (remote.py) - Polls remote sites / syncs with peers / peer watchdog
    ├── WeatherFetcher (weather.py) - MET Norway API client (1h updates + on-demand)
    └── Database (db.py) - SQLite: readings, devices, weather, settings, alerts tables
```

### Supporting Modules

- **formatting.py** — Shared utility functions used by all UI modules: `format_age()`, `format_age_long()`, `format_uptime()`, `parse_time_arg()`, `resolve_device()`, `build_remote_device_list()`, `create_ascii_graph()`, `compute_cutoff()`. Always add shared formatting/parsing logic here instead of duplicating across UI modules.
- **models.py** — Dataclasses (`SensorReading`, `DeviceInfo`, `AppConfig`, `WeatherData`, etc.) and enums (`SensorType`). Pure data layer with no internal imports.
- **demo.py** — Generates fake sensor/weather data for `--demo` mode. Uses in-memory SQLite.
- **widget_output.py** — Standalone JSON output for desktop widgets (Übersicht widget in `widget/`, SwiftBar). Reads directly from SQLite, no app instance: `python3 -m hutwatch.widget_output -d /path/to/hutwatch.db`

**Data Flow**:
1. BLE Scanner detects advertisements → Parsers extract data → SensorStore (24h cache)
2. Aggregator (every 5 min) → calculates min/max/avg → SQLite (90-day retention) → alert evaluation
3. UI commands query both SensorStore (recent) and Database (historical)

**Peer Sync Flow** (recommended for multi-site):
1. **Connector** (has `peers:` config) sends own data via `POST /api/v1/sync` to peer
2. **Listener** (has only `api_port`) receives connector's data, returns own data
3. Both sides see each other's sensors and weather — only one side needs configuration
4. Falls back to read-only `GET /api/v1/status` if peer runs an older version
5. Remote sensor readings are buffered by `RemotePoller` and flushed into the local `readings` table on the aggregator's 5-min bucket, so remote history and graphs work like local ones. Remote devices are mirrored into `devices` with a `site` column.

**Central hub mode**: a hub sets `api_port` (+ `api_token`) and `peer_watchdog`; peers push to it. The watchdog emits a Telegram/TUI alert when a peer stops syncing for `threshold_seconds` and again on recovery.

**Remote Site Flow** (legacy, read-only):
1. Local instance runs ApiServer on `api_port` → exposes JSON API
2. Remote instance runs RemotePoller → fetches data via GET, caches to SQLite `settings` table
3. One-way: remote sees local, but local doesn't see remote

**API endpoints** (api.py): `GET /api/v1/status`, `GET /api/v1/health`, `POST /api/v1/sync`.
When `api_token` is set, `/sync` requires a matching `X-HutWatch-Token` header (401 otherwise).

**Device identifiers**: local devices are addressed by order number (`1`, `2`), alias, config name, or MAC;
remote/peer devices by `r1`, `r2`, … (sequential across all remote sites). `resolve_device()` handles both
and is what every UI should call.

**UI Mode Selection** (mutually exclusive):
- `--demo` → TuiDashboard with fake data (no config/BLE/network needed, in-memory SQLite)
- `--tui` → TuiDashboard (interactive, suppresses logging)
- `--console [N]` → ConsoleReporter (keypress or timed interval)
- Neither → TelegramBot if configured, else ConsoleReporter with 30s default

## Key Design Patterns

- **Async everywhere**: All I/O is async (BLE, HTTP, Telegram polling, database)
- **Always-on discovery**: BLE scanner discovers new sensors even when sensors are pre-configured
- **Auto-restart with backoff**: BLE scanner and Telegram bot restart on failure (max 120s backoff)
- **Watchdog timeouts**: 2 min overall, 5 min per-sensor for BLE
- **Thread-safe cache**: SensorStore uses locks (BLE callback thread + aggregator)
- **Graceful shutdown**: Signal handlers (SIGINT/SIGTERM) coordinate shutdown
- **Shared formatting**: All UI modules use `formatting.py` for common logic (age formatting, device resolution, graphs, time parsing)
- **Optional dependencies degrade, never crash**: `python-telegram-bot` and `matplotlib` are import-guarded (`HAS_MATPLOTLIB`); the app must run without them

## Internationalization (i18n)

All user-facing strings are translated via a dictionary-based `t(key, **kwargs)` system. No external i18n libraries.
Use the `/add-string` skill — both files must always carry identical key sets (enforced by hook + `/lint`).

**Files:**
- `hutwatch/i18n.py` — `t()`, `init_lang()`, `wind_direction_text()` helpers
- `hutwatch/strings_fi.py` — Finnish strings
- `hutwatch/strings_en.py` — English strings (same keys)

**Key naming:** `category_description` in snake_case:
- `common_` — shared (no_data, weather default name, min/max/avg)
- `time_` — age/uptime formatting (callable lambdas for pluralization)
- `weather_` — wind directions (list), labels, precipitation
- `tg_` — Telegram messages (include Markdown formatting)
- `tui_` — TUI dashboard
- `console_` — console output
- `scheduler_` — scheduled reports
- `remote_` — remote site labels (offline, fetched ago, cached)
- `alert_` — threshold alert / peer watchdog notifications

**String value types:**
1. Plain string: `"tg_help_title": "📋 *Help*"`
2. Format template: `"tg_device_temp": "{order}. *{name}*: {temp:.1f}°C"`
3. Callable (pluralization): `"time_days": lambda n, **_: f"{n} day" if n == 1 else f"{n} days"`
4. List: `"weather_wind_directions": ["north", "northeast", ...]`

**Language selection:** `config.yaml: language: fi` (default) or `en`. CLI `--lang en` overrides config. `init_lang()` is called in `__main__.py` before loading config.

**Not translated:** log messages, CLI --help text, widget JSON keys, BLE parsers.

## Sensor Parsers

Located in `hutwatch/ble/parsers/`:
- **ruuvi.py**: RuuviTag Data Format 3 (RAWv1) and Format 5 (RAWv2)
- **xiaomi.py**: Xiaomi LYWSD03MMC with ATC or PVVX custom firmware (13 or 15-17 bytes)

Both extract manufacturer-specific data from BLE advertisement payloads.

## Database Schema (db.py)

Five tables, created on startup with `CREATE TABLE IF NOT EXISTS`:
- `readings`: 5-min aggregated sensor data, local and remote (90-day retention, auto-cleanup)
- `devices`: Device metadata with user-defined aliases, display ordering, `hidden` flag, `site` (NULL = local)
- `weather`: Historical weather observations from yr.no
- `settings`: Key-value store for runtime config (site name, weather location, remote cache)
- `alerts`: Threshold rules per (mac, alert_type), with trigger state, `unit` and `auto`

**Schema migrations** are additive `ALTER TABLE ... ADD COLUMN` calls wrapped in `try/except` (see the `hidden` and `site` columns). Follow that pattern for new columns — there is no migration framework and existing DBs must keep working.

## Alerts

Four `alert_type` values share one `alerts` table and one state machine in `AlertManager`:
`temp_low`, `temp_high`, `batt_low`, `silent`. Rules are evaluated by the aggregator's
5-minute pass; `Aggregator._build_alert_inputs()` assembles temperatures, battery levels
and last-seen times, and `HutWatchApp._format_alert()` turns each event into a message.

- **Unit-aware thresholds.** The `unit` column (`C` / `V` / `%` / `h`) says how to read and
  render `threshold`, since Ruuvi reports volts and Xiaomi percent. Use
  `formatting.format_alert_value()` for display and `formatting.resolve_alert_type()` to
  map a user-typed action (`low`, `high`, `batt`, `silent`) to a type and label.
- **Auto-provisioned rules.** `batt_low` and `silent` (`alerts.AUTO_TYPES`) are created for
  every active device from the `device_watchdog` config block. `auto = 1` marks a rule that
  still follows the config default; any user-set threshold clears it. Devices unheard from
  for more than `AUTO_RULE_MAX_AGE_DAYS` get no new rules — device rows outlive sensors,
  especially on macOS where BLE identifiers rotate.
- **`off` disables auto types, deletes the others.** Deleting an auto-provisioned rule would
  only make the next pass recreate it, so `AlertManager.remove_alert()` sets `enabled = 0`
  for those instead.
- **Reminders.** `alerts.REMINDING_TYPES` re-notify every `remind_days` while the condition
  holds, driven by `last_triggered`. Temperature alerts do not repeat.
- **Guards.** Battery checks are skipped below `cold_grace_temp` (coin-cell voltage sags in
  frost); silence checks wait `SILENCE_GRACE_SECONDS` after startup.

## Telegram Commands

Handlers live in `telegram/commands.py`, registered in `telegram/bot.py:_setup_handlers()`:
- `/temps`, `/weather`, `/status`, `/history`, `/stats`, `/graph`, `/report` — data display
- `/devices`, `/rename`, `/hide`, `/unhide`, `/showhidden` — device management
- `/alert` — temperature, battery and silence alerts
- `/menu` (also `/start`) — interactive inline keyboard buttons; callbacks go to `button_callback`
- Finnish aliases: `/laitteet`, `/nimea`, `/saa`, `/piilota`, `/nayta`, `/halytys`

`/graph` sends a matplotlib PNG when matplotlib is installed, otherwise falls back to the ASCII graph.

## TUI Dashboard Commands (tui.py)

Interactive ASCII dashboard (`--tui`). Single keys in `_INSTANT_KEYS` fire immediately; keys in `_INPUT_KEYS` open a command line:
- `h [aika]` — History (e.g., `h 6`, `h 1d`, `h 7d`)
- `s [aika]` — Stats (e.g., `s 1d`, `s 7d`)
- `g <n> [aika]` — Temperature graph (e.g., `g 1 24h`, `g r1 3d`, `g sää 7d`)
- `d` — Device list
- `a [<n> low|high|batt|silent <value>|off]` — Alert list / set / clear thresholds (arrow keys move the alert cursor)
- `hide <n>` / `unhide <n>` — Hide or unhide a device
- `f` — Toggle showing hidden devices
- `n <n> <name>` — Rename sensor (e.g., `n 1 Olohuone`)
- `p <name>` — Name the site (config `site_name` takes precedence)
- `w <place>` — Set weather location by name (geocoding via Nominatim)
- `w <lat> <lon>` — Set weather location by coordinates
- `wr` — Refresh weather now
- `t` — Toggle status section
- `y` — Toggle summary mode (inline min-max / expanded)
- `r` / Enter — Refresh / back to dashboard
- `q` — Quit

Async operations from sync command handlers use "pending action" pattern (`_pending_*` flags checked in the async run loop).

Adding a command to either UI: use the `/add-command` skill — it covers i18n keys, handler registration, shared-utility use, and doc updates.

## Utility Scripts

```bash
./venv/bin/python get_chat_id.py BOT_TOKEN  # Find Telegram chat ID
./venv/bin/python scan_all.py               # List all visible BLE devices
```

## Configuration

`config.yaml` contains:
- `language`: UI language — `fi` (default) or `en`. Can be overridden with `--lang` CLI flag.
- `site_name`: Name reported to peers/hub. Falls back to the DB value set by the TUI `p` command.
- `sensors`: List of MAC addresses with names and types (ruuvi/xiaomi). Discovery is always on — new sensors are found automatically even when some are pre-configured. Empty list `[]` uses pure auto-discovery.
- `telegram`: Bot token, chat_id, report_interval (optional — requires `pip install hutwatch[telegram]`)
- `weather`: Coordinates (latitude/longitude) and location_name (optional — can also be set from TUI, persisted to DB)
- `api_port` / `api_bind`: REST API server port and bind address (default `0.0.0.0`; use `127.0.0.1` behind nginx)
- `api_token`: Shared secret required in `X-HutWatch-Token` for `POST /api/v1/sync`
- `peers`: Bidirectional peer sync (recommended — each with `name`, `url`, `poll_interval`, optional `token`). Only the connector side needs this; the listener only needs `api_port`.
- `peer_watchdog`: `threshold_seconds` (0 disables) and `check_interval_seconds` for hub-side offline alerts
- `device_watchdog`: defaults for the auto-provisioned battery and silence alerts — `battery_voltage_low`, `battery_percent_low`, `silent_hours`, `cold_grace_temp`, `remind_days` (any threshold 0 disables that check)
- `remote_sites`: Legacy read-only remote monitoring (each with `name`, `url`, `poll_interval`, optional `token`)

Without Telegram, use `--tui` for interactive dashboard or `--console` for simple output.

See `config.example.yaml` for template.
