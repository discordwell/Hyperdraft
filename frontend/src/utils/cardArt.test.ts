/**
 * cardArt — unit tests for engine-specific path builders.
 *
 * Focused on the Finance path builder added for Finance card art rendering.
 * Confirms:
 *  - Card name slugification matches the on-disk PNG naming convention
 *    (e.g. "Flash Crash Bot" → flash_crash_bot.png).
 *  - The FINA domain prefers the `fina/` subfolder; FINM prefers `finm/`.
 *  - No domain hint defaults to FINA-first (the only folder with art today).
 *  - Other subset folders appear as fallbacks for resilience.
 */
import { describe, expect, it } from 'vitest';

import { cardNameToFilename, getFinanceArtPaths } from './cardArt';

describe('cardNameToFilename', () => {
  it('lowercases and snake-cases', () => {
    expect(cardNameToFilename('Flash Crash Bot')).toBe('flash_crash_bot');
  });

  it('strips apostrophes and commas', () => {
    expect(cardNameToFilename("Trader's Edge, Inc")).toBe('traders_edge_inc');
  });

  it('collapses repeated separators', () => {
    expect(cardNameToFilename('Pump-and-Dump')).toBe('pump_and_dump');
  });
});

describe('getFinanceArtPaths', () => {
  it('builds /api/card-art/finance/fina/<slug>.png as the primary path with no domain hint', () => {
    const paths = getFinanceArtPaths('Flash Crash Bot');
    expect(paths[0]).toBe('/api/card-art/finance/fina/flash_crash_bot.png');
    // finm subset should follow as fallback so future FINM art lands somewhere.
    expect(paths).toContain('/api/card-art/finance/finm/flash_crash_bot.png');
  });

  it('prefers the FINM folder when domain="FINM"', () => {
    const paths = getFinanceArtPaths('Acme Holdings', 'FINM');
    expect(paths[0]).toBe('/api/card-art/finance/finm/acme_holdings.png');
    // FINA still appears so that a card mis-labelled with the wrong domain
    // can still resolve to whichever subset actually owns the PNG.
    expect(paths).toContain('/api/card-art/finance/fina/acme_holdings.png');
  });

  it('prefers the FINA folder when domain="FINA"', () => {
    const paths = getFinanceArtPaths('Capital Call', 'FINA');
    expect(paths[0]).toBe('/api/card-art/finance/fina/capital_call.png');
  });

  it('ignores unknown domain values and falls back to default ordering', () => {
    const paths = getFinanceArtPaths('Dark Pool Architect', 'TOKEN');
    expect(paths[0]).toBe('/api/card-art/finance/fina/dark_pool_architect.png');
  });
});
