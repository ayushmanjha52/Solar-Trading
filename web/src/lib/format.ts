// Every number in the interface goes through here. Nothing rounds upstream.

const MINUS = "−";

/** Milli-paise to rupees, Indian digit grouping: -1234567 -> "−₹12.35". */
export function inr(mp: number, digits = 2): string {
  const r = mp / 100_000;
  const s = Math.abs(r).toLocaleString("en-IN", { minimumFractionDigits: digits, maximumFractionDigits: digits });
  return `${r < 0 && Math.abs(r) >= 0.5 * 10 ** -digits ? MINUS : ""}₹${s}`;
}

/** Signed rupees with an explicit plus, for savings. */
export function inrSigned(mp: number, digits = 2): string {
  const s = inr(mp, digits);
  return mp > 0 && !s.startsWith(MINUS) && s !== `₹${(0).toFixed(digits)}` ? `+${s}` : s;
}

/** Paise per kWh to "₹6.12". */
export function price(paise: number | null | undefined): string {
  return paise == null ? "—" : `₹${(paise / 100).toFixed(2)}`;
}

/** Wh to kWh with fixed decimals. */
export function kwh(wh: number | null | undefined, digits = 3): string {
  if (wh == null) return "—";
  const v = wh / 1000;
  return `${v < 0 ? MINUS : ""}${Math.abs(v).toFixed(digits)}`;
}

/** Wh to signed kWh: "+0.412" export, "−0.310" import. */
export function kwhSigned(wh: number, digits = 3): string {
  if (wh === 0) return (0).toFixed(digits);
  return `${wh > 0 ? "+" : MINUS}${Math.abs(wh / 1000).toFixed(digits)}`;
}

export function pct(f: number, digits = 2): string {
  return `${(f * 100).toFixed(digits)}%`;
}

export function shortHash(h: string | undefined, head = 10, tail = 6): string {
  if (!h) return "—";
  return h.length <= head + tail + 1 ? h : `${h.slice(0, head)}…${h.slice(-tail)}`;
}

export function dayLabel(day: string): string {
  const d = new Date(`${day}T00:00:00Z`);
  return d
    .toLocaleDateString("en-GB", { weekday: "short", day: "2-digit", month: "short", year: "numeric", timeZone: "UTC" })
    .toUpperCase();
}

export function slotLabel(slot: number): string {
  return String(slot).padStart(2, "0");
}

export function slotEnd(time: string): string {
  const [h, m] = time.split(":").map(Number);
  const t = h * 60 + m + 30;
  return `${String(Math.floor(t / 60) % 24).padStart(2, "0")}:${String(t % 60).padStart(2, "0")}`;
}
