"""Tune the club xG model's time-decay half-life by out-of-sample log loss.

We sweep candidate half-lives, and for each one walk forward across several
test seasons (train only on earlier seasons, predict the held-out one), pool
every prediction across the top-5 leagues, and measure log loss. The half-life
with the lowest pooled log loss is the most accurate — not a betting edge, just
the sharpest honest probabilities the model can give.
"""

from __future__ import annotations

import pandas as pd

from .. import config
from . import dixon_coles, evaluate

_HALF_LIVES = [None, 60, 90, 120, 180, 240, 365, 540]
_TEST_SEASONS = ["2223", "2324", "2425"]


def _pooled_log_loss(half_life, test_seasons) -> tuple[float, int]:
    probs, actuals = [], []
    for code in config.FOOTBALL_LEAGUES:
        df = evaluate.load_league(code)
        df = df[df["ftr"].notna()]
        for season in test_seasons:
            train = df[df["season"] < season]
            test = df[df["season"] == season]
            if train.empty or test.empty:
                continue
            ref_date = pd.to_datetime(train["date"]).max()
            model = dixon_coles.fit(train, half_life_days=half_life,
                                    ref_date=ref_date, use_xg=True)
            for r in test.itertuples(index=False):
                probs.append(model.predict(r.home, r.away))
                actuals.append(r.ftr)
    return evaluate._log_loss(probs, actuals), len(actuals)


def run(test_seasons=None) -> float:
    test_seasons = test_seasons or _TEST_SEASONS
    print(f"Tuning xG half-life on seasons {test_seasons} "
          f"(top-5 leagues, out-of-sample)\n" + "=" * 52)
    print(f"  {'half-life':>12}   {'pooled log loss':>16}")
    print("  " + "-" * 34)
    results = []
    for hl in _HALF_LIVES:
        ll, n = _pooled_log_loss(hl, test_seasons)
        results.append((hl, ll))
        label = "none (flat)" if hl is None else f"{hl} days"
        print(f"  {label:>12}   {ll:>16.4f}")

    best_hl, best_ll = min(results, key=lambda x: x[1])
    label = "none" if best_hl is None else f"{best_hl} days"
    print("  " + "-" * 34)
    print(f"  BEST: {label}  (log loss {best_ll:.4f})")
    print(f"  Current config: {config.XG_HALF_LIFE_DAYS} days")
    return best_hl


if __name__ == "__main__":
    run()
