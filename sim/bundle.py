"""Write the small data bundle a deployed engine needs, from the full pipeline's outputs.

    python -m sim.bundle        (after python -m ml.data and python -m ml.evaluate)

The live engine trades 24 feeder households over Oct 2012 - Mar 2013. Building
the full 300-household, three-year panel inside a small cloud container is slow
and needs gigabytes of memory, so the deployment ships only the slice the engine
reads, cut from the full pipeline's own outputs and recorded with hashes:

  customers.parquet   all 300 customers' metadata and quality flags (the feeder
                      is chosen from these, exactly as locally)
  panel.parquet       the feeder households' half-hourly rows over the simulated
                      range, plus the day before (the seasonal-naive fallback needs it)
  forecasts_feeder.*  out-of-sample P10/P50/P90 from ml/evaluate.py

Rebuilding everything from the raw Ausgrid archive remains `python -m ml.data`.
"""

from __future__ import annotations

import hashlib
import json
import shutil

import pandas as pd

from ml import config as ml_config
from sim.config import DEFAULT
from sim.feeder import build

OUT = ml_config.ROOT / "deploy" / "bundle"


def sha256(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    model = build(DEFAULT)
    customers = [h.customer for h in model.households]
    lo = pd.Timestamp(DEFAULT.first_day, tz=ml_config.LOCAL_TZ).tz_convert("UTC") - pd.Timedelta(days=1)
    hi = pd.Timestamp(DEFAULT.last_day, tz=ml_config.LOCAL_TZ).tz_convert("UTC") + pd.Timedelta(days=1)
    panel = pd.read_parquet(ml_config.PANEL_PARQUET,
                            filters=[("customer", "in", customers), ("ts_utc", ">=", lo), ("ts_utc", "<", hi)])
    panel.to_parquet(OUT / "panel.parquet", index=False, compression="zstd")
    shutil.copy2(ml_config.CUSTOMERS_PARQUET, OUT / "customers.parquet")
    for name in ("forecasts_feeder.parquet", "forecasts_feeder.json"):
        shutil.copy2(ml_config.DATA_PROCESSED / name, OUT / name)
    manifest = {
        "source": "python -m ml.data (Ausgrid archive sha256 " + ml_config.AUSGRID_SHA256 + ") and python -m ml.evaluate",
        "feeder_customers": customers,
        "range_utc": [str(lo), str(hi)],
        "rows": len(panel),
        "files": {p.name: sha256(p) for p in sorted(OUT.glob("*")) if p.name != "manifest.json"},
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    total = sum(p.stat().st_size for p in OUT.glob("*"))
    print(f"wrote {OUT.relative_to(ml_config.ROOT)}  {len(panel):,} panel rows, {total / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
