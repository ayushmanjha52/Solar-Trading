"""Anchor commitments and settlements on an EVM chain (local Anvil, or Amoy).

    LEM_RPC           JSON-RPC URL (default http://127.0.0.1:8545)
    LEM_OPERATOR_KEY  operator private key. Defaults to Anvil's public test key
                      0 ON CHAIN 31337 ONLY; any other chain requires it set.

Addresses come from contracts/deployments/<chainid>.json, written by
contracts/script/Deploy.s.sol. Each settlement transaction emits the
contract's own two-pass settlement per household; the client decodes those
events and checks them against the engine's numbers, so the chain is an
independent second computation, not a copy.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path

import requests
from eth_abi import decode, encode
from eth_account import Account
from eth_utils import function_signature_to_4byte_selector, keccak

DEPLOYMENTS = Path(__file__).resolve().parents[1] / "contracts" / "deployments"
ANVIL_KEY_0 = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"

TRADE = "(uint32,uint32,uint64,uint64)"
READING = "(uint32,uint64,uint64,bytes)"
SIG = {
    "startRun": "startRun()",
    "commit": "commit(uint64,bytes32)",
    "settle": f"settle(uint64,uint32,{TRADE}[],{READING}[])",
    "registerMany": "registerMany(uint32[],address[])",
    "signerOf": "signerOf(uint32)",
    "currentRun": "currentRun()",
}
HOUSEHOLD_SETTLED = "0x" + keccak(text="HouseholdSettled(uint64,uint64,uint32,int256,int256)").hex()
CUSTOM_ERRORS = {
    "0x" + keccak(text=sig).hex()[:8]: sig.split("(")[0]
    for sig in [
        "NotOperator()", "AlreadyCommitted()", "NotCommitted()", "AlreadySettled()", "CommitmentMismatch()",
        "PriceOutsideBand(uint32)", "ReadingsNotSorted()", "MeterIdTooLarge(uint32)", "BadSignature(uint32)",
        "MissingReading(uint32)", "LossExceedsInjection()", "NotOwner()", "AlreadyRegistered(uint32)", "ZeroSigner()",
    ]
}


class ChainError(RuntimeError):
    pass


def selector(name: str) -> bytes:
    return function_signature_to_4byte_selector(SIG[name])


class ChainClient:
    def __init__(self, rpc: str, chain_id: int, registry: str, market: str, key: str, explorer: str | None):
        self.rpc = rpc
        self.chain_id = chain_id
        self.registry = registry
        self.market = market
        self.account = Account.from_key(key)
        self.explorer = explorer
        self._lock = threading.Lock()
        self._nonce: int | None = None
        self.run: int | None = None
        self.last_block: int | None = None

    # --- construction -----------------------------------------------------------

    @classmethod
    def connect_or_none(cls) -> ChainClient | None:
        rpc = os.environ.get("LEM_RPC", "http://127.0.0.1:8545")
        try:
            chain_id = int(cls._call_rpc(rpc, "eth_chainId", []), 16)
        except Exception:
            return None
        dep = DEPLOYMENTS / f"{chain_id}.json"
        if not dep.exists():
            return None
        d = json.loads(dep.read_text(encoding="utf-8"))
        key = os.environ.get("LEM_OPERATOR_KEY") or (ANVIL_KEY_0 if chain_id == 31337 else None)
        if key is None:
            raise ChainError(f"chain {chain_id} needs LEM_OPERATOR_KEY")
        explorer = "https://amoy.polygonscan.com" if chain_id == 80002 else None
        client = cls(rpc, chain_id, d["registry"], d["market"], key, explorer)
        # A restarted Anvil keeps the deployment file but loses the contracts, and a
        # call to an address with no code "succeeds". Check the code is really there.
        for addr in (client.registry, client.market):
            if client._rpc("eth_getCode", [addr, "latest"]) in ("0x", "0x0", None):
                return None
        return client

    # --- JSON-RPC ---------------------------------------------------------------

    @staticmethod
    def _call_rpc(rpc: str, method: str, params: list):
        r = requests.post(rpc, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params}, timeout=15)
        body = r.json()
        if "error" in body:
            err = body["error"]
            data = err.get("data")
            if isinstance(data, dict):
                data = data.get("data")
            if isinstance(data, str) and data[:10].lower() in CUSTOM_ERRORS:
                raise ChainError(f"reverted: {CUSTOM_ERRORS[data[:10].lower()]}")
            raise ChainError(err.get("message", str(err)))
        return body["result"]

    def _rpc(self, method: str, params: list):
        return self._call_rpc(self.rpc, method, params)

    def _eth_call(self, to: str, data: bytes) -> bytes | None:
        try:
            out = self._rpc("eth_call", [{"to": to, "data": "0x" + data.hex()}, "latest"])
        except ChainError:
            return None
        return bytes.fromhex(out[2:])

    def _send(self, to: str, data: bytes) -> dict:
        with self._lock:
            if self._nonce is None:
                self._nonce = int(self._rpc("eth_getTransactionCount", [self.account.address, "pending"]), 16)
            call = {"from": self.account.address, "to": to, "data": "0x" + data.hex()}
            try:
                gas = int(int(self._rpc("eth_estimateGas", [call]), 16) * 1.25)
            except ChainError as e:  # a revert: the contract refused
                return {"status": "failed", "error": str(e)}
            gas_price = int(self._rpc("eth_gasPrice", []), 16)
            tx = {
                "type": 2, "chainId": self.chain_id, "nonce": self._nonce, "to": to, "value": 0, "data": data,
                "gas": gas, "maxFeePerGas": gas_price * 2, "maxPriorityFeePerGas": min(gas_price, 2_000_000_000),
            }
            raw = self.account.sign_transaction(tx).raw_transaction
            try:
                tx_hash = self._rpc("eth_sendRawTransaction", ["0x" + raw.hex().removeprefix("0x")])
            except ChainError as e:
                self._nonce = None
                return {"status": "failed", "error": str(e)}
            self._nonce += 1
        receipt = None
        for _ in range(200):
            receipt = self._rpc("eth_getTransactionReceipt", [tx_hash])
            if receipt:
                break
            threading.Event().wait(0.05)
        if not receipt:
            return {"status": "failed", "tx": tx_hash, "error": "no receipt"}
        self.last_block = int(receipt["blockNumber"], 16)
        return {
            "status": "confirmed" if receipt["status"] == "0x1" else "failed",
            "tx": tx_hash,
            "block": self.last_block,
            "gas_used": int(receipt["gasUsed"], 16),
            "_logs": receipt["logs"],
        }

    # --- market operations ------------------------------------------------------

    def register_meters(self, meters: dict[int, str]) -> None:
        missing_ids, missing_addrs = [], []
        for meter_id, address in sorted(meters.items()):
            out = self._eth_call(self.registry, selector("signerOf") + encode(["uint32"], [meter_id]))
            current = "0x" + out[-20:].hex() if out else None
            if current is None or int(current, 16) == 0:
                missing_ids.append(meter_id)
                missing_addrs.append(address)
            elif current.lower() != address.lower():
                raise ChainError(f"meter {meter_id} is registered to a different key on chain {self.chain_id}; "
                                 "redeploy or change the simulation seed")
        if missing_ids:
            res = self._send(self.registry, selector("registerMany") +
                             encode(["uint32[]", "address[]"], [missing_ids, missing_addrs]))
            if res["status"] != "confirmed":
                raise ChainError(f"registering meters failed: {res.get('error')}")

    def start_run(self) -> int:
        res = self._send(self.market, selector("startRun"))
        if res["status"] != "confirmed":
            raise ChainError(f"startRun failed: {res.get('error')}")
        out = self._eth_call(self.market, selector("currentRun"))
        self.run = decode(["uint64"], out)[0]
        return self.run

    def commit(self, rec, sim) -> dict:
        data = selector("commit") + encode(["uint64", "bytes32"],
                                           [sim.slot_start(rec.g), bytes.fromhex(rec.commitment[2:])])
        return self._public(self._send(self.market, data))

    def settle(self, rec, sim) -> dict:
        readings = [
            (r.meter_id, r.import_wh, r.export_wh, bytes.fromhex(r.signature[2:]))
            for _, r in sorted(rec.readings.items())
        ]
        trades = [(t.seller, t.buyer, t.injected_wh, t.delivered_wh) for t in rec.allocation.trades]
        data = selector("settle") + encode(
            ["uint64", "uint32", f"{TRADE}[]", f"{READING}[]"],
            [sim.slot_start(rec.g), rec.clearing.price or 0, trades, readings],
        )
        res = self._send(self.market, data)
        if res["status"] == "confirmed":
            on_chain = {}
            for log in res["_logs"]:
                if log["topics"][0].lower() == HOUSEHOLD_SETTLED and log["address"].lower() == self.market.lower():
                    meter = int(log["topics"][3], 16)
                    market_mp, imbalance_mp = decode(["int256", "int256"], bytes.fromhex(log["data"][2:]))
                    on_chain[meter] = (market_mp, imbalance_mp)
            engine = {h: (s.market_mp, s.imbalance_mp) for h, s in rec.settlement.households.items()}
            res["matches_engine"] = on_chain == engine
            res["households_settled"] = len(on_chain)
        return self._public(res)

    @staticmethod
    def _public(res: dict) -> dict:
        return {k: v for k, v in res.items() if not k.startswith("_")}

    def status(self) -> dict:
        return {"connected": True, "chain_id": self.chain_id, "rpc": self.rpc, "market": self.market,
                "registry": self.registry, "block": self.last_block, "run": self.run, "explorer": self.explorer}
