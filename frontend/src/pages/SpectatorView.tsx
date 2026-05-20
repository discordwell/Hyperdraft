/**
 * SpectatorView Page
 *
 * Watch bot vs bot games.
 */

import { useEffect, useState, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { botGameAPI } from '../services/api';
import { GameBoard } from '../components/game';
import type { GameState, BotGameStatus, ReplayFrame } from '../types';

export function SpectatorView() {
  const { gameId } = useParams<{ gameId: string }>();
  const navigate = useNavigate();

  const [gameState, setGameState] = useState<GameState | null>(null);
  const [status, setStatus] = useState<BotGameStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isPaused, setIsPaused] = useState(false);
  const [pollInterval, setPollInterval] = useState(1500);
  const [replayCursor, setReplayCursor] = useState(0);
  const [recentFrames, setRecentFrames] = useState<ReplayFrame[]>([]);

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

  const fetchReplayFrames = useCallback(async () => {
    if (!gameId || isPaused) return;

    try {
      const replay = await botGameAPI.getReplay(gameId, { since: replayCursor, limit: 200 });
      if (replay.frames && replay.frames.length) {
        setRecentFrames((prev) => [...prev, ...replay.frames].slice(-80));
        setReplayCursor((c) => c + replay.frames.length);
      }
    } catch {
      // Non-fatal; replay frames may not be ready early in match.
    }
  }, [gameId, isPaused, replayCursor]);

  // Reset replay cursor when navigating to a new game
  useEffect(() => {
    if (!gameId) return;
    setReplayCursor(0);
    setRecentFrames([]);
  }, [gameId]);

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

  // Poll for replay frames (reasoning / action log)
  useEffect(() => {
    if (!gameId || isPaused) return;
    const interval = setInterval(fetchReplayFrames, pollInterval);
    return () => clearInterval(interval);
  }, [gameId, isPaused, pollInterval, fetchReplayFrames]);

  const lastDecision = [...recentFrames].reverse().find(
    (f) => (f.action as Record<string, unknown> | null)?.kind === 'action_processed',
  );
  const lastAction = lastDecision?.action as Record<string, unknown> | undefined;
  const lastAiRaw = lastAction?.data as Record<string, unknown> | undefined;
  const lastAi = lastAiRaw?.ai as Record<string, unknown> | undefined;

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
      <div className="min-h-screen bg-brand-ink flex items-center justify-center">
        <div className="text-center">
          <div className="w-16 h-16 border-4 border-brand-sheen border-t-transparent rounded-full animate-spin mx-auto mb-4" />
          <p className="brand-eyebrow text-brand-chalk">Loading match</p>
        </div>
      </div>
    );
  }

  // Error state
  if (error && !gameState) {
    return (
      <div className="min-h-screen bg-brand-ink flex items-center justify-center">
        <div className="text-center">
          <p className="text-brand-ember mb-4">{error}</p>
          <button
            onClick={() => navigate('/')}
            className="px-4 py-2 bg-gradient-to-b from-brand-foil-bright via-brand-foil to-brand-foil-deep text-brand-ink shadow-brand-foil"
          >
            Back to lobby
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-brand-ink text-brand-cream flex flex-col">
      <div className="bg-brand-obsidian/85 backdrop-blur-xl border-b border-brand-hairline/60 p-4 flex items-center justify-between sticky top-0 z-30">
        <div className="flex items-center gap-4">
          <button
            onClick={() => navigate('/')}
            className="text-brand-chalk hover:text-brand-foil transition-colors text-sm tracking-wide"
          >
            ← Lobby
          </button>
          <p className="brand-eyebrow text-brand-sheen">Spectator</p>
          <h1 className="text-lg font-display font-semibold text-brand-cream">Bot vs Bot</h1>
          {status && (
            <span
              className={
                'px-2 py-0.5 border text-[11px] tracking-wider uppercase ' +
                (status.status === 'running'
                  ? 'border-brand-sheen/60 bg-brand-sheen/10 text-brand-sheen'
                  : 'border-brand-hairline bg-brand-shelf text-brand-chalk')
              }
            >
              {status.status === 'running' ? '● Live' : 'Finished'}
            </span>
          )}
        </div>

        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <span className="brand-eyebrow text-brand-dust">Speed</span>
            <div className="flex gap-1">
              {[
                { label: '0.5×', value: 3000 },
                { label: '1×', value: 1500 },
                { label: '2×', value: 750 },
                { label: '4×', value: 375 },
              ].map(({ label, value }) => (
                <button
                  key={value}
                  onClick={() => handleSpeedChange(value)}
                  className={
                    'px-2 py-1 text-[11px] brand-mono transition-all ' +
                    (pollInterval === value
                      ? 'bg-brand-foil/15 text-brand-foil border border-brand-foil/60'
                      : 'bg-brand-obsidian text-brand-chalk border border-brand-hairline hover:border-brand-foil/40')
                  }
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          <button
            onClick={() => setIsPaused(!isPaused)}
            className={
              'px-3 py-1 border text-sm transition-colors ' +
              (isPaused
                ? 'border-brand-sheen/60 bg-brand-sheen/10 text-brand-sheen hover:bg-brand-sheen/20'
                : 'border-brand-foil/60 bg-brand-foil/10 text-brand-foil hover:bg-brand-foil/20')
            }
          >
            {isPaused ? '▶ Play' : '⏸ Pause'}
          </button>

          {status && (
            <div className="brand-mono text-xs text-brand-chalk">
              <span className="brand-eyebrow text-brand-dust mr-1.5">turn</span>
              <span className="text-brand-cream">{status.turn}</span>
            </div>
          )}
        </div>
      </div>

      {lastDecision && (
        <div className="bg-brand-obsidian/60 border-b border-brand-hairline/60 px-4 py-2 text-xs text-brand-parchment">
          <span className="brand-eyebrow text-brand-dust mr-2">Last</span>
          <span className="font-semibold text-brand-cream">{String(lastAction?.player_name || lastAction?.player_id || '')}</span>{' '}
          <span className="text-brand-chalk">{String(lastAction?.action_type ?? '')}{lastAction?.card_name ? ` ${String(lastAction.card_name)}` : ''}</span>
          {typeof lastAi?.reasoning === 'string' && lastAi.reasoning.trim() && (
            <span className="text-brand-dust"> · {lastAi.reasoning}</span>
          )}
          {typeof lastAi?.model === 'string' && (
            <span className="brand-mono text-brand-dust"> ({lastAi.model})</span>
          )}
        </div>
      )}

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

        {status?.status === 'finished' && (
          <div className="absolute inset-0 bg-brand-ink/85 backdrop-blur-sm flex items-center justify-center z-50">
            <div className="text-center brand-frame px-12 py-10">
              <p className="brand-eyebrow text-brand-foil mb-2">Match complete</p>
              <h2 className="text-4xl font-display font-bold text-brand-cream mb-3">Game over</h2>
              <p className="text-brand-parchment text-lg mb-1">
                {status.winner
                  ? `Winner: ${gameState?.players[status.winner]?.name || status.winner}`
                  : 'Draw'}
              </p>
              <p className="brand-mono text-sm text-brand-chalk mb-6">
                total turns: {status.turn}
              </p>
              <div className="flex gap-3 justify-center">
                <button
                  onClick={() => navigate('/')}
                  className="px-6 py-3 bg-gradient-to-b from-brand-foil-bright via-brand-foil to-brand-foil-deep text-brand-ink shadow-brand-foil hover:shadow-brand-foil-strong transition-all font-medium"
                >
                  Lobby
                </button>
                <button
                  onClick={() => {
                    if (gameId) navigate(`/replay/${gameId}`);
                  }}
                  className="px-6 py-3 bg-brand-shelf hover:bg-brand-glass border border-brand-hairline hover:border-brand-foil/40 text-brand-cream transition-colors"
                >
                  Replay
                </button>
                <button
                  onClick={async () => {
                    try {
                      const response = await botGameAPI.start({ delay_ms: pollInterval });
                      navigate(`/spectate/${response.game_id}`);
                    } catch (err) {
                      setError(err instanceof Error ? err.message : 'Failed to start new game');
                    }
                  }}
                  className="px-6 py-3 bg-brand-shelf hover:bg-brand-glass border border-brand-hairline hover:border-brand-sheen/40 text-brand-cream transition-colors"
                >
                  Watch another
                </button>
              </div>
            </div>
          </div>
        )}
      </div>

      {error && (
        <div className="fixed bottom-4 right-4 p-3 bg-brand-ember/10 border border-brand-ember/50 text-brand-ember text-sm">
          {error}
        </div>
      )}
    </div>
  );
}

export default SpectatorView;
