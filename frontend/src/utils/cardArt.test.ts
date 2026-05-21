/**
 * Card-art URL builder tests.
 *
 * Covers the Minecraft path builder, whose slug rules differ slightly
 * from `cardNameToFilename` (strips colons, parens, dots, bangs in
 * addition to apostrophes/commas). The slug must round-trip to the same
 * filename the Python backend writes via
 * `src/cards/minecraft/__init__.py::_slug`, so this test pins the
 * contract.
 */

import { describe, it, expect } from 'vitest';
import {
  getMinecraftArtPaths,
  minecraftCardNameToFilename,
} from './cardArt';

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
