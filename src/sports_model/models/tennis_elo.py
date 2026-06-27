"""Surface-aware Elo for ATP tennis.

Tennis suits Elo perfectly: 1-v-1, no draws, lots of matches. Surface matters
enormously (clay specialists vs grass), so alongside an overall rating we keep
a separate rating per surface (Hard / Clay / Grass). A prediction on a given
surface blends the two: half the player's surface rating, half their overall.

No home advantage — matches are at neutral venues.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

_INIT = 1500.0
_K = 32.0
_SURFACE_WEIGHT = 0.5   # blend: 0.5*surface + 0.5*overall
_SURFACES = ("Hard", "Clay", "Grass")


@dataclass
class TennisEloModel:
    overall: dict[str, float]
    surface: dict[str, dict[str, float]]   # {surface: {player: rating}}
    surface_weight: float = _SURFACE_WEIGHT
    _default: float = field(default=_INIT)

    def _blended(self, player: str, surface: str | None) -> float:
        ov = self.overall.get(player, self._default)
        if surface and surface in self.surface:
            sv = self.surface[surface].get(player, ov)
            return self.surface_weight * sv + (1 - self.surface_weight) * ov
        return ov

    def predict(self, a: str, b: str, surface: str | None = None) -> dict:
        ra = self._blended(a, surface)
        rb = self._blended(b, surface)
        pa = 1.0 / (1.0 + 10 ** (-(ra - rb) / 400.0))
        return {"a_win": pa, "b_win": 1.0 - pa,
                "elo_a": self.overall.get(a, self._default),
                "elo_b": self.overall.get(b, self._default)}


def fit(matches: pd.DataFrame) -> TennisEloModel:
    """Fit overall + per-surface Elo from winner/loser match rows."""
    df = matches.sort_values("date")
    overall: dict[str, float] = {}
    surface: dict[str, dict[str, float]] = {s: {} for s in _SURFACES}

    def update(table, w, l):
        rw = table.get(w, _INIT)
        rl = table.get(l, _INIT)
        exp_w = 1.0 / (1.0 + 10 ** (-(rw - rl) / 400.0))
        table[w] = rw + _K * (1.0 - exp_w)
        table[l] = rl - _K * (1.0 - exp_w)

    for r in df.itertuples(index=False):
        w, l = r.winner, r.loser
        update(overall, w, l)
        if r.surface in surface:
            update(surface[r.surface], w, l)

    return TennisEloModel(overall=overall, surface=surface)
