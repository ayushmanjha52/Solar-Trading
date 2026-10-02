"""Out-of-sample quantile forecasts for the feeder, aligned to the simulation's slot index.

Produced by `python -m ml.evaluate` for the test window, which covers the
whole simulated range, so no agent ever sees a forecast fitted on its own
future. If the file is missing, agents fall back to the seasonal-naive rule.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from ml import config as ml_config
from sim.data import EnergyData
from sim.feeder import FeederModel

PATH = ml_config.DATA_PROCESSED / "forecasts_feeder.parquet"


class Forecasts:
    def __init__(self, q: np.ndarray, model: str):
        self.q = q  # [household index, g, 3] in Wh; NaN where unavailable
        self.model = model

    def get(self, h: int, g: int) -> np.ndarray | None:
        row = self.q[h - 1, g]
        return None if np.isnan(row).any() else row


def load(model: FeederModel, data: EnergyData) -> Forecasts | None:
    if not PATH.exists():
        return None
    df = pd.read_parquet(PATH)
    meta = json.loads((ml_config.DATA_PROCESSED / "forecasts_feeder.json").read_text(encoding="utf-8"))
    n = data.load_wh.shape[1]
    q = np.full((len(model.households), n, 3), np.nan, np.float32)
    g_all = ((pd.DatetimeIndex(df["ts_utc"]) - data.origin) / pd.Timedelta(minutes=30)).to_numpy().astype(int)
    keep = (g_all >= 0) & (g_all < n)
    for h in model.households:
        m = keep & (df["customer"].to_numpy() == h.customer) & (df["pv"].to_numpy() == h.pv)
        q[h.id - 1, g_all[m]] = df.loc[m, ["p10_wh", "p50_wh", "p90_wh"]].to_numpy()
    return Forecasts(q, meta["model"])
