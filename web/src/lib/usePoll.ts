"use client";

import { useCallback, useEffect, useRef, useState } from "react";

/** Poll a JSON endpoint. Holds the last good value through errors; pauses while the tab is hidden. */
export function usePoll<T>(url: string | null, intervalMs = 1000) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const kick = useRef<() => void>(() => {});

  const load = useCallback(async () => {
    if (!url) return;
    try {
      const r = await fetch(url, { cache: "no-store" });
      const body = await r.json().catch(() => null);
      if (!r.ok) {
        setError((body && body.detail) || `Request failed (${r.status}).`);
      } else {
        setData(body as T);
        setError(null);
      }
    } catch {
      setError("The web server is not responding.");
    }
  }, [url]);

  useEffect(() => {
    let alive = true;
    const loop = async () => {
      if (!alive) return;
      if (document.visibilityState === "visible") await load();
      if (alive) timer.current = setTimeout(loop, intervalMs);
    };
    kick.current = () => {
      if (timer.current) clearTimeout(timer.current);
      loop();
    };
    loop();
    const onVisible = () => document.visibilityState === "visible" && kick.current();
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      alive = false;
      if (timer.current) clearTimeout(timer.current);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [load, intervalMs]);

  return { data, error, refresh: () => kick.current() };
}

export async function postJson<T>(url: string, body: unknown, method = "POST"): Promise<{ ok: boolean; data: T | null; error: string | null }> {
  try {
    const r = await fetch(url, {
      method,
      headers: { "content-type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    const data = await r.json().catch(() => null);
    if (!r.ok) {
      const detail = data?.detail;
      const msg = typeof detail === "string" ? detail : Array.isArray(detail) ? detail.map((d) => d.msg).join(" ") : null;
      return { ok: false, data: null, error: msg ?? `Request failed (${r.status}).` };
    }
    return { ok: true, data: data as T, error: null };
  } catch {
    return { ok: false, data: null, error: "The web server is not responding." };
  }
}
