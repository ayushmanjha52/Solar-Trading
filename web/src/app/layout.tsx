import type { Metadata } from "next";
import { Bricolage_Grotesque, Instrument_Sans, Instrument_Serif, JetBrains_Mono } from "next/font/google";
import { Footer } from "@/components/Footer";
import { Nav } from "@/components/Nav";
import "./globals.css";

const display = Bricolage_Grotesque({ subsets: ["latin"], variable: "--font-display", display: "swap" });
const serif = Instrument_Serif({ subsets: ["latin"], weight: "400", style: ["italic"], variable: "--font-serif", display: "swap" });
const sans = Instrument_Sans({ subsets: ["latin"], variable: "--font-sans", display: "swap" });
const mono = JetBrains_Mono({ subsets: ["latin"], weight: ["400", "500"], variable: "--font-mono", display: "swap" });

export const metadata: Metadata = {
  title: "Local Energy Market",
  description:
    "Neighbours trade rooftop solar on one low-voltage street. The book clears every half hour at one price, and every trade is settled against signed meter readings.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${display.variable} ${serif.variable} ${sans.variable} ${mono.variable}`}>
      <body className="flex min-h-screen flex-col text-label">
        <Nav />
        <main className="mx-auto w-full max-w-[1400px] flex-1 px-4 pb-16 pt-8 md:px-8">{children}</main>
        <Footer />
      </body>
    </html>
  );
}
