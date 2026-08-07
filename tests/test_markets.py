"""Tests for Markets mode.

The most important tests here are the two controls on the evaluation harness.

A backtest that reports "no edge" is worthless unless you have shown it is
capable of reporting an edge. So we feed it two synthetic series:

  * a POSITIVE control with a deliberately leaked, genuinely predictive signal -
    the harness must find a large edge. If it does not, the harness is broken and
    every "no edge" verdict it has ever produced is meaningless.

  * a NEGATIVE control that is a pure random walk with no structure at all - the
    harness must land near 50% and must NOT declare an edge. If it does, it is
    leaking the future somewhere.

Together they bracket the real result: the harness can see signal when it exists,
and does not hallucinate signal when it does not.
"""

from __future__ import annotations

import json
import math
import sqlite3

import numpy as np
import pytest

from markets_model import config, db, evaluate, features, paper, report, timeutil
from markets_model.ingest import crypto


# --- helpers ---------------------------------------------------------------

def _rows_from_closes(closes, start_ts: int = 1_600_000_000, step: int = 3600):
    """Wrap a close series in candle-shaped sqlite3.Row objects."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE c (symbol TEXT, timeframe TEXT, ts INT, open REAL,"
        " high REAL, low REAL, close REAL, volume REAL)"
    )
    prev = closes[0]
    for i, c in enumerate(closes):
        conn.execute(
            "INSERT INTO c VALUES ('T','1h',?,?,?,?,?,?)",
            (
                start_ts + i * step,
                prev,
                max(prev, c) * 1.0005,
                min(prev, c) * 0.9995,
                c,
                1000.0,
            ),
        )
        prev = c
    return conn.execute("SELECT * FROM c ORDER BY ts").fetchall()


def _random_walk(n: int, seed: int = 7, vol: float = 0.004):
    rng = np.random.default_rng(seed)
    steps = rng.normal(0.0, vol, size=n)
    return list(100.0 * np.exp(np.cumsum(steps)))


# --- timeutil: the Windows pre-1970 bug ------------------------------------

def test_utc_from_epoch_handles_pre_1970():
    """S&P 500 history starts in 1927, so negative epochs must not raise.

    datetime.fromtimestamp() raises OSError on Windows for these values; this is
    the regression guard for that.
    """
    dt = timeutil.utc_from_epoch(-1_325_376_000)  # 1928-01-01
    assert dt.year == 1928
    assert timeutil.iso_date(-1_325_376_000).startswith("1928-")


def test_epoch_roundtrip_pre_1970():
    ts = -1_000_000_000
    assert timeutil.epoch_from_utc(timeutil.utc_from_epoch(ts)) == ts


# --- payoff arithmetic -----------------------------------------------------

def test_breakeven_hit_rate():
    """An 80% payout needs 55.56% accuracy just to break even."""
    assert config.breakeven_hit_rate(0.80) == pytest.approx(1 / 1.8)
    assert config.breakeven_hit_rate(0.80) == pytest.approx(0.5556, abs=1e-4)
    # A 100% payout is the fair coin flip.
    assert config.breakeven_hit_rate(1.0) == pytest.approx(0.5)


def test_wilson_interval_brackets_estimate():
    lo, hi = evaluate.wilson_interval(520, 1000)
    assert lo < 0.52 < hi
    # Smaller samples must give wider intervals.
    lo2, hi2 = evaluate.wilson_interval(52, 100)
    assert (hi2 - lo2) > (hi - lo)


def test_log_loss_of_coin_flip():
    y = np.array([0, 1, 0, 1])
    p = np.full(4, 0.5)
    assert evaluate.log_loss(y, p) == pytest.approx(math.log(2), abs=1e-9)


# --- features: the no-look-ahead contract ----------------------------------

def test_features_are_causal():
    """Feature rows must not change when FUTURE bars are appended.

    This is the strongest available check on look-ahead: build features on a
    prefix, then on the full series, and require the overlapping rows to be
    bit-identical. Any forward-looking calculation breaks this.
    """
    closes = _random_walk(600, seed=3)
    full = _rows_from_closes(closes)
    prefix = _rows_from_closes(closes[:400])

    ts_f, o_f, h_f, l_f, c_f, v_f = features.arrays_from_candles(full)
    ts_p, o_p, h_p, l_p, c_p, v_p = features.arrays_from_candles(prefix)

    X_full, idx_full = features.build_matrix(ts_f, o_f, h_f, l_f, c_f, v_f)
    X_pre, idx_pre = features.build_matrix(ts_p, o_p, h_p, l_p, c_p, v_p)

    n = len(idx_pre)
    assert n > 100, "need a meaningful overlap to test"
    assert list(idx_pre) == list(idx_full[:n])
    np.testing.assert_allclose(X_pre, X_full[:n], rtol=0, atol=0)


def test_dataset_target_alignment():
    """y[k] must describe close[idx[k] + horizon] vs close[idx[k]]."""
    closes = _random_walk(500, seed=11)
    rows = _rows_from_closes(closes)
    horizon = 3
    X, y, idx, _ts, close = features.build_dataset(rows, horizon=horizon)

    assert X.shape[0] == y.size == idx.size
    for k in range(0, idx.size, 37):  # spot-check a spread of rows
        i = int(idx[k])
        assert y[k] == (1 if close[i + horizon] > close[i] else 0)


def test_dataset_drops_unsettled_tail():
    """No row may reference a bar beyond the end of the series."""
    closes = _random_walk(400, seed=5)
    rows = _rows_from_closes(closes)
    horizon = 4
    _X, _y, idx, _ts, close = features.build_dataset(rows, horizon=horizon)
    assert idx.size > 0
    assert int(idx.max()) + horizon < close.size


# --- the two controls on the harness ---------------------------------------

def test_harness_detects_a_real_edge(monkeypatch):
    """POSITIVE CONTROL: with genuine signal, the harness must find the edge.

    We build a series whose next move is strongly determined by the last move
    (alternating), which `ret_1` captures directly. A working harness should
    report a hit rate far above breakeven.

    If this test fails, no "NO EDGE" verdict from this harness can be trusted.
    """
    n = 3000
    rng = np.random.default_rng(19)
    closes = [100.0]
    up = True
    for _ in range(n):
        # Mean-reverting by construction, with a little noise so it is not
        # perfectly separable.
        if rng.random() < 0.9:
            up = not up
        step = 0.004 if up else -0.004
        closes.append(closes[-1] * (1 + step + rng.normal(0, 0.0004)))

    rows = _rows_from_closes(closes)
    monkeypatch.setattr(evaluate.db, "load_candles", lambda *a, **k: rows)

    r = evaluate.walk_forward("T", "1h", horizon=1, n_blocks=5)
    assert r is not None
    assert r.n > 500
    assert r.hit_rate > 0.70, f"harness missed an obvious edge (hit={r.hit_rate:.3f})"
    assert r.beats_base_rate
    assert r.profitable_at_payout
    assert "EDGE" in r.verdict()


def test_harness_finds_no_edge_in_a_random_walk(monkeypatch):
    """NEGATIVE CONTROL: on a pure random walk there is nothing to find.

    A hit rate materially above 50% here would mean the harness is leaking
    future information, since the series has no exploitable structure at all.
    """
    closes = _random_walk(6000, seed=23)
    rows = _rows_from_closes(closes)
    monkeypatch.setattr(evaluate.db, "load_candles", lambda *a, **k: rows)

    r = evaluate.walk_forward("T", "1h", horizon=1, n_blocks=8)
    assert r is not None
    assert r.n > 1000
    assert 0.45 < r.hit_rate < 0.55, f"suspicious hit rate {r.hit_rate:.3f} on noise"
    assert not r.profitable_at_payout
    assert r.ev_per_trade < 0


def test_verdict_requires_minimum_sample():
    """A tiny sample must never be reported as an edge, however good it looks."""
    r = evaluate.EvalResult(
        symbol="T", timeframe="1h", horizon=1, model="logreg-h1",
        n=50, base_rate=0.5, hit_rate=0.90, hit_ci=(0.80, 0.96),
        model_log_loss=0.30, base_log_loss=0.69, brier_score=0.10,
        payout=0.80, breakeven=config.breakeven_hit_rate(0.80),
        ev_per_trade=0.62,
    )
    assert not r.enough_data
    assert not r.profitable_at_payout
    assert "INSUFFICIENT DATA" in r.verdict()


def test_calibration_bins_sum_to_sample():
    y = np.array([0, 1] * 200)
    p = np.linspace(0.05, 0.95, 400)
    bins = evaluate.calibration_bins(y, p, n_bins=10)
    assert sum(b["n"] for b in bins) == y.size


# --- the Coinbase fallback -------------------------------------------------
# Binance geo-blocks US IPs, so the scheduled cloud job falls back to Coinbase.
# Coinbase orders its candles [time, LOW, HIGH, OPEN, close, volume] — low and
# high before open — which is unlike every other source here. Getting it wrong
# yields bars that still look plausible while corrupting every range-based
# feature, so the reordering is pinned down here.

def test_coinbase_candle_column_order():
    # time, low, high, open, close, volume  (Coinbase's order)
    candle = [1785970800, 100.0, 110.0, 105.0, 108.0, 42.5]
    symbol, tf, ts, open_, high, low, close, vol = crypto._parse_cb_candle(
        "BTCUSDT", "1h", candle
    )
    assert (symbol, tf, ts) == ("BTCUSDT", "1h", 1785970800)
    assert open_ == 105.0
    assert high == 110.0
    assert low == 100.0
    assert close == 108.0
    assert vol == 42.5
    # The invariant that catches a swap: high bounds everything, low floors it.
    assert high >= max(open_, close, low)
    assert low <= min(open_, close, high)


def test_coinbase_product_mapping():
    """Our USDT symbols map to Coinbase's USD products."""
    assert crypto._cb_product("BTCUSDT") == "BTC-USD"
    assert crypto._cb_product("DOGEUSDT") == "DOGE-USD"
    # A symbol that isn't USDT-quoted passes through with -USD appended.
    assert crypto._cb_product("BTC") == "BTC-USD"


def test_coinbase_covers_every_reported_timeframe():
    """Every timeframe the app reports must be servable by the fallback.

    Otherwise a US-hosted cloud run would silently publish crypto with gaps at
    whichever horizons Coinbase cannot provide.
    """
    for tf in report.REPORT_TIMEFRAMES:
        assert tf in crypto._CB_GRANULARITY, f"Coinbase cannot serve {tf}"
        assert crypto._CB_GRANULARITY[tf] == config.TIMEFRAMES[tf] * 60


# --- paper trading (the forward test) --------------------------------------

def _pred(p_up: float, up: bool, tf: str = "1h") -> dict:
    return {"p_up": p_up, "actual_up": up, "timeframe": tf, "symbol": "X",
            "made_at_ts": 0}


def test_paper_scores_the_side_the_model_leaned():
    """Correct = the leaned side matched, whichever side that was.

    A DOWN call that comes off is a win. Scoring only 'up' calls would flatter
    or punish the model arbitrarily depending on market drift.
    """
    rows = [
        _pred(0.60, True),    # leaned up, went up   -> win
        _pred(0.40, False),   # leaned down, went down -> win
        _pred(0.60, False),   # leaned up, went down -> loss
        _pred(0.40, True),    # leaned down, went up -> loss
    ]
    s = paper.summarise_predictions(rows, 0.80)
    assert s["n"] == 4
    assert s["wins"] == 2
    assert s["hit"] == 0.5


def test_paper_ev_matches_the_payout_math():
    rows = [_pred(0.6, True)] * 60 + [_pred(0.6, False)] * 40  # 60% hit
    s = paper.summarise_predictions(rows, 0.80)
    assert s["hit"] == pytest.approx(0.60)
    assert s["ev"] == pytest.approx(0.60 * 0.80 - 0.40)


def test_paper_refuses_to_claim_an_edge_on_a_small_sample():
    """10 wins from 10 is not evidence, however good it looks."""
    s = paper.summarise_predictions([_pred(0.9, True)] * 10, 0.80)
    assert s["hit"] == 1.0
    assert s["enough"] is False
    assert s["clears_breakeven"] is False


def test_paper_uses_lower_bound_not_point_estimate():
    """A 56% point estimate whose interval dips below breakeven is not an edge."""
    n, wins = 600, 336  # 56.0%, comfortably above the 55.56% point threshold
    rows = [_pred(0.6, True)] * wins + [_pred(0.6, False)] * (n - wins)
    s = paper.summarise_predictions(rows, 0.80)
    assert s["hit"] > config.breakeven_hit_rate(0.80)   # point estimate clears
    assert s["ci"][0] < config.breakeven_hit_rate(0.80)  # but the low end doesn't
    assert s["clears_breakeven"] is False


def test_settlement_is_one_bar_after_the_target_bar_opens():
    """`target_ts` is the settling bar's OPEN; the outcome lands at its CLOSE.

    Treating target_ts itself as the deadline declares a forecast finished a
    whole bar early — it discarded every 1h forecast made during the current
    hour, and would have thrown away a full day on the 1d horizon.
    """
    target = 1_785_970_800
    assert paper.settles_at(target, "1h") == target + 3600
    assert paper.settles_at(target, "5m") == target + 300
    assert paper.settles_at(target, "1d") == target + 86400

    # The concrete case that exposed it: the settling bar OPENS at target and
    # closes an hour later, so 19 minutes in, the outcome is still unknown.
    now = target + 1140
    assert paper.settles_at(target, "1h") > now, "must still be pending"
    assert target <= now, "the naive check would wrongly call this closed"

    # And once that bar has closed, it really is due.
    assert paper.settles_at(target, "1h") <= target + 3600


def test_snapshot_exposes_settles_at_one_bar_past_target(temp_db):
    """The app needs the settle time, not just the target bar's open time."""
    data = report.build_data(timeframes=["1h"])
    h = data["instruments"][0]["horizons"]["1h"]
    assert h["settles_at"] == h["target"] + 3600
    assert h["target"] == h["cutoff"] + 3600


def test_paper_store_unavailable_is_not_systemexit():
    """report.py guards with `except Exception`; SystemExit would slip past it.

    If this regresses, a missing paper table takes the whole nightly snapshot
    down instead of degrading to "no live record yet".
    """
    assert issubclass(paper.PaperStoreUnavailable, Exception)
    assert not issubclass(paper.PaperStoreUnavailable, SystemExit)


def test_snapshot_survives_an_unavailable_paper_store(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_KEY", raising=False)
    assert report._safe_live_record(0.80) is None


# --- the snapshot contract with the Flutter app ----------------------------

@pytest.fixture()
def temp_db(tmp_path, monkeypatch):
    """Point the package at a throwaway database seeded with one instrument."""
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "markets.db")
    db.init_db()

    closes = _random_walk(700, seed=31)
    rows = []
    ts = 1_700_000_000
    prev = closes[0]
    for i, c in enumerate(closes):
        rows.append(
            ("BTCUSDT", "1h", ts + i * 3600, prev, max(prev, c) * 1.001,
             min(prev, c) * 0.999, c, 100.0)
        )
        prev = c
    db.upsert_candles(rows)
    return tmp_path


def test_snapshot_shape_and_json_roundtrip(temp_db):
    """build_data must produce exactly what the app reads, and survive JSON.

    The Flutter side indexes into these keys directly, so a rename here is a
    silent runtime crash there. This test is the contract.
    """
    data = report.build_data(timeframes=["1h"])

    for key in (
        "generated", "payout", "breakeven", "min_sample",
        "timeframes", "asset_classes", "instruments", "summary",
    ):
        assert key in data, f"snapshot missing '{key}'"

    assert data["breakeven"] == pytest.approx(config.breakeven_hit_rate(0.80))

    inst = next(i for i in data["instruments"] if i["symbol"] == "BTCUSDT")
    for key in ("symbol", "name", "asset", "last", "change", "spark", "horizons"):
        assert key in inst

    h = inst["horizons"]["1h"]
    for key in ("p_up", "ref_close", "cutoff", "target", "drivers", "track"):
        assert key in h
    assert 0.0 < h["p_up"] < 1.0
    # The settlement bar must be exactly one bar after the information cutoff.
    assert h["target"] - h["cutoff"] == 3600

    # Must survive the trip to Supabase and back.
    assert json.loads(json.dumps(data))["summary"] == data["summary"]


def test_snapshot_reports_no_track_record_when_unevaluated(temp_db):
    """With no eval_runs rows, `track` must be null - never a fabricated number."""
    data = report.build_data(timeframes=["1h"])
    inst = next(i for i in data["instruments"] if i["symbol"] == "BTCUSDT")
    assert inst["horizons"]["1h"]["track"] is None
    assert data["summary"]["measured"] == 0
    assert data["summary"]["cleared_breakeven"] == 0


def test_snapshot_track_record_flags_below_breakeven(temp_db):
    """A saved 52% hit rate must be reported as NOT clearing breakeven."""
    r = evaluate.EvalResult(
        symbol="BTCUSDT", timeframe="1h", horizon=1, model="logreg-h1",
        n=4000, base_rate=0.5, hit_rate=0.52, hit_ci=(0.505, 0.535),
        model_log_loss=0.6925, base_log_loss=0.6931, brier_score=0.2498,
        payout=0.80, breakeven=config.breakeven_hit_rate(0.80),
        ev_per_trade=0.52 * 0.8 - 0.48,
    )
    evaluate.save_result(r)

    data = report.build_data(timeframes=["1h"])
    track = data["instruments"][0]["horizons"]["1h"]["track"]
    assert track is not None
    assert track["enough"] is True
    assert track["clears_breakeven"] is False, "52% must never read as profitable"
    assert track["ev"] < 0
    assert data["summary"]["cleared_breakeven"] == 0
