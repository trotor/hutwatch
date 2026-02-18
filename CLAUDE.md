# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Workflow

Tasks are managed through **GitHub issues**. When planning new features or fixes:
1. Create a GitHub issue with description and acceptance criteria (`/issue` skill or `gh issue create`)
2. Reference the issue number in commits (`Fixes #N`)
3. Close the issue when the work is complete (`gh issue close N`)

Use `/lint` skill to run all static checks before committing.

## Project Overview

HutWatch is a BLE (Bluetooth Low Energy) temperature monitoring system with three UI modes: Telegram bot, TUI dashboard, and console output. It reads temperature/humidity data from RuuviTag and Xiaomi LYWSD03MMC sensors, fetches weather from MET Norway API (yr.no), and stores data in SQLite.

**Language**: Python 3.10+ (async/await throughout)
**Platform**: Linux with Bluetooth adapter (tested Ubuntu 20.04/22.04), macOS (Core Bluetooth)
**UI Language**: Bilingual Finnish/English via `t()` translation system
**Documentation**: English (README.md), Finnish (LUEMINUT.md)

## Installation

```bash
python3 -m venv venv

# Without Telegram (console output only)
./venv/bin/pip install -e .

# With Telegram bot
./venv/bin/pip install -e ".[telegram]"
```

## Running the Application

```bash
# TUI dashboard (recommended for local use)
./venv/bin/python -m hutwatch -c config.yaml --tui

# TUI in English
./venv/bin/python -m hutwatch -c config.yaml --tui --lang en

# Demo mode (no config/BLE/network needed)
./venv/bin/python -m hutwatch --demo

# Console output every 60s
./venv/bin/python -m hutwatch -c config.yaml --console 60

# Console output on Enter keypress
./venv/bin/python -m hutwatch -c config.yaml --console

# Telegram bot (default when telegram configured)
./venv/bin/python -m hutwatch -c config.yaml -v

# Systemd service
sudo systemctl status hutwatch
sudo journalctl -u hutwatch -f
```

## Architecture

```
HutWatchApp (app.py) - Main coordinator, signals, component lifecycle
    ├── BleScanner (ble/scanner.py) - Continuous BLE scanning with always-on discovery
    │   └── SensorStore (ble/sensor_store.py) - Thread-safe 24h in-memory cache
    ├── Aggregator (aggregator.py) - 5-min sensor aggregation + 1h weather fetch
    ├── UI (one of, selected by CLI flags):
    │   ├── TelegramBot (telegram/bot.py) - Polling-based bot with auto-restart
    │   │   ├── CommandHandlers (telegram/commands.py) - All /command handlers
    │   │   └── ReportScheduler (telegram/scheduler.py) - Periodic reports
    │   ├── TuiDashboard (tui.py) - Interactive ASCII terminal dashboard
    │   └── ConsoleReporter (console.py) - Simple periodic/keypress output
    ├── ApiServer (api.py) - aiohttp REST API + peer sync endpoint
    ├── RemotePoller (remote.py) - Polls remote sites / syncs with peers
    ├── WeatherFetcher (weather.py) - MET Norway API client (1h updates + on-demand)
    └── Database (db.py) - SQLite: readings, devices, weather, settings tables
```

### Supporting Modules

- **formatting.py** — Shared utility functions used by all UI modules: `format_age()`, `format_age_long()`, `format_uptime()`, `parse_time_arg()`, `resolve_device()`, `create_ascii_graph()`, `compute_cutoff()`. Always add shared formatting/parsing logic here instead of duplicating across UI modules.
- **models.py** — Dataclasses (`SensorReading`, `DeviceInfo`, `AppConfig`, `WeatherData`, etc.) and enums (`SensorType`). Pure data layer with no internal imports.
- **demo.py** — Generates fake sensor/weather data for `--demo` mode. Uses in-memory SQLite.
- **widget_output.py** — Standalone JSON output for desktop widgets (Übersicht, SwiftBar). Reads directly from SQLite: `python3 -m hutwatch.widget_output -d /path/to/hutwatch.db`

**Data Flow**:
1. BLE Scanner detects advertisements → Parsers extract data → SensorStore (24h cache)
2. Aggregator (every 5 min) → calculates min/max/avg → SQLite (90-day retention)
3. UI commands query both SensorStore (recent) and Database (historical)

**Peer Sync Flow** (recommended for multi-site):
1. **Connector** (has `peers:` config) sends own data via `POST /api/v1/sync` to peer
2. **Listener** (has only `api_port`) receives connector's data, returns own data
3. Both sides see each other's sensors and weather — only one side needs configuration
4. Falls back to read-only `GET /api/v1/status` if peer runs an older version

**Remote Site Flow** (legacy, read-only):
1. Local instance runs ApiServer on `api_port` → exposes JSON API
2. Remote instance runs RemotePoller → fetches data via GET, caches to SQLite `settings` table
3. One-way: remote sees local, but local doesn't see remote

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

## Internationalization (i18n)

All user-facing strings are translated via a dictionary-based `t(key, **kwargs)` system. No external i18n libraries.

**Files:**
- `hutwatch/i18n.py` — `t()`, `init_lang()`, `wind_direction_text()` helpers
- `hutwatch/strings_fi.py` — Finnish strings (~180 keys)
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

Four tables:
- `readings`: 5-min aggregated sensor data (90-day retention, auto-cleanup)
- `devices`: Device metadata with user-defined aliases and display ordering
- `weather`: Historical weather observations from yr.no
- `settings`: Key-value store for runtime config (site name, weather location, remote cache)

## Telegram Commands

Main commands in `telegram/commands.py`:
- `/temps`, `/weather`, `/status`, `/history`, `/stats`, `/graph` - Data display
- `/devices`, `/rename` - Device management
- `/menu` - Interactive inline keyboard buttons
- Finnish aliases: `/laitteet`, `/nimea`, `/saa`

Device resolution supports: order number (1, 2), alias, or config name.

## TUI Dashboard Commands (tui.py)

Interactive ASCII dashboard (`--tui`):
- `h [aika]` — History (e.g., `h 6`, `h 1d`, `h 7d`)
- `s [aika]` — Stats (e.g., `s 1d`, `s 7d`)
- `g <n> [aika]` — Temperature graph (e.g., `g 1 24h`, `g sää 7d`)
- `d` — Device list
- `n <n> <name>` — Rename sensor (e.g., `n 1 Olohuone`)
- `p <name>` — Name the site (e.g., `p Mökki`)
- `w <place>` — Set weather location by name (geocoding via Nominatim)
- `w <lat> <lon>` — Set weather location by coordinates
- `wr` — Refresh weather now
- `t` — Toggle status section
- `y` — Toggle summary mode (inline min-max / expanded)
- `r` / Enter — Refresh / back to dashboard
- `q` — Quit

Async operations from sync command handlers use "pending action" pattern (flags checked in async run loop).

## Utility Scripts

```bash
./venv/bin/python get_chat_id.py BOT_TOKEN  # Find Telegram chat ID
./venv/bin/python scan_all.py               # List all visible BLE devices
```

## Configuration

`config.yaml` contains:
- `language`: UI language — `fi` (default) or `en`. Can be overridden with `--lang` CLI flag.
- `sensors`: List of MAC addresses with names and types (ruuvi/xiaomi). Discovery is always on — new sensors are found automatically even when some are pre-configured. Empty list `[]` uses pure auto-discovery.
- `telegram`: Bot token, chat_id, report_interval (optional — requires `pip install hutwatch[telegram]`)
- `weather`: Coordinates (latitude/longitude) and location_name (optional — can also be set from TUI, persisted to DB)
- `api_port`: Port for the REST API server (optional — enables peer sync and remote sharing, e.g., `8099`)
- `peers`: Bidirectional peer sync (recommended — each with `name`, `url`, `poll_interval`). Only the connector side needs this; the listener only needs `api_port`.
- `remote_sites`: Legacy read-only remote monitoring (each with `name`, `url`, `poll_interval`)

Without Telegram, use `--tui` for interactive dashboard or `--console` for simple output.

See `config.example.yaml` for template.
