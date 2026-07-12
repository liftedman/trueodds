"""NBA Summer League (Las Vegas) — ESPN-sourced, same Elo as the NBA.

Honesty note: Summer League squads are rookies/prospects, not real NBA rosters,
and it's only a handful of games, so ratings barely separate and predictions
are near coin-flips. The snapshot flags this league as an exhibition so the app
shows a low-confidence banner.
"""
from __future__ import annotations

import pandas as pd

from .. import db
from . import espn, nba, nba_elo

# ESPN Summer League abbreviation -> full name. Summer teams are the NBA
# franchises (a few ESPN abbrs differ) plus the odd select/international side.
_VARIANT = {"GS": "GSW", "NO": "NOP", "NY": "NYK", "SA": "SAS",
            "UTAH": "UTA", "WSH": "WAS"}
TEAM_NAMES = dict(nba.TEAM_NAMES)
for _espn, _our in _VARIANT.items():
    if _our in nba.TEAM_NAMES:
        TEAM_NAMES[_espn] = nba.TEAM_NAMES[_our]


def load_games() -> pd.DataFrame:
    with db.connect() as conn:
        return pd.read_sql_query(
            "SELECT date, season, home, away, home_pts, away_pts "
            "FROM bball_games WHERE league='summer' ORDER BY date",
            conn,
        )


def fit_model(games: pd.DataFrame | None = None) -> nba_elo.NBAEloModel:
    return nba_elo.fit(games if games is not None else load_games())


def team_ratings(model: nba_elo.NBAEloModel) -> list[dict]:
    rated = [{"abbr": a, "name": TEAM_NAMES.get(a, a), "elo": round(e, 1)}
             for a, e in model.ratings.items()]
    rated.sort(key=lambda x: -x["elo"])
    return rated


def fixtures(model: nba_elo.NBAEloModel) -> list[dict]:
    return espn.fixtures("summer", model, TEAM_NAMES)
