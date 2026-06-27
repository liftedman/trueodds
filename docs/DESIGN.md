# sports-model — Design System

The visual language for the app. One neutral foundation (light **and** dark),
with a **per-sport accent** so each section is instantly recognisable. Tokens
below are the source of truth — reuse them verbatim in the web dashboard and
the Flutter app.

## Principles
- **Honest by design.** Confidence is always shown; we never imply certainty.
- **Calm base, vivid accent.** Neutral surfaces; one strong sport colour at a time.
- **Same in light & dark.** Every token has both values; nothing hard-codes a shade.
- **Legible data.** Probabilities and scores use a monospace face for clean alignment.

## Color — neutral foundation

| Token | Light | Dark |
|---|---|---|
| `--ground` (page) | `#F6F7F9` | `#0E1117` |
| `--surface` (cards) | `#FFFFFF` | `#171C24` |
| `--text` | `#131722` | `#E9EDF3` |
| `--muted` | `#5A6472` | `#8B95A4` |
| `--line` (borders) | `#E4E8EE` | `#242B35` |

## Color — per-sport accent

Each sport sets `--accent` (and a readable `--accent-ink` for text on the accent).

| Sport | Accent | Notes |
|---|---|---|
| Clubs (football) | `#16B364` green | pitch |
| World Cup | `#2E7DF6` blue | |
| NBA | `#8B5CF6` purple | |
| Tennis | `#84CC16` lime | "lemon green" |
| Champions League | `#E5484D` red | |

App default accent (no sport context): `#2E7DF6` blue.

## Confidence (the honesty signal)

| Level | Color | Meaning |
|---|---|---|
| High | `#16B364` green | model is fairly sure (e.g. ≥65%) |
| Medium | `#E8A33D` amber | leaning, not strong |
| Low | `#8B95A4` grey | close to a coin-flip — say so |

## Typography
- **Display / headings:** system sans — `-apple-system, "Segoe UI", Roboto, sans-serif`, weight 700–800, tight tracking.
- **Body:** same sans, 15px, weight 400.
- **Data (numbers/odds/scores):** monospace — `ui-monospace, "Cascadia Mono", Consolas, monospace`.
- **Scale:** 40 / 28 / 20 / 15 / 13 / 11 (display → caption), clamped for mobile.

## Shape & spacing
- Radius: 8px controls · 14px cards · pill (999px) badges.
- Spacing scale: 4 · 8 · 12 · 16 · 24 · 32 · 48.
- Borders: 1px `--line`. Shadows: subtle, dark-mode uses border over shadow.

## Components
- **Tabs** — sticky; active tab carries the sport accent.
- **Predictor card** — matchup, animated probability bars (accent), confidence badge.
- **Market chips** — compact pills; high-probability ones use the accent.
- **Fixture row** — date/time, teams, live badge (pulsing red `#E5484D`), prediction.
- **Theme toggle** — light/dark, persists in `localStorage`.
- **Honesty panel** — visible "we don't beat the bookmaker" + live calibration.
