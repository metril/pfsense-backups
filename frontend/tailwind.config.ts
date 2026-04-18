import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        border: "hsl(var(--border))",
        bg: "hsl(var(--bg))",
        fg: "hsl(var(--fg))",
        muted: "hsl(var(--muted))",
        "muted-fg": "hsl(var(--muted-fg))",
        accent: "hsl(var(--accent))",
        "accent-fg": "hsl(var(--accent-fg))",
        danger: "hsl(var(--danger))",
        ok: "hsl(var(--ok))",
        warn: "hsl(var(--warn))",
        info: "hsl(var(--info))",
      },
    },
  },
  plugins: [],
} satisfies Config;
