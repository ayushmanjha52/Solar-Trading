"""Build the simulated LV feeder from real Ausgrid households.

Ausgrid publishes postcodes, not network topology, so the feeder is synthetic:
one 3-phase backbone from the distribution transformer, households connected
at seeded random distances along it through single-phase service cables. The
electrical distances are therefore invented; the load and generation behind
each node are real. The interface labels the feeder as simulated.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

import pandas as pd

from market.losses import Feeder
from ml import config as ml_config
from ml.data.weather import cell_of
from sim.config import SimConfig


@dataclass(frozen=True)
class Household:
    id: int  # 1..n, numbered from the feeder head outwards
    label: str  # "H01"
    customer: int  # Ausgrid customer id, for traceability
    postcode: int
    pv: bool
    pv_kwp: float  # 0 for households simulated without PV
    position_m: float
    service_m: float


@dataclass(frozen=True)
class FeederModel:
    households: list[Household]
    feeder: Feeder
    backbone_m: float

    def by_id(self, h: int) -> Household:
        return self.households[h - 1]


def candidate_customers(cfg: SimConfig) -> pd.DataFrame:
    c = pd.read_parquet(ml_config.CUSTOMERS_PARQUET)
    c["cell"] = cell_of(c["lat"], c["lon"])
    # Clean on every quality flag, and complete: no gaps to paper over.
    c = c[(c["cell"] == cfg.cell) & c["clean"] & (c["missing_periods"] == 0)]
    return c.sort_values("customer").reset_index(drop=True)


def build(cfg: SimConfig) -> FeederModel:
    rng = random.Random(f"feeder:{cfg.seed}")
    pool = candidate_customers(cfg)
    if len(pool) < cfg.n_households:
        raise RuntimeError(f"cell {cfg.cell} has {len(pool)} clean households, need {cfg.n_households}")
    chosen = pool.iloc[sorted(rng.sample(range(len(pool)), cfg.n_households))]
    n_pv = round(cfg.pv_share * cfg.n_households)
    pv_customers = set(rng.sample(list(chosen["customer"]), n_pv))

    positions = sorted(rng.uniform(25.0, cfg.backbone_m) for _ in range(cfg.n_households))
    order = list(chosen.itertuples())
    rng.shuffle(order)  # which household sits where is random, then numbered from the head out

    households = []
    for i, (row, pos) in enumerate(zip(order, positions), start=1):
        pv = int(row.customer) in pv_customers
        households.append(Household(
            id=i,
            label=f"H{i:02d}",
            customer=int(row.customer),
            postcode=int(row.postcode),
            pv=pv,
            pv_kwp=float(row.capacity_kwp) if pv else 0.0,
            position_m=round(pos, 1),
            service_m=round(rng.uniform(*cfg.service_m), 1),
        ))
    feeder = Feeder(
        positions_m={h.id: h.position_m for h in households},
        service_m={h.id: h.service_m for h in households},
    )
    return FeederModel(households=households, feeder=feeder, backbone_m=cfg.backbone_m)
