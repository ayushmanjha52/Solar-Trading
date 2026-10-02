"""Bidding strategies: how much to offer or bid, and at what price.

Volume rules decide a household's contracted net position for a slot
(positive = sell that much, negative = buy that much):

  seasonal_naive  yesterday's same-slot net energy (the pre-Milestone-2 agent)
  p50             the median of the quantile forecast
  newsvendor      the optimal quantile of the forecast, given the price expected
  perfect         the actual metered net energy: an ORACLE upper bound, never deployable

The newsvendor rule. Contract a net position C against an uncertain net energy
X. Pass 2 settles any shortfall at retail R and any excess at feed-in F, and the
contract earns p (sellers) or costs p + w (buyers). Maximising expected
payoff gives P(X < C) = (p - F) / (R - F) for a seller and
P(X < C) = (p + w - F) / (R - F) for a buyer: the optimal contract is a
quantile of the forecast, at a level set by where the price sits in the band.
With the price mid-band that level is about 0.5, so over- and under-committing
cost about the same; the asymmetry the forecast must price appears only when
the expected price moves toward one edge of the band.

Price rules decide the limit price:

  truthful   the household's reservation price: a seller accepts anything above
             feed-in, a buyer anything below retail minus wheeling. In a
             uniform-price auction this is also the price-taker's order.
  shaded     sellers ask, and buyers bid, a fixed share of the band away from
             their reservation price, hoping to move the clearing price.
  random     a seeded random shade (the live demo's default, for variety).
"""

from __future__ import annotations

import random

import numpy as np

from market.orders import Order, Side, Tariff

LEVELS = np.array([0.1, 0.5, 0.9])


def quantile_at(q3: np.ndarray, level: float) -> float:
    """Interpolate a P10/P50/P90 forecast at any level, clamped to the outer quantiles."""
    return float(np.interp(np.clip(level, 0.1, 0.9), LEVELS, q3))


def newsvendor_position(q3: np.ndarray, expected_price: float, tariff: Tariff) -> float:
    span = tariff.retail - tariff.feed_in
    sell_level = (expected_price - tariff.feed_in) / span
    buy_level = (expected_price + tariff.wheeling - tariff.feed_in) / span
    as_seller = quantile_at(q3, sell_level)
    if as_seller > 0:
        return as_seller
    as_buyer = quantile_at(q3, buy_level)
    return as_buyer if as_buyer < 0 else 0.0


def limit_price(rule: str, side: Side, tariff: Tariff, shade: float, rng_key: str) -> int:
    span = tariff.ceiling - tariff.floor
    if rule == "truthful":
        s = 0.0
    elif rule == "shaded":
        s = shade
    elif rule == "random":
        s = random.Random(rng_key).random() * shade
    else:
        raise ValueError(f"unknown price rule {rule}")
    off = round(s * span)
    return tariff.floor + off if side is Side.SELL else tariff.ceiling - off


def order_for(household: int, g: int, position_wh: float, price_rule: str, tariff: Tariff, shade: float,
              seed: int, seq: int, min_wh: int, tag: str = "agent") -> Order | None:
    q = int(round(abs(position_wh)))
    if q < min_wh:
        return None
    side = Side.SELL if position_wh > 0 else Side.BUY
    price = limit_price(price_rule, side, tariff, shade, f"price:{seed}:{g}:{household}")
    return Order(f"g{g}-h{household}-{tag}", household, side, q, price, seq)
