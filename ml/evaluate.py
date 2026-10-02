"""Milestone 2: every forecaster, one test window, one table.

    python -m ml.evaluate            (after python -m ml.data)
    python -m ml.evaluate --quick    (smaller samples, for CI)

Outputs
  reports/forecasting/results.md / results.json   the comparison table
  reports/forecasting/forecast_fan.png            what the quantiles look like
  data/processed/forecasts_feeder.parquet         out-of-sample P10/P50/P90 for the
                                                  feeder households, used by the market agents

Evaluation sets (test window only)
  Feeder   the 24 households exactly as simulated (10 with PV, 14 without):
           the forecasts the market actually consumes.
  PV, sun up  all 124 pool households with their PV, daylight slots only. Night
           slots are easy for every model and would flatter the averages; this
           set is where PV forecasting is actually tested.

What could make a good number look good for the wrong reason, and the check:
  * lookahead in a feature           -> perturbation test, fails the build
  * weather of the target slot       -> shown only as a labelled oracle row
  * selecting the model on test      -> selection uses validation pinball only
  * night zeros inflating skill      -> the PV, sun-up table
  * one lucky window                 -> 95% CIs from a day-block bootstrap
"""

from __future__ import annotations

import argparse
import json
import sys
import time

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from ml import config
from ml.features import build_features as bf
from ml.features.dataset import Variant, feeder_variants, frame, load_panel, pool_customers
from ml.models import baselines, lstm_model, xgb_model
from ml.models.baselines import QUANTILES

OUT = config.ROOT / "reports" / "forecasting"
FORECASTS = config.DATA_PROCESSED / "forecasts_feeder.parquet"
SIM_RANGE = ("2012-10-01", "2013-03-31")


def log(msg: str) -> None:
    print(msg, flush=True)


# --- metrics -----------------------------------------------------------------------

def pinball(y: np.ndarray, q: np.ndarray) -> float:
    d = y[:, None] - q
    a = np.array(QUANTILES)
    return float(np.mean(np.maximum(a * d, (a - 1) * d)))


def day_bootstrap_ci(err: np.ndarray, day: np.ndarray, n: int = 300, seed: int = 0) -> tuple[float, float]:
    """95% CI of the mean of err, resampling whole days (errors within a day are correlated)."""
    codes, inv = np.unique(day, return_inverse=True)
    sums = np.bincount(inv, weights=err)
    counts = np.bincount(inv)
    rng = np.random.default_rng(seed)
    pick = rng.integers(0, len(codes), size=(n, len(codes)))
    means = sums[pick].sum(1) / counts[pick].sum(1)
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def score(name: str, y: np.ndarray, day: np.ndarray, point: np.ndarray, q: np.ndarray | None,
          persistence_mae: float | None, note: str = "") -> dict:
    ae = np.abs(y - point)
    lo, hi = day_bootstrap_ci(ae, day)
    row = {
        "model": name, "mae_wh": float(ae.mean()), "mae_ci_wh": [lo, hi],
        "rmse_wh": float(np.sqrt(np.mean((y - point) ** 2))),
        "skill_vs_persistence": None if persistence_mae is None else float(1 - ae.mean() / persistence_mae),
        "pinball_wh": None, "coverage_80": None, "note": note,
    }
    if q is not None:
        row["pinball_wh"] = pinball(y, q)
        row["coverage_80"] = float(np.mean((y >= q[:, 0]) & (y <= q[:, 2])))
    return row


# --- pipeline ----------------------------------------------------------------------

def main(quick: bool = False) -> None:
    t0 = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    customers = pool_customers()
    feeder = feeder_variants()
    log(f"data      {len(customers)} households in the pool, {len(feeder)} on the feeder")
    p = load_panel(customers)
    tr, va, te = p.split("train"), p.split("val"), p.split("test")

    # Leakage: perturb everything after t-2 and require every feature to stay put.
    rng = np.random.default_rng(0)
    for v in [feeder[0], next(v for v in feeder if v.pv)]:
        bf.assert_causal(p.series(v), p.cal, p.sun[v.customer], rng.choice(np.concatenate([tr, te]), 25))
    log("check     no feature depends on data after t-2 (perturbation test)")

    pool = [Variant(c, pv) for c in customers for pv in (True, False)]
    Xtr, ytr, _ = frame(p, pool, tr)
    Xva, yva, _ = frame(p, pool, va)
    n_train = 600_000 if quick else 3_000_000
    sel = rng.choice(len(ytr), size=min(n_train, len(ytr)), replace=False)
    vsel = rng.choice(len(yva), size=min(400_000, len(yva)), replace=False)
    Xtr_s, ytr_s, Xva_s, yva_s = Xtr.iloc[sel], ytr[sel], Xva.iloc[vsel], yva[vsel]
    log(f"train     {len(ytr_s):,} rows sampled from {len(ytr):,}; validation {len(yva_s):,}")

    rq = baselines.ResidualQuantiles().fit(Xtr, ytr)
    log("fit       seasonal naive + residual quantiles")
    t1 = time.time()
    xp = xgb_model.fit_point(Xtr_s, ytr_s, Xva_s, yva_s)
    log(f"fit       XGBoost point, {xp.best_iteration + 1} trees, {time.time() - t1:.0f}s")
    t1 = time.time()
    xq = xgb_model.fit_quantile(Xtr_s, ytr_s, Xva_s, yva_s)
    log(f"fit       XGBoost + calibrated quantiles (z = {np.round(xq.z, 2).tolist()}), {time.time() - t1:.0f}s")

    # Oracle: same model class handed the target slot's actual weather. Never deployable.
    Xtr_o, _, _ = frame(p, pool, tr, oracle=True)
    Xva_o, _, _ = frame(p, pool, va, oracle=True)
    t1 = time.time()
    xo = xgb_model.fit_quantile(Xtr_o.iloc[sel], ytr_s, Xva_o.iloc[vsel], yva_s)
    log(f"fit       XGBoost quantile ORACLE (target-slot weather), {time.time() - t1:.0f}s")
    del Xtr, Xtr_o, Xva_o

    # LSTM on windows drawn from the same pool and windows.
    series = [p.series(v) for v in pool]
    feats = [{**p.cal, "sun_elev": p.sun[v.customer], "pv_kwp": np.full(len(p.ts), s.pv_kwp)}
             for s, v in zip(series, pool)]
    win = lstm_model.Windows(series, feats)
    which_tr = np.repeat(np.arange(len(pool)), len(tr))
    t_tr = np.tile(tr, len(pool))
    which_va = np.repeat(np.arange(len(pool)), len(va))
    t_va = np.tile(va, len(pool))
    t1 = time.time()
    lstm = lstm_model.train(win, (which_tr, t_tr), (which_va, t_va),
                            epochs=4 if quick else 10, steps_per_epoch=200 if quick else 500, log=log)
    log(f"fit       LSTM, {time.time() - t1:.0f}s")

    # Model selection for the market: validation pinball on the feeder variants only.
    fva_idx = [pool.index(v) for v in feeder]
    which_fva = np.repeat(fva_idx, len(va))
    t_fva = np.tile(va, len(feeder))
    Xfva, yfva, _ = frame(p, feeder, va)
    val_scores = {
        "XGBoost + calibrated quantiles": pinball(yfva, xq.predict(Xfva)),
        "LSTM quantile": pinball(yfva, lstm_model.predict(lstm, win, which_fva, t_fva)),
        "Seasonal naive + residual quantiles": pinball(yfva, rq.predict(Xfva)),
    }
    chosen = min(val_scores, key=val_scores.get)
    log(f"select    validation pinball (Wh): " + ", ".join(f"{k} {v:.1f}" for k, v in val_scores.items())
        + f" -> market uses {chosen}")

    # --- the test window, touched once ---------------------------------------------
    tables = {}
    for set_name, variants, daylight in [("Feeder, as simulated", feeder, False),
                                         ("PV households, sun up", [Variant(c, True) for c in customers], True)]:
        X, y, meta = frame(p, variants, te)
        X_o, _, _ = frame(p, variants, te, oracle=True)
        which = np.array([pool.index(Variant(c, pv)) for c, pv in zip(meta["customer"], meta["pv"])])
        mask = (X["sun_elev"].to_numpy() > 0) if daylight else np.ones(len(y), bool)
        day = meta["t"].to_numpy() // 48
        preds = {
            "Persistence": (baselines.point(X, "Persistence"), None, ""),
            "Seasonal naive": (baselines.point(X, "Seasonal naive"), None, "the agents' forecast before this milestone"),
            "Weekly naive": (baselines.point(X, "Weekly naive"), None, ""),
        }
        q_rq = rq.predict(X)
        preds["Seasonal naive + residual quantiles"] = (q_rq[:, 1], q_rq, "probabilistic baseline")
        preds["XGBoost point"] = (xgb_model.predict(xp, X), None, "squared error")
        q_x = xq.predict(X)
        preds["XGBoost + calibrated quantiles"] = (q_x[:, 1], q_x, "point + learned error scale, calibrated on validation")
        q_l = lstm_model.predict(lstm, win, which, meta["t"].to_numpy())
        preds["LSTM quantile"] = (q_l[:, 1], q_l, "pinball; P50 as point")
        q_o = xo.predict(X_o)
        preds["XGBoost + calibrated quantiles + target-slot weather (ORACLE)"] = (
            q_o[:, 1], q_o, "NOT DEPLOYABLE: uses weather nobody had at bid time")
        pers_mae = float(np.abs(y[mask] - preds["Persistence"][0][mask]).mean())
        rows = []
        for name, (pt, q, note) in preds.items():
            ok = mask & ~np.isnan(pt)
            rows.append(score(name, y[ok], day[ok], pt[ok], None if q is None else q[ok], pers_mae, note))
        tables[set_name] = {"rows": rows, "n": int(mask.sum()), "households": len(variants)}
        if set_name.startswith("Feeder"):
            fan = (X, y, meta, q_x if chosen == "XGBoost + calibrated quantiles" else q_l if chosen == "LSTM quantile" else q_rq)

    results = {
        "task": "net energy of one household, 2 half-hours ahead of the last meter reading (the market's gate)",
        "splits": {"train": "2010-07-08..2012-06-30", "val": "2012-07-01..2012-09-30", "test": "2012-10-01..2013-06-30"},
        "units": "Wh per half hour",
        "validation_pinball_wh": val_scores,
        "market_model": chosen,
        "tables": tables,
        "runtime_s": round(time.time() - t0),
        "quick": quick,
    }
    (OUT / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    (OUT / "results.md").write_text(markdown(results), encoding="utf-8")
    log(markdown(results))

    write_market_forecasts(p, feeder, pool, chosen, xq, lstm, win, rq)
    fan_figure(*fan, p)
    log(f"done      {time.time() - t0:.0f}s")


def write_market_forecasts(p, feeder, pool, chosen, xq, lstm, win, rq) -> None:
    lo, hi = SIM_RANGE
    day = p.ts.tz_convert(config.LOCAL_TZ).normalize().tz_localize(None)
    idx = np.nonzero((day >= pd.Timestamp(lo)) & (day <= pd.Timestamp(hi)))[0]
    X, _, meta = frame(p, feeder, idx)
    if chosen == "XGBoost + calibrated quantiles":
        q = xq.predict(X)
    elif chosen == "LSTM quantile":
        which = np.array([pool.index(Variant(c, pv)) for c, pv in zip(meta["customer"], meta["pv"])])
        q = lstm_model.predict(lstm, win, which, meta["t"].to_numpy())
    else:
        q = rq.predict(X)
    out = pd.DataFrame({
        "customer": meta["customer"].astype(np.int16), "pv": meta["pv"],
        "ts_utc": p.ts[meta["t"].to_numpy()],
        "p10_wh": q[:, 0].astype(np.float32), "p50_wh": q[:, 1].astype(np.float32), "p90_wh": q[:, 2].astype(np.float32),
    })
    out.attrs["model"] = chosen
    out.to_parquet(FORECASTS, index=False)
    (config.DATA_PROCESSED / "forecasts_feeder.json").write_text(json.dumps({"model": chosen, "rows": len(out)}), encoding="utf-8")
    log(f"wrote     {FORECASTS.relative_to(config.ROOT)}  {len(out):,} rows from {chosen}")


def markdown(r: dict) -> str:
    lines = [f"Task: {r['task']}. Test window {r['splits']['test']}; units {r['units']}.", ""]
    for name, t in r["tables"].items():
        lines += [f"**{name}** ({t['households']} households, {t['n']:,} slots)", "",
                  "| Model | MAE | MAE 95% CI | RMSE | Skill vs persistence | Pinball | P10–P90 coverage |",
                  "|---|---:|---:|---:|---:|---:|---:|"]
        for row in t["rows"]:
            cov = "" if row["coverage_80"] is None else f"{row['coverage_80'] * 100:.1f}%"
            pin = "" if row["pinball_wh"] is None else f"{row['pinball_wh']:.1f}"
            lines.append(f"| {row['model']} | {row['mae_wh']:.1f} | {row['mae_ci_wh'][0]:.1f}–{row['mae_ci_wh'][1]:.1f} | "
                         f"{row['rmse_wh']:.1f} | {row['skill_vs_persistence'] * 100:+.1f}% | {pin} | {cov} |")
        lines.append("")
    lines.append(f"Market agents use: **{r['market_model']}** (lowest validation pinball on the feeder).")
    return "\n".join(lines)


def fan_figure(X, y, meta, q, p) -> None:
    """Three sunny-to-cloudy days for one PV household on the feeder: quantile band vs what happened."""
    pv = meta[meta["pv"]]["customer"].iloc[0]
    m = (meta["customer"] == pv).to_numpy()
    t = meta["t"].to_numpy()[m]
    ts = p.ts[t].tz_convert(config.LOCAL_TZ)
    start = np.nonzero(ts.normalize() == pd.Timestamp("2012-11-11", tz=config.LOCAL_TZ))[0]
    if len(start) == 0:
        return
    s = slice(start[0], start[0] + 4 * 48)
    xs = ts[s].tz_localize(None)
    plt.rcParams.update({"font.family": "DejaVu Sans"})
    fig, ax = plt.subplots(figsize=(12, 4.2), facecolor="#12161B")
    ax.set_facecolor("#1C232B")
    ax.fill_between(xs, q[m][s, 0] / 1000, q[m][s, 2] / 1000, color="#F2A93B", alpha=0.25, linewidth=0, step="post",
                    label="P10–P90")
    ax.step(xs, q[m][s, 1] / 1000, where="post", color="#F2A93B", linewidth=1.5, label="P50")
    ax.step(xs, X["net_l48"].to_numpy()[m][s] / 1000, where="post", color="#6E7A87", linewidth=1, label="seasonal naive")
    ax.step(xs, y[m][s] / 1000, where="post", color="#E8EDF2", linewidth=1.5, label="metered")
    ax.axhline(0, color="#6E7A87", linewidth=0.8)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color("#2A3440")
    ax.tick_params(colors="#6E7A87")
    ax.grid(color="#2A3440", linewidth=0.6)
    ax.set_ylabel("net kWh per half hour", color="#6E7A87")
    ax.set_title(f"Ausgrid customer {pv}: forecast two slots ahead vs the meter, 11–14 Nov 2012 (test window)",
                 color="#E8EDF2", loc="left", fontsize=11)
    leg = ax.legend(frameon=False, loc="upper left", ncol=4)
    for txt in leg.get_texts():
        txt.set_color("#6E7A87")
    fig.tight_layout()
    fig.savefig(OUT / "forecast_fan.png", dpi=140, facecolor="#12161B")
    plt.close(fig)
    publish_figure(OUT / "forecast_fan.png")


def publish_figure(path) -> None:
    """Copy a figure into the website's public folder so the Results page shows the latest run."""
    import shutil

    public = config.ROOT / "web" / "public" / "figures"
    if public.parent.exists():
        public.mkdir(exist_ok=True)
        shutil.copy2(path, public / path.name)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # rupee signs on a Windows console
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    main(ap.parse_args().quick)
