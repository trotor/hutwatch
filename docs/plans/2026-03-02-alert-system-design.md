# Alert System Design

## Summary

Temperature threshold alerts for HutWatch sensors. Alerts fire once when a threshold is crossed and reset when the value returns to normal. Notifications via Telegram messages and TUI dashboard indicators.

## Requirements

- **Monitored values:** temperature only (min/max per device)
- **Management:** Telegram commands + TUI commands, stored in SQLite database
- **Alert logic:** fire once when threshold crossed, reset when value returns to normal
- **Recovery notifications:** configurable per alert (on/off)
- **Check interval:** every 5 minutes (piggybacks on aggregation cycle)
- **Notification channels:** Telegram message + TUI warning indicator

## Data Model

### Database table `alerts`

```sql
CREATE TABLE IF NOT EXISTS alerts (
    mac TEXT NOT NULL,
    alert_type TEXT NOT NULL,       -- 'temp_low' or 'temp_high'
    threshold REAL NOT NULL,
    enabled INTEGER DEFAULT 1,
    triggered INTEGER DEFAULT 0,
    notify_recovery INTEGER DEFAULT 0,
    last_triggered DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (mac, alert_type)
);
```

### Dataclasses

```python
@dataclass
class AlertRule:
    mac: str
    alert_type: str          # 'temp_low' / 'temp_high'
    threshold: float
    enabled: bool
    triggered: bool
    notify_recovery: bool

@dataclass
class AlertEvent:
    mac: str
    device_name: str
    alert_type: str
    threshold: float
    current_value: float
    is_recovery: bool
```

## Component: AlertManager (`hutwatch/alerts.py`)

Standalone module with no UI dependencies.

### Interface

```python
class AlertManager:
    def __init__(self, db: Database):
        self._db = db

    # CRUD
    def set_alert(mac, alert_type, threshold, notify_recovery=False) -> None
    def remove_alert(mac, alert_type) -> None
    def get_alerts(mac=None) -> list[AlertRule]
    def enable_alert(mac, alert_type, enabled=True) -> None
    def set_notify_recovery(mac, alert_type, enabled=True) -> None

    # Check — called by aggregator
    def check(readings: dict[str, SensorReading]) -> list[AlertEvent]
```

### Check logic

1. Fetch all enabled alerts from database
2. For each alert, get latest sensor reading from `readings` dict
3. Compare value to threshold:
   - `temp_low`: alert if `value < threshold`
   - `temp_high`: alert if `value > threshold`
4. If threshold crossed and `triggered=0`: create AlertEvent, set `triggered=1`
5. If value normal and `triggered=1`: set `triggered=0`, create recovery AlertEvent if `notify_recovery=1`
6. Update database state
7. Return list of AlertEvents

## Integration: Aggregator

At the end of `Aggregator._aggregate()`, after saving readings:

```python
events = self._alert_manager.check(current_readings)
if events:
    await self._app.emit_alerts(events)
```

## Integration: HutWatchApp

- Creates `AlertManager` instance during startup
- Passes it to `Aggregator`
- `emit_alerts(events)` method routes events to the active UI:
  - Telegram: sends message via `bot.send_message()`
  - TUI: stores events for dashboard display

## Telegram Commands

| Command | Action |
|---------|--------|
| `/alert` | List all alerts with status |
| `/alert <device> low <value>` | Set low threshold |
| `/alert <device> high <value>` | Set high threshold |
| `/alert <device> low off` | Remove low threshold |
| `/alert <device> high off` | Remove high threshold |
| `/alert <device> recovery on/off` | Toggle recovery notification |

Finnish alias: `/halytys`

### Message formats

Alert triggered:
```
⚠️ Mökki: Lämpötila 0.5°C alittaa rajan 1.0°C
```

Recovery:
```
✅ Mökki: Lämpötila palautunut normaaliksi (3.2°C, raja 1.0°C)
```

## TUI Commands

| Command | Action |
|---------|--------|
| `a` | List all alerts |
| `a <n> low <value>` | Set low threshold |
| `a <n> high <value>` | Set high threshold |
| `a <n> low off` | Remove |
| `a <n> high off` | Remove |
| `a <n> recovery on/off` | Toggle recovery notification |

Dashboard indicator: `⚠` after temperature value when alert is triggered.

## Files to Create/Modify

| File | Change |
|------|--------|
| `hutwatch/alerts.py` | NEW — AlertManager, AlertRule, AlertEvent |
| `hutwatch/db.py` | New alerts table + CRUD methods |
| `hutwatch/aggregator.py` | Call AlertManager.check() after aggregation |
| `hutwatch/app.py` | Create AlertManager, add emit_alerts() |
| `hutwatch/telegram/commands.py` | /alert command handler |
| `hutwatch/telegram/bot.py` | Register command + alert message sending |
| `hutwatch/tui.py` | `a` command + warning indicator in dashboard |
| `hutwatch/strings_fi.py` | Alert-related Finnish strings |
| `hutwatch/strings_en.py` | Alert-related English strings |

## Not in scope

- Humidity alerts (future expansion possible with same architecture)
- Weather alerts
- Console mode alerts
- Config.yaml alert definitions
- Alert history/log
