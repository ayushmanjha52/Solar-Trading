"""Turn cleared volume into seller -> buyer flows on the feeder.

The auction decides how much each household buys or sells, and at what price.
It does not say who supplies whom, but losses depend on exactly that. Flows are
allocated nearest-first: the pair with the lowest path resistance trades first.
That is a greedy heuristic, not the loss-minimising transport solution, and is
documented as such.

A pair whose loss fraction would exceed the cap trades only as much as stays
under it. Volume that cannot be placed under the cap is reported as curtailed:
the seller keeps it (and exports to the grid), the buyer imports it from the
grid.
"""

from __future__ import annotations

from dataclasses import dataclass

from market.double_auction import Clearing
from market.losses import Feeder
from market.orders import Order, Side


@dataclass(frozen=True)
class Trade:
    seller: int
    buyer: int
    injected_wh: int  # leaves the seller's meter
    delivered_wh: int  # arrives at the buyer's meter
    loss_fraction: float
    path_m: float

    @property
    def loss_wh(self) -> int:
        return self.injected_wh - self.delivered_wh


@dataclass(frozen=True)
class Allocation:
    trades: list[Trade]
    curtailed_sell_wh: dict[int, int]
    curtailed_buy_wh: dict[int, int]

    @property
    def injected_wh(self) -> int:
        return sum(t.injected_wh for t in self.trades)

    @property
    def delivered_wh(self) -> int:
        return sum(t.delivered_wh for t in self.trades)


def household_fills(clearing: Clearing, orders: list[Order]) -> tuple[dict[int, int], dict[int, int]]:
    sell: dict[int, int] = {}
    buy: dict[int, int] = {}
    for o in orders:
        q = clearing.fills.get(o.order_id, 0)
        if q:
            target = sell if o.side is Side.SELL else buy
            target[o.household] = target.get(o.household, 0) + q
    return sell, buy


def allocate(clearing: Clearing, orders: list[Order], feeder: Feeder, loss_cap: float) -> Allocation:
    sell, buy = household_fills(clearing, orders)
    rem_sell, rem_buy = dict(sell), dict(buy)
    pairs = sorted(
        ((feeder.path_ohm(s, b), s, b) for s in sell for b in buy if s != b),
        key=lambda x: x,
    )
    trades: list[Trade] = []
    for _, s, b in pairs:
        q = min(rem_sell[s], rem_buy[b])
        if q <= 0:
            continue
        q = int(min(q, feeder.max_energy_wh(s, b, loss_cap)))
        if q <= 0:
            continue
        f = feeder.loss_fraction(s, b, q)
        loss = round(q * f)
        trades.append(Trade(s, b, q, q - loss, f, feeder.path_m(s, b)))
        rem_sell[s] -= q
        rem_buy[b] -= q
    return Allocation(
        trades=trades,
        curtailed_sell_wh={h: q for h, q in rem_sell.items() if q > 0},
        curtailed_buy_wh={h: q for h, q in rem_buy.items() if q > 0},
    )
