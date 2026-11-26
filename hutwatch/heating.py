"""Read-only status of an optional heating controller with a JSON HTTP API.

The controller is configured with `heating_url` (e.g. http://127.0.0.1:8077). It must serve
`/api/v1/rooms` and `/api/v1/prices`; `/api/v1/car`, `/api/v1/alerts` and `/api/v1/sensors`
are optional.
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
    """Rooms, prices, car hint, alerts and sensors; None when rooms or prices cannot be read."""
    base = base_url.rstrip("/") + "/api/v1"
    async with aiohttp.ClientSession() as session:
        results = await asyncio.gather(
            _get(session, f"{base}/rooms"),
            _get(session, f"{base}/prices"),
            _get(session, f"{base}/car"),
            _get(session, f"{base}/alerts"),
            _get(session, f"{base}/sensors"),
            return_exceptions=True,
        )
    rooms, prices, car, alerts, sensors = results
    if isinstance(rooms, Exception) or isinstance(prices, Exception):
        logger.warning("Heating status unavailable: %s", type(rooms if isinstance(rooms, Exception) else prices).__name__)
        return None
    return {
        "rooms": rooms,
        "prices": prices,
        "car": None if isinstance(car, Exception) else (car or {}).get("car"),
        "alerts": [] if isinstance(alerts, Exception) else (alerts or {}).get("active", []),
        "sensors": {} if isinstance(sensors, Exception) else (sensors or {}),
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

    sensors = data.get("sensors") or {}
    outdoor = sensors.get("outdoor") or {}
    if outdoor.get("temp_c") is not None:
        lines.append(t("tg_heating_outdoor", temp=outdoor["temp_c"]))

    car = data.get("car")
    if car and car.get("text"):
        lines.append("🚗 " + _md(car["text"]))

    for alert in data.get("alerts", []):
        lines.append("⚠️ " + _md(alert.get("text", "")))

    rooms = sorted(data.get("rooms", []), key=lambda r: r["settings"]["name"])
    by_room, others = _sensors_by_room(sensors.get("sensors") or [], rooms)

    lines.append("")
    for room in rooms:
        rt = (room.get("state") or {}).get("realtime") or {}
        room_name = room["settings"]["name"]
        name = _md(room_name)
        if rt.get("room_temp") is None and rt.get("floor_temp") is None:
            line = t("tg_heating_room_no_data", name=name)
        else:
            line = t(
                "tg_heating_room",
                icon="🔥" if rt.get("relay_on") else "▫️",
                name=name,
                room=rt.get("room_temp") if rt.get("room_temp") is not None else float("nan"),
                floor=rt.get("floor_temp") if rt.get("floor_temp") is not None else float("nan"),
            )
        for s in by_room.get(room["settings"]["mac"], []):
            label = t("tg_heating_sensor_own") if s.get("name") == room_name else _md(s.get("name") or "")
            line += t("tg_heating_sensor", name=label, temp=s["latest"]["temp_c"]) + _stale(s)
        lines.append(line)

    if others:
        lines.append("")
        lines.append(t("tg_heating_others"))
        for s in sorted(others, key=lambda s: s.get("name") or ""):
            lines.append(t("tg_heating_other", name=_md(s.get("name") or s.get("id", "")),
                           temp=s["latest"]["temp_c"]) + _stale(s))
    return "\n".join(lines)


def _stale(sensor: dict) -> str:
    return t("tg_heating_stale") if sensor.get("stale") else ""


def _sensors_by_room(sensors: list, rooms: list) -> tuple[dict, list]:
    """Indoor sensors with a reading, grouped under their room: the room the controller links
    them to, else the room with the same name. The rest are returned as others."""
    mac_by_name = {r["settings"]["name"]: r["settings"]["mac"] for r in rooms}
    by_room: dict = {}
    others = []
    for s in sensors:
        if s.get("role") == "outdoor" or (s.get("latest") or {}).get("temp_c") is None:
            continue
        mac = s.get("room") or mac_by_name.get(s.get("name"))
        if mac:
            by_room.setdefault(mac, []).append(s)
        else:
            others.append(s)
    return by_room, others
