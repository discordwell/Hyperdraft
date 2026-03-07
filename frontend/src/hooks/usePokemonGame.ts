/**
 * usePokemonGame Hook
 *
 * Pokemon TCG-specific game actions and state management.
 */

import { useCallback, useMemo } from 'react';
import { useGameStore } from '../stores/gameStore';
import { useSocket } from './useSocket';
import { matchAPI } from '../services/api';
import type { CardData, PlayerData, ActionType, GameLogEntry } from '../types';

export function usePokemonGame() {
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
  const sendPKMAction = useCallback(async (
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

  // Play a card from hand (basic Pokemon, trainer)
  const playCard = useCallback((cardId: string) => {
    sendPKMAction('PKM_PLAY_CARD' as ActionType, { cardId });
  }, [sendPKMAction]);

  // Attach energy to a Pokemon
  const attachEnergy = useCallback((energyCardId: string, targetPokemonId: string) => {
    sendPKMAction('PKM_ATTACH_ENERGY' as ActionType, {
      cardId: energyCardId,
      targets: [[targetPokemonId]],
    });
  }, [sendPKMAction]);

  // Attack with active Pokemon
  const attack = useCallback((attackIndex: number) => {
    sendPKMAction('PKM_ATTACK' as ActionType, {
      targets: [[String(attackIndex)]],
    });
  }, [sendPKMAction]);

  // Retreat active Pokemon
  const retreat = useCallback((benchPokemonId: string) => {
    sendPKMAction('PKM_RETREAT' as ActionType, {
      targets: [[benchPokemonId]],
    });
  }, [sendPKMAction]);

  // Evolve a Pokemon
  const evolve = useCallback((evolutionCardId: string, targetPokemonId: string) => {
    sendPKMAction('PKM_EVOLVE' as ActionType, {
      cardId: evolutionCardId,
      sourceId: targetPokemonId,
    });
  }, [sendPKMAction]);

  // Use a Pokemon's ability
  const useAbility = useCallback((pokemonId: string) => {
    sendPKMAction('PKM_USE_ABILITY' as ActionType, {
      sourceId: pokemonId,
    });
  }, [sendPKMAction]);

  // End turn
  const endTurn = useCallback(() => {
    sendPKMAction('PKM_END_TURN' as ActionType);
  }, [sendPKMAction]);

  // Check if it's my turn
  const isMyTurn = useMemo((): boolean => {
    if (!gameState || !playerId) return false;
    return gameState.active_player === playerId;
  }, [gameState, playerId]);

  // Get my player data
  const myPlayer = useMemo((): PlayerData | null => {
    if (!gameState || !playerId) return null;
    return gameState.players[playerId] || null;
  }, [gameState, playerId]);

  // Get opponent player data
  const opponentPlayer = useMemo((): PlayerData | null => {
    if (!gameState || !playerId) return null;
    const oppId = Object.keys(gameState.players).find(id => id !== playerId);
    return oppId ? gameState.players[oppId] : null;
  }, [gameState, playerId]);

  const opponentId = useMemo((): string | null => {
    if (!gameState || !playerId) return null;
    return Object.keys(gameState.players).find(id => id !== playerId) || null;
  }, [gameState, playerId]);

  // Get active Pokemon per player
  const myActivePokemon = useMemo((): CardData | null => {
    if (!gameState?.active_pokemon || !playerId) return null;
    return gameState.active_pokemon[playerId] || null;
  }, [gameState, playerId]);

  const opponentActivePokemon = useMemo((): CardData | null => {
    if (!gameState?.active_pokemon || !opponentId) return null;
    return gameState.active_pokemon[opponentId] || null;
  }, [gameState, opponentId]);

  // Get bench per player
  const myBench = useMemo((): CardData[] => {
    if (!gameState?.bench || !playerId) return [];
    return gameState.bench[playerId] || [];
  }, [gameState, playerId]);

  const opponentBench = useMemo((): CardData[] => {
    if (!gameState?.bench || !opponentId) return [];
    return gameState.bench[opponentId] || [];
  }, [gameState, opponentId]);

  // Stadium card
  const stadiumCard = useMemo((): CardData | null => {
    return gameState?.stadium_card || null;
  }, [gameState]);

  // Graveyard (discard pile) data
  const myGraveyard = useMemo((): CardData[] => {
    if (!gameState?.graveyard || !playerId) return [];
    return gameState.graveyard[playerId] || [];
  }, [gameState, playerId]);

  const opponentGraveyard = useMemo((): CardData[] => {
    if (!gameState?.graveyard || !opponentId) return [];
    return gameState.graveyard[opponentId] || [];
  }, [gameState, opponentId]);

  // Game log
  const gameLog = useMemo((): GameLogEntry[] => {
    return gameState?.game_log || [];
  }, [gameState]);

  // Check if energy can be attached
  const canAttachEnergy = useCallback((card: CardData): boolean => {
    if (!isMyTurn || !myPlayer) return false;
    if (myPlayer.energy_attached_this_turn) return false;
    return card.types?.includes('ENERGY') || false;
  }, [isMyTurn, myPlayer]);

  // Check if a card can be played from hand
  const canPlayCard = useCallback((card: CardData): boolean => {
    if (!isMyTurn) return false;
    const types = card.types || [];

    // Basic Pokemon - can play if bench has room
    if (types.includes('POKEMON') && card.evolution_stage === 'Basic') {
      return (myBench.length < 5);
    }

    // Evolution - need a valid target on field
    if (types.includes('POKEMON') && (card.evolution_stage === 'Stage 1' || card.evolution_stage === 'Stage 2')) {
      return true; // Simplified - server validates
    }

    // Item trainer - always playable
    if (types.includes('ITEM')) return true;

    // Supporter - once per turn
    if (types.includes('SUPPORTER')) {
      return !myPlayer?.supporter_played_this_turn;
    }

    // Stadium - once per turn
    if (types.includes('STADIUM')) return true;

    // Energy - can attach once per turn
    if (types.includes('ENERGY')) {
      return !myPlayer?.energy_attached_this_turn;
    }

    return false;
  }, [isMyTurn, myPlayer, myBench]);

  return {
    // State
    gameState,
    matchId,
    playerId,
    isConnected,
    myPlayer,
    opponentPlayer,
    opponentId,
    myActivePokemon,
    opponentActivePokemon,
    myBench,
    opponentBench,
    stadiumCard,
    myGraveyard,
    opponentGraveyard,
    gameLog,

    // Actions
    playCard,
    attachEnergy,
    attack,
    retreat,
    evolve,
    useAbility,
    endTurn,

    // Queries
    isMyTurn,
    canPlayCard,
    canAttachEnergy,

    // UI
    setError,
    error: store.ui.error,
  };
}
