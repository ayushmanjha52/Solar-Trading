"use client";

import Link from "next/link";
import { inrSigned, kwh } from "@/lib/format";
import type { Live } from "@/lib/types";
import { usePoll } from "@/lib/usePoll";
import { GITHUB_URL } from "./Nav";

interface Summary {
  forecast_model: string | null;
  forecast_skill: number | null;
  saving_per_home_year_inr: number | null;
}

function Stat({ label, value, note, tone = "text-label" }: { label: string; value: string; note: string; tone?: string }) {
  return (
    <div className="card px-5 py-4">
      <div className="legend">{label}</div>
      <div className={`hero-figure mt-2 text-[1.9rem] leading-none ${tone}`}>{value}</div>
      <div className="mt-2 text-xs text-label-muted">{note}</div>
    </div>
  );
}

export function Hero() {
  const live = usePoll<Live>("/api/live", 3000);
  const summary = usePoll<Summary>("/api/summary", 600_000);
  const t = live.data?.day.totals;
  const s = summary.data;

  return (
    <section className="pb-4 pt-6 md:pt-10">
      <div className="pill w-fit text-label-muted">
        <span className="h-1.5 w-1.5 rounded-full bg-export" />
        Peer-to-peer solar trading on one street
      </div>
      <h1 className="display mt-6 max-w-4xl text-[clamp(2.4rem,1.5rem+3.6vw,4.4rem)] leading-[1.02] text-label">
        Neighbours trade their sunlight. <span className="accent text-export">Every kilowatt-hour is proven.</span>
      </h1>
      <p className="mt-6 max-w-2xl text-[1.05rem] leading-relaxed text-label-muted">
        Twenty-four Sydney homes share one low-voltage feeder. Rooftop surplus clears every half hour at a single fair
        price, between what the grid pays and what it charges, and every trade is settled against cryptographically
        signed meter readings.
      </p>
      <div className="mt-8 flex flex-wrap gap-3">
        <Link
          href="/trade"
          className="rounded-full bg-export px-5 py-2.5 text-sm font-semibold text-[#1a1204] transition-transform hover:-translate-y-px"
        >
          Trade as a household
        </Link>
        <Link href="/method" className="rounded-full border border-panel-etch px-5 py-2.5 text-sm text-label hover:border-label-muted">
          How it works
        </Link>
        <a
          href={GITHUB_URL}
          target="_blank"
          rel="noreferrer"
          className="rounded-full border border-panel-etch px-5 py-2.5 text-sm text-label hover:border-label-muted"
        >
          Source code
        </a>
      </div>

      <div className="mt-10 grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Stat
          label="Traded today"
          value={t ? `${kwh(t.injected_wh, 1)} kWh` : "…"}
          note="between neighbours, so far on the simulated day"
          tone="text-export"
        />
        <Stat
          label="Households vs grid-only"
          value={t ? inrSigned(t.saving_mp) : "…"}
          note="the same meter readings billed with no market"
        />
        <Stat
          label="Settlements verified"
          value={t ? `${t.settled_slots} / ${t.settled_slots}` : "…"}
          note={t && !t.all_verified ? "a settlement failed verification" : "commitment and 24 signatures, every slot"}
          tone={t && !t.all_verified ? "text-alarm" : "text-armed"}
        />
        <Stat
          label="Forecast error"
          value={s?.forecast_skill != null ? `−${Math.round(s.forecast_skill * 100)}%` : "…"}
          note="against persistence, on an untouched test window"
          tone="text-import"
        />
      </div>
    </section>
  );
}
