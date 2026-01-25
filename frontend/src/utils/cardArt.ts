/**
 * Card Art Utilities
 *
 * Functions for generating card art paths from card names.
 */

/**
 * Convert a card name to the snake_case filename format.
 * - "Mosswood Dreadknight" -> "mosswood_dreadknight"
 * - "Serra Angel" -> "serra_angel"
 * - Removes apostrophes and commas
 * - Replaces spaces with underscores
 */
export function cardNameToFilename(name: string): string {
  return name
    .toLowerCase()
    .replace(/[',]/g, '') // Remove apostrophes and commas
    .replace(/\s+/g, '_') // Replace spaces with underscores
    .replace(/-/g, '_') // Replace hyphens with underscores
    .replace(/_+/g, '_') // Collapse multiple underscores
    .replace(/^_|_$/g, ''); // Trim leading/trailing underscores
}

// MTG set codes used for art path generation
const MTG_SET_CODES = ['woe', 'lci', 'mkm', 'otj', 'blb', 'dsk', 'fdn', 'eoe', 'ecl', 'spm', 'tla', 'fin'];

// Custom set prefixes used for art path generation
const CUSTOM_SET_PREFIXES = ['star_wars', 'pokemon_horizons', 'studio_ghibli', 'custom'];

/**
 * Get the card art URL for a given card name.
 *
 * Since we don't have set information in the card data, we try multiple
 * possible paths and the component will handle fallback.
 *
 * @param name - The card name
 * @param setCode - Optional set code (e.g., 'woe', 'lci')
 * @param customSet - Optional custom set name (e.g., 'star_wars')
 * @returns The URL path to the card art image
 */
export function getCardArtUrl(
  name: string,
  setCode?: string,
  customSet?: string
): string {
  const filename = cardNameToFilename(name);

  // If we have a set code, use the mtg subdirectory structure
  if (setCode) {
    return `/assets/card_art/mtg/${setCode.toLowerCase()}/${filename}.png`;
  }

  // If we have a custom set, use the custom subdirectory structure
  if (customSet) {
    const setFolder = customSet.toLowerCase().replace(/\s+/g, '_');
    return `/assets/card_art/custom/${setFolder}/${filename}.png`;
  }

  // Default: try the card name directly at root level
  return `/assets/card_art/${filename}.png`;
}

/**
 * Generate all possible art paths for a card.
 * Used to try multiple locations when looking for card art.
 *
 * @param name - The card name
 * @returns Array of possible art URLs to try
 */
export function getPossibleArtPaths(name: string): string[] {
  const filename = cardNameToFilename(name);
  const paths: string[] = [];

  // 1. Try root level with just the card name
  paths.push(`/assets/card_art/${filename}.png`);

  // 2. Try common MTG set prefixes
  for (const set of MTG_SET_CODES) {
    // Try prefixed filename at root (current structure)
    paths.push(`/assets/card_art/${set}_${filename}.png`);
    // Try subdirectory structure (future structure)
    paths.push(`/assets/card_art/mtg/${set}/${filename}.png`);
  }

  // 3. Try common custom set prefixes
  for (const set of CUSTOM_SET_PREFIXES) {
    // Try prefixed filename at root (current structure)
    paths.push(`/assets/card_art/${set}_${filename}.png`);
    // Try subdirectory structure (future structure)
    paths.push(`/assets/card_art/custom/${set}/${filename}.png`);
  }

  return paths;
}

/**
 * Generate art path with set prefix.
 * Used when we know the set but files are at root level with prefixes.
 *
 * @param name - The card name
 * @param setPrefix - The set prefix (e.g., 'woe', 'star_wars')
 * @returns The URL path to the card art image
 */
export function getCardArtUrlWithPrefix(name: string, setPrefix: string): string {
  const filename = cardNameToFilename(name);
  const prefix = setPrefix.toLowerCase().replace(/\s+/g, '_');
  return `/assets/card_art/${prefix}_${filename}.png`;
}
