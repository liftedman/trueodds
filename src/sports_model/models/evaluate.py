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


def build_receipts(half_life_days: float | None = None) -> dict | None:
    """A public, out-of-sample track record for the app ("The Receipts").

    For every top league we train on all earlier seasons and grade the model on
    the most recent completed season it never saw. We report how often the pick
    (the favourite) actually won, how well-calibrated those probabilities were,
    and the same numbers for the bookmaker — the honest benchmark.
    """
    half_life_days = half_life_days or config.XG_HALF_LIFE_DAYS
    model_hits: list[tuple[float, bool]] = []   # (prob on our pick, did it win)
    book_hits: list[tuple[float, bool]] = []
    m_probs, b_probs, actuals = [], [], []
    examples: list[dict] = []
    seasons_used: set[str] = set()

    for code in config.FOOTBALL_LEAGUES:
        df = load_league(code)
        seasons = sorted(df["season"].unique())
        if len(seasons) < 2:
            continue
        target = seasons[-1]
        train = df[df["season"] < target]
        test = df[(df["season"] == target) & df["ftr"].notna()]
        if train.empty or test.empty:
            continue
        ref = pd.to_datetime(train["date"]).max()
        model = dixon_coles.fit(train, half_life_days=half_life_days,
                                ref_date=ref, use_xg=True)
        seasons_used.add(target)
        for _, row in test.iterrows():
            bp = _implied_probs(row)
            if bp is None:
                continue
            mp = model.predict(row["home"], row["away"])
            actual = row["ftr"]
            m_probs.append(mp); b_probs.append(bp); actuals.append(actual)
            fav = max(mp, key=mp.get)
            model_hits.append((mp[fav], fav == actual))
            bfav = max(bp, key=bp.get)
            book_hits.append((bp[bfav], bfav == actual))
            name = {"H": row["home"], "A": row["away"], "D": "Draw"}
            examples.append({
                "match": f"{row['home']} v {row['away']}",
                "pick": name[fav],
                "prob": round(mp[fav], 3),
                "score": f"{int(row['fthg'])}-{int(row['ftag'])}",
                "result": name[actual],
                "hit": bool(fav == actual),
            })

    if not model_hits:
        return None

    def hit_rate(rows):
        return round(sum(h for _, h in rows) / len(rows), 4)

    # calibration: bucket by the probability we put on our pick
    buckets = [(0.0, 0.5, "under 50%"), (0.5, 0.6, "50–60%"),
               (0.6, 0.7, "60–70%"), (0.7, 0.8, "70–80%"),
               (0.8, 1.01, "80%+")]
    calib = []
    for lo, hi, label in buckets:
        grp = [(p, h) for p, h in model_hits if lo <= p < hi]
        if not grp:
            continue
        calib.append({
            "label": label,
            "predicted": round(sum(p for p, _ in grp) / len(grp), 4),
            "actual": round(sum(h for _, h in grp) / len(grp), 4),
            "n": len(grp),
        })

    # examples: our 3 most confident correct calls + 1 confident miss (honesty)
    hits = sorted([e for e in examples if e["hit"]],
                  key=lambda e: e["prob"], reverse=True)[:3]
    misses = sorted([e for e in examples if not e["hit"]],
                    key=lambda e: e["prob"], reverse=True)[:1]

    season_label = "/".join(sorted(seasons_used)) if seasons_used else ""
    return {
        "basis": "Top European leagues, most recent completed season, "
                 "out-of-sample (the model never trained on it).",
        "season": season_label,
        "n": len(model_hits),
        "model": {"hit_rate": hit_rate(model_hits),
                  "brier": round(_brier(m_probs, actuals), 4)},
        "bookmaker": {"hit_rate": hit_rate(book_hits),
                      "brier": round(_brier(b_probs, actuals), 4)},
        "calibration": calib,
        "examples": hits + misses,
    }


def _calibration_buckets(hits: list[tuple[float, bool]]) -> list[dict]:
    """Bucket (prob-on-pick, hit) pairs by confidence band."""
    bands = [(0.0, 0.5, "under 50%"), (0.5, 0.6, "50–60%"),
             (0.6, 0.7, "60–70%"), (0.7, 0.8, "70–80%"), (0.8, 1.01, "80%+")]
    out = []
    for lo, hi, label in bands:
        grp = [(p, h) for p, h in hits if lo <= p < hi]
        if not grp:
            continue
        out.append({
            "label": label,
            "predicted": round(sum(p for p, _ in grp) / len(grp), 4),
            "actual": round(sum(h for _, h in grp) / len(grp), 4),
            "n": len(grp),
        })
    return out


def build_wc_receipts(train_before: str = "2022-01-01") -> dict | None:
    """Out-of-sample track record for the World Cup / international model.

    Elo is naturally walk-forward: a team's rating before a match only reflects
    earlier matches. We fit the goal model on matches before `train_before`,
    then walk every match from that date on — predicting each with the ratings
    as they stood *before* it, grading, then updating. No bookmaker exists for
    internationals, so we report hit-rate and calibration only.
    """
    from .. import db
    from . import elo as elo_mod

    with db.connect() as conn:
        df = pd.read_sql_query(
            "SELECT date, home, away, home_score, away_score, tournament, neutral "
            "FROM international_matches WHERE home_score IS NOT NULL ORDER BY date",
            conn,
        )
    if df.empty:
        return None
    df["date"] = pd.to_datetime(df["date"])
    cutoff = pd.Timestamp(train_before)
    train = df[df["date"] < cutoff]
    test = df[df["date"] >= cutoff]
    if len(train) < 1000 or test.empty:
        return None

    base = elo_mod.fit(train)  # goal-model params + ratings as of the cutoff
    ratings = dict(base.ratings)
    model = elo_mod.EloModel(ratings=ratings, sup_slope=base.sup_slope,
                             total_base=base.total_base, total_gap=base.total_gap)

    hits: list[tuple[float, bool]] = []
    wc_examples: list[dict] = []
    for r in test.itertuples(index=False):
        neutral = bool(r.neutral)
        p = model.predict(r.home, r.away, neutral=neutral)
        probs = {"H": p["H"], "D": p["D"], "A": p["A"]}
        hs, as_ = int(r.home_score), int(r.away_score)
        actual = "H" if hs > as_ else ("D" if hs == as_ else "A")
        fav = max(probs, key=probs.get)
        hits.append((probs[fav], fav == actual))
        if (r.tournament or "") == "FIFA World Cup":
            name = {"H": r.home, "A": r.away, "D": "Draw"}
            wc_examples.append({
                "match": f"{r.home} v {r.away}", "pick": name[fav],
                "prob": round(probs[fav], 3), "score": f"{hs}-{as_}",
                "result": name[actual], "hit": bool(fav == actual),
            })
        # carry ratings forward (same update as elo.fit)
        rh, ra = ratings.get(r.home, 1500.0), ratings.get(r.away, 1500.0)
        adv = 0.0 if neutral else elo_mod._HOME_ADV
        dr = rh - ra + adv
        we = 1.0 / (1.0 + 10 ** (-dr / 400.0))
        act = 1.0 if hs > as_ else (0.5 if hs == as_ else 0.0)
        delta = elo_mod._k_factor(r.tournament) * elo_mod._g_mult(hs - as_) * (act - we)
        ratings[r.home] = rh + delta
        ratings[r.away] = ra - delta

    if not hits:
        return None
    # examples: most confident correct World Cup calls + one confident miss
    hitsex = sorted([e for e in wc_examples if e["hit"]],
                    key=lambda e: e["prob"], reverse=True)[:3]
    missex = sorted([e for e in wc_examples if not e["hit"]],
                    key=lambda e: e["prob"], reverse=True)[:1]
    return {
        "basis": "International matches since "
                 f"{cutoff.year}, out-of-sample (the World Cup Elo predicted each "
                 "before it was played). No betting market exists for these.",
        "n": len(hits),
        "hit_rate": round(sum(h for _, h in hits) / len(hits), 4),
        "calibration": _calibration_buckets(hits),
        "examples": hitsex + missex,
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
