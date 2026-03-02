"""Time window parser and epiweek calculator."""

from __future__ import annotations

import re
from datetime import datetime, timedelta

_WINDOW_RE = re.compile(r"^(\d+)([wdhm])$")

_UNITS = {
    "w": lambda n: timedelta(weeks=n),
    "d": lambda n: timedelta(days=n),
    "h": lambda n: timedelta(hours=n),
    "m": lambda n: timedelta(minutes=n),
}


def parse_time_window(window: str) -> timedelta:
    """Parse "12w", "4w", "7d", "24h", "30m" → timedelta."""
    match = _WINDOW_RE.match(window.strip())
    if not match:
        raise ValueError(
            f"Invalid time window format: {window!r}"
            " (expected e.g. '12w', '7d', '24h', '30m')"
        )
    amount, unit = int(match.group(1)), match.group(2)
    return _UNITS[unit](amount)


def epiweek(dt: datetime) -> str:
    """Return ISO week string like '2026-W09' for dedup keys."""
    iso = dt.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"
