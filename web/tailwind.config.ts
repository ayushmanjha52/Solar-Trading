import type { Config } from "tailwindcss";

// Substation mimic panel vocabulary. Each colour means one thing, everywhere:
// amber = energy injected / selling, cyan = energy drawn / buying,
// alarm = band violation or settlement mismatch, armed = settled and verified.
const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    borderRadius: { none: "0", DEFAULT: "2px", sm: "2px" },
    extend: {
      colors: {
        panel: {
          base: "var(--panel-base)",
          raised: "var(--panel-raised)",
          etch: "var(--panel-etch)",
        },
        label: { DEFAULT: "var(--label)", muted: "var(--label-muted)" },
        export: "var(--flow-export)",
        import: "var(--flow-import)",
        alarm: "var(--state-alarm)",
        armed: "var(--state-armed)",
      },
      fontFamily: {
        display: ["var(--font-display)", "sans-serif"],
        sans: ["var(--font-sans)", "sans-serif"],
        mono: ["var(--font-mono)", "monospace"],
      },
      fontSize: {
        "2xs": ["0.6875rem", { lineHeight: "1rem" }],
      },
    },
  },
  plugins: [],
};

export default config;
