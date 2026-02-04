"""Telegram bot command handlers."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from ..ble.sensor_store import SensorStore
from ..models import AppConfig, DeviceInfo

if TYPE_CHECKING:
    from ..db import Database
    from ..weather import WeatherFetcher

logger = logging.getLogger(__name__)


def _format_timestamp() -> str:
    """Format current timestamp for display."""
    return datetime.now().strftime("%d.%m. %H:%M")


# Wind direction to Finnish text
def _wind_direction_text(degrees: Optional[float]) -> str:
    """Convert wind direction degrees to Finnish text."""
    if degrees is None:
        return ""
    directions = [
        "pohjoisesta", "koillisesta", "idästä", "kaakosta",
        "etelästä", "lounaasta", "lännestä", "luoteesta"
    ]
    index = int((degrees + 22.5) / 45) % 8
    return directions[index]


class CommandHandlers:
    """Telegram command handlers."""

    def __init__(
        self,
        config: AppConfig,
        store: SensorStore,
        db: Optional["Database"] = None,
        weather: Optional["WeatherFetcher"] = None,
    ) -> None:
        self._config = config
        self._store = store
        self._db = db
        self._weather = weather
        self._reports_enabled = False
        self._start_time = datetime.now()

    def _get_devices_with_config_names(self) -> list[DeviceInfo]:
        """Get all devices with config names populated."""
        if not self._db:
            return []

        devices = self._db.get_all_devices()
        for device in devices:
            sensor_config = self._config.get_sensor_by_mac(device.mac)
            if sensor_config:
                device.config_name = sensor_config.name
        return devices

    def _resolve_device(self, identifier: str) -> Optional[DeviceInfo]:
        """Resolve device by order number, alias, config name, or MAC.

        Returns DeviceInfo with config_name populated if found.
        """
        if not self._db:
            return None

        # Try as order number first
        if identifier.isdigit():
            device = self._db.get_device_by_order(int(identifier))
            if device:
                sensor_config = self._config.get_sensor_by_mac(device.mac)
                if sensor_config:
                    device.config_name = sensor_config.name
                return device

        # Get all devices to search
        devices = self._get_devices_with_config_names()

        # Search by alias (case-insensitive)
        for device in devices:
            if device.alias and device.alias.lower() == identifier.lower():
                return device

        # Search by config name (case-insensitive)
        for device in devices:
            if device.config_name and device.config_name.lower() == identifier.lower():
                return device

        # Search by MAC address (case-insensitive)
        identifier_upper = identifier.upper()
        for device in devices:
            if device.mac == identifier_upper:
                return device

        return None

    @property
    def reports_enabled(self) -> bool:
        """Check if scheduled reports are enabled."""
        return self._reports_enabled

    @reports_enabled.setter
    def reports_enabled(self, value: bool) -> None:
        """Set scheduled reports state."""
        self._reports_enabled = value

    async def temps(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Handle /temps command - show current temperatures."""
        if not update.effective_message:
            return

        lines = [f"🌡️ *Lämpötilat* ({_format_timestamp()})\n"]

        # Use device ordering if database is available
        if self._db:
            devices = self._get_devices_with_config_names()
            for device in devices:
                reading = self._store.get_latest(device.mac)
                name = device.get_display_name()

                if reading:
                    age = datetime.now() - reading.timestamp
                    age_str = self._format_age(age)

                    line = f"{device.display_order}. *{name}*: {reading.temperature:.1f}°C"
                    if reading.humidity is not None:
                        line += f", {reading.humidity:.0f}%"
                    line += f" _{age_str}_"
                else:
                    line = f"{device.display_order}. *{name}*: _ei dataa_"

                lines.append(line)
        else:
            # Fallback to config-based ordering
            for sensor_config in self._config.sensors:
                reading = self._store.get_latest(sensor_config.mac)

                if reading:
                    age = datetime.now() - reading.timestamp
                    age_str = self._format_age(age)

                    line = f"*{sensor_config.name}*: {reading.temperature:.1f}°C"
                    if reading.humidity is not None:
                        line += f", {reading.humidity:.0f}%"
                    line += f" _{age_str}_"
                else:
                    line = f"*{sensor_config.name}*: _ei dataa_"

                lines.append(line)

        # Add weather info if available
        if self._weather and self._weather.latest:
            from ..weather import get_weather_emoji

            w = self._weather.latest
            emoji = get_weather_emoji(w.symbol_code)
            lines.append("")
            lines.append(f"{emoji} *{self._weather.location_name}*: {w.temperature:.1f}°C")

        await update.effective_message.reply_text(
            "\n".join(lines),
            parse_mode="Markdown",
        )

    async def status(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Handle /status command - show system status."""
        if not update.effective_message:
            return

        lines = [f"🔧 *Järjestelmän tila* ({_format_timestamp()})\n"]

        # Sensor status
        lines.append("*Anturit:*")

        # Use device ordering if database is available
        if self._db:
            devices = self._get_devices_with_config_names()
            active = 0
            for device in devices:
                reading = self._store.get_latest(device.mac)
                name = device.get_display_name()
                status_emoji = "✅" if reading else "❌"

                if reading:
                    active += 1
                    age = datetime.now() - reading.timestamp
                    if age > timedelta(minutes=10):
                        status_emoji = "⚠️"

                    info = f"{reading.temperature:.1f}°C"
                    if reading.rssi is not None:
                        info += f", RSSI: {reading.rssi} dBm"
                    if reading.battery_voltage is not None:
                        info += f", {reading.battery_voltage:.2f}V"
                    elif reading.battery_percent is not None:
                        info += f", {reading.battery_percent}%"

                    lines.append(f"  {status_emoji} {device.display_order}. {name}: {info}")
                else:
                    lines.append(f"  {status_emoji} {device.display_order}. {name}: ei yhteyttä")

            total = len(devices)
        else:
            # Fallback to config-based ordering
            for sensor_config in self._config.sensors:
                reading = self._store.get_latest(sensor_config.mac)
                status_emoji = "✅" if reading else "❌"

                if reading:
                    age = datetime.now() - reading.timestamp
                    if age > timedelta(minutes=10):
                        status_emoji = "⚠️"

                    info = f"{reading.temperature:.1f}°C"
                    if reading.rssi is not None:
                        info += f", RSSI: {reading.rssi} dBm"
                    if reading.battery_voltage is not None:
                        info += f", {reading.battery_voltage:.2f}V"
                    elif reading.battery_percent is not None:
                        info += f", {reading.battery_percent}%"

                    lines.append(f"  {status_emoji} {sensor_config.name}: {info}")
                else:
                    lines.append(f"  {status_emoji} {sensor_config.name}: ei yhteyttä")

            total = len(self._config.sensors)
            active = len([
                s for s in self._config.sensors
                if self._store.get_latest(s.mac) is not None
            ])

        lines.append(f"\n*Yhteenveto:* {active}/{total} anturia aktiivisia")

        # Report status
        report_status = "päällä ✅" if self._reports_enabled else "pois ❌"
        lines.append(f"*Ajastettu raportointi:* {report_status}")

        # Uptime
        uptime = datetime.now() - self._start_time
        uptime_str = self._format_uptime(uptime)
        lines.append(f"*Käynnissä:* {uptime_str}")

        await update.effective_message.reply_text(
            "\n".join(lines),
            parse_mode="Markdown",
        )

    async def report(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Handle /report command - toggle scheduled reports."""
        if not update.effective_message:
            return

        args = context.args or []

        if not args:
            status = "päällä ✅" if self._reports_enabled else "pois ❌"
            await update.effective_message.reply_text(
                f"📬 Ajastettu raportointi on *{status}*\n\n"
                f"Käyttö:\n"
                f"`/report on` - ota käyttöön\n"
                f"`/report off` - poista käytöstä",
                parse_mode="Markdown",
            )
            return

        cmd = args[0].lower()
        if cmd in ("on", "päällä", "1", "true"):
            self._reports_enabled = True
            await update.effective_message.reply_text(
                "✅ Ajastettu raportointi *käytössä*",
                parse_mode="Markdown",
            )
        elif cmd in ("off", "pois", "0", "false"):
            self._reports_enabled = False
            await update.effective_message.reply_text(
                "❌ Ajastettu raportointi *pois käytöstä*",
                parse_mode="Markdown",
            )
        else:
            await update.effective_message.reply_text(
                "❓ Käytä: `/report on` tai `/report off`",
                parse_mode="Markdown",
            )

    async def devices(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Handle /devices command - list all devices with their order numbers."""
        if not update.effective_message:
            return

        if not self._db:
            await update.effective_message.reply_text(
                "❌ Tietokanta ei käytössä"
            )
            return

        devices = self._get_devices_with_config_names()

        if not devices:
            await update.effective_message.reply_text(
                "❌ Ei laitteita"
            )
            return

        lines = [f"📱 *Laitteet* ({_format_timestamp()})\n"]

        for device in devices:
            display_name = device.get_full_display_name()
            lines.append(
                f"{device.display_order}. {display_name} - `{device.mac}` ({device.sensor_type})"
            )

        await update.effective_message.reply_text(
            "\n".join(lines),
            parse_mode="Markdown",
        )

    async def rename(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Handle /rename command - set device alias."""
        if not update.effective_message:
            return

        if not self._db:
            await update.effective_message.reply_text(
                "❌ Tietokanta ei käytössä"
            )
            return

        args = context.args or []

        if len(args) < 2:
            await update.effective_message.reply_text(
                "Käyttö: `/rename <nro> <nimi>`\n"
                "Esim: `/rename 1 Olohuone`\n"
                "Poista alias: `/rename 1 -`",
                parse_mode="Markdown",
            )
            return

        identifier = args[0]
        new_alias = " ".join(args[1:])

        # Handle clearing alias
        if new_alias == "-":
            new_alias = None

        # Resolve device
        device = self._resolve_device(identifier)
        if not device:
            await update.effective_message.reply_text(
                f"❌ Laitetta '{identifier}' ei löytynyt"
            )
            return

        # Set alias
        if self._db.set_device_alias(device.mac, new_alias):
            if new_alias:
                await update.effective_message.reply_text(
                    f"✅ Laite {device.display_order} nimetty: *{new_alias}*",
                    parse_mode="Markdown",
                )
            else:
                await update.effective_message.reply_text(
                    f"✅ Laite {device.display_order} alias poistettu",
                    parse_mode="Markdown",
                )
        else:
            await update.effective_message.reply_text(
                "❌ Nimeäminen epäonnistui"
            )

    def _parse_time_arg(self, arg: str) -> tuple[Optional[int], Optional[int]]:
        """Parse time argument like '6', '24h', '7d'. Returns (hours, days)."""
        match = re.match(r"^(\d+)(h|d)?$", arg.lower())
        if not match:
            return None, None

        value = int(match.group(1))
        unit = match.group(2) or "h"

        if unit == "d":
            return None, value
        return value, None

    async def history(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Handle /history command - show temperature history."""
        if not update.effective_message:
            return

        args = context.args or []

        # Parse arguments: /history [sensor_identifier] [time]
        sensor_identifier: Optional[str] = None
        hours: Optional[int] = 6
        days: Optional[int] = None

        for arg in args:
            h, d = self._parse_time_arg(arg)
            if h is not None or d is not None:
                hours = h
                days = d
            else:
                sensor_identifier = arg

        # Use database for longer history
        use_db = self._db and (days or (hours and hours > 24))

        if sensor_identifier:
            # Try to resolve device by number/alias/name/MAC
            device = self._resolve_device(sensor_identifier)
            if device:
                display_name = device.get_display_name()
                mac = device.mac
            else:
                await update.effective_message.reply_text(
                    f"❌ Anturia '{sensor_identifier}' ei löytynyt"
                )
                return

            if use_db:
                await self._send_db_history(
                    update, display_name, mac, hours, days
                )
            else:
                readings = self._store.get_history(mac, hours or 6)
                await self._send_history(
                    update, display_name, readings, hours or 6
                )
        else:
            # Show history for all sensors
            time_str = f"{days}d" if days else f"{hours}h"
            lines = [f"📈 *Historia ({time_str})* ({_format_timestamp()})\n"]

            # Use device ordering if database is available
            if self._db:
                devices = self._get_devices_with_config_names()
                for device in devices:
                    name = device.get_display_name()
                    if use_db:
                        stats = self._db.get_stats(device.mac, hours=hours, days=days)
                        if stats and stats["sample_count"] > 0:
                            lines.append(
                                f"{device.display_order}. *{name}*: "
                                f"min {stats['temp_min']:.1f}°C, "
                                f"max {stats['temp_max']:.1f}°C, "
                                f"ka {stats['temp_avg']:.1f}°C"
                            )
                        else:
                            lines.append(f"{device.display_order}. *{name}*: _ei historiaa_")
                    else:
                        readings = self._store.get_history(device.mac, hours or 6)
                        if readings:
                            temps = [r.temperature for r in readings]
                            lines.append(
                                f"{device.display_order}. *{name}*: "
                                f"min {min(temps):.1f}°C, "
                                f"max {max(temps):.1f}°C, "
                                f"ka {sum(temps)/len(temps):.1f}°C"
                            )
                        else:
                            lines.append(f"{device.display_order}. *{name}*: _ei historiaa_")
            else:
                for sensor_config in self._config.sensors:
                    if use_db:
                        stats = self._db.get_stats(sensor_config.mac, hours=hours, days=days)
                        if stats and stats["sample_count"] > 0:
                            lines.append(
                                f"*{sensor_config.name}*: "
                                f"min {stats['temp_min']:.1f}°C, "
                                f"max {stats['temp_max']:.1f}°C, "
                                f"ka {stats['temp_avg']:.1f}°C"
                            )
                        else:
                            lines.append(f"*{sensor_config.name}*: _ei historiaa_")
                    else:
                        readings = self._store.get_history(sensor_config.mac, hours or 6)
                        if readings:
                            temps = [r.temperature for r in readings]
                            lines.append(
                                f"*{sensor_config.name}*: "
                                f"min {min(temps):.1f}°C, "
                                f"max {max(temps):.1f}°C, "
                                f"ka {sum(temps)/len(temps):.1f}°C"
                            )
                        else:
                            lines.append(f"*{sensor_config.name}*: _ei historiaa_")

            # Add weather history if available
            if self._db and self._weather:
                weather_stats = self._db.get_weather_stats(hours=hours, days=days)
                if weather_stats and weather_stats["sample_count"] > 0:
                    lines.append("")
                    lines.append(
                        f"🌤️ *{self._weather.location_name}*: "
                        f"min {weather_stats['temp_min']:.1f}°C, "
                        f"max {weather_stats['temp_max']:.1f}°C, "
                        f"ka {weather_stats['temp_avg']:.1f}°C"
                    )

            await update.effective_message.reply_text(
                "\n".join(lines),
                parse_mode="Markdown",
            )

    async def _send_history(
        self,
        update: Update,
        sensor_name: str,
        readings: list,
        hours: int,
    ) -> None:
        """Send detailed history for a single sensor from memory."""
        if not update.effective_message:
            return

        if not readings:
            await update.effective_message.reply_text(
                f"❌ Ei historiaa anturille {sensor_name}"
            )
            return

        temps = [r.temperature for r in readings]
        lines = [
            f"📈 *{sensor_name} - Historia ({hours}h)* ({_format_timestamp()})\n",
            f"Min: {min(temps):.1f}°C",
            f"Max: {max(temps):.1f}°C",
            f"Keskiarvo: {sum(temps)/len(temps):.1f}°C",
            f"Lukemia: {len(readings)}",
        ]

        await update.effective_message.reply_text(
            "\n".join(lines),
            parse_mode="Markdown",
        )

    async def _send_db_history(
        self,
        update: Update,
        sensor_name: str,
        mac: str,
        hours: Optional[int],
        days: Optional[int],
    ) -> None:
        """Send detailed history for a single sensor from database."""
        if not update.effective_message or not self._db:
            return

        stats = self._db.get_stats(mac, hours=hours, days=days)

        if not stats or stats["sample_count"] == 0:
            await update.effective_message.reply_text(
                f"❌ Ei historiaa anturille {sensor_name}"
            )
            return

        time_str = f"{days}d" if days else f"{hours}h"
        lines = [
            f"📈 *{sensor_name} - Historia ({time_str})* ({_format_timestamp()})\n",
            f"Min: {stats['temp_min']:.1f}°C",
            f"Max: {stats['temp_max']:.1f}°C",
            f"Keskiarvo: {stats['temp_avg']:.1f}°C",
            f"Datapisteitä: {stats['sample_count']}",
        ]

        if stats.get("humidity_avg"):
            lines.append(f"Kosteus (ka): {stats['humidity_avg']:.0f}%")

        await update.effective_message.reply_text(
            "\n".join(lines),
            parse_mode="Markdown",
        )

    async def stats(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Handle /stats command - show detailed statistics."""
        if not update.effective_message:
            return

        if not self._db:
            await update.effective_message.reply_text(
                "❌ Tietokanta ei käytössä"
            )
            return

        args = context.args or []

        # Parse arguments: /stats [sensor_identifier] [time]
        sensor_identifier: Optional[str] = None
        hours: Optional[int] = None
        days: int = 1  # Default 1 day

        for arg in args:
            h, d = self._parse_time_arg(arg)
            if h is not None:
                hours = h
                days = 0
            elif d is not None:
                days = d
            else:
                sensor_identifier = arg

        if sensor_identifier:
            # Try to resolve device by number/alias/name/MAC
            device = self._resolve_device(sensor_identifier)
            if device:
                display_name = device.get_display_name()
                mac = device.mac
            else:
                await update.effective_message.reply_text(
                    f"❌ Anturia '{sensor_identifier}' ei löytynyt"
                )
                return

            await self._send_stats(
                update, display_name, mac, hours, days
            )
        else:
            # Show stats for all sensors
            time_str = f"{days}d" if days else f"{hours}h"
            lines = [f"📊 *Tilastot ({time_str})* ({_format_timestamp()})\n"]

            devices = self._get_devices_with_config_names()
            for device in devices:
                name = device.get_display_name()
                stats = self._db.get_stats(
                    device.mac,
                    hours=hours,
                    days=days if not hours else None,
                )

                if stats and stats["sample_count"] > 0:
                    lines.append(
                        f"{device.display_order}. *{name}*:\n"
                        f"  Min: {stats['temp_min']:.1f}°C, "
                        f"Max: {stats['temp_max']:.1f}°C, "
                        f"Ka: {stats['temp_avg']:.1f}°C"
                    )
                else:
                    lines.append(f"{device.display_order}. *{name}*: _ei dataa_")

            # Add weather stats if available
            if self._weather:
                weather_stats = self._db.get_weather_stats(
                    hours=hours,
                    days=days if not hours else None,
                )
                if weather_stats and weather_stats["sample_count"] > 0:
                    lines.append("")
                    lines.append(
                        f"🌤️ *{self._weather.location_name}*:\n"
                        f"  Min: {weather_stats['temp_min']:.1f}°C, "
                        f"Max: {weather_stats['temp_max']:.1f}°C, "
                        f"Ka: {weather_stats['temp_avg']:.1f}°C"
                    )
                    if weather_stats.get("precipitation_total") and weather_stats["precipitation_total"] > 0:
                        lines.append(f"  Sade: {weather_stats['precipitation_total']:.1f} mm")

            await update.effective_message.reply_text(
                "\n".join(lines),
                parse_mode="Markdown",
            )

    async def _send_stats(
        self,
        update: Update,
        sensor_name: str,
        mac: str,
        hours: Optional[int],
        days: Optional[int],
    ) -> None:
        """Send detailed statistics for a single sensor."""
        if not update.effective_message or not self._db:
            return

        stats = self._db.get_stats(mac, hours=hours, days=days)

        if not stats or stats["sample_count"] == 0:
            await update.effective_message.reply_text(
                f"❌ Ei tilastoja anturille {sensor_name}"
            )
            return

        time_str = f"{days} päivää" if days else f"{hours} tuntia"
        lines = [
            f"📊 *{sensor_name} - Tilastot ({time_str})* ({_format_timestamp()})\n",
            f"🌡 *Lämpötila:*",
            f"  Min: {stats['temp_min']:.1f}°C",
            f"  Max: {stats['temp_max']:.1f}°C",
            f"  Keskiarvo: {stats['temp_avg']:.1f}°C",
        ]

        if stats.get("humidity_avg"):
            lines.append(f"\n💧 *Kosteus (ka):* {stats['humidity_avg']:.0f}%")

        lines.append(f"\n📈 Datapisteitä: {stats['sample_count']}")

        await update.effective_message.reply_text(
            "\n".join(lines),
            parse_mode="Markdown",
        )

    async def graph(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Handle /graph command - show ASCII temperature graph."""
        if not update.effective_message:
            return

        if not self._db:
            await update.effective_message.reply_text(
                "❌ Tietokanta ei käytössä"
            )
            return

        args = context.args or []

        # Parse arguments: /graph [sensor_identifier] [time]
        sensor_identifier: Optional[str] = None
        hours = 24
        days: Optional[int] = None

        for arg in args:
            h, d = self._parse_time_arg(arg)
            if h is not None:
                hours = h
                days = None
            elif d is not None:
                days = d
                hours = d * 24
            else:
                sensor_identifier = arg

        # Dynamic width based on time range
        if hours <= 24:
            width = 24
        elif hours <= 72:
            width = 36
        else:
            width = 48

        # Time string for display
        time_str = f"{days}d" if days else f"{hours}h"

        if not sensor_identifier:
            weather_hint = " tai `/graph sää`" if self._weather else ""
            await update.effective_message.reply_text(
                f"Käyttö: `/graph <anturi> [aika]`\n"
                f"Esim: `/graph 1 24h`, `/graph 1 7d`{weather_hint}",
                parse_mode="Markdown",
            )
            return

        # Check if requesting weather graph
        if sensor_identifier.lower() in ("sää", "saa", "weather", "ulko"):
            if not self._weather:
                await update.effective_message.reply_text(
                    "❌ Sää ei käytössä"
                )
                return

            data = self._db.get_weather_graph_data(hours)
            display_name = self._weather.location_name

            if not data:
                await update.effective_message.reply_text(
                    f"❌ Ei säädataa"
                )
                return

            graph, timeline = self._create_ascii_graph(data, width=width, height=8)
            temps = [t for _, t in data]

            text = (
                f"🌤️ *{display_name}* ({time_str}) ({_format_timestamp()})\n"
                f"```\n{graph}\n{timeline}```\n"
                f"Min: {min(temps):.1f}°C | Max: {max(temps):.1f}°C | Ka: {sum(temps)/len(temps):.1f}°C"
            )

            await update.effective_message.reply_text(text, parse_mode="Markdown")
            return

        # Try to resolve device by number/alias/name/MAC
        device = self._resolve_device(sensor_identifier)
        if not device:
            await update.effective_message.reply_text(
                f"❌ Anturia '{sensor_identifier}' ei löytynyt"
            )
            return

        display_name = device.get_display_name()
        data = self._db.get_graph_data(device.mac, hours)

        if not data:
            await update.effective_message.reply_text(
                f"❌ Ei dataa anturille {display_name}"
            )
            return

        graph, timeline = self._create_ascii_graph(data, width=width, height=8)
        temps = [t for _, t in data]

        text = (
            f"📈 *{display_name}* ({time_str}) ({_format_timestamp()})\n"
            f"```\n{graph}\n{timeline}```\n"
            f"Min: {min(temps):.1f}°C | Max: {max(temps):.1f}°C | Ka: {sum(temps)/len(temps):.1f}°C"
        )

        await update.effective_message.reply_text(text, parse_mode="Markdown")

    def _create_ascii_graph(
        self,
        data: list[tuple[datetime, float]],
        width: int = 24,
        height: int = 8,
    ) -> tuple[str, str]:
        """Create ASCII art graph from data points.

        Returns tuple of (graph_string, timeline_string).
        """
        if not data:
            return "Ei dataa", ""

        timestamps = [t for t, _ in data]
        temps = [t for _, t in data]
        min_temp = min(temps)
        max_temp = max(temps)
        temp_range = max_temp - min_temp

        if temp_range == 0:
            temp_range = 1

        # Sample data to fit width
        step = max(1, len(data) // width)
        sampled = [temps[i] for i in range(0, len(data), step)][:width]
        sampled_times = [timestamps[i] for i in range(0, len(data), step)][:width]
        actual_width = len(sampled)

        # Build graph
        lines = []
        for row in range(height):
            threshold = max_temp - (row / (height - 1)) * temp_range
            line = ""
            for temp in sampled:
                if temp >= threshold:
                    line += "█"
                else:
                    line += " "
            # Add temperature label on first and last row
            if row == 0:
                lines.append(f"{max_temp:5.1f}°│{line}│")
            elif row == height - 1:
                lines.append(f"{min_temp:5.1f}°│{line}│")
            else:
                lines.append(f"      │{line}│")

        # Build timeline
        if sampled_times:
            first_time = sampled_times[0]
            last_time = sampled_times[-1]
            total_hours = (last_time - first_time).total_seconds() / 3600

            if total_hours <= 24:
                # Show hours
                first_label = first_time.strftime("%H:%M")
                last_label = last_time.strftime("%H:%M")
            elif total_hours <= 168:
                # Show dates for multi-day
                first_label = first_time.strftime("%d.%m")
                last_label = last_time.strftime("%d.%m")
            else:
                first_label = first_time.strftime("%d.%m")
                last_label = last_time.strftime("%d.%m")

            # Create timeline with labels at start and end
            padding = actual_width - len(first_label) - len(last_label)
            if padding > 0:
                timeline = f"      └{first_label}{' ' * padding}{last_label}┘"
            else:
                timeline = f"      └{first_label}{'─' * (actual_width - len(first_label))}┘"
        else:
            timeline = ""

        return "\n".join(lines), timeline

    async def weather(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Handle /weather command - show current weather."""
        if not update.effective_message:
            return

        if not self._weather:
            await update.effective_message.reply_text(
                "❌ Sää ei käytössä (ei konfiguroitu)"
            )
            return

        from ..weather import get_weather_emoji

        w = self._weather.latest

        if not w:
            await update.effective_message.reply_text(
                "❌ Säätietoja ei saatavilla"
            )
            return

        emoji = get_weather_emoji(w.symbol_code)
        location = self._weather.location_name

        lines = [
            f"{emoji} *{location} - Sää* ({_format_timestamp()})\n",
            f"🌡 *Lämpötila:* {w.temperature:.1f}°C",
        ]

        if w.humidity is not None:
            lines.append(f"💧 *Kosteus:* {w.humidity:.0f}%")

        if w.wind_speed is not None:
            wind_dir = _wind_direction_text(w.wind_direction)
            lines.append(f"💨 *Tuuli:* {w.wind_speed:.1f} m/s {wind_dir}")

        if w.pressure is not None:
            lines.append(f"📊 *Ilmanpaine:* {w.pressure:.0f} hPa")

        if w.precipitation is not None and w.precipitation > 0:
            lines.append(f"🌧 *Sade (1h):* {w.precipitation:.1f} mm")

        if w.cloud_cover is not None:
            lines.append(f"☁️ *Pilvisyys:* {w.cloud_cover:.0f}%")

        # Add weather history from database if available
        if self._db:
            stats = self._db.get_weather_stats(hours=24)
            if stats and stats["sample_count"] > 1:
                lines.append("")
                lines.append(f"📈 *24h:* min {stats['temp_min']:.1f}°C, max {stats['temp_max']:.1f}°C")
                if stats.get("precipitation_total") and stats["precipitation_total"] > 0:
                    lines.append(f"🌧 *Sade yhteensä:* {stats['precipitation_total']:.1f} mm")

        await update.effective_message.reply_text(
            "\n".join(lines),
            parse_mode="Markdown",
        )

    async def help(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Handle /help command."""
        if not update.effective_message:
            return

        text = """🏠 *HutWatch - Ohje*

*Peruskomennot:*
/temps - Nykyiset lämpötilat + sää
/status - Järjestelmän tila
/weather - Ulkosää yksityiskohtaisesti
/report on|off - Raportointi päälle/pois

*Laitteiden hallinta:*
/devices - Listaa laitteet numeroineen
/rename <nro> <nimi> - Vaihda laitteen alias

*Historia ja tilastot:*
/history [anturi] [aika] - Historia + sää
/stats [anturi] [aika] - Tilastot + sää
/graph <anturi|sää> [aika] - ASCII-graafi

*Anturin valinta:*
Numero: `/history 1`
Alias: `/history Olohuone`
Nimi: `/history Ruuvi1`
Sää: `/graph sää 48h`

*Aikaformaatit:*
`6` tai `6h` - 6 tuntia
`7d` - 7 päivää

*Esimerkkejä:*
`/history 1 24h`
`/stats 7d`
`/graph 2 48h`
`/graph sää 24h`
"""
        await update.effective_message.reply_text(text, parse_mode="Markdown")

    async def menu(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Handle /menu command - show main menu with buttons."""
        if not update.effective_message:
            return

        keyboard = [
            [
                InlineKeyboardButton("🌡️ Lämpötilat", callback_data="temps"),
                InlineKeyboardButton("🌤️ Sää", callback_data="weather"),
            ],
            [
                InlineKeyboardButton("📈 Historia 1d", callback_data="history_1d"),
                InlineKeyboardButton("📈 Historia 7d", callback_data="history_7d"),
            ],
            [
                InlineKeyboardButton("📊 Tilastot 1d", callback_data="stats_1d"),
                InlineKeyboardButton("📊 Tilastot 7d", callback_data="stats_7d"),
            ],
            [
                InlineKeyboardButton("🔧 Status", callback_data="status"),
                InlineKeyboardButton("❓ Ohje", callback_data="help"),
            ],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.effective_message.reply_text(
            "🏠 *HutWatch*\n\nValitse toiminto:",
            parse_mode="Markdown",
            reply_markup=reply_markup,
        )

    async def button_callback(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Handle button callbacks."""
        query = update.callback_query
        if not query:
            return

        await query.answer()

        data = query.data

        # Create a fake context.args for commands that need it
        if data == "temps":
            context.args = []
            await self._send_temps_with_buttons(query)
        elif data == "weather":
            await self._send_weather_with_buttons(query)
        elif data == "status":
            context.args = []
            await self._send_status_response(query)
        elif data == "help":
            await self._send_help_response(query)
        elif data.startswith("history_"):
            time_arg = data.replace("history_", "")
            await self._send_history_response(query, time_arg)
        elif data.startswith("stats_"):
            time_arg = data.replace("stats_", "")
            await self._send_stats_response(query, time_arg)
        elif data == "menu":
            await self._send_menu(query)

    async def _send_menu(self, query) -> None:
        """Send main menu."""
        keyboard = [
            [
                InlineKeyboardButton("🌡️ Lämpötilat", callback_data="temps"),
                InlineKeyboardButton("🌤️ Sää", callback_data="weather"),
            ],
            [
                InlineKeyboardButton("📈 Historia 1d", callback_data="history_1d"),
                InlineKeyboardButton("📈 Historia 7d", callback_data="history_7d"),
            ],
            [
                InlineKeyboardButton("📊 Tilastot 1d", callback_data="stats_1d"),
                InlineKeyboardButton("📊 Tilastot 7d", callback_data="stats_7d"),
            ],
            [
                InlineKeyboardButton("🔧 Status", callback_data="status"),
                InlineKeyboardButton("❓ Ohje", callback_data="help"),
            ],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            "🏠 *HutWatch*\n\nValitse toiminto:",
            parse_mode="Markdown",
            reply_markup=reply_markup,
        )

    async def _send_temps_with_buttons(self, query) -> None:
        """Send temperatures with navigation buttons."""
        lines = [f"🌡️ *Lämpötilat* ({_format_timestamp()})\n"]

        if self._db:
            devices = self._get_devices_with_config_names()
            for device in devices:
                reading = self._store.get_latest(device.mac)
                name = device.get_display_name()

                if reading:
                    age = datetime.now() - reading.timestamp
                    age_str = self._format_age(age)

                    line = f"{device.display_order}. *{name}*: {reading.temperature:.1f}°C"
                    if reading.humidity is not None:
                        line += f", {reading.humidity:.0f}%"
                    line += f" _{age_str}_"
                else:
                    line = f"{device.display_order}. *{name}*: _ei dataa_"

                lines.append(line)

        # Add weather
        if self._weather and self._weather.latest:
            from ..weather import get_weather_emoji
            w = self._weather.latest
            emoji = get_weather_emoji(w.symbol_code)
            lines.append("")
            lines.append(f"{emoji} *{self._weather.location_name}*: {w.temperature:.1f}°C")

        keyboard = [
            [
                InlineKeyboardButton("🔄 Päivitä", callback_data="temps"),
                InlineKeyboardButton("🏠 Valikko", callback_data="menu"),
            ],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            "\n".join(lines),
            parse_mode="Markdown",
            reply_markup=reply_markup,
        )

    async def _send_weather_with_buttons(self, query) -> None:
        """Send weather with navigation buttons."""
        if not self._weather or not self._weather.latest:
            await query.edit_message_text("❌ Säätietoja ei saatavilla")
            return

        from ..weather import get_weather_emoji

        w = self._weather.latest
        emoji = get_weather_emoji(w.symbol_code)
        location = self._weather.location_name

        lines = [
            f"{emoji} *{location} - Sää* ({_format_timestamp()})\n",
            f"🌡 *Lämpötila:* {w.temperature:.1f}°C",
        ]

        if w.humidity is not None:
            lines.append(f"💧 *Kosteus:* {w.humidity:.0f}%")

        if w.wind_speed is not None:
            wind_dir = _wind_direction_text(w.wind_direction)
            lines.append(f"💨 *Tuuli:* {w.wind_speed:.1f} m/s {wind_dir}")

        if w.pressure is not None:
            lines.append(f"📊 *Ilmanpaine:* {w.pressure:.0f} hPa")

        if self._db:
            stats = self._db.get_weather_stats(hours=24)
            if stats and stats["sample_count"] > 1:
                lines.append("")
                lines.append(f"📈 *24h:* min {stats['temp_min']:.1f}°C, max {stats['temp_max']:.1f}°C")

        keyboard = [
            [
                InlineKeyboardButton("🔄 Päivitä", callback_data="weather"),
                InlineKeyboardButton("🏠 Valikko", callback_data="menu"),
            ],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            "\n".join(lines),
            parse_mode="Markdown",
            reply_markup=reply_markup,
        )

    async def _send_history_response(self, query, time_arg: str) -> None:
        """Send history with navigation buttons."""
        hours = None
        days = None

        if time_arg.endswith("d"):
            days = int(time_arg[:-1])
        else:
            hours = int(time_arg.replace("h", ""))

        time_str = f"{days}d" if days else f"{hours}h"
        lines = [f"📈 *Historia ({time_str})* ({_format_timestamp()})\n"]

        if self._db:
            devices = self._get_devices_with_config_names()
            for device in devices:
                name = device.get_display_name()
                stats = self._db.get_stats(device.mac, hours=hours, days=days)
                if stats and stats["sample_count"] > 0:
                    lines.append(
                        f"{device.display_order}. *{name}*: "
                        f"min {stats['temp_min']:.1f}°C, "
                        f"max {stats['temp_max']:.1f}°C, "
                        f"ka {stats['temp_avg']:.1f}°C"
                    )
                else:
                    lines.append(f"{device.display_order}. *{name}*: _ei historiaa_")

            # Add weather
            if self._weather:
                weather_stats = self._db.get_weather_stats(hours=hours, days=days)
                if weather_stats and weather_stats["sample_count"] > 0:
                    lines.append("")
                    lines.append(
                        f"🌤️ *{self._weather.location_name}*: "
                        f"min {weather_stats['temp_min']:.1f}°C, "
                        f"max {weather_stats['temp_max']:.1f}°C, "
                        f"ka {weather_stats['temp_avg']:.1f}°C"
                    )

        keyboard = [
            [
                InlineKeyboardButton("1d", callback_data="history_1d"),
                InlineKeyboardButton("7d", callback_data="history_7d"),
                InlineKeyboardButton("30d", callback_data="history_30d"),
            ],
            [
                InlineKeyboardButton("🏠 Valikko", callback_data="menu"),
            ],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            "\n".join(lines),
            parse_mode="Markdown",
            reply_markup=reply_markup,
        )

    async def _send_stats_response(self, query, time_arg: str) -> None:
        """Send stats with navigation buttons."""
        hours = None
        days = None

        if time_arg.endswith("d"):
            days = int(time_arg[:-1])
        else:
            hours = int(time_arg.replace("h", ""))

        time_str = f"{days}d" if days else f"{hours}h"
        lines = [f"📊 *Tilastot ({time_str})* ({_format_timestamp()})\n"]

        if self._db:
            devices = self._get_devices_with_config_names()
            for device in devices:
                name = device.get_display_name()
                stats = self._db.get_stats(
                    device.mac,
                    hours=hours,
                    days=days if not hours else None,
                )

                if stats and stats["sample_count"] > 0:
                    lines.append(
                        f"{device.display_order}. *{name}*:\n"
                        f"  Min: {stats['temp_min']:.1f}°C, "
                        f"Max: {stats['temp_max']:.1f}°C, "
                        f"Ka: {stats['temp_avg']:.1f}°C"
                    )
                else:
                    lines.append(f"{device.display_order}. *{name}*: _ei dataa_")

            # Add weather
            if self._weather:
                weather_stats = self._db.get_weather_stats(
                    hours=hours,
                    days=days if not hours else None,
                )
                if weather_stats and weather_stats["sample_count"] > 0:
                    lines.append("")
                    lines.append(
                        f"🌤️ *{self._weather.location_name}*:\n"
                        f"  Min: {weather_stats['temp_min']:.1f}°C, "
                        f"Max: {weather_stats['temp_max']:.1f}°C, "
                        f"Ka: {weather_stats['temp_avg']:.1f}°C"
                    )

        keyboard = [
            [
                InlineKeyboardButton("1d", callback_data="stats_1d"),
                InlineKeyboardButton("7d", callback_data="stats_7d"),
                InlineKeyboardButton("30d", callback_data="stats_30d"),
            ],
            [
                InlineKeyboardButton("🏠 Valikko", callback_data="menu"),
            ],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            "\n".join(lines),
            parse_mode="Markdown",
            reply_markup=reply_markup,
        )

    async def _send_status_response(self, query) -> None:
        """Send status with navigation buttons."""
        lines = [f"🔧 *Järjestelmän tila* ({_format_timestamp()})\n"]
        lines.append("*Anturit:*")

        if self._db:
            devices = self._get_devices_with_config_names()
            active = 0
            for device in devices:
                reading = self._store.get_latest(device.mac)
                name = device.get_display_name()
                status_emoji = "✅" if reading else "❌"

                if reading:
                    active += 1
                    age = datetime.now() - reading.timestamp
                    if age > timedelta(minutes=10):
                        status_emoji = "⚠️"

                    info = f"{reading.temperature:.1f}°C"
                    if reading.battery_percent is not None:
                        info += f", {reading.battery_percent}%"

                    lines.append(f"  {status_emoji} {device.display_order}. {name}: {info}")
                else:
                    lines.append(f"  {status_emoji} {device.display_order}. {name}: ei yhteyttä")

            total = len(devices)
            lines.append(f"\n*Yhteenveto:* {active}/{total} anturia aktiivisia")

            # Uptime
            uptime = datetime.now() - self._start_time
            uptime_str = self._format_uptime(uptime)
            lines.append(f"*Käynnissä:* {uptime_str}")

        keyboard = [
            [
                InlineKeyboardButton("🔄 Päivitä", callback_data="status"),
                InlineKeyboardButton("🏠 Valikko", callback_data="menu"),
            ],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            "\n".join(lines),
            parse_mode="Markdown",
            reply_markup=reply_markup,
        )

    async def _send_help_response(self, query) -> None:
        """Send help with navigation buttons."""
        text = """🏠 *HutWatch - Ohje*

*Komennot:*
/menu - Päävalikko napeilla
/temps - Lämpötilat
/weather - Ulkosää
/history [aika] - Historia
/stats [aika] - Tilastot

*Aikaformaatit:*
`6h` - 6 tuntia
`7d` - 7 päivää"""

        keyboard = [
            [
                InlineKeyboardButton("🏠 Valikko", callback_data="menu"),
            ],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            text,
            parse_mode="Markdown",
            reply_markup=reply_markup,
        )

    def _format_age(self, age: timedelta) -> str:
        """Format timedelta as human-readable string."""
        total_seconds = int(age.total_seconds())

        if total_seconds < 60:
            return f"{total_seconds}s sitten"
        elif total_seconds < 3600:
            minutes = total_seconds // 60
            return f"{minutes}min sitten"
        else:
            hours = total_seconds // 3600
            return f"{hours}h sitten"

    def _format_uptime(self, uptime: timedelta) -> str:
        """Format uptime as human-readable string."""
        total_seconds = int(uptime.total_seconds())
        days = total_seconds // 86400
        hours = (total_seconds % 86400) // 3600
        minutes = (total_seconds % 3600) // 60

        if days > 0:
            return f"{days}pv {hours}h {minutes}min"
        elif hours > 0:
            return f"{hours}h {minutes}min"
        else:
            return f"{minutes}min"
