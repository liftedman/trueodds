"""Hunt for a real edge: best opening prices + closing-line value (CLV).

Two changes from the naive backtest that give us an honest shot at an edge:

1. Bet at the BEST OPENING odds across bookmakers (max_h/d/a), not the sharp
   closing average. This is the price a disciplined line-shopper can actually
   get, and it's softer (higher) than the close.

2. Measure CLV against PINNACLE's closing line. Pinnacle is the sharpest book;
   its de-margined closing probabilities are the best public estimate of the
   "true" probability. For a bet we struck at `bet_odds` on outcome o:

        CLV_EV = bet_odds * q_close(o) - 1

   where q_close is Pinnacle's closing probability. Averaged over many bets,
   positive CLV means we systematically took prices better than where the
   sharp market settled — the strongest leading indicator that a model has
   genuine predictive value. CLV is far less noisy than realized yield, which
   swings wildly on a few results.

We sweep a range of edge thresholds: a real edge usually shows up only in the
SELECTIVE tail (bet less, bet better), if it shows up at all.
"""

from __future__ import annotations

import pandas as pd

from .. import config, db
from ..models import dixon_coles

_OUTCOMES = ["H", "D", "A"]
_THRESHOLDS = [0.0, 0.05, 0.10, 0.15, 0.20, 0.30]


def _devig(odds: dict[str, float]) -> dict[str, float] | None:
    if any(odds.get(o) is None or odds[o] <= 1.0 for o in _OUTCOMES):
        return None
    raw = {o: 1.0 / odds[o] for o in _OUTCOMES}
    total = sum(raw.values())
    return {o: raw[o] / total for o in _OUTCOMES}


# Bet-price column sets:
#   "best"     -> best opening odds across books (inflates CLV vs a single close)
#   "pinnacle" -> Pinnacle opening, for a clean same-book CLV vs Pinnacle close
_BET_COLS = {
    "best": ("max_h", "max_d", "max_a"),
    "pinnacle": ("pso_h", "pso_d", "pso_a"),
}


def _collect_bets(league_code: str, target_season: str,
                  bet_source: str = "best", use_xg: bool = True,
                  half_life_days: float | None = 180) -> list[dict]:
    """Fit the model on prior seasons; return one record per candidate bet."""
    bh, bd, ba = _BET_COLS[bet_source]
    with db.connect() as conn:
        df = pd.read_sql_query(
            "SELECT date, season, home, away, ftr, fthg, ftag, xg_h, xg_a, "
            f"{bh}, {bd}, {ba}, psc_h, psc_d, psc_a "
            "FROM football_matches WHERE league_code=? ORDER BY date",
            conn, params=(league_code,),
        )
    train = df[df["season"] < target_season]
    test = df[(df["season"] == target_season) & df["ftr"].notna()].copy()
    if train.empty or test.empty:
        raise ValueError(f"Not enough data: {len(train)}/{len(test)}")

    ref_date = pd.to_datetime(train["date"]).max()
    model = dixon_coles.fit(
        train, half_life_days=half_life_days, ref_date=ref_date, use_xg=use_xg
    )

    records: list[dict] = []
    for _, row in test.iterrows():
        open_odds = {"H": row[bh], "D": row[bd], "A": row[ba]}
        close_odds = {"H": row["psc_h"], "D": row["psc_d"], "A": row["psc_a"]}
        if any(pd.isna(v) for v in open_odds.values()):
            continue
        q_close = _devig(close_odds)
        if q_close is None:
            continue
        probs = model.predict(row["home"], row["away"])
        for o in _OUTCOMES:
            bet_odds = float(open_odds[o])
            edge = probs[o] * bet_odds - 1.0
            records.append({
                "edge": edge,
                "bet_odds": bet_odds,
                "won": row["ftr"] == o,
                "clv_ev": bet_odds * q_close[o] - 1.0,
                "beat_close": bet_odds > close_odds[o],
            })
    return records


def run_sweep(target_season: str = "2425", bet_source: str = "best") -> None:
    """Sweep edge thresholds across all leagues; report yield and CLV."""
    src_label = ("BEST OPENING odds (best-of-N)" if bet_source == "best"
                 else "PINNACLE OPENING odds (clean same-book CLV)")
    print(f"Edge hunt, season {target_season}: bet at {src_label}, "
          f"CLV vs Pinnacle close\n" + "=" * 72)

    all_records: list[dict] = []
    for code in config.FOOTBALL_LEAGUES:
        try:
            all_records.extend(
                _collect_bets(code, target_season, bet_source=bet_source)
            )
        except ValueError as e:
            print(f"{config.FOOTBALL_LEAGUES[code]}: skipped ({e})")

    print(f"\n{'min edge':>9} {'bets':>6} {'yield':>9} {'avg CLV':>9} "
          f"{'beat close':>11}")
    print("-" * 72)
    for thr in _THRESHOLDS:
        sel = [r for r in all_records if r["edge"] > thr]
        if not sel:
            print(f"{thr*100:>7.0f}% {0:>6}   (no bets)")
            continue
        n = len(sel)
        profit = sum((r["bet_odds"] - 1.0) if r["won"] else -1.0 for r in sel)
        yield_pct = profit / n * 100
        avg_clv = sum(r["clv_ev"] for r in sel) / n * 100
        beat = sum(r["beat_close"] for r in sel) / n * 100
        print(f"{thr*100:>7.0f}% {n:>6} {yield_pct:>+8.2f}% "
              f"{avg_clv:>+8.2f}% {beat:>10.1f}%")

    print("-" * 72)
    print("Reading this: positive AVG CLV (not yield) is the real signal. If")
    print("CLV stays negative at every threshold, the model has no edge — the")
    print("market prices these matches better than we do, period.")


_TOTALS_BET_COLS = {
    "best": ("max_ov", "max_un"),
    "pinnacle": ("pso_ov", "pso_un"),
}


def _devig2(over: float, under: float) -> dict[str, float] | None:
    """De-margin a two-way (over/under) market into probabilities."""
    if over is None or under is None or over <= 1.0 or under <= 1.0:
        return None
    ro, ru = 1.0 / over, 1.0 / under
    total = ro + ru
    return {"OV": ro / total, "UN": ru / total}


def _collect_totals_bets(league_code: str, target_season: str,
                         bet_source: str = "pinnacle", use_xg: bool = False,
                         half_life_days: float | None = 180) -> list[dict]:
    """Fit the model; return one record per Over/Under 2.5 candidate bet."""
    bov, bun = _TOTALS_BET_COLS[bet_source]
    with db.connect() as conn:
        df = pd.read_sql_query(
            "SELECT date, season, home, away, fthg, ftag, xg_h, xg_a, "
            f"{bov}, {bun}, psc_ov, psc_un "
            "FROM football_matches WHERE league_code=? ORDER BY date",
            conn, params=(league_code,),
        )
    train = df[df["season"] < target_season]
    test = df[(df["season"] == target_season) & df["fthg"].notna()].copy()
    if train.empty or test.empty:
        raise ValueError(f"Not enough data: {len(train)}/{len(test)}")

    ref_date = pd.to_datetime(train["date"]).max()
    model = dixon_coles.fit(
        train, half_life_days=half_life_days, ref_date=ref_date, use_xg=use_xg
    )

    records: list[dict] = []
    for _, row in test.iterrows():
        bet_odds = {"OV": row[bov], "UN": row[bun]}
        if any(pd.isna(v) for v in bet_odds.values()):
            continue
        q_close = _devig2(row["psc_ov"], row["psc_un"])
        if q_close is None:
            continue
        probs = model.predict_totals(row["home"], row["away"])
        total_goals = row["fthg"] + row["ftag"]
        result = "OV" if total_goals > 2.5 else "UN"
        for o in ("OV", "UN"):
            price = float(bet_odds[o])
            edge = probs[o] * price - 1.0
            records.append({
                "edge": edge,
                "bet_odds": price,
                "won": result == o,
                "clv_ev": price * q_close[o] - 1.0,
                "beat_close": price > (row["psc_ov"] if o == "OV"
                                       else row["psc_un"]),
            })
    return records


def scan_leagues_totals(
    leagues: dict[str, str],
    use_xg: bool = False,
    min_edge: float = 0.05,
    bet_source: str = "pinnacle",
) -> None:
    """Clean same-book CLV scan for the Over/Under 2.5 market across leagues."""
    mode = "xG" if use_xg else "goals"
    print(f"OVER/UNDER 2.5 CLV scan ({bet_source} open->close, {mode} model, "
          f"edge>{min_edge*100:.0f}%)\n" + "=" * 72)
    print(f"{'league':<20} {'bets':>6} {'yield':>9} {'avg CLV':>9} "
          f"{'beat close':>11}")
    print("-" * 72)

    rows = []
    for code, name in leagues.items():
        pooled: list[dict] = []
        for season in config.FOOTBALL_SEASONS:
            try:
                pooled.extend(
                    _collect_totals_bets(code, season, bet_source=bet_source,
                                         use_xg=use_xg)
                )
            except ValueError:
                continue
        sel = [r for r in pooled if r["edge"] > min_edge]
        if not sel:
            print(f"{name:<20} {0:>6}   (no data)")
            continue
        n = len(sel)
        profit = sum((r["bet_odds"] - 1.0) if r["won"] else -1.0 for r in sel)
        rows.append((name, n, profit / n * 100,
                     sum(r["clv_ev"] for r in sel) / n * 100,
                     sum(r["beat_close"] for r in sel) / n * 100))

    for name, n, yld, clv, beat in sorted(rows, key=lambda r: -r[3]):
        print(f"{name:<20} {n:>6} {yld:>+8.2f}% {clv:>+8.2f}% {beat:>10.1f}%")

    print("-" * 72)
    print("Positive avg CLV here = the model beats the closing line on totals.")
    print("This is the market the scoreline model is built for — its best shot.")


def scan_leagues(
    leagues: dict[str, str],
    use_xg: bool = False,
    min_edge: float = 0.05,
    bet_source: str = "pinnacle",
) -> None:
    """Clean same-book CLV scan across many leagues, pooled over all seasons.

    For each league we train on prior seasons and test forward across every
    season that has history, pool the bets above `min_edge`, and report yield
    plus average CLV. Ranked by CLV — a genuinely soft market should surface
    as consistently POSITIVE clean CLV (the model beating the closing line).
    """
    mode = "xG" if use_xg else "goals"
    print(f"Soft-market CLV scan ({bet_source} open->close, {mode} model, "
          f"edge>{min_edge*100:.0f}%)\n" + "=" * 72)
    print(f"{'league':<20} {'bets':>6} {'yield':>9} {'avg CLV':>9} "
          f"{'beat close':>11}")
    print("-" * 72)

    rows = []
    for code, name in leagues.items():
        pooled: list[dict] = []
        for season in config.FOOTBALL_SEASONS:
            try:
                pooled.extend(
                    _collect_bets(code, season, bet_source=bet_source,
                                  use_xg=use_xg)
                )
            except ValueError:
                continue  # no prior-season history for this target
        sel = [r for r in pooled if r["edge"] > min_edge]
        if not sel:
            print(f"{name:<20} {0:>6}   (no data)")
            continue
        n = len(sel)
        profit = sum((r["bet_odds"] - 1.0) if r["won"] else -1.0 for r in sel)
        yld = profit / n * 100
        clv = sum(r["clv_ev"] for r in sel) / n * 100
        beat = sum(r["beat_close"] for r in sel) / n * 100
        rows.append((name, n, yld, clv, beat))

    for name, n, yld, clv, beat in sorted(rows, key=lambda r: -r[3]):
        print(f"{name:<20} {n:>6} {yld:>+8.2f}% {clv:>+8.2f}% {beat:>10.1f}%")

    print("-" * 72)
    print("Ranked by avg CLV (high to low). Positive CLV in a league = the")
    print("model's picks there beat the closing line = candidate soft market.")
    print("Treat any positive as a HYPOTHESIS to confirm, never a green light.")


if __name__ == "__main__":
    run_sweep()
