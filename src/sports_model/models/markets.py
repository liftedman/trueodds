"""Derive common betting markets from a scoreline probability matrix.

Both the club model (Dixon-Coles) and the World Cup model (Elo) expose a
`score_matrix(home, away)` — a grid where mat[i][j] = P(home scores i, away
scores j). Every goals-based market is just a sum over the right cells, so we
compute them all from that one grid: no extra model needed.

Note on "accuracy": Over 0.5 lands ~92% of the time, Over 1.5 ~75% — high, but
those are easy calls at tiny odds. Over 2.5 and BTTS sit near 50-55%. The grid
reports each honestly.
"""

from __future__ import annotations

import numpy as np

GOAL_LINES = [0.5, 1.5, 2.5, 3.5]


def goal_markets(mat: np.ndarray) -> dict:
    """Over/Under for common lines + Both Teams To Score, from a score grid."""
    n = mat.shape[0]
    totals = np.add.outer(np.arange(n), np.arange(n))
    out: dict[str, float] = {}
    for line in GOAL_LINES:
        over = float(mat[totals > line].sum())
        out[f"over_{line}"] = over
        out[f"under_{line}"] = 1.0 - over
    btts_yes = float(mat[1:, 1:].sum())   # home >=1 AND away >=1
    out["btts_yes"] = btts_yes
    out["btts_no"] = 1.0 - btts_yes
    return out


def result_markets(mat: np.ndarray) -> dict:
    """Double chance, draw-no-bet, handicaps, clean sheets, team totals."""
    n = mat.shape[0]
    I, J = np.indices((n, n))
    home = float(mat[I > J].sum())
    draw = float(mat[I == J].sum())
    away = float(mat[I < J].sum())
    hb = home + away  # for draw-no-bet (stake refunded on a draw)
    return {
        "dc_1x": home + draw, "dc_12": home + away, "dc_x2": draw + away,
        "dnb_home": home / hb if hb else 0.0,
        "dnb_away": away / hb if hb else 0.0,
        # Asian handicap -1.5: team must win by 2+ goals.
        "home_hcap_15": float(mat[I - J >= 2].sum()),
        "away_hcap_15": float(mat[J - I >= 2].sum()),
        # Clean sheet = opponent scores 0.
        "home_cs": float(mat[:, 0].sum()),
        "away_cs": float(mat[0, :].sum()),
        # Team total over 1.5 = that team scores 2+.
        "home_tt15": float(mat[I >= 2].sum()),
        "away_tt15": float(mat[J >= 2].sum()),
    }
