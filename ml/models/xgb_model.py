"""Gradient-boosted trees on the tabular features.

Point model: squared error, early-stopped on the validation window.

Quantile model: point forecast plus calibrated residual quantiles.
  1. the point model p(x) is fitted on one half of the training sample;
  2. a scale model s(x) is fitted on the other half, to predict |y - p(x)|, so
     it learns where errors are large (cloudy middays) and small (nights);
  3. on the validation window, z_k is the empirical k-quantile of
     (y - p(x)) / s(x), for k in P10, P50, P90;
  4. the forecast quantiles are p(x) + z_k * s(x).
This is split-conformal calibration with a learned, heteroscedastic scale. The
quantiles cannot cross (z is monotone, s > 0), and coverage is calibrated on
data the models never trained on.

Why not XGBoost's native `reg:quantileerror`: pinball gradients are a constant
plus-or-minus alpha, so on targets measured in hundreds of Wh the model creeps
towards the answer and never early-stops; on this machine it ran for over
twenty minutes on 600,000 rows without converging. The LSTM in lstm_model.py
is the model trained directly on the pinball loss.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import xgboost as xgb

from ml.models.baselines import QUANTILES

PARAMS = {
    "tree_method": "hist",
    "max_depth": 8,
    "eta": 0.05,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "min_child_weight": 20,
    "seed": 0,
    "nthread": 0,
    "objective": "reg:squarederror",
    "eval_metric": "rmse",
}
SCALE_FLOOR_WH = 5.0


def _dm(X: pd.DataFrame, y: np.ndarray | None = None) -> xgb.DMatrix:
    return xgb.DMatrix(X, label=y, missing=np.nan)


def fit_point(Xtr, ytr, Xva, yva, rounds: int = 3000) -> xgb.Booster:
    return xgb.train(PARAMS, _dm(Xtr, ytr), rounds, evals=[(_dm(Xva, yva), "val")],
                     early_stopping_rounds=60, verbose_eval=False)


def predict(booster: xgb.Booster, X: pd.DataFrame) -> np.ndarray:
    return booster.predict(_dm(X), iteration_range=(0, booster.best_iteration + 1))


@dataclass
class QuantileModel:
    point: xgb.Booster
    scale: xgb.Booster
    z: np.ndarray  # calibrated multipliers for P10, P50, P90

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        p = predict(self.point, X)
        s = np.maximum(predict(self.scale, X), SCALE_FLOOR_WH)
        return p[:, None] + self.z[None, :] * s[:, None]


def fit_quantile(Xtr, ytr, Xva, yva, seed: int = 0) -> QuantileModel:
    rng = np.random.default_rng(seed)
    half = rng.permutation(len(ytr))
    a, b = half[: len(ytr) // 2], half[len(ytr) // 2:]
    # Early stopping for both models uses the first half of validation; calibration uses the second.
    vh = rng.permutation(len(yva))
    va, vb = vh[: len(yva) // 2], vh[len(yva) // 2:]
    point = fit_point(Xtr.iloc[a], ytr[a], Xva.iloc[va], yva[va])
    resid_b = np.abs(ytr[b] - predict(point, Xtr.iloc[b]))
    resid_va = np.abs(yva[va] - predict(point, Xva.iloc[va]))
    scale = fit_point(Xtr.iloc[b], resid_b, Xva.iloc[va], resid_va)
    p_vb = predict(point, Xva.iloc[vb])
    s_vb = np.maximum(predict(scale, Xva.iloc[vb]), SCALE_FLOOR_WH)
    z = np.quantile((yva[vb] - p_vb) / s_vb, QUANTILES)
    return QuantileModel(point, scale, np.sort(z))
