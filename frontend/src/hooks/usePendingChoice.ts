/**
 * usePendingChoice — shared hook that wires up the cross-engine
 * PendingChoice prompt UI.
 *
 * Reads `gameState.pending_choice` from the Zustand store, filters to the
 * current player, and provides a submit handler that POSTs to
 * `/match/{id}/choice`. The result of the submit replaces `gameState`.
 *
 * Used by every non-MTG GameView (SCP, HS, PKM, YGO, Finance, MC) to
 * render the same `<ChoiceModal>` overlay that MTG mounts inline. MTG's
 * legacy `ui.targetingMode` slice (cast-time pre-target overlay) was
 * removed in Phase 5 — cast-time targeting is now handled by
 * `GameBoard`'s drag-to-target layer, and resolution-time choices flow
 * through this same pending_choice path.
 */
import { useCallback, useMemo, useState } from 'react';

import { matchAPI } from '../services/api';
import { useGameStore } from '../stores/gameStore';
import type { PendingChoice } from '../types';

export interface UsePendingChoiceResult {
  pendingChoice: PendingChoice | null;
  handleChoiceSubmit: (selectedIds: string[]) => Promise<void>;
  isLoading: boolean;
  error: string | null;
}

export function usePendingChoice(): UsePendingChoiceResult {
  const gameState = useGameStore((s) => s.gameState);
  const playerId = useGameStore((s) => s.playerId);
  const matchId = useGameStore((s) => s.matchId);
  const setGameState = useGameStore((s) => s.setGameState);

  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const pendingChoice = useMemo<PendingChoice | null>(() => {
    const pc = gameState?.pending_choice;
    if (!pc || !playerId) return null;
    if (pc.player !== playerId) return null;
    return pc;
  }, [gameState?.pending_choice, playerId]);

  const handleChoiceSubmit = useCallback(
    async (selectedIds: string[]) => {
      if (!matchId || !playerId || !pendingChoice) return;
      setIsLoading(true);
      setError(null);
      try {
        const result = await matchAPI.submitChoice(
          matchId,
          pendingChoice.id,
          playerId,
          selectedIds,
        );
        if (result.success && result.new_state) {
          setGameState(result.new_state);
        } else if (!result.success) {
          setError(result.message);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to submit choice');
      } finally {
        setIsLoading(false);
      }
    },
    [matchId, playerId, pendingChoice, setGameState],
  );

  return { pendingChoice, handleChoiceSubmit, isLoading, error };
}
