"""Paper trading: log forecasts before the outcome exists, then grade them.

This is the part that can settle the argument. A walk-forward backtest is only
as trustworthy as the person who wrote it; a forward record written in advance
and never edited is not. If the model really is stuck around 51%, this will show
it in public, at no cost. If it somehow clears the 55.56% breakeven over a few
hundred logged trades, that is evidence worth having.

Three operations:

  log      write a prediction for every instrument/timeframe whose latest bar we
           have not already logged. Never overwrites a graded row.
  resolve  find pending rows whose settlement bar has now closed, look up the
           actual close, and grade them.
  record   aggregate the graded rows into a live hit rate with a confidence
           interval, for the app to display.

Rows live in Supabase (see docs/markets_paper_schema.sql), not in the local
SQLite file, because the scheduled cloud job rebuilds that file from scratch
every run. Consequence worth knowing: local and cloud runs contribute to the
SAME record.
"""

from __future__ import annotations

import json
import os
import time

import requests

from . import config, db, direction, evaluate, features

_TIMEOUT = 60
TABLE = "paper_predictions"


class PaperStoreUnavailable(RuntimeError):
    """The paper store can't be reached (no creds, or the table isn't created).

    Deliberately a RuntimeError and NOT SystemExit. report.py folds the live
    record into the snapshot inside a `except Exception` guard so a missing
    paper store can never take Markets mode offline - and SystemExit inherits
    from BaseException, so it would sail straight through that guard and kill
    the nightly push. The CLI turns this back into a friendly exit itself.
    """


def _creds() -> tuple[str, str]:
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not url or not key:
        raise PaperStoreUnavailable(
            "Set SUPABASE_URL and SUPABASE_SERVICE_KEY in .env first "
            "(the same values the snapshot push uses)."
        )
    return url.rstrip("/"), key


def _headers(key: str, extra: dict | None = None) -> dict:
    h = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    if extra:
        h.update(extra)
    return h


def _missing_table_hint(resp) -> None:
    if resp.status_code == 404 or (
        resp.status_code == 400 and "paper_predictions" in resp.text
    ):
        raise PaperStoreUnavailable(
            f"Supabase has no '{TABLE}' table yet. Open your project -> "
            "SQL Editor, paste docs/markets_paper_schema.sql, and Run."
        )


# --- logging ---------------------------------------------------------------

def _forecast(symbol: str, timeframe: str, horizon: int = 1) -> dict | None:
    """Fit on settled bars and forecast the latest closed bar's successor.

    Returns None when there is not enough history. Mirrors report._instrument_block
    so the logged forecast is exactly what the app displays - if these two ever
    diverged, the track record would be grading a different model than the one on
    screen.
    """
    candles = db.load_candles(symbol, timeframe, limit=6000)
    if len(candles) < features.WARMUP + 250:
        return None

    X, y, _idx, _ts, _close = features.build_dataset(candles, horizon=horizon)
    if X.shape[0] < 250:
        return None

    model = direction.fit_model(X, y, kind="logreg")

    ts_arr, open_, high, low, close_arr, volume = features.arrays_from_candles(candles)
    X_all, idx_all = features.build_matrix(ts_arr, open_, high, low, close_arr, volume)
    if X_all.shape[0] == 0:
        return None

    last_i = int(idx_all[-1])
    bar_secs = config.TIMEFRAMES[timeframe] * 60
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "horizon": horizon,
        "made_at_ts": int(ts_arr[last_i]),
        "target_ts": int(ts_arr[last_i]) + horizon * bar_secs,
        "ref_close": float(close_arr[last_i]),
        "p_up": float(model.predict_proba_up(X_all[-1:])[0]),
        "model": f"{direction.MODEL_VERSION}-h{horizon}",
    }


# How long past its settlement time a prediction may wait for its bar before we
# accept the bar is never coming. Generous relative to normal upstream lag
# (usually well under one bar), but short enough that a weekend does not leave
# junk sitting in the pending queue for days.
VOID_GRACE_BARS = 3


def settles_at(target_ts: int, timeframe: str) -> int:
    """When the prediction is actually decided.

    `target_ts` is the settling bar's OPEN time, so the outcome is not known
    until that bar CLOSES, one bar length later. Comparing target_ts itself
    against the clock declares a forecast finished a whole bar early - which for
    a 1h horizon silently threw away every forecast made in the current hour,
    and for 1d would have discarded a full day.
    """
    return target_ts + config.TIMEFRAMES[timeframe] * 60


def log(timeframes: list[str] | None = None, horizon: int = 1) -> int:
    """Log a forecast per instrument/timeframe. Returns rows written.

    Only forecasts whose window is still OPEN are logged. A forecast for a bar
    that has already closed is not a prediction - logging it would let a stale
    ingest quietly pad the record with hindsight.
    """
    url, key = _creds()
    timeframes = timeframes or ["1h"]
    now = int(time.time())

    rows: list[dict] = []
    skipped_closed = 0
    for inst in config.INSTRUMENTS:
        for tf in timeframes:
            f = _forecast(inst.symbol, tf, horizon)
            if f is None:
                continue
            if settles_at(f["target_ts"], tf) <= now:
                skipped_closed += 1
                continue
            rows.append(f)

    if skipped_closed:
        print(
            f"  skipped {skipped_closed} forecast(s) whose window had already "
            "closed (ingest is behind — run ingest first)"
        )
    if not rows:
        print("  nothing to log.")
        return 0

    resp = requests.post(
        f"{url}/rest/v1/{TABLE}",
        headers=_headers(
            key,
            # merge-duplicates makes a retried run idempotent rather than
            # inflating the sample with duplicate rows.
            {"Prefer": "resolution=merge-duplicates,return=minimal"},
        ),
        data=json.dumps(rows),
        timeout=_TIMEOUT,
    )
    _missing_table_hint(resp)
    resp.raise_for_status()
    print(f"  logged {len(rows)} forecast(s).")
    return len(rows)


# --- resolving -------------------------------------------------------------

def resolve() -> int:
    """Grade pending rows whose settlement bar has closed. Returns rows graded."""
    url, key = _creds()
    now = int(time.time())

    resp = requests.get(
        f"{url}/rest/v1/{TABLE}",
        headers=_headers(key),
        params={
            "select": "id,symbol,timeframe,target_ts,ref_close",
            "actual_up": "is.null",
            "target_ts": f"lte.{now}",
            "order": "target_ts.asc",
            "limit": "2000",
        },
        timeout=_TIMEOUT,
    )
    _missing_table_hint(resp)
    resp.raise_for_status()
    pending = resp.json()
    if not pending:
        print("  nothing to resolve.")
        return 0

    graded = 0
    unavailable = 0
    not_due = 0
    voided: list[str] = []
    for p in pending:
        # The query above filters on target_ts (the settling bar's OPEN time),
        # which is a deliberate superset: a row is only genuinely due once that
        # bar has CLOSED. Filtering precisely in SQL isn't possible in one query
        # because the bar length varies by timeframe, so it's done here.
        if settles_at(int(p["target_ts"]), p["timeframe"]) > now:
            not_due += 1
            continue
        with db.connect() as conn:
            row = conn.execute(
                "SELECT close FROM candles WHERE symbol=? AND timeframe=? AND ts=?",
                (p["symbol"], p["timeframe"], p["target_ts"]),
            ).fetchone()
        if row is None:
            # The bar may simply not be ingested yet — or it may never exist. A
            # forecast logged just before a market closes targets a bar that
            # never forms (FX stops on Friday evening), so it can never settle.
            # Those are VOID: not a win, not a loss, and counting them either way
            # would corrupt the record. They are dropped rather than graded,
            # which is safe because the criterion is "the bar never existed",
            # never "the outcome was unflattering".
            bar_secs = config.TIMEFRAMES[p["timeframe"]] * 60
            if now - settles_at(int(p["target_ts"]), p["timeframe"]) > (
                VOID_GRACE_BARS * bar_secs
            ):
                voided.append(f"{p['symbol']}/{p['timeframe']}")
                requests.delete(
                    f"{url}/rest/v1/{TABLE}",
                    headers=_headers(key, {"Prefer": "return=minimal"}),
                    params={"id": f"eq.{p['id']}"},
                    timeout=_TIMEOUT,
                ).raise_for_status()
                continue
            unavailable += 1
            continue  # settlement bar not ingested yet; try again next run

        settle = float(row["close"])
        ref = float(p["ref_close"])
        if settle == ref:
            continue  # exact tie: leave pending rather than invent an outcome

        r = requests.patch(
            f"{url}/rest/v1/{TABLE}",
            headers=_headers(key, {"Prefer": "return=minimal"}),
            params={"id": f"eq.{p['id']}"},
            data=json.dumps(
                {
                    "settle_close": settle,
                    "actual_up": settle > ref,
                    "resolved_at": "now()",
                }
            ),
            timeout=_TIMEOUT,
        )
        r.raise_for_status()
        graded += 1

    print(f"  resolved {graded} prediction(s).")
    if not_due:
        print(f"  {not_due} not due yet - their settling bar is still open.")
    if unavailable:
        print(
            f"  {unavailable} still pending - their settlement bar is not in the "
            "local database yet (ingest that timeframe, then resolve again)."
        )
    if voided:
        print(
            f"  {len(voided)} VOID - the settling bar never formed, so these can "
            "never be graded (typically logged just before a market closed): "
            + ", ".join(voided)
        )
    return graded


# --- the live record -------------------------------------------------------

def summarise_predictions(rows: list[dict], payout: float) -> dict:
    """Aggregate graded rows into a hit rate, interval and expected value.

    A row counts as correct when the side the model leaned matches the outcome:
    p_up > 0.5 predicts up, anything else predicts down. p_up == 0.5 is treated
    as a "down" call rather than a free pass - a model with no opinion should not
    be scored as right half the time by convention.
    """
    n = len(rows)
    if n == 0:
        return {"n": 0}

    wins = sum(1 for r in rows if (r["p_up"] > 0.5) == bool(r["actual_up"]))
    hit = wins / n
    lo, hi = evaluate.wilson_interval(wins, n)
    breakeven = config.breakeven_hit_rate(payout)
    enough = n >= config.MIN_SAMPLE_FOR_CLAIM
    return {
        "n": n,
        "wins": wins,
        "hit": hit,
        "ci": [lo, hi],
        "ev": hit * payout - (1.0 - hit),
        "enough": enough,
        # Lower bound, not the point estimate - same discipline as the backtest.
        "clears_breakeven": enough and lo > breakeven,
    }

def record(payout: float | None = None) -> dict:
    """Aggregate graded predictions into a live, forward-tested track record.

    Read with the SERVICE key here because this runs server-side; the app reads
    the same rows with the anon key via the public SELECT policy.
    """
    url, key = _creds()
    payout = payout if payout is not None else config.DEFAULT_FIXED_PAYOUT
    breakeven = config.breakeven_hit_rate(payout)

    rows: list[dict] = []
    page = 0
    while True:
        resp = requests.get(
            f"{url}/rest/v1/{TABLE}",
            headers=_headers(key),
            params={
                "select": "symbol,timeframe,p_up,actual_up,made_at_ts",
                "actual_up": "not.is.null",
                "order": "made_at_ts.asc",
                "limit": "1000",
                "offset": str(page * 1000),
            },
            timeout=_TIMEOUT,
        )
        _missing_table_hint(resp)
        resp.raise_for_status()
        batch = resp.json()
        rows.extend(batch)
        if len(batch) < 1000:
            break
        page += 1

    by_tf: dict[str, dict] = {}
    for tf in sorted({r["timeframe"] for r in rows}):
        by_tf[tf] = summarise_predictions(
            [r for r in rows if r["timeframe"] == tf], payout
        )

    return {
        "overall": summarise_predictions(rows, payout),
        "by_timeframe": by_tf,
        "payout": payout,
        "breakeven": breakeven,
        "first_ts": rows[0]["made_at_ts"] if rows else None,
        "last_ts": rows[-1]["made_at_ts"] if rows else None,
        "pending": _pending_count(url, key),
    }


def _pending_count(url: str, key: str) -> int:
    """How many logged forecasts are still awaiting their outcome."""
    resp = requests.get(
        f"{url}/rest/v1/{TABLE}",
        headers=_headers(key, {"Prefer": "count=exact"}),
        params={"select": "id", "actual_up": "is.null", "limit": "1"},
        timeout=_TIMEOUT,
    )
    if resp.status_code >= 400:
        return 0
    # PostgREST reports the total in Content-Range as "0-0/123".
    rng = resp.headers.get("content-range", "")
    if "/" in rng:
        try:
            return int(rng.split("/")[-1])
        except ValueError:
            return 0
    return 0


def publish_record(rec: dict | None = None) -> bool:
    """Patch the live record into the published snapshot, in place.

    The hourly job cannot afford to rebuild the whole snapshot: doing that needs
    every timeframe ingested AND the eval_runs table, and the cloud runner
    rebuilds its database from scratch each time, so a cheap hourly `push` would
    republish with missing horizons and null track records - strictly worse than
    what is already live.

    So instead we read the existing row, swap in the one key that changed, and
    write it back. Small (~117KB) and safe against the daily full rebuild, which
    runs at a different time and simply recomputes this field anyway.

    Returns False if there is no snapshot row yet to patch.
    """
    url, key = _creds()
    rec = rec if rec is not None else record()

    resp = requests.get(
        f"{url}/rest/v1/snapshot",
        headers=_headers(key),
        params={"select": "data", "id": "eq.markets"},
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    rows = resp.json()
    if not rows:
        print("  no markets snapshot to patch yet — run `push` first.")
        return False

    data = rows[0]["data"]
    data["live_record"] = rec

    patch = requests.patch(
        f"{url}/rest/v1/snapshot",
        headers=_headers(key, {"Prefer": "return=minimal"}),
        params={"id": "eq.markets"},
        data=json.dumps({"data": data, "updated_at": "now()"}),
        timeout=_TIMEOUT,
    )
    patch.raise_for_status()
    n = rec.get("overall", {}).get("n", 0)
    print(f"  published live record to the snapshot ({n} graded).")
    return True


def format_record(rec: dict) -> str:
    """Console summary of the live record."""
    o = rec["overall"]
    lines = ["Live paper-trading record (forward-tested, logged before the outcome)"]
    if o["n"] == 0:
        lines.append(
            f"  no graded predictions yet ({rec['pending']} pending). "
            "Run `paper` again once their windows have closed."
        )
        return "\n".join(lines)

    lines += [
        f"  graded predictions : {o['n']}   ({rec['pending']} pending)",
        f"  hit rate           : {o['hit']:.2%}  "
        f"(95% CI {o['ci'][0]:.2%} - {o['ci'][1]:.2%})",
        f"  breakeven needed   : {rec['breakeven']:.2%} @ {rec['payout']:.0%} payout",
        f"  EV per trade       : {o['ev']:+.2%}",
    ]
    if not o["enough"]:
        lines.append(
            f"  -> Too few to claim anything yet "
            f"(need {config.MIN_SAMPLE_FOR_CLAIM})."
        )
    elif o["clears_breakeven"]:
        lines.append("  -> Clears breakeven. Verify before believing it.")
    else:
        lines.append("  -> Below breakeven: acting on these would lose money.")

    if rec["by_timeframe"]:
        lines.append("\n  by timeframe:")
        for tf, s in rec["by_timeframe"].items():
            if s["n"] == 0:
                continue
            lines.append(
                f"    {tf:4s} n={s['n']:5d}  hit={s['hit']:.2%}  ev={s['ev']:+.2%}"
            )
    return "\n".join(lines)
