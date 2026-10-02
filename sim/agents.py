"""Household bidding agents.

Volume comes from a seasonal-naive forecast: a household expects this half
hour to look like the same half hour yesterday. That is the weakest honest
forecast, deliberately, until Milestone 2 earns a better one. Its errors are
what the imbalance pass prices.

Price is seeded random inside the band: sellers ask a little above the feed-in
tariff, buyers bid a little below the retail ceiling. This is a placeholder
for the strategies of Milestone 6 (truthful, shaded, forecast-driven,
price-taker), not a claim about how households behave.
"""

from __future__ import annotations

import random

from market.orders import Order, Side, Tariff
from sim.config import SimConfig
from sim.data import SLOTS, EnergyData


def forecast_net_wh(data: EnergyData, h: int, g: int) -> int:
    return data.net_wh(h, g - SLOTS)


def agent_orders(cfg: SimConfig, data: EnergyData, tariff: Tariff, households: list[int], g: int,
                 next_seq) -> list[Order]:
    orders = []
    span = tariff.ceiling - tariff.floor
    for h in households:
        f = forecast_net_wh(data, h, g)
        if abs(f) < cfg.min_order_wh:
            continue
        rng = random.Random(f"price:{cfg.seed}:{g}:{h}")
        shade = round(rng.random() * cfg.price_spread * span)
        if f > 0:
            orders.append(Order(f"g{g}-h{h}-agent", h, Side.SELL, f, tariff.floor + shade, next_seq()))
        else:
            orders.append(Order(f"g{g}-h{h}-agent", h, Side.BUY, -f, tariff.ceiling - shade, next_seq()))
    return orders
