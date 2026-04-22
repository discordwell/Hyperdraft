/**
 * LegendaryEntranceOverlay
 *
 * Fires a brief (~1.5s) fanfare animation when a qualifying permanent first
 * appears on the battlefield. Shared across MTG / HS / PKM / YGO modes.
 *
 * Detection rules (see `isLegendaryCard`):
 *  - Explicit supertype "Legendary" or type "LEGENDARY" in card.types
 *  - Text contains "Legendary"
 *  - Pokemon marked as `is_ex`
 *  - Mana cost / CMC of 6 or higher
 *  - YGO monster with ATK >= 3000
 *
 * The overlay is purely visual: it renders as `pointer-events-none` so
 * End Turn, clicks, and drag-and-drop continue to work underneath.
 *
 * Performance: consumers are expected to memoize `battlefieldCards`
 * (e.g. `gameState.battlefield`) so this component does NOT force the
 * game board to re-render when an event fires. Internal queue state is
 * local to this component.
 */

import { useEffect, useRef, useState, useCallback } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import type { CardData } from '../../../types';
import { useGameStore } from '../../../stores/gameStore';

interface LegendaryEntranceOverlayProps {
  /** Every card currently on the battlefield (or in active/bench for PKM, monster zones for YGO). */
  battlefieldCards: CardData[];
  /** Optional: first render bootstrap. When true (default) we seed the "seen" set to skip cards already on the board when this component mounts. */
  skipInitial?: boolean;
}

type QueueItem = {
  id: string;
  card: CardData;
};

function parseCmcFromManaCost(manaCost: string | null | undefined): number {
  if (!manaCost) return 0;
  // Handle plain numeric HS/PKM costs like "5"
  const numeric = Number(manaCost);
  if (!Number.isNaN(numeric)) return numeric;

  // Handle {2}{W}{U} style MTG costs
  let cmc = 0;
  const tokens = manaCost.match(/\{([^}]+)\}/g) || [];
  for (const tok of tokens) {
    const inner = tok.slice(1, -1);
    const asNum = Number(inner);
    if (!Number.isNaN(asNum)) {
      cmc += asNum;
    } else if (inner === 'X') {
      // X doesn't count
    } else {
      // Colored / hybrid pip = 1
      cmc += 1;
    }
  }
  return cmc;
}

export function isLegendaryCard(card: CardData): boolean {
  // Explicit MTG supertype
  if (card.types && card.types.some((t) => t.toLowerCase() === 'legendary')) {
    return true;
  }
  // Text-based detection for MTG real-set cards (where supertypes aren't serialized)
  if (card.text && /\bLegendary\b/.test(card.text)) {
    return true;
  }
  // Pokemon EX
  if (card.is_ex) {
    return true;
  }
  // YGO 3000+ ATK monsters
  if (typeof card.atk === 'number' && card.atk >= 3000) {
    return true;
  }
  // High-cost MTG / HS heuristic
  const cmc = parseCmcFromManaCost(card.mana_cost);
  if (cmc >= 6) {
    return true;
  }
  return false;
}

/** Accent gradient varies by game flavor. */
function colorsForCard(card: CardData): { glow: string; ring: string; accent: string; rarityLabel: string } {
  if (card.is_ex) {
    return { glow: 'shadow-[0_0_80px_20px_rgba(250,204,21,0.55)]', ring: 'ring-yellow-300', accent: 'from-yellow-300 via-amber-400 to-orange-500', rarityLabel: 'Pokémon ex' };
  }
  if (card.ygo_monster_type) {
    return { glow: 'shadow-[0_0_80px_20px_rgba(251,191,36,0.55)]', ring: 'ring-amber-300', accent: 'from-amber-200 via-yellow-400 to-amber-600', rarityLabel: 'Boss Monster' };
  }
  return { glow: 'shadow-[0_0_80px_20px_rgba(250,204,21,0.45)]', ring: 'ring-yellow-300', accent: 'from-yellow-200 via-amber-400 to-yellow-600', rarityLabel: 'Legendary' };
}

export function LegendaryEntranceOverlay({ battlefieldCards, skipInitial = true }: LegendaryEntranceOverlayProps) {
  const animationsEnabled = useGameStore((s) => s.ui.animationsEnabled);

  const seenIdsRef = useRef<Set<string>>(new Set());
  const initializedRef = useRef(false);
  const [queue, setQueue] = useState<QueueItem[]>([]);
  const [current, setCurrent] = useState<QueueItem | null>(null);

  // Detect newly-added qualifying cards.
  useEffect(() => {
    if (!initializedRef.current) {
      initializedRef.current = true;
      if (skipInitial) {
        for (const c of battlefieldCards) seenIdsRef.current.add(c.id);
        return;
      }
    }

    const current = seenIdsRef.current;
    const newlyAdded: CardData[] = [];
    for (const c of battlefieldCards) {
      if (!current.has(c.id)) {
        current.add(c.id);
        if (isLegendaryCard(c)) newlyAdded.push(c);
      }
    }

    // Also prune ids that have left the battlefield so re-summons re-trigger.
    const liveIds = new Set(battlefieldCards.map((c) => c.id));
    for (const id of Array.from(current)) {
      if (!liveIds.has(id)) current.delete(id);
    }

    if (newlyAdded.length > 0 && animationsEnabled) {
      setQueue((prev) => [...prev, ...newlyAdded.map((c) => ({ id: c.id, card: c }))]);
    }
  }, [battlefieldCards, animationsEnabled, skipInitial]);

  // Drive the queue: when nothing playing, pop the next item.
  useEffect(() => {
    if (current || queue.length === 0) return;
    const [next, ...rest] = queue;
    setCurrent(next);
    setQueue(rest);

    const t = setTimeout(() => setCurrent(null), 1500);
    return () => clearTimeout(t);
  }, [current, queue]);

  const handleDismiss = useCallback(() => setCurrent(null), []);

  if (!animationsEnabled) return null;

  return (
    <div className="pointer-events-none fixed inset-0 z-40 flex items-center justify-center">
      <AnimatePresence>
        {current && (
          <motion.div
            key={current.id}
            className="pointer-events-none relative flex flex-col items-center"
            initial={{ opacity: 0, scale: 0.2 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.85, y: -40 }}
            transition={{ duration: 0.45, ease: 'easeOut' }}
            onAnimationComplete={() => {
              // Nothing here; timeout handles dismiss.
            }}
            onClick={handleDismiss}
          >
            <LegendaryCardFanfare card={current.card} />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function LegendaryCardFanfare({ card }: { card: CardData }) {
  const { glow, ring, accent, rarityLabel } = colorsForCard(card);

  return (
    <div className="flex flex-col items-center gap-3">
      {/* Rarity banner */}
      <motion.div
        initial={{ opacity: 0, y: 30 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.15, duration: 0.35 }}
        className={`px-4 py-1 rounded-full bg-gradient-to-r ${accent} text-black text-xs font-black uppercase tracking-[0.25em] shadow-lg`}
      >
        {rarityLabel}
      </motion.div>

      {/* Card body */}
      <motion.div
        className={`relative w-56 h-80 rounded-xl ring-4 ${ring} ${glow} overflow-hidden`}
        initial={{ rotate: -3 }}
        animate={{ rotate: [-3, 2, 0] }}
        transition={{ duration: 0.7 }}
      >
        {/* Base panel */}
        <div className={`absolute inset-0 bg-gradient-to-br ${accent} opacity-90`} />
        {/* Inner dark card face */}
        <div className="absolute inset-2 rounded-lg bg-gray-900/90 border border-white/20 p-3 flex flex-col">
          <div className="text-[11px] text-white/60 uppercase tracking-wider mb-1">
            {card.types?.length ? card.types.join(' · ') : 'Creature'}
          </div>
          <div className="text-lg font-extrabold text-white leading-tight drop-shadow-[0_1px_6px_rgba(0,0,0,0.6)]">
            {card.name}
          </div>
          <div className="mt-auto">
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.35, duration: 0.3 }}
              className="text-[11px] leading-snug text-white/80 line-clamp-5"
            >
              {card.text || card.ability_text || ''}
            </motion.div>
            {(card.power !== null && card.power !== undefined) && (
              <div className="mt-2 text-right text-white font-bold text-sm">
                {card.power}/{card.toughness}
              </div>
            )}
            {typeof card.atk === 'number' && (
              <div className="mt-2 text-right text-white font-bold text-sm">
                ATK {card.atk}
                {typeof card.def_val === 'number' ? ` / DEF ${card.def_val}` : ''}
              </div>
            )}
            {typeof card.hp === 'number' && (
              <div className="mt-2 text-right text-white font-bold text-sm">
                HP {card.hp}
              </div>
            )}
          </div>
        </div>

        {/* Shimmer sweep */}
        <motion.div
          className="absolute inset-0 bg-gradient-to-br from-white/0 via-white/40 to-white/0"
          initial={{ x: '-120%' }}
          animate={{ x: '120%' }}
          transition={{ delay: 0.2, duration: 0.7, ease: 'easeInOut' }}
          style={{ mixBlendMode: 'screen' }}
        />
      </motion.div>
    </div>
  );
}

export default LegendaryEntranceOverlay;
