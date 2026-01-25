"""Telegram bot command handlers."""

import logging
from datetime import datetime, timedelta
from typing import Optional

from telegram import Update
from telegram.ext import ContextTypes

from ..ble.sensor_store import SensorStore
from ..models import AppConfig

logger = logging.getLogger(__name__)


class CommandHandlers:
    """Telegram command handlers."""

    def __init__(self, config: AppConfig, store: SensorStore) -> None:
        self._config = config
        self._store = store

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

        await update.effective_message.reply_text(
            "\n".join(lines),
            parse_mode="Markdown",
        )

    async def history(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Handle /history command - show temperature history."""
        if not update.effective_message:
            return

        args = context.args or []

        # Parse arguments: /history [sensor_name] [hours]
        sensor_name: Optional[str] = None
        hours = 6  # Default 6 hours

        for arg in args:
            if arg.isdigit():
                hours = min(int(arg), 24)  # Max 24 hours
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

            readings = self._store.get_history(sensor_config.mac, hours)
            await self._send_history(
                update,
                sensor_config.name,
                readings,
                hours,
            )
        else:
            # Show history for all sensors
            lines = [f"📈 *Historia ({hours}h)*\n"]

            for sensor_config in self._config.sensors:
                readings = self._store.get_history(sensor_config.mac, hours)

                if readings:
                    temps = [r.temperature for r in readings]
                    min_temp = min(temps)
                    max_temp = max(temps)
                    avg_temp = sum(temps) / len(temps)

                    lines.append(
                        f"*{sensor_config.name}*: "
                        f"min {min_temp:.1f}°C, "
                        f"max {max_temp:.1f}°C, "
                        f"ka {avg_temp:.1f}°C"
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
        """Send detailed history for a single sensor."""
        if not update.effective_message:
            return

        if not readings:
            await update.effective_message.reply_text(
                f"❌ Ei historiaa anturille {sensor_name}"
            )
            return

        temps = [r.temperature for r in readings]
        min_temp = min(temps)
        max_temp = max(temps)
        avg_temp = sum(temps) / len(temps)

        lines = [
            f"📈 *{sensor_name} - Historia ({hours}h)*\n",
            f"Min: {min_temp:.1f}°C",
            f"Max: {max_temp:.1f}°C",
            f"Keskiarvo: {avg_temp:.1f}°C",
            f"Lukemia: {len(readings)}",
        ]

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

*Komennot:*
/temps - Kaikkien anturien lämpötilat
/status - Järjestelmän tila
/history - Lämpötilahistoria
/history [anturi] [h] - Tietyn anturin historia
/help - Tämä ohje

*Esimerkkejä:*
`/history Ulko 12` - Ulko-anturin 12h historia
`/history 6` - Kaikkien anturien 6h historia
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
