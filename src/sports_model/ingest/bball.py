"""Ingest basketball results from ESPN's public scoreboard (WNBA, extensible).

ESPN caps a scoreboard query at 100 events, so we page month-by-month over a
window of past months. Finished games (with scores) are stored in bball_games;
the Elo model and live fixtures are built from the same ESPN source.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

import requests

from .. import config, db

_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/{path}/scoreboard"
_TIMEOUT = 20

# league key -> ESPN path. (NBA stays on nba_api / nba_games; this is for the
# ESPN-sourced leagues.)
LEAGUES = {"wnba": "wnba"}

_INSERT = """
INSERT INTO bball_games (league, game_id, date, season, home, away, home_pts, away_pts)
VALUES (:league, :game_id, :date, :season, :home, :away, :home_pts, :away_pts)
ON CONFLICT (league, game_id) DO UPDATE SET
    home_pts=excluded.home_pts, away_pts=excluded.away_pts
"""


def _months_back(n: int) -> list[tuple[str, str]]:
    """Return (first, last) YYYYMMDD strings for each of the last n months."""
    out = []
    today = date.today()
    y, m = today.year, today.month
    for _ in range(n):
        first = date(y, m, 1)
        last = date(y + (m // 12), (m % 12) + 1, 1)  # first of next month
        # step back to the actual last day by using next-month-first - 1 day
        from datetime import timedelta
        last = last - timedelta(days=1)
        out.append((first.strftime("%Y%m%d"), last.strftime("%Y%m%d")))
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    return out


def _fetch_month(session, path: str, lo: str, hi: str) -> list[dict]:
    try:
        r = session.get(_URL.format(path=path), params={"dates": f"{lo}-{hi}"},
                        timeout=_TIMEOUT)
        r.raise_for_status()
        return r.json().get("events", [])
    except (requests.RequestException, ValueError):
        return []


def ingest_league(league: str, months: int = 16) -> int:
    db.init_db()
    path = LEAGUES[league]
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0"})

    rows: dict[str, dict] = {}
    for lo, hi in _months_back(months):
        for ev in _fetch_month(session, path, lo, hi):
            state = (ev.get("status", {}).get("type", {}) or {}).get("state")
            if state != "post":
                continue  # only completed games make ratings
            try:
                comp = ev["competitions"][0]
                cs = comp["competitors"]
                home = next(c for c in cs if c.get("homeAway") == "home")
                away = next(c for c in cs if c.get("homeAway") == "away")
                hp = int(home.get("score"))
                ap = int(away.get("score"))
            except (KeyError, IndexError, StopIteration, TypeError, ValueError):
                continue
            d = (ev.get("date") or "")[:10]
            season = int(d[:4]) if d[:4].isdigit() else date.today().year
            rows[ev["id"]] = {
                "league": league, "game_id": ev["id"], "date": d, "season": season,
                "home": home["team"]["abbreviation"],
                "away": away["team"]["abbreviation"],
                "home_pts": hp, "away_pts": ap,
            }

    with db.connect() as conn:
        conn.executemany(_INSERT, list(rows.values()))
    return len(rows)


def ingest_all() -> None:
    for league in LEAGUES:
        n = ingest_league(league)
        print(f"  ok    {league}: {n} games")
    print(f"\nDone. Basketball games ingested into {config.DB_PATH}")


if __name__ == "__main__":
    ingest_all()
