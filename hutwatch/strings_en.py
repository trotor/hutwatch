"""English (en) strings for HutWatch UI."""

STRINGS: dict = {
    # ── Common ────────────────────────────────────────────────────────
    "common_no_data": "no data",
    "common_no_data_md": "_no data_",
    "common_no_connection": "no connection",
    "common_no_history_md": "_no history_",
    "common_weather_default_name": "Weather",
    "common_db_not_available": "Database not available",
    "common_no_devices": "No devices",
    "common_sensor_not_found": "Sensor '{identifier}' not found",
    "common_no_data_for_sensor": "No data for sensor {name}",
    "common_no_stats_for_sensor": "No statistics for sensor {name}",
    "common_no_history_for_sensor": "No history for sensor {name}",
    "common_avg_abbr": "avg",
    "common_precipitation": "precip",

    # ── Time formatting ───────────────────────────────────────────────
    "time_ago_seconds": "{n}s ago",
    "time_ago_minutes": "{n}min ago",
    "time_ago_hours": "{n}h ago",
    "time_short_seconds": "{n}s",
    "time_short_minutes": "{n}min",
    "time_short_hours": "{n}h",
    "time_uptime_dhm": "{d}d {h}h {m}min",
    "time_uptime_hm": "{h}h {m}min",
    "time_uptime_m": "{m}min",
    "time_days": lambda n, **_: f"{n} day" if n == 1 else f"{n} days",
    "time_hours": lambda n, **_: f"{n} hour" if n == 1 else f"{n} hours",
    "time_ago_suffix": "{age} ago",
    "time_fetched_ago": "fetched {age} ago",

    # ── Weather ───────────────────────────────────────────────────────
    "weather_wind_directions": [
        "from the north", "from the northeast",
        "from the east", "from the southeast",
        "from the south", "from the southwest",
        "from the west", "from the northwest",
    ],
    "weather_not_configured": "Weather not enabled",
    "weather_not_configured_detail": "Weather not enabled (not configured)",
    "weather_not_available": "Weather data not available",
    "weather_no_data": "No weather data",
    "weather_temperature": "Temperature",
    "weather_humidity": "Humidity",
    "weather_wind": "Wind",
    "weather_pressure": "Pressure",
    "weather_precipitation_1h": "Precip (1h)",
    "weather_cloud_cover": "Cloud cover",
    "weather_precip_total": "Total precipitation",

    # ── Telegram: temps ───────────────────────────────────────────────
    "tg_temps_header": "🌡️ *Temperatures* ({timestamp})\n",

    # ── Telegram: status ──────────────────────────────────────────────
    "tg_status_header": "🔧 *System Status* ({timestamp})\n",
    "tg_status_sensors_label": "*Sensors:*",
    "tg_status_summary": "*Summary:* {active}/{total} sensors active",
    "tg_status_report_on": "on ✅",
    "tg_status_report_off": "off ❌",
    "tg_status_report_label": "*Scheduled reports:*",
    "tg_status_uptime_label": "*Uptime:*",

    # ── Telegram: report ──────────────────────────────────────────────
    "tg_report_status": (
        "📬 Scheduled reports are *{status}*\n\n"
        "Usage:\n"
        "`/report on` - enable\n"
        "`/report off` - disable"
    ),
    "tg_report_enabled": "✅ Scheduled reports *enabled*",
    "tg_report_disabled": "❌ Scheduled reports *disabled*",
    "tg_report_unknown": "❓ Usage: `/report on` or `/report off`",

    # ── Telegram: devices ─────────────────────────────────────────────
    "tg_devices_header": "📱 *Devices* ({timestamp})\n",

    # ── Telegram: rename ──────────────────────────────────────────────
    "tg_rename_usage": (
        "Usage: `/rename <num> <name>`\n"
        "Example: `/rename 1 Living room`\n"
        "Remove alias: `/rename 1 -`"
    ),
    "tg_rename_not_found": "Device '{identifier}' not found",
    "tg_rename_success": "✅ Device {order} renamed: *{name}*",
    "tg_rename_cleared": "✅ Device {order} alias removed",
    "tg_rename_failed": "Rename failed",

    # ── Telegram: history ─────────────────────────────────────────────
    "tg_history_header": "📈 *History ({time})* ({timestamp})\n",
    "tg_history_detail_header": "📈 *{name} - History ({time})* ({timestamp})\n",
    "tg_history_avg": "Average",
    "tg_history_readings": "Readings",
    "tg_history_datapoints": "Data points",
    "tg_history_humidity_avg": "Humidity (avg)",

    # ── Telegram: stats ───────────────────────────────────────────────
    "tg_stats_header": "📊 *Statistics ({time})* ({timestamp})\n",
    "tg_stats_detail_header": "📊 *{name} - Statistics ({time})* ({timestamp})\n",
    "tg_stats_temp_label": "🌡 *Temperature:*",
    "tg_stats_avg_label": "Average",
    "tg_stats_humidity_label": "💧 *Humidity (avg):*",
    "tg_stats_datapoints": "📈 Data points",
    "tg_stats_precipitation": "Precipitation",

    # ── Telegram: graph ───────────────────────────────────────────────
    "tg_graph_usage": (
        "Usage: `/graph <sensor> [time]`\n"
        "Example: `/graph 1 24h`, `/graph 1 7d`"
    ),
    "tg_graph_weather_hint": " or `/graph weather`",

    # ── Telegram: weather ─────────────────────────────────────────────
    "tg_weather_header": "{emoji} *{location} - Weather* ({timestamp})\n",
    "tg_weather_temp": "🌡 *Temperature:*",
    "tg_weather_humidity": "💧 *Humidity:*",
    "tg_weather_wind": "💨 *Wind:*",
    "tg_weather_pressure": "📊 *Pressure:*",
    "tg_weather_precipitation": "🌧 *Precip (1h):*",
    "tg_weather_cloud_cover": "☁️ *Cloud cover:*",
    "tg_weather_24h": "📈 *24h:*",
    "tg_weather_precip_total": "🌧 *Total precipitation:*",

    # ── Telegram: help ────────────────────────────────────────────────
    "tg_help_full": (
        "🏠 *HutWatch v{version} - Help*\n"
        "\n"
        "*Basic commands:*\n"
        "/temps - Current temperatures + weather\n"
        "/status - System status\n"
        "/weather - Outdoor weather details\n"
        "/report on|off - Toggle scheduled reports\n"
        "\n"
        "*Device management:*\n"
        "/devices - List devices with numbers\n"
        "/rename <num> <name> - Set device alias\n"
        "\n"
        "*History and statistics:*\n"
        "/history [sensor] [time] - History + weather\n"
        "/stats [sensor] [time] - Statistics + weather\n"
        "/graph <sensor|weather> [time] - ASCII graph\n"
        "\n"
        "*Sensor selection:*\n"
        "Number: `/history 1`\n"
        "Alias: `/history Living room`\n"
        "Name: `/history Ruuvi1`\n"
        "Weather: `/graph weather 48h`\n"
        "\n"
        "*Time formats:*\n"
        "`6` or `6h` - 6 hours\n"
        "`7d` - 7 days\n"
        "\n"
        "*Examples:*\n"
        "`/history 1 24h`\n"
        "`/stats 7d`\n"
        "`/graph 2 48h`\n"
        "`/graph weather 24h`\n"
    ),
    "tg_help_short": (
        "🏠 *HutWatch v{version} - Help*\n"
        "\n"
        "*Commands:*\n"
        "/menu - Main menu with buttons\n"
        "/temps - Temperatures\n"
        "/weather - Outdoor weather\n"
        "/history [time] - History\n"
        "/stats [time] - Statistics\n"
        "\n"
        "*Time formats:*\n"
        "`6h` - 6 hours\n"
        "`7d` - 7 days"
    ),

    # ── Telegram: menu ────────────────────────────────────────────────
    "tg_menu_header": "🏠 *HutWatch*\n\nChoose an action:",
    "tg_menu_btn_temps": "🌡️ Temperatures",
    "tg_menu_btn_weather": "🌤️ Weather",
    "tg_menu_btn_history_1d": "📈 History 1d",
    "tg_menu_btn_history_7d": "📈 History 7d",
    "tg_menu_btn_stats_1d": "📊 Stats 1d",
    "tg_menu_btn_stats_7d": "📊 Stats 7d",
    "tg_menu_btn_status": "🔧 Status",
    "tg_menu_btn_help": "❓ Help",
    "tg_menu_btn_refresh": "🔄 Refresh",
    "tg_menu_btn_back": "🏠 Menu",

    # ── Telegram: shutdown ────────────────────────────────────────────
    "tg_shutdown_message": "🔴 *HutWatch shutting down*",

    # ── Scheduler ─────────────────────────────────────────────────────
    "scheduler_report_header": "📊 *Temperature Report* ({timestamp})\n",

    # ── TUI: view labels ──────────────────────────────────────────────
    "tui_view_history": "History",
    "tui_view_stats": "Statistics",
    "tui_view_devices": "Devices",
    "tui_view_graph": "Graph",

    # ── TUI: dashboard ────────────────────────────────────────────────
    "tui_temperatures": "Temperatures",
    "tui_no_sensor_data": "No sensor data yet...",
    "tui_24h_summary": "24h summary",

    # ── TUI: status section ───────────────────────────────────────────
    "tui_status_label": "Status",
    "tui_sensors_active": "{active}/{total} active",
    "tui_sensors_label": "Sensors:",
    "tui_sensors_not_configured": "not configured",
    "tui_battery": "batt",
    "tui_uptime_label": "Uptime:",

    # ── TUI: footer commands ──────────────────────────────────────────
    "tui_cmd_history": "[h] history",
    "tui_cmd_stats": "[s] stats",
    "tui_cmd_devices": "[d] devices",
    "tui_cmd_graph": "[g <n>] graph",
    "tui_cmd_status_toggle": "[t] status",
    "tui_cmd_summary_toggle": "[y] summary",
    "tui_cmd_rename": "[n <n> <name>] rename",
    "tui_cmd_site_name": "[p <name>] site",
    "tui_cmd_weather_refresh": "[wr] refresh weather",
    "tui_cmd_weather_set": "[w <place>] weather",
    "tui_cmd_quit": "[q] quit",
    "tui_cmd_back": "[Enter] dashboard  [r] refresh  [q] quit",

    # ── TUI: history view ─────────────────────────────────────────────
    "tui_history_readings": "{n} readings",
    "tui_history_datapoints": "{n} data points",
    "tui_history_no_data_period": "No data for selected time period",
    "tui_history_period_hint": "Time period: h 6, h 1d, h 7d, h 30d",

    # ── TUI: stats view ──────────────────────────────────────────────
    "tui_stats_temp_label": "Temperature:",
    "tui_stats_humidity_label": "Humidity:",
    "tui_stats_wind_label": "Wind:",
    "tui_stats_precip_label": "Precip:",
    "tui_stats_data_label": "Data:",
    "tui_stats_points": "{n} points",
    "tui_stats_no_data_period": "No data for selected time period",
    "tui_stats_period_hint": "Time period: s 6h, s 1d, s 7d, s 30d",

    # ── TUI: devices view ─────────────────────────────────────────────
    "tui_devices_no_devices": "No devices",
    "tui_devices_col_num": "#",
    "tui_devices_col_name": "Name",
    "tui_devices_col_alias": "Alias",
    "tui_devices_col_mac": "MAC",
    "tui_devices_col_type": "Type",
    "tui_devices_rename_hint": "Rename: n <num> <name>   Clear alias: n <num> -",

    # ── TUI: graph view ───────────────────────────────────────────────
    "tui_graph_no_data": "No data",
    "tui_graph_period_hint": "Time period: g {sensor} 6h, g {sensor} 7d",

    # ── TUI: command feedback ─────────────────────────────────────────
    "tui_status_toggle_visible": "Status section visible",
    "tui_status_toggle_hidden": "Status section hidden",
    "tui_summary_toggle_expanded": "Expanded summary visible",
    "tui_summary_toggle_inline": "Compact summary (min–max inline)",
    "tui_graph_usage": "Usage: g <sensor> [time]  (e.g. g 1, g 1 7d, g weather)",
    "tui_graph_weather_not_available": "Weather not available",
    "tui_sensor_not_found": "Sensor '{identifier}' not found",
    "tui_rename_usage": "Usage: n <num> <name>  or  n <num> -  (clear)",
    "tui_rename_alias_cleared": "Alias removed: {name}",
    "tui_rename_success": "Renamed: {old} -> {new}",
    "tui_site_name_current": "Site name: {name}  (clear: p -)",
    "tui_site_name_usage": "Usage: p <name>  (e.g. p Lake Cabin)",
    "tui_site_name_cleared": "Site name removed",
    "tui_site_name_set": "Site name set: {name}",
    "tui_weather_cmd_not_supported": "Weather setup not supported in this mode",
    "tui_weather_cmd_usage": (
        "Usage: w <place>  or  w <lat> <lon> [name]\n"
        "  e.g. w Helsinki  or  w 60.17 24.94 Helsinki"
    ),
    "tui_weather_setting": "Setting weather: {name}...",
    "tui_weather_searching": "Searching for: {query}...",
    "tui_weather_set": "Weather set: {name} ({lat}, {lon})",
    "tui_weather_set_error": "Error setting weather: {error}",
    "tui_weather_refreshing": "Refreshing weather...",
    "tui_weather_refreshed": "Weather updated",
    "tui_weather_refresh_failed": "Weather refresh failed",
    "tui_weather_error": "Error: {error}",
    "tui_weather_not_available": "Weather not enabled",
    "tui_geocode_failed": "Geocoding failed (HTTP {status})",
    "tui_geocode_not_found": "Place '{query}' not found",
    "tui_geocode_error": "Geocoding error: {error}",
    "tui_unknown_command": "Unknown command: {cmd}",

    # ── Remote sites ─────────────────────────────────────────────────
    "remote_offline": "offline",
    "remote_fetched_ago": "fetched {age} ago",

    # ── Console ───────────────────────────────────────────────────────
    "console_no_data_yet": "No sensor data yet...",
    "console_header": "Sensor Readings ({count} sensors)",
    "console_col_sensor": "Sensor",
    "console_col_temp": "Temp",
    "console_col_humidity": "Hum",
    "console_col_battery": "Batt",
    "console_col_age": "Age",
    "console_press_enter": "Press Enter to show readings, Ctrl+C to quit",
}
