"""Sport news aggregator.

Pulls reputable RSS feeds, keeps only recent items, dedupes, tags by sport,
and returns a compact list. We surface headline + summary + link only (the app
links out to the original article) — the correct, license-friendly approach.

Aggregated server-side and embedded in the snapshot, so the app reads news the
same way it reads predictions (cached + offline-friendly, no keys in the app).
"""
from __future__ import annotations

import html
import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree as ET

import requests

# sport tag -> [(source label, RSS url)] — reputable, stable, real-time feeds.
FEEDS: dict[str, list[tuple[str, str]]] = {
    "football": [
        ("BBC Sport", "https://feeds.bbci.co.uk/sport/football/rss.xml"),
        ("The Guardian", "https://www.theguardian.com/football/rss"),
        ("Sky Sports", "https://www.skysports.com/rss/12040"),
    ],
    "nba": [
        ("ESPN", "https://www.espn.com/espn/rss/nba/news"),
        ("Sky Sports", "https://www.skysports.com/rss/12118"),
    ],
    "tennis": [
        ("BBC Sport", "https://feeds.bbci.co.uk/sport/tennis/rss.xml"),
        ("The Guardian", "https://www.theguardian.com/sport/tennis/rss"),
    ],
    "general": [
        ("BBC Sport", "https://feeds.bbci.co.uk/sport/rss.xml"),
        ("The Guardian", "https://www.theguardian.com/sport/rss"),
    ],
}

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")
_HEADERS = {"User-Agent": "Mozilla/5.0 (TrueOdds news aggregator)"}
_MEDIA = "{http://search.yahoo.com/mrss/}"


def _image(item) -> str | None:
    """Largest media:thumbnail / media:content / image enclosure, if any."""
    best, best_w = None, -1
    for tag in ("thumbnail", "content"):
        for el in item.findall(_MEDIA + tag):
            url = el.get("url")
            if not url:
                continue
            try:
                w = int(el.get("width") or 0)
            except ValueError:
                w = 0
            if w >= best_w:
                best, best_w = url, w
    if not best:
        enc = item.find("enclosure")
        if enc is not None and (enc.get("type") or "").startswith("image"):
            best = enc.get("url")
    return best


# og:image / twitter:image meta tag (content before or after the property attr)
_OG = re.compile(
    r'<meta[^>]+(?:property|name)=["\'](?:og:image|twitter:image)["\']'
    r'[^>]+content=["\']([^"\']+)["\']',
    re.I,
)
_OG_REV = re.compile(
    r'<meta[^>]+content=["\']([^"\']+)["\']'
    r'[^>]+(?:property|name)=["\'](?:og:image|twitter:image)["\']',
    re.I,
)


def _og_image(url: str) -> str | None:
    """Fetch a page's social-preview image (used when the feed has none)."""
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=8)
        resp.raise_for_status()
        head = resp.text[:200_000]  # og tags live in <head>
        for rx in (_OG, _OG_REV):
            m = rx.search(head)
            if m and m.group(1).startswith("http"):
                return m.group(1)
    except Exception:
        return None
    return None


def _clean(text: str, limit: int) -> str:
    text = html.unescape(_TAG.sub("", text or ""))
    text = _WS.sub(" ", text).strip()
    return (text[: limit - 1] + "…") if len(text) > limit else text


def _parse_date(s: str | None):
    if not s:
        return None
    try:
        dt = parsedate_to_datetime(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _fetch_feed(sport: str, source: str, url: str, since: datetime) -> list[dict]:
    out: list[dict] = []
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=12)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
    except Exception:
        return out
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        if not title or not link:
            continue
        pub = _parse_date(item.findtext("pubDate"))
        if pub and pub < since:
            continue
        out.append(
            {
                "title": _clean(title, 160),
                "url": link,
                "source": source,
                "sport": sport,
                "summary": _clean(item.findtext("description") or "", 320),
                "image": _image(item),
                "published": pub.isoformat() if pub else None,
            }
        )
    return out


def fetch_news(
    max_age_hours: int = 48, per_sport: int = 12, total: int = 40
) -> list[dict]:
    """Recent sport news across our sports, newest first, deduped."""
    since = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
    seen: set[str] = set()
    merged: list[dict] = []
    for sport, feeds in FEEDS.items():
        items: list[dict] = []
        for source, url in feeds:
            items.extend(_fetch_feed(sport, source, url, since))
        items.sort(key=lambda x: x["published"] or "", reverse=True)
        kept = 0
        for it in items:
            key = re.sub(r"[^a-z0-9]", "", it["title"].lower())[:60]
            if key in seen:
                continue
            seen.add(key)
            merged.append(it)
            kept += 1
            if kept >= per_sport:
                break
    merged.sort(key=lambda x: x["published"] or "", reverse=True)
    merged = merged[:total]

    # Backfill images for sources whose feed carries none (e.g. ESPN/NBA) via
    # the article's og:image. Capped so it never bloats the push.
    budget = 30
    for it in merged:
        if not it.get("image") and budget > 0:
            budget -= 1
            it["image"] = _og_image(it["url"])

    return merged


if __name__ == "__main__":
    items = fetch_news()
    print(f"{len(items)} items")
    for it in items[:12]:
        print(f"  [{it['sport']:8}] {it['source']:12} {it['published']}  {it['title']}")
