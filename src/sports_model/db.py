"""SQLite database layer.

We use the standard-library `sqlite3` module — no external dependency, the DB
is a single file at data/sports.db. Think of this as your lightweight,
zero-setup Postgres for local work.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from collections.abc import Iterator

from . import config

# Schema for football matches. One row per match.
# - A UNIQUE constraint on (league, season, date, home, away) makes ingestion
#   idempotent: re-running an import updates rows instead of duplicating them.
# - Odds columns store DECIMAL (European) odds. NULL where a bookmaker didn't
#   price that match.
_SCHEMA = """
CREATE TABLE IF NOT EXISTS football_matches (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    league_code  TEXT    NOT NULL,
    league_name  TEXT    NOT NULL,
    season       TEXT    NOT NULL,
    date         TEXT    NOT NULL,          -- ISO 8601: YYYY-MM-DD
    home         TEXT    NOT NULL,
    away         TEXT    NOT NULL,
    fthg         INTEGER,                   -- full-time home goals
    ftag         INTEGER,                   -- full-time away goals
    ftr          TEXT,                      -- 'H' / 'D' / 'A'
    xg_h         REAL,                      -- expected goals, home (understat)
    xg_a         REAL,                      -- expected goals, away (understat)
    home_corners INTEGER,
    away_corners INTEGER,
    home_cards   INTEGER,                   -- yellows + reds
    away_cards   INTEGER,
    -- Bet365 closing odds
    b365h        REAL,
    b365d        REAL,
    b365a        REAL,
    -- Market average CLOSING odds (consensus across bookmakers)
    avgh         REAL,
    avgd         REAL,
    avga         REAL,
    -- Best OPENING odds across all bookmakers (what a line-shopper gets)
    max_h        REAL,
    max_d        REAL,
    max_a        REAL,
    -- Pinnacle OPENING odds (same-book bet price for a clean CLV test)
    pso_h        REAL,
    pso_d        REAL,
    pso_a        REAL,
    -- Pinnacle CLOSING odds (sharpest book — used as the 'true price' for CLV)
    psc_h        REAL,
    psc_d        REAL,
    psc_a        REAL,
    -- Over/Under 2.5 goals odds. ov = over 2.5, un = under 2.5.
    pso_ov       REAL,   -- Pinnacle opening over   (clean-CLV bet price)
    pso_un       REAL,   -- Pinnacle opening under
    psc_ov       REAL,   -- Pinnacle closing over   (CLV benchmark)
    psc_un       REAL,   -- Pinnacle closing under
    max_ov       REAL,   -- best opening over  (best-price bet)
    max_un       REAL,   -- best opening under
    UNIQUE (league_code, season, date, home, away)
);

CREATE INDEX IF NOT EXISTS idx_fm_league_season
    ON football_matches (league_code, season);
CREATE INDEX IF NOT EXISTS idx_fm_date
    ON football_matches (date);

-- International (national team) matches, for the Elo / World Cup model.
-- Includes future fixtures: those have NULL scores until played.
CREATE TABLE IF NOT EXISTS international_matches (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    date         TEXT    NOT NULL,          -- ISO 8601: YYYY-MM-DD
    home         TEXT    NOT NULL,
    away         TEXT    NOT NULL,
    home_score   INTEGER,                   -- NULL = not played yet
    away_score   INTEGER,
    tournament   TEXT,
    neutral      INTEGER,                   -- 1 if played at a neutral venue
    UNIQUE (date, home, away)
);

CREATE INDEX IF NOT EXISTS idx_im_date ON international_matches (date);
CREATE INDEX IF NOT EXISTS idx_im_tournament ON international_matches (tournament);

-- NBA games (one row per game). Teams stored as 3-letter abbreviations.
CREATE TABLE IF NOT EXISTS nba_games (
    game_id    TEXT PRIMARY KEY,
    date       TEXT NOT NULL,          -- ISO 8601: YYYY-MM-DD
    season     TEXT NOT NULL,          -- e.g. '2023-24'
    home       TEXT NOT NULL,
    away       TEXT NOT NULL,
    home_pts   INTEGER,
    away_pts   INTEGER
);

CREATE INDEX IF NOT EXISTS idx_nba_date ON nba_games (date);
CREATE INDEX IF NOT EXISTS idx_nba_season ON nba_games (season);

-- Tennis matches (ATP). Stored winner/loser (tennis has no home/away).
CREATE TABLE IF NOT EXISTS tennis_matches (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    date      TEXT NOT NULL,       -- ISO 8601
    surface   TEXT,                -- Hard / Clay / Grass
    winner    TEXT NOT NULL,
    loser     TEXT NOT NULL,
    tourney   TEXT,
    UNIQUE (date, winner, loser, tourney)
);

CREATE INDEX IF NOT EXISTS idx_tennis_date ON tennis_matches (date);
"""


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    """Yield a SQLite connection, committing on success and closing always.

    Usage:
        with connect() as conn:
            conn.execute(...)
    """
    config.ensure_dirs()
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row  # access columns by name, like a dict
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


# Columns added after the first release. SQLite can't add a column via
# CREATE TABLE IF NOT EXISTS, so we add them defensively on every init.
_MIGRATIONS = [
    "ALTER TABLE football_matches ADD COLUMN xg_h REAL",
    "ALTER TABLE football_matches ADD COLUMN xg_a REAL",
    "ALTER TABLE football_matches ADD COLUMN max_h REAL",
    "ALTER TABLE football_matches ADD COLUMN max_d REAL",
    "ALTER TABLE football_matches ADD COLUMN max_a REAL",
    "ALTER TABLE football_matches ADD COLUMN psc_h REAL",
    "ALTER TABLE football_matches ADD COLUMN psc_d REAL",
    "ALTER TABLE football_matches ADD COLUMN psc_a REAL",
    "ALTER TABLE football_matches ADD COLUMN pso_h REAL",
    "ALTER TABLE football_matches ADD COLUMN pso_d REAL",
    "ALTER TABLE football_matches ADD COLUMN pso_a REAL",
    "ALTER TABLE football_matches ADD COLUMN pso_ov REAL",
    "ALTER TABLE football_matches ADD COLUMN pso_un REAL",
    "ALTER TABLE football_matches ADD COLUMN psc_ov REAL",
    "ALTER TABLE football_matches ADD COLUMN psc_un REAL",
    "ALTER TABLE football_matches ADD COLUMN max_ov REAL",
    "ALTER TABLE football_matches ADD COLUMN max_un REAL",
    "ALTER TABLE football_matches ADD COLUMN home_corners INTEGER",
    "ALTER TABLE football_matches ADD COLUMN away_corners INTEGER",
    "ALTER TABLE football_matches ADD COLUMN home_cards INTEGER",
    "ALTER TABLE football_matches ADD COLUMN away_cards INTEGER",
]


def init_db() -> None:
    """Create tables and indexes, then apply any additive migrations."""
    with connect() as conn:
        conn.executescript(_SCHEMA)
        for stmt in _MIGRATIONS:
            try:
                conn.execute(stmt)
            except sqlite3.OperationalError:
                pass  # column already exists — fine


if __name__ == "__main__":
    init_db()
    print(f"Initialized database at {config.DB_PATH}")
