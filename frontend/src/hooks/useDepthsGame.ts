/**
 * useDepthsGame — submarine-fleet engine data hook.
 *
 * Mirrors useMinecraftGame: same socket lifecycle, same poll-then-update
 * shape, same callback fan-out. Adapts the action helpers to the depths
 * vocabulary: Vessels (not mobs), Torpedo + Sonar Charges (not materials),
 * Depth Bands (not columns), Detection (not block declaration), and the
 * Flagship as life-total.
 */

import { useCallback, useMemo } from 'react';
import { useGameStore } from '../stores/gameStore';
import { useSocket } from './useSocket';
import { matchAPI } from '../services/api';
import type { ActionType, CardData, PlayerData } from '../types';

export type DepthBand = 'SURFACE' | 'PERISCOPE' | 'MID' | 'DEEP' | 'CRUSH';

export const DEPTH_BANDS: readonly DepthBand[] = [
  'SURFACE',
  'PERISCOPE',
  'MID',
  'DEEP',
  'CRUSH',
];

const VESSEL_TYPES = new Set(['DEPTHS_VESSEL']);
const MINE_TYPES = new Set(['DEPTHS_MINE']);

export function useDepthsGame() {
  const store = useGameStore();
  const { matchId, playerId, gameState, setGameState, setError } = store;

  const { isConnected } = useSocket({
    matchId: matchId || undefined,
    playerId: playerId || undefined,
    isSpectator: false,
    onError: (msg) => setError(msg),
  });

  const sendDepthsAction = useCallback(async (
    actionType: ActionType,
    opts: {
      cardId?: string;
      sourceId?: string;
      targets?: string[][];
      depthBand?: DepthBand | string;
      vesselId?: string;
      attackers?: { attacker_id: string; target_id?: string; firing_band?: string }[];
      interceptors?: { attacker_id: string; interceptor_id: string }[];
      detectTargets?: string[];
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
      depth_band: opts.depthBand,
      vessel_id: opts.vesselId,
      attackers: opts.attackers || [],
      interceptors: opts.interceptors || [],
      detect_targets: opts.detectTargets || [],
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

  const isVessel = (c: CardData) => c.types.some((t) => VESSEL_TYPES.has(t));
  const isMine = (c: CardData) => c.types.some((t) => MINE_TYPES.has(t));

  const myVessels = useMemo(
    () => (gameState?.battlefield || []).filter((c) => c.controller === playerId && isVessel(c)),
    [gameState?.battlefield, playerId],
  );

  const opponentVessels = useMemo(
    () => (gameState?.battlefield || []).filter((c) => c.controller !== playerId && isVessel(c)),
    [gameState?.battlefield, playerId],
  );

  const myMines = useMemo(
    () => (gameState?.battlefield || []).filter((c) => c.controller === playerId && isMine(c)),
    [gameState?.battlefield, playerId],
  );

  const opponentMines = useMemo(
    () => (gameState?.battlefield || []).filter((c) => c.controller !== playerId && isMine(c)),
    [gameState?.battlefield, playerId],
  );

  const myFlagship = useMemo<CardData | null>(() => {
    if (!myPlayer) return null;
    const fid = myPlayer.flagship_id;
    if (fid) {
      return (gameState?.battlefield || []).find((c) => c.id === fid) || null;
    }
    // Fallback: first vessel marked as flagship.
    return myVessels.find((c) => c.is_flagship || c.subtypes.includes('Flagship')) || null;
  }, [gameState?.battlefield, myPlayer, myVessels]);

  const opponentFlagship = useMemo<CardData | null>(() => {
    if (!opponentPlayer) return null;
    const fid = opponentPlayer.flagship_id;
    if (fid) {
      return (gameState?.battlefield || []).find((c) => c.id === fid) || null;
    }
    return opponentVessels.find((c) => c.is_flagship || c.subtypes.includes('Flagship')) || null;
  }, [gameState?.battlefield, opponentPlayer, opponentVessels]);

  const canPayCost = useCallback((cost: { tc?: number; sc?: number }) => {
    const tc = myPlayer?.tc ?? 0;
    const sc = myPlayer?.sc ?? 0;
    return (cost.tc ?? 0) <= tc && (cost.sc ?? 0) <= sc;
  }, [myPlayer]);

  const canPlayCard = useCallback((card: CardData) => (
    isMyTurn() && canPayCost(card.depths_cost || {})
  ), [isMyTurn, canPayCost]);

  const canUseVessel = useCallback((card: CardData) => (
    isMyTurn()
    && card.controller === playerId
    && isVessel(card)
    && !card.tapped
    && !card.summoning_sickness
  ), [isMyTurn, playerId]);

  const canIntercept = useCallback((card: CardData) => (
    card.controller === playerId
    && isVessel(card)
    && !card.tapped
  ), [playerId]);

  // Action callbacks ---------------------------------------------------------

  const playCard = useCallback((cardId: string, depthBand?: DepthBand) => {
    sendDepthsAction('DEPTHS_PLAY_CARD', { cardId, depthBand });
  }, [sendDepthsAction]);

  const dive = useCallback((vesselId: string) => {
    sendDepthsAction('DEPTHS_DIVE', { vesselId });
  }, [sendDepthsAction]);

  const surface = useCallback((vesselId: string) => {
    sendDepthsAction('DEPTHS_SURFACE', { vesselId });
  }, [sendDepthsAction]);

  const layMine = useCallback((cardId: string, depthBand: DepthBand) => {
    sendDepthsAction('DEPTHS_LAY_MINE', { cardId, depthBand });
  }, [sendDepthsAction]);

  const declareAttackers = useCallback((
    attackers: { attacker_id: string; target_id?: string; firing_band?: string }[],
  ) => {
    sendDepthsAction('DEPTHS_DECLARE_ATTACKERS', { attackers });
  }, [sendDepthsAction]);

  const detect = useCallback((detectTargets: string[]) => {
    sendDepthsAction('DEPTHS_DETECT', { detectTargets });
  }, [sendDepthsAction]);

  const declareInterceptors = useCallback((
    interceptors: { attacker_id: string; interceptor_id: string }[],
  ) => {
    sendDepthsAction('DEPTHS_DECLARE_INTERCEPTORS', { interceptors });
  }, [sendDepthsAction]);

  const activateAbility = useCallback((sourceId: string, abilityId?: string) => {
    sendDepthsAction('DEPTHS_ACTIVATE_ABILITY', { sourceId, abilityId });
  }, [sendDepthsAction]);

  const endTurn = useCallback(
    () => sendDepthsAction('DEPTHS_END_TURN'),
    [sendDepthsAction],
  );

  return {
    gameState,
    matchId,
    playerId,
    isConnected,
    myPlayer,
    opponentId,
    opponentPlayer,
    myFlagship,
    opponentFlagship,
    myVessels,
    opponentVessels,
    myMines,
    opponentMines,
    isMyTurn,
    canPlayCard,
    canUseVessel,
    canIntercept,
    playCard,
    dive,
    surface,
    layMine,
    declareAttackers,
    detect,
    declareInterceptors,
    activateAbility,
    endTurn,
    setError,
    error: store.ui.error,
  };
}
