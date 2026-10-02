import os

import pytest
from fastapi.testclient import TestClient

os.environ["LEM_CHAIN"] = "0"

from sim.api import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        c.post("/api/clock", json={"action": "pause"})
        yield c


def test_live_has_clock_day_and_current_slot(client):
    r = client.get("/api/live").json()
    assert {"clock", "day", "current", "book"} <= set(r)
    assert len(r["day"]["slots"]) == 48


def test_feeder_lists_households_with_meter_keys(client):
    f = client.get("/api/feeder").json()
    assert len(f["households"]) == 24
    assert all(h["meter_address"].startswith("0x") for h in f["households"])
    assert f["tariff"]["feed_in"] == 300 and f["tariff"]["retail"] == 850


def test_out_of_band_order_is_refused_with_reason(client):
    g = client.get("/api/live").json()["clock"]["g"] + 1
    r = client.post("/api/orders", json={"household": 3, "g": g, "side": "sell", "qty_wh": 500, "price": 250})
    assert r.status_code == 422
    assert "Outside that range the grid is the better deal" in r.json()["detail"]


def test_order_round_trip(client):
    g = client.get("/api/live").json()["clock"]["g"] + 1
    r = client.post("/api/orders", json={"household": 3, "g": g, "side": "buy", "qty_wh": 500, "price": 700})
    assert r.status_code == 201
    oid = r.json()["id"]
    assert any(o["id"] == oid for o in client.get("/api/orders").json())
    client.post("/api/clock", json={"action": "step"})
    client.post("/api/clock", json={"action": "step"})
    o = next(o for o in client.get("/api/orders").json() if o["id"] == oid)
    assert o["status"] == "settled" and "settlement" in o


def test_clock_is_open_without_an_admin_token(client, monkeypatch):
    monkeypatch.delenv("LEM_ADMIN_TOKEN", raising=False)
    assert client.get("/api/clock").json()["controls_locked"] is False
    assert client.post("/api/clock", json={"action": "pause"}).status_code == 200


def test_public_deployment_locks_the_shared_clock(client, monkeypatch):
    monkeypatch.setenv("LEM_ADMIN_TOKEN", "s3cret")
    assert client.get("/api/clock").json()["controls_locked"] is True
    r = client.post("/api/clock", json={"action": "jump", "day": "2012-12-01"})
    assert r.status_code == 403 and "operator" in r.json()["detail"]
    assert client.post("/api/clock", json={"action": "pause"}, headers={"X-Admin-Token": "wrong"}).status_code == 403
    assert client.post("/api/clock", json={"action": "pause"}, headers={"X-Admin-Token": "s3cret"}).status_code == 200
    # Visitors can still trade.
    g = client.get("/api/live").json()["clock"]["g"] + 1
    r = client.post("/api/orders", json={"household": 9, "g": g, "side": "buy", "qty_wh": 300, "price": 700})
    assert r.status_code == 201


def test_one_household_cannot_flood_a_slot(client):
    g = client.get("/api/live").json()["clock"]["g"] + 3
    codes = [client.post("/api/orders", json={"household": 11, "g": g, "side": "buy", "qty_wh": 100, "price": 700}).status_code
             for _ in range(7)]
    assert codes[:5] == [201] * 5 and codes[5:] == [422, 422]


def test_step_settles_and_ledger_verifies(client):
    client.post("/api/clock", json={"action": "step"})
    ledger = client.get("/api/ledger").json()
    settled = [x for x in ledger if x["status"] == "settled"]
    assert settled and all(x["verification"]["verified"] for x in settled)
