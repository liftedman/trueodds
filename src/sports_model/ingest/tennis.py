"""Ingest ATP tennis matches from the Tennismylife/TML-Database mirror.

TML-Database uses Jeff Sackmann's column layout (winner_name / loser_name /
surface / tourney_date) and is live-updated, one CSV per year. We store the
essentials: date, surface, winner, loser, tournament.
"""

from __future__ import annotations

import io

import pandas as pd
import requests

from .. import config, db

_URL = "https://raw.githubusercontent.com/Tennismylife/TML-Database/master/{}.csv"
_YEARS = list(range(2018, 2027))   # 2018 .. 2026
_TIMEOUT = 60

_INSERT = """
INSERT INTO tennis_matches (date, surface, winner, loser, tourney, tour)
VALUES (:date, :surface, :winner, :loser, :tourney, 'atp')
ON CONFLICT (date, winner, loser, tourney) DO NOTHING
"""


def _iso(d) -> str | None:
    s = str(int(d)) if pd.notna(d) else ""
    if len(s) == 8:
        return f"{s[:4]}-{s[4:6]}-{s[6:]}"
    return None


def ingest_all() -> None:
    db.init_db()
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0"})
    total = 0
    for yr in _YEARS:
        try:
            r = session.get(_URL.format(yr), timeout=_TIMEOUT)
            if r.status_code != 200:
                print(f"  skip  {yr}: HTTP {r.status_code}")
                continue
            df = pd.read_csv(io.BytesIO(r.content))
        except Exception as e:
            print(f"  skip  {yr}: {type(e).__name__}")
            continue

        rows = []
        for rr in df.itertuples(index=False):
            date = _iso(getattr(rr, "tourney_date", None))
            w, l = getattr(rr, "winner_name", None), getattr(rr, "loser_name", None)
            if not date or pd.isna(w) or pd.isna(l):
                continue
            rows.append({
                "date": date,
                "surface": (getattr(rr, "surface", None)
                            if pd.notna(getattr(rr, "surface", None)) else None),
                "winner": str(w).strip(), "loser": str(l).strip(),
                "tourney": str(getattr(rr, "tourney_name", "")).strip(),
            })
        with db.connect() as conn:
            conn.executemany(_INSERT, rows)
        total += len(rows)
        print(f"  ok    {yr}: {len(rows):>4} matches")
    print(f"\nDone. {total} tennis matches ingested into {config.DB_PATH}")


if __name__ == "__main__":
    ingest_all()
