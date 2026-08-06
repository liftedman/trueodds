"""SQLite layer for Markets mode (data/markets.db).

Same approach as sports_model/db.py: stdlib sqlite3, one file, idempotent
ingestion via UNIQUE constraints so re-running an import updates rather than
duplicates.

Two tables carry the whole design:

  candles      OHLCV bars, one row per (symbol, timeframe, bar-open-time).
  predictions  Every forecast we have ever published, with the outcome filled
               in once the bar it referred to has closed.

`predictions` is the important one. It is the audit trail - an append-only log
written BEFORE the outcome is known, which is the only way a track record means
anything. The sports model earns trust the same way.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager

from . import config

_SCHEMA = """
-- OHLCV bars. `ts` is the bar's OPEN time as a Unix epoch in SECONDS, UTC.
-- Storing open-time (not close-time) matches every exchange API and keeps the
-- "is this bar finished?" question explicit: a bar is closed once
-- now >= ts + timeframe_minutes*60.
CREATE TABLE IF NOT EXISTS candles (
    symbol     TEXT    NOT NULL,
    timeframe  TEXT    NOT NULL,        -- '1m' / '5m' / '15m' / '1h' / '4h' / '1d'
    ts         INTEGER NOT NULL,        -- bar open time, epoch seconds UTC
    open       REAL    NOT NULL,
    high       REAL    NOT NULL,
    low        REAL    NOT NULL,
    close      REAL    NOT NULL,
    volume     REAL,                    -- NULL where the source has none (FX/indices)
    PRIMARY KEY (symbol, timeframe, ts)
);

CREATE INDEX IF NOT EXISTS idx_candles_sym_tf_ts ON candles (symbol, timeframe, ts);

-- Published predictions, written at the moment of forecast and resolved later.
--
-- made_at_ts   open time of the LAST CLOSED bar we used (our information cutoff)
-- target_ts    open time of the bar whose close settles the prediction
-- p_up         our probability that target close > cutoff close
-- actual_up    1/0 once known, NULL while pending
-- model        version tag, so a model change doesn't silently rewrite history
CREATE TABLE IF NOT EXISTS predictions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol      TEXT    NOT NULL,
    timeframe   TEXT    NOT NULL,
    horizon     INTEGER NOT NULL,       -- number of bars ahead
    made_at_ts  INTEGER NOT NULL,
    target_ts   INTEGER NOT NULL,
    ref_close   REAL    NOT NULL,       -- close at the information cutoff
    p_up        REAL    NOT NULL,
    model       TEXT    NOT NULL,
    settle_close REAL,                  -- close at target_ts, once known
    actual_up   INTEGER,                -- 1 / 0 / NULL (pending)
    UNIQUE (symbol, timeframe, horizon, made_at_ts, model)
);

CREATE INDEX IF NOT EXISTS idx_pred_pending ON predictions (actual_up, target_ts);
CREATE INDEX IF NOT EXISTS idx_pred_symbol  ON predictions (symbol, timeframe);

-- Results of each honest walk-forward evaluation run, so the app can show a
-- real, dated measurement rather than a number we typed in.
CREATE TABLE IF NOT EXISTS eval_runs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    run_ts        INTEGER NOT NULL,     -- when the evaluation was run
    symbol        TEXT    NOT NULL,
    timeframe     TEXT    NOT NULL,
    horizon       INTEGER NOT NULL,
    model         TEXT    NOT NULL,
    n             INTEGER NOT NULL,     -- out-of-sample predictions scored
    hit_rate      REAL,
    log_loss      REAL,
    base_log_loss REAL,                 -- always-predict-base-rate benchmark
    brier         REAL,
    base_rate     REAL,                 -- fraction of 'up' outcomes in the sample
    breakeven     REAL,                 -- hit rate needed at the assumed payout
    payout        REAL,
    UNIQUE (run_ts, symbol, timeframe, horizon, model)
);
"""


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    """Yield a connection, committing on success and always closing."""
    config.ensure_dirs()
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


_MIGRATIONS: list[str] = [
    # Additive columns go here as the schema evolves (see sports_model/db.py).
]


def init_db() -> None:
    """Create tables and indexes, then apply additive migrations."""
    with connect() as conn:
        conn.executescript(_SCHEMA)
        for stmt in _MIGRATIONS:
            try:
                conn.execute(stmt)
            except sqlite3.OperationalError:
                pass  # already applied


def upsert_candles(rows: list[tuple]) -> int:
    """Insert or update OHLCV rows.

    Each row: (symbol, timeframe, ts, open, high, low, close, volume).
    Returns the number of rows written.
    """
    if not rows:
        return 0
    with connect() as conn:
        conn.executemany(
            """
            INSERT INTO candles (symbol, timeframe, ts, open, high, low, close, volume)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (symbol, timeframe, ts) DO UPDATE SET
                open = excluded.open,
                high = excluded.high,
                low  = excluded.low,
                close = excluded.close,
                volume = excluded.volume
            """,
            rows,
        )
    return len(rows)


def load_candles(
    symbol: str,
    timeframe: str,
    limit: int | None = None,
) -> list[sqlite3.Row]:
    """Return bars for a symbol/timeframe in ascending time order.

    `limit` takes the MOST RECENT n bars but still returns them oldest-first,
    which is what every model and feature function here expects.
    """
    with connect() as conn:
        if limit:
            cur = conn.execute(
                """
                SELECT * FROM (
                    SELECT * FROM candles
                    WHERE symbol = ? AND timeframe = ?
                    ORDER BY ts DESC LIMIT ?
                ) ORDER BY ts ASC
                """,
                (symbol, timeframe, limit),
            )
        else:
            cur = conn.execute(
                """
                SELECT * FROM candles
                WHERE symbol = ? AND timeframe = ?
                ORDER BY ts ASC
                """,
                (symbol, timeframe),
            )
        return cur.fetchall()


def candle_count(symbol: str, timeframe: str) -> int:
    with connect() as conn:
        cur = conn.execute(
            "SELECT COUNT(*) AS n FROM candles WHERE symbol = ? AND timeframe = ?",
            (symbol, timeframe),
        )
        return int(cur.fetchone()["n"])


def latest_ts(symbol: str, timeframe: str) -> int | None:
    """Open time of the newest stored bar, or None if we have nothing."""
    with connect() as conn:
        cur = conn.execute(
            "SELECT MAX(ts) AS t FROM candles WHERE symbol = ? AND timeframe = ?",
            (symbol, timeframe),
        )
        row = cur.fetchone()
        return int(row["t"]) if row and row["t"] is not None else None


def status() -> list[sqlite3.Row]:
    """Per-symbol/timeframe row counts and coverage - powers `main.py status`."""
    with connect() as conn:
        cur = conn.execute(
            """
            SELECT symbol, timeframe, COUNT(*) AS bars,
                   MIN(ts) AS first_ts, MAX(ts) AS last_ts
            FROM candles
            GROUP BY symbol, timeframe
            ORDER BY symbol, timeframe
            """
        )
        return cur.fetchall()


if __name__ == "__main__":
    init_db()
    print(f"Initialized markets database at {config.DB_PATH}")
