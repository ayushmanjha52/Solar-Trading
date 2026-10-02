"""The simulated market, one half-hour slot at a time.

Each tick of the clock moves one settlement period forward:

  1. delivery of slot g ends. Every meter signs its reading for g. The
     settlement for g is computed from the trades COMMITTED at gate closure and
     those signed readings, then verified: the commitment recomputed from the
     stored trades must match, every signature must recover to the meter's
     registered key, and the price must sit in the band.
  2. gate closure for slot g+1. Its book is cleared, the volume allocated into
     flows on the feeder, and keccak256(trades) published as the commitment,
     before anyone has seen a meter reading for g+1. The operator cannot later
     settle a different outcome without the hash failing to match.
  3. the book for g+2 opens. Agents post orders from their forecasts; a
     visitor acting for a household can post orders for any open slot.
"""

from __future__ import annotations

import dataclasses
import itertools
import json
import threading
import time
from dataclasses import dataclass, field

from market import flows
from market.double_auction import Clearing, book_curves, clear
from market.orders import CONFIG_PATH, BandViolation, Order, Side, Tariff
from market.settlement import Reading, SlotSettlement, settle
from sim import agents, crypto
from sim import data as sim_data
from sim import feeder as sim_feeder
from sim import forecasts as sim_forecasts
from sim.config import DEFAULT, SimConfig

SLOTS = sim_data.SLOTS
MAX_USER_ORDER_WH = 20_000
USER_HORIZON = SLOTS  # visitors may trade up to a day ahead


class OrderRejected(ValueError):
    pass


@dataclass
class UserOrder:
    order: Order
    g: int
    placed_at: float
    status: str = "open"  # open -> cleared -> settled, or cancelled
    fill_wh: int = 0


@dataclass
class SlotRecord:
    g: int
    orders: list[Order]
    clearing: Clearing
    allocation: flows.Allocation
    commitment: str
    committed_at: float
    readings: dict[int, crypto.SignedReading] | None = None
    settlement: SlotSettlement | None = None
    verification: dict | None = None
    chain: dict = field(default_factory=dict)


def slot_time(slot: int) -> str:
    m = (slot - 1) * 30
    return f"{m // 60:02d}:{m % 60:02d}"


class Simulation:
    def __init__(self, cfg: SimConfig = DEFAULT, chain=None):
        if chain is not None:
            # Meter signatures are bound to the contract that will check them.
            cfg = dataclasses.replace(cfg, chain_id=chain.chain_id, verifying_contract=chain.market)
        self.cfg = cfg
        self.tariff = Tariff.from_config()
        self.loss_cap = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))["loss_cap_fraction"]
        self.model = sim_feeder.build(cfg)
        self.data = sim_data.load(cfg, self.model)
        self.forecasts = sim_forecasts.load(self.model, self.data)
        self.meters = {h.id: crypto.Meter(h.id, cfg.seed, cfg.chain_id, cfg.verifying_contract)
                       for h in self.model.households}
        self.chain = chain
        if chain is not None:
            chain.register_meters({h: m.address for h, m in self.meters.items()})
        self.lock = threading.RLock()
        self.paused = False
        self.slot_seconds = cfg.slot_seconds
        self.reset(cfg.start_day, cfg.start_slot)

    # --- lifecycle ------------------------------------------------------------

    def reset(self, day: str, slot: int = 1) -> None:
        """Start the clock at (day, slot), replaying that day from 00:00 so its history exists."""
        with self.lock:
            target = self.data.g_of(day, slot)
            if not 1 <= slot <= SLOTS or not self.data.first_g <= target < self.data.last_g - 1:
                raise ValueError(f"{day} slot {slot} is outside the simulated range "
                                 f"{self.cfg.first_day} to {self.cfg.last_day}")
            self._seq = itertools.count()
            self.records: dict[int, SlotRecord] = {}
            self.books: dict[int, list[Order]] = {}
            self.user_orders: dict[str, UserOrder] = {}
            if self.chain is not None:
                self.chain.start_run()  # a replayed timeline is a new, publicly visible run
            g0 = target - target % SLOTS
            self.g = g0
            self._open_book(g0)
            self._clear(g0)
            self._open_book(g0 + 1)
            while self.g < target:
                self.tick()

    def tick(self) -> None:
        with self.lock:
            self._settle(self.g)
            if self.g + 2 > self.data.last_g:
                self.reset(self.cfg.first_day)
                return
            self.g += 1
            self._clear(self.g)
            self._open_book(self.g + 1)
            self._prune()

    def _next_seq(self) -> int:
        return next(self._seq)

    def _user_households(self, g: int) -> set[int]:
        return {u.order.household for u in self.user_orders.values() if u.g == g and u.status == "open"}

    def _open_book(self, g: int) -> None:
        controlled = self._user_households(g)
        free = [h.id for h in self.model.households if h.id not in controlled]
        book = [u.order for u in self.user_orders.values() if u.g == g and u.status == "open"]
        book += agents.agent_orders(self.cfg, self.data, self.tariff, free, g, self._next_seq,
                                    self.forecasts, self.expected_price())
        self.books[g] = book

    def expected_price(self) -> float:
        """What an agent expects the next slot to clear at: the mean cleared price of the last day."""
        prices = [r.clearing.price for g, r in self.records.items() if g > self.g - SLOTS and r.clearing.price]
        return sum(prices) / len(prices) if prices else (self.tariff.floor + self.tariff.ceiling) / 2

    def forecast(self, h: int, g: int) -> dict:
        """The forecast an agent bids from, for display: quantiles if available, else seasonal naive."""
        q = self.forecasts.get(h, g) if self.forecasts is not None else None
        if q is not None and self.cfg.volume_rule != "seasonal_naive":
            return {"p10_wh": int(q[0]), "p50_wh": int(q[1]), "p90_wh": int(q[2])}
        return {"p50_wh": agents.forecast_net_wh(self.data, h, g)}

    @property
    def forecast_label(self) -> str:
        if self.forecasts is not None and self.cfg.volume_rule != "seasonal_naive":
            return f"{self.forecasts.model}, out of sample; agents bid the {self.cfg.volume_rule} quantile"
        return "seasonal naive (same slot yesterday)"

    def _clear(self, g: int) -> None:
        orders = self.books.pop(g)
        clearing = clear(orders, self.tariff)
        allocation = flows.allocate(clearing, orders, self.model.feeder, self.loss_cap)
        rec = SlotRecord(
            g=g, orders=orders, clearing=clearing, allocation=allocation,
            commitment=crypto.commitment(self.slot_start(g), clearing.price or 0, allocation.trades),
            committed_at=time.time(),
        )
        self.records[g] = rec
        for u in self.user_orders.values():
            if u.g == g and u.status == "open":
                u.status, u.fill_wh = "cleared", clearing.fills.get(u.order.order_id, 0)
        if self.chain is not None:
            rec.chain["commit"] = self._anchor(self.chain.commit, rec)

    def _settle(self, g: int) -> None:
        rec = self.records[g]
        start = self.slot_start(g)
        readings = {}
        for h in self.model.households:
            net = self.data.net_wh(h.id, g)
            readings[h.id] = self.meters[h.id].sign(start, max(-net, 0), max(net, 0))
        rec.readings = readings
        rec.settlement = settle(
            rec.allocation.trades, rec.clearing.price, self.tariff,
            {h: Reading(r.import_wh, r.export_wh) for h, r in readings.items()},
        )
        rec.verification = self.verify(rec)
        for u in self.user_orders.values():
            if u.g == g and u.status == "cleared":
                u.status = "settled"
        if self.chain is not None:
            rec.chain["settle"] = self._anchor(self.chain.settle, rec)

    def _anchor(self, op, rec: SlotRecord) -> dict:
        """A chain failure is recorded against the slot, never allowed to stop the market."""
        try:
            return op(rec, self)
        except Exception as e:  # network down, node restarted, revert
            return {"status": "failed", "error": str(e)[:200]}

    def verify(self, rec: SlotRecord) -> dict:
        """Re-derive everything a settlement depends on from its evidence."""
        start = self.slot_start(rec.g)
        recomputed = crypto.commitment(start, rec.clearing.price or 0, rec.allocation.trades)
        bad_signers = [
            h for h, r in (rec.readings or {}).items()
            if r.slot_start != start
            or crypto.recover_signer(r, self.cfg.chain_id, self.cfg.verifying_contract) != self.meters[h].address
        ]
        band_ok = rec.clearing.price is None or self.tariff.admits(rec.clearing.price)
        return {
            "commitment_matches": recomputed == rec.commitment,
            "signatures_valid": not bad_signers,
            "bad_signers": bad_signers,
            "band_ok": band_ok,
            "verified": recomputed == rec.commitment and not bad_signers and band_ok,
        }

    def _prune(self) -> None:
        horizon = self.g - (self.g % SLOTS) - (self.cfg.keep_days - 1) * SLOTS
        for g in [g for g in self.records if g < horizon]:
            del self.records[g]
        for oid in [o for o, u in self.user_orders.items() if u.g < horizon]:
            del self.user_orders[oid]

    # --- visitor orders -------------------------------------------------------

    def place_order(self, household: int, g: int, side: str, qty_wh: int, price: int) -> UserOrder:
        with self.lock:
            if household not in self.meters:
                raise OrderRejected(f"There is no household {household} on this feeder.")
            if g <= self.g:
                raise OrderRejected("That slot's gate has closed. Choose a later slot.")
            if g > self.g + USER_HORIZON or g > self.data.last_g:
                raise OrderRejected("Orders open at most one day ahead.")
            if not 0 < qty_wh <= MAX_USER_ORDER_WH:
                raise OrderRejected(f"Quantity must be between 0.001 and {MAX_USER_ORDER_WH / 1000:.0f} kWh.")
            try:
                self.tariff.check(price)
            except BandViolation as e:
                raise OrderRejected(str(e)) from e
            side_enum = Side(side)
            label = self.model.by_id(household).label
            for u in self.user_orders.values():
                if u.g == g and u.order.household == household and u.status == "open" and u.order.side is not side_enum:
                    other = "selling" if u.order.side is Side.SELL else "buying"
                    raise OrderRejected(f"{label} is already {other} in slot {self.data.slot_of(g):02d}. "
                                        "Cancel that order first.")
            order = Order(f"u{int(time.time() * 1000)}-{self._next_seq()}", household, side_enum, qty_wh, price,
                          self._next_seq())
            u = UserOrder(order=order, g=g, placed_at=time.time())
            self.user_orders[order.order_id] = u
            if g in self.books:  # book already open: the agent for this household stands aside
                self.books[g] = [o for o in self.books[g]
                                 if not (o.household == household and o.order_id.endswith("-agent"))]
                self.books[g].append(order)
            return u

    def cancel_order(self, order_id: str) -> None:
        with self.lock:
            u = self.user_orders.get(order_id)
            if u is None:
                raise OrderRejected("No such order.")
            if u.status != "open" or u.g <= self.g:
                raise OrderRejected("That order's slot has already cleared.")
            u.status = "cancelled"
            if u.g in self.books:
                self._open_book(u.g)

    # --- helpers --------------------------------------------------------------

    def slot_start(self, g: int) -> int:
        return int(self.data.ts(g).timestamp())

    def day_start_g(self, g: int) -> int:
        return g - g % SLOTS

    def status_of(self, g: int) -> str:
        rec = self.records.get(g)
        if rec is not None and rec.settlement is not None:
            return "settled"
        if g == self.g:
            return "delivery"
        if g == self.g + 1:
            return "open"
        return "future" if g > self.g else "unrecorded"
