import { useEffect } from 'react';
import CatsGame from '../games/cats';
import { useDiscoveryStore } from '../stores/discoveryStore';

/**
 * Cats game view — minimal wrapper that renders the cats.tsx board.
 *
 * Currently mock-data only (see useCatsGame.ts `USE_MOCK_DATA`).
 * Backend integration TODO when /api/cats routes land.
 */
export function CatsGameView() {
  useEffect(() => useDiscoveryStore.getState().markPlayed('cats'), []);
  return <CatsGame />;
}

export default CatsGameView;
