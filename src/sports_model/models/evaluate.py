"""Honest out-of-sample evaluation of the football model.

The cardinal rule: never let the model see the season it's being scored on.
For a target season we train ONLY on earlier seasons, then predict every match
in the target season. We score those predictions two ways:

  - log loss  (lower = better; punishes confident wrong calls hard)
  - Brier     (lower = better; mean squared probability error)
  - accuracy  (argmax hit rate — intuitive but a weak measure for 3 outcomes)

Then we run the SAME scoring on the bookmaker's own probabilities (their odds
with the margin stripped out). That comparison is the whole point: the market
is the benchmark to beat. If our log loss is worse than the bookmaker's, we
have no edge — and that's the honest, common result for a baseline model.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .. import config, db
from . import dixon_coles

_OUTCOMES = ["H", "D", "A"]


def load_league(league_code: str) -> pd.DataFrame:
    """Load all matches for one league, ordered by date."""
    with db.connect() as conn:
        df = pd.read_sql_query(
            "SELECT date, season, home, away, fthg, ftag, ftr, "
            "xg_h, xg_a, avgh, avgd, avga FROM football_matches "
            "WHERE league_code = ? ORDER BY date",
            conn,
            params=(league_code,),
        )
    return df


def _implied_probs(row: pd.Series) -> dict[str, float] | None:
    """Bookmaker odds -> margin-free probabilities (the 'overround' removed)."""
    o = (row["avgh"], row["avgd"], row["avga"])
    if any(pd.isna(v) or v <= 1.0 for v in o):
        return None
    raw = np.array([1.0 / v for v in o])
    raw /= raw.sum()  # strip the bookmaker margin
    return {k: float(p) for k, p in zip(_OUTCOMES, raw)}


def _log_loss(probs: list[dict[str, float]], actuals: list[str]) -> float:
    eps = 1e-15
    return float(
        -np.mean([np.log(max(p[a], eps)) for p, a in zip(probs, actuals)])
    )


def _brier(probs: list[dict[str, float]], actuals: list[str]) -> float:
    total = 0.0
    for p, a in zip(probs, actuals):
        total += sum((p[k] - (1.0 if k == a else 0.0)) ** 2 for k in _OUTCOMES)
    return float(total / len(probs))


def _accuracy(probs: list[dict[str, float]], actuals: list[str]) -> float:
    hits = sum(max(p, key=p.get) == a for p, a in zip(probs, actuals))
    return hits / len(probs)


def _metrics(probs, actuals) -> dict:
    return {
        "log_loss": _log_loss(probs, actuals),
        "brier": _brier(probs, actuals),
        "accuracy": _accuracy(probs, actuals),
    }


def backtest_season(
    league_code: str,
    target_season: str,
    half_life_days: float | None = 180,
) -> dict:
    """Train on all seasons before `target_season`, score that season.

    Fits two models — one on actual goals, one on xG — and compares both to
    the bookmaker on the same set of matches (those that have closing odds).
    """
    df = load_league(league_code)
    train = df[df["season"] < target_season]
    test = df[(df["season"] == target_season) & df["ftr"].notna()].copy()

    if train.empty or test.empty:
        raise ValueError(
            f"Not enough data: {len(train)} train / {len(test)} test rows"
        )

    ref_date = pd.to_datetime(train["date"]).max()
    goals_model = dixon_coles.fit(
        train, half_life_days=half_life_days, ref_date=ref_date
    )
    xg_model = dixon_coles.fit(
        train, half_life_days=half_life_days, ref_date=ref_date, use_xg=True
    )

    goals_probs, xg_probs, book_probs, actuals = [], [], [], []
    for _, row in test.iterrows():
        bp = _implied_probs(row)
        if bp is None:
            continue  # only score matches the bookmaker also priced
        goals_probs.append(goals_model.predict(row["home"], row["away"]))
        xg_probs.append(xg_model.predict(row["home"], row["away"]))
        book_probs.append(bp)
        actuals.append(row["ftr"])

    return {
        "league": config.FOOTBALL_LEAGUES[league_code],
        "season": target_season,
        "train_matches": len(train),
        "compared_matches": len(actuals),
        "goals_model": _metrics(goals_probs, actuals),
        "xg_model": _metrics(xg_probs, actuals),
        "bookmaker": _metrics(book_probs, actuals),
    }


def _fmt(r: dict) -> str:
    g, x, b = r["goals_model"], r["xg_model"], r["bookmaker"]
    g_gap = g["log_loss"] - b["log_loss"]
    x_gap = x["log_loss"] - b["log_loss"]
    return (
        f"{r['league']:<16} {r['season']}  "
        f"(train {r['train_matches']}, test {r['compared_matches']})\n"
        f"               log loss     brier      accuracy\n"
        f"  goals model  {g['log_loss']:.4f}      {g['brier']:.4f}     {g['accuracy']*100:5.1f}%\n"
        f"  xG model     {x['log_loss']:.4f}      {x['brier']:.4f}     {x['accuracy']*100:5.1f}%\n"
        f"  bookmaker    {b['log_loss']:.4f}      {b['brier']:.4f}     {b['accuracy']*100:5.1f}%\n"
        f"  -> vs bookmaker log-loss:  goals {g_gap:+.4f}   xG {x_gap:+.4f}\n"
    )


def run_all(target_season: str = "2425", half_life_days: float | None = 180) -> None:
    """Backtest every league for the target season and print a comparison."""
    print(f"Backtesting season {target_season} "
          f"(half-life {half_life_days} days)\n" + "=" * 62)
    results = []
    for code in config.FOOTBALL_LEAGUES:
        try:
            r = backtest_season(code, target_season, half_life_days)
            results.append(r)
            print(_fmt(r))
        except ValueError as e:
            print(f"{config.FOOTBALL_LEAGUES[code]}: skipped ({e})\n")

    if results:
        import numpy as np

        def avg(key):
            return np.mean([r[key]["log_loss"] for r in results])

        g, x, b = avg("goals_model"), avg("xg_model"), avg("bookmaker")
        print("=" * 62)
        print("AVERAGE log loss across leagues (lower = better):")
        print(f"  goals model  {g:.4f}   (vs bookmaker {g - b:+.4f})")
        print(f"  xG model     {x:.4f}   (vs bookmaker {x - b:+.4f})")
        print(f"  bookmaker    {b:.4f}")
        better = "xG" if x < g else "goals"
        print(f"\n  -> {better} model has the lower average log loss of the two.")


if __name__ == "__main__":
    run_all()
