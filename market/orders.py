"""Orders, tariffs and the price band.

Units are integers throughout so Python, TypeScript and Solidity agree to the
last digit: energy in Wh, money in paise, prices in paise per kWh.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "market.json"


class Side(str, Enum):
    BUY = "buy"
    SELL = "sell"


class BandViolation(ValueError):
    """A price outside the open interval (feed-in tariff, retail tariff - wheeling)."""


def rupees(paise: int) -> str:
    return f"₹{paise / 100:.2f}"


@dataclass(frozen=True)
class Tariff:
    """The band. Outside it nobody has a reason to trade locally.

    feed_in   what the utility pays a household for export
    retail    what the utility charges a household for import
    wheeling  network charge a buyer pays per kWh delivered over the DISCOM's wires

    The seller receives the cleared price p; the buyer pays p + wheeling. Trading
    beats the grid for both only if feed_in < p and p + wheeling < retail, so a
    wheeling charge narrows the band from the top.
    """

    feed_in: int
    retail: int
    wheeling: int = 0

    def __post_init__(self) -> None:
        if min(self.feed_in, self.retail, self.wheeling) < 0:
            raise ValueError("tariffs must be non-negative")
        if self.ceiling - self.floor < 0:
            raise ValueError(
                f"wheeling charge {rupees(self.wheeling)} closes the band: no price beats the grid for both sides"
            )

    @property
    def floor(self) -> int:
        """Lowest admissible price (inclusive)."""
        return self.feed_in + 1

    @property
    def ceiling(self) -> int:
        """Highest admissible price (inclusive)."""
        return self.retail - self.wheeling - 1

    def admits(self, price: int) -> bool:
        return self.feed_in < price < self.retail - self.wheeling

    def check(self, price: int) -> None:
        if not self.admits(price):
            raise BandViolation(
                f"Price must sit between {rupees(self.feed_in)} and {rupees(self.retail - self.wheeling)} per kWh. "
                "Outside that range the grid is the better deal."
            )

    @classmethod
    def from_config(cls, path: Path = CONFIG_PATH) -> Tariff:
        c = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            feed_in=c["feed_in_tariff_paise_per_kwh"],
            retail=c["retail_tariff_paise_per_kwh"],
            wheeling=c["wheeling_charge_paise_per_kwh"],
        )


@dataclass(frozen=True)
class Order:
    order_id: str
    household: int
    side: Side
    qty_wh: int
    price: int  # paise per kWh
    seq: int  # submission order; earlier wins ties at the same price

    def __post_init__(self) -> None:
        if self.qty_wh <= 0:
            raise ValueError(f"order {self.order_id}: quantity must be positive")
