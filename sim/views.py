"""JSON views of the simulation for the web app.

Money is integer milli-paise ("mp", 1/100,000 of a rupee); energy is integer
Wh; prices are integer paise per kWh. The web app formats; nothing here rounds.
"""

from __future__ import annotations

import os

from market.double_auction import book_curves
from sim.engine import SLOTS, SlotRecord, Simulation, UserOrder, slot_time

PROVENANCE = (
    "Simulation-backed on real data. Meters are simulated processes holding real ECDSA keys. "
    "Load and generation are Ausgrid Solar Home Electricity Data (Sydney, 2010-13); weather from Open-Meteo (ERA5)."
)


def feeder(sim: Simulation) -> dict:
    t = sim.tariff
    return {
        "name": "LV feeder 01 (simulated topology)",
        "backbone_m": sim.model.backbone_m,
        "conductors": {
            "backbone": "95 mm² Al, 0.320 Ω/km",
            "service": "16 mm² Cu, 1.15 Ω/km",
            "phase_voltage": sim.model.feeder.phase_voltage,
            "power_factor": sim.model.feeder.power_factor,
        },
        "tariff": {"feed_in": t.feed_in, "retail": t.retail, "wheeling": t.wheeling,
                   "floor": t.floor, "ceiling": t.ceiling},
        "loss_cap": sim.loss_cap,
        "households": [
            {"id": h.id, "label": h.label, "customer": h.customer, "postcode": h.postcode, "pv": h.pv,
             "pv_kwp": h.pv_kwp, "position_m": h.position_m, "service_m": h.service_m,
             "meter_address": sim.meters[h.id].address}
            for h in sim.model.households
        ],
        "sim": {"seed": sim.cfg.seed, "cell": sim.cfg.cell, "first_day": sim.cfg.first_day,
                "last_day": sim.cfg.last_day, "pv_share": sim.cfg.pv_share,
                "chain_id": sim.cfg.chain_id, "verifying_contract": sim.cfg.verifying_contract,
                "forecast": sim.forecast_label, "volume_rule": sim.cfg.volume_rule, "price_rule": sim.cfg.price_rule},
        "provenance": PROVENANCE,
    }


def clock(sim: Simulation) -> dict:
    g = sim.g
    return {
        "g": g, "day": sim.data.local_day(g), "slot": sim.data.slot_of(g), "slot_time": slot_time(sim.data.slot_of(g)),
        "paused": sim.paused, "slot_seconds": sim.slot_seconds,
        "first_day": sim.cfg.first_day, "last_day": sim.cfg.last_day,
        "chain": sim.chain.status() if sim.chain is not None else {"connected": False},
        # Public deployments lock the shared clock to the operator (see sim/api.py).
        "controls_locked": bool(os.environ.get("LEM_ADMIN_TOKEN")),
    }


def _trade(t, sim: Simulation) -> dict:
    return {"seller": t.seller, "buyer": t.buyer, "injected_wh": t.injected_wh, "delivered_wh": t.delivered_wh,
            "loss_wh": t.loss_wh, "loss_fraction": t.loss_fraction, "path_m": round(t.path_m, 1)}


def slot_summary(sim: Simulation, g: int) -> dict:
    rec = sim.records.get(g)
    out = {"g": g, "slot": sim.data.slot_of(g), "time": slot_time(sim.data.slot_of(g)), "status": sim.status_of(g)}
    if rec is not None:
        a = rec.allocation
        out.update({
            "price": rec.clearing.price, "volume_wh": rec.clearing.volume_wh,
            "injected_wh": a.injected_wh, "delivered_wh": a.delivered_wh, "n_trades": len(a.trades),
            "verified": rec.verification["verified"] if rec.verification else None,
        })
        if rec.settlement is not None:
            out["saving_mp"] = sum(h.saving_mp for h in rec.settlement.households.values())
    return out


def day(sim: Simulation, g_in_day: int | None = None) -> dict:
    g0 = sim.day_start_g(sim.g if g_in_day is None else g_in_day)
    slots = [slot_summary(sim, g) for g in range(g0, g0 + SLOTS)]
    settled = [sim.records[s["g"]] for s in slots if s["status"] == "settled"]
    totals = {
        "settled_slots": len(settled),
        "injected_wh": sum(r.allocation.injected_wh for r in settled),
        "delivered_wh": sum(r.allocation.delivered_wh for r in settled),
        "trades": sum(len(r.allocation.trades) for r in settled),
        "market_value_mp": sum(r.clearing.price * r.allocation.injected_wh for r in settled if r.clearing.price),
        "saving_mp": sum(h.saving_mp for r in settled for h in r.settlement.households.values()),
        "operator_mp": sum(r.settlement.operator_mp for r in settled),
        "all_verified": all(r.verification["verified"] for r in settled),
    }
    return {"day": sim.data.local_day(g0), "first_g": g0, "slots": slots, "totals": totals}


def _order(o, rec_fill: int | None) -> dict:
    return {"id": o.order_id, "household": o.household, "side": o.side.value, "qty_wh": o.qty_wh,
            "price": o.price, "by": "agent" if o.order_id.endswith("-agent") else "visitor",
            "fill_wh": rec_fill}


def slot(sim: Simulation, g: int) -> dict | None:
    rec: SlotRecord | None = sim.records.get(g)
    if rec is None:
        return None
    s = slot_summary(sim, g)
    s.update({
        "day": sim.data.local_day(g),
        "slot_start": sim.slot_start(g),
        "orders": [_order(o, rec.clearing.fills.get(o.order_id, 0)) for o in rec.orders],
        "curves": book_curves(rec.orders),
        "marginal_bid": rec.clearing.marginal_bid, "marginal_ask": rec.clearing.marginal_ask,
        "trades": [_trade(t, sim) for t in rec.allocation.trades],
        "curtailed_wh": sum(rec.allocation.curtailed_sell_wh.values()),
        "commitment": rec.commitment,
        "committed_at": rec.committed_at,
        "verification": rec.verification,
        "chain": rec.chain,
    })
    if rec.readings is not None:
        s["readings"] = [{"meter": r.meter_id, "import_wh": r.import_wh, "export_wh": r.export_wh,
                          "signature": r.signature, "signer": sim.meters[h].address}
                         for h, r in rec.readings.items()]
    if rec.settlement is not None:
        st = rec.settlement
        s["settlement"] = {
            "households": [
                {"household": h.household, "contracted_export_wh": h.contracted_export_wh,
                 "contracted_import_wh": h.contracted_import_wh, "metered_export_wh": h.metered_export_wh,
                 "metered_import_wh": h.metered_import_wh, "deviation_wh": h.deviation_wh,
                 "market_mp": h.market_mp, "imbalance_mp": h.imbalance_mp, "grid_only_mp": h.grid_only_mp,
                 "saving_mp": h.saving_mp}
                for h in st.households.values()
            ],
            "loss_cost_mp": st.loss_cost_mp, "wheeling_income_mp": st.wheeling_income_mp,
            "operator_mp": st.operator_mp,
        }
    return s


def open_book(sim: Simulation) -> dict:
    g = sim.g + 1
    orders = sim.books.get(g, [])
    return {"g": g, "slot": sim.data.slot_of(g), "time": slot_time(sim.data.slot_of(g)),
            "orders": [_order(o, None) for o in orders], "curves": book_curves(orders)}


def live(sim: Simulation) -> dict:
    with sim.lock:
        g = sim.g
        current = slot(sim, g)
        positions = {}
        for t in sim.records[g].allocation.trades:
            positions.setdefault(t.seller, {"export_wh": 0, "import_wh": 0})["export_wh"] += t.injected_wh
            positions.setdefault(t.buyer, {"export_wh": 0, "import_wh": 0})["import_wh"] += t.delivered_wh
        return {
            "clock": clock(sim),
            "day": day(sim),
            "current": current,
            "previous": slot(sim, g - 1),
            "book": open_book(sim),
            "positions": positions,
        }


def user_order(sim: Simulation, u: UserOrder) -> dict:
    rec = sim.records.get(u.g)
    out = {
        **_order(u.order, u.fill_wh if u.status in ("cleared", "settled") else None),
        "g": u.g, "day": sim.data.local_day(u.g), "slot": sim.data.slot_of(u.g),
        "time": slot_time(sim.data.slot_of(u.g)), "status": u.status, "placed_at": u.placed_at,
        "label": sim.model.by_id(u.order.household).label,
    }
    if rec is not None and rec.clearing.price is not None and u.status in ("cleared", "settled"):
        out["cleared_price"] = rec.clearing.price
    if rec is not None and rec.settlement is not None:
        hs = rec.settlement.households[u.order.household]
        out["settlement"] = {"market_mp": hs.market_mp, "imbalance_mp": hs.imbalance_mp,
                             "saving_mp": hs.saving_mp, "deviation_wh": hs.deviation_wh}
    return out


def household(sim: Simulation, h: int) -> dict:
    with sim.lock:
        hh = sim.model.by_id(h)
        g0 = sim.day_start_g(sim.g)
        rows = []
        for g in range(g0, g0 + SLOTS):
            status = sim.status_of(g)
            row = {"g": g, "slot": sim.data.slot_of(g), "time": slot_time(sim.data.slot_of(g)), "status": status,
                   **_forecast(sim, h, g)}
            rec = sim.records.get(g)
            if rec is not None:
                row["contracted_export_wh"] = sum(t.injected_wh for t in rec.allocation.trades if t.seller == h)
                row["contracted_import_wh"] = sum(t.delivered_wh for t in rec.allocation.trades if t.buyer == h)
                row["price"] = rec.clearing.price
            if status == "settled":
                hs = rec.settlement.households[h]
                r = rec.readings[h]
                row.update({"metered_net_wh": r.export_wh - r.import_wh, "load_wh": int(sim.data.load_wh[h - 1, g]),
                            "gen_wh": int(sim.data.gen_wh[h - 1, g]), "market_mp": hs.market_mp,
                            "imbalance_mp": hs.imbalance_mp, "grid_only_mp": hs.grid_only_mp,
                            "saving_mp": hs.saving_mp, "deviation_wh": hs.deviation_wh,
                            "signature": r.signature, "verified": rec.verification["verified"]})
            rows.append(row)
        settled = [r for r in rows if r["status"] == "settled"]
        return {
            "household": next(x for x in feeder(sim)["households"] if x["id"] == h),
            "day": sim.data.local_day(g0),
            "clock": clock(sim),
            "forecast_label": sim.forecast_label,
            "slots": rows,
            "totals": {
                "sold_wh": sum(r.get("contracted_export_wh", 0) for r in settled),
                "bought_wh": sum(r.get("contracted_import_wh", 0) for r in settled),
                "market_mp": sum(r["market_mp"] for r in settled),
                "imbalance_mp": sum(r["imbalance_mp"] for r in settled),
                "grid_only_mp": sum(r["grid_only_mp"] for r in settled),
                "saving_mp": sum(r["saving_mp"] for r in settled),
                "short_slots": sum(1 for r in settled if r["deviation_wh"] < -10 and
                                   (r.get("contracted_export_wh") or r.get("contracted_import_wh"))),
                "long_slots": sum(1 for r in settled if r["deviation_wh"] > 10 and
                                  (r.get("contracted_export_wh") or r.get("contracted_import_wh"))),
            },
            "orders": [user_order(sim, u) for u in sim.user_orders.values() if u.order.household == h],
            "upcoming": [
                {"g": g, "day": sim.data.local_day(g), "slot": sim.data.slot_of(g),
                 "time": slot_time(sim.data.slot_of(g)), **_forecast(sim, h, g)}
                for g in range(sim.g + 1, min(sim.g + 1 + SLOTS, sim.data.last_g + 1))
            ],
        }


def households(sim: Simulation) -> list[dict]:
    with sim.lock:
        g0 = sim.day_start_g(sim.g)
        out = []
        for hh in feeder(sim)["households"]:
            h = hh["id"]
            sold = bought = saving = 0
            for g in range(g0, g0 + SLOTS):
                rec = sim.records.get(g)
                if rec is None or rec.settlement is None:
                    continue
                hs = rec.settlement.households[h]
                sold += hs.contracted_export_wh
                bought += hs.contracted_import_wh
                saving += hs.saving_mp
            pos = live_position(sim, h)
            out.append({**hh, "sold_wh": sold, "bought_wh": bought, "saving_mp": saving, **pos})
        return out


def live_position(sim: Simulation, h: int) -> dict:
    rec = sim.records[sim.g]
    exp = sum(t.injected_wh for t in rec.allocation.trades if t.seller == h)
    imp = sum(t.delivered_wh for t in rec.allocation.trades if t.buyer == h)
    return {"now_export_wh": exp, "now_import_wh": imp, **_forecast(sim, h, sim.g)}


def _forecast(sim: Simulation, h: int, g: int) -> dict:
    f = sim.forecast(h, g)
    out = {"forecast_net_wh": f["p50_wh"]}
    if "p10_wh" in f:
        out.update({"forecast_p10_wh": f["p10_wh"], "forecast_p90_wh": f["p90_wh"]})
    return out


def ledger(sim: Simulation, limit: int = 96) -> list[dict]:
    with sim.lock:
        out = []
        for g in sorted(sim.records, reverse=True)[:limit]:
            rec = sim.records[g]
            out.append({
                **slot_summary(sim, g), "day": sim.data.local_day(g), "commitment": rec.commitment,
                "committed_at": rec.committed_at, "readings": len(rec.readings or {}),
                "verification": rec.verification, "chain": rec.chain,
            })
        return out


def orders(sim: Simulation) -> list[dict]:
    with sim.lock:
        return [user_order(sim, u) for u in sorted(sim.user_orders.values(), key=lambda u: -u.placed_at)]
