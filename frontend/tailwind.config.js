/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        // ─── Lab stack (HD-CRIT-001) ─────────────────────────────────────
        // Instrument Serif (display) + Geist (body) + Geist Mono (telemetry).
        // Old Fraunces / JetBrains Mono kept reachable via 'legacy-serif' and
        // 'legacy-mono' for Phyrexian-frame and foil-era components that
        // explicitly pin the old face.
        sans: ['Geist', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        serif: ['"Instrument Serif"', 'Fraunces', 'ui-serif', 'Georgia', 'serif'],
        display: ['"Instrument Serif"', 'Fraunces', 'ui-serif', 'Georgia', 'serif'],
        mono: ['"Geist Mono"', '"JetBrains Mono"', 'ui-monospace', 'SFMono-Regular', 'monospace'],
        'legacy-serif': ['Fraunces', 'ui-serif', 'Georgia', 'serif'],
        'legacy-mono': ['"JetBrains Mono"', 'ui-monospace', 'monospace'],
        'card-name': ['Cinzel', 'serif'],
        'card-text': ['Inter', 'sans-serif'],
      },
      letterSpacing: {
        'brand-tight': '-0.025em',  // lab masthead tracking
        'brand-wide': '0.14em',     // mono telemetry labels
      },
      colors: {
        // ─── Lab palette (HD-PAL-01) ─────────────────────────────────────
        // Paper + ink + sodium accent. Hex approximations of the OKLCH
        // tokens in src/styles/lab.css (those are the source of truth; the
        // hex here is what Tailwind needs to compose with alpha utilities).
        //
        // The `brand` namespace keeps its names so every existing utility
        // (bg-brand-ink, text-brand-cream, border-brand-foil/40) keeps
        // working — the values just pivot.
        brand: {
          // canvas + surfaces → paper triad
          ink: '#f5efe0',          // outermost canvas → paper
          obsidian: '#f5efe0',     // primary surface → paper
          velvet: '#ece5d2',       // raised surface → paper-2
          shelf: '#ece5d2',        // tile / card surface → paper-2
          glass: '#ddd3bc',        // hover / focus surface → paper-3
          mist: '#d2cdc0',         // hairline → rule-2
          hairline: '#bdb8ab',     // stronger border → rule
          // foil → sodium accent
          foil: '#de8c41',
          'foil-bright': '#ee9f56',
          'foil-deep': '#9d5d24',
          'foil-shadow': '#6c3f17',
          // sheen → plasma (cool blue secondary accent)
          sheen: '#5e84cf',
          'sheen-deep': '#3d68bd',
          'sheen-glow': '#8aa6df',
          // type → ink triad
          cream: '#1c1f2a',        // body type → ink
          parchment: '#4e525c',    // slightly muted body → ink-2
          chalk: '#7f8189',        // secondary text → ink-3
          dust: '#7f8189',         // tertiary → ink-3
          // semantic states
          ember: '#c64f3e',        // halt
          spore: '#a5c544',        // acid
          violet: '#5e84cf',       // → plasma (no separate violet in lab)
        },
        // ─── Legacy tokens (kept for incremental migration) ───
        // MTG mana colors
        'mana-white': '#f9faf4',
        'mana-blue': '#0e68ab',
        'mana-black': '#150b00',
        'mana-red': '#d3202a',
        'mana-green': '#00733e',
        'mana-colorless': '#c9c5c0',
        // Game UI colors
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
        // Pokemon type colors
        'pkm-grass': '#4CAF50',
        'pkm-fire': '#F44336',
        'pkm-water': '#2196F3',
        'pkm-lightning': '#FFC107',
        'pkm-psychic': '#9C27B0',
        'pkm-fighting': '#D84315',
        'pkm-darkness': '#424242',
        'pkm-metal': '#9E9E9E',
        'pkm-dragon': '#FF8F00',
        'pkm-colorless': '#BDBDBD',
        // Yu-Gi-Oh! theme colors
        'ygo-dark': '#0a0e1a',
        'ygo-surface': '#111827',
        'ygo-gold': '#d4a843',
        'ygo-gold-bright': '#f5d478',
        'ygo-gold-dim': '#8b7230',
        'ygo-purple': '#7c3aed',
        'ygo-monster': '#c87533',
        'ygo-effect': '#b45309',
        'ygo-spell': '#0d9488',
        'ygo-trap': '#be185d',
        'ygo-ritual': '#1e40af',
        'ygo-synchro': '#e5e7eb',
        'ygo-xyz': '#1f2937',
        'ygo-link': '#1d4ed8',
      },
      backgroundImage: {
        // Foil sweep — diagonal holographic gradient that crosses a tile on hover.
        // Used by GameModeTile via an absolutely-positioned overlay whose
        // background-position animates on hover.
        'brand-foil-sweep':
          'linear-gradient(115deg, transparent 0%, transparent 28%, rgba(233,200,118,0.18) 38%, rgba(94,234,212,0.22) 50%, rgba(157,123,234,0.18) 62%, transparent 72%, transparent 100%)',
        // Subtle vignette to focus attention away from screen edges.
        'brand-vignette':
          'radial-gradient(ellipse at center, transparent 55%, rgba(0,0,0,0.45) 100%)',
        // Hairline-grid behind hero sections — like a card-grading caliper layout.
        'brand-grid':
          'linear-gradient(rgba(203,161,78,0.045) 1px, transparent 1px), linear-gradient(90deg, rgba(203,161,78,0.045) 1px, transparent 1px)',
      },
      boxShadow: {
        'brand-foil': '0 0 0 1px rgba(203,161,78,0.35), 0 14px 32px -8px rgba(203,161,78,0.18)',
        'brand-foil-strong':
          '0 0 0 1px rgba(233,200,118,0.65), 0 18px 42px -6px rgba(233,200,118,0.3), inset 0 1px 0 rgba(255,243,205,0.08)',
        'brand-tile':
          '0 1px 0 rgba(255,255,255,0.04), 0 30px 60px -25px rgba(0,0,0,0.6), 0 0 0 1px rgba(51,57,74,0.6)',
        'brand-inset': 'inset 0 1px 0 rgba(255,255,255,0.04), inset 0 0 0 1px rgba(51,57,74,0.5)',
      },
      animation: {
        // Brand animations — the ones that ship with the wordmark + hero entrance.
        'brand-shimmer': 'brand-shimmer 3.4s ease-in-out infinite',
        'brand-foil-sweep': 'brand-foil-sweep 1.1s cubic-bezier(0.22,0.8,0.3,1) forwards',
        'brand-rise': 'brand-rise 0.7s cubic-bezier(0.22,0.8,0.3,1) backwards',
        'brand-pulse': 'brand-pulse 2.6s ease-in-out infinite',
        // ─── Legacy animations (unchanged) ───
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'glow': 'glow 2s ease-in-out infinite alternate',
        'shake': 'shake 0.5s ease-in-out',
        'float-in': 'float-in 0.4s ease-out',
        'pkm-glow': 'pkm-glow 2s ease-in-out infinite alternate',
        'ygo-glow': 'ygo-glow 2s ease-in-out infinite alternate',
        'ygo-summon': 'ygo-summon 0.5s ease-out',
        'ygo-lp-flash': 'ygo-lp-flash 0.6s ease-in-out',
        'ygo-chain-pulse': 'ygo-chain-pulse 1.5s ease-in-out infinite',
      },
      keyframes: {
        glow: {
          '0%': { boxShadow: '0 0 5px #e94560, 0 0 10px #e94560' },
          '100%': { boxShadow: '0 0 10px #e94560, 0 0 20px #e94560, 0 0 30px #e94560' },
        },
        shake: {
          '0%, 100%': { transform: 'translateX(0)' },
          '20%': { transform: 'translateX(-6px)' },
          '40%': { transform: 'translateX(6px)' },
          '60%': { transform: 'translateX(-4px)' },
          '80%': { transform: 'translateX(4px)' },
        },
        'float-in': {
          '0%': { opacity: '0', transform: 'translateY(20px) scale(0.95)' },
          '100%': { opacity: '1', transform: 'translateY(0) scale(1)' },
        },
        'pkm-glow': {
          '0%': { boxShadow: '0 0 8px var(--pkm-glow-color, #4CAF50)' },
          '100%': { boxShadow: '0 0 16px var(--pkm-glow-color, #4CAF50), 0 0 32px var(--pkm-glow-color, #4CAF50)' },
        },
        'ygo-glow': {
          '0%': { boxShadow: '0 0 6px var(--ygo-glow-color, #d4a843)' },
          '100%': { boxShadow: '0 0 14px var(--ygo-glow-color, #d4a843), 0 0 28px var(--ygo-glow-color, #d4a843)' },
        },
        'ygo-summon': {
          '0%': { transform: 'scale(0.3) rotateY(180deg)', opacity: '0' },
          '60%': { transform: 'scale(1.1) rotateY(0deg)', opacity: '1' },
          '100%': { transform: 'scale(1) rotateY(0deg)', opacity: '1' },
        },
        'ygo-lp-flash': {
          '0%, 100%': { backgroundColor: 'transparent' },
          '50%': { backgroundColor: 'rgba(239, 68, 68, 0.3)' },
        },
        'ygo-chain-pulse': {
          '0%, 100%': { boxShadow: '0 0 4px #7c3aed' },
          '50%': { boxShadow: '0 0 12px #7c3aed, 0 0 24px #7c3aed' },
        },
        // ─── Brand keyframes ───
        'brand-shimmer': {
          '0%, 100%': { opacity: '0.55', filter: 'brightness(1)' },
          '50%': { opacity: '1', filter: 'brightness(1.18)' },
        },
        'brand-foil-sweep': {
          '0%': { backgroundPosition: '-180% 0', opacity: '0' },
          '20%': { opacity: '1' },
          '100%': { backgroundPosition: '180% 0', opacity: '0' },
        },
        'brand-rise': {
          '0%': { opacity: '0', transform: 'translateY(14px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        'brand-pulse': {
          '0%, 100%': { boxShadow: '0 0 0 0 rgba(94,234,212,0.45)' },
          '50%': { boxShadow: '0 0 0 12px rgba(94,234,212,0)' },
        },
      },
    },
  },
  plugins: [],
}
