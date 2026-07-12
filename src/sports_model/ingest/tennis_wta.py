"""Ingest WTA tennis matches from tennis-data.co.uk (one Excel file per year).

Sackmann's WTA files aren't reachable from here, so we use tennis-data.co.uk,
which publishes WTA results (with odds) as .xlsx. Columns differ from the ATP
mirror: Date, Surface, Winner, Loser, Tournament (players as "Surname I.").
Stored in tennis_matches with tour='wta'.
"""
from __future__ import annotations

import io

import pandas as pd
import requests

from .. import config, db

_URL = "http://www.tennis-data.co.uk/{yr}w/{yr}.xlsx"
_YEARS = list(range(2018, 2027))
_TIMEOUT = 60

_INSERT = """
INSERT INTO tennis_matches (date, surface, winner, loser, tourney, tour)
VALUES (:date, :surface, :winner, :loser, :tourney, 'wta')
ON CONFLICT (date, winner, loser, tourney) DO NOTHING
"""

_SURFACES = {"Hard", "Clay", "Grass"}


def _iso(d) -> str | None:
    try:
        return pd.to_datetime(d).strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        return None


def ingest_all() -> None:
    db.init_db()
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0"})
    total = 0
    for yr in _YEARS:
        try:
            r = session.get(_URL.format(yr=yr), timeout=_TIMEOUT)
            if r.status_code != 200:
                print(f"  skip  {yr}: HTTP {r.status_code}")
                continue
            df = pd.read_excel(io.BytesIO(r.content))
        except Exception as e:
            print(f"  skip  {yr}: {type(e).__name__}: {e}")
            continue

        rows = []
        for rr in df.itertuples(index=False):
            date = _iso(getattr(rr, "Date", None))
            w, l = getattr(rr, "Winner", None), getattr(rr, "Loser", None)
            if not date or pd.isna(w) or pd.isna(l):
                continue
            surf = getattr(rr, "Surface", None)
            surf = surf if surf in _SURFACES else ("Hard" if surf == "Carpet" else None)
            rows.append({
                "date": date, "surface": surf,
                "winner": str(w).strip(), "loser": str(l).strip(),
                "tourney": str(getattr(rr, "Tournament", "")).strip(),
            })
        with db.connect() as conn:
            conn.executemany(_INSERT, rows)
        total += len(rows)
        print(f"  ok    {yr}: {len(rows):>4} matches")
    print(f"\nDone. {total} WTA matches ingested into {config.DB_PATH}")


if __name__ == "__main__":
    ingest_all()
