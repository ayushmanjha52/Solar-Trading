import Link from "next/link";
import { kwh, pct, slotEnd, slotLabel } from "@/lib/format";
import type { ChainStatus, SlotDetail, Tariff } from "@/lib/types";
import { Annunciator, Figure, Hash } from "./ui";

export function SlotReadout({
  slot,
  previous,
  tariff,
  chain,
}: {
  slot: SlotDetail;
  previous: SlotDetail | null;
  tariff: Tariff;
  chain: ChainStatus;
}) {
  const lost = slot.injected_wh! - slot.delivered_wh!;
  const lossShare = slot.injected_wh ? lost / slot.injected_wh : 0;
  const bandOk = slot.price == null || (slot.price > tariff.feed_in && slot.price < tariff.retail - tariff.wheeling);
  const prevV = previous?.verification;
  const commitTx = slot.chain.commit;
  const settleTx = previous?.chain.settle;

  return (
    <div>
      <div className="legend">
        SP {slotLabel(slot.slot)} · {slot.time}–{slotEnd(slot.time)} AEST · in delivery
      </div>
      <div className="mt-3 flex items-baseline gap-3">
        {slot.price != null ? (
          <>
            <span className="hero-figure text-5xl text-label">₹{(slot.price / 100).toFixed(2)}</span>
            <span className="num text-sm text-label-muted">per kWh, everyone</span>
          </>
        ) : (
          <span className="hero-figure text-3xl text-label-muted">No trade</span>
        )}
      </div>
      {slot.price == null && (
        <p className="mt-2 text-sm text-label-muted">The book did not cross: no bid met an offer for this slot.</p>
      )}

      <div className="mt-5 grid grid-cols-2 gap-x-6 gap-y-4 sm:grid-cols-3">
        <Figure label="Injected" value={kwh(slot.injected_wh)} unit="kWh" tone="export" />
        <Figure label="Received" value={kwh(slot.delivered_wh)} unit="kWh" tone="import" />
        <Figure label="Lost as heat" value={kwh(lost)} unit="kWh" sub={`${pct(lossShare)} of injected`} />
        <Figure label="Trades" value={slot.trades.length} />
        <Figure
          label="Offers · bids"
          value={`${slot.orders.filter((o) => o.side === "sell").length} · ${slot.orders.filter((o) => o.side === "buy").length}`}
        />
        <Figure label="Over loss cap" value={kwh(slot.curtailed_wh)} unit="kWh" tone={slot.curtailed_wh ? "label" : "muted"} sub="not traded" />
      </div>

      <div className="mt-5 border-t border-panel-etch pt-4">
        <div className="legend">Commitment, published at gate closure</div>
        <div className="mt-1 text-sm">
          <Hash value={slot.commitment} head={18} tail={8} />
        </div>
        <p className="mt-1 text-xs text-label-muted">
          keccak256 of the cleared trades, fixed before any meter has reported. Settlement must reproduce it.
        </p>
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        <Annunciator label={bandOk ? "Band OK" : "Band violation"} state={bandOk ? "armed" : "alarm"} detail="Cleared price strictly between feed-in and retail" />
        <Annunciator label="Committed" state="armed" detail={slot.commitment} />
        {prevV ? (
          <Annunciator
            label={prevV.verified ? `SP ${slotLabel(previous!.slot)} verified` : `SP ${slotLabel(previous!.slot)} mismatch`}
            state={prevV.verified ? "armed" : "alarm"}
            detail="Previous slot: commitment recomputed, 24 meter signatures recovered, price in band"
          />
        ) : (
          <Annunciator label="Awaiting settlement" state="idle" />
        )}
        {chain.connected ? (
          <Annunciator
            label={commitTx?.status === "confirmed" ? "Anchored" : commitTx?.status === "failed" ? "Anchor failed" : "Anchoring"}
            state={commitTx?.status === "confirmed" ? "armed" : commitTx?.status === "failed" ? "alarm" : "active"}
            detail={commitTx?.tx}
          />
        ) : (
          <Annunciator label="Not anchored" state="idle" detail="No chain connected. Settlement is verified off-chain only." />
        )}
      </div>

      {previous && (
        <p className="mt-3 text-xs text-label-muted">
          SP {slotLabel(previous.slot)} settled against {previous.readings?.length ?? 0} signed meter readings
          {settleTx?.tx ? " and anchored on chain" : ""}.{" "}
          <Link href={`/settlement/${previous.g}`} className="text-label underline decoration-panel-etch underline-offset-2">
            Inspect the evidence
          </Link>
        </p>
      )}
    </div>
  );
}
