/**
 * PKMGameView Page
 *
 * Dedicated game view for Pokemon TCG engine games.
 * Uses the usePokemonGame hook for Pokemon-specific action types.
 */

import { useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { usePokemonGame } from '../hooks/usePokemonGame';
import { useGameStore } from '../stores/gameStore';
import { PKMGameBoard } from '../components/game/PKMGameBoard';
import { matchAPI } from '../services/api';

export function PKMGameView() {
  const { matchId } = useParams<{ matchId: string }>();
  const navigate = useNavigate();

  const {
    gameState,
    playerId,
    isConnected,
    myPlayer,
    opponentPlayer,
    isMyTurn,
    myActivePokemon,
    opponentActivePokemon,
    myBench,
    opponentBench,
    stadiumCard,
    canPlayCard,
    canAttachEnergy,
    playCard,
    attachEnergy,
    attack,
    retreat,
    evolve,
    useAbility,
    endTurn,
    setError,
    error,
  } = usePokemonGame();

  const storeMatchId = useGameStore((state) => state.matchId);
  const storePlayerId = useGameStore((state) => state.playerId);
  const setGameState = useGameStore((state) => state.setGameState);

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
      <div className="min-h-screen bg-emerald-950 flex items-center justify-center">
        <div className="text-center">
          <div className="w-16 h-16 border-4 border-yellow-500 border-t-transparent rounded-full animate-spin mx-auto mb-4" />
          <p className="text-gray-400">Loading Pokemon game...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-emerald-950 flex">
      {/* Main Game Area */}
      <div className="flex-1 relative">
        <PKMGameBoard
          gameState={gameState}
          playerId={playerId}
          isMyTurn={isMyTurn()}
          myPlayer={myPlayer}
          opponentPlayer={opponentPlayer}
          myActivePokemon={myActivePokemon}
          opponentActivePokemon={opponentActivePokemon}
          myBench={myBench}
          opponentBench={opponentBench}
          stadiumCard={stadiumCard}
          hand={gameState.hand || []}
          canPlayCard={canPlayCard}
          canAttachEnergy={canAttachEnergy}
          onPlayCard={playCard}
          onAttachEnergy={attachEnergy}
          onAttack={attack}
          onRetreat={retreat}
          onEvolve={evolve}
          onUseAbility={useAbility}
          onEndTurn={endTurn}
        />
      </div>

      {/* Sidebar */}
      <div className="w-64 bg-gray-900 border-l border-green-800 flex flex-col">
        {/* Connection Status */}
        <div className="p-3 border-b border-green-800 flex items-center justify-between">
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

        {/* Game info */}
        <div className="flex-1 p-4 overflow-y-auto">
          {/* Turn info */}
          <div className="mb-3">
            <div className="text-xs text-gray-400 uppercase tracking-wide mb-1">Status</div>
            <div className={`text-sm font-bold ${isMyTurn() ? 'text-yellow-400' : 'text-gray-500'}`}>
              {isMyTurn() ? 'Your Turn' : "Waiting for opponent..."}
            </div>
          </div>

          {/* Per-turn status */}
          {myPlayer && (
            <div className="mb-3 space-y-1">
              <div className="text-xs text-gray-400 uppercase tracking-wide mb-1">Turn Actions</div>
              <div className={`text-xs ${myPlayer.energy_attached_this_turn ? 'text-gray-500 line-through' : 'text-green-400'}`}>
                Energy Attachment {myPlayer.energy_attached_this_turn ? '(used)' : '(available)'}
              </div>
              <div className={`text-xs ${myPlayer.supporter_played_this_turn ? 'text-gray-500 line-through' : 'text-green-400'}`}>
                Supporter {myPlayer.supporter_played_this_turn ? '(played)' : '(available)'}
              </div>
            </div>
          )}

          {/* Active Pokemon info */}
          {myActivePokemon && (
            <div className="mb-3">
              <div className="text-xs text-gray-400 uppercase tracking-wide mb-1">Active Pokemon</div>
              <div className="text-sm text-white font-bold">{myActivePokemon.name}</div>
              <div className="text-xs text-gray-400">
                HP: {Math.max(0, (myActivePokemon.hp || 0) - (myActivePokemon.damage_counters || 0) * 10)} / {myActivePokemon.hp}
              </div>
              {(myActivePokemon.attached_energy?.length || 0) > 0 && (
                <div className="text-xs text-gray-400 mt-0.5">
                  Energy: {myActivePokemon.attached_energy?.length || 0}
                </div>
              )}
            </div>
          )}

          {/* Discard pile */}
          <div className="mb-3">
            <div className="text-xs text-gray-400 uppercase tracking-wide mb-1">Discard Pile</div>
            <div className="text-xs text-gray-500">
              {(gameState.graveyard?.[playerId]?.length || 0)} cards
            </div>
          </div>

          {/* Error Display */}
          {error && (
            <div className="mt-4 p-3 bg-red-900/50 border border-red-500 rounded text-red-200 text-sm">
              {error}
            </div>
          )}
        </div>

        {/* Back to Menu */}
        <div className="p-3 border-t border-green-800">
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

export default PKMGameView;
