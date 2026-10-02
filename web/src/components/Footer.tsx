import Link from "next/link";

export function Footer() {
  return (
    <footer className="border-t border-panel-etch">
      <div className="mx-auto max-w-[1440px] px-4 py-5 text-xs leading-relaxed text-label-muted md:px-6">
        <p>
          <span className="text-label">Simulation-backed on real data.</span> There is no physical microgrid. Meters are
          simulated processes holding real ECDSA keys. Load and generation come from the Ausgrid Solar Home Electricity
          Data (Sydney, 2010–13); weather from Open-Meteo (ERA5 reanalysis). Prices are in rupees against an Indian
          tariff band applied to Australian households.{" "}
          <Link href="/method" className="underline decoration-panel-etch underline-offset-2 hover:text-label">
            What is real and what is not
          </Link>
          .
        </p>
      </div>
    </footer>
  );
}
