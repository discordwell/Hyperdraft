import { useEffect } from 'react';
import ClankersGame from '../games/clankers';
import { useDiscoveryStore } from '../stores/discoveryStore';

/**
 * Clankers game view — minimal wrapper that renders the clankers.tsx board.
 *
 * Currently mock-data only (see useClankersGame.ts). Backend integration
 * lands when /api/clankers routes are wired.
 *
 * The pure rendering surface (`ClankersBoardInner`) is exported from
 * `frontend/src/games/clankers.tsx`, ready for a future read-only
 * spectator/replay adapter (same pattern as components/game/CatsBoard.tsx).
 */
export function ClankersGameView() {
  useEffect(() => useDiscoveryStore.getState().markPlayed('clankers'), []);
  return <ClankersGame />;
}

export default ClankersGameView;
