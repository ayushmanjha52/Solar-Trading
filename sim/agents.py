"""Household bidding agents for the live market.

Volume: the newsvendor quantile of the household's out-of-sample P10/P50/P90
forecast (see sim/strategies.py), at the level set by the price the agent
expects, which is the mean cleared price of the last day. Where no forecast
exists the agent falls back to the seasonal-naive rule (same slot yesterday).

Price: a seeded random shade from the household's reservation price, so the
live order book has some texture. The study (sim/study.py) compares this with
truthful and shaded pricing.
"""

from __future__ import annotations

from market.orders import Order, Tariff
from sim import strategies
from sim.config import SimConfig
from sim.data import SLOTS, EnergyData


def forecast_net_wh(data: EnergyData, h: int, g: int) -> int:
    """Seasonal naive: the same slot yesterday."""
    return data.net_wh(h, g - SLOTS)


def position_wh(cfg: SimConfig, data: EnergyData, forecasts, tariff: Tariff, h: int, g: int,
                expected_price: float) -> float:
    if forecasts is not None and cfg.volume_rule != "seasonal_naive":
        q3 = forecasts.get(h, g)
        if q3 is not None:
            if cfg.volume_rule == "p50":
                return float(q3[1])
            return strategies.newsvendor_position(q3, expected_price, tariff)
    return float(forecast_net_wh(data, h, g))


def agent_orders(cfg: SimConfig, data: EnergyData, tariff: Tariff, households: list[int], g: int,
                 next_seq, forecasts=None, expected_price: float | None = None) -> list[Order]:
    p_hat = expected_price if expected_price is not None else (tariff.floor + tariff.ceiling) / 2
    orders = []
    for h in households:
        pos = position_wh(cfg, data, forecasts, tariff, h, g, p_hat)
        o = strategies.order_for(h, g, pos, cfg.price_rule, tariff, cfg.price_spread, cfg.seed, 0, cfg.min_order_wh)
        if o is not None:
            orders.append(Order(o.order_id, o.household, o.side, o.qty_wh, o.price, next_seq()))
    return orders
