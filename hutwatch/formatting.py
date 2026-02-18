"""Shared formatting and utility functions for all UI modules."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Optional

from .i18n import t

if TYPE_CHECKING:
    from .db import Database
    from .models import AppConfig, DeviceInfo


def format_age(seconds: float) -> str:
    """Format age in seconds to short human-readable string (e.g. '5min', '2h')."""
    if seconds < 60:
        return t("time_short_seconds", n=int(seconds))
    elif seconds < 3600:
        return t("time_short_minutes", n=int(seconds / 60))
    else:
        return t("time_short_hours", n=int(seconds / 3600))


def format_age_long(seconds: float) -> str:
    """Format age in seconds to long human-readable string (e.g. '5 minutes ago')."""
    seconds = int(seconds)
    if seconds < 60:
        return t("time_ago_seconds", n=seconds)
    elif seconds < 3600:
        return t("time_ago_minutes", n=seconds // 60)
    else:
        return t("time_ago_hours", n=seconds // 3600)


def format_uptime(uptime: timedelta) -> str:
    """Format uptime timedelta as human-readable string."""
    total_seconds = int(uptime.total_seconds())
    days = total_seconds // 86400
    hours = (total_seconds % 86400) // 3600
    minutes = (total_seconds % 3600) // 60

    if days > 0:
        return t("time_uptime_dhm", d=days, h=hours, m=minutes)
    elif hours > 0:
        return t("time_uptime_hm", h=hours, m=minutes)
    else:
        return t("time_uptime_m", m=minutes)


def parse_time_arg(arg: str) -> tuple[Optional[int], Optional[int]]:
    """Parse time argument like '6', '24h', '7d'.

    Returns (hours, days) tuple. Both None if parsing fails.
    """
    arg = arg.lower().strip()
    if arg.endswith("d"):
        try:
            return None, int(arg[:-1])
        except ValueError:
            return None, None
    elif arg.endswith("h"):
        try:
            return int(arg[:-1]), None
        except ValueError:
            return None, None
    else:
        try:
            return int(arg), None
        except ValueError:
            return None, None


def compute_cutoff(
    hours: Optional[int] = None,
    days: Optional[int] = None,
    default_hours: int = 24,
) -> datetime:
    """Compute a cutoff datetime from hours/days parameters."""
    if days:
        return datetime.now() - timedelta(days=days)
    elif hours:
        return datetime.now() - timedelta(hours=hours)
    else:
        return datetime.now() - timedelta(hours=default_hours)


def resolve_device(
    identifier: str,
    db: Database,
    config: AppConfig,
) -> Optional[DeviceInfo]:
    """Resolve device by order number, alias, config name, or MAC.

    Returns DeviceInfo with config_name populated if found.
    """
    # Try as order number first
    if identifier.isdigit():
        device = db.get_device_by_order(int(identifier))
        if device:
            sensor_config = config.get_sensor_by_mac(device.mac)
            if sensor_config:
                device.config_name = sensor_config.name
            return device

    # Get all devices with config names populated
    devices = db.get_all_devices()
    for d in devices:
        sensor_config = config.get_sensor_by_mac(d.mac)
        if sensor_config:
            d.config_name = sensor_config.name

    # Search by alias (case-insensitive)
    for d in devices:
        if d.alias and d.alias.lower() == identifier.lower():
            return d

    # Search by config name (case-insensitive)
    for d in devices:
        if d.config_name and d.config_name.lower() == identifier.lower():
            return d

    # Search by MAC address
    for d in devices:
        if d.mac == identifier.upper():
            return d

    return None


def create_ascii_graph(
    data: list[tuple[datetime, float]],
    width: int = 24,
    height: int = 8,
    no_data_message: Optional[str] = None,
) -> tuple[str, str]:
    """Create ASCII art graph from data points.

    Returns tuple of (graph_string, timeline_string).
    """
    if not data:
        return no_data_message or t("common_no_data"), ""

    timestamps = [ts for ts, _ in data]
    temps = [v for _, v in data]
    min_temp = min(temps)
    max_temp = max(temps)
    temp_range = max_temp - min_temp

    if temp_range == 0:
        temp_range = 1

    # Sample data to fit width
    step = max(1, len(data) // width)
    sampled = [temps[i] for i in range(0, len(data), step)][:width]
    sampled_times = [timestamps[i] for i in range(0, len(data), step)][:width]
    actual_width = len(sampled)

    # Build graph
    lines = []
    for row in range(height):
        threshold = max_temp - (row / (height - 1)) * temp_range
        bar = ""
        for temp in sampled:
            if temp >= threshold:
                bar += "\u2588"
            else:
                bar += " "
        if row == 0:
            lines.append(f"{max_temp:5.1f}\u00b0\u2502{bar}\u2502")
        elif row == height - 1:
            lines.append(f"{min_temp:5.1f}\u00b0\u2502{bar}\u2502")
        else:
            lines.append(f"      \u2502{bar}\u2502")

    # Build timeline
    if sampled_times:
        first_time = sampled_times[0]
        last_time = sampled_times[-1]
        total_h = (last_time - first_time).total_seconds() / 3600

        if total_h <= 24:
            first_label = first_time.strftime("%H:%M")
            last_label = last_time.strftime("%H:%M")
        else:
            first_label = first_time.strftime("%d.%m")
            last_label = last_time.strftime("%d.%m")

        padding = actual_width - len(first_label) - len(last_label)
        if padding > 0:
            timeline = f"      \u2514{first_label}{' ' * padding}{last_label}\u2518"
        else:
            timeline = f"      \u2514{first_label}{'\u2500' * (actual_width - len(first_label))}\u2518"
    else:
        timeline = ""

    return "\n".join(lines), timeline
