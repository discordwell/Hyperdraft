/**
 * Pokemon TCG Animation Utilities
 *
 * Shared motion variants and helpers for framer-motion animations.
 */

import type { Variants, Transition } from 'framer-motion';

// Spring presets
export const springSnappy: Transition = { type: 'spring', stiffness: 500, damping: 30 };
export const springBouncy: Transition = { type: 'spring', stiffness: 300, damping: 20 };
export const springGentle: Transition = { type: 'spring', stiffness: 200, damping: 25 };
export const tweenFast: Transition = { type: 'tween', duration: 0.2, ease: 'easeOut' };
export const tweenSmooth: Transition = { type: 'tween', duration: 0.35, ease: 'easeInOut' };

// Card enter/exit
export const cardEnter: Variants = {
  initial: { opacity: 0, scale: 0.8, y: 20 },
  animate: { opacity: 1, scale: 1, y: 0, transition: springBouncy },
  exit: { opacity: 0, scale: 0.8, y: -20, transition: tweenFast },
};

// Hand card stagger
export const handStagger: Variants = {
  animate: {
    transition: { staggerChildren: 0.05 },
  },
};

export const handCard: Variants = {
  initial: { opacity: 0, y: 30 },
  animate: { opacity: 1, y: 0, transition: springGentle },
  exit: { opacity: 0, y: 30, transition: tweenFast },
};

// Bench slide
export const benchSlide: Variants = {
  initial: { opacity: 0, x: -30, scale: 0.9 },
  animate: { opacity: 1, x: 0, scale: 1, transition: springSnappy },
  exit: { opacity: 0, x: 30, scale: 0.9, transition: tweenFast },
};

// KO spin out
export const koSpin: Variants = {
  initial: { opacity: 1, scale: 1, rotate: 0 },
  exit: { opacity: 0, scale: 0.3, rotate: 180, transition: { duration: 0.6, ease: 'easeIn' } },
};

// Turn banner
export const turnBanner: Variants = {
  initial: { opacity: 0, y: -60, scale: 0.8 },
  animate: { opacity: 1, y: 0, scale: 1, transition: springBouncy },
  exit: { opacity: 0, y: -60, scale: 0.8, transition: tweenFast },
};

// Damage flash
export const damageFlash: Variants = {
  initial: { scale: 1 },
  flash: { scale: [1, 1.3, 1], transition: { duration: 0.3 } },
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

// Prize card flip
export const prizeFlip: Variants = {
  faceDown: { rotateY: 180 },
  faceUp: { rotateY: 0, transition: { duration: 0.5, ease: 'easeOut' } },
};

// Type code to glow color
const TYPE_GLOW_MAP: Record<string, string> = {
  G: '#4CAF50',
  R: '#F44336',
  W: '#2196F3',
  L: '#FFC107',
  P: '#9C27B0',
  F: '#D84315',
  D: '#616161',
  M: '#9E9E9E',
  N: '#FF8F00',
  C: '#BDBDBD',
};

export function typeToGlowColor(typeCode: string): string {
  return TYPE_GLOW_MAP[typeCode] || TYPE_GLOW_MAP.C;
}

// Type code to border color class
const TYPE_BORDER_MAP: Record<string, string> = {
  G: 'border-green-500',
  R: 'border-red-500',
  W: 'border-blue-400',
  L: 'border-yellow-400',
  P: 'border-purple-500',
  F: 'border-orange-600',
  D: 'border-gray-600',
  M: 'border-gray-400',
  N: 'border-amber-500',
  C: 'border-gray-400',
};

export function typeToBorderClass(typeCode: string): string {
  return TYPE_BORDER_MAP[typeCode] || TYPE_BORDER_MAP.C;
}

// Type code to bg color class
const TYPE_BG_MAP: Record<string, string> = {
  G: 'bg-green-600',
  R: 'bg-red-600',
  W: 'bg-blue-500',
  L: 'bg-yellow-400',
  P: 'bg-purple-500',
  F: 'bg-orange-700',
  D: 'bg-gray-800',
  M: 'bg-gray-400',
  N: 'bg-amber-600',
  C: 'bg-gray-300',
};

export function typeToBgClass(typeCode: string): string {
  return TYPE_BG_MAP[typeCode] || TYPE_BG_MAP.C;
}
