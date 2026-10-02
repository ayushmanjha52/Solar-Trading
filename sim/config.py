"""Simulation parameters. Everything that changes an outcome is here and seeded."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SimConfig:
    seed: int = 20121112

    # The feeder: households drawn from one ERA5 cell so they share weather, as
    # neighbours on one LV feeder do. Cell -33.75_151.25 is Sydney's lower north
    # shore / northern beaches, the densest cell in the dataset.
    cell: str = "-33.75_151.25"
    n_households: int = 24
    # Every Ausgrid home has PV. A real feeder does not, and a market where
    # every house has surplus at noon has no buyers. Households without PV keep
    # their real Ausgrid load profile; their generation is set to zero.
    pv_share: float = 0.42
    backbone_m: float = 420.0
    service_m: tuple[float, float] = (12.0, 38.0)

    # Simulated calendar: spring and summer 2012-13, when there is surplus to trade.
    first_day: str = "2012-10-01"
    last_day: str = "2013-03-31"
    start_day: str = "2012-11-12"
    start_slot: int = 21  # 10:00 AEST, replayed from midnight, so a visitor lands mid-morning

    # Agents bid volumes from a seasonal-naive forecast (same slot yesterday)
    # at seeded random prices inside the band. Milestone 6 replaces this with
    # strategies; Milestone 2 replaces the forecast.
    min_order_wh: int = 40
    volume_rule: str = "newsvendor"  # or "p50", "seasonal_naive"; see sim/strategies.py
    price_rule: str = "random"  # or "truthful", "shaded"
    price_spread: float = 0.55  # share of the band an agent's price may wander from its own tariff edge

    slot_seconds: float = 5.0  # wall-clock seconds per simulated half hour
    keep_days: int = 3  # settled history kept in memory

    chain_id: int = 31337
    # Address the settlement contract gets on a fresh Anvil chain (deployer
    # account 0, nonce 1). Meter signatures are bound to it via EIP-712.
    verifying_contract: str = "0xe7f1725E7734CE288F8367e1Bb143E90bb3F0512"


DEFAULT = SimConfig()
