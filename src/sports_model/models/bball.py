"""Generic ESPN-sourced basketball league (NBL, NCAA, …) for the hub.

Team names come from the bball_teams table (captured at ingest), so a league
needs no hardcoded roster map — it just works once its games are ingested.
NBA/WNBA/Summer keep their own modules (league-specific quirks); this covers
the rest.
"""
from __future__ import annotations

import pandas as pd

from .. import db
from . import espn, nba_elo


def team_names(league: str) -> dict[str, str]:
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT abbr, name FROM bball_teams WHERE league=?", (league,)
        ).fetchall()
    return {r["abbr"]: r["name"] for r in rows}


def load_games(league: str) -> pd.DataFrame:
    with db.connect() as conn:
        return pd.read_sql_query(
            "SELECT date, season, home, away, home_pts, away_pts "
            "FROM bball_games WHERE league=? ORDER BY date",
            conn, params=(league,),
        )


def fit_model(league: str) -> nba_elo.NBAEloModel:
    return nba_elo.fit(load_games(league))


def team_ratings(model: nba_elo.NBAEloModel, league: str) -> list[dict]:
    names = team_names(league)
    rated = [{"abbr": a, "name": names.get(a, a), "elo": round(e, 1)}
             for a, e in model.ratings.items()]
    rated.sort(key=lambda x: -x["elo"])
    return rated


def fixtures(league: str, model: nba_elo.NBAEloModel) -> list[dict]:
    return espn.fixtures(league, model, team_names(league))
