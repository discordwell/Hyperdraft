/**
 * PKMGameLog - Scrollable game log panel for the Pokemon TCG sidebar.
 *
 * Shows recent game actions color-coded by event type, with turn dividers.
 */

import { useEffect, useRef } from 'react';
import type { GameLogEntry } from '../../types/game';

interface PKMGameLogProps {
  entries: GameLogEntry[];
}

/** Map event_type to Tailwind text classes. */
function entryClasses(eventType: string): string {
  const t = eventType.toLowerCase();

  if (t.includes('ko') || t.includes('knockout')) {
    return 'text-red-600 font-bold';
  }
  if (t.includes('attack') || t.includes('damage')) {
    return 'text-red-400';
  }
  if (t.includes('energy')) {
    return 'text-yellow-400';
  }
  if (t.includes('trainer') || t.includes('supporter') || t.includes('item') || t.includes('stadium')) {
    return 'text-blue-400';
  }
  if (t.includes('turn_start') || t.includes('turn_end') || t.includes('turn start') || t.includes('turn end')) {
    return 'text-gray-500 italic';
  }
  if (t.includes('evolve') || t.includes('evolution')) {
    return 'text-purple-400';
  }
  return 'text-gray-300';
}

function formatTimestamp(ts: number): string {
  const d = new Date(ts * 1000);
  const h = d.getHours().toString().padStart(2, '0');
  const m = d.getMinutes().toString().padStart(2, '0');
  const s = d.getSeconds().toString().padStart(2, '0');
  return `${h}:${m}:${s}`;
}

export function PKMGameLog({ entries }: PKMGameLogProps) {
  const scrollRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom when new entries arrive
  useEffect(() => {
    const el = scrollRef.current;
    if (el) {
      el.scrollTop = el.scrollHeight;
    }
  }, [entries.length]);

  let lastTurn: number | null = null;

  return (
    <div className="flex flex-col">
      <div className="text-xs text-gray-400 uppercase tracking-wide mb-2 px-1">
        Game Log
      </div>

      <div
        ref={scrollRef}
        className="overflow-y-auto max-h-64 space-y-0.5 scrollbar-thin scrollbar-thumb-gray-700 scrollbar-track-transparent"
      >
        {entries.length === 0 ? (
          <div className="text-gray-600 text-xs italic px-1">No events yet.</div>
        ) : (
          entries.map((entry, idx) => {
            const showDivider = entry.turn !== lastTurn;
            lastTurn = entry.turn;

            return (
              <div key={idx}>
                {/* Turn divider */}
                {showDivider && (
                  <div className="flex items-center gap-2 my-1.5">
                    <div className="flex-1 h-px bg-gray-700" />
                    <span className="text-[10px] text-gray-500 font-semibold whitespace-nowrap">
                      Turn {entry.turn}
                    </span>
                    <div className="flex-1 h-px bg-gray-700" />
                  </div>
                )}

                {/* Log entry */}
                <div className="flex items-start gap-1.5 px-1 py-0.5 rounded hover:bg-white/5 transition-colors">
                  <div className="flex-1 min-w-0">
                    <span className={`text-xs leading-snug ${entryClasses(entry.event_type)}`}>
                      {entry.text}
                    </span>
                  </div>
                  {entry.timestamp != null && (
                    <span className="text-[10px] text-gray-600 flex-shrink-0 mt-px">
                      {formatTimestamp(entry.timestamp)}
                    </span>
                  )}
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}

export default PKMGameLog;
