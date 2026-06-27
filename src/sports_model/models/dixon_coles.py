"""Dixon-Coles football model.

A Poisson goals model with the Dixon & Coles (1997) low-score correction.

The idea, plainly:
  - Every team has an ATTACK strength and a DEFENCE strength.
  - Playing at home is worth a fixed bonus (HOME ADVANTAGE).
  - Expected home goals  = exp(attack[home] + defence[away] + home_adv)
  - Expected away goals  = exp(attack[away] + defence[home])
  - Goals are ~Poisson around those expectations, with a small correction
    (rho) for 0-0, 1-0, 0-1, 1-1 results, which plain Poisson gets wrong.

We fit all those strengths at once by maximum likelihood (find the numbers
that make the observed scorelines most probable). Then for any fixture we
build a grid of scoreline probabilities and sum them into P(home win),
P(draw), P(away win).

Coming from Go: `fit()` returns a `DixonColesModel` dataclass (like a struct)
holding the fitted parameters; `model.predict(home, away)` is a method on it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import gammaln

# Max goals per team when building the scoreline grid for prediction.
# 10 is plenty — P(a team scores >10) is vanishingly small.
_MAX_GOALS = 10


def _tau(home_goals, away_goals, lam_h, lam_a, rho):
    """Dixon-Coles low-score correction factor (vectorised).

    Adjusts the four low-scoring cells; returns 1.0 everywhere else.
    """
    out = np.ones_like(lam_h, dtype=float)
    h0 = home_goals == 0
    h1 = home_goals == 1
    a0 = away_goals == 0
    a1 = away_goals == 1
    out[h0 & a0] = 1.0 - lam_h[h0 & a0] * lam_a[h0 & a0] * rho
    out[h0 & a1] = 1.0 + lam_h[h0 & a1] * rho
    out[h1 & a0] = 1.0 + lam_a[h1 & a0] * rho
    out[h1 & a1] = 1.0 - rho
    return out


@dataclass
class DixonColesModel:
    teams: list[str]
    attack: dict[str, float]
    defence: dict[str, float]
    home_adv: float
    rho: float
    # Means used as a fallback for teams unseen in training (e.g. promoted sides).
    _mean_attack: float = field(default=0.0)
    _mean_defence: float = field(default=0.0)

    def _strength(self, team: str) -> tuple[float, float]:
        """Return (attack, defence) for a team, falling back to league mean."""
        return (
            self.attack.get(team, self._mean_attack),
            self.defence.get(team, self._mean_defence),
        )

    def expected_goals(self, home: str, away: str) -> tuple[float, float]:
        ah, dh = self._strength(home)
        aa, da = self._strength(away)
        lam_h = np.exp(ah + da + self.home_adv)
        lam_a = np.exp(aa + dh)
        return float(lam_h), float(lam_a)

    def score_matrix(self, home: str, away: str) -> np.ndarray:
        """Normalised scoreline probability matrix: mat[i,j]=P(home i, away j)."""
        lam_h, lam_a = self.expected_goals(home, away)

        goals = np.arange(0, _MAX_GOALS + 1)
        # Poisson pmf for each goal count.
        ph = np.exp(goals * np.log(lam_h) - lam_h - gammaln(goals + 1))
        pa = np.exp(goals * np.log(lam_a) - lam_a - gammaln(goals + 1))

        # Outer product -> matrix[i, j] = P(home i goals, away j goals).
        mat = np.outer(ph, pa)

        # Apply the low-score correction to the 2x2 corner.
        for i in range(2):
            for j in range(2):
                mat[i, j] *= _single_tau(i, j, lam_h, lam_a, self.rho)

        mat /= mat.sum()  # renormalise after correction
        return mat

    def predict(self, home: str, away: str) -> dict[str, float]:
        """Return {'H':p, 'D':p, 'A':p} for a fixture."""
        mat = self.score_matrix(home, away)
        home_win = np.tril(mat, -1).sum()  # home goals > away goals
        draw = np.trace(mat)
        away_win = np.triu(mat, 1).sum()
        return {"H": float(home_win), "D": float(draw), "A": float(away_win)}

    def predict_totals(self, home: str, away: str,
                       line: float = 2.5) -> dict[str, float]:
        """Return {'OV':p, 'UN':p} for total goals over/under `line`.

        The scoreline grid already encodes the full distribution of total
        goals, so this is just summing the right cells. For line 2.5: OVER
        means 3+ total goals, UNDER means 0-2.
        """
        mat = self.score_matrix(home, away)
        totals = np.add.outer(
            np.arange(mat.shape[0]), np.arange(mat.shape[1])
        )
        over = float(mat[totals > line].sum())
        under = float(mat[totals < line].sum())
        return {"OV": over, "UN": under}


def _single_tau(x: int, y: int, lam_h: float, lam_a: float, rho: float) -> float:
    if x == 0 and y == 0:
        return 1.0 - lam_h * lam_a * rho
    if x == 0 and y == 1:
        return 1.0 + lam_h * rho
    if x == 1 and y == 0:
        return 1.0 + lam_a * rho
    if x == 1 and y == 1:
        return 1.0 - rho
    return 1.0


def fit(
    matches: pd.DataFrame,
    half_life_days: float | None = None,
    ref_date: pd.Timestamp | None = None,
    use_xg: bool = False,
) -> DixonColesModel:
    """Fit the model by maximum likelihood.

    matches: DataFrame with columns home, away, fthg, ftag (and xg_h, xg_a if
             use_xg), plus date if using time decay.
    half_life_days: if set, older matches count less. A match `half_life_days`
             old has half the weight of today's. None = all matches equal.
    ref_date: the "today" that decay is measured from (defaults to the latest
             match date in the data).
    use_xg: fit team strengths to expected goals (xg_h/xg_a) instead of actual
             goals. xG is a lower-noise signal of underlying performance. When
             True the low-score (rho) correction is disabled — it only makes
             sense for integer scorelines.
    """
    home_col, away_col = ("xg_h", "xg_a") if use_xg else ("fthg", "ftag")
    df = matches.dropna(subset=[home_col, away_col]).copy()

    teams = sorted(set(df["home"]) | set(df["away"]))
    idx = {t: i for i, t in enumerate(teams)}
    n = len(teams)

    home_i = df["home"].map(idx).to_numpy()
    away_i = df["away"].map(idx).to_numpy()
    # Response values: integer goals or continuous xG. The Poisson-rate
    # likelihood y*log(mu) - mu works for non-integer y too (quasi-Poisson);
    # the factorial term is constant w.r.t. parameters so we omit it entirely.
    hg = df[home_col].to_numpy(dtype=float)
    ag = df[away_col].to_numpy(dtype=float)

    # Time-decay weights.
    if half_life_days:
        dates = pd.to_datetime(df["date"])
        ref = ref_date if ref_date is not None else dates.max()
        age_days = (ref - dates).dt.days.to_numpy().astype(float)
        decay = np.log(2) / half_life_days
        weights = np.exp(-decay * age_days)
    else:
        weights = np.ones(len(df))

    # Parameter vector layout: [attack(n), defence(n), home_adv, rho]
    def unpack(p):
        return p[:n], p[n : 2 * n], p[2 * n], p[2 * n + 1]

    def neg_log_likelihood(p):
        attack, defence, home_adv, rho = unpack(p)
        log_lam_h = attack[home_i] + defence[away_i] + home_adv
        log_lam_a = attack[away_i] + defence[home_i]
        lam_h = np.exp(log_lam_h)
        lam_a = np.exp(log_lam_a)

        # Poisson-rate log-likelihood (factorial term omitted — it's constant).
        ll = (hg * log_lam_h - lam_h) + (ag * log_lam_a - lam_a)
        # Low-score correction applies only to integer scorelines.
        if not use_xg:
            tau = _tau(hg, ag, lam_h, lam_a, rho)
            tau = np.clip(tau, 1e-10, None)
            ll = ll + np.log(tau)

        return -np.sum(weights * ll)

    # Sensible starting point: zero strengths, mild home advantage, no rho.
    x0 = np.concatenate([np.zeros(n), np.zeros(n), [0.25], [0.0]])
    # When using xG, pin rho to 0 (the correction is disabled).
    rho_bounds = (0.0, 0.0) if use_xg else (-0.2, 0.2)
    bounds = [(-3, 3)] * n + [(-3, 3)] * n + [(-1, 1), rho_bounds]

    res = minimize(neg_log_likelihood, x0, method="L-BFGS-B", bounds=bounds)

    attack, defence, home_adv, rho = unpack(res.x)
    return DixonColesModel(
        teams=teams,
        attack={t: float(attack[i]) for t, i in idx.items()},
        defence={t: float(defence[i]) for t, i in idx.items()},
        home_adv=float(home_adv),
        rho=float(rho),
        _mean_attack=float(np.mean(attack)),
        _mean_defence=float(np.mean(defence)),
    )
