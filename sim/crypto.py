"""Meter keys, signed readings, and the settlement commitment.

The encodings here must match contracts/src/EnergyMarket.sol byte for byte:
  * readings are EIP-712 typed data, bound to the chain id and the settlement
    contract's address, so a signature cannot be replayed elsewhere;
  * the commitment is keccak256(abi.encode(slotStart, price, trades)).

Meters are simulated processes, but their keys are real secp256k1 keys and the
signatures are real ECDSA. Keys are derived from the simulation seed so a run
is reproducible; a real meter generates its key inside a secure element and
never reveals it. That secure element is where the trust lives: the contract
can check that a reading was signed by the key registered for a meter, not
that the reading is true.
"""

from __future__ import annotations

from dataclasses import dataclass

from eth_abi import encode
from eth_account import Account
from eth_account.messages import encode_typed_data
from eth_utils import keccak

from market.flows import Trade

READING_TYPES = {
    "MeterReading": [
        {"name": "meterId", "type": "uint32"},
        {"name": "slotStart", "type": "uint64"},
        {"name": "importWh", "type": "uint64"},
        {"name": "exportWh", "type": "uint64"},
    ]
}
TRADE_ABI = "(uint32,uint32,uint64,uint64)[]"


def domain(chain_id: int, verifying_contract: str) -> dict:
    return {
        "name": "LocalEnergyMarket",
        "version": "1",
        "chainId": chain_id,
        "verifyingContract": verifying_contract,
    }


@dataclass(frozen=True)
class SignedReading:
    meter_id: int
    slot_start: int  # unix seconds, UTC
    import_wh: int
    export_wh: int
    signature: str  # 0x-prefixed 65-byte r||s||v

    def message(self) -> dict:
        return {"meterId": self.meter_id, "slotStart": self.slot_start,
                "importWh": self.import_wh, "exportWh": self.export_wh}


class Meter:
    """A simulated smart meter holding a real ECDSA signing key."""

    def __init__(self, meter_id: int, seed: int, chain_id: int, verifying_contract: str):
        self.meter_id = meter_id
        self._account = Account.from_key(keccak(text=f"lem-sim-meter:{seed}:{meter_id}"))
        self._domain = domain(chain_id, verifying_contract)

    @property
    def address(self) -> str:
        return self._account.address

    def sign(self, slot_start: int, import_wh: int, export_wh: int) -> SignedReading:
        msg = {"meterId": self.meter_id, "slotStart": slot_start, "importWh": import_wh, "exportWh": export_wh}
        signable = encode_typed_data(self._domain, READING_TYPES, msg)
        sig = self._account.sign_message(signable).signature
        return SignedReading(self.meter_id, slot_start, import_wh, export_wh, "0x" + sig.hex().removeprefix("0x"))


def recover_signer(reading: SignedReading, chain_id: int, verifying_contract: str) -> str:
    signable = encode_typed_data(domain(chain_id, verifying_contract), READING_TYPES, reading.message())
    return Account.recover_message(signable, signature=reading.signature)


def trades_tuple(trades: list[Trade]) -> list[tuple[int, int, int, int]]:
    return [(t.seller, t.buyer, t.injected_wh, t.delivered_wh) for t in trades]


def commitment(slot_start: int, price: int, trades: list[Trade]) -> str:
    """keccak256(abi.encode(uint64 slotStart, uint32 price, Trade[] trades))."""
    data = encode(["uint64", "uint32", TRADE_ABI], [slot_start, price, trades_tuple(trades)])
    return "0x" + keccak(data).hex()
