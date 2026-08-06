"""Epoch <-> datetime helpers that survive pre-1970 timestamps on Windows.

`datetime.fromtimestamp(negative_value)` raises OSError [Errno 22] on Windows
because the underlying CRT call rejects negative time_t. That is not a hypothetical:
Yahoo serves S&P 500 daily bars from 1927 and Dow Jones from 1896, so any index
with deep history produces negative epoch seconds and crashes naive conversion.

Adding a timedelta to the epoch does the arithmetic in Python instead of the C
library, which handles negatives correctly on every platform.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def utc_from_epoch(ts: int | float) -> datetime:
    """Epoch seconds -> aware UTC datetime. Safe for negative (pre-1970) values."""
    return EPOCH + timedelta(seconds=float(ts))


def epoch_from_utc(dt: datetime) -> int:
    """Aware (or naive-UTC) datetime -> epoch seconds. Safe for pre-1970."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int((dt - EPOCH).total_seconds())


def iso_date(ts: int | float) -> str:
    """Epoch seconds -> 'YYYY-MM-DD'."""
    return utc_from_epoch(ts).strftime("%Y-%m-%d")
