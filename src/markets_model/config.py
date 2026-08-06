"""Central configuration for Markets mode: instruments, horizons, payouts.

Deliberately mirrors sports_model/config.py - same single-source-of-truth idea,
same shape - so the two modes stay easy to reason about side by side.

The database is SEPARATE (data/markets.db). Sports and Markets share the app
shell and the evaluation philosophy, not their storage.
"""

from __future__ import annotations

import os
from pathlib import Path

# config.py -> markets_model -> src -> project root
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
DB_PATH = DATA_DIR / "markets.db"

try:
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass


# --- Optional API keys -----------------------------------------------------
# Everything in the default instrument set works with NO key at all. These are
# read by nothing yet - they are here for a future higher-quality intraday
# source (OANDA gives true dealable FX bars; Yahoo's FX intraday is indicative).


def oanda_api_key() -> str | None:
    """OANDA v20 practice/live token - optional, for intraday FX bars."""
    return os.environ.get("OANDA_API_KEY")


def oanda_account_id() -> str | None:
    return os.environ.get("OANDA_ACCOUNT_ID")


def twelvedata_api_key() -> str | None:
    """Twelve Data key - optional alternative source for intraday non-crypto."""
    return os.environ.get("TWELVEDATA_API_KEY")


# --- Asset classes ---------------------------------------------------------
# These are the tab groups in the app's Markets mode.
ASSET_CLASSES: dict[str, str] = {
    "crypto": "Crypto",
    "fx": "Forex",
    "equity": "Stocks",
    "index": "Indices",
    "commodity": "Commodities",
}


class Instrument:
    """One tradable thing we model.

    symbol    our canonical id, e.g. 'BTCUSDT', 'EURUSD', 'AAPL'
    name      display name
    asset     key into ASSET_CLASSES
    source    which ingest module owns it ('binance' | 'yahoo')
    src_code  the symbol as that source spells it
    """

    __slots__ = ("symbol", "name", "asset", "source", "src_code")

    def __init__(self, symbol: str, name: str, asset: str, source: str, src_code: str):
        self.symbol = symbol
        self.name = name
        self.asset = asset
        self.source = source
        self.src_code = src_code

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Instrument({self.symbol!r}, {self.asset!r}, {self.source!r})"


# Crypto via Binance's public REST API: no key, no rate-limit signup, and 1-minute
# bars going back years. This is the ONLY asset class where we get free
# intraday history deep enough to honestly test 1m-1h horizons - which is also
# what fixed-time platforms push hardest. So crypto is our primary test bed.
_CRYPTO = [
    Instrument("BTCUSDT", "Bitcoin", "crypto", "binance", "BTCUSDT"),
    Instrument("ETHUSDT", "Ethereum", "crypto", "binance", "ETHUSDT"),
    Instrument("SOLUSDT", "Solana", "crypto", "binance", "SOLUSDT"),
    Instrument("XRPUSDT", "XRP", "crypto", "binance", "XRPUSDT"),
    Instrument("BNBUSDT", "BNB", "crypto", "binance", "BNBUSDT"),
    Instrument("ADAUSDT", "Cardano", "crypto", "binance", "ADAUSDT"),
    Instrument("DOGEUSDT", "Dogecoin", "crypto", "binance", "DOGEUSDT"),
]

# Everything non-crypto comes from Yahoo Finance via the `yfinance` package:
# one source covering FX, stocks, indices and commodities, no API key.
#
# (An earlier draft used Stooq's CSV endpoint. Stooq now gates automated access
# behind a JavaScript proof-of-work challenge, so it is no longer usable here.)
#
# Yahoo's history depth varies by interval - see YAHOO_MAX_PERIOD. It is deep
# enough to evaluate every horizon we offer, which is the requirement.
_FX = [
    Instrument("EURUSD", "EUR/USD", "fx", "yahoo", "EURUSD=X"),
    Instrument("GBPUSD", "GBP/USD", "fx", "yahoo", "GBPUSD=X"),
    Instrument("USDJPY", "USD/JPY", "fx", "yahoo", "USDJPY=X"),
    Instrument("USDCHF", "USD/CHF", "fx", "yahoo", "USDCHF=X"),
    Instrument("AUDUSD", "AUD/USD", "fx", "yahoo", "AUDUSD=X"),
    Instrument("USDCAD", "USD/CAD", "fx", "yahoo", "USDCAD=X"),
    Instrument("NZDUSD", "NZD/USD", "fx", "yahoo", "NZDUSD=X"),
]

_EQUITY = [
    Instrument("AAPL", "Apple", "equity", "yahoo", "AAPL"),
    Instrument("MSFT", "Microsoft", "equity", "yahoo", "MSFT"),
    Instrument("NVDA", "NVIDIA", "equity", "yahoo", "NVDA"),
    Instrument("AMZN", "Amazon", "equity", "yahoo", "AMZN"),
    Instrument("GOOGL", "Alphabet", "equity", "yahoo", "GOOGL"),
    Instrument("TSLA", "Tesla", "equity", "yahoo", "TSLA"),
    Instrument("META", "Meta", "equity", "yahoo", "META"),
]

_INDEX = [
    Instrument("SPX", "S&P 500", "index", "yahoo", "^GSPC"),
    Instrument("NDX", "Nasdaq 100", "index", "yahoo", "^NDX"),
    Instrument("DJI", "Dow Jones 30", "index", "yahoo", "^DJI"),
    Instrument("DAX", "DAX 40", "index", "yahoo", "^GDAXI"),
    Instrument("UKX", "FTSE 100", "index", "yahoo", "^FTSE"),
    Instrument("NKX", "Nikkei 225", "index", "yahoo", "^N225"),
]

_COMMODITY = [
    Instrument("XAUUSD", "Gold", "commodity", "yahoo", "GC=F"),
    Instrument("XAGUSD", "Silver", "commodity", "yahoo", "SI=F"),
    Instrument("WTI", "Crude Oil (WTI)", "commodity", "yahoo", "CL=F"),
    Instrument("BRENT", "Crude Oil (Brent)", "commodity", "yahoo", "BZ=F"),
    Instrument("NATGAS", "Natural Gas", "commodity", "yahoo", "NG=F"),
    Instrument("COPPER", "Copper", "commodity", "yahoo", "HG=F"),
]

INSTRUMENTS: list[Instrument] = [*_CRYPTO, *_FX, *_EQUITY, *_INDEX, *_COMMODITY]

BY_SYMBOL: dict[str, Instrument] = {i.symbol: i for i in INSTRUMENTS}


def instruments_for(asset: str | None = None, source: str | None = None) -> list[Instrument]:
    """Filter the instrument universe by asset class and/or source."""
    out = INSTRUMENTS
    if asset:
        out = [i for i in out if i.asset == asset]
    if source:
        out = [i for i in out if i.source == source]
    return list(out)


# --- Timeframes ------------------------------------------------------------
# Canonical bar intervals. Values are the Binance interval strings; minutes are
# what everything else keys off.
TIMEFRAMES: dict[str, int] = {
    "1m": 1,
    "5m": 5,
    "15m": 15,
    "1h": 60,
    "4h": 240,
    "1d": 1440,
}

# How far back Yahoo will serve each interval. These are hard limits imposed by
# the upstream API, measured against it rather than assumed, and they decide
# which horizons we can honestly evaluate for non-crypto assets.
#
# Observed bar counts for EUR/USD at each limit:
#   1m   7d    ~8,600 bars    thin - a weak measurement, flag it as such
#   5m   60d  ~16,800 bars    solid
#   15m  60d   ~5,600 bars    solid
#   1h   730d ~17,200 bars    solid
#   1d   max   ~5,900 bars    ~23 years
YAHOO_MAX_PERIOD: dict[str, str] = {
    "1m": "7d",
    "5m": "60d",
    "15m": "60d",
    "1h": "730d",
    "1d": "max",
}

# Below this many out-of-sample predictions we refuse to publish a hit rate:
# the confidence interval is so wide the number would mislead. At n=500 the 95%
# interval on a ~50% rate is roughly +/-4.4pp, which is already wide enough that
# the honest read is "indistinguishable from a coin flip".
MIN_SAMPLE_FOR_CLAIM = 500

# The horizons fixed-time platforms actually offer, expressed in BARS of the
# matching timeframe. A "5m" prediction = direction of the next 1 bar of 5m data.
# We predict at bar close and settle at the close N bars later - an unambiguous
# information boundary, the same role kickoff time plays in the sports model.
PREDICTION_HORIZONS: dict[str, tuple[str, int]] = {
    "1m": ("1m", 1),
    "5m": ("5m", 1),
    "15m": ("15m", 1),
    "1h": ("1h", 1),
    "4h": ("4h", 1),
    "1d": ("1d", 1),
}


# --- Payoff assumptions ----------------------------------------------------
# Typical fixed-time payout on a winning trade: stake back + 80%. Losing trades
# return nothing. Equivalent decimal odds = 1 + payout.
#
# Breakeven hit rate = 1 / (1 + payout). At 0.80 that is 55.56%.
#
# This constant exists so the app can show a user the hit rate they ACTUALLY
# need, next to the hit rate the model ACTUALLY achieves. That comparison is
# the single most useful number in Markets mode.
DEFAULT_FIXED_PAYOUT = 0.80

# Round-trip spot cost as a fraction of notional, used when evaluating spot-style
# (non-binary) execution. ~1 pip on a major = 0.0001 / 1.10 ~= 0.9bp; we use a
# deliberately conservative 2bp so a "profitable" backtest has to clear a real bar.
DEFAULT_SPOT_COST = 0.0002


def breakeven_hit_rate(payout: float = DEFAULT_FIXED_PAYOUT) -> float:
    """Win rate needed to break even on a fixed-payout binary trade.

    payout=0.80 -> 0.5556. Anything the model achieves below this LOSES money,
    no matter how confident it looks.
    """
    return 1.0 / (1.0 + payout)


def ensure_dirs() -> None:
    for d in (DATA_DIR, RAW_DIR, PROCESSED_DIR):
        d.mkdir(parents=True, exist_ok=True)
