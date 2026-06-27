"""Club league schedule with kickoff times and live status (TheSportsDB).

The free TheSportsDB key doesn't serve club leagues through the day endpoint
(it samples a few minor leagues), but `eventsnextleague` returns the upcoming
fixture(s) for a specific league id. We call it once per top-5 league.

Team names from TheSportsDB are mapped to our football-data names via an alias
table (seeded from the understat mapping, since both use full club names) plus
a normalisation fallback against each league's known teams. Unmappable names
are skipped and reported rather than guessed.

Note: the top-5 leagues break over the summer, so this returns little or
nothing until the season resumes in August — by design, it fills in then.
"""

from __future__ import annotations

import unicodedata
from datetime import datetime, timedelta

import requests

from .. import config
from ..ingest.understat import _TEAM_ALIAS as _UNDERSTAT_ALIAS

_TSDB_NEXT = "https://www.thesportsdb.com/api/v1/json/3/eventsnextleague.php"
_TIMEOUT = 20
_FINISHED = {"FT", "AET", "PEN", "Match Finished", "FT_PEN"}
_LIVE = {"1H", "2H", "HT", "ET", "LIVE", "P"}

# TheSportsDB -> football-data names. Seed with the understat aliases (same
# full-name style) and add TheSportsDB-specific spellings.
_ALIAS: dict[str, str] = dict(_UNDERSTAT_ALIAS)
_ALIAS.update({
    "Atletico Madrid": "Ath Madrid",
    "Athletic Bilbao": "Ath Bilbao",
    "Real Betis": "Betis",
    "Inter Milan": "Inter",
    "Borussia Monchengladbach": "M'gladbach",
    "Nottingham Forest": "Nott'm Forest",
    "Paris Saint-Germain": "Paris SG",
    "Saint-Etienne": "St Etienne",
    "1. FC Heidenheim": "Heidenheim",
})

def _norm(name: str) -> str:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return "".join(ch for ch in s.lower() if ch.isalnum())


def _resolve(name: str, team_names: set[str], norm_map: dict[str, str]):
    """Map a TheSportsDB team name to a model team name, or None."""
    if name in team_names:
        return name
    if name in _ALIAS and _ALIAS[name] in team_names:
        return _ALIAS[name]
    nn = _norm(name)
    if nn in norm_map:
        return norm_map[nn]
    for k, v in _ALIAS.items():
        if _norm(k) == nn and v in team_names:
            return v
    for m in team_names:  # last resort: containment
        nm = _norm(m)
        if nm and (nm in nn or nn in nm):
            return m
    return None


def _to_local(time_utc: str, day: str) -> str:
    try:
        dt = datetime.strptime(f"{day} {time_utc}", "%Y-%m-%d %H:%M:%S")
        dt += timedelta(hours=config.DISPLAY_TZ_OFFSET_HOURS)
        return dt.strftime("%H:%M")
    except (ValueError, TypeError):
        return ""


def fetch_all(models_by_code: dict) -> tuple[dict, list[str]]:
    """Return ({league_code: [fixtures]}, unmapped_names).

    Calls eventsnextleague once per league. models_by_code: {code: fitted
    DixonColesModel}; predictions and the team universe come from each model.
    """
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0"})

    names = {c: set(m.attack) for c, m in models_by_code.items()}
    norm_maps = {c: {_norm(t): t for t in names[c]} for c in names}

    out: dict[str, list] = {c: [] for c in models_by_code}
    unmapped: set[str] = set()

    for code, model in models_by_code.items():
        lid = config.CLUB_TSDB_IDS.get(code)
        if not lid:
            continue
        try:
            resp = session.get(_TSDB_NEXT, params={"id": lid}, timeout=_TIMEOUT)
            resp.raise_for_status()
            events = resp.json().get("events") or []
        except (requests.RequestException, ValueError):
            continue
        for e in events:
            status = (e.get("strStatus") or "NS").strip()
            if status in _FINISHED:
                continue
            raw_h = (e.get("strHomeTeam") or "").strip()
            raw_a = (e.get("strAwayTeam") or "").strip()
            home = _resolve(raw_h, names[code], norm_maps[code])
            away = _resolve(raw_a, names[code], norm_maps[code])
            if not home:
                unmapped.add(f"{code}: {raw_h}")
            if not away:
                unmapped.add(f"{code}: {raw_a}")
            if not home or not away:
                continue
            p = model.predict(home, away)
            t = model.predict_totals(home, away)
            out[code].append({
                "date": e.get("dateEvent"),
                "time": _to_local(e.get("strTime"), e.get("dateEvent")),
                "live": status in _LIVE,
                "home": home, "away": away,
                "h": round(p["H"], 3), "d": round(p["D"], 3), "a": round(p["A"], 3),
                "ov": round(t["OV"], 3),
            })
    return out, sorted(unmapped)
