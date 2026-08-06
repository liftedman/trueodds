"""Causal feature engineering.

Every feature here is computed from bars at index <= i only. That rule is the
whole point of this module, and it is why the feature code is written out
longhand instead of using convenient whole-array helpers: functions like
`df.rolling(...).mean()` are easy to get right, and `df.pct_change().shift(-1)`
or a z-score taken over the *full* history are just as easy to get wrong. A
single accidental forward reference turns a worthless model into one that looks
extraordinary, so the arithmetic is kept explicit and auditable.

The target is built by `build_dataset`: row i predicts whether
close[i + horizon] > close[i]. Row i's features stop at bar i, so the
information boundary is exact - the same role kickoff time plays in the sports
model.

Nothing here is standardised against global statistics. Scaling happens inside
the walk-forward loop in evaluate.py, fitted on training bars only, because
scaling on the full series leaks the future distribution into the past.
"""

from __future__ import annotations

import math

import numpy as np

from . import timeutil

# Feature names, in the exact column order build_matrix produces.
FEATURE_NAMES: list[str] = [
    "ret_1",
    "ret_3",
    "ret_5",
    "ret_10",
    "ret_20",
    "vol_10",
    "vol_30",
    "rsi_14",
    "range_pos_20",
    "sma_dist_20",
    "sma_dist_50",
    "body_frac",
    "hl_range_z",
    "vol_z_20",
    "hour_sin",
    "hour_cos",
    "dow_sin",
    "dow_cos",
]

# Bars of history a full feature row needs. Rows before this are unusable.
WARMUP = 60


def _safe_log_ret(a: float, b: float) -> float:
    """log(a/b), guarding against zero/negative prices in bad data."""
    if a <= 0.0 or b <= 0.0:
        return 0.0
    return math.log(a / b)


def _rsi(closes: np.ndarray, i: int, period: int = 14) -> float:
    """Wilder-style RSI over the `period` bars ending at i, scaled to 0-1.

    Uses a simple average of gains/losses (not the recursive smoothing) so the
    value at i depends only on the last `period` differences - no state carried
    forward that could accidentally embed later bars.
    """
    start = i - period
    if start < 1:
        return 0.5
    gains = 0.0
    losses = 0.0
    for j in range(start + 1, i + 1):
        d = closes[j] - closes[j - 1]
        if d >= 0:
            gains += d
        else:
            losses -= d
    if gains + losses == 0.0:
        return 0.5
    return gains / (gains + losses)


def _std(vals: np.ndarray) -> float:
    if vals.size < 2:
        return 0.0
    s = float(np.std(vals))
    return s if s == s else 0.0  # NaN guard


def build_matrix(
    ts: np.ndarray,
    open_: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    volume: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Build the feature matrix.

    Returns (X, idx) where X[k] are the features known at bar idx[k]. Only bars
    with a complete warmup window appear, so idx starts at WARMUP.
    """
    n = close.size
    rows: list[list[float]] = []
    kept: list[int] = []

    # Pre-compute log returns once: logret[j] = log(close[j]/close[j-1]).
    logret = np.zeros(n, dtype=float)
    for j in range(1, n):
        logret[j] = _safe_log_ret(close[j], close[j - 1])

    for i in range(WARMUP, n):
        c = close[i]

        # --- momentum: returns over several lookbacks -----------------------
        ret_1 = logret[i]
        ret_3 = _safe_log_ret(c, close[i - 3])
        ret_5 = _safe_log_ret(c, close[i - 5])
        ret_10 = _safe_log_ret(c, close[i - 10])
        ret_20 = _safe_log_ret(c, close[i - 20])

        # --- volatility: dispersion of recent returns -----------------------
        vol_10 = _std(logret[i - 9 : i + 1])
        vol_30 = _std(logret[i - 29 : i + 1])

        # --- mean reversion / location --------------------------------------
        rsi_14 = _rsi(close, i, 14)

        win20 = close[i - 19 : i + 1]
        lo20, hi20 = float(win20.min()), float(win20.max())
        range_pos_20 = (c - lo20) / (hi20 - lo20) if hi20 > lo20 else 0.5

        sma20 = float(win20.mean())
        sma50 = float(close[i - 49 : i + 1].mean())
        sma_dist_20 = (c / sma20 - 1.0) if sma20 > 0 else 0.0
        sma_dist_50 = (c / sma50 - 1.0) if sma50 > 0 else 0.0

        # --- bar shape -------------------------------------------------------
        bar_range = high[i] - low[i]
        body_frac = ((c - open_[i]) / bar_range) if bar_range > 0 else 0.0

        # Current bar's range vs its recent norm - a cheap regime signal.
        recent_ranges = high[i - 19 : i + 1] - low[i - 19 : i + 1]
        rr_mean = float(recent_ranges.mean())
        rr_std = _std(recent_ranges)
        hl_range_z = ((bar_range - rr_mean) / rr_std) if rr_std > 0 else 0.0

        # --- volume ----------------------------------------------------------
        # Absent for FX and indices; a constant 0 then, which the model ignores.
        v = volume[i]
        vwin = volume[i - 19 : i + 1]
        if v == v and vwin.size and float(vwin.max()) > 0:
            v_mean = float(vwin.mean())
            v_std = _std(vwin)
            vol_z_20 = ((v - v_mean) / v_std) if v_std > 0 else 0.0
        else:
            vol_z_20 = 0.0

        # --- session / seasonality -------------------------------------------
        # Encoded as sin/cos pairs so 23:00 and 00:00 are adjacent rather than
        # maximally distant. Intraday FX and equities genuinely behave
        # differently by session, so this is a real regime feature.
        # timeutil, not datetime.fromtimestamp: index history reaches back before
        # 1970 and negative timestamps raise OSError on Windows.
        dt = timeutil.utc_from_epoch(int(ts[i]))
        hour_frac = (dt.hour + dt.minute / 60.0) / 24.0
        hour_sin = math.sin(2 * math.pi * hour_frac)
        hour_cos = math.cos(2 * math.pi * hour_frac)
        dow_frac = dt.weekday() / 7.0
        dow_sin = math.sin(2 * math.pi * dow_frac)
        dow_cos = math.cos(2 * math.pi * dow_frac)

        row = [
            ret_1, ret_3, ret_5, ret_10, ret_20,
            vol_10, vol_30,
            rsi_14, range_pos_20, sma_dist_20, sma_dist_50,
            body_frac, hl_range_z, vol_z_20,
            hour_sin, hour_cos, dow_sin, dow_cos,
        ]
        if any(x != x or math.isinf(x) for x in row):
            continue  # drop rows corrupted by bad upstream data

        rows.append(row)
        kept.append(i)

    if not rows:
        return np.empty((0, len(FEATURE_NAMES))), np.empty(0, dtype=int)

    return np.asarray(rows, dtype=float), np.asarray(kept, dtype=int)


def arrays_from_candles(candles) -> tuple[np.ndarray, ...]:
    """Unpack sqlite3.Row candles into aligned numpy arrays."""
    ts = np.asarray([int(r["ts"]) for r in candles], dtype=np.int64)
    open_ = np.asarray([float(r["open"]) for r in candles], dtype=float)
    high = np.asarray([float(r["high"]) for r in candles], dtype=float)
    low = np.asarray([float(r["low"]) for r in candles], dtype=float)
    close = np.asarray([float(r["close"]) for r in candles], dtype=float)
    volume = np.asarray(
        [float(r["volume"]) if r["volume"] is not None else float("nan") for r in candles],
        dtype=float,
    )
    return ts, open_, high, low, close, volume


def build_dataset(candles, horizon: int = 1):
    """Build (X, y, idx, ts, close) for a direction model.

    y[k] = 1 if close[idx[k] + horizon] > close[idx[k]] else 0.

    Rows whose target bar does not exist yet are dropped, so every returned row
    has a settled outcome. Exact ties (close unchanged) are dropped too rather
    than being arbitrarily assigned - on a fixed-time platform an unchanged
    price is typically a loss or a refund depending on the venue, and quietly
    calling it "up" would flatter the model.
    """
    ts, open_, high, low, close, volume = arrays_from_candles(candles)
    if close.size < WARMUP + horizon + 2:
        return (
            np.empty((0, len(FEATURE_NAMES))),
            np.empty(0, dtype=int),
            np.empty(0, dtype=int),
            ts,
            close,
        )

    X_all, idx_all = build_matrix(ts, open_, high, low, close, volume)

    keep_rows: list[int] = []
    ys: list[int] = []
    for k, i in enumerate(idx_all):
        j = i + horizon
        if j >= close.size:
            break
        if close[j] == close[i]:
            continue  # tie - see docstring
        keep_rows.append(k)
        ys.append(1 if close[j] > close[i] else 0)

    if not keep_rows:
        return (
            np.empty((0, len(FEATURE_NAMES))),
            np.empty(0, dtype=int),
            np.empty(0, dtype=int),
            ts,
            close,
        )

    sel = np.asarray(keep_rows, dtype=int)
    return X_all[sel], np.asarray(ys, dtype=int), idx_all[sel], ts, close
