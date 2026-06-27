"""NBA upcoming games + live scores via nba_api ScoreboardV3.

Mirrors the football fixtures feed: for each of the next few days we pull the
scoreboard, drop finished games, and attach an Elo prediction (win prob +
projected score). gameStatus: 1 = scheduled, 2 = live, 3 = final.

Off-season note: the NBA breaks from late June to October, and next season's
schedule isn't published until ~August — so this returns nothing until then,
then fills in automatically (same as the club leagues in summer).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from .. import config
from . import nba as nba_mod

_FINAL = 3
_LIVE = 2


def _fmt(utc_iso: str) -> tuple[str, str]:
    try:
        dt = datetime.strptime(utc_iso, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc)
        local = dt + timedelta(hours=config.DISPLAY_TZ_OFFSET_HOURS)
        return local.strftime("%Y-%m-%d"), local.strftime("%H:%M")
    except (ValueError, TypeError):
        return (utc_iso or "")[:10], ""


def fetch_schedule(model, days_ahead: int = 7,
                   today: str | None = None) -> list[dict]:
    """Upcoming + live NBA games over the next `days_ahead` days."""
    from nba_api.stats.endpoints import scoreboardv3

    start = datetime.strptime(today, "%Y-%m-%d") if today else datetime.combine(
        date.today(), datetime.min.time())
    out: list[dict] = []
    for i in range(days_ahead):
        day = (start + timedelta(days=i)).strftime("%Y-%m-%d")
        try:
            data = scoreboardv3.ScoreboardV3(game_date=day, timeout=30).get_dict()
        except Exception:
            continue
        games = (data.get("scoreboard") or {}).get("games", [])
        for g in games:
            if g.get("gameStatus") == _FINAL:
                continue  # played -> never show again
            ht, at = g.get("homeTeam", {}), g.get("awayTeam", {})
            home, away = ht.get("teamTricode"), at.get("teamTricode")
            if not home or not away:
                continue
            live = g.get("gameStatus") == _LIVE
            date_s, tm = _fmt(g.get("gameTimeUTC"))
            p = model.predict(home, away)
            score = None
            if live and ht.get("score") is not None:
                score = f"{ht['score']}-{at['score']}"
            out.append({
                "date": date_s, "time": tm, "live": live,
                "status": g.get("gameStatusText", ""), "score": score,
                "home": nba_mod.TEAM_NAMES.get(home, home),
                "away": nba_mod.TEAM_NAMES.get(away, away),
                "home_win": round(p["home_win"], 3),
                "away_win": round(p["away_win"], 3),
                "proj": f"{p['proj_home']:.0f}-{p['proj_away']:.0f}",
            })
    return out
