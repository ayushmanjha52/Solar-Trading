"""Two-pass settlement for one slot, in exact integer money.

Money unit: milli-paise (1/1000 paise). price [paise/kWh] x energy [Wh] is
exactly milli-paise, so nothing here ever rounds. ₹1 = 100,000 milli-paise.

Pass 1, market. Trades fixed at gate closure settle at the cleared price,
whatever happens next. Sellers are paid p per Wh injected; buyers pay p plus
the wheeling charge per Wh delivered. The gap between the two, p x losses, is
the cost of losses; the wheeling charge is what pays for it.

Pass 2, imbalance. Forecasts are wrong, so metered energy differs from the
contracted position. Each household's deviation settles against the grid at
grid tariffs: short (delivered less, or consumed more, than contracted) pays
the retail tariff; long is paid the feed-in tariff. A household that did not
trade has no contracted position, so pass 2 reduces to its ordinary bill.

Counterfactual. The same meter readings billed with no market at all. Every
savings figure is measured against this, never against nothing.
"""

from __future__ import annotations

from dataclasses import dataclass

from market.flows import Trade
from market.orders import Tariff


@dataclass(frozen=True)
class Reading:
    import_wh: int
    export_wh: int


@dataclass(frozen=True)
class HouseholdSettlement:
    household: int
    contracted_export_wh: int
    contracted_import_wh: int
    metered_export_wh: int
    metered_import_wh: int
    market_mp: int  # pass 1, + received / - paid
    imbalance_mp: int  # pass 2
    grid_only_mp: int  # counterfactual

    @property
    def deviation_wh(self) -> int:
        """Metered net export minus contracted net export. Negative = short."""
        metered = self.metered_export_wh - self.metered_import_wh
        contracted = self.contracted_export_wh - self.contracted_import_wh
        return metered - contracted

    @property
    def total_mp(self) -> int:
        return self.market_mp + self.imbalance_mp

    @property
    def saving_mp(self) -> int:
        return self.total_mp - self.grid_only_mp


@dataclass(frozen=True)
class SlotSettlement:
    price: int | None
    households: dict[int, HouseholdSettlement]
    loss_cost_mp: int  # p x lost Wh: paid to sellers, received by nobody
    wheeling_income_mp: int

    @property
    def operator_mp(self) -> int:
        return self.wheeling_income_mp - self.loss_cost_mp


def imbalance_cash(deviation_wh: int, tariff: Tariff) -> int:
    return deviation_wh * tariff.feed_in if deviation_wh > 0 else deviation_wh * tariff.retail


def settle(trades: list[Trade], price: int | None, tariff: Tariff, readings: dict[int, Reading]) -> SlotSettlement:
    if trades and price is None:
        raise ValueError("trades without a cleared price")
    if price is not None:
        tariff.check(price)
    c_exp: dict[int, int] = {}
    c_imp: dict[int, int] = {}
    for t in trades:
        c_exp[t.seller] = c_exp.get(t.seller, 0) + t.injected_wh
        c_imp[t.buyer] = c_imp.get(t.buyer, 0) + t.delivered_wh
    missing = (set(c_exp) | set(c_imp)) - set(readings)
    if missing:
        raise ValueError(f"no meter reading for trading households {sorted(missing)}")

    out: dict[int, HouseholdSettlement] = {}
    for h, r in readings.items():
        ce, ci = c_exp.get(h, 0), c_imp.get(h, 0)
        market = 0
        if price is not None:
            market = price * ce - (price + tariff.wheeling) * ci
        deviation = (r.export_wh - r.import_wh) - (ce - ci)
        out[h] = HouseholdSettlement(
            household=h,
            contracted_export_wh=ce,
            contracted_import_wh=ci,
            metered_export_wh=r.export_wh,
            metered_import_wh=r.import_wh,
            market_mp=market,
            imbalance_mp=imbalance_cash(deviation, tariff),
            grid_only_mp=r.export_wh * tariff.feed_in - r.import_wh * tariff.retail,
        )
    lost = sum(t.loss_wh for t in trades)
    delivered = sum(t.delivered_wh for t in trades)
    return SlotSettlement(
        price=price,
        households=out,
        loss_cost_mp=(price or 0) * lost,
        wheeling_income_mp=tariff.wheeling * delivered,
    )
