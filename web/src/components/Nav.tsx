"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { dayLabel, slotEnd } from "@/lib/format";
import type { Clock } from "@/lib/types";
import { usePoll } from "@/lib/usePoll";

export const GITHUB_URL = "https://github.com/ayushmanjha52/Solar-Trading";

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
      <span className="text-label">{data.paused ? "Paused" : "Live"}</span>
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
          <a
            href={GITHUB_URL}
            target="_blank"
            rel="noreferrer"
            className="rounded-full p-1.5 text-label-muted transition-colors hover:bg-white/[0.06] hover:text-label"
            aria-label="Source code on GitHub"
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
              <path d="M12 .5a11.5 11.5 0 0 0-3.64 22.41c.58.1.79-.25.79-.56v-2c-3.2.7-3.88-1.37-3.88-1.37-.53-1.33-1.28-1.69-1.28-1.69-1.05-.71.08-.7.08-.7 1.16.08 1.77 1.19 1.77 1.19 1.03 1.77 2.71 1.26 3.37.96.1-.75.4-1.26.73-1.55-2.55-.29-5.24-1.28-5.24-5.69 0-1.26.45-2.29 1.19-3.1-.12-.29-.52-1.46.11-3.05 0 0 .97-.31 3.17 1.18a11 11 0 0 1 5.77 0c2.2-1.49 3.17-1.18 3.17-1.18.63 1.59.23 2.76.11 3.05.74.81 1.19 1.84 1.19 3.1 0 4.42-2.7 5.39-5.26 5.68.41.36.78 1.06.78 2.14v3.17c0 .31.21.67.8.56A11.5 11.5 0 0 0 12 .5Z" />
            </svg>
          </a>
        </div>
      </div>
    </header>
  );
}
