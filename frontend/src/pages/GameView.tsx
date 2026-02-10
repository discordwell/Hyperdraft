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
import { GameBoard, GraveyardModal } from '../components/game';
import { ActionMenu, TargetPicker, ChoiceModal } from '../components/actions';
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
    startTargeting,
    addTarget,
    cancelTargeting,
    confirmTargets,
    toggleAttacker,
    canAct,
    canDeclareAttackers,
    setError,
    setAutoPassMode,
    enablePassUntilEndOfTurn,
    hasActionsOtherThanPass,
  } = useGame();

  const { endDrag } = useDragDropStore();

  const storeMatchId = useGameStore((state) => state.matchId);
  const storePlayerId = useGameStore((state) => state.playerId);
  const setGameState = useGameStore((state) => state.setGameState);

  // Fetch initial state if we don't have connection info
  useEffect(() => {
    if (!matchId) return;

    // If we don't have connection info, try to get it
    if (!storeMatchId || storeMatchId !== matchId) {
      // For now, redirect to home - in a real app, we'd have a rejoin mechanism
      navigate('/');
      return;
    }

    // Fetch initial game state
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
  }, [matchId, storeMatchId, storePlayerId, gameState, navigate, setGameState, setError]);

  // Handle card clicks
  const handleCardClick = useCallback(
    (card: CardData, zone: 'hand' | 'battlefield') => {
      // If we're in targeting mode
      if (ui.targetingMode !== 'none') {
        // If clicking a valid target, add it
        if (ui.validTargets.includes(card.id)) {
          addTarget(card.id);
          return;
        }
        // If clicking a card in hand (not a valid target), cancel targeting and allow new selection
        if (zone === 'hand') {
          cancelTargeting();
          // Fall through to normal hand card handling below
        } else {
          // Clicking an invalid target on battlefield - do nothing
          return;
        }
      }

      // If in declare attackers step, toggle attacker
      if (canDeclareAttackers && zone === 'battlefield') {
        toggleAttacker(card.id);
        return;
      }

      // If clicking a card in hand
      if (zone === 'hand' && canAct()) {
        // Check if it's a castable spell
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
      ui.targetingMode,
      ui.validTargets,
      canDeclareAttackers,
      canAct,
      gameState,
      addTarget,
      cancelTargeting,
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

  // Handle casting a spell via drag and drop
  const handleCastSpell = useCallback(
    (cardId: string, targets?: string[]) => {
      endDrag();
      castSpell(cardId);

      // If we have targets, add them
      if (targets && targets.length > 0) {
        targets.forEach((t) => addTarget(t));
        confirmTargets();
      }

      // Send the action
      setTimeout(() => sendAction(), 0);
    },
    [castSpell, addTarget, confirmTargets, sendAction, endDrag]
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

  // Handle action selection from menu
  const handleActionSelect = useCallback(
    (action: LegalActionData) => {
      selectAction(action);

      // If this action requires targets, enter targeting mode.
      // Server will validate targets; we use a broad allow-list client-side.
      if (action.type === 'CAST_SPELL' && action.requires_targets && gameState) {
        const validTargets = [
          ...gameState.battlefield.map((c) => c.id),
          ...Object.keys(gameState.players),
        ];
        startTargeting('single', validTargets);
      }
    },
    [selectAction, startTargeting, gameState]
  );

  // Handle confirm action
  const handleConfirmAction = useCallback(async () => {
    // If we have selected targets, confirm them first
    if (ui.selectedTargets.length > 0) {
      confirmTargets();
    }

    await sendAction();
  }, [ui.selectedTargets, confirmTargets, sendAction]);

  // Handle cancel
  const handleCancel = useCallback(() => {
    if (ui.targetingMode !== 'none') {
      cancelTargeting();
    } else {
      selectAction(null);
      selectCard(null);
    }
  }, [ui.targetingMode, cancelTargeting, selectAction, selectCard]);

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

  // Handle choice submission
  const handleChoiceSubmit = useCallback(async (selectedIds: string[]) => {
    if (!matchId || !playerId || !pendingChoice) return;

    setIsSubmittingChoice(true);
    try {
      const result = await matchAPI.submitChoice(matchId, playerId, selectedIds);
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

      if (!gameState) return;

      if (action.type === 'CAST_SPELL' && action.requires_targets) {
        const validTargets = [
          ...gameState.battlefield.map((c) => c.id),
          ...Object.keys(gameState.players),
        ];
        startTargeting('single', validTargets);
        return;
      }

      // Fire immediately for non-targeted casts (consistent with hand drag-cast).
      setTimeout(() => sendAction(), 0);
    },
    [gameState, selectAction, startTargeting, sendAction]
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
      if (e.key === ' ' && canAct() && !ui.selectedAction && ui.targetingMode === 'none') {
        e.preventDefault();
        pass();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [ui.autoPassMode, ui.selectedAction, ui.targetingMode, setAutoPassMode, enablePassUntilEndOfTurn, canAct, pass]);

  // Loading state
  if (!gameState || !playerId) {
    return (
      <div className="min-h-screen bg-game-bg flex items-center justify-center">
        <div className="text-center">
          <div className="w-16 h-16 border-4 border-game-accent border-t-transparent rounded-full animate-spin mx-auto mb-4" />
          <p className="text-gray-400">Loading game...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-game-bg flex">
      {/* Main Game Area */}
      <div className="flex-1 relative">
        <GameBoard
          gameState={gameState}
          playerId={playerId}
          selectedCardId={ui.selectedCardId}
          validTargets={ui.validTargets}
          selectedAttackers={ui.selectedAttackers}
          selectedBlockers={ui.selectedBlockers}
          onCardClick={handleCardClick}
          onPlayLand={handlePlayLand}
          onCastSpell={handleCastSpell}
          onCastMultiTargetSpell={handleCastMultiTargetSpell}
        />

        {/* Target Picker Overlay */}
        <TargetPicker
          isActive={ui.targetingMode !== 'none'}
          selectedTargets={ui.selectedTargets}
          requiredCount={ui.requiredTargetCount}
          onConfirm={handleConfirmAction}
          onCancel={cancelTargeting}
        />

        {/* Choice Modal Overlay */}
        {pendingChoice && (
          <ChoiceModal
            pendingChoice={pendingChoice}
            battlefield={gameState.battlefield}
            hand={gameState.hand}
            graveyard={graveyardLookup}
            players={gameState.players}
            onSubmit={handleChoiceSubmit}
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
      <div className="w-80 bg-game-surface border-l border-gray-700 flex flex-col">
        {/* Connection Status */}
        <div className="p-3 border-b border-gray-700 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div
              className={`w-2 h-2 rounded-full ${
                isConnected ? 'bg-green-500' : 'bg-red-500'
              }`}
            />
            <span className="text-sm text-gray-400">
              {isConnected ? 'Connected' : 'Disconnected'}
            </span>
          </div>
          <button
            onClick={handleConcede}
            className="text-xs text-red-400 hover:text-red-300"
          >
            Concede
          </button>
        </div>

        {/* Action Menu */}
        <div className="flex-1 p-4 overflow-y-auto">
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
          <div className="mt-6 pt-4 border-t border-gray-700">
            <div className="text-xs text-gray-400 uppercase tracking-wide mb-2">
              Zones
            </div>
            <button
              onClick={() => setIsGraveyardOpen(true)}
              className="w-full px-3 py-2 rounded bg-gray-700 text-gray-200 hover:bg-gray-600 transition-all text-sm font-semibold"
              title="View your graveyard"
            >
              Graveyard ({myGraveyard.length})
            </button>
          </div>

          {/* Error Display */}
          {ui.error && (
            <div className="mt-4 p-3 bg-red-900/50 border border-red-500 rounded text-red-200 text-sm">
              {ui.error}
            </div>
          )}
        </div>

        {/* Drag hint */}
        <div className="px-4 py-2 border-t border-gray-700 text-xs text-gray-500 text-center">
          Tip: Drag cards from your hand to play lands or target spells
        </div>

        {/* Back to Menu */}
        <div className="p-3 border-t border-gray-700">
          <button
            onClick={() => navigate('/')}
            className="w-full px-4 py-2 bg-gray-700 text-gray-300 rounded hover:bg-gray-600 transition-all"
          >
            Back to Menu
          </button>
        </div>
      </div>
    </div>
  );
}

export default GameView;
