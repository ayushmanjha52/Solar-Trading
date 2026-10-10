import { readRepoJson } from "@/lib/server";

export const dynamic = "force-dynamic";

interface Row {
  model: string;
  volume: string;
  price: string;
  skill_vs_persistence: number;
  saving_inr_per_household_year: number;
}

/** Headline numbers from the offline results (ml/evaluate.py, sim/study.py), for the home page. */
export function GET() {
  const fc = readRepoJson<{ market_model: string; tables: Record<string, { rows: Row[] }> }>(
    "reports/forecasting/results.json",
    "forecasting.json",
  );
  const st = readRepoJson<{ strategies: Row[] }>("reports/study/results.json", "study.json");
  const best = fc?.tables?.["Feeder, as simulated"]?.rows.find((r) => r.model === fc.market_model);
  const p50 = st?.strategies.find((r) => r.volume === "Forecast P50" && r.price === "truthful");
  return Response.json({
    forecast_model: fc?.market_model ?? null,
    forecast_skill: best?.skill_vs_persistence ?? null,
    saving_per_home_year_inr: p50?.saving_inr_per_household_year ?? null,
  });
}
