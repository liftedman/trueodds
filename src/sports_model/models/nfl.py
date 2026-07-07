"""NFL helpers: load games, fit the Elo model, rank teams, list fixtures."""
from __future__ import annotations

from datetime import date as _date

import pandas as pd

from .. import db
from . import nfl_elo

# nflverse abbreviation -> full team name.
TEAM_NAMES = {
    "ARI": "Arizona Cardinals", "ATL": "Atlanta Falcons", "BAL": "Baltimore Ravens",
    "BUF": "Buffalo Bills", "CAR": "Carolina Panthers", "CHI": "Chicago Bears",
    "CIN": "Cincinnati Bengals", "CLE": "Cleveland Browns", "DAL": "Dallas Cowboys",
    "DEN": "Denver Broncos", "DET": "Detroit Lions", "GB": "Green Bay Packers",
    "HOU": "Houston Texans", "IND": "Indianapolis Colts", "JAX": "Jacksonville Jaguars",
    "KC": "Kansas City Chiefs", "LA": "Los Angeles Rams", "LAC": "Los Angeles Chargers",
    "LV": "Las Vegas Raiders", "MIA": "Miami Dolphins", "MIN": "Minnesota Vikings",
    "NE": "New England Patriots", "NO": "New Orleans Saints", "NYG": "New York Giants",
    "NYJ": "New York Jets", "PHI": "Philadelphia Eagles", "PIT": "Pittsburgh Steelers",
    "SEA": "Seattle Seahawks", "SF": "San Francisco 49ers", "TB": "Tampa Bay Buccaneers",
    "TEN": "Tennessee Titans", "WAS": "Washington Commanders",
    # legacy codes that appear in older rows
    "OAK": "Las Vegas Raiders", "SD": "Los Angeles Chargers", "STL": "Los Angeles Rams",
}


def load_games() -> pd.DataFrame:
    with db.connect() as conn:
        return pd.read_sql_query(
            "SELECT date, season, week, home, away, home_score, away_score, "
            "neutral, game_type FROM nfl_games ORDER BY date",
            conn,
        )


def fit_model(games: pd.DataFrame | None = None) -> nfl_elo.NFLEloModel:
    return nfl_elo.fit(games if games is not None else load_games())


def team_ratings(model: nfl_elo.NFLEloModel) -> list[dict]:
    """Currently-active teams, ranked by Elo, with full names."""
    rated = [{"abbr": a, "name": TEAM_NAMES.get(a, a), "elo": round(e, 1)}
             for a, e in model.ratings.items()
             # drop relocated legacy codes so we don't list duplicates
             if a not in {"OAK", "SD", "STL"}]
    rated.sort(key=lambda x: -x["elo"])
    return rated


def upcoming_fixtures(model: nfl_elo.NFLEloModel,
                      games: pd.DataFrame | None = None, limit: int = 24) -> list[dict]:
    """Upcoming scheduled games (null scores, future date) with predictions."""
    df = games if games is not None else load_games()
    today = _date.today().isoformat()
    up = df[df["home_score"].isna() & (df["date"] >= today)].sort_values("date")
    out = []
    for r in up.head(limit).itertuples(index=False):
        p = model.predict(r.home, r.away, neutral=bool(r.neutral))
        out.append({
            "date": r.date, "time": "", "live": False,
            "home": TEAM_NAMES.get(r.home, r.home),
            "away": TEAM_NAMES.get(r.away, r.away),
            "home_win": round(p["home_win"], 3),
            "away_win": round(p["away_win"], 3),
            "proj": f"{round(p['proj_home'])}-{round(p['proj_away'])}",
        })
    return out
