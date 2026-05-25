/**
 * GameView Page
 *
 * Main game playing interface with drag and drop support.
 */

import { useEffect, useCallback, useState, useMemo } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useGame } from '../hooks/useGame';
import { useDiscoveryStore } from '../stores/discoveryStore';
import { useGameStore } from '../stores/gameStore';
import { useCardZoneStore } from '../stores/cardZoneStore';
import { useAltP } from '../hooks/useAltP';

// Engine accent palette for overlay-mode pending_choice highlighting.
// Mirrors the per-engine accents used by each game's hand-card primitive.
// Kept here (rather than in cardZoneStore) so the store stays
// engine-agnostic — the caller picks the accent.
const ENGINE_ACCENT_BY_MODE: Record<string, string> = {
  mtg: '#a78bfa',
  hearthstone: '#fbbf24',
  pokemon: '#fca5a5',
  yugioh: '#c4b5fd',
  cats: '#fbbf24',
  clankers: '#60a5fa',
  minecraft: '#a3e635',
  depths: '#22d3ee',
  finance: '#86efac',
  scp: '#f97316',
};
import { GameBoard, GraveyardModal, PriorityPrompt } from '../components/game';
import { GameLog } from '../components/game/GameLog';
import { AnimationsToggle } from '../components/game/shared/AnimationsToggle';
import { ActionMenu, ChoiceModal } from '../components/actions';
import { GameViewLayout } from '../components/brand';
import { Timeline } from '../components/lab';
import { PipelineView, type PipelineEvent, type PipelineStage } from '../components/lab';
import { HSGameView } from './HSGameView';
import { PKMGameView } from './PKMGameView';
import { YGOGameView } from './YGOGameView';
import { SCPGameView } from './SCPGameView';
import { matchAPI } from '../services/api';
import type { CardData, LegalActionData, GameLogEntry, PlayerData } from '../types';

/**
 * Heuristic: map a server-supplied event_type to one of the four
 * interceptor pipeline stages. The real engine emits these events with a
 * known InterceptorPriority (TRANSFORM / PREVENT / RESOLVE / REACT), but
 * the Socket.IO log bridge currently discards the stage tag — see
 * src/server/modes/*.py. Until that's wired, we infer from event-type
 * vocabulary:
 *
 *   - PREVENT: cancel / counter / fizzle / ward / shroud verbiage.
 *   - TRANSFORM: replacement effects, redirects, P/T modifiers, scry/surveil.
 *   - REACT: ETB / death / leaves-battlefield triggers, end-step queues.
 *   - RESOLVE: everything else that actually mutates state.
 */
function classifyStage(eventType: string): PipelineStage {
  const k = eventType.toLowerCase();
  if (
    k.includes('prevent') ||
    k.includes('counter') ||
    k.includes('fizzle') ||
    k.includes('ward')
  ) {
    return 'prevent';
  }
  if (
    k.includes('replace') ||
    k.includes('redirect') ||
    k.includes('pt_modif') ||
    k.includes('pt_modify') ||
    k.includes('temporary_pt') ||
    k.includes('pt_change') ||
    k.includes('scry') ||
    k.includes('surveil') ||
    k.includes('query_cost')
  ) {
    return 'transform';
  }
  if (
    k.includes('trigger') ||
    k.includes('etb') ||
    k.includes('enter_battlefield') ||
    k.includes('death') ||
    k.includes('leaves_battlefield') ||
    k.includes('end_step') ||
    k.includes('reaction') ||
    k.includes('react') ||
    k.includes('upkeep')
  ) {
    return 'react';
  }
  return 'resolve';
}

function gameLogToPipelineEvents(
  log: GameLogEntry[],
  players: Record<string, PlayerData>,
): PipelineEvent[] {
  return log.map((entry, i) => {
    const stage = classifyStage(entry.event_type);
    const playerName = entry.player
      ? players[entry.player]?.name ?? entry.player
      : 'engine';
    return {
      id: `log-${i}`,
      stage,
      type: entry.event_type.toUpperCase(),
      source: playerName,
      description: entry.text,
      t: `T${entry.turn} +${(i % 99).toString().padStart(2, '0')}`,
      turn: entry.turn,
    };
  });
}

/**
 * Fallback demo events used when the active match hasn't logged anything
 * yet. Covers all four stages over three turns so the README hero shot has
 * the full pipeline lit. Event-type vocabulary drawn from
 * `src/engine/types.py::EventType`.
 */
const SAMPLE_PIPELINE_EVENTS: PipelineEvent[] = [
  // Turn 1 — Boros Reckoner redirect + Lightning Bolt
  { id: 'p1', stage: 'transform', type: 'PT_MODIFICATION', source: 'Glorious Anthem', description: 'All creatures you control get +1/+1.', t: 'T1 +01', turn: 1 },
  { id: 'p2', stage: 'resolve', type: 'SPELL_CAST', source: 'Bob', description: 'Bob casts Lightning Bolt targeting Alice.', t: 'T1 +02', turn: 1, relatedId: 'bolt' },
  { id: 'p3', stage: 'transform', type: 'DAMAGE', source: 'Boros Reckoner', description: 'Damage redirected: Alice → Boros Reckoner.', t: 'T1 +03', turn: 1, relatedId: 'bolt' },
  { id: 'p4', stage: 'prevent', type: 'DAMAGE', source: 'Leyline of Sanctity', description: 'No damage prevented (Reckoner is a creature).', t: 'T1 +04', turn: 1, relatedId: 'bolt' },
  { id: 'p5', stage: 'resolve', type: 'DAMAGE', source: 'Lightning Bolt', description: '3 damage dealt to Boros Reckoner.', t: 'T1 +05', turn: 1, relatedId: 'bolt' },
  { id: 'p6', stage: 'react', type: 'DAMAGE_TRIGGER', source: 'Boros Reckoner', description: 'Reckoner deals 3 damage back to Bob.', t: 'T1 +06', turn: 1, relatedId: 'bolt' },
  { id: 'p7', stage: 'resolve', type: 'LIFE_CHANGE', source: 'Boros Reckoner', description: 'Bob loses 3 life (20 → 17).', t: 'T1 +07', turn: 1, relatedId: 'bolt' },

  // Turn 2 — Soul Warden ETB cascade
  { id: 'p8', stage: 'resolve', type: 'TURN_START', source: 'engine', description: 'Turn 2 begins. Alice draws Soul Warden.', t: 'T2 +01', turn: 2 },
  { id: 'p9', stage: 'resolve', type: 'SPELL_CAST', source: 'Alice', description: 'Alice casts Soul Warden ({W}).', t: 'T2 +02', turn: 2, relatedId: 'warden' },
  { id: 'p10', stage: 'resolve', type: 'ZONE_CHANGE', source: 'Soul Warden', description: 'Soul Warden enters the battlefield.', t: 'T2 +03', turn: 2, relatedId: 'warden' },
  { id: 'p11', stage: 'react', type: 'ETB', source: 'Soul Warden', description: 'ETB trigger queued.', t: 'T2 +04', turn: 2, relatedId: 'warden' },
  { id: 'p12', stage: 'react', type: 'LIFE_CHANGE', source: 'Soul Warden', description: 'Alice gains 1 life (17 → 18).', t: 'T2 +05', turn: 2, relatedId: 'warden' },

  // Turn 3 — Counterspell on Wrath of God
  { id: 'p13', stage: 'resolve', type: 'SPELL_CAST', source: 'Bob', description: 'Bob casts Wrath of God ({2}{W}{W}).', t: 'T3 +01', turn: 3, relatedId: 'wrath' },
  { id: 'p14', stage: 'prevent', type: 'COUNTERSPELL', source: 'Counterspell', description: 'Counterspell counters Wrath of God.', t: 'T3 +02', turn: 3, relatedId: 'wrath' },
  { id: 'p15', stage: 'resolve', type: 'ZONE_CHANGE', source: 'Wrath of God', description: 'Wrath of God put into Bob\'s graveyard.', t: 'T3 +03', turn: 3, relatedId: 'wrath' },
  { id: 'p16', stage: 'transform', type: 'QUERY_COST', source: 'Sphinx\'s Tutelage', description: 'Next spell costs {1} more (Trinisphere static).', t: 'T3 +04', turn: 3 },
  { id: 'p17', stage: 'react', type: 'END_STEP_TRIGGER', source: 'Forgotten Ancient', description: 'Move +1/+1 counters at end of turn.', t: 'T3 +05', turn: 3 },
];

export function GameView() {
  useEffect(() => useDiscoveryStore.getState().markPlayed('mtg'), []);
  const { matchId } = useParams<{ matchId: string }>();
  const navigate = useNavigate();

  const {
    gameState,
    ui,
    playerId,
    isConnected,
    sendAction,
    pass,
    castSpell,
    playLand,
    selectCard,
    selectAction,
    toggleAttacker,
    canAct,
    canDeclareAttackers,
    setError,
    setAutoPassMode,
    enablePassUntilEndOfTurn,
    hasActionsOtherThanPass,
  } = useGame();

  // Drag clears itself via useCardZone.onDrop (calls clearAll after the
  // play action fires), so the explicit endDrag calls here are redundant
  // — but harmless as a defensive guard. Wraps cardZoneStore.endDrag.
  const endDrag = useCallback(() => useCardZoneStore.getState().endDrag(), []);

  const storeMatchId = useGameStore((state) => state.matchId);
  const storePlayerId = useGameStore((state) => state.playerId);
  const setGameState = useGameStore((state) => state.setGameState);
  const setConnection = useGameStore((state) => state.setConnection);

  // Fetch initial state if we don't have connection info
  useEffect(() => {
    if (!matchId) return;

    // Spectator auto-join: landed here without prior connection info
    // (e.g. via /watch/live or a shared /game/<id> link). Pick the first
    // player as the viewer so the spectator sees one seat's hand. The
    // submitted-action layer remains live but is gated by the engine's
    // active-player check, so accidental clicks lose the race to the
    // ultra subprocess that's actually piloting that seat.
    if (!storeMatchId || storeMatchId !== matchId) {
      const joinAsSpectator = async () => {
        try {
          const initial = await matchAPI.getState(matchId);
          const playerIds = Object.keys(initial.players || {});
          const spectatorPlayerId = playerIds[0];
          if (!spectatorPlayerId) {
            navigate('/');
            return;
          }
          setConnection(matchId, spectatorPlayerId, false);
          const full = await matchAPI.getState(matchId, spectatorPlayerId);
          setGameState(full);
        } catch {
          navigate('/');
        }
      };
      joinAsSpectator();
      return;
    }

    // Normal flow — fetch initial state for a match we're already connected to
    const fetchState = async () => {
      try {
        const state = await matchAPI.getState(matchId, storePlayerId || undefined);
        setGameState(state);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to fetch game state');
      }
    };

    if (!gameState && storePlayerId) {
      fetchState();
    }
  }, [matchId, storeMatchId, storePlayerId, gameState, navigate, setGameState, setError, setConnection]);

  useEffect(() => {
    if (gameState?.game_mode === 'minecraft' && matchId) {
      navigate(`/game/${matchId}/mc`, { replace: true });
    }
  }, [gameState?.game_mode, matchId, navigate]);

  useEffect(() => {
    if (gameState?.game_mode === 'depths' && matchId) {
      navigate(`/game/${matchId}/depths`, { replace: true });
    }
  }, [gameState?.game_mode, matchId, navigate]);

  useEffect(() => {
    if (gameState?.game_mode === 'scp' && matchId) {
      navigate(`/game/${matchId}/scp`, { replace: true });
    }
  }, [gameState?.game_mode, matchId, navigate]);

  // Handle card clicks
  const handleCardClick = useCallback(
    (card: CardData, zone: 'hand' | 'battlefield') => {
      // If in declare attackers step, toggle attacker
      if (canDeclareAttackers && zone === 'battlefield') {
        toggleAttacker(card.id);
        return;
      }

      // If clicking a card in hand
      if (zone === 'hand' && canAct()) {
        // Check if it's a castable spell — drag-to-target is handled by
        // GameBoard's own DnD layer (handleCastSpell). Plain clicks just
        // queue the cast in the action menu; targets are picked there if
        // needed.
        const castAction = gameState?.legal_actions.find(
          (a) => a.type === 'CAST_SPELL' && a.card_id === card.id
        );
        if (castAction) {
          castSpell(card.id);
          return;
        }

        // Check if it's a playable land
        const landAction = gameState?.legal_actions.find(
          (a) => a.type === 'PLAY_LAND' && a.card_id === card.id
        );
        if (landAction) {
          playLand(card.id);
          return;
        }
      }

      // Default: just select the card
      selectCard(card.id);
    },
    [
      canDeclareAttackers,
      canAct,
      gameState,
      toggleAttacker,
      castSpell,
      playLand,
      selectCard,
    ]
  );

  // Handle playing a land via drag and drop
  const handlePlayLand = useCallback(
    (cardId: string) => {
      endDrag();
      playLand(cardId);
      // Immediately send the action since lands don't need confirmation
      const action = gameState?.legal_actions.find(
        (a) => a.type === 'PLAY_LAND' && a.card_id === cardId
      );
      if (action) {
        selectAction(action);
        // Send action after state updates
        setTimeout(() => sendAction(), 0);
      }
    },
    [playLand, gameState, selectAction, sendAction, endDrag]
  );

  // Handle casting a spell via drag and drop. When targets are
  // supplied by the DnD layer, bypass `selectAction` + `sendAction`
  // (which used to route through the deleted selectedTargets slice)
  // and submit the request directly with targets baked in.
  const handleCastSpell = useCallback(
    (cardId: string, targets?: string[]) => {
      endDrag();
      if (!targets || targets.length === 0) {
        castSpell(cardId);
        setTimeout(() => sendAction(), 0);
        return;
      }
      if (!playerId || !matchId) return;
      const request = {
        action_type: 'CAST_SPELL' as const,
        player_id: playerId,
        card_id: cardId,
        targets: [targets],
      };
      matchAPI.submitAction(matchId, request).then((result) => {
        if (result.success && result.new_state) {
          setGameState(result.new_state);
        } else if (!result.success) {
          setError(result.message);
        }
      }).catch((err) => {
        setError(err instanceof Error ? err.message : 'Failed to cast spell');
      });
    },
    [castSpell, sendAction, endDrag, playerId, matchId, setGameState, setError]
  );

  // Handle casting a multi-target spell
  const handleCastMultiTargetSpell = useCallback(
    (cardId: string, targets: string[][]) => {
      endDrag();

      // Find and select the action
      const action = gameState?.legal_actions.find(
        (a) => a.type === 'CAST_SPELL' && a.card_id === cardId
      );
      if (!action || !playerId) return;

      // Build and send the action request directly
      const request = {
        action_type: 'CAST_SPELL' as const,
        player_id: playerId,
        card_id: cardId,
        targets: targets,
      };

      matchAPI.submitAction(matchId!, request).then((result) => {
        if (result.success && result.new_state) {
          setGameState(result.new_state);
        } else if (!result.success) {
          setError(result.message);
        }
      }).catch((err) => {
        setError(err instanceof Error ? err.message : 'Failed to cast spell');
      });
    },
    [gameState, playerId, matchId, setGameState, setError, endDrag]
  );

  // Handle action selection from menu. Cast-time targeting is now driven
  // entirely by GameBoard's drag-to-target layer (which calls
  // handleCastSpell/handleCastMultiTargetSpell with targets baked in) and
  // by pending_choice for resolution-time choices — so the action menu
  // just queues the action and sendAction() submits it.
  const handleActionSelect = useCallback(
    (action: LegalActionData) => {
      selectAction(action);
    },
    [selectAction]
  );

  // Handle confirm action
  const handleConfirmAction = useCallback(async () => {
    await sendAction();
  }, [sendAction]);

  // Handle cancel
  const handleCancel = useCallback(() => {
    selectAction(null);
    selectCard(null);
  }, [selectAction, selectCard]);

  // Handle "Respond" from the priority prompt — scroll the sidebar's
  // action menu into view so the player sees their options. v1 deliberately
  // doesn't pop a modal — the action menu already lists everything cast/
  // activate-able. Future: a richer popup that filters to instant-speed
  // responses while the stack is non-empty.
  const handleRespondToPriority = useCallback(() => {
    const menu = document.getElementById('action-menu-anchor');
    if (menu) {
      menu.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }, []);

  // Handle concede
  const handleConcede = useCallback(async () => {
    if (!matchId || !playerId) return;
    if (!confirm('Are you sure you want to concede?')) return;

    try {
      await matchAPI.concede(matchId, playerId);
      navigate('/');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to concede');
    }
  }, [matchId, playerId, navigate, setError]);

  // Track choice submission loading state
  const [isSubmittingChoice, setIsSubmittingChoice] = useState(false);
  const [isGraveyardOpen, setIsGraveyardOpen] = useState(false);

  // HD-CRIT-018 ⌥P pipeline view overlay state. The overlay swaps the
  // cards for a TRANSFORM/PREVENT/RESOLVE/REACT event-stream view; ⌥P
  // toggles, Escape closes. `selectedEventId` is the cross-column
  // highlight target (v1 = visual only).
  const [pipelineOpen, setPipelineOpen] = useState(false);
  const [selectedEventId, setSelectedEventId] = useState<string | null>(null);
  const togglePipeline = useCallback(() => {
    setPipelineOpen((v) => !v);
    setSelectedEventId(null);
  }, []);
  useAltP(togglePipeline);
  useEffect(() => {
    if (!pipelineOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        setPipelineOpen(false);
      }
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [pipelineOpen]);

  // Check if there's a pending choice for this player
  const pendingChoice = useMemo(() => {
    if (!gameState?.pending_choice || !playerId) return null;
    // Only show if it's this player's choice to make
    if (gameState.pending_choice.player !== playerId) return null;
    return gameState.pending_choice;
  }, [gameState?.pending_choice, playerId]);

  // Phase 5b: MTG cast-time targets ship as overlay-mode pending choices.
  // GameBoard renders click-to-target highlights for these; ChoiceModal
  // collapses to a floating cancel pill (see ChoiceModal isOverlayMode).
  const overlayPendingChoice = useMemo(() => {
    if (!pendingChoice) return null;
    return pendingChoice.interaction_mode === 'overlay' ? pendingChoice : null;
  }, [pendingChoice]);

  // Arc A — fold MTG cast-time targeting into the shared cardZoneStore.
  // When an overlay-mode pending_choice arrives, prime the store with
  // its options as valid zones. Each click on a lit zone appends to
  // pendingTargets; the overlay pill (in ChoiceModal) submits via
  // matchAPI.submitChoice when min/max satisfied.
  useEffect(() => {
    const store = useCardZoneStore.getState();
    if (overlayPendingChoice && gameState?.game_mode) {
      const accent = ENGINE_ACCENT_BY_MODE[gameState.game_mode] ?? '#a78bfa';
      const optionIds = (overlayPendingChoice.options ?? [])
        .map((opt) => (typeof opt === 'string' ? opt : opt.id))
        .filter((id): id is string => typeof id === 'string');
      // Re-prime on id transition (engine emitted a new choice).
      if (store.activeChoiceId !== overlayPendingChoice.id) {
        store.primeFromChoice({
          choiceId: overlayPendingChoice.id,
          sourceId: overlayPendingChoice.source_id ?? null,
          prompt: overlayPendingChoice.prompt ?? 'Pick a target',
          engineId: gameState.game_mode,
          accent,
          optionIds,
          // Arc B will populate target_metadata; until then, synthesize
          // a minimal shape from min/max so the pill renders progress.
          metadata: {
            label: overlayPendingChoice.prompt ?? 'Target',
            predicate_description: '',
            min: overlayPendingChoice.min_choices ?? 1,
            max: overlayPendingChoice.max_choices ?? 1,
          },
        });
      }
    } else if (store.activeChoiceId !== null) {
      store.clearChoice();
    }
  }, [overlayPendingChoice, gameState?.game_mode]);

  // Handle choice submission
  const handleChoiceSubmit = useCallback(async (selectedIds: string[]) => {
    if (!matchId || !playerId || !pendingChoice) return;

    setIsSubmittingChoice(true);
    try {
      const result = await matchAPI.submitChoice(
        matchId,
        pendingChoice.id,
        playerId,
        selectedIds
      );
      if (result.success && result.new_state) {
        setGameState(result.new_state);
      } else if (!result.success) {
        setError(result.message);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to submit choice');
    } finally {
      setIsSubmittingChoice(false);
    }
  }, [matchId, playerId, pendingChoice, setGameState, setError]);

  // Build graveyard lookup for choice modal
  const graveyardLookup = useMemo(() => {
    return gameState?.graveyard || {};
  }, [gameState?.graveyard]);

  const myGraveyard = useMemo(() => {
    if (!gameState || !playerId) return [];
    return gameState.graveyard?.[playerId] || [];
  }, [gameState, playerId]);

  const handleGraveyardCast = useCallback(
    (action: LegalActionData) => {
      setIsGraveyardOpen(false);
      selectAction(action);
      // Cast-time targets come from drag-to-target or pending_choice; this
      // path just queues the action and submits.
      setTimeout(() => sendAction(), 0);
    },
    [selectAction, sendAction]
  );

  // Keyboard shortcuts for auto-pass
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // F6 - Toggle pass until end of turn
      if (e.key === 'F6') {
        e.preventDefault();
        if (ui.autoPassMode === 'end_of_turn') {
          setAutoPassMode('no_actions');
        } else {
          enablePassUntilEndOfTurn();
        }
      }
      // Escape - Cancel auto-pass modes (except smart mode)
      if (e.key === 'Escape' && ui.autoPassMode === 'end_of_turn') {
        e.preventDefault();
        setAutoPassMode('no_actions');
      }
      // Space - Quick pass (when we have priority)
      if (e.key === ' ' && canAct() && !ui.selectedAction) {
        e.preventDefault();
        pass();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [ui.autoPassMode, ui.selectedAction, setAutoPassMode, enablePassUntilEndOfTurn, canAct, pass]);

  // HD-CRIT-018 — derive pipeline events from game_log when present, fall
  // back to sample data so the overlay always renders something demoable.
  // Hook must live ABOVE the engine-route early-returns so React's hook
  // counter stays stable across re-renders (otherwise the next render
  // calls one more useMemo than the previous and crashes the page).
  const pipelineEvents = useMemo<PipelineEvent[]>(() => {
    if (gameState?.game_log && gameState.game_log.length > 0) {
      return gameLogToPipelineEvents(
        gameState.game_log,
        gameState.players,
      );
    }
    return SAMPLE_PIPELINE_EVENTS;
  }, [gameState?.game_log, gameState?.players]);

  // Route to HS view for hearthstone-engine games
  if (gameState?.game_mode === 'hearthstone') {
    return <HSGameView />;
  }

  // Route to PKM view for pokemon-engine games
  if (gameState?.game_mode === 'pokemon') {
    return <PKMGameView />;
  }

  // Route to YGO view for yugioh-engine games
  if (gameState?.game_mode === 'yugioh') {
    return <YGOGameView />;
  }

  if (gameState?.game_mode === 'minecraft') {
    return (
      <div className="min-h-screen bg-game-bg flex items-center justify-center">
        <div className="w-16 h-16 border-4 border-game-accent border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  if (gameState?.game_mode === 'finance') {
    return (
      <div className="min-h-screen flex items-center justify-center" style={{ background: '#03080f' }}>
        <div className="w-16 h-16 border-4 border-t-transparent rounded-full animate-spin" style={{ borderColor: '#00FF88', borderTopColor: 'transparent' }} />
      </div>
    );
  }

  if (gameState?.game_mode === 'depths') {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-950">
        <div
          className="w-16 h-16 border-4 border-t-transparent rounded-full animate-spin"
          style={{ borderColor: '#22d3ee', borderTopColor: 'transparent' }}
        />
      </div>
    );
  }

  if (gameState?.game_mode === 'scp') {
    return <SCPGameView />;
  }

  // Loading state
  if (!gameState || !playerId) {
    return (
      <div className="min-h-screen bg-brand-ink flex items-center justify-center">
        <div className="text-center">
          <div className="w-16 h-16 border-4 border-brand-foil border-t-transparent rounded-full animate-spin mx-auto mb-4" />
          <p className="brand-eyebrow text-brand-chalk">Loading match</p>
        </div>
      </div>
    );
  }

  // Derive a few brand-bar metadata pieces from the game state shape.
  // Defensive: gameState shape varies across modes, so missing fields
  // gracefully degrade to omitted chips rather than crashing.
  const turnNumber =
    (gameState as unknown as { turn_number?: number }).turn_number ??
    (gameState as unknown as { turn?: number }).turn;
  const phaseName =
    (gameState as unknown as { phase?: string }).phase ??
    (gameState as unknown as { current_phase?: string }).current_phase;
  const opponentEntry =
    gameState?.players &&
    Object.entries(gameState.players).find(([id]) => id !== playerId);
  const opponentName = opponentEntry ? (opponentEntry[1] as { name?: string }).name : undefined;
  const playerEntry = gameState?.players?.[playerId] as { name?: string } | undefined;
  const playerName = playerEntry?.name;

  // HD-CRIT 17 — read-only Timeline rail. During a live game we don't
  // know the total length, so we floor the right edge a few turns out and
  // label it LIVE so the bar reads as "you're here" instead of "X% done".
  const railCurrent = typeof turnNumber === 'number' ? turnNumber : 0;
  const railTotal = Math.max(railCurrent + 1, 8);

  return (
    <GameViewLayout
      mode="mtg"
      matchId={matchId}
      turn={turnNumber}
      phase={phaseName}
      opponentName={opponentName}
      playerName={playerName}
      pipelineOpen={pipelineOpen}
    >
    <div
      className="px-4 py-2 border-b"
      style={{
        background: 'var(--paper)',
        color: 'var(--ink)',
        borderColor: 'var(--rule-2)',
      }}
    >
      <Timeline
        currentTurn={railCurrent}
        totalTurns={railTotal}
        endLabel="LIVE"
        mode="compact"
        ariaLabel={`Live match — currently turn ${railCurrent}`}
      />
    </div>
    <div className="min-h-[calc(100vh-3.5rem)] bg-brand-ink flex">
      {/* Main Game Area */}
      <div className="flex-1 relative">
        <GameBoard
          gameState={gameState}
          playerId={playerId}
          selectedCardId={ui.selectedCardId}
          selectedAttackers={ui.selectedAttackers}
          selectedBlockers={ui.selectedBlockers}
          onCardClick={handleCardClick}
          onPlayLand={handlePlayLand}
          onCastSpell={handleCastSpell}
          onCastMultiTargetSpell={handleCastMultiTargetSpell}
          overlayPendingChoice={overlayPendingChoice}
          onSubmitOverlayChoice={handleChoiceSubmit}
        />

        {/* Priority Prompt — surfaces priority window during stack
            resolution. Auto-pass already handles the no-stack case;
            this only renders when something is on the stack OR a
            trigger has just fired and is waiting in the queue. */}
        <PriorityPrompt
          gameState={gameState}
          playerId={playerId}
          onPass={pass}
          onRespond={handleRespondToPriority}
        />

        {/* Choice Modal Overlay. In overlay mode the modal renders just
            a floating Cancel pill; GameBoard handles target highlighting
            and click submission. `onCancel` is intentionally a no-op for
            cast-time targeting (MTG rules don't allow aborting a cast
            once initiated). The choice will time out server-side if the
            player doesn't pick. */}
        {pendingChoice && (
          <ChoiceModal
            pendingChoice={pendingChoice}
            battlefield={gameState.battlefield}
            hand={gameState.hand}
            graveyard={graveyardLookup}
            players={gameState.players}
            onSubmit={handleChoiceSubmit}
            onCancel={pendingChoice.interaction_mode === 'overlay' ? () => { /* server choice stays pending */ } : undefined}
            isLoading={isSubmittingChoice}
          />
        )}

        {/* Graveyard Modal */}
        <GraveyardModal
          isOpen={isGraveyardOpen}
          cards={myGraveyard}
          legalActions={gameState.legal_actions}
          canAct={canAct()}
          onClose={() => setIsGraveyardOpen(false)}
          onCast={handleGraveyardCast}
        />
      </div>

      {/* Sidebar */}
      <div className="w-80 bg-brand-obsidian border-l border-brand-hairline/60 flex flex-col">
        {/* Connection Status */}
        <div className="p-3 border-b border-brand-hairline/60 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div
              className={`w-2 h-2 rounded-full ${
                isConnected ? 'bg-brand-sheen' : 'bg-brand-ember'
              }`}
            />
            <span className="brand-eyebrow text-brand-chalk">
              {isConnected ? 'Connected' : 'Disconnected'}
            </span>
          </div>
          <button
            onClick={handleConcede}
            className="text-[11px] uppercase tracking-[0.14em] text-brand-ember/80 hover:text-brand-ember transition-colors"
          >
            Concede
          </button>
        </div>

        {/* Action Menu */}
        <div id="action-menu-anchor" className="flex-1 p-4 overflow-y-auto">
          <ActionMenu
            actions={gameState.legal_actions}
            selectedAction={ui.selectedAction}
            canAct={canAct()}
            isLoading={ui.isLoading}
            autoPassMode={ui.autoPassMode}
            hasActionsOtherThanPass={hasActionsOtherThanPass()}
            onActionSelect={handleActionSelect}
            onPass={pass}
            onConfirm={handleConfirmAction}
            onCancel={handleCancel}
            onSetAutoPassMode={setAutoPassMode}
            onPassUntilEndOfTurn={enablePassUntilEndOfTurn}
          />

          {/* Zones */}
          <div className="mt-6 pt-4 border-t border-brand-hairline/60">
            <div className="brand-eyebrow mb-2">Zones</div>
            <button
              onClick={() => setIsGraveyardOpen(true)}
              className="w-full px-3 py-2 bg-brand-shelf hover:bg-brand-glass border border-brand-hairline hover:border-brand-foil/40 text-brand-cream transition-all text-sm"
              title="View your graveyard"
            >
              Graveyard <span className="brand-mono text-brand-foil">({myGraveyard.length})</span>
            </button>
          </div>

          {/* Game Log */}
          <div className="mt-6 pt-4 border-t border-brand-hairline/60">
            <GameLog
              entries={gameState.game_log || []}
              playerNames={Object.fromEntries(Object.entries(gameState.players).map(([id, p]) => [id, p.name]))}
              scrollClass="max-h-64"
              accentClass="bg-brand-foil/15"
            />
          </div>

          {/* Animations preference */}
          <div className="mt-4 pt-3 border-t border-brand-hairline/60">
            <AnimationsToggle />
          </div>

          {/* Error Display */}
          {ui.error && (
            <div className="mt-4 p-3 bg-brand-ember/10 border border-brand-ember/50 text-brand-ember text-sm">
              {ui.error}
            </div>
          )}
        </div>

        {/* Drag hint */}
        <div className="px-4 py-2 border-t border-brand-hairline/60 text-xs text-brand-dust text-center">
          Tip: drag cards from your hand to play lands or target spells <span className="brand-mono">· ⌥P pipeline</span>
        </div>
      </div>
    </div>

    {/* HD-CRIT-018 — ⌥P Pipeline View overlay. Replaces the cards with
        the four-column event stream. Toggled by useAltP above; Escape
        closes. Click on the scrim closes too. The modal is a paper
        chassis matching EnginePicker's lab styling. */}
    {pipelineOpen && (
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Pipeline view"
        data-testid="pipeline-overlay"
        onClick={(e) => {
          if (e.target === e.currentTarget) setPipelineOpen(false);
        }}
        style={{
          position: 'fixed',
          inset: 0,
          zIndex: 1000,
          background: 'color-mix(in oklab, var(--ink) 28%, transparent)',
          backdropFilter: 'blur(8px) saturate(1.05)',
          display: 'grid',
          placeItems: 'center',
          padding: 24,
          fontFamily: 'var(--font-sans)',
        }}
      >
        <div
          style={{
            width: 'min(1400px, 100%)',
            maxHeight: 'calc(100vh - 48px)',
            background: 'var(--paper)',
            border: '1.5px solid var(--ink)',
            boxShadow: '0 30px 80px -30px rgba(20,24,40,.55)',
            padding: 26,
            display: 'grid',
            gridTemplateRows: 'auto 1fr auto',
            gap: 18,
            minHeight: 0,
          }}
        >
          <header
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'baseline',
              borderBottom: '1px solid var(--rule)',
              paddingBottom: 14,
            }}
          >
            <h2
              style={{
                margin: 0,
                fontFamily: 'var(--font-serif)',
                fontSize: 32,
                fontWeight: 400,
                lineHeight: 1,
                letterSpacing: '-.015em',
                color: 'var(--ink)',
              }}
            >
              The cards are an{' '}
              <em style={{ color: 'var(--sodium)', fontStyle: 'italic' }}>
                event stream
              </em>
              .
            </h2>
            <div
              style={{
                display: 'flex',
                gap: 16,
                alignItems: 'baseline',
                fontFamily: 'var(--font-mono)',
                fontSize: 11,
                letterSpacing: '.1em',
                textTransform: 'uppercase',
                color: 'var(--ink-3)',
              }}
            >
              <span>Turn {turnNumber ?? 1}</span>
              <span>{pipelineEvents.length} events</span>
              <span>⌥P · Esc to close</span>
            </div>
          </header>

          <div style={{ minHeight: 0, display: 'flex' }}>
            <PipelineView
              events={pipelineEvents}
              activeStage={
                (phaseName?.toLowerCase().includes('react')
                  ? 'react'
                  : 'resolve') as PipelineStage
              }
              selectedEventId={selectedEventId}
              onSelect={(id) =>
                setSelectedEventId((cur) => (cur === id ? null : id))
              }
            />
          </div>

          <footer
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              borderTop: '1px solid var(--rule)',
              paddingTop: 14,
              fontFamily: 'var(--font-mono)',
              fontSize: 11,
              letterSpacing: '.1em',
              textTransform: 'uppercase',
              color: 'var(--ink-3)',
            }}
          >
            <span style={{ textTransform: 'none', letterSpacing: 0 }}>
              {gameState?.game_log && gameState.game_log.length > 0
                ? `Live from match ${matchId}. Stage classification is heuristic until the server bridges InterceptorPriority.`
                : 'Demo events — match log is empty.'}
            </span>
            <span>HD-CRIT-018 · PIPELINE</span>
          </footer>
        </div>
      </div>
    )}
    </GameViewLayout>
  );
}

export default GameView;
