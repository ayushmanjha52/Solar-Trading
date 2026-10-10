import { householdsView, isHosted } from "@/lib/hosted";
import { proxy } from "@/lib/server";

export const dynamic = "force-dynamic";

export function GET() {
  if (isHosted()) return Response.json(householdsView());
  return proxy("/api/households");
}
