"""Live scores + near-term fixtures for NBA / NFL from ESPN's public scoreboard.

ESPN's site API is free, keyless, and — unlike stats.nba.com — reachable from
CI, so it drives live in-game scores and upcoming games for both leagues. We
map ESPN's team abbreviations to ours, then attach an Elo prediction to each
game. Finished games are dropped (they never show as upcoming/live).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import requests

from .. import config

_URL = {
    "nba": "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard",
    "wnba": "https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/scoreboard",
    "nfl": "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard",
}

# ESPN abbreviation -> our abbreviation (only where they differ).
# WNBA is ESPN end-to-end (history + live), so no remapping needed.
_ALIAS = {
    "nba": {"GS": "GSW", "NO": "NOP", "NY": "NYK", "SA": "SAS",
            "UTAH": "UTA", "WSH": "WAS"},
    "wnba": {"CONN": "CON", "GSV": "GS", "WSH": "WAS"},
    "nfl": {"LAR": "LA", "WSH": "WAS", "JAC": "JAX"},
}

_TIMEOUT = 15


def _parse_utc(s: str) -> datetime | None:
    for fmt in ("%Y-%m-%dT%H:%MZ", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            continue
    return None


def fixtures(sport: str, model, team_names: dict[str, str], days: int = 6) -> list[dict]:
    """Upcoming + live games for `sport` over the next `days` days, with Elo
    predictions. Returns [] if ESPN is unreachable."""
    url = _URL.get(sport)
    if not url:
        return []
    alias = _ALIAS.get(sport, {})
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0"})

    now = datetime.now(timezone.utc)
    events: list[dict] = []
    seen: set[str] = set()
    for i in range(days):
        day = (now + timedelta(days=i)).strftime("%Y%m%d")
        try:
            r = session.get(url, params={"dates": day}, timeout=_TIMEOUT)
            r.raise_for_status()
            for ev in r.json().get("events", []):
                if ev.get("id") and ev["id"] not in seen:
                    seen.add(ev["id"])
                    events.append(ev)
        except (requests.RequestException, ValueError):
            continue

    out: list[dict] = []
    for ev in events:
        try:
            comp = ev["competitions"][0]
            cs = comp["competitors"]
            home = next(c for c in cs if c.get("homeAway") == "home")
            away = next(c for c in cs if c.get("homeAway") == "away")
        except (KeyError, IndexError, StopIteration):
            continue
        ha = alias.get(home["team"]["abbreviation"], home["team"]["abbreviation"])
        aa = alias.get(away["team"]["abbreviation"], away["team"]["abbreviation"])
        state = (ev.get("status", {}).get("type", {}) or {}).get("state")
        if state == "post":
            continue  # finished — don't surface
        live = state == "in"

        ko = _parse_utc(ev.get("date", ""))
        if ko is None:
            continue
        local = ko + timedelta(hours=config.DISPLAY_TZ_OFFSET_HOURS)

        p = model.predict(ha, aa)
        score = None
        if live:
            hs, as_ = home.get("score"), away.get("score")
            if hs is not None and as_ is not None:
                score = f"{hs}-{as_}"

        out.append({
            "date": local.strftime("%Y-%m-%d"),
            "time": local.strftime("%H:%M"),
            "live": live,
            "status": (ev.get("status", {}).get("type", {}) or {}).get("shortDetail", ""),
            "score": score,
            "home": team_names.get(ha, ha),
            "away": team_names.get(aa, aa),
            "home_win": round(p["home_win"], 3),
            "away_win": round(p["away_win"], 3),
            "proj": f"{round(p['proj_home'])}-{round(p['proj_away'])}",
        })
    out.sort(key=lambda x: (not x["live"], x["date"], x["time"]))
    return out
