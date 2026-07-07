"""Central configuration: paths, leagues, seasons.

Coming from Go, think of this as a package of exported constants. Everything
else imports from here so there's a single source of truth.
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

# --- Paths -----------------------------------------------------------------
# PROJECT_ROOT resolves to c:\NJS\sports-model regardless of where a script
# is run from. We walk up from this file: config.py -> sports_model -> src -> root.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
DB_PATH = DATA_DIR / "sports.db"

# Load secrets from a local .env file (git-ignored) if present.
try:
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass


def football_data_api_key() -> str | None:
    """football-data.org API token, from the FOOTBALL_DATA_API_KEY env var."""
    return os.environ.get("FOOTBALL_DATA_API_KEY")


def supabase_url() -> str | None:
    """Supabase project URL (e.g. https://xxxx.supabase.co)."""
    return os.environ.get("SUPABASE_URL")


def supabase_key() -> str | None:
    """Supabase service-role key (server-side writes only — keep secret)."""
    return os.environ.get("SUPABASE_SERVICE_KEY")


# football-data.org competition codes for the top-5 (complete fixtures + live).
FOOTBALL_DATA_COMP_CODES: dict[str, str] = {
    "E0": "PL",    # Premier League
    "SP1": "PD",   # Primera Division (La Liga)
    "D1": "BL1",   # Bundesliga
    "I1": "SA",    # Serie A
    "F1": "FL1",   # Ligue 1
    "E1": "ELC",   # Championship
    "N1": "DED",   # Eredivisie
    "P1": "PPL",   # Primeira Liga
}
FOOTBALL_DATA_WC_CODE = "WC"


# --- Football leagues ------------------------------------------------------
# football-data.co.uk uses short division codes. These are the top-5 European
# leagues, which have the cleanest free history + closing odds.
# Top-5 leagues: most efficiently priced, and the only ones understat covers
# for xG. These are our calibration benchmark, not where we expect an edge.
FOOTBALL_LEAGUES: dict[str, str] = {
    "E0": "Premier League",
    "SP1": "La Liga",
    "D1": "Bundesliga",
    "I1": "Serie A",
    "F1": "Ligue 1",
    "E1": "Championship",       # England 2nd tier — fixtures via football-data.org
    "N1": "Eredivisie",         # Netherlands — fixtures via football-data.org
    "P1": "Primeira Liga",      # Portugal — fixtures via football-data.org
    "SC0": "Scottish Premiership",  # fixtures via TheSportsDB
    "B1": "Belgian Pro League",     # fixtures via TheSportsDB
    "T1": "Süper Lig",              # Turkey — fixtures via TheSportsDB
    "G1": "Greek Super League",     # fixtures via TheSportsDB
}

# Secondary leagues: lower divisions. Softer lines, thinner sharp money -> the
# realistic place to hunt for a market inefficiency. No xG available, so these
# use the goals-based model. (Kept for backtests, not shown in the app.)
SECONDARY_FOOTBALL_LEAGUES: dict[str, str] = {
    "E2": "League One (ENG)",
    "E3": "League Two (ENG)",
    "D2": "2. Bundesliga",
    "SP2": "La Liga 2",
    "I2": "Serie B",
    "F2": "Ligue 2",
}

# Combined lookup for name resolution during ingestion.
ALL_FOOTBALL_LEAGUES: dict[str, str] = {
    **FOOTBALL_LEAGUES,
    **SECONDARY_FOOTBALL_LEAGUES,
}

# Season codes as football-data.co.uk encodes them: "2324" = 2023/24 season.
# The list is generated from a fixed start year up to the *current* season, so
# ingest always pulls the latest season automatically — no manual bumping. The
# not-yet-started upcoming season just 404s harmlessly until fixtures publish.
FOOTBALL_SEASON_START = 2019  # earliest season we ingest


def season_code(start_year: int) -> str:
    """2023 -> '2324' (football-data.co.uk's two-year encoding)."""
    return f"{start_year % 100:02d}{(start_year + 1) % 100:02d}"


def current_season_start(today: date | None = None) -> int:
    """Starting year of the season in play now. Football kicks off in August,
    so from July we roll to the new season."""
    today = today or date.today()
    return today.year if today.month >= 7 else today.year - 1


FOOTBALL_SEASONS: list[str] = [
    season_code(y) for y in range(FOOTBALL_SEASON_START, current_season_start() + 1)
]

FOOTBALL_BASE_URL = "https://www.football-data.co.uk/mmz4281"

# Time-decay half-life (days) for the club xG model: a match this old counts
# half as much as today's. Tuned by `main.py tune-halflife` (out-of-sample):
# 240 days gave the lowest pooled log loss across 2022/23-2024/25.
XG_HALF_LIFE_DAYS = 240


# TheSportsDB league IDs for the top-5, used to fetch club kickoff times + live
# status (the same source as the World Cup schedule).
CLUB_TSDB_IDS: dict[str, str] = {
    "E0": "4328",   # Premier League
    "SP1": "4335",  # La Liga
    "D1": "4331",   # Bundesliga
    "I1": "4332",   # Serie A
    "F1": "4334",   # Ligue 1
    "E1": "4329",   # Championship (TheSportsDB fallback)
    "N1": "4337",   # Eredivisie
    "P1": "4344",   # Primeira Liga
    "SC0": "4330",  # Scottish Premiership (TheSportsDB primary — not on football-data free)
    "B1": "4338",   # Belgian Pro League
    "T1": "4339",   # Turkish Süper Lig
    "G1": "4336",   # Greek Super League
}

# Kickoff times from TheSportsDB are UTC. We display them shifted to this
# offset (hours). Default +1 = West Africa Time (Nigeria). Change if needed.
DISPLAY_TZ_OFFSET_HOURS = 1
DISPLAY_TZ_LABEL = "WAT"


def ensure_dirs() -> None:
    """Create the data folders if they don't exist yet."""
    for d in (DATA_DIR, RAW_DIR, PROCESSED_DIR):
        d.mkdir(parents=True, exist_ok=True)
