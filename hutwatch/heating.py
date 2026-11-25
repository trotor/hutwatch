"""Read-only status of an optional heating controller with a JSON HTTP API.

The controller is configured with `heating_url` (e.g. http://127.0.0.1:8077). It must serve
`/api/v1/rooms` and `/api/v1/prices`; `/api/v1/car` and `/api/v1/alerts` are optional.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

import aiohttp

from .i18n import t

logger = logging.getLogger(__name__)

SLOT = timedelta(minutes=15)
TIMEOUT_S = 5


async def _get(session: aiohttp.ClientSession, url: str):
    async with session.get(url, timeout=aiohttp.ClientTimeout(total=TIMEOUT_S)) as resp:
        resp.raise_for_status()
        return await resp.json()


async def fetch_heating(base_url: str) -> Optional[dict]:
    """Rooms, prices, car hint and alerts; None when rooms or prices cannot be read."""
    base = base_url.rstrip("/") + "/api/v1"
    async with aiohttp.ClientSession() as session:
        results = await asyncio.gather(
            _get(session, f"{base}/rooms"),
            _get(session, f"{base}/prices"),
            _get(session, f"{base}/car"),
            _get(session, f"{base}/alerts"),
            return_exceptions=True,
        )
    rooms, prices, car, alerts = results
    if isinstance(rooms, Exception) or isinstance(prices, Exception):
        logger.warning("Heating status unavailable: %s", type(rooms if isinstance(rooms, Exception) else prices).__name__)
        return None
    return {
        "rooms": rooms,
        "prices": prices,
        "car": None if isinstance(car, Exception) else (car or {}).get("car"),
        "alerts": [] if isinstance(alerts, Exception) else (alerts or {}).get("active", []),
    }


def _md(text: str) -> str:
    """Escape Telegram legacy-Markdown control characters in free text."""
    for ch in ("\\", "_", "*", "`", "["):
        text = text.replace(ch, "\\" + ch)
    return text


def _local(iso: str) -> datetime:
    return datetime.fromisoformat(iso).astimezone()


def format_heating(data: dict, now: datetime) -> str:
    """Telegram message (Markdown) for one heating status; `now` is timezone-aware."""
    lines = [t("tg_heating_header", time=now.astimezone().strftime("%H:%M"))]

    real = [p for p in data.get("prices", []) if not p.get("forecast")]
    current = next(
        (p for p in real if _local(p["start"]) <= now < _local(p["start"]) + SLOT), None
    )
    ahead = [p for p in real if _local(p["start"]) + SLOT > now]
    if current and ahead:
        low = min(ahead, key=lambda p: p["price_c"])
        lines.append(t(
            "tg_heating_price", now=current["price_c"],
            at=_local(low["start"]).strftime("%H:%M"), low=low["price_c"],
        ))

    car = data.get("car")
    if car and car.get("text"):
        lines.append("🚗 " + _md(car["text"]))

    for alert in data.get("alerts", []):
        lines.append("⚠️ " + _md(alert.get("text", "")))

    lines.append("")
    for room in sorted(data.get("rooms", []), key=lambda r: r["settings"]["name"]):
        rt = (room.get("state") or {}).get("realtime") or {}
        name = _md(room["settings"]["name"])
        if rt.get("room_temp") is None and rt.get("floor_temp") is None:
            lines.append(t("tg_heating_room_no_data", name=name))
            continue
        lines.append(t(
            "tg_heating_room",
            icon="🔥" if rt.get("relay_on") else "▫️",
            name=name,
            room=rt.get("room_temp") if rt.get("room_temp") is not None else float("nan"),
            floor=rt.get("floor_temp") if rt.get("floor_temp") is not None else float("nan"),
        ))
    return "\n".join(lines)
