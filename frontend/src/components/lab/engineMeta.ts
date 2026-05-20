/**
 * Lab-display metadata for the 8 engines.
 *
 * The brand registry (`components/brand/modes.ts`) is canonical for routing
 * + tile content. This adds the lab-specific fields used by the engine rack
 * (HD-ART-01) and engine picker (HD-ART-02): completeness, top-line stat,
 * and the four-stat grid shown in the picker card.
 *
 * Numbers are intentionally hand-curated rather than queried from the
 * backend — these read as a designer's spec sheet, not live telemetry.
 * Update them as engines mature; they're an editorial signal, not a metric.
 */

import { GAME_MODES, type GameModeId, type GameModeMeta } from '../brand/modes';

export interface LabEngineMeta extends GameModeMeta {
  /** E1..E8 row number — 1-indexed for the engine rack. */
  ix: string;
  /** One-line subtitle shown under the name. */
  subtitle: string;
  /** Right-aligned single stat shown on the rack row. */
  stat: string;
  /** 0..100 — completeness bar fill. */
  completeness: number;
  /** Whether the bar uses the sodium accent. Only the lead engine. */
  leadEngine: boolean;
  /** Four short stats shown on the engine-picker card. */
  pickerStats: Array<{ k: string; v: string }>;
}

const META: Record<GameModeId, Omit<LabEngineMeta, keyof GameModeMeta>> = {
  mtg: {
    ix: 'E1',
    subtitle: '12 real Standard sets · Scryfall mirror',
    stat: '~3,450 cards',
    completeness: 96,
    leadEngine: true,
    pickerStats: [
      { k: '~3,450', v: 'cards' },
      { k: '4 tiers', v: 'AI' },
      { k: 'full', v: 'stack' },
      { k: '12', v: 'sets' },
    ],
  },
  hearthstone: {
    ix: 'E2',
    subtitle: 'battlecry · deathrattle · taunt',
    stat: 'lethal AI',
    completeness: 70,
    leadEngine: false,
    pickerStats: [
      { k: 'battlecry', v: 'wired' },
      { k: 'deathrattle', v: 'wired' },
      { k: 'lethal', v: 'AI' },
      { k: 'ultra', v: 'tier' },
    ],
  },
  pokemon: {
    ix: 'E3',
    subtitle: '12 trainer adapters · prize-aware',
    stat: 'planning AI',
    completeness: 74,
    leadEngine: false,
    pickerStats: [
      { k: '12', v: 'trainers' },
      { k: 'prize', v: 'aware' },
      { k: '5', v: 'conditions' },
      { k: 'evolution', v: 'wired' },
    ],
  },
  yugioh: {
    ix: 'E4',
    subtitle: 'chain · spell / trap / flip',
    stat: '4 decks',
    completeness: 62,
    leadEngine: false,
    pickerStats: [
      { k: '51', v: 'cards' },
      { k: '4', v: 'decks' },
      { k: 'chain', v: 'system' },
      { k: 'goat', v: 'meta' },
    ],
  },
  minecraft: {
    ix: 'E5',
    subtitle: 'biomes · mines · raid the End',
    stat: '12 decks',
    completeness: 64,
    leadEngine: false,
    pickerStats: [
      { k: '12', v: 'decks' },
      { k: '3x3', v: 'craft' },
      { k: 'biome', v: 'mana' },
      { k: 'raid', v: 'finisher' },
    ],
  },
  finance: {
    ix: 'E6',
    subtitle: 'yield · leverage · the long short',
    stat: 'novel rules',
    completeness: 54,
    leadEngine: false,
    pickerStats: [
      { k: 'yield', v: 'engine' },
      { k: 'leverage', v: 'mechanic' },
      { k: 'short', v: 'enabled' },
      { k: '—', v: 'AI' },
    ],
  },
  depths: {
    ix: 'E7',
    subtitle: '5 pressure bands · sonar · torpedoes',
    stat: 'silent threat',
    completeness: 58,
    leadEngine: false,
    pickerStats: [
      { k: '5', v: 'bands' },
      { k: 'sonar', v: 'reveal' },
      { k: 'silent', v: 'damage' },
      { k: 'SUBS', v: 'fleet' },
    ],
  },
  scp: {
    ix: 'E8',
    subtitle: '7 archetypes · containment theme',
    stat: 'archetype viewer',
    completeness: 66,
    leadEngine: false,
    pickerStats: [
      { k: '7', v: 'archetypes' },
      { k: 'containment', v: 'theme' },
      { k: 'arch.', v: 'viewer' },
      { k: '312', v: 'cards' },
    ],
  },
};

export const LAB_ENGINES: LabEngineMeta[] = GAME_MODES.map((m) => ({
  ...m,
  ...META[m.id],
}));

export function getLabEngine(id: GameModeId | string): LabEngineMeta | undefined {
  return LAB_ENGINES.find((e) => e.id === (id as GameModeId));
}
