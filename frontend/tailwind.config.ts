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
        obsidian: "#030305",
        iron: "#1C1C21",
        "iron-light": "#2D2D35",
        ember: "#FF2A2A",
        burnt: "#FF6B00",
        frost: "#4D9FFF",
        bone: "#F5F5FA",
      },
      fontFamily: {
        bebas: ["var(--font-bebas)"],
        inter: ["var(--font-inter)"],
      },
      borderWidth: {
        '2': '2px',
        '3': '3px',
      },
      boxShadow: {
        'runic-glow-ember': '0 0 15px 2px rgba(139, 0, 0, 0.4)',
        'runic-glow-burnt': '0 0 15px 2px rgba(194, 65, 12, 0.4)',
        'runic-glow-frost': '0 0 15px 2px rgba(59, 130, 246, 0.4)',
      }
    },
  },
  plugins: [],
};
export default config;
