"""Features for the forecast the market actually needs.

The task is set by the market's gate, not by convenience. Agents post orders
for slot t when slot t-1 begins; the last slot whose meter reading exists then
is t-2. So the forecast is two steps ahead of the last observation, and every
feature for target t uses data from slots <= t-2, or quantities known in
advance (calendar, solar geometry, PV capacity).

ERA5 weather at slot t is NOT a legal feature: it is reanalysis, the weather as
it actually was, which nobody bidding at t-1 could have known. It is built
only for the "oracle" row of the results table, to show how much such leakage
would flatter a model, and is never used by a deployable model.

`assert_causal` is the leakage check required by the brief, done as a
perturbation test rather than a correlation test: change every value the
forecaster is not allowed to see and confirm no feature moves. A correlation
test cannot do this job, because energy series are autocorrelated at every lag.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ml import config
from ml.data import solar

HORIZON = 2  # target slot minus last observed slot
SLOTS = 48
WEEK = 7 * SLOTS
SEQ_LEN = 96  # history window for the sequence model

FEATURES = [
    "net_l2", "net_l3", "net_l4", "net_l6", "gen_l2", "load_l2",
    "net_l48", "net_l96", "net_l336", "gen_l48", "load_l48", "load_l336",
    "net_mean6", "net_slot_mean7", "load_slot_mean7", "gen_slot_max7", "clear_l2",
    "sun_elev", "sun_elev_l2", "pv_kwp", "slot", "dow", "month",
]
ORACLE_FEATURES = FEATURES + ["ghi_t"]


def shift(x: np.ndarray, k: int) -> np.ndarray:
    """out[t] = x[t-k]; NaN where t-k is before the start."""
    out = np.full_like(x, np.nan, dtype=np.float64)
    out[k:] = x[:-k] if k else x
    return out


def rolling_mean_observed(x: np.ndarray, start_lag: int, window: int) -> np.ndarray:
    """Mean of x[t-start_lag-window+1 .. t-start_lag]."""
    s = shift(x, start_lag)
    c = np.concatenate([[0.0], np.nancumsum(np.nan_to_num(s))])
    n = np.concatenate([[0], np.cumsum(~np.isnan(s))])
    idx = np.arange(len(x))
    lo = np.maximum(idx - window + 1, 0)
    cnt = n[idx + 1] - n[lo]
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(cnt == window, (c[idx + 1] - c[lo]) / window, np.nan)


@dataclass(frozen=True)
class Series:
    """One household variant: gen is zero for a household simulated without PV."""
    load_wh: np.ndarray
    gen_wh: np.ndarray
    pv_kwp: float

    @property
    def net_wh(self) -> np.ndarray:
        return self.gen_wh - self.load_wh


def calendar(ts_utc: pd.DatetimeIndex) -> dict[str, np.ndarray]:
    local = ts_utc.tz_convert(config.LOCAL_TZ)
    return {
        "slot": ((local.hour * 60 + local.minute) // 30).to_numpy(np.float64),
        "dow": local.dayofweek.to_numpy(np.float64),
        "month": local.month.to_numpy(np.float64),
    }


def sun_elevation(ts_utc: pd.DatetimeIndex, lat: float, lon: float) -> np.ndarray:
    return solar.elevation_deg(ts_utc + config.PERIOD / 2, lat, lon)


def features(s: Series, cal: dict[str, np.ndarray], sun: np.ndarray, ghi: np.ndarray | None = None) -> dict:
    """All features for every target index t, as arrays aligned to t."""
    net, gen, load = s.net_wh.astype(np.float64), s.gen_wh.astype(np.float64), s.load_wh.astype(np.float64)
    f = {
        "net_l2": shift(net, 2), "net_l3": shift(net, 3), "net_l4": shift(net, 4), "net_l6": shift(net, 6),
        "gen_l2": shift(gen, 2), "load_l2": shift(load, 2),
        "net_l48": shift(net, 48), "net_l96": shift(net, 96), "net_l336": shift(net, 336),
        "gen_l48": shift(gen, 48), "load_l48": shift(load, 48), "load_l336": shift(load, 336),
        "net_mean6": rolling_mean_observed(net, 2, 6),
        "net_slot_mean7": np.mean([shift(net, SLOTS * k) for k in range(1, 8)], axis=0),
        "load_slot_mean7": np.mean([shift(load, SLOTS * k) for k in range(1, 8)], axis=0),
        "gen_slot_max7": np.max([shift(gen, SLOTS * k) for k in range(1, 8)], axis=0),
    }
    # Recent clearness: generation two slots ago relative to the best of the past week at that slot.
    env_l2 = np.max([shift(gen, 2 + SLOTS * k) for k in range(1, 8)], axis=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        f["clear_l2"] = np.where(env_l2 > 20, np.clip(f["gen_l2"] / env_l2, 0, 1.5), np.nan)
    f["sun_elev"] = sun
    f["sun_elev_l2"] = shift(sun, 2)
    f["pv_kwp"] = np.full(len(net), s.pv_kwp)
    f.update(cal)
    if ghi is not None:
        f["ghi_t"] = ghi  # ORACLE ONLY: the weather of the target slot itself
    return f


def assert_causal(s: Series, cal: dict, sun: np.ndarray, targets: np.ndarray, seed: int = 0) -> None:
    """Fail if any deployable feature for target t changes when data from slots > t-HORIZON changes."""
    rng = np.random.default_rng(seed)
    base = features(s, cal, sun)
    for t in targets:
        load, gen = s.load_wh.astype(np.float64).copy(), s.gen_wh.astype(np.float64).copy()
        cut = t - HORIZON + 1  # first slot the forecaster may not see
        load[cut:] = rng.uniform(0, 5000, len(load) - cut)
        gen[cut:] = rng.uniform(0, 5000, len(gen) - cut) * (s.pv_kwp > 0)
        moved = features(Series(load, gen, s.pv_kwp), cal, sun)
        for name in FEATURES:
            a, b = base[name][t], moved[name][t]
            if not (np.isnan(a) and np.isnan(b)) and a != b:
                raise AssertionError(f"feature {name} for target {t} depends on data after t-{HORIZON}: lookahead")


def sequences(s: Series, targets: np.ndarray) -> np.ndarray:
    """History windows for the sequence model: slots t-HORIZON-SEQ_LEN+1 .. t-HORIZON, channels net/gen/load in kWh."""
    stack = np.stack([s.net_wh, s.gen_wh, s.load_wh], axis=1).astype(np.float32) / 1000
    offsets = np.arange(-HORIZON - SEQ_LEN + 1, -HORIZON + 1)
    return stack[targets[:, None] + offsets[None, :]]
