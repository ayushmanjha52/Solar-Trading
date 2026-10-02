"use client";

import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceDot,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { kwh, price } from "@/lib/format";
import type { Curves, Tariff } from "@/lib/types";

type Pt = { x: number; y: number };

/** Cumulative steps -> points for a stepAfter line: each price holds from the previous cumulative Wh. */
function steps(curve: [number, number][]): Pt[] {
  if (curve.length === 0) return [];
  const pts: Pt[] = [{ x: 0, y: curve[0][0] }];
  for (let i = 1; i < curve.length; i++) pts.push({ x: curve[i - 1][1], y: curve[i][0] });
  pts.push({ x: curve[curve.length - 1][1], y: curve[curve.length - 1][0] });
  return pts;
}

function TipContent({ active, payload }: { active?: boolean; payload?: { payload: Pt; name: string }[] }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="num border border-panel-etch bg-panel-base px-2 py-1 text-2xs text-label">
      {payload.map((p) => (
        <div key={p.name}>
          <span className={p.name === "supply" ? "text-export" : "text-import"}>{p.name}</span> {kwh(p.payload.x)} kWh at{" "}
          {price(p.payload.y)}
        </div>
      ))}
    </div>
  );
}

export function MarketDepth({
  curves,
  tariff,
  cleared,
  height = 240,
}: {
  curves: Curves;
  tariff: Tariff;
  cleared?: { price: number | null; volume_wh: number };
  height?: number;
}) {
  const supply = steps(curves.supply);
  const demand = steps(curves.demand);
  const maxX = Math.max(100, ...supply.map((p) => p.x), ...demand.map((p) => p.x));
  const ceilingLine = tariff.retail - tariff.wheeling;
  const yTicks: number[] = [];
  for (let p = Math.ceil(tariff.feed_in / 100) * 100; p <= tariff.retail; p += 100) yTicks.push(p);

  if (supply.length === 0 && demand.length === 0) {
    return (
      <div className="flex items-center justify-center text-sm text-label-muted" style={{ height }}>
        No orders yet for this slot. Place a bid or an offer to open the book.
      </div>
    );
  }

  return (
    <div style={{ height }} aria-label="Order book depth: cumulative supply and demand against price">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart margin={{ top: 8, right: 12, bottom: 18, left: 0 }}>
          <CartesianGrid stroke="var(--panel-etch)" vertical={false} />
          <XAxis
            type="number"
            dataKey="x"
            domain={[0, maxX]}
            tickFormatter={(v: number) => (v / 1000).toFixed(1)}
            stroke="var(--panel-etch)"
            tickLine={false}
            label={{ value: "cumulative kWh", position: "insideBottom", offset: -10, fill: "var(--label-muted)" }}
          />
          <YAxis
            type="number"
            dataKey="y"
            domain={[tariff.feed_in - 40, tariff.retail + 40]}
            ticks={yTicks}
            tickFormatter={(v: number) => (v / 100).toFixed(2)}
            stroke="var(--panel-etch)"
            tickLine={false}
            width={44}
          />
          <ReferenceLine
            y={tariff.feed_in}
            stroke="var(--label-muted)"
            label={{ value: `feed-in ${price(tariff.feed_in)}`, position: "insideBottomRight", fill: "var(--label-muted)" }}
          />
          <ReferenceLine
            y={ceilingLine}
            stroke="var(--label-muted)"
            label={{
              value: tariff.wheeling ? `retail − wheeling ${price(ceilingLine)}` : `retail ${price(ceilingLine)}`,
              position: "insideTopRight",
              fill: "var(--label-muted)",
            }}
          />
          <Tooltip content={<TipContent />} cursor={{ stroke: "var(--label-muted)", strokeWidth: 1 }} />
          <Line
            name="supply"
            data={supply}
            dataKey="y"
            type="stepAfter"
            stroke="var(--flow-export)"
            strokeWidth={2}
            dot={false}
            isAnimationActive={false}
          />
          <Line
            name="demand"
            data={demand}
            dataKey="y"
            type="stepAfter"
            stroke="var(--flow-import)"
            strokeWidth={2}
            dot={false}
            isAnimationActive={false}
          />
          {cleared && cleared.price != null && (
            <ReferenceDot
              x={cleared.volume_wh}
              y={cleared.price}
              r={5}
              fill="var(--label)"
              stroke="var(--panel-raised)"
              strokeWidth={2}
            />
          )}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export function DepthLegend({ cleared }: { cleared?: { price: number | null; volume_wh: number } }) {
  return (
    <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 legend">
      <span className="flex items-center gap-1.5">
        <i className="inline-block h-0.5 w-4 bg-export" /> offers (sell)
      </span>
      <span className="flex items-center gap-1.5">
        <i className="inline-block h-0.5 w-4 bg-import" /> bids (buy)
      </span>
      {cleared?.price != null && (
        <span className="flex items-center gap-1.5">
          <i className="inline-block h-2 w-2 rounded-full bg-label" /> cleared {price(cleared.price)} · {kwh(cleared.volume_wh)} kWh
        </span>
      )}
    </div>
  );
}
