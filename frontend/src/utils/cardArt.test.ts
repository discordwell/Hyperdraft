/**
 * cardArt — engine-specific art-resolution helper tests.
 *
 * Each engine's slug rules + URL chain are pinned here so the URL the
 * frontend optimistically builds matches the PNG the Python backend
 * writes via its own `_slug` / `_wire_image_urls` logic. The Depths,
 * Minecraft, and Finance helpers are tested side-by-side; Cats has no
 * art on disk yet and its stub is exercised in the audit branch only.
 */

import { describe, expect, it } from 'vitest';

import {
  cardNameToFilename,
  getDepthsArtPaths,
  getMinecraftArtPaths,
  minecraftCardNameToFilename,
} from './cardArt';

// ── cardNameToFilename (the shared MTG/Depths slug) ─────────────────────

describe('cardNameToFilename', () => {
  it('lowercases and snake_cases plain names', () => {
    expect(cardNameToFilename('Acoustic Decoy')).toBe('acoustic_decoy');
  });

  it("strips apostrophes (Captain's Bell)", () => {
    expect(cardNameToFilename("Captain's Bell")).toBe('captains_bell');
  });

  it('replaces hyphens with underscores (Anti-Sub Drone)', () => {
    expect(cardNameToFilename('Anti-Sub Drone')).toBe('anti_sub_drone');
  });

  it('handles names with X-7 style codes (Black Demon X-7)', () => {
    expect(cardNameToFilename('Black Demon X-7')).toBe('black_demon_x_7');
  });

  it('preserves non-ASCII characters lowercased (Admiral Dönitz)', () => {
    // The art file on disk is admiral_dönitz.png — lower() preserves ö.
    expect(cardNameToFilename('Admiral Dönitz')).toBe('admiral_dönitz');
  });

  it('strips punctuation marks that appear in card titles', () => {
    expect(cardNameToFilename('Brace for Impact!')).toBe('brace_for_impact');
  });
});

// ── Depths ─────────────────────────────────────────────────────────────

describe('getDepthsArtPaths', () => {
  it('returns submarine_fleet first, then abyssal_expanse', () => {
    expect(getDepthsArtPaths('Acoustic Decoy')).toEqual([
      '/api/card-art/depths/submarine_fleet/acoustic_decoy.png',
      '/api/card-art/depths/abyssal_expanse/acoustic_decoy.png',
    ]);
  });

  it('uses the cardNameToFilename slug in each candidate URL', () => {
    const paths = getDepthsArtPaths("Captain's Bell");
    expect(paths[0]).toBe('/api/card-art/depths/submarine_fleet/captains_bell.png');
  });
});

// ── Minecraft ──────────────────────────────────────────────────────────

describe('minecraftCardNameToFilename', () => {
  it('lower-snake_cases a multi-word title', () => {
    expect(minecraftCardNameToFilename('Lantern of the Lost')).toBe('lantern_of_the_lost');
  });

  it('strips apostrophes and commas, collapses runs', () => {
    expect(minecraftCardNameToFilename("Steve's Helper")).toBe('steves_helper');
    expect(minecraftCardNameToFilename('Glissa, the Traitor')).toBe('glissa_the_traitor');
  });

  it('strips colons, parens, dots, bangs', () => {
    expect(minecraftCardNameToFilename('Atraxa: Grand Unifier')).toBe('atraxa_grand_unifier');
    expect(minecraftCardNameToFilename('Sheoldred (Whispering)')).toBe('sheoldred_whispering');
    expect(minecraftCardNameToFilename('Boom!')).toBe('boom');
  });

  it('treats hyphens like spaces', () => {
    expect(minecraftCardNameToFilename('Sleep-Stealer')).toBe('sleep_stealer');
  });
});

describe('getMinecraftArtPaths', () => {
  it('returns the canonical /api/card-art/minecraft path for a known card', () => {
    const paths = getMinecraftArtPaths('Lantern of the Lost');
    expect(paths).toContain('/api/card-art/minecraft/lantern_of_the_lost.png');
  });

  it('prefers a backend-supplied image_url when provided', () => {
    const paths = getMinecraftArtPaths(
      'Lantern of the Lost',
      '/api/card-art/minecraft/lantern_of_the_lost.png',
    );
    // Backend URL leads the list; derived URL is deduped.
    expect(paths[0]).toBe('/api/card-art/minecraft/lantern_of_the_lost.png');
    expect(paths).toHaveLength(1);
  });

  it('keeps a divergent backend URL ahead of the derived fallback', () => {
    const paths = getMinecraftArtPaths(
      'Lantern of the Lost',
      '/cdn/special/lantern.png',
    );
    expect(paths).toEqual([
      '/cdn/special/lantern.png',
      '/api/card-art/minecraft/lantern_of_the_lost.png',
    ]);
  });

  it('returns at least the derived path for any non-empty name', () => {
    const paths = getMinecraftArtPaths('Bed');
    expect(paths).toEqual(['/api/card-art/minecraft/bed.png']);
  });
});
