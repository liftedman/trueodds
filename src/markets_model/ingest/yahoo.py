"""FX, stocks, indices and commodities from Yahoo Finance (via `yfinance`).

One free, keyless source covering four of our five asset classes. History depth
per interval is capped upstream - see config.YAHOO_MAX_PERIOD, whose numbers were
measured against the live API rather than assumed.

Two correctness details that matter more than they look:

1. `auto_adjust=False`. We want the price a trader actually saw. Adjusted closes
   retroactively rewrite history for dividends and splits, which would leak
   future corporate-action information into a backtest.

2. We drop the final row when it is a bar still forming. Yahoo happily returns a
   partial current bar, and treating it as closed is the classic way an intraday
   backtest acquires look-ahead.
"""

from __future__ import annotations

import time
import warnings
from datetime import timezone

from .. import config, db, timeutil

# yfinance is noisy about missing data on delisted/odd tickers; we report
# failures ourselves, per symbol, so the chatter adds nothing.
warnings.filterwarnings("ignore", module="yfinance")


def _import_yf():
    """Import yfinance lazily so the rest of the package works without it."""
    try:
        import yfinance as yf
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "yfinance is required for FX/stocks/indices/commodities. "
            'Install it with:  pip install -e ".[dev]"  (or pip install yfinance)'
        ) from exc
    return yf


def fetch_bars(src_code: str, interval: str, period: str | None = None) -> list[tuple]:
    """Fetch bars for one Yahoo ticker at one interval.

    Returns (ts, open, high, low, close, volume) tuples, oldest first, with the
    still-forming bar removed. `ts` is bar OPEN time in epoch seconds UTC.
    """
    yf = _import_yf()
    period = period or config.YAHOO_MAX_PERIOD.get(interval, "60d")

    df = yf.Ticker(src_code).history(
        period=period,
        interval=interval,
        auto_adjust=False,   # see module docstring
        actions=False,
    )
    if df is None or df.empty:
        return []

    bar_secs = config.TIMEFRAMES[interval] * 60
    now_s = int(time.time())

    out: list[tuple] = []
    for idx, row in df.iterrows():
        # yfinance indexes by bar open time; tz-aware for intraday, naive-UTC
        # for daily on some tickers. Normalise both to epoch seconds.
        py_dt = idx.to_pydatetime()
        if py_dt.tzinfo is None:
            py_dt = py_dt.replace(tzinfo=timezone.utc)
        ts = int(py_dt.timestamp())

        # Skip the bar that has not closed yet.
        if ts + bar_secs > now_s:
            continue

        try:
            o, h, low_, c = (
                float(row["Open"]),
                float(row["High"]),
                float(row["Low"]),
                float(row["Close"]),
            )
        except (TypeError, ValueError, KeyError):
            continue
        # Yahoo emits NaN rows on market holidays; NaN != NaN catches them.
        if any(v != v for v in (o, h, low_, c)):
            continue

        vol = row.get("Volume")
        try:
            vol = float(vol)
            if vol != vol or vol <= 0:
                vol = None  # FX and indices carry no real volume
        except (TypeError, ValueError):
            vol = None

        out.append((ts, o, h, low_, c, vol))

    out.sort(key=lambda r: r[0])
    return out


def ingest(
    timeframes: list[str] | None = None,
    assets: list[str] | None = None,
    symbols: list[str] | None = None,
) -> int:
    """Ingest Yahoo-sourced bars. Returns rows written."""
    timeframes = timeframes or ["5m", "15m", "1h", "1d"]
    universe = config.instruments_for(source="yahoo")
    if assets:
        keep = set(assets)
        universe = [i for i in universe if i.asset in keep]
    if symbols:
        wanted = {s.upper() for s in symbols}
        universe = [i for i in universe if i.symbol in wanted]

    db.init_db()
    total = 0
    failures: list[str] = []

    for inst in universe:
        for tf in timeframes:
            try:
                recs = fetch_bars(inst.src_code, tf)
            except Exception as exc:  # noqa: BLE001
                failures.append(f"{inst.symbol}/{tf}")
                print(f"  {inst.symbol:8s} {tf:4s} FAILED  {type(exc).__name__}: {exc}")
                continue

            if not recs:
                print(f"  {inst.symbol:8s} {tf:4s}      0 bars  (no data returned)")
                continue

            rows = [(inst.symbol, tf, *r) for r in recs]
            n = db.upsert_candles(rows)
            total += n
            first = timeutil.iso_date(recs[0][0])
            last = timeutil.iso_date(recs[-1][0])
            print(f"  {inst.symbol:8s} {tf:4s} {n:6d} bars  {first} -> {last}")
            time.sleep(0.25)  # considerate pacing on a free endpoint

    if failures:
        print(f"\n  {len(failures)} request(s) failed: {', '.join(failures)}")
    return total
