"""Refresh just the price fields in the published snapshot.

WHY THE CLOUD RELAYS PRICES INSTEAD OF THE APP FETCHING THEM

The obvious way to show live prices is to have the app call an exchange API
directly. Measured against the network this app is actually used on, that fails:
api.binance.com, data-api.binance.vision, api.exchange.coinbase.com,
api.coinbase.com and api.kraken.com all fail DNS resolution, while Yahoo,
GitHub and Supabase resolve normally. Selective ISP-level blocking of crypto
exchanges - intermittent, but real.

So the data path is: GitHub runner (reaches the exchanges) -> Supabase (reaches
everyone) -> app. The app never talks to an exchange, which also means it needs
no keys, no CORS exemptions, and keeps working on a filtered connection.

This module is the cheap half of that. A full `push` rebuilds every model and
takes minutes; refreshing prices only needs the newest bars, so it reads them
from the local database and patches `last`, `change` and `spark` into the
existing snapshot row, leaving predictions and track records untouched.

Deliberately does NOT touch p_up or anything under `horizons`: a fresher price
must never be mistaken for a fresher forecast. The app's staleness guard still
reports the forecast window as closed even while the price ticks.
"""

from __future__ import annotations

import json
import os

import requests

from . import config, db, report

_TIMEOUT = 60


class SnapshotUnavailable(RuntimeError):
    """No snapshot row to patch, or no credentials to reach it."""


def _creds() -> tuple[str, str]:
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not url or not key:
        raise SnapshotUnavailable(
            "Set SUPABASE_URL and SUPABASE_SERVICE_KEY in .env first."
        )
    return url.rstrip("/"), key


def collect(timeframes: list[str] | None = None) -> dict[str, dict]:
    """Latest price context per instrument, from whatever is in the database.

    Uses the finest timeframe available for each instrument, matching how
    report.build_data picks one, so the app sees a consistent basis whichever
    job wrote last.
    """
    timeframes = timeframes or report.REPORT_TIMEFRAMES
    out: dict[str, dict] = {}

    for inst in config.INSTRUMENTS:
        for tf in timeframes:
            bars = db.load_candles(inst.symbol, tf, limit=report.SPARK_POINTS)
            if len(bars) < 2:
                continue
            closes = [float(b["close"]) for b in bars]
            out[inst.symbol] = {
                "last": closes[-1],
                "change": (closes[-1] / closes[0] - 1.0) if closes[0] > 0 else 0.0,
                "change_tf": tf,
                "spark": closes,
                # Bar open time of the newest bar, so the app can say how fresh
                # this price actually is rather than implying "now".
                "as_of": int(bars[-1]["ts"]),
            }
            break  # finest timeframe wins

    return out


def publish(prices: dict[str, dict] | None = None) -> int:
    """Patch price fields into the snapshot row. Returns instruments updated."""
    url, key = _creds()
    prices = prices if prices is not None else collect()
    if not prices:
        print("  no prices to publish (nothing ingested).")
        return 0

    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }

    resp = requests.get(
        f"{url}/rest/v1/snapshot",
        headers=headers,
        params={"select": "data", "id": "eq.markets"},
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    rows = resp.json()
    if not rows:
        raise SnapshotUnavailable(
            "No markets snapshot to patch — run `push` first."
        )

    data = rows[0]["data"]
    updated = 0
    for inst in data.get("instruments", []):
        p = prices.get(inst["symbol"])
        if not p:
            continue
        inst["last"] = p["last"]
        inst["change"] = p["change"]
        inst["change_tf"] = p["change_tf"]
        inst["spark"] = p["spark"]
        inst["price_as_of"] = p["as_of"]
        updated += 1

    # Top-level stamp so the app can show price freshness separately from the
    # snapshot build time — they are now different things.
    data["prices_updated"] = max(p["as_of"] for p in prices.values())

    patch = requests.patch(
        f"{url}/rest/v1/snapshot",
        headers={**headers, "Prefer": "return=minimal"},
        params={"id": "eq.markets"},
        data=json.dumps({"data": data, "updated_at": "now()"}),
        timeout=_TIMEOUT,
    )
    patch.raise_for_status()
    print(f"  refreshed prices for {updated} instrument(s).")
    return updated
