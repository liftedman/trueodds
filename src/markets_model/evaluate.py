"""Walk-forward evaluation - the honest part.

This module exists to try to prove the direction model worthless. Everything it
reports is out-of-sample: the model is refitted on an expanding window and only
ever scores bars it has never seen, in strict time order. No shuffling, no
k-fold, no scaling statistics borrowed from the future.

Four guards against the standard ways a backtest flatters itself:

1. **Expanding-window walk-forward.** Train on [0, t), predict [t, t+block),
   advance. Refitting per block means the model never sees its own test data,
   and the scaler is refitted with it (see direction.DirectionModel.fit).

2. **A benchmark that is hard to beat by accident.** We compare the model's log
   loss against always predicting the *training* base rate. Beating a coin flip
   is trivial when a series drifts upward; beating the drift itself is the
   actual bar.

3. **A minimum sample size.** Below config.MIN_SAMPLE_FOR_CLAIM we report the
   number but refuse to call it an edge, and we always print the Wilson
   confidence interval so the reader can see how little the point estimate means.

4. **Costs applied before the verdict.** A 53% hit rate is a losing strategy at
   an 80% fixed payout. The verdict is computed net of the payoff structure, not
   from accuracy in the abstract.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field

import numpy as np

from . import config, db, direction, features


# --- metric helpers --------------------------------------------------------

def _clip(p: np.ndarray, eps: float = 1e-12) -> np.ndarray:
    return np.clip(p, eps, 1.0 - eps)


def log_loss(y: np.ndarray, p: np.ndarray) -> float:
    """Mean negative log likelihood. Lower is better; 0.6931 = coin flip."""
    if y.size == 0:
        return float("nan")
    pc = _clip(p)
    return float(-np.mean(y * np.log(pc) + (1 - y) * np.log(1 - pc)))


def brier(y: np.ndarray, p: np.ndarray) -> float:
    if y.size == 0:
        return float("nan")
    return float(np.mean((p - y) ** 2))


def wilson_interval(wins: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval for a proportion.

    Preferred over the normal approximation because it stays sane at small n and
    near 0/1 - exactly the regimes where a hit rate is most likely to be
    over-interpreted.
    """
    if n == 0:
        return (float("nan"), float("nan"))
    ph = wins / n
    denom = 1.0 + z * z / n
    centre = (ph + z * z / (2 * n)) / denom
    half = z * math.sqrt(ph * (1 - ph) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def calibration_bins(y: np.ndarray, p: np.ndarray, n_bins: int = 10) -> list[dict]:
    """Bucket predictions and compare predicted vs realised frequency.

    A well-calibrated model that has no edge still shows p ~= realised in every
    bucket - it just never strays far from the base rate. That distinction is
    what makes calibration worth showing a user.
    """
    out: list[dict] = []
    if y.size == 0:
        return out
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    for b in range(n_bins):
        lo, hi = edges[b], edges[b + 1]
        mask = (p >= lo) & (p < hi) if b < n_bins - 1 else (p >= lo) & (p <= hi)
        n = int(mask.sum())
        if n == 0:
            continue
        out.append(
            {
                "lo": float(lo),
                "hi": float(hi),
                "n": n,
                "predicted": float(p[mask].mean()),
                "realised": float(y[mask].mean()),
            }
        )
    return out


# --- result container ------------------------------------------------------

@dataclass
class EvalResult:
    symbol: str
    timeframe: str
    horizon: int
    model: str
    n: int
    base_rate: float
    hit_rate: float
    hit_ci: tuple[float, float]
    model_log_loss: float
    base_log_loss: float
    brier_score: float
    payout: float
    breakeven: float
    ev_per_trade: float
    # Same metrics restricted to predictions the model is most confident about,
    # which is how anyone would actually trade it.
    conf_threshold: float = 0.0
    conf_n: int = 0
    conf_hit_rate: float = float("nan")
    conf_hit_ci: tuple[float, float] = (float("nan"), float("nan"))
    conf_ev: float = float("nan")
    calibration: list[dict] = field(default_factory=list)
    top_features: list[tuple[str, float]] = field(default_factory=list)

    # --- interpretation ----------------------------------------------------
    @property
    def beats_base_rate(self) -> bool:
        """Did the model carry more information than the drift-only benchmark?"""
        return self.model_log_loss < self.base_log_loss

    @property
    def enough_data(self) -> bool:
        return self.n >= config.MIN_SAMPLE_FOR_CLAIM

    @property
    def profitable_at_payout(self) -> bool:
        """Is the LOWER confidence bound above breakeven?

        Using the lower bound, not the point estimate, is the whole discipline.
        A 56% point estimate whose interval reaches down to 51% is not an edge;
        it is a sample that happens to lean the right way.
        """
        return self.enough_data and self.hit_ci[0] > self.breakeven

    def verdict(self) -> str:
        if not self.enough_data:
            return (
                f"INSUFFICIENT DATA - {self.n} out-of-sample predictions "
                f"(need {config.MIN_SAMPLE_FOR_CLAIM}). No claim either way."
            )
        if self.profitable_at_payout:
            return (
                "APPARENT EDGE - hit rate's lower bound clears breakeven. "
                "Treat with suspicion: re-run on other symbols and periods, and "
                "paper-trade before believing it."
            )
        if self.beats_base_rate:
            return (
                "SOME SIGNAL, NOT PROFITABLE - better calibrated than the "
                f"base-rate benchmark, but the hit rate does not clear the "
                f"{self.breakeven:.2%} needed at a {self.payout:.0%} payout."
            )
        return (
            "NO EDGE - the model carries no more information than predicting "
            "the base rate, and loses money at this payout."
        )


# --- the walk-forward loop -------------------------------------------------

def walk_forward(
    symbol: str,
    timeframe: str,
    horizon: int = 1,
    kind: str = "logreg",
    initial_frac: float = 0.5,
    n_blocks: int = 10,
    payout: float = config.DEFAULT_FIXED_PAYOUT,
    conf_threshold: float = 0.02,
    max_bars: int | None = None,
) -> EvalResult | None:
    """Evaluate the direction model out-of-sample. Returns None if data is short.

    initial_frac  fraction of history used for the first training window
    n_blocks      how many refit-and-test steps to take across the remainder
    conf_threshold  |p - 0.5| above which a prediction counts as "confident"
    """
    candles = db.load_candles(symbol, timeframe, limit=max_bars)
    if len(candles) < features.WARMUP + horizon + 200:
        return None

    X, y, idx, _ts, _close = features.build_dataset(candles, horizon=horizon)
    if X.shape[0] < 200:
        return None

    n = X.shape[0]
    start = int(n * initial_frac)
    if start < 100 or start >= n - 10:
        return None

    block = max(1, (n - start) // n_blocks)

    oos_p: list[np.ndarray] = []
    oos_y: list[np.ndarray] = []
    base_p: list[np.ndarray] = []
    last_model: direction.DirectionModel | None = None

    t = start
    while t < n:
        end = min(t + block, n)

        # IMPORTANT: the training window stops `horizon` rows short of t.
        # Row t-1's target is close[idx[t-1] + horizon], which lands at or after
        # the first test bar. Including it would hand the model an outcome from
        # inside the test period - a subtle leak that survives most reviews.
        train_end = max(0, t - horizon)
        if train_end < 100:
            t = end
            continue

        X_tr, y_tr = X[:train_end], y[:train_end]
        X_te, y_te = X[t:end], y[t:end]
        if y_te.size == 0:
            break

        model = direction.fit_model(X_tr, y_tr, kind=kind)
        last_model = model

        oos_p.append(model.predict_proba_up(X_te))
        oos_y.append(y_te)
        # The benchmark: predict the training base rate for every test bar.
        base_p.append(np.full(y_te.size, model.base_rate, dtype=float))

        t = end

    if not oos_y:
        return None

    p = np.concatenate(oos_p)
    yy = np.concatenate(oos_y)
    bp = np.concatenate(base_p)

    preds_up = p > 0.5
    wins = int((preds_up == (yy == 1)).sum())
    total = int(yy.size)
    hit = wins / total

    # EV per unit staked on a fixed-payout binary trade:
    #   win  -> +payout
    #   lose -> -1
    ev = hit * payout - (1.0 - hit)

    conf_mask = np.abs(p - 0.5) >= conf_threshold
    conf_n = int(conf_mask.sum())
    if conf_n > 0:
        c_wins = int((preds_up[conf_mask] == (yy[conf_mask] == 1)).sum())
        c_hit = c_wins / conf_n
        c_ci = wilson_interval(c_wins, conf_n)
        c_ev = c_hit * payout - (1.0 - c_hit)
    else:
        c_hit, c_ci, c_ev = float("nan"), (float("nan"), float("nan")), float("nan")

    return EvalResult(
        symbol=symbol,
        timeframe=timeframe,
        horizon=horizon,
        model=f"{kind}-h{horizon}",
        n=total,
        base_rate=float(yy.mean()),
        hit_rate=hit,
        hit_ci=wilson_interval(wins, total),
        model_log_loss=log_loss(yy, p),
        base_log_loss=log_loss(yy, bp),
        brier_score=brier(yy, p),
        payout=payout,
        breakeven=config.breakeven_hit_rate(payout),
        ev_per_trade=ev,
        conf_threshold=conf_threshold,
        conf_n=conf_n,
        conf_hit_rate=c_hit,
        conf_hit_ci=c_ci,
        conf_ev=c_ev,
        calibration=calibration_bins(yy, p),
        top_features=(
            last_model.coefficients(features.FEATURE_NAMES)[:6] if last_model else []
        ),
    )


# --- reporting -------------------------------------------------------------

def format_result(r: EvalResult) -> str:
    """Human-readable block for the CLI."""
    lines = [
        f"{r.symbol}  {r.timeframe}  horizon={r.horizon} bar(s)  model={r.model}",
        f"  out-of-sample predictions : {r.n}",
        f"  base rate (actual 'up')   : {r.base_rate:.2%}",
        f"  hit rate                  : {r.hit_rate:.2%}  "
        f"(95% CI {r.hit_ci[0]:.2%} - {r.hit_ci[1]:.2%})",
        f"  breakeven @ {r.payout:.0%} payout    : {r.breakeven:.2%}",
        f"  EV per trade              : {r.ev_per_trade:+.2%}",
        f"  log loss  model / base    : {r.model_log_loss:.5f} / {r.base_log_loss:.5f}"
        f"   ({'better' if r.beats_base_rate else 'no better'})",
        f"  Brier score               : {r.brier_score:.5f}",
    ]
    if r.conf_n:
        lines.append(
            f"  confident subset (|p-.5|>={r.conf_threshold:.2f}) : n={r.conf_n}  "
            f"hit={r.conf_hit_rate:.2%}  EV={r.conf_ev:+.2%}"
        )
    if r.top_features:
        feats = ", ".join(f"{n}={c:+.3f}" for n, c in r.top_features)
        lines.append(f"  strongest coefficients    : {feats}")
    lines.append(f"  VERDICT: {r.verdict()}")
    return "\n".join(lines)


def save_result(r: EvalResult, run_ts: int | None = None) -> None:
    """Persist an evaluation so the app can display a dated, real measurement."""
    run_ts = run_ts or int(time.time())
    db.init_db()
    with db.connect() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO eval_runs (
                run_ts, symbol, timeframe, horizon, model, n,
                hit_rate, log_loss, base_log_loss, brier,
                base_rate, breakeven, payout
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_ts, r.symbol, r.timeframe, r.horizon, r.model, r.n,
                r.hit_rate, r.model_log_loss, r.base_log_loss, r.brier_score,
                r.base_rate, r.breakeven, r.payout,
            ),
        )
