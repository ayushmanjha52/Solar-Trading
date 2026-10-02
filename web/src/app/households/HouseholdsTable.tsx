"use client";

import Link from "next/link";
import { EngineOffline, Loading, Panel } from "@/components/ui";
import { inrSigned, kwh, kwhSigned, shortHash } from "@/lib/format";
import type { HouseholdRow } from "@/lib/types";
import { usePoll } from "@/lib/usePoll";

export function HouseholdsTable() {
  const { data, error } = usePoll<HouseholdRow[]>("/api/households", 2000);
  if (error && !data) return <EngineOffline message={error} />;
  if (!data) return <Loading />;

  const pv = data.filter((h) => h.pv).length;
  return (
    <div className="space-y-5">
      <div>
        <h1 className="display text-2xl uppercase text-label">Households</h1>
        <p className="mt-1 max-w-3xl text-sm text-label-muted">
          {data.length} households on the feeder, {pv} with rooftop PV. Each is a real Ausgrid customer&apos;s half-hourly
          load{pv ? " and, for PV homes, generation" : ""}; households shown without PV keep their real load with
          generation set to zero, so the feeder has buyers at noon. Positions are numbered from the transformer out.
        </p>
      </div>
      <Panel title="Today, settled slots only" bodyClassName="p-0">
        <div className="overflow-x-auto">
          <table className="num w-full text-xs">
            <thead>
              <tr className="legend border-b border-panel-etch text-left">
                <th className="px-4 py-2 font-normal">Household</th>
                <th className="px-3 py-2 font-normal">PV</th>
                <th className="px-3 py-2 text-right font-normal">From TX</th>
                <th className="px-3 py-2 text-right font-normal">Now, contracted</th>
                <th className="px-3 py-2 text-right font-normal">Sold today</th>
                <th className="px-3 py-2 text-right font-normal">Bought today</th>
                <th className="px-3 py-2 text-right font-normal">vs grid-only</th>
                <th className="px-3 py-2 font-normal">Meter key</th>
                <th className="px-4 py-2 font-normal">Ausgrid id</th>
              </tr>
            </thead>
            <tbody>
              {data.map((h) => {
                const now = h.now_export_wh ? h.now_export_wh : h.now_import_wh ? -h.now_import_wh : 0;
                return (
                  <tr key={h.id} className="border-b border-panel-etch last:border-0 hover:bg-panel-base">
                    <td className="px-4 py-2">
                      <Link href={`/households/${h.id}`} className="text-label underline decoration-panel-etch underline-offset-2">
                        {h.label}
                      </Link>
                    </td>
                    <td className="px-3 py-2 text-label-muted">{h.pv ? `${h.pv_kwp.toFixed(2)} kWp` : "—"}</td>
                    <td className="px-3 py-2 text-right text-label-muted">{h.position_m.toFixed(0)} m</td>
                    <td className={`px-3 py-2 text-right ${now > 0 ? "text-export" : now < 0 ? "text-import" : "text-label-muted"}`}>
                      {now ? `${kwhSigned(now)} kWh` : "—"}
                    </td>
                    <td className="px-3 py-2 text-right text-export">{h.sold_wh ? kwh(h.sold_wh) : "—"}</td>
                    <td className="px-3 py-2 text-right text-import">{h.bought_wh ? kwh(h.bought_wh) : "—"}</td>
                    <td className={`px-3 py-2 text-right ${h.saving_mp < 0 ? "text-alarm" : "text-label"}`}>
                      {h.saving_mp ? inrSigned(h.saving_mp) : "—"}
                    </td>
                    <td className="px-3 py-2 text-label-muted" title={h.meter_address}>
                      {shortHash(h.meter_address, 8, 4)}
                    </td>
                    <td className="px-4 py-2 text-label-muted">
                      #{h.customer} · {h.postcode}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Panel>
      <p className="text-xs text-label-muted">
        A negative figure in red means the household lost money against grid-only billing that day, almost always
        because a forecast promised energy the roof did not deliver and the shortfall was bought back at retail.
      </p>
    </div>
  );
}
