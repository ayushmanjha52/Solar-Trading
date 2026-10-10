"""Record a week of the market for the engine-free hosted website.

    python -m sim.export_hosted

Static and serverless hosts (Vercel) cannot run the engine, which is a
long-running process with its own clock. This records seven consecutive days
from the real engine instead: every slot's book, clearing, flows, losses,
commitment, 24 signed meter readings, verification and settlement, plus each
household's forecast and metered energy. The website (web/src/lib/hosted.ts)
replays them on a loop timed by the wall clock, so every visitor sees the same
market. Nothing is re-computed or typed in; signatures still verify in the
browser.

Also copies the files the website reads from outside web/ (tariff config,
results) into web/data/static, so a host that only ships web/ still has them.
"""

from __future__ import annotations

import dataclasses
import json
import shutil

from ml import config as ml_config
from sim import views
from sim.config import DEFAULT
from sim.engine import SLOTS, Simulation

ROOT = ml_config.ROOT
OUT = ROOT / "web" / "data" / "hosted"
STATIC = ROOT / "web" / "data" / "static"
FIRST_DAY = "2012-11-10"
DAYS = 7


def main() -> None:
    cfg = dataclasses.replace(DEFAULT, keep_days=DAYS + 2)
    sim = Simulation(cfg)
    sim.reset(FIRST_DAY, 1)
    g0 = sim.g
    for _ in range(DAYS * SLOTS):
        sim.tick()  # the last tick settles the week's final slot

    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "days").mkdir(parents=True)
    days = []
    for d in range(DAYS):
        first = g0 + d * SLOTS
        day = sim.data.local_day(first)
        slots = []
        for g in range(first, first + SLOTS):
            s = views.slot(sim, g)
            s["status"] = "settled"
            s["committed_at"] = None  # set at replay time from the replay clock
            s["chain"] = {}
            slots.append(s)
        households = {}
        for h in sim.model.households:
            rows = [sim.forecast(h.id, g) for g in range(first, first + SLOTS)]
            households[str(h.id)] = {
                "p50": [r["p50_wh"] for r in rows],
                "p10": [r.get("p10_wh") for r in rows],
                "p90": [r.get("p90_wh") for r in rows],
                "load": [int(sim.data.load_wh[h.id - 1, g]) for g in range(first, first + SLOTS)],
                "gen": [int(sim.data.gen_wh[h.id - 1, g]) for g in range(first, first + SLOTS)],
            }
        (OUT / "days" / f"{day}.json").write_text(
            json.dumps({"day": day, "slots": slots, "households": households}, separators=(",", ":")),
            encoding="utf-8",
        )
        days.append(day)

    feeder = views.feeder(sim)
    (OUT / "feeder.json").write_text(json.dumps(feeder, separators=(",", ":")), encoding="utf-8")
    (OUT / "index.json").write_text(json.dumps({
        "days": days,
        "slot_seconds": sim.slot_seconds,
        "night_slot_seconds": 1.0,
        "daylight_slots": [12, 39],
        "recorded_from": "python -m sim.export_hosted (the market engine, sim/engine.py)",
    }, indent=2), encoding="utf-8")

    STATIC.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "config" / "market.json", STATIC / "market.json")
    shutil.copy2(ROOT / "reports" / "forecasting" / "results.json", STATIC / "forecasting.json")
    shutil.copy2(ROOT / "reports" / "study" / "results.json", STATIC / "study.json")

    size = sum(p.stat().st_size for p in OUT.rglob("*.json"))
    print(f"wrote {OUT.relative_to(ROOT)}: {DAYS} days from {FIRST_DAY}, {size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
