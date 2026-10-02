"""Baselines. They ship first and every learned model is reported against them.

persistence      the last observed slot (t-2)
seasonal naive   the same slot yesterday (t-48); what the market agents used before Milestone 2
weekly naive     the same slot last week (t-336)
seasonal naive + residual quantiles
                 a probabilistic baseline: seasonal naive plus the training-set
                 quantiles of its own error, per slot and PV/no-PV. A quantile
                 model that cannot beat this has learned nothing about risk.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

QUANTILES = (0.1, 0.5, 0.9)
POINT = {"Persistence": "net_l2", "Seasonal naive": "net_l48", "Weekly naive": "net_l336"}


def point(X: pd.DataFrame, name: str) -> np.ndarray:
    return X[POINT[name]].to_numpy(np.float64)


class ResidualQuantiles:
    def fit(self, X: pd.DataFrame, y: np.ndarray) -> "ResidualQuantiles":
        resid = y - X["net_l48"].to_numpy()
        key = X["slot"].to_numpy().astype(int) * 2 + (X["pv_kwp"].to_numpy() > 0)
        df = pd.DataFrame({"key": key, "r": resid}).dropna()
        self.table = df.groupby("key")["r"].quantile(list(QUANTILES)).unstack()
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        key = X["slot"].to_numpy().astype(int) * 2 + (X["pv_kwp"].to_numpy() > 0)
        q = self.table.reindex(key).to_numpy()
        return X["net_l48"].to_numpy()[:, None] + q
