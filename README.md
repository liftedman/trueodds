# sports-model

A multi-sport prediction engine — football clubs, the World Cup, the NBA, and
tennis — built from public data, with **honest, measured** probabilities.

> **Read this first.** This model does **not** beat the bookmaker, and it never
> claimed to. We tested that exhaustively (see *Honest findings* below). It
> produces well-calibrated probabilities — useful for understanding and
> informed prediction — not a betting edge. Anyone promising ~80% accuracy on
> match outcomes is selling something; the realistic ceiling is ~55–60%.

---

## What it does

For each sport it gives win/draw/away probabilities, plus markets (goals
over/under, BTTS, double chance, handicaps, corners, cards; spread & totals for
the NBA), expected goals, likely scorelines, team/player ratings, and upcoming
fixtures with kickoff times and **live scores**. Everything is viewable in a
single self-contained HTML dashboard with tabbed navigation.

You can also fold in **team news** ("key players out") on each predictor to
adjust a match manually.

---

## Architecture

It's a **local, batch pipeline that generates a static dashboard** — no server,
no cloud database.

```
DATA SOURCES ──► SQLite (data/sports.db) ──► Python models (fit per run)
                                                     │
                                                     ▼
                                          report.py builds dashboard.html
                                          (ratings + prediction math embedded;
                                           recomputed live in-browser via JS)
                                                     │
                                                     ▼
                                       static page (opened / hosted as needed)
```

- Models are **fit on demand** each run (seconds) — there is no saved model file.
- The interactive predictors recompute in the browser from embedded ratings.
- A self-paced refresh loop can regenerate the page during live matches.

---

## Data sources

| Source | Used for |
|---|---|
| football-data.co.uk | Club results, odds, corners, cards (top-5 + secondary leagues) |
| understat (JSON endpoint) | Expected goals (xG) for top-5 leagues |
| martj42/international_results (GitHub) | International match history + WC fixtures |
| nba_api (stats.nba.com) | NBA game results + schedule + live scores |
| Tennismylife/TML-Database (GitHub) | ATP tennis match history |
| football-data.org (API key) | Club/UCL fixtures (fallback) — **note: its WC schedule was unreliable** |
| TheSportsDB (free) | World Cup fixtures + live scores (the accurate WC source) |

Secrets go in a git-ignored `.env` (see `.env.example`): `FOOTBALL_DATA_API_KEY`.

---

## Models

| Sport | Model |
|---|---|
| Club football | **Dixon-Coles** on expected goals (xG), 240-day time-decay (tuned) |
| World Cup / internationals | **Elo** (importance-weighted), goals derived from rating gap |
| NBA | **Elo** (home court, 25%/season regression), projected score + spread/total |
| Tennis | **Surface-aware Elo** (separate Hard/Clay/Grass ratings) |
| Champions League | **Unified cross-league Elo** (domestic + European links) |

What we use: goals/xG, home advantage, ratings, recent form (minor), manual
lineup adjustments. What we deliberately exclude: **head-to-head** (tested →
zero predictive value) and **betting odds as an input** (that just copies the
bookmaker).

---

## Setup

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
copy .env.example .env   # then paste your football-data.org key (optional)
```

## Commands

```powershell
# --- data ingestion ---
python -m sports_model.main ingest          # club results + odds (top-5)
python -m sports_model.main ingest-xg        # understat xG -> matches
python -m sports_model.main ingest-extra     # secondary leagues
python -m sports_model.main ingest-intl      # internationals + WC fixtures
python -m sports_model.main ingest-nba       # NBA games
python -m sports_model.main ingest-tennis    # ATP tennis matches

# --- predictions / views ---
python -m sports_model.main wc               # World Cup fixtures + predictions (live)
python -m sports_model.main fixtures         # club fixtures + predictions
python -m sports_model.main nba              # NBA ratings + predictions
python -m sports_model.main tennis           # ATP ratings + sample predictions
python -m sports_model.main cl               # unified club Elo / UCL
python -m sports_model.main status           # what's in the database

# --- evaluation (the honest part) ---
python -m sports_model.main backtest [season]    # model vs bookmaker, out-of-sample
python -m sports_model.main value [season]       # paper-betting yield vs closing odds
python -m sports_model.main edge-hunt [season]   # CLV sweep (best-price + closing)
python -m sports_model.main scan                 # soft-league CLV scan
python -m sports_model.main scan-totals          # over/under 2.5 CLV scan
python -m sports_model.main feature-test         # does form / H2H add value?
python -m sports_model.main tune-halflife        # tune the xG time-decay

# --- dashboard ---
python -m sports_model.main report           # build data/processed/dashboard.html
```

## Test

```powershell
pytest
```

---

## Honest findings

Measured out-of-sample on data the models never trained on:

- The club xG model lands **within ~3% of the bookmaker's closing line** — good,
  but consistently *behind* it. No edge.
- **Value-betting backtests are negative** (~−13% yield) across markets, leagues,
  best-price and closing odds. Confirmed on thousands of bets.
- **Head-to-head adds nothing** (the "they always beat them" myth — disproven on
  this data). **Recent form** adds ~0.4% — real but tiny, mostly already in the
  ratings.
- High accuracy exists only on **easy markets** (Over 0.5 goals ~92%, big
  favourites) at tiny odds — not on meaningful outcomes.

Conclusion: a principled tool for understanding match probabilities, not a way
to beat the market.

---

## Project layout

```
src/sports_model/
  config.py            paths, leagues, seasons, settings
  db.py                SQLite schema + connection
  main.py              CLI entry point (all commands)
  report.py            builds the HTML dashboard
  ingest/              data ingestion per source
  models/              dixon_coles, elo, nba_elo, tennis_elo, club_elo,
                       markets, evaluate, tune, feature_test, *_schedule, ...
  betting/             value detection, staking, ledger, edge_hunt
tests/                 test suite
data/                  sports.db + generated dashboard (git-ignored)
```
