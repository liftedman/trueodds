"""NBA helpers: load games, fit the Elo model, rank teams."""

from __future__ import annotations

import pandas as pd

from .. import db
from . import nba_elo

# 3-letter abbreviation -> full team name (for display).
TEAM_NAMES = {
    "ATL": "Atlanta Hawks", "BOS": "Boston Celtics", "BKN": "Brooklyn Nets",
    "CHA": "Charlotte Hornets", "CHI": "Chicago Bulls",
    "CLE": "Cleveland Cavaliers", "DAL": "Dallas Mavericks",
    "DEN": "Denver Nuggets", "DET": "Detroit Pistons",
    "GSW": "Golden State Warriors", "HOU": "Houston Rockets",
    "IND": "Indiana Pacers", "LAC": "LA Clippers", "LAL": "LA Lakers",
    "MEM": "Memphis Grizzlies", "MIA": "Miami Heat", "MIL": "Milwaukee Bucks",
    "MIN": "Minnesota Timberwolves", "NOP": "New Orleans Pelicans",
    "NYK": "New York Knicks", "OKC": "Oklahoma City Thunder",
    "ORL": "Orlando Magic", "PHI": "Philadelphia 76ers", "PHX": "Phoenix Suns",
    "POR": "Portland Trail Blazers", "SAC": "Sacramento Kings",
    "SAS": "San Antonio Spurs", "TOR": "Toronto Raptors", "UTA": "Utah Jazz",
    "WAS": "Washington Wizards",
}


def load_games() -> pd.DataFrame:
    with db.connect() as conn:
        return pd.read_sql_query(
            "SELECT date, season, home, away, home_pts, away_pts "
            "FROM nba_games ORDER BY date",
            conn,
        )


def fit_model(games: pd.DataFrame | None = None) -> nba_elo.NBAEloModel:
    return nba_elo.fit(games if games is not None else load_games())


def team_ratings(model: nba_elo.NBAEloModel) -> list[dict]:
    """All rated teams, ranked by Elo, with full names."""
    rated = [{"abbr": a, "name": TEAM_NAMES.get(a, a), "elo": round(e, 1)}
             for a, e in model.ratings.items()]
    rated.sort(key=lambda x: -x["elo"])
    return rated
