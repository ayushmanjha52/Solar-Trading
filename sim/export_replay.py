"""Record one simulated day from the real engine and build the static replay page.

    python -m sim.export_replay [--day 2012-11-12]

The replay page (deploy/replay/) is the part of the project that can be hosted
anywhere as a single file: every number in it comes from the engine's own
records for that day (clearing, flows, losses, commitments, signed readings,
verification, settlement). It replays them; it does not trade. The live,
interactive market needs the engine (see README).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ml import config as ml_config
from sim import views
from sim.engine import SLOTS, Simulation

ROOT = ml_config.ROOT
TEMPLATE = ROOT / "deploy" / "replay" / "template.html"
OUT = ROOT / "deploy" / "replay" / "feeder-replay.html"


def record_day(day: str) -> dict:
    sim = Simulation()
    sim.reset(day, 1)
    for _ in range(SLOTS):
        sim.tick()  # the 48th tick settles the day's last slot
    g0 = sim.data.g_of(day, 1)
    feeder = views.feeder(sim)
    slots = []
    for g in range(g0, g0 + SLOTS):
        s = views.slot(sim, g)
        rec = sim.records[g]
        positions = {}
        for t in rec.allocation.trades:
            positions.setdefault(t.seller, [0, 0])[0] += t.injected_wh
            positions.setdefault(t.buyer, [0, 0])[1] += t.delivered_wh
        slots.append({
            "slot": s["slot"], "time": s["time"], "price": s["price"], "volume_wh": s["volume_wh"],
            "injected_wh": s["injected_wh"], "delivered_wh": s["delivered_wh"],
            "trades": [[t["seller"], t["buyer"], t["injected_wh"], t["delivered_wh"], round(t["loss_fraction"], 6),
                        t["path_m"]] for t in s["trades"]],
            "curves": s["curves"], "offers": sum(o["side"] == "sell" for o in s["orders"]),
            "bids": sum(o["side"] == "buy" for o in s["orders"]),
            "marginal": [s["marginal_bid"], s["marginal_ask"]],
            "commitment": s["commitment"], "verified": s["verification"]["verified"],
            "signatures": len(s["readings"]),
            "readings": [[r["meter"], r["import_wh"], r["export_wh"], r["signature"]] for r in s["readings"]],
            "positions": positions,
            "saving_mp": sum(h["saving_mp"] for h in s["settlement"]["households"]),
            "loss_cost_mp": s["settlement"]["loss_cost_mp"],
        })
    return {
        "day": day,
        "feeder": {k: feeder[k] for k in ("name", "backbone_m", "conductors", "tariff", "loss_cap", "households")},
        "sim": feeder["sim"], "provenance": feeder["provenance"], "slots": slots,
    }


def results() -> dict:
    out = {}
    fc = ROOT / "reports" / "forecasting" / "results.json"
    st = ROOT / "reports" / "study" / "results.json"
    if fc.exists():
        r = json.loads(fc.read_text(encoding="utf-8"))
        out["forecasting"] = {"market_model": r["market_model"], "splits": r["splits"],
                              "tables": {k: v["rows"] for k, v in r["tables"].items()}}
    if st.exists():
        r = json.loads(st.read_text(encoding="utf-8"))
        out["study"] = {k: r[k] for k in ("period", "strategies", "grid_only_bill_inr", "households",
                                          "loss_cost_paise_per_kwh")}
        out["study"]["wheeling"] = {k: {"zero": v["saving_zero_at_paise"], "w": v["wheeling_paise"],
                                        "saving": v["saving_inr"]} for k, v in r["wheeling"].items()}
        out["study"]["ic"] = list(r["incentive_compatibility"]["summary"].values())
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", default="2012-11-12")
    day = ap.parse_args().day
    data = {"replay": record_day(day), "results": results()}
    blob = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    html = TEMPLATE.read_text(encoding="utf-8").replace("/*__DATA__*/null", blob)
    OUT.write_text(html, encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}  {len(html) / 1e6:.2f} MB, day {day}")


if __name__ == "__main__":
    main()
