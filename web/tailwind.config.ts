import type { Config } from "tailwindcss";

// Colour carries meaning, everywhere: amber = energy sold / injected,
// teal = energy bought / drawn, red = band violation or settlement mismatch,
// green = settled and verified. Everything else is black and greys.
const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
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
        serif: ["var(--font-serif)", "serif"],
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
