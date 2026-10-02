"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { kwh, kwhSigned, pct } from "@/lib/format";
import type { Feeder, Household, Trade } from "@/lib/types";

// Conductor resistances, matching market/losses.py. Only their ratio matters
// here: the pulse thins in proportion to the resistance it has crossed.
const R_BACKBONE = 0.32; // ohm/km, 95 mm² Al
const R_SERVICE = 1.15; // ohm/km, 16 mm² Cu

const W = 1200;
const H = 330;
const BUS_Y = 160;
const X0 = 104;
const X1 = 1164;
const BOX_W = 48;
const BOX_H = 38;
const ABOVE_TOP = 44;
const BELOW_TOP = 238;
const STUB = 16;
const PULSE_MS = 1700;
const STAGGER_MS = 70;
const DASH = 30;
const MAGNIFY = 50;

interface Node {
  h: Household;
  tapX: number;
  boxX: number; // centre
  above: boolean;
}

/** Spread boxes so they never overlap, keeping order, each cluster centred on its taps. */
function spread(desired: number[], gap: number, min: number, max: number): number[] {
  type C = { start: number; n: number; centre: number; sum: number };
  const cs: C[] = [];
  desired.forEach((d, i) => {
    cs.push({ start: i, n: 1, centre: d, sum: d });
    while (cs.length > 1) {
      const b = cs[cs.length - 1];
      const a = cs[cs.length - 2];
      const aRight = a.centre + ((a.n - 1) / 2) * gap;
      const bLeft = b.centre - ((b.n - 1) / 2) * gap;
      if (bLeft - aRight >= gap) break;
      const merged = { start: a.start, n: a.n + b.n, sum: a.sum + b.sum, centre: 0 };
      merged.centre = merged.sum / merged.n;
      cs.splice(cs.length - 2, 2, merged);
    }
  });
  const out: number[] = [];
  cs.forEach((c) => {
    for (let k = 0; k < c.n; k++) out.push(c.centre + (k - (c.n - 1) / 2) * gap);
  });
  const shiftLo = Math.max(0, min - out[0]);
  const shiftHi = Math.min(0, max - out[out.length - 1]);
  return out.map((x) => x + shiftLo + shiftHi);
}

function layout(feeder: Feeder): Node[] {
  const scale = (X1 - X0) / feeder.backbone_m;
  const hs = [...feeder.households].sort((a, b) => a.position_m - b.position_m);
  const nodes: Node[] = hs.map((h, i) => ({ h, tapX: X0 + h.position_m * scale, boxX: 0, above: i % 2 === 0 }));
  for (const above of [true, false]) {
    const side = nodes.filter((n) => n.above === above);
    const xs = spread(
      side.map((n) => n.tapX),
      BOX_W + 10,
      X0 + BOX_W / 2,
      X1 - BOX_W / 2,
    );
    side.forEach((n, i) => (n.boxX = xs[i]));
  }
  return nodes;
}

function edgeY(n: Node) {
  return n.above ? ABOVE_TOP + BOX_H : BELOW_TOP;
}
function stubY(n: Node) {
  return n.above ? BUS_Y - STUB : BUS_Y + STUB;
}

interface Route {
  d: string;
  segLen: [number, number, number]; // drawn length: seller drop, busbar, buyer drop
  segR: [number, number, number]; // resistance of the same three segments
  trade: Trade;
  w0: number;
}

function route(s: Node, b: Node, t: Trade, maxInjected: number): Route {
  const dropS = Math.hypot(s.boxX - s.tapX, edgeY(s) - stubY(s)) + STUB;
  const dropB = Math.hypot(b.boxX - b.tapX, edgeY(b) - stubY(b)) + STUB;
  const bus = Math.abs(s.tapX - b.tapX);
  return {
    d: `M ${s.boxX} ${edgeY(s)} L ${s.tapX} ${stubY(s)} L ${s.tapX} ${BUS_Y} L ${b.tapX} ${BUS_Y} L ${b.tapX} ${stubY(b)} L ${b.boxX} ${edgeY(b)}`,
    segLen: [dropS, bus, dropB],
    segR: [
      R_SERVICE * s.h.service_m,
      R_BACKBONE * Math.abs(s.h.position_m - b.h.position_m),
      R_SERVICE * b.h.service_m,
    ],
    trade: t,
    w0: 2.5 + 9 * Math.sqrt(t.injected_wh / maxInjected),
  };
}

/** Share of the route's resistance crossed after travelling `dist` drawn units. */
function resistanceShare(r: Route, dist: number): number {
  const [a, b, c] = r.segLen;
  const [ra, rb, rc] = r.segR;
  const total = ra + rb + rc || 1;
  let crossed: number;
  if (dist <= a) crossed = ra * (dist / (a || 1));
  else if (dist <= a + b) crossed = ra + rb * ((dist - a) / (b || 1));
  else crossed = ra + rb + rc * Math.min(1, (dist - a - b) / (c || 1));
  return crossed / total;
}

function usePrefersReducedMotion() {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReduced(mq.matches);
    const on = () => setReduced(mq.matches);
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);
  return reduced;
}

export function FeederMimic({
  feeder,
  trades,
  positions,
  g,
  magnify,
}: {
  feeder: Feeder;
  trades: Trade[];
  positions: Record<string, { export_wh: number; import_wh: number }>;
  g: number;
  magnify: boolean;
}) {
  // The feeder and a cleared slot's trades never change once fetched, but every
  // poll returns fresh objects. Key the layout and the animation on content so a
  // poll mid-pulse does not restart it.
  const feederKey = JSON.stringify(feeder.households);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const nodes = useMemo(() => layout(feeder), [feederKey]);
  const byId = useMemo(() => new Map(nodes.map((n) => [n.h.id, n])), [nodes]);
  const reduced = usePrefersReducedMotion();
  const slotTrades = useRef<{ g: number; trades: Trade[] }>({ g, trades });
  if (slotTrades.current.g !== g) slotTrades.current = { g, trades };
  const pinned = slotTrades.current;
  const routes = useMemo(() => {
    const maxInjected = Math.max(1, ...pinned.trades.map((t) => t.injected_wh));
    return pinned.trades
      .filter((t) => byId.has(t.seller) && byId.has(t.buyer))
      .map((t) => route(byId.get(t.seller)!, byId.get(t.buyer)!, t, maxInjected));
  }, [pinned, byId]);
  const pathRefs = useRef<(SVGPathElement | null)[]>([]);
  const magnifyRef = useRef(magnify);
  magnifyRef.current = magnify;

  // One orchestrated moment per clearing: every trade's pulse traverses its route once.
  useEffect(() => {
    if (reduced || routes.length === 0) return;
    const els = pathRefs.current.slice(0, routes.length);
    const lengths = els.map((el) => (el ? el.getTotalLength() : 0));
    const start = performance.now();
    let raf = 0;
    const frame = (now: number) => {
      let running = false;
      routes.forEach((r, i) => {
        const el = els[i];
        if (!el) return;
        const P = lengths[i];
        const t = (now - start - i * STAGGER_MS) / PULSE_MS;
        if (t < 0) {
          el.style.opacity = "0";
          running = true;
          return;
        }
        if (t > 1.15) {
          el.style.opacity = "0";
          return;
        }
        running = true;
        const head = Math.min(1, t) * P;
        const visible = Math.min(1, r.trade.loss_fraction * (magnifyRef.current ? MAGNIFY : 1));
        const w = r.w0 * (1 - Math.min(0.92, visible) * resistanceShare(r, head));
        el.style.opacity = t > 1 ? String(1 - (t - 1) / 0.15) : "1";
        el.setAttribute("stroke-dasharray", `${DASH} ${P + DASH}`);
        el.setAttribute("stroke-dashoffset", String(DASH - head));
        el.setAttribute("stroke-width", w.toFixed(2));
      });
      if (running) raf = requestAnimationFrame(frame);
    };
    raf = requestAnimationFrame(frame);
    return () => cancelAnimationFrame(raf);
  }, [g, routes, reduced]);

  const ticks = [];
  for (let m = 0; m <= feeder.backbone_m; m += 50) ticks.push(m);
  const scale = (X1 - X0) / feeder.backbone_m;

  return (
    <div className="overflow-x-auto">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="block w-full min-w-[880px]"
        role="img"
        aria-label={`Feeder mimic: ${feeder.households.length} households on a ${feeder.backbone_m} metre LV backbone, ${routes.length} trades this slot.`}
      >
        <defs>
          <marker id="arrow" viewBox="0 0 8 8" refX="6" refY="4" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
            <path d="M0,0 L8,4 L0,8 z" fill="var(--flow-export)" />
          </marker>
        </defs>

        {/* Transformer and feeder head */}
        <g>
          <line x1={20} y1={BUS_Y} x2={36} y2={BUS_Y} stroke="var(--label-muted)" strokeWidth={2} />
          <circle cx={50} cy={BUS_Y} r={14} fill="none" stroke="var(--label)" strokeWidth={1.5} />
          <circle cx={70} cy={BUS_Y} r={14} fill="none" stroke="var(--label)" strokeWidth={1.5} />
          <text x={60} y={BUS_Y - 26} textAnchor="middle" className="num" fontSize={11} fill="var(--label)">
            TX
          </text>
          <text x={60} y={BUS_Y + 34} textAnchor="middle" className="num" fontSize={10} fill="var(--label-muted)">
            11/0.415 kV
          </text>
          <line x1={84} y1={BUS_Y} x2={X1 + 12} y2={BUS_Y} stroke="var(--label-muted)" strokeWidth={3} />
          <line x1={X1 + 12} y1={BUS_Y - 8} x2={X1 + 12} y2={BUS_Y + 8} stroke="var(--label-muted)" strokeWidth={2} />
        </g>

        {/* Service drops and household nodes */}
        {nodes.map((n) => {
          const pos = positions[String(n.h.id)];
          const exp = pos?.export_wh ?? 0;
          const imp = pos?.import_wh ?? 0;
          const tone = exp > 0 ? "var(--flow-export)" : imp > 0 ? "var(--flow-import)" : "var(--panel-etch)";
          const text = exp > 0 ? "var(--flow-export)" : imp > 0 ? "var(--flow-import)" : "var(--label-muted)";
          const top = n.above ? ABOVE_TOP : BELOW_TOP;
          return (
            <g key={n.h.id}>
              <title>
                {`${n.h.label} · ${n.h.pv ? `PV ${n.h.pv_kwp.toFixed(2)} kWp` : "no PV"} · ${n.h.position_m.toFixed(0)} m from the transformer, ${n.h.service_m.toFixed(0)} m service`}
              </title>
              <polyline
                points={`${n.tapX},${BUS_Y} ${n.tapX},${stubY(n)} ${n.boxX},${edgeY(n)}`}
                fill="none"
                stroke="var(--label-muted)"
                strokeWidth={1}
              />
              <circle cx={n.tapX} cy={BUS_Y} r={2.5} fill="var(--label)" />
              <rect x={n.boxX - BOX_W / 2} y={top} width={BOX_W} height={BOX_H} fill="var(--panel-base)" stroke={tone} strokeWidth={1.5} rx={1} />
              <text x={n.boxX} y={top + 15} textAnchor="middle" className="num" fontSize={11} fill="var(--label)">
                {n.h.label}
              </text>
              <text x={n.boxX} y={top + 30} textAnchor="middle" className="num" fontSize={10} fill={text}>
                {exp > 0 ? kwhSigned(exp, 2) : imp > 0 ? kwhSigned(-imp, 2) : "—"}
              </text>
              {n.h.pv && (
                // Rooftop PV: a panel sitting on the house's roof line.
                <rect aria-hidden x={n.boxX - 12} y={top - 6} width={24} height={3} fill="var(--label-muted)" />
              )}
            </g>
          );
        })}

        {/* Trades: animated pulses, or static arrows when motion is reduced */}
        {routes.map((r, i) =>
          reduced ? (
            <path
              key={`${g}-${i}`}
              d={r.d}
              fill="none"
              stroke="var(--flow-export)"
              strokeWidth={Math.max(1.5, r.w0 * 0.6)}
              strokeOpacity={0.75}
              markerEnd="url(#arrow)"
            >
              <title>{`${kwh(r.trade.injected_wh)} kWh injected, ${kwh(r.trade.delivered_wh)} kWh received (${pct(r.trade.loss_fraction)} lost)`}</title>
            </path>
          ) : (
            <path
              key={`${g}-${i}`}
              ref={(el) => {
                pathRefs.current[i] = el;
              }}
              d={r.d}
              fill="none"
              stroke="var(--flow-export)"
              strokeLinecap="butt"
              strokeLinejoin="round"
              strokeWidth={r.w0}
              style={{ opacity: 0 }}
            />
          ),
        )}

        {/* Distance from the transformer */}
        <g>
          <line x1={X0} y1={H - 16} x2={X1} y2={H - 16} stroke="var(--panel-etch)" strokeWidth={1} />
          {ticks.map((m) => (
            <g key={m}>
              <line x1={X0 + m * scale} y1={H - 20} x2={X0 + m * scale} y2={H - 12} stroke="var(--label-muted)" strokeWidth={1} />
              <text x={X0 + m * scale} y={H - 1} textAnchor="middle" className="num" fontSize={10} fill="var(--label-muted)">
                {m === 0 ? "0 m" : m}
              </text>
            </g>
          ))}
        </g>
      </svg>
    </div>
  );
}
