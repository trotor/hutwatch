# Battery & Silence Alerts — Implementation Plan

> **Superseded in part (2026-11-10, #17):** auto-provisioned battery alerts flapped around the
> threshold, so battery thresholds now default to 0 (off) and low batteries are shown as a
> temperature-aware UI marker (`hutwatch/battery.py`). Silence alerts and opt-in battery alerts
> work as described below.

**Issue:** [#16](https://github.com/trotor/hutwatch/issues/16)

**Goal:** Warn about draining batteries and devices that have gone quiet, automatically and repeatedly, without per-device setup.

**Architecture:** Reuse the existing `alerts` table and `AlertManager` rather than building a parallel mechanism. Two new `alert_type` values (`batt_low`, `silent`) join `temp_low`/`temp_high`; the threshold column becomes unit-aware via a new `unit` column. Rules are auto-provisioned per device from `config.yaml` defaults and marked `auto=1` so config changes propagate to rules the user has never touched. The aggregator's existing 5-minute alert pass feeds battery values and last-seen timestamps into the same `AlertManager.check()` call, and `HutWatchApp._emit_alerts()` formats per type.

**Tech stack:** Python 3.10+, SQLite, python-telegram-bot (existing), async/await.

---

## Design decisions

**Unit-aware thresholds.** Ruuvi reports volts (~2.2–3.0 V), Xiaomi ATC/PVVX reports percent. Rather than two alert types, one `batt_low` type carries a `unit` (`V` or `%`) resolved from what the device actually reports at rule-creation time. `unit` also covers `C` (temperature, the default for existing rows) and `h` (silence hours), which lets one formatting path serve every type.

**`off` disables, it does not delete.** Auto-provisioning would immediately recreate a deleted row. `a 1 batt off` therefore sets `enabled=0`; the UI already renders a disabled state (`alert_status_disabled`). Temperature alerts keep their current delete-on-`off` behavior since nothing re-creates them.

**Cold grace.** CR2477 voltage sags in frost and recovers when the sensor warms. Without a guard every cold night would fire a battery warning, so battery evaluation is skipped while the sensor reads below `cold_grace_temp` (default −15 °C).

**Startup grace.** At startup the sensor store is empty and every device's last DB reading is old, so silence checks are suppressed for the first 15 minutes while BLE picks up advertisements.

**Reminders apply to the new types only.** `batt_low` and `silent` re-notify every `remind_days`; `temp_low`/`temp_high` keep firing once per crossing, unchanged.

**No colored text in Telegram.** The Bot API has no color attribute. The `<pre><code class="language-diff">` syntax-highlight trick is the only real-color option and was rejected: it needs `parse_mode="HTML"` (the codebase is Markdown throughout), forces monospace, varies by client version, and shows no color in notification previews. Status is conveyed with emoji, matching `/status`.

---

### Task 1: Database — schema, defaults, last-seen query

**Files:** `hutwatch/db.py`

- Add two additive migrations next to the existing `hidden` / `site` ones, each in its own `try/except`:
  `ALTER TABLE alerts ADD COLUMN unit TEXT DEFAULT 'C'` and `ALTER TABLE alerts ADD COLUMN auto INTEGER DEFAULT 0`.
- `set_alert(...)` gains `unit: str = "C"` and `auto: bool = False`. Preserve the existing `triggered`/`last_triggered` state on update instead of the current `INSERT OR REPLACE` reset — re-setting a threshold must not silently clear an active alert's reminder clock.
- `ensure_alert_default(mac, alert_type, threshold, unit)` — insert when absent; when present and `auto=1`, update the threshold to the current config default; when `auto=0`, leave the user's value alone.
- `set_alert_enabled(mac, alert_type, enabled) -> bool`.
- `touch_alert_triggered(mac, alert_type)` — bump `last_triggered` without changing `triggered`, for reminders.
- `get_alert_last_triggered(mac, alert_type)` is not needed separately; return `last_triggered` from `get_alerts()` rows.
- `get_last_reading_times() -> dict[str, datetime]` — `SELECT mac, MAX(timestamp) FROM readings GROUP BY mac`, for silence detection beyond the store's 24 h window.

### Task 2: Config — `device_watchdog` block

**Files:** `hutwatch/models.py`, `hutwatch/config.py`, `config.example.yaml`

- `DeviceWatchdogConfig` dataclass: `battery_voltage_low: float = 2.5`, `battery_percent_low: int = 15`, `silent_hours: int = 12`, `cold_grace_temp: float = -15.0`, `remind_days: int = 7`. Zero disables the corresponding check.
- `AppConfig.device_watchdog: DeviceWatchdogConfig`.
- Parse `device_watchdog:` in `load_config()` following the `peer_watchdog` pattern (per-field `try/except`, warn and fall back to the default).
- Document the block in `config.example.yaml` with the frost caveat.

### Task 3: AlertManager — generalize and add the two checks

**Files:** `hutwatch/alerts.py`

- `AlertRule` gains `unit: str` and `auto: bool`; `AlertEvent` gains `unit: str` and `is_reminder: bool`.
- `sync_default_rules(devices, battery_units)` — called from the aggregator pass; provisions `batt_low` (only for devices whose battery unit is known) and `silent` rules from the watchdog config, skipping hidden devices.
- Extract the trigger/recover/remind state machine into one helper used by all four types. Reminder path: rule already `triggered`, type is `batt_low` or `silent`, and `now - last_triggered >= remind_days` → emit with `is_reminder=True` and `touch_alert_triggered()`.
- `_is_violated()` extended: `batt_low` → value below threshold; `silent` → hours since last seen above threshold.
- Battery values arrive as a `mac -> (value, unit)` map; silence as `mac -> last_seen`. Cold grace is applied by the caller-supplied temperature map so `AlertManager` stays free of store/DB access.

### Task 4: Aggregator — feed the new inputs

**Files:** `hutwatch/aggregator.py`

- Extend the existing alert block to build, alongside `current_readings`/`device_names`: battery values with units (latest local reading; `RemoteSensor` fields for peers), and last-seen times (`SensorStore` first, `db.get_last_reading_times()` as fallback; `age_seconds` for remote sensors).
- Skip hidden devices and sensors belonging to offline peer sites — the peer watchdog already covers a whole site going dark.
- Track app start time to enforce the 15-minute startup grace on silence checks.

### Task 5: Alert routing and message formatting

**Files:** `hutwatch/app.py`

- `_emit_alerts()` branches on `alert_type`: temperature keeps its current strings; `batt_low` and `silent` get their own, with a reminder variant selected by `is_reminder`.
- A shared value formatter renders `2.41V` / `14%` / `18 h` / `-3.2°C` from `unit`.

### Task 6: TUI

**Files:** `hutwatch/tui.py`

- `a <n> batt <value|off>` and `a <n> silent <hours|off>` in `_handle_alert_cmd()`; `off` disables rather than removes for these two types, and any explicit set clears `auto`.
- `_render_alerts()` prints the unit-aware threshold and marks auto-provisioned rules.
- Device list gains a battery indicator (🪫) and a silence indicator (🔇) next to the affected device.
- `add_alert_event()` is currently a stub that only logs — leave it as is; this plan does not depend on it.

### Task 7: Telegram

**Files:** `hutwatch/telegram/commands.py`

- `/alert <device> batt <value|off>` and `/alert <device> silent <hours|off>`; same disable-not-delete rule.
- `_alert_list()` renders units and the auto marker.
- `/status` appends 🪫 after the battery reading when below threshold and 🔇 when the device is silent.

### Task 8: Strings

**Files:** `hutwatch/strings_fi.py`, `hutwatch/strings_en.py`

New keys in the `alert_` group, added to both files in the same order: type labels (`alert_batt_low`, `alert_silent`), triggered/recovery/reminder messages for both new types, unit-formatting helpers, the auto marker, and updated `tg_alert_usage` / `tui_alert_usage`. The i18n hook validates key parity on every edit.

### Task 9: Docs

**Files:** `config.example.yaml`, `README.md`, `LUEMINUT.md`, `CLAUDE.md`

- `device_watchdog` block documented in all three config docs, with the frost and startup-grace behavior spelled out.
- `CLAUDE.md`: new alert types, the `unit`/`auto` columns, and the disable-not-delete rule under the alerts description.

### Task 10: Verify

- `/lint` — `py_compile`, `check_i18n.py`, `check_version_sync.py`, import check.
- `--demo` smoke test.
- Targeted manual check against a copy of `hutwatch.db`: provisioning creates rules, a lowered threshold triggers, recovery clears, and the reminder fires when `last_triggered` is backdated.
