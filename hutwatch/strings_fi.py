"""Finnish (fi) strings for HutWatch UI."""

STRINGS: dict = {
    # ── Common ────────────────────────────────────────────────────────
    "common_no_data": "ei dataa",
    "common_no_data_md": "_ei dataa_",
    "common_no_connection": "ei yhteyttä",
    "common_no_history_md": "_ei historiaa_",
    "common_weather_default_name": "Sää",
    "common_db_not_available": "Tietokanta ei käytössä",
    "common_no_devices": "Ei laitteita",
    "common_sensor_not_found": "Anturia '{identifier}' ei löytynyt",
    "common_no_data_for_sensor": "Ei dataa anturille {name}",
    "common_no_stats_for_sensor": "Ei tilastoja anturille {name}",
    "common_no_history_for_sensor": "Ei historiaa anturille {name}",
    "common_avg_abbr": "ka",
    "common_precipitation": "sade",

    # ── Time formatting ───────────────────────────────────────────────
    "time_ago_seconds": "{n}s sitten",
    "time_ago_minutes": "{n}min sitten",
    "time_ago_hours": "{n}h sitten",
    "time_short_seconds": "{n}s",
    "time_short_minutes": "{n}min",
    "time_short_hours": "{n}h",
    "time_uptime_dhm": "{d}pv {h}h {m}min",
    "time_uptime_hm": "{h}h {m}min",
    "time_uptime_m": "{m}min",
    "time_days": lambda n, **_: f"{n} päivä" if n == 1 else f"{n} päivää",
    "time_hours": lambda n, **_: f"{n} tunti" if n == 1 else f"{n} tuntia",
    "time_ago_suffix": "{age} sitten",
    "time_fetched_ago": "haettu {age} sitten",

    # ── Weather ───────────────────────────────────────────────────────
    "weather_wind_directions": [
        "pohjoisesta", "koillisesta", "idästä", "kaakosta",
        "etelästä", "lounaasta", "lännestä", "luoteesta",
    ],
    "weather_not_configured": "Sää ei käytössä",
    "weather_not_configured_detail": "Sää ei käytössä (ei konfiguroitu)",
    "weather_not_available": "Säätietoja ei saatavilla",
    "weather_no_data": "Ei säädataa",
    "weather_temperature": "Lämpötila",
    "weather_humidity": "Kosteus",
    "weather_wind": "Tuuli",
    "weather_pressure": "Ilmanpaine",
    "weather_precipitation_1h": "Sade (1h)",
    "weather_cloud_cover": "Pilvisyys",
    "weather_precip_total": "Sade yhteensä",

    # ── Telegram: temps ───────────────────────────────────────────────
    "tg_temps_header": "🌡️ *Lämpötilat* ({timestamp})\n",

    # ── Telegram: status ──────────────────────────────────────────────
    "tg_status_header": "🔧 *Järjestelmän tila* ({timestamp})\n",
    "tg_status_sensors_label": "*Anturit:*",
    "tg_status_summary": "*Yhteenveto:* {active}/{total} anturia aktiivisia",
    "tg_status_report_on": "päällä ✅",
    "tg_status_report_off": "pois ❌",
    "tg_status_report_label": "*Ajastettu raportointi:*",
    "tg_status_uptime_label": "*Käynnissä:*",

    # ── Telegram: report ──────────────────────────────────────────────
    "tg_report_status": (
        "📬 Ajastettu raportointi on *{status}*\n\n"
        "Käyttö:\n"
        "`/report on` - ota käyttöön\n"
        "`/report off` - poista käytöstä"
    ),
    "tg_report_enabled": "✅ Ajastettu raportointi *käytössä*",
    "tg_report_disabled": "❌ Ajastettu raportointi *pois käytöstä*",
    "tg_report_unknown": "❓ Käytä: `/report on` tai `/report off`",

    # ── Telegram: devices ─────────────────────────────────────────────
    "tg_devices_header": "📱 *Laitteet* ({timestamp})\n",

    # ── Telegram: rename ──────────────────────────────────────────────
    "tg_rename_usage": (
        "Käyttö: `/rename <nro> <nimi>`\n"
        "Esim: `/rename 1 Olohuone`\n"
        "Poista alias: `/rename 1 -`"
    ),
    "tg_rename_not_found": "Laitetta '{identifier}' ei löytynyt",
    "tg_rename_success": "✅ Laite {order} nimetty: *{name}*",
    "tg_rename_cleared": "✅ Laite {order} alias poistettu",
    "tg_rename_failed": "Nimeäminen epäonnistui",

    # ── Telegram: history ─────────────────────────────────────────────
    "tg_history_header": "📈 *Historia ({time})* ({timestamp})\n",
    "tg_history_detail_header": "📈 *{name} - Historia ({time})* ({timestamp})\n",
    "tg_history_avg": "Keskiarvo",
    "tg_history_readings": "Lukemia",
    "tg_history_datapoints": "Datapisteitä",
    "tg_history_humidity_avg": "Kosteus (ka)",

    # ── Telegram: stats ───────────────────────────────────────────────
    "tg_stats_header": "📊 *Tilastot ({time})* ({timestamp})\n",
    "tg_stats_detail_header": "📊 *{name} - Tilastot ({time})* ({timestamp})\n",
    "tg_stats_temp_label": "🌡 *Lämpötila:*",
    "tg_stats_avg_label": "Keskiarvo",
    "tg_stats_humidity_label": "💧 *Kosteus (ka):*",
    "tg_stats_datapoints": "📈 Datapisteitä",
    "tg_stats_precipitation": "Sade",

    # ── Telegram: graph ───────────────────────────────────────────────
    "tg_graph_usage": (
        "Käyttö: `/graph <anturi> [aika]`\n"
        "Esim: `/graph 1 24h`, `/graph 1 7d`"
    ),
    "tg_graph_weather_hint": " tai `/graph sää`",

    # ── Telegram: weather ─────────────────────────────────────────────
    "tg_weather_header": "{emoji} *{location} - Sää* ({timestamp})\n",
    "tg_weather_temp": "🌡 *Lämpötila:*",
    "tg_weather_humidity": "💧 *Kosteus:*",
    "tg_weather_wind": "💨 *Tuuli:*",
    "tg_weather_pressure": "📊 *Ilmanpaine:*",
    "tg_weather_precipitation": "🌧 *Sade (1h):*",
    "tg_weather_cloud_cover": "☁️ *Pilvisyys:*",
    "tg_weather_24h": "📈 *24h:*",
    "tg_weather_precip_total": "🌧 *Sade yhteensä:*",

    # ── Telegram: help ────────────────────────────────────────────────
    "tg_help_full": (
        "🏠 *HutWatch v{version} - Ohje*\n"
        "\n"
        "*Peruskomennot:*\n"
        "/temps - Nykyiset lämpötilat + sää\n"
        "/status - Järjestelmän tila\n"
        "/weather - Ulkosää yksityiskohtaisesti\n"
        "/report on|off - Raportointi päälle/pois\n"
        "\n"
        "*Laitteiden hallinta:*\n"
        "/devices - Listaa laitteet numeroineen\n"
        "/rename <nro> <nimi> - Vaihda laitteen alias\n"
        "\n"
        "*Historia ja tilastot:*\n"
        "/history [anturi] [aika] - Historia + sää\n"
        "/stats [anturi] [aika] - Tilastot + sää\n"
        "/graph <anturi|sää> [aika] - ASCII-graafi\n"
        "\n"
        "*Anturin valinta:*\n"
        "Numero: `/history 1`\n"
        "Alias: `/history Olohuone`\n"
        "Nimi: `/history Ruuvi1`\n"
        "Sää: `/graph sää 48h`\n"
        "\n"
        "*Aikaformaatit:*\n"
        "`6` tai `6h` - 6 tuntia\n"
        "`7d` - 7 päivää\n"
        "\n"
        "*Esimerkkejä:*\n"
        "`/history 1 24h`\n"
        "`/stats 7d`\n"
        "`/graph 2 48h`\n"
        "`/graph sää 24h`\n"
    ),
    "tg_help_short": (
        "🏠 *HutWatch v{version} - Ohje*\n"
        "\n"
        "*Komennot:*\n"
        "/menu - Päävalikko napeilla\n"
        "/temps - Lämpötilat\n"
        "/weather - Ulkosää\n"
        "/history [aika] - Historia\n"
        "/stats [aika] - Tilastot\n"
        "\n"
        "*Aikaformaatit:*\n"
        "`6h` - 6 tuntia\n"
        "`7d` - 7 päivää"
    ),

    # ── Telegram: menu ────────────────────────────────────────────────
    "tg_menu_header": "🏠 *HutWatch*\n\nValitse toiminto:",
    "tg_menu_btn_temps": "🌡️ Lämpötilat",
    "tg_menu_btn_weather": "🌤️ Sää",
    "tg_menu_btn_history_1d": "📈 Historia 1d",
    "tg_menu_btn_history_7d": "📈 Historia 7d",
    "tg_menu_btn_stats_1d": "📊 Tilastot 1d",
    "tg_menu_btn_stats_7d": "📊 Tilastot 7d",
    "tg_menu_btn_status": "🔧 Status",
    "tg_menu_btn_help": "❓ Ohje",
    "tg_menu_btn_refresh": "🔄 Päivitä",
    "tg_menu_btn_back": "🏠 Valikko",

    # ── Telegram: shutdown ────────────────────────────────────────────
    "tg_shutdown_message": "🔴 *HutWatch pysähtyy*",

    # ── Scheduler ─────────────────────────────────────────────────────
    "scheduler_report_header": "📊 *Lämpötilaraportti* ({timestamp})\n",

    # ── TUI: view labels ──────────────────────────────────────────────
    "tui_view_history": "Historia",
    "tui_view_stats": "Tilastot",
    "tui_view_devices": "Laitteet",
    "tui_view_graph": "Graafi",

    # ── TUI: dashboard ────────────────────────────────────────────────
    "tui_temperatures": "Lämpötilat",
    "tui_no_sensor_data": "Ei anturidataa vielä...",
    "tui_24h_summary": "24h yhteenveto",

    # ── TUI: status section ───────────────────────────────────────────
    "tui_status_label": "Status",
    "tui_sensors_active": "{active}/{total} aktiivista",
    "tui_sensors_label": "Anturit:",
    "tui_sensors_not_configured": "ei konfiguroitu",
    "tui_battery": "akku",
    "tui_uptime_label": "Käynnissä:",

    # ── TUI: footer commands ──────────────────────────────────────────
    "tui_cmd_history": "[h] historia",
    "tui_cmd_stats": "[s] tilastot",
    "tui_cmd_devices": "[d] laitteet",
    "tui_cmd_graph": "[g <n>] graafi",
    "tui_cmd_status_toggle": "[t] tila",
    "tui_cmd_summary_toggle": "[y] yhteenveto",
    "tui_cmd_rename": "[n <n> <nimi>] nimeä",
    "tui_cmd_site_name": "[p <nimi>] paikka",
    "tui_cmd_weather_refresh": "[wr] päivitä sää",
    "tui_cmd_weather_set": "[w <paikka>] sää",
    "tui_cmd_quit": "[q] lopeta",
    "tui_cmd_back": "[Enter] dashboard  [r] päivitä  [q] lopeta",

    # ── TUI: history view ─────────────────────────────────────────────
    "tui_history_readings": "{n} lukemaa",
    "tui_history_datapoints": "{n} datapistettä",
    "tui_history_no_data_period": "Ei dataa valitulle ajanjaksolle",
    "tui_history_period_hint": "Aikajakso: h 6, h 1d, h 7d, h 30d",

    # ── TUI: stats view ──────────────────────────────────────────────
    "tui_stats_temp_label": "Lämpötila:",
    "tui_stats_humidity_label": "Kosteus:",
    "tui_stats_wind_label": "Tuuli:",
    "tui_stats_precip_label": "Sade:",
    "tui_stats_data_label": "Data:",
    "tui_stats_points": "{n} pistettä",
    "tui_stats_no_data_period": "Ei dataa valitulle ajanjaksolle",
    "tui_stats_period_hint": "Aikajakso: s 6h, s 1d, s 7d, s 30d",

    # ── TUI: devices view ─────────────────────────────────────────────
    "tui_devices_no_devices": "Ei laitteita",
    "tui_devices_col_num": "#",
    "tui_devices_col_name": "Nimi",
    "tui_devices_col_alias": "Alias",
    "tui_devices_col_mac": "MAC",
    "tui_devices_col_type": "Tyyppi",
    "tui_devices_rename_hint": "Nimeä: n <nro> <nimi>   Poista alias: n <nro> -",

    # ── TUI: graph view ───────────────────────────────────────────────
    "tui_graph_no_data": "Ei dataa",
    "tui_graph_period_hint": "Aikajakso: g {sensor} 6h, g {sensor} 7d",

    # ── TUI: command feedback ─────────────────────────────────────────
    "tui_status_toggle_visible": "Status-osio näkyvillä",
    "tui_status_toggle_hidden": "Status-osio piilotettu",
    "tui_summary_toggle_expanded": "Laajennettu yhteenveto näkyvillä",
    "tui_summary_toggle_inline": "Tiivistetty yhteenveto (min–max rivissä)",
    "tui_graph_usage": "Kaytto: g <anturi> [aika]  (esim. g 1, g 1 7d, g saa)",
    "tui_graph_weather_not_available": "Saa ei kaytossa",
    "tui_sensor_not_found": "Anturia '{identifier}' ei loytynyt",
    "tui_rename_usage": "Kaytto: n <nro> <nimi>  tai  n <nro> -  (tyhjenna)",
    "tui_rename_alias_cleared": "Alias poistettu: {name}",
    "tui_rename_success": "Nimetty uudelleen: {old} -> {new}",
    "tui_site_name_current": "Paikan nimi: {name}  (tyhjennä: p -)",
    "tui_site_name_usage": "Käyttö: p <nimi>  (esim. p Mökki Toivalassa)",
    "tui_site_name_cleared": "Paikan nimi poistettu",
    "tui_site_name_set": "Paikan nimi asetettu: {name}",
    "tui_weather_cmd_not_supported": "Sään asetus ei tuettu tässä tilassa",
    "tui_weather_cmd_usage": (
        "Käyttö: w <paikka>  tai  w <lat> <lon> [nimi]\n"
        "  Esim: w Toivala  tai  w 62.99 27.73 Toivala"
    ),
    "tui_weather_setting": "Asetetaan sää: {name}...",
    "tui_weather_searching": "Haetaan paikkaa: {query}...",
    "tui_weather_set": "Sää asetettu: {name} ({lat}, {lon})",
    "tui_weather_set_error": "Virhe sään asetuksessa: {error}",
    "tui_weather_refreshing": "Päivitetään sää...",
    "tui_weather_refreshed": "Sää päivitetty",
    "tui_weather_refresh_failed": "Sään päivitys epäonnistui",
    "tui_weather_error": "Virhe: {error}",
    "tui_weather_not_available": "Sää ei käytössä",
    "tui_geocode_failed": "Geokoodaus epäonnistui (HTTP {status})",
    "tui_geocode_not_found": "Paikkaa '{query}' ei löytynyt",
    "tui_geocode_error": "Geokoodausvirhe: {error}",
    "tui_unknown_command": "Tuntematon komento: {cmd}",

    # ── Remote sites ─────────────────────────────────────────────────
    "remote_offline": "ei yhteyttä",
    "remote_fetched_ago": "haettu {age} sitten",

    # ── Console ───────────────────────────────────────────────────────
    "console_no_data_yet": "Ei anturidataa vielä...",
    "console_header": "Anturilukemat ({count} anturia)",
    "console_col_sensor": "Anturi",
    "console_col_temp": "Lämpö",
    "console_col_humidity": "Kost.",
    "console_col_battery": "Akku",
    "console_col_age": "Ikä",
    "console_press_enter": "Paina Enter näyttääksesi lukemat, Ctrl+C lopettaaksesi",
}
