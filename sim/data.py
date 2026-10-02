"""Half-hourly energy for the feeder's households, as integer Wh arrays.

Global slot index g counts half hours from 00:00 AEST on the day before the
simulated range (the extra day feeds the seasonal-naive forecast).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ml import config as ml_config
from sim.config import SimConfig
from sim.feeder import FeederModel

SLOTS = 48


@dataclass(frozen=True)
class EnergyData:
    origin: pd.Timestamp  # UTC start of g = 0
    load_wh: np.ndarray  # [household index, g]
    gen_wh: np.ndarray
    first_g: int  # first simulated slot (start of first_day)
    last_g: int  # last simulated slot, inclusive

    def ts(self, g: int) -> pd.Timestamp:
        return self.origin + pd.Timedelta(minutes=30 * g)

    def local_day(self, g: int) -> str:
        return (self.ts(g).tz_convert(ml_config.LOCAL_TZ)).strftime("%Y-%m-%d")

    def slot_of(self, g: int) -> int:
        """Settlement period 1..48 in AEST."""
        return g % SLOTS + 1

    def g_of(self, day: str, slot: int) -> int:
        start = pd.Timestamp(day, tz=ml_config.LOCAL_TZ).tz_convert("UTC")
        return int((start - self.origin) / pd.Timedelta(minutes=30)) + slot - 1

    def net_wh(self, h: int, g: int) -> int:
        """Generation minus load: positive exports, negative imports."""
        return int(self.gen_wh[h - 1, g] - self.load_wh[h - 1, g])


def load(cfg: SimConfig, model: FeederModel) -> EnergyData:
    origin = pd.Timestamp(cfg.first_day, tz=ml_config.LOCAL_TZ).tz_convert("UTC") - pd.Timedelta(days=1)
    end = pd.Timestamp(cfg.last_day, tz=ml_config.LOCAL_TZ).tz_convert("UTC") + pd.Timedelta(days=1)
    customers = [h.customer for h in model.households]
    panel = pd.read_parquet(
        ml_config.PANEL_PARQUET,
        columns=["customer", "ts_utc", "load_kwh", "gen_kwh"],
        filters=[("customer", "in", customers), ("ts_utc", ">=", origin), ("ts_utc", "<", end)],
    )
    n = int((end - origin) / pd.Timedelta(minutes=30))
    load_wh = np.zeros((len(customers), n), np.int64)
    gen_wh = np.zeros((len(customers), n), np.int64)
    for h in model.households:
        rows = panel[panel["customer"] == h.customer].sort_values("ts_utc")
        if len(rows) != n or rows[["load_kwh", "gen_kwh"]].isna().any().any():
            raise RuntimeError(f"customer {h.customer} has gaps in the simulated range")
        load_wh[h.id - 1] = np.rint(rows["load_kwh"].to_numpy() * 1000).astype(np.int64)
        if h.pv:
            gen_wh[h.id - 1] = np.rint(rows["gen_kwh"].to_numpy() * 1000).astype(np.int64)
    return EnergyData(origin=origin, load_wh=load_wh, gen_wh=gen_wh, first_g=SLOTS, last_g=n - 1)
