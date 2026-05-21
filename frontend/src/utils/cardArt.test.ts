/**
 * cardArt — Depths art-resolution helper tests.
 *
 * The Depths engine wires art under /api/card-art/depths/<expansion>/<slug>.png.
 * getDepthsArtPaths() returns the candidate URL chain for a card name; the
 * <DepthsArt> component walks the list and falls back to a sonar glyph if
 * every candidate 404s.
 */
import { describe, expect, it } from 'vitest';

import { cardNameToFilename, getDepthsArtPaths } from './cardArt';

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
