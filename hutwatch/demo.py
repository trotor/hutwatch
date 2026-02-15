"""Demo mode: launches TUI with realistic fake data for screenshots."""

from __future__ import annotations

import asyncio
import math
import random
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from .ble.sensor_store import SensorStore
from .db import Database
from .models import AppConfig, SensorConfig, SensorReading, SensorType, WeatherData
from .remote import RemoteSensor, RemoteSiteData, RemoteWeather

# Reproducible output
random.seed(42)

# ── Demo sensor definitions ──────────────────────────────────────────

DEMO_SENSORS = [
    {"mac": "AA:BB:CC:DD:EE:01", "name": "Olohuone", "type": "ruuvi",
     "temp": 21.3, "hum": 42.0, "bat_pct": 87, "bat_v": 2.95, "rssi": -62},
    {"mac": "AA:BB:CC:DD:EE:02", "name": "Makuuhuone", "type": "ruuvi",
     "temp": 19.8, "hum": 45.0, "bat_pct": 72, "bat_v": 2.78, "rssi": -71},
    {"mac": "AA:BB:CC:DD:EE:03", "name": "Sauna", "type": "xiaomi",
     "temp": 24.1, "hum": 38.0, "bat_pct": 64, "bat_v": None, "rssi": -58},
    {"mac": "AA:BB:CC:DD:EE:04", "name": "Ulkokatos", "type": "ruuvi",
     "temp": -3.2, "hum": 89.0, "bat_pct": 91, "bat_v": 3.05, "rssi": -80},
]

DEMO_WEATHER = {
    "location": "Tampere",
    "lat": 61.4991, "lon": 23.7871,
    "temp": -4.2, "hum": 85.0, "pressure": 1018.0,
    "wind_speed": 3.4, "wind_dir": 225.0,  # SW
    "cloud_cover": 88.0, "precipitation": 0.0,
    "symbol": "cloudy",
}

DEMO_REMOTE_SENSORS = [
    RemoteSensor(name="Olohuone", mac="FF:EE:DD:CC:BB:01", type="xiaomi",
                 order=1, temperature=22.4, humidity=39.0, age_seconds=15),
    RemoteSensor(name="Makuuhuone", mac="FF:EE:DD:CC:BB:02", type="xiaomi",
                 order=2, temperature=20.1, humidity=43.0, age_seconds=15),
    RemoteSensor(name="Parveke", mac="FF:EE:DD:CC:BB:03", type="ruuvi",
                 order=3, temperature=-1.8, humidity=82.0, age_seconds=30),
]

DEMO_REMOTE_WEATHER = RemoteWeather(
    temperature=-2.8, humidity=78.0, pressure=1015.0,
    wind_speed=4.1, wind_direction=200.0,
    cloud_cover=65.0, symbol_code="partlycloudy",
    location="Helsinki",
)


# ── Duck-type stand-ins ──────────────────────────────────────────────

class DemoWeather:
    """Stand-in for WeatherFetcher — provides .latest, .last_fetch, .location_name."""

    def __init__(self, data: WeatherData, location: str) -> None:
        self._data = data
        self._location = location
        self._last_fetch = datetime.now() - timedelta(minutes=12)

    @property
    def latest(self) -> Optional[WeatherData]:
        return self._data

    @property
    def last_fetch(self) -> Optional[datetime]:
        return self._last_fetch

    @property
    def location_name(self) -> str:
        return self._location


class DemoRemote:
    """Stand-in for RemotePoller — provides .get_all_site_data()."""

    def __init__(self, sites: dict[str, RemoteSiteData]) -> None:
        self._sites = sites

    def get_all_site_data(self) -> dict[str, RemoteSiteData]:
        return dict(self._sites)


# ── Data population ──────────────────────────────────────────────────

def _sinusoidal(base: float, amplitude: float, phase: float, t: float) -> float:
    """Generate sinusoidal value with small random noise."""
    return base + amplitude * math.sin(2 * math.pi * t / 24.0 + phase) + random.gauss(0, 0.15)


def _populate_db(db: Database) -> None:
    """Insert 24h of 5-min aggregated readings + weather history."""
    now = datetime.now()
    points = 288  # 24h * 12 per hour

    # Sensor base temps and daily amplitudes
    profiles = [
        {"mac": "AA:BB:CC:DD:EE:01", "base": 21.0, "amp": 0.8, "phase": 0.0, "hum": 42},
        {"mac": "AA:BB:CC:DD:EE:02", "base": 19.5, "amp": 0.6, "phase": 0.5, "hum": 45},
        {"mac": "AA:BB:CC:DD:EE:03", "base": 23.0, "amp": 2.0, "phase": 1.0, "hum": 38},
        {"mac": "AA:BB:CC:DD:EE:04", "base": -3.0, "amp": 2.5, "phase": -0.5, "hum": 89},
    ]

    for p in profiles:
        for i in range(points):
            ts = now - timedelta(minutes=5 * (points - 1 - i))
            hours_ago = (points - 1 - i) * 5 / 60.0
            temp = _sinusoidal(p["base"], p["amp"], p["phase"], hours_ago)
            noise = random.gauss(0, 0.1)
            db.save_aggregated_reading(
                mac=p["mac"],
                timestamp=ts,
                temp_avg=round(temp, 2),
                temp_min=round(temp - abs(noise) - 0.2, 2),
                temp_max=round(temp + abs(noise) + 0.2, 2),
                humidity_avg=round(p["hum"] + random.gauss(0, 1.5), 1),
                sample_count=random.randint(4, 6),
            )

    # Weather history (hourly for 24h)
    for i in range(24):
        ts = now - timedelta(hours=23 - i)
        hours_ago = 23 - i
        temp = _sinusoidal(-4.0, 1.5, -1.0, hours_ago)
        db.save_weather(
            timestamp=ts,
            temperature=round(temp, 1),
            humidity=round(85 + random.gauss(0, 3), 0),
            pressure=round(1018 + random.gauss(0, 0.5), 1),
            wind_speed=round(3.0 + random.gauss(0, 0.8), 1),
            wind_direction=225 + random.gauss(0, 15),
            precipitation=round(max(0, random.gauss(-0.3, 0.2)), 1),
            cloud_cover=round(min(100, max(0, 85 + random.gauss(0, 8))), 0),
            symbol_code="cloudy",
        )

    # Register devices with aliases and ordering
    for i, s in enumerate(DEMO_SENSORS, 1):
        db._conn.execute(
            "INSERT INTO devices (mac, alias, display_order, sensor_type) VALUES (?, ?, ?, ?)",
            (s["mac"], s["name"], i, s["type"]),
        )
    db._conn.commit()

    # Set site name
    db.set_setting("site_name", "Mökki")


def _populate_store(store: SensorStore) -> None:
    """Add recent SensorReading objects for live display."""
    now = datetime.now()
    for s in DEMO_SENSORS:
        reading = SensorReading(
            mac=s["mac"],
            timestamp=now - timedelta(seconds=random.randint(5, 45)),
            temperature=s["temp"],
            humidity=s["hum"],
            battery_percent=s["bat_pct"],
            battery_voltage=s["bat_v"],
            rssi=s["rssi"],
        )
        store.add_reading(reading)


# ── Entry point ──────────────────────────────────────────────────────

async def run_demo() -> None:
    """Launch TUI with demo data. No config file, BLE, or network needed."""
    from .tui import TuiDashboard

    # In-memory database
    db = Database(Path(":memory:"))
    db.connect()
    _populate_db(db)

    # Sensor store with live readings
    store = SensorStore()
    _populate_store(store)

    # Weather stand-in
    w = DEMO_WEATHER
    weather = DemoWeather(
        data=WeatherData(
            timestamp=datetime.now() - timedelta(minutes=12),
            temperature=w["temp"],
            humidity=w["hum"],
            pressure=w["pressure"],
            wind_speed=w["wind_speed"],
            wind_direction=w["wind_dir"],
            precipitation=w["precipitation"],
            cloud_cover=w["cloud_cover"],
            symbol_code=w["symbol"],
        ),
        location=w["location"],
    )

    # Remote site stand-in
    remote = DemoRemote({
        "koti": RemoteSiteData(
            site_name="Koti",
            sensors=DEMO_REMOTE_SENSORS,
            weather=DEMO_REMOTE_WEATHER,
            last_fetch=datetime.now() - timedelta(seconds=18),
            online=True,
        ),
    })

    # Minimal config (no real sensors — all data comes from store/db)
    config = AppConfig(
        sensors=[
            SensorConfig(mac=s["mac"], name=s["name"], type=SensorType(s["type"]))
            for s in DEMO_SENSORS
        ],
    )

    # Launch TUI — app=None disables weather/rename setup commands
    tui = TuiDashboard(
        config=config,
        store=store,
        db=db,
        weather=weather,
        app=None,
        remote=remote,
    )

    await tui.start()

    # Wait until TUI exits
    try:
        while tui._running:
            await asyncio.sleep(0.5)
    except asyncio.CancelledError:
        pass
    finally:
        await tui.stop()
        db.close()
