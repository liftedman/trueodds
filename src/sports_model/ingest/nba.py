"""Ingest NBA game results via the nba_api package (stats.nba.com).

LeagueGameLog returns one row per team per game. The two rows for a game share
a GAME_ID; the home team's MATCHUP contains 'vs.', the away team's contains '@'.
We pair them into one row per game (teams as 3-letter abbreviations).
"""

from __future__ import annotations

import time

from .. import config, db

# NBA seasons to load (string form the API expects).
NBA_SEASONS = [
    "2019-20", "2020-21", "2021-22", "2022-23",
    "2023-24", "2024-25", "2025-26",
]

_INSERT = """
INSERT INTO nba_games (game_id, date, season, home, away, home_pts, away_pts)
VALUES (:game_id, :date, :season, :home, :away, :home_pts, :away_pts)
ON CONFLICT (game_id) DO UPDATE SET
    home_pts=excluded.home_pts, away_pts=excluded.away_pts
"""


def _season_rows(season: str) -> list[dict]:
    from nba_api.stats.endpoints import leaguegamelog

    gl = leaguegamelog.LeagueGameLog(
        season=season, season_type_all_star="Regular Season", timeout=60)
    df = gl.get_data_frames()[0]

    games: dict[str, dict] = {}
    for r in df.itertuples(index=False):
        gid = r.GAME_ID
        g = games.setdefault(gid, {"game_id": gid, "date": r.GAME_DATE,
                                   "season": season})
        if "vs." in r.MATCHUP:      # home team
            g["home"] = r.TEAM_ABBREVIATION
            g["home_pts"] = int(r.PTS) if r.PTS is not None else None
        else:                        # away team ('@')
            g["away"] = r.TEAM_ABBREVIATION
            g["away_pts"] = int(r.PTS) if r.PTS is not None else None

    # Keep only fully-paired games.
    return [g for g in games.values()
            if {"home", "away"} <= g.keys()]


def ingest_all() -> None:
    db.init_db()
    total = 0
    for season in NBA_SEASONS:
        try:
            rows = _season_rows(season)
        except Exception as e:
            print(f"  skip  {season}: {type(e).__name__}: {e}")
            continue
        with db.connect() as conn:
            conn.executemany(_INSERT, rows)
        total += len(rows)
        print(f"  ok    {season}: {len(rows):>4} games")
        time.sleep(0.6)  # be gentle with stats.nba.com
    print(f"\nDone. {total} NBA games ingested into {config.DB_PATH}")


if __name__ == "__main__":
    ingest_all()
