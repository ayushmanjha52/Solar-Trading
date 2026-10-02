import { proxy } from "@/lib/server";

export const dynamic = "force-dynamic";

export function GET(_req: Request, { params }: { params: { g: string } }) {
  if (!/^\d+$/.test(params.g)) return Response.json({ detail: "Slot ids are numbers." }, { status: 404 });
  return proxy(`/api/slot/${params.g}`);
}
