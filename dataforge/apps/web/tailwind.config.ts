import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        paper: "#F4F1EA",
        surface: "#FFFFFF",
        ink: "#141414",
        steel: "#6E6A63",
        line: "#D8D4CB",
        red: "#E02617",
        blue: "#1E58E8",
        yellow: "#F5A800",
        green: "#1F7A33",
      },
      fontFamily: {
        display: ["var(--font-display)"],
        body: ["var(--font-body)"],
        mono: ["var(--font-mono)"],
      },
      boxShadow: {
        bau: "5px 5px 0 0 #141414",
        "bau-sm": "3px 3px 0 0 #141414",
      },
    },
  },
  plugins: [],
};
export default config;
