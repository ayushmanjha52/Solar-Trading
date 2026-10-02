"use client";

import { useState } from "react";
import type { Clock } from "@/lib/types";
import { postJson } from "@/lib/usePoll";

const SPEEDS = [2, 5, 10];

const btn =
  "num border border-panel-etch px-2.5 py-1 text-2xs uppercase tracking-wider text-label hover:border-label-muted disabled:opacity-40";

export function ClockControls({ clock, onChange }: { clock: Clock; onChange: () => void }) {
  const [error, setError] = useState<string | null>(null);
  const [day, setDay] = useState(clock.day);

  const send = async (body: Record<string, unknown>) => {
    const r = await postJson("/api/clock", body);
    setError(r.error);
    onChange();
  };

  return (
    <div className="flex flex-wrap items-center gap-2">
      {clock.paused ? (
        <button className={btn} onClick={() => send({ action: "resume" })}>
          Resume
        </button>
      ) : (
        <button className={btn} onClick={() => send({ action: "pause" })}>
          Pause
        </button>
      )}
      <button className={btn} onClick={() => send({ action: "step" })} title="Advance one half-hour slot now">
        Step
      </button>
      <div className="flex" role="group" aria-label="Seconds per simulated half hour">
        {SPEEDS.map((s) => (
          <button
            key={s}
            className={`${btn} -ml-px ${clock.slot_seconds === s ? "border-label-muted bg-panel-etch" : ""}`}
            onClick={() => send({ action: "speed", slot_seconds: s })}
            aria-pressed={clock.slot_seconds === s}
          >
            {s}s
          </button>
        ))}
      </div>
      <form
        className="flex items-center gap-1"
        onSubmit={(e) => {
          e.preventDefault();
          send({ action: "jump", day });
        }}
      >
        <input
          type="date"
          value={day}
          min={clock.first_day}
          max={clock.last_day}
          onChange={(e) => setDay(e.target.value)}
          className="num border border-panel-etch bg-panel-base px-2 py-0.5 text-2xs text-label"
          aria-label="Jump to day"
        />
        <button className={btn} type="submit">
          Go
        </button>
      </form>
      {error && <span className="text-xs text-alarm">{error}</span>}
    </div>
  );
}
