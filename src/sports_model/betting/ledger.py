"""Paper-betting backtest.

Trains the xG model on past seasons, then walks the target season in date
order placing value bets against Bet365 closing odds, and tracks the result.

Two staking results are reported side by side:
  - FLAT (1 unit/bet): yield = profit / total_staked. The honest edge measure.
  - KELLY (fractional): compounding bankroll growth, for intuition.

Why bet against *closing* odds? It's the toughest possible test. Closing odds
are the sharpest the market ever gets. If we can't show a positive yield vs the
close, we have no edge — full stop. (When we later go LIVE we'd bet at opening/
soft prices and also measure closing-line value; that needs odds captured at
bet time, which this historical dataset doesn't have. Noted, not faked.)
"""

from __future__ import annotations

import csv

import pandas as pd

from .. import config, db
from ..models import dixon_coles
from . import staking, value

_START_BANKROLL = 100.0


def _odds_dict(row: pd.Series) -> dict[str, float] | None:
    o = {"H": row["b365h"], "D": row["b365d"], "A": row["b365a"]}
    if any(pd.isna(v) or v <= 1.0 for v in o.values()):
        return None
    return {k: float(v) for k, v in o.items()}


def run_value_backtest(
    league_code: str,
    target_season: str,
    min_edge: float = 0.05,
    half_life_days: float | None = 180,
    use_xg: bool = True,
    kelly_fraction: float = 0.25,
    write_csv: bool = False,
) -> dict:
    """Backtest a value-betting strategy for one league-season."""
    with db.connect() as conn:
        df = pd.read_sql_query(
            "SELECT date, season, home, away, fthg, ftag, ftr, xg_h, xg_a, "
            "b365h, b365d, b365a FROM football_matches "
            "WHERE league_code=? ORDER BY date",
            conn,
            params=(league_code,),
        )

    train = df[df["season"] < target_season]
    test = df[(df["season"] == target_season) & df["ftr"].notna()].copy()
    if train.empty or test.empty:
        raise ValueError(f"Not enough data: {len(train)}/{len(test)}")

    ref_date = pd.to_datetime(train["date"]).max()
    model = dixon_coles.fit(
        train, half_life_days=half_life_days, ref_date=ref_date, use_xg=use_xg
    )

    n_bets = n_wins = 0
    flat_staked = flat_profit = 0.0
    bankroll = _START_BANKROLL
    rows_out = []

    for _, row in test.iterrows():
        odds = _odds_dict(row)
        if odds is None:
            continue
        probs = model.predict(row["home"], row["away"])
        for bet in value.find_value_bets(probs, odds, min_edge=min_edge):
            won = row["ftr"] == bet.outcome
            n_bets += 1
            n_wins += won

            # FLAT staking (1 unit).
            flat_staked += 1.0
            flat_profit += (bet.odds - 1.0) if won else -1.0

            # KELLY staking (fraction of current bankroll).
            kf = staking.kelly_fraction(
                bet.model_p, bet.odds, fraction=kelly_fraction
            )
            stake = bankroll * kf
            bankroll += stake * (bet.odds - 1.0) if won else -stake

            rows_out.append({
                "date": row["date"], "home": row["home"], "away": row["away"],
                "pick": bet.outcome, "odds": bet.odds,
                "model_p": round(bet.model_p, 4), "edge": round(bet.edge, 4),
                "result": row["ftr"], "won": int(won),
            })

    if write_csv and rows_out:
        config.ensure_dirs()
        path = config.PROCESSED_DIR / f"bets_{league_code}_{target_season}.csv"
        with open(path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows_out[0].keys()))
            w.writeheader()
            w.writerows(rows_out)

    return {
        "league": config.FOOTBALL_LEAGUES[league_code],
        "season": target_season,
        "n_bets": n_bets,
        "win_rate": (n_wins / n_bets) if n_bets else 0.0,
        "flat_staked": flat_staked,
        "flat_profit": flat_profit,
        "flat_yield": (flat_profit / flat_staked) if flat_staked else 0.0,
        "kelly_start": _START_BANKROLL,
        "kelly_final": bankroll,
        "kelly_roi": (bankroll - _START_BANKROLL) / _START_BANKROLL,
    }


def _fmt(r: dict) -> str:
    return (
        f"{r['league']:<16} {r['season']}\n"
        f"  bets placed   {r['n_bets']:>5}   win rate {r['win_rate']*100:5.1f}%\n"
        f"  FLAT  staked {r['flat_staked']:>7.0f}u  profit {r['flat_profit']:+8.2f}u"
        f"   yield {r['flat_yield']*100:+6.2f}%\n"
        f"  KELLY 100 -> {r['kelly_final']:7.2f}u"
        f"   ROI {r['kelly_roi']*100:+6.2f}%\n"
    )


def run_all(
    target_season: str = "2425",
    min_edge: float = 0.05,
    use_xg: bool = True,
) -> None:
    print(f"Value-betting backtest, season {target_season}  "
          f"(min edge {min_edge*100:.0f}%, "
          f"{'xG' if use_xg else 'goals'} model, vs Bet365 close)\n" + "=" * 60)
    agg_staked = agg_profit = 0.0
    total_bets = 0
    for code in config.FOOTBALL_LEAGUES:
        try:
            r = run_value_backtest(
                code, target_season, min_edge=min_edge,
                use_xg=use_xg, write_csv=True,
            )
        except ValueError as e:
            print(f"{config.FOOTBALL_LEAGUES[code]}: skipped ({e})\n")
            continue
        print(_fmt(r))
        agg_staked += r["flat_staked"]
        agg_profit += r["flat_profit"]
        total_bets += r["n_bets"]

    if agg_staked:
        print("=" * 60)
        print(f"OVERALL: {total_bets} bets, {agg_staked:.0f}u staked (flat), "
              f"profit {agg_profit:+.2f}u, "
              f"yield {agg_profit / agg_staked * 100:+.2f}%")
        if agg_profit <= 0:
            print("  -> Negative yield: NO betting edge vs the closing line. "
                  "Expected. Do NOT bet real money on this.")
        else:
            print("  -> Positive yield on paper. Treat with deep suspicion "
                  "until confirmed live on hundreds more bets (could be noise).")


if __name__ == "__main__":
    run_all()
