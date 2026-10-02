import type { Metadata } from "next";
import { Archivo, IBM_Plex_Mono, IBM_Plex_Sans } from "next/font/google";
import { Footer } from "@/components/Footer";
import { Nav } from "@/components/Nav";
import "./globals.css";

// Archivo at 125% width is Archivo Expanded: a wide industrial grotesque for the few display moments.
const display = Archivo({ subsets: ["latin"], axes: ["wdth"], variable: "--font-display", display: "swap" });
// IBM Plex was drawn for engineering documentation; Mono carries every number.
const sans = IBM_Plex_Sans({ subsets: ["latin"], weight: ["400", "500", "600"], variable: "--font-sans", display: "swap" });
const mono = IBM_Plex_Mono({ subsets: ["latin"], weight: ["400", "500"], variable: "--font-mono", display: "swap" });

export const metadata: Metadata = {
  title: "Local Energy Market",
  description:
    "A peer-to-peer market for a residential LV feeder, cleared every half hour and settled against signed meter readings. Simulation-backed on real Ausgrid data.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${display.variable} ${sans.variable} ${mono.variable}`}>
      <body className="flex min-h-screen flex-col bg-panel-base text-label antialiased">
        <Nav />
        <main className="mx-auto w-full max-w-[1440px] flex-1 px-4 pb-12 pt-6 md:px-6">{children}</main>
        <Footer />
      </body>
    </html>
  );
}
