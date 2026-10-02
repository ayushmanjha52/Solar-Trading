import dataclasses

import pytest

from market.flows import Trade
from sim import crypto
from sim.engine import OrderRejected, Simulation

CHAIN, CONTRACT = 31337, "0xe7f1725E7734CE288F8367e1Bb143E90bb3F0512"


@pytest.fixture(scope="module")
def sim():
    s = Simulation()
    s.reset("2012-11-12", 20)  # 09:30, mid-morning: trading is live
    for _ in range(6):
        s.tick()
    return s


# --- crypto ---------------------------------------------------------------------

def test_reading_signature_recovers_to_the_meter():
    m = crypto.Meter(7, seed=1, chain_id=CHAIN, verifying_contract=CONTRACT)
    r = m.sign(1_352_678_400, import_wh=0, export_wh=412)
    assert crypto.recover_signer(r, CHAIN, CONTRACT) == m.address


def test_altered_reading_no_longer_recovers_to_the_meter():
    m = crypto.Meter(7, seed=1, chain_id=CHAIN, verifying_contract=CONTRACT)
    r = m.sign(1_352_678_400, import_wh=0, export_wh=412)
    forged = dataclasses.replace(r, export_wh=900)
    assert crypto.recover_signer(forged, CHAIN, CONTRACT) != m.address


def test_signature_is_bound_to_chain_and_contract():
    m = crypto.Meter(7, seed=1, chain_id=CHAIN, verifying_contract=CONTRACT)
    r = m.sign(1_352_678_400, 0, 412)
    assert crypto.recover_signer(r, 137, CONTRACT) != m.address
    assert crypto.recover_signer(r, CHAIN, "0x" + "11" * 20) != m.address


def test_commitment_changes_with_any_trade_field():
    t = [Trade(1, 2, 500, 498, 0.004, 120.0)]
    base = crypto.commitment(1_352_678_400, 550, t)
    assert crypto.commitment(1_352_678_400, 551, t) != base
    assert crypto.commitment(1_352_678_400, 550, [Trade(1, 2, 500, 499, 0.002, 120.0)]) != base
    assert crypto.commitment(1_352_678_400, 550, [Trade(1, 3, 500, 498, 0.004, 120.0)]) != base
    # Loss fraction and path length are derived, not settled, so they are not committed.
    assert crypto.commitment(1_352_678_400, 550, [Trade(1, 2, 500, 498, 0.9, 1.0)]) == base


# --- engine ---------------------------------------------------------------------

def test_reset_replays_the_day_from_midnight(sim):
    day_start = sim.g - sim.g % 48
    assert all(g in sim.records for g in range(day_start, sim.g + 1))
    assert sim.data.slot_of(sim.g) == 26  # started at 20, ticked 6 times


def test_every_settled_slot_verifies(sim):
    settled = [r for r in sim.records.values() if r.settlement is not None]
    assert len(settled) == 25
    assert all(r.verification["verified"] for r in settled)


def test_morning_market_actually_trades(sim):
    assert sum(len(r.allocation.trades) for r in sim.records.values()) > 0


def test_restated_trades_fail_verification(sim):
    rec = next(r for r in sim.records.values() if r.settlement is not None and r.allocation.trades)
    honest = rec.allocation
    t0 = honest.trades[0]
    restated = dataclasses.replace(honest, trades=[dataclasses.replace(t0, delivered_wh=t0.delivered_wh + 100)]
                                   + honest.trades[1:])
    rec.allocation = restated
    try:
        v = sim.verify(rec)
        assert not v["commitment_matches"] and not v["verified"]
    finally:
        rec.allocation = honest
    assert sim.verify(rec)["verified"]


def test_reading_signed_by_the_wrong_key_fails_verification(sim):
    rec = next(r for r in sim.records.values() if r.settlement is not None)
    honest = rec.readings[3]
    impostor = sim.meters[4].sign(honest.slot_start, honest.import_wh, honest.export_wh)
    rec.readings[3] = dataclasses.replace(impostor, meter_id=3)
    try:
        v = sim.verify(rec)
        assert v["bad_signers"] == [3] and not v["verified"]
    finally:
        rec.readings[3] = honest


def test_money_is_conserved_every_slot(sim):
    for rec in sim.records.values():
        if rec.settlement is not None:
            s = rec.settlement
            assert sum(h.market_mp for h in s.households.values()) + s.operator_mp == 0


def test_cleared_prices_sit_strictly_inside_the_band(sim):
    for rec in sim.records.values():
        if rec.clearing.price is not None:
            assert sim.tariff.feed_in < rec.clearing.price < sim.tariff.retail - sim.tariff.wheeling


# --- visitor orders -------------------------------------------------------------

def test_visitor_order_replaces_the_agent_and_settles():
    s = Simulation()
    s.reset("2012-11-12", 22)
    g = s.g + 1
    u = s.place_order(5, g, "buy", 1500, 800)
    book = s.books[g]
    assert u.order in book
    assert not any(o.household == 5 and o.order_id.endswith("-agent") for o in book)
    s.tick()
    assert u.status == "cleared"
    s.tick()
    assert u.status == "settled"
    assert s.records[g].verification["verified"]


def test_order_outside_the_band_is_rejected_with_interface_copy():
    s = Simulation()
    with pytest.raises(OrderRejected, match=r"between ₹3.00 and ₹8.50 per kWh. Outside that range the grid"):
        s.place_order(5, s.g + 1, "sell", 1000, 900)


def test_closed_gate_and_horizon_are_enforced():
    s = Simulation()
    with pytest.raises(OrderRejected, match="gate has closed"):
        s.place_order(5, s.g, "buy", 1000, 600)
    with pytest.raises(OrderRejected, match="one day ahead"):
        s.place_order(5, s.g + 49, "buy", 1000, 600)


def test_a_household_cannot_buy_and_sell_in_one_slot():
    s = Simulation()
    g = s.g + 2
    s.place_order(5, g, "buy", 1000, 600)
    with pytest.raises(OrderRejected, match="already buying"):
        s.place_order(5, g, "sell", 1000, 600)
