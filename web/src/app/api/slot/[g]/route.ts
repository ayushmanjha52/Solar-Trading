import { isHosted, slotView } from "@/lib/hosted";
import { proxy } from "@/lib/server";

export const dynamic = "force-dynamic";

export function GET(_req: Request, { params }: { params: { g: string } }) {
  if (!/^\d+$/.test(params.g)) return Response.json({ detail: "Slot ids are numbers." }, { status: 404 });
  if (isHosted()) {
    const view = slotView(Number(params.g));
    return view
      ? Response.json(view)
      : Response.json({ detail: "No record for that slot. It has not cleared yet in this replay." }, { status: 404 });
  }
  return proxy(`/api/slot/${params.g}`);
}
