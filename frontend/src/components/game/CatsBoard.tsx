/**
 * CatsBoard — read-only Cats engine board for spectator / replay dispatch.
 *
 * The interactive Cats UI is implemented in `frontend/src/games/cats.tsx`
 * as `CatsGame`, which pulls live state from `useCatsGame()`. That hook
 * subscribes to the live socket / mock store and isn't usable from a
 * read-only `gameState` payload.
 *
 * This module re-exports the same `CatsBoardInner` rendering surface
 * (lifted out of `cats.tsx` so both the interactive page and the read-only
 * spectator wrapper share one source of truth for visuals), wrapped in a
 * `gameState`-driven adapter. The cozy cream/butterscotch palette and
 * paw/yarn/fish-bone iconography are preserved per `docs/design/brand.md`
 * ("each game keeps its own identity").
 *
 * `gameState.cats` is the canonical Cats payload populated by the server's
 * `_serialize_cats_state` (see `src/server/session.py`). When that payload
 * is missing (e.g. a bot game that crashed during setup) we render a
 * graceful empty state instead of throwing.
 */
import { CatsBoardInner, CatsEmptyState } from '../../games/cats';
import type { CatsState } from '../../hooks/useCatsGame';
import type { GameState } from '../../types';

export interface CatsBoardProps {
  gameState: GameState;
  /**
   * Spectators get a stable seat id from the dispatcher, but Cats's view is
   * already seat-relative ("me" vs "opponent" inside `gameState.cats`), so
   * we accept the prop for API symmetry with SCPBoard but don't depend on
   * it for the layout.
   */
  playerId: string;
  /**
   * Defaults to true. The wired Cats board exposes no interactive elements
   * yet beyond `onAction`; spectator mode wires a no-op handler so play /
   * claim / knock-over are inert clicks.
   */
  readOnly?: boolean;
}

/**
 * The pure rendering surface for a Cats match.
 */
export function CatsBoard({ gameState, playerId }: CatsBoardProps) {
  void playerId; // intentionally unused — Cats payload is already seat-relative.
  const cats = (gameState as unknown as { cats?: CatsState | null }).cats;
  if (!cats) {
    return <CatsEmptyState message="No Cats state on this frame." />;
  }
  // Pass a no-op action handler — read-only.
  return <CatsBoardInner state={cats} onAction={() => undefined} />;
}

export default CatsBoard;
