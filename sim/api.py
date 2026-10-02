"""HTTP service for the simulated market. The web app is its only client.

    python -m sim.api            (serves on 127.0.0.1:8000)

The live order book is held in this process's memory. In production that is
Redis's job (and settled history is Postgres's); neither is needed while one
process owns the whole feeder, and neither is installed on the dev machine.

Public deployments set LEM_ADMIN_TOKEN. The clock is shared by every visitor,
so pausing, stepping, changing speed or jumping to another day then requires
that token in the X-Admin-Token header. Without the variable (local
development) the controls are open.
"""

from __future__ import annotations

import hmac
import os
import threading
import time
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from sim import views
from sim.engine import OrderRejected, Simulation

SIM: Simulation | None = None


def get() -> Simulation:
    if SIM is None:
        raise HTTPException(503, "Simulation is starting.")
    return SIM


def clock_loop(sim: Simulation, stop: threading.Event) -> None:
    next_tick = time.monotonic() + sim.slot_seconds
    while not stop.is_set():
        time.sleep(0.05)
        if sim.paused:
            next_tick = time.monotonic() + sim.slot_seconds
            continue
        if time.monotonic() >= next_tick:
            sim.tick()
            next_tick = time.monotonic() + sim.slot_seconds


def make_chain():
    if os.environ.get("LEM_CHAIN", "1") == "0":
        return None
    try:
        from sim.chain import ChainClient
    except ImportError:
        return None
    return ChainClient.connect_or_none()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global SIM
    SIM = Simulation(chain=make_chain())
    stop = threading.Event()
    t = threading.Thread(target=clock_loop, args=(SIM, stop), daemon=True)
    t.start()
    yield
    stop.set()


app = FastAPI(title="Local Energy Market simulation", lifespan=lifespan)


@app.get("/api/feeder")
def feeder():
    return views.feeder(get())


@app.get("/api/live")
def live():
    return views.live(get())


@app.get("/api/day")
def day():
    sim = get()
    with sim.lock:
        return views.day(sim)


@app.get("/api/slot/{g}")
def slot(g: int):
    sim = get()
    with sim.lock:
        s = views.slot(sim, g)
    if s is None:
        raise HTTPException(404, "No record for that slot. It has not cleared yet, or it has been pruned.")
    return s


@app.get("/api/households")
def households():
    return views.households(get())


@app.get("/api/households/{h}")
def household(h: int):
    sim = get()
    if h not in sim.meters:
        raise HTTPException(404, f"There is no household {h} on this feeder.")
    return views.household(sim, h)


@app.get("/api/ledger")
def ledger(limit: int = 96):
    return views.ledger(get(), limit)


class OrderIn(BaseModel):
    household: int
    g: int
    side: str = Field(pattern="^(buy|sell)$")
    qty_wh: int
    price: int  # paise per kWh


@app.get("/api/orders")
def list_orders():
    return views.orders(get())


@app.post("/api/orders", status_code=201)
def place_order(o: OrderIn):
    sim = get()
    try:
        u = sim.place_order(o.household, o.g, o.side, o.qty_wh, o.price)
    except OrderRejected as e:
        raise HTTPException(422, str(e)) from e
    with sim.lock:
        return views.user_order(sim, u)


@app.delete("/api/orders/{order_id}")
def cancel_order(order_id: str):
    try:
        get().cancel_order(order_id)
    except OrderRejected as e:
        raise HTTPException(422, str(e)) from e
    return {"cancelled": order_id}


def admin_token() -> str | None:
    return os.environ.get("LEM_ADMIN_TOKEN") or None


def require_operator(token: str | None) -> None:
    expected = admin_token()
    if expected and not hmac.compare_digest((token or "").encode(), expected.encode()):
        raise HTTPException(403, "The clock is shared by every visitor, so only the operator can change it.")


@app.get("/api/clock")
def get_clock():
    sim = get()
    with sim.lock:
        return views.clock(sim)


class ClockIn(BaseModel):
    action: str = Field(pattern="^(pause|resume|step|speed|jump)$")
    slot_seconds: float | None = None
    day: str | None = None
    slot: int | None = None


@app.post("/api/clock")
def control_clock(c: ClockIn, x_admin_token: str | None = Header(default=None)):
    require_operator(x_admin_token)
    sim = get()
    if c.action == "pause":
        sim.paused = True
    elif c.action == "resume":
        sim.paused = False
    elif c.action == "step":
        sim.tick()
    elif c.action == "speed":
        if c.slot_seconds is None or not 1 <= c.slot_seconds <= 60:
            raise HTTPException(422, "Slot length must be between 1 and 60 seconds.")
        sim.slot_seconds = c.slot_seconds
    elif c.action == "jump":
        try:
            sim.reset(c.day or sim.cfg.start_day, c.slot or sim.cfg.start_slot)
        except ValueError as e:
            raise HTTPException(422, str(e)) from e
    with sim.lock:
        return views.clock(sim)


def main() -> None:
    uvicorn.run("sim.api:app", host="127.0.0.1", port=int(os.environ.get("LEM_PORT", "8000")), log_level="warning")


if __name__ == "__main__":
    main()
