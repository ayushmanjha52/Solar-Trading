"""Backtest harness: the live market's code path without the cryptography.

Same feeder, same data, same auction, flows, losses and two-pass settlement as
sim/engine.py. Meter signing and chain calls are skipped: they prove the
outcome, they do not change it, and skipping them makes a six-month run take
seconds instead of minutes.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field

import numpy as np

from market import flows
from market.double_auction import clear
from market.orders import CONFIG_PATH, Order, Tariff
from market.settlement import Reading, settle
from sim import agents, strategies
from sim import data as sim_data
from sim import feeder as sim_feeder
from sim import forecasts as sim_forecasts
from sim.config import DEFAULT

SLOTS = sim_data.SLOTS
_CACHE: dict = {}


def world():
    """Feeder, data and forecasts, loaded once per process."""
    if not _CACHE:
        model = sim_feeder.build(DEFAULT)
        data = sim_data.load(DEFAULT, model)
        _CACHE.update(model=model, data=data, forecasts=sim_forecasts.load(model, data))
    return _CACHE["model"], _CACHE["data"], _CACHE["forecasts"]


@dataclass(frozen=True)
class Scenario:
    name: str
    volume: str = "newsvendor"  # seasonal_naive | p50 | newsvendor | perfect
    price: str = "truthful"  # truthful | shaded | random
    shade: float = 0.3
    wheeling: int = 0  # paise per kWh
    seed: int = 0
    first_day: str = "2012-10-01"
    last_day: str = "2013-03-31"
    deviant: int | None = None  # one household that departs from the others' price rule
    deviant_price: str = "shaded"
    deviant_shade: float = 0.3


@dataclass
class Result:
    scenario: Scenario
    slots: int = 0
    cleared_slots: int = 0
    injected_wh: int = 0
    delivered_wh: int = 0
    # Over-commitment: sold more than was exported, or bought more than was used. This is
    # where forecast error costs money (settled at retail, or sold back at feed-in). Energy
    # beyond an unfilled order is not counted: buying the rest from the grid costs nothing extra.
    overcommit_wh: int = 0
    prices: list = field(default_factory=list)
    market_mp: dict = field(default_factory=dict)
    imbalance_mp: dict = field(default_factory=dict)
    grid_only_mp: dict = field(default_factory=dict)
    operator_mp: int = 0
    price_x_volume: int = 0

    def saving_mp(self, h: int | None = None) -> int:
        hs = [h] if h is not None else list(self.market_mp)
        return sum(self.market_mp[k] + self.imbalance_mp[k] - self.grid_only_mp[k] for k in hs)

    def summary(self) -> dict:
        days = self.slots / SLOTS
        return {
            "scenario": self.scenario.name, "volume": self.scenario.volume, "price": self.scenario.price,
            "wheeling_paise": self.scenario.wheeling, "seed": self.scenario.seed, "days": days,
            "cleared_share": self.cleared_slots / max(self.slots, 1),
            "traded_kwh": self.injected_wh / 1000,
            "loss_share": 1 - self.delivered_wh / self.injected_wh if self.injected_wh else 0.0,
            "mean_price_inr": self.price_x_volume / self.injected_wh / 100 if self.injected_wh else None,
            "price_sd_inr": float(np.std(self.prices)) / 100 if self.prices else None,
            "overcommit_kwh": self.overcommit_wh / 1000,
            "saving_inr": self.saving_mp() / 100_000,
            "saving_inr_per_household_year": self.saving_mp() / 100_000 / len(self.market_mp) * 365 / days,
            "grid_only_bill_inr": -sum(self.grid_only_mp.values()) / 100_000,
            "operator_inr": self.operator_mp / 100_000,
        }


def run(sc: Scenario) -> Result:
    model, data, forecasts = world()
    cfg = json_cfg()
    tariff = Tariff(cfg["feed_in_tariff_paise_per_kwh"], cfg["retail_tariff_paise_per_kwh"], sc.wheeling)
    g0, g1 = data.g_of(sc.first_day, 1), data.g_of(sc.last_day, SLOTS)
    hs = [h.id for h in model.households]
    res = Result(sc, market_mp={h: 0 for h in hs}, imbalance_mp={h: 0 for h in hs}, grid_only_mp={h: 0 for h in hs})
    seq = itertools.count()
    recent: list[int] = []
    for g in range(g0, g1 + 1):
        p_hat = float(np.mean(recent[-SLOTS:])) if recent else (tariff.floor + tariff.ceiling) / 2
        orders: list[Order] = []
        for h in hs:
            pos = (data.net_wh(h, g) if sc.volume == "perfect"
                   else agents.position_wh(_vol_cfg(sc.volume), data, forecasts, tariff, h, g, p_hat))
            rule, shade = (sc.deviant_price, sc.deviant_shade) if h == sc.deviant else (sc.price, sc.shade)
            o = strategies.order_for(h, g, pos, rule, tariff, shade, sc.seed, next(seq), DEFAULT.min_order_wh)
            if o is not None:
                orders.append(o)
        c = clear(orders, tariff)
        alloc = flows.allocate(c, orders, model.feeder, cfg["loss_cap_fraction"])
        readings = {}
        for h in hs:
            net = data.net_wh(h, g)
            readings[h] = Reading(max(-net, 0), max(net, 0))
        st = settle(alloc.trades, c.price, tariff, readings)
        res.slots += 1
        if c.price is not None and alloc.trades:
            res.cleared_slots += 1
            recent.append(c.price)
            res.prices.append(c.price)
            res.price_x_volume += c.price * alloc.injected_wh
        res.injected_wh += alloc.injected_wh
        res.delivered_wh += alloc.delivered_wh
        res.operator_mp += st.operator_mp
        for h, s in st.households.items():
            res.market_mp[h] += s.market_mp
            res.imbalance_mp[h] += s.imbalance_mp
            res.grid_only_mp[h] += s.grid_only_mp
            nc = s.contracted_export_wh - s.contracted_import_wh
            nm = s.metered_export_wh - s.metered_import_wh
            if nc > 0:
                res.overcommit_wh += max(0, nc - nm)
            elif nc < 0:
                res.overcommit_wh += max(0, nm - nc)
    return res


_VOL_CFGS: dict = {}


def _vol_cfg(volume: str):
    import dataclasses

    if volume not in _VOL_CFGS:
        _VOL_CFGS[volume] = dataclasses.replace(DEFAULT, volume_rule=volume)
    return _VOL_CFGS[volume]


_JSON: dict = {}


def json_cfg() -> dict:
    import json

    if not _JSON:
        _JSON.update(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
    return _JSON
