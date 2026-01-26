/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        'card-name': ['Cinzel', 'serif'],
        'card-text': ['Inter', 'sans-serif'],
      },
      colors: {
        // MTG mana colors
        'mana-white': '#f9faf4',
        'mana-blue': '#0e68ab',
        'mana-black': '#150b00',
        'mana-red': '#d3202a',
        'mana-green': '#00733e',
        'mana-colorless': '#c9c5c0',
        // Game UI colors
        'game-bg': '#1a1a2e',
        'game-surface': '#16213e',
        'game-accent': '#e94560',
        'game-gold': '#f5a623',
        // Sketch card colors
        'card-parchment': '#f5f0e6',
        'card-parchment-dark': '#e8e0d0',
        'card-bg-dark': '#2d2a26',
        // Color identity accents
        'card-white': '#f9e4a8',
        'card-blue': '#6b9bc4',
        'card-black': '#4a4a4a',
        'card-red': '#d4694a',
        'card-green': '#5d8c5a',
        'card-gold': '#c4a446',
        'card-colorless': '#9e9e9e',
        'card-land': '#a89984',
      },
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'glow': 'glow 2s ease-in-out infinite alternate',
      },
      keyframes: {
        glow: {
          '0%': { boxShadow: '0 0 5px #e94560, 0 0 10px #e94560' },
          '100%': { boxShadow: '0 0 10px #e94560, 0 0 20px #e94560, 0 0 30px #e94560' },
        },
      },
    },
  },
  plugins: [],
}
