import { useEffect } from 'react';
import CatsGame from '../games/cats';
import { useDiscoveryStore } from '../stores/discoveryStore';

/**
 * Cats game view — minimal wrapper that renders the cats.tsx board.
 *
 * Currently mock-data only (see useCatsGame.ts `USE_MOCK_DATA`).
 * Backend integration TODO when /api/cats routes land.
 *
 * The pure rendering surface (`CatsBoardInner`) is exported from
 * `frontend/src/games/cats.tsx` and re-wrapped into a `gameState`-driven
 * read-only adapter at `frontend/src/components/game/CatsBoard.tsx` for
 * spectator + replay dispatch. The live page below stays as the
 * `useCatsGame`-driven interactive entry point.
 */
export function CatsGameView() {
  useEffect(() => useDiscoveryStore.getState().markPlayed('cats'), []);
  return <CatsGame />;
}

export default CatsGameView;
