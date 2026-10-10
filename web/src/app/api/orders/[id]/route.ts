import { HOSTED_ORDER_MESSAGE, isHosted } from "@/lib/hosted";
import { proxy } from "@/lib/server";

export const dynamic = "force-dynamic";

export function DELETE(_req: Request, { params }: { params: { id: string } }) {
  if (isHosted()) return Response.json({ detail: HOSTED_ORDER_MESSAGE }, { status: 503 });
  return proxy(`/api/orders/${encodeURIComponent(params.id)}`, { method: "DELETE" });
}
