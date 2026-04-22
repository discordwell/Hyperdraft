/**
 * GameLog (MTG + generic fallback)
 *
 * Drop-in panel for showing the MTG/HS game log. Uses the shared helpers in
 * ./shared/gameLogShared.ts for icons, color classes, and AI-play clustering.
 *
 * Renders nothing if `entries` is undefined/empty and `hideWhenEmpty` is true,
 * otherwise shows an empty-state message so sidebars don't look broken.
 */

import { useEffect, useMemo, useRef, useState } from 'react';
import type { GameLogEntry } from '../../types/game';
import { clusterLogEntries, colorClassForEvent, iconForEvent } from './shared/gameLogShared';

interface GameLogProps {
  entries: GameLogEntry[];
  playerNames?: Record<string, string>;
  /** Tailwind class applied to the scroll container (control max height). */
  scrollClass?: string;
  hideWhenEmpty?: boolean;
  /** Theme accent for dividers. Default = mtg blue. */
  accentClass?: string;
  heading?: string;
}

export function GameLog({
  entries,
  playerNames,
  scrollClass = 'max-h-80',
  hideWhenEmpty = false,
  accentClass = 'bg-blue-700/40',
  heading = 'Game Log',
}: GameLogProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const clusters = useMemo(() => clusterLogEntries(entries || []), [entries]);
  const [expanded, setExpanded] = useState<Set<number>>(new Set());

  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [entries?.length]);

  const toggle = (idx: number) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(idx)) next.delete(idx);
      else next.add(idx);
      return next;
    });
  };

  if (hideWhenEmpty && clusters.length === 0) return null;

  return (
    <div className="flex flex-col">
      {heading && (
        <div className="text-xs text-gray-400 uppercase tracking-wide mb-2 px-1">{heading}</div>
      )}
      <div
        ref={scrollRef}
        className={`overflow-y-auto space-y-0.5 ${scrollClass} scrollbar-thin scrollbar-thumb-gray-700 scrollbar-track-transparent`}
      >
        {clusters.length === 0 ? (
          <div className="text-gray-600 text-xs italic px-1">No events yet.</div>
        ) : (
          clusters.map((cluster, idx) => {
            const showDivider = idx === 0 || cluster.turn !== clusters[idx - 1].turn;
            const isExpanded = expanded.has(idx);
            const hasChildren = cluster.children.length > 0;
            const activeName = cluster.player !== 'system' ? playerNames?.[cluster.player] : undefined;

            return (
              <div key={cluster.startIndex}>
                {showDivider && (
                  <div className="flex items-center gap-2 my-1.5">
                    <div className={`flex-1 h-px ${accentClass}`} />
                    <span className="text-[10px] text-gray-400 font-semibold whitespace-nowrap">
                      Turn {cluster.turn}
                      {activeName ? ` - ${activeName}` : ''}
                    </span>
                    <div className={`flex-1 h-px ${accentClass}`} />
                  </div>
                )}

                <button
                  type="button"
                  onClick={hasChildren ? () => toggle(idx) : undefined}
                  className={`w-full flex items-start gap-1.5 px-1 py-0.5 rounded text-left ${
                    hasChildren ? 'hover:bg-white/10 cursor-pointer' : 'cursor-default'
                  } transition-colors`}
                >
                  <span className="text-[11px] leading-snug flex-shrink-0 w-4 text-center" aria-hidden>
                    {iconForEvent(cluster.headline)}
                  </span>
                  <span className={`text-xs leading-snug flex-1 min-w-0 ${colorClassForEvent(cluster.headline)}`}>
                    {cluster.headline.text}
                    {hasChildren && (
                      <span className="ml-1 text-[10px] text-gray-500">
                        ({cluster.children.length + 1}) {isExpanded ? '▾' : '▸'}
                      </span>
                    )}
                  </span>
                </button>

                {isExpanded && hasChildren && (
                  <div className="ml-5 border-l border-gray-700/60 pl-2 space-y-0.5 mt-0.5 mb-1">
                    {cluster.children.map((child, i) => (
                      <div key={i} className="flex items-start gap-1.5 px-1 py-px">
                        <span className="text-[10px] leading-snug flex-shrink-0 w-4 text-center" aria-hidden>
                          {iconForEvent(child)}
                        </span>
                        <span className={`text-[11px] leading-snug flex-1 min-w-0 ${colorClassForEvent(child)}`}>
                          {child.text}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}

export default GameLog;
