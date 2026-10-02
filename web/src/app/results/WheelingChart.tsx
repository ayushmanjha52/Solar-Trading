"use client";

import { CartesianGrid, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

interface Curve {
  wheeling_paise: number[];
  saving_inr: number[];
  saving_zero_at_paise: number | null;
}

const LABEL: Record<string, string> = { newsvendor: "Newsvendor quantile", seasonal_naive: "Seasonal naive" };
const COLOR: Record<string, string> = { newsvendor: "var(--flow-export)", seasonal_naive: "var(--label-muted)" };

export function WheelingChart({ curves }: { curves: Record<string, Curve> }) {
  const keys = Object.keys(curves);
  const rows = curves[keys[0]].wheeling_paise.map((w, i) => {
    const row: Record<string, number> = { w: w / 100 };
    keys.forEach((k) => (row[k] = curves[k].saving_inr[i]));
    return row;
  });
  return (
    <div className="h-72 border border-panel-etch bg-panel-raised p-3" aria-label="Households' saving against wheeling charge">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={rows} margin={{ top: 8, right: 16, bottom: 18, left: 8 }}>
          <CartesianGrid stroke="var(--panel-etch)" vertical={false} />
          <XAxis
            dataKey="w"
            type="number"
            domain={[0, "dataMax"]}
            ticks={[0, 1, 2, 3, 4, 5]}
            tickFormatter={(v: number) => v.toFixed(1)}
            stroke="var(--panel-etch)"
            label={{ value: "wheeling charge, ₹ per kWh", position: "insideBottom", offset: -10, fill: "var(--label-muted)" }}
          />
          <YAxis
            stroke="var(--panel-etch)"
            tickFormatter={(v: number) => `${v < 0 ? "−" : ""}₹${Math.abs(Math.round(v)).toLocaleString("en-IN")}`}
            width={70}
          />
          <ReferenceLine y={0} stroke="var(--label)" />
          <Tooltip
            contentStyle={{ background: "var(--panel-base)", border: "1px solid var(--panel-etch)", fontFamily: "var(--font-mono)", fontSize: 11 }}
            labelFormatter={(v: number) => `wheeling ₹${Number(v).toFixed(2)}/kWh`}
            formatter={(v: number, k: string) => [`₹${Math.round(v).toLocaleString("en-IN")}`, LABEL[k] ?? k]}
          />
          <Legend verticalAlign="top" align="right" height={28} formatter={(k: string) => <span className="legend">{LABEL[k] ?? k}</span>} />
          {keys.map((k) => (
            <Line key={k} dataKey={k} stroke={COLOR[k]} strokeWidth={2} dot={{ r: 2.5 }} isAnimationActive={false} />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
