/**
 * useGame Hook
 *
 * High-level hook for game interactions, combining store and socket functionality.
 */

import { useCallback, useMemo } from 'react';
import { useGameStore } from '../stores/gameStore';
import { useSocket } from './useSocket';
import { matchAPI } from '../services/api';
import type { LegalActionData, ActionType } from '../types';

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
  } = store;

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
  const pass = useCallback(async () => {
    if (!playerId || !matchId) return;

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

    // Build and send immediately
    const request = {
      action_type: 'PASS' as ActionType,
      player_id: playerId,
    };

    setLoading(true);
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
      setLoading(false);
      selectAction(null);
    }
  }, [playerId, matchId, isConnected, socketSendAction, setLoading, setError, selectAction, store]);

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
    pass,
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
