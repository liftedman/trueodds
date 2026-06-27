"""World Cup schedule with kickoff times and live status (TheSportsDB).

The martj42 results dataset has dates but no kickoff times. TheSportsDB's free
endpoint does: we query `eventsday` for each upcoming date, filter to the World
Cup league, and get kickoff time (UTC) plus a live status (NS = not started,
1H/2H/HT = in progress, FT = finished). This lets us:
  - show times, not just dates,
  - drop matches once they're played (status-based, so they never reappear),
  - flag matches that are live right now.

Predictions come from our Elo model. Team names are mapped from TheSportsDB's
spelling to the Elo/martj42 spelling.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import requests

from .. import config
from . import elo, world_cup

_TSDB = "https://www.thesportsdb.com/api/v1/json/3/eventsday.php"
_WC_LEAGUE_ID = "4429"
_TIMEOUT = 20
_FINISHED = {"FT", "AET", "PEN", "Match Finished", "FT_PEN"}
_LIVE = {"1H", "2H", "HT", "ET", "LIVE", "P"}

# TheSportsDB spelling -> Elo (martj42) spelling. Only differences need entries.
_TEAM_ALIAS = {
    "Bosnia-Herzegovina": "Bosnia and Herzegovina",
    "USA": "United States",
    "Korea Republic": "South Korea",
    "IR Iran": "Iran",
    "Czechia": "Czech Republic",
    "Cabo Verde": "Cape Verde",
    "Ivory Coast": "Côte d'Ivoire",
    "Curacao": "Curaçao",
}


def _elo_name(tsdb_name: str) -> str:
    return _TEAM_ALIAS.get(tsdb_name, tsdb_name)


def _to_local(time_utc: str, day: str) -> str:
    """'19:00:00' + '2026-06-24' (UTC) -> 'HH:MM' shifted to display tz."""
    try:
        dt = datetime.strptime(f"{day} {time_utc}", "%Y-%m-%d %H:%M:%S")
        dt += timedelta(hours=config.DISPLAY_TZ_OFFSET_HOURS)
        return dt.strftime("%H:%M")
    except (ValueError, TypeError):
        return ""


def fetch_schedule(days_ahead: int = 12, today: str | None = None,
                   model: elo.EloModel | None = None) -> list[dict]:
    """Upcoming + live World Cup matches over the next `days_ahead` days.

    Finished matches are excluded. Each item carries kickoff time, status, and
    an Elo prediction. Returns [] if the source is unreachable (caller falls
    back to the date-only schedule).
    """
    model = model or world_cup.fit_model()
    start = datetime.strptime(today, "%Y-%m-%d") if today else datetime.combine(
        date.today(), datetime.min.time())
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0"})

    out: list[dict] = []
    for i in range(days_ahead):
        day = (start + timedelta(days=i)).strftime("%Y-%m-%d")
        try:
            resp = session.get(_TSDB, params={"d": day, "s": "Soccer"},
                               timeout=_TIMEOUT)
            resp.raise_for_status()
            events = resp.json().get("events") or []
        except (requests.RequestException, ValueError):
            continue
        for e in events:
            if e.get("idLeague") != _WC_LEAGUE_ID:
                continue
            status = (e.get("strStatus") or "NS").strip()
            if status in _FINISHED:
                continue  # played -> never show again
            # Sanity guard: a match can't still be live ~2.5h after kickoff.
            # TheSportsDB sometimes leaves a status stuck (e.g. '2H' 0-0 hours
            # later); drop those as finished. (2.5h safely covers a full match.)
            ts = e.get("strTimestamp")
            if ts:
                try:
                    ko = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S").replace(
                        tzinfo=timezone.utc)
                    if datetime.now(timezone.utc) - ko > timedelta(hours=2.5):
                        continue
                except ValueError:
                    pass
            home = _elo_name((e.get("strHomeTeam") or "").strip())
            away = _elo_name((e.get("strAwayTeam") or "").strip())
            if not home or not away:
                continue
            pred = model.predict(home, away, neutral=True)
            tot = model.predict_totals(home, away, neutral=True)
            live = status in _LIVE
            hs, as_ = e.get("intHomeScore"), e.get("intAwayScore")
            score = f"{hs}-{as_}" if (live and hs is not None and as_ is not None) else None
            out.append({
                "date": e.get("dateEvent"),
                "time": _to_local(e.get("strTime"), e.get("dateEvent")),
                "live": live,
                "status": status,
                "score": score,
                "home": home,
                "away": away,
                "pred": pred,
                "totals": tot,
            })
    return out
