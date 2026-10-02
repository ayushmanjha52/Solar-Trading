"use client";

import Link from "next/link";
import { useState } from "react";
import { ClockControls } from "@/components/ClockControls";
import { FeederMimic } from "@/components/FeederMimic";
import { DepthLegend, MarketDepth } from "@/components/MarketDepth";
import { SettlementRuler } from "@/components/SettlementRuler";
import { SlotReadout } from "@/components/SlotReadout";
import { TradeTable } from "@/components/TradeTable";
import { Annunciator, EngineOffline, Figure, Loading, Panel } from "@/components/ui";
import { dayLabel, inr, inrSigned, kwh, pct, slotLabel } from "@/lib/format";
import type { Feeder, Live } from "@/lib/types";
import { usePoll } from "@/lib/usePoll";

export function ControlRoom() {
  const live = usePoll<Live>("/api/live", 1000);
  const feeder = usePoll<Feeder>("/api/feeder", 60_000);
  const [magnify, setMagnify] = useState(false);

  if ((live.error && !live.data) || (feeder.error && !feeder.data)) {
    return <EngineOffline message={live.error ?? feeder.error ?? ""} />;
  }
  if (!live.data || !feeder.data) return <Loading />;

  const { clock, day, current, previous, book, positions } = live.data;
  const f = feeder.data;
  const t = day.totals;
  const lostToday = t.injected_wh - t.delivered_wh;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="display text-2xl uppercase text-label">Control room</h1>
          <p className="num mt-1 text-xs uppercase tracking-wider text-label-muted">
            {f.name} · {f.households.length} households · {dayLabel(day.day)}
          </p>
        </div>
        <ClockControls clock={clock} onChange={live.refresh} />
      </div>

      <Panel
        title="Settlement periods · bar height = energy traded"
        right={<span className="legend">AEST · SP 01 starts 00:00</span>}
      >
        <SettlementRuler slots={day.slots} />
      </Panel>

      <Panel
        title={`Feeder mimic · SP ${slotLabel(current.slot)} trades`}
        right={
          <label className="legend flex cursor-pointer items-center gap-2">
            <input
              type="checkbox"
              checked={magnify}
              onChange={(e) => setMagnify(e.target.checked)}
              className="accent-[var(--label)]"
            />
            Magnify losses ×50
          </label>
        }
        bodyClassName="px-2 pb-3 pt-1"
      >
        <FeederMimic feeder={f} trades={current.trades} positions={positions} g={current.g} magnify={magnify} />
        <div className="mt-1 flex flex-wrap gap-x-5 gap-y-1 px-2 legend">
          <span className="flex items-center gap-1.5">
            <i className="inline-block h-2.5 w-2.5 border border-export" /> selling (injects)
          </span>
          <span className="flex items-center gap-1.5">
            <i className="inline-block h-2.5 w-2.5 border border-import" /> buying (draws)
          </span>
          <span className="flex items-center gap-1.5">
            <i className="inline-block h-[3px] w-4 bg-label-muted" /> rooftop PV
          </span>
          <span>
            Pulse width ∝ energy; it thins by the share lost as heat on its route
            {magnify ? ", drawn ×50 so the loss is visible" : ", drawn to scale"}.
          </span>
          <span>Topology is simulated; load and generation at each node are real.</span>
        </div>
      </Panel>

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-[minmax(0,1.05fr)_minmax(0,1fr)_minmax(0,1fr)]">
        <Panel title="Slot in delivery">
          <SlotReadout slot={current} previous={previous} tariff={f.tariff} chain={clock.chain} />
        </Panel>
        <Panel title={`Cleared book · SP ${slotLabel(current.slot)}`}>
          <MarketDepth curves={current.curves} tariff={f.tariff} cleared={{ price: current.price ?? null, volume_wh: current.volume_wh ?? 0 }} />
          <DepthLegend cleared={{ price: current.price ?? null, volume_wh: current.volume_wh ?? 0 }} />
          <div className="mt-4 max-h-56 overflow-y-auto">
            <TradeTable trades={current.trades} households={f.households} />
          </div>
        </Panel>
        <Panel
          title={`Open book · SP ${slotLabel(book.slot)} · ${book.time}`}
          right={
            <Link href="/trade" className="num text-2xs uppercase tracking-wider text-label underline decoration-panel-etch underline-offset-4">
              Place an order
            </Link>
          }
        >
          <MarketDepth curves={book.curves} tariff={f.tariff} />
          <DepthLegend />
          <p className="mt-3 text-xs text-label-muted">
            {book.orders.length > 0
              ? `${book.orders.filter((o) => o.side === "sell").length} offers and ${book.orders.filter((o) => o.side === "buy").length} bids. Gate closes when SP ${slotLabel(book.slot)} begins. ${
                  book.orders.some((o) => o.by === "visitor") ? "Includes visitor orders." : `Agents bid from: ${f.sim.forecast}.`
                }`
              : "No orders yet for this slot. Place a bid or an offer to open the book."}
          </p>
        </Panel>
      </div>

      <Panel title={`Today so far · ${t.settled_slots} of 48 slots settled`}>
        <div className="grid grid-cols-2 gap-x-6 gap-y-4 md:grid-cols-3 xl:grid-cols-6">
          <Figure label="Traded" value={kwh(t.injected_wh, 2)} unit="kWh" tone="export" />
          <Figure
            label="Lost as heat"
            value={kwh(lostToday, 3)}
            unit="kWh"
            sub={t.injected_wh ? `${pct(lostToday / t.injected_wh)} of traded` : undefined}
          />
          <Figure label="Trades" value={t.trades} />
          <Figure label="Market value" value={inr(t.market_value_mp)} />
          <Figure
            label="Households vs grid-only"
            value={inrSigned(t.saving_mp)}
            tone={t.saving_mp >= 0 ? "label" : "alarm"}
          />
          <Figure
            label="Cost of losses"
            value={inr(-t.operator_mp)}
            sub={f.tariff.wheeling ? "net of wheeling income" : "unrecovered: no wheeling charge"}
            tone="muted"
          />
        </div>
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <Annunciator
            label={t.settled_slots === 0 ? "Nothing settled yet" : t.all_verified ? "All settlements verified" : "Settlement mismatch"}
            state={t.settled_slots === 0 ? "idle" : t.all_verified ? "armed" : "alarm"}
          />
          <span className="text-xs text-label-muted">
            Savings compare each household&apos;s market and imbalance settlement with billing the same meter readings at
            retail and feed-in tariffs, with no market at all.
          </span>
        </div>
      </Panel>
    </div>
  );
}
