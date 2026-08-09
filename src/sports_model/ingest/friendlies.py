"""Ingest upcoming club friendlies (pre-season / mid-season) from TheSportsDB.

Friendlies aren't served by TheSportsDB's per-league "next fixtures" endpoint on
the free key, so we go per team: resolve each current top-flight club to its
TheSportsDB id (cached in `tsdb_team_ids`), then read that team's next events and
keep the ones in the "Club Friendlies" pseudo-league (id 4569). Each friendly
shows up under both teams, so we de-duplicate on (date, home, away).

We only need to resolve ids once — they're stable — so day-to-day this is just
one light "next events" call per club. Names are stored raw; the report resolves
them to model teams and rates the match with the unified cross-league club Elo,
flagging the whole thing as a low-confidence exhibition (squads rotate).
"""
from __future__ import annotations

import time
import unicodedata

import requests

from .. import config, db
from ..models import evaluate
from ..models.club_schedule import _ALIAS

_SEARCH = "https://www.thesportsdb.com/api/v1/json/3/searchteams.php"
_NEXT = "https://www.thesportsdb.com/api/v1/json/3/eventsnext.php"
# A team's most recent finished events. Note the payload key is "results", not
# "events" like the other endpoints.
_LAST = "https://www.thesportsdb.com/api/v1/json/3/eventslast.php"
_FRIENDLIES_LEAGUE_ID = "4569"  # TheSportsDB "Club Friendlies"
_FINISHED = {"FT", "AET", "PEN", "Match Finished", "FT_PEN"}
_TIMEOUT = 15
# The free key rate-limits at ~30 requests/minute, so we pace one call every
# ~2.2s. We check only the top-5 leagues' clubs (whose friendlies are the ones
# fans follow) to keep the daily run inside a few minutes; opponents from any
# league still resolve, because the rating universe spans all 12.
_THROTTLE = 2.2
_CHECK_LEAGUES = ("E0", "SP1", "D1", "I1", "F1")

# fuller search terms for football-data's abbreviated names, layered on top of
# the TheSportsDB->football-data alias table (inverted for name lookups).
_INV_ALIAS = {v: k for k, v in _ALIAS.items()}

# football-data name -> a fuller name that searchteams resolves cleanly. Only
# the clubs whose short name is ambiguous or hits a women's/lower-league team.
_SEARCH_ALIAS = {
    "Brighton": "Brighton & Hove Albion",
    "Tottenham": "Tottenham Hotspur",
    "West Ham": "West Ham United",
    "Leeds": "Leeds United",
    "Nott'm Forest": "Nottingham Forest",
    "Newcastle": "Newcastle United",
    "Wolves": "Wolverhampton Wanderers",
    "Man City": "Manchester City",
    "Man United": "Manchester United",
    "Ath Madrid": "Atletico Madrid",
    "Ath Bilbao": "Athletic Bilbao",
    "Betis": "Real Betis",
    "Sociedad": "Real Sociedad",
    "M'gladbach": "Borussia Monchengladbach",
    "Paris SG": "Paris Saint-Germain",
    "Inter": "Inter Milan",
}

_BAD = ("women", "wfc", " u21", " u23", " u19", "reserves", "ladies", "youth")


def _norm(name: str) -> str:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return "".join(ch for ch in s.lower() if ch.isalnum())


def _current_teams() -> list[str]:
    """Clubs in the most recent season of the leagues we check for friendlies."""
    teams: set[str] = set()
    for code in _CHECK_LEAGUES:
        try:
            df = evaluate.load_league(code)
        except Exception:
            continue
        latest = df["season"].max()
        teams |= set(df[df["season"] == latest]["home"])
    return sorted(teams)


def _get(session: requests.Session, url: str, params: dict | None = None) -> dict:
    """GET with one retry (the free key intermittently drops requests)."""
    for attempt in range(2):
        try:
            r = session.get(url, params=params, timeout=_TIMEOUT)
            r.raise_for_status()
            return r.json() or {}
        except (requests.RequestException, ValueError):
            if attempt == 0:
                time.sleep(3.0)
    return {}


def _search_id(session: requests.Session, name: str) -> str:
    """Best-effort TheSportsDB idTeam for one club, or '' if unresolved.

    Tries progressively: a hand-tuned fuller name, the alias table, then the raw
    name — stopping at the first query that yields a clean men's-soccer hit.
    """
    candidates = []
    for q in (_SEARCH_ALIAS.get(name), _INV_ALIAS.get(name), name):
        if q and q not in candidates:
            candidates.append(q)
    for query in candidates:
        data = _get(session, _SEARCH, {"t": query})
        teams = data.get("teams") or []
        target = _norm(query)
        best = ""
        for t in teams:
            nm = t.get("strTeam") or ""
            lg = t.get("strLeague") or ""
            if (t.get("strSport") or "") != "Soccer":
                continue
            if any(b in f"{nm} {lg}".lower() for b in _BAD):
                continue
            if _norm(nm) == target:
                return t.get("idTeam") or ""
            if not best:
                best = t.get("idTeam") or ""
        if best:
            return best
    return ""


def _resolve_ids(session: requests.Session, teams: list[str]) -> dict[str, str]:
    """Return {name: id} for resolvable clubs. Ids are cached once; failures are
    NOT cached, so a rate-limited run retries the misses next time."""
    with db.connect() as conn:
        cached = {r["name"]: r["tsdb_id"] for r in
                  conn.execute("SELECT name, tsdb_id FROM tsdb_team_ids")
                  if r["tsdb_id"]}
    out: dict[str, str] = {}
    resolved_now = 0
    for t in teams:
        if t in cached:
            out[t] = cached[t]
            continue
        tid = _search_id(session, t)
        time.sleep(_THROTTLE)
        if not tid:
            continue  # leave uncached so we retry next run
        out[t] = tid
        resolved_now += 1
        with db.connect() as conn:
            conn.execute(
                "INSERT INTO tsdb_team_ids (name, tsdb_id) VALUES (?, ?) "
                "ON CONFLICT (name) DO UPDATE SET tsdb_id=excluded.tsdb_id",
                (t, tid))
    print(f"  resolved {resolved_now} new id(s); "
          f"{len(out)}/{len(teams)} checked clubs now have an id")
    return out


def _fetch_friendlies(session: requests.Session, ids: dict[str, str]) -> list[dict]:
    """De-duplicated upcoming friendlies across all resolved clubs."""
    seen: set[tuple] = set()
    out: list[dict] = []
    for tid in {v for v in ids.values() if v}:
        events = _get(session, _NEXT, {"id": tid}).get("events") or []
        time.sleep(_THROTTLE)
        for e in events:
            if str(e.get("idLeague")) != _FRIENDLIES_LEAGUE_ID:
                continue
            status = (e.get("strStatus") or "NS").strip()
            if status in _FINISHED:
                continue
            home = (e.get("strHomeTeam") or "").strip()
            away = (e.get("strAwayTeam") or "").strip()
            date = e.get("dateEvent")
            if not (home and away and date):
                continue
            key = (date, home, away)
            if key in seen:
                continue
            seen.add(key)
            out.append({"date": date, "time_utc": e.get("strTime"),
                        "home": home, "away": away, "status": status})
        time.sleep(_THROTTLE)
    return out


def _fetch_results(session: requests.Session, ids: dict[str, str]) -> list[dict]:
    """Finished friendlies from each club's last events. Raw names.

    One throttled call per club (~3 minutes for the top-5 pool), which is why
    this runs in the daily ingest and not in the 15-minute snapshot push.
    """
    seen: set[tuple] = set()
    out: list[dict] = []
    for tid in {v for v in ids.values() if v}:
        try:
            events = _get(session, _LAST, {"id": tid}).get("results") or []
        except Exception:  # noqa: BLE001 - one club failing must not sink the feed
            continue
        time.sleep(_THROTTLE)
        for e in events:
            if str(e.get("idLeague")) != _FRIENDLIES_LEAGUE_ID:
                continue
            if (e.get("strStatus") or "").strip() not in _FINISHED:
                continue
            d = e.get("dateEvent")
            home = (e.get("strHomeTeam") or "").strip()
            away = (e.get("strAwayTeam") or "").strip()
            if not (d and home and away):
                continue
            try:
                hs = int(e.get("intHomeScore"))
                aws = int(e.get("intAwayScore"))
            except (TypeError, ValueError):
                continue  # no score yet — not gradeable
            key = (d, home, away)
            if key in seen:
                continue
            seen.add(key)
            out.append({"date": d, "home": home, "away": away,
                        "home_score": hs, "away_score": aws})
    return out


def recent_results(universe, norm_map, days: int = 14) -> list[dict]:
    """Finished friendlies for grading "Beat the Model" picks. Cheap DB read.

    A finished friendly leaves no trace anywhere else — the fixture fetch skips
    finished statuses and `run` clears that table each pass — so without this a
    pick on one could never be graded and simply sat there after the match ended.

    Names resolve through the SAME universe/norm_map the report uses for the
    fixtures, because a pick is stored against the displayed name; resolving
    differently here would silently fail to match it.
    """
    from datetime import date, timedelta

    from ..models.club_schedule import _resolve

    cutoff = (date.today() - timedelta(days=days)).isoformat()
    try:
        with db.connect() as conn:
            rows = [dict(r) for r in conn.execute(
                "SELECT date, home, away, home_score, away_score "
                "FROM friendly_results WHERE date >= ? ORDER BY date DESC",
                (cutoff,))]
    except Exception:  # noqa: BLE001 - table predates this feature
        return []

    out: list[dict] = []
    for r in rows:
        home = _resolve(r["home"], universe, norm_map)
        away = _resolve(r["away"], universe, norm_map)
        if not home or not away:
            continue
        hs, aws = r["home_score"], r["away_score"]
        out.append({
            "sport": "friendlies",
            "date": r["date"],
            "home": home,
            "away": away,
            "result": "H" if hs > aws else ("A" if aws > hs else "D"),
            "score": f"{hs}-{aws}",
        })
    return out


def run() -> None:
    """Resolve club ids (cached), fetch upcoming friendlies, replace the table."""
    db.init_db()
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0"})

    teams = _current_teams()
    print(f"Club friendlies: {len(teams)} current clubs to check")
    ids = _resolve_ids(session, teams)
    fixtures = _fetch_friendlies(session, ids)
    print(f"  found {len(fixtures)} upcoming friendly fixture(s)")

    with db.connect() as conn:
        conn.execute("DELETE FROM friendly_fixtures")
        conn.executemany(
            "INSERT OR REPLACE INTO friendly_fixtures "
            "(date, time_utc, home, away, status) "
            "VALUES (:date, :time_utc, :home, :away, :status)",
            fixtures)

    # Finished friendlies, so picks on them can be graded once the match ends.
    # ACCUMULATED, never cleared: unlike fixtures, results are history, and
    # dropping them would silently void a user's pending pick.
    results = _fetch_results(session, ids)
    print(f"  found {len(results)} finished friendly result(s)")
    with db.connect() as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO friendly_results "
            "(date, home, away, home_score, away_score) "
            "VALUES (:date, :home, :away, :home_score, :away_score)",
            results)
