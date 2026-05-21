/**
 * SpectatorView Page
 *
 * Watch bot vs bot games.
 *
 * Phase C4: outer chrome (header strip, loading/error states, last-decision
 * banner, match-complete overlay, error toast) is ported to lab posture
 * (paper / ink / sodium per HD-PAL-01). The embedded game render — the
 * `<GameBoard>` inside the `flex-1` container — is byte-identical to the
 * pre-port version. Per `docs/design/brand.md` "On the laboratory
 * archetype": when you're watching a Hearthstone match, the board still
 * looks like Hearthstone. The seam between lab and game lives at the
 * `<header>` / `<main>` boundary below.
 */

import { useEffect, useMemo, useState, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { botGameAPI } from '../services/api';
import { GameBoard } from '../components/game';
import { shortCode } from './PublicMatch';
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

  const code = useMemo(() => shortCode(gameId), [gameId]);

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

  // ─── Mode badge: surface engine/game_mode when available ────────────
  // Backend doesn't always populate this consistently; if missing, the
  // chip reads "match" — mirrors PublicMatch's same fallback.
  const modeLabel = useMemo(() => {
    const fromStatus = (status as unknown as { game_mode?: string; mode?: string } | null);
    return (
      fromStatus?.game_mode ||
      fromStatus?.mode ||
      'match'
    );
  }, [status]);

  // ─── Inline keyframe for the acid pulse — same name as PublicMatch
  // would collide on a parent route that mounts both; scope it by giving
  // the spectator pulse its own animation name. ────────────────────────
  const acidKeyframes = (
    <style>{`
      @keyframes spectator-acid-pulse {
        0%, 100% {
          box-shadow: 0 0 0 0 rgba(163, 230, 53, 0.55),
                      0 0 10px rgba(163, 230, 53, 0.65);
        }
        50% {
          box-shadow: 0 0 0 6px rgba(163, 230, 53, 0),
                      0 0 14px rgba(163, 230, 53, 0.85);
        }
      }
    `}</style>
  );

  // Loading state — lab posture: paper backdrop, mono "connecting" eyebrow.
  if (isLoading) {
    return (
      <div className="min-h-screen bg-brand-ink flex items-center justify-center">
        {acidKeyframes}
        <div className="text-center">
          <div className="w-12 h-12 border-2 border-brand-hairline border-t-brand-foil rounded-full animate-spin mx-auto mb-4" />
          <p className="brand-eyebrow text-brand-chalk">Spectating · connecting…</p>
        </div>
      </div>
    );
  }

  // Error state — lab posture.
  if (error && !gameState) {
    return (
      <div className="min-h-screen bg-brand-ink flex items-center justify-center">
        {acidKeyframes}
        <div className="text-center brand-frame px-10 py-8">
          <p className="brand-eyebrow text-brand-ember mb-2">Spectating · failed</p>
          <p className="text-brand-cream mb-6">{error}</p>
          <button
            onClick={() => navigate('/')}
            className="px-4 py-2 border border-brand-hairline hover:border-brand-foil/70 bg-brand-obsidian hover:bg-brand-shelf transition-colors brand-mono text-xs tracking-tight text-brand-cream"
          >
            Back to lobby
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-brand-ink text-brand-cream flex flex-col">
      {acidKeyframes}

      {/* === Lab masthead — outer chrome ================================ */}
      <header className="border-b border-brand-hairline/60 bg-brand-obsidian/85 backdrop-blur-xl sticky top-0 z-30">
        <div className="max-w-[1600px] mx-auto px-4 lg:px-8 py-3 flex flex-wrap items-center gap-x-6 gap-y-3">
          {/* HYPERDRAFT wordmark + match short-code */}
          <div className="flex items-baseline gap-3">
            <button
              onClick={() => navigate('/')}
              className="brand-eyebrow text-brand-dust hover:text-brand-foil transition-colors"
              aria-label="Back to lobby"
            >
              ← hyperdraft
            </button>
            <span
              className="brand-mono text-base lg:text-lg tracking-tight text-brand-cream"
              data-testid="spectator-shortcode"
              aria-label="Match short code"
            >
              {code}
            </span>
          </div>

          {/* Mode badge — placeholder chip reading "match" when backend
              hasn't surfaced the engine yet. Lab posture: ink-outlined,
              paper background, mono uppercase. */}
          <span
            className="px-2 py-0.5 border border-brand-hairline bg-brand-shelf brand-mono text-[11px] tracking-wider uppercase text-brand-chalk"
            data-testid="spectator-mode-badge"
          >
            {modeLabel}
          </span>

          {/* Spectating indicator — acid pulse dot. Goes quiet (no animation
              colour) when the match is finished. */}
          <div className="flex items-center gap-2" aria-live="polite">
            <span
              aria-hidden
              className="inline-block w-2 h-2 rounded-full"
              style={
                status?.status === 'finished'
                  ? {
                      background: 'var(--brand-hairline)',
                      boxShadow: 'none',
                    }
                  : {
                      background: 'var(--brand-spore, #a3e635)',
                      boxShadow:
                        '0 0 0 0 rgba(163, 230, 53, 0.55), 0 0 10px rgba(163, 230, 53, 0.65)',
                      animation: 'spectator-acid-pulse 1.8s ease-in-out infinite',
                    }
              }
            />
            <span className="brand-eyebrow text-brand-chalk">
              {status?.status === 'finished' ? 'Match complete' : 'Spectating'}
            </span>
          </div>

          {/* Right cluster — turn counter, speed picker, pause toggle. All
              monospaced, ink-outlined, no foil gradients. */}
          <div className="ml-auto flex items-center gap-4">
            {status && (
              <div className="brand-mono text-xs text-brand-chalk">
                <span className="brand-eyebrow text-brand-dust mr-1.5">turn</span>
                <span className="text-brand-cream">{status.turn}</span>
              </div>
            )}

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
                      'px-2 py-1 text-[11px] brand-mono transition-colors ' +
                      (pollInterval === value
                        ? 'bg-brand-shelf text-brand-foil border border-brand-foil/70'
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
                'px-3 py-1 border brand-mono text-xs transition-colors ' +
                (isPaused
                  ? 'border-brand-foil/70 bg-brand-shelf text-brand-foil hover:border-brand-foil'
                  : 'border-brand-hairline bg-brand-obsidian text-brand-cream hover:border-brand-foil/40')
              }
            >
              {isPaused ? '▶ Play' : '⏸ Pause'}
            </button>

            <button
              type="button"
              onClick={() => navigate('/')}
              className="px-3 py-1.5 border border-brand-hairline hover:border-brand-foil/70 bg-brand-obsidian hover:bg-brand-shelf transition-colors brand-mono text-xs tracking-tight text-brand-cream"
              aria-label="Back to lobby"
            >
              Back to lobby
            </button>
          </div>
        </div>
      </header>

      {/* Last-decision banner — wrapper chrome (spectator commentary,
          not the game's own UI). Lab posture: hairline rule, paper bg,
          mono caption + sodium emphasis for the player name. */}
      {lastDecision && (
        <div className="bg-brand-obsidian/60 border-b border-brand-hairline/60 px-4 py-2 brand-mono text-xs text-brand-parchment">
          <span className="brand-eyebrow text-brand-dust mr-2">Last</span>
          <span className="text-brand-foil">{String(lastAction?.player_name || lastAction?.player_id || '')}</span>{' '}
          <span className="text-brand-cream">{String(lastAction?.action_type ?? '')}{lastAction?.card_name ? ` ${String(lastAction.card_name)}` : ''}</span>
          {typeof lastAi?.reasoning === 'string' && lastAi.reasoning.trim() && (
            <span className="text-brand-chalk"> · {lastAi.reasoning}</span>
          )}
          {typeof lastAi?.model === 'string' && (
            <span className="text-brand-dust"> ({lastAi.model})</span>
          )}
        </div>
      )}

      {/* === Game body — embedded game render. UNTOUCHED per Phase C4
          spec: "when you're watching a Hearthstone match, the board still
          LOOKS like Hearthstone". The seam is the boundary above this
          block. ====================================================== */}
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

        {/* Match-complete overlay — wrapper chrome (sits on top of the
            game board after the match ends, so it belongs to the lab
            wrapper, not the game's own identity). Lab posture: hairline
            plate, serif heading, mono telemetry, ink-outlined buttons. */}
        {status?.status === 'finished' && (
          <div className="absolute inset-0 bg-brand-ink/85 backdrop-blur-sm flex items-center justify-center z-50">
            <div className="text-center brand-frame px-12 py-10">
              <p className="brand-eyebrow text-brand-foil mb-2">Match complete</p>
              <h2 className="text-4xl font-display font-semibold text-brand-cream mb-3">Game over</h2>
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
                  className="px-5 py-2.5 border border-brand-hairline hover:border-brand-foil/70 bg-brand-obsidian hover:bg-brand-shelf transition-colors brand-mono text-xs tracking-tight text-brand-cream"
                >
                  Back to lobby
                </button>
                <button
                  onClick={() => {
                    if (gameId) navigate(`/replay/${gameId}`);
                  }}
                  className="px-5 py-2.5 border border-brand-hairline hover:border-brand-foil/70 bg-brand-obsidian hover:bg-brand-shelf transition-colors brand-mono text-xs tracking-tight text-brand-cream"
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
                  className="px-5 py-2.5 border border-brand-hairline hover:border-brand-foil/70 bg-brand-obsidian hover:bg-brand-shelf transition-colors brand-mono text-xs tracking-tight text-brand-cream"
                >
                  Watch another
                </button>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Error toast — wrapper chrome, lab posture (halt accent on hairline). */}
      {error && (
        <div className="fixed bottom-4 right-4 px-3 py-2 bg-brand-shelf border border-brand-ember/60 brand-mono text-xs text-brand-ember">
          {error}
        </div>
      )}
    </div>
  );
}

export default SpectatorView;
