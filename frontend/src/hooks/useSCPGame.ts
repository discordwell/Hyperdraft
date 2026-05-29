import { useCallback, useMemo } from 'react';
import { useGameStore } from '../stores/gameStore';
import { useSocket } from './useSocket';
import { matchAPI } from '../services/api';
import type { ActionType, CardData, PlayerData, SCPIncident, SCPSiteState } from '../types';

const typeHas = (card: CardData, type: string) => card.types.includes(type);

export function useSCPGame() {
  const store = useGameStore();
  const { matchId, playerId, gameState, setGameState, setError } = store;

  const { isConnected } = useSocket({
    matchId: matchId || undefined,
    playerId: playerId || undefined,
    isSpectator: false,
    onError: (msg) => setError(msg),
  });

  const sendSCPAction = useCallback(async (
    actionType: ActionType,
    opts: {
      cardId?: string;
      sourceId?: string;
      anomalyId?: string;
      staffIds?: string[];
      containedId?: string;
      activeId?: string;
      mood?: string;
      protocol?: string;
      actionKind?: string;
      index?: number;
      amount?: number;
      abilityIndex?: number;
      fastTrack?: boolean;
      sealed?: boolean;
    } = {},
  ) => {
    if (!playerId || !matchId) return;
    try {
      const result = await matchAPI.submitAction(matchId, {
        action_type: actionType,
        player_id: playerId,
        card_id: opts.cardId,
        source_id: opts.sourceId,
        anomaly_id: opts.anomalyId,
        staff_ids: opts.staffIds || [],
        contained_id: opts.containedId,
        active_id: opts.activeId,
        mood: opts.mood,
        protocol: opts.protocol,
        action_kind: opts.actionKind,
        index: opts.index,
        amount: opts.amount,
        ability_index: opts.abilityIndex,
        fast_track: Boolean(opts.fastTrack),
        sealed: Boolean(opts.sealed),
      });
      if (result.success && result.new_state) {
        setGameState(result.new_state);
        setError(null);
      } else if (!result.success) {
        setError(result.message);
      }
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

  const mySite = useMemo<SCPSiteState>(() => (
    (playerId && gameState?.scp_sites?.[playerId]) || {}
  ), [gameState?.scp_sites, playerId]);

  const opponentSite = useMemo<SCPSiteState>(() => (
    (opponentId && gameState?.scp_sites?.[opponentId]) || {}
  ), [gameState?.scp_sites, opponentId]);

  const myDossiers = useMemo(() => (
    (gameState?.battlefield || []).filter((card) => card.controller === playerId && card.types.some((t) => t.startsWith('SCP_')))
  ), [gameState?.battlefield, playerId]);

  const opponentDossiers = useMemo(() => (
    (gameState?.battlefield || []).filter((card) => card.controller === opponentId && card.types.some((t) => t.startsWith('SCP_')))
  ), [gameState?.battlefield, opponentId]);

  const myPending = useMemo(
    () => myDossiers.filter((card) => card.scp_status === 'pending' || card.scp_status === 'sealed'),
    [myDossiers],
  );

  const opponentPending = useMemo(
    () => opponentDossiers.filter((card) => card.scp_status === 'pending' || card.scp_status === 'sealed'),
    [opponentDossiers],
  );

  const activeAnomalies = gameState?.scp_anomalies?.[playerId || ''] || [];
  const containedAnomalies = gameState?.scp_contained?.[playerId || ''] || [];
  const personnel = gameState?.scp_personnel?.[playerId || ''] || [];
  const facilities = gameState?.scp_facilities?.[playerId || ''] || [];
  const mandates = gameState?.scp_mandates?.[playerId || ''] || [];
  const opponentAnomalies = gameState?.scp_anomalies?.[opponentId || ''] || [];
  const opponentContained = gameState?.scp_contained?.[opponentId || ''] || [];
  const opponentPersonnel = gameState?.scp_personnel?.[opponentId || ''] || [];
  const incidents = gameState?.scp_incidents?.[playerId || ''] || [];
  const assignmentSlots = playerId ? gameState?.scp_assignment_slots?.[playerId] ?? 0 : 0;

  const hand = useMemo(() => gameState?.hand || [], [gameState?.hand]);

  return {
    gameState,
    matchId,
    playerId,
    isConnected,
    myPlayer,
    opponentId,
    opponentPlayer,
    mySite,
    opponentSite,
    hand,
    myPending,
    opponentPending,
    activeAnomalies,
    containedAnomalies,
    personnel,
    facilities,
    mandates,
    opponentAnomalies,
    opponentContained,
    opponentPersonnel,
    incidents: incidents as SCPIncident[],
    assignmentSlots,
    isMyTurn,
    isAnomaly: (card: CardData) => typeHas(card, 'SCP_ANOMALY'),
    openDossier: (cardId: string, fastTrack = false, sealed = false) => (
      sendSCPAction('SCP_OPEN_DOSSIER', { cardId, fastTrack, sealed })
    ),
    revealDossier: (sourceId: string) => sendSCPAction('SCP_REVEAL_DOSSIER', { sourceId }),
    research: (anomalyId: string, staffIds: string[]) => sendSCPAction('SCP_RESEARCH', { anomalyId, staffIds }),
    contain: (anomalyId: string, staffIds: string[]) => sendSCPAction('SCP_CONTAIN', { anomalyId, staffIds }),
    suppress: (anomalyId: string, staffIds: string[]) => sendSCPAction('SCP_SUPPRESS', { anomalyId, staffIds }),
    spendEthics: (amount = 2, mode = 'buy_clearance') => sendSCPAction('SCP_SPEND_ETHICS', { amount, actionKind: mode }),
    shiftMood: (anomalyId: string, mood: string) => sendSCPAction('SCP_SHIFT_MOOD', { anomalyId, mood }),
    crossContain: (containedId: string, activeId: string) => sendSCPAction('SCP_CROSS_CONTAIN', { containedId, activeId }),
    memoryHole: (sourceId: string) => sendSCPAction('SCP_MEMORY_HOLE', { sourceId }),
    applyProtocol: (anomalyId: string, protocol: string) => sendSCPAction('SCP_APPLY_PROTOCOL', { anomalyId, protocol }),
    resolveIncident: (index: number) => sendSCPAction('SCP_RESOLVE_INCIDENT', { index }),
    activateAbility: (sourceId: string, abilityIndex: number) => (
      sendSCPAction('SCP_ACTIVATE_ABILITY', { sourceId, abilityIndex })
    ),
    endTurn: () => sendSCPAction('SCP_END_TURN'),
    setError,
    error: store.ui.error,
  };
}
