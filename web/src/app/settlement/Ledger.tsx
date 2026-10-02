"use client";

import Link from "next/link";
import { Annunciator, EngineOffline, Hash, Loading, Panel } from "@/components/ui";
import { kwh, price, slotLabel } from "@/lib/format";
import type { Clock, LedgerRow } from "@/lib/types";
import { usePoll } from "@/lib/usePoll";

const STEPS = [
  ["Gate closure", "The book clears. The trades are fixed and keccak256(slot, price, trades) is published as the commitment, before any meter has reported."],
  ["Delivery", "Half an hour of real Ausgrid load and generation flows through the feeder."],
  ["Readings", "Each of the 24 meters signs its import and export for the slot with its own ECDSA key."],
  ["Settlement", "The commitment is recomputed from the stored trades, every signature is recovered against the meter registry, and the price is checked against the band. Only then do pass 1 (market) and pass 2 (imbalance) settle."],
];

export function Ledger() {
  const ledger = usePoll<LedgerRow[]>("/api/ledger?limit=144", 2000);
  const clock = usePoll<Clock>("/api/clock", 2000);
  if (ledger.error && !ledger.data) return <EngineOffline message={ledger.error} />;
  if (!ledger.data || !clock.data) return <Loading />;

  const rows = ledger.data;
  const settled = rows.filter((r) => r.status === "settled");
  const failed = settled.filter((r) => !r.verification?.verified);
  const chain = clock.data.chain;

  return (
    <div className="space-y-5">
      <div>
        <h1 className="display text-2xl uppercase text-label">Settlement</h1>
        <p className="mt-1 max-w-3xl text-sm text-label-muted">
          Matching happens off-chain; settlement is proven. Every slot is committed before delivery and settled only
          against signed meter readings, so the operator cannot quietly restate an outcome afterwards.
        </p>
      </div>

      <div className="grid gap-px border border-panel-etch bg-panel-etch md:grid-cols-4">
        {STEPS.map(([title, body], i) => (
          <div key={title} className="bg-panel-raised p-4">
            <div className="legend">
              {String(i + 1).padStart(2, "0")} · {title}
            </div>
            <p className="mt-2 text-xs leading-relaxed text-label">{body}</p>
          </div>
        ))}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <Annunciator
          label={failed.length ? `${failed.length} mismatched` : `${settled.length} settled · all verified`}
          state={failed.length ? "alarm" : settled.length ? "armed" : "idle"}
        />
        {chain.connected ? (
          <Annunciator label={`Anchored · chain ${chain.chain_id}`} state="armed" detail={chain.market} />
        ) : (
          <Annunciator label="Not anchored on chain" state="idle" detail="No chain connected; verified off-chain only" />
        )}
        {chain.connected && chain.market && (
          <span className="num text-2xs text-label-muted">
            EnergyMarket <Hash value={chain.market} head={10} tail={6} /> · block {chain.block}
          </span>
        )}
      </div>

      <Panel title="Ledger · newest first" bodyClassName="p-0">
        <div className="overflow-x-auto">
          <table className="num w-full text-xs">
            <thead>
              <tr className="legend border-b border-panel-etch text-left">
                <th className="px-4 py-2 font-normal">Slot</th>
                <th className="px-3 py-2 font-normal">Status</th>
                <th className="px-3 py-2 text-right font-normal">Price</th>
                <th className="px-3 py-2 text-right font-normal">Traded</th>
                <th className="px-3 py-2 text-right font-normal">Trades</th>
                <th className="px-3 py-2 font-normal">Commitment</th>
                <th className="px-3 py-2 text-right font-normal">Readings</th>
                <th className="px-3 py-2 font-normal">Check</th>
                <th className="px-4 py-2 font-normal">Chain</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => {
                const v = r.verification;
                return (
                  <tr key={r.g} className="border-b border-panel-etch last:border-0 hover:bg-panel-base">
                    <td className="px-4 py-2">
                      <Link href={`/settlement/${r.g}`} className="text-label underline decoration-panel-etch underline-offset-2">
                        SP {slotLabel(r.slot)}
                      </Link>{" "}
                      <span className="text-label-muted">
                        {r.day} {r.time}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-label-muted">{r.status === "delivery" ? "in delivery" : r.status}</td>
                    <td className="px-3 py-2 text-right">{price(r.price)}</td>
                    <td className="px-3 py-2 text-right">{r.injected_wh ? `${kwh(r.injected_wh)} kWh` : "—"}</td>
                    <td className="px-3 py-2 text-right">{r.n_trades ?? 0}</td>
                    <td className="px-3 py-2">
                      <Hash value={r.commitment} head={10} tail={4} />
                    </td>
                    <td className="px-3 py-2 text-right">{r.readings || "—"}</td>
                    <td className="px-3 py-2">
                      {v == null ? (
                        <span className="text-label-muted">awaiting readings</span>
                      ) : v.verified ? (
                        <span className="text-armed">verified</span>
                      ) : (
                        <span className="text-alarm">
                          {!v.commitment_matches ? "commitment mismatch" : !v.signatures_valid ? "bad signature" : "out of band"}
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-2">
                      {r.chain.settle?.tx ? (
                        <span
                          className={r.chain.settle.matches_engine === false ? "text-alarm" : "text-armed"}
                          title={r.chain.settle.tx}
                        >
                          settled · blk {r.chain.settle.block}
                          {r.chain.settle.matches_engine === false ? " · differs" : " · matches"}
                        </span>
                      ) : r.chain.commit?.tx ? (
                        <span className="text-label" title={r.chain.commit.tx}>
                          committed · blk {r.chain.commit.block}
                        </span>
                      ) : r.chain.commit?.status === "failed" || r.chain.settle?.status === "failed" ? (
                        <span className="text-alarm" title={r.chain.settle?.error ?? r.chain.commit?.error}>
                          failed
                        </span>
                      ) : (
                        <span className="text-label-muted">—</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  );
}
