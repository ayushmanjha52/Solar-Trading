// Engine-free hosting: replay a recorded week of the market (sim/export_hosted.py).
//
// The market engine is a long-running process with its own clock, which a
// serverless host cannot run. The engine therefore records seven real days,
// and this module replays them on a loop timed by the wall clock, returning
// the same JSON shapes the engine's HTTP API returns (sim/views.py). Every
// visitor sees the same slot at the same moment. Nothing is re-computed: the
// books, trades, commitments, signed readings and settlements are the
// engine's own, and the signatures still verify in the browser.
//
// What cannot work without the engine: placing orders and moving the clock.
import { readFileSync } from "node:fs";
import path from "node:path";
import type { Feeder, HouseholdSlot, LedgerRow, SlotDetail, SlotStatus, SlotSummary } from "./types";

const DIR = path.join(process.cwd(), "data", "hosted");
const SLOTS = 48;
// Fixed origin for the replay clock, so every server instance agrees on the slot.
const EPOCH_S = Date.UTC(2026, 0, 1) / 1000;

export const HOSTED_ORDER_MESSAGE =
  "This hosted copy replays a recorded week of the market, so it cannot take orders. To trade, run the full market: clone the repository and run python demo.py.";
export const HOSTED_CLOCK_MESSAGE = "This hosted copy replays a recorded week on a fixed clock.";

export function isHosted(): boolean {
  return process.env.LEM_HOSTED === "1" || (process.env.VERCEL === "1" && !process.env.SIM_URL);
}

interface HouseholdArrays {
  p50: number[];
  p10: (number | null)[];
  p90: (number | null)[];
  load: number[];
  gen: number[];
}
interface DayFile {
  day: string;
  slots: SlotDetail[];
  households: Record<string, HouseholdArrays>;
}
interface Index {
  days: string[];
  slot_seconds: number;
  night_slot_seconds: number;
  daylight_slots: [number, number];
}
interface Week {
  index: Index;
  feeder: Feeder;
  days: DayFile[];
  timeline: SlotDetail[];
  starts: number[]; // seconds into the cycle at which each slot's gate closes
  cycle: number;
  byG: Map<number, number>;
}

let week: Week | null = null;

function load(): Week {
  if (week) return week;
  const read = (rel: string) => JSON.parse(readFileSync(path.join(DIR, rel), "utf8"));
  const index: Index = read("index.json");
  const feeder: Feeder = read("feeder.json");
  const days: DayFile[] = index.days.map((d) => read(`days/${d}.json`));
  const timeline = days.flatMap((d) => d.slots);
  const starts: number[] = [];
  let t = 0;
  for (const s of timeline) {
    starts.push(t);
    const day = s.slot >= index.daylight_slots[0] && s.slot <= index.daylight_slots[1];
    t += day ? index.slot_seconds : Math.min(index.slot_seconds, index.night_slot_seconds);
  }
  week = { index, feeder, days, timeline, starts, cycle: t, byG: new Map(timeline.map((s, i) => [s.g, i])) };
  return week;
}

/** Which slot is in delivery now, and when the current cycle began (unix seconds). */
function position(nowS = Date.now() / 1000) {
  const w = load();
  const into = (((nowS - EPOCH_S) % w.cycle) + w.cycle) % w.cycle;
  let lo = 0;
  let hi = w.starts.length - 1;
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1;
    if (w.starts[mid] <= into) lo = mid;
    else hi = mid - 1;
  }
  return { i: lo, cycleStart: nowS - into };
}

const dayOf = (i: number) => Math.floor(i / SLOTS);
const wrap = (i: number) => {
  const n = load().timeline.length;
  return ((i % n) + n) % n;
};

function statusOf(j: number, i: number): SlotStatus {
  if (j < i) return "settled";
  if (j === i) return "delivery";
  if (j === i + 1) return "open";
  return "future";
}

function detail(j: number, i: number, cycleStart: number): SlotDetail {
  const w = load();
  const s = w.timeline[j];
  const status = statusOf(j, i);
  const out: SlotDetail = { ...s, status, committed_at: cycleStart + w.starts[j], chain: {} };
  if (status !== "settled") {
    delete out.readings;
    delete out.settlement;
    out.verification = null;
    out.verified = null;
    delete out.saving_mp;
  }
  return out;
}

function summary(j: number, i: number): SlotSummary {
  const s = load().timeline[j];
  const status = statusOf(j, i);
  const base: SlotSummary = { g: s.g, slot: s.slot, time: s.time, status };
  if (status === "future") return base;
  return {
    ...base,
    price: s.price,
    volume_wh: s.volume_wh,
    injected_wh: s.injected_wh,
    delivered_wh: s.delivered_wh,
    n_trades: s.trades.length,
    verified: status === "settled" ? s.verified : null,
    ...(status === "settled" ? { saving_mp: s.saving_mp } : {}),
  };
}

export function clockView() {
  const w = load();
  const { i } = position();
  const s = w.timeline[i];
  return {
    g: s.g,
    day: s.day,
    slot: s.slot,
    slot_time: s.time,
    paused: false,
    slot_seconds: w.index.slot_seconds,
    first_day: w.index.days[0],
    last_day: w.index.days[w.index.days.length - 1],
    chain: { connected: false },
    controls_locked: true,
    hosted: true,
  };
}

export function feederView() {
  return load().feeder;
}

export function dayView() {
  const w = load();
  const { i } = position();
  const first = dayOf(i) * SLOTS;
  const slots = Array.from({ length: SLOTS }, (_, k) => summary(first + k, i));
  const settled = slots.map((s, k) => ({ s, d: w.timeline[first + k] })).filter((x) => x.s.status === "settled");
  return {
    day: w.days[dayOf(i)].day,
    first_g: w.timeline[first].g,
    slots,
    totals: {
      settled_slots: settled.length,
      injected_wh: settled.reduce((a, x) => a + (x.d.injected_wh ?? 0), 0),
      delivered_wh: settled.reduce((a, x) => a + (x.d.delivered_wh ?? 0), 0),
      trades: settled.reduce((a, x) => a + x.d.trades.length, 0),
      market_value_mp: settled.reduce((a, x) => a + (x.d.price ?? 0) * (x.d.injected_wh ?? 0), 0),
      saving_mp: settled.reduce((a, x) => a + (x.d.saving_mp ?? 0), 0),
      operator_mp: settled.reduce((a, x) => a + (x.d.settlement?.operator_mp ?? 0), 0),
      all_verified: settled.every((x) => x.d.verified),
    },
  };
}

export function liveView() {
  const w = load();
  const { i, cycleStart } = position();
  const current = detail(i, i, cycleStart);
  const prevIndex = i > 0 ? i - 1 : w.timeline.length - 1;
  const previous = { ...w.timeline[prevIndex], status: "settled" as const, committed_at: cycleStart + w.starts[prevIndex], chain: {} };
  const next = w.timeline[wrap(i + 1)];
  const positions: Record<string, { export_wh: number; import_wh: number }> = {};
  for (const t of current.trades) {
    (positions[t.seller] ??= { export_wh: 0, import_wh: 0 }).export_wh += t.injected_wh;
    (positions[t.buyer] ??= { export_wh: 0, import_wh: 0 }).import_wh += t.delivered_wh;
  }
  return {
    clock: clockView(),
    day: dayView(),
    current,
    previous,
    book: {
      g: next.g,
      slot: next.slot,
      time: next.time,
      orders: next.orders.map((o) => ({ ...o, fill_wh: null })),
      curves: next.curves,
    },
    positions,
  };
}

export function slotView(g: number): SlotDetail | null {
  const w = load();
  const j = w.byG.get(g);
  const { i, cycleStart } = position();
  if (j === undefined || j > i) return null;
  return detail(j, i, cycleStart);
}

export function ledgerView(limit = 96): LedgerRow[] {
  const w = load();
  const { i, cycleStart } = position();
  const rows: LedgerRow[] = [];
  for (let j = i; j >= 0 && rows.length < limit; j--) {
    const d = detail(j, i, cycleStart);
    rows.push({
      ...summary(j, i),
      day: d.day,
      commitment: d.commitment,
      committed_at: d.committed_at,
      readings: d.readings?.length ?? 0,
      verification: d.verification,
      chain: {},
    });
  }
  return rows;
}

function forecastAt(h: number, j: number) {
  const w = load();
  const k = wrap(j);
  const arr = w.days[dayOf(k)].households[String(h)];
  const s = k % SLOTS;
  const out: { forecast_net_wh: number; forecast_p10_wh?: number; forecast_p90_wh?: number } = { forecast_net_wh: arr.p50[s] };
  if (arr.p10[s] != null && arr.p90[s] != null) {
    out.forecast_p10_wh = arr.p10[s] as number;
    out.forecast_p90_wh = arr.p90[s] as number;
  }
  return out;
}

function settledFor(h: number, d: SlotDetail) {
  return d.settlement?.households.find((x) => x.household === h);
}

export function householdsView() {
  const w = load();
  const { i } = position();
  const first = dayOf(i) * SLOTS;
  const current = w.timeline[i];
  return w.feeder.households.map((hh) => {
    let sold = 0;
    let bought = 0;
    let saving = 0;
    for (let j = first; j < i; j++) {
      const s = settledFor(hh.id, w.timeline[j]);
      if (s) {
        sold += s.contracted_export_wh;
        bought += s.contracted_import_wh;
        saving += s.saving_mp;
      }
    }
    const exp = current.trades.filter((t) => t.seller === hh.id).reduce((a, t) => a + t.injected_wh, 0);
    const imp = current.trades.filter((t) => t.buyer === hh.id).reduce((a, t) => a + t.delivered_wh, 0);
    return { ...hh, sold_wh: sold, bought_wh: bought, saving_mp: saving, now_export_wh: exp, now_import_wh: imp, ...forecastAt(hh.id, i) };
  });
}

export function householdView(h: number) {
  const w = load();
  const hh = w.feeder.households.find((x) => x.id === h);
  if (!hh) return null;
  const { i } = position();
  const d = dayOf(i);
  const first = d * SLOTS;
  const arr = w.days[d].households[String(h)];
  const rows: HouseholdSlot[] = [];
  for (let k = 0; k < SLOTS; k++) {
    const j = first + k;
    const s = w.timeline[j];
    const status = statusOf(j, i);
    const row: HouseholdSlot = { g: s.g, slot: s.slot, time: s.time, status, ...forecastAt(h, j) };
    if (j <= i) {
      row.contracted_export_wh = s.trades.filter((t) => t.seller === h).reduce((a, t) => a + t.injected_wh, 0);
      row.contracted_import_wh = s.trades.filter((t) => t.buyer === h).reduce((a, t) => a + t.delivered_wh, 0);
      row.price = s.price;
    }
    if (status === "settled") {
      const st = settledFor(h, s)!;
      const r = s.readings!.find((x) => x.meter === h)!;
      Object.assign(row, {
        metered_net_wh: r.export_wh - r.import_wh,
        load_wh: arr.load[k],
        gen_wh: arr.gen[k],
        market_mp: st.market_mp,
        imbalance_mp: st.imbalance_mp,
        grid_only_mp: st.grid_only_mp,
        saving_mp: st.saving_mp,
        deviation_wh: st.deviation_wh,
        signature: r.signature,
        verified: s.verified ?? undefined,
      });
    }
    rows.push(row);
  }
  const settled = rows.filter((r) => r.status === "settled");
  const traded = (r: HouseholdSlot) => (r.contracted_export_wh ?? 0) > 0 || (r.contracted_import_wh ?? 0) > 0;
  return {
    household: hh,
    day: w.days[d].day,
    clock: clockView(),
    forecast_label: w.feeder.sim.forecast,
    slots: rows,
    totals: {
      sold_wh: settled.reduce((a, r) => a + (r.contracted_export_wh ?? 0), 0),
      bought_wh: settled.reduce((a, r) => a + (r.contracted_import_wh ?? 0), 0),
      market_mp: settled.reduce((a, r) => a + (r.market_mp ?? 0), 0),
      imbalance_mp: settled.reduce((a, r) => a + (r.imbalance_mp ?? 0), 0),
      grid_only_mp: settled.reduce((a, r) => a + (r.grid_only_mp ?? 0), 0),
      saving_mp: settled.reduce((a, r) => a + (r.saving_mp ?? 0), 0),
      short_slots: settled.filter((r) => (r.deviation_wh ?? 0) < -10 && traded(r)).length,
      long_slots: settled.filter((r) => (r.deviation_wh ?? 0) > 10 && traded(r)).length,
    },
    orders: [],
    upcoming: Array.from({ length: SLOTS }, (_, k) => {
      const j = i + 1 + k;
      const s = w.timeline[wrap(j)];
      return { g: s.g, day: s.day, slot: s.slot, time: s.time, ...forecastAt(h, j) };
    }),
  };
}
