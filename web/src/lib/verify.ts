// Independent verification in the browser. Uses viem, not the engine's code,
// to recompute the settlement commitment and recover each meter signature.
// The encodings mirror sim/crypto.py and contracts/src/EnergyMarket.sol.
import { encodeAbiParameters, keccak256, recoverTypedDataAddress, type Hex } from "viem";
import type { Feeder, SlotDetail } from "./types";

export const READING_TYPES = {
  MeterReading: [
    { name: "meterId", type: "uint32" },
    { name: "slotStart", type: "uint64" },
    { name: "importWh", type: "uint64" },
    { name: "exportWh", type: "uint64" },
  ],
} as const;

export function commitmentOf(slot: SlotDetail): Hex {
  const encoded = encodeAbiParameters(
    [
      { type: "uint64" },
      { type: "uint32" },
      {
        type: "tuple[]",
        components: [{ type: "uint32" }, { type: "uint32" }, { type: "uint64" }, { type: "uint64" }],
      },
    ],
    [
      BigInt(slot.slot_start),
      slot.price ?? 0,
      slot.trades.map((t) => [t.seller, t.buyer, BigInt(t.injected_wh), BigInt(t.delivered_wh)] as const),
    ],
  );
  return keccak256(encoded);
}

export interface BrowserCheck {
  commitment: Hex;
  commitmentMatches: boolean;
  readings: { meter: number; recovered: string; registered: string; ok: boolean }[];
  priceInBand: boolean;
}

export async function verifySlot(slot: SlotDetail, feeder: Feeder): Promise<BrowserCheck> {
  const commitment = commitmentOf(slot);
  const domain = {
    name: "LocalEnergyMarket",
    version: "1",
    chainId: feeder.sim.chain_id,
    verifyingContract: feeder.sim.verifying_contract as Hex,
  } as const;
  const readings = await Promise.all(
    (slot.readings ?? []).map(async (r) => {
      const recovered = await recoverTypedDataAddress({
        domain,
        types: READING_TYPES,
        primaryType: "MeterReading",
        message: {
          meterId: r.meter,
          slotStart: BigInt(slot.slot_start),
          importWh: BigInt(r.import_wh),
          exportWh: BigInt(r.export_wh),
        },
        signature: r.signature as Hex,
      });
      const registered = feeder.households.find((h) => h.id === r.meter)?.meter_address ?? "";
      return { meter: r.meter, recovered, registered, ok: recovered.toLowerCase() === registered.toLowerCase() };
    }),
  );
  const t = feeder.tariff;
  return {
    commitment,
    commitmentMatches: commitment.toLowerCase() === slot.commitment.toLowerCase(),
    readings,
    priceInBand: slot.price == null || (slot.price > t.feed_in && slot.price < t.retail - t.wheeling),
  };
}
