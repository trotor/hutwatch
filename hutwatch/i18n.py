"""Internationalization support for HutWatch UI."""

from __future__ import annotations

from typing import Any

_current_strings: dict[str, Any] = {}
_current_lang: str = "fi"


def init_lang(lang: str = "fi") -> None:
    """Initialize language. Call once at startup before any UI code."""
    global _current_strings, _current_lang
    _current_lang = lang
    if lang == "en":
        from . import strings_en

        _current_strings = strings_en.STRINGS
    else:
        from . import strings_fi

        _current_strings = strings_fi.STRINGS


def get_lang() -> str:
    """Return current language code."""
    return _current_lang


def t(key: str, **kwargs: Any) -> Any:
    """Look up a translated string by key, with optional format arguments.

    String values can be:
    - Plain string: returned as-is (or formatted if kwargs given)
    - Format template: "{name} has {count}" -- filled via str.format(**kwargs)
    - Callable: called with **kwargs, for pluralization or complex logic
    - List/other: returned as-is (e.g. wind direction lists)
    """
    val = _current_strings[key]
    if callable(val):
        return val(**kwargs)
    if isinstance(val, str) and kwargs:
        return val.format(**kwargs)
    return val


def wind_direction_text(degrees: float | None) -> str:
    """Convert wind direction degrees to localized text."""
    if degrees is None:
        return ""
    directions = t("weather_wind_directions")
    return directions[int((degrees + 22.5) / 45) % 8]
