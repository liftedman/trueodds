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

## Markets mode (trading analysis)

The app has **two modes** the user switches between: **Sports** (above) and
**Markets** — the same honest-measurement approach applied to tradable
instruments, covering the range that fixed-time ("binary") platforms like
ExpertOption offer.

Separate Python package (`src/markets_model/`), separate database
(`data/markets.db`), separate Supabase row (`id='markets'`), so the two modes
fail independently.

### The one number that matters

A fixed payout of 80% is decimal odds of 1.80, so **breakeven is 55.56%**.
Below that a trade loses money no matter how confident it looks — a ~10% house
edge per trade, roughly 3× the vig on a football 1X2 market, with the platform
acting as both counterparty and price source. Every screen in Markets mode shows
the model's confidence next to that bar, and next to the hit rate it has
actually achieved.

### Coverage

| Asset class | Instruments | Source |
|---|---|---|
| Crypto | 7 (BTC, ETH, SOL, XRP, BNB, ADA, DOGE) | Binance, falling back to Coinbase (no key) |
| Forex | 7 majors | Yahoo Finance (`yfinance`, no key) |
| Stocks | 7 US large-cap | Yahoo Finance |
| Indices | 6 (S&P 500, Nasdaq 100, Dow, DAX, FTSE, Nikkei) | Yahoo Finance |
| Commodities | 6 (gold, silver, WTI, Brent, nat gas, copper) | Yahoo Finance |

Horizons: **5m / 15m / 1h / 1d**. 1m is deliberately excluded — Yahoo serves
only 7 days of it, so it cannot be evaluated honestly for four of the five asset
classes, and shipping an unevaluated horizon is the thing this mode exists not
to do. (Stooq was the original source; it now gates automated access behind a
JavaScript proof-of-work challenge.)

**Two crypto sources on purpose.** Binance is preferred — deeper history, 1000
bars per request, USDT pairs matching how these instruments are quoted on the
platforms being modelled. But Binance geo-blocks US IPs and GitHub Actions
runners are US-hosted, so the nightly job would otherwise publish a snapshot
with no crypto at all and silently drop the asset class from the app. Coinbase
Exchange is the fallback: keyless, US-available, lists all seven pairs, and
covers every reported timeframe. It quotes USD rather than USDT — a ~0.09%
basis, immaterial for direction. `ingest-crypto` probes once and prints which
source served the data.

### Commands

```powershell
python -m markets_model.main ingest            # everything (crypto + Yahoo)
python -m markets_model.main ingest-crypto     # Binance only
python -m markets_model.main ingest-yahoo      # FX / stocks / indices / commodities
python -m markets_model.main status            # what's stored

python -m markets_model.main eval BTCUSDT 5m       # walk-forward, one instrument
python -m markets_model.main eval-all --save       # the full honest sweep
python -m markets_model.main predict EURUSD 1h     # forecast the next bar
python -m markets_model.main resolve               # settle logged predictions

python -m markets_model.main report            # build data/processed/markets.json
python -m markets_model.main push              # upload snapshot to Supabase
```

### How the evaluation avoids fooling itself

- **Expanding-window walk-forward.** Train on `[0, t)`, predict `[t, t+block)`,
  advance. The scaler refits with the model, so no future statistics leak back.
- **Training stops `horizon` rows short of the test block** — otherwise the last
  training row's outcome lands inside the test period. A subtle leak that
  survives most reviews.
- **Benchmarked against the drift, not a coin flip.** Beating 50% is trivial on
  a series that trends; the comparison is against always predicting the training
  base rate.
- **Wilson confidence intervals, and the lower bound is what counts.** A 56%
  point estimate whose interval reaches 51% is not an edge.
- **Costs applied before the verdict** — accuracy is judged against the payout,
  not in the abstract.
- **Multiple-testing is stated out loud.** Sweeping 122 combinations, ~6.1
  clear the bar by luck alone; the app prints that number beside the real count.

### Honest findings (measured 2026-08-06)

Walk-forward over **978,813 bars**, 122 instrument/horizon combinations:

- **Mean hit rate 51.31%** against the **55.56%** needed. Every EV negative.
- **1 of 122 cleared breakeven** — against ~6.1 expected from chance alone.
  Fewer winners than luck predicts, i.e. no evidence of an edge.
- 30 of 122 beat the base-rate benchmark (better calibrated, still not tradable).
- The lone outlier is **USDCAD 5m at 57.00%** (n=8,070, CI 55.92–58.08%). Treat
  it as a data artifact until proven otherwise: Yahoo's intraday FX bars are
  *indicative*, not dealable, and repeated/stale quotes manufacture exactly this
  kind of spurious autocorrelation. Re-test against a real dealable feed
  (OANDA) before taking it seriously — and note 5m FX spread would eat most of
  a 1.4pp edge anyway.

Same conclusion as the sports side, reached the same way: well-calibrated
probabilities, no edge. That measurement — published rather than hidden — is
the product.

### Harness controls (`tests/test_markets.py`)

A "no edge" result is worthless unless the harness can detect an edge, so two
synthetic controls bracket every real result:

- **Positive control** — a series with genuine signal; the harness must find
  >70% and declare an edge. If this fails, no verdict it has ever produced means
  anything.
- **Negative control** — a pure random walk; the harness must land near 50% and
  must not declare an edge.
- Plus a **causality test**: features built on a prefix must be bit-identical to
  the same rows built on the full series. Any forward-looking calculation breaks
  it.

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
