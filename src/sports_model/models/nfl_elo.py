"""Elo rating model for the NFL.

Same Elo backbone as the NBA model, tuned for pro football:
  - Ties are possible (rare) and count as a half-result.
  - Ratings regress ~1/3 toward the mean between seasons (rosters, draft, free
    agency) — the established NFL-Elo carryover.
  - A projected score comes from the rating gap: expected margin scales with the
    gap, plus the league's average total points.

Home-field advantage is a fixed Elo bonus; K controls how fast ratings move.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

_INIT = 1500.0
_HOME_ADV = 55.0    # Elo points for home field (~2.3 pts)
_K = 20.0
_CARRY = 0.67       # season-to-season carryover (regress ~1/3 to the mean)


@dataclass
class NFLEloModel:
    ratings: dict[str, float]
    home_adv: float = _HOME_ADV
    margin_slope: float = 0.045     # points of margin per Elo point (fit)
    mean_total: float = 45.0        # league average total points (fit)
    margin_std: float = 13.5        # spread of actual vs predicted margin (fit)
    total_std: float = 14.0         # spread of total points (fit)
    _default: float = field(default=_INIT)

    def rating(self, team: str) -> float:
        return self.ratings.get(team, self._default)

    def predict(self, home: str, away: str, neutral: bool = False) -> dict:
        adv = 0.0 if neutral else self.home_adv
        dr = self.rating(home) - self.rating(away) + adv
        p_home = 1.0 / (1.0 + 10 ** (-dr / 400.0))
        margin = self.margin_slope * dr
        return {
            "home_win": p_home, "away_win": 1.0 - p_home,
            "proj_home": (self.mean_total + margin) / 2.0,
            "proj_away": (self.mean_total - margin) / 2.0,
            "elo_home": self.rating(home), "elo_away": self.rating(away),
        }

    def cover_prob(self, home: str, away: str, line: float,
                   neutral: bool = False) -> float:
        """P(home margin > line). line = -3.5 means home wins by 4+."""
        dr = self.rating(home) - self.rating(away) + (0.0 if neutral else self.home_adv)
        margin = self.margin_slope * dr
        z = (-line - margin) / self.margin_std
        return 1.0 - 0.5 * (1.0 + math.erf(z / math.sqrt(2)))

    def total_over_prob(self, home: str, away: str, line: float) -> float:
        z = (line - self.mean_total) / self.total_std
        return 1.0 - 0.5 * (1.0 + math.erf(z / math.sqrt(2)))


def fit(games: pd.DataFrame) -> NFLEloModel:
    """Fit NFL Elo + projected-score params from played games.

    games: rows with date, season, home, away, home_score, away_score.
    """
    df = games.dropna(subset=["home_score", "away_score"]).copy()
    df = df.sort_values("date")

    ratings: dict[str, float] = {}
    prev_season = None
    dr_list, margin_list, total_list = [], [], []

    for r in df.itertuples(index=False):
        if r.season != prev_season and prev_season is not None:
            for t in ratings:
                ratings[t] = _INIT + _CARRY * (ratings[t] - _INIT)
        prev_season = r.season

        rh = ratings.get(r.home, _INIT)
        ra = ratings.get(r.away, _INIT)
        dr = rh - ra + _HOME_ADV
        exp_home = 1.0 / (1.0 + 10 ** (-dr / 400.0))

        hp, ap = int(r.home_score), int(r.away_score)
        actual = 1.0 if hp > ap else (0.5 if hp == ap else 0.0)
        delta = _K * (actual - exp_home)
        ratings[r.home] = rh + delta
        ratings[r.away] = ra - delta

        dr_list.append(dr)
        margin_list.append(hp - ap)
        total_list.append(hp + ap)

    dr_arr = np.array(dr_list, dtype=float)
    margin_arr = np.array(margin_list, dtype=float)
    denom = float(np.sum(dr_arr * dr_arr))
    margin_slope = float(np.sum(dr_arr * margin_arr) / denom) if denom else 0.045
    mean_total = float(np.mean(total_list)) if total_list else 45.0
    resid = margin_arr - margin_slope * dr_arr
    margin_std = max(float(np.std(resid)), 1.0) if len(resid) > 1 else 13.5
    total_std = max(float(np.std(np.array(total_list))), 1.0) if len(total_list) > 1 else 14.0

    return NFLEloModel(ratings=ratings, margin_slope=margin_slope,
                       mean_total=mean_total, margin_std=margin_std,
                       total_std=total_std)
