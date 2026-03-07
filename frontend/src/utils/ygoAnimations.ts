/**
 * Yu-Gi-Oh! Animation Utilities
 *
 * Shared motion variants and helpers for framer-motion animations.
 * Theme: Dark + Gold
 */

import type { Variants, Transition } from 'framer-motion';

// Spring presets (shared with PKM)
export const springSnappy: Transition = { type: 'spring', stiffness: 500, damping: 30 };
export const springBouncy: Transition = { type: 'spring', stiffness: 300, damping: 20 };
export const springGentle: Transition = { type: 'spring', stiffness: 200, damping: 25 };
export const tweenFast: Transition = { type: 'tween', duration: 0.2, ease: 'easeOut' };
export const tweenSmooth: Transition = { type: 'tween', duration: 0.35, ease: 'easeInOut' };

// Card summon (flip + scale)
export const cardSummon: Variants = {
  initial: { opacity: 0, scale: 0.3, rotateY: 180 },
  animate: { opacity: 1, scale: 1, rotateY: 0, transition: { duration: 0.5, ease: 'easeOut' } },
  exit: { opacity: 0, scale: 0.5, rotate: 15, transition: { duration: 0.3, ease: 'easeIn' } },
};

// Card enter (generic zone enter — scale + fade)
export const cardEnter: Variants = {
  initial: { opacity: 0, scale: 0.8, y: 10 },
  animate: { opacity: 1, scale: 1, y: 0, transition: springBouncy },
  exit: { opacity: 0, scale: 0.7, y: -10, transition: tweenFast },
};

// Hand card stagger container
export const handStagger: Variants = {
  animate: {
    transition: { staggerChildren: 0.04 },
  },
};

// Hand card (y slide)
export const handCard: Variants = {
  initial: { opacity: 0, y: 40 },
  animate: { opacity: 1, y: 0, transition: springGentle },
  exit: { opacity: 0, y: 40, transition: tweenFast },
};

// Zone slide (set to back row)
export const zoneSlide: Variants = {
  initial: { opacity: 0, y: -20, scale: 0.9 },
  animate: { opacity: 1, y: 0, scale: 1, transition: springSnappy },
  exit: { opacity: 0, y: 20, scale: 0.9, transition: tweenFast },
};

// Turn banner
export const turnBanner: Variants = {
  initial: { opacity: 0, y: -60, scale: 0.8 },
  animate: { opacity: 1, y: 0, scale: 1, transition: springBouncy },
  exit: { opacity: 0, y: -60, scale: 0.8, transition: tweenFast },
};

// Attack slash
export const attackSlash: Variants = {
  initial: { x: 0 },
  attack: { x: [0, -6, 6, -4, 4, 0], transition: { duration: 0.4 } },
};

// Chain link pulse
export const chainLink: Variants = {
  initial: { scale: 1 },
  pulse: { scale: [1, 1.1, 1], transition: { duration: 0.5, repeat: Infinity } },
};

// Modal backdrop
export const modalBackdrop: Variants = {
  initial: { opacity: 0 },
  animate: { opacity: 1, transition: { duration: 0.2 } },
  exit: { opacity: 0, transition: { duration: 0.15 } },
};

// Modal content
export const modalContent: Variants = {
  initial: { opacity: 0, scale: 0.9, y: 20 },
  animate: { opacity: 1, scale: 1, y: 0, transition: springBouncy },
  exit: { opacity: 0, scale: 0.9, y: 20, transition: tweenFast },
};

// Game over overlay
export const gameOverOverlay: Variants = {
  initial: { opacity: 0, scale: 0.6 },
  animate: { opacity: 1, scale: 1, transition: { type: 'spring', stiffness: 200, damping: 15 } },
};

// Attribute glow color map
const ATTRIBUTE_GLOW_MAP: Record<string, string> = {
  DARK: '#7c3aed',
  LIGHT: '#facc15',
  FIRE: '#ef4444',
  WATER: '#3b82f6',
  EARTH: '#92400e',
  WIND: '#22c55e',
  DIVINE: '#eab308',
};

export function attributeToGlowColor(attribute: string): string {
  return ATTRIBUTE_GLOW_MAP[attribute] || '#d4a843';
}

// Monster type to border class
const MONSTER_TYPE_BORDER_MAP: Record<string, string> = {
  Normal: 'border-ygo-gold',
  Effect: 'border-orange-500',
  Fusion: 'border-purple-500',
  Synchro: 'border-gray-300',
  Xyz: 'border-gray-700',
  Link: 'border-blue-600',
  Ritual: 'border-blue-800',
};

export function monsterTypeToBorderClass(monsterType: string): string {
  return MONSTER_TYPE_BORDER_MAP[monsterType] || 'border-ygo-gold';
}

// Monster type to background gradient
const MONSTER_TYPE_BG_MAP: Record<string, string> = {
  Normal: 'bg-gradient-to-b from-amber-800/90 to-amber-950',
  Effect: 'bg-gradient-to-b from-orange-700/90 to-orange-950',
  Fusion: 'bg-gradient-to-b from-purple-700/90 to-purple-950',
  Synchro: 'bg-gradient-to-b from-gray-100 to-gray-300 text-gray-900',
  Xyz: 'bg-gradient-to-b from-gray-800 to-gray-950',
  Link: 'bg-gradient-to-b from-blue-700/90 to-blue-950',
  Ritual: 'bg-gradient-to-b from-blue-800/90 to-blue-950',
};

export function monsterTypeToBgGradient(monsterType: string): string {
  return MONSTER_TYPE_BG_MAP[monsterType] || MONSTER_TYPE_BG_MAP.Normal;
}
