"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { dayLabel, slotEnd, slotLabel } from "@/lib/format";
import type { Clock } from "@/lib/types";
import { usePoll } from "@/lib/usePoll";

const LINKS = [
  { href: "/", label: "Control room" },
  { href: "/trade", label: "Trade" },
  { href: "/households", label: "Households" },
  { href: "/settlement", label: "Settlement" },
  { href: "/method", label: "Method" },
];

function ClockBadge() {
  const { data, error } = usePoll<Clock>("/api/clock", 2000);
  if (error && !data) {
    return (
      <span className="num border border-alarm px-2 py-1 text-2xs uppercase tracking-wider text-alarm" title={error}>
        Engine offline
      </span>
    );
  }
  if (!data) return <span className="legend">Connecting…</span>;
  return (
    <span className="num flex items-center gap-3 text-2xs uppercase tracking-wider text-label-muted">
      <span className={data.paused ? "text-label-muted" : "text-label"}>{data.paused ? "Paused" : "Sim"}</span>
      <span>{dayLabel(data.day)}</span>
      <span className="text-label">
        SP {slotLabel(data.slot)} · {data.slot_time}–{slotEnd(data.slot_time)} AEST
      </span>
      <span
        className={data.chain.connected ? "text-armed" : "text-label-muted"}
        title={data.chain.connected ? `Anchoring to chain ${data.chain.chain_id}` : "No chain connected"}
      >
        {data.chain.connected ? `Chain ${data.chain.chain_id}` : "No chain"}
      </span>
    </span>
  );
}

export function Nav() {
  const path = usePathname();
  return (
    <header className="border-b border-panel-etch bg-panel-base">
      <div className="mx-auto flex max-w-[1440px] flex-wrap items-center gap-x-8 gap-y-3 px-4 py-3 md:px-6">
        <Link href="/" className="display flex items-center gap-2 text-sm uppercase tracking-wide text-label">
          <span aria-hidden className="inline-block h-3 w-3 border border-export" />
          Local Energy Market
        </Link>
        <nav className="flex flex-wrap gap-x-5 gap-y-1 text-sm">
          {LINKS.map((l) => {
            const active = l.href === "/" ? path === "/" : path.startsWith(l.href);
            return (
              <Link
                key={l.href}
                href={l.href}
                className={`border-b py-1 ${active ? "border-label text-label" : "border-transparent text-label-muted hover:text-label"}`}
              >
                {l.label}
              </Link>
            );
          })}
        </nav>
        <div className="ml-auto">
          <ClockBadge />
        </div>
      </div>
    </header>
  );
}
