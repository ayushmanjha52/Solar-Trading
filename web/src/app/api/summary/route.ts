import { existsSync, readFileSync } from "node:fs";
import path from "node:path";

export const dynamic = "force-dynamic";

function read(rel: string) {
  const file = path.join(process.cwd(), "..", rel);
  return existsSync(file) ? JSON.parse(readFileSync(file, "utf8")) : null;
}

/** Headline numbers from the offline results (ml/evaluate.py, sim/study.py), for the home page. */
export function GET() {
  const fc = read("reports/forecasting/results.json");
  const st = read("reports/study/results.json");
  const feeder = fc?.tables?.["Feeder, as simulated"]?.rows ?? [];
  const best = feeder.find((r: { model: string }) => r.model === fc?.market_model);
  const p50 = st?.strategies?.find((r: { volume: string; price: string }) => r.volume === "Forecast P50" && r.price === "truthful");
  return Response.json({
    forecast_model: fc?.market_model ?? null,
    forecast_skill: best?.skill_vs_persistence ?? null,
    saving_per_home_year_inr: p50?.saving_inr_per_household_year ?? null,
  });
}
