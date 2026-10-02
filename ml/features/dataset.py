"""Assemble forecasting datasets with chronological splits.

Splits are by the target slot's AEST date, never random:
  train  2010-07-08 .. 2012-06-30   (first week dropped: the weekly lag needs it)
  val    2012-07-01 .. 2012-09-30   model selection and early stopping only
  test   2012-10-01 .. 2013-06-30   touched once, for the results table

The test window contains the market simulation's range (Oct 2012 - Mar 2013),
so every forecast the market agents use is out of sample.

Households. The pool is the 24 feeder households plus 100 other clean Ausgrid
households (seeded sample). Each is used in two variants: with its real PV,
and with generation removed, because the simulated feeder has households of
both kinds.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

import numpy as np
import pandas as pd

from ml import config
from ml.data import preprocess
from ml.data.weather import cell_of
from ml.features import build_features as bf

SPLITS = {
    "train": ("2010-07-08", "2012-06-30"),
    "val": ("2012-07-01", "2012-09-30"),
    "test": ("2012-10-01", "2013-06-30"),
}
EXTRA_HOUSEHOLDS = 100
SEED = 20121112


@dataclass(frozen=True)
class Variant:
    customer: int
    pv: bool


@dataclass
class Panel:
    ts: pd.DatetimeIndex
    customers: pd.DataFrame  # indexed by customer
    load: dict[int, np.ndarray]
    gen: dict[int, np.ndarray]
    cal: dict[str, np.ndarray]
    sun: dict[int, np.ndarray]
    ghi: dict[int, np.ndarray]

    def series(self, v: Variant) -> bf.Series:
        gen = self.gen[v.customer] if v.pv else np.zeros_like(self.gen[v.customer])
        kwp = float(self.customers.at[v.customer, "capacity_kwp"]) if v.pv else 0.0
        return bf.Series(self.load[v.customer], gen, kwp)

    def split(self, name: str) -> np.ndarray:
        lo, hi = SPLITS[name]
        day = self.ts.tz_convert(config.LOCAL_TZ).normalize().tz_localize(None)
        return np.nonzero((day >= pd.Timestamp(lo)) & (day <= pd.Timestamp(hi)))[0]


def feeder_variants() -> list[Variant]:
    from sim.config import DEFAULT
    from sim.feeder import build

    return [Variant(h.customer, h.pv) for h in build(DEFAULT).households]


def pool_customers() -> list[int]:
    c = pd.read_parquet(config.CUSTOMERS_PARQUET)
    clean = c[c["clean"] & (c["missing_periods"] == 0)]["customer"].tolist()
    feeder = {v.customer for v in feeder_variants()}
    others = sorted(set(clean) - feeder)
    extra = random.Random(SEED).sample(others, EXTRA_HOUSEHOLDS)
    return sorted(feeder | set(extra))


def load_panel(customers: list[int]) -> Panel:
    meta = pd.read_parquet(config.CUSTOMERS_PARQUET).set_index("customer").loc[customers]
    panel = pd.read_parquet(config.PANEL_PARQUET, columns=["customer", "load_kwh", "gen_kwh"],
                            filters=[("customer", "in", customers)])
    n = preprocess.N_PERIODS
    load, gen = {}, {}
    for cust, rows in panel.groupby("customer"):
        if len(rows) != n:
            raise RuntimeError(f"customer {cust}: expected {n} periods")
        load[cust] = np.rint(rows["load_kwh"].to_numpy() * 1000)
        gen[cust] = np.rint(rows["gen_kwh"].to_numpy() * 1000)
        if np.isnan(load[cust]).any() or np.isnan(gen[cust]).any():
            raise RuntimeError(f"customer {cust} has gaps; pool households must be complete")
    ts = preprocess.grid_index()
    sun_by_loc: dict[tuple, np.ndarray] = {}
    sun = {}
    for cust in customers:
        key = (meta.at[cust, "lat"], meta.at[cust, "lon"])
        if key not in sun_by_loc:
            sun_by_loc[key] = bf.sun_elevation(ts, *key)
        sun[cust] = sun_by_loc[key]
    weather = pd.read_parquet(config.WEATHER_PARQUET, columns=["cell", "ts_utc", "shortwave_radiation"])
    ghi_by_cell = {cell: w.sort_values("ts_utc")["shortwave_radiation"].to_numpy() for cell, w in weather.groupby("cell")}
    cells = cell_of(meta["lat"], meta["lon"])
    ghi = {cust: ghi_by_cell[cells.loc[cust]] for cust in customers}
    return Panel(ts, meta, load, gen, bf.calendar(ts), sun, ghi)


def frame(p: Panel, variants: list[Variant], idx: np.ndarray, oracle: bool = False):
    """Feature matrix, target and row metadata for the given variants at target indices idx."""
    cols = bf.ORACLE_FEATURES if oracle else bf.FEATURES
    Xs, ys, metas = [], [], []
    for v in variants:
        s = p.series(v)
        f = bf.features(s, p.cal, p.sun[v.customer], p.ghi[v.customer] if oracle else None)
        Xs.append(np.column_stack([f[c][idx] for c in cols]).astype(np.float32))
        ys.append(s.net_wh[idx].astype(np.float32))
        metas.append(pd.DataFrame({"customer": v.customer, "pv": v.pv, "t": idx}))
    X = pd.DataFrame(np.vstack(Xs), columns=cols)
    return X, np.concatenate(ys), pd.concat(metas, ignore_index=True)
