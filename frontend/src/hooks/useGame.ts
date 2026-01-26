/**
 * useGame Hook
 *
 * High-level hook for game interactions, combining store and socket functionality.
 */

import { useCallback, useMemo, useEffect, useRef } from 'react';
import { useGameStore } from '../stores/gameStore';
import { useSocket } from './useSocket';
import { matchAPI } from '../services/api';
import type { LegalActionData, ActionType } from '../types';

// Re-export AutoPassMode for consumers
export type { AutoPassMode } from '../stores/gameStore';

export function useGame() {
  const store = useGameStore();
  const {
    matchId,
    playerId,
    isSpectator,
    gameState,
    ui,
    selectCard,
    selectAction,
    startTargeting,
    addTarget,
    cancelTargeting,
    confirmTargets,
    toggleAttacker,
    setBlocker,
    clearCombatSelections,
    buildActionRequest,
    setLoading,
    setError,
    getMyBattlefield,
    getOpponentBattlefield,
    getOpponentId,
    isMyTurn,
    canAct,
    hasActionsOtherThanPass,
    setAutoPassMode,
    enablePassUntilEndOfTurn,
    cancelAutoPass,
    shouldAutoPass,
    checkAutoPassConditions,
  } = store;

  // Track if we're currently auto-passing to prevent loops
  const autoPassingRef = useRef(false);

  // Initialize socket connection
  const { sendAction: socketSendAction, isConnected } = useSocket({
    matchId: matchId || undefined,
    playerId: playerId || undefined,
    isSpectator,
    onError: (msg) => setError(msg),
  });

  // Send action (via WebSocket or REST)
  const sendAction = useCallback(async () => {
    const request = buildActionRequest();
    if (!request || !matchId) return;

    setLoading(true);
    try {
      // Prefer WebSocket if connected
      if (isConnected) {
        socketSendAction(request);
      } else {
        // Fallback to REST - update state from response
        const result = await matchAPI.submitAction(matchId, request);
        if (result.success && result.new_state) {
          store.setGameState(result.new_state);
        } else if (!result.success) {
          setError(result.message);
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to send action');
    } finally {
      setLoading(false);
      // Clear selections after action
      selectAction(null);
      selectCard(null);
    }
  }, [
    buildActionRequest,
    matchId,
    isConnected,
    socketSendAction,
    setLoading,
    setError,
    selectAction,
    selectCard,
    store,
  ]);

  // Pass priority
  const pass = useCallback(async (isAutoPass = false) => {
    if (!playerId || !matchId) return;

    // Don't show UI updates for auto-pass
    if (!isAutoPass) {
      const passAction: LegalActionData = {
        type: 'PASS',
        card_id: null,
        ability_id: null,
        source_id: null,
        description: 'Pass priority',
        requires_targets: false,
        requires_mana: false,
      };
      selectAction(passAction);
    }

    // Build and send immediately
    const request = {
      action_type: 'PASS' as ActionType,
      player_id: playerId,
    };

    if (!isAutoPass) {
      setLoading(true);
    }
    try {
      if (isConnected) {
        socketSendAction(request);
      } else {
        // REST fallback - also refetch state after action
        const result = await matchAPI.submitAction(matchId, request);
        if (result.success && result.new_state) {
          store.setGameState(result.new_state);
        } else if (!result.success) {
          setError(result.message);
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to pass');
    } finally {
      if (!isAutoPass) {
        setLoading(false);
        selectAction(null);
      }
    }
  }, [playerId, matchId, isConnected, socketSendAction, setLoading, setError, selectAction, store]);

  // Auto-pass effect: when game state changes and we have priority, check if we should auto-pass
  useEffect(() => {
    // Don't auto-pass if we're already processing one or not connected
    if (autoPassingRef.current || !gameState || !playerId) return;

    // Check if it's our turn to act
    if (gameState.priority_player !== playerId) return;

    // Check if we should auto-pass
    const { shouldPass, reason } = checkAutoPassConditions();

    if (shouldPass) {
      autoPassingRef.current = true;

      // Small delay to prevent UI flicker and allow state to settle
      const timer = setTimeout(async () => {
        try {
          await pass(true); // Pass with isAutoPass = true
        } finally {
          autoPassingRef.current = false;
        }
      }, 50);

      return () => {
        clearTimeout(timer);
        autoPassingRef.current = false;
      };
    } else if (reason && ui.autoPassMode !== 'off' && ui.autoPassMode !== 'no_actions') {
      // Update the UI with why auto-pass stopped (only for explicit auto-pass modes)
      store.setError(null); // Clear any previous error
    }
  }, [gameState, playerId, checkAutoPassConditions, pass, ui.autoPassMode, store]);

  // Cast a spell from hand
  const castSpell = useCallback(
    (cardId: string) => {
      // Find the legal action for this card
      const action = gameState?.legal_actions.find(
        (a) => a.type === 'CAST_SPELL' && a.card_id === cardId
      );

      if (action) {
        selectAction(action);

        // If requires targets, start targeting mode
        if (action.requires_targets) {
          // Get valid targets from battlefield and players
          const validTargets = [
            ...gameState!.battlefield.map((c) => c.id),
            ...Object.keys(gameState!.players),
          ];
          startTargeting('single', validTargets);
        } else {
          // No targets needed, we can send the action directly
          // But we need to set it first so buildActionRequest works
        }
      }
    },
    [gameState, selectAction, startTargeting]
  );

  // Play a land from hand
  const playLand = useCallback(
    (cardId: string) => {
      const action = gameState?.legal_actions.find(
        (a) => a.type === 'PLAY_LAND' && a.card_id === cardId
      );

      if (action) {
        selectAction(action);
      }
    },
    [gameState, selectAction]
  );

  // Check if a card can be cast
  const canCast = useCallback(
    (cardId: string): boolean => {
      if (!gameState || !canAct()) return false;
      return gameState.legal_actions.some(
        (a) => a.type === 'CAST_SPELL' && a.card_id === cardId
      );
    },
    [gameState, canAct]
  );

  // Check if a land can be played
  const canPlayLand = useCallback(
    (cardId: string): boolean => {
      if (!gameState || !canAct()) return false;
      return gameState.legal_actions.some(
        (a) => a.type === 'PLAY_LAND' && a.card_id === cardId
      );
    },
    [gameState, canAct]
  );

  // Get available actions grouped by type
  const availableActions = useMemo(() => {
    if (!gameState) return { pass: false, spells: [], lands: [], abilities: [] };

    return {
      pass: gameState.legal_actions.some((a) => a.type === 'PASS'),
      spells: gameState.legal_actions.filter((a) => a.type === 'CAST_SPELL'),
      lands: gameState.legal_actions.filter((a) => a.type === 'PLAY_LAND'),
      abilities: gameState.legal_actions.filter((a) => a.type === 'ACTIVATE_ABILITY'),
    };
  }, [gameState]);

  // Combat helpers
  const isInCombat = useMemo(() => {
    return gameState?.phase === 'COMBAT';
  }, [gameState]);

  const canDeclareAttackers = useMemo(() => {
    return (
      isInCombat &&
      gameState?.step === 'DECLARE_ATTACKERS' &&
      isMyTurn() &&
      canAct()
    );
  }, [isInCombat, gameState, isMyTurn, canAct]);

  const canDeclareBlockers = useMemo(() => {
    return (
      isInCombat &&
      gameState?.step === 'DECLARE_BLOCKERS' &&
      !isMyTurn() &&
      canAct()
    );
  }, [isInCombat, gameState, isMyTurn, canAct]);

  return {
    // State
    gameState,
    ui,
    matchId,
    playerId,
    isSpectator,
    isConnected,

    // Actions
    sendAction,
    pass: () => pass(false), // Wrap to always pass false for manual calls
    castSpell,
    playLand,

    // Card selection
    selectCard,
    selectAction,

    // Targeting
    startTargeting,
    addTarget,
    cancelTargeting,
    confirmTargets,

    // Combat
    toggleAttacker,
    setBlocker,
    clearCombatSelections,

    // Auto-pass
    setAutoPassMode,
    enablePassUntilEndOfTurn,
    cancelAutoPass,
    shouldAutoPass,
    hasActionsOtherThanPass,

    // Queries
    canCast,
    canPlayLand,
    availableActions,
    isInCombat,
    canDeclareAttackers,
    canDeclareBlockers,
    isMyTurn,
    canAct,
    getMyBattlefield,
    getOpponentBattlefield,
    getOpponentId,

    // UI state
    setLoading,
    setError,
  };
}
