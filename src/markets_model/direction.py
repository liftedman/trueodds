"""The short-horizon direction model: P(price is higher N bars from now).

Deliberately modest choices. Logistic regression with L2 regularisation is the
default because it is hard to overfit, produces probabilities that are usually
close to calibrated without post-processing, and its coefficients can be read
and sanity-checked. A gradient-boosting variant is available for comparison.

The point of this module is not to be clever. It is to be a fair, competent
attempt - so that when evaluate.py reports the out-of-sample number, that number
is a meaningful statement about the market rather than about a bug or a
deliberately weak model. If a straightforward, well-regularised classifier on
sensible features cannot beat the base rate, that is the finding.

Scaler and model are fitted TOGETHER on training data only and returned as one
object, so it is structurally impossible for the caller to scale using
statistics the training window could not have known.
"""

from __future__ import annotations

import numpy as np

MODEL_VERSION = "logreg-v1"


class DirectionModel:
    """Scaler + classifier fitted on one training window."""

    __slots__ = ("_mu", "_sd", "_clf", "kind", "base_rate")

    def __init__(self, kind: str = "logreg"):
        self.kind = kind
        self._mu: np.ndarray | None = None
        self._sd: np.ndarray | None = None
        self._clf = None
        self.base_rate = 0.5

    # --- fitting -----------------------------------------------------------
    def fit(self, X: np.ndarray, y: np.ndarray) -> "DirectionModel":
        """Fit on training rows only. Standardisation stats come from X alone."""
        self.base_rate = float(y.mean()) if y.size else 0.5

        self._mu = X.mean(axis=0)
        sd = X.std(axis=0)
        # Constant columns (e.g. volume for FX, always 0) would divide by zero.
        sd[sd < 1e-12] = 1.0
        self._sd = sd
        Xs = (X - self._mu) / self._sd

        # A degenerate training window (all one class) has nothing to learn.
        if np.unique(y).size < 2:
            self._clf = None
            return self

        if self.kind == "gbdt":
            from sklearn.ensemble import HistGradientBoostingClassifier

            self._clf = HistGradientBoostingClassifier(
                max_iter=200,
                learning_rate=0.05,
                max_depth=3,
                l2_regularization=1.0,
                early_stopping=True,
                validation_fraction=0.15,
                random_state=0,
            )
        else:
            from sklearn.linear_model import LogisticRegression

            # C=0.1 is deliberately strong regularisation. Financial features
            # are noisy and correlated; a loose fit finds structure that does
            # not survive out of sample.
            self._clf = LogisticRegression(C=0.1, max_iter=2000, solver="lbfgs")

        self._clf.fit(Xs, y)
        return self

    # --- prediction --------------------------------------------------------
    def predict_proba_up(self, X: np.ndarray) -> np.ndarray:
        """P(up) for each row. Falls back to the training base rate if unfit."""
        if self._clf is None or self._mu is None:
            return np.full(X.shape[0], self.base_rate, dtype=float)
        Xs = (X - self._mu) / self._sd
        return self._clf.predict_proba(Xs)[:, 1]

    def coefficients(self, names: list[str]) -> list[tuple[str, float]]:
        """(feature, coefficient) pairs, largest magnitude first.

        Only meaningful for the linear model - returns [] for gbdt. Useful for
        showing a user *why* a prediction leans the way it does.
        """
        clf = self._clf
        if clf is None or not hasattr(clf, "coef_"):
            return []
        coefs = clf.coef_[0]
        pairs = list(zip(names, (float(c) for c in coefs)))
        pairs.sort(key=lambda p: abs(p[1]), reverse=True)
        return pairs


def fit_model(X: np.ndarray, y: np.ndarray, kind: str = "logreg") -> DirectionModel:
    return DirectionModel(kind=kind).fit(X, y)
