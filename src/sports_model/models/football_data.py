"""Complete fixtures, kickoff times, and live scores from football-data.org.

This is the preferred fixtures source when a FOOTBALL_DATA_API_KEY is set: it
returns the *full* schedule (not a sample), exact kickoff times, and live
status + score. Functions return None when there's no key or the API is
unreachable, so callers can fall back to the free sources.

Status meanings we use:
  TIMED / SCHEDULED -> upcoming    IN_PLAY -> live    PAUSED -> live (half-time)
  FINISHED -> done (excluded; a played game never reappears)
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import requests

from .. import config

_BASE = "https://api.football-data.org/v4/competitions/{code}/matches"
_UPCOMING = "TIMED,SCHEDULED,IN_PLAY,PAUSED"  # everything except finished
_LIVE = {"IN_PLAY", "PAUSED"}
_TIMEOUT = 30

# football-data.org national-team name -> our Elo (martj42) name.
_WC_ALIAS = {
    "Bosnia-Herzegovina": "Bosnia and Herzegovina",
    "Cape Verde Islands": "Cape Verde",
    "Congo DR": "DR Congo",
    "Czechia": "Czech Republic",
}


def _session() -> requests.Session | None:
    key = config.football_data_api_key()
    if not key:
        return None
    s = requests.Session()
    s.headers.update({"X-Auth-Token": key})
    return s


def _fmt(utc_iso: str) -> tuple[str, str]:
    """'2026-06-24T19:00:00Z' -> ('2026-06-24', 'HH:MM' in display tz)."""
    dt = datetime.strptime(utc_iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    local = dt + timedelta(hours=config.DISPLAY_TZ_OFFSET_HOURS)
    return local.strftime("%Y-%m-%d"), local.strftime("%H:%M")


def _live_score(m: dict) -> str | None:
    ft = (m.get("score") or {}).get("fullTime") or {}
    if ft.get("home") is not None and ft.get("away") is not None:
        return f"{ft['home']}-{ft['away']}"
    return None


def _fetch(session, code: str) -> list[dict]:
    r = session.get(_BASE.format(code=code), params={"status": _UPCOMING},
                    timeout=_TIMEOUT)
    r.raise_for_status()
    return r.json().get("matches", [])


def wc_fixtures(model, limit: int | None = None) -> list[dict] | None:
    """Upcoming + live World Cup fixtures with Elo predictions, or None."""
    session = _session()
    if session is None:
        return None
    try:
        matches = _fetch(session, config.FOOTBALL_DATA_WC_CODE)
    except (requests.RequestException, ValueError):
        return None

    out = []
    for m in matches:
        rh, ra = m["homeTeam"]["name"], m["awayTeam"]["name"]
        if not rh or not ra:
            continue  # knockout slot not yet decided
        home = _WC_ALIAS.get(rh, rh)
        away = _WC_ALIAS.get(ra, ra)
        date, tm = _fmt(m["utcDate"])
        p = model.predict(home, away, neutral=True)
        t = model.predict_totals(home, away, neutral=True)
        out.append({
            "date": date, "time": tm,
            "live": m["status"] in _LIVE, "status": m["status"],
            "score": _live_score(m) if m["status"] in _LIVE else None,
            "home": home, "away": away,
            "h": round(p["H"], 3), "d": round(p["D"], 3), "a": round(p["A"], 3),
            "ov": round(t["OV"], 3),
        })
    return out[:limit] if limit else out


def cl_fixtures(model) -> list[dict] | None:
    """Upcoming + live Champions League fixtures, predicted by the unified Elo.

    Empty until the new CL is drawn (~late August). Team names resolved against
    the model's rating keys (our football-data.co.uk club names).
    """
    session = _session()
    if session is None:
        return None
    from .club_schedule import _norm, _resolve

    try:
        matches = _fetch(session, "CL")
    except (requests.RequestException, ValueError):
        return None

    names = set(model.ratings)
    norm_map = {_norm(t): t for t in names}
    out = []
    for m in matches:
        ht, at = m["homeTeam"], m["awayTeam"]
        rh = _resolve(ht.get("shortName") or ht.get("name") or "", names, norm_map)
        ra = _resolve(at.get("shortName") or at.get("name") or "", names, norm_map)
        if not rh or not ra:
            continue
        date, tm = _fmt(m["utcDate"])
        p = model.predict(rh, ra)            # home/away (not neutral)
        t = model.predict_totals(rh, ra)
        out.append({
            "date": date, "time": tm,
            "live": m["status"] in _LIVE, "status": m["status"],
            "score": _live_score(m) if m["status"] in _LIVE else None,
            "home": rh, "away": ra,
            "h": round(p["H"], 3), "d": round(p["D"], 3), "a": round(p["A"], 3),
            "ov": round(t["OV"], 3),
        })
    return out


def club_fixtures(models_by_code: dict) -> dict | None:
    """{league_code: [fixtures]} with xG predictions, or None if no key."""
    session = _session()
    if session is None:
        return None
    from .club_schedule import _norm, _resolve

    out: dict[str, list] = {c: [] for c in models_by_code}
    for code, model in models_by_code.items():
        comp = config.FOOTBALL_DATA_COMP_CODES.get(code)
        if not comp:
            continue
        try:
            matches = _fetch(session, comp)
        except (requests.RequestException, ValueError):
            continue
        names = set(model.attack)
        norm_map = {_norm(t): t for t in names}
        for m in matches:
            ht, at = m["homeTeam"], m["awayTeam"]
            rh = ht.get("shortName") or ht.get("name")
            ra = at.get("shortName") or at.get("name")
            if not rh or not ra:
                continue
            home = _resolve(rh, names, norm_map)
            away = _resolve(ra, names, norm_map)
            if not home or not away:
                continue
            date, tm = _fmt(m["utcDate"])
            p = model.predict(home, away)
            t = model.predict_totals(home, away)
            out[code].append({
                "date": date, "time": tm,
                "live": m["status"] in _LIVE, "status": m["status"],
                "score": _live_score(m) if m["status"] in _LIVE else None,
                "home": home, "away": away,
                "h": round(p["H"], 3), "d": round(p["D"], 3), "a": round(p["A"], 3),
                "ov": round(t["OV"], 3),
            })
    return out
