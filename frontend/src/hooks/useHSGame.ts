/**
 * useHSGame Hook
 *
 * Hearthstone-specific game actions and state management.
 */

import { useCallback, useMemo } from 'react';
import { useGameStore } from '../stores/gameStore';
import { useSocket } from './useSocket';
import { matchAPI } from '../services/api';
import type { CardData, PlayerData, ActionType } from '../types';

export function useHSGame() {
  const store = useGameStore();
  const {
    matchId,
    playerId,
    gameState,
    setGameState,
    setError,
  } = store;

  // Initialize socket connection
  const { sendAction: socketSendAction, isConnected } = useSocket({
    matchId: matchId || undefined,
    playerId: playerId || undefined,
    isSpectator: false,
    onError: (msg) => setError(msg),
  });

  // Generic action sender
  const sendHSAction = useCallback(async (
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

  // Play a card from hand
  const playCard = useCallback((cardId: string, targetId?: string) => {
    sendHSAction('HS_PLAY_CARD', {
      cardId,
      targets: targetId ? [[targetId]] : [],
    });
  }, [sendHSAction]);

  // Attune a card as a mana source (Frierenrift variant)
  const attuneCard = useCallback((cardId: string) => {
    sendHSAction('HS_ATTUNE_CARD', { cardId });
  }, [sendHSAction]);

  // Attack with a minion or hero
  const attack = useCallback((attackerId: string, targetId: string) => {
    sendHSAction('HS_ATTACK', {
      sourceId: attackerId,
      targets: [[targetId]],
    });
  }, [sendHSAction]);

  // Use hero power
  const useHeroPower = useCallback((targetId?: string) => {
    sendHSAction('HS_HERO_POWER', {
      targets: targetId ? [[targetId]] : [],
    });
  }, [sendHSAction]);

  // End turn
  const endTurn = useCallback(() => {
    sendHSAction('HS_END_TURN');
  }, [sendHSAction]);

  // Check if it's my turn
  const isMyTurn = useCallback((): boolean => {
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

  // Check if a card can be played (mana check)
  const canPlayCard = useCallback((card: CardData): boolean => {
    if (!isMyTurn() || !myPlayer) return false;
    const cost = parseMana(card.mana_cost);
    if (cost > (myPlayer.mana_crystals_available || 0)) return false;

    // Variant affinity gate: [AF:azure/ember/verdant] => [AF:a/e/v]
    if (gameState?.variant === 'frierenrift') {
      const req = parseAffinity(card.text);
      const resources = myPlayer.variant_resources || {};
      if ((resources.azure || 0) < req.azure) return false;
      if ((resources.ember || 0) < req.ember) return false;
      if ((resources.verdant || 0) < req.verdant) return false;
    }
    return true;
  }, [isMyTurn, myPlayer, gameState?.variant]);

  const canAttuneCard = useCallback((_card: CardData): boolean => {
    if (!isMyTurn() || !myPlayer) return false;
    if (gameState?.variant !== 'frierenrift') return false;
    const resources = myPlayer.variant_resources || {};
    const attunesLeft = Number(resources.attunes_left ?? 0);
    return attunesLeft > 0;
  }, [isMyTurn, myPlayer, gameState?.variant]);

  // Check if hero power can be used
  const canUseHeroPower = useMemo((): boolean => {
    if (!isMyTurn() || !myPlayer) return false;
    if (myPlayer.hero_power_used) return false;
    return (myPlayer.hero_power_cost || 2) <= (myPlayer.mana_crystals_available || 0);
  }, [isMyTurn, myPlayer]);

  // Get my battlefield minions
  const myMinions = useMemo((): CardData[] => {
    if (!gameState || !playerId) return [];
    return gameState.battlefield.filter(c => c.controller === playerId);
  }, [gameState, playerId]);

  // Get opponent battlefield minions
  const opponentMinions = useMemo((): CardData[] => {
    if (!gameState || !playerId) return [];
    return gameState.battlefield.filter(c => c.controller !== playerId);
  }, [gameState, playerId]);

  // Get attackable targets (respecting taunt)
  const getAttackableTargets = useCallback((_attackerId: string): string[] => {
    if (!opponentId || !opponentPlayer) return [];

    const tauntMinions = opponentMinions.filter(m =>
      m.keywords?.includes('taunt')
    );

    if (tauntMinions.length > 0) {
      return tauntMinions.map(m => m.id);
    }

    // Can attack any enemy minion or hero
    const targets = opponentMinions.map(m => m.id);
    if (opponentPlayer.hero_id) {
      targets.push(opponentPlayer.hero_id);
    }
    return targets;
  }, [opponentId, opponentPlayer, opponentMinions]);

  // Check if a minion can attack
  const canAttack = useCallback((card: CardData): boolean => {
    if (!isMyTurn()) return false;
    if ((card.attacks_this_turn || 0) > 0) return false;
    if (card.frozen) return false;
    if (card.summoning_sickness) {
      // Check for charge or rush
      const hasCharge = card.keywords?.includes('charge');
      const hasRush = card.keywords?.includes('rush');
      if (!hasCharge && !hasRush) return false;
    }
    return true;
  }, [isMyTurn]);

  return {
    // State
    gameState,
    matchId,
    playerId,
    isConnected,
    myPlayer,
    opponentPlayer,
    opponentId,
    myMinions,
    opponentMinions,

    // Actions
    playCard,
    attuneCard,
    attack,
    useHeroPower,
    endTurn,

    // Queries
    isMyTurn,
    canPlayCard,
    canAttuneCard,
    canUseHeroPower,
    canAttack,
    getAttackableTargets,

    // UI
    setError,
    error: store.ui.error,
  };
}

// Helper: parse mana cost string like "{3}" or "{2}{R}" to numeric cost
function parseMana(costStr: string | null): number {
  if (!costStr) return 0;
  const matches = costStr.match(/\{(\d+)\}/g);
  if (!matches) return 0;
  return matches.reduce((sum, m) => sum + parseInt(m.replace(/[{}]/g, ''), 10), 0);
}

function parseAffinity(text: string | null | undefined): { azure: number; ember: number; verdant: number } {
  const out = { azure: 0, ember: 0, verdant: 0 };
  if (!text) return out;
  const m = text.match(/\[AF:(\d+)\/(\d+)\/(\d+)\]/i);
  if (!m) return out;
  return {
    azure: Number.parseInt(m[1] || '0', 10) || 0,
    ember: Number.parseInt(m[2] || '0', 10) || 0,
    verdant: Number.parseInt(m[3] || '0', 10) || 0,
  };
}
