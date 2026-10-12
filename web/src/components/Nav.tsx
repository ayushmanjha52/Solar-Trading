"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { dayLabel, slotEnd } from "@/lib/format";
import type { Clock } from "@/lib/types";
import { usePoll } from "@/lib/usePoll";

const LINKS = [
  { href: "/", label: "Control room" },
  { href: "/trade", label: "Trade" },
  { href: "/households", label: "Households" },
  { href: "/settlement", label: "Settlement" },
  { href: "/results", label: "Results" },
  { href: "/method", label: "Method" },
];

export function Mark({ size = 22 }: { size?: number }) {
  // A sun over a busbar: the whole project in one glyph.
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden>
      <circle cx="12" cy="9" r="4" fill="var(--flow-export)" />
      <g stroke="var(--flow-export)" strokeWidth="1.6" strokeLinecap="round">
        <path d="M12 1.5v1.6M4.6 4.6l1.1 1.1M19.4 4.6l-1.1 1.1M2 9h1.6M20.4 9H22" />
      </g>
      <path d="M3 18.5h18" stroke="var(--label)" strokeWidth="1.8" strokeLinecap="round" />
      <path d="M7 18.5v3M12 18.5v3M17 18.5v3" stroke="var(--flow-import)" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}

function ClockBadge() {
  const { data, error } = usePoll<Clock>("/api/clock", 2000);
  if (error && !data) {
    return (
      <span className="pill text-alarm" title={error}>
        <span className="h-[7px] w-[7px] rounded-full bg-alarm" /> Engine offline
      </span>
    );
  }
  if (!data) return <span className="pill text-label-muted">Connecting…</span>;
  return (
    <span className="pill text-label-muted" title={data.chain.connected ? `Anchoring to chain ${data.chain.chain_id}` : "Settlement verified off-chain"}>
      {data.paused ? <span className="h-[7px] w-[7px] rounded-full bg-label-muted" /> : <span className="live-dot" />}
      <span className="text-label">{data.paused ? "Paused" : data.hosted ? "Replay" : "Live"}</span>
      <span className="hidden sm:inline">{dayLabel(data.day)}</span>
      <span className="num text-label">
        {data.slot_time}–{slotEnd(data.slot_time)}
      </span>
    </span>
  );
}

export function Nav() {
  const path = usePathname();
  return (
    <header className="sticky top-0 z-30 border-b border-panel-etch bg-[rgba(7,8,10,0.72)] backdrop-blur-xl">
      <div className="mx-auto flex max-w-[1400px] flex-wrap items-center gap-x-8 gap-y-3 px-4 py-3.5 md:px-8">
        <Link href="/" className="flex items-center gap-2.5">
          <Mark />
          <span className="display text-[1.05rem] text-label">Local Energy Market</span>
        </Link>
        <nav className="flex flex-wrap gap-1 text-sm">
          {LINKS.map((l) => {
            const active = l.href === "/" ? path === "/" : path.startsWith(l.href);
            return (
              <Link
                key={l.href}
                href={l.href}
                className={`rounded-full px-3 py-1.5 transition-colors ${
                  active ? "bg-white/[0.07] text-label" : "text-label-muted hover:bg-white/[0.04] hover:text-label"
                }`}
              >
                {l.label}
              </Link>
            );
          })}
        </nav>
        <div className="ml-auto flex items-center gap-3">
          <ClockBadge />
        </div>
      </div>
    </header>
  );
}
