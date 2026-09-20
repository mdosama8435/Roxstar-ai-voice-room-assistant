import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        background: "#090a0f",
        surface: {
          DEFAULT: "#11131a",
          secondary: "#161924",
          tertiary: "#1d2130",
          border: "#262b3d",
        },
        roxstar: {
          purple: "#9333ea",
          violet: "#a855f7",
          pink: "#ec4899",
          blue: "#3b82f6",
          cyan: "#06b6d4",
          glow: "rgba(168, 85, 247, 0.15)",
        },
      },
      boxShadow: {
        glass: "0 8px 32px 0 rgba(0, 0, 0, 0.37)",
        "glow-purple": "0 0 25px -5px rgba(168, 85, 247, 0.3)",
        "glow-pink": "0 0 25px -5px rgba(236, 72, 153, 0.3)",
        "glow-blue": "0 0 25px -5px rgba(59, 130, 246, 0.3)",
      },
      backdropBlur: {
        xs: "2px",
      },
    },
  },
  plugins: [],
};

export default config;
