"""WNBA helpers: load ESPN-sourced games, fit Elo (same model as the NBA),
rank teams, and list live/upcoming fixtures."""
from __future__ import annotations

import pandas as pd

from .. import db
from . import espn, nba_elo

# ESPN uses a few different abbreviations for the same team across seasons —
# collapse them to one canonical key so a team has a single rating.
_CANON = {"CONN": "CON", "GSV": "GS", "WSH": "WAS"}


def _canon(abbr: str) -> str:
    return _CANON.get(abbr, abbr)


# Canonical abbreviation -> full team name (incl. 2026 expansion sides).
TEAM_NAMES = {
    "ATL": "Atlanta Dream", "CHI": "Chicago Sky", "CON": "Connecticut Sun",
    "DAL": "Dallas Wings", "GS": "Golden State Valkyries", "IND": "Indiana Fever",
    "LA": "Los Angeles Sparks", "LV": "Las Vegas Aces", "MIN": "Minnesota Lynx",
    "NY": "New York Liberty", "PHX": "Phoenix Mercury", "SEA": "Seattle Storm",
    "WAS": "Washington Mystics", "TOR": "Toronto Tempo", "POR": "Portland Fire",
}


def load_games() -> pd.DataFrame:
    with db.connect() as conn:
        df = pd.read_sql_query(
            "SELECT date, season, home, away, home_pts, away_pts "
            "FROM bball_games WHERE league='wnba' ORDER BY date",
            conn,
        )
    df["home"] = df["home"].map(_canon)
    df["away"] = df["away"].map(_canon)
    # Drop All-Star & preseason exhibitions vs national teams (not real WNBA
    # sides) so they don't pollute the ratings.
    known = set(TEAM_NAMES)
    return df[df["home"].isin(known) & df["away"].isin(known)].copy()


def fit_model(games: pd.DataFrame | None = None) -> nba_elo.NBAEloModel:
    return nba_elo.fit(games if games is not None else load_games())


def team_ratings(model: nba_elo.NBAEloModel) -> list[dict]:
    rated = [{"abbr": a, "name": TEAM_NAMES.get(a, a), "elo": round(e, 1)}
             for a, e in model.ratings.items()]
    rated.sort(key=lambda x: -x["elo"])
    return rated


def fixtures(model: nba_elo.NBAEloModel) -> list[dict]:
    names = set(TEAM_NAMES.values())
    return [f for f in espn.fixtures("wnba", model, TEAM_NAMES)
            if f["home"] in names and f["away"] in names]
