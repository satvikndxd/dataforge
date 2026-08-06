import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        // ── Classic Bauhaus palette ──
        paper: "#F4F1EA",
        surface: "#FFFFFF",
        ink: "#141414",
        steel: "#6E6A63",
        line: "#D8D4CB",
        // Legacy names remapped onto the Bauhaus palette so existing
        // utility classes resolve to the new design system.
        obsidian: "#F4F1EA", // page background (was near-black)
        iron: "#6E6A63", // muted gray
        "iron-light": "#D8D4CB", // hairline
        ember: "#E02617", // Bauhaus red
        burnt: "#F5A800", // Bauhaus yellow
        frost: "#1E58E8", // Bauhaus blue
        bone: "#141414", // ink text
      },
      fontFamily: {
        display: ["var(--font-display)"],
        inter: ["var(--font-inter)"],
        mono: ["var(--font-mono)"],
      },
      borderWidth: {
        "2": "2px",
        "3": "3px",
        "4": "4px",
      },
      boxShadow: {
        "bau-ink": "6px 6px 0 0 #141414",
        "bau-red": "6px 6px 0 0 #E02617",
        "bau-blue": "6px 6px 0 0 #1E58E8",
        "bau-yellow": "6px 6px 0 0 #F5A800",
      },
    },
  },
  plugins: [],
};
export default config;
