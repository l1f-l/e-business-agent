import type { Config } from "tailwindcss";

export default {
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        canvas: "#F7F5F1",
        surface: "#FFFFFF",
        ink: "#1B1B18",
        muted: "#6F6D66",
        faint: "#9B9890",
        line: "#E4E1DA",
        accent: {
          DEFAULT: "#C24A2B",
          soft: "#FBEDE8",
          deep: "#8F3419",
        },
        pine: "#2F5D4A",
      },
      fontFamily: {
        sans: [
          "-apple-system",
          "BlinkMacSystemFont",
          "Segoe UI",
          "PingFang SC",
          "Hiragino Sans GB",
          "Microsoft YaHei",
          "sans-serif",
        ],
      },
      keyframes: {
        rise: {
          "0%": { opacity: "0", transform: "translateY(6px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
      },
      animation: {
        rise: "rise .22s ease-out both",
      },
    },
  },
  plugins: [],
} satisfies Config;
