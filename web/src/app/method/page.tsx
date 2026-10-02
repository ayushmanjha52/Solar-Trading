import Image from "next/image";
import type { ReactNode } from "react";
import { marketConfig } from "@/lib/server";

export const metadata = { title: "Method · Local Energy Market" };
export const dynamic = "force-dynamic";

function Section({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  return (
    <section id={id} className="scroll-mt-6 border-t border-panel-etch pt-6">
      <h2 className="display text-lg uppercase text-label">{title}</h2>
      <div className="mt-3 max-w-3xl space-y-3 text-sm leading-relaxed text-label">{children}</div>
    </section>
  );
}

function Muted({ children }: { children: ReactNode }) {
  return <p className="text-label-muted">{children}</p>;
}

function Code({ children }: { children: ReactNode }) {
  return <code className="num text-[0.8125rem] text-label">{children}</code>;
}

const rupee = (paise: number) => `₹${(paise / 100).toFixed(2)}`;

export default function MethodPage() {
  const c = marketConfig();
  const fit = c.feed_in_tariff_paise_per_kwh;
  const retail = c.retail_tariff_paise_per_kwh;
  const wheel = c.wheeling_charge_paise_per_kwh;

  const ledger: [string, string, string][] = [
    ["Half-hourly load and generation", "Real", "Ausgrid Solar Home Electricity Data, 2012-13, 24 households from one ERA5 weather cell (Sydney lower north shore)."],
    ["Meter keys and signatures", "Real", "secp256k1 keys, EIP-712 typed-data signatures, verified by recovery. Keys are derived from the seed so runs reproduce."],
    ["Commitments", "Real", "keccak256 over the ABI-encoded trades, identical in Python, the browser (viem) and Solidity."],
    ["Clearing, losses, settlement", "Real computation", "Integer Wh and paise; 960+ unit and property tests."],
    ["Feeder topology", "Simulated", "Ausgrid publishes postcodes, not networks. Positions along a 420 m backbone and service lengths are seeded random."],
    ["Who has PV", "Simulated", "Every Ausgrid home has PV. 10 of 24 keep it; 14 keep their real load with generation removed, so there are buyers at noon."],
    ["Bidding agents", "Simulated", "Volume: the newsvendor quantile of an out-of-sample P10/P50/P90 forecast. Price: seeded random shade from the reservation price."],
    ["Forecasts", "Real computation", "Trained on 2010-12, tested once on 2012-13 against persistence and naive baselines. See Results."],
    ["Strategy and wheeling study", "Real computation", "Six-month backtests of strategies, wheeling charges and unilateral deviations. See Results."],
    ["The clock", "Simulated", "One half hour every few seconds, replaying spring and summer 2012-13."],
    ["Public testnet deployment", "Not built", "Polygon Amoy needs a funded key you hold. A local Anvil chain anchors the same transactions when it is running."],
    ["Durable storage", "Not built", "The live book and recent history live in the engine's memory (Redis and Postgres in production)."],
  ];

  return (
    <div className="space-y-8 pb-6">
      <div>
        <h1 className="display text-2xl uppercase text-label">Method</h1>
        <p className="mt-2 max-w-3xl text-sm leading-relaxed text-label-muted">
          A peer-to-peer market for one residential LV feeder. Households with rooftop solar sell surplus to neighbours
          instead of exporting it to the utility. The book clears every half hour at one price; every settlement is
          checked against signed meter readings. This page says what is real, what is simulated, what is not built,
          and where each mechanism stops being accurate.
        </p>
        <nav className="mt-4 flex flex-wrap gap-x-4 gap-y-1 text-xs">
          {[
            ["real", "Real or simulated"],
            ["band", "The band"],
            ["clearing", "Clearing"],
            ["losses", "Losses"],
            ["trust", "Commit, settle, trust"],
            ["settlement", "Settlement"],
            ["data", "Data checks"],
            ["limits", "Known limits"],
          ].map(([id, t]) => (
            <a key={id} href={`#${id}`} className="text-label-muted underline decoration-panel-etch underline-offset-2 hover:text-label">
              {t}
            </a>
          ))}
        </nav>
      </div>

      <Section id="real" title="Real or simulated">
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <tbody>
              {ledger.map(([what, status, note]) => (
                <tr key={what} className="border-b border-panel-etch align-top last:border-0">
                  <td className="py-2 pr-4 text-label">{what}</td>
                  <td
                    className={`num whitespace-nowrap py-2 pr-4 uppercase tracking-wider ${
                      status.startsWith("Real") ? "text-armed" : status === "Simulated" ? "text-label" : "text-label-muted"
                    }`}
                  >
                    {status}
                  </td>
                  <td className="py-2 text-label-muted">{note}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>

      <Section id="band" title="The band">
        <p>
          A household only gains by trading locally if it beats the grid. A seller must receive more than the feed-in
          tariff (<span className="num">{rupee(fit)}</span>), and a buyer must pay less than retail (
          <span className="num">{rupee(retail)}</span>) once any wheeling charge (
          <span className="num">{rupee(wheel)}</span>) is added. So every cleared price sits strictly inside{" "}
          <span className="num">
            ({rupee(fit)}, {rupee(retail - wheel)})
          </span>
          . Outside that band the market has no reason to exist.
        </p>
        <p>
          The rule is enforced three times, deliberately: in the web API route before an order reaches the engine, in
          the Python engine when it accepts orders and again when it clears, and in the settlement contract on chain.
          Each layer can be reached without the others.
        </p>
        <Muted>
          The tariffs are Indian; the households are Australian (about 6.6 MWh a year each, 1.7 kWp average PV). The
          price band is a parameter applied to real Australian load shapes, not a model of an Indian feeder.
        </Muted>
      </Section>

      <Section id="clearing" title="Clearing">
        <p>
          Uniform-price double auction per settlement period. Bids are walked from the highest price down, offers from
          the lowest up, matching quantity while the bid still meets the offer. Everyone who trades gets one price: the
          midpoint of the last matched bid and offer. Since both lie inside the band, so does the midpoint.
        </p>
        <p>
          Property tests on 500 random books check that volume bought equals volume sold, nobody trades at a price
          worse than their own limit, and no unfilled bid and unfilled offer could still trade with each other.
        </p>
        <Muted>
          Matching is off-chain on purpose. An order-book walk on chain costs gas in proportion to the number of
          participants and puts a hot loop in the most expensive place to run one. The chain only checks the result.
        </Muted>
      </Section>

      <Section id="losses" title="Losses">
        <p>
          Energy injected by a seller exceeds energy received by a buyer; the difference is heat in the conductors.
          Each trade follows a path: the seller&apos;s single-phase service cable (16 mm² Cu, 1.15 Ω/km), the backbone
          between the two poles (95 mm² Al, 0.32 Ω/km), and the buyer&apos;s service. The loss fraction is
        </p>
        <p className="num border border-panel-etch bg-panel-raised px-4 py-3 text-xs">
          loss / P = P · R<sub>path</sub> / (V<sub>phase</sub> · pf)², &nbsp; R<sub>path</sub> counts phase and neutral
        </p>
        <p>
          On this feeder that comes to 0.1 to 0.6 percent per trade: neighbours trading a few hundred watts lose very
          little. The feeder mimic draws each pulse thinning by exactly that share, so at true scale the thinning is
          nearly invisible. The &ldquo;magnify ×50&rdquo; switch exists to show the mechanism and says so on screen.
          Trades are capped at a 5 percent loss; volume over the cap is not traded.
        </p>
        <Muted>
          What this model is not: losses are quadratic in current, so simultaneous trades do not add; the true loss
          depends on net flow in each conductor segment. Voltage rise at the end of a feeder full of exporting PV,
          thermal limits, reactive power and phase imbalance are ignored. A correct treatment needs an AC load-flow
          solve on the feeder model. The cost of losses is paid by the market operator and is what a wheeling charge
          would recover; with no wheeling charge it is shown as unrecovered.
        </Muted>
      </Section>

      <Section id="trust" title="Commit, settle, and the oracle problem">
        <p>
          At gate closure the operator publishes keccak256 of the cleared trades and price, before any meter has
          reported. Settlement must reproduce that hash from the trades it settles. Without this step the operator could
          run the auction, watch the outcome, and settle a different one. With it, a restated trade fails the check:
          the test suite does exactly that and watches verification fail.
        </p>
        <p>
          A contract cannot observe a kilowatt-hour. It can only verify that a reading was signed by the key that the
          registry associates with a meter. The oracle problem is relocated, not solved: trust moves into the
          meter&apos;s secure element, which must keep its key secret and sign only what it measured. Here the meters
          are software, so that trust is assumed, and this page says so.
        </p>
        <Muted>
          On every settlement page, &ldquo;Verify in this browser&rdquo; recomputes the commitment and recovers all
          24 signatures with viem, independently of the engine&apos;s own check.
        </Muted>
      </Section>

      <Section id="settlement" title="Settlement in two passes">
        <p>
          <span className="text-label">Pass 1, market.</span> Trades fixed at gate closure settle at the cleared price
          whatever happens next. Sellers are paid for energy injected; buyers pay for energy delivered (plus wheeling).
        </p>
        <p>
          <span className="text-label">Pass 2, imbalance.</span> Forecasts are wrong, so metered energy differs from
          the contract. Each household&apos;s deviation settles against the grid: short pays retail, long is paid
          feed-in. A seller who promised sun that did not arrive buys the shortfall back at retail, which is exactly
          the risk a probabilistic forecast should price.
        </p>
        <p>
          <span className="text-label">Counterfactual.</span> Every saving is measured against billing the same signed
          readings with no market at all. Money is integer milli-paise; the settlement page shows that buyers&apos;
          payments equal sellers&apos; receipts plus the cost of losses, exactly.
        </p>
      </Section>

      <Section id="data" title="Data checks">
        <p>
          Ausgrid has withdrawn the dataset from its website; the archive used is a third-party copy, pinned by SHA-256.
          The parser reproduces Ausgrid&apos;s own published annual means and medians to the kWh. The files are in
          Sydney clock time with daylight saving yet always have 48 columns: on spring-forward days two columns are
          placeholders (always zero) and are dropped; on fall-back days the repeated hour is summed into one column and
          is split. After conversion, generation is centred within 8 minutes of computed solar noon in every month;
          left in clock time, summer would sit 60 minutes late.
        </p>
        <div className="border border-panel-etch">
          <Image
            src="/figures/sanity_milestone1.png"
            alt="Milestone 1 sanity figure: generation by day and slot with the horizon overlaid, mean profiles, clock check before and after daylight-saving conversion, and weather alignment by lag."
            width={2100}
            height={1440}
            className="h-auto w-full"
          />
        </div>
      </Section>

      <Section id="limits" title="Known limits">
        <ul className="list-disc space-y-2 pl-5 marker:text-label-muted">
          <li>Forecasts are two slots ahead and use no weather, because no weather forecast archive covers 2012-13. ERA5 is reanalysis: what the weather was, not what a household could have known. It appears on the Results page only as a labelled oracle.</li>
          <li>Flow allocation is greedy nearest-first, not the loss-minimising transport solution.</li>
          <li>Agent prices in the live demo are seeded random inside the band; the study tests truthful and shaded pricing and unilateral deviations, over two months for incentive compatibility.</li>
          <li>The feeder is synthetic and the PV share is chosen. Real penetration and topology would change volumes and losses.</li>
          <li>History is kept in memory for three simulated days; restarting the engine restarts the market.</li>
        </ul>
      </Section>
    </div>
  );
}
