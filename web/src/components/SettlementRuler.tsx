"use client";

import Link from "next/link";
import { kwh, price, slotEnd, slotLabel } from "@/lib/format";
import type { SlotSummary } from "@/lib/types";

/**
 * The 48-slot settlement ruler: one tick per half-hour settlement period,
 * numbered 01-48 because the period index is a real market concept.
 * Settled and verified = armed green; in delivery = highlighted; everything
 * else is etched. A settled slot that failed verification shows alarm red.
 */
export function SettlementRuler({
  slots,
  volumeKey = "injected_wh",
  linkSettled = true,
  values,
  scaleFloorWh = 2000,
}: {
  slots: SlotSummary[];
  volumeKey?: "injected_wh" | "volume_wh";
  linkSettled?: boolean;
  scaleFloorWh?: number;
  /** Optional per-slot bar values (Wh, signed: + export amber, − import cyan) instead of market volume. */
  values?: (number | null)[];
}) {
  const vols = values ?? slots.map((s) => s[volumeKey] ?? null);
  // A floor on the scale so one tiny trade does not draw as a full-height bar.
  const max = Math.max(scaleFloorWh, ...vols.map((v) => Math.abs(v ?? 0)));

  return (
    <div>
      <div className="grid gap-px" style={{ gridTemplateColumns: "repeat(48, minmax(0, 1fr))" }}>
        {slots.map((s, i) => {
          const v = vols[i];
          const h = v ? Math.max(2, (Math.abs(v) / max) * 100) : 0;
          const settled = s.status === "settled";
          const tick =
            settled && s.verified === false
              ? "bg-alarm"
              : settled
                ? "bg-armed"
                : s.status === "delivery"
                  ? "bg-label"
                  : "bg-panel-etch";
          const title = [
            `SP ${slotLabel(s.slot)} · ${s.time}–${slotEnd(s.time)} AEST`,
            s.status === "delivery" ? "in delivery" : s.status === "open" ? "book open" : s.status,
            s.price != null ? `${price(s.price)}/kWh` : null,
            s.injected_wh != null ? `${kwh(s.injected_wh)} kWh traded` : null,
            settled ? (s.verified ? "verified" : "VERIFICATION FAILED") : null,
          ]
            .filter(Boolean)
            .join(" · ");
          const cell = (
            <div className="group flex flex-col" title={title}>
              <div className="flex h-10 items-end justify-center">
                {h > 0 && (
                  <div
                    className={v != null && v < 0 ? "w-3/5 bg-import" : "w-3/5 bg-export"}
                    style={{ height: `${h}%`, opacity: s.status === "future" ? 0.35 : 1 }}
                  />
                )}
              </div>
              <div className={`mt-1 h-3 ${tick} ${s.status === "open" ? "outline outline-1 -outline-offset-1 outline-label-muted" : ""}`} />
              <div
                className={`num mt-1 text-center text-[10px] leading-none ${
                  s.status === "delivery" ? "text-label" : "text-label-muted"
                } ${s.slot % 4 === 1 || s.status === "delivery" ? "" : "max-lg:invisible"}`}
              >
                {slotLabel(s.slot)}
              </div>
            </div>
          );
          return linkSettled && (settled || s.status === "delivery") ? (
            <Link key={s.g} href={`/settlement/${s.g}`} aria-label={title}>
              {cell}
            </Link>
          ) : (
            <div key={s.g}>{cell}</div>
          );
        })}
      </div>
      <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1 legend">
        <span className="flex items-center gap-1.5">
          <i className="inline-block h-2 w-3 bg-armed" /> settled · verified
        </span>
        <span className="flex items-center gap-1.5">
          <i className="inline-block h-2 w-3 bg-label" /> in delivery
        </span>
        <span className="flex items-center gap-1.5">
          <i className="inline-block h-2 w-3 bg-panel-etch outline outline-1 -outline-offset-1 outline-label-muted" /> book open
        </span>
        <span className="flex items-center gap-1.5">
          <i className="inline-block h-2 w-3 bg-panel-etch" /> not yet
        </span>
        <span className="flex items-center gap-1.5">
          <i className="inline-block h-2 w-3 bg-alarm" /> verification failed
        </span>
      </div>
    </div>
  );
}
