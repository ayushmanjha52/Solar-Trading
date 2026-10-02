import random

import pytest

from market.double_auction import book_curves, clear
from market.orders import BandViolation, Order, Side, Tariff

T = Tariff(feed_in=300, retail=850)


def bid(i, price, qty, h=None):
    return Order(f"b{i}", h if h is not None else 100 + i, Side.BUY, qty, price, i)


def ask(i, price, qty, h=None):
    return Order(f"a{i}", h if h is not None else 200 + i, Side.SELL, qty, price, i)


# --- the band ---------------------------------------------------------------

@pytest.mark.parametrize("price", [300, 850, 299, 851, 0, 10_000])
def test_orders_on_or_outside_the_band_are_rejected(price):
    with pytest.raises(BandViolation, match="between ₹3.00 and ₹8.50"):
        clear([bid(1, price, 100)], T)


def test_band_edges_inside_are_accepted():
    c = clear([bid(1, 849, 100), ask(1, 301, 100)], T)
    assert c.price == (849 + 301) // 2


def test_wheeling_narrows_the_band_from_the_top():
    t = Tariff(feed_in=300, retail=850, wheeling=150)
    assert t.ceiling == 699
    with pytest.raises(BandViolation, match="between ₹3.00 and ₹7.00"):
        clear([bid(1, 750, 100)], t)


def test_wheeling_that_closes_the_band_is_refused():
    with pytest.raises(ValueError, match="closes the band"):
        Tariff(feed_in=300, retail=850, wheeling=550)


# --- clearing ---------------------------------------------------------------

def test_single_cross_clears_at_midpoint_for_the_smaller_side():
    c = clear([bid(1, 700, 500), ask(1, 400, 300)], T)
    assert (c.price, c.volume_wh) == (550, 300)
    assert c.fills == {"b1": 300, "a1": 300}


def test_book_that_does_not_cross_clears_nothing():
    c = clear([bid(1, 400, 500), ask(1, 700, 300)], T)
    assert not c.crossed and c.volume_wh == 0 and c.fills == {}


def test_empty_and_one_sided_books():
    assert clear([], T).volume_wh == 0
    assert clear([ask(1, 400, 100), ask(2, 500, 100)], T).volume_wh == 0


def test_time_priority_breaks_ties_at_the_same_price():
    c = clear([bid(1, 700, 100), ask(1, 400, 100, h=1), ask(2, 400, 100, h=2)], T)
    assert c.fills.get("a1") == 100 and "a2" not in c.fills


def test_marginal_order_is_partially_filled():
    c = clear([bid(1, 800, 250), ask(1, 400, 100), ask(2, 500, 100), ask(3, 600, 100)], T)
    assert c.fills == {"b1": 250, "a1": 100, "a2": 100, "a3": 50}
    assert c.price == (800 + 600) // 2


def test_duplicate_ids_rejected():
    with pytest.raises(ValueError, match="duplicate"):
        clear([bid(1, 700, 100), bid(1, 600, 100)], T)


def test_book_curves_are_cumulative():
    curves = book_curves([ask(1, 500, 100), ask(2, 400, 50), bid(1, 600, 70)])
    assert curves["supply"] == [(400, 50), (500, 150)]
    assert curves["demand"] == [(600, 70)]


# --- properties over random books -------------------------------------------

def random_book(rng: random.Random, tariff: Tariff) -> list[Order]:
    orders = []
    for i in range(rng.randint(0, 30)):
        side = rng.choice([Side.BUY, Side.SELL])
        price = rng.randint(tariff.floor, tariff.ceiling)
        orders.append(Order(f"o{i}", rng.randint(1, 24), side, rng.randint(1, 3000), price, i))
    return orders


@pytest.mark.parametrize("seed", range(500))
def test_clearing_invariants(seed):
    rng = random.Random(seed)
    tariff = Tariff(300, 850, rng.choice([0, 0, 50, 200]))
    orders = random_book(rng, tariff)
    c = clear(orders, tariff)
    by_id = {o.order_id: o for o in orders}

    buy = sum(q for oid, q in c.fills.items() if by_id[oid].side is Side.BUY)
    sell = sum(q for oid, q in c.fills.items() if by_id[oid].side is Side.SELL)
    assert buy == sell == c.volume_wh  # every Wh bought was sold

    if c.crossed:
        assert tariff.feed_in < c.price < tariff.retail - tariff.wheeling  # strictly inside the band
    for oid, q in c.fills.items():
        o = by_id[oid]
        assert 0 < q <= o.qty_wh
        # Individual rationality: nobody trades at a price worse than they asked for.
        assert (o.price >= c.price) if o.side is Side.BUY else (o.price <= c.price)

    # Efficiency: no unfilled bid and unfilled ask that would still trade with each other.
    open_bids = [o.price for o in orders if o.side is Side.BUY and c.fills.get(o.order_id, 0) < o.qty_wh]
    open_asks = [o.price for o in orders if o.side is Side.SELL and c.fills.get(o.order_id, 0) < o.qty_wh]
    if open_bids and open_asks:
        assert max(open_bids) < min(open_asks)
