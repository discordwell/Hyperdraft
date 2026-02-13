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

type ReplayMode = 'action' | 'phase';

interface PhaseSlice {
  start: number;
  end: number;
  turn: number;
  phase: string;
  step: string;
}

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

function buildPhaseSlices(frames: ReplayFrame[]): PhaseSlice[] {
  const slices: PhaseSlice[] = [];

  for (let i = 0; i < frames.length; i += 1) {
    const frame = frames[i];
    const prev = slices[slices.length - 1];

    if (!prev || prev.turn !== frame.turn || prev.phase !== frame.phase || prev.step !== frame.step) {
      slices.push({
        start: i,
        end: i,
        turn: frame.turn,
        phase: frame.phase,
        step: frame.step,
      });
      continue;
    }

    prev.end = i;
  }

  return slices;
}

function countInterestingInSlice(frames: ReplayFrame[], slice: PhaseSlice): number {
  let count = 0;
  for (let i = slice.start; i <= slice.end; i += 1) {
    if (isInteresting(frames[i])) count += 1;
  }
  return count;
}

function findPrevTurnSlice(slices: PhaseSlice[], currentPhaseIndex: number): number | null {
  if (currentPhaseIndex <= 0) return null;

  const currentTurn = slices[currentPhaseIndex].turn;
  for (let i = currentPhaseIndex - 1; i >= 0; i -= 1) {
    if (slices[i].turn < currentTurn) {
      const turn = slices[i].turn;
      let firstForTurn = i;
      while (firstForTurn > 0 && slices[firstForTurn - 1].turn === turn) {
        firstForTurn -= 1;
      }
      return firstForTurn;
    }
  }

  return null;
}

function findNextTurnSlice(slices: PhaseSlice[], currentPhaseIndex: number): number | null {
  if (currentPhaseIndex >= slices.length - 1) return null;

  const currentTurn = slices[currentPhaseIndex].turn;
  for (let i = currentPhaseIndex + 1; i < slices.length; i += 1) {
    if (slices[i].turn > currentTurn) {
      return i;
    }
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
  const [viewMode, setViewMode] = useState<ReplayMode>('phase');

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
  const phaseSlices = useMemo(() => buildPhaseSlices(frames), [frames]);

  const phaseIndexByFrame = useMemo(() => {
    const indexMap: number[] = Array(frames.length).fill(0);
    phaseSlices.forEach((slice, phaseIndex) => {
      for (let i = slice.start; i <= slice.end; i += 1) {
        indexMap[i] = phaseIndex;
      }
    });
    return indexMap;
  }, [frames.length, phaseSlices]);

  const clampedIndex = Math.max(0, Math.min(frameIndex, Math.max(0, frames.length - 1)));
  const currentFrame = frames.length ? frames[clampedIndex] : null;
  const currentState = (currentFrame?.state as any) || null;

  const currentPhaseIndex = frames.length ? phaseIndexByFrame[clampedIndex] || 0 : 0;
  const currentPhaseSlice = phaseSlices[currentPhaseIndex] || null;

  const visibleIndex = viewMode === 'phase' ? currentPhaseIndex : clampedIndex;
  const visibleTotal = viewMode === 'phase' ? phaseSlices.length : frames.length;

  const spectatorPlayerId = useMemo(() => getSpectatorPlayerId(currentState), [currentState]);

  const phaseRepresentativeFrame = useMemo(() => {
    if (!currentPhaseSlice) return currentFrame;

    for (let i = currentPhaseSlice.end; i >= currentPhaseSlice.start; i -= 1) {
      if (isInteresting(frames[i])) return frames[i];
    }

    return frames[currentPhaseSlice.end] || currentFrame;
  }, [currentFrame, currentPhaseSlice, frames]);

  const actionSummary = useMemo(
    () => summarizeFrameAction(viewMode === 'phase' ? phaseRepresentativeFrame : currentFrame),
    [currentFrame, phaseRepresentativeFrame, viewMode],
  );

  const prevJumpDisabled = useMemo(() => {
    if (!frames.length) return true;
    if (viewMode === 'phase') {
      return findPrevTurnSlice(phaseSlices, currentPhaseIndex) === null;
    }
    return findPrevInteresting(frames, clampedIndex) === null;
  }, [clampedIndex, currentPhaseIndex, frames, phaseSlices, viewMode]);

  const nextJumpDisabled = useMemo(() => {
    if (!frames.length) return true;
    if (viewMode === 'phase') {
      return findNextTurnSlice(phaseSlices, currentPhaseIndex) === null;
    }
    return findNextInteresting(frames, clampedIndex) === null;
  }, [clampedIndex, currentPhaseIndex, frames, phaseSlices, viewMode]);

  const canStepBackward = viewMode === 'phase' ? currentPhaseIndex > 0 : clampedIndex > 0;
  const canStepForward = viewMode === 'phase'
    ? currentPhaseIndex < phaseSlices.length - 1
    : clampedIndex < frames.length - 1;

  // Playback loop
  useEffect(() => {
    if (!isPlaying) return;
    if (!frames.length) return;

    const t = setInterval(() => {
      setFrameIndex((i) => {
        if (viewMode === 'phase') {
          const phaseIndex = phaseIndexByFrame[i] || 0;
          const nextPhase = phaseIndex + 1;
          if (nextPhase >= phaseSlices.length) return i;
          return phaseSlices[nextPhase].start;
        }

        const nextFrame = i + 1;
        if (nextFrame >= frames.length) return i;
        return nextFrame;
      });
    }, speedMs);

    return () => clearInterval(t);
  }, [frames.length, isPlaying, phaseIndexByFrame, phaseSlices, speedMs, viewMode]);

  // Auto-stop at end
  useEffect(() => {
    if (!isPlaying) return;

    const atEnd = viewMode === 'phase'
      ? phaseSlices.length > 0 && currentPhaseIndex >= phaseSlices.length - 1
      : frames.length > 0 && clampedIndex >= frames.length - 1;

    if (atEnd) {
      setIsPlaying(false);
    }
  }, [clampedIndex, currentPhaseIndex, frames.length, isPlaying, phaseSlices.length, viewMode]);

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

  const currentPhaseLabel = currentPhaseSlice
    ? `Turn ${currentPhaseSlice.turn} • ${currentPhaseSlice.phase}/${currentPhaseSlice.step}`
    : `Turn ${currentFrame?.turn ?? 0} • ${currentFrame?.phase ?? ''}/${currentFrame?.step ?? ''}`;

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
              {currentPhaseLabel}
              {actionSummary.model ? ` • ${actionSummary.model}` : ''}
            </p>
          </div>
        </div>

        {/* Controls */}
        <div className="flex items-center gap-3">
          <div className="flex items-center bg-gray-800 rounded border border-gray-700 overflow-hidden">
            <button
              onClick={() => setViewMode('phase')}
              className={`px-2 py-1 text-xs ${viewMode === 'phase' ? 'bg-game-accent text-white' : 'text-gray-300 hover:bg-gray-700'}`}
            >
              Phase
            </button>
            <button
              onClick={() => setViewMode('action')}
              className={`px-2 py-1 text-xs ${viewMode === 'action' ? 'bg-game-accent text-white' : 'text-gray-300 hover:bg-gray-700'}`}
            >
              Action
            </button>
          </div>

          <button
            onClick={() => {
              if (viewMode === 'phase') {
                const prevTurnPhase = findPrevTurnSlice(phaseSlices, currentPhaseIndex);
                if (prevTurnPhase !== null) setFrameIndex(phaseSlices[prevTurnPhase].start);
                return;
              }

              const i = findPrevInteresting(frames, clampedIndex);
              if (i !== null) setFrameIndex(i);
            }}
            className="px-2 py-1 bg-gray-800 text-white rounded hover:bg-gray-700 border border-gray-700"
            disabled={prevJumpDisabled}
            title={viewMode === 'phase' ? 'Previous turn' : 'Previous non-PASS action'}
          >
            ⏮
          </button>
          <button
            onClick={() => {
              if (viewMode === 'phase') {
                const prevPhase = Math.max(0, currentPhaseIndex - 1);
                setFrameIndex(phaseSlices[prevPhase]?.start ?? clampedIndex);
                return;
              }

              setFrameIndex((i) => Math.max(0, i - 1));
            }}
            className="px-2 py-1 bg-gray-700 text-white rounded hover:bg-gray-600"
            disabled={!canStepBackward}
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
            onClick={() => {
              if (viewMode === 'phase') {
                const nextPhase = Math.min(phaseSlices.length - 1, currentPhaseIndex + 1);
                setFrameIndex(phaseSlices[nextPhase]?.start ?? clampedIndex);
                return;
              }

              setFrameIndex((i) => Math.min(frames.length - 1, i + 1));
            }}
            className="px-2 py-1 bg-gray-700 text-white rounded hover:bg-gray-600"
            disabled={!canStepForward}
          >
            ▶
          </button>
          <button
            onClick={() => {
              if (viewMode === 'phase') {
                const nextTurnPhase = findNextTurnSlice(phaseSlices, currentPhaseIndex);
                if (nextTurnPhase !== null) setFrameIndex(phaseSlices[nextTurnPhase].start);
                return;
              }

              const i = findNextInteresting(frames, clampedIndex);
              if (i !== null) setFrameIndex(i);
            }}
            className="px-2 py-1 bg-gray-800 text-white rounded hover:bg-gray-700 border border-gray-700"
            disabled={nextJumpDisabled}
            title={viewMode === 'phase' ? 'Next turn' : 'Next non-PASS action'}
          >
            ⏭
          </button>

          <div className="text-gray-400 text-sm tabular-nums">
            {visibleTotal ? `${visibleIndex + 1}/${visibleTotal}` : '0/0'}
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
          max={Math.max(0, visibleTotal - 1)}
          value={visibleIndex}
          onChange={(e) => {
            const index = parseInt(e.target.value, 10);
            if (viewMode === 'phase') {
              setFrameIndex(phaseSlices[index]?.start ?? 0);
            } else {
              setFrameIndex(index);
            }
          }}
          className="flex-1"
        />
        <div className="text-xs text-gray-400">
          {viewMode === 'phase' ? (
            <>{currentPhaseLabel} • {currentPhaseSlice ? `${currentPhaseSlice.end - currentPhaseSlice.start + 1} frames` : '0 frames'}</>
          ) : (
            <>Turn {currentFrame?.turn ?? 0} • {currentFrame?.phase ?? ''}/{currentFrame?.step ?? ''}</>
          )}
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
          <h2 className="text-white font-bold mb-2">
            {viewMode === 'phase' ? 'Phase Summary' : 'Decision'}
          </h2>
          <div className="text-gray-300 text-sm mb-1">{currentPhaseLabel}</div>
          <div className="text-gray-400 text-xs mb-3">{actionSummary.title}</div>

          {viewMode === 'phase' && currentPhaseSlice && (
            <div className="mb-4 text-xs text-gray-400">
              {countInterestingInSlice(frames, currentPhaseSlice)} non-pass action(s) in this phase window
            </div>
          )}

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
            <h3 className="text-white font-bold mb-2">{viewMode === 'phase' ? 'Phases' : 'Frames'}</h3>
            <div className="text-xs text-gray-400 mb-2">Click to jump</div>

            {viewMode === 'phase' ? (
              <div className="space-y-1">
                {phaseSlices
                  .slice(Math.max(0, currentPhaseIndex - 20), Math.min(phaseSlices.length, currentPhaseIndex + 21))
                  .map((slice, offset) => {
                    const phaseListStart = Math.max(0, currentPhaseIndex - 20);
                    const phaseIdx = phaseListStart + offset;
                    const isActive = phaseIdx === currentPhaseIndex;
                    const interestingCount = countInterestingInSlice(frames, slice);

                    return (
                      <button
                        key={`${slice.start}-${slice.end}`}
                        onClick={() => setFrameIndex(slice.start)}
                        className={`w-full text-left px-2 py-1 rounded border ${
                          isActive
                            ? 'bg-gray-800 border-game-accent text-white'
                            : 'bg-gray-900/30 border-gray-700 text-gray-300 hover:bg-gray-800/60'
                        }`}
                      >
                        <div className="text-xs truncate">
                          <span className="text-gray-500 mr-2">#{phaseIdx + 1}</span>
                          Turn {slice.turn} {slice.phase}/{slice.step}
                        </div>
                        <div className="text-[11px] text-gray-500">
                          {slice.end - slice.start + 1} frame(s) • {interestingCount} non-pass
                        </div>
                      </button>
                    );
                  })}
              </div>
            ) : (
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
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export default ReplayView;
