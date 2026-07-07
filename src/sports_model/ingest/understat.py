"""Ingest expected-goals (xG) data from understat.com.

understat exposes a JSON endpoint per league-season:

    https://understat.com/getLeagueData/{LEAGUE}/{YEAR}

returning {"teams": ..., "players": ..., "dates": [match, ...]} where each
match has home/away titles, goals, and xG.

We attach each match's xG to the rows already in `football_matches` (which
came from football-data.co.uk). The join key is (league, season, home, away):
in a round-robin league every ordered pair plays exactly once per season, so
this is unambiguous and avoids fragile date/timezone matching.

The one wrinkle: understat and football-data spell team names differently
("Manchester City" vs "Man City"). _TEAM_ALIAS maps understat -> football-data.
Any understat team that can't be aligned to a DB row is reported, not silently
dropped.
"""

from __future__ import annotations

import requests

from .. import config, db

# understat league slug -> our football-data league code.
_LEAGUE_MAP = {
    "EPL": "E0",
    "La_liga": "SP1",
    "Bundesliga": "D1",
    "Serie_A": "I1",
    "Ligue_1": "F1",
}

# understat uses the season's starting year ("2023" = 2023/24); our codes are
# "2324". Build the mapping from config.FOOTBALL_SEASONS.
def _our_season(start_year: int) -> str:
    return f"{start_year % 100:02d}{(start_year + 1) % 100:02d}"


# understat uses the season's starting year; auto-extend to the current season
# so xG ingestion tracks the calendar with no manual edits.
_UNDERSTAT_YEARS = list(range(2019, config.current_season_start() + 1))

# understat team title -> football-data.co.uk team name.
# Only names that actually differ need an entry; exact matches pass through.
_TEAM_ALIAS: dict[str, str] = {
    # Premier League
    "Manchester City": "Man City",
    "Manchester United": "Man United",
    "Newcastle United": "Newcastle",
    "Nottingham Forest": "Nott'm Forest",
    "Wolverhampton Wanderers": "Wolves",
    "West Bromwich Albion": "West Brom",
    # La Liga
    "Athletic Club": "Ath Bilbao",
    "Atletico Madrid": "Ath Madrid",
    "Celta Vigo": "Celta",
    "Rayo Vallecano": "Vallecano",
    "Real Betis": "Betis",
    "Real Sociedad": "Sociedad",
    "Espanyol": "Espanol",
    "Real Valladolid": "Valladolid",
    "SD Huesca": "Huesca",
    # Bundesliga
    "Bayer Leverkusen": "Leverkusen",
    "Borussia Dortmund": "Dortmund",
    "Borussia M.Gladbach": "M'gladbach",
    "Eintracht Frankfurt": "Ein Frankfurt",
    "FC Cologne": "FC Koln",
    "FC Heidenheim": "Heidenheim",
    "Mainz 05": "Mainz",
    "RasenBallsport Leipzig": "RB Leipzig",
    "VfB Stuttgart": "Stuttgart",
    "Arminia Bielefeld": "Bielefeld",
    "Greuther Fuerth": "Greuther Furth",
    "Hertha Berlin": "Hertha",
    "VfL Bochum": "Bochum",
    "SC Freiburg": "Freiburg",
    "FC Augsburg": "Augsburg",
    "Fortuna Duesseldorf": "Fortuna Dusseldorf",
    "Darmstadt 98": "Darmstadt",
    "St. Pauli": "St Pauli",
    # Serie A
    "AC Milan": "Milan",
    "Parma Calcio 1913": "Parma",
    "SPAL 2013": "Spal",
    # Ligue 1
    "Clermont Foot": "Clermont",
    "Paris Saint Germain": "Paris SG",
    "Saint-Etienne": "St Etienne",
}

_BASE = "https://understat.com/getLeagueData"
_HEADERS = {"User-Agent": "Mozilla/5.0", "X-Requested-With": "XMLHttpRequest"}
_TIMEOUT = 30


def _map_name(understat_title: str) -> str:
    return _TEAM_ALIAS.get(understat_title, understat_title)


def _fetch(us_league: str, year: int) -> list[dict]:
    url = f"{_BASE}/{us_league}/{year}"
    resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
    resp.raise_for_status()
    return resp.json()["dates"]


_UPDATE = """
UPDATE football_matches
   SET xg_h = :xg_h, xg_a = :xg_a
 WHERE league_code = :league_code
   AND season      = :season
   AND home        = :home
   AND away        = :away
"""


def ingest_all() -> None:
    """Fetch xG for every league-season and attach to existing match rows."""
    db.init_db()
    session = requests.Session()
    session.headers.update(_HEADERS)

    total_updated = 0
    unmatched: dict[str, set[str]] = {}

    for us_league, code in _LEAGUE_MAP.items():
        for year in _UNDERSTAT_YEARS:
            season = _our_season(year)
            try:
                matches = _fetch(us_league, year)
            except requests.HTTPError as e:
                print(f"  skip  {us_league} {year}: {e}")
                continue

            updated_here = 0
            with db.connect() as conn:
                # Which DB team names exist for this league-season (for reporting).
                db_teams = {
                    r["home"]
                    for r in conn.execute(
                        "SELECT DISTINCT home FROM football_matches "
                        "WHERE league_code=? AND season=?",
                        (code, season),
                    )
                }
                for m in matches:
                    if not m.get("isResult"):
                        continue  # skip not-yet-played fixtures
                    home = _map_name(m["h"]["title"])
                    away = _map_name(m["a"]["title"])
                    if home not in db_teams:
                        unmatched.setdefault(f"{us_league} {season}", set()).add(
                            f"{m['h']['title']} -> {home}"
                        )
                    cur = conn.execute(
                        _UPDATE,
                        {
                            "league_code": code,
                            "season": season,
                            "home": home,
                            "away": away,
                            "xg_h": float(m["xG"]["h"]),
                            "xg_a": float(m["xG"]["a"]),
                        },
                    )
                    updated_here += cur.rowcount

            total_updated += updated_here
            print(f"  ok    {config.FOOTBALL_LEAGUES[code]:<16} {season}: "
                  f"{updated_here:>4} matches matched with xG")

    if unmatched:
        print("\n!! understat teams that did NOT align to a DB row "
              "(add to _TEAM_ALIAS):")
        for ls, names in sorted(unmatched.items()):
            for n in sorted(names):
                print(f"   {ls}: {n}")

    print(f"\nDone. {total_updated} matches now have xG.")


if __name__ == "__main__":
    ingest_all()
