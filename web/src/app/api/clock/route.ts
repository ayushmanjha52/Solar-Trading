import { clockView, HOSTED_CLOCK_MESSAGE, isHosted } from "@/lib/hosted";
import { proxy } from "@/lib/server";

export const dynamic = "force-dynamic";

const ACTIONS = new Set(["pause", "resume", "step", "speed", "jump"]);

export function GET() {
  if (isHosted()) return Response.json(clockView());
  return proxy("/api/clock");
}

/** Clock changes affect every visitor; the engine checks the operator token (X-Admin-Token) when one is configured. */
export async function POST(req: Request) {
  const body = await req.json().catch(() => null);
  if (!body || !ACTIONS.has(body.action)) {
    return Response.json({ detail: "Unknown clock action." }, { status: 422 });
  }
  if (isHosted()) return Response.json({ detail: HOSTED_CLOCK_MESSAGE }, { status: 403 });
  const headers: Record<string, string> = { "content-type": "application/json" };
  const token = req.headers.get("x-admin-token");
  if (token) headers["x-admin-token"] = token;
  return proxy("/api/clock", { method: "POST", headers, body: JSON.stringify(body) });
}
