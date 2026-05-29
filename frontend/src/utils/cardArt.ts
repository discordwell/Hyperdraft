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
  FBM: { type: 'custom', folder: 'fae_but_mid' },
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
    .replace(/[',:()!."]/g, '')
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
 * Get Depths (Submarine Fleet) art paths.
 *
 * Depths cards live under /api/card-art/depths/<expansion>/<slug>.png — the
 * `submarine_fleet` folder is the launch set; future Depths expansions
 * (e.g. abyssal_expanse) will sit alongside it. We try them all so the
 * <CardArt> fallback chain Just Works regardless of which expansion a card
 * came from.
 *
 * If the backend already wired an `image_url` (Depths cards do this via
 * `_wire_image_urls` in src/cards/depths/submarine_fleet/__init__.py), the
 * caller should prefer that and only use this helper as a fallback chain.
 */
export function getDepthsArtPaths(cardName: string): string[] {
  const filename = cardNameToFilename(cardName);
  return [
    `/api/card-art/depths/submarine_fleet/${filename}.png`,
    `/api/card-art/depths/abyssal_expanse/${filename}.png`,
  ];
}

/**
 * Convert a Minecraft card name to its on-disk slug.
 *
 * Matches the Python slug used by `src/cards/minecraft/__init__.py::_slug` so
 * the URL the frontend optimistically builds resolves to the same PNG the
 * backend would emit via `card_def.image_url`. Strips MTG/MC punctuation
 * (apostrophes, commas, colons, parens, dots, bangs), normalises whitespace
 * and hyphens to underscores, then collapses runs.
 */
export function minecraftCardNameToFilename(name: string): string {
  return name
    .toLowerCase()
    .replace(/['",:().!]/g, '')
    .replace(/[\s-]+/g, '_')
    .replace(/_+/g, '_')
    .replace(/^_|_$/g, '');
}

/**
 * Get Minecraft TCG art paths for a card.
 *
 * Minecraft art is rendered locally only (no Scryfall fallback — these are
 * fan-made / Minecraft-themed cards). If the backend already supplied an
 * `image_url`, the caller should prefer that and pass it as `preferred`;
 * otherwise we derive the deterministic path at
 * `/api/card-art/minecraft/<slug>.png`. Returns a deduped ordered list.
 */
export function getMinecraftArtPaths(name: string, preferred?: string | null): string[] {
  const paths: string[] = [];
  if (preferred) {
    paths.push(preferred);
  }
  const filename = minecraftCardNameToFilename(name);
  if (filename) {
    paths.push(`/api/card-art/minecraft/${filename}.png`);
  }
  return [...new Set(paths)];
}

/**
 * Get Finance TCG art paths.
 *
 * Art lives under `assets/card_art/finance/<subset>/<slug>.png` and is served
 * via `/api/card-art/finance/<subset>/<slug>.png`. The current subset folder
 * is `fina/` (FINA — Set 1: Quant & IB). FINM (Set 2) has no art yet but is
 * a future subset; passing `domain="FINM"` prefers `finm/` first.
 *
 * Priority:
 * 1. Subset folder hinted by domain (FINA → `fina/`, FINM → `finm/`)
 * 2. The other known finance subset folder as a fallback
 *
 * Unlike MTG, there is no Scryfall fallback — Finance cards are bespoke.
 */
export function getFinanceArtPaths(cardName: string, domain?: string | null): string[] {
  const filename = cardNameToFilename(cardName);
  const paths: string[] = [];
  const subsets = ['fina', 'finm'];

  // Prefer the domain-hinted subset folder first.
  const normalized = (domain || '').trim().toLowerCase();
  if (normalized && subsets.includes(normalized)) {
    paths.push(`/api/card-art/finance/${normalized}/${filename}.png`);
    for (const s of subsets) {
      if (s !== normalized) paths.push(`/api/card-art/finance/${s}/${filename}.png`);
    }
  } else {
    for (const s of subsets) {
      paths.push(`/api/card-art/finance/${s}/${filename}.png`);
    }
  }
  return paths;
}

/**
 * Get Hearthstone/variant-oriented art paths.
 *
 * Priority:
 * 1. Variant-local generated art (e.g., /api/card-art/custom/riftclash/*.png)
 * 2. Known HS variant folders
 * 3. Scryfall fallbacks
 */
export function getHearthstoneArtPaths(name: string, variant?: string | null): string[] {
  const filename = cardNameToFilename(name);
  const paths: string[] = [];

  if (variant) {
    paths.push(`/api/card-art/custom/${variant}/${filename}.png`);
  }

  // Known HS variant folders (works even if variant is null/missing).
  paths.push(
    `/api/card-art/custom/riftclash/${filename}.png`,
    `/api/card-art/custom/frierenrift/${filename}.png`,
    `/api/card-art/custom/stormrift/${filename}.png`,
    `/api/card-art/custom/hearthstone/${filename}.png`
  );

  paths.push(...getPossibleArtPaths(name));

  // De-duplicate while preserving order.
  return [...new Set(paths)];
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

/**
 * Get Cats-engine art paths for a card name.
 *
 * NOTE: As of this commit there is no card art on disk for the Cats engine —
 * `assets/card_art/cats/` does not exist. The board (`frontend/src/games/cats.tsx`)
 * renders cards using inline SVG glyphs via `TypeGlyph`/`CategoryGlyph`/`MoodGlyph`,
 * and intentionally has no `<img>` slot today.
 *
 * This helper exists as the seam where art lookup will plug in once the
 * Cats set ships PNGs. The intended URL pattern mirrors other engines:
 *   `/api/card-art/cats/<snake_case_name>.png`
 *
 * When art lands:
 *   1. Drop PNGs into `assets/card_art/cats/` (server static mount at
 *      `src/server/main.py` already serves any new folder there).
 *   2. Add an `<img src>` slot inside `CatCard`'s art area in
 *      `frontend/src/games/cats.tsx` (currently the `TypeGlyph` block,
 *      ~line 1109), falling back to the existing `TypeGlyph` on load error
 *      via the same pattern as `components/cards/Card.tsx::CardArt`.
 *   3. Flip this helper to return real paths.
 *
 * Until then this returns an empty array so any future caller can wire
 * the seam without a second cardArt.ts edit.
 *
 * @param name - The card name (unused while no art exists)
 * @returns Empty array (no art on disk yet)
 */
export function getCatsArtPaths(_name: string): string[] {
  // Intentionally empty: no Cats card art exists on disk.
  // See JSDoc above for the path pattern to use once PNGs land.
  void _name;
  return [];
}
