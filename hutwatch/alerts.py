"""Alert manager for temperature, battery and silence monitoring."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .db import Database
    from .models import DeviceInfo, DeviceWatchdogConfig, SensorReading

logger = logging.getLogger(__name__)

# Alert types that re-notify while the condition persists
REMINDING_TYPES = ("batt_low", "silent")

# Alert types whose rules are provisioned from config defaults
AUTO_TYPES = ("batt_low", "silent")


@dataclass
class AlertRule:
    """A configured alert threshold."""

    mac: str
    alert_type: str  # 'temp_low', 'temp_high', 'batt_low' or 'silent'
    threshold: float
    enabled: bool
    triggered: bool
    notify_recovery: bool
    unit: str = "C"  # 'C', 'V', '%' or 'h'
    auto: bool = False
    last_triggered: Optional[datetime] = None


@dataclass
class AlertEvent:
    """An alert that has fired, recovered, or is being repeated."""

    mac: str
    device_name: str
    alert_type: str
    threshold: float
    current_value: float
    is_recovery: bool
    unit: str = "C"
    is_reminder: bool = False


@dataclass
class DeviceHealth:
    """Non-temperature inputs for one device's alert evaluation."""

    battery_value: Optional[float] = None
    battery_unit: Optional[str] = None  # 'V' or '%'
    silent_hours: Optional[float] = None
    temperature: Optional[float] = None


@dataclass
class AlertInputs:
    """Everything AlertManager.check() needs for one evaluation pass."""

    readings: dict[str, "SensorReading"] = field(default_factory=dict)
    device_names: dict[str, str] = field(default_factory=dict)
    health: dict[str, DeviceHealth] = field(default_factory=dict)
    check_silence: bool = True


class AlertManager:
    """Manages threshold alerts for temperature, battery level and silence.

    Call check() with the current inputs to detect threshold crossings.
    Returns AlertEvent objects for newly triggered, recovered, or repeated alerts.
    """

    def __init__(
        self, db: "Database", watchdog: Optional["DeviceWatchdogConfig"] = None,
    ) -> None:
        self._db = db
        self._watchdog = watchdog

    def set_alert(
        self,
        mac: str,
        alert_type: str,
        threshold: float,
        notify_recovery: bool = False,
        unit: str = "C",
    ) -> None:
        """Create or update a user-defined alert rule."""
        self._db.set_alert(
            mac, alert_type, threshold, notify_recovery, unit=unit, auto=False,
        )

    def remove_alert(self, mac: str, alert_type: str) -> bool:
        """Remove an alert rule.

        Auto-provisioned types are disabled instead of deleted — deleting them
        would only make the next provisioning pass recreate the rule.
        """
        if alert_type in AUTO_TYPES:
            return self._db.set_alert_enabled(mac, alert_type, False)
        return self._db.remove_alert(mac, alert_type)

    def get_alerts(self, mac: Optional[str] = None) -> list[AlertRule]:
        """Get alert rules as AlertRule objects."""
        rows = self._db.get_alerts(mac)
        return [self._row_to_rule(row) for row in rows]

    def set_notify_recovery(self, mac: str, alert_type: str, enabled: bool) -> bool:
        """Set recovery notification flag."""
        return self._db.set_alert_notify_recovery(mac, alert_type, enabled)

    def sync_default_rules(
        self,
        devices: list["DeviceInfo"],
        battery_units: dict[str, str],
    ) -> None:
        """Provision auto-managed battery and silence rules from config defaults.

        Battery rules are only created for devices that actually report a
        battery level, since the threshold unit comes from what they report.
        Hidden devices are skipped entirely.
        """
        if not self._watchdog:
            return

        wd = self._watchdog
        for device in devices:
            if device.hidden:
                continue

            unit = battery_units.get(device.mac)
            if unit == "V" and wd.battery_voltage_low > 0:
                self._db.ensure_alert_default(
                    device.mac, "batt_low", wd.battery_voltage_low, "V",
                )
            elif unit == "%" and wd.battery_percent_low > 0:
                self._db.ensure_alert_default(
                    device.mac, "batt_low", float(wd.battery_percent_low), "%",
                )

            if wd.silent_hours > 0:
                self._db.ensure_alert_default(
                    device.mac, "silent", float(wd.silent_hours), "h",
                )

    def check(self, inputs: AlertInputs) -> list[AlertEvent]:
        """Check all alert rules against the current inputs.

        Returns AlertEvent objects for alerts that newly triggered, recovered,
        or are due for a reminder.
        """
        events: list[AlertEvent] = []

        for alert in self.get_alerts():
            if not alert.enabled:
                continue

            value = self._current_value(alert, inputs)
            if value is None:
                continue

            name = inputs.device_names.get(alert.mac, alert.mac)
            event = self._evaluate(alert, value, name)
            if event:
                events.append(event)

        return events

    # ── Internals ─────────────────────────────────────────────────────

    def _current_value(
        self, alert: AlertRule, inputs: AlertInputs,
    ) -> Optional[float]:
        """Resolve the value this rule compares against, or None to skip."""
        if alert.alert_type in ("temp_low", "temp_high"):
            reading = inputs.readings.get(alert.mac)
            return reading.temperature if reading else None

        health = inputs.health.get(alert.mac)
        if not health:
            return None

        if alert.alert_type == "batt_low":
            if health.battery_value is None:
                return None
            # Unit mismatch means the rule predates a firmware/sensor change
            if health.battery_unit and health.battery_unit != alert.unit:
                return None
            # Battery voltage sags in frost and recovers when the sensor warms,
            # so a cold reading is not evidence of a dying cell.
            if (
                self._watchdog
                and health.temperature is not None
                and health.temperature < self._watchdog.cold_grace_temp
            ):
                return None
            return health.battery_value

        if alert.alert_type == "silent":
            if not inputs.check_silence:
                return None
            return health.silent_hours

        return None

    def _evaluate(
        self, alert: AlertRule, value: float, name: str,
    ) -> Optional[AlertEvent]:
        """Run the trigger/recover/remind state machine for one rule."""
        violated = self._is_violated(alert, value)

        if violated and not alert.triggered:
            self._db.update_alert_triggered(alert.mac, alert.alert_type, True)
            logger.info(
                "Alert triggered: %s %s %.2f%s (threshold %.2f%s)",
                name, alert.alert_type, value, alert.unit, alert.threshold, alert.unit,
            )
            return self._event(alert, value, name)

        if violated and alert.triggered and self._reminder_due(alert):
            self._db.touch_alert_triggered(alert.mac, alert.alert_type)
            logger.info(
                "Alert reminder: %s %s %.2f%s", name, alert.alert_type, value, alert.unit,
            )
            return self._event(alert, value, name, is_reminder=True)

        if not violated and alert.triggered:
            self._db.update_alert_triggered(alert.mac, alert.alert_type, False)
            logger.info(
                "Alert recovered: %s %s %.2f%s (threshold %.2f%s)",
                name, alert.alert_type, value, alert.unit, alert.threshold, alert.unit,
            )
            # Auto-provisioned alerts always report recovery — a battery that
            # was replaced or a device that came back is worth knowing about.
            if alert.notify_recovery or alert.alert_type in AUTO_TYPES:
                return self._event(alert, value, name, is_recovery=True)

        return None

    def _reminder_due(self, alert: AlertRule) -> bool:
        """Check whether a still-violated alert should re-notify."""
        if alert.alert_type not in REMINDING_TYPES:
            return False
        if not self._watchdog or self._watchdog.remind_days <= 0:
            return False
        if alert.last_triggered is None:
            return True
        elapsed = datetime.now() - alert.last_triggered
        return elapsed >= timedelta(days=self._watchdog.remind_days)

    @staticmethod
    def _event(
        alert: AlertRule,
        value: float,
        name: str,
        is_recovery: bool = False,
        is_reminder: bool = False,
    ) -> AlertEvent:
        return AlertEvent(
            mac=alert.mac,
            device_name=name,
            alert_type=alert.alert_type,
            threshold=alert.threshold,
            current_value=value,
            is_recovery=is_recovery,
            unit=alert.unit,
            is_reminder=is_reminder,
        )

    @staticmethod
    def _row_to_rule(row: dict) -> AlertRule:
        """Build an AlertRule from a database row."""
        last_triggered = None
        raw = row.get("last_triggered")
        if raw:
            try:
                last_triggered = datetime.strptime(raw, "%Y-%m-%d %H:%M:%S")
            except (ValueError, TypeError):
                last_triggered = None

        return AlertRule(
            mac=row["mac"],
            alert_type=row["alert_type"],
            threshold=row["threshold"],
            enabled=bool(row["enabled"]),
            triggered=bool(row["triggered"]),
            notify_recovery=bool(row["notify_recovery"]),
            unit=row.get("unit") or "C",
            auto=bool(row.get("auto", 0)),
            last_triggered=last_triggered,
        )

    @staticmethod
    def _is_violated(alert: AlertRule, value: float) -> bool:
        """Check if a value violates the alert threshold."""
        if alert.alert_type in ("temp_low", "batt_low"):
            return value < alert.threshold
        if alert.alert_type in ("temp_high", "silent"):
            return value > alert.threshold
        return False

