/**
 * Shared helpers for game log rendering.
 *
 * Provides:
 *  - iconForEvent: map event_type/text to a short glyph
 *  - colorClassForEvent: mode-agnostic color classes
 *  - clusterLogEntries: group consecutive entries by (turn, actor)
 *    so AI plays collapse into one expandable block.
 */

import type { GameLogEntry } from '../../../types/game';

/** Short glyph used as a left-side icon for a log entry. */
export function iconForEvent(entry: GameLogEntry): string {
  const t = (entry.event_type || '').toLowerCase();
  const text = (entry.text || '').toLowerCase();

  // Deaths / KOs / destruction first (most specific)
  if (t.includes('ko') || t.includes('knockout') || t.includes('death') || t.includes('destroy') || text.includes('dies')) {
    return '💀';
  }
  // Damage
  if (t.includes('damage') || text.includes('damage')) {
    return '🔥';
  }
  // Heal / life gain
  if (t.includes('heal') || t.includes('life_change') || text.includes('gain') || text.includes('heal')) {
    return '❤️';
  }
  // Attack
  if (t.includes('attack')) {
    return '⚔️';
  }
  // Counter / buff
  if (t.includes('counter') || t.includes('pt_modification') || text.includes('+1/+1')) {
    return '➕';
  }
  // Spells / activations
  if (t.includes('cast') || t.includes('spell') || t.includes('activate') || text.includes('cast') || text.includes('activate')) {
    return '✨';
  }
  // Trainer / tool / artifact
  if (t.includes('trainer') || t.includes('supporter') || t.includes('item') || t.includes('equip')) {
    return '🧰';
  }
  // Traps
  if (t.includes('trap')) {
    return '🪤';
  }
  // Summons / plays
  if (t.includes('summon') || t.includes('play') || t.includes('play_card') || t.includes('etb') || text.includes('summon')) {
    return '🂠';
  }
  // Evolve
  if (t.includes('evolve') || t.includes('evolution')) {
    return '🔺';
  }
  // Energy
  if (t.includes('energy')) {
    return '⚡';
  }
  // Draw
  if (t.includes('draw')) {
    return '📜';
  }
  // Turn markers
  if (t.includes('turn') || t.includes('phase') || t.includes('upkeep') || t.includes('step')) {
    return '⏱';
  }
  // Position / set
  if (t.includes('position') || t.includes('set')) {
    return '📌';
  }
  return '·';
}

/**
 * Color class family for a log entry text. Does not set a background — the
 * consumer owns layout. Works with each mode's theme because it only sets
 * Tailwind text colors.
 */
export function colorClassForEvent(entry: GameLogEntry): string {
  const t = (entry.event_type || '').toLowerCase();
  const text = (entry.text || '').toLowerCase();

  if (t.includes('ko') || t.includes('knockout') || t.includes('death') || t.includes('destroy')) {
    return 'text-red-500 font-semibold';
  }
  if (t.includes('damage')) {
    return 'text-red-300';
  }
  if (t.includes('heal') || t.includes('life_change') || text.includes('gain')) {
    return 'text-emerald-300';
  }
  if (t.includes('attack')) {
    return 'text-orange-300';
  }
  if (t.includes('cast') || t.includes('spell') || t.includes('activate')) {
    return 'text-violet-300';
  }
  if (t.includes('trap')) {
    return 'text-pink-300';
  }
  if (t.includes('counter') || t.includes('pt_modification')) {
    return 'text-amber-300';
  }
  if (t.includes('summon') || t.includes('play') || t.includes('etb')) {
    return 'text-sky-300';
  }
  if (t.includes('evolve')) {
    return 'text-purple-300';
  }
  if (t.includes('energy')) {
    return 'text-yellow-300';
  }
  if (t.includes('trainer') || t.includes('supporter') || t.includes('item')) {
    return 'text-blue-300';
  }
  if (t.includes('turn') || t.includes('phase') || t.includes('step')) {
    return 'text-gray-500 italic';
  }
  return 'text-gray-300';
}

/**
 * Cluster: for a run of consecutive entries sharing (turn, player), pick
 * a representative "headline" entry and keep the remainder as children.
 * Callers use this to render a compact "AI played X" row that expands to
 * reveal triggers, damage, deaths, etc.
 */
export interface LogCluster {
  turn: number;
  /** Who acted (or 'system' if the entry has no player id). */
  player: string;
  /** One-line headline shown in collapsed mode. */
  headline: GameLogEntry;
  /** Remaining entries to reveal when expanded (may be empty). */
  children: GameLogEntry[];
  /** Index of first entry in original array (for stable keys). */
  startIndex: number;
}

/** Priority order when picking the cluster headline — higher wins. */
function headlinePriority(entry: GameLogEntry): number {
  const t = (entry.event_type || '').toLowerCase();
  if (t.includes('cast') || t.includes('spell') || t.includes('activate')) return 90;
  if (t.includes('summon') || t.includes('play') || t.includes('normal_summon') || t.includes('special_summon')) return 85;
  if (t.includes('attack')) return 80;
  if (t.includes('evolve')) return 75;
  if (t.includes('energy')) return 40;
  if (t.includes('ko') || t.includes('knockout') || t.includes('death') || t.includes('destroy')) return 60;
  if (t.includes('damage')) return 30;
  if (t.includes('counter') || t.includes('pt_modification')) return 20;
  if (t.includes('turn') || t.includes('phase') || t.includes('step')) return 0;
  return 10;
}

export function clusterLogEntries(entries: GameLogEntry[]): LogCluster[] {
  if (entries.length === 0) return [];

  const out: LogCluster[] = [];
  let runStart = 0;

  const flushRun = (endExclusive: number) => {
    const run = entries.slice(runStart, endExclusive);
    if (run.length === 0) return;

    // Turn banners are their own cluster, always solo.
    if ((run[0].event_type || '').toLowerCase().includes('turn') && run.length === 1) {
      out.push({
        turn: run[0].turn,
        player: run[0].player || 'system',
        headline: run[0],
        children: [],
        startIndex: runStart,
      });
      return;
    }

    // Pick headline = highest priority entry in the run (ties: first occurrence).
    let bestIdx = 0;
    let bestPrio = -1;
    for (let i = 0; i < run.length; i++) {
      const p = headlinePriority(run[i]);
      if (p > bestPrio) {
        bestPrio = p;
        bestIdx = i;
      }
    }
    const headline = run[bestIdx];
    const children = run.filter((_, i) => i !== bestIdx);

    out.push({
      turn: headline.turn,
      player: headline.player || run[0].player || 'system',
      headline,
      children,
      startIndex: runStart,
    });
  };

  for (let i = 1; i < entries.length; i++) {
    const prev = entries[i - 1];
    const cur = entries[i];
    const sameTurn = prev.turn === cur.turn;
    const samePlayer = (prev.player || '') === (cur.player || '');
    // Turn/phase markers break runs unconditionally
    const curIsTurnMarker = (cur.event_type || '').toLowerCase().includes('turn');
    const prevIsTurnMarker = (prev.event_type || '').toLowerCase().includes('turn');

    if (!sameTurn || !samePlayer || curIsTurnMarker || prevIsTurnMarker) {
      flushRun(i);
      runStart = i;
    }
  }
  flushRun(entries.length);

  return out;
}
