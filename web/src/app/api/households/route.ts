import { proxy } from "@/lib/server";

export const dynamic = "force-dynamic";

export function GET() {
  return proxy("/api/households");
}
