"""PNG temperature graph rendering for Telegram."""

from __future__ import annotations

import io
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt

    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False


def render_temperature_graph(
    data: list[tuple[datetime, float]],
    title: str,
    hours: int,
) -> Optional[io.BytesIO]:
    """Render a temperature line chart as PNG bytes.

    Returns None when matplotlib is unavailable or data is empty.
    """
    if not HAS_MATPLOTLIB or not data:
        return None

    times = [d[0] for d in data]
    temps = [d[1] for d in data]

    try:
        fig, ax = plt.subplots(figsize=(8, 4), dpi=110)
        ax.plot(times, temps, linewidth=1.8, color="#d62728")
        ax.fill_between(times, temps, alpha=0.12, color="#d62728")
        ax.grid(True, alpha=0.3, linestyle="--")
        ax.set_ylabel("°C")
        ax.set_title(title)

        if hours <= 36:
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
        elif hours <= 24 * 7:
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%a %H:%M"))
        else:
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%d.%m."))

        fig.autofmt_xdate()
        fig.tight_layout()

        buf = io.BytesIO()
        fig.savefig(buf, format="png")
        plt.close(fig)
        buf.seek(0)
        return buf
    except Exception as e:
        logger.warning("Failed to render PNG graph: %s", e)
        return None
