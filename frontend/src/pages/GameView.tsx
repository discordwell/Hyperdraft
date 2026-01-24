/**
 * GameView Page
 *
 * Main game playing interface.
 */

import { useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useGame } from '../hooks/useGame';
import { useGameStore } from '../stores/gameStore';
import { GameBoard } from '../components/game';
import { ActionMenu, TargetPicker } from '../components/actions';
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
    addTarget,
    cancelTargeting,
    confirmTargets,
    toggleAttacker,
    canAct,
    canDeclareAttackers,
    setError,
  } = useGame();

  const storeMatchId = useGameStore((state) => state.matchId);
  const storePlayerId = useGameStore((state) => state.playerId);
  const setConnection = useGameStore((state) => state.setConnection);
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
      // If we're in targeting mode, try to add as target
      if (ui.targetingMode !== 'none') {
        if (ui.validTargets.includes(card.id)) {
          addTarget(card.id);
        }
        return;
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
      toggleAttacker,
      castSpell,
      playLand,
      selectCard,
    ]
  );

  // Handle action selection from menu
  const handleActionSelect = useCallback(
    (action: LegalActionData) => {
      selectAction(action);

      // If it's a cast spell action on a specific card, handle it
      if (action.type === 'CAST_SPELL' && action.card_id) {
        castSpell(action.card_id);
      } else if (action.type === 'PLAY_LAND' && action.card_id) {
        playLand(action.card_id);
      }
    },
    [selectAction, castSpell, playLand]
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
        />

        {/* Target Picker Overlay */}
        <TargetPicker
          isActive={ui.targetingMode !== 'none'}
          selectedTargets={ui.selectedTargets}
          requiredCount={ui.requiredTargetCount}
          onConfirm={handleConfirmAction}
          onCancel={cancelTargeting}
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
            onActionSelect={handleActionSelect}
            onPass={pass}
            onConfirm={handleConfirmAction}
            onCancel={handleCancel}
          />

          {/* Error Display */}
          {ui.error && (
            <div className="mt-4 p-3 bg-red-900/50 border border-red-500 rounded text-red-200 text-sm">
              {ui.error}
            </div>
          )}
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
