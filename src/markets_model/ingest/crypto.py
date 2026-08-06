"""Crypto OHLCV, from Binance where reachable and Coinbase where it is not.

Why crypto matters here: it is the only asset class with free intraday history
deep enough to honestly test the 1m-1h horizons fixed-time platforms are built
on, and it trades 24/7 so there are no session gaps to reason about.

TWO SOURCES, ON PURPOSE. Binance is preferred - deeper history, 1000 bars per
request, and USDT pairs that match how these instruments are actually quoted on
the platforms we are modelling. But Binance geo-blocks US IP addresses, and
GitHub Actions runners are US-hosted, so the scheduled cloud refresh cannot
reach it. Without a fallback the nightly job would rebuild the snapshot with no
crypto at all and quietly drop the whole asset class from the app.

Coinbase Exchange is the fallback: keyless, US-available, and it lists all seven
of our pairs. It quotes against USD rather than USDT, which is a real but
immaterial difference here - the two track each other to within a few basis
points, and we are predicting direction, not price. Bars from the two sources
can interleave in one series; at this granularity that is noise, not a defect.

If neither is reachable, ingestion says so rather than silently storing nothing.
"""

from __future__ import annotations

import time

import requests

from .. import config, db

# Market-data-only host first, then the main API.
_HOSTS = [
    "https://data-api.binance.vision",
    "https://api.binance.com",
]

_MAX_LIMIT = 1000  # bars per request (Binance cap)
_TIMEOUT = 20

# --- Coinbase fallback -----------------------------------------------------
_CB_URL = "https://api.exchange.coinbase.com"
_CB_MAX = 300  # candles per request (Coinbase cap)

# Bar length in seconds, as Coinbase's `granularity` parameter. It accepts only
# this fixed set, which covers every timeframe we report on. 4h has no Coinbase
# equivalent (it offers 6h) and is skipped rather than silently substituted.
_CB_GRANULARITY = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "1h": 3600,
    "1d": 86400,
}


def _cb_product(symbol: str) -> str:
    """'BTCUSDT' -> 'BTC-USD'. Coinbase quotes in USD, not USDT."""
    base = symbol[:-4] if symbol.endswith("USDT") else symbol
    return f"{base}-USD"


def _parse_cb_candle(symbol: str, interval: str, c: list) -> tuple:
    """One Coinbase candle -> our (symbol, tf, ts, open, high, low, close, vol).

    Coinbase returns [time, LOW, HIGH, OPEN, close, volume] - low and high come
    BEFORE open, which is not the order any other source here uses. Mixing them
    up produces bars that still look plausible (prices are all in range) while
    quietly corrupting every range- and body-based feature, so this reordering
    is isolated in one tested function rather than inlined in the fetch loop.
    """
    ts, low, high, open_, close, vol = (
        int(c[0]), float(c[1]), float(c[2]), float(c[3]), float(c[4]), float(c[5]),
    )
    return (symbol, interval, ts, open_, high, low, close, vol)


def _get_klines(
    host: str,
    symbol: str,
    interval: str,
    start_ms: int,
    limit: int = _MAX_LIMIT,
) -> list[list]:
    """One raw /klines call. Raises on HTTP error."""
    resp = requests.get(
        f"{host}/api/v3/klines",
        params={
            "symbol": symbol,
            "interval": interval,
            "startTime": start_ms,
            "limit": limit,
        },
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


def _pick_host(symbol: str, interval: str) -> str | None:
    """Return the first host that answers, or None if all are unreachable."""
    probe_start = int((time.time() - 3600) * 1000)
    for host in _HOSTS:
        try:
            _get_klines(host, symbol, interval, probe_start, limit=1)
            return host
        except Exception:  # noqa: BLE001 - any failure means try the next host
            continue
    return None


def fetch_klines(symbol: str, interval: str, bars: int) -> list[tuple]:
    """Fetch approximately the last `bars` closed bars for one symbol.

    Returns rows shaped for db.upsert_candles. Walks FORWARD from an estimated
    start time in pages of 1000, which is the pagination style Binance supports
    cleanly.

    The final (still-forming) bar is dropped - a bar that has not closed yet has
    no settled close, and including it is the most common way an intraday
    backtest quietly acquires look-ahead.
    """
    minutes = config.TIMEFRAMES[interval]
    host = _pick_host(symbol, interval)
    if host is None:
        raise RuntimeError(
            "Binance unreachable from this network (tried "
            + ", ".join(_HOSTS)
            + "). Crypto ingestion needs one of these hosts."
        )

    now_ms = int(time.time() * 1000)
    span_ms = bars * minutes * 60 * 1000
    start_ms = now_ms - span_ms

    rows: list[tuple] = []
    seen: set[int] = set()

    while start_ms < now_ms:
        try:
            batch = _get_klines(host, symbol, interval, start_ms)
        except Exception as exc:  # noqa: BLE001
            # Partial data is still useful; report and stop paging.
            print(f"    ! {symbol} {interval}: stopped early ({exc})")
            break
        if not batch:
            break

        for k in batch:
            open_ms = int(k[0])
            if open_ms in seen:
                continue
            seen.add(open_ms)
            rows.append(
                (
                    symbol,
                    interval,
                    open_ms // 1000,
                    float(k[1]),
                    float(k[2]),
                    float(k[3]),
                    float(k[4]),
                    float(k[5]),
                )
            )

        last_open_ms = int(batch[-1][0])
        next_start = last_open_ms + minutes * 60 * 1000
        if next_start <= start_ms:
            break  # no forward progress - bail rather than spin
        start_ms = next_start

        if len(batch) < _MAX_LIMIT:
            break  # caught up to the present

        time.sleep(0.12)  # stay well inside the public rate limit

    # Drop the bar still in progress.
    bar_secs = minutes * 60
    now_s = int(time.time())
    rows = [r for r in rows if r[2] + bar_secs <= now_s]
    rows.sort(key=lambda r: r[2])
    return rows


def fetch_coinbase(symbol: str, interval: str, bars: int) -> list[tuple]:
    """Fetch ~`bars` closed bars for one symbol from Coinbase Exchange.

    Same return shape as fetch_klines. Coinbase caps a response at 300 candles
    and returns them newest-first, so we walk forward in windows and sort at the
    end.
    """
    gran = _CB_GRANULARITY.get(interval)
    if gran is None:
        raise ValueError(f"Coinbase has no {interval} granularity")

    product = _cb_product(symbol)
    now = int(time.time())
    start = now - bars * gran

    rows: list[tuple] = []
    seen: set[int] = set()
    headers = {"User-Agent": "markets-model/0.1 (+local research)"}

    while start < now:
        end = min(start + _CB_MAX * gran, now)
        try:
            resp = requests.get(
                f"{_CB_URL}/products/{product}/candles",
                params={"granularity": gran, "start": start, "end": end},
                headers=headers,
                timeout=_TIMEOUT,
            )
            resp.raise_for_status()
            batch = resp.json()
        except Exception as exc:  # noqa: BLE001
            print(f"    ! {symbol} {interval}: stopped early ({exc})")
            break

        for c in batch:
            row = _parse_cb_candle(symbol, interval, c)
            if row[2] in seen:
                continue
            seen.add(row[2])
            rows.append(row)

        start = end
        time.sleep(0.15)  # public endpoint: stay well under the rate limit

    # Drop the bar still forming.
    now_s = int(time.time())
    rows = [r for r in rows if r[2] + gran <= now_s]
    rows.sort(key=lambda r: r[2])
    return rows


def ingest(
    timeframes: list[str] | None = None,
    bars: int = 5000,
    symbols: list[str] | None = None,
) -> int:
    """Ingest crypto bars for the configured timeframes. Returns rows written.

    Picks the source ONCE up front rather than per symbol: whether Binance is
    reachable is a property of the network, not of any one pair, and probing 28
    times to learn the same answer would just be slow.
    """
    timeframes = timeframes or ["1m", "5m", "15m", "1h", "1d"]
    universe = config.instruments_for(asset="crypto", source="binance")
    if symbols:
        wanted = {s.upper() for s in symbols}
        universe = [i for i in universe if i.symbol in wanted]
    if not universe:
        return 0

    probe = universe[0].src_code
    host = _pick_host(probe, timeframes[0] if timeframes else "1h")
    if host:
        print(f"  source: Binance ({host})")
    else:
        print(
            "  source: Coinbase - Binance unreachable from this network.\n"
            "          (Expected on US IPs, including GitHub Actions runners.)"
        )

    db.init_db()
    total = 0
    failures: list[str] = []

    for inst in universe:
        for tf in timeframes:
            try:
                if host:
                    rows = fetch_klines(inst.src_code, tf, bars)
                    # Store under our canonical symbol. Equal to src_code for
                    # crypto today, but keeping the mapping explicit means a
                    # future rename cannot silently split one series in two.
                    rows = [(inst.symbol, *r[1:]) for r in rows]
                else:
                    rows = fetch_coinbase(inst.symbol, tf, bars)
            except ValueError as exc:
                # Timeframe the fallback cannot serve (e.g. 4h) - say so.
                print(f"  {inst.symbol:10s} {tf:4s} skipped ({exc})")
                continue
            except Exception as exc:  # noqa: BLE001
                failures.append(f"{inst.symbol}/{tf}")
                print(f"  {inst.symbol:10s} {tf:4s} FAILED ({exc})")
                continue

            n = db.upsert_candles(rows)
            total += n
            print(f"  {inst.symbol:10s} {tf:4s} {n:6d} bars")

    if failures:
        print(f"\n  {len(failures)} request(s) failed: {', '.join(failures)}")
    return total
