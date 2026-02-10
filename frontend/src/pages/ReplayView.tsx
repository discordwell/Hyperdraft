/**
 * ReplayView Page
 *
 * Watch a completed bot-vs-bot replay (or a live game's frames so far).
 */

import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { botGameAPI } from '../services/api';
import { GameBoard } from '../components/game';
import type { ReplayFrame, ReplayResponse, GameState } from '../types';

function getSpectatorPlayerId(state: GameState | null): string {
  if (!state) return '';
  const ids = Object.keys(state.players);
  return ids.length ? ids[0] : '';
}

function summarizeFrameAction(frame: ReplayFrame | null): { title: string; reasoning?: string; model?: string; prompt?: string } {
  if (!frame || !frame.action) return { title: 'No action' };

  const a: any = frame.action;

  if (a.kind === 'action_processed') {
    const who = a.player_name || a.player_id || 'Player';
    const what = a.action_type || 'ACTION';
    const card = a.card_name ? ` ${a.card_name}` : '';
    const ai = a.data?.ai;
    const reasoning = typeof ai?.reasoning === 'string' ? ai.reasoning : undefined;
    const model = typeof ai?.model === 'string' ? ai.model : undefined;
    const prompt = typeof ai?.prompt === 'string' ? ai.prompt : undefined;
    return { title: `${who}: ${what}${card}`, reasoning, model, prompt };
  }

  if (a.kind === 'ai_choice') {
    const who = a.player_name || a.player_id || 'Player';
    return { title: `${who}: choice (${a.choice_type || 'unknown'})` };
  }

  if (typeof a.type === 'string') {
    return { title: a.type };
  }

  return { title: 'Action' };
}

function isInteresting(frame: ReplayFrame): boolean {
  const a: any = frame.action;
  return a?.kind === 'action_processed' && typeof a.action_type === 'string' && a.action_type !== 'PASS';
}

function findPrevInteresting(frames: ReplayFrame[], fromIndex: number): number | null {
  for (let i = Math.min(fromIndex - 1, frames.length - 1); i >= 0; i -= 1) {
    if (isInteresting(frames[i])) return i;
  }
  return null;
}

function findNextInteresting(frames: ReplayFrame[], fromIndex: number): number | null {
  for (let i = Math.max(0, fromIndex + 1); i < frames.length; i += 1) {
    if (isInteresting(frames[i])) return i;
  }
  return null;
}

export function ReplayView() {
  const { gameId } = useParams<{ gameId: string }>();
  const navigate = useNavigate();

  const [replay, setReplay] = useState<ReplayResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const [frameIndex, setFrameIndex] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [speedMs, setSpeedMs] = useState(300);

  // Load replay frames (up to the server cap)
  useEffect(() => {
    if (!gameId) return;

    let cancelled = false;
    setIsLoading(true);
    setError(null);

    botGameAPI.getReplay(gameId, { since: 0, limit: 5000 })
      .then((r) => {
        if (cancelled) return;
        setReplay(r);
        setFrameIndex(0);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : 'Failed to load replay');
      })
      .finally(() => {
        if (cancelled) return;
        setIsLoading(false);
      });

    return () => { cancelled = true; };
  }, [gameId]);

  const frames = replay?.frames || [];
  const clampedIndex = Math.max(0, Math.min(frameIndex, Math.max(0, frames.length - 1)));
  const currentFrame = frames.length ? frames[clampedIndex] : null;
  const currentState = (currentFrame?.state as any) || null;

  const spectatorPlayerId = useMemo(() => getSpectatorPlayerId(currentState), [currentState]);
  const actionSummary = useMemo(() => summarizeFrameAction(currentFrame), [currentFrame]);

  // Playback loop
  useEffect(() => {
    if (!isPlaying) return;
    if (!frames.length) return;

    const t = setInterval(() => {
      setFrameIndex((i) => {
        const next = i + 1;
        if (next >= frames.length) {
          // Stop at end
          return i;
        }
        return next;
      });
    }, speedMs);

    return () => clearInterval(t);
  }, [isPlaying, frames.length, speedMs]);

  // Auto-stop at end
  useEffect(() => {
    if (!isPlaying) return;
    if (frames.length && clampedIndex >= frames.length - 1) {
      setIsPlaying(false);
    }
  }, [isPlaying, clampedIndex, frames.length]);

  if (isLoading) {
    return (
      <div className="min-h-screen bg-game-bg flex items-center justify-center">
        <div className="text-center">
          <div className="w-16 h-16 border-4 border-game-accent border-t-transparent rounded-full animate-spin mx-auto mb-4" />
          <p className="text-gray-400">Loading replay...</p>
        </div>
      </div>
    );
  }

  if (error || !replay) {
    return (
      <div className="min-h-screen bg-game-bg flex items-center justify-center">
        <div className="text-center">
          <p className="text-red-400 mb-4">{error || 'Replay not found'}</p>
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
      <div className="bg-game-surface border-b border-gray-700 p-4 flex items-center justify-between gap-4">
        <div className="flex items-center gap-4 min-w-0">
          <button onClick={() => navigate(-1)} className="text-gray-400 hover:text-white">
            ← Back
          </button>
          <div className="min-w-0">
            <h1 className="text-xl font-bold text-white truncate">Replay</h1>
            <p className="text-xs text-gray-400 truncate">
              {actionSummary.title}{actionSummary.model ? ` • ${actionSummary.model}` : ''}
            </p>
          </div>
        </div>

        {/* Controls */}
        <div className="flex items-center gap-3">
          <button
            onClick={() => {
              const i = findPrevInteresting(frames, clampedIndex);
              if (i !== null) setFrameIndex(i);
            }}
            className="px-2 py-1 bg-gray-800 text-white rounded hover:bg-gray-700 border border-gray-700"
            disabled={findPrevInteresting(frames, clampedIndex) === null}
            title="Previous non-PASS action"
          >
            ⏮
          </button>
          <button
            onClick={() => setFrameIndex((i) => Math.max(0, i - 1))}
            className="px-2 py-1 bg-gray-700 text-white rounded hover:bg-gray-600"
            disabled={clampedIndex <= 0}
          >
            ◀
          </button>
          <button
            onClick={() => setIsPlaying((p) => !p)}
            className={`px-3 py-1 rounded ${isPlaying ? 'bg-yellow-600 hover:bg-yellow-500' : 'bg-green-600 hover:bg-green-500'} text-white`}
            disabled={!frames.length}
          >
            {isPlaying ? '⏸ Pause' : '▶ Play'}
          </button>
          <button
            onClick={() => setFrameIndex((i) => Math.min(frames.length - 1, i + 1))}
            className="px-2 py-1 bg-gray-700 text-white rounded hover:bg-gray-600"
            disabled={clampedIndex >= frames.length - 1}
          >
            ▶
          </button>
          <button
            onClick={() => {
              const i = findNextInteresting(frames, clampedIndex);
              if (i !== null) setFrameIndex(i);
            }}
            className="px-2 py-1 bg-gray-800 text-white rounded hover:bg-gray-700 border border-gray-700"
            disabled={findNextInteresting(frames, clampedIndex) === null}
            title="Next non-PASS action"
          >
            ⏭
          </button>

          <div className="text-gray-400 text-sm tabular-nums">
            {frames.length ? `${clampedIndex + 1}/${frames.length}` : '0/0'}
          </div>

          <select
            value={speedMs}
            onChange={(e) => setSpeedMs(parseInt(e.target.value, 10))}
            className="px-2 py-1 bg-gray-800 border border-gray-600 rounded text-white text-sm"
          >
            <option value={800}>0.5x</option>
            <option value={300}>1x</option>
            <option value={150}>2x</option>
            <option value={80}>4x</option>
          </select>
        </div>
      </div>

      {/* Scrubber */}
      <div className="bg-game-surface border-b border-gray-700 p-3 flex items-center gap-3">
        <input
          type="range"
          min={0}
          max={Math.max(0, frames.length - 1)}
          value={clampedIndex}
          onChange={(e) => setFrameIndex(parseInt(e.target.value, 10))}
          className="flex-1"
        />
        <div className="text-xs text-gray-400">
          Turn {currentFrame?.turn ?? 0} • {currentFrame?.phase ?? ''}/{currentFrame?.step ?? ''}
        </div>
      </div>

      {/* Body */}
      <div className="flex-1 grid grid-cols-1 lg:grid-cols-[1fr_420px]">
        <div className="relative">
          {currentState && spectatorPlayerId ? (
            <GameBoard gameState={currentState} playerId={spectatorPlayerId} />
          ) : (
            <div className="flex items-center justify-center h-full">
              <p className="text-gray-500">No game state available</p>
            </div>
          )}
        </div>

        <div className="border-l border-gray-700 bg-game-surface p-4 overflow-auto">
          <h2 className="text-white font-bold mb-2">Decision</h2>
          <div className="text-gray-300 text-sm mb-3">{actionSummary.title}</div>
          {actionSummary.reasoning && (
            <div className="mb-4">
              <div className="text-xs text-gray-400 mb-1">Reasoning</div>
              <div className="text-sm text-gray-200 whitespace-pre-wrap">{actionSummary.reasoning}</div>
            </div>
          )}
          {actionSummary.prompt && (
            <div>
              <div className="text-xs text-gray-400 mb-1">Prompt (record_prompts=true)</div>
              <pre className="text-xs text-gray-300 whitespace-pre-wrap bg-gray-900/60 border border-gray-700 rounded p-2 max-h-[40vh] overflow-auto">
                {actionSummary.prompt}
              </pre>
            </div>
          )}

          <div className="mt-6">
            <h3 className="text-white font-bold mb-2">Frames</h3>
            <div className="text-xs text-gray-400 mb-2">Click to jump</div>
            <div className="space-y-1">
              {frames.slice(Math.max(0, clampedIndex - 30), Math.min(frames.length, clampedIndex + 31)).map((f, offset) => {
                const i = Math.max(0, clampedIndex - 30) + offset;
                const s = summarizeFrameAction(f);
                const isActive = i === clampedIndex;
                return (
                  <button
                    key={i}
                    onClick={() => setFrameIndex(i)}
                    className={`w-full text-left px-2 py-1 rounded border ${
                      isActive
                        ? 'bg-gray-800 border-game-accent text-white'
                        : 'bg-gray-900/30 border-gray-700 text-gray-300 hover:bg-gray-800/60'
                    }`}
                  >
                    <div className="text-xs truncate">
                      <span className="text-gray-500 mr-2">#{i + 1}</span>
                      {s.title}
                    </div>
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default ReplayView;
