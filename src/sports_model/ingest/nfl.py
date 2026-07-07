"""Ingest NFL games + schedule from the nflverse dataset (Lee Sharpe's games.csv).

One CSV holds every game since 1999 *and* the current season's upcoming
schedule (future games have blank scores) — like the international results file,
so it feeds both the Elo ratings and the fixtures list with no API key.
"""
from __future__ import annotations

import csv
import io

import requests

from .. import config, db

_URL = "https://raw.githubusercontent.com/nflverse/nfldata/master/data/games.csv"
_TIMEOUT = 60

_INSERT = """
INSERT INTO nfl_games
    (game_id, date, season, week, game_type, home, away, home_score, away_score, neutral)
VALUES
    (:game_id, :date, :season, :week, :game_type, :home, :away, :home_score, :away_score, :neutral)
ON CONFLICT (game_id) DO UPDATE SET
    date=excluded.date, week=excluded.week, game_type=excluded.game_type,
    home_score=excluded.home_score, away_score=excluded.away_score,
    neutral=excluded.neutral
"""


def _int(v: str | None) -> int | None:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def ingest_all() -> None:
    db.init_db()
    resp = requests.get(_URL, timeout=_TIMEOUT)
    resp.raise_for_status()
    rows = list(csv.DictReader(io.StringIO(resp.text)))

    records, upcoming = [], 0
    for x in rows:
        gid = x.get("game_id")
        home, away = x.get("home_team"), x.get("away_team")
        if not gid or not home or not away:
            continue
        hs, as_ = _int(x.get("home_score")), _int(x.get("away_score"))
        if hs is None or as_ is None:
            upcoming += 1
        records.append({
            "game_id": gid,
            "date": x.get("gameday"),
            "season": _int(x.get("season")),
            "week": _int(x.get("week")),
            "game_type": x.get("game_type"),
            "home": home,
            "away": away,
            "home_score": hs,
            "away_score": as_,
            "neutral": 1 if x.get("location") == "Neutral" else 0,
        })

    with db.connect() as conn:
        conn.executemany(_INSERT, records)

    print(f"Ingested {len(records)} NFL games "
          f"({len(records) - upcoming} played, {upcoming} upcoming) "
          f"into {config.DB_PATH}")


if __name__ == "__main__":
    ingest_all()
