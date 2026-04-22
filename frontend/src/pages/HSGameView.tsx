/**
 * HSGameView Page
 *
 * Dedicated game view for Hearthstone-engine games (vanilla HS, Stormrift, etc).
 * Uses the useHSGame hook for HS-specific action types.
 */

import { useEffect, useCallback, useState, useMemo } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useHSGame } from '../hooks/useHSGame';
import { useGameStore } from '../stores/gameStore';
import { HSGameBoard } from '../components/game/HSGameBoard';
import { DragHintOverlay } from '../components/game/DragHintOverlay';
import { HSGameLog } from '../components/game/HSGameLog';
import { AnimationsToggle } from '../components/game/shared/AnimationsToggle';
import { matchAPI } from '../services/api';

export function HSGameView() {
  const { matchId } = useParams<{ matchId: string }>();
  const navigate = useNavigate();
  const [sidebarTab, setSidebarTab] = useState<'info' | 'log'>('info');

  const {
    gameState,
    playerId,
    isConnected,
    myPlayer,
    isMyTurn,
    canPlayCard,
    canAttuneCard,
    canAttack,
    canUseHeroPower,
    getAttackableTargets,
    playCard,
    attuneCard,
    attack,
    useHeroPower,
    endTurn,
    setError,
    error,
  } = useHSGame();

  const storeMatchId = useGameStore((state) => state.matchId);
  const storePlayerId = useGameStore((state) => state.playerId);
  const setGameState = useGameStore((state) => state.setGameState);

  // Derived: game log + player name lookup (used by the sidebar log tab)
  const hsGameLog = useMemo(() => gameState?.game_log || [], [gameState?.game_log]);
  const playerNames = useMemo<Record<string, string>>(() => {
    const map: Record<string, string> = {};
    if (gameState) {
      for (const [id, p] of Object.entries(gameState.players)) {
        map[id] = p.name;
      }
    }
    return map;
  }, [gameState]);

  // Fetch initial state
  useEffect(() => {
    if (!matchId) return;

    if (!storeMatchId || storeMatchId !== matchId) {
      navigate('/');
      return;
    }

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

  // Concede handler
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
        <DragHintOverlay />
        <HSGameBoard
          gameState={gameState}
          playerId={playerId}
          isMyTurn={isMyTurn()}
          canPlayCard={canPlayCard}
          canAttuneCard={canAttuneCard}
          canAttack={canAttack}
          canUseHeroPower={canUseHeroPower}
          getAttackableTargets={getAttackableTargets}
          onPlayCard={playCard}
          onAttuneCard={attuneCard}
          onAttack={attack}
          onHeroPower={useHeroPower}
          onEndTurn={endTurn}
        />
      </div>

      {/* Sidebar */}
      <div className="w-64 bg-game-surface border-l border-gray-700 flex flex-col">
        {/* Connection Status */}
        <div className="p-3 border-b border-gray-700 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className={`w-2 h-2 rounded-full ${isConnected ? 'bg-green-500' : 'bg-red-500'}`} />
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

        {/* Sidebar tabs */}
        <div className="flex border-b border-gray-700">
          <button
            onClick={() => setSidebarTab('info')}
            className={`flex-1 py-2 text-xs font-bold uppercase tracking-wider transition-colors ${
              sidebarTab === 'info' ? 'text-orange-300 border-b-2 border-orange-400' : 'text-gray-500 hover:text-gray-300'
            }`}
          >
            Info
          </button>
          <button
            onClick={() => setSidebarTab('log')}
            className={`flex-1 py-2 text-xs font-bold uppercase tracking-wider transition-colors ${
              sidebarTab === 'log' ? 'text-orange-300 border-b-2 border-orange-400' : 'text-gray-500 hover:text-gray-300'
            }`}
          >
            Log
            {hsGameLog.length > 0 && (
              <span className="ml-1 text-[9px] bg-gray-700 text-gray-400 px-1 rounded">{hsGameLog.length}</span>
            )}
          </button>
        </div>

        {/* Tab content */}
        <div className="flex-1 p-4 overflow-y-auto">
          {sidebarTab === 'info' ? (
            <>
              {/* Variant info */}
              {gameState.variant && (
                <div className="mb-3 p-2 bg-purple-900/30 border border-purple-700 rounded text-purple-300 text-xs font-semibold uppercase">
                  {gameState.variant}
                </div>
              )}

              {/* Turn info */}
              <div className="mb-3">
                <div className="text-xs text-gray-400 uppercase tracking-wide mb-1">Status</div>
                <div className={`text-sm font-bold ${isMyTurn() ? 'text-green-400' : 'text-gray-500'}`}>
                  {isMyTurn() ? 'Your Turn' : "Waiting for opponent..."}
                </div>
              </div>

              {/* Mana */}
              {myPlayer && (
                <div className="mb-3">
                  <div className="text-xs text-gray-400 uppercase tracking-wide mb-1">Mana</div>
                  <div className="text-blue-300 font-bold">
                    {myPlayer.mana_crystals_available} / {myPlayer.mana_crystals}
                  </div>
                </div>
              )}

              {myPlayer?.variant_resources && gameState.variant === 'frierenrift' && (
                <div className="mb-3">
                  <div className="text-xs text-gray-400 uppercase tracking-wide mb-1">Aether Shards</div>
                  <div className="text-sm text-cyan-300 font-semibold">
                    Azure: {myPlayer.variant_resources.azure || 0}
                  </div>
                  <div className="text-sm text-orange-300 font-semibold">
                    Ember: {myPlayer.variant_resources.ember || 0}
                  </div>
                  <div className="text-sm text-emerald-300 font-semibold">
                    Verdant: {myPlayer.variant_resources.verdant || 0}
                  </div>
                  <div className="text-xs text-yellow-300 mt-1">
                    Attunes left this turn: {myPlayer.variant_resources.attunes_left || 0}
                  </div>
                </div>
              )}

              {/* Animations preference */}
              <div className="mb-3 pt-3 border-t border-gray-700">
                <AnimationsToggle />
              </div>

              {/* Error Display */}
              {error && (
                <div className="mt-4 p-3 bg-red-900/50 border border-red-500 rounded text-red-200 text-sm">
                  {error}
                </div>
              )}
            </>
          ) : (
            <HSGameLog entries={hsGameLog} playerNames={playerNames} />
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

export default HSGameView;
