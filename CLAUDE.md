# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

HutWatch is a BLE (Bluetooth Low Energy) temperature monitoring system with Telegram integration. It reads temperature/humidity data from RuuviTag and Xiaomi LYWSD03MMC sensors, fetches weather from MET Norway API (yr.no), stores data in SQLite, and sends reports via Telegram.

**Language**: Python 3.10+ (async/await throughout)
**Platform**: Linux with Bluetooth adapter (tested Ubuntu 20.04/22.04)
**UI Language**: Finnish (all Telegram messages and some commands)

## Running the Application

```bash
# Manual execution with verbose logging
./venv/bin/python -m hutwatch -c config.yaml -v

# Systemd service
sudo systemctl status hutwatch
sudo journalctl -u hutwatch -f
```

## Architecture

```
HutWatchApp (app.py) - Main coordinator, signals, component lifecycle
    ├── BleScanner (ble/scanner.py) - Continuous BLE scanning with auto-restart
    │   └── SensorStore (ble/sensor_store.py) - Thread-safe 24h in-memory cache
    ├── Aggregator (aggregator.py) - 5-min periodic aggregation to SQLite
    ├── TelegramBot (telegram/bot.py) - Polling-based bot with auto-restart
    │   ├── CommandHandlers (telegram/commands.py) - All /command handlers
    │   └── ReportScheduler (telegram/scheduler.py) - Periodic reports
    ├── WeatherFetcher (weather.py) - MET Norway API client (10-min updates)
    └── Database (db.py) - SQLite: readings, devices, weather tables
```

**Data Flow**:
1. BLE Scanner detects advertisements → Parsers extract data → SensorStore (24h cache)
2. Aggregator (every 5 min) → calculates min/max/avg → SQLite (90-day retention)
3. Telegram commands query both SensorStore (recent) and Database (historical)

## Key Design Patterns

- **Async everywhere**: All I/O is async (BLE, HTTP, Telegram polling, database)
- **Auto-restart with backoff**: BLE scanner and Telegram bot restart on failure (max 120s backoff)
- **Watchdog timeouts**: 2 min overall, 5 min per-sensor for BLE
- **Thread-safe cache**: SensorStore uses locks (BLE callback thread + aggregator)
- **Graceful shutdown**: Signal handlers (SIGINT/SIGTERM) coordinate shutdown

## Sensor Parsers

Located in `hutwatch/ble/parsers/`:
- **ruuvi.py**: RuuviTag Data Format 3 (RAWv1) and Format 5 (RAWv2)
- **xiaomi.py**: Xiaomi LYWSD03MMC with ATC or PVVX custom firmware (13 or 15-17 bytes)

Both extract manufacturer-specific data from BLE advertisement payloads.

## Database Schema (db.py)

Three tables:
- `readings`: 5-min aggregated sensor data (90-day retention, auto-cleanup)
- `devices`: Device metadata with user-defined aliases and display ordering
- `weather`: Historical weather observations from yr.no

## Telegram Commands

Main commands in `telegram/commands.py`:
- `/temps`, `/weather`, `/status`, `/history`, `/stats`, `/graph` - Data display
- `/devices`, `/rename` - Device management
- `/menu` - Interactive inline keyboard buttons
- Finnish aliases: `/laitteet`, `/nimea`, `/saa`

Device resolution supports: order number (1, 2), alias, or config name.

## Utility Scripts

```bash
./venv/bin/python get_chat_id.py BOT_TOKEN  # Find Telegram chat ID
./venv/bin/python scan_all.py               # List all visible BLE devices
```

## Configuration

`config.yaml` contains:
- `sensors`: List of MAC addresses with names and types (ruuvi/xiaomi)
- `telegram`: Bot token, chat_id, report_interval
- `weather`: Coordinates (latitude/longitude) and location_name

See `config.example.yaml` for template.
