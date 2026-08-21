import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        void: "#0E1013",
        panel: "#171A1F",
        "panel-raised": "#1F232A",
        hairline: "#2A2F38",
        ink: "#E8E6E1",
        "ink-muted": "#8B9099",
        buy: "#3DDC84",
        sell: "#FF5C5C",
        signal: "#E8A33D",
      },
      fontFamily: {
        display: ["var(--font-display)", "sans-serif"],
        mono: ["var(--font-mono)", "monospace"],
        body: ["var(--font-body)", "sans-serif"],
      },
      backgroundImage: {
        "grid-fade":
          "linear-gradient(to bottom, rgba(232,163,61,0.06), transparent 60%)",
      },
    },
  },
  plugins: [],
};

export default config;
