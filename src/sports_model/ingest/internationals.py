"""Ingest international (national-team) results into the database.

Source: Mart Jürisoo's "International football results from 1872 to present"
(github.com/martj42/international_results) — a free, well-maintained CSV with
every recognised international, and crucially the *upcoming* fixtures too (rows
with empty scores). That gives us the World Cup 2026 schedule for free.
"""

from __future__ import annotations

import io

import pandas as pd
import requests

from .. import config, db

_URL = (
    "https://raw.githubusercontent.com/martj42/"
    "international_results/master/results.csv"
)
_TIMEOUT = 60

_INSERT = """
INSERT INTO international_matches
    (date, home, away, home_score, away_score, tournament, neutral)
VALUES
    (:date, :home, :away, :home_score, :away_score, :tournament, :neutral)
ON CONFLICT (date, home, away) DO UPDATE SET
    home_score=excluded.home_score, away_score=excluded.away_score,
    tournament=excluded.tournament, neutral=excluded.neutral
"""


def ingest_all() -> None:
    db.init_db()
    resp = requests.get(_URL, timeout=_TIMEOUT)
    resp.raise_for_status()
    df = pd.read_csv(io.BytesIO(resp.content), encoding="utf-8")

    rows = []
    for _, r in df.iterrows():
        rows.append({
            "date": str(r["date"]),
            "home": str(r["home_team"]).strip(),
            "away": str(r["away_team"]).strip(),
            "home_score": None if pd.isna(r["home_score"]) else int(r["home_score"]),
            "away_score": None if pd.isna(r["away_score"]) else int(r["away_score"]),
            "tournament": str(r["tournament"]).strip(),
            "neutral": 1 if bool(r["neutral"]) else 0,
        })

    with db.connect() as conn:
        conn.executemany(_INSERT, rows)

    played = sum(1 for r in rows if r["home_score"] is not None)
    upcoming = len(rows) - played
    print(f"Ingested {len(rows)} international matches "
          f"({played} played, {upcoming} upcoming) into {config.DB_PATH}")


if __name__ == "__main__":
    ingest_all()
