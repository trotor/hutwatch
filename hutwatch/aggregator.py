"""Data aggregator for periodic database storage."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Optional

from .alerts import AlertManager
from .battery import update_battery_states
from .ble.sensor_store import SensorStore
from .db import Database
from .models import AppConfig

if TYPE_CHECKING:
    from .alerts import AlertInputs
    from .models import SensorReading
    from .remote import RemotePoller
    from .weather import WeatherFetcher

logger = logging.getLogger(__name__)

# Aggregation interval in seconds (5 minutes)
AGGREGATION_INTERVAL = 300

# Weather fetch interval in seconds (1 hour)
WEATHER_FETCH_INTERVAL = 3600

# Grace period after startup before silence alerts are evaluated (15 minutes),
# so BLE has time to pick up advertisements before anything looks quiet
SILENCE_GRACE_SECONDS = 900

# Devices unheard from for longer than this get no new auto rules. Device rows
# outlive the sensors themselves — macOS rotates its BLE identifiers, so old
# rows accumulate — and a sensor that vanished months ago is not news.
AUTO_RULE_MAX_AGE_DAYS = 7


class Aggregator:
    """Aggregates sensor data and saves to database periodically."""

    def __init__(
        self,
        config: AppConfig,
        store: SensorStore,
        db: Database,
        weather: Optional["WeatherFetcher"] = None,
    ) -> None:
        self._config = config
        self._store = store
        self._db = db
        self._weather = weather
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._weather_task: Optional[asyncio.Task] = None
        self._last_aggregation: dict[str, datetime] = {}
        self._alert_manager: Optional[AlertManager] = None
        self._alert_callback = None  # async callable(list[AlertEvent])
        self._remote: Optional["RemotePoller"] = None
        self._start_time = datetime.now()

    async def start(self) -> None:
        """Start the aggregator."""
        if self._running:
            return

        logger.info("Starting data aggregator (interval: %ds)", AGGREGATION_INTERVAL)
        self._running = True
        self._start_time = datetime.now()
        self._task = asyncio.create_task(self._run())

        if self._weather:
            logger.info("Starting weather fetcher (interval: %ds)", WEATHER_FETCH_INTERVAL)
            self._weather_task = asyncio.create_task(self._run_weather())

    def set_weather(self, weather: "WeatherFetcher") -> None:
        """Set weather fetcher and start periodic fetching."""
        self._weather = weather
        if self._running and not self._weather_task:
            self._weather_task = asyncio.create_task(self._run_weather())

    def set_alert_manager(
        self, manager: AlertManager, callback, remote: Optional["RemotePoller"] = None,
    ) -> None:
        """Set alert manager and callback for alert events."""
        self._alert_manager = manager
        self._alert_callback = callback
        self._remote = remote

    async def fetch_weather_now(self) -> bool:
        """Fetch weather on demand. Returns True if successful."""
        if not self._weather:
            return False
        await self._fetch_weather()
        return self._weather.latest is not None

    async def stop(self) -> None:
        """Stop the aggregator."""
        if not self._running:
            return

        logger.info("Stopping data aggregator")
        self._running = False

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        if self._weather_task:
            self._weather_task.cancel()
            try:
                await self._weather_task
            except asyncio.CancelledError:
                pass
            self._weather_task = None

    async def _run(self) -> None:
        """Main aggregation loop."""
        # Evaluate battery state from stored history right away
        self._update_battery_states()

        while self._running:
            try:
                await asyncio.sleep(AGGREGATION_INTERVAL)
                await self._aggregate()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Aggregation error: %s", e)

    async def _aggregate(self) -> None:
        """Aggregate and save data for all sensors."""
        now = datetime.now()
        # Round to 5-minute boundary
        timestamp = now.replace(
            minute=(now.minute // 5) * 5,
            second=0,
            microsecond=0,
        )

        for sensor_config in self._config.sensors:
            mac = sensor_config.mac

            # Get recent readings from store
            readings = self._store.get_history(mac, hours=1)

            # Filter to last 5 minutes
            cutoff = now - timedelta(seconds=AGGREGATION_INTERVAL)
            recent = [r for r in readings if r.timestamp >= cutoff]

            if not recent:
                continue

            # Calculate aggregates
            temps = [r.temperature for r in recent]
            temp_avg = sum(temps) / len(temps)
            temp_min = min(temps)
            temp_max = max(temps)

            humidity_avg = None
            humidities = [r.humidity for r in recent if r.humidity is not None]
            if humidities:
                humidity_avg = sum(humidities) / len(humidities)

            pressure_avg = None
            pressures = [r.pressure for r in recent if r.pressure is not None]
            if pressures:
                pressure_avg = sum(pressures) / len(pressures)

            # Get latest battery info
            latest = recent[-1]
            battery_voltage = latest.battery_voltage
            battery_percent = latest.battery_percent

            # Save to database
            self._db.save_aggregated_reading(
                mac=mac,
                timestamp=timestamp,
                temp_avg=temp_avg,
                temp_min=temp_min,
                temp_max=temp_max,
                humidity_avg=humidity_avg,
                pressure_avg=pressure_avg,
                battery_voltage=battery_voltage,
                battery_percent=battery_percent,
                sample_count=len(recent),
            )

            logger.debug(
                "Aggregated %d readings for %s: %.1f°C (min=%.1f, max=%.1f)",
                len(recent),
                sensor_config.name,
                temp_avg,
                temp_min,
                temp_max,
            )

        # Flush buffered remote readings into the same 5-min bucket
        if self._remote is not None:
            try:
                n = self._remote.flush_readings_to_db(timestamp)
                if n:
                    logger.debug("Flushed %d remote sensor aggregates", n)
            except Exception as e:
                logger.warning("Failed to flush remote readings: %s", e)

        self._update_battery_states()

        # Check alert thresholds
        if self._alert_manager and self._alert_callback:
            try:
                inputs = self._build_alert_inputs(now)
                events = self._alert_manager.check(inputs)
                if events:
                    await self._alert_callback(events)
            except Exception as e:
                logger.error("Alert check error: %s", e)

    def _build_alert_inputs(self, now: datetime) -> "AlertInputs":
        """Collect temperature, battery and last-seen data for the alert pass."""
        from .alerts import AlertInputs, DeviceHealth
        from .models import SensorReading

        inputs = AlertInputs()

        # Silence checks need BLE to have had a chance to hear the sensors first
        inputs.check_silence = (
            now - self._start_time >= timedelta(seconds=SILENCE_GRACE_SECONDS)
        )

        # Local devices plus every peer's — get_all_devices() returns only
        # site IS NULL rows, and peer sensors need watching just as much
        devices = self._db.get_all_devices(include_hidden=True)
        if self._remote:
            for site_name in self._remote.get_all_site_data():
                devices.extend(self._db.get_all_devices(site=site_name))
        device_map = {d.mac: d for d in devices}
        battery_units: dict[str, str] = {}
        auto_eligible: set[str] = set()

        stored_last_seen = self._db.get_last_reading_times()

        # ── Local sensors ─────────────────────────────────────────────
        for sensor_config in self._config.sensors:
            mac = sensor_config.mac
            device = device_map.get(mac)
            if device and device.hidden:
                continue

            if device:
                inputs.device_names[mac] = device.get_display_name()
            else:
                inputs.device_names[mac] = sensor_config.name

            health = DeviceHealth()

            history = self._store.get_history(mac, hours=1)
            latest = history[-1] if history else None
            if latest:
                inputs.readings[mac] = latest
                health.temperature = latest.temperature

            last_seen = latest.timestamp if latest else stored_last_seen.get(mac)
            if last_seen:
                health.silent_hours = (now - last_seen).total_seconds() / 3600
            else:
                # Never heard from: measure silence from app start so a sensor
                # that never appears still eventually raises an alert
                health.silent_hours = (now - self._start_time).total_seconds() / 3600

            # Battery: prefer a live reading, fall back to the last stored one
            battery = self._latest_battery(mac, latest)
            if battery:
                health.battery_value, health.battery_unit = battery
                if self._eligible_for_auto_rules(health.silent_hours):
                    battery_units[mac] = health.battery_unit

            inputs.health[mac] = health
            if self._eligible_for_auto_rules(health.silent_hours):
                auto_eligible.add(mac)

        # ── Remote/peer sensors ───────────────────────────────────────
        if self._remote:
            for site_name, site_data in self._remote.get_all_site_data().items():
                # A whole site going dark is the peer watchdog's job
                if not site_data.online:
                    continue
                for sensor in site_data.sensors:
                    if not sensor.mac:
                        continue
                    mac = sensor.mac.upper()
                    if mac in inputs.health:
                        continue
                    device = device_map.get(mac)
                    if device and device.hidden:
                        continue

                    inputs.device_names[mac] = f"{site_name} / {sensor.name}"

                    if sensor.temperature is not None:
                        inputs.readings[mac] = SensorReading(
                            mac=mac,
                            timestamp=now,
                            temperature=sensor.temperature,
                            humidity=sensor.humidity,
                        )

                    health = DeviceHealth(temperature=sensor.temperature)
                    if sensor.battery_voltage is not None:
                        health.battery_value = sensor.battery_voltage
                        health.battery_unit = "V"
                    elif sensor.battery_percent is not None:
                        health.battery_value = float(sensor.battery_percent)
                        health.battery_unit = "%"

                    if sensor.age_seconds is not None:
                        health.silent_hours = sensor.age_seconds / 3600

                    inputs.health[mac] = health
                    if self._eligible_for_auto_rules(health.silent_hours):
                        auto_eligible.add(mac)
                        if health.battery_unit:
                            battery_units[mac] = health.battery_unit

        # Provision auto-managed rules for the devices we have recently heard from
        known = [d for d in devices if d.mac in auto_eligible]
        self._alert_manager.sync_default_rules(known, battery_units)

        return inputs

    @staticmethod
    def _eligible_for_auto_rules(silent_hours: Optional[float]) -> bool:
        """Whether a device is recent enough to be given auto-managed rules."""
        if silent_hours is None:
            return True
        return silent_hours <= AUTO_RULE_MAX_AGE_DAYS * 24

    def _latest_battery(
        self, mac: str, latest: Optional["SensorReading"],
    ) -> Optional[tuple[float, str]]:
        """Get the most recent battery level and its unit for a device."""
        if latest is not None:
            if latest.battery_voltage is not None:
                return latest.battery_voltage, "V"
            if latest.battery_percent is not None:
                return float(latest.battery_percent), "%"

        stored = self._db.get_latest_battery(mac)
        if stored:
            return stored
        return None

    def _update_battery_states(self) -> None:
        """Recompute low-battery flags for local and remote/peer sensors.

        Remote readings are flushed into the local readings table, so their
        battery history is evaluated here too — older peers don't send a
        battery_low flag of their own.
        """
        macs = [s.mac for s in self._config.sensors]
        if self._remote:
            for site_data in self._remote.get_all_site_data().values():
                macs.extend(s.mac.upper() for s in site_data.sensors if s.mac)
        update_battery_states(self._store, self._db, macs)

    async def _run_weather(self) -> None:
        """Weather fetch loop."""
        # Fetch immediately on start
        await self._fetch_weather()

        while self._running:
            try:
                await asyncio.sleep(WEATHER_FETCH_INTERVAL)
                await self._fetch_weather()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Weather fetch error: %s", e)

    async def _fetch_weather(self) -> None:
        """Fetch and save weather data."""
        if not self._weather:
            return

        weather = await self._weather.fetch()
        if weather:
            # Round timestamp to 5-minute boundary
            now = datetime.now()
            timestamp = now.replace(
                minute=(now.minute // 5) * 5,
                second=0,
                microsecond=0,
            )

            self._db.save_weather(
                timestamp=timestamp,
                temperature=weather.temperature,
                humidity=weather.humidity,
                pressure=weather.pressure,
                wind_speed=weather.wind_speed,
                wind_direction=weather.wind_direction,
                precipitation=weather.precipitation,
                cloud_cover=weather.cloud_cover,
                symbol_code=weather.symbol_code,
            )
