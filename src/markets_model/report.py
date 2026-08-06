"""Build the Markets snapshot the Flutter app reads.

Mirrors sports_model/report.py in role: gather everything the client needs into
one JSON blob, so the app does no modelling of its own beyond rendering.

The shape is deliberately "prediction + its track record, together". Every
forecast in this payload ships with the measured out-of-sample hit rate for that
exact symbol/timeframe and the hit rate needed to break even at the assumed
payout. The app should never be able to show a confident-looking number without
the evidence about whether that confidence has ever been worth anything.

Track records come from the `eval_runs` table, so `report` is fast and reuses
the honest walk-forward numbers rather than silently recomputing something
weaker. Populate it first:

    python -m markets_model.main eval-all --timeframes 1h 1d --save
    python -m markets_model.main report
"""

from __future__ import annotations

import json
import time

from . import config, db, direction, evaluate, features, timeutil

# Timeframes the app offers. 1m is deliberately excluded: Yahoo only serves 7
# days of it, so we cannot evaluate it honestly for four of the five asset
# classes, and shipping an unevaluated horizon is exactly what this app exists
# not to do.
REPORT_TIMEFRAMES = ["5m", "15m", "1h", "1d"]

# Bars used to fit the live prediction. Capped so a full report stays quick;
# well past the point where more history changes the fit.
FIT_BARS = 6000

SPARK_POINTS = 48


def _latest_eval(symbol: str, timeframe: str, horizon: int = 1) -> dict | None:
    """Most recent saved walk-forward result for this combination."""
    with db.connect() as conn:
        row = conn.execute(
            """
            SELECT * FROM eval_runs
            WHERE symbol = ? AND timeframe = ? AND horizon = ?
            ORDER BY run_ts DESC LIMIT 1
            """,
            (symbol, timeframe, horizon),
        ).fetchone()
    if row is None:
        return None

    n = int(row["n"])
    hit = float(row["hit_rate"])
    wins = round(hit * n)
    lo, hi = evaluate.wilson_interval(wins, n)
    payout = float(row["payout"])
    breakeven = float(row["breakeven"])
    enough = n >= config.MIN_SAMPLE_FOR_CLAIM

    return {
        "n": n,
        "hit": hit,
        "ci": [lo, hi],
        "ev": hit * payout - (1.0 - hit),
        "log_loss": float(row["log_loss"]),
        "base_log_loss": float(row["base_log_loss"]),
        "beats_base": float(row["log_loss"]) < float(row["base_log_loss"]),
        "enough": enough,
        # The one claim that matters: is the LOWER bound above breakeven?
        "clears_breakeven": enough and lo > breakeven,
        "measured_at": int(row["run_ts"]),
    }


def _instrument_block(inst, timeframe: str) -> dict | None:
    """Live prediction + track record for one instrument at one timeframe."""
    candles = db.load_candles(inst.symbol, timeframe, limit=FIT_BARS)
    if len(candles) < features.WARMUP + 250:
        return None

    X, y, _idx, _ts, _close = features.build_dataset(candles, horizon=1)
    if X.shape[0] < 250:
        return None

    model = direction.fit_model(X, y, kind="logreg")

    ts_arr, open_, high, low, close_arr, volume = features.arrays_from_candles(candles)
    X_all, idx_all = features.build_matrix(ts_arr, open_, high, low, close_arr, volume)
    if X_all.shape[0] == 0:
        return None

    last_i = int(idx_all[-1])
    p_up = float(model.predict_proba_up(X_all[-1:])[0])
    bar_secs = config.TIMEFRAMES[timeframe] * 60

    return {
        "p_up": p_up,
        "ref_close": float(close_arr[last_i]),
        "cutoff": int(ts_arr[last_i]),
        "target": int(ts_arr[last_i]) + bar_secs,
        "drivers": [
            {"feature": nm, "weight": w}
            for nm, w in model.coefficients(features.FEATURE_NAMES)[:5]
        ],
        "track": _latest_eval(inst.symbol, timeframe, horizon=1),
    }


def build_data(timeframes: list[str] | None = None, payout: float | None = None) -> dict:
    """Assemble the full Markets snapshot."""
    timeframes = timeframes or REPORT_TIMEFRAMES
    payout = payout if payout is not None else config.DEFAULT_FIXED_PAYOUT
    breakeven = config.breakeven_hit_rate(payout)

    instruments: list[dict] = []
    for inst in config.INSTRUMENTS:
        horizons: dict[str, dict] = {}
        for tf in timeframes:
            block = _instrument_block(inst, tf)
            if block is not None:
                horizons[tf] = block
        if not horizons:
            continue  # nothing ingested for this instrument yet

        # Price context from the finest timeframe we actually have.
        finest = next(tf for tf in timeframes if tf in horizons)
        bars = db.load_candles(inst.symbol, finest, limit=SPARK_POINTS)
        closes = [float(b["close"]) for b in bars]
        change = (
            (closes[-1] / closes[0] - 1.0) if len(closes) > 1 and closes[0] > 0 else 0.0
        )

        instruments.append(
            {
                "symbol": inst.symbol,
                "name": inst.name,
                "asset": inst.asset,
                "last": closes[-1] if closes else None,
                "change": change,
                "change_tf": finest,
                "spark": closes,
                "horizons": horizons,
            }
        )

    # --- the honest headline, computed not typed --------------------------
    tracks = [
        h["track"]
        for i in instruments
        for h in i["horizons"].values()
        if h["track"] is not None
    ]
    scored = [t for t in tracks if t["enough"]]
    summary = {
        "measured": len(scored),
        "cleared_breakeven": sum(1 for t in scored if t["clears_breakeven"]),
        "beat_base_rate": sum(1 for t in scored if t["beats_base"]),
        "mean_hit": (sum(t["hit"] for t in scored) / len(scored)) if scored else None,
        "best_hit": max((t["hit"] for t in scored), default=None),
        # Testing many combinations guarantees some will look good by luck. At a
        # 5% false-positive rate this is how many "edges" pure chance produces.
        # The app shows it next to the real count so a lone winner in a large
        # sweep reads as noise rather than as a discovery.
        "expected_false_positives": 0.05 * len(scored),
    }

    return {
        "generated": int(time.time()),
        "payout": payout,
        "breakeven": breakeven,
        "min_sample": config.MIN_SAMPLE_FOR_CLAIM,
        "timeframes": timeframes,
        "asset_classes": [
            {"key": k, "name": v}
            for k, v in config.ASSET_CLASSES.items()
            if any(i["asset"] == k for i in instruments)
        ],
        "instruments": instruments,
        "summary": summary,
    }


def write_json(path=None, **kwargs) -> str:
    """Write the snapshot to disk (default data/processed/markets.json)."""
    config.ensure_dirs()
    path = path or (config.PROCESSED_DIR / "markets.json")
    data = build_data(**kwargs)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, separators=(",", ":"))
    return str(path)


def summarise(data: dict) -> str:
    """One-screen console summary of what the snapshot says."""
    s = data["summary"]
    lines = [
        f"Markets snapshot  generated {timeutil.utc_from_epoch(data['generated']):%Y-%m-%d %H:%M} UTC",
        f"  instruments            : {len(data['instruments'])}",
        f"  timeframes             : {', '.join(data['timeframes'])}",
        f"  payout assumed         : {data['payout']:.0%}  (breakeven {data['breakeven']:.2%})",
        f"  track records measured : {s['measured']}",
        f"  beat base rate         : {s['beat_base_rate']}/{s['measured']}",
        f"  cleared breakeven      : {s['cleared_breakeven']}/{s['measured']}",
    ]
    if s["mean_hit"] is not None:
        lines.append(f"  mean hit rate          : {s['mean_hit']:.2%}")
        lines.append(f"  best hit rate          : {s['best_hit']:.2%}")
    return "\n".join(lines)
