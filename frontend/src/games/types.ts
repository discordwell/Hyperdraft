/**
 * Game module interface.
 *
 * Each TCG plugs into the deckbuilder by exporting a GameModule. The module
 * describes how to render that game's filters, stat tiles, and any extra
 * polish (charts, breakdowns) on top of the generic DeckStats panel.
 *
 * Adding a new game: drop a `<game>.tsx` in this folder, register it in
 * `registry.ts`, and add the id to `GAMES` in `types/deckbuilder.ts`.
 */

import type { ComponentType } from 'react';
import type { DeckStats, Game } from '../types/deckbuilder';

export interface StatTile {
  label: string;
  value: number;
}

export interface GameModule {
  id: Game;
  label: string;
  /** Whether to render the WUBRG color pips + color filter buttons. */
  showColors: boolean;
  /** Label for the cost-range filter (e.g. "Mana Value", "Materials"). */
  costLabel: string;
  /** Card type strings exposed in the FilterPanel (engine CardType.name). */
  typeFilters: readonly string[];
  /** Pretty-print a type for a filter button (default: strip prefix). */
  formatType: (t: string) => string;
  /** 3-tile quick stats summary shown next to the Main count. */
  tiles: (stats: DeckStats | null) => StatTile[];
  /** Optional extra panel rendered below the cost curve (charts etc.). */
  StatsExtras?: ComponentType<{ stats: DeckStats }>;
}

export function defaultFormatType(t: string): string {
  const stripped = t.replace(/^(MC|PKM|YGO|HS|SCP)_/, '');
  return stripped.charAt(0) + stripped.slice(1).toLowerCase();
}
