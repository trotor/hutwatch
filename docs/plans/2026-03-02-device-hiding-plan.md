# Device Hiding Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add ability to hide BLE devices from all UIs, with show-hidden toggles in each UI mode.

**Architecture:** Add `hidden` column to `devices` table, `hidden` field to `DeviceInfo` model, filter in `get_all_devices()`. Each UI gets hide/unhide commands and a show-hidden toggle. Data collection and peer sync are unaffected.

**Tech Stack:** Python 3.10+, SQLite, async/await, python-telegram-bot

---

### Task 1: Add `hidden` field to DeviceInfo model

**Files:**
- Modify: `hutwatch/models.py:126-154`

**Step 1: Add hidden field to DeviceInfo**

In `hutwatch/models.py`, add `hidden: bool = False` after `sensor_type`:

```python
@dataclass
class DeviceInfo:
    """Device information from database."""

    mac: str
    alias: Optional[str]
    display_order: int
    sensor_type: str
    hidden: bool = False
    config_name: Optional[str] = None
```

Note: `hidden` must come before `config_name` because both have defaults, but field ordering must keep non-defaults before defaults. Since `hidden` has a default and `config_name` has a default, order between them doesn't matter for dataclass rules — but put `hidden` first since it's a DB field and `config_name` is runtime-only.

**Step 2: Verify compile**

Run: `python -m py_compile hutwatch/models.py`
Expected: no output (success)

**Step 3: Commit**

```bash
git add hutwatch/models.py
git commit -m "Add hidden field to DeviceInfo model"
```

---

### Task 2: Add `hidden` column to DB and update all device queries

**Files:**
- Modify: `hutwatch/db.py`

**Step 1: Add migration in `_create_tables()`**

After the existing `CREATE TABLE IF NOT EXISTS devices` block (line ~78), add migration:

```python
# Migration: add hidden column
try:
    self._conn.execute("ALTER TABLE devices ADD COLUMN hidden INTEGER DEFAULT 0")
    self._conn.commit()
except Exception:
    pass  # Column already exists
```

**Step 2: Update `get_all_devices()` to accept `include_hidden` parameter**

Change method at line 291:

```python
def get_all_devices(self, include_hidden: bool = False) -> list[DeviceInfo]:
    """Get all devices ordered by display_order."""
    if not self._conn:
        return []

    if include_hidden:
        query = "SELECT mac, alias, display_order, sensor_type, hidden FROM devices ORDER BY display_order"
        params: tuple = ()
    else:
        query = "SELECT mac, alias, display_order, sensor_type, hidden FROM devices WHERE hidden = 0 ORDER BY display_order"
        params = ()

    cursor = self._conn.execute(query, params)
    return [
        DeviceInfo(
            mac=row["mac"],
            alias=row["alias"],
            display_order=row["display_order"],
            sensor_type=row["sensor_type"],
            hidden=bool(row["hidden"]),
        )
        for row in cursor.fetchall()
    ]
```

**Step 3: Update `get_device()` at line 272 to include hidden field**

```python
def get_device(self, mac: str) -> Optional[DeviceInfo]:
    """Get device info by MAC address."""
    if not self._conn:
        return None

    cursor = self._conn.execute(
        "SELECT mac, alias, display_order, sensor_type, hidden FROM devices WHERE mac = ?",
        (mac.upper(),),
    )
    row = cursor.fetchone()
    if row:
        return DeviceInfo(
            mac=row["mac"],
            alias=row["alias"],
            display_order=row["display_order"],
            sensor_type=row["sensor_type"],
            hidden=bool(row["hidden"]),
        )
    return None
```

**Step 4: Update `get_device_by_order()` at line 380**

```python
def get_device_by_order(self, order: int) -> Optional[DeviceInfo]:
    """Get device by display order number."""
    if not self._conn:
        return None

    cursor = self._conn.execute(
        "SELECT mac, alias, display_order, sensor_type, hidden FROM devices WHERE display_order = ?",
        (order,),
    )
    row = cursor.fetchone()
    if row:
        return DeviceInfo(
            mac=row["mac"],
            alias=row["alias"],
            display_order=row["display_order"],
            sensor_type=row["sensor_type"],
            hidden=bool(row["hidden"]),
        )
    return None
```

**Step 5: Add `set_device_hidden()` method**

Add after `set_device_order()` (after line ~345):

```python
def set_device_hidden(self, mac: str, hidden: bool) -> bool:
    """Set device hidden state."""
    if not self._conn:
        return False

    try:
        cursor = self._conn.execute(
            """
            UPDATE devices SET hidden = ?, updated_at = CURRENT_TIMESTAMP
            WHERE mac = ?
            """,
            (1 if hidden else 0, mac.upper()),
        )
        self._conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        logger.error("Error setting device hidden: %s", e)
        return False
```

**Step 6: Verify compile**

Run: `python -m py_compile hutwatch/db.py`

**Step 7: Commit**

```bash
git add hutwatch/db.py
git commit -m "Add hidden column to devices table and update queries"
```

---

### Task 3: Add i18n strings for device hiding

**Files:**
- Modify: `hutwatch/strings_fi.py`
- Modify: `hutwatch/strings_en.py`

**Step 1: Add Finnish strings**

In `hutwatch/strings_fi.py`, add after `tui_devices_rename_hint` (line 248):

```python
    "tui_devices_hide_hint": "Piilota: hide <nro>   Näytä: unhide <nro>",

```

Add in the TUI footer commands section (after line 221, before `tui_cmd_quit`):

```python
    "tui_cmd_show_hidden": "[f] piilotetut",
```

Add in the TUI command feedback section (after `tui_unknown_command`, line 286):

```python
    "tui_hide_success": "Laite {name} piilotettu",
    "tui_unhide_success": "Laite {name} näytetään",
    "tui_hide_not_found": "Laitetta ei löytynyt: {id}",
    "tui_show_hidden_on": "Piilotetut laitteet näytetään",
    "tui_show_hidden_off": "Piilotetut laitteet piilotettu",
    "tui_hidden_marker": "[H]",
```

Add Telegram strings in the Telegram command feedback section (find `tg_rename_success` or similar, add nearby):

```python
    "tg_hide_success": "✅ Laite *{name}* piilotettu",
    "tg_unhide_success": "✅ Laite *{name}* näytetään",
    "tg_hide_not_found": "❌ Laitetta ei löytynyt: {id}",
    "tg_showhidden_on": "👁 Piilotetut laitteet näytetään",
    "tg_showhidden_off": "🙈 Piilotetut laitteet piilotettu",
```

**Step 2: Add English strings**

Same keys in `hutwatch/strings_en.py`:

After `tui_devices_rename_hint` (line 250):

```python
    "tui_devices_hide_hint": "Hide: hide <num>   Show: unhide <num>",
```

Footer commands (after line 223, before `tui_cmd_quit`):

```python
    "tui_cmd_show_hidden": "[f] hidden",
```

TUI command feedback (after `tui_unknown_command`, line 288):

```python
    "tui_hide_success": "Device {name} hidden",
    "tui_unhide_success": "Device {name} visible",
    "tui_hide_not_found": "Device not found: {id}",
    "tui_show_hidden_on": "Showing hidden devices",
    "tui_show_hidden_off": "Hidden devices not shown",
    "tui_hidden_marker": "[H]",
```

Telegram strings:

```python
    "tg_hide_success": "✅ Device *{name}* hidden",
    "tg_unhide_success": "✅ Device *{name}* visible",
    "tg_hide_not_found": "❌ Device not found: {id}",
    "tg_showhidden_on": "👁 Showing hidden devices",
    "tg_showhidden_off": "🙈 Hidden devices not shown",
```

**Step 3: Verify i18n sync**

Run: `python tools/check_i18n.py`
Expected: no missing keys

**Step 4: Commit**

```bash
git add hutwatch/strings_fi.py hutwatch/strings_en.py
git commit -m "Add i18n strings for device hiding feature"
```

---

### Task 4: Add hide/unhide/show-hidden to TUI

**Files:**
- Modify: `hutwatch/tui.py`

**Step 1: Add `_show_hidden` instance variable**

In `__init__` (line ~126, after `_show_summary`):

```python
self._show_hidden: bool = False  # toggle with 'f' command
```

**Step 2: Add `f` toggle command in `_handle_command()`**

In `_handle_command()` (line ~319), add after the `y` toggle block (line ~343):

```python
    if cmd == "f":
        self._show_hidden = not self._show_hidden
        self._status_msg = t("tui_show_hidden_on") if self._show_hidden else t("tui_show_hidden_off")
        return
```

**Step 3: Add `hide` and `unhide` commands in `_handle_command()`**

Add before the `self._status_msg = t("tui_unknown_command"...)` line at end of method:

```python
    if cmd in ("hide", "unhide"):
        if len(parts) < 2:
            self._status_msg = t("tui_hide_not_found", id="?")
            return
        identifier = " ".join(parts[1:])
        device = resolve_device(identifier, self._db, self._config)
        if not device:
            self._status_msg = t("tui_hide_not_found", id=identifier)
            return
        hide = cmd == "hide"
        self._db.set_device_hidden(device.mac, hide)
        name = device.get_display_name()
        self._status_msg = t("tui_hide_success", name=name) if hide else t("tui_unhide_success", name=name)
        return
```

**Step 4: Update `_get_ordered_devices()` to respect `_show_hidden`**

At line 556, change `self._db.get_all_devices()` to:

```python
devices = self._db.get_all_devices(include_hidden=self._show_hidden)
```

**Step 5: Update `_render_devices()` to show hidden marker and respect toggle**

At line 1466, change `self._db.get_all_devices()` to:

```python
devices = self._db.get_all_devices(include_hidden=self._show_hidden)
```

In the device row rendering, add hidden marker. Change the line that builds each row to prepend `[H]` if hidden:

```python
        for d in sorted(devices, key=lambda x: x.display_order):
            sensor_config = self._config.get_sensor_by_mac(d.mac)
            config_name = sensor_config.name if sensor_config else "-"
            alias = d.alias or "-"
            order = str(d.display_order)
            sensor_type = d.sensor_type or "-"
            hidden_mark = f" {t('tui_hidden_marker')}" if d.hidden else ""

            lines.append(
                f"  {order:<4}{config_name:<16}{alias:<16}{d.mac:<20}{sensor_type:<8}{hidden_mark}"
            )
```

Also update the hint line at bottom of devices view to include hide hint:

```python
    lines.append(f"  {DIM}{t('tui_devices_rename_hint')}{RESET}")
    lines.append(f"  {DIM}{t('tui_devices_hide_hint')}{RESET}")
```

**Step 6: Add `[f]` to footer help**

In `_render_footer()` (line ~663), add in the dashboard commands list after the summary toggle line:

```python
cmds.append(t("tui_cmd_show_hidden"))
```

**Step 7: Update TUI class docstring**

Add `hide`/`unhide`/`f` to the docstring command list at top of class (line ~59).

**Step 8: Verify compile**

Run: `python -m py_compile hutwatch/tui.py`

**Step 9: Commit**

```bash
git add hutwatch/tui.py
git commit -m "Add hide/unhide/show-hidden commands to TUI"
```

---

### Task 5: Add hide/unhide/showhidden to Telegram bot

**Files:**
- Modify: `hutwatch/telegram/commands.py`
- Modify: `hutwatch/telegram/bot.py`

**Step 1: Add `_show_hidden` state to CommandHandlers**

In `CommandHandlers.__init__()` in `commands.py`, add:

```python
self._show_hidden: bool = False
```

**Step 2: Add `hide` command handler**

Add new method in `commands.py`:

```python
async def hide(
    self,
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Handle /hide command - hide a device."""
    if not update.effective_message or not self._db:
        return

    args = context.args
    if not args:
        await update.effective_message.reply_text(
            "❌ " + t("tg_hide_not_found", id="?"),
            parse_mode="Markdown",
        )
        return

    identifier = " ".join(args)
    device = resolve_device(identifier, self._db, self._config)
    if not device:
        await update.effective_message.reply_text(
            t("tg_hide_not_found", id=identifier),
            parse_mode="Markdown",
        )
        return

    self._db.set_device_hidden(device.mac, True)
    name = device.get_display_name()
    await update.effective_message.reply_text(
        t("tg_hide_success", name=name),
        parse_mode="Markdown",
    )
```

**Step 3: Add `unhide` command handler**

Same pattern as hide but with `False` and `tg_unhide_success`.

**Step 4: Add `showhidden` command handler**

```python
async def showhidden(
    self,
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Handle /showhidden command - toggle showing hidden devices."""
    if not update.effective_message:
        return

    self._show_hidden = not self._show_hidden
    msg = t("tg_showhidden_on") if self._show_hidden else t("tg_showhidden_off")
    await update.effective_message.reply_text(msg, parse_mode="Markdown")
```

**Step 5: Update `_get_devices_with_config_names()` to respect show_hidden**

Change at line 56:

```python
def _get_devices_with_config_names(self) -> list[DeviceInfo]:
    """Get all devices with config names populated."""
    if not self._db:
        return []

    devices = self._db.get_all_devices(include_hidden=self._show_hidden)
    for device in devices:
        sensor_config = self._config.get_sensor_by_mac(device.mac)
        if sensor_config:
            device.config_name = sensor_config.name
    return devices
```

**Step 6: Register handlers in bot.py**

In `hutwatch/telegram/bot.py`, add after the existing handler registrations (after line 76):

```python
self._app.add_handler(CommandHandler("hide", self._commands.hide))
self._app.add_handler(CommandHandler("piilota", self._commands.hide))
self._app.add_handler(CommandHandler("unhide", self._commands.unhide))
self._app.add_handler(CommandHandler("nayta", self._commands.unhide))
self._app.add_handler(CommandHandler("showhidden", self._commands.showhidden))
```

**Step 7: Update Telegram help text in i18n**

Update `tg_help_full` in both string files to add hide/unhide under "Laitteiden hallinta" / "Device management":

Finnish: `/hide <nro> - Piilota laite\n/unhide <nro> - Näytä laite\n/showhidden - Näytä/piilota piilotetut\n`

English: `/hide <num> - Hide device\n/unhide <num> - Show device\n/showhidden - Toggle hidden devices\n`

**Step 8: Add `resolve_device` import to commands.py if not already imported**

Check if `from ..formatting import resolve_device` is already present. If not, add it.

**Step 9: Verify compile**

Run: `python -m py_compile hutwatch/telegram/commands.py && python -m py_compile hutwatch/telegram/bot.py`

**Step 10: Commit**

```bash
git add hutwatch/telegram/commands.py hutwatch/telegram/bot.py hutwatch/strings_fi.py hutwatch/strings_en.py
git commit -m "Add hide/unhide/showhidden commands to Telegram bot"
```

---

### Task 6: Add `--show-hidden` to console mode

**Files:**
- Modify: `hutwatch/console.py`
- Modify: `hutwatch/__main__.py`
- Modify: `hutwatch/app.py`

**Step 1: Add `show_hidden` parameter to ConsoleReporter**

In `console.py` `__init__` (line ~30), add `show_hidden: bool = False` parameter and store as `self._show_hidden`.

**Step 2: Update `_print_readings()` to filter hidden devices**

At line ~127 where `devices = self._db.get_all_devices()`, change to:

```python
devices = self._db.get_all_devices(include_hidden=self._show_hidden)
```

Also, when building rows from `readings`, skip hidden devices. After getting `device_map`, filter the readings loop:

```python
    # Build set of hidden MACs for filtering
    if not self._show_hidden:
        all_devices = self._db.get_all_devices(include_hidden=True)
        hidden_macs = {d.mac for d in all_devices if d.hidden}
    else:
        hidden_macs = set()

    rows: list[tuple[str, str, str, str, str]] = []
    for mac, reading in sorted(readings.items()):
        if mac in hidden_macs:
            continue
        ...
```

This is needed because `readings` comes from SensorStore (all sensors), while `device_map` is from DB. A sensor in readings but not in DB shouldn't be hidden (it's newly discovered).

**Step 3: Add `--show-hidden` CLI flag**

In `hutwatch/__main__.py`, in `parse_args()` (after `--demo` around line 100):

```python
parser.add_argument(
    "--show-hidden",
    action="store_true",
    help="Show hidden devices in console output",
)
```

**Step 4: Pass flag to ConsoleReporter**

In `hutwatch/app.py`, where ConsoleReporter is instantiated (find the line), add `show_hidden=self._show_hidden` parameter. Also store the flag from args in `HutWatchApp.__init__`.

Check how args flow: `__main__.py` calls `HutWatchApp` — find where args are passed and add `show_hidden`.

**Step 5: Verify compile**

Run: `python -m py_compile hutwatch/console.py && python -m py_compile hutwatch/__main__.py && python -m py_compile hutwatch/app.py`

**Step 6: Commit**

```bash
git add hutwatch/console.py hutwatch/__main__.py hutwatch/app.py
git commit -m "Add --show-hidden flag to console mode"
```

---

### Task 7: Run full lint and manual test

**Step 1: Run lint**

Run: `/lint` skill (py_compile all files, check_i18n, check_version_sync, import checks)

Fix any issues found.

**Step 2: Manual test with demo mode**

Run: `./venv/bin/python -m hutwatch --demo`

Verify:
- Dashboard shows devices
- `d` command shows device list
- `hide 1` hides device 1, status message confirms
- Dashboard no longer shows device 1
- `f` toggles show-hidden, device 1 reappears with `[H]`
- `unhide 1` restores device 1
- `f` toggles back, device 1 visible normally

**Step 3: Commit any fixes**

```bash
git add -u
git commit -m "Fix lint issues from device hiding feature"
```
