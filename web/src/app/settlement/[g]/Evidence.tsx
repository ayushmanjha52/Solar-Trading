"use client";

import Link from "next/link";
import { useState } from "react";
import { DepthLegend, MarketDepth } from "@/components/MarketDepth";
import { TradeTable } from "@/components/TradeTable";
import { Annunciator, EngineOffline, Figure, Hash, Loading, Panel } from "@/components/ui";
import { dayLabel, inr, inrSigned, kwh, kwhSigned, price, slotEnd, slotLabel } from "@/lib/format";
import type { Feeder, SlotDetail } from "@/lib/types";
import { usePoll } from "@/lib/usePoll";
import { type BrowserCheck, verifySlot } from "@/lib/verify";

export function Evidence({ g }: { g: number }) {
  const slot = usePoll<SlotDetail>(`/api/slot/${g}`, 2000);
  const feeder = usePoll<Feeder>("/api/feeder", 60_000);
  const [check, setCheck] = useState<BrowserCheck | null>(null);
  const [checking, setChecking] = useState(false);
  const [checkError, setCheckError] = useState<string | null>(null);

  if (slot.error && !slot.data) {
    return (
      <div className="space-y-3">
        <EngineOffline message={slot.error} />
        <Link href="/settlement" className="text-sm text-label underline decoration-panel-etch underline-offset-2">
          Back to the ledger
        </Link>
      </div>
    );
  }
  if (!slot.data || !feeder.data) return <Loading />;
  const s = slot.data;
  const f = feeder.data;
  const label = (id: number) => f.households.find((h) => h.id === id)?.label ?? `#${id}`;
  const st = s.settlement;
  const v = s.verification;
  const marketSum = st ? st.households.reduce((a, h) => a + h.market_mp, 0) : 0;

  async function runCheck() {
    setChecking(true);
    setCheckError(null);
    try {
      setCheck(await verifySlot(s, f));
    } catch (e) {
      setCheckError(e instanceof Error ? e.message : "Verification failed to run.");
    }
    setChecking(false);
  }

  return (
    <div className="space-y-5">
      <div>
        <div className="legend">
          <Link href="/settlement" className="hover:text-label">
            Settlement
          </Link>{" "}
          / SP {slotLabel(s.slot)}
        </div>
        <h1 className="display mt-1 text-2xl uppercase text-label">
          SP {slotLabel(s.slot)} · {s.time}–{slotEnd(s.time)}
        </h1>
        <p className="num mt-1 text-xs uppercase tracking-wider text-label-muted">
          {dayLabel(s.day)} · AEST · slot start {s.slot_start} (unix, UTC) ·{" "}
          {s.status === "settled" ? "settled" : s.status === "delivery" ? "in delivery, awaiting meter readings" : s.status}
        </p>
      </div>

      <div className="flex flex-wrap gap-2">
        <Annunciator label="Committed before delivery" state="armed" detail={s.commitment} />
        {v ? (
          <>
            <Annunciator label={v.commitment_matches ? "Commitment matches" : "Commitment mismatch"} state={v.commitment_matches ? "armed" : "alarm"} />
            <Annunciator
              label={v.signatures_valid ? `${s.readings?.length ?? 0} signatures valid` : `Bad signatures: ${v.bad_signers.map(label).join(", ")}`}
              state={v.signatures_valid ? "armed" : "alarm"}
            />
            <Annunciator label={v.band_ok ? "Price in band" : "Price out of band"} state={v.band_ok ? "armed" : "alarm"} />
          </>
        ) : (
          <Annunciator label="Awaiting meter readings" state="active" />
        )}
        {s.chain.settle?.tx ? (
          <Annunciator label={`Settled on chain · block ${s.chain.settle.block}`} state="armed" detail={s.chain.settle.tx} />
        ) : s.chain.commit?.tx ? (
          <Annunciator label={`Committed on chain · block ${s.chain.commit.block}`} state="active" detail={s.chain.commit.tx} />
        ) : (
          <Annunciator label="Not anchored" state="idle" />
        )}
      </div>

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-2 [&>*]:min-w-0">
        <Panel title="1 · The commitment">
          <div className="text-sm">
            <Hash value={s.commitment} head={66} tail={0} />
          </div>
          <p className="mt-2 text-xs leading-relaxed text-label-muted">
            keccak256(abi.encode(uint64 slotStart, uint32 price, (uint32 seller, uint32 buyer, uint64 injectedWh, uint64
            deliveredWh)[] trades)), published when the gate closed at{" "}
            {new Date(s.committed_at * 1000).toLocaleTimeString("en-GB")} wall-clock time. Price{" "}
            <span className="num text-label">{s.price ?? 0}</span> paise/kWh, {s.trades.length} trades.
          </p>
          <div className="mt-4">
            <TradeTable trades={s.trades} households={f.households} />
          </div>
        </Panel>

        <Panel title="The cleared book">
          <MarketDepth curves={s.curves} tariff={f.tariff} cleared={{ price: s.price ?? null, volume_wh: s.volume_wh ?? 0 }} height={220} />
          <DepthLegend cleared={{ price: s.price ?? null, volume_wh: s.volume_wh ?? 0 }} />
          <div className="mt-4 grid grid-cols-3 gap-4">
            <Figure label="Cleared" value={price(s.price)} unit="/kWh" />
            <Figure label="Marginal bid · ask" value={`${price(s.marginal_bid)} · ${price(s.marginal_ask)}`} />
            <Figure label="Volume" value={kwh(s.volume_wh)} unit="kWh" />
          </div>
        </Panel>
      </div>

      <Panel
        title="2 · Signed meter readings"
        right={
          s.readings ? (
            <button
              onClick={runCheck}
              disabled={checking}
              className="num border border-label-muted px-3 py-1 text-2xs uppercase tracking-wider text-label hover:bg-panel-etch disabled:opacity-50"
            >
              {checking ? "Checking…" : "Verify in this browser"}
            </button>
          ) : null
        }
        bodyClassName="p-0"
      >
        {!s.readings ? (
          <p className="p-4 text-sm text-label-muted">Meters sign when delivery of this slot ends.</p>
        ) : (
          <>
            {(check || checkError) && (
              <div className="border-b border-panel-etch p-4 text-xs leading-relaxed">
                {checkError ? (
                  <span className="text-alarm">{checkError}</span>
                ) : (
                  check && (
                    <div className="space-y-1">
                      <div className={check.commitmentMatches ? "text-armed" : "text-alarm"}>
                        Commitment recomputed with viem: <Hash value={check.commitment} head={18} tail={8} />{" "}
                        {check.commitmentMatches ? "matches the published one." : "DOES NOT match the published one."}
                      </div>
                      <div className={check.readings.every((r) => r.ok) ? "text-armed" : "text-alarm"}>
                        {check.readings.filter((r) => r.ok).length} of {check.readings.length} signatures recover to the
                        meter&apos;s registered key.
                      </div>
                      <div className={check.priceInBand ? "text-armed" : "text-alarm"}>
                        Cleared price {check.priceInBand ? "is" : "is NOT"} strictly inside the band.
                      </div>
                      <div className="text-label-muted">
                        Computed in your browser from the evidence above, independently of the engine&apos;s own check.
                        The registered keys come from the same operator API; on chain they would come from the
                        MeterRegistry contract instead.
                      </div>
                    </div>
                  )
                )}
              </div>
            )}
            <div className="overflow-x-auto">
              <table className="num w-full text-xs">
                <thead>
                  <tr className="legend border-b border-panel-etch text-left">
                    <th className="px-4 py-2 font-normal">Meter</th>
                    <th className="px-3 py-2 text-right font-normal">Import Wh</th>
                    <th className="px-3 py-2 text-right font-normal">Export Wh</th>
                    <th className="px-3 py-2 font-normal">Signature</th>
                    <th className="px-4 py-2 font-normal">Registered key</th>
                  </tr>
                </thead>
                <tbody>
                  {s.readings.map((r) => {
                    const c = check?.readings.find((x) => x.meter === r.meter);
                    return (
                      <tr key={r.meter} className="border-b border-panel-etch last:border-0">
                        <td className="px-4 py-1.5">
                          <Link href={`/households/${r.meter}`} className="text-label underline decoration-panel-etch underline-offset-2">
                            {label(r.meter)}
                          </Link>
                        </td>
                        <td className={`px-3 py-1.5 text-right ${r.import_wh ? "text-import" : "text-label-muted"}`}>{r.import_wh}</td>
                        <td className={`px-3 py-1.5 text-right ${r.export_wh ? "text-export" : "text-label-muted"}`}>{r.export_wh}</td>
                        <td className="px-3 py-1.5">
                          <Hash value={r.signature} head={14} tail={6} />
                        </td>
                        <td className="px-4 py-1.5">
                          <Hash value={r.signer} head={10} tail={6} />
                          {c && <span className={`ml-2 ${c.ok ? "text-armed" : "text-alarm"}`}>{c.ok ? "recovered ✓" : "mismatch"}</span>}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </>
        )}
      </Panel>

      {st && (
        <Panel title="3 · Settlement: pass 1 market at the cleared price, pass 2 imbalance at grid tariffs" bodyClassName="p-0">
          <div className="overflow-x-auto">
            <table className="num w-full text-xs">
              <thead>
                <tr className="legend border-b border-panel-etch text-left">
                  <th className="px-4 py-2 font-normal">Household</th>
                  <th className="px-3 py-2 text-right font-normal">Contracted</th>
                  <th className="px-3 py-2 text-right font-normal">Metered</th>
                  <th className="px-3 py-2 text-right font-normal">Deviation</th>
                  <th className="px-3 py-2 text-right font-normal">Market</th>
                  <th className="px-3 py-2 text-right font-normal">Imbalance</th>
                  <th className="px-3 py-2 text-right font-normal">Grid-only</th>
                  <th className="px-4 py-2 text-right font-normal">vs grid-only</th>
                </tr>
              </thead>
              <tbody>
                {st.households.map((h) => {
                  const c = h.contracted_export_wh - h.contracted_import_wh;
                  const m = h.metered_export_wh - h.metered_import_wh;
                  return (
                    <tr key={h.household} className="border-b border-panel-etch last:border-0">
                      <td className="px-4 py-1.5 text-label">{label(h.household)}</td>
                      <td className={`px-3 py-1.5 text-right ${c > 0 ? "text-export" : c < 0 ? "text-import" : "text-label-muted"}`}>
                        {c ? kwhSigned(c) : "—"}
                      </td>
                      <td className="px-3 py-1.5 text-right">{kwhSigned(m)}</td>
                      <td className={`px-3 py-1.5 text-right ${c && h.deviation_wh < -10 ? "text-alarm" : "text-label-muted"}`}>
                        {c ? kwhSigned(h.deviation_wh) : "—"}
                      </td>
                      <td className="px-3 py-1.5 text-right">{h.market_mp ? inrSigned(h.market_mp) : "—"}</td>
                      <td className="px-3 py-1.5 text-right">{inrSigned(h.imbalance_mp)}</td>
                      <td className="px-3 py-1.5 text-right text-label-muted">{inrSigned(h.grid_only_mp)}</td>
                      <td className={`px-4 py-1.5 text-right ${h.saving_mp < 0 ? "text-alarm" : h.saving_mp > 0 ? "text-label" : "text-label-muted"}`}>
                        {h.saving_mp ? inrSigned(h.saving_mp) : "—"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <div className="grid gap-4 border-t border-panel-etch p-4 md:grid-cols-4">
            <Figure label="Sellers received − buyers paid" value={inrSigned(marketSum)} sub="= cost of losses − wheeling income" />
            <Figure label="Cost of losses" value={inr(st.loss_cost_mp)} sub="cleared price × energy lost as heat" />
            <Figure label="Wheeling income" value={inr(st.wheeling_income_mp)} />
            <Figure
              label="Money conserved"
              value={marketSum + st.operator_mp === 0 ? "exactly" : "NO"}
              tone={marketSum + st.operator_mp === 0 ? "armed" : "alarm"}
              sub="integer milli-paise, no rounding"
            />
          </div>
        </Panel>
      )}

      {(s.chain.commit || s.chain.settle) && (
        <Panel title="4 · On chain">
          <div className="grid gap-4 text-xs md:grid-cols-2">
            {(["commit", "settle"] as const).map((k) => {
              const tx = s.chain[k];
              if (!tx) return null;
              return (
                <div key={k}>
                  <div className="legend">{k === "commit" ? "commit(slotStart, hash)" : "settle(slotStart, price, trades, readings)"}</div>
                  <div className="mt-1">
                    {tx.tx ? <Hash value={tx.tx} head={66} tail={0} /> : <span className="text-label-muted">{tx.status}</span>}
                  </div>
                  <div className="num mt-1 text-label-muted">
                    {tx.status} {tx.block != null && `· block ${tx.block}`} {tx.gas_used != null && `· ${tx.gas_used.toLocaleString("en-IN")} gas`}
                    {tx.error && <span className="text-alarm"> · {tx.error}</span>}
                  </div>
                  {k === "settle" && tx.matches_engine != null && (
                    <p className={`mt-2 ${tx.matches_engine ? "text-armed" : "text-alarm"}`}>
                      {tx.matches_engine
                        ? `The contract recomputed the two-pass settlement for ${tx.households_settled} households from the trades and signed readings; every figure equals the engine's.`
                        : "The contract's settlement DIFFERS from the engine's."}
                    </p>
                  )}
                </div>
              );
            })}
          </div>
        </Panel>
      )}
    </div>
  );
}
