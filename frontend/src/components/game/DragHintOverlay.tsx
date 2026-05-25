/**
 * DragHintOverlay
 *
 * Floating hint bar shown during drag operations. Reads from cardZoneStore
 * (the shared primitive used by all 10 engines as of PR 5). Displays the
 * intent verb so the player knows what their drag will do — useful for
 * Pokemon (attach/evolve/play look different) and for new players.
 */

import { useCardZoneStore } from '../../stores/cardZoneStore';

const INTENT_LABELS: Record<string, string> = {
  play: 'Play Card',
  attack: 'Attack',
  attach: 'Attach Energy',
  evolve: 'Evolve Pokémon',
  summon: 'Summon Monster',
  set: 'Set Card',
  activate: 'Activate',
  retreat: 'Retreat',
  target: 'Pick Target',
};

// Engine-id (matches GameState.game_mode) → tailwind color class.
// Mirrors the per-engine accent palette but maps to bg/border/text triplets
// so the hint reads in the game's identity color at a glance.
const ENGINE_COLORS: Record<string, string> = {
  hearthstone: 'bg-amber-800/90 border-amber-500/50 text-amber-100',
  pokemon: 'bg-red-800/90 border-red-400/50 text-red-50',
  yugioh: 'bg-purple-900/90 border-purple-400/50 text-purple-100',
  mtg: 'bg-indigo-800/90 border-indigo-400/50 text-indigo-100',
  cats: 'bg-amber-800/90 border-amber-500/50 text-amber-100',
  clankers: 'bg-blue-800/90 border-blue-500/50 text-blue-100',
  minecraft: 'bg-lime-800/90 border-lime-500/50 text-lime-100',
  depths: 'bg-cyan-800/90 border-cyan-500/50 text-cyan-100',
  finance: 'bg-emerald-800/90 border-emerald-500/50 text-emerald-100',
  scp: 'bg-orange-800/90 border-orange-500/50 text-orange-100',
};

export function DragHintOverlay() {
  const dragCardId = useCardZoneStore((s) => s.dragCardId);
  const activeIntent = useCardZoneStore((s) => s.activeIntent);
  const engineId = useCardZoneStore((s) => s.engineId);

  // Only show during an actual drag — not a click-prime, not a choice prime.
  // (Choice prime uses the overlay pill in ChoiceModal; click-prime is its
  // own visual via the primed card's lift + drop-shadow.)
  if (!dragCardId) return null;

  const label = INTENT_LABELS[activeIntent ?? 'play'] ?? 'Drag to target';
  const colorClass = (engineId && ENGINE_COLORS[engineId]) || ENGINE_COLORS.mtg;

  return (
    <div className="fixed top-4 left-1/2 -translate-x-1/2 z-50 pointer-events-none">
      <div
        className={`px-4 py-2 rounded-lg border backdrop-blur-sm shadow-lg text-sm font-bold ${colorClass}`}
      >
        {label}
      </div>
    </div>
  );
}
