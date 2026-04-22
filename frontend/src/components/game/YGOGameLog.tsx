/**
 * YGOGameLog - Scrollable game log panel for the Yu-Gi-Oh! sidebar.
 *
 * Redesigned with:
 *  - Icon prefix per entry (sword / spell / trap / skull / etc.)
 *  - Gold turn dividers
 *  - Clustered AI turns (click to expand)
 *  - Color-coded mode-preserved theme
 */

import { useEffect, useMemo, useRef, useState } from 'react';
import type { GameLogEntry } from '../../types/game';
import { clusterLogEntries, colorClassForEvent, iconForEvent } from './shared/gameLogShared';

interface YGOGameLogProps {
  entries: GameLogEntry[];
  /** Optional name lookup so turn dividers can include the active duelist. */
  playerNames?: Record<string, string>;
}

export function YGOGameLog({ entries, playerNames }: YGOGameLogProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const clusters = useMemo(() => clusterLogEntries(entries), [entries]);
  const [expanded, setExpanded] = useState<Set<number>>(new Set());

  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [entries.length]);

  const toggle = (idx: number) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(idx)) next.delete(idx);
      else next.add(idx);
      return next;
    });
  };

  return (
    <div className="flex flex-col">
      <div ref={scrollRef} className="overflow-y-auto max-h-64 space-y-0.5">
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
                    <div className="flex-1 h-px bg-ygo-gold-dim/30" />
                    <span className="text-[10px] text-ygo-gold-dim font-semibold whitespace-nowrap">
                      Turn {cluster.turn}
                      {activeName ? ` - ${activeName}` : ''}
                    </span>
                    <div className="flex-1 h-px bg-ygo-gold-dim/30" />
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
                  <div className="ml-5 border-l border-ygo-gold-dim/30 pl-2 space-y-0.5 mt-0.5 mb-1">
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

export default YGOGameLog;
