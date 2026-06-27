"""Unified cross-league club Elo (for Champions League predictions).

Our per-league xG models aren't comparable across leagues. clubelo.com (the
usual cross-league source) is unreachable from here, so we build our own:
run a single Elo over six seasons of domestic results from every league we
have, with last season's Champions League results mixed in. Those CL games are
the bridges that let one league's clubs be rated against another's.

Approximation, stated plainly: the cross-league calibration rests on a single
season of European links, so it's directional, not definitive. Goal-model
parameters (supremacy & total) are fit from the same data, like the other Elo
models.
"""

from __future__ import annotations

import requests

from .. import config, db
from . import elo
from .club_schedule import _norm, _resolve

_K = 30.0
_HOME_ADV = 65.0   # Elo points for home advantage in club football
import numpy as np


def _g_mult(gd: int) -> float:
    gd = abs(gd)
    if gd <= 1:
        return 1.0
    if gd == 2:
        return 1.5
    return (11 + gd) / 8.0


def _domestic_matches() -> list[dict]:
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT date, home, away, fthg, ftag FROM football_matches "
            "WHERE fthg IS NOT NULL AND ftag IS NOT NULL ORDER BY date"
        ).fetchall()
    return [dict(r) for r in rows]


def _cl_matches(team_universe: set[str]) -> list[dict]:
    """Finished Champions League matches from football-data.org, names resolved."""
    key = config.football_data_api_key()
    if not key:
        return []
    try:
        r = requests.get(
            "https://api.football-data.org/v4/competitions/CL/matches",
            headers={"X-Auth-Token": key},
            params={"status": "FINISHED"}, timeout=30)
        r.raise_for_status()
        matches = r.json().get("matches", [])
    except (requests.RequestException, ValueError):
        return []

    norm_map = {_norm(t): t for t in team_universe}
    out = []
    for m in matches:
        ht, at = m["homeTeam"], m["awayTeam"]
        sc = (m.get("score") or {}).get("fullTime") or {}
        if sc.get("home") is None:
            continue
        home = _resolve(ht.get("shortName") or ht.get("name") or "",
                        team_universe, norm_map)
        away = _resolve(at.get("shortName") or at.get("name") or "",
                        team_universe, norm_map)
        if not home or not away:
            continue
        out.append({"date": m["utcDate"][:10], "home": home, "away": away,
                    "fthg": sc["home"], "ftag": sc["away"]})
    return out


def build() -> tuple[elo.EloModel, dict]:
    """Return (unified-Elo model, diagnostics)."""
    domestic = _domestic_matches()
    universe = {m["home"] for m in domestic} | {m["away"] for m in domestic}
    cl = _cl_matches(universe)

    matches = sorted(domestic + cl, key=lambda m: m["date"])
    ratings: dict[str, float] = {}
    drs, sups, totals = [], [], []

    for m in matches:
        h, a = m["home"], m["away"]
        rh = ratings.get(h, 1500.0)
        ra = ratings.get(a, 1500.0)
        dr = rh - ra + _HOME_ADV
        exp = 1.0 / (1.0 + 10 ** (-dr / 400.0))
        hg, ag = int(m["fthg"]), int(m["ftag"])
        actual = 1.0 if hg > ag else 0.5 if hg == ag else 0.0
        delta = _K * _g_mult(hg - ag) * (actual - exp)
        ratings[h] = rh + delta
        ratings[a] = ra - delta
        drs.append(dr); sups.append(hg - ag); totals.append(hg + ag)

    dr_arr = np.array(drs, dtype=float)
    sup_arr = np.array(sups, dtype=float)
    denom = float(np.sum(dr_arr * dr_arr))
    sup_slope = float(np.sum(dr_arr * sup_arr) / denom) if denom else 0.0045
    slope, intercept = np.polyfit(np.abs(dr_arr), np.array(totals, dtype=float), 1)

    model = elo.EloModel(ratings=ratings, home_adv=_HOME_ADV,
                         sup_slope=sup_slope, total_base=float(intercept),
                         total_gap=float(slope))
    cl_teams = sorted({m["home"] for m in cl} | {m["away"] for m in cl})
    diag = {"domestic": len(domestic), "cl_links": len(cl),
            "teams": len(ratings), "cl_teams": cl_teams}
    return model, diag
