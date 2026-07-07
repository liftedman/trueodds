"""Team crest (badge) URLs from football-data.org, cached to data/crests.json.

Run occasionally: `python -m sports_model.main crests`. The push reads the
cached file and attaches a 'crest' URL to each club team; the app shows the
crest with the monogram avatar as a graceful fallback.

Only PNG crests are kept (Flutter's Image.network renders PNG directly; the WC
nation crests are SVG and are left to the monogram fallback for now). Covers
the leagues football-data.org serves (top-5 + Championship/Eredivisie/Primeira);
other leagues fall back to monograms.
"""
from __future__ import annotations

import json

import requests

from . import config, db
from .models.club_schedule import _norm, _resolve

_TEAMS_URL = "https://api.football-data.org/v4/competitions/{code}/teams"
_TIMEOUT = 30
CRESTS_PATH = config.DATA_DIR / "crests.json"


def _our_team_names(code: str) -> set[str]:
    """Every team name we have for a league (so promoted sides get crests too)."""
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT DISTINCT home FROM football_matches WHERE league_code=?",
            (code,),
        ).fetchall()
    return {r["home"] for r in rows}


def fetch_crests() -> dict[str, dict[str, str]]:
    """{league_code: {our_team_name: crest_png_url}} — also written to disk."""
    key = config.football_data_api_key()
    if not key:
        return {}
    session = requests.Session()
    session.headers.update({"X-Auth-Token": key})

    out: dict[str, dict[str, str]] = {}
    for code, comp in config.FOOTBALL_DATA_COMP_CODES.items():
        try:
            r = session.get(_TEAMS_URL.format(code=comp), timeout=_TIMEOUT)
            r.raise_for_status()
            teams = r.json().get("teams", [])
        except (requests.RequestException, ValueError):
            continue
        names = _our_team_names(code)
        norm = {_norm(n): n for n in names}
        mapping: dict[str, str] = {}
        for t in teams:
            crest = (t.get("crest") or "").strip()
            if not crest.lower().endswith(".png"):
                continue  # PNG only — SVGs need an extra renderer
            raw = t.get("shortName") or t.get("name") or ""
            our = _resolve(raw, names, norm)
            if our:
                mapping[our] = crest
        if mapping:
            out[code] = mapping

    CRESTS_PATH.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


def load_crests() -> dict[str, dict[str, str]]:
    """Read the cached crest map; {} if it hasn't been generated yet."""
    try:
        return json.loads(CRESTS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
