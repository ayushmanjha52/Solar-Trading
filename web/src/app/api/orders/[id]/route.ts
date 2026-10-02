import { proxy } from "@/lib/server";

export const dynamic = "force-dynamic";

export function DELETE(_req: Request, { params }: { params: { id: string } }) {
  return proxy(`/api/orders/${encodeURIComponent(params.id)}`, { method: "DELETE" });
}
