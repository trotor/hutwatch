Add a new i18n translation key to both `hutwatch/strings_fi.py` and `hutwatch/strings_en.py`.

Read both string files to understand the current structure and categories.

The key naming convention is `category_description` in snake_case. Categories include:
- `common_` — shared UI strings
- `time_` — time formatting
- `weather_` — weather terms
- `tg_` — Telegram messages (may include Markdown)
- `tui_` — TUI dashboard
- `console_` — console output
- `scheduler_` — scheduled reports
- `remote_` — remote site monitoring

If an argument is provided, parse it as the key name. Otherwise ask the user for:
1. The key name (following the naming convention)
2. The Finnish value
3. The English value

String values can be:
- Plain string: `"text here"`
- Format template: `"text {variable} here"` (uses str.format)
- Callable for pluralization: `lambda n, **_: f"{n} päivä" if n == 1 else f"{n} päivää"`
- List: `["item1", "item2"]`

Add the key to both files in the correct category section (find the matching `# ── Category` comment block). Place it at the end of the relevant category section.

After adding, the i18n sync hook will automatically validate that both files have matching keys.
