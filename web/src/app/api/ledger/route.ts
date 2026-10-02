import { proxy } from "@/lib/server";

export const dynamic = "force-dynamic";

export function GET(req: Request) {
  const limit = new URL(req.url).searchParams.get("limit") ?? "96";
  return proxy(`/api/ledger?limit=${encodeURIComponent(limit)}`);
}
