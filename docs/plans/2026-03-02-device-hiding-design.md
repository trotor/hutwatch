# Device Hiding Design

## Summary

Add ability to hide/ignore discovered BLE devices. Hidden devices are not shown in any UI by default, but a "show hidden" toggle reveals them. Data collection and peer sync continue normally for hidden devices — hiding is purely a local UI filter.

## Database

- Add `hidden INTEGER DEFAULT 0` column to `devices` table
- Migration: `ALTER TABLE devices ADD COLUMN hidden INTEGER DEFAULT 0`
- `get_all_devices(include_hidden=False)` — UI calls filter by default
- `set_device_hidden(mac, hidden: bool)` — new method
- `DeviceInfo` model gets `hidden: bool = False` field

## Data Collection

- SensorStore and Aggregator operate normally for all devices (hidden or not)
- Hidden is purely a display-layer filter
- API/peer sync sends hidden devices normally — peers see them like any other remote device

## UI: TUI Dashboard

- `hide N` / `unhide N` commands — toggle hidden flag by order number, alias, or MAC
- `f` key — toggle "show hidden" mode on dashboard
- When show-hidden is on, hidden devices appear with `[H]` marker
- Device list (`d`) respects show-hidden toggle
- All views (temps, history, stats, graph) filter hidden devices unless toggle is on

## UI: Telegram Bot

- `/hide N` and `/unhide N` commands — toggle hidden flag
- `/showhidden` — toggle session-level flag to include hidden devices
- `/temps`, `/status`, `/devices` respect the toggle
- Finnish aliases: `/piilota`, `/nayta`

## UI: Console

- `--show-hidden` CLI flag — include hidden devices in output
- Without flag, hidden devices are filtered out

## i18n Keys

New keys needed in both `strings_fi.py` and `strings_en.py`:
- `common_hidden_marker` — `[H]` marker text
- `tui_hide_success`, `tui_unhide_success` — confirmation messages
- `tui_hide_help` — help text for hide/unhide commands
- `tui_show_hidden_on`, `tui_show_hidden_off` — toggle feedback
- `tg_hide_success`, `tg_unhide_success` — Telegram confirmations
- `tg_showhidden_on`, `tg_showhidden_off` — toggle feedback
- `tg_hide_help` — help text

## Edge Cases

- Hide a device not in DB → error message
- All devices hidden → empty dashboard with "no visible devices" message
- Hidden applies only to local devices; remote/peer devices are always shown
- `resolve_device()` can still find hidden devices (for hide/unhide commands)
