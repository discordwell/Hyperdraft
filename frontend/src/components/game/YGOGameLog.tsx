/**
 * YGOGameLog - Scrollable game log panel for the Yu-Gi-Oh! sidebar.
 *
 * Color-coded entries: Summon=gold, Attack/Damage=red, Spell=teal,
 * Trap=pink, LP change=yellow, Turn=gray italic, Set=dim, Chain=purple
 */

import { useEffect, useRef } from 'react';
import type { GameLogEntry } from '../../types/game';

interface YGOGameLogProps {
  entries: GameLogEntry[];
}

function entryClasses(entry: GameLogEntry): string {
  const t = (entry.event_type || '').toLowerCase();
  const text = (entry.text || '').toLowerCase();

  if (t.includes('summon') || text.includes('summon')) return 'text-ygo-gold-bright font-semibold';
  if (t.includes('attack') || t.includes('damage') || t.includes('destroy')) return 'text-red-400';
  if (t.includes('activate') || t.includes('spell') || text.includes('activate')) return 'text-teal-400';
  if (t.includes('position')) return 'text-gray-400';
  if (t.includes('trap')) return 'text-pink-400';
  if (t.includes('lp') || t.includes('life')) return 'text-yellow-400';
  if (t.includes('chain')) return 'text-purple-400';
  if (t.includes('set') || text.includes('set')) return 'text-gray-500';
  if (t.includes('turn') || t.includes('phase')) return 'text-gray-500 italic';
  if (t.includes('draw')) return 'text-gray-400';
  return 'text-gray-300';
}

export function YGOGameLog({ entries }: YGOGameLogProps) {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [entries.length]);

  return (
    <div className="flex flex-col">
      <div
        ref={scrollRef}
        className="overflow-y-auto max-h-64 space-y-0.5"
      >
        {entries.length === 0 ? (
          <div className="text-gray-600 text-xs italic px-1">No events yet.</div>
        ) : (
          entries.map((entry, idx) => {
            const showDivider = idx === 0 || entry.turn !== entries[idx - 1].turn;

            return (
              <div key={idx}>
                {showDivider && (
                  <div className="flex items-center gap-2 my-1.5">
                    <div className="flex-1 h-px bg-ygo-gold-dim/30" />
                    <span className="text-[10px] text-ygo-gold-dim font-semibold whitespace-nowrap">
                      Turn {entry.turn}
                    </span>
                    <div className="flex-1 h-px bg-ygo-gold-dim/30" />
                  </div>
                )}

                <div className="flex items-start gap-1.5 px-1 py-0.5 rounded hover:bg-white/5 transition-colors">
                  <div className="flex-1 min-w-0">
                    <span className={`text-xs leading-snug ${entryClasses(entry)}`}>
                      {entry.text}
                    </span>
                  </div>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}

export default YGOGameLog;
