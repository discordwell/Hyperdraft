/**
 * SpectatorView Page
 *
 * Watch bot vs bot games.
 */

import { useEffect, useState, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { botGameAPI } from '../services/api';
import { GameBoard } from '../components/game';
import type { GameState, BotGameStatus } from '../types';

export function SpectatorView() {
  const { gameId } = useParams<{ gameId: string }>();
  const navigate = useNavigate();

  const [gameState, setGameState] = useState<GameState | null>(null);
  const [status, setStatus] = useState<BotGameStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isPaused, setIsPaused] = useState(false);
  const [pollInterval, setPollInterval] = useState(1500);

  // Fetch game state
  const fetchState = useCallback(async () => {
    if (!gameId || isPaused) return;

    try {
      const [stateResponse, statusResponse] = await Promise.all([
        botGameAPI.getState(gameId),
        botGameAPI.getStatus(gameId),
      ]);

      setGameState(stateResponse);
      setStatus(statusResponse);
      setError(null);
    } catch (err) {
      // If game not found, it might have ended
      if (err instanceof Error && err.message.includes('not found')) {
        try {
          const statusResponse = await botGameAPI.getStatus(gameId);
          setStatus(statusResponse);
        } catch {
          setError('Game not found');
        }
      } else {
        setError(err instanceof Error ? err.message : 'Failed to fetch game state');
      }
    } finally {
      setIsLoading(false);
    }
  }, [gameId, isPaused]);

  // Initial fetch
  useEffect(() => {
    fetchState();
  }, [fetchState]);

  // Poll for updates
  useEffect(() => {
    if (!gameId || status?.status === 'finished' || isPaused) return;

    const interval = setInterval(fetchState, pollInterval);
    return () => clearInterval(interval);
  }, [gameId, status?.status, isPaused, pollInterval, fetchState]);

  // Handle speed change
  const handleSpeedChange = (speed: number) => {
    setPollInterval(speed);
  };

  // Get a dummy player ID for the board (we're just spectating)
  const spectatorPlayerId = gameState
    ? Object.keys(gameState.players)[0]
    : '';

  // Loading state
  if (isLoading) {
    return (
      <div className="min-h-screen bg-game-bg flex items-center justify-center">
        <div className="text-center">
          <div className="w-16 h-16 border-4 border-game-accent border-t-transparent rounded-full animate-spin mx-auto mb-4" />
          <p className="text-gray-400">Loading game...</p>
        </div>
      </div>
    );
  }

  // Error state
  if (error && !gameState) {
    return (
      <div className="min-h-screen bg-game-bg flex items-center justify-center">
        <div className="text-center">
          <p className="text-red-400 mb-4">{error}</p>
          <button
            onClick={() => navigate('/')}
            className="px-4 py-2 bg-game-accent text-white rounded hover:bg-red-500"
          >
            Back to Menu
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-game-bg flex flex-col">
      {/* Header */}
      <div className="bg-game-surface border-b border-gray-700 p-4 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <button
            onClick={() => navigate('/')}
            className="text-gray-400 hover:text-white"
          >
            ← Back
          </button>
          <h1 className="text-xl font-bold text-white">Bot vs Bot Game</h1>
          {status && (
            <span
              className={`px-2 py-1 rounded text-sm ${
                status.status === 'running'
                  ? 'bg-green-600 text-white'
                  : 'bg-gray-600 text-gray-200'
              }`}
            >
              {status.status === 'running' ? 'Live' : 'Finished'}
            </span>
          )}
        </div>

        {/* Controls */}
        <div className="flex items-center gap-4">
          {/* Speed Control */}
          <div className="flex items-center gap-2">
            <span className="text-sm text-gray-400">Speed:</span>
            <div className="flex gap-1">
              {[
                { label: '0.5x', value: 3000 },
                { label: '1x', value: 1500 },
                { label: '2x', value: 750 },
                { label: '4x', value: 375 },
              ].map(({ label, value }) => (
                <button
                  key={value}
                  onClick={() => handleSpeedChange(value)}
                  className={`px-2 py-1 text-xs rounded ${
                    pollInterval === value
                      ? 'bg-game-accent text-white'
                      : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          {/* Pause/Play */}
          <button
            onClick={() => setIsPaused(!isPaused)}
            className={`px-3 py-1 rounded ${
              isPaused
                ? 'bg-green-600 text-white hover:bg-green-500'
                : 'bg-yellow-600 text-white hover:bg-yellow-500'
            }`}
          >
            {isPaused ? '▶ Play' : '⏸ Pause'}
          </button>

          {/* Turn Counter */}
          {status && (
            <div className="text-gray-400">
              Turn: <span className="text-white font-bold">{status.turn}</span>
            </div>
          )}
        </div>
      </div>

      {/* Game Board */}
      <div className="flex-1 relative">
        {gameState ? (
          <GameBoard
            gameState={gameState}
            playerId={spectatorPlayerId}
            // No interaction for spectators
          />
        ) : (
          <div className="flex items-center justify-center h-full">
            <p className="text-gray-500">No game state available</p>
          </div>
        )}

        {/* Game Over Overlay */}
        {status?.status === 'finished' && (
          <div className="absolute inset-0 bg-black/80 flex items-center justify-center z-50">
            <div className="text-center">
              <h2 className="text-4xl font-bold text-white mb-4">Game Over</h2>
              <p className="text-gray-300 text-lg mb-2">
                {status.winner
                  ? `Winner: ${gameState?.players[status.winner]?.name || status.winner}`
                  : 'Draw'}
              </p>
              <p className="text-gray-400 mb-6">
                Total turns: {status.turn}
              </p>
              <div className="flex gap-4 justify-center">
                <button
                  onClick={() => navigate('/')}
                  className="px-6 py-3 bg-game-accent text-white rounded-lg font-bold hover:bg-red-500"
                >
                  Back to Menu
                </button>
                <button
                  onClick={async () => {
                    // Start a new bot game
                    try {
                      const response = await botGameAPI.start({
                        delay_ms: pollInterval,
                      });
                      navigate(`/spectate/${response.game_id}`);
                    } catch (err) {
                      setError(err instanceof Error ? err.message : 'Failed to start new game');
                    }
                  }}
                  className="px-6 py-3 bg-gray-700 text-white rounded-lg font-bold hover:bg-gray-600"
                >
                  Watch Another
                </button>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Error Display */}
      {error && (
        <div className="fixed bottom-4 right-4 p-3 bg-red-900/90 border border-red-500 rounded text-red-200">
          {error}
        </div>
      )}
    </div>
  );
}

export default SpectatorView;
