"""Alert manager for temperature threshold monitoring."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .db import Database
    from .models import SensorReading

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
