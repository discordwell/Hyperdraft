/**
 * Game mode metadata — single source of truth for the brand surface.
 *
 * Every visible game mode in HYPERDRAFT lives here. Component code reads
 * the registry instead of switching on raw string game modes; this keeps
 * tile order, accent colors, and per-mode routing in one auditable place.
 */

export type GameModeId =
  | 'mtg'
  | 'hearthstone'
  | 'pokemon'
  | 'yugioh'
  | 'minecraft'
  | 'finance'
  | 'depths'
  | 'scp';

export interface GameModeMeta {
  id: GameModeId;
  /** Short uppercase code rendered in monograms and stat lines. */
  code: string;
  /** Display name shown on tiles + breadcrumbs. */
  name: string;
  /** Long ceremonial title for the hero / detail header. */
  title: string;
  /** One-line blurb for marketing copy. */
  blurb: string;
  /** Per-mode hue tag, biased toward the foil-stamped palette. */
  accent: 'gold' | 'sheen' | 'ember' | 'spore' | 'violet';
  /**
   * Per-mode top-of-game route. For modes that piggyback on GameView, this
   * is /game/:matchId; mode-specific views go to /game/:matchId/<suffix>.
   */
  gameViewSuffix: '' | '/hs' | '/pkm' | '/ygo' | '/mc' | '/fin' | '/depths' | '/scp';
}

export const GAME_MODES: GameModeMeta[] = [
  {
    id: 'mtg',
    code: 'MTG',
    name: 'Magic',
    title: 'Magic: The Gathering',
    blurb: 'Twelve real Standard sets, full priority + stack.',
    accent: 'gold',
    gameViewSuffix: '',
  },
  {
    id: 'hearthstone',
    code: 'HS',
    name: 'Hearthstone',
    title: 'Hearthstone',
    blurb: 'Tempo brawls with class identities + variants.',
    accent: 'ember',
    gameViewSuffix: '/hs',
  },
  {
    id: 'pokemon',
    code: 'PKM',
    name: 'Pokémon',
    title: 'Pokémon TCG',
    blurb: 'Energy-powered attacks, prize race to six.',
    accent: 'sheen',
    gameViewSuffix: '/pkm',
  },
  {
    id: 'yugioh',
    code: 'YGO',
    name: 'Yu-Gi-Oh!',
    title: 'Yu-Gi-Oh!',
    blurb: 'Chain links, set traps, normal & special summons.',
    accent: 'gold',
    gameViewSuffix: '/ygo',
  },
  {
    id: 'minecraft',
    code: 'MNR',
    name: 'Minecraft',
    title: 'Minecraft Card Game',
    blurb: 'Build the 3×3, mine the biomes, raid the End.',
    accent: 'spore',
    gameViewSuffix: '/mc',
  },
  {
    id: 'finance',
    code: 'FIN',
    name: 'Finance',
    title: 'Finance TCG',
    blurb: 'Yield, leverage, and the long short.',
    accent: 'sheen',
    gameViewSuffix: '/fin',
  },
  {
    id: 'depths',
    code: 'DPT',
    name: 'Depths',
    title: 'Submarine Fleet: Depths',
    blurb: 'Five bands of pressure, silent torpedoes, sonar.',
    accent: 'sheen',
    gameViewSuffix: '/depths',
  },
  {
    id: 'scp',
    code: 'SCP',
    name: 'SCP',
    title: 'SCP: Secure / Contain / Protect',
    blurb: 'Open dossiers, contain anomalies, mind the breach.',
    accent: 'violet',
    gameViewSuffix: '/scp',
  },
];

const MODE_BY_ID = Object.fromEntries(GAME_MODES.map((m) => [m.id, m])) as Record<
  GameModeId,
  GameModeMeta
>;

export function getMode(id: GameModeId | string): GameModeMeta | undefined {
  return MODE_BY_ID[id as GameModeId];
}

export const ACCENT_CLASSES: Record<
  GameModeMeta['accent'],
  { text: string; ring: string; bg: string; glow: string }
> = {
  gold: {
    text: 'text-brand-foil',
    ring: 'ring-brand-foil/40',
    bg: 'bg-brand-foil/15',
    glow: 'shadow-[0_0_24px_-4px_rgba(203,161,78,0.45)]',
  },
  sheen: {
    text: 'text-brand-sheen',
    ring: 'ring-brand-sheen/40',
    bg: 'bg-brand-sheen/10',
    glow: 'shadow-[0_0_24px_-4px_rgba(94,234,212,0.45)]',
  },
  ember: {
    text: 'text-brand-ember',
    ring: 'ring-brand-ember/40',
    bg: 'bg-brand-ember/15',
    glow: 'shadow-[0_0_24px_-4px_rgba(220,79,67,0.45)]',
  },
  spore: {
    text: 'text-brand-spore',
    ring: 'ring-brand-spore/40',
    bg: 'bg-brand-spore/10',
    glow: 'shadow-[0_0_24px_-4px_rgba(163,230,53,0.45)]',
  },
  violet: {
    text: 'text-brand-violet',
    ring: 'ring-brand-violet/40',
    bg: 'bg-brand-violet/10',
    glow: 'shadow-[0_0_24px_-4px_rgba(157,123,234,0.45)]',
  },
};
