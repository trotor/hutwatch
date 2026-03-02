# Alert System Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add temperature threshold alerts that notify via Telegram and show warnings in TUI dashboard.

**Architecture:** New `AlertManager` component in `hutwatch/alerts.py` owns all alert logic (CRUD + threshold checking). The aggregator calls `AlertManager.check()` every 5 minutes. `HutWatchApp.emit_alerts()` routes triggered events to the active UI (Telegram message or TUI indicator). Alert rules are stored in a new `alerts` SQLite table.

**Tech Stack:** Python 3.10+, SQLite, python-telegram-bot (existing), async/await

**Design doc:** `docs/plans/2026-03-02-alert-system-design.md`

---

### Task 1: Add i18n strings for alerts

Both string files must stay in sync. Add alert-related keys to both languages.

**Files:**
- Modify: `hutwatch/strings_fi.py` (append before closing `}`)
- Modify: `hutwatch/strings_en.py` (append before closing `}`)

**Step 1: Add Finnish strings**

Add to `hutwatch/strings_fi.py` before the closing `}`, after the `console_` section:

```python
    # ── Alerts ─────────────────────────────────────────────────────────
    "alert_temp_low": "alaraja",
    "alert_temp_high": "yläraja",
    "alert_triggered": "⚠️ *{name}*: Lämpötila {temp:.1f}°C {direction} rajan {threshold:.1f}°C",
    "alert_recovery": "✅ *{name}*: Lämpötila palautunut normaaliksi ({temp:.1f}°C, raja {threshold:.1f}°C)",
    "alert_direction_below": "alittaa",
    "alert_direction_above": "ylittää",
    "alert_none": "Ei hälytyksiä asetettu",
    "alert_list_header": "🔔 *Hälytykset*\n",
    "alert_list_item": "{order}. *{name}*: {type} {threshold:.1f}°C {status}",
    "alert_status_ok": "✅",
    "alert_status_triggered": "⚠️",
    "alert_status_disabled": "⏸",
    "alert_set_success": "✅ Hälytys asetettu: *{name}* {type} {threshold:.1f}°C",
    "alert_removed": "✅ Hälytys poistettu: *{name}* {type}",
    "alert_not_found": "Hälytystä ei löytynyt: {name} {type}",
    "alert_recovery_on": "✅ Palautumisilmoitus päällä: *{name}* {type}",
    "alert_recovery_off": "✅ Palautumisilmoitus pois: *{name}* {type}",
    "tg_alert_usage": (
        "Käyttö:\n"
        "`/alert` - näytä hälytykset\n"
        "`/alert <laite> low <arvo>` - aseta alaraja\n"
        "`/alert <laite> high <arvo>` - aseta yläraja\n"
        "`/alert <laite> low off` - poista alaraja\n"
        "`/alert <laite> high off` - poista yläraja\n"
        "`/alert <laite> recovery on/off` - palautumisilmoitus"
    ),
    "tui_cmd_alert": "[a] hälytykset",
    "tui_alert_usage": "Käyttö: a <nro> low/high <arvo>  tai  a <nro> low/high off",
    "tui_alert_indicator": "⚠",
```

**Step 2: Add English strings**

Add to `hutwatch/strings_en.py` before the closing `}`, after the `console_` section:

```python
    # ── Alerts ─────────────────────────────────────────────────────────
    "alert_temp_low": "low",
    "alert_temp_high": "high",
    "alert_triggered": "⚠️ *{name}*: Temperature {temp:.1f}°C {direction} limit {threshold:.1f}°C",
    "alert_recovery": "✅ *{name}*: Temperature back to normal ({temp:.1f}°C, limit {threshold:.1f}°C)",
    "alert_direction_below": "below",
    "alert_direction_above": "above",
    "alert_none": "No alerts configured",
    "alert_list_header": "🔔 *Alerts*\n",
    "alert_list_item": "{order}. *{name}*: {type} {threshold:.1f}°C {status}",
    "alert_status_ok": "✅",
    "alert_status_triggered": "⚠️",
    "alert_status_disabled": "⏸",
    "alert_set_success": "✅ Alert set: *{name}* {type} {threshold:.1f}°C",
    "alert_removed": "✅ Alert removed: *{name}* {type}",
    "alert_not_found": "Alert not found: {name} {type}",
    "alert_recovery_on": "✅ Recovery notification on: *{name}* {type}",
    "alert_recovery_off": "✅ Recovery notification off: *{name}* {type}",
    "tg_alert_usage": (
        "Usage:\n"
        "`/alert` - show alerts\n"
        "`/alert <device> low <value>` - set low threshold\n"
        "`/alert <device> high <value>` - set high threshold\n"
        "`/alert <device> low off` - remove low threshold\n"
        "`/alert <device> high off` - remove high threshold\n"
        "`/alert <device> recovery on/off` - recovery notification"
    ),
    "tui_cmd_alert": "[a] alerts",
    "tui_alert_usage": "Usage: a <num> low/high <value>  or  a <num> low/high off",
    "tui_alert_indicator": "⚠",
```

**Step 3: Run lint to verify strings are in sync**

Run: `python3 scripts/check_i18n.py`
Expected: PASS (both files have same keys)

**Step 4: Commit**

```bash
git add hutwatch/strings_fi.py hutwatch/strings_en.py
git commit -m "Add i18n strings for alert system"
```

---

### Task 2: Add alerts table and CRUD methods to database

**Files:**
- Modify: `hutwatch/db.py`

**Step 1: Add alerts table creation**

In `hutwatch/db.py`, inside `_create_tables()` method, add after the `settings` table creation (after line 116, before `self._conn.commit()`):

```python
        # Alerts table for temperature threshold alerts
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS alerts (
                mac TEXT NOT NULL,
                alert_type TEXT NOT NULL,
                threshold REAL NOT NULL,
                enabled INTEGER DEFAULT 1,
                triggered INTEGER DEFAULT 0,
                notify_recovery INTEGER DEFAULT 0,
                last_triggered DATETIME,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (mac, alert_type)
            )
        """)
```

**Step 2: Add CRUD methods**

Add these methods to the `Database` class, after the `set_device_hidden` method (after line 376) and before `sync_devices_from_config`:

```python
    # Alert management methods

    def set_alert(
        self, mac: str, alert_type: str, threshold: float, notify_recovery: bool = False,
    ) -> None:
        """Create or update an alert rule."""
        if not self._conn:
            return
        try:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO alerts (mac, alert_type, threshold, notify_recovery, enabled, triggered)
                VALUES (?, ?, ?, ?, 1, 0)
                """,
                (mac.upper(), alert_type, threshold, 1 if notify_recovery else 0),
            )
            self._conn.commit()
        except Exception as e:
            logger.error("Error setting alert: %s", e)

    def remove_alert(self, mac: str, alert_type: str) -> bool:
        """Remove an alert rule. Returns True if a row was deleted."""
        if not self._conn:
            return False
        try:
            cursor = self._conn.execute(
                "DELETE FROM alerts WHERE mac = ? AND alert_type = ?",
                (mac.upper(), alert_type),
            )
            self._conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            logger.error("Error removing alert: %s", e)
            return False

    def get_alerts(self, mac: Optional[str] = None) -> list[dict]:
        """Get alert rules. If mac is given, filter by device."""
        if not self._conn:
            return []
        if mac:
            cursor = self._conn.execute(
                "SELECT * FROM alerts WHERE mac = ? ORDER BY alert_type",
                (mac.upper(),),
            )
        else:
            cursor = self._conn.execute(
                "SELECT * FROM alerts ORDER BY mac, alert_type"
            )
        return [dict(row) for row in cursor.fetchall()]

    def update_alert_triggered(self, mac: str, alert_type: str, triggered: bool) -> None:
        """Update the triggered state and last_triggered timestamp."""
        if not self._conn:
            return
        try:
            if triggered:
                self._conn.execute(
                    """
                    UPDATE alerts SET triggered = 1, last_triggered = CURRENT_TIMESTAMP
                    WHERE mac = ? AND alert_type = ?
                    """,
                    (mac.upper(), alert_type),
                )
            else:
                self._conn.execute(
                    "UPDATE alerts SET triggered = 0 WHERE mac = ? AND alert_type = ?",
                    (mac.upper(), alert_type),
                )
            self._conn.commit()
        except Exception as e:
            logger.error("Error updating alert triggered state: %s", e)

    def set_alert_notify_recovery(self, mac: str, alert_type: str, enabled: bool) -> bool:
        """Set the notify_recovery flag for an alert. Returns True if updated."""
        if not self._conn:
            return False
        try:
            cursor = self._conn.execute(
                "UPDATE alerts SET notify_recovery = ? WHERE mac = ? AND alert_type = ?",
                (1 if enabled else 0, mac.upper(), alert_type),
            )
            self._conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            logger.error("Error setting alert notify_recovery: %s", e)
            return False
```

**Step 3: Run compile check**

Run: `python3 -m py_compile hutwatch/db.py`
Expected: No output (success)

**Step 4: Commit**

```bash
git add hutwatch/db.py
git commit -m "Add alerts table and CRUD methods to database"
```

---

### Task 3: Create AlertManager component

**Files:**
- Create: `hutwatch/alerts.py`

**Step 1: Create the AlertManager module**

Create `hutwatch/alerts.py`:

```python
"""Alert manager for temperature threshold monitoring."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .db import Database
    from .models import DeviceInfo, SensorReading

logger = logging.getLogger(__name__)


@dataclass
class AlertRule:
    """A configured alert threshold."""

    mac: str
    alert_type: str  # 'temp_low' or 'temp_high'
    threshold: float
    enabled: bool
    triggered: bool
    notify_recovery: bool


@dataclass
class AlertEvent:
    """An alert that has fired or recovered."""

    mac: str
    device_name: str
    alert_type: str  # 'temp_low' or 'temp_high'
    threshold: float
    current_value: float
    is_recovery: bool


class AlertManager:
    """Manages temperature threshold alerts.

    Call check() with current sensor readings to detect threshold crossings.
    Returns AlertEvent objects for newly triggered or recovered alerts.
    """

    def __init__(self, db: "Database") -> None:
        self._db = db

    def set_alert(
        self,
        mac: str,
        alert_type: str,
        threshold: float,
        notify_recovery: bool = False,
    ) -> None:
        """Create or update an alert rule."""
        self._db.set_alert(mac, alert_type, threshold, notify_recovery)

    def remove_alert(self, mac: str, alert_type: str) -> bool:
        """Remove an alert rule."""
        return self._db.remove_alert(mac, alert_type)

    def get_alerts(self, mac: Optional[str] = None) -> list[AlertRule]:
        """Get alert rules as AlertRule objects."""
        rows = self._db.get_alerts(mac)
        return [
            AlertRule(
                mac=row["mac"],
                alert_type=row["alert_type"],
                threshold=row["threshold"],
                enabled=bool(row["enabled"]),
                triggered=bool(row["triggered"]),
                notify_recovery=bool(row["notify_recovery"]),
            )
            for row in rows
        ]

    def set_notify_recovery(self, mac: str, alert_type: str, enabled: bool) -> bool:
        """Set recovery notification flag."""
        return self._db.set_alert_notify_recovery(mac, alert_type, enabled)

    def check(
        self,
        readings: dict[str, "SensorReading"],
        device_names: dict[str, str],
    ) -> list[AlertEvent]:
        """Check all alerts against current readings.

        Args:
            readings: MAC -> latest SensorReading
            device_names: MAC -> display name for alert messages

        Returns:
            List of AlertEvent for newly triggered or recovered alerts.
        """
        events: list[AlertEvent] = []
        alerts = self.get_alerts()

        for alert in alerts:
            if not alert.enabled:
                continue

            reading = readings.get(alert.mac)
            if reading is None:
                continue

            temp = reading.temperature
            name = device_names.get(alert.mac, alert.mac)
            violated = self._is_violated(alert, temp)

            if violated and not alert.triggered:
                # Threshold just crossed — fire alert
                self._db.update_alert_triggered(alert.mac, alert.alert_type, True)
                events.append(AlertEvent(
                    mac=alert.mac,
                    device_name=name,
                    alert_type=alert.alert_type,
                    threshold=alert.threshold,
                    current_value=temp,
                    is_recovery=False,
                ))
                logger.info(
                    "Alert triggered: %s %s %.1f°C (threshold %.1f°C)",
                    name, alert.alert_type, temp, alert.threshold,
                )

            elif not violated and alert.triggered:
                # Value returned to normal — reset
                self._db.update_alert_triggered(alert.mac, alert.alert_type, False)
                if alert.notify_recovery:
                    events.append(AlertEvent(
                        mac=alert.mac,
                        device_name=name,
                        alert_type=alert.alert_type,
                        threshold=alert.threshold,
                        current_value=temp,
                        is_recovery=True,
                    ))
                logger.info(
                    "Alert recovered: %s %s %.1f°C (threshold %.1f°C)",
                    name, alert.alert_type, temp, alert.threshold,
                )

        return events

    @staticmethod
    def _is_violated(alert: AlertRule, temp: float) -> bool:
        """Check if a temperature violates the alert threshold."""
        if alert.alert_type == "temp_low":
            return temp < alert.threshold
        elif alert.alert_type == "temp_high":
            return temp > alert.threshold
        return False
```

**Step 2: Run compile check**

Run: `python3 -m py_compile hutwatch/alerts.py`
Expected: No output (success)

**Step 3: Commit**

```bash
git add hutwatch/alerts.py
git commit -m "Add AlertManager component for temperature threshold alerts"
```

---

### Task 4: Integrate AlertManager into Aggregator

**Files:**
- Modify: `hutwatch/aggregator.py`

**Step 1: Add AlertManager parameter to Aggregator**

In `hutwatch/aggregator.py`, add import at line 10 (after existing imports):

```python
from .alerts import AlertManager
```

Modify `__init__` (line 29-43) to accept `alert_manager` and `alert_callback`:

After `self._weather = weather` (line 39), add:

```python
        self._alert_manager: Optional[AlertManager] = None
        self._alert_callback: Optional[object] = None  # async callable
```

Add a setter method after `set_weather` (after line 62):

```python
    def set_alert_manager(
        self, manager: AlertManager, callback: object,
    ) -> None:
        """Set alert manager and callback for alert events."""
        self._alert_manager = manager
        self._alert_callback = callback
```

**Step 2: Add alert check to _aggregate()**

At the end of `_aggregate()` method, after the `for sensor_config in self._config.sensors:` loop (after line 171), add:

```python
        # Check alert thresholds
        if self._alert_manager and self._alert_callback:
            try:
                # Build current readings dict from store
                current_readings = {}
                device_names = {}
                for sensor_config in self._config.sensors:
                    mac = sensor_config.mac
                    latest = self._store.get_latest(mac)
                    if latest:
                        current_readings[mac] = latest
                        device = self._db.get_device(mac)
                        if device:
                            device_names[mac] = device.get_display_name()
                        else:
                            device_names[mac] = sensor_config.name

                events = self._alert_manager.check(current_readings, device_names)
                if events:
                    await self._alert_callback(events)
            except Exception as e:
                logger.error("Alert check error: %s", e)
```

**Step 3: Verify SensorStore has get_latest method**

Check `hutwatch/ble/sensor_store.py` for `get_latest()`. If it doesn't exist, we need to add it or use `get_history(mac, hours=1)[-1]` instead. Adjust the code accordingly.

Run: `grep -n 'def get_latest' hutwatch/ble/sensor_store.py`

If no `get_latest` exists, replace the `latest = self._store.get_latest(mac)` line with:

```python
                    history = self._store.get_history(mac, hours=1)
                    if history:
                        current_readings[mac] = history[-1]
                        ...
```

**Step 4: Run compile check**

Run: `python3 -m py_compile hutwatch/aggregator.py`
Expected: No output (success)

**Step 5: Commit**

```bash
git add hutwatch/aggregator.py
git commit -m "Integrate AlertManager into aggregator for periodic threshold checks"
```

---

### Task 5: Wire AlertManager into HutWatchApp

**Files:**
- Modify: `hutwatch/app.py`

**Step 1: Add import**

Add at line 11 (after `from .aggregator import Aggregator`):

```python
from .alerts import AlertManager
```

**Step 2: Add instance variable**

In `__init__`, after `self._aggregator: Optional[Aggregator] = None` (line 57), add:

```python
        self._alert_manager: Optional[AlertManager] = None
```

**Step 3: Initialize AlertManager in start()**

After `self._aggregator = Aggregator(...)` (line 113), add:

```python
        # Initialize alert manager
        self._alert_manager = AlertManager(self._db)
        self._aggregator.set_alert_manager(self._alert_manager, self._emit_alerts)
```

**Step 4: Add emit_alerts method**

Add before the `run()` method (before line 288):

```python
    async def _emit_alerts(self, events: list) -> None:
        """Route alert events to the active UI."""
        from .alerts import AlertEvent
        from .i18n import t

        for event in events:
            if event.is_recovery:
                text = t("alert_recovery",
                         name=event.device_name,
                         temp=event.current_value,
                         threshold=event.threshold)
            else:
                direction = t("alert_direction_below") if event.alert_type == "temp_low" else t("alert_direction_above")
                text = t("alert_triggered",
                         name=event.device_name,
                         temp=event.current_value,
                         direction=direction,
                         threshold=event.threshold)

            # Send to Telegram
            if self._bot:
                try:
                    await self._bot.send_message(text)
                except Exception as e:
                    logger.error("Failed to send alert to Telegram: %s", e)

            # Send to TUI
            if self._tui:
                self._tui.add_alert_event(event)

            logger.info("Alert: %s", text)
```

**Step 5: Expose alert_manager for command handlers**

The Telegram `CommandHandlers` and TUI need access to `AlertManager`. This is handled by passing it as a constructor parameter in the next tasks.

**Step 6: Update bot creation to pass alert_manager**

In `start()`, where `TelegramBot` is created (line 144), change to:

```python
            self._bot = TelegramBot(
                self._config, self._store, self._db, self._weather,
                remote=self._remote, alert_manager=self._alert_manager,
            )
```

And where `TuiDashboard` is created (line 173), change to:

```python
                self._tui = TuiDashboard(
                    self._config, self._store, self._db, self._weather,
                    app=self, remote=self._remote, alert_manager=self._alert_manager,
                )
```

**Step 7: Run compile check**

Run: `python3 -m py_compile hutwatch/app.py`
Expected: No output (success)

**Step 8: Commit**

```bash
git add hutwatch/app.py
git commit -m "Wire AlertManager into HutWatchApp with emit_alerts routing"
```

---

### Task 6: Add /alert command to Telegram bot

**Files:**
- Modify: `hutwatch/telegram/commands.py`
- Modify: `hutwatch/telegram/bot.py`

**Step 1: Add alert_manager parameter to CommandHandlers**

In `hutwatch/telegram/commands.py`, add to `__init__` signature (after `remote` param):

```python
        alert_manager: Optional[object] = None,
```

And store it:

```python
        self._alert_manager = alert_manager
```

**Step 2: Add /alert command handler**

Add to `CommandHandlers` class, after the `showhidden` method (after line 1441):

```python
    async def alert(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Handle /alert command - manage temperature alerts."""
        if not update.effective_message or not self._db or not self._alert_manager:
            return

        args = context.args or []

        # No args: list all alerts
        if not args:
            await self._alert_list(update)
            return

        # Need at least: <device> <low/high> <value/off>
        # Or: <device> recovery <on/off>
        if len(args) < 2:
            await update.effective_message.reply_text(
                t("tg_alert_usage"), parse_mode="Markdown",
            )
            return

        # Parse device identifier (could be multi-word)
        # Strategy: last 2 args are type+value, rest is device identifier
        last_arg = args[-1].lower()
        second_last = args[-2].lower() if len(args) >= 3 else None

        # Handle: <device> recovery on/off
        if second_last == "recovery" and last_arg in ("on", "off"):
            identifier = " ".join(args[:-2])
            if not identifier:
                await update.effective_message.reply_text(
                    t("tg_alert_usage"), parse_mode="Markdown",
                )
                return
            device = self._resolve_device(identifier)
            if not device:
                await update.effective_message.reply_text(
                    t("common_sensor_not_found", identifier=identifier),
                    parse_mode="Markdown",
                )
                return
            enabled = last_arg == "on"
            # Set recovery for both alert types
            found = False
            for at in ("temp_low", "temp_high"):
                if self._alert_manager.set_notify_recovery(device.mac, at, enabled):
                    found = True
            if found:
                name = device.get_display_name()
                type_label = t("alert_temp_low") + "/" + t("alert_temp_high")
                msg_key = "alert_recovery_on" if enabled else "alert_recovery_off"
                await update.effective_message.reply_text(
                    t(msg_key, name=name, type=type_label),
                    parse_mode="Markdown",
                )
            else:
                name = device.get_display_name()
                await update.effective_message.reply_text(
                    t("alert_not_found", name=name, type="recovery"),
                    parse_mode="Markdown",
                )
            return

        # Handle: <device> <low/high> <value/off>
        if len(args) >= 3 and second_last in ("low", "high"):
            identifier = " ".join(args[:-2])
            alert_type = "temp_low" if second_last == "low" else "temp_high"
            type_label = t("alert_temp_low") if second_last == "low" else t("alert_temp_high")
        elif len(args) >= 2 and args[-2].lower() in ("low", "high"):
            # Only 2 args: could be "<num> low" which is incomplete
            await update.effective_message.reply_text(
                t("tg_alert_usage"), parse_mode="Markdown",
            )
            return
        else:
            await update.effective_message.reply_text(
                t("tg_alert_usage"), parse_mode="Markdown",
            )
            return

        device = self._resolve_device(identifier)
        if not device:
            await update.effective_message.reply_text(
                t("common_sensor_not_found", identifier=identifier),
                parse_mode="Markdown",
            )
            return

        name = device.get_display_name()

        if last_arg == "off":
            # Remove alert
            if self._alert_manager.remove_alert(device.mac, alert_type):
                await update.effective_message.reply_text(
                    t("alert_removed", name=name, type=type_label),
                    parse_mode="Markdown",
                )
            else:
                await update.effective_message.reply_text(
                    t("alert_not_found", name=name, type=type_label),
                    parse_mode="Markdown",
                )
        else:
            # Set alert
            try:
                threshold = float(last_arg)
            except ValueError:
                await update.effective_message.reply_text(
                    t("tg_alert_usage"), parse_mode="Markdown",
                )
                return
            self._alert_manager.set_alert(device.mac, alert_type, threshold)
            await update.effective_message.reply_text(
                t("alert_set_success", name=name, type=type_label, threshold=threshold),
                parse_mode="Markdown",
            )

    async def _alert_list(self, update: Update) -> None:
        """Show all configured alerts."""
        alerts = self._alert_manager.get_alerts()
        if not alerts:
            await update.effective_message.reply_text(
                t("alert_none"), parse_mode="Markdown",
            )
            return

        lines = [t("alert_list_header")]
        for alert in alerts:
            device = self._db.get_device(alert.mac)
            if not device:
                continue
            name = device.get_display_name()
            type_label = t("alert_temp_low") if alert.alert_type == "temp_low" else t("alert_temp_high")
            if not alert.enabled:
                status = t("alert_status_disabled")
            elif alert.triggered:
                status = t("alert_status_triggered")
            else:
                status = t("alert_status_ok")
            lines.append(t("alert_list_item",
                          order=device.display_order,
                          name=name,
                          type=type_label,
                          threshold=alert.threshold,
                          status=status))

        await update.effective_message.reply_text(
            "\n".join(lines), parse_mode="Markdown",
        )
```

**Step 3: Register command in bot.py**

In `hutwatch/telegram/bot.py`:

1. Add `alert_manager` param to `TelegramBot.__init__` (after `remote`):

```python
        alert_manager: Optional[object] = None,
```

2. Pass it to `CommandHandlers`:

```python
        self._commands = CommandHandlers(config, store, db, weather, remote=remote, alert_manager=alert_manager)
```

3. Register command handlers in `start()`, after the `showhidden` handler (after line 79):

```python
        self._app.add_handler(CommandHandler("alert", self._commands.alert))
        self._app.add_handler(CommandHandler("halytys", self._commands.alert))
```

**Step 4: Update Telegram help text**

Add alert commands to the help strings. In `strings_fi.py`, inside `tg_help_full`, add after the device management section:

```
        "\n"
        "*Hälytykset:*\n"
        "/alert - Näytä hälytykset\n"
        "/alert <nro> low/high <arvo> - Aseta raja\n"
        "/alert <nro> low/high off - Poista raja\n"
```

And in `strings_en.py`, inside `tg_help_full`:

```
        "\n"
        "*Alerts:*\n"
        "/alert - Show alerts\n"
        "/alert <num> low/high <value> - Set threshold\n"
        "/alert <num> low/high off - Remove threshold\n"
```

**Step 5: Run compile check**

Run: `python3 -m py_compile hutwatch/telegram/commands.py && python3 -m py_compile hutwatch/telegram/bot.py`
Expected: No output (success)

**Step 6: Commit**

```bash
git add hutwatch/telegram/commands.py hutwatch/telegram/bot.py hutwatch/strings_fi.py hutwatch/strings_en.py
git commit -m "Add /alert Telegram command for managing temperature alerts"
```

---

### Task 7: Add alert commands and indicator to TUI

**Files:**
- Modify: `hutwatch/tui.py`

**Step 1: Add alert_manager parameter to TuiDashboard**

In `__init__` signature (around line 97), add `alert_manager` parameter:

```python
        alert_manager: Optional[object] = None,
```

Store it:

```python
        self._alert_manager = alert_manager
        self._alert_events: list = []  # Recent alert events for display
```

Add the `add_alert_event` method (called by `app._emit_alerts`):

```python
    def add_alert_event(self, event: object) -> None:
        """Add an alert event for dashboard display."""
        self._alert_events.append(event)
```

**Step 2: Add 'a' to _INPUT_KEYS**

Change line 51:

```python
_INPUT_KEYS = frozenset('ahsgnpwu')
```

**Step 3: Add alert command handling**

In `_handle_command()` (around line 323), add before the `self._status_msg = t("tui_unknown_command", cmd=cmd)` line (line 413):

```python
        if cmd == "a":
            self._handle_alert_cmd(parts[1:])
            return
```

**Step 4: Add _handle_alert_cmd method**

Add after `_handle_weather_cmd` (after line 526):

```python
    def _handle_alert_cmd(self, args: list[str]) -> None:
        """Handle alert command: a, a <n> low/high <value>, a <n> low/high off."""
        if not self._alert_manager:
            self._status_msg = t("common_db_not_available")
            return

        if not args:
            # Show alerts list
            self._view = "alerts"
            return

        # Need: <device> <low/high> <value/off>
        # Or: <device> recovery <on/off>
        if len(args) < 3:
            self._status_msg = t("tui_alert_usage")
            return

        identifier = args[0]
        device = resolve_device(identifier, self._db, self._config)
        if not device:
            self._status_msg = t("tui_sensor_not_found", identifier=identifier)
            return

        action = args[1].lower()
        value = args[2].lower()
        name = device.get_display_name()

        if action == "recovery":
            enabled = value == "on"
            for at in ("temp_low", "temp_high"):
                self._alert_manager.set_notify_recovery(device.mac, at, enabled)
            msg_key = "alert_recovery_on" if enabled else "alert_recovery_off"
            type_label = t("alert_temp_low") + "/" + t("alert_temp_high")
            self._status_msg = t(msg_key, name=name, type=type_label)
            return

        if action not in ("low", "high"):
            self._status_msg = t("tui_alert_usage")
            return

        alert_type = "temp_low" if action == "low" else "temp_high"
        type_label = t("alert_temp_low") if action == "low" else t("alert_temp_high")

        if value == "off":
            if self._alert_manager.remove_alert(device.mac, alert_type):
                self._status_msg = t("alert_removed", name=name, type=type_label)
            else:
                self._status_msg = t("alert_not_found", name=name, type=type_label)
        else:
            try:
                threshold = float(value)
            except ValueError:
                self._status_msg = t("tui_alert_usage")
                return
            self._alert_manager.set_alert(device.mac, alert_type, threshold)
            self._status_msg = t("alert_set_success", name=name, type=type_label, threshold=threshold)
```

**Step 5: Add alert indicator to dashboard**

In `_render_sensor_lines()` (line 733), after the parts list is built and before `result.append("  ".join(parts))` (line 786), add:

```python
                # Alert indicator
                if self._alert_manager:
                    for alert in self._alert_manager.get_alerts(mac):
                        if alert.triggered:
                            parts.append(f"{RED}{t('tui_alert_indicator')}{RESET}")
                            break
```

**Step 6: Add alerts view rendering**

In the main render dispatcher (find `_render_` method calls for different views), add a case for `"alerts"` view. Look for the pattern where `_view` is checked to decide which render method to call. Add:

```python
        elif self._view == "alerts":
            self._render_alerts(lines, cols)
```

Then add the render method:

```python
    def _render_alerts(self, lines: list[str], cols: int) -> None:
        """Render the alerts view."""
        from .i18n import t

        lines.append(f"{BOLD}🔔 {t('alert_list_header').strip()}{RESET}")
        lines.append("")

        if not self._alert_manager:
            lines.append(t("alert_none"))
            return

        alerts = self._alert_manager.get_alerts()
        if not alerts:
            lines.append(t("alert_none"))
            return

        for alert in alerts:
            device = self._db.get_device(alert.mac)
            if not device:
                continue
            name = device.get_display_name()
            type_label = t("alert_temp_low") if alert.alert_type == "temp_low" else t("alert_temp_high")
            if not alert.enabled:
                status = t("alert_status_disabled")
            elif alert.triggered:
                status = f"{RED}{t('alert_status_triggered')}{RESET}"
            else:
                status = f"{GREEN}{t('alert_status_ok')}{RESET}"
            recovery = " 🔔" if alert.notify_recovery else ""
            lines.append(
                f"  {device.display_order}. {name}: {type_label} {alert.threshold:.1f}°C {status}{recovery}"
            )

        lines.append("")
        lines.append(f"{DIM}{t('tui_alert_usage')}{RESET}")
```

**Step 7: Add alert command to TUI footer**

In the footer rendering section, add `t("tui_cmd_alert")` to the list of commands shown.

**Step 8: Run compile check**

Run: `python3 -m py_compile hutwatch/tui.py`
Expected: No output (success)

**Step 9: Commit**

```bash
git add hutwatch/tui.py
git commit -m "Add alert commands and triggered indicator to TUI dashboard"
```

---

### Task 8: Run full lint and test in demo mode

**Step 1: Run i18n check**

Run: `python3 scripts/check_i18n.py`
Expected: PASS

**Step 2: Run py_compile on all modified files**

Run: `python3 -m py_compile hutwatch/alerts.py hutwatch/db.py hutwatch/aggregator.py hutwatch/app.py hutwatch/tui.py hutwatch/telegram/commands.py hutwatch/telegram/bot.py`
Expected: No output (success)

**Step 3: Run import check**

Run: `python3 scripts/check_imports.py`
Expected: PASS

**Step 4: Test demo mode**

Run: `timeout 5 python3 -m hutwatch --demo 2>&1 || true`
Expected: TUI renders without crash

**Step 5: Final commit if any fixes needed**

```bash
git add -A
git commit -m "Fix lint issues from alert system integration"
```

---

### Task 9: Create GitHub issue and close it

**Step 1: Create issue (if not already created)**

```bash
gh issue create --title "Add temperature threshold alert system" \
  --body "Temperature alerts that fire when thresholds are crossed. Telegram notifications + TUI indicators. See docs/plans/2026-03-02-alert-system-design.md"
```

**Step 2: Close issue after implementation**

```bash
gh issue close <N>
```
