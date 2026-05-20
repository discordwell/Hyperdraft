/**
 * Timeline — one widget, three jobs (HD-CRIT 17).
 *
 * The same scrubber is the lobby ticker ("currently at turn 4 of HD-8F4A"),
 * the in-board read-only rail ("you are at T4"), and the replay scrubber
 * on the post-match page. Compact mode strips the labels for use inside
 * other lab Plate cards; full mode adds the match ID + turn count above
 * the bar.
 *
 * Visual (mirrors HD-ART-03 right-rail replay scrubber):
 *   ┌────────────────────────────────────────────────────┐
 *   │ HD-8F4A                              T4 of T8      │ <- full only
 *   │ ════════════━━━━●─────────────────────────────────  │ <- 6px hairline
 *   │ T0                                            T8    │ <- compact hides
 *   └────────────────────────────────────────────────────┘
 *
 * Motion: ink fill width + pip head left transition use a 220ms
 * ease-out-cubic curve (HD-MOT — animate state, not decoration; the
 * 140-320ms range; eased-out cubic on physical movement, hard steps
 * on time). The turn number above swaps without a transition because
 * it's discrete time, not physical movement.
 *
 * Interaction: when onScrub is set, the bar becomes a button — click
 * computes the target turn from click x relative to the bar width and
 * fires the callback. Without onScrub the bar is read-only (used inside
 * GameView during a live game).
 */

import { useCallback, useRef } from 'react';

export interface TimelineProps {
  /** Current turn (0..totalTurns). */
  currentTurn: number;
  /** Total turns in the run; the right end-label defaults to T{totalTurns}. */
  totalTurns: number;
  /** Override the right-edge label (e.g. "DONE", "T?", "LIVE"). */
  endLabel?: string;
  /** Optional match ID, rendered as the eyebrow in `full` mode. */
  matchId?: string;
  /** `compact` drops the T0 / end labels and reduces the bar height. */
  mode?: 'compact' | 'full';
  /** If supplied, the bar becomes clickable and emits the target turn. */
  onScrub?: (turn: number) => void;
  /** Accessible label override; default derives from currentTurn + totalTurns. */
  ariaLabel?: string;
}

/**
 * One-widget-three-jobs replay timeline.
 *
 * @example Lobby ticker (compact, navigates on click)
 *   <Timeline currentTurn={4} totalTurns={8} mode="compact"
 *             onScrub={(t) => navigate(`/spectate/HD-8F4A?turn=${t}`)} />
 *
 * @example Live game rail (compact, read-only)
 *   <Timeline currentTurn={state.turn} totalTurns={state.turn + 1}
 *             mode="compact" />
 *
 * @example Replay scrubber (full, scrubs frame index)
 *   <Timeline currentTurn={frameIndex} totalTurns={totalFrames - 1}
 *             matchId={matchId} mode="full"
 *             endLabel={`T${totalFrames}`}
 *             onScrub={(i) => setFrameIndex(i)} />
 */
export function Timeline({
  currentTurn,
  totalTurns,
  endLabel,
  matchId,
  mode = 'full',
  onScrub,
  ariaLabel,
}: TimelineProps) {
  const trackRef = useRef<HTMLDivElement>(null);

  // Clamp so a malformed totalTurns can't divide by zero or render the
  // pip off the rail. We still respect currentTurn === totalTurns (game
  // just ended) so the pip lands flush with the right end.
  const safeTotal = Math.max(1, totalTurns);
  const safeCurrent = Math.max(0, Math.min(currentTurn, safeTotal));
  const pct = (safeCurrent / safeTotal) * 100;
  const rightLabel = endLabel ?? `T${safeTotal}`;
  const interactive = typeof onScrub === 'function';

  const handleClick = useCallback(
    (e: React.MouseEvent<HTMLDivElement>) => {
      if (!interactive || !trackRef.current) return;
      const rect = trackRef.current.getBoundingClientRect();
      if (rect.width <= 0) return;
      const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
      // Round so a click at 47% of an 8-turn run lands on T4, not T3.76.
      const target = Math.round(ratio * safeTotal);
      onScrub!(target);
    },
    [interactive, onScrub, safeTotal],
  );

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLDivElement>) => {
      if (!interactive) return;
      if (e.key === 'ArrowLeft') {
        e.preventDefault();
        onScrub!(Math.max(0, safeCurrent - 1));
      } else if (e.key === 'ArrowRight') {
        e.preventDefault();
        onScrub!(Math.min(safeTotal, safeCurrent + 1));
      } else if (e.key === 'Home') {
        e.preventDefault();
        onScrub!(0);
      } else if (e.key === 'End') {
        e.preventDefault();
        onScrub!(safeTotal);
      }
    },
    [interactive, onScrub, safeCurrent, safeTotal],
  );

  const trackHeight = mode === 'compact' ? 4 : 6;
  const pipSize = mode === 'compact' ? 10 : 12;

  return (
    <div
      data-testid="lab-timeline"
      data-mode={mode}
      style={{ fontFamily: 'var(--font-sans)' }}
    >
      {/* full-mode header — match ID + turn-of-total */}
      {mode === 'full' && (
        <div
          className="flex items-baseline justify-between mb-2"
          style={{ color: 'var(--ink-3)' }}
        >
          <span
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: '11px',
              letterSpacing: '0.08em',
              textTransform: 'uppercase',
              color: 'var(--ink-2)',
            }}
          >
            {matchId ?? 'replay'}
          </span>
          <span
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: '11px',
              letterSpacing: '0.04em',
              color: 'var(--ink-2)',
              fontVariantNumeric: 'tabular-nums',
            }}
          >
            T{safeCurrent} <span style={{ color: 'var(--ink-3)' }}>of</span> {rightLabel}
          </span>
        </div>
      )}

      {/* track wrapper — gives the pip head somewhere to overflow above the
          hairline rule without inflating the bar height */}
      <div
        ref={trackRef}
        role={interactive ? 'slider' : 'progressbar'}
        aria-label={
          ariaLabel ??
          (interactive
            ? `Replay timeline — turn ${safeCurrent} of ${safeTotal}. Click or use arrow keys to scrub.`
            : `Currently at turn ${safeCurrent} of ${safeTotal}.`)
        }
        aria-valuemin={0}
        aria-valuemax={safeTotal}
        aria-valuenow={safeCurrent}
        tabIndex={interactive ? 0 : -1}
        onClick={handleClick}
        onKeyDown={handleKeyDown}
        style={{
          position: 'relative',
          height: `${trackHeight}px`,
          width: '100%',
          background: 'var(--rule-2)',
          cursor: interactive ? 'pointer' : 'default',
          // Slight tactile hit target — pad clickable area without changing
          // the visual hairline. The track ref still measures the visible bar.
          ...(interactive
            ? { boxShadow: '0 8px 0 -7px transparent, 0 -8px 0 -7px transparent' }
            : {}),
        }}
      >
        {/* ink fill — 0 to current */}
        <div
          aria-hidden
          style={{
            position: 'absolute',
            left: 0,
            top: 0,
            bottom: 0,
            width: `${pct}%`,
            background: 'var(--ink)',
            // HD-MOT: ease-out cubic, 220ms — physical movement of the
            // playhead is animated, the discrete turn number above isn't.
            transition: 'width 220ms cubic-bezier(0.22, 0.8, 0.3, 1)',
          }}
        />

        {/* sodium pip head */}
        <div
          aria-hidden
          style={{
            position: 'absolute',
            left: `${pct}%`,
            top: '50%',
            width: `${pipSize}px`,
            height: `${pipSize}px`,
            transform: 'translate(-50%, -50%)',
            background: 'var(--sodium)',
            border: '1px solid var(--ink)',
            borderRadius: '50%',
            boxShadow: '0 1px 0 var(--paper-2)',
            transition: 'left 220ms cubic-bezier(0.22, 0.8, 0.3, 1)',
          }}
        />
      </div>

      {/* compact-mode hides T0 / endLabel tick labels — used inside other
          lab plates where the surrounding card already names what the bar
          measures */}
      {mode === 'full' && (
        <div
          className="flex items-baseline justify-between mt-1.5"
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: '10px',
            letterSpacing: '0.06em',
            color: 'var(--ink-3)',
            fontVariantNumeric: 'tabular-nums',
          }}
        >
          <span>T0</span>
          <span>{rightLabel}</span>
        </div>
      )}
    </div>
  );
}

export default Timeline;
