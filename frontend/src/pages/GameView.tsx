/**
 * GameView Page
 *
 * Main game playing interface with drag and drop support.
 */

import { useEffect, useCallback, useState, useMemo } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useGame } from '../hooks/useGame';
import { useGameStore } from '../stores/gameStore';
import { useDragDropStore } from '../hooks/useDragDrop';
import { GameBoard, GraveyardModal, PriorityPrompt } from '../components/game';
import { GameLog } from '../components/game/GameLog';
import { AnimationsToggle } from '../components/game/shared/AnimationsToggle';
import { ActionMenu, ChoiceModal } from '../components/actions';
import { GameViewLayout } from '../components/brand';
import { HSGameView } from './HSGameView';
import { PKMGameView } from './PKMGameView';
import { YGOGameView } from './YGOGameView';
import { SCPGameView } from './SCPGameView';
import { matchAPI } from '../services/api';
import type { CardData, LegalActionData } from '../types';

export function GameView() {
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

  const endDrag = useDragDropStore((s) => s.endDrag);

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

  return (
    <GameViewLayout
      mode="mtg"
      matchId={matchId}
      turn={turnNumber}
      phase={phaseName}
      opponentName={opponentName}
      playerName={playerName}
    >
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
          Tip: drag cards from your hand to play lands or target spells
        </div>
      </div>
    </div>
    </GameViewLayout>
  );
}

export default GameView;
