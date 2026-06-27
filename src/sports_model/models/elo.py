"""Elo rating model for international football.

Why Elo and not Dixon-Coles here: 200+ national teams that play each other
rarely and irregularly. A goals-based league model needs dense, repeated
fixtures; Elo is built exactly for sparse, head-to-head competition and is the
established standard for international football (the "World Football Elo").

Each team has a rating. After a match the winner takes points from the loser:

    expected_home = 1 / (1 + 10^(-(R_home - R_away + home_adv) / 400))
    R_home += K * G * (actual_home - expected_home)

  - home_adv: Elo points for playing at home (0 at a neutral venue).
  - K: how much a result moves ratings — bigger for the World Cup than a
    friendly (match importance).
  - G: goal-difference multiplier — blowouts move ratings more.

To turn a rating gap into Home/Draw/Away probabilities we fit a draw model
(`P(draw)` shrinks as the gap grows) from the historical results themselves,
then split the Elo expectation around it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy.special import gammaln

_INIT_RATING = 1500.0
_HOME_ADV = 100.0  # Elo points for a non-neutral home venue
_MAXG = 10         # max goals per side in the scoreline grid


def _k_factor(tournament: str) -> float:
    t = tournament or ""
    if t == "FIFA World Cup":
        return 60.0
    if "World Cup" in t:  # qualification
        return 50.0
    if any(x in t for x in (
        "UEFA Euro", "Copa Am", "African Cup of Nations", "AFC Asian Cup",
        "Gold Cup", "Confederations", "UEFA Nations",
    )):
        return 50.0 if "qualif" not in t.lower() else 40.0
    if "Friendly" in t:
        return 20.0
    return 30.0


def _g_mult(goal_diff: int) -> float:
    gd = abs(goal_diff)
    if gd <= 1:
        return 1.0
    if gd == 2:
        return 1.5
    return (11 + gd) / 8.0


@dataclass
class EloModel:
    ratings: dict[str, float]
    home_adv: float = _HOME_ADV
    # Goal model derived from the rating gap:
    #   expected supremacy (home - away goals) = sup_slope * rating_gap
    #   expected total goals = total_base + total_gap * |rating_gap|
    # Total rises with the mismatch (favourites pile them on), so Over/Under
    # actually varies by fixture instead of being constant.
    sup_slope: float = 0.0024
    total_base: float = 2.60
    total_gap: float = 0.0010
    _default: float = field(default=_INIT_RATING)

    def rating(self, team: str) -> float:
        return self.ratings.get(team, self._default)

    def expected_goals(self, home: str, away: str,
                       neutral: bool = True) -> tuple[float, float]:
        adv = 0.0 if neutral else self.home_adv
        dr = self.rating(home) - self.rating(away) + adv
        total = max(1.2, self.total_base + self.total_gap * abs(dr))
        sup = self.sup_slope * dr
        lam_h = max(0.12, (total + sup) / 2.0)
        lam_a = max(0.12, (total - sup) / 2.0)
        return lam_h, lam_a

    def score_matrix(self, home: str, away: str, neutral: bool = True) -> np.ndarray:
        lam_h, lam_a = self.expected_goals(home, away, neutral)
        goals = np.arange(0, _MAXG + 1)
        ph = np.exp(goals * np.log(lam_h) - lam_h - gammaln(goals + 1))
        pa = np.exp(goals * np.log(lam_a) - lam_a - gammaln(goals + 1))
        mat = np.outer(ph, pa)
        return mat / mat.sum()

    def predict(self, home: str, away: str, neutral: bool = True) -> dict:
        mat = self.score_matrix(home, away, neutral)
        return {
            "H": float(np.tril(mat, -1).sum()),
            "D": float(np.trace(mat)),
            "A": float(np.triu(mat, 1).sum()),
            "elo_home": self.rating(home),
            "elo_away": self.rating(away),
        }

    def predict_totals(self, home: str, away: str, neutral: bool = True,
                       line: float = 2.5) -> dict:
        mat = self.score_matrix(home, away, neutral)
        totals = np.add.outer(np.arange(mat.shape[0]), np.arange(mat.shape[1]))
        return {"OV": float(mat[totals > line].sum()),
                "UN": float(mat[totals < line].sum())}


def fit(matches: pd.DataFrame) -> EloModel:
    """Fit Elo ratings + draw model from played international matches.

    matches: rows with home, away, home_score, away_score, tournament, neutral.
             Unplayed fixtures (NULL scores) are ignored for fitting.
    """
    played = matches.dropna(subset=["home_score", "away_score"]).copy()
    played = played.sort_values("date")

    ratings: dict[str, float] = {}
    dr_list: list[float] = []      # pre-match rating gap (incl. home adv)
    sup_list: list[int] = []       # actual goal supremacy (home - away)
    total_list: list[int] = []     # actual total goals

    for r in played.itertuples(index=False):
        h, a = r.home, r.away
        rh = ratings.get(h, _INIT_RATING)
        ra = ratings.get(a, _INIT_RATING)
        adv = 0.0 if r.neutral else _HOME_ADV
        dr = rh - ra + adv
        we = 1.0 / (1.0 + 10 ** (-dr / 400.0))

        hs, as_ = int(r.home_score), int(r.away_score)
        if hs > as_:
            actual = 1.0
        elif hs == as_:
            actual = 0.5
        else:
            actual = 0.0

        k = _k_factor(r.tournament)
        g = _g_mult(hs - as_)
        delta = k * g * (actual - we)
        ratings[h] = rh + delta
        ratings[a] = ra - delta

        dr_list.append(dr)
        sup_list.append(hs - as_)
        total_list.append(hs + as_)

    # Goal model: regress actual supremacy on the rating gap (through origin),
    # and take the mean total goals. Use only recent-era data weighting via the
    # full history (simple, robust).
    dr_arr = np.array(dr_list, dtype=float)
    sup_arr = np.array(sup_list, dtype=float)
    total_arr = np.array(total_list, dtype=float)

    # Supremacy vs rating gap (through origin).
    denom = float(np.sum(dr_arr * dr_arr))
    sup_slope = float(np.sum(dr_arr * sup_arr) / denom) if denom > 0 else 0.0024

    # Total goals vs |rating gap| (linear with intercept).
    if len(dr_arr) > 10:
        slope, intercept = np.polyfit(np.abs(dr_arr), total_arr, 1)
        total_base, total_gap = float(intercept), float(slope)
    else:
        total_base, total_gap = 2.60, 0.0010

    return EloModel(ratings=ratings, sup_slope=sup_slope,
                    total_base=total_base, total_gap=total_gap)
