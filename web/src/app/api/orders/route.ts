import { bandError, proxy } from "@/lib/server";

export const dynamic = "force-dynamic";

export function GET() {
  return proxy("/api/orders");
}

/**
 * Place an order. This route is the first of three band checks: it refuses
 * an out-of-band price before the engine sees it. The engine checks again
 * when it accepts the order and when it clears, and the settlement contract
 * checks the cleared price once more on chain.
 */
export async function POST(req: Request) {
  const body = await req.json().catch(() => null);
  if (!body) return Response.json({ detail: "Send the order as JSON." }, { status: 400 });

  const { household, g, side, qty_wh, price } = body;
  if (side !== "buy" && side !== "sell") {
    return Response.json({ detail: "Choose Sell surplus or Buy energy." }, { status: 422 });
  }
  if (![household, g, qty_wh].every((v) => Number.isInteger(v))) {
    return Response.json({ detail: "Household, slot and quantity must be whole numbers." }, { status: 422 });
  }
  if (qty_wh <= 0) {
    return Response.json({ detail: "Quantity must be more than zero." }, { status: 422 });
  }
  const band = bandError(price);
  if (band) return Response.json({ detail: band }, { status: 422 });

  return proxy("/api/orders", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ household, g, side, qty_wh, price }),
  });
}
