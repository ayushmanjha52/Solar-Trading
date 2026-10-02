"""Integration with a deployed chain. Skipped unless a local Anvil with the contracts is running
(python demo.py starts one, or: anvil + forge script script/Deploy.s.sol --rpc-url local --broadcast)."""

import dataclasses

import pytest

from market.settlement import Reading, settle
from sim.chain import ChainClient
from sim.engine import Simulation

client = ChainClient.connect_or_none()
pytestmark = pytest.mark.skipif(client is None, reason="no deployed local chain")


@pytest.fixture(scope="module")
def sim():
    s = Simulation(chain=client)
    s.reset("2012-11-12", 22)
    s.tick()
    return s


def test_every_slot_commits_and_settles_on_chain(sim):
    settled = [r for r in sim.records.values() if r.settlement is not None]
    assert settled
    for r in settled:
        assert r.chain["commit"]["status"] == "confirmed"
        assert r.chain["settle"]["status"] == "confirmed", r.chain["settle"]


def test_contract_settlement_equals_the_engine(sim):
    for r in sim.records.values():
        if r.settlement is not None:
            assert r.chain["settle"]["matches_engine"] is True
            assert r.chain["settle"]["households_settled"] == 24


def test_contract_refuses_restated_trades(sim):
    # Commit the honest trades for the slot in delivery, then try to settle a restated version.
    rec = sim.records[sim.g]
    assert rec.chain["commit"]["status"] == "confirmed"
    if not rec.allocation.trades:
        pytest.skip("slot in delivery has no trades")
    t0 = rec.allocation.trades[0]
    forged = dataclasses.replace(rec.allocation, trades=[dataclasses.replace(t0, delivered_wh=t0.delivered_wh - 1)]
                                 + rec.allocation.trades[1:])
    honest = rec.allocation
    # Validly signed readings, so the only thing wrong is the restated trade.
    rec.readings = {h.id: sim.meters[h.id].sign(sim.slot_start(sim.g), 0, 0) for h in sim.model.households}
    rec.allocation = forged
    rec.settlement = settle(forged.trades, rec.clearing.price, sim.tariff, {h: Reading(0, 0) for h in rec.readings})
    try:
        res = client.settle(rec, sim)
        assert res["status"] == "failed"
        assert res["error"] == "reverted: CommitmentMismatch"
    finally:
        rec.allocation, rec.readings, rec.settlement = honest, None, None
