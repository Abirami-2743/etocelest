/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      fontFamily: {
        display: ["'Fraunces'", "serif"],
        sans: ["'Inter'", "system-ui", "sans-serif"],
        mono: ["'IBM Plex Mono'", "monospace"],
      },
      colors: {
        canvas: {
          50: "#FBFCFE",
          100: "#F3F6FB",
          200: "#E9EEF6",
        },
        ink: {
          900: "#181B24",
          700: "#3A3F4D",
          500: "#6B7180",
        },
        judge: {
          500: "#3B4C8A",
          600: "#2D3A6B",
          700: "#232C52",
        },
        astro: {
          400: "#2E9BE0",
          500: "#1B7FC4",
        },
        logistics: {
          400: "#E0A427",
          500: "#C18A12",
        },
        crew: {
          400: "#E4602E",
          500: "#C94A1E",
        },
        missionvalue: {
          400: "#8A64F0",
          500: "#7047D6",
        },
      },
      boxShadow: {
        glass: "0 8px 32px rgba(35, 44, 82, 0.08)",
        "glass-lg": "0 20px 60px rgba(35, 44, 82, 0.12)",
      },
      backgroundImage: {
        grain:
          "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='120' height='120'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='0.035'/%3E%3C/svg%3E\")",
      },
      keyframes: {
        drift: {
          "0%, 100%": { transform: "translate(0,0) scale(1)" },
          "50%": { transform: "translate(2%, -3%) scale(1.05)" },
        },
        pulseRing: {
          "0%": { transform: "scale(0.9)", opacity: 0.6 },
          "100%": { transform: "scale(1.6)", opacity: 0 },
        },
      },
      animation: {
        drift: "drift 18s ease-in-out infinite",
        "drift-slow": "drift 26s ease-in-out infinite",
        pulseRing: "pulseRing 2.2s cubic-bezier(0.2,0.6,0.4,1) infinite",
      },
    },
  },
  plugins: [],
};
