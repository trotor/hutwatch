# HutWatch

> English | **[Suomi](LUEMINUT.md)**

BLE temperature monitoring with a Telegram bot and terminal UI. Reads temperature/humidity data from RuuviTag and Xiaomi LYWSD03MMC sensors, fetches outdoor weather from yr.no, and displays data via Telegram, an ASCII dashboard, or console output.

![TUI Dashboard](resources/tui-dashboard.png)

## Features

- RuuviTag (Data Format 3/5) support
- Xiaomi LYWSD03MMC (ATC/PVVX custom firmware) support
- Continuous auto-discovery: new sensors are found automatically even when some are pre-configured
- Outdoor weather from MET Norway API (yr.no), updated hourly
- **Multi-site monitoring**: built-in API server and remote polling — monitor multiple locations (e.g. home + cabin) over Tailscale or VPN
- **Three UI modes:**
  - **Telegram bot**: `/temps`, `/weather`, `/history`, `/stats`, `/graph`, `/menu`
  - **TUI dashboard**: interactive ASCII terminal view (temperatures, weather, stats, graphs, device management)
  - **Console output**: simple table output at intervals or on keypress
- **Summary mode**: toggleable 24h min-max display — compact inline or expanded statistics
- SQLite database for long-term history
- 24h in-memory cache + 90-day database history
- Site naming and weather location setting from TUI (persisted to database)
- Bilingual UI: Finnish (default) and English — set via config or `--lang` flag
- Systemd service

## Requirements

- Python 3.10+
- Bluetooth adapter (BLE support)
- Linux (tested on Ubuntu 20.04/22.04) or macOS

## Installation

```bash
# Clone the repo
git clone https://github.com/trotor/hutwatch.git
cd hutwatch

# Create a virtual environment
python3 -m venv venv

# Install — choose one:
./venv/bin/pip install -e .              # Without Telegram
./venv/bin/pip install -e ".[telegram]"  # With Telegram bot

# Copy and edit configuration
cp config.example.yaml config.yaml
nano config.yaml
```

> **Note:** If you are upgrading an existing installation with Telegram enabled,
> make sure to install the `.[telegram]` extra. A plain `pip install -e .` will
> not install the Telegram package.

## Configuration

Edit `config.yaml`:

```yaml
# UI language: fi (Finnish, default) or en (English)
# Can also be set with --lang CLI flag
# language: fi

# Empty list = auto-discovery only
# Listed sensors + auto-discovery: new sensors are still found automatically
sensors: []

# Or list sensors manually:
# sensors:
#   - mac: "AA:BB:CC:DD:EE:FF"
#     name: "Outdoor"
#     type: ruuvi
#   - mac: "11:22:33:44:55:66"
#     name: "Indoor"
#     type: xiaomi

# Telegram bot (optional — requires pip install hutwatch[telegram])
# Without Telegram, use console output or TUI.
# telegram:
#   token: "YOUR_BOT_TOKEN"
#   chat_id: YOUR_CHAT_ID
#   report_interval: 3600

# Outdoor weather from yr.no (optional — can also be set from TUI)
# weather:
#   latitude: 60.1699
#   longitude: 24.9384
#   location_name: "Helsinki"

# API server for remote site sharing (optional)
# Exposes sensor data as JSON on the given port.
# api_port: 8099

# Remote HutWatch instances to monitor (optional)
# Fetches sensor/weather data from other HutWatch API servers.
# remote_sites:
#   - name: "Cabin"
#     url: "http://100.64.0.2:8099"
#     poll_interval: 30
```

### Creating a Telegram Bot

1. Open Telegram and find `@BotFather`
2. Send `/newbot` and follow the instructions
3. Copy the token to your config.yaml

### Finding Your Chat ID

1. Send a message to your bot in Telegram
2. Run:
```bash
./venv/bin/python -c "
import asyncio
from telegram import Bot
bot = Bot('YOUR_TOKEN')
updates = asyncio.run(bot.get_updates())
for u in updates:
    if u.message:
        print(f'chat_id: {u.message.chat.id}')
"
```

## Usage

### TUI Dashboard (recommended for local use)

```bash
./venv/bin/python -m hutwatch -c config.yaml --tui
```

Interactive ASCII dashboard with the following commands:

| Command | Action |
|---------|--------|
| `h [time]` | History (e.g., `h 6`, `h 1d`, `h 7d`) |
| `s [time]` | Statistics (e.g., `s 1d`, `s 7d`) |
| `g <n> [time]` | Temperature graph (e.g., `g 1 24h`, `g weather 7d`) |
| `d` | Device list |
| `n <n> <name>` | Rename sensor (e.g., `n 1 Living room`) |
| `p <name>` | Name the site (e.g., `p Cabin`) |
| `w <place>` | Set weather location (e.g., `w Helsinki`) |
| `w <lat> <lon>` | Set weather by coordinates |
| `wr` | Refresh weather now |
| `t` | Toggle status section |
| `y` | Toggle summary mode (inline min-max / expanded 24h stats) |
| `r` / Enter | Refresh / back to dashboard |
| `q` | Quit |

Weather location and site name are stored in the database and persist across restarts.

### Demo Mode

Try the TUI without any hardware, config, or network — uses fake sensor data in-memory:

```bash
./venv/bin/python -m hutwatch --demo          # Finnish
./venv/bin/python -m hutwatch --demo --lang en # English
```

### Console Output

```bash
# Print every 60s (skip Telegram)
./venv/bin/python -m hutwatch -c config.yaml --console 60

# Print on Enter keypress
./venv/bin/python -m hutwatch -c config.yaml --console

# Default (no Telegram): print every 30s
./venv/bin/python -m hutwatch -c config.yaml -v
```

### Telegram Bot

```bash
./venv/bin/python -m hutwatch -c config.yaml -v
```

### Systemd Service

```bash
sudo cp hutwatch.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now hutwatch

sudo systemctl status hutwatch
sudo journalctl -u hutwatch -f
```

## Telegram Commands

### Basic Commands

| Command | Description |
|---------|-------------|
| `/menu` | Interactive menu with buttons |
| `/temps` | All sensor temperatures + weather |
| `/weather` | Detailed weather conditions |
| `/status` | System status |
| `/help` | Help |

### History and Statistics

| Command | Description |
|---------|-------------|
| `/history` | Temperature history (6h default) |
| `/history 24h` | 24-hour history |
| `/history 7d` | 7-day history |
| `/stats 1d` | Daily statistics (min/max/avg) |
| `/graph 1 24h` | ASCII graph for sensor 1 |
| `/graph sää 48h` | Weather temperature graph |

### Device Management

| Command | Description |
|---------|-------------|
| `/devices` | List devices with numbers |
| `/rename 1 Living room` | Rename device 1 |
| `/report on/off` | Toggle scheduled reports |

## Interactive Menu

The `/menu` or `/start` command opens an interactive menu with inline buttons:

- Temperatures and weather in one tap
- History 1d / 7d / 30d
- Statistics 1d / 7d / 30d
- Refresh button in every view

## Multi-Site Monitoring (Remote Sites)

HutWatch can monitor multiple locations by connecting instances over a network (e.g. Tailscale or VPN). Each site runs its own HutWatch with a built-in API server, and a central instance polls data from all remote sites.

### How It Works

1. **API server**: Each HutWatch instance can expose its sensor and weather data as JSON via a built-in HTTP API (`/api/v1/status`).
2. **Remote poller**: A HutWatch instance can poll one or more remote API servers and display their data alongside local sensors.

### Example: Home + Cabin

**Cabin** (remote site) — runs HutWatch with the API server enabled:

```yaml
# config.yaml on cabin
sensors: []
api_port: 8099
```

```bash
./venv/bin/python -m hutwatch -c config.yaml --tui
```

**Home** (central site) — polls the cabin over Tailscale:

```yaml
# config.yaml at home
sensors: []
api_port: 8099

remote_sites:
  - name: "Cabin"
    url: "http://100.64.0.2:8099"   # Tailscale IP of cabin
    poll_interval: 30
```

The TUI dashboard and console output show remote site sensors and weather alongside local data. The API port can also be set via the `--api-port` CLI flag.

## macOS: Background Service and Desktop Widget

### Background Service with launchd

Native macOS service management. Starts automatically on login and restarts on failure.

1. Create `~/Library/LaunchAgents/com.hutwatch.agent.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.hutwatch.agent</string>
    <key>ProgramArguments</key>
    <array>
        <string>/path/to/hutwatch/venv/bin/python3</string>
        <string>-m</string>
        <string>hutwatch</string>
        <string>-c</string>
        <string>/path/to/hutwatch/config.yaml</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/path/to/hutwatch</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/path/to/hutwatch/logs/hutwatch.log</string>
    <key>StandardErrorPath</key>
    <string>/path/to/hutwatch/logs/hutwatch.err</string>
</dict>
</plist>
```

2. Enable:

```bash
mkdir -p logs
launchctl load ~/Library/LaunchAgents/com.hutwatch.agent.plist
```

3. Management:

```bash
# Check status
launchctl list | grep hutwatch

# Stop
launchctl unload ~/Library/LaunchAgents/com.hutwatch.agent.plist

# Restart
launchctl unload ~/Library/LaunchAgents/com.hutwatch.agent.plist
launchctl load ~/Library/LaunchAgents/com.hutwatch.agent.plist

# Follow logs
tail -f logs/hutwatch.log
```

### Übersicht Desktop Widget

[Übersicht](https://tracesof.net/uebersicht/) is a free macOS app that displays HTML/JS widgets on the desktop.

1. Install Übersicht: https://tracesof.net/uebersicht/
2. Copy the widget:

```bash
cp -r widget/hutwatch.widget "$HOME/Library/Application Support/Übersicht/widgets/"
```

3. Edit the paths in `index.jsx` (lines 7-8) to match your installation
4. The widget updates automatically every 30 seconds

Widget data is produced by:

```bash
./venv/bin/python -m hutwatch.widget_output -d hutwatch.db
```

## Xiaomi Sensor Firmware

Xiaomi LYWSD03MMC requires custom firmware to broadcast BLE advertisements:

- [ATC firmware](https://github.com/atc1441/ATC_MiThermometer)
- [PVVX firmware](https://github.com/pvvx/ATC_MiThermometer)

Flashing can be done in the browser: https://pvvx.github.io/ATC_MiThermometer/TelinkMiFlasher.html

## License

MIT
