"""Distribution losses on a radial LV feeder.

A trade's energy leaves the seller through a single-phase service cable, runs
along the three-phase backbone between the two connection points, and enters
the buyer through their service cable. The loss is I²R over that path:

    I = P / (V_phase · pf)          P = trade energy / period length
    loss / P = P · R_path / (V_phase² · pf²)

R_path counts the phase AND neutral conductors (factor 2), i.e. it assumes the
trade's current returns on the neutral with no help from phase balancing. That
is conservative: a perfectly balanced three-phase flow would lose 1/6 as much
on the backbone.

What this model is not. Losses are quadratic in current, so the loss of two
simultaneous trades is not the sum of their isolated losses; the true loss
depends on the net flow in each conductor segment. Voltage rise at the far end
of a feeder full of exporting PV, conductor thermal limits, reactive power and
phase imbalance are all ignored. A correct treatment needs an AC load-flow
solve (e.g. pandapower or OpenDSS on the feeder model) with voltage and
thermal limits. This model gives the right order of magnitude (fractions of a
percent to a few percent) and the right gradients: more distance and more
power cost more.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Feeder:
    positions_m: dict[int, float]  # household -> distance of its pole from the feeder head
    service_m: dict[int, float]  # household -> length of its service cable
    backbone_ohm_per_km: float = 0.320  # 95 mm² aluminium LV mains, 20 °C
    service_ohm_per_km: float = 1.15  # 16 mm² copper service cable, 20 °C
    phase_voltage: float = 230.0
    power_factor: float = 0.95
    period_h: float = 0.5

    def path_m(self, a: int, b: int) -> float:
        """Conductor route length between two households (backbone + both services)."""
        return abs(self.positions_m[a] - self.positions_m[b]) + self.service_m[a] + self.service_m[b]

    def path_ohm(self, a: int, b: int) -> float:
        """Loop resistance (phase + neutral) of the route between two households."""
        backbone = self.backbone_ohm_per_km * abs(self.positions_m[a] - self.positions_m[b]) / 1000
        services = self.service_ohm_per_km * (self.service_m[a] + self.service_m[b]) / 1000
        return 2 * (backbone + services)

    def loss_fraction(self, a: int, b: int, energy_wh: float) -> float:
        """Share of injected energy lost as heat on the way from a to b."""
        power_w = energy_wh / self.period_h
        return power_w * self.path_ohm(a, b) / (self.phase_voltage * self.power_factor) ** 2

    def max_energy_wh(self, a: int, b: int, loss_cap: float) -> float:
        """Largest trade from a to b whose loss fraction stays at or under the cap."""
        r = self.path_ohm(a, b)
        if r == 0:
            return float("inf")
        return loss_cap * (self.phase_voltage * self.power_factor) ** 2 * self.period_h / r
