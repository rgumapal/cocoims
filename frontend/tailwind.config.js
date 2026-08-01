/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ["selector", '[data-theme="dark"]'],
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      // Every entry below reads a CSS custom property from
      // src/design/tokens.css. This is the enforcement mechanism behind
      // CLAUDE.md DESIGN: "Components reference semantic tokens only,
      // never primitives, never raw hex" — a class like `bg-surface` or
      // `text-negative` is the only way to reach a color at all; there is
      // no Tailwind default palette available to reach for instead.
      colors: {
        bg: "var(--bg)",
        surface: "var(--surface)",
        "surface-2": "var(--surface-2)",
        "surface-hover": "var(--surface-hover)",
        border: "var(--border)",
        "border-strong": "var(--border-strong)",

        text: "var(--text)",
        "text-2": "var(--text-2)",
        "text-3": "var(--text-3)",
        "text-invert": "var(--text-invert)",

        accent: "var(--accent)",
        "accent-hover": "var(--accent-hover)",
        "accent-fg": "var(--accent-fg)",
        "accent-subtle": "var(--accent-subtle)",

        "header-bg": "var(--header-bg)",
        "header-fg": "var(--header-fg)",

        positive: "var(--positive)",
        attention: "var(--attention)",
        negative: "var(--negative)",
        "positive-bg": "var(--positive-bg)",
        "attention-bg": "var(--attention-bg)",
        "negative-bg": "var(--negative-bg)",
      },
      fontFamily: {
        ui: ["IBM Plex Sans", "system-ui", "sans-serif"],
        data: ["IBM Plex Mono", "ui-monospace", "monospace"],
        dense: ["IBM Plex Sans Condensed", "sans-serif"],
      },
      // SPEC §12.3's type scale: size/line-height/weight per entry.
      fontSize: {
        display: ["28px", { lineHeight: "1.2", fontWeight: "600" }],
        h1: ["20px", { lineHeight: "1.3", fontWeight: "600" }],
        h2: ["16px", { lineHeight: "1.4", fontWeight: "600" }],
        body: ["14px", { lineHeight: "1.5", fontWeight: "400" }],
        small: ["13px", { lineHeight: "1.4", fontWeight: "400" }],
        micro: ["11px", { lineHeight: "1.3", fontWeight: "500" }],
      },
      borderRadius: {
        sm: "var(--r-sm)",
        md: "var(--r-md)",
        lg: "var(--r-lg)",
      },
      boxShadow: {
        1: "var(--shadow-1)",
        2: "var(--shadow-2)",
      },
      transitionDuration: {
        theme: "120ms", // SPEC §12.2: theme change is a 120ms fade, nothing else
      },
    },
  },
  plugins: [],
};
