import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import Image from "next/image";
import type { ReactNode } from "react";
import { WheelingChart } from "./WheelingChart";

export const metadata = { title: "Results · Local Energy Market" };
export const dynamic = "force-dynamic";

// Result files are produced by Python (ml/evaluate.py, sim/study.py); their shapes are read loosely here.
function readJson(rel: string): any | null {
  const file = path.join(process.cwd(), "..", rel);
  return existsSync(file) ? JSON.parse(readFileSync(file, "utf8")) : null;
}

function Section({ title, children, id }: { title: string; children: ReactNode; id: string }) {
  return (
    <section id={id} className="border-t border-panel-etch pt-6">
      <h2 className="display text-lg uppercase text-label">{title}</h2>
      <div className="mt-3 space-y-3 text-sm leading-relaxed text-label">{children}</div>
    </section>
  );
}

function OracleNote({ fc }: { fc: any }) {
  const t = fc.tables["PV households, sun up"];
  if (!t) return null;
  const real = t.rows.find((r: any) => r.model === fc.market_model) ?? t.rows.find((r: any) => r.model.startsWith("XGBoost +"));
  const oracle = t.rows.find((r: any) => r.model.includes("ORACLE"));
  const pers = t.rows.find((r: any) => r.model === "Persistence");
  const naive = t.rows.find((r: any) => r.model === "Seasonal naive");
  if (!real || !oracle || !pers || !naive) return null;
  const gain = 1 - oracle.mae_wh / real.mae_wh;
  return (
    <ul className="list-disc space-y-2 pl-5 text-sm marker:text-label-muted">
      <li>
        On PV households in daylight, the learned model cuts MAE by{" "}
        <span className="num">{(real.skill_vs_persistence * 100).toFixed(0)}%</span> against persistence; seasonal naive,
        the agents&apos; forecast before this milestone, is{" "}
        <span className="num">{Math.abs(naive.skill_vs_persistence * 100).toFixed(0)}%</span>{" "}
        {naive.skill_vs_persistence < 0 ? "worse" : "better"} than persistence. Two slots ahead, the last reading beats
        yesterday.
      </li>
      <li>
        Handing the model the target slot&apos;s weather (the oracle) improves daylight MAE by only{" "}
        <span className="num">{(gain * 100).toFixed(1)}%</span>. That is a finding, not a bug: ERA5 irradiance correlates
        with generation about as strongly as the household&apos;s own meter reading from an hour earlier, which the
        deployable model already has. At this horizon leakage would have bought little; at a day-ahead horizon, with no
        recent reading to lean on, the same leak would flatter a model far more.
      </li>
    </ul>
  );
}

function StrategyFindings({ st }: { st: any }) {
  const row = (v: string, p: string) => st.strategies.find((r: any) => r.volume === v && r.price === p);
  const naive = row("Seasonal naive", "truthful");
  const p50 = row("Forecast P50", "truthful");
  const nvT = row("Newsvendor quantile", "truthful");
  const nvR = row("Newsvendor quantile", "random");
  const p50R = row("Forecast P50", "random");
  const sym = row("Forecast P50", "shaded");
  if (!naive || !p50 || !nvT || !nvR || !p50R || !sym) return null;
  return (
    <ul className="list-disc space-y-2 pl-5 marker:text-label-muted">
      <li>
        Forecast quality is worth money. Seasonal-naive volumes capture{" "}
        <span className="num">{Math.round(naive.share_of_oracle * 100)}%</span> of what perfect foresight would save; the
        learned forecast&apos;s median captures <span className="num">{Math.round(p50.share_of_oracle * 100)}%</span>, and
        over-committed energy falls from <span className="num">{Math.round(naive.overcommit_kwh)}</span> to{" "}
        <span className="num">{Math.round(p50.overcommit_kwh)}</span> kWh.
      </li>
      <li>
        With truthful pricing the cleared price is always the band&apos;s midpoint (
        <span className="num">₹{nvT.mean_price_inr.toFixed(2)}</span>, sd{" "}
        <span className="num">₹{nvT.price_sd_inr.toFixed(2)}</span>): the lowest accepted bid is always retail and the
        highest accepted offer always feed-in. The price carries no information about scarcity. So the newsvendor quantile
        is exactly 0.5 and the newsvendor rule equals the median (
        {rupees(nvT.saving_inr)} vs {rupees(p50.saving_inr)}).
      </li>
      <li>
        When prices move off the midpoint, the optimal quantile moves with them. Under random pricing the newsvendor rule
        saves <span className="num">{rupees(nvR.saving_inr)}</span> against{" "}
        <span className="num">{rupees(p50R.saving_inr)}</span> for the median (sd over seeds{" "}
        <span className="num">{rupees(nvR.saving_sd_inr)}</span>). The risk the forecast must price is asymmetric only to
        the extent that the price sits away from the middle of the band.
      </li>
      <li>
        Shading by everyone at once changes nothing (shaded = truthful, row for row): the midpoint rule cancels symmetric
        shading. Only one-sided deviation can move the price; see incentive compatibility below.
      </li>
    </ul>
  );
}

const rupees = (x: number, digits = 0) =>
  `${x < 0 ? "−" : ""}₹${Math.abs(x).toLocaleString("en-IN", { minimumFractionDigits: digits, maximumFractionDigits: digits })}`;

function Missing({ cmd }: { cmd: string }) {
  return (
    <p className="text-label-muted">
      Not generated yet. Run <code className="num text-label">{cmd}</code>.
    </p>
  );
}

export default function ResultsPage() {
  const fc = readJson("reports/forecasting/results.json");
  const st = readJson("reports/study/results.json");

  return (
    <div className="space-y-8 pb-6">
      <div>
        <h1 className="display text-2xl uppercase text-label">Results</h1>
        <p className="mt-2 max-w-3xl text-sm leading-relaxed text-label-muted">
          Milestone 2 (forecasting) and Milestone 6 (the study). Every number on this page is regenerated from scratch by{" "}
          <code className="num text-label">python -m ml.evaluate</code> and <code className="num text-label">python -m sim.study</code>{" "}
          on fixed seeds. Negative results are reported as they came out.
        </p>
      </div>

      <Section id="forecasting" title="Forecasting">
        {!fc ? (
          <Missing cmd="python -m ml.evaluate" />
        ) : (
          <>
            <p className="max-w-3xl text-label-muted">
              Task: {fc.task}. Chronological splits; the test window ({fc.splits.test}) is used once, for these tables.
              Model selection used validation pinball loss only. Units: Wh per half hour.
            </p>
            {Object.entries(fc.tables).map(([name, t]: [string, any]) => (
              <div key={name} className="overflow-x-auto">
                <div className="legend mb-2">
                  {name} · {t.households} households · {t.n.toLocaleString("en-IN")} slots
                </div>
                <table className="num w-full min-w-[760px] text-xs">
                  <thead>
                    <tr className="legend border-b border-panel-etch text-left">
                      <th className="py-2 pr-3 font-normal">Model</th>
                      <th className="py-2 pr-3 text-right font-normal">MAE</th>
                      <th className="py-2 pr-3 text-right font-normal">95% CI</th>
                      <th className="py-2 pr-3 text-right font-normal">RMSE</th>
                      <th className="py-2 pr-3 text-right font-normal">vs persistence</th>
                      <th className="py-2 pr-3 text-right font-normal">Pinball</th>
                      <th className="py-2 text-right font-normal">P10–P90 holds</th>
                    </tr>
                  </thead>
                  <tbody>
                    {t.rows.map((r: any) => {
                      const oracle = r.model.includes("ORACLE");
                      return (
                        <tr key={r.model} className={`border-b border-panel-etch last:border-0 ${oracle ? "text-label-muted" : ""}`}>
                          <td className="py-1.5 pr-3">
                            {r.model}
                            {r.note && <div className="text-2xs text-label-muted">{r.note}</div>}
                          </td>
                          <td className="py-1.5 pr-3 text-right">{r.mae_wh.toFixed(1)}</td>
                          <td className="py-1.5 pr-3 text-right text-label-muted">
                            {r.mae_ci_wh[0].toFixed(1)}–{r.mae_ci_wh[1].toFixed(1)}
                          </td>
                          <td className="py-1.5 pr-3 text-right">{r.rmse_wh.toFixed(1)}</td>
                          <td className={`py-1.5 pr-3 text-right ${r.skill_vs_persistence < 0 ? "text-alarm" : ""}`}>
                            {(r.skill_vs_persistence * 100).toFixed(1)}%
                          </td>
                          <td className="py-1.5 pr-3 text-right">{r.pinball_wh == null ? "—" : r.pinball_wh.toFixed(1)}</td>
                          <td className="py-1.5 text-right">{r.coverage_80 == null ? "—" : `${(r.coverage_80 * 100).toFixed(1)}%`}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            ))}
            <p className="max-w-3xl text-label-muted">
              The market&apos;s agents use <span className="text-label">{fc.market_model}</span>, chosen on validation
              pinball. A well-calibrated P10–P90 band holds the outcome 80% of the time. The oracle row is the same model
              handed the target slot&apos;s actual weather, which no bidder could have had.
            </p>
            <OracleNote fc={fc} />
            {existsSync(path.join(process.cwd(), "public", "figures", "forecast_fan.png")) && (
              <div className="border border-panel-etch">
                <Image src="/figures/forecast_fan.png" alt="Quantile forecast band against metered energy for one PV household over four days" width={1680} height={588} className="h-auto w-full" />
              </div>
            )}
          </>
        )}
      </Section>

      <Section id="strategies" title="Strategies">
        {!st ? (
          <Missing cmd="python -m sim.study" />
        ) : (
          <>
            <p className="max-w-3xl text-label-muted">
              {st.households} households, {st.period.strategies[0]} to {st.period.strategies[1]}. Saving is what the
              households together paid less than billing the same signed meter readings with no market (grid-only bill
              for the period: {rupees(st.grid_only_bill_inr)}). Random pricing is averaged over seeds.
            </p>
            <div className="overflow-x-auto">
              <table className="num w-full min-w-[820px] text-xs">
                <thead>
                  <tr className="legend border-b border-panel-etch text-left">
                    <th className="py-2 pr-3 font-normal">Volume rule</th>
                    <th className="py-2 pr-3 font-normal">Price rule</th>
                    <th className="py-2 pr-3 text-right font-normal">Saving</th>
                    <th className="py-2 pr-3 text-right font-normal">± sd</th>
                    <th className="py-2 pr-3 text-right font-normal">Per home-year</th>
                    <th className="py-2 pr-3 text-right font-normal">Of oracle</th>
                    <th className="py-2 pr-3 text-right font-normal">Traded kWh</th>
                    <th className="py-2 pr-3 text-right font-normal">Over-committed kWh</th>
                    <th className="py-2 text-right font-normal">Price (sd)</th>
                  </tr>
                </thead>
                <tbody>
                  <tr className="border-b border-panel-etch text-label-muted">
                    <td className="py-1.5 pr-3">No market</td>
                    <td className="py-1.5 pr-3">—</td>
                    <td className="py-1.5 pr-3 text-right">₹0</td>
                    <td className="py-1.5 pr-3 text-right">—</td>
                    <td className="py-1.5 pr-3 text-right">₹0</td>
                    <td className="py-1.5 pr-3 text-right">0%</td>
                    <td className="py-1.5 pr-3 text-right">0</td>
                    <td className="py-1.5 pr-3 text-right">0</td>
                    <td className="py-1.5 text-right">—</td>
                  </tr>
                  {st.strategies.map((r: any) => (
                    <tr key={r.volume + r.price} className={`border-b border-panel-etch last:border-0 ${r.volume.includes("oracle") ? "text-label-muted" : ""}`}>
                      <td className="py-1.5 pr-3">{r.volume}</td>
                      <td className="py-1.5 pr-3">{r.price}</td>
                      <td className={`py-1.5 pr-3 text-right ${r.saving_inr < 0 ? "text-alarm" : ""}`}>{rupees(r.saving_inr)}</td>
                      <td className="py-1.5 pr-3 text-right text-label-muted">{r.runs > 1 ? rupees(r.saving_sd_inr) : "—"}</td>
                      <td className="py-1.5 pr-3 text-right">{rupees(r.saving_inr_per_household_year)}</td>
                      <td className="py-1.5 pr-3 text-right">{r.share_of_oracle == null ? "—" : `${Math.round(r.share_of_oracle * 100)}%`}</td>
                      <td className="py-1.5 pr-3 text-right">{Math.round(r.traded_kwh).toLocaleString("en-IN")}</td>
                      <td className="py-1.5 pr-3 text-right">{Math.round(r.overcommit_kwh).toLocaleString("en-IN")}</td>
                      <td className="py-1.5 text-right">
                        ₹{r.mean_price_inr.toFixed(2)} <span className="text-label-muted">({r.price_sd_inr.toFixed(2)})</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <StrategyFindings st={st} />
          </>
        )}
      </Section>

      <Section id="wheeling" title="Wheeling charge">
        {!st ? (
          <Missing cmd="python -m sim.study" />
        ) : (
          <>
            <p className="max-w-3xl text-label-muted">
              A network charge per kWh delivered, paid by buyers, narrows the band from the top. Truthful pricing, so the
              market keeps clearing until the band closes at{" "}
              {rupees((st.tariff.retail_paise - st.tariff.feed_in_paise) / 100, 2)}. The question that matters is
              earlier: when do households stop gaining at all, once forecast errors are paid for?
            </p>
            <WheelingChart curves={st.wheeling} />
            <ul className="list-disc space-y-1 pl-5 marker:text-label-muted">
              {Object.entries(st.wheeling).map(([v, c]: [string, any]) => (
                <li key={v}>
                  {v === "newsvendor" ? "Newsvendor quantile" : "Seasonal naive"}: households stop gaining at{" "}
                  <span className="num">
                    {c.saving_zero_at_paise == null ? "no charge below closure" : `${rupees(c.saving_zero_at_paise / 100, 2)}/kWh`}
                  </span>
                  .
                </li>
              ))}
              <li>
                Recovering only the cost of losses needs about{" "}
                <span className="num">{rupees(st.loss_cost_paise_per_kwh / 100, 3)}/kWh</span>.
              </li>
            </ul>
          </>
        )}
      </Section>

      <Section id="ic" title="Incentive compatibility">
        {!st ? (
          <Missing cmd="python -m sim.study" />
        ) : (
          <>
            <p className="max-w-3xl text-label-muted">
              Everyone bids their reservation price except one household, which shades its price by a share of the band.
              Repeated for every household, {st.period.incentive_compatibility[0]} to {st.period.incentive_compatibility[1]}.
              If shading pays, the uniform-price auction is not incentive-compatible for that household.
            </p>
            <div className="overflow-x-auto">
              <table className="num w-full min-w-[680px] text-xs">
                <thead>
                  <tr className="legend border-b border-panel-etch text-left">
                    <th className="py-2 pr-3 font-normal">Deviant</th>
                    <th className="py-2 pr-3 text-right font-normal">Shade</th>
                    <th className="py-2 pr-3 text-right font-normal">Gain</th>
                    <th className="py-2 pr-3 text-right font-normal">Mean gain</th>
                    <th className="py-2 pr-3 text-right font-normal">Best</th>
                    <th className="py-2 pr-3 text-right font-normal">Everyone else</th>
                    <th className="py-2 text-right font-normal">Total welfare</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.values(st.incentive_compatibility.summary).map((x: any) => (
                    <tr key={`${x.group}${x.shade}`} className="border-b border-panel-etch last:border-0">
                      <td className="py-1.5 pr-3">{x.group}</td>
                      <td className="py-1.5 pr-3 text-right">{Math.round(x.shade * 100)}%</td>
                      <td className="py-1.5 pr-3 text-right">
                        {x.households_that_gain} of {x.households}
                      </td>
                      <td className={`py-1.5 pr-3 text-right ${x.mean_gain_inr > 0 ? "text-alarm" : ""}`}>{rupees(x.mean_gain_inr, 2)}</td>
                      <td className="py-1.5 pr-3 text-right">{rupees(x.max_gain_inr, 2)}</td>
                      <td className="py-1.5 pr-3 text-right">{rupees(x.mean_others_change_inr, 2)}</td>
                      <td className="py-1.5 text-right">{rupees(x.mean_welfare_change_inr, 2)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="max-w-3xl text-label-muted">
              Read with the supply on this feeder in mind: at most hours there is less surplus than demand. A seller who
              asks more still gets filled and, as the highest accepted offer, raises the uniform price for every seller. A
              buyer who bids less is simply the last bid in the queue and gets rationed out. So shading pays sellers and
              never pays buyers here, and what sellers gain buyers lose: the auction is not strategy-proof, but the damage
              is a transfer more than lost welfare. Gains in red are where the mechanism rewards departing from the truth.
            </p>
          </>
        )}
      </Section>
    </div>
  );
}
