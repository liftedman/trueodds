"""Command-line entry point.

Run with:
    python -m sports_model.main init       # create the empty database
    python -m sports_model.main ingest     # download + load football data
    python -m sports_model.main ingest-xg  # attach understat xG to matches
    python -m sports_model.main ingest-extra  # load soft/secondary leagues
    python -m sports_model.main ingest-intl   # load international results + WC fixtures
    python -m sports_model.main ingest-nba    # load NBA game results
    python -m sports_model.main nba        # NBA Elo ratings + sample predictions
    python -m sports_model.main wc         # upcoming World Cup fixtures + predictions
    python -m sports_model.main fixtures   # upcoming club fixtures + times + predictions
    python -m sports_model.main status     # show what's in the database
    python -m sports_model.main backtest   # train + score the model vs bookmaker
    python -m sports_model.main value      # paper-bet the model vs closing odds
    python -m sports_model.main edge-hunt  # opening prices + CLV sweep (edge test)
    python -m sports_model.main scan       # clean CLV scan across soft leagues
    python -m sports_model.main scan-totals  # Over/Under 2.5 CLV scan
    python -m sports_model.main report     # build the HTML dashboard
"""

from __future__ import annotations

import sys

from . import db


def cmd_init() -> None:
    db.init_db()
    from . import config

    print(f"Database ready at {config.DB_PATH}")


def cmd_ingest() -> None:
    from .ingest import football

    football.ingest_all()


def cmd_ingest_xg() -> None:
    from .ingest import understat

    understat.ingest_all()


def cmd_ingest_extra() -> None:
    from . import config
    from .ingest import football

    football.ingest_all(leagues=config.SECONDARY_FOOTBALL_LEAGUES)


def cmd_ingest_intl() -> None:
    from .ingest import internationals

    internationals.ingest_all()


def cmd_ingest_nba() -> None:
    from .ingest import nba

    nba.ingest_all()


def cmd_ingest_nfl() -> None:
    from .ingest import nfl

    nfl.ingest_all()


def cmd_ingest_wnba() -> None:
    from .ingest import bball

    bball.ingest_all()


def cmd_nba() -> None:
    from . import config
    from .models import nba, nba_schedule

    model = nba.fit_model()

    # Upcoming games (off-season -> empty until ~October).
    try:
        fixtures = nba_schedule.fetch_schedule(model, days_ahead=7)
    except Exception:
        fixtures = []
    tz = config.DISPLAY_TZ_LABEL
    if fixtures:
        print("Upcoming NBA games\n" + "=" * 40)
        for f in fixtures:
            when = f"{f['date']} {f['time']} {tz}" if f["time"] else f["date"]
            live = f"  ● LIVE {f['score']}" if f["live"] and f["score"] else ""
            print(f"  {when}{live}  {f['home']} v {f['away']}")
            print(f"     home {f['home_win']*100:.0f}%  away "
                  f"{f['away_win']*100:.0f}%  proj {f['proj']}")
        print()
    else:
        print("No upcoming NBA games (off-season until ~October).\n")

    ratings = nba.team_ratings(model)
    print("NBA Elo ratings (top to bottom)\n" + "=" * 40)
    for r in ratings:
        print(f"  {r['elo']:>7.1f}  {r['name']}")

    # A couple of sample matchups (best vs worst, and a marquee pairing).
    if len(ratings) >= 2:
        best, worst = ratings[0]["abbr"], ratings[-1]["abbr"]
        print("\nSample predictions (home team first):")
        for h, a in [(best, worst), ("LAL", "BOS"), ("DEN", "GSW")]:
            if h not in model.ratings or a not in model.ratings:
                continue
            p = model.predict(h, a)
            print(f"  {nba.TEAM_NAMES.get(h, h)} v {nba.TEAM_NAMES.get(a, a)}: "
                  f"home {p['home_win']*100:.0f}%  away {p['away_win']*100:.0f}%  "
                  f"proj {p['proj_home']:.0f}-{p['proj_away']:.0f}")


def cmd_ingest_tennis() -> None:
    from .ingest import tennis

    tennis.ingest_all()


def cmd_tennis() -> None:
    from .models import tennis

    matches = tennis.load_matches()
    model = tennis.fit_model(matches)
    players = tennis.active_players(model, matches)
    print(f"ATP Elo — top 20 active players (of {len(players)})\n" + "=" * 44)
    for p in players[:20]:
        print(f"  {p['elo']:>7.1f}  {p['name']}")
    if len(players) >= 2:
        a, b = players[0]["name"], players[1]["name"]
        print(f"\nSample: {a} vs {b}")
        for surf in ("Hard", "Clay", "Grass"):
            pr = model.predict(a, b, surf)
            print(f"  {surf:>5}: {a} {pr['a_win']*100:.0f}%  {b} {pr['b_win']*100:.0f}%")


def cmd_cl() -> None:
    from .models import club_elo

    model, diag = club_elo.build()
    print(f"Unified club Elo  (domestic {diag['domestic']}, "
          f"CL links {diag['cl_links']}, teams {diag['teams']})\n" + "=" * 50)
    cl_teams = diag.get("cl_teams") or []
    ranked = sorted(cl_teams, key=lambda t: -model.rating(t))
    print("CL clubs by rating:")
    for t in ranked[:20]:
        print(f"  {model.rating(t):7.0f}  {t}")
    if len(ranked) >= 2:
        a, b = ranked[0], ranked[1]
        p = model.predict(a, b, neutral=True)
        print(f"\nSample (neutral): {a} v {b} -> "
              f"{p['H']*100:.0f}/{p['D']*100:.0f}/{p['A']*100:.0f}")


def cmd_wc() -> None:
    from . import config
    from .models import world_cup, wc_schedule, football_data

    model = world_cup.fit_model()
    tz = config.DISPLAY_TZ_LABEL

    # Preferred: TheSportsDB (matches the real tournament + live scores).
    fixtures = wc_schedule.fetch_schedule(days_ahead=14, model=model)
    source = "TheSportsDB (live)"
    if not fixtures:  # fall back to football-data.org
        fixtures = football_data.wc_fixtures(model, limit=24)
        source = "football-data.org"
    if not fixtures:  # last resort: ingested dataset, dates only
        fixtures = [
            {"date": f["date"], "time": "", "live": False, "status": "",
             "score": None, "home": f["home"], "away": f["away"],
             "h": f["pred"]["H"], "d": f["pred"]["D"], "a": f["pred"]["A"]}
            for f in world_cup.upcoming_fixtures(model, limit=20)
        ]
        source = "ingested dataset (dates only)"
        fixtures = [f for f in fixtures]
    if not fixtures:
        print("No upcoming World Cup fixtures found.")
        return

    print(f"Upcoming World Cup fixtures — {source}\n" + "=" * 66)
    for f in fixtures:
        # Support both the football-data shape (h/d/a) and the old pred shape.
        h = f.get("h", f.get("pred", {}).get("H"))
        d = f.get("d", f.get("pred", {}).get("D"))
        a = f.get("a", f.get("pred", {}).get("A"))
        when = f"{f['date']} {f.get('time','')} {tz}".strip() if f.get("time") else f["date"]
        if f.get("live"):
            lbl = "HT" if f.get("status") == "PAUSED" else "LIVE"
            when += f"   ● {lbl}" + (f"  {f['score']}" if f.get("score") else "")
        print(f"{when}")
        print(f"   {f['home']} {h*100:4.1f}%  draw {d*100:4.1f}%  "
              f"{f['away']} {a*100:4.1f}%")


def cmd_scan() -> None:
    from . import config
    from .betting import edge_hunt

    edge_hunt.scan_leagues(config.SECONDARY_FOOTBALL_LEAGUES, use_xg=False)


def cmd_report() -> None:
    from . import report

    report.write_report()


def cmd_push() -> None:
    from . import push

    push.push_snapshot()


def cmd_serve() -> None:
    import uvicorn

    host = sys.argv[2] if len(sys.argv) > 2 else "127.0.0.1"
    port = int(sys.argv[3]) if len(sys.argv) > 3 else 8000
    print(f"Starting prediction API on http://{host}:{port}  (docs at /docs)")
    uvicorn.run("sports_model.api:app", host=host, port=port)


def cmd_fixtures() -> None:
    """Upcoming top-5 club fixtures with kickoff times + predictions."""
    import pandas as pd

    from . import config
    from .models import club_schedule, dixon_coles, evaluate, football_data

    models = {}
    for code in config.FOOTBALL_LEAGUES:
        df = evaluate.load_league(code)
        ref = pd.to_datetime(df["date"]).max()
        models[code] = dixon_coles.fit(
            df, half_life_days=config.XG_HALF_LIFE_DAYS, ref_date=ref, use_xg=True)

    fixtures = football_data.club_fixtures(models)  # complete + live, if key
    unmapped = []
    if fixtures is None:
        fixtures, unmapped = club_schedule.fetch_all(models)
    tz = config.DISPLAY_TZ_LABEL
    any_fx = False
    for code in config.FOOTBALL_LEAGUES:
        fx = fixtures.get(code, [])
        if not fx:
            continue
        any_fx = True
        print(f"\n{config.FOOTBALL_LEAGUES[code]}")
        for f in fx:
            when = f"{f['date']} {f['time']} {tz}" if f.get("time") else f["date"]
            if f.get("live"):
                lbl = "HT" if f.get("status") == "PAUSED" else "LIVE"
                when += f"  ● {lbl}" + (f" {f['score']}" if f.get("score") else "")
            print(f"  {when}  {f['home']} v {f['away']}")
            print(f"     H {f['h']*100:.0f}%  D {f['d']*100:.0f}%  "
                  f"A {f['a']*100:.0f}%   Over2.5 {f['ov']*100:.0f}%")
    if not any_fx:
        print("No upcoming top-5 fixtures (leagues in summer break until August).")
    if unmapped:
        print(f"\n(unmapped team names skipped: {', '.join(unmapped)})")


def cmd_feature_test() -> None:
    from .models import feature_test

    feature_test.run()


def cmd_tune_halflife() -> None:
    from .models import tune

    tune.run()


def cmd_scan_totals() -> None:
    from . import config
    from .betting import edge_hunt

    print(">>> Top-5 leagues, xG model <<<")
    edge_hunt.scan_leagues_totals(config.FOOTBALL_LEAGUES, use_xg=True)
    print("\n>>> All leagues, goals model <<<")
    edge_hunt.scan_leagues_totals(config.ALL_FOOTBALL_LEAGUES, use_xg=False)


def cmd_status() -> None:
    with db.connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n, MIN(date) AS first, MAX(date) AS last "
            "FROM football_matches"
        ).fetchone()
        print(f"football_matches: {row['n']} rows "
              f"({row['first']} -> {row['last']})")
        print("\nBy league / season:")
        for r in conn.execute(
            "SELECT league_name, season, COUNT(*) AS n "
            "FROM football_matches GROUP BY league_code, season "
            "ORDER BY league_name, season"
        ):
            print(f"  {r['league_name']:<16} {r['season']}: {r['n']:>4}")


def cmd_backtest() -> None:
    from .models import evaluate

    season = sys.argv[2] if len(sys.argv) > 2 else "2425"
    evaluate.run_all(target_season=season)


def cmd_value() -> None:
    from .betting import ledger

    season = sys.argv[2] if len(sys.argv) > 2 else "2425"
    ledger.run_all(target_season=season)


def cmd_edgehunt() -> None:
    from .betting import edge_hunt

    season = sys.argv[2] if len(sys.argv) > 2 else "2425"
    source = sys.argv[3] if len(sys.argv) > 3 else "best"
    edge_hunt.run_sweep(target_season=season, bet_source=source)


def cmd_crests() -> None:
    from . import crests

    out = crests.fetch_crests()
    n = sum(len(v) for v in out.values())
    print(f"Cached {n} team crests across {len(out)} leagues -> {crests.CRESTS_PATH}")


_COMMANDS = {
    "init": cmd_init,
    "ingest": cmd_ingest,
    "ingest-xg": cmd_ingest_xg,
    "ingest-extra": cmd_ingest_extra,
    "ingest-intl": cmd_ingest_intl,
    "ingest-nba": cmd_ingest_nba,
    "ingest-nfl": cmd_ingest_nfl,
    "ingest-wnba": cmd_ingest_wnba,
    "nba": cmd_nba,
    "ingest-tennis": cmd_ingest_tennis,
    "tennis": cmd_tennis,
    "cl": cmd_cl,
    "wc": cmd_wc,
    "status": cmd_status,
    "backtest": cmd_backtest,
    "value": cmd_value,
    "edge-hunt": cmd_edgehunt,
    "crests": cmd_crests,
    "scan": cmd_scan,
    "scan-totals": cmd_scan_totals,
    "report": cmd_report,
    "push": cmd_push,
    "serve": cmd_serve,
    "fixtures": cmd_fixtures,
    "feature-test": cmd_feature_test,
    "tune-halflife": cmd_tune_halflife,
}


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] not in _COMMANDS:
        print(__doc__)
        sys.exit(1)
    _COMMANDS[sys.argv[1]]()


if __name__ == "__main__":
    main()
