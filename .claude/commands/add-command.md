Add a new user command to the HutWatch TUI dashboard and/or Telegram bot.

This skill guides through all the steps needed to add a new interactive command consistently.

If arguments are provided, use the first as the command name. Otherwise ask the user for:
1. Command name/letter (e.g., `x` for TUI, `/export` for Telegram)
2. Brief description of what the command does
3. Which UIs it should be added to: TUI only, Telegram only, or both

Then execute these steps:

### 1. Add i18n strings

For each UI target, add the necessary translation keys to both `hutwatch/strings_fi.py` and `hutwatch/strings_en.py`:
- Help text key (e.g., `tui_cmd_help` or `tg_cmd_help`)
- Any output format strings the command will need
- Error messages if applicable

Follow the existing key naming convention (`tui_` prefix for TUI, `tg_` prefix for Telegram).

### 2. Implement the command handler

**For TUI** (`hutwatch/tui.py`):
- Add the command letter to `_INSTANT_KEYS` or `_INPUT_KEYS` frozenset as appropriate
- Add the handler case in `_handle_command()` method
- If the command needs async operations, use the "pending action" pattern (set a `_pending_*` flag, check it in the main loop)
- Add any rendering methods needed (follow existing `_render_*` patterns)

**For Telegram** (`hutwatch/telegram/commands.py`):
- Add an async handler method in `CommandHandlers`
- Register it in `hutwatch/telegram/bot.py` `_setup_handlers()` with `CommandHandler`
- If it needs Finnish alias, add that too

### 3. Use shared utilities

If the command needs any of these, import from `hutwatch/formatting.py`:
- `format_age()` / `format_age_long()` — age formatting
- `parse_time_arg()` — time argument parsing ("6h", "7d")
- `resolve_device()` — device lookup by number/alias/name/MAC
- `create_ascii_graph()` — ASCII graph generation
- `compute_cutoff()` — datetime cutoff calculation

### 4. Update documentation

- Add the command to the appropriate section in `CLAUDE.md` (TUI Dashboard Commands / Telegram Commands)
- Add the command to the TUI help text in the `TuiDashboard` class docstring

### 5. Verify

Run `/lint` to ensure all checks pass.

Show the user a summary of all files modified and the new command's usage.
