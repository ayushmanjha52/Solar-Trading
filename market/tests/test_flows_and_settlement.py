import random

import pytest

from market.double_auction import clear
from market.flows import Trade, allocate
from market.losses import Feeder
from market.orders import Order, Side, Tariff
from market.settlement import Reading, settle

T = Tariff(feed_in=300, retail=850)


def feeder(n=6, spacing=60.0, service=20.0):
    return Feeder(positions_m={h: h * spacing for h in range(1, n + 1)},
                  service_m={h: service for h in range(1, n + 1)})


# --- losses -------------------------------------------------------------------

def test_loss_grows_with_distance_and_power():
    f = feeder()
    assert f.loss_fraction(1, 2, 500) < f.loss_fraction(1, 6, 500)
    assert f.loss_fraction(1, 6, 500) < f.loss_fraction(1, 6, 1500)


def test_loss_is_symmetric_and_positive():
    f = feeder()
    assert f.loss_fraction(2, 5, 800) == pytest.approx(f.loss_fraction(5, 2, 800))
    assert f.loss_fraction(3, 3, 800) > 0  # services still carry the current


def test_loss_magnitude_is_lv_realistic():
    # 1 kW (500 Wh per half hour) over 300 m of backbone and two 20 m services:
    # hand calculation 2*(0.32*0.3 + 1.15*0.04) = 0.284 ohm; 1000*0.284/(230*0.95)^2 = 0.59 %.
    f = feeder(n=6, spacing=60.0)
    assert f.loss_fraction(1, 6, 500) == pytest.approx(0.00593, rel=0.01)


def test_max_energy_respects_cap():
    f = feeder()
    q = f.max_energy_wh(1, 6, 0.01)
    assert f.loss_fraction(1, 6, q) == pytest.approx(0.01)


# --- allocation ---------------------------------------------------------------

def test_nearest_pairs_trade_first():
    orders = [Order("s1", 1, Side.SELL, 500, 400, 0), Order("b2", 2, Side.BUY, 500, 700, 1),
              Order("b6", 6, Side.BUY, 500, 700, 2)]
    a = allocate(clear(orders, T), orders, feeder(), loss_cap=0.05)
    assert [(t.seller, t.buyer) for t in a.trades] == [(1, 2)]


def test_loss_cap_curtails_volume():
    orders = [Order("s1", 1, Side.SELL, 50_000, 400, 0), Order("b6", 6, Side.BUY, 50_000, 700, 1)]
    f = feeder()
    a = allocate(clear(orders, T), orders, f, loss_cap=0.02)
    assert len(a.trades) == 1
    assert a.trades[0].loss_fraction <= 0.02 + 1e-12
    assert a.curtailed_sell_wh[1] == a.curtailed_buy_wh[6] > 0


@pytest.mark.parametrize("seed", range(200))
def test_allocation_conserves_energy(seed):
    rng = random.Random(seed)
    orders = [Order(f"o{i}", rng.randint(1, 6), rng.choice([Side.BUY, Side.SELL]), rng.randint(1, 3000),
                    rng.randint(301, 849), i) for i in range(rng.randint(0, 20))]
    c = clear(orders, T)
    a = allocate(c, orders, feeder(), loss_cap=0.05)
    for t in a.trades:
        assert t.seller != t.buyer
        assert 0 <= t.loss_wh <= t.injected_wh * 0.05 + 1
        assert t.delivered_wh == t.injected_wh - t.loss_wh
    # Allocated plus curtailed never exceeds what the auction filled.
    assert a.injected_wh + sum(a.curtailed_sell_wh.values()) <= c.volume_wh


# --- settlement ---------------------------------------------------------------

def test_delivered_as_contracted_beats_grid_for_both_sides():
    trade = Trade(seller=1, buyer=2, injected_wh=1000, delivered_wh=990, loss_fraction=0.01, path_m=100)
    s = settle([trade], 550, T, {1: Reading(import_wh=0, export_wh=1000), 2: Reading(import_wh=990, export_wh=0)})
    seller, buyer = s.households[1], s.households[2]
    assert seller.market_mp == 550 * 1000 and seller.imbalance_mp == 0
    assert seller.saving_mp == (550 - 300) * 1000
    assert buyer.market_mp == -550 * 990 and buyer.imbalance_mp == 0
    assert buyer.saving_mp == (850 - 550) * 990
    assert s.loss_cost_mp == 550 * 10


def test_short_seller_buys_the_shortfall_at_retail():
    trade = Trade(1, 2, 1000, 990, 0.01, 100)
    s = settle([trade], 550, T, {1: Reading(0, 400), 2: Reading(990, 0)})
    seller = s.households[1]
    assert seller.deviation_wh == -600
    assert seller.imbalance_mp == -600 * 850
    # Over-committing loses money against simply exporting what you had.
    assert seller.saving_mp == 550 * 1000 - 600 * 850 - 400 * 300
    assert seller.saving_mp < 0


def test_long_seller_exports_the_excess_at_feed_in():
    s = settle([Trade(1, 2, 1000, 990, 0.01, 100)], 550, T, {1: Reading(0, 1500), 2: Reading(990, 0)})
    assert s.households[1].imbalance_mp == 500 * 300


def test_non_trader_pays_an_ordinary_bill():
    s = settle([], None, T, {7: Reading(import_wh=800, export_wh=0)})
    h = s.households[7]
    assert h.total_mp == h.grid_only_mp == -800 * 850 and h.saving_mp == 0


def test_missing_reading_for_a_trader_is_an_error():
    with pytest.raises(ValueError, match="no meter reading"):
        settle([Trade(1, 2, 1000, 990, 0.01, 100)], 550, T, {1: Reading(0, 1000)})


@pytest.mark.parametrize("seed", range(200))
def test_market_money_is_conserved(seed):
    rng = random.Random(seed)
    tariff = Tariff(300, 850, rng.choice([0, 40, 120]))
    trades = []
    for _ in range(rng.randint(1, 8)):
        s, b = rng.sample(range(1, 7), 2)
        inj = rng.randint(1, 2000)
        loss = rng.randint(0, inj // 50)
        trades.append(Trade(s, b, inj, inj - loss, loss / inj, 100))
    readings = {h: Reading(rng.randint(0, 2000), rng.randint(0, 2000)) for h in range(1, 7)}
    price = rng.randint(tariff.floor, tariff.ceiling)
    s = settle(trades, price, tariff, readings)
    # Buyers' payments = sellers' receipts + cost of losses - wheeling income. Exactly.
    assert sum(h.market_mp for h in s.households.values()) + s.operator_mp == 0
