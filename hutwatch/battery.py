"""Low-battery detection that tolerates temperature-induced voltage dips.

Coin cell voltage drops sharply in the cold, so the instantaneous reading
says little about remaining capacity. Instead we look at a rolling window
of history and ask: did the battery reach a healthy voltage *for its
temperature* at any point? If yes, it is fine — the low readings were just
cold nights. Only when every sample in the window is below its
temperature-adjusted threshold is the battery considered low.

Hysteresis prevents the flag from flickering around the threshold.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Iterable, Optional

if TYPE_CHECKING:
    from .ble.sensor_store import SensorStore
    from .db import Database

logger = logging.getLogger(__name__)

# Look-back window for battery evaluation
BATTERY_WINDOW_HOURS = 72
# Minimum history span before a "low" verdict is trusted
BATTERY_MIN_COVERAGE_HOURS = 24
# Once low, the battery must exceed its threshold by this much to clear
BATTERY_HYSTERESIS_V = 0.10

# Temperature-dependent low-voltage thresholds (same bands as Ruuvi Station)
BATTERY_LOW_V_WARM = 2.5   # temp >= 0 °C
BATTERY_LOW_V_COLD = 2.3   # -20 °C < temp < 0 °C
BATTERY_LOW_V_FROST = 2.0  # temp <= -20 °C

# (timestamp, battery_voltage, temperature)
BatterySample = tuple[datetime, Optional[float], Optional[float]]


def battery_threshold(temp_c: float) -> float:
    """Return the low-voltage threshold for a given temperature."""
    if temp_c <= -20:
        return BATTERY_LOW_V_FROST
    if temp_c < 0:
        return BATTERY_LOW_V_COLD
    return BATTERY_LOW_V_WARM


def battery_low_state(
    samples: Iterable[BatterySample],
    was_low: bool = False,
) -> Optional[bool]:
    """Evaluate battery state from a window of samples.

    Returns True (low), False (ok) or None (unknown: no data, or too little
    history to call it low).
    """
    valid = [(ts, v, tc) for ts, v, tc in samples if v is not None and tc is not None]
    if not valid:
        return None

    # Best headroom over the window: how far above its temperature-adjusted
    # threshold the battery got at its best moment.
    headroom = max(v - battery_threshold(tc) for _, v, tc in valid)

    clear_at = BATTERY_HYSTERESIS_V if was_low else 0.0
    if headroom >= clear_at:
        return False

    if was_low:
        return True

    # Not enough history to rule out "just a cold spell"
    timestamps = [ts for ts, _, _ in valid]
    span = max(timestamps) - min(timestamps)
    if span < timedelta(hours=BATTERY_MIN_COVERAGE_HOURS):
        return None

    return True


def update_battery_states(
    store: "SensorStore",
    db: "Database",
    macs: Iterable[str],
) -> None:
    """Recompute low-battery flags for the given sensors into the store."""
    now = datetime.now()
    cutoff = now - timedelta(hours=BATTERY_WINDOW_HOURS)

    for mac in macs:
        try:
            samples: list[BatterySample] = list(db.get_battery_samples(mac, BATTERY_WINDOW_HOURS))
            # Include in-memory readings (covers a fresh DB / not-yet-aggregated data)
            samples.extend(
                (r.timestamp, r.battery_voltage, r.temperature)
                for r in store.get_history(mac, hours=BATTERY_WINDOW_HOURS)
                if r.timestamp >= cutoff
            )

            was_low = store.get_battery_low(mac) is True
            state = battery_low_state(samples, was_low=was_low)
            if state != store.get_battery_low(mac):
                logger.info("Battery state for %s: %s", mac, {True: "low", False: "ok", None: "unknown"}[state])
            store.set_battery_low(mac, state)
        except Exception as e:
            logger.error("Battery state update failed for %s: %s", mac, e)


def remote_battery_low(store: "SensorStore", sensor: object) -> bool:
    """Low-battery state for a remote/peer sensor.

    Prefer the flag the peer computed itself; older peers don't send one, so
    fall back to the state evaluated from their flushed history locally.
    """
    flag = getattr(sensor, "battery_low", None)
    if flag is None:
        mac = getattr(sensor, "mac", "") or ""
        flag = store.get_battery_low(mac) if mac else None
    return bool(flag)
