/**
 * useYGOGame Hook
 *
 * Yu-Gi-Oh!-specific game actions and state management.
 */

import { useCallback, useMemo } from 'react';
import { useGameStore } from '../stores/gameStore';
import { useSocket } from './useSocket';
import { matchAPI } from '../services/api';
import type { CardData, PlayerData, ActionType, GameLogEntry } from '../types';

export function useYGOGame() {
  const store = useGameStore();
  const {
    matchId,
    playerId,
    gameState,
    setGameState,
    setError,
  } = store;

  const { sendAction: socketSendAction, isConnected } = useSocket({
    matchId: matchId || undefined,
    playerId: playerId || undefined,
    isSpectator: false,
    onError: (msg) => setError(msg),
  });

  // Generic action sender
  const sendYGOAction = useCallback(async (
    actionType: ActionType,
    opts: {
      cardId?: string;
      sourceId?: string;
      targets?: string[][];
    } = {}
  ) => {
    if (!playerId || !matchId) return;

    const request = {
      action_type: actionType,
      player_id: playerId,
      card_id: opts.cardId,
      source_id: opts.sourceId,
      targets: opts.targets || [],
    };

    try {
      if (isConnected) {
        socketSendAction(request);
      } else {
        const result = await matchAPI.submitAction(matchId, request);
        if (result.success && result.new_state) {
          setGameState(result.new_state);
        } else if (!result.success) {
          setError(result.message);
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Action failed');
    }
  }, [playerId, matchId, isConnected, socketSendAction, setGameState, setError]);

  // Normal Summon a monster
  const normalSummon = useCallback((cardId: string) => {
    sendYGOAction('YGO_NORMAL_SUMMON' as ActionType, { cardId });
  }, [sendYGOAction]);

  // Set a monster face-down
  const setMonster = useCallback((cardId: string) => {
    sendYGOAction('YGO_SET_MONSTER' as ActionType, { cardId });
  }, [sendYGOAction]);

  // Flip Summon a face-down monster
  const flipSummon = useCallback((cardId: string) => {
    sendYGOAction('YGO_FLIP_SUMMON' as ActionType, { cardId });
  }, [sendYGOAction]);

  // Change monster battle position
  const changePosition = useCallback((cardId: string) => {
    sendYGOAction('YGO_CHANGE_POSITION' as ActionType, { cardId });
  }, [sendYGOAction]);

  // Activate a spell/trap
  const activateCard = useCallback((cardId: string, targetId?: string) => {
    sendYGOAction('YGO_ACTIVATE' as ActionType, {
      cardId,
      targets: targetId ? [[targetId]] : [],
    });
  }, [sendYGOAction]);

  // Set a spell/trap face-down
  const setSpellTrap = useCallback((cardId: string) => {
    sendYGOAction('YGO_SET_SPELL_TRAP' as ActionType, { cardId });
  }, [sendYGOAction]);

  // Declare attack on a monster
  const declareAttack = useCallback((attackerId: string, targetId: string) => {
    sendYGOAction('YGO_DECLARE_ATTACK' as ActionType, {
      sourceId: attackerId,
      targets: [[targetId]],
    });
  }, [sendYGOAction]);

  // Direct attack
  const directAttack = useCallback((attackerId: string) => {
    sendYGOAction('YGO_DIRECT_ATTACK' as ActionType, {
      sourceId: attackerId,
    });
  }, [sendYGOAction]);

  // End current phase
  const endPhase = useCallback(() => {
    sendYGOAction('YGO_END_PHASE' as ActionType);
  }, [sendYGOAction]);

  // End turn
  const endTurn = useCallback(() => {
    sendYGOAction('YGO_END_TURN' as ActionType);
  }, [sendYGOAction]);

  // Computed state
  const isMyTurn = useCallback((): boolean => {
    if (!gameState || !playerId) return false;
    return gameState.active_player === playerId;
  }, [gameState, playerId]);

  const myPlayer = useMemo((): PlayerData | null => {
    if (!gameState || !playerId) return null;
    return gameState.players[playerId] || null;
  }, [gameState, playerId]);

  const opponentPlayer = useMemo((): PlayerData | null => {
    if (!gameState || !playerId) return null;
    const oppId = Object.keys(gameState.players).find(id => id !== playerId);
    return oppId ? gameState.players[oppId] : null;
  }, [gameState, playerId]);

  const opponentId = useMemo((): string | null => {
    if (!gameState || !playerId) return null;
    return Object.keys(gameState.players).find(id => id !== playerId) || null;
  }, [gameState, playerId]);

  // Monster zones
  const myMonsterZones = useMemo((): (CardData | null)[] => {
    if (!gameState?.monster_zones || !playerId) return [null, null, null, null, null];
    return gameState.monster_zones[playerId] || [null, null, null, null, null];
  }, [gameState, playerId]);

  const oppMonsterZones = useMemo((): (CardData | null)[] => {
    if (!gameState?.monster_zones || !opponentId) return [null, null, null, null, null];
    return gameState.monster_zones[opponentId] || [null, null, null, null, null];
  }, [gameState, opponentId]);

  // Spell/Trap zones
  const mySpellTrapZones = useMemo((): (CardData | null)[] => {
    if (!gameState?.spell_trap_zones || !playerId) return [null, null, null, null, null];
    return gameState.spell_trap_zones[playerId] || [null, null, null, null, null];
  }, [gameState, playerId]);

  const oppSpellTrapZones = useMemo((): (CardData | null)[] => {
    if (!gameState?.spell_trap_zones || !opponentId) return [null, null, null, null, null];
    return gameState.spell_trap_zones[opponentId] || [null, null, null, null, null];
  }, [gameState, opponentId]);

  // Field spells
  const myFieldSpell = useMemo((): CardData | null => {
    if (!gameState?.field_spells || !playerId) return null;
    return gameState.field_spells[playerId] || null;
  }, [gameState, playerId]);

  const oppFieldSpell = useMemo((): CardData | null => {
    if (!gameState?.field_spells || !opponentId) return null;
    return gameState.field_spells[opponentId] || null;
  }, [gameState, opponentId]);

  // Graveyards
  const myGraveyard = useMemo((): CardData[] => {
    if (!gameState?.graveyard || !playerId) return [];
    return gameState.graveyard[playerId] || [];
  }, [gameState, playerId]);

  const oppGraveyard = useMemo((): CardData[] => {
    if (!gameState?.graveyard || !opponentId) return [];
    return gameState.graveyard[opponentId] || [];
  }, [gameState, opponentId]);

  // Banished
  const myBanished = useMemo((): CardData[] => {
    if (!gameState?.banished || !playerId) return [];
    return gameState.banished[playerId] || [];
  }, [gameState, playerId]);

  const oppBanished = useMemo((): CardData[] => {
    if (!gameState?.banished || !opponentId) return [];
    return gameState.banished[opponentId] || [];
  }, [gameState, opponentId]);

  // Extra deck sizes
  const myExtraDeckSize = useMemo((): number => {
    if (!gameState?.extra_deck_sizes || !playerId) return 0;
    return gameState.extra_deck_sizes[playerId] || 0;
  }, [gameState, playerId]);

  const oppExtraDeckSize = useMemo((): number => {
    if (!gameState?.extra_deck_sizes || !opponentId) return 0;
    return gameState.extra_deck_sizes[opponentId] || 0;
  }, [gameState, opponentId]);

  // Current YGO phase
  const ygoPhase = useMemo((): string => {
    return gameState?.ygo_phase || '';
  }, [gameState]);

  // Game log
  const gameLog = useMemo((): GameLogEntry[] => {
    return gameState?.game_log || [];
  }, [gameState]);

  return {
    gameState,
    playerId,
    isConnected,
    myPlayer,
    opponentPlayer,
    isMyTurn,
    // Zones
    myMonsterZones,
    oppMonsterZones,
    mySpellTrapZones,
    oppSpellTrapZones,
    myFieldSpell,
    oppFieldSpell,
    myGraveyard,
    oppGraveyard,
    myBanished,
    oppBanished,
    myExtraDeckSize,
    oppExtraDeckSize,
    ygoPhase,
    gameLog,
    // Actions
    normalSummon,
    setMonster,
    flipSummon,
    changePosition,
    activateCard,
    setSpellTrap,
    declareAttack,
    directAttack,
    endPhase,
    endTurn,
    setError,
    error: store.ui.error,
  };
}
