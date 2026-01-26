/**
 * Card Art Utilities
 *
 * Functions for generating card art URLs using local assets and Scryfall API.
 */

/**
 * Map set codes to their folder names in assets/card_art/
 */
export const SET_CODE_TO_FOLDER: Record<string, { type: 'mtg' | 'custom'; folder: string }> = {
  // MTG Standard sets
  WOE: { type: 'mtg', folder: 'woe' },
  LCI: { type: 'mtg', folder: 'lci' },
  MKM: { type: 'mtg', folder: 'mkm' },
  OTJ: { type: 'mtg', folder: 'otj' },
  BIG: { type: 'mtg', folder: 'otj' },
  BLB: { type: 'mtg', folder: 'blb' },
  DSK: { type: 'mtg', folder: 'dsk' },
  FDN: { type: 'mtg', folder: 'fdn' },
  DFT: { type: 'mtg', folder: 'dft' },
  TKR: { type: 'mtg', folder: 'tkr' },
  // Universes Beyond
  EOE: { type: 'mtg', folder: 'mh3' },
  ECL: { type: 'mtg', folder: 'lrw' },
  SPM: { type: 'mtg', folder: 'spm' },
  TLA: { type: 'mtg', folder: 'atla' },
  FIN: { type: 'mtg', folder: 'ff' },
  // Custom sets
  TLAC: { type: 'custom', folder: 'penultimate_avatar' },
  SPMC: { type: 'custom', folder: 'man_of_pider' },
  FINC: { type: 'custom', folder: 'princess_catholicon' },
  TMH: { type: 'custom', folder: 'temporal_horizons' },
  LRW: { type: 'custom', folder: 'lorwyn_custom' },
  SWR: { type: 'custom', folder: 'star_wars' },
  DMS: { type: 'custom', folder: 'demon_slayer' },
  OPC: { type: 'custom', folder: 'one_piece' },
  PKH: { type: 'custom', folder: 'pokemon_horizons' },
  ZLD: { type: 'custom', folder: 'legend_of_zelda' },
  GHB: { type: 'custom', folder: 'studio_ghibli' },
  MHA: { type: 'custom', folder: 'my_hero_academia' },
  LTR: { type: 'custom', folder: 'lord_of_the_rings' },
  JJK: { type: 'custom', folder: 'jujutsu_kaisen' },
  AOT: { type: 'custom', folder: 'attack_on_titan' },
  HPW: { type: 'custom', folder: 'harry_potter' },
  MVL: { type: 'custom', folder: 'marvel_avengers' },
  NRT: { type: 'custom', folder: 'naruto' },
  DBZ: { type: 'custom', folder: 'dragon_ball' },
};

/**
 * Convert a card name to the snake_case filename format.
 */
export function cardNameToFilename(name: string): string {
  return name
    .toLowerCase()
    .replace(/[',]/g, '')
    .replace(/\s+/g, '_')
    .replace(/-/g, '_')
    .replace(/_+/g, '_')
    .replace(/^_|_$/g, '');
}

/**
 * Get local image URL for a card from the assets folder.
 *
 * @param cardName - The card name
 * @param setCode - The set code (e.g., 'DMS', 'WOE')
 * @returns The local image URL or null if set not mapped
 */
export function getLocalImageUrl(cardName: string, setCode: string): string | null {
  const mapping = SET_CODE_TO_FOLDER[setCode];
  if (!mapping) return null;

  const filename = cardNameToFilename(cardName);
  return `/api/card-art/${mapping.type}/${mapping.folder}/${filename}.png`;
}

/**
 * Get the Scryfall image URL for a card by name.
 *
 * @param name - The card name (exact match)
 * @param version - Image version: 'art_crop' (default), 'normal', 'small', 'large', 'png', 'border_crop'
 * @returns The Scryfall image URL
 */
export function getScryfallImageUrl(
  name: string,
  version: 'art_crop' | 'normal' | 'small' | 'large' | 'png' | 'border_crop' = 'art_crop'
): string {
  const encodedName = encodeURIComponent(name);
  return `https://api.scryfall.com/cards/named?exact=${encodedName}&format=image&version=${version}`;
}

/**
 * Get a fuzzy match Scryfall image URL.
 *
 * @param name - The card name (fuzzy match)
 * @param version - Image version
 * @returns The Scryfall image URL with fuzzy matching
 */
export function getScryfallFuzzyImageUrl(
  name: string,
  version: 'art_crop' | 'normal' | 'small' | 'large' | 'png' | 'border_crop' = 'art_crop'
): string {
  const encodedName = encodeURIComponent(name);
  return `https://api.scryfall.com/cards/named?fuzzy=${encodedName}&format=image&version=${version}`;
}

/**
 * Generate all possible art paths for a card.
 * Priority: local assets first, then Scryfall fallback.
 *
 * @param name - The card name
 * @param setCode - Optional set code for local asset lookup
 * @returns Array of possible art URLs to try
 */
export function getPossibleArtPaths(name: string, setCode?: string): string[] {
  const paths: string[] = [];

  // Try local first if setCode provided
  if (setCode) {
    const localUrl = getLocalImageUrl(name, setCode);
    if (localUrl) {
      paths.push(localUrl);
    }
  }

  // Scryfall fallbacks
  paths.push(
    getScryfallImageUrl(name, 'art_crop'),
    getScryfallFuzzyImageUrl(name, 'art_crop'),
    getScryfallImageUrl(name, 'normal'),
    getScryfallFuzzyImageUrl(name, 'small')
  );

  return paths;
}

/**
 * Get the card art URL for a given card name.
 *
 * @param name - The card name
 * @returns The Scryfall image URL
 */
export function getCardArtUrl(name: string): string {
  return getScryfallImageUrl(name, 'art_crop');
}
