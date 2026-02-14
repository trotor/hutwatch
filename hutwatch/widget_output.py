"""JSON output for external widgets (Übersicht, SwiftBar, etc.).

Reads latest sensor readings and weather from SQLite and outputs JSON to stdout.
No async loop needed — direct synchronous DB reads.

Usage:
    python3 -m hutwatch.widget_output -d /path/to/hutwatch.db
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional


def _get_connection(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def _get_setting(conn: sqlite3.Connection, key: str) -> Optional[str]:
    row = conn.execute(
        "SELECT value FROM settings WHERE key = ?", (key,)
    ).fetchone()
    return row["value"] if row else None


def _get_devices(conn: sqlite3.Connection) -> list[dict]:
    cursor = conn.execute(
        "SELECT mac, alias, display_order, sensor_type FROM devices ORDER BY display_order"
    )
    return [dict(row) for row in cursor.fetchall()]


def _get_latest_readings(conn: sqlite3.Connection) -> dict[str, dict]:
    """Get the most recent aggregated reading per device."""
    cursor = conn.execute("""
        SELECT r.mac, r.timestamp, r.temp_avg, r.temp_min, r.temp_max,
               r.humidity_avg, r.battery_voltage, r.battery_percent
        FROM readings r
        INNER JOIN (
            SELECT mac, MAX(timestamp) as max_ts
            FROM readings
            GROUP BY mac
        ) latest ON r.mac = latest.mac AND r.timestamp = latest.max_ts
    """)
    result = {}
    for row in cursor.fetchall():
        result[row["mac"]] = dict(row)
    return result


def _get_latest_weather(conn: sqlite3.Connection) -> Optional[dict]:
    cursor = conn.execute("""
        SELECT timestamp, temperature, humidity, pressure,
               wind_speed, wind_direction, precipitation,
               cloud_cover, symbol_code
        FROM weather
        ORDER BY timestamp DESC
        LIMIT 1
    """)
    row = cursor.fetchone()
    return dict(row) if row else None


def generate_output(db_path: Path) -> dict:
    """Generate JSON-serializable dict with current state."""
    conn = _get_connection(db_path)
    now = datetime.now()

    try:
        site_name = _get_setting(conn, "site_name") or None
        weather_location = _get_setting(conn, "weather_location_name") or None

        devices = _get_devices(conn)
        readings = _get_latest_readings(conn)
        weather = _get_latest_weather(conn)

        sensors = []
        for dev in devices:
            mac = dev["mac"]
            reading = readings.get(mac)
            name = dev["alias"] or mac
            entry: dict = {
                "name": name,
                "mac": mac,
                "type": dev["sensor_type"],
                "order": dev["display_order"],
            }
            if reading:
                entry["temperature"] = reading["temp_avg"]
                entry["humidity"] = reading["humidity_avg"]
                entry["battery_percent"] = reading["battery_percent"]
                entry["battery_voltage"] = reading["battery_voltage"]
                entry["timestamp"] = reading["timestamp"]
                # Calculate age in seconds
                try:
                    ts = datetime.strptime(reading["timestamp"], "%Y-%m-%d %H:%M:%S")
                    entry["age_seconds"] = int((now - ts).total_seconds())
                except (ValueError, TypeError):
                    entry["age_seconds"] = None
            else:
                entry["temperature"] = None
                entry["age_seconds"] = None

            sensors.append(entry)

        output: dict = {
            "timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
            "site_name": site_name,
            "sensors": sensors,
        }

        if weather:
            output["weather"] = {
                "temperature": weather["temperature"],
                "humidity": weather["humidity"],
                "pressure": weather["pressure"],
                "wind_speed": weather["wind_speed"],
                "wind_direction": weather["wind_direction"],
                "precipitation": weather["precipitation"],
                "cloud_cover": weather["cloud_cover"],
                "symbol_code": weather["symbol_code"],
                "timestamp": weather["timestamp"],
                "location": weather_location,
            }

        return output

    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Output HutWatch data as JSON for external widgets"
    )
    parser.add_argument(
        "-d", "--database",
        type=Path,
        default=Path("hutwatch.db"),
        help="Path to SQLite database (default: hutwatch.db)",
    )
    args = parser.parse_args()

    if not args.database.exists():
        print(json.dumps({"error": f"Database not found: {args.database}"}))
        return 1

    try:
        data = generate_output(args.database)
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 0
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
