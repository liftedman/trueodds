"""CLI entry point for Markets mode.

    python -m markets_model.main <command> [args]

Run `python -m markets_model.main --help` for the full list.
"""

from __future__ import annotations

import argparse
import sys
import time

from . import config, db, direction, evaluate, features, timeutil


# --- ingestion -------------------------------------------------------------

def cmd_init(_args) -> int:
    db.init_db()
    print(f"Initialized markets database at {config.DB_PATH}")
    return 0


def cmd_ingest_crypto(args) -> int:
    from .ingest import crypto

    tfs = args.timeframes or ["1m", "5m", "15m", "1h", "1d"]
    print(f"Ingesting crypto ({', '.join(tfs)}) from Binance...")
    n = crypto.ingest(timeframes=tfs, bars=args.bars, symbols=args.symbols)
    print(f"\n{n} bars written.")
    return 0


def cmd_ingest_yahoo(args) -> int:
    from .ingest import yahoo

    tfs = args.timeframes or ["5m", "15m", "1h", "1d"]
    print(f"Ingesting FX / stocks / indices / commodities ({', '.join(tfs)}) from Yahoo...")
    n = yahoo.ingest(timeframes=tfs, assets=args.assets, symbols=args.symbols)
    print(f"\n{n} bars written.")
    return 0


def cmd_ingest(args) -> int:
    """Ingest everything - crypto plus the four Yahoo-sourced asset classes."""
    rc = cmd_ingest_crypto(args)
    print()
    rc |= cmd_ingest_yahoo(args)
    return rc


def cmd_status(_args) -> int:
    rows = db.status()
    if not rows:
        print("No candles stored yet. Run:  python -m markets_model.main ingest")
        return 0

    print(f"{'symbol':10s} {'tf':5s} {'bars':>8s}  {'from':10s}   {'to':10s}")
    print("-" * 52)
    by_asset: dict[str, int] = {}
    for r in rows:
        first = timeutil.iso_date(r["first_ts"])
        last = timeutil.iso_date(r["last_ts"])
        print(f"{r['symbol']:10s} {r['timeframe']:5s} {r['bars']:8d}  {first}   {last}")
        inst = config.BY_SYMBOL.get(r["symbol"])
        if inst:
            by_asset[inst.asset] = by_asset.get(inst.asset, 0) + r["bars"]

    print("-" * 52)
    total = sum(r["bars"] for r in rows)
    for asset, n in sorted(by_asset.items(), key=lambda kv: -kv[1]):
        print(f"  {config.ASSET_CLASSES.get(asset, asset):14s} {n:9d} bars")
    print(f"  {'TOTAL':14s} {total:9d} bars")
    return 0


# --- evaluation ------------------------------------------------------------

def cmd_eval(args) -> int:
    r = evaluate.walk_forward(
        symbol=args.symbol.upper(),
        timeframe=args.timeframe,
        horizon=args.horizon,
        kind=args.model,
        payout=args.payout,
        n_blocks=args.blocks,
    )
    if r is None:
        print(
            f"Not enough data for {args.symbol.upper()} {args.timeframe}. "
            "Ingest more bars first (`status` shows what you have)."
        )
        return 1
    print(evaluate.format_result(r))
    if args.save:
        evaluate.save_result(r)
        print("\n  (saved to eval_runs)")
    return 0


def cmd_eval_all(args) -> int:
    """Sweep every stored symbol/timeframe and summarise honestly.

    This is the command that answers the real question: across the whole
    universe and every horizon a fixed-time platform offers, does the model beat
    the payout anywhere - and is that anything more than what you would expect
    from running many tests?
    """
    stored = db.status()
    if not stored:
        print("Nothing ingested yet.")
        return 1

    tfs = set(args.timeframes) if args.timeframes else None
    pairs = [
        (r["symbol"], r["timeframe"])
        for r in stored
        if (tfs is None or r["timeframe"] in tfs) and r["bars"] >= 500
    ]
    if not pairs:
        print("No symbol/timeframe combination has enough bars yet.")
        return 1

    print(
        f"Walk-forward evaluation: {len(pairs)} symbol/timeframe combinations, "
        f"payout {args.payout:.0%}, breakeven {config.breakeven_hit_rate(args.payout):.2%}\n"
    )
    header = (
        f"{'symbol':9s} {'tf':4s} {'n':>7s} {'hit':>7s} {'CI low':>7s} "
        f"{'EV':>8s} {'logloss':>9s} {'base':>9s}  verdict"
    )
    print(header)
    print("-" * len(header))

    run_ts = int(time.time())
    results: list[evaluate.EvalResult] = []
    for symbol, tf in pairs:
        r = evaluate.walk_forward(
            symbol=symbol,
            timeframe=tf,
            horizon=args.horizon,
            kind=args.model,
            payout=args.payout,
            n_blocks=args.blocks,
        )
        if r is None:
            continue
        results.append(r)
        if args.save:
            evaluate.save_result(r, run_ts=run_ts)

        tag = (
            "EDGE?" if r.profitable_at_payout
            else ("signal" if r.beats_base_rate else "no edge")
        )
        if not r.enough_data:
            tag = "thin"
        print(
            f"{r.symbol:9s} {r.timeframe:4s} {r.n:7d} {r.hit_rate:7.2%} "
            f"{r.hit_ci[0]:7.2%} {r.ev_per_trade:+8.2%} "
            f"{r.model_log_loss:9.5f} {r.base_log_loss:9.5f}  {tag}"
        )

    if not results:
        print("No combination had enough data to evaluate.")
        return 1

    # --- the summary that matters -----------------------------------------
    n_total = len(results)
    n_signal = sum(1 for r in results if r.beats_base_rate)
    n_edge = sum(1 for r in results if r.profitable_at_payout)
    n_thin = sum(1 for r in results if not r.enough_data)
    mean_hit = sum(r.hit_rate for r in results) / n_total
    breakeven = config.breakeven_hit_rate(args.payout)

    print("\n" + "=" * 72)
    print("SUMMARY")
    print(f"  combinations evaluated        : {n_total}  ({n_thin} with thin samples)")
    print(f"  mean hit rate                 : {mean_hit:.2%}")
    print(f"  breakeven needed @ {args.payout:.0%} payout : {breakeven:.2%}")
    print(f"  beat the base-rate benchmark  : {n_signal}/{n_total}")
    print(f"  cleared breakeven (CI lower)  : {n_edge}/{n_total}")

    # Multiple-testing caution. With ~5% of tests passing at random, a handful of
    # "edges" across dozens of combinations is the expected noise, not a finding.
    expected_false = 0.05 * n_total
    print(
        f"\n  Expected false positives from running {n_total} tests at 5%: "
        f"~{expected_false:.1f}"
    )
    if n_edge == 0:
        print(
            "  -> No edge anywhere. This is the expected result, and it is the\n"
            "     honest headline for Markets mode."
        )
    elif n_edge <= expected_false:
        print(
            "  -> The apparent edges are within multiple-testing noise. Not\n"
            "     evidence of a real edge."
        )
    else:
        print(
            "  -> More apparent edges than chance predicts. Worth investigating,\n"
            "     but assume a data or leakage bug until proven otherwise."
        )
    print("=" * 72)
    return 0


# --- live prediction -------------------------------------------------------

def cmd_predict(args) -> int:
    """Publish a prediction for the next bar, from the latest closed bar."""
    symbol, tf, horizon = args.symbol.upper(), args.timeframe, args.horizon

    candles = db.load_candles(symbol, tf)
    if len(candles) < features.WARMUP + 200:
        print(f"Not enough stored bars for {symbol} {tf}.")
        return 1

    # Fit on everything whose outcome is already settled, then score the most
    # recent closed bar - which has no outcome yet. That is a genuine forecast.
    X, y, idx, ts, close = features.build_dataset(candles, horizon=horizon)
    if X.shape[0] < 200:
        print("Not enough usable feature rows.")
        return 1

    model = direction.fit_model(X, y, kind=args.model)

    ts_arr, open_, high, low, close_arr, volume = features.arrays_from_candles(candles)
    X_all, idx_all = features.build_matrix(ts_arr, open_, high, low, close_arr, volume)
    if X_all.shape[0] == 0:
        print("Could not build features for the latest bar.")
        return 1

    last_i = int(idx_all[-1])
    p_up = float(model.predict_proba_up(X_all[-1:])[0])
    ref_close = float(close_arr[last_i])
    cutoff = timeutil.utc_from_epoch(int(ts_arr[last_i]))
    bar_secs = config.TIMEFRAMES[tf] * 60
    target_ts = int(ts_arr[last_i]) + horizon * bar_secs
    target_dt = timeutil.utc_from_epoch(target_ts)

    breakeven = config.breakeven_hit_rate(args.payout)
    edge_side = "UP" if p_up > 0.5 else "DOWN"
    p_side = p_up if p_up > 0.5 else 1.0 - p_up

    print(f"{symbol}  {tf}  horizon={horizon} bar(s)")
    print(f"  information cutoff : {cutoff:%Y-%m-%d %H:%M} UTC (close {ref_close:g})")
    print(f"  settles at         : {target_dt:%Y-%m-%d %H:%M} UTC")
    print(f"  P(up)              : {p_up:.2%}")
    print(f"  leaning            : {edge_side} at {p_side:.2%} confidence")
    print(f"  breakeven needed   : {breakeven:.2%} @ {args.payout:.0%} payout")

    if p_side < breakeven:
        print(
            f"\n  This is BELOW breakeven. On a fixed-time trade paying "
            f"{args.payout:.0%},\n  acting on it has negative expected value of "
            f"{p_side * args.payout - (1 - p_side):+.2%} per unit staked."
        )
    else:
        print(
            "\n  Above breakeven on paper. Check `eval` for this symbol/timeframe:\n"
            "  a single confident-looking forecast means nothing if the measured\n"
            "  out-of-sample hit rate does not clear breakeven too."
        )

    coefs = model.coefficients(features.FEATURE_NAMES)[:5]
    if coefs:
        print("\n  strongest drivers  : " + ", ".join(f"{n}={c:+.3f}" for n, c in coefs))

    if args.save:
        with db.connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO predictions (
                    symbol, timeframe, horizon, made_at_ts, target_ts,
                    ref_close, p_up, model
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    symbol, tf, horizon, int(ts_arr[last_i]), target_ts,
                    ref_close, p_up, f"{args.model}-h{horizon}",
                ),
            )
        print("\n  (logged to predictions - resolve later with `resolve`)")
    return 0


def cmd_resolve(_args) -> int:
    """Fill in outcomes for logged predictions whose target bar has closed."""
    db.init_db()
    with db.connect() as conn:
        pending = conn.execute(
            "SELECT * FROM predictions WHERE actual_up IS NULL"
        ).fetchall()

        resolved = 0
        for p in pending:
            row = conn.execute(
                "SELECT close FROM candles WHERE symbol=? AND timeframe=? AND ts=?",
                (p["symbol"], p["timeframe"], p["target_ts"]),
            ).fetchone()
            if row is None:
                continue  # target bar not ingested yet
            settle = float(row["close"])
            if settle == p["ref_close"]:
                continue  # tie - leave pending rather than guess
            conn.execute(
                "UPDATE predictions SET settle_close=?, actual_up=? WHERE id=?",
                (settle, 1 if settle > p["ref_close"] else 0, p["id"]),
            )
            resolved += 1

        total = conn.execute(
            "SELECT COUNT(*) AS n FROM predictions WHERE actual_up IS NOT NULL"
        ).fetchone()["n"]
        wins = conn.execute(
            """
            SELECT COUNT(*) AS n FROM predictions
            WHERE actual_up IS NOT NULL
              AND ((p_up > 0.5 AND actual_up = 1) OR (p_up <= 0.5 AND actual_up = 0))
            """
        ).fetchone()["n"]

    print(f"Resolved {resolved} prediction(s) this run.")
    if total:
        lo, hi = evaluate.wilson_interval(wins, total)
        print(
            f"Live track record: {wins}/{total} correct = {wins / total:.2%} "
            f"(95% CI {lo:.2%} - {hi:.2%})"
        )
        if total < config.MIN_SAMPLE_FOR_CLAIM:
            print(
                f"  Too few to mean anything yet (need "
                f"{config.MIN_SAMPLE_FOR_CLAIM})."
            )
    else:
        print("No resolved predictions yet.")
    return 0


# --- snapshot for the app --------------------------------------------------

def cmd_report(args) -> int:
    from . import report

    path = report.write_json(timeframes=args.timeframes)
    with open(path, encoding="utf-8") as fh:
        import json as _json

        data = _json.load(fh)
    print(report.summarise(data))
    print(f"\nWrote {path}")
    return 0


def cmd_push(args) -> int:
    from . import push

    push.push_snapshot(timeframes=args.timeframes)
    return 0


# --- argument parsing ------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="markets_model.main",
        description="Markets mode - honest short-horizon analysis.",
    )
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="create the database").set_defaults(func=cmd_init)
    sub.add_parser("status", help="what's stored").set_defaults(func=cmd_status)

    def add_ingest_args(sp, with_assets: bool = False):
        sp.add_argument("--timeframes", nargs="*", choices=list(config.TIMEFRAMES))
        sp.add_argument("--symbols", nargs="*", help="limit to these symbols")
        sp.add_argument("--bars", type=int, default=5000, help="crypto bars per timeframe")
        if with_assets:
            sp.add_argument("--assets", nargs="*", choices=list(config.ASSET_CLASSES))
        else:
            sp.set_defaults(assets=None)

    sp = sub.add_parser("ingest", help="ingest everything (crypto + Yahoo)")
    add_ingest_args(sp, with_assets=True)
    sp.set_defaults(func=cmd_ingest)

    sp = sub.add_parser("ingest-crypto", help="Binance crypto bars")
    add_ingest_args(sp)
    sp.set_defaults(func=cmd_ingest_crypto)

    sp = sub.add_parser("ingest-yahoo", help="FX / stocks / indices / commodities")
    add_ingest_args(sp, with_assets=True)
    sp.set_defaults(func=cmd_ingest_yahoo)

    def add_model_args(sp):
        sp.add_argument("--horizon", type=int, default=1, help="bars ahead")
        sp.add_argument("--model", choices=["logreg", "gbdt"], default="logreg")
        sp.add_argument("--payout", type=float, default=config.DEFAULT_FIXED_PAYOUT)
        sp.add_argument("--save", action="store_true")

    sp = sub.add_parser("eval", help="walk-forward evaluation for one instrument")
    sp.add_argument("symbol")
    sp.add_argument("timeframe", choices=list(config.TIMEFRAMES))
    add_model_args(sp)
    sp.add_argument("--blocks", type=int, default=10)
    sp.set_defaults(func=cmd_eval)

    sp = sub.add_parser("eval-all", help="sweep every stored symbol/timeframe")
    add_model_args(sp)
    sp.add_argument("--timeframes", nargs="*", choices=list(config.TIMEFRAMES))
    sp.add_argument("--blocks", type=int, default=8)
    sp.set_defaults(func=cmd_eval_all)

    sp = sub.add_parser("predict", help="forecast the next bar")
    sp.add_argument("symbol")
    sp.add_argument("timeframe", choices=list(config.TIMEFRAMES))
    add_model_args(sp)
    sp.set_defaults(func=cmd_predict)

    sub.add_parser(
        "resolve", help="settle logged predictions and show the live record"
    ).set_defaults(func=cmd_resolve)

    sp = sub.add_parser("report", help="build the app snapshot (data/processed)")
    sp.add_argument("--timeframes", nargs="*", choices=list(config.TIMEFRAMES))
    sp.set_defaults(func=cmd_report)

    sp = sub.add_parser("push", help="build + upload the snapshot to Supabase")
    sp.add_argument("--timeframes", nargs="*", choices=list(config.TIMEFRAMES))
    sp.set_defaults(func=cmd_push)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
