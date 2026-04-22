/**
 * DragHintOverlay
 *
 * Floating hint bar shown during drag operations.
 * Displays intent text like "Summon Monster", "Attach Energy", etc.
 */

import { useDragDropStore } from '../../hooks/useDragDrop';

const INTENT_LABELS: Record<string, string> = {
  play: 'Play Card',
  attack: 'Attack',
  attach: 'Attach Energy',
  evolve: 'Evolve Pokemon',
  summon: 'Summon Monster',
  set: 'Set Card',
  activate: 'Activate',
};

const MODE_COLORS: Record<string, string> = {
  hs: 'bg-emerald-800/90 border-emerald-500/50 text-emerald-100',
  pkm: 'bg-amber-800/90 border-amber-500/50 text-amber-100',
  ygo: 'bg-yellow-900/90 border-yellow-500/50 text-yellow-100',
  mtg: 'bg-blue-800/90 border-blue-500/50 text-blue-100',
};

export function DragHintOverlay() {
  const isDragging = useDragDropStore((s) => s.isDragging);
  const dragItem = useDragDropStore((s) => s.dragItem);

  if (!isDragging || !dragItem) return null;

  const intent = dragItem.intent || 'play';
  const gameMode = dragItem.gameMode || 'mtg';
  const label = INTENT_LABELS[intent] || 'Drag to target';
  const colorClass = MODE_COLORS[gameMode] || MODE_COLORS.mtg;

  return (
    <div className="fixed top-4 left-1/2 -translate-x-1/2 z-50 pointer-events-none">
      <div
        className={`px-4 py-2 rounded-lg border backdrop-blur-sm shadow-lg text-sm font-bold ${colorClass}`}
      >
        {label}: {dragItem.card.name}
      </div>
    </div>
  );
}
