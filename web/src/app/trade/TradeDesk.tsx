"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { DepthLegend, MarketDepth } from "@/components/MarketDepth";
import { EngineOffline, Loading, Panel } from "@/components/ui";
import { inrSigned, kwh, kwhSigned, price, slotEnd, slotLabel } from "@/lib/format";
import type { Feeder, HouseholdView, Live, UserOrder } from "@/lib/types";
import { postJson, usePoll } from "@/lib/usePoll";

type Side = "sell" | "buy";

const field = "num w-full border border-panel-etch bg-panel-base px-3 py-2 text-sm text-label focus:border-label-muted";

export function TradeDesk() {
  const params = useSearchParams();
  const feeder = usePoll<Feeder>("/api/feeder", 60_000);
  const live = usePoll<Live>("/api/live", 1500);
  const orders = usePoll<UserOrder[]>("/api/orders", 1500);

  const [h, setH] = useState<number>(() => Number(params.get("h")) || 7);
  const [side, setSide] = useState<Side>("sell");
  const [g, setG] = useState<number | null>(null);
  const [qty, setQty] = useState("0.500");
  const [rupees, setRupees] = useState("5.50");
  const [message, setMessage] = useState<{ tone: "ok" | "error"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  const household = usePoll<HouseholdView>(`/api/households/${h}`, 3000);

  // Keep the chosen slot open: once its gate closes, move to the next open slot.
  const clockG = live.data?.clock.g;
  useEffect(() => {
    if (clockG == null) return;
    if (g == null || g <= clockG) setG(clockG + 1);
  }, [clockG, g]);

  const upcoming = household.data?.upcoming ?? [];
  const chosen = upcoming.find((u) => u.g === g);
  const forecast = chosen?.forecast_net_wh ?? null;

  const tariff = feeder.data?.tariff;
  const pricePaise = Math.round(Number(rupees) * 100);
  const bandMessage = useMemo(() => {
    if (!tariff || !rupees) return null;
    const hi = tariff.retail - tariff.wheeling;
    if (!(pricePaise > tariff.feed_in && pricePaise < hi)) {
      return `Price must sit between ${price(tariff.feed_in)} and ${price(hi)} per kWh. Outside that range the grid is the better deal.`;
    }
    return null;
  }, [tariff, pricePaise, rupees]);

  if ((feeder.error && !feeder.data) || (live.error && !live.data)) {
    return <EngineOffline message={feeder.error ?? live.error ?? ""} />;
  }
  if (!feeder.data || !live.data) return <Loading />;

  const f = feeder.data;
  const hh = f.households.find((x) => x.id === h)!;
  const isNextSlot = g === live.data.clock.g + 1;
  const myOrders = (orders.data ?? []).filter((o) => o.status !== "cancelled");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (g == null) return;
    setBusy(true);
    setMessage(null);
    const qty_wh = Math.round(Number(qty) * 1000);
    const r = await postJson<UserOrder>("/api/orders", { household: h, g, side, qty_wh, price: pricePaise });
    setBusy(false);
    if (r.ok && r.data) {
      setMessage({
        tone: "ok",
        text: `${side === "sell" ? "Offer" : "Bid"} placed for ${hh.label} in SP ${slotLabel(r.data.slot)}. ${hh.label}'s agent stands aside for that slot.`,
      });
      orders.refresh();
      live.refresh();
    } else {
      setMessage({ tone: "error", text: r.error ?? "The order was not placed." });
    }
  }

  async function cancel(id: string) {
    const r = await postJson(`/api/orders/${encodeURIComponent(id)}`, undefined, "DELETE");
    if (!r.ok) setMessage({ tone: "error", text: r.error ?? "Could not cancel." });
    orders.refresh();
    live.refresh();
  }

  return (
    <div className="space-y-5">
      <div>
        <h1 className="display text-2xl uppercase text-label">Trade</h1>
        <p className="mt-1 max-w-3xl text-sm text-label-muted">
          Act for one household on the feeder. Your order replaces that household&apos;s bidding agent for the slot you
          choose. The gate closes when the slot begins; the book then clears at one price for everyone.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-[420px_minmax(0,1fr)]">
        <Panel title="Order" className="min-w-0">
          <form onSubmit={submit} className="space-y-4">
            <div>
              <label className="legend" htmlFor="hh">
                Household
              </label>
              <select id="hh" className={`${field} mt-1`} value={h} onChange={(e) => setH(Number(e.target.value))}>
                {f.households.map((x) => (
                  <option key={x.id} value={x.id}>
                    {x.label} · {x.pv ? `PV ${x.pv_kwp.toFixed(2)} kWp` : "no PV"} · {x.position_m.toFixed(0)} m
                  </option>
                ))}
              </select>
            </div>

            <div className="grid grid-cols-2" role="radiogroup" aria-label="Side">
              {(["sell", "buy"] as Side[]).map((s) => (
                <button
                  key={s}
                  type="button"
                  role="radio"
                  aria-checked={side === s}
                  onClick={() => setSide(s)}
                  className={`-ml-px border px-3 py-2 text-sm first:ml-0 ${
                    side === s
                      ? s === "sell"
                        ? "border-export text-export"
                        : "border-import text-import"
                      : "border-panel-etch text-label-muted hover:text-label"
                  }`}
                >
                  {s === "sell" ? "Sell surplus" : "Buy energy"}
                </button>
              ))}
            </div>

            <div>
              <label className="legend" htmlFor="slot">
                Settlement period
              </label>
              <select id="slot" className={`${field} mt-1`} value={g ?? ""} onChange={(e) => setG(Number(e.target.value))}>
                {upcoming.map((u, i) => (
                  <option key={u.g} value={u.g}>
                    SP {slotLabel(u.slot)} · {u.time}–{slotEnd(u.time)}
                    {u.day !== live.data!.clock.day ? ` · ${u.day}` : ""}
                    {i === 0 ? " · gate closes next" : ""}
                  </option>
                ))}
              </select>
              {forecast != null && (
                <p className="mt-1 text-xs text-label-muted">
                  {hh.label} in this slot yesterday:{" "}
                  <span className={`num ${forecast > 0 ? "text-export" : forecast < 0 ? "text-import" : ""}`}>
                    {kwhSigned(forecast)} kWh
                  </span>{" "}
                  {forecast > 0 ? "surplus" : forecast < 0 ? "drawn from the grid" : ""}. That is all the agent would
                  have known.
                </p>
              )}
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="legend" htmlFor="qty">
                  Quantity, kWh
                </label>
                <input
                  id="qty"
                  className={`${field} mt-1`}
                  inputMode="decimal"
                  value={qty}
                  onChange={(e) => setQty(e.target.value)}
                />
              </div>
              <div>
                <label className="legend" htmlFor="price">
                  Price, ₹ per kWh
                </label>
                <input
                  id="price"
                  className={`${field} mt-1 ${bandMessage ? "border-alarm" : ""}`}
                  inputMode="decimal"
                  value={rupees}
                  onChange={(e) => setRupees(e.target.value)}
                  aria-invalid={!!bandMessage}
                  aria-describedby="band"
                />
              </div>
            </div>
            <p id="band" className={`text-xs ${bandMessage ? "text-alarm" : "text-label-muted"}`}>
              {bandMessage ??
                `The band: above the feed-in tariff ${price(f.tariff.feed_in)}, below retail ${price(
                  f.tariff.retail - f.tariff.wheeling,
                )}. Sellers receive the cleared price; buyers pay it${f.tariff.wheeling ? " plus wheeling" : ""}.`}
            </p>

            <button
              type="submit"
              disabled={busy}
              className={`num w-full border px-3 py-2.5 text-xs uppercase tracking-wider disabled:opacity-50 ${
                side === "sell" ? "border-export text-export" : "border-import text-import"
              } hover:bg-panel-etch`}
            >
              {busy ? "Placing…" : side === "sell" ? "Place offer" : "Place bid"}
            </button>
            {message && (
              <p role="status" className={`text-sm ${message.tone === "ok" ? "text-armed" : "text-alarm"}`}>
                {message.text}
              </p>
            )}
            <p className="text-xs leading-relaxed text-label-muted">
              Delivery is checked against the household&apos;s signed meter reading. Sell more than the house exports
              and the shortfall is bought back at retail; buy more than it uses and the excess is sold at feed-in.
            </p>
          </form>
        </Panel>

        <div className="min-w-0 space-y-5">
          <Panel
            title={g != null ? `Book · SP ${slotLabel(chosen?.slot ?? 0)}${isNextSlot ? " · gate closes next" : ""}` : "Book"}
          >
            {isNextSlot ? (
              <>
                <MarketDepth curves={live.data.book.curves} tariff={f.tariff} height={220} />
                <DepthLegend />
                <p className="mt-2 text-xs text-label-muted">
                  {live.data.book.orders.length} orders: agents bid from yesterday&apos;s same-slot energy
                  {live.data.book.orders.some((o) => o.by === "visitor") ? "; visitor orders included" : ""}.
                </p>
              </>
            ) : (
              <p className="py-8 text-center text-sm text-label-muted">
                No orders yet for this slot. Place a bid or an offer to open the book. Agents post theirs one slot
                before the gate closes.
              </p>
            )}
          </Panel>

          <Panel title="Your orders">
            {myOrders.length === 0 ? (
              <p className="text-sm text-label-muted">No orders yet. Place a bid or an offer to open the book.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="num w-full text-xs">
                  <thead>
                    <tr className="legend text-left">
                      <th className="py-1.5 pr-3 font-normal">Household</th>
                      <th className="py-1.5 pr-3 font-normal">Slot</th>
                      <th className="py-1.5 pr-3 font-normal">Side</th>
                      <th className="py-1.5 pr-3 text-right font-normal">kWh</th>
                      <th className="py-1.5 pr-3 text-right font-normal">Limit</th>
                      <th className="py-1.5 pr-3 font-normal">Status</th>
                      <th className="py-1.5 pr-3 text-right font-normal">Filled</th>
                      <th className="py-1.5 pr-3 text-right font-normal">Cleared</th>
                      <th className="py-1.5 text-right font-normal">vs grid-only</th>
                    </tr>
                  </thead>
                  <tbody>
                    {myOrders.map((o) => (
                      <tr key={o.id} className="border-t border-panel-etch">
                        <td className="py-1.5 pr-3">
                          <Link href={`/households/${o.household}`} className="text-label underline decoration-panel-etch underline-offset-2">
                            {o.label}
                          </Link>
                        </td>
                        <td className="py-1.5 pr-3 text-label-muted">
                          SP {slotLabel(o.slot)} {o.time}
                        </td>
                        <td className={`py-1.5 pr-3 ${o.side === "sell" ? "text-export" : "text-import"}`}>
                          {o.side === "sell" ? "sell" : "buy"}
                        </td>
                        <td className="py-1.5 pr-3 text-right">{kwh(o.qty_wh)}</td>
                        <td className="py-1.5 pr-3 text-right">{price(o.price)}</td>
                        <td className="py-1.5 pr-3">
                          {o.status === "open" ? (
                            <button onClick={() => cancel(o.id)} className="text-label-muted underline decoration-panel-etch underline-offset-2 hover:text-label">
                              open · cancel
                            </button>
                          ) : (
                            <span className={o.status === "settled" ? "text-armed" : "text-label"}>{o.status}</span>
                          )}
                        </td>
                        <td className="py-1.5 pr-3 text-right">{o.fill_wh == null ? "—" : kwh(o.fill_wh)}</td>
                        <td className="py-1.5 pr-3 text-right">{o.cleared_price ? price(o.cleared_price) : "—"}</td>
                        <td className="py-1.5 text-right">
                          {o.settlement ? (
                            <span className={o.settlement.saving_mp < 0 ? "text-alarm" : "text-label"}>
                              {inrSigned(o.settlement.saving_mp)}
                            </span>
                          ) : (
                            "—"
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <p className="mt-3 text-xs text-label-muted">
                  &ldquo;vs grid-only&rdquo; is the household&apos;s whole settlement for that slot (market plus
                  imbalance) minus what the same meter reading would have cost with no market.
                </p>
              </div>
            )}
          </Panel>
        </div>
      </div>
    </div>
  );
}
