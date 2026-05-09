import { useCallback, useMemo } from 'react';
import { useGameStore } from '../stores/gameStore';
import { useSocket } from './useSocket';
import { matchAPI } from '../services/api';
import type { ActionType, CardData, PlayerData } from '../types';

export function useMinecraftGame() {
  const store = useGameStore();
  const { matchId, playerId, gameState, setGameState, setError } = store;

  const { isConnected } = useSocket({
    matchId: matchId || undefined,
    playerId: playerId || undefined,
    isSpectator: false,
    onError: (msg) => setError(msg),
  });

  const sendMCAction = useCallback(async (
    actionType: ActionType,
    opts: {
      cardId?: string;
      sourceId?: string;
      targets?: string[][];
      cell?: { x: number; y: number };
      biomeIndex?: number;
      actionKind?: string;
      attackers?: { attacker_id: string; target_id?: string; target_column?: number }[];
      blockers?: { attacker_id: string; blocker_id: string }[];
      targetColumn?: number;
      keep?: boolean;
    } = {},
  ) => {
    if (!playerId || !matchId) return;
    const request = {
      action_type: actionType,
      player_id: playerId,
      card_id: opts.cardId,
      source_id: opts.sourceId,
      targets: opts.targets || [],
      cell: opts.cell,
      biome_index: opts.biomeIndex,
      action_kind: opts.actionKind,
      attackers: opts.attackers || [],
      blockers: opts.blockers || [],
      target_column: opts.targetColumn,
      keep: opts.keep,
    };
    try {
      const result = await matchAPI.submitAction(matchId, request);
      if (result.success && result.new_state) setGameState(result.new_state);
      else if (!result.success) setError(result.message);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Action failed');
    }
  }, [playerId, matchId, setGameState, setError]);

  const isMyTurn = useCallback(() => !!gameState && !!playerId && gameState.active_player === playerId, [gameState, playerId]);

  const myPlayer = useMemo<PlayerData | null>(() => {
    if (!gameState || !playerId) return null;
    return gameState.players[playerId] || null;
  }, [gameState, playerId]);

  const opponentId = useMemo(() => {
    if (!gameState || !playerId) return null;
    return Object.keys(gameState.players).find((id) => id !== playerId) || null;
  }, [gameState, playerId]);

  const opponentPlayer = useMemo<PlayerData | null>(() => {
    if (!gameState || !opponentId) return null;
    return gameState.players[opponentId] || null;
  }, [gameState, opponentId]);

  const myMobs = useMemo(() => (gameState?.battlefield || []).filter(
    (c) => c.controller === playerId && c.types.includes('MC_MOB'),
  ), [gameState?.battlefield, playerId]);

  const opponentMobs = useMemo(() => (gameState?.battlefield || []).filter(
    (c) => c.controller !== playerId && c.types.includes('MC_MOB'),
  ), [gameState?.battlefield, playerId]);

  const canPayCost = useCallback((cost: Record<string, number>) => {
    const materials = myPlayer?.mc_materials || {};
    return Object.entries(cost).every(([key, value]) => (materials[key] || 0) >= value);
  }, [myPlayer]);

  const discountedCost = useCallback((card: CardData) => {
    const cost = { ...(card.mc_cost || {}) };
    if (
      gameState?.minecraft_day_phase === 'day'
      && (card.types.includes('MC_STRUCTURE') || card.types.includes('MC_BLOCK'))
    ) {
      for (const material of ['wood', 'stone']) {
        if ((cost[material] || 0) > 0) {
          cost[material] = Math.max(0, (cost[material] || 0) - 1);
          if (cost[material] === 0) delete cost[material];
          break;
        }
      }
    }
    return cost;
  }, [gameState?.minecraft_day_phase]);

  const canPay = useCallback((card: CardData) => (
    canPayCost(card.mc_cost || {}) || canPayCost(discountedCost(card))
  ), [canPayCost, discountedCost]);

  const canPlayCard = useCallback((card: CardData) => isMyTurn() && canPay(card), [isMyTurn, canPay]);

  const canUseMob = useCallback((card: CardData) => (
    isMyTurn()
    && card.controller === playerId
    && card.types.includes('MC_MOB')
    && !card.tapped
    && !card.mc_exhausted
    && !card.summoning_sickness
  ), [isMyTurn, playerId]);

  const canBlockMob = useCallback((card: CardData) => (
    card.controller === playerId
    && card.types.includes('MC_MOB')
    && !card.tapped
    && !card.mc_exhausted
  ), [playerId]);

  const playCard = useCallback((
    cardId: string,
    cell?: { x: number; y: number },
    targetColumn?: number,
  ) => {
    sendMCAction('MC_PLAY_CARD', { cardId, cell, targetColumn });
  }, [sendMCAction]);

  const mineWithWorker = useCallback((workerId: string, biomeIndex: number) => {
    sendMCAction('MC_ASSIGN_WORKER', { sourceId: workerId, biomeIndex });
  }, [sendMCAction]);

  const avatarMine = useCallback((biomeIndex: number) => {
    sendMCAction('MC_AVATAR_ACTION', { actionKind: 'mine', biomeIndex });
  }, [sendMCAction]);

  const avatarExplore = useCallback((biomeIndex: number) => {
    sendMCAction('MC_AVATAR_ACTION', { actionKind: 'explore', biomeIndex });
  }, [sendMCAction]);

  const avatarAttack = useCallback((targetColumn: number) => {
    sendMCAction('MC_AVATAR_ACTION', { actionKind: 'attack', targetColumn });
  }, [sendMCAction]);

  const attack = useCallback((attackerId: string, targetColumn: number) => {
    sendMCAction('MC_DECLARE_ATTACKERS', {
      attackers: [{ attacker_id: attackerId, target_column: targetColumn }],
    });
  }, [sendMCAction]);

  const declareBlockers = useCallback((blockers: { attacker_id: string; blocker_id: string }[]) => {
    sendMCAction('MC_DECLARE_BLOCKERS', { blockers });
  }, [sendMCAction]);

  const endTurn = useCallback(() => sendMCAction('MC_END_TURN'), [sendMCAction]);

  const sendMulliganDecision = useCallback(
    (keep: boolean) => sendMCAction('MC_MULLIGAN_DECISION', { keep }),
    [sendMCAction],
  );

  return {
    gameState,
    matchId,
    playerId,
    isConnected,
    myPlayer,
    opponentId,
    opponentPlayer,
    myMobs,
    opponentMobs,
    isMyTurn,
    canPlayCard,
    canUseMob,
    canBlockMob,
    playCard,
    mineWithWorker,
    avatarMine,
    avatarExplore,
    avatarAttack,
    attack,
    declareBlockers,
    endTurn,
    sendMulliganDecision,
    setError,
    error: store.ui.error,
  };
}
