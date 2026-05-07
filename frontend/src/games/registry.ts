/**
 * Game module registry.
 *
 * Maps a Game id to its corresponding GameModule. Components that need to
 * vary behavior per game (DeckStats, FilterPanel, ...) read from here.
 */

import type { Game } from '../types/deckbuilder';
import type { GameModule } from './types';

import { mtg } from './mtg';
import { minecraft } from './minecraft';
import { pokemon } from './pokemon';
import { yugioh } from './yugioh';
import { hearthstone } from './hearthstone';
import { depths } from './depths';
import { finance } from './finance';

export const GAME_MODULES: Record<Game, GameModule> = {
  mtg,
  minecraft,
  pokemon,
  yugioh,
  hearthstone,
  depths,
  finance,
};

export function getGameModule(game: Game): GameModule {
  return GAME_MODULES[game] ?? mtg;
}
