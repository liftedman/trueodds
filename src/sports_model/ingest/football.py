"""Ingest football match data + closing odds from football-data.co.uk.

football-data.co.uk publishes one CSV per league per season, free, with
results and bookmaker odds. URL pattern:

    https://www.football-data.co.uk/mmz4281/{season}/{code}.csv

e.g. .../mmz4281/2324/E0.csv  -> Premier League 2023/24.

Column names drift between seasons, so we look up each field from a list of
candidate column names and take the first that exists. This keeps ingestion
robust across ~20 years of slightly different CSV layouts.
"""

from __future__ import annotations

import io
import time

import pandas as pd
import requests

from .. import config, db

# For each logical field, the candidate CSV column names in priority order.
# Older seasons used different headers (e.g. BbAvH for market-average home odds);
# newer ones use AvgCH (closing average) / AvgH (pre-match average).
_ODDS_CANDIDATES: dict[str, list[str]] = {
    # Bet365 closing
    "b365h": ["B365CH", "B365H"],
    "b365d": ["B365CD", "B365D"],
    "b365a": ["B365CA", "B365A"],
    # Market-average closing (consensus)
    "avgh": ["AvgCH", "AvgH", "BbAvH"],
    "avgd": ["AvgCD", "AvgD", "BbAvD"],
    "avga": ["AvgCA", "AvgA", "BbAvA"],
    # Best OPENING odds across books (MaxH = pre-close max; fall back to avg/B365)
    "max_h": ["MaxH", "BbMxH", "AvgH", "B365H"],
    "max_d": ["MaxD", "BbMxD", "AvgD", "B365D"],
    "max_a": ["MaxA", "BbMxA", "AvgA", "B365A"],
    # Pinnacle OPENING (same-book bet price for clean CLV; fall back to B365/avg)
    "pso_h": ["PSH", "B365H", "AvgH"],
    "pso_d": ["PSD", "B365D", "AvgD"],
    "pso_a": ["PSA", "B365A", "AvgA"],
    # Pinnacle CLOSING (sharp benchmark for CLV; fall back to B365/avg closing)
    "psc_h": ["PSCH", "B365CH", "AvgCH"],
    "psc_d": ["PSCD", "B365CD", "AvgCD"],
    "psc_a": ["PSCA", "B365CA", "AvgCA"],
    # Over/Under 2.5 goals — Pinnacle open/close + best open, with fallbacks.
    "pso_ov": ["P>2.5", "B365>2.5", "Avg>2.5"],
    "pso_un": ["P<2.5", "B365<2.5", "Avg<2.5"],
    "psc_ov": ["PC>2.5", "B365C>2.5", "AvgC>2.5"],
    "psc_un": ["PC<2.5", "B365C<2.5", "AvgC<2.5"],
    "max_ov": ["Max>2.5", "Avg>2.5", "B365>2.5"],
    "max_un": ["Max<2.5", "Avg<2.5", "B365<2.5"],
}

_TIMEOUT = 30


def _first_present(row: pd.Series, candidates: list[str]) -> float | None:
    """Return the first candidate column's value that exists and is numeric.

    football-data CSVs occasionally contain junk like '#' in odds cells; we
    treat anything non-numeric as missing rather than crashing.
    """
    for col in candidates:
        if col in row.index and pd.notna(row[col]):
            try:
                return float(row[col])
            except (ValueError, TypeError):
                continue
    return None


def _download_csv(season: str, code: str, retries: int = 3) -> pd.DataFrame | None:
    """Fetch one league-season CSV. Returns None if it's missing (404).

    Retries transient network/SSL errors with a short backoff so one glitch
    doesn't abort a long multi-league ingest.
    """
    url = f"{config.FOOTBALL_BASE_URL}/{season}/{code}.csv"
    for attempt in range(retries):
        try:
            resp = requests.get(url, timeout=_TIMEOUT)
            break
        except requests.exceptions.RequestException:
            if attempt == retries - 1:
                print(f"  warn  {code} {season}: network error, skipped")
                return None
            time.sleep(1.5 * (attempt + 1))
    if resp.status_code == 404:
        return None
    resp.raise_for_status()

    # Cache the raw file so we don't re-download during development.
    config.ensure_dirs()
    raw_path = config.RAW_DIR / f"{code}_{season}.csv"
    raw_path.write_bytes(resp.content)

    # football-data CSVs are latin-1 and sometimes have trailing junk columns.
    df = pd.read_csv(io.BytesIO(resp.content), encoding="latin-1")
    return df


def _int(row: pd.Series, *cols: str) -> int | None:
    """Sum the given integer columns (e.g. yellows + reds), None if all missing."""
    total = None
    for c in cols:
        if c in row.index and pd.notna(row[c]):
            try:
                total = (total or 0) + int(row[c])
            except (ValueError, TypeError):
                continue
    return total


def _normalize(df: pd.DataFrame, code: str, season: str) -> list[dict]:
    """Turn a raw league-season DataFrame into clean match dict rows."""
    league_name = config.ALL_FOOTBALL_LEAGUES[code]
    rows: list[dict] = []

    for _, r in df.iterrows():
        # Skip blank/footer rows that lack the essentials.
        if pd.isna(r.get("HomeTeam")) or pd.isna(r.get("AwayTeam")):
            continue
        if pd.isna(r.get("Date")):
            continue

        # Dates are dd/mm/yy or dd/mm/yyyy -> parse day-first, store ISO.
        date = pd.to_datetime(r["Date"], dayfirst=True, errors="coerce")
        if pd.isna(date):
            continue

        row = {
            "league_code": code,
            "league_name": league_name,
            "season": season,
            "date": date.strftime("%Y-%m-%d"),
            "home": str(r["HomeTeam"]).strip(),
            "away": str(r["AwayTeam"]).strip(),
            "fthg": int(r["FTHG"]) if pd.notna(r.get("FTHG")) else None,
            "ftag": int(r["FTAG"]) if pd.notna(r.get("FTAG")) else None,
            "ftr": str(r["FTR"]).strip() if pd.notna(r.get("FTR")) else None,
            # Corners (HC/AC) and cards (yellows HY/AY + reds HR/AR).
            "home_corners": _int(r, "HC"),
            "away_corners": _int(r, "AC"),
            "home_cards": _int(r, "HY", "HR"),
            "away_cards": _int(r, "AY", "AR"),
        }
        for field, candidates in _ODDS_CANDIDATES.items():
            row[field] = _first_present(r, candidates)
        rows.append(row)

    return rows


_INSERT = """
INSERT INTO football_matches
    (league_code, league_name, season, date, home, away,
     fthg, ftag, ftr, b365h, b365d, b365a, avgh, avgd, avga,
     max_h, max_d, max_a, pso_h, pso_d, pso_a, psc_h, psc_d, psc_a,
     pso_ov, pso_un, psc_ov, psc_un, max_ov, max_un,
     home_corners, away_corners, home_cards, away_cards)
VALUES
    (:league_code, :league_name, :season, :date, :home, :away,
     :fthg, :ftag, :ftr, :b365h, :b365d, :b365a, :avgh, :avgd, :avga,
     :max_h, :max_d, :max_a, :pso_h, :pso_d, :pso_a, :psc_h, :psc_d, :psc_a,
     :pso_ov, :pso_un, :psc_ov, :psc_un, :max_ov, :max_un,
     :home_corners, :away_corners, :home_cards, :away_cards)
ON CONFLICT (league_code, season, date, home, away) DO UPDATE SET
    fthg=excluded.fthg, ftag=excluded.ftag, ftr=excluded.ftr,
    b365h=excluded.b365h, b365d=excluded.b365d, b365a=excluded.b365a,
    avgh=excluded.avgh, avgd=excluded.avgd, avga=excluded.avga,
    max_h=excluded.max_h, max_d=excluded.max_d, max_a=excluded.max_a,
    pso_h=excluded.pso_h, pso_d=excluded.pso_d, pso_a=excluded.pso_a,
    psc_h=excluded.psc_h, psc_d=excluded.psc_d, psc_a=excluded.psc_a,
    pso_ov=excluded.pso_ov, pso_un=excluded.pso_un,
    psc_ov=excluded.psc_ov, psc_un=excluded.psc_un,
    max_ov=excluded.max_ov, max_un=excluded.max_un,
    home_corners=excluded.home_corners, away_corners=excluded.away_corners,
    home_cards=excluded.home_cards, away_cards=excluded.away_cards
"""


def ingest_all(leagues: dict[str, str] | None = None) -> None:
    """Download + load the given league-seasons into the database.

    leagues: {code: name} map. Defaults to the top-5 (xG-capable) leagues.
             Pass config.SECONDARY_FOOTBALL_LEAGUES for the soft-market set.
    """
    leagues = leagues or config.FOOTBALL_LEAGUES
    db.init_db()
    total = 0
    for code in leagues:
        for season in config.FOOTBALL_SEASONS:
            df = _download_csv(season, code)
            if df is None:
                print(f"  skip  {code} {season} (not found)")
                continue
            rows = _normalize(df, code, season)
            with db.connect() as conn:
                conn.executemany(_INSERT, rows)
            total += len(rows)
            label = config.ALL_FOOTBALL_LEAGUES[code]
            print(f"  ok    {label:<18} {season}: {len(rows):>4} matches")
    print(f"\nDone. {total} match rows ingested into {config.DB_PATH}")


if __name__ == "__main__":
    ingest_all()
