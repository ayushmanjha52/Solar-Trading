import { proxy } from "@/lib/server";

export const dynamic = "force-dynamic";

const ACTIONS = new Set(["pause", "resume", "step", "speed", "jump"]);

export function GET() {
  return proxy("/api/clock");
}

export async function POST(req: Request) {
  const body = await req.json().catch(() => null);
  if (!body || !ACTIONS.has(body.action)) {
    return Response.json({ detail: "Unknown clock action." }, { status: 422 });
  }
  return proxy("/api/clock", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
}
