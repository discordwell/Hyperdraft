import CatsGame from '../games/cats';

/**
 * Cats game view — minimal wrapper that renders the cats.tsx board.
 *
 * Currently mock-data only (see useCatsGame.ts `USE_MOCK_DATA`).
 * Backend integration TODO when /api/cats routes land.
 */
export function CatsGameView() {
  return <CatsGame />;
}

export default CatsGameView;
