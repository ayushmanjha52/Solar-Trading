"use client";

import { useEffect, useState } from "react";
import type { Clock } from "@/lib/types";
import { postJson } from "@/lib/usePoll";

const SPEEDS = [2, 5, 10];
const TOKEN_KEY = "lem-operator-token";

const btn =
  "num border border-panel-etch px-2.5 py-1 text-2xs uppercase tracking-wider text-label hover:border-label-muted disabled:opacity-40";

function readToken(): string {
  try {
    return localStorage.getItem(TOKEN_KEY) ?? "";
  } catch {
    return "";
  }
}

function writeToken(t: string) {
  try {
    if (t) localStorage.setItem(TOKEN_KEY, t);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage unavailable: the token lasts for this page view only */
  }
}

export function ClockControls({ clock, onChange }: { clock: Clock; onChange: () => void }) {
  const [error, setError] = useState<string | null>(null);
  const [day, setDay] = useState(clock.day);
  const [token, setToken] = useState("");
  const [draft, setDraft] = useState("");
  const [unlocking, setUnlocking] = useState(false);

  useEffect(() => setToken(readToken()), []);

  const locked = !!clock.controls_locked && !token;

  const send = async (body: Record<string, unknown>) => {
    const r = await postJson("/api/clock", body, "POST", token ? { "x-admin-token": token } : {});
    if (r.status === 403) {
      writeToken("");
      setToken("");
    }
    setError(r.error);
    onChange();
  };

  if (locked) {
    return (
      <div className="flex flex-wrap items-center gap-2">
        <span className="legend">{clock.paused ? "Paused by the operator" : `Clock runs for everyone · ${clock.slot_seconds}s per slot`}</span>
        {unlocking ? (
          <form
            className="flex items-center gap-1"
            onSubmit={(e) => {
              e.preventDefault();
              writeToken(draft);
              setToken(draft);
              setUnlocking(false);
              setError(null);
            }}
          >
            <label htmlFor="operator-token" className="sr-only">
              Operator token
            </label>
            <input
              id="operator-token"
              type="password"
              autoComplete="off"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder="operator token"
              className="num w-36 border border-panel-etch bg-panel-base px-2 py-0.5 text-2xs text-label"
            />
            <button className={btn} type="submit">
              Unlock
            </button>
          </form>
        ) : (
          <button className={btn} onClick={() => setUnlocking(true)}>
            Operator
          </button>
        )}
        {error && <span className="text-xs text-alarm">{error}</span>}
      </div>
    );
  }

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
      {clock.controls_locked && (
        <button
          className={btn}
          onClick={() => {
            writeToken("");
            setToken("");
          }}
          title="Forget the operator token in this browser"
        >
          Lock
        </button>
      )}
      {error && <span className="text-xs text-alarm">{error}</span>}
    </div>
  );
}
