"""Telegram bot command handlers."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Optional

from telegram import Update
from telegram.ext import ContextTypes

from ..ble.sensor_store import SensorStore
from ..models import AppConfig

if TYPE_CHECKING:
    from ..db import Database

logger = logging.getLogger(__name__)


class CommandHandlers:
    """Telegram command handlers."""

    def __init__(
        self,
        config: AppConfig,
        store: SensorStore,
        db: Optional[Database] = None,
    ) -> None:
        self._config = config
        self._store = store
        self._db = db
        self._reports_enabled = True

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

        lines = ["📊 *Lämpötilat*\n"]

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

        lines = ["🔧 *Järjestelmän tila*\n"]

        # Sensor status
        lines.append("*Anturit:*")
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

                lines.append(
                    f"  {status_emoji} {sensor_config.name}: {info}"
                )
            else:
                lines.append(
                    f"  {status_emoji} {sensor_config.name}: ei yhteyttä"
                )

        # Summary
        total = len(self._config.sensors)
        active = len([
            s for s in self._config.sensors
            if self._store.get_latest(s.mac) is not None
        ])
        lines.append(f"\n*Yhteenveto:* {active}/{total} anturia aktiivisia")

        # Report status
        report_status = "päällä ✅" if self._reports_enabled else "pois ❌"
        lines.append(f"*Ajastettu raportointi:* {report_status}")

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

        # Parse arguments: /history [sensor_name] [time]
        sensor_name: Optional[str] = None
        hours: Optional[int] = 6
        days: Optional[int] = None

        for arg in args:
            h, d = self._parse_time_arg(arg)
            if h is not None or d is not None:
                hours = h
                days = d
            else:
                sensor_name = arg

        # Use database for longer history
        use_db = self._db and (days or (hours and hours > 24))

        if sensor_name:
            # Find sensor by name
            sensor_config = None
            for s in self._config.sensors:
                if s.name.lower() == sensor_name.lower():
                    sensor_config = s
                    break

            if not sensor_config:
                await update.effective_message.reply_text(
                    f"❌ Anturia '{sensor_name}' ei löytynyt"
                )
                return

            if use_db:
                await self._send_db_history(
                    update, sensor_config.name, sensor_config.mac, hours, days
                )
            else:
                readings = self._store.get_history(sensor_config.mac, hours or 6)
                await self._send_history(
                    update, sensor_config.name, readings, hours or 6
                )
        else:
            # Show history for all sensors
            time_str = f"{days}d" if days else f"{hours}h"
            lines = [f"📈 *Historia ({time_str})*\n"]

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
            f"📈 *{sensor_name} - Historia ({hours}h)*\n",
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
            f"📈 *{sensor_name} - Historia ({time_str})*\n",
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

        # Parse arguments: /stats [sensor_name] [time]
        sensor_name: Optional[str] = None
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
                sensor_name = arg

        if sensor_name:
            # Find sensor by name
            sensor_config = None
            for s in self._config.sensors:
                if s.name.lower() == sensor_name.lower():
                    sensor_config = s
                    break

            if not sensor_config:
                await update.effective_message.reply_text(
                    f"❌ Anturia '{sensor_name}' ei löytynyt"
                )
                return

            await self._send_stats(
                update, sensor_config.name, sensor_config.mac, hours, days
            )
        else:
            # Show stats for all sensors
            time_str = f"{days}d" if days else f"{hours}h"
            lines = [f"📊 *Tilastot ({time_str})*\n"]

            for sensor_config in self._config.sensors:
                stats = self._db.get_stats(
                    sensor_config.mac,
                    hours=hours,
                    days=days if not hours else None,
                )

                if stats and stats["sample_count"] > 0:
                    lines.append(
                        f"*{sensor_config.name}*:\n"
                        f"  Min: {stats['temp_min']:.1f}°C, "
                        f"Max: {stats['temp_max']:.1f}°C, "
                        f"Ka: {stats['temp_avg']:.1f}°C"
                    )
                else:
                    lines.append(f"*{sensor_config.name}*: _ei dataa_")

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
            f"📊 *{sensor_name} - Tilastot ({time_str})*\n",
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

        # Parse arguments: /graph [sensor_name] [time]
        sensor_name: Optional[str] = None
        hours = 24

        for arg in args:
            h, d = self._parse_time_arg(arg)
            if h is not None:
                hours = h
            elif d is not None:
                hours = d * 24
            else:
                sensor_name = arg

        if not sensor_name:
            await update.effective_message.reply_text(
                "Käyttö: `/graph <anturi> [aika]`\n"
                "Esim: `/graph Ulkona 24h`",
                parse_mode="Markdown",
            )
            return

        # Find sensor by name
        sensor_config = None
        for s in self._config.sensors:
            if s.name.lower() == sensor_name.lower():
                sensor_config = s
                break

        if not sensor_config:
            await update.effective_message.reply_text(
                f"❌ Anturia '{sensor_name}' ei löytynyt"
            )
            return

        data = self._db.get_graph_data(sensor_config.mac, hours)

        if not data:
            await update.effective_message.reply_text(
                f"❌ Ei dataa anturille {sensor_config.name}"
            )
            return

        graph = self._create_ascii_graph(data, width=24, height=8)
        temps = [t for _, t in data]

        text = (
            f"📈 *{sensor_config.name}* ({hours}h)\n"
            f"```\n{graph}```\n"
            f"Min: {min(temps):.1f}°C | Max: {max(temps):.1f}°C | Ka: {sum(temps)/len(temps):.1f}°C"
        )

        await update.effective_message.reply_text(text, parse_mode="Markdown")

    def _create_ascii_graph(
        self,
        data: list[tuple[datetime, float]],
        width: int = 24,
        height: int = 8,
    ) -> str:
        """Create ASCII art graph from data points."""
        if not data:
            return "Ei dataa"

        temps = [t for _, t in data]
        min_temp = min(temps)
        max_temp = max(temps)
        temp_range = max_temp - min_temp

        if temp_range == 0:
            temp_range = 1

        # Sample data to fit width
        step = max(1, len(data) // width)
        sampled = [temps[i] for i in range(0, len(data), step)][:width]

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

        return "\n".join(lines)

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
/temps - Nykyiset lämpötilat
/status - Järjestelmän tila
/report on|off - Raportointi päälle/pois

*Historia ja tilastot:*
/history [anturi] [aika] - Historia
/stats [anturi] [aika] - Tilastot (min/max/avg)
/graph <anturi> [aika] - ASCII-graafi

*Aikaformaatit:*
`6` tai `6h` - 6 tuntia
`7d` - 7 päivää

*Esimerkkejä:*
`/history Ulkona 24h`
`/stats 7d`
`/graph Sisällä 48h`
"""
        await update.effective_message.reply_text(text, parse_mode="Markdown")

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
