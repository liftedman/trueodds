"""Stake sizing.

Two modes:
  - flat:  always stake 1 unit. The cleanest way to MEASURE an edge, because
           yield = profit / total_staked isn't distorted by compounding.
  - kelly: fractional Kelly — bet a fraction of bankroll proportional to edge.
           Optimal for GROWING a bankroll *if* you genuinely have an edge.
           With no real edge it just loses money faster, which is why we
           evaluate with flat stakes first.

Kelly fraction for a single decimal-odds bet:
    f* = (p * odds - 1) / (odds - 1) = edge / (odds - 1)
We scale by `fraction` (e.g. 0.25 = quarter-Kelly) because full Kelly is
brutally volatile and very sensitive to probability errors, and cap it so a
single bet can never risk more than `cap` of the bankroll.
"""

from __future__ import annotations


def kelly_fraction(
    model_p: float,
    odds: float,
    fraction: float = 0.25,
    cap: float = 0.05,
) -> float:
    """Fraction of bankroll to stake (0 if no edge)."""
    edge = model_p * odds - 1.0
    if edge <= 0:
        return 0.0
    full = edge / (odds - 1.0)
    return min(full * fraction, cap)
