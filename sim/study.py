"""Milestone 6: the study. Strategies, wheeling charges, incentive compatibility.

    python -m sim.study            (after python -m ml.evaluate)
    python -m sim.study --quick    (one month, fewer seeds; for CI)

Every figure is measured against the counterfactual of no market at all: the
same signed meter readings billed at retail for import and feed-in for export.
A positive saving means the households, together, paid less than that.

  1. Strategy comparison. Volume rule x price rule over Oct 2012 - Mar 2013 (out
     of sample for every forecast). Random pricing is run over five seeds.
  2. Wheeling sensitivity. A network charge per kWh delivered narrows the band
     from the top. At what charge do households stop gaining, and at what
     charge does the market stop clearing?
  3. Incentive compatibility. Everyone bids their reservation price; one
     household at a time shades its price instead. If shading pays, the
     mechanism is not incentive-compatible, and by how much matters.

Outputs: reports/study/results.json, results.md, wheeling.png, strategies.png
"""

from __future__ import annotations

import argparse
import json
import sys
import os
import time
from concurrent.futures import ProcessPoolExecutor

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from ml import config as ml_config
from sim.backtest import Scenario, json_cfg, run, world

OUT = ml_config.ROOT / "reports" / "study"
VOLUMES = ["seasonal_naive", "p50", "newsvendor", "perfect"]
VOLUME_LABEL = {"seasonal_naive": "Seasonal naive", "p50": "Forecast P50", "newsvendor": "Newsvendor quantile",
                "perfect": "Perfect foresight (oracle)"}


def _run(sc: Scenario) -> dict:
    r = run(sc)
    s = r.summary()
    if sc.deviant is not None or sc.name.startswith("ic-base"):
        s["per_household_saving_inr"] = {h: r.saving_mp(h) / 100_000 for h in r.market_mp}
    return s


def run_all(scenarios: list[Scenario], workers: int) -> list[dict]:
    with ProcessPoolExecutor(max_workers=workers) as ex:
        return list(ex.map(_run, scenarios, chunksize=1))


def main(quick: bool = False) -> None:
    t0 = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    model, _, forecasts = world()
    if forecasts is None:
        raise SystemExit("No forecasts: run python -m ml.evaluate first.")
    cfg = json_cfg()
    F, R = cfg["feed_in_tariff_paise_per_kwh"], cfg["retail_tariff_paise_per_kwh"]
    span = ("2012-11-01", "2012-11-30") if quick else ("2012-10-01", "2013-03-31")
    seeds = [0, 1] if quick else [0, 1, 2, 3, 4]
    workers = max(1, min(12, (os.cpu_count() or 2) - 2))

    # 1. Strategies
    strat = []
    for v in VOLUMES:
        strat.append(Scenario(f"{v}/truthful", volume=v, price="truthful", first_day=span[0], last_day=span[1]))
        strat.append(Scenario(f"{v}/shaded", volume=v, price="shaded", first_day=span[0], last_day=span[1]))
        for s in seeds:
            strat.append(Scenario(f"{v}/random", volume=v, price="random", shade=0.55, seed=s,
                                  first_day=span[0], last_day=span[1]))
    # 2. Wheeling
    levels = list(range(0, 550, 50)) + [R - F - 2]
    wheel = [Scenario(f"wheel/{v}/{w}", volume=v, price="truthful", wheeling=w, first_day=span[0], last_day=span[1])
             for v in ("seasonal_naive", "newsvendor") for w in levels]
    # 3. Incentive compatibility (two months, everyone truthful but one). P50 volumes, which do not
    # depend on the expected price: a deviant who moves the price must not also move everyone's
    # quantities through their price expectations, or the test measures that instead.
    ic_span = ("2012-11-01", "2012-11-30") if quick else ("2012-11-01", "2012-12-31")
    shades = [0.15, 0.4]
    ic = [Scenario("ic-base", volume="p50", price="truthful", first_day=ic_span[0], last_day=ic_span[1])]
    ic += [Scenario(f"ic/{h.id}/{s}", volume="p50", price="truthful", deviant=h.id, deviant_shade=s,
                    first_day=ic_span[0], last_day=ic_span[1])
           for h in model.households for s in shades]
    has_pv = {h.id: h.pv for h in model.households}

    all_sc = strat + wheel + ic
    print(f"study     {len(all_sc)} backtests on {workers} workers", flush=True)
    out = run_all(all_sc, workers)
    res_strat, res_wheel, res_ic = out[:len(strat)], out[len(strat):len(strat) + len(wheel)], out[len(strat) + len(wheel):]

    # --- 1. strategy table: mean and spread over seeds for random pricing
    table = []
    for v in VOLUMES:
        for p in ("truthful", "shaded", "random"):
            rows = [r for r in res_strat if r["volume"] == v and r["price"] == p]
            sav = np.array([r["saving_inr"] for r in rows])
            table.append({
                "volume": VOLUME_LABEL[v], "price": p, "runs": len(rows),
                "saving_inr": float(sav.mean()), "saving_sd_inr": float(sav.std()) if len(rows) > 1 else 0.0,
                "saving_inr_per_household_year": float(np.mean([r["saving_inr_per_household_year"] for r in rows])),
                "traded_kwh": float(np.mean([r["traded_kwh"] for r in rows])),
                "overcommit_kwh": float(np.mean([r["overcommit_kwh"] for r in rows])),
                "mean_price_inr": float(np.mean([r["mean_price_inr"] or 0 for r in rows])),
                "price_sd_inr": float(np.mean([r["price_sd_inr"] or 0 for r in rows])),
                "loss_share": float(np.mean([r["loss_share"] for r in rows])),
                "cleared_share": float(np.mean([r["cleared_share"] for r in rows])),
            })
    grid_bill = res_strat[0]["grid_only_bill_inr"]
    for row in table:  # share of the perfect-foresight saving each forecast captures, same price rule
        oracle = table_row(table, VOLUME_LABEL["perfect"], row["price"])["saving_inr"]
        row["share_of_oracle"] = row["saving_inr"] / oracle if oracle else None

    # --- 2. wheeling: where savings cross zero, where volume stops
    curves = {}
    for v in ("seasonal_naive", "newsvendor"):
        rows = sorted([r for r in res_wheel if r["volume"] == v], key=lambda r: r["wheeling_paise"])
        ws = np.array([r["wheeling_paise"] for r in rows])
        sav = np.array([r["saving_inr"] for r in rows])
        crossing = None
        for i in range(1, len(ws)):
            if sav[i - 1] > 0 >= sav[i]:
                crossing = float(ws[i - 1] + (ws[i] - ws[i - 1]) * sav[i - 1] / (sav[i - 1] - sav[i]))
                break
        curves[v] = {
            "wheeling_paise": ws.tolist(), "saving_inr": sav.tolist(),
            "traded_kwh": [r["traded_kwh"] for r in rows], "operator_inr": [r["operator_inr"] for r in rows],
            "saving_zero_at_paise": crossing,
        }
    loss_recovery = (table_row(table, "Newsvendor quantile", "truthful")["mean_price_inr"] * 100
                     * table_row(table, "Newsvendor quantile", "truthful")["loss_share"])

    # --- 3. incentive compatibility
    base = res_ic[0]["per_household_saving_inr"]
    gains = []
    for r, sc in zip(res_ic[1:], ic[1:]):
        h = sc.deviant
        gains.append({"household": h, "shade": sc.deviant_shade,
                      "gain_inr": r["per_household_saving_inr"][h] - base[h],
                      "others_change_inr": sum(v - base[k] for k, v in r["per_household_saving_inr"].items() if k != h),
                      "welfare_change_inr": r["saving_inr"] - res_ic[0]["saving_inr"]})
    ic_summary = {}
    for s in shades:
        for group, members in (("with PV (mostly sellers)", True), ("without PV (buyers)", False)):
            g = [x for x in gains if x["shade"] == s and has_pv[x["household"]] == members]
            arr = np.array([x["gain_inr"] for x in g])
            ic_summary[f"{s}|{group}"] = {
                "shade": s, "group": group,
                "households_that_gain": int((arr > 0.005).sum()), "households": len(g),
                "mean_gain_inr": float(arr.mean()), "max_gain_inr": float(arr.max()),
                "mean_others_change_inr": float(np.mean([x["others_change_inr"] for x in g])),
                "mean_welfare_change_inr": float(np.mean([x["welfare_change_inr"] for x in g])),
            }

    results = {
        "period": {"strategies": span, "incentive_compatibility": ic_span},
        "tariff": {"feed_in_paise": F, "retail_paise": R},
        "forecast_model": forecasts.model,
        "households": len(model.households),
        "grid_only_bill_inr": grid_bill,
        "strategies": table,
        "wheeling": curves,
        "loss_cost_paise_per_kwh": loss_recovery,
        "incentive_compatibility": {"summary": ic_summary, "deviations": gains},
        "runtime_s": round(time.time() - t0),
        "quick": quick,
    }
    (OUT / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    (OUT / "results.md").write_text(markdown(results), encoding="utf-8")
    figures(results)
    print(markdown(results), flush=True)
    print(f"done      {time.time() - t0:.0f}s", flush=True)


def table_row(table, volume, price):
    return next(r for r in table if r["volume"] == volume and r["price"] == price)


def markdown(r: dict) -> str:
    a, b = r["period"]["strategies"]
    lines = [f"Feeder of {r['households']} households, {a} to {b}. Forecasts: {r['forecast_model']} (out of sample).",
             f"Grid-only bill for the feeder over the period: ₹{r['grid_only_bill_inr']:,.0f}.", "",
             "**1. Strategies** (saving = households together vs billing the same meters with no market)", "",
             "| Volume rule | Price rule | Saving ₹ | ± sd | ₹ / household / year | Share of oracle | Traded kWh | Over-committed kWh | Price ₹ (sd) |",
             "|---|---|---:|---:|---:|---:|---:|---:|---:|"]
    for t in r["strategies"]:
        share = "" if t["share_of_oracle"] is None else f"{t['share_of_oracle'] * 100:.0f}%"
        lines.append(f"| {t['volume']} | {t['price']} | {t['saving_inr']:,.0f} | {t['saving_sd_inr']:,.0f} | "
                     f"{t['saving_inr_per_household_year']:,.0f} | {share} | {t['traded_kwh']:,.0f} | "
                     f"{t['overcommit_kwh']:,.0f} | {t['mean_price_inr']:.2f} ({t['price_sd_inr']:.2f}) |")
    lines += ["", "**2. Wheeling charge** (truthful pricing)", ""]
    for v, c in r["wheeling"].items():
        z = c["saving_zero_at_paise"]
        lines.append(f"- {VOLUME_LABEL[v]}: households stop gaining at "
                     + (f"₹{z / 100:.2f}/kWh" if z is not None else "no charge below the band's closure")
                     + f"; the market keeps clearing until the band closes at ₹{(r['tariff']['retail_paise'] - r['tariff']['feed_in_paise']) / 100:.2f}.")
    lines.append(f"- Recovering the cost of losses alone needs about ₹{r['loss_cost_paise_per_kwh'] / 100:.3f}/kWh.")
    lines += ["", "**3. Incentive compatibility** (everyone truthful but one household, which shades its price)", ""]
    for x in r["incentive_compatibility"]["summary"].values():
        lines.append(f"- {x['group']}, shading {x['shade']:.0%} of the band: {x['households_that_gain']} of "
                     f"{x['households']} gain (mean ₹{x['mean_gain_inr']:.2f}, best ₹{x['max_gain_inr']:.2f}); "
                     f"everyone else changes by ₹{x['mean_others_change_inr']:.2f}; total welfare by "
                     f"₹{x['mean_welfare_change_inr']:.2f}.")
    return "\n".join(lines)


def figures(r: dict) -> None:
    plt.rcParams.update({"font.family": "DejaVu Sans"})
    fig, ax = plt.subplots(figsize=(9, 4.2), facecolor="#12161B")
    ax.set_facecolor("#1C232B")
    colors = {"seasonal_naive": "#6E7A87", "newsvendor": "#F2A93B"}
    for v, c in r["wheeling"].items():
        ax.plot(np.array(c["wheeling_paise"]) / 100, c["saving_inr"], color=colors[v], linewidth=2, marker="o",
                markersize=3.5, label=VOLUME_LABEL[v])
        if c["saving_zero_at_paise"] is not None:
            ax.axvline(c["saving_zero_at_paise"] / 100, color=colors[v], linewidth=0.8)
    ax.axhline(0, color="#E8EDF2", linewidth=0.8)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color("#2A3440")
    ax.tick_params(colors="#6E7A87")
    ax.grid(color="#2A3440", linewidth=0.6)
    ax.set_xlabel("wheeling charge, ₹ per kWh delivered", color="#6E7A87")
    ax.set_ylabel("households' saving vs no market, ₹", color="#6E7A87")
    ax.set_title("Where a network charge eats the market", color="#E8EDF2", loc="left")
    leg = ax.legend(frameon=False)
    for t in leg.get_texts():
        t.set_color("#6E7A87")
    fig.tight_layout()
    fig.savefig(OUT / "wheeling.png", dpi=140, facecolor="#12161B")
    plt.close(fig)
    from ml.evaluate import publish_figure

    publish_figure(OUT / "wheeling.png")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # rupee signs on a Windows console
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    main(ap.parse_args().quick)
