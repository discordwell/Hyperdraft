import { useCallback, useMemo } from 'react';
import { useGameStore } from '../stores/gameStore';
import { useSocket } from './useSocket';
import { matchAPI } from '../services/api';
import type { ActionType, CardData, PlayerData } from '../types';

export function useFinanceGame() {
  const store = useGameStore();
  const { matchId, playerId, gameState, setGameState, setError } = store;

  const { isConnected } = useSocket({
    matchId: matchId || undefined,
    playerId: playerId || undefined,
    isSpectator: false,
    onError: (msg) => setError(msg),
  });

  const sendFinanceAction = useCallback(async (
    actionType: ActionType,
    opts: {
      cardId?: string;
      sourceId?: string;
      targets?: string[][];
      attackers?: { attacker_id: string; target_id?: string }[];
      blockers?: { attacker_id: string; blocker_id: string }[];
      abilityId?: string;
    } = {},
  ) => {
    if (!playerId || !matchId) return;
    const request = {
      action_type: actionType,
      player_id: playerId,
      card_id: opts.cardId,
      source_id: opts.sourceId,
      targets: opts.targets || [],
      attackers: opts.attackers || [],
      blockers: opts.blockers || [],
      ability_id: opts.abilityId,
    };
    try {
      const result = await matchAPI.submitAction(matchId, request);
      if (result.success && result.new_state) setGameState(result.new_state);
      else if (!result.success) setError(result.message);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Action failed');
    }
  }, [playerId, matchId, setGameState, setError]);

  const isMyTurn = useCallback(
    () => !!gameState && !!playerId && gameState.active_player === playerId,
    [gameState, playerId],
  );

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

  // ---- Board card lists ------------------------------------------------

  const myTraders = useMemo(() => (gameState?.battlefield || []).filter(
    (c) => c.controller === playerId && c.types.some((t) => t === 'FIN_TRADER'),
  ), [gameState?.battlefield, playerId]);

  const myAssets = useMemo(() => (gameState?.battlefield || []).filter(
    (c) => c.controller === playerId && c.types.some((t) => t === 'FIN_ASSET'),
  ), [gameState?.battlefield, playerId]);

  const myStructures = useMemo(() => (gameState?.battlefield || []).filter(
    (c) => c.controller === playerId && c.types.some((t) => t === 'FIN_STRUCTURE'),
  ), [gameState?.battlefield, playerId]);

  const myHand = useMemo<CardData[]>(() => gameState?.hand || [], [gameState?.hand]);

  const oppTraders = useMemo(() => (gameState?.battlefield || []).filter(
    (c) => c.controller !== playerId && c.types.some((t) => t === 'FIN_TRADER'),
  ), [gameState?.battlefield, playerId]);

  const oppAssets = useMemo(() => (gameState?.battlefield || []).filter(
    (c) => c.controller !== playerId && c.types.some((t) => t === 'FIN_ASSET'),
  ), [gameState?.battlefield, playerId]);

  // ---- Finance-specific state from turn_data ---------------------------
  // These are surfaced by the server as top-level GameState fields if the
  // finance adapter populates them, or derived from player mana_crystals.

  const myLiquidity = useMemo(
    () => myPlayer?.mana_crystals_available ?? 0,
    [myPlayer],
  );

  const myLiquidityMax = useMemo(
    () => myPlayer?.mana_crystals ?? 0,
    [myPlayer],
  );

  const currentPhase = useMemo(() => {
    if (!gameState) return 'PRE_MARKET';
    const gs = gameState as unknown as Record<string, unknown>;
    return (gs['finance_phase'] as string) ?? gameState.phase ?? 'PRE_MARKET';
  }, [gameState]);

  // Derivatives Desk — list of card IDs from finance_turn_data
  const myDerivDesk = useMemo<string[]>(() => {
    if (!gameState || !playerId) return [];
    const gs = gameState as unknown as Record<string, unknown>;
    const turnData = gs['finance_turn_data'] as Record<string, unknown> | undefined;
    const raw = turnData?.[`finance_deriv_desk_${playerId}`];
    return Array.isArray(raw) ? (raw as string[]) : [];
  }, [gameState, playerId]);

  // Dark Pool — boolean whether any card occupies the slot
  const darkPoolActive = useMemo<boolean>(() => {
    if (!gameState) return false;
    const gs = gameState as unknown as Record<string, unknown>;
    return !!(gs['finance_dark_pool']);
  }, [gameState]);

  // ---- Capability helpers ----------------------------------------------

  const canPlayCard = useCallback(
    (card: CardData) => isMyTurn() && (card.mana_cost === null || myLiquidity >= parseInt(card.mana_cost?.replace(/\D/g, '') || '0', 10)),
    [isMyTurn, myLiquidity],
  );

  const canAttack = useCallback(
    (card: CardData) => isMyTurn() && card.controller === playerId && !card.tapped && !card.summoning_sickness && card.types.some((t) => t === 'FIN_TRADER'),
    [isMyTurn, playerId],
  );

  const canBlock = useCallback(
    (card: CardData) => card.controller === playerId && !card.tapped && card.types.some((t) => t === 'FIN_TRADER'),
    [playerId],
  );

  // ---- Actions ---------------------------------------------------------

  const playCard = useCallback((cardId: string) => {
    sendFinanceAction('FIN_PLAY_CARD', { cardId });
  }, [sendFinanceAction]);

  const declareAttackers = useCallback(
    (attackers: { attacker_id: string; target_id?: string }[]) => {
      sendFinanceAction('FIN_DECLARE_ATTACKERS', { attackers });
    },
    [sendFinanceAction],
  );

  const declareBlockers = useCallback(
    (blockers: { attacker_id: string; blocker_id: string }[]) => {
      sendFinanceAction('FIN_DECLARE_BLOCKERS', { blockers });
    },
    [sendFinanceAction],
  );

  const activateAbility = useCallback((sourceId: string, abilityId?: string) => {
    sendFinanceAction('FIN_ACTIVATE_ABILITY', { sourceId, abilityId });
  }, [sendFinanceAction]);

  const endTurn = useCallback(() => sendFinanceAction('FIN_END_TURN'), [sendFinanceAction]);

  const playResponse = useCallback(
    (cardId: string, targetStackCardId: string) => {
      sendFinanceAction('FIN_PLAY_RESPONSE', {
        cardId,
        targets: [[targetStackCardId]],
      });
    },
    [sendFinanceAction],
  );

  const passResponse = useCallback(
    () => sendFinanceAction('FIN_PASS_RESPONSE'),
    [sendFinanceAction],
  );

  const sendAction = useCallback(
    (action: object) => sendFinanceAction((action as { action_type: ActionType }).action_type, action as never),
    [sendFinanceAction],
  );

  return {
    gameState,
    matchId,
    playerId,
    isConnected,
    myPlayer,
    opponentId,
    opponentPlayer,
    myHand,
    myTraders,
    myAssets,
    myStructures,
    myDerivDesk,
    oppTraders,
    oppAssets,
    currentPhase,
    myLiquidity,
    myLiquidityMax,
    darkPoolActive,
    isMyTurn,
    canPlayCard,
    canAttack,
    canBlock,
    playCard,
    declareAttackers,
    declareBlockers,
    activateAbility,
    endTurn,
    playResponse,
    passResponse,
    sendAction,
    setError,
    error: store.ui.error,
  };
}
