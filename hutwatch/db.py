"""SQLite database for historical sensor data."""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

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
        self._conn.commit()
        logger.debug("Database tables created")

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
