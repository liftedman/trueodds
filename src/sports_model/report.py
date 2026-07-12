"""Generate a self-contained HTML dashboard from the trained model.

`python -m sports_model.main report` fits the xG model for each top-5 league,
exports team attack/defence ratings + the honest calibration findings, and
writes a single static HTML file (data inlined) to data/processed/dashboard.html.

The page reimplements the Dixon-Coles prediction in JavaScript so it can compute
match probabilities live in the browser from the embedded ratings — letting you
pick any two teams and watch the model think, with no server.
"""

from __future__ import annotations

import json
from datetime import date

import pandas as pd

from . import config
from .models import dixon_coles, evaluate


def _build_data() -> dict:
    from . import crests as crests_mod
    from .models import club_schedule, football_data

    crests = crests_mod.load_crests()  # {code: {team: crest_url}}
    leagues: dict[str, dict] = {}
    models: dict[str, object] = {}
    for code, name in config.FOOTBALL_LEAGUES.items():
        df = evaluate.load_league(code)
        # Fit on all available data; 180-day half-life so ratings reflect
        # recent (end of latest season) strength.
        ref_date = pd.to_datetime(df["date"]).max()
        model = dixon_coles.fit(
            df, half_life_days=config.XG_HALF_LIFE_DAYS,
            ref_date=ref_date, use_xg=True,
        )

        # Dropdown teams = those in the most recent season (current top flight).
        latest = df["season"].max()
        current = sorted(set(df[df["season"] == latest]["home"]))

        teams = [
            {
                "name": t,
                "attack": round(model.attack.get(t, model._mean_attack), 4),
                "defence": round(model.defence.get(t, model._mean_defence), 4),
            }
            for t in current
        ]

        # Honest calibration: our xG model vs the bookmaker on the unseen season.
        try:
            bt = evaluate.backtest_season(
                code, latest, half_life_days=config.XG_HALF_LIFE_DAYS)
            calib = {
                "model_ll": round(bt["xg_model"]["log_loss"], 4),
                "book_ll": round(bt["bookmaker"]["log_loss"], 4),
                "season": latest,
            }
        except ValueError:
            calib = None

        # Recent match log (last 2 seasons) so the page can compute form + H2H.
        recent = sorted(df["season"].unique())[-2:]

        # Corner/card rates per current team -> attach to the team entries.
        rates = _count_rates(code, list(recent))
        league_crests = crests.get(code, {})
        for t in teams:
            r = rates.get(t["name"])
            if r:
                t.update(r)
            crest = league_crests.get(t["name"])
            if crest:
                t["crest"] = crest

        log_df = df[df["season"].isin(recent) & df["fthg"].notna()]
        match_log = [
            [r.date, r.home, r.away, int(r.fthg), int(r.ftag)]
            for r in log_df.itertuples(index=False)
        ]

        models[code] = model
        leagues[code] = {
            "name": name,
            "home_adv": round(model.home_adv, 4),
            "rho": round(model.rho, 4),
            "teams": teams,
            "calib": calib,
            "log": match_log,
            "fixtures": [],
        }

    # Upcoming club fixtures (kickoff times + live scores) per league.
    # Preferred: football-data.org (complete + live); else free TheSportsDB.
    fixtures_by_code = football_data.club_fixtures(models)
    if fixtures_by_code is None:
        # No API key at all — use TheSportsDB for every league.
        try:
            fixtures_by_code, _ = club_schedule.fetch_all(models)
        except Exception:
            fixtures_by_code = {}
    else:
        # football-data.org only covers leagues with a competition code; fill
        # the rest (Scotland/Belgium/Turkey/Greece) from TheSportsDB.
        gaps = {c: m for c, m in models.items()
                if not fixtures_by_code.get(c) and config.CLUB_TSDB_IDS.get(c)}
        if gaps:
            try:
                tsdb_fx, _ = club_schedule.fetch_all(gaps)
                for c, fx in tsdb_fx.items():
                    if fx:
                        fixtures_by_code[c] = fx
            except Exception:
                pass
    for code, fx in (fixtures_by_code or {}).items():
        leagues[code]["fixtures"] = fx

    nba_data = _build_nba_data()
    wnba_data = _build_wnba_data()
    summer_data = _build_summer_data()
    nbl_data = _build_bball("nbl", "NBL", title_field=8)
    ncaam_data = _build_bball("ncaam", "NCAA (M)", title_field=16)
    tennis_atp = _build_tennis_data("atp")
    tennis_wta = _build_tennis_data("wta")
    tennis_tours = []
    if tennis_atp:
        tennis_tours.append({"key": "tennis", "name": "ATP"})
    if tennis_wta:
        tennis_tours.append({"key": "tennis_wta", "name": "WTA"})
    # Which basketball leagues to offer in the app's Basketball hub dropdown.
    # Off-season leagues return None and simply don't appear.
    basketball = []
    for key, block, label in [
        ("nba", nba_data, "NBA"), ("wnba", wnba_data, "WNBA"),
        ("summer", summer_data, "Summer League"),
        ("nbl", nbl_data, "NBL"), ("ncaam", ncaam_data, "NCAA (M)"),
    ]:
        if block:
            basketball.append({"key": key, "name": label})

    return {
        "generated": date.today().isoformat(),
        "build": _git_sha(),  # which commit produced this snapshot (diagnostic)
        "tz": config.DISPLAY_TZ_LABEL,
        "leagues": leagues,
        "wc": _build_wc_data(),
        "nba": nba_data,
        "wnba": wnba_data,
        "summer": summer_data,
        "nbl": nbl_data,
        "ncaam": ncaam_data,
        "basketball_leagues": basketball,
        "nfl": _build_nfl_data(),
        "tennis": tennis_atp,
        "tennis_wta": tennis_wta,
        "tennis_tours": tennis_tours,
        "cl": _build_cl_data(),
        "news": _safe_news(),
        "receipts": _safe_receipts(),
        "wc_receipts": _safe_wc_receipts(),
        "results": _safe_results(),
    }


def _git_sha() -> str:
    """Short SHA of the commit this code is running from (for diagnosing which
    version the cloud actually executed). 'unknown' if git isn't available."""
    try:
        import subprocess
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=config.PROJECT_ROOT, text=True, stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return "unknown"


def _safe_news() -> list[dict]:
    """Recent sport news for the app feed; never fatal to the snapshot."""
    try:
        from . import news
        return news.fetch_news()
    except Exception:
        return []


def _safe_receipts() -> dict | None:
    """Out-of-sample track record ("The Receipts"); never fatal to the snapshot."""
    try:
        return evaluate.build_receipts()
    except Exception:
        return None


def _safe_wc_receipts() -> dict | None:
    """World Cup / international track record; never fatal to the snapshot."""
    try:
        return evaluate.build_wc_receipts()
    except Exception:
        return None


def _safe_results() -> list[dict]:
    """Recently finished matches for grading user picks; never fatal."""
    try:
        from .models import football_data
        return football_data.recent_results()
    except Exception:
        return []


def _count_rates(code: str, seasons: list[str]) -> dict[str, dict]:
    """Per-team corner/card rates (for & against) over the given seasons.

    cf/ca = corners for / against per match; kf/ka = cards the team gets /
    cards its opponents get. Used to project total corners and cards.
    """
    from . import db

    placeholders = ",".join("?" * len(seasons))
    with db.connect() as conn:
        rows = conn.execute(
            f"SELECT home, away, home_corners, away_corners, home_cards, "
            f"away_cards FROM football_matches WHERE league_code=? "
            f"AND season IN ({placeholders}) AND home_corners IS NOT NULL",
            (code, *seasons),
        ).fetchall()

    acc: dict[str, dict] = {}

    def bump(team, cf, ca, kf, ka):
        a = acc.setdefault(team, {"cf": 0, "ca": 0, "kf": 0, "ka": 0, "n": 0})
        a["cf"] += cf; a["ca"] += ca; a["kf"] += kf; a["ka"] += ka; a["n"] += 1

    for r in rows:
        hc, ac, hk, ak = (r["home_corners"], r["away_corners"],
                          r["home_cards"], r["away_cards"])
        if None in (hc, ac, hk, ak):
            continue
        bump(r["home"], hc, ac, hk, ak)   # home: for=hc, against=ac, cards=hk, opp=ak
        bump(r["away"], ac, hc, ak, hk)

    out: dict[str, dict] = {}
    for team, a in acc.items():
        if a["n"] == 0:
            continue
        out[team] = {
            "cf": round(a["cf"] / a["n"], 2), "ca": round(a["ca"] / a["n"], 2),
            "kf": round(a["kf"] / a["n"], 2), "ka": round(a["ka"] / a["n"], 2),
        }
    return out


def _build_nba_data() -> dict | None:
    """NBA Elo ratings + projected-score params + upcoming/live games."""
    from .models import espn, nba as nba_mod, nba_schedule

    try:
        model = nba_mod.fit_model()
    except Exception:
        return None

    # ESPN first (live scores + cloud-reachable); nba_api only as a fallback.
    try:
        fixtures = espn.fixtures("nba", model, nba_mod.TEAM_NAMES)
    except Exception:
        fixtures = []
    if not fixtures:
        try:
            fixtures = nba_schedule.fetch_schedule(model, days_ahead=7)
        except Exception:
            fixtures = []

    return {
        "home_adv": round(model.home_adv, 1),
        "margin_slope": round(model.margin_slope, 5),
        "mean_total": round(model.mean_total, 2),
        "margin_std": round(model.margin_std, 2),
        "total_std": round(model.total_std, 2),
        "teams": nba_mod.team_ratings(model),  # [{abbr, name, elo}] ranked
        "fixtures": fixtures,
        "title_odds": _safe_title_odds(model.ratings, nba_mod.TEAM_NAMES, 16),
        "log": _bball_log(nba_mod.load_games(), nba_mod.TEAM_NAMES),
    }


def _bball_log(df, names: dict, limit: int = 700) -> list:
    """Recent games as [date, home_name, away_name, home_pts, away_pts] for the
    app's form + head-to-head display (context only)."""
    import pandas as pd
    sub = df.tail(limit)
    out = []
    for r in sub.itertuples(index=False):
        if pd.isna(r.home_pts) or pd.isna(r.away_pts):
            continue
        out.append([r.date, names.get(r.home, r.home), names.get(r.away, r.away),
                    int(r.home_pts), int(r.away_pts)])
    return out


def _safe_title_odds(ratings, names, field_size) -> list[dict]:
    try:
        from .models import title_odds
        return title_odds.title_odds(ratings, names, field_size=field_size)
    except Exception:
        return []


def _build_wnba_data() -> dict | None:
    """WNBA Elo (ESPN-sourced) + projected-score params + live/upcoming games."""
    from .models import wnba as wnba_mod

    try:
        model = wnba_mod.fit_model()
    except Exception:
        return None
    if not model.ratings:
        return None
    try:
        fixtures = wnba_mod.fixtures(model)
    except Exception:
        fixtures = []
    return {
        "name": "WNBA",
        "home_adv": round(model.home_adv, 1),
        "margin_slope": round(model.margin_slope, 5),
        "mean_total": round(model.mean_total, 2),
        "margin_std": round(model.margin_std, 2),
        "total_std": round(model.total_std, 2),
        "teams": wnba_mod.team_ratings(model),
        "fixtures": fixtures,
        "title_odds": _safe_title_odds(model.ratings, wnba_mod.TEAM_NAMES, 8),
        "log": _bball_log(wnba_mod.load_games(), wnba_mod.TEAM_NAMES),
    }


def _build_summer_data() -> dict | None:
    """NBA Summer League — flagged as an exhibition (low-confidence)."""
    from .models import summer as summer_mod

    try:
        model = summer_mod.fit_model()
    except Exception:
        return None
    if not model.ratings:
        return None
    try:
        fixtures = summer_mod.fixtures(model)
    except Exception:
        fixtures = []
    return {
        "name": "Summer League",
        "exhibition": True,  # app shows a low-confidence banner
        "home_adv": round(model.home_adv, 1),
        "margin_slope": round(model.margin_slope, 5),
        "mean_total": round(model.mean_total, 2),
        "margin_std": round(model.margin_std, 2),
        "total_std": round(model.total_std, 2),
        "teams": summer_mod.team_ratings(model),
        "fixtures": fixtures,
        "log": _bball_log(summer_mod.load_games(), summer_mod.TEAM_NAMES),
    }


def _build_bball(league: str, name: str, title_field: int = 8) -> dict | None:
    """Generic ESPN basketball league (NBL, NCAA…). None if no games yet."""
    from .models import bball as bball_mod

    try:
        games = bball_mod.load_games(league)
        if games.empty:
            return None
        model = bball_mod.fit_model(league)
    except Exception:
        return None
    if not model.ratings:
        return None
    try:
        fixtures = bball_mod.fixtures(league, model)
    except Exception:
        fixtures = []
    return {
        "name": name,
        "home_adv": round(model.home_adv, 1),
        "margin_slope": round(model.margin_slope, 5),
        "mean_total": round(model.mean_total, 2),
        "margin_std": round(model.margin_std, 2),
        "total_std": round(model.total_std, 2),
        "teams": bball_mod.team_ratings(model, league),
        "fixtures": fixtures,
        "title_odds": _safe_title_odds(
            model.ratings, bball_mod.team_names(league), title_field),
        "log": _bball_log(games, bball_mod.team_names(league)),
    }


def _build_nfl_data() -> dict | None:
    """NFL Elo ratings, projected-score params, and upcoming/live fixtures."""
    from .models import espn, nfl as nfl_mod

    try:
        model = nfl_mod.fit_model()
    except Exception:
        return None
    if not model.ratings:
        return None
    # ESPN first (live scores in-season); the static schedule is the off-season
    # fallback so the tab still previews the fixture list.
    try:
        fixtures = espn.fixtures("nfl", model, nfl_mod.TEAM_NAMES, days=8)
    except Exception:
        fixtures = []
    if not fixtures:
        try:
            fixtures = nfl_mod.upcoming_fixtures(model)
        except Exception:
            fixtures = []
    return {
        "home_adv": round(model.home_adv, 1),
        "margin_slope": round(model.margin_slope, 5),
        "mean_total": round(model.mean_total, 2),
        "margin_std": round(model.margin_std, 2),
        "total_std": round(model.total_std, 2),
        "teams": nfl_mod.team_ratings(model),  # [{abbr, name, elo}] ranked
        "fixtures": fixtures,
    }


def _build_cl_data() -> dict | None:
    """Unified cross-league Elo for the Champions League predictor + fixtures."""
    from .models import club_elo, football_data

    try:
        model, diag = club_elo.build()
    except Exception:
        return None
    cl_teams = diag.get("cl_teams") or []
    if not cl_teams:
        return None
    teams = [{"name": t, "elo": round(model.rating(t), 1)} for t in cl_teams]
    teams.sort(key=lambda x: -x["elo"])

    fixtures = football_data.cl_fixtures(model) or []

    return {
        "home_adv": round(model.home_adv, 1),
        "sup_slope": round(model.sup_slope, 6),
        "total_base": round(model.total_base, 4),
        "total_gap": round(model.total_gap, 6),
        "tz": config.DISPLAY_TZ_LABEL,
        "teams": teams,
        "fixtures": fixtures,
    }


def _build_tennis_data(tour: str = "atp") -> dict | None:
    """Surface-aware Elo ratings for a tennis tour (atp / wta)."""
    from .models import tennis as tennis_mod

    try:
        matches = tennis_mod.load_matches(tour)
        model = tennis_mod.fit_model(matches, tour=tour)
        players = tennis_mod.active_players(model, matches)
    except Exception:
        return None
    if not players:
        return None
    return {"surface_weight": model.surface_weight, "players": players}


def _build_wc_data() -> dict:
    """Elo ratings, draw-model params, and upcoming fixtures for the World Cup."""
    from .models import world_cup, wc_schedule, football_data

    model = world_cup.fit_model()
    ratings = world_cup.wc_team_ratings(model, 2026)

    # Preferred: football-data.org — it carries the full official schedule
    # (group stage + already-decided knockout ties) with kickoff times and live
    # status. TheSportsDB's free endpoint only samples a couple of games a day,
    # so it's a fallback when there's no API key / it's unreachable.
    fixtures = football_data.wc_fixtures(model) or []
    if not fixtures:
        try:
            for f in wc_schedule.fetch_schedule(days_ahead=14, model=model):
                fixtures.append({
                    "date": f["date"], "time": f["time"], "live": f["live"],
                    "status": f.get("status", ""), "score": f.get("score"),
                    "home": f["home"], "away": f["away"],
                    "h": round(f["pred"]["H"], 3),
                    "d": round(f["pred"]["D"], 3),
                    "a": round(f["pred"]["A"], 3),
                    "ov": round(f["totals"]["OV"], 3),
                })
        except Exception:
            fixtures = []

    # Fallback: date-only fixtures from the ingested dataset.
    if not fixtures:
        for f in world_cup.upcoming_fixtures(model, limit=24):
            fixtures.append({
                "date": f["date"], "time": "", "live": False,
                "status": "", "score": None,
                "home": f["home"], "away": f["away"],
                "h": round(f["pred"]["H"], 3),
                "d": round(f["pred"]["D"], 3),
                "a": round(f["pred"]["A"], 3),
                "ov": round(model.predict_totals(f["home"], f["away"])["OV"], 3),
            })

    return {
        "home_adv": round(model.home_adv, 1),
        "sup_slope": round(model.sup_slope, 6),
        "total_base": round(model.total_base, 4),
        "total_gap": round(model.total_gap, 6),
        "tz": config.DISPLAY_TZ_LABEL,
        "teams": ratings,  # [{name, elo}] ranked
        "fixtures": fixtures,
    }


def build_html() -> str:
    data = _build_data()
    payload = json.dumps(data, separators=(",", ":"))
    return _TEMPLATE.replace("/*__DATA__*/", payload)


def write_report() -> None:
    config.ensure_dirs()
    path = config.PROCESSED_DIR / "dashboard.html"
    path.write_text(build_html(), encoding="utf-8")
    print(f"Dashboard written to {path}")


# ---------------------------------------------------------------------------
# HTML template. /*__DATA__*/ is replaced with the JSON payload.
# Design: floodlit-pitch ground (deep pine), sodium-amber accent, teal for
# totals, monospace numerics (odds-board feel). System fonts only.
# ---------------------------------------------------------------------------
_TEMPLATE = r"""<div id="app" data-theme="dark" data-sport="clubs">
<style>
  * { box-sizing: border-box; }
  #app {
    --ground:#0E1117; --panel:#171C24; --line:#242B35; --text:#E9EDF3; --muted:#8B95A4;
    --accent:#2E7DF6; --accent-ink:#FFFFFF; --teal:#5BA8A0;
    --hi:#16B364; --med:#E8A33D; --lo:#8B95A4;
    --shadow:none;
    --glow:color-mix(in srgb, var(--accent) 40%, transparent);
    --tint:color-mix(in srgb, var(--accent) 14%, var(--panel));
    --sans: -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    --mono: ui-monospace, "Cascadia Mono", "Consolas", "SFMono-Regular", monospace;
    background:
      radial-gradient(120% 80% at 100% 0%, color-mix(in srgb, var(--accent) 6%, transparent), transparent 60%),
      var(--ground);
    color: var(--text);
    font-family: var(--sans);
    line-height: 1.5;
    padding: clamp(20px, 4vw, 56px);
    max-width: 1000px;
    margin: 0 auto;
    min-height: 100vh;
    transition: background .3s, color .25s;
  }
  #app[data-theme="light"] {
    --ground:#F6F7F9; --panel:#FFFFFF; --line:#E4E8EE; --text:#131722; --muted:#5A6472;
    --shadow:0 1px 2px rgba(16,22,30,.06), 0 10px 30px rgba(16,22,30,.06);
  }
  #app[data-sport="clubs"]  { --accent:#16B364; --accent-ink:#04130B; }
  #app[data-sport="wc"]     { --accent:#2E7DF6; --accent-ink:#FFFFFF; }
  #app[data-sport="nba"]    { --accent:#8B5CF6; --accent-ink:#FFFFFF; }
  #app[data-sport="tennis"] { --accent:#84CC16; --accent-ink:#10210A; }
  #app[data-sport="cl"]     { --accent:#E5484D; --accent-ink:#FFFFFF; }
  .topline { display:flex; justify-content:space-between; align-items:center; gap:12px; }
  .theme-btn { border:1px solid var(--line); background:var(--panel); color:var(--text);
    border-radius:999px; padding:7px 13px; font-family:var(--mono); font-size:12px;
    cursor:pointer; white-space:nowrap; transition:border-color .2s; }
  .theme-btn:hover { border-color:var(--accent); }
  .eyebrow {
    font-family: var(--mono);
    font-size: 12px;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    color: var(--accent);
    margin: 0 0 14px;
  }
  h1 {
    font-size: clamp(28px, 5vw, 48px);
    font-weight: 800;
    letter-spacing: -0.02em;
    line-height: 1.05;
    margin: 0 0 12px;
  }
  .lede { color: var(--muted); max-width: 60ch; margin: 0 0 8px; }
  .lede b { color: var(--text); font-weight: 600; }
  .tabs {
    position: sticky; top: 0; z-index: 20; display: flex; flex-wrap: wrap; gap: 6px;
    background: var(--ground); padding: 12px 0 10px; margin: 18px 0 4px;
    border-bottom: 1px solid var(--line);
  }
  .tab-btn {
    background: transparent; color: var(--muted); border: 1px solid var(--line);
    border-radius: 9px; padding: 9px 16px; font-family: var(--sans);
    font-size: 14px; font-weight: 600; cursor: pointer;
  }
  .tab-btn:hover { color: var(--text); border-color: var(--muted); }
  .tab-btn.active { color: var(--accent-ink); background: var(--accent); border-color: var(--accent);
    box-shadow: 0 4px 16px var(--glow); }
  .tab-btn:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
  .tabpanel[hidden] { display: none; }
  .panel {
    background: var(--panel);
    border: 1px solid var(--line);
    border-radius: 14px;
    padding: clamp(18px, 3vw, 28px);
    margin-top: 28px;
    box-shadow: var(--shadow);
    transition: background .25s, border-color .25s, box-shadow .2s;
  }
  .section-label {
    font-family: var(--mono);
    font-size: 12px;
    letter-spacing: 0.16em;
    text-transform: uppercase;
    color: var(--muted);
    margin: 0 0 18px;
  }
  .controls { display: flex; flex-wrap: wrap; gap: 14px; align-items: flex-end; }
  .control { display: flex; flex-direction: column; gap: 6px; }
  .control label {
    font-family: var(--mono); font-size: 11px; letter-spacing: 0.12em;
    text-transform: uppercase; color: var(--muted);
  }
  select {
    background: var(--ground);
    color: var(--text);
    border: 1px solid var(--line);
    border-radius: 8px;
    padding: 9px 12px;
    font-family: var(--sans);
    font-size: 15px;
    min-width: 150px;
  }
  select:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
  .matchup {
    display: flex; align-items: center; justify-content: center; gap: 18px;
    margin: 26px 0 8px; font-size: clamp(18px, 3.2vw, 26px); font-weight: 800;
    text-align: center;
  }
  .matchup .vs {
    font-family: var(--mono); font-size: 13px; color: var(--accent);
    font-weight: 400; letter-spacing: 0.1em;
  }
  .matchup .team { flex: 1; }
  .matchup .home { text-align: right; }
  .matchup .away { text-align: left; }
  .bars { margin-top: 18px; display: flex; flex-direction: column; gap: 12px; }
  .bar-row { display: grid; grid-template-columns: 92px 1fr 64px; align-items: center; gap: 14px; }
  .bar-row .name {
    font-family: var(--mono); font-size: 11px; letter-spacing: 0.08em;
    text-transform: uppercase; color: var(--muted);
  }
  .track { background: var(--ground); border-radius: 6px; height: 22px; overflow: hidden; border: 1px solid var(--line); }
  .fill { height: 100%; width: 0; background: var(--accent); border-radius: 5px 0 0 5px;
          box-shadow: 0 0 14px var(--glow);
          transition: width 0.7s cubic-bezier(.2,.8,.2,1), background .25s, box-shadow .25s; }
  .fill.draw { opacity: .55; box-shadow: none; }
  .fill.away { opacity: .35; box-shadow: none; }
  .pct { font-family: var(--mono); font-size: 16px; text-align: right; font-variant-numeric: tabular-nums; color: var(--muted); }
  .pct.lead { color: var(--accent); font-weight: 700; }
  .swap {
    background: var(--ground); color: var(--text); border: 1px solid var(--line);
    border-radius: 8px; padding: 9px 14px; font-family: var(--mono); font-size: 13px;
    cursor: pointer; letter-spacing: 0.06em;
  }
  .swap:hover { border-color: var(--accent); color: var(--accent); }
  .swap:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
  .scorelines {
    margin-top: 18px; padding-top: 16px; border-top: 1px dashed var(--line);
    display: flex; flex-wrap: wrap; gap: 16px; align-items: baseline;
  }
  .scorelines .sl-label {
    font-family: var(--mono); font-size: 11px; letter-spacing: 0.12em;
    text-transform: uppercase; color: var(--muted);
  }
  .scorelines .sl { font-family: var(--mono); font-size: 13px; color: var(--muted); }
  .scorelines .sl b { color: var(--text); font-size: 15px; }
  .markets { margin-top: 18px; padding-top: 16px; border-top: 1px dashed var(--line);
             display: flex; flex-wrap: wrap; gap: 10px; align-items: center; }
  .markets .sl-label { font-family: var(--mono); font-size: 11px; letter-spacing: 0.12em;
             text-transform: uppercase; color: var(--muted); width: 100%; margin-bottom: 2px; }
  .mkt { display: flex; flex-direction: column; gap: 2px; padding: 7px 12px;
         background: var(--ground); border: 1px solid var(--line); border-radius: 8px; min-width: 78px; }
  .mkt .mn { font-family: var(--mono); font-size: 10px; letter-spacing: 0.06em; color: var(--muted); }
  .mkt .mp { font-family: var(--mono); font-size: 16px; font-variant-numeric: tabular-nums; }
  .mkt.hi .mp { color: var(--accent); }            /* >=70% — high confidence */
  .mkt.hi { border-color: var(--accent); background: var(--tint); }
  /* form & head-to-head */
  .formh2h { margin-top: 18px; padding-top: 16px; border-top: 1px dashed var(--line);
             display: grid; grid-template-columns: 1fr 1fr 1.4fr; gap: 18px; }
  .fh-col { display: flex; flex-direction: column; gap: 8px; }
  .fh-label { font-family: var(--mono); font-size: 11px; letter-spacing: 0.1em;
              text-transform: uppercase; color: var(--muted); }
  .streak { display: flex; gap: 5px; }
  .streak .g {
    width: 22px; height: 22px; border-radius: 5px; display: grid; place-items: center;
    font-family: var(--mono); font-size: 11px; font-weight: 700; color: var(--ground);
  }
  .streak .g.W { background: var(--accent); }
  .streak .g.D { background: var(--muted); }
  .streak .g.L { background: #6E4A4A; color: var(--text); }
  .fh-col.h2h #fh-h2h { font-family: var(--mono); font-size: 12px; color: var(--text); line-height: 1.7; }
  .fh-note { font-family: var(--mono); font-size: 11px; color: var(--muted);
             margin: 14px 0 0; line-height: 1.5; }
  @media (max-width: 560px) { .formh2h { grid-template-columns: 1fr 1fr; } }
  .legend { font-family: var(--mono); font-size: 11px; color: var(--muted); margin: -8px 0 16px; }
  .legend .k { display: inline-block; width: 22px; height: 9px; border-radius: 3px; vertical-align: middle; margin-right: 5px; }
  .legend .k.atk { background: var(--accent); }
  .legend .k.def { background: var(--teal); }
  .totals {
    margin-top: 22px; padding-top: 18px; border-top: 1px dashed var(--line);
    display: flex; flex-wrap: wrap; gap: 22px; align-items: center;
    font-family: var(--mono); font-size: 14px; color: var(--muted);
  }
  .totals b { color: var(--teal); font-size: 18px; }
  .totals .xg b { color: var(--text); }
  /* ratings */
  .rate-row { display: grid; grid-template-columns: 130px 1fr 1fr; gap: 12px; align-items: center;
              padding: 5px 0; border-bottom: 1px solid var(--line); }
  .rate-row .tname { font-size: 13px; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .rate-bar { display: flex; align-items: center; gap: 8px; }
  .rate-bar .seg { height: 9px; border-radius: 4px; }
  .rate-bar.atk .seg { background: var(--accent); }
  .rate-bar.def .seg { background: var(--teal); }
  .rate-bar .v { font-family: var(--mono); font-size: 11px; color: var(--muted); min-width: 38px; }
  .rate-head { display: grid; grid-template-columns: 130px 1fr 1fr; gap: 12px;
               font-family: var(--mono); font-size: 11px; letter-spacing: 0.1em;
               text-transform: uppercase; color: var(--muted); margin-bottom: 8px; }
  /* findings */
  table.calib { width: 100%; border-collapse: collapse; font-family: var(--mono); font-size: 13px; }
  table.calib th, table.calib td { text-align: right; padding: 7px 10px; border-bottom: 1px solid var(--line); }
  table.calib th:first-child, table.calib td:first-child { text-align: left; }
  table.calib th { color: var(--muted); font-weight: 400; letter-spacing: 0.06em; }
  .verdict { margin-top: 18px; padding: 16px 18px; border-left: 3px solid var(--accent);
             background: var(--tint); border-radius: 0 8px 8px 0; color: var(--text); }
  .verdict b { color: var(--accent); }
  .badge { font-family: var(--mono); font-size: 10px; letter-spacing: 0.12em;
           background: var(--teal); color: var(--ground); padding: 2px 7px;
           border-radius: 4px; vertical-align: middle; margin-left: 6px; }
  .toggle { display: flex; align-items: center; gap: 7px; font-size: 14px;
            color: var(--text); padding: 8px 0; cursor: pointer; }
  .toggle input { width: 16px; height: 16px; accent-color: var(--accent); }
  /* WC fixtures list */
  .fix { display: grid; grid-template-columns: 78px 1fr auto; gap: 14px;
         align-items: center; padding: 11px 0; border-bottom: 1px solid var(--line); }
  .fix .fdate { font-family: var(--mono); font-size: 11px; color: var(--muted); }
  .fix .teams { font-size: 14px; font-weight: 600; }
  .fix .teams .at { color: var(--muted); font-weight: 400; font-size: 12px; }
  .fix .odds { display: flex; gap: 4px; font-family: var(--mono); font-size: 11px; }
  .fix .odds span { padding: 3px 7px; border-radius: 5px; background: var(--ground);
                    border: 1px solid var(--line); color: var(--muted); min-width: 42px; text-align: center; }
  .fix .odds span.win { border-color: var(--accent); color: var(--accent); }
  .fix .fdate .ftime { color: var(--text); }
  .livedot { color: #E5484D; font-family: var(--mono); font-size: 10px;
             font-weight: 700; letter-spacing: 0.08em; margin-left: 8px;
             animation: pulse 1.4s ease-in-out infinite; }
  @keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.35; } }
  @media (prefers-reduced-motion: reduce) { .livedot { animation: none; } }
  @media (max-width: 560px) { .fix { grid-template-columns: 60px 1fr; }
                              .fix .odds { grid-column: 1 / -1; } }
  .morebtn {
    margin-top: 12px; background: transparent; color: var(--accent);
    border: 1px solid var(--line); border-radius: 8px; padding: 8px 14px;
    font-family: var(--mono); font-size: 12px; letter-spacing: 0.06em;
    cursor: pointer; width: 100%;
  }
  .morebtn:hover { border-color: var(--accent); }
  .morebtn:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
  .nba-rrow { display: grid; grid-template-columns: 28px 1fr auto; gap: 12px;
              align-items: center; padding: 6px 0; border-bottom: 1px solid var(--line); }
  .nba-rrow .rk { font-family: var(--mono); font-size: 11px; color: var(--muted); text-align: right; }
  .nba-rrow .rn { font-size: 13px; font-weight: 600; }
  .nba-rrow .re { font-family: var(--mono); font-size: 12px; color: var(--accent); }
  .foot { margin-top: 32px; font-family: var(--mono); font-size: 11px; color: var(--muted); letter-spacing: 0.04em; }
  @media (prefers-reduced-motion: reduce) { .fill { transition: none; } }
  @media (max-width: 560px) { .bar-row { grid-template-columns: 76px 1fr 52px; } }
</style>

<div class="topline">
  <p class="eyebrow">sports-model · multi-sport predictions</p>
  <button id="theme-btn" class="theme-btn" type="button">☀ Light</button>
</div>
<h1>Watch the model think.</h1>
<p class="lede">Pick a sport, pick two teams, and watch a model compute live
probabilities in your browser — football clubs, the World Cup, and the NBA.
Every number is honest; the model's real track record is under <b>About</b>.</p>

<nav class="tabs" id="tabs">
  <button class="tab-btn active" data-tab="clubs" type="button">⚽ Clubs</button>
  <button class="tab-btn" data-tab="wc" type="button">🏆 World Cup</button>
  <button class="tab-btn" data-tab="nba" type="button">🏀 NBA</button>
  <button class="tab-btn" data-tab="tennis" type="button">🎾 Tennis</button>
  <button class="tab-btn" data-tab="cl" type="button">⭐ UCL</button>
  <button class="tab-btn" data-tab="about" type="button">ⓘ About</button>
</nav>

<section class="tabpanel" id="panel-clubs">
<div class="panel">
  <p class="section-label">Live predictor</p>
  <div class="controls">
    <div class="control">
      <label for="league">League</label>
      <select id="league"></select>
    </div>
    <div class="control">
      <label for="home">Home team</label>
      <select id="home"></select>
    </div>
    <div class="control">
      <label for="away">Away team</label>
      <select id="away"></select>
    </div>
    <div class="control">
      <label for="home-out">Home key out</label>
      <select id="home-out" class="outsel"></select>
    </div>
    <div class="control">
      <label for="away-out">Away key out</label>
      <select id="away-out" class="outsel"></select>
    </div>
    <div class="control">
      <label for="swap">&nbsp;</label>
      <button id="swap" class="swap" type="button" title="Swap home and away">⇄ swap</button>
    </div>
  </div>

  <div class="matchup">
    <span class="team home" id="m-home">—</span>
    <span class="vs">VS</span>
    <span class="team away" id="m-away">—</span>
  </div>

  <div class="bars">
    <div class="bar-row"><span class="name">Home win</span>
      <div class="track"><div class="fill" id="f-h"></div></div><span class="pct" id="p-h">—</span></div>
    <div class="bar-row"><span class="name">Draw</span>
      <div class="track"><div class="fill draw" id="f-d"></div></div><span class="pct" id="p-d">—</span></div>
    <div class="bar-row"><span class="name">Away win</span>
      <div class="track"><div class="fill away" id="f-a"></div></div><span class="pct" id="p-a">—</span></div>
  </div>

  <div class="totals">
    <span>Goals market &nbsp; Over 2.5 <b id="t-ov">—</b> &nbsp;·&nbsp; Under 2.5 <b id="t-un">—</b></span>
    <span class="xg">Expected goals <b id="xg">—</b></span>
  </div>

  <div class="markets" id="markets"></div>
  <div class="markets" id="result-markets"></div>
  <div class="markets" id="cc-markets"></div>
  <div class="scorelines" id="scorelines"></div>

  <div class="formh2h" id="formh2h">
    <div class="fh-col">
      <span class="fh-label" id="fh-home-label">—</span>
      <span class="streak" id="fh-home"></span>
    </div>
    <div class="fh-col">
      <span class="fh-label" id="fh-away-label">—</span>
      <span class="streak" id="fh-away"></span>
    </div>
    <div class="fh-col h2h">
      <span class="fh-label">Recent head-to-head</span>
      <span id="fh-h2h">—</span>
    </div>
  </div>
  <p class="fh-note">Form (last 5: newest first) adds a small measured edge;
  head-to-head added nothing in our test — shown for interest, not used in the
  prediction above.</p>
</div>

<div class="panel">
  <p class="section-label">Upcoming fixtures &amp; predictions
    <span id="club-fix-league"></span></p>
  <div id="club-fixtures"></div>
</div>

<div class="panel">
  <p class="section-label">How the model rates <span id="rate-league">—</span></p>
  <p class="legend"><span class="k atk"></span>Attack
     &nbsp;&nbsp; <span class="k def"></span>Defensive strength
     &nbsp;— longer bar is better, sorted by overall quality</p>
  <div class="rate-head"><span>Team</span><span>Attack</span><span>Defence</span></div>
  <div id="ratings"></div>
</div>
</section>

<section class="tabpanel" id="panel-wc" hidden>
<div class="panel wc">
  <p class="section-label">World Cup 2026 · live predictor <span class="badge">Elo</span></p>
  <p class="lede" style="margin-bottom:16px">A different model for a different
  problem: national teams play too rarely for a goals model, so this uses Elo
  ratings built from 49,000 internationals back to 1872. Group games are at
  neutral venues; turn off "neutral" to add home advantage.</p>
  <div class="controls">
    <div class="control">
      <label for="wc-home">Team A</label>
      <select id="wc-home"></select>
    </div>
    <div class="control">
      <label for="wc-away">Team B</label>
      <select id="wc-away"></select>
    </div>
    <div class="control">
      <label for="wc-neutral">Venue</label>
      <label class="toggle"><input type="checkbox" id="wc-neutral" checked> neutral</label>
    </div>
    <div class="control">
      <label for="wc-a-out">A key out</label>
      <select id="wc-a-out" class="outsel"></select>
    </div>
    <div class="control">
      <label for="wc-b-out">B key out</label>
      <select id="wc-b-out" class="outsel"></select>
    </div>
  </div>
  <div class="matchup">
    <span class="team home" id="wc-m-home">—</span>
    <span class="vs">VS</span>
    <span class="team away" id="wc-m-away">—</span>
  </div>
  <div class="bars">
    <div class="bar-row"><span class="name" id="wc-n-h">A win</span>
      <div class="track"><div class="fill" id="wc-f-h"></div></div><span class="pct" id="wc-p-h">—</span></div>
    <div class="bar-row"><span class="name">Draw</span>
      <div class="track"><div class="fill draw" id="wc-f-d"></div></div><span class="pct" id="wc-p-d">—</span></div>
    <div class="bar-row"><span class="name" id="wc-n-a">B win</span>
      <div class="track"><div class="fill away" id="wc-f-a"></div></div><span class="pct" id="wc-p-a">—</span></div>
  </div>
  <div class="totals">
    <span>Goals market &nbsp; Over 2.5 <b id="wc-t-ov">—</b> &nbsp;·&nbsp; Under 2.5 <b id="wc-t-un">—</b></span>
    <span class="xg">Expected goals <b id="wc-xg">—</b></span>
  </div>
  <div class="scorelines" id="wc-scorelines"></div>
  <div class="markets" id="wc-markets"></div>
  <div class="markets" id="wc-result-markets"></div>
  <div class="totals"><span class="xg">Elo rating &nbsp; <b id="wc-elo">—</b></span></div>
</div>

<div class="panel">
  <p class="section-label">Upcoming fixtures &amp; predictions</p>
  <div id="wc-fixtures"></div>
</div>
</section>

<section class="tabpanel" id="panel-nba" hidden>
<div class="panel nba" id="nba-panel">
  <p class="section-label">NBA · live predictor <span class="badge">Elo</span></p>
  <p class="lede" style="margin-bottom:16px">Ratings from 8,000+ games since
  2019, regressed 25% each off-season. Basketball has no draws — just a win
  probability and a projected score. Home court is on by default.</p>
  <div class="controls">
    <div class="control">
      <label for="nba-home">Home team</label>
      <select id="nba-home"></select>
    </div>
    <div class="control">
      <label for="nba-away">Away team</label>
      <select id="nba-away"></select>
    </div>
    <div class="control">
      <label for="nba-neutral">Venue</label>
      <label class="toggle"><input type="checkbox" id="nba-neutral"> neutral</label>
    </div>
    <div class="control">
      <label for="nba-h-out">Home key out</label>
      <select id="nba-h-out" class="outsel"></select>
    </div>
    <div class="control">
      <label for="nba-a-out">Away key out</label>
      <select id="nba-a-out" class="outsel"></select>
    </div>
  </div>
  <div class="matchup">
    <span class="team home" id="nba-m-home">—</span>
    <span class="vs">VS</span>
    <span class="team away" id="nba-m-away">—</span>
  </div>
  <div class="bars">
    <div class="bar-row"><span class="name" id="nba-n-h">Home</span>
      <div class="track"><div class="fill" id="nba-f-h"></div></div><span class="pct" id="nba-p-h">—</span></div>
    <div class="bar-row"><span class="name" id="nba-n-a">Away</span>
      <div class="track"><div class="fill away" id="nba-f-a"></div></div><span class="pct" id="nba-p-a">—</span></div>
  </div>
  <div class="totals">
    <span>Projected score <b id="nba-proj">—</b></span>
    <span class="xg">Elo rating <b id="nba-elo">—</b></span>
  </div>
  <div class="markets" id="nba-markets"></div>
  <p class="section-label" style="margin:24px 0 12px">Upcoming games</p>
  <div id="nba-fixtures"></div>
  <p class="section-label" style="margin:24px 0 12px">Power ratings</p>
  <div id="nba-ratings"></div>
</div>
</section>

<section class="tabpanel" id="panel-tennis" hidden>
<div class="panel">
  <p class="section-label">Tennis · ATP predictor <span class="badge">Elo</span></p>
  <p class="lede" style="margin-bottom:16px">Surface-aware Elo from 22,000 ATP
  matches since 2018. Pick two players and a surface — clay specialists and
  grass-court players rate differently, and the prediction reflects it.</p>
  <div class="controls">
    <div class="control">
      <label for="t-a">Player A</label>
      <select id="t-a"></select>
    </div>
    <div class="control">
      <label for="t-b">Player B</label>
      <select id="t-b"></select>
    </div>
    <div class="control">
      <label for="t-surface">Surface</label>
      <select id="t-surface">
        <option value="Hard" selected>Hard</option>
        <option value="Clay">Clay</option>
        <option value="Grass">Grass</option>
      </select>
    </div>
  </div>
  <div class="matchup">
    <span class="team home" id="t-m-a">—</span>
    <span class="vs">VS</span>
    <span class="team away" id="t-m-b">—</span>
  </div>
  <div class="bars">
    <div class="bar-row"><span class="name" id="t-n-a">Player A</span>
      <div class="track"><div class="fill" id="t-f-a"></div></div><span class="pct" id="t-p-a">—</span></div>
    <div class="bar-row"><span class="name" id="t-n-b">Player B</span>
      <div class="track"><div class="fill away" id="t-f-b"></div></div><span class="pct" id="t-p-b">—</span></div>
  </div>
  <div class="totals"><span class="xg">Elo (overall) <b id="t-elo">—</b></span></div>
  <p class="section-label" style="margin:24px 0 12px">Power ratings</p>
  <div id="t-ratings"></div>
</div>
</section>

<section class="tabpanel" id="panel-cl" hidden>
<div class="panel">
  <p class="section-label">Champions League · predictor <span class="badge">Elo</span></p>
  <p class="lede" style="margin-bottom:16px">A unified cross-league Elo so clubs
  from different leagues can be compared. Honest caveat: it's anchored by one
  season of European results, so it's directional — and clubs that dominate
  weaker leagues are rated a little generously.</p>
  <div class="controls">
    <div class="control">
      <label for="cl-home">Home / Team A</label>
      <select id="cl-home"></select>
    </div>
    <div class="control">
      <label for="cl-away">Away / Team B</label>
      <select id="cl-away"></select>
    </div>
    <div class="control">
      <label for="cl-neutral">Venue</label>
      <label class="toggle"><input type="checkbox" id="cl-neutral"> neutral (final)</label>
    </div>
    <div class="control">
      <label for="cl-a-out">Home key out</label>
      <select id="cl-a-out" class="outsel"></select>
    </div>
    <div class="control">
      <label for="cl-b-out">Away key out</label>
      <select id="cl-b-out" class="outsel"></select>
    </div>
  </div>
  <div class="matchup">
    <span class="team home" id="cl-m-home">—</span>
    <span class="vs">VS</span>
    <span class="team away" id="cl-m-away">—</span>
  </div>
  <div class="bars">
    <div class="bar-row"><span class="name" id="cl-n-h">Home</span>
      <div class="track"><div class="fill" id="cl-f-h"></div></div><span class="pct" id="cl-p-h">—</span></div>
    <div class="bar-row"><span class="name">Draw</span>
      <div class="track"><div class="fill draw" id="cl-f-d"></div></div><span class="pct" id="cl-p-d">—</span></div>
    <div class="bar-row"><span class="name" id="cl-n-a">Away</span>
      <div class="track"><div class="fill away" id="cl-f-a"></div></div><span class="pct" id="cl-p-a">—</span></div>
  </div>
  <div class="totals">
    <span>Goals market &nbsp; Over 2.5 <b id="cl-t-ov">—</b> &nbsp;·&nbsp; Under 2.5 <b id="cl-t-un">—</b></span>
    <span class="xg">Expected goals <b id="cl-xg">—</b></span>
  </div>
  <div class="markets" id="cl-markets"></div>
  <div class="scorelines" id="cl-scorelines"></div>
  <div class="totals"><span class="xg">Elo rating <b id="cl-elo">—</b></span></div>
</div>

<div class="panel">
  <p class="section-label">Upcoming fixtures &amp; predictions</p>
  <div id="cl-fixtures"></div>
</div>
</section>

<section class="tabpanel" id="panel-about" hidden>
<div class="panel">
  <p class="section-label">How it works</p>
  <p class="lede" style="max-width:68ch">Three models, each suited to its sport.
  <b>Clubs</b> use a Dixon-Coles expected-goals model (teams play often, shot
  quality matters). The <b>World Cup</b>, <b>NBA</b> and <b>Tennis</b> use Elo
  ratings (teams/players meet rarely; tennis Elo is surface-aware). Every
  probability is computed live in your browser from the embedded ratings.</p>
  <p class="lede" style="max-width:68ch; margin-top:12px">Data: results &amp;
  odds from football-data.co.uk, expected goals from understat, internationals
  from a public results archive, NBA from the official stats API, ATP tennis
  from the TML-Database mirror, and live fixtures/scores from football-data.org
  and TheSportsDB.</p>
</div>

<div class="panel">
  <p class="section-label">The honest scoreboard</p>
  <p class="lede" style="margin-bottom:16px">Log loss on the most recent season,
  which the model never trained on. Lower is better. The bookmaker's closing
  line wins in every league — by a small, consistent margin.</p>
  <table class="calib">
    <thead><tr><th>League</th><th>Our model</th><th>Bookmaker</th><th>Gap</th></tr></thead>
    <tbody id="calib"></tbody>
  </table>
  <div class="verdict">
    <b>Verdict: no betting edge.</b> Across every market tested (match result and
    over/under), every signal (goals and xG), and 18 leagues from the Premier
    League to the Belgian top flight, the model's picks lose to the closing line
    by 3–4% on a clean same-book test. That deficit is uniform — the limit is the
    model, not the market. This dashboard is a learning tool, not a betting tool.
  </div>
</div>
</section>

<p class="foot" id="foot">—</p>

<script>
const DATA = /*__DATA__*/;
const MAXG = 10;
const FACT = [1];
for (let k = 1; k <= MAXG; k++) FACT[k] = FACT[k-1] * k;

function pois(k, lam) { return Math.pow(lam, k) * Math.exp(-lam) / FACT[k]; }

function tau(x, y, lh, la, rho) {
  if (x===0 && y===0) return 1 - lh*la*rho;
  if (x===0 && y===1) return 1 + lh*rho;
  if (x===1 && y===0) return 1 + la*rho;
  if (x===1 && y===1) return 1 - rho;
  return 1;
}

function rating(league, team) {
  const t = DATA.leagues[league].teams.find(x => x.name === team);
  return t || {attack: 0, defence: 0};
}

function predict(league, home, away, outH = 0, outA = 0) {
  const L = DATA.leagues[league];
  const h = rating(league, home), a = rating(league, away);
  // Key players out: weaken that team's attack and let them concede a bit more.
  const lh = Math.exp((h.attack - 0.07*outH) + (a.defence + 0.05*outA) + L.home_adv);
  const la = Math.exp((a.attack - 0.07*outA) + (h.defence + 0.05*outH));
  const ph = [], pa = [];
  for (let k = 0; k <= MAXG; k++) { ph[k] = pois(k, lh); pa[k] = pois(k, la); }
  let mat = [], sum = 0;
  for (let i = 0; i <= MAXG; i++) { mat[i] = [];
    for (let j = 0; j <= MAXG; j++) {
      let p = ph[i] * pa[j];
      if (i < 2 && j < 2) p *= tau(i, j, lh, la, L.rho);
      mat[i][j] = p; sum += p;
    }
  }
  let H=0, D=0, A=0, OV=0, UN=0, o05=0, o15=0, o35=0, btts=0;
  let hcapH=0, hcapA=0, csH=0, csA=0, ttH=0, ttA=0;
  const scores = [];
  for (let i = 0; i <= MAXG; i++)
    for (let j = 0; j <= MAXG; j++) {
      const p = mat[i][j] / sum;
      if (i > j) H += p; else if (i === j) D += p; else A += p;
      if (i + j > 2) OV += p; else UN += p;
      if (i + j > 0) o05 += p;
      if (i + j > 1) o15 += p;
      if (i + j > 3) o35 += p;
      if (i >= 1 && j >= 1) btts += p;
      if (i - j >= 2) hcapH += p;        // home -1.5
      if (j - i >= 2) hcapA += p;        // away -1.5
      if (j === 0) csH += p;             // home clean sheet
      if (i === 0) csA += p;             // away clean sheet
      if (i >= 2) ttH += p;              // home over 1.5
      if (j >= 2) ttA += p;              // away over 1.5
      scores.push({i, j, p});
    }
  scores.sort((a, b) => b.p - a.p);
  const ha = H + A || 1;
  return {H, D, A, OV, UN, lh, la, scores: scores.slice(0, 5),
          mk: {o05, o15, o25: OV, o35, btts},
          rm: {dc1x: H+D, dc12: H+A, dcx2: D+A, dnbH: H/ha, dnbA: A/ha,
               hcapH, hcapA, csH, csA, ttH, ttA}};
}

const $ = id => document.getElementById(id);

// Populate a "key players out" selector (0-3) and wire it to a callback.
function fillOut(sel, onChange) {
  sel.innerHTML = "";
  for (let i = 0; i <= 3; i++) {
    const o = document.createElement("option");
    o.value = i; o.textContent = i === 0 ? "Full squad" : i + " key out";
    sel.appendChild(o);
  }
  sel.addEventListener("change", onChange);
}

function fillSelect(sel, items, selected) {
  sel.innerHTML = "";
  items.forEach(it => {
    const o = document.createElement("option");
    o.value = it; o.textContent = it;
    if (it === selected) o.selected = true;
    sel.appendChild(o);
  });
}

function renderRatings(league) {
  const teams = DATA.leagues[league].teams.slice();
  const atks = teams.map(t => t.attack), defs = teams.map(t => -t.defence);
  const aMin = Math.min(...atks), aMax = Math.max(...atks);
  const dMin = Math.min(...defs), dMax = Math.max(...defs);
  const norm = (v, lo, hi) => hi === lo ? 0.5 : (v - lo) / (hi - lo);
  // sort by overall strength (attack + defensive strength)
  teams.sort((p, q) => (q.attack - q.defence) - (p.attack - p.defence));
  $("rate-league").textContent = DATA.leagues[league].name;
  const box = $("ratings"); box.innerHTML = "";
  teams.forEach(t => {
    const dstr = -t.defence;
    const aw = (8 + norm(t.attack, aMin, aMax) * 92).toFixed(0);
    const dw = (8 + norm(dstr, dMin, dMax) * 92).toFixed(0);
    const row = document.createElement("div");
    row.className = "rate-row";
    row.innerHTML =
      `<span class="tname">${t.name}</span>` +
      `<span class="rate-bar atk"><span class="seg" style="width:${aw}%"></span><span class="v">${t.attack.toFixed(2)}</span></span>` +
      `<span class="rate-bar def"><span class="seg" style="width:${dw}%"></span><span class="v">${dstr.toFixed(2)}</span></span>`;
    box.appendChild(row);
  });
}

// Render rows into a box, showing the first `visible` and hiding the rest
// behind a "Show all" toggle. Keeps long lists calm but one tap from complete.
function renderCollapsible(box, rowsHtml, visible, noun) {
  box.innerHTML = "";
  rowsHtml.slice(0, visible).forEach(h => box.insertAdjacentHTML("beforeend", h));
  if (rowsHtml.length <= visible) return;
  const extra = document.createElement("div");
  extra.style.display = "none";
  rowsHtml.slice(visible).forEach(h => extra.insertAdjacentHTML("beforeend", h));
  box.appendChild(extra);
  const btn = document.createElement("button");
  btn.className = "morebtn";
  const total = rowsHtml.length;
  const collapsed = () => `Show all ${total} ${noun}  ▾`;
  btn.textContent = collapsed();
  btn.addEventListener("click", () => {
    const open = extra.style.display === "none";
    extra.style.display = open ? "block" : "none";
    btn.textContent = open ? "Show less  ▴" : collapsed();
  });
  box.appendChild(btn);
}

function fixtureRowHtml(f, tz) {
  const probs = {h: f.h, d: f.d, a: f.a};
  const fav = Object.keys(probs).reduce((x, y) => probs[x] >= probs[y] ? x : y);
  const when = f.time
    ? `${f.date}<br><span class="ftime">${f.time} ${tz}</span>` : f.date;
  const liveLabel = (f.status === "PAUSED" ? "HT" : "LIVE")
    + (f.score ? " " + f.score : "");
  const live = f.live ? `<span class="livedot">● ${liveLabel}</span>` : "";
  return `<div class="fix"><span class="fdate">${when}</span>`
    + `<span class="teams">${f.home} <span class="at">v</span> ${f.away}${live}`
    + `<br><span class="at">Over 2.5: ${(f.ov*100).toFixed(0)}%</span></span>`
    + `<span class="odds">`
    + `<span class="${fav==='h'?'win':''}">${(f.h*100).toFixed(0)}%</span>`
    + `<span class="${fav==='d'?'win':''}">${(f.d*100).toFixed(0)}%</span>`
    + `<span class="${fav==='a'?'win':''}">${(f.a*100).toFixed(0)}%</span>`
    + `</span></div>`;
}

// Live matches first, then chronological.
function sortLiveFirst(fx) {
  return fx.slice().sort((a, b) => (b.live ? 1 : 0) - (a.live ? 1 : 0));
}

// Factorials up to 40 for corner/card Poisson totals (counts run higher).
const FACTB = [1];
for (let k = 1; k <= 40; k++) FACTB[k] = FACTB[k-1] * k;

// P(total > line) for a Poisson(lam), line of form N.5.
function poisOver(lam, line) {
  let cum = 0;
  for (let k = 0; k <= Math.floor(line); k++)
    cum += Math.pow(lam, k) * Math.exp(-lam) / FACTB[k];
  return 1 - cum;
}

// Corners & cards markets from the two teams' for/against rates.
function renderCC(lg, homeName, awayName) {
  const box = $("cc-markets");
  const teams = DATA.leagues[lg].teams;
  const H = teams.find(t => t.name === homeName);
  const A = teams.find(t => t.name === awayName);
  if (!H || !A || H.cf == null || A.cf == null) { box.innerHTML = ""; return; }
  const corners = (H.cf + A.ca) / 2 + (A.cf + H.ca) / 2;
  const cards = (H.kf + A.ka) / 2 + (A.kf + H.ka) / 2;
  const chips = (items) => items.map(([n, p]) => {
    const hi = p >= 0.70 ? " hi" : "";
    return `<span class="mkt${hi}"><span class="mn">${n}</span>`
      + `<span class="mp">${(p*100).toFixed(0)}%</span></span>`;
  }).join("");
  const cItems = [8.5, 9.5, 10.5, 11.5].map(l => ["Corners O" + l, poisOver(corners, l)]);
  const kItems = [2.5, 3.5, 4.5, 5.5].map(l => ["Cards O" + l, poisOver(cards, l)]);
  box.innerHTML =
    `<span class="sl-label">Corners (proj ${corners.toFixed(1)}) &amp; `
    + `cards (proj ${cards.toFixed(1)}) — chance of over</span>`
    + chips(cItems) + chips(kItems);
}

// Result, handicap, clean-sheet & team-total markets as chips.
function renderResultMarkets(boxId, rm) {
  const items = [
    ["Double chance 1X", rm.dc1x], ["12", rm.dc12], ["X2", rm.dcx2],
    ["Home -1.5", rm.hcapH], ["Away -1.5", rm.hcapA],
    ["Home clean sheet", rm.csH], ["Away clean sheet", rm.csA],
    ["Home o1.5", rm.ttH], ["Away o1.5", rm.ttA],
  ];
  $(boxId).innerHTML =
    '<span class="sl-label">Result, handicap &amp; team markets</span>' +
    items.map(([n, p]) => {
      const hi = p >= 0.70 ? " hi" : "";
      return `<span class="mkt${hi}"><span class="mn">${n}</span>`
        + `<span class="mp">${(p*100).toFixed(0)}%</span></span>`;
    }).join("");
}

// Goals markets as chips; high-probability (>=70%) ones glow.
function renderMarkets(boxId, mk) {
  const items = [["Over 0.5", mk.o05], ["Over 1.5", mk.o15],
                 ["Over 2.5", mk.o25], ["Over 3.5", mk.o35], ["BTTS yes", mk.btts]];
  $(boxId).innerHTML =
    '<span class="sl-label">Goals markets — chance of each happening</span>' +
    items.map(([n, p]) => {
      const hi = p >= 0.70 ? " hi" : "";
      return `<span class="mkt${hi}"><span class="mn">${n}</span>`
        + `<span class="mp">${(p*100).toFixed(0)}%</span></span>`;
    }).join("");
}

function renderClubFixtures(lg) {
  const tz = DATA.tz || "UTC";
  const fx = sortLiveFirst(DATA.leagues[lg].fixtures || []);
  $("club-fix-league").textContent = "· " + DATA.leagues[lg].name;
  const box = $("club-fixtures");
  if (!fx.length) {
    box.innerHTML = '<p class="lede" style="margin:0">No upcoming fixtures '
      + 'right now — the league is in its summer break. This fills in '
      + 'automatically once the season resumes (August).</p>';
    return;
  }
  renderCollapsible(box, fx.map(f => fixtureRowHtml(f, tz)), 6, "fixtures");
}

function renderCalib() {
  const body = $("calib"); body.innerHTML = "";
  Object.values(DATA.leagues).forEach(L => {
    if (!L.calib) return;
    const gap = (L.calib.model_ll - L.calib.book_ll);
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${L.name}</td><td>${L.calib.model_ll.toFixed(4)}</td>` +
      `<td>${L.calib.book_ll.toFixed(4)}</td>` +
      `<td style="color:var(--accent)">+${gap.toFixed(4)}</td>`;
    body.appendChild(tr);
  });
}

function teamForm(lg, team, n) {
  const out = [];
  for (const m of (DATA.leagues[lg].log || [])) {
    const [d, h, a, hg, ag] = m;
    if (h === team) out.push(hg > ag ? "W" : hg === ag ? "D" : "L");
    else if (a === team) out.push(ag > hg ? "W" : ag === hg ? "D" : "L");
  }
  return out.slice(-n).reverse();  // newest first
}

function h2hGames(lg, home, away, n) {
  const out = [];
  for (const m of (DATA.leagues[lg].log || [])) {
    const [d, h, a] = m;
    if ((h === home && a === away) || (h === away && a === home)) out.push(m);
  }
  return out.slice(-n).reverse();
}

function renderFormH2H(lg, home, away) {
  $("fh-home-label").textContent = home + " · form";
  $("fh-away-label").textContent = away + " · form";
  const mk = arr => arr.length
    ? arr.map(r => `<span class="g ${r}">${r}</span>`).join("")
    : '<span style="color:var(--muted);font-size:12px">no recent matches</span>';
  $("fh-home").innerHTML = mk(teamForm(lg, home, 5));
  $("fh-away").innerHTML = mk(teamForm(lg, away, 5));
  const games = h2hGames(lg, home, away, 5);
  $("fh-h2h").innerHTML = games.length
    ? games.map(([d, h, a, hg, ag]) => `${d}&nbsp; ${h} ${hg}–${ag} ${a}`).join("<br>")
    : "no meetings in the last 2 seasons";
}

function update() {
  const lg = $("league").value, home = $("home").value, away = $("away").value;
  $("m-home").textContent = home;
  $("m-away").textContent = away;
  const r = predict(lg, home, away, +$("home-out").value, +$("away-out").value);
  $("f-h").style.width = (r.H*100).toFixed(1) + "%";
  $("f-d").style.width = (r.D*100).toFixed(1) + "%";
  $("f-a").style.width = (r.A*100).toFixed(1) + "%";
  $("p-h").textContent = (r.H*100).toFixed(1) + "%";
  $("p-d").textContent = (r.D*100).toFixed(1) + "%";
  $("p-a").textContent = (r.A*100).toFixed(1) + "%";
  $("t-ov").textContent = (r.OV*100).toFixed(0) + "%";
  $("t-un").textContent = (r.UN*100).toFixed(0) + "%";
  $("xg").textContent = r.lh.toFixed(2) + " – " + r.la.toFixed(2);

  // Highlight the favourite outcome.
  const vals = {"p-h": r.H, "p-d": r.D, "p-a": r.A};
  const fav = Object.keys(vals).reduce((a, b) => vals[a] >= vals[b] ? a : b);
  ["p-h", "p-d", "p-a"].forEach(id => $(id).classList.toggle("lead", id === fav));

  // Most likely exact scorelines.
  const sl = r.scores.map(s =>
    `<span class="sl"><b>${s.i}–${s.j}</b> ${(s.p*100).toFixed(1)}%</span>`
  ).join("");
  $("scorelines").innerHTML = `<span class="sl-label">Most likely scores</span>` + sl;
  renderMarkets("markets", r.mk);
  renderResultMarkets("result-markets", r.rm);
  renderCC(lg, home, away);

  renderFormH2H(lg, home, away);
}

function onLeagueChange() {
  const lg = $("league").value;
  const teams = DATA.leagues[lg].teams.map(t => t.name).sort();
  fillSelect($("home"), teams, teams[0]);
  fillSelect($("away"), teams, teams[1]);
  renderRatings(lg);
  renderClubFixtures(lg);
  update();
}

// ---- World Cup (Elo) ----
const WC = DATA.wc;
const WC_ELO = {};
WC.teams.forEach(t => { WC_ELO[t.name] = t.elo; });

function predictWC(home, away, neutral, outH = 0, outA = 0) {
  const adv = neutral ? 0 : WC.home_adv;
  const dr = ((WC_ELO[home] ?? 1500) - 40*outH)
           - ((WC_ELO[away] ?? 1500) - 40*outA) + adv;
  const total = Math.max(1.2, WC.total_base + WC.total_gap * Math.abs(dr));
  const sup = WC.sup_slope * dr;
  const lh = Math.max(0.12, (total + sup) / 2);
  const la = Math.max(0.12, (total - sup) / 2);
  const ph = [], pa = [];
  for (let k = 0; k <= MAXG; k++) { ph[k] = pois(k, lh); pa[k] = pois(k, la); }
  let mat = [], sum = 0;
  for (let i = 0; i <= MAXG; i++) { mat[i] = [];
    for (let j = 0; j <= MAXG; j++) { mat[i][j] = ph[i] * pa[j]; sum += mat[i][j]; }
  }
  let H=0, D=0, A=0, OV=0, UN=0, o05=0, o15=0, o35=0, btts=0;
  let hcapH=0, hcapA=0, csH=0, csA=0, ttH=0, ttA=0;
  const scores = [];
  for (let i = 0; i <= MAXG; i++)
    for (let j = 0; j <= MAXG; j++) {
      const p = mat[i][j] / sum;
      if (i > j) H += p; else if (i === j) D += p; else A += p;
      if (i + j > 2) OV += p; else UN += p;
      if (i + j > 0) o05 += p;
      if (i + j > 1) o15 += p;
      if (i + j > 3) o35 += p;
      if (i >= 1 && j >= 1) btts += p;
      if (i - j >= 2) hcapH += p;        // home -1.5
      if (j - i >= 2) hcapA += p;        // away -1.5
      if (j === 0) csH += p;             // home clean sheet
      if (i === 0) csA += p;             // away clean sheet
      if (i >= 2) ttH += p;              // home over 1.5
      if (j >= 2) ttA += p;              // away over 1.5
      scores.push({i, j, p});
    }
  scores.sort((a, b) => b.p - a.p);
  const ha = H + A || 1;
  return {H, D, A, OV, UN, lh, la, scores: scores.slice(0, 5),
          mk: {o05, o15, o25: OV, o35, btts},
          rm: {dc1x: H+D, dc12: H+A, dcx2: D+A, dnbH: H/ha, dnbA: A/ha,
               hcapH, hcapA, csH, csA, ttH, ttA}};
}

function updateWC() {
  const home = $("wc-home").value, away = $("wc-away").value;
  const neutral = $("wc-neutral").checked;
  $("wc-m-home").textContent = home;
  $("wc-m-away").textContent = away;
  $("wc-n-h").textContent = home;
  $("wc-n-a").textContent = away;
  const r = predictWC(home, away, neutral, +$("wc-a-out").value, +$("wc-b-out").value);
  $("wc-f-h").style.width = (r.H*100).toFixed(1) + "%";
  $("wc-f-d").style.width = (r.D*100).toFixed(1) + "%";
  $("wc-f-a").style.width = (r.A*100).toFixed(1) + "%";
  $("wc-p-h").textContent = (r.H*100).toFixed(1) + "%";
  $("wc-p-d").textContent = (r.D*100).toFixed(1) + "%";
  $("wc-p-a").textContent = (r.A*100).toFixed(1) + "%";
  const vals = {"wc-p-h": r.H, "wc-p-d": r.D, "wc-p-a": r.A};
  const fav = Object.keys(vals).reduce((a, b) => vals[a] >= vals[b] ? a : b);
  ["wc-p-h", "wc-p-d", "wc-p-a"].forEach(id => $(id).classList.toggle("lead", id === fav));
  $("wc-t-ov").textContent = (r.OV*100).toFixed(0) + "%";
  $("wc-t-un").textContent = (r.UN*100).toFixed(0) + "%";
  $("wc-xg").textContent = r.lh.toFixed(2) + " – " + r.la.toFixed(2);
  const sl = r.scores.map(s =>
    `<span class="sl"><b>${s.i}–${s.j}</b> ${(s.p*100).toFixed(1)}%</span>`
  ).join("");
  $("wc-scorelines").innerHTML = `<span class="sl-label">Most likely scores</span>` + sl;
  renderMarkets("wc-markets", r.mk);
  renderResultMarkets("wc-result-markets", r.rm);
  $("wc-elo").textContent =
    home + " " + Math.round(WC_ELO[home] ?? 1500) + "  ·  " +
    away + " " + Math.round(WC_ELO[away] ?? 1500);
}

function renderWCFixtures() {
  const box = $("wc-fixtures");
  const tz = WC.tz || DATA.tz || "UTC";
  if (!WC.fixtures.length) {
    box.innerHTML = '<p class="lede" style="margin:0">No upcoming fixtures in the data right now.</p>';
    return;
  }
  const fx = sortLiveFirst(WC.fixtures);
  renderCollapsible(box, fx.map(f => fixtureRowHtml(f, tz)), 6, "fixtures");
}

function initWC() {
  const names = WC.teams.map(t => t.name).sort();
  fillSelect($("wc-home"), names, names[0]);
  fillSelect($("wc-away"), names, names[1]);
  $("wc-home").addEventListener("change", updateWC);
  $("wc-away").addEventListener("change", updateWC);
  $("wc-neutral").addEventListener("change", updateWC);
  fillOut($("wc-a-out"), updateWC);
  fillOut($("wc-b-out"), updateWC);
  renderWCFixtures();
  updateWC();
}

// ---- NBA (Elo, no draws, projected score) ----
const NBA = DATA.nba;
const NBA_ELO = {};
if (NBA) NBA.teams.forEach(t => { NBA_ELO[t.abbr] = t.elo; });

function nbaName(abbr) {
  const t = NBA.teams.find(x => x.abbr === abbr);
  return t ? t.name : abbr;
}

function predictNBA(home, away, neutral, outH = 0, outA = 0) {
  const adv = neutral ? 0 : NBA.home_adv;
  const dr = ((NBA_ELO[home] ?? 1500) - 40*outH)
           - ((NBA_ELO[away] ?? 1500) - 40*outA) + adv;
  const pHome = 1 / (1 + Math.pow(10, -dr / 400));
  const margin = NBA.margin_slope * dr;
  return {home: pHome, away: 1 - pHome,
          projHome: (NBA.mean_total + margin) / 2,
          projAway: (NBA.mean_total - margin) / 2};
}

// Standard normal CDF (Abramowitz-Stegun approximation).
function ncdf(x) {
  const t = 1 / (1 + 0.2316419 * Math.abs(x));
  const d = 0.3989423 * Math.exp(-x * x / 2);
  const p = d * t * (0.3193815 + t * (-0.3565638 + t * (1.781478
    + t * (-1.821256 + t * 1.330274))));
  return x > 0 ? 1 - p : p;
}

function renderNbaMarkets(home, away, neutral, outH = 0, outA = 0) {
  const adv = neutral ? 0 : NBA.home_adv;
  const dr = ((NBA_ELO[home] ?? 1500) - 40*outH)
           - ((NBA_ELO[away] ?? 1500) - 40*outA) + adv;
  const margin = NBA.margin_slope * dr;
  const cover = line => 1 - ncdf((line - margin) / NBA.margin_std);  // P(margin>line)
  const tot = line => 1 - ncdf((line - NBA.mean_total) / NBA.total_std);
  const base = Math.floor(NBA.mean_total) + 0.5;
  const items = [
    ["Home -5.5", cover(5.5)], ["Home -10.5", cover(10.5)],
    ["Home +5.5", cover(-5.5)],
    ["Over " + (base - 10), tot(base - 10)], ["Over " + base, tot(base)],
    ["Over " + (base + 10), tot(base + 10)],
  ];
  $("nba-markets").innerHTML =
    '<span class="sl-label">Spread &amp; total points</span>' +
    items.map(([n, p]) => {
      const hi = p >= 0.70 ? " hi" : "";
      return `<span class="mkt${hi}"><span class="mn">${n}</span>`
        + `<span class="mp">${(p*100).toFixed(0)}%</span></span>`;
    }).join("");
}

function updateNBA() {
  const home = $("nba-home").value, away = $("nba-away").value;
  const oh = +$("nba-h-out").value, oa = +$("nba-a-out").value;
  const r = predictNBA(home, away, $("nba-neutral").checked, oh, oa);
  $("nba-m-home").textContent = nbaName(home);
  $("nba-m-away").textContent = nbaName(away);
  $("nba-n-h").textContent = nbaName(home);
  $("nba-n-a").textContent = nbaName(away);
  $("nba-f-h").style.width = (r.home*100).toFixed(1) + "%";
  $("nba-f-a").style.width = (r.away*100).toFixed(1) + "%";
  $("nba-p-h").textContent = (r.home*100).toFixed(1) + "%";
  $("nba-p-a").textContent = (r.away*100).toFixed(1) + "%";
  $("nba-p-h").classList.toggle("lead", r.home >= r.away);
  $("nba-p-a").classList.toggle("lead", r.away > r.home);
  $("nba-proj").textContent = `${r.projHome.toFixed(0)}–${r.projAway.toFixed(0)}`;
  $("nba-elo").textContent =
    `${nbaName(home)} ${Math.round(NBA_ELO[home] ?? 1500)}  ·  ` +
    `${nbaName(away)} ${Math.round(NBA_ELO[away] ?? 1500)}`;
  renderNbaMarkets(home, away, $("nba-neutral").checked, oh, oa);
}

function nbaFixtureRow(f, tz) {
  const fav = f.home_win >= f.away_win ? "h" : "a";
  const when = f.time
    ? `${f.date}<br><span class="ftime">${f.time} ${tz}</span>` : f.date;
  const live = f.live
    ? `<span class="livedot">● LIVE${f.score ? " " + f.score : ""}</span>` : "";
  return `<div class="fix"><span class="fdate">${when}</span>`
    + `<span class="teams">${f.home} <span class="at">v</span> ${f.away}${live}`
    + `<br><span class="at">proj ${f.proj}</span></span>`
    + `<span class="odds">`
    + `<span class="${fav==='h'?'win':''}">${(f.home_win*100).toFixed(0)}%</span>`
    + `<span class="${fav==='a'?'win':''}">${(f.away_win*100).toFixed(0)}%</span>`
    + `</span></div>`;
}

function renderNbaFixtures() {
  const box = $("nba-fixtures");
  const fx = sortLiveFirst(NBA.fixtures || []);
  if (!fx.length) {
    box.innerHTML = '<p class="lede" style="margin:0">No upcoming games — the '
      + 'NBA is in its off-season. This fills in when the 2026-27 schedule is '
      + 'released (around October).</p>';
    return;
  }
  const tz = DATA.tz || "UTC";
  renderCollapsible(box, fx.map(f => nbaFixtureRow(f, tz)), 6, "games");
}

function renderNbaRatings() {
  const rows = NBA.teams.map((t, i) =>
    `<div class="nba-rrow"><span class="rk">${i+1}</span>` +
    `<span class="rn">${t.name}</span>` +
    `<span class="re">${t.elo.toFixed(0)}</span></div>`);
  renderCollapsible($("nba-ratings"), rows, 8, "teams");
}

function fillSelectNBA(sel, teams, selectedAbbr) {
  sel.innerHTML = "";
  teams.forEach(t => {
    const o = document.createElement("option");
    o.value = t.abbr; o.textContent = t.name;
    if (t.abbr === selectedAbbr) o.selected = true;
    sel.appendChild(o);
  });
}

function initNBA() {
  if (!NBA || !NBA.teams.length) {
    const p = $("nba-panel"); if (p) p.style.display = "none";
    return;
  }
  const byName = NBA.teams.slice().sort((a, b) => a.name < b.name ? -1 : 1);
  fillSelectNBA($("nba-home"), byName, NBA.teams[0].abbr);   // top-rated home
  fillSelectNBA($("nba-away"), byName, NBA.teams[1].abbr);   // 2nd-rated away
  $("nba-home").addEventListener("change", updateNBA);
  $("nba-away").addEventListener("change", updateNBA);
  $("nba-neutral").addEventListener("change", updateNBA);
  fillOut($("nba-h-out"), updateNBA);
  fillOut($("nba-a-out"), updateNBA);
  renderNbaFixtures();
  renderNbaRatings();
  updateNBA();
}

// ---- Tennis (surface-aware Elo) ----
const TENNIS = DATA.tennis;
const T_PLAYERS = {};
if (TENNIS) TENNIS.players.forEach(p => { T_PLAYERS[p.name] = p; });

function tBlend(p, surf) {
  const sv = surf === "Clay" ? p.clay : surf === "Grass" ? p.grass : p.hard;
  return TENNIS.surface_weight * sv + (1 - TENNIS.surface_weight) * p.elo;
}

function predictTennis(a, b, surf) {
  const ra = tBlend(T_PLAYERS[a], surf), rb = tBlend(T_PLAYERS[b], surf);
  const pa = 1 / (1 + Math.pow(10, -(ra - rb) / 400));
  return {a: pa, b: 1 - pa};
}

function updateTennis() {
  const a = $("t-a").value, b = $("t-b").value, surf = $("t-surface").value;
  $("t-m-a").textContent = a; $("t-m-b").textContent = b;
  $("t-n-a").textContent = a; $("t-n-b").textContent = b;
  const r = predictTennis(a, b, surf);
  $("t-f-a").style.width = (r.a*100).toFixed(1) + "%";
  $("t-f-b").style.width = (r.b*100).toFixed(1) + "%";
  $("t-p-a").textContent = (r.a*100).toFixed(1) + "%";
  $("t-p-b").textContent = (r.b*100).toFixed(1) + "%";
  $("t-p-a").classList.toggle("lead", r.a >= r.b);
  $("t-p-b").classList.toggle("lead", r.b > r.a);
  $("t-elo").textContent =
    `${a} ${Math.round(T_PLAYERS[a].elo)}  ·  ${b} ${Math.round(T_PLAYERS[b].elo)}`;
}

function renderTennisRatings() {
  const rows = TENNIS.players.map((p, i) =>
    `<div class="nba-rrow"><span class="rk">${i+1}</span>` +
    `<span class="rn">${p.name}</span>` +
    `<span class="re">${p.elo.toFixed(0)}</span></div>`);
  renderCollapsible($("t-ratings"), rows, 10, "players");
}

function initTennis() {
  if (!TENNIS || !TENNIS.players.length) {
    const p = $("panel-tennis"); if (p) p.hidden = true;
    const btn = document.querySelector('[data-tab="tennis"]');
    if (btn) btn.style.display = "none";
    return;
  }
  const byName = TENNIS.players.slice().sort((x, y) => x.name < y.name ? -1 : 1);
  const mk = (sel, def) => {
    sel.innerHTML = "";
    byName.forEach(p => {
      const o = document.createElement("option");
      o.value = p.name; o.textContent = p.name;
      if (p.name === def) o.selected = true;
      sel.appendChild(o);
    });
  };
  mk($("t-a"), TENNIS.players[0].name);   // top-rated
  mk($("t-b"), TENNIS.players[1].name);   // 2nd
  $("t-a").addEventListener("change", updateTennis);
  $("t-b").addEventListener("change", updateTennis);
  $("t-surface").addEventListener("change", updateTennis);
  renderTennisRatings();
  updateTennis();
}

// ---- Champions League (unified cross-league Elo) ----
const CL = DATA.cl;
const CL_ELO = {};
if (CL) CL.teams.forEach(t => { CL_ELO[t.name] = t.elo; });

function predictCL(home, away, neutral, outH = 0, outA = 0) {
  const adv = neutral ? 0 : CL.home_adv;
  const dr = ((CL_ELO[home] ?? 1500) - 40*outH)
           - ((CL_ELO[away] ?? 1500) - 40*outA) + adv;
  const total = Math.max(1.2, CL.total_base + CL.total_gap * Math.abs(dr));
  const sup = CL.sup_slope * dr;
  const lh = Math.max(0.12, (total + sup) / 2);
  const la = Math.max(0.12, (total - sup) / 2);
  const ph = [], pa = [];
  for (let k = 0; k <= MAXG; k++) { ph[k] = pois(k, lh); pa[k] = pois(k, la); }
  let mat = [], sum = 0;
  for (let i = 0; i <= MAXG; i++) { mat[i] = [];
    for (let j = 0; j <= MAXG; j++) { mat[i][j] = ph[i] * pa[j]; sum += mat[i][j]; }
  }
  let H=0, D=0, A=0, OV=0, UN=0, o05=0, o15=0, o35=0, btts=0;
  const scores = [];
  for (let i = 0; i <= MAXG; i++)
    for (let j = 0; j <= MAXG; j++) {
      const p = mat[i][j] / sum;
      if (i > j) H += p; else if (i === j) D += p; else A += p;
      if (i + j > 2) OV += p; else UN += p;
      if (i + j > 0) o05 += p;
      if (i + j > 1) o15 += p;
      if (i + j > 3) o35 += p;
      if (i >= 1 && j >= 1) btts += p;
      scores.push({i, j, p});
    }
  scores.sort((a, b) => b.p - a.p);
  return {H, D, A, OV, UN, lh, la, scores: scores.slice(0, 5),
          mk: {o05, o15, o25: OV, o35, btts}};
}

function updateCL() {
  const home = $("cl-home").value, away = $("cl-away").value;
  const r = predictCL(home, away, $("cl-neutral").checked,
                      +$("cl-a-out").value, +$("cl-b-out").value);
  $("cl-m-home").textContent = home; $("cl-m-away").textContent = away;
  $("cl-n-h").textContent = home; $("cl-n-a").textContent = away;
  $("cl-f-h").style.width = (r.H*100).toFixed(1) + "%";
  $("cl-f-d").style.width = (r.D*100).toFixed(1) + "%";
  $("cl-f-a").style.width = (r.A*100).toFixed(1) + "%";
  $("cl-p-h").textContent = (r.H*100).toFixed(1) + "%";
  $("cl-p-d").textContent = (r.D*100).toFixed(1) + "%";
  $("cl-p-a").textContent = (r.A*100).toFixed(1) + "%";
  const vals = {"cl-p-h": r.H, "cl-p-d": r.D, "cl-p-a": r.A};
  const fav = Object.keys(vals).reduce((a, b) => vals[a] >= vals[b] ? a : b);
  ["cl-p-h", "cl-p-d", "cl-p-a"].forEach(id => $(id).classList.toggle("lead", id === fav));
  $("cl-t-ov").textContent = (r.OV*100).toFixed(0) + "%";
  $("cl-t-un").textContent = (r.UN*100).toFixed(0) + "%";
  $("cl-xg").textContent = r.lh.toFixed(2) + " – " + r.la.toFixed(2);
  const sl = r.scores.map(s =>
    `<span class="sl"><b>${s.i}–${s.j}</b> ${(s.p*100).toFixed(1)}%</span>`).join("");
  $("cl-scorelines").innerHTML = `<span class="sl-label">Most likely scores</span>` + sl;
  renderMarkets("cl-markets", r.mk);
  $("cl-elo").textContent =
    `${home} ${Math.round(CL_ELO[home] ?? 1500)}  ·  ${away} ${Math.round(CL_ELO[away] ?? 1500)}`;
}

function renderClFixtures() {
  const box = $("cl-fixtures");
  const tz = CL.tz || DATA.tz || "UTC";
  const fx = sortLiveFirst(CL.fixtures || []);
  if (!fx.length) {
    box.innerHTML = '<p class="lede" style="margin:0">No upcoming fixtures — '
      + 'the 2026-27 Champions League is drawn in late August. This fills in then.</p>';
    return;
  }
  renderCollapsible(box, fx.map(f => fixtureRowHtml(f, tz)), 6, "fixtures");
}

function initCL() {
  if (!CL || !CL.teams.length) {
    const p = $("panel-cl"); if (p) p.hidden = true;
    const btn = document.querySelector('[data-tab="cl"]');
    if (btn) btn.style.display = "none";
    return;
  }
  const byName = CL.teams.slice().sort((a, b) => a.name < b.name ? -1 : 1);
  const mk = (sel, def) => {
    sel.innerHTML = "";
    byName.forEach(t => {
      const o = document.createElement("option");
      o.value = t.name; o.textContent = t.name;
      if (t.name === def) o.selected = true;
      sel.appendChild(o);
    });
  };
  mk($("cl-home"), CL.teams[0].name);
  mk($("cl-away"), CL.teams[1].name);
  $("cl-home").addEventListener("change", updateCL);
  $("cl-away").addEventListener("change", updateCL);
  $("cl-neutral").addEventListener("change", updateCL);
  fillOut($("cl-a-out"), updateCL);
  fillOut($("cl-b-out"), updateCL);
  renderClFixtures();
  updateCL();
}

function initTabs() {
  const btns = document.querySelectorAll(".tab-btn");
  btns.forEach(b => b.addEventListener("click", () => {
    btns.forEach(x => x.classList.toggle("active", x === b));
    const tab = b.dataset.tab;
    document.querySelectorAll(".tabpanel").forEach(p => {
      p.hidden = (p.id !== "panel-" + tab);
    });
    document.getElementById("app").setAttribute("data-sport", tab);  // reskin accent
    const tabs = document.getElementById("tabs");
    if (tabs) tabs.scrollIntoView({behavior: "smooth", block: "start"});
  }));
}

function initTheme() {
  const app = document.getElementById("app");
  const btn = document.getElementById("theme-btn");
  try {
    const saved = localStorage.getItem("sm-theme");
    if (saved) app.setAttribute("data-theme", saved);
  } catch (e) { /* sandboxed: ignore */ }
  const sync = () => {
    btn.textContent = app.getAttribute("data-theme") === "dark" ? "☀ Light" : "🌙 Dark";
  };
  sync();
  btn.addEventListener("click", () => {
    const next = app.getAttribute("data-theme") === "dark" ? "light" : "dark";
    app.setAttribute("data-theme", next);
    try { localStorage.setItem("sm-theme", next); } catch (e) { /* ignore */ }
    sync();
  });
}

(function init() {
  const codes = Object.keys(DATA.leagues);
  const sel = $("league"); sel.innerHTML = "";
  codes.forEach(c => {
    const o = document.createElement("option");
    o.value = c; o.textContent = DATA.leagues[c].name;
    sel.appendChild(o);
  });
  sel.addEventListener("change", onLeagueChange);
  $("home").addEventListener("change", update);
  $("away").addEventListener("change", update);
  fillOut($("home-out"), update);
  fillOut($("away-out"), update);
  $("swap").addEventListener("click", () => {
    const h = $("home").value, a = $("away").value;
    $("home").value = a; $("away").value = h; update();
  });
  $("foot").textContent = "Generated " + DATA.generated +
    " · club: xG Dixon-Coles · national: Elo · computed live in-browser";
  onLeagueChange();
  initWC();
  initNBA();
  initTennis();
  initCL();
  initTabs();
  initTheme();
})();
</script>
</div>
"""


if __name__ == "__main__":
    write_report()
