/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        co: "#1565c0", // Colombia
        es: "#c62828", // España
      },
    },
  },
  plugins: [],
};
