// Server-only helpers for route handlers. Never import from a client component.
import { readFileSync } from "node:fs";
import path from "node:path";

export const SIM_URL = process.env.SIM_URL ?? "http://127.0.0.1:8000";

const OFFLINE = "The market engine is not running. Start it with: python -m sim.api";

/** Forward a request to the Python engine and relay its answer unchanged. */
export async function proxy(pathname: string, init?: RequestInit): Promise<Response> {
  try {
    const r = await fetch(`${SIM_URL}${pathname}`, { ...init, cache: "no-store" });
    const body = await r.text();
    return new Response(body, {
      status: r.status,
      headers: { "content-type": r.headers.get("content-type") ?? "application/json" },
    });
  } catch {
    return Response.json({ detail: OFFLINE }, { status: 503 });
  }
}

interface MarketConfig {
  feed_in_tariff_paise_per_kwh: number;
  retail_tariff_paise_per_kwh: number;
  wheeling_charge_paise_per_kwh: number;
}

/** The same config/market.json the Python engine and the contract deployment read. */
export function marketConfig(): MarketConfig {
  const file = process.env.MARKET_CONFIG ?? path.join(process.cwd(), "..", "config", "market.json");
  return JSON.parse(readFileSync(file, "utf8")) as MarketConfig;
}

/**
 * Band check, layer 1 of 3 (then the Python engine, then the settlement contract).
 * Returns the interface message when the price is outside (feed-in, retail - wheeling).
 */
export function bandError(pricePaise: unknown): string | null {
  const c = marketConfig();
  const lo = c.feed_in_tariff_paise_per_kwh;
  const hi = c.retail_tariff_paise_per_kwh - c.wheeling_charge_paise_per_kwh;
  if (typeof pricePaise === "number" && Number.isInteger(pricePaise) && pricePaise > lo && pricePaise < hi) {
    return null;
  }
  return (
    `Price must sit between ₹${(lo / 100).toFixed(2)} and ₹${(hi / 100).toFixed(2)} per kWh. ` +
    "Outside that range the grid is the better deal."
  );
}
