"""Elo rating model for the NBA.

Same Elo backbone as the international model, with basketball specifics:
  - No draws: outcomes are just home win / away win.
  - Ratings regress 25% toward the mean between seasons (rosters change), the
    standard approach for carrying NBA strength across years.
  - A projected score is derived from the rating gap: expected margin scales
    with the gap, and we add the league's average total points.

Home-court advantage is a fixed Elo bonus. K controls how fast ratings move.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

_INIT = 1500.0
_HOME_ADV = 100.0     # Elo points for home court
_K = 20.0
_CARRY = 0.75         # season-to-season rating carryover (regress 25% to mean)


@dataclass
class NBAEloModel:
    ratings: dict[str, float]
    home_adv: float = _HOME_ADV
    margin_slope: float = 0.04      # points of margin per Elo point (fit)
    mean_total: float = 225.0       # league average total points (fit)
    margin_std: float = 13.5        # spread of actual vs predicted margin (fit)
    total_std: float = 20.0         # spread of total points (fit)
    _default: float = field(default=_INIT)

    def rating(self, team: str) -> float:
        return self.ratings.get(team, self._default)

    def predict(self, home: str, away: str, neutral: bool = False) -> dict:
        adv = 0.0 if neutral else self.home_adv
        dr = self.rating(home) - self.rating(away) + adv
        p_home = 1.0 / (1.0 + 10 ** (-dr / 400.0))
        margin = self.margin_slope * dr            # expected home - away points
        proj_home = (self.mean_total + margin) / 2.0
        proj_away = (self.mean_total - margin) / 2.0
        return {
            "home_win": p_home, "away_win": 1.0 - p_home,
            "proj_home": proj_home, "proj_away": proj_away,
            "elo_home": self.rating(home), "elo_away": self.rating(away),
        }

    def cover_prob(self, home: str, away: str, line: float,
                   neutral: bool = False) -> float:
        """P(home margin > line). line = -5.5 means home wins by 6+."""
        import math
        dr = self.rating(home) - self.rating(away) + (0.0 if neutral else self.home_adv)
        margin = self.margin_slope * dr
        z = (-line - margin) / self.margin_std
        return 1.0 - 0.5 * (1.0 + math.erf(z / math.sqrt(2)))

    def total_over_prob(self, home: str, away: str, line: float) -> float:
        """P(total points > line)."""
        import math
        z = (line - self.mean_total) / self.total_std
        return 1.0 - 0.5 * (1.0 + math.erf(z / math.sqrt(2)))


def fit(games: pd.DataFrame) -> NBAEloModel:
    """Fit NBA Elo + projected-score params from played games.

    games: rows with date, season, home, away, home_pts, away_pts.
    """
    df = games.dropna(subset=["home_pts", "away_pts"]).copy()
    df = df.sort_values("date")

    ratings: dict[str, float] = {}
    prev_season = None
    dr_list, margin_list, total_list = [], [], []

    for r in df.itertuples(index=False):
        if r.season != prev_season and prev_season is not None:
            # New season: regress all ratings toward the mean.
            for t in ratings:
                ratings[t] = _INIT + _CARRY * (ratings[t] - _INIT)
        prev_season = r.season

        rh = ratings.get(r.home, _INIT)
        ra = ratings.get(r.away, _INIT)
        dr = rh - ra + _HOME_ADV
        exp_home = 1.0 / (1.0 + 10 ** (-dr / 400.0))

        hp, ap = int(r.home_pts), int(r.away_pts)
        actual = 1.0 if hp > ap else 0.0
        delta = _K * (actual - exp_home)
        ratings[r.home] = rh + delta
        ratings[r.away] = ra - delta

        dr_list.append(dr)
        margin_list.append(hp - ap)
        total_list.append(hp + ap)

    dr_arr = np.array(dr_list, dtype=float)
    margin_arr = np.array(margin_list, dtype=float)
    denom = float(np.sum(dr_arr * dr_arr))
    margin_slope = float(np.sum(dr_arr * margin_arr) / denom) if denom else 0.04
    mean_total = float(np.mean(total_list)) if total_list else 225.0
    # Spread of outcomes around the predictions -> for spread/total markets.
    resid = margin_arr - margin_slope * dr_arr
    # Floor the spreads so degenerate inputs never divide by zero.
    margin_std = max(float(np.std(resid)), 1.0) if len(resid) > 1 else 13.5
    total_std = max(float(np.std(np.array(total_list))), 1.0) if len(total_list) > 1 else 20.0

    return NBAEloModel(ratings=ratings, margin_slope=margin_slope,
                       mean_total=mean_total, margin_std=margin_std,
                       total_std=total_std)
