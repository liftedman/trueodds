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

# league key -> (ESPN path, query granularity). NCAA has far more than 100
# games a month (ESPN's per-query cap), so it's fetched day-by-day.
LEAGUES = {
    "wnba": ("wnba", "month"),
    "summer": ("nba-summer-las-vegas", "month"),
    "nbl": ("nbl", "month"),
    "ncaam": ("mens-college-basketball", "day"),
}

_TEAMS = """
INSERT INTO bball_teams (league, abbr, name) VALUES (:league, :abbr, :name)
ON CONFLICT (league, abbr) DO UPDATE SET name=excluded.name
"""

_INSERT = """
INSERT INTO bball_games (league, game_id, date, season, home, away, home_pts, away_pts)
VALUES (:league, :game_id, :date, :season, :home, :away, :home_pts, :away_pts)
ON CONFLICT (league, game_id) DO UPDATE SET
    home_pts=excluded.home_pts, away_pts=excluded.away_pts
"""


def _ranges(granularity: str) -> list[str]:
    """ESPN `dates` params to cover ~2 recent seasons.

    'month' -> one "YYYYMMDD-YYYYMMDD" range per month (16 months back).
    'day'   -> one "YYYYMMDD" per day (260 days back) for high-volume leagues.
    """
    from datetime import timedelta
    today = date.today()
    if granularity == "day":
        return [(today - timedelta(days=i)).strftime("%Y%m%d") for i in range(260)]
    out = []
    y, m = today.year, today.month
    for _ in range(16):
        first = date(y, m, 1)
        nxt = date(y + (m // 12), (m % 12) + 1, 1)
        last = nxt - timedelta(days=1)
        out.append(f"{first:%Y%m%d}-{last:%Y%m%d}")
        m -= 1
        if m == 0:
            m, y = 12, y - 1
    return out


def _fetch(session, path: str, dates: str) -> list[dict]:
    try:
        r = session.get(_URL.format(path=path), params={"dates": dates},
                        timeout=_TIMEOUT)
        r.raise_for_status()
        return r.json().get("events", [])
    except (requests.RequestException, ValueError):
        return []


def ingest_league(league: str) -> int:
    db.init_db()
    path, gran = LEAGUES[league]
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0"})

    rows: dict[str, dict] = {}
    names: dict[str, str] = {}
    for dates in _ranges(gran):
        for ev in _fetch(session, path, dates):
            try:
                comp = ev["competitions"][0]
                cs = comp["competitors"]
                home = next(c for c in cs if c.get("homeAway") == "home")
                away = next(c for c in cs if c.get("homeAway") == "away")
            except (KeyError, IndexError, StopIteration):
                continue
            for c in (home, away):
                t = c["team"]
                if t.get("abbreviation"):
                    names[t["abbreviation"]] = (
                        t.get("shortDisplayName") or t.get("displayName") or t["abbreviation"])
            state = (ev.get("status", {}).get("type", {}) or {}).get("state")
            if state != "post":
                continue  # only completed games make ratings
            try:
                hp, ap = int(home.get("score")), int(away.get("score"))
            except (TypeError, ValueError):
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
        conn.executemany(_TEAMS, [{"league": league, "abbr": a, "name": n}
                                  for a, n in names.items()])
    return len(rows)


def ingest_all() -> None:
    for league in LEAGUES:
        try:
            n = ingest_league(league)
            print(f"  ok    {league}: {n} games")
        except Exception as e:
            print(f"  skip  {league}: {type(e).__name__}: {e}")
    print(f"\nDone. Basketball games ingested into {config.DB_PATH}")


if __name__ == "__main__":
    ingest_all()
