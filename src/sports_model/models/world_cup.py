"""World Cup helpers: load internationals, fit Elo, predict upcoming fixtures.

Ties the pure Elo model (elo.py) to the database and the specific job of
predicting the 2026 World Cup. Upcoming fixtures come straight from the
ingested dataset (unplayed rows in the 'FIFA World Cup' tournament).
"""

from __future__ import annotations

from datetime import date

import pandas as pd

from .. import db
from . import elo

_WC = "FIFA World Cup"


def load_matches() -> pd.DataFrame:
    with db.connect() as conn:
        return pd.read_sql_query(
            "SELECT date, home, away, home_score, away_score, tournament, "
            "neutral FROM international_matches ORDER BY date",
            conn,
        )


def fit_model(matches: pd.DataFrame | None = None) -> elo.EloModel:
    return elo.fit(matches if matches is not None else load_matches())


def upcoming_fixtures(model: elo.EloModel, limit: int | None = None,
                      today: str | None = None) -> list[dict]:
    """Unplayed World Cup fixtures from today onward, with predictions."""
    today = today or date.today().isoformat()
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT date, home, away, neutral FROM international_matches "
            "WHERE tournament = ? AND home_score IS NULL AND date >= ? "
            "ORDER BY date, home",
            (_WC, today),
        ).fetchall()

    out = []
    for r in rows:
        pred = model.predict(r["home"], r["away"], neutral=bool(r["neutral"]))
        out.append({
            "date": r["date"], "home": r["home"], "away": r["away"],
            "neutral": bool(r["neutral"]), "pred": pred,
        })
    return out[:limit] if limit else out


def wc_team_ratings(model: elo.EloModel, year: int = 2026) -> list[dict]:
    """Ratings for teams involved in this year's World Cup, ranked."""
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT DISTINCT home AS t FROM international_matches "
            "WHERE tournament = ? AND date >= ? "
            "UNION SELECT DISTINCT away FROM international_matches "
            "WHERE tournament = ? AND date >= ?",
            (_WC, f"{year}-01-01", _WC, f"{year}-01-01"),
        ).fetchall()
    teams = sorted({r["t"] for r in rows})
    rated = [{"name": t, "elo": round(model.rating(t), 1)} for t in teams]
    rated.sort(key=lambda x: -x["elo"])
    return rated
