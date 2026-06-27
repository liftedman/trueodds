"""Honest test: do recent form and head-to-head add predictive value?

The base xG Dixon-Coles model already outputs P(H/D/A). The question is whether
*recent form* and *head-to-head history* carry signal the base model misses.

Method — nested stacking (the standard way to value a feature):
  1. Walk forward season by season. For each season, the base probabilities come
     from a model trained only on earlier seasons (no leakage).
  2. For every match also compute:
       form_diff = home recent points-per-game (last 5) - away recent ppg
       h2h_diff  = (home wins - away wins) in prior meetings / number of meetings
  3. Fit a multinomial logistic regression on the earlier seasons and score the
     held-out latest season, for nested feature sets:
       base            (just the base log-probabilities, recalibrated)
       base + form
       base + h2h
       base + form + h2h
  4. Compare out-of-sample log loss. If a feature helps, it lowers log loss.
     If it doesn't, it doesn't — and that is the honest answer.
"""

from __future__ import annotations

import bisect
from collections import defaultdict

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss
from sklearn.preprocessing import StandardScaler

from .. import config
from . import dixon_coles, evaluate

_OUT = {"H": 0, "D": 1, "A": 2}
_PTS = {"H": (3, 0), "D": (1, 1), "A": (0, 3)}  # (home_points, away_points)


def _build_histories(df: pd.DataFrame):
    """Per-team chronological points list, and per-pair meeting list."""
    team_dates: dict[str, list[str]] = defaultdict(list)
    team_points: dict[str, list[int]] = defaultdict(list)
    meetings: dict[frozenset, list[tuple]] = defaultdict(list)
    for r in df.itertuples(index=False):
        hp, ap = _PTS[r.ftr]
        team_dates[r.home].append(r.date); team_points[r.home].append(hp)
        team_dates[r.away].append(r.date); team_points[r.away].append(ap)
        meetings[frozenset((r.home, r.away))].append((r.date, r.home, r.ftr))
    return team_dates, team_points, meetings


def _form(team, date, team_dates, team_points, n=5):
    """Average points over a team's last `n` matches strictly before `date`."""
    dates = team_dates.get(team, [])
    i = bisect.bisect_left(dates, date)  # matches before today
    if i == 0:
        return 1.0  # neutral prior (~1 ppg) when no history
    pts = team_points[team][max(0, i - n):i]
    return sum(pts) / len(pts)


def _h2h(home, away, date, meetings):
    """(home wins - away wins) / meetings, from the current home team's view."""
    games = meetings.get(frozenset((home, away)), [])
    hw = aw = n = 0
    for d, gh, ftr in games:
        if d >= date:
            continue
        n += 1
        winner = gh if ftr == "H" else (None if ftr == "D" else
                                        (away if gh == home else home))
        if winner == home:
            hw += 1
        elif winner == away:
            aw += 1
    return (hw - aw) / n if n else 0.0


def build_dataset() -> pd.DataFrame:
    rows = []
    for code in config.FOOTBALL_LEAGUES:
        df = evaluate.load_league(code)
        df = df[df["ftr"].notna()].sort_values("date").reset_index(drop=True)
        team_dates, team_points, meetings = _build_histories(df)
        seasons = sorted(df["season"].unique())

        for season in seasons[1:]:  # need prior history to train
            train = df[df["season"] < season]
            ref_date = pd.to_datetime(train["date"]).max()
            model = dixon_coles.fit(train, half_life_days=180,
                                    ref_date=ref_date, use_xg=True)
            test = df[df["season"] == season]
            for r in test.itertuples(index=False):
                p = model.predict(r.home, r.away)
                rows.append({
                    "season": season,
                    "lH": np.log(max(p["H"], 1e-6)),
                    "lD": np.log(max(p["D"], 1e-6)),
                    "lA": np.log(max(p["A"], 1e-6)),
                    "form_diff": _form(r.home, r.date, team_dates, team_points)
                                 - _form(r.away, r.date, team_dates, team_points),
                    "h2h_diff": _h2h(r.home, r.away, r.date, meetings),
                    "y": _OUT[r.ftr],
                })
    return pd.DataFrame(rows)


_BASE = ["lH", "lD", "lA"]
_VARIANTS = {
    "base": _BASE,
    "base + form": _BASE + ["form_diff"],
    "base + h2h": _BASE + ["h2h_diff"],
    "base + form + h2h": _BASE + ["form_diff", "h2h_diff"],
}


def run() -> None:
    data = build_dataset()
    test_season = data["season"].max()
    tr = data[data["season"] < test_season]
    te = data[data["season"] == test_season]
    print(f"Feature value test — train {len(tr)} matches, "
          f"test {len(te)} (season {test_season})\n" + "=" * 60)

    # Reference: the raw base model probabilities, no meta-model at all.
    raw = te[["lH", "lD", "lA"]].to_numpy()
    raw_probs = np.exp(raw) / np.exp(raw).sum(axis=1, keepdims=True)
    raw_ll = log_loss(te["y"], raw_probs, labels=[0, 1, 2])
    print(f"  raw base model (no stacking)   log loss {raw_ll:.4f}\n")

    print(f"  {'stacked model':<22} {'test log loss':>13}  {'vs base'}")
    print("  " + "-" * 50)
    base_ll = None
    for name, feats in _VARIANTS.items():
        scaler = StandardScaler().fit(tr[feats])
        clf = LogisticRegression(max_iter=2000, C=1.0)
        clf.fit(scaler.transform(tr[feats]), tr["y"])
        probs = clf.predict_proba(scaler.transform(te[feats]))
        ll = log_loss(te["y"], probs, labels=[0, 1, 2])
        if base_ll is None:
            base_ll = ll
            delta = ""
        else:
            d = ll - base_ll
            delta = f"{d:+.4f} ({'better' if d < 0 else 'worse'})"
        print(f"  {name:<22} {ll:>13.4f}  {delta}")

    print("\n  Lower is better. If 'form'/'h2h' rows aren't clearly below 'base',")
    print("  those features add no real signal beyond team strength.")


if __name__ == "__main__":
    run()
