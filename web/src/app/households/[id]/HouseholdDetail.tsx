"use client";

import Link from "next/link";
import {
  Bar,
  CartesianGrid,
  Cell,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { SettlementRuler } from "@/components/SettlementRuler";
import { EngineOffline, Figure, Hash, Loading, Panel } from "@/components/ui";
import { dayLabel, inr, inrSigned, kwh, kwhSigned, price, slotLabel } from "@/lib/format";
import type { HouseholdSlot, HouseholdView, SlotSummary } from "@/lib/types";
import { usePoll } from "@/lib/usePoll";

interface Row {
  slot: number;
  metered: number | null;
  forecast: number;
  contracted: number | null;
}

function ChartTip({ active, payload }: { active?: boolean; payload?: { payload: Row }[] }) {
  if (!active || !payload?.length) return null;
  const r = payload[0].payload;
  return (
    <div className="num border border-panel-etch bg-panel-base px-2 py-1.5 text-2xs leading-5 text-label">
      <div className="text-label-muted">SP {slotLabel(r.slot)}</div>
      <div>forecast {kwhSigned(r.forecast * 1000)} kWh</div>
      {r.contracted != null && <div>contracted {kwhSigned(r.contracted * 1000)} kWh</div>}
      {r.metered != null && <div>metered {kwhSigned(r.metered * 1000)} kWh</div>}
    </div>
  );
}

export function HouseholdDetail({ id }: { id: number }) {
  const { data, error } = usePoll<HouseholdView>(`/api/households/${id}`, 2000);
  if (error && !data) return <EngineOffline message={error} />;
  if (!data) return <Loading />;

  const { household: hh, slots, totals } = data;
  const rows: Row[] = slots.map((s) => ({
    slot: s.slot,
    metered: s.metered_net_wh != null ? s.metered_net_wh / 1000 : null,
    forecast: s.forecast_net_wh / 1000,
    contracted:
      s.contracted_export_wh != null ? ((s.contracted_export_wh ?? 0) - (s.contracted_import_wh ?? 0)) / 1000 : null,
  }));
  const rulerSlots: SlotSummary[] = slots.map((s) => ({
    g: s.g,
    slot: s.slot,
    time: s.time,
    status: s.status,
    price: s.price,
    verified: s.verified ?? null,
  }));
  const traded = slots.filter(
    (s: HouseholdSlot) => s.status === "settled" && ((s.contracted_export_wh ?? 0) > 0 || (s.contracted_import_wh ?? 0) > 0),
  );

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="legend">
            <Link href="/households" className="hover:text-label">
              Households
            </Link>{" "}
            / {hh.label}
          </div>
          <h1 className="display mt-1 text-2xl uppercase text-label">{hh.label}</h1>
          <p className="num mt-1 text-xs uppercase tracking-wider text-label-muted">
            {hh.pv ? `PV ${hh.pv_kwp.toFixed(2)} kWp` : "No PV"} · {hh.position_m.toFixed(0)} m from the transformer ·{" "}
            {hh.service_m.toFixed(0)} m service · Ausgrid customer #{hh.customer}, postcode {hh.postcode} ·{" "}
            {dayLabel(data.day)}
          </p>
        </div>
        <Link
          href={`/trade?h=${hh.id}`}
          className="num border border-label-muted px-3 py-1.5 text-2xs uppercase tracking-wider text-label hover:bg-panel-etch"
        >
          Trade as {hh.label}
        </Link>
      </div>

      <Panel title="Metered energy by slot · amber exported, cyan imported">
        <SettlementRuler slots={rulerSlots} values={slots.map((s) => s.metered_net_wh ?? null)} scaleFloorWh={500} />
      </Panel>

      <Panel title="Forecast, contract and meter">
        <div className="h-72" aria-label="Per-slot forecast, contracted position and metered net energy">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={rows} margin={{ top: 8, right: 12, bottom: 4, left: 0 }}>
              <CartesianGrid stroke="var(--panel-etch)" vertical={false} />
              <XAxis
                dataKey="slot"
                tickFormatter={(v: number) => slotLabel(v)}
                ticks={[1, 7, 13, 19, 25, 31, 37, 43, 48]}
                stroke="var(--panel-etch)"
                tickLine={false}
              />
              <YAxis stroke="var(--panel-etch)" tickLine={false} width={44} tickFormatter={(v: number) => v.toFixed(1)} />
              <ReferenceLine y={0} stroke="var(--label-muted)" />
              <Tooltip content={<ChartTip />} cursor={{ fill: "var(--panel-etch)", opacity: 0.4 }} />
              <Bar dataKey="metered" isAnimationActive={false} maxBarSize={12}>
                {rows.map((r) => (
                  <Cell key={r.slot} fill={(r.metered ?? 0) >= 0 ? "var(--flow-export)" : "var(--flow-import)"} />
                ))}
              </Bar>
              <Line dataKey="forecast" type="stepAfter" stroke="var(--label-muted)" strokeWidth={1.5} dot={false} isAnimationActive={false} />
              <Line dataKey="contracted" type="stepAfter" stroke="var(--label)" strokeWidth={2} dot={false} connectNulls={false} isAnimationActive={false} />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
        <div className="mt-2 flex flex-wrap gap-x-5 gap-y-1 legend">
          <span className="flex items-center gap-1.5">
            <i className="inline-block h-2.5 w-2 bg-export" />
            <i className="-ml-1 inline-block h-2.5 w-2 bg-import" /> metered, signed by the meter
          </span>
          <span className="flex items-center gap-1.5">
            <i className="inline-block h-0.5 w-4 bg-label-muted" /> forecast: same slot yesterday
          </span>
          <span className="flex items-center gap-1.5">
            <i className="inline-block h-0.5 w-4 bg-label" /> contracted at gate closure
          </span>
          <span>kWh per half hour; above zero exports, below zero imports.</span>
        </div>
      </Panel>

      <Panel title={`Today so far · ${slots.filter((s) => s.status === "settled").length} settled slots`}>
        <div className="grid grid-cols-2 gap-x-6 gap-y-4 md:grid-cols-4 xl:grid-cols-7">
          <Figure label="Sold" value={kwh(totals.sold_wh)} unit="kWh" tone="export" />
          <Figure label="Bought" value={kwh(totals.bought_wh)} unit="kWh" tone="import" />
          <Figure label="Market" value={inrSigned(totals.market_mp)} sub="pass 1, at cleared prices" />
          <Figure label="Imbalance" value={inrSigned(totals.imbalance_mp)} sub="pass 2, at grid tariffs" />
          <Figure label="Grid-only bill" value={inrSigned(totals.grid_only_mp)} sub="same meters, no market" tone="muted" />
          <Figure
            label="vs grid-only"
            value={inrSigned(totals.saving_mp)}
            tone={totals.saving_mp < 0 ? "alarm" : "label"}
          />
          <Figure label="Short · long" value={`${totals.short_slots} · ${totals.long_slots}`} sub="slots off contract" />
        </div>
      </Panel>

      <Panel title="Slots where this household traded" bodyClassName="p-0">
        {traded.length === 0 ? (
          <p className="p-4 text-sm text-label-muted">No settled trades yet today.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="num w-full text-xs">
              <thead>
                <tr className="legend border-b border-panel-etch text-left">
                  <th className="px-4 py-2 font-normal">Slot</th>
                  <th className="px-3 py-2 text-right font-normal">Price</th>
                  <th className="px-3 py-2 text-right font-normal">Forecast</th>
                  <th className="px-3 py-2 text-right font-normal">Contracted</th>
                  <th className="px-3 py-2 text-right font-normal">Metered</th>
                  <th className="px-3 py-2 text-right font-normal">Deviation</th>
                  <th className="px-3 py-2 text-right font-normal">Market</th>
                  <th className="px-3 py-2 text-right font-normal">Imbalance</th>
                  <th className="px-3 py-2 text-right font-normal">vs grid-only</th>
                  <th className="px-4 py-2 font-normal">Meter signature</th>
                </tr>
              </thead>
              <tbody>
                {traded.map((s) => {
                  const c = (s.contracted_export_wh ?? 0) - (s.contracted_import_wh ?? 0);
                  return (
                    <tr key={s.g} className="border-b border-panel-etch last:border-0">
                      <td className="px-4 py-2">
                        <Link href={`/settlement/${s.g}`} className="text-label underline decoration-panel-etch underline-offset-2">
                          SP {slotLabel(s.slot)}
                        </Link>{" "}
                        <span className="text-label-muted">{s.time}</span>
                      </td>
                      <td className="px-3 py-2 text-right">{price(s.price)}</td>
                      <td className="px-3 py-2 text-right text-label-muted">{kwhSigned(s.forecast_net_wh)}</td>
                      <td className={`px-3 py-2 text-right ${c > 0 ? "text-export" : "text-import"}`}>{kwhSigned(c)}</td>
                      <td className="px-3 py-2 text-right">{kwhSigned(s.metered_net_wh ?? 0)}</td>
                      <td
                        className={`px-3 py-2 text-right ${(s.deviation_wh ?? 0) < -10 ? "text-alarm" : "text-label-muted"}`}
                        title={(s.deviation_wh ?? 0) < 0 ? "short: settled at retail" : "long: settled at feed-in"}
                      >
                        {kwhSigned(s.deviation_wh ?? 0)}
                      </td>
                      <td className="px-3 py-2 text-right">{inrSigned(s.market_mp ?? 0)}</td>
                      <td className="px-3 py-2 text-right">{inrSigned(s.imbalance_mp ?? 0)}</td>
                      <td className={`px-3 py-2 text-right ${(s.saving_mp ?? 0) < 0 ? "text-alarm" : "text-label"}`}>
                        {inrSigned(s.saving_mp ?? 0)}
                      </td>
                      <td className="px-4 py-2">
                        <Hash value={s.signature} head={10} tail={4} />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      <Panel title="Meter">
        <div className="grid gap-4 md:grid-cols-2">
          <div>
            <div className="legend">Registered signing key (address)</div>
            <div className="mt-1 text-sm">
              <Hash value={hh.meter_address} head={42} tail={0} />
            </div>
            <p className="mt-2 text-xs leading-relaxed text-label-muted">
              Every half hour this meter signs its import and export (EIP-712, bound to the chain id and the settlement
              contract). Settlement accepts a reading only if its signature recovers to this address. That proves which
              key signed, not that the reading is true: the trust sits in the meter&apos;s secure element.
            </p>
          </div>
          <div>
            <div className="legend">Grid-only bill today</div>
            <div className="num mt-1 text-sm text-label">{inr(totals.grid_only_mp)}</div>
            <p className="mt-2 text-xs leading-relaxed text-label-muted">
              The counterfactual: the same signed readings billed at retail for import and feed-in for export, as if
              the market did not exist. Every saving on this page is measured against it.
            </p>
          </div>
        </div>
      </Panel>
    </div>
  );
}
