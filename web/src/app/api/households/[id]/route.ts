import { proxy } from "@/lib/server";

export const dynamic = "force-dynamic";

export function GET(_req: Request, { params }: { params: { id: string } }) {
  if (!/^\d+$/.test(params.id)) return Response.json({ detail: "Household ids are numbers." }, { status: 404 });
  return proxy(`/api/households/${params.id}`);
}
