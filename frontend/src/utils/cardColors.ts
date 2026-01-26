/**
 * Card Color Utilities
 *
 * Functions for determining card color styling based on colors and types.
 */

/**
 * Color stripe/bar Tailwind classes for card identity
 */
export const COLOR_STRIPE_CLASSES: Record<string, string> = {
  W: 'bg-card-white',
  WHITE: 'bg-card-white',
  U: 'bg-card-blue',
  BLUE: 'bg-card-blue',
  B: 'bg-card-black',
  BLACK: 'bg-card-black',
  R: 'bg-card-red',
  RED: 'bg-card-red',
  G: 'bg-card-green',
  GREEN: 'bg-card-green',
};

/**
 * Get the Tailwind class for a card's color stripe/bar.
 *
 * @param colors - Array of color identities (e.g., ['WHITE', 'BLUE'])
 * @param types - Array of card types (e.g., ['CREATURE', 'LAND'])
 * @returns Tailwind background class
 */
export function getCardColorClass(colors: string[], types: string[]): string {
  // Lands get a special color
  if (types.some(t => t.toUpperCase() === 'LAND')) {
    return 'bg-card-land';
  }

  // Colorless
  if (colors.length === 0) {
    return 'bg-card-colorless';
  }

  // Multicolor (gold)
  if (colors.length > 1) {
    return 'bg-card-gold';
  }

  // Single color
  return COLOR_STRIPE_CLASSES[colors[0]] || COLOR_STRIPE_CLASSES[colors[0].toUpperCase()] || 'bg-card-colorless';
}

/**
 * Get a gradient class for multicolor cards (used in modal detail view).
 *
 * @param colors - Array of color identities
 * @param types - Array of card types
 * @returns Tailwind background/gradient class
 */
export function getCardColorGradient(colors: string[], types: string[]): string {
  if (types.some(t => t.toUpperCase() === 'LAND')) {
    return 'bg-card-land';
  }

  if (colors.length === 0) {
    return 'bg-card-colorless';
  }

  if (colors.length > 1) {
    return 'bg-gradient-to-r from-card-gold via-amber-300 to-card-gold';
  }

  return COLOR_STRIPE_CLASSES[colors[0]] || COLOR_STRIPE_CLASSES[colors[0].toUpperCase()] || 'bg-card-colorless';
}

/**
 * Get hex color for a mana color (for non-Tailwind uses).
 */
export const MANA_HEX_COLORS: Record<string, string> = {
  W: '#f9e4a8',
  WHITE: '#f9e4a8',
  U: '#6b9bc4',
  BLUE: '#6b9bc4',
  B: '#4a4a4a',
  BLACK: '#4a4a4a',
  R: '#d4694a',
  RED: '#d4694a',
  G: '#5d8c5a',
  GREEN: '#5d8c5a',
};

/**
 * Get hex color for a card's primary color.
 */
export function getCardPrimaryHex(colors: string[]): string {
  if (colors.length === 0) return '#9e9e9e'; // colorless
  if (colors.length > 1) return '#c4a446'; // gold
  return MANA_HEX_COLORS[colors[0]] || MANA_HEX_COLORS[colors[0].toUpperCase()] || '#9e9e9e';
}
