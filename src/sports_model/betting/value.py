"""Value detection: where does our model disagree with the bookmaker?

A bet has positive expected value (EV) when our estimated probability,
multiplied by the decimal odds on offer, exceeds 1:

    edge = p_model * decimal_odds - 1

If we think Arsenal win with p=0.55 and the book offers 2.10, then
0.55 * 2.10 - 1 = +0.155  -> a +15.5% edge (in theory).

The catch: this is only "value" if our p is actually better-calibrated than
the price. Our backtest exists precisely to check whether that's true.
"""

from __future__ import annotations

from dataclasses import dataclass

_OUTCOMES = ["H", "D", "A"]


@dataclass
class ValueBet:
    outcome: str          # 'H' / 'D' / 'A'
    odds: float           # decimal odds we'd bet at
    model_p: float        # our probability
    edge: float           # p*odds - 1 (expected profit per unit staked)


def find_value_bets(
    probs: dict[str, float],
    odds: dict[str, float],
    min_edge: float = 0.0,
) -> list[ValueBet]:
    """Return outcomes where model EV beats the price by at least min_edge.

    probs: {'H':.., 'D':.., 'A':..} from our model.
    odds:  {'H':.., 'D':.., 'A':..} decimal odds on offer (None/<=1 skipped).
    """
    out: list[ValueBet] = []
    for o in _OUTCOMES:
        price = odds.get(o)
        if price is None or price <= 1.0:
            continue
        edge = probs[o] * price - 1.0
        if edge > min_edge:
            out.append(ValueBet(o, float(price), float(probs[o]), float(edge)))
    return out
