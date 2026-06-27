"""FastAPI prediction service — exposes the models as JSON over HTTP.

Models are fit once at startup and cached in memory (fitting per request would
be slow); endpoints read from that cache. This is the keystone a Flutter app,
an admin dashboard, or any client would consume.

Run:
    python -m sports_model.main serve          # http://127.0.0.1:8000
    uvicorn sports_model.api:app --reload      # dev, auto-reload
Interactive docs at /docs once running.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException

from . import config
from .models import (club_elo, dixon_coles, evaluate, markets,
                     nba as nba_mod, tennis as tennis_mod, world_cup)

STATE: dict = {}


def _fit_all() -> None:
    """Fit and cache every model. Called once at startup."""
    club_models, club_teams = {}, {}
    for code in config.FOOTBALL_LEAGUES:
        df = evaluate.load_league(code)
        ref = pd.to_datetime(df["date"]).max()
        club_models[code] = dixon_coles.fit(
            df, half_life_days=config.XG_HALF_LIFE_DAYS, ref_date=ref, use_xg=True)
        latest = df["season"].max()
        club_teams[code] = sorted(set(df[df["season"] == latest]["home"]))
    STATE["clubs"] = club_models
    STATE["club_teams"] = club_teams
    STATE["wc"] = world_cup.fit_model()
    STATE["nba"] = nba_mod.fit_model()
    tmatches = tennis_mod.load_matches()
    STATE["tennis"] = tennis_mod.fit_model(tmatches)
    STATE["tennis_players"] = tennis_mod.active_players(STATE["tennis"], tmatches)
    cl_model, cl_diag = club_elo.build()
    STATE["cl"] = cl_model
    STATE["cl_teams"] = cl_diag.get("cl_teams", [])


@asynccontextmanager
async def lifespan(app: FastAPI):
    _fit_all()
    yield


app = FastAPI(title="sports-model API", version="1.0", lifespan=lifespan)


# --- helpers ---------------------------------------------------------------
def _r(d: dict, n: int = 4) -> dict:
    return {k: round(float(v), n) for k, v in d.items()}


def _top_scorelines(mat: np.ndarray, n: int = 5) -> list[dict]:
    cells = [(i, j, mat[i, j]) for i in range(mat.shape[0])
             for j in range(mat.shape[1])]
    cells.sort(key=lambda c: -c[2])
    return [{"score": f"{i}-{j}", "p": round(float(p), 4)} for i, j, p in cells[:n]]


def _grid_payload(mat, wdl, lam) -> dict:
    return {
        "result": {"home": round(wdl["H"], 4), "draw": round(wdl["D"], 4),
                   "away": round(wdl["A"], 4)},
        "expected_goals": {"home": round(lam[0], 2), "away": round(lam[1], 2)},
        "goals_markets": _r(markets.goal_markets(mat)),
        "result_markets": _r(markets.result_markets(mat)),
        "scorelines": _top_scorelines(mat),
    }


# --- endpoints -------------------------------------------------------------
@app.get("/health")
def health():
    return {"status": "ok", "sports": ["clubs", "wc", "nba", "tennis", "cl"]}


@app.get("/sports")
def sports():
    return {
        "clubs": {"leagues": {c: config.FOOTBALL_LEAGUES[c]
                              for c in STATE["clubs"]},
                  "teams": STATE["club_teams"]},
        "wc": {"teams": sorted(STATE["wc"].ratings)},
        "nba": {"teams": [t["abbr"] for t in nba_mod.team_ratings(STATE["nba"])]},
        "tennis": {"players": [p["name"] for p in STATE["tennis_players"]]},
        "cl": {"teams": STATE["cl_teams"]},
    }


@app.get("/predict")
def predict(sport: str, home: str | None = None, away: str | None = None,
            league: str | None = None, a: str | None = None,
            b: str | None = None, surface: str = "Hard", neutral: bool = False):
    if sport == "clubs":
        models = STATE["clubs"]
        if league not in models:
            raise HTTPException(404, f"unknown league '{league}'")
        m = models[league]
        if home not in m.attack or away not in m.attack:
            raise HTTPException(404, "unknown team for this league")
        mat = m.score_matrix(home, away)
        return {"sport": sport, "league": league, "home": home, "away": away,
                **_grid_payload(mat, m.predict(home, away),
                                m.expected_goals(home, away))}

    if sport in ("wc", "cl"):
        m = STATE[sport]
        if home not in m.ratings or away not in m.ratings:
            raise HTTPException(404, "unknown team")
        mat = m.score_matrix(home, away, neutral)
        return {"sport": sport, "home": home, "away": away, "neutral": neutral,
                "elo": {"home": round(m.rating(home), 1),
                        "away": round(m.rating(away), 1)},
                **_grid_payload(mat, m.predict(home, away, neutral),
                                m.expected_goals(home, away, neutral))}

    if sport == "nba":
        m = STATE["nba"]
        if home not in m.ratings or away not in m.ratings:
            raise HTTPException(404, "unknown team (use 3-letter codes)")
        p = m.predict(home, away, neutral)
        return {"sport": sport, "home": home, "away": away,
                "result": {"home": round(p["home_win"], 4),
                           "away": round(p["away_win"], 4)},
                "projected_score": {"home": round(p["proj_home"], 1),
                                    "away": round(p["proj_away"], 1)},
                "spread": {f"home_{ln}": round(m.cover_prob(home, away, ln, neutral), 4)
                           for ln in (-10.5, -5.5, 5.5)},
                "totals": {f"over_{ln}": round(m.total_over_prob(home, away, ln), 4)
                           for ln in (215.5, 225.5, 235.5)}}

    if sport == "tennis":
        m = STATE["tennis"]
        names = {p["name"] for p in STATE["tennis_players"]}
        if a not in names or b not in names:
            raise HTTPException(404, "unknown player")
        pr = m.predict(a, b, surface)
        return {"sport": sport, "a": a, "b": b, "surface": surface,
                "result": {"a": round(pr["a_win"], 4), "b": round(pr["b_win"], 4)}}

    raise HTTPException(400, f"unknown sport '{sport}'")


@app.get("/ratings")
def ratings(sport: str, league: str | None = None):
    if sport == "clubs":
        if league not in STATE["clubs"]:
            raise HTTPException(404, f"unknown league '{league}'")
        m = STATE["clubs"][league]
        return [{"team": t, "attack": round(m.attack[t], 3),
                 "defence": round(m.defence[t], 3)}
                for t in STATE["club_teams"][league]]
    if sport in ("wc", "cl"):
        m = STATE[sport]
        teams = sorted(m.ratings) if sport == "wc" else STATE["cl_teams"]
        out = [{"team": t, "elo": round(m.rating(t), 1)} for t in teams]
        return sorted(out, key=lambda x: -x["elo"])
    if sport == "nba":
        return nba_mod.team_ratings(STATE["nba"])
    if sport == "tennis":
        return STATE["tennis_players"]
    raise HTTPException(400, f"unknown sport '{sport}'")


@app.get("/fixtures")
def fixtures(sport: str):
    if sport == "wc":
        from .models import wc_schedule
        fx = wc_schedule.fetch_schedule(STATE["wc"], days_ahead=14)
        return [{"date": f["date"], "time": f["time"], "live": f["live"],
                 "status": f.get("status"), "score": f.get("score"),
                 "home": f["home"], "away": f["away"],
                 "result": {"home": round(f["pred"]["H"], 4),
                            "draw": round(f["pred"]["D"], 4),
                            "away": round(f["pred"]["A"], 4)}} for f in fx]
    if sport == "nba":
        from .models import nba_schedule
        return nba_schedule.fetch_schedule(STATE["nba"], days_ahead=7)
    if sport == "clubs":
        from .models import football_data, club_schedule
        fx = football_data.club_fixtures(STATE["clubs"])
        if fx is None:
            fx, _ = club_schedule.fetch_all(STATE["clubs"])
        return fx
    if sport == "cl":
        from .models import football_data
        return football_data.cl_fixtures(STATE["cl"]) or []
    raise HTTPException(400, f"unknown sport '{sport}'")
