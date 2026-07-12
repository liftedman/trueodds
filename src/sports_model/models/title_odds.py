"""Championship ("title chances") via Monte-Carlo simulation.

Given current Elo ratings, we seed the top teams into a bracket and simulate
many best-of-seven playoffs, counting how often each team wins it all. It's an
honest, rating-based estimate — labelled in the app as "if the playoffs were
seeded by current rating", since we don't model the exact conference format.
"""
from __future__ import annotations

import random
from math import comb


def _game_prob(ra: float, rb: float) -> float:
    return 1.0 / (1.0 + 10 ** (-(ra - rb) / 400.0))


def _series_prob(p: float, best_of: int = 7) -> float:
    """P(win a best-of-N series) given per-game win prob p."""
    need = best_of // 2 + 1
    return sum(comb(need - 1 + k, k) * p ** need * (1 - p) ** k for k in range(need))


def _seed_order(n: int) -> list[int]:
    """Standard bracket seeding order for a power-of-two field (0-indexed)."""
    order = [0]
    while len(order) < n:
        m = len(order) * 2
        order = [x for i in order for x in (i, m - 1 - i)]
    return order


def title_odds(ratings: dict[str, float], names: dict[str, str],
               field_size: int = 8, n_sims: int = 5000, best_of: int = 7) -> list[dict]:
    """Championship probability per team. Returns [{name, pct}] desc, pct>0."""
    ranked = sorted(ratings, key=lambda t: -ratings[t])
    # largest power of two that fits both the field target and the team count
    size = 1
    while size * 2 <= min(field_size, len(ranked)):
        size *= 2
    if size < 2:
        return []
    field = [ranked[i] for i in _seed_order(size)]

    cache: dict[tuple[str, str], float] = {}

    def sp(a: str, b: str) -> float:
        key = (a, b)
        if key not in cache:
            cache[key] = _series_prob(_game_prob(ratings[a], ratings[b]), best_of)
        return cache[key]

    wins = {t: 0 for t in field}
    rng = random.Random(1234)  # fixed seed -> stable odds between pushes
    for _ in range(n_sims):
        alive = field
        while len(alive) > 1:
            nxt = []
            for i in range(0, len(alive), 2):
                a, b = alive[i], alive[i + 1]
                nxt.append(a if rng.random() < sp(a, b) else b)
            alive = nxt
        wins[alive[0]] += 1

    out = [{"name": names.get(t, t), "pct": round(wins[t] / n_sims, 4)}
           for t in field if wins[t] > 0]
    out.sort(key=lambda x: -x["pct"])
    return out
