import Link from "next/link";
import { Mark } from "./Nav";

export function Footer() {
  return (
    <footer className="border-t border-panel-etch">
      <div className="mx-auto grid max-w-[1400px] gap-8 px-4 py-10 text-sm md:grid-cols-[1fr_1.4fr] md:px-8">
        <div>
          <div className="flex items-center gap-2.5">
            <Mark size={20} />
            <span className="display text-label">Local Energy Market</span>
          </div>
          <p className="mt-3 text-label-muted">
            Designed and built by <span className="text-label">Ayushman Jha</span>.
          </p>
          <div className="mt-4 flex flex-wrap gap-2">
            <Link href="/method" className="pill text-label hover:border-label-muted">
              How it works
            </Link>
            <Link href="/results" className="pill text-label hover:border-label-muted">
              Results
            </Link>
          </div>
        </div>
        <p className="leading-relaxed text-label-muted">
          <span className="text-label">Simulation-backed on real data.</span> There is no physical microgrid. Meters are
          simulated processes holding real ECDSA keys. Load and generation come from the Ausgrid Solar Home Electricity
          Data (Sydney, 2010–13); weather from Open-Meteo (ERA5 reanalysis). Prices are in rupees against an Indian tariff
          band applied to Australian households.{" "}
          <Link href="/method" className="text-label underline decoration-panel-etch underline-offset-4 hover:decoration-label-muted">
            What is real and what is not
          </Link>
          .
        </p>
      </div>
    </footer>
  );
}
