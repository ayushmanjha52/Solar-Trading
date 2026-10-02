"""Uniform-price double auction for one half-hour settlement period.

Bids are walked from the highest price down, asks from the lowest up, matching
quantity while the bid still meets the ask. Everyone who trades pays or
receives one price: the midpoint of the last matched bid and ask. Because that
midpoint lies between two prices that are both inside the band, the cleared
price is inside the band by construction. It is checked again anyway.

The band is enforced here, in the web API route, and in the settlement
contract. Three checks for one rule is deliberate: each layer can be called
without the others.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from market.orders import Order, Side, Tariff


@dataclass(frozen=True)
class Clearing:
    price: int | None  # paise per kWh; None when the book does not cross
    volume_wh: int
    fills: dict[str, int] = field(default_factory=dict)  # order_id -> Wh filled
    marginal_bid: int | None = None
    marginal_ask: int | None = None

    @property
    def crossed(self) -> bool:
        return self.price is not None


def clear(orders: list[Order], tariff: Tariff) -> Clearing:
    for o in orders:
        tariff.check(o.price)
    ids = [o.order_id for o in orders]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate order ids in book")

    bids = sorted((o for o in orders if o.side is Side.BUY), key=lambda o: (-o.price, o.seq))
    asks = sorted((o for o in orders if o.side is Side.SELL), key=lambda o: (o.price, o.seq))

    fills: dict[str, int] = {}
    i = j = 0
    rem_bid = bids[0].qty_wh if bids else 0
    rem_ask = asks[0].qty_wh if asks else 0
    last_bid = last_ask = None
    volume = 0
    while i < len(bids) and j < len(asks) and bids[i].price >= asks[j].price:
        q = min(rem_bid, rem_ask)
        fills[bids[i].order_id] = fills.get(bids[i].order_id, 0) + q
        fills[asks[j].order_id] = fills.get(asks[j].order_id, 0) + q
        volume += q
        last_bid, last_ask = bids[i].price, asks[j].price
        rem_bid -= q
        rem_ask -= q
        if rem_bid == 0:
            i += 1
            rem_bid = bids[i].qty_wh if i < len(bids) else 0
        if rem_ask == 0:
            j += 1
            rem_ask = asks[j].qty_wh if j < len(asks) else 0

    if volume == 0:
        return Clearing(price=None, volume_wh=0)
    price = (last_bid + last_ask) // 2
    tariff.check(price)
    return Clearing(price=price, volume_wh=volume, fills=fills, marginal_bid=last_bid, marginal_ask=last_ask)


def book_curves(orders: list[Order]) -> dict[str, list[tuple[int, int]]]:
    """Cumulative supply and demand as (price, Wh) steps, for depth charts."""
    curves: dict[str, list[tuple[int, int]]] = {"supply": [], "demand": []}
    total = 0
    for o in sorted((o for o in orders if o.side is Side.SELL), key=lambda o: (o.price, o.seq)):
        total += o.qty_wh
        curves["supply"].append((o.price, total))
    total = 0
    for o in sorted((o for o in orders if o.side is Side.BUY), key=lambda o: (-o.price, o.seq)):
        total += o.qty_wh
        curves["demand"].append((o.price, total))
    return curves
