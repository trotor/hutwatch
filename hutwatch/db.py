"""SQLite database for historical sensor data."""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .models import SensorConfig

from .models import DeviceInfo

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = Path("hutwatch.db")


class Database:
    """SQLite database for sensor readings."""

    def __init__(self, db_path: Path = DEFAULT_DB_PATH) -> None:
        self._db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None

    def connect(self) -> None:
        """Connect to database and create tables."""
        logger.info("Connecting to database: %s", self._db_path)
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._create_tables()

    def close(self) -> None:
        """Close database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None

    def _create_tables(self) -> None:
        """Create database tables if they don't exist."""
        if not self._conn:
            return

        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS readings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                mac TEXT NOT NULL,
                timestamp DATETIME NOT NULL,
                temp_avg REAL NOT NULL,
                temp_min REAL NOT NULL,
                temp_max REAL NOT NULL,
                humidity_avg REAL,
                pressure_avg REAL,
                battery_voltage REAL,
                battery_percent INTEGER,
                sample_count INTEGER NOT NULL,
                UNIQUE(mac, timestamp)
            )
        """)
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_readings_mac_time
            ON readings(mac, timestamp)
        """)

        # Devices table for aliases and ordering
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS devices (
                mac TEXT PRIMARY KEY,
                alias TEXT,
                display_order INTEGER,
                sensor_type TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Weather table for external weather data
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS weather (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME NOT NULL,
                temperature REAL NOT NULL,
                humidity REAL,
                pressure REAL,
                wind_speed REAL,
                wind_direction REAL,
                precipitation REAL,
                cloud_cover REAL,
                symbol_code TEXT,
                UNIQUE(timestamp)
            )
        """)
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_weather_time
            ON weather(timestamp)
        """)

        # Key-value settings table
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)

        self._conn.commit()
        logger.debug("Database tables created")

    def get_setting(self, key: str) -> Optional[str]:
        """Get a setting value by key."""
        if not self._conn:
            return None
        row = self._conn.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else None

    def set_setting(self, key: str, value: str) -> None:
        """Set a setting value (insert or update)."""
        if not self._conn:
            return
        self._conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, value),
        )
        self._conn.commit()

    def save_aggregated_reading(
        self,
        mac: str,
        timestamp: datetime,
        temp_avg: float,
        temp_min: float,
        temp_max: float,
        humidity_avg: Optional[float] = None,
        pressure_avg: Optional[float] = None,
        battery_voltage: Optional[float] = None,
        battery_percent: Optional[int] = None,
        sample_count: int = 1,
    ) -> None:
        """Save an aggregated reading to the database."""
        if not self._conn:
            return

        try:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO readings
                (mac, timestamp, temp_avg, temp_min, temp_max, humidity_avg,
                 pressure_avg, battery_voltage, battery_percent, sample_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    mac.upper(),
                    timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                    temp_avg,
                    temp_min,
                    temp_max,
                    humidity_avg,
                    pressure_avg,
                    battery_voltage,
                    battery_percent,
                    sample_count,
                ),
            )
            self._conn.commit()
            logger.debug("Saved aggregated reading for %s", mac)
        except Exception as e:
            logger.error("Error saving reading: %s", e)

    def get_history(
        self,
        mac: str,
        hours: Optional[int] = None,
        days: Optional[int] = None,
    ) -> list[dict]:
        """Get historical readings for a sensor."""
        if not self._conn:
            return []

        if days:
            cutoff = datetime.now() - timedelta(days=days)
        elif hours:
            cutoff = datetime.now() - timedelta(hours=hours)
        else:
            cutoff = datetime.now() - timedelta(hours=24)

        cursor = self._conn.execute(
            """
            SELECT timestamp, temp_avg, temp_min, temp_max, humidity_avg
            FROM readings
            WHERE mac = ? AND timestamp >= ?
            ORDER BY timestamp ASC
            """,
            (mac.upper(), cutoff.strftime("%Y-%m-%d %H:%M:%S")),
        )

        return [dict(row) for row in cursor.fetchall()]

    def get_stats(
        self,
        mac: str,
        hours: Optional[int] = None,
        days: Optional[int] = None,
    ) -> Optional[dict]:
        """Get statistics for a sensor."""
        if not self._conn:
            return None

        if days:
            cutoff = datetime.now() - timedelta(days=days)
        elif hours:
            cutoff = datetime.now() - timedelta(hours=hours)
        else:
            cutoff = datetime.now() - timedelta(hours=24)

        cursor = self._conn.execute(
            """
            SELECT
                MIN(temp_min) as temp_min,
                MAX(temp_max) as temp_max,
                AVG(temp_avg) as temp_avg,
                AVG(humidity_avg) as humidity_avg,
                COUNT(*) as sample_count,
                MIN(timestamp) as first_reading,
                MAX(timestamp) as last_reading
            FROM readings
            WHERE mac = ? AND timestamp >= ?
            """,
            (mac.upper(), cutoff.strftime("%Y-%m-%d %H:%M:%S")),
        )

        row = cursor.fetchone()
        if row and row["sample_count"] > 0:
            return dict(row)
        return None

    def get_graph_data(
        self,
        mac: str,
        hours: int = 24,
    ) -> list[tuple[datetime, float]]:
        """Get data points for graphing."""
        if not self._conn:
            return []

        cutoff = datetime.now() - timedelta(hours=hours)

        cursor = self._conn.execute(
            """
            SELECT timestamp, temp_avg
            FROM readings
            WHERE mac = ? AND timestamp >= ?
            ORDER BY timestamp ASC
            """,
            (mac.upper(), cutoff.strftime("%Y-%m-%d %H:%M:%S")),
        )

        return [
            (datetime.strptime(row["timestamp"], "%Y-%m-%d %H:%M:%S"), row["temp_avg"])
            for row in cursor.fetchall()
        ]

    def cleanup_old_data(self, days: int = 90) -> int:
        """Remove data older than specified days."""
        if not self._conn:
            return 0

        cutoff = datetime.now() - timedelta(days=days)
        cursor = self._conn.execute(
            "DELETE FROM readings WHERE timestamp < ?",
            (cutoff.strftime("%Y-%m-%d %H:%M:%S"),),
        )
        self._conn.commit()
        return cursor.rowcount

    # Device management methods

    def get_device(self, mac: str) -> Optional[DeviceInfo]:
        """Get device info by MAC address."""
        if not self._conn:
            return None

        cursor = self._conn.execute(
            "SELECT mac, alias, display_order, sensor_type FROM devices WHERE mac = ?",
            (mac.upper(),),
        )
        row = cursor.fetchone()
        if row:
            return DeviceInfo(
                mac=row["mac"],
                alias=row["alias"],
                display_order=row["display_order"],
                sensor_type=row["sensor_type"],
            )
        return None

    def get_all_devices(self) -> list[DeviceInfo]:
        """Get all devices ordered by display_order."""
        if not self._conn:
            return []

        cursor = self._conn.execute(
            "SELECT mac, alias, display_order, sensor_type FROM devices ORDER BY display_order"
        )
        return [
            DeviceInfo(
                mac=row["mac"],
                alias=row["alias"],
                display_order=row["display_order"],
                sensor_type=row["sensor_type"],
            )
            for row in cursor.fetchall()
        ]

    def set_device_alias(self, mac: str, alias: Optional[str]) -> bool:
        """Set device alias. Pass None to clear alias."""
        if not self._conn:
            return False

        try:
            self._conn.execute(
                """
                UPDATE devices SET alias = ?, updated_at = CURRENT_TIMESTAMP
                WHERE mac = ?
                """,
                (alias, mac.upper()),
            )
            self._conn.commit()
            return self._conn.total_changes > 0
        except Exception as e:
            logger.error("Error setting device alias: %s", e)
            return False

    def set_device_order(self, mac: str, order: int) -> bool:
        """Set device display order."""
        if not self._conn:
            return False

        try:
            self._conn.execute(
                """
                UPDATE devices SET display_order = ?, updated_at = CURRENT_TIMESTAMP
                WHERE mac = ?
                """,
                (order, mac.upper()),
            )
            self._conn.commit()
            return self._conn.total_changes > 0
        except Exception as e:
            logger.error("Error setting device order: %s", e)
            return False

    def sync_devices_from_config(self, sensors: list["SensorConfig"]) -> None:
        """Sync devices from config to database.

        Adds new devices, does not overwrite existing aliases/orders.
        """
        if not self._conn:
            return

        # Get existing devices
        cursor = self._conn.execute("SELECT mac FROM devices")
        existing_macs = {row["mac"] for row in cursor.fetchall()}

        # Get next available order number
        cursor = self._conn.execute("SELECT MAX(display_order) FROM devices")
        row = cursor.fetchone()
        next_order = (row[0] or 0) + 1

        # Add new devices
        for sensor in sensors:
            mac = sensor.mac.upper()
            if mac not in existing_macs:
                self._conn.execute(
                    """
                    INSERT INTO devices (mac, alias, display_order, sensor_type)
                    VALUES (?, NULL, ?, ?)
                    """,
                    (mac, next_order, sensor.type.value),
                )
                logger.info("Added device %s (%s) with order %d", sensor.name, mac, next_order)
                next_order += 1

        self._conn.commit()

    def get_device_by_order(self, order: int) -> Optional[DeviceInfo]:
        """Get device by display order number."""
        if not self._conn:
            return None

        cursor = self._conn.execute(
            "SELECT mac, alias, display_order, sensor_type FROM devices WHERE display_order = ?",
            (order,),
        )
        row = cursor.fetchone()
        if row:
            return DeviceInfo(
                mac=row["mac"],
                alias=row["alias"],
                display_order=row["display_order"],
                sensor_type=row["sensor_type"],
            )
        return None

    # Weather methods

    def save_weather(
        self,
        timestamp: datetime,
        temperature: float,
        humidity: Optional[float] = None,
        pressure: Optional[float] = None,
        wind_speed: Optional[float] = None,
        wind_direction: Optional[float] = None,
        precipitation: Optional[float] = None,
        cloud_cover: Optional[float] = None,
        symbol_code: Optional[str] = None,
    ) -> None:
        """Save weather data to the database."""
        if not self._conn:
            return

        try:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO weather
                (timestamp, temperature, humidity, pressure, wind_speed,
                 wind_direction, precipitation, cloud_cover, symbol_code)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                    temperature,
                    humidity,
                    pressure,
                    wind_speed,
                    wind_direction,
                    precipitation,
                    cloud_cover,
                    symbol_code,
                ),
            )
            self._conn.commit()
            logger.debug("Saved weather data: %.1f°C", temperature)
        except Exception as e:
            logger.error("Error saving weather: %s", e)

    def get_weather_history(
        self,
        hours: Optional[int] = None,
        days: Optional[int] = None,
    ) -> list[dict]:
        """Get weather history."""
        if not self._conn:
            return []

        if days:
            cutoff = datetime.now() - timedelta(days=days)
        elif hours:
            cutoff = datetime.now() - timedelta(hours=hours)
        else:
            cutoff = datetime.now() - timedelta(hours=24)

        cursor = self._conn.execute(
            """
            SELECT timestamp, temperature, humidity, pressure,
                   wind_speed, precipitation, symbol_code
            FROM weather
            WHERE timestamp >= ?
            ORDER BY timestamp ASC
            """,
            (cutoff.strftime("%Y-%m-%d %H:%M:%S"),),
        )

        return [dict(row) for row in cursor.fetchall()]

    def get_weather_stats(
        self,
        hours: Optional[int] = None,
        days: Optional[int] = None,
    ) -> Optional[dict]:
        """Get weather statistics."""
        if not self._conn:
            return None

        if days:
            cutoff = datetime.now() - timedelta(days=days)
        elif hours:
            cutoff = datetime.now() - timedelta(hours=hours)
        else:
            cutoff = datetime.now() - timedelta(hours=24)

        cursor = self._conn.execute(
            """
            SELECT
                MIN(temperature) as temp_min,
                MAX(temperature) as temp_max,
                AVG(temperature) as temp_avg,
                AVG(humidity) as humidity_avg,
                AVG(wind_speed) as wind_avg,
                SUM(precipitation) as precipitation_total,
                COUNT(*) as sample_count,
                MIN(timestamp) as first_reading,
                MAX(timestamp) as last_reading
            FROM weather
            WHERE timestamp >= ?
            """,
            (cutoff.strftime("%Y-%m-%d %H:%M:%S"),),
        )

        row = cursor.fetchone()
        if row and row["sample_count"] > 0:
            return dict(row)
        return None

    def get_latest_weather(self) -> Optional[dict]:
        """Get the most recent weather data."""
        if not self._conn:
            return None

        cursor = self._conn.execute(
            """
            SELECT timestamp, temperature, humidity, pressure,
                   wind_speed, wind_direction, precipitation,
                   cloud_cover, symbol_code
            FROM weather
            ORDER BY timestamp DESC
            LIMIT 1
            """
        )

        row = cursor.fetchone()
        if row:
            return dict(row)
        return None

    def get_weather_graph_data(
        self,
        hours: int = 24,
    ) -> list[tuple[datetime, float]]:
        """Get weather data points for graphing."""
        if not self._conn:
            return []

        cutoff = datetime.now() - timedelta(hours=hours)

        cursor = self._conn.execute(
            """
            SELECT timestamp, temperature
            FROM weather
            WHERE timestamp >= ?
            ORDER BY timestamp ASC
            """,
            (cutoff.strftime("%Y-%m-%d %H:%M:%S"),),
        )

        return [
            (datetime.strptime(row["timestamp"], "%Y-%m-%d %H:%M:%S"), row["temperature"])
            for row in cursor.fetchall()
        ]
