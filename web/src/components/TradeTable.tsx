import { kwh, pct } from "@/lib/format";
import type { Household, Trade } from "@/lib/types";

export function TradeTable({ trades, households }: { trades: Trade[]; households: Household[] }) {
  const label = (id: number) => households.find((h) => h.id === id)?.label ?? `#${id}`;
  if (trades.length === 0) {
    return <p className="text-sm text-label-muted">No trades in this slot.</p>;
  }
  return (
    <div className="overflow-x-auto">
      <table className="num w-full text-xs">
        <thead>
          <tr className="legend text-left">
            <th className="py-1.5 pr-3 font-normal">Route</th>
            <th className="py-1.5 pr-3 text-right font-normal">Injected</th>
            <th className="py-1.5 pr-3 text-right font-normal">Received</th>
            <th className="py-1.5 pr-3 text-right font-normal">Lost</th>
            <th className="py-1.5 text-right font-normal">Path</th>
          </tr>
        </thead>
        <tbody>
          {trades.map((t, i) => (
            <tr key={i} className="border-t border-panel-etch">
              <td className="py-1.5 pr-3">
                <span className="text-export">{label(t.seller)}</span>
                <span className="text-label-muted"> → </span>
                <span className="text-import">{label(t.buyer)}</span>
              </td>
              <td className="py-1.5 pr-3 text-right text-label">{kwh(t.injected_wh)}</td>
              <td className="py-1.5 pr-3 text-right text-label">{kwh(t.delivered_wh)}</td>
              <td className="py-1.5 pr-3 text-right text-label-muted">{pct(t.loss_fraction, 2)}</td>
              <td className="py-1.5 text-right text-label-muted">{t.path_m.toFixed(0)} m</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
