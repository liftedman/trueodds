"""Tennis helpers: load matches, fit Elo, list active players with ratings."""

from __future__ import annotations

import pandas as pd

from .. import db
from . import tennis_elo


def load_matches(tour: str = "atp") -> pd.DataFrame:
    with db.connect() as conn:
        return pd.read_sql_query(
            "SELECT date, surface, winner, loser FROM tennis_matches "
            "WHERE tour=? ORDER BY date",
            conn, params=(tour,),
        )


def fit_model(matches: pd.DataFrame | None = None,
              tour: str = "atp") -> tennis_elo.TennisEloModel:
    return tennis_elo.fit(matches if matches is not None else load_matches(tour))


def active_players(model, matches: pd.DataFrame, since: str = "2025-01-01",
                   min_matches: int = 8) -> list[dict]:
    """Players with >= min_matches since `since`, ranked by overall Elo."""
    recent = matches[matches["date"] >= since]
    counts: dict[str, int] = {}
    for r in recent.itertuples(index=False):
        counts[r.winner] = counts.get(r.winner, 0) + 1
        counts[r.loser] = counts.get(r.loser, 0) + 1

    out = []
    for name, n in counts.items():
        if n < min_matches:
            continue
        out.append({
            "name": name,
            "elo": round(model.overall.get(name, 1500.0), 1),
            "hard": round(model.surface["Hard"].get(name, model.overall.get(name, 1500.0)), 1),
            "clay": round(model.surface["Clay"].get(name, model.overall.get(name, 1500.0)), 1),
            "grass": round(model.surface["Grass"].get(name, model.overall.get(name, 1500.0)), 1),
        })
    out.sort(key=lambda x: -x["elo"])
    return out
