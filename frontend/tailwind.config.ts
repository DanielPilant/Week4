import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "Consolas", "monospace"],
      },
      colors: {
        // Bloomberg-ish palette
        terminal: {
          bg:      "#0a0e14",
          panel:   "#0f1419",
          border:  "#1c2530",
          text:    "#d3d8e0",
          dim:     "#5c6773",
          accent:  "#ffb454",
          green:   "#7fd962",
          red:     "#f07178",
          cyan:    "#39bae6",
          amber:   "#ffb454",
        },
      },
      boxShadow: {
        panel: "0 0 0 1px #1c2530, 0 0 24px rgba(0,0,0,0.45)",
      },
    },
  },
  plugins: [],
};

export default config;
