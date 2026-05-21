/**
 * Gatherer smoke test — Phase C / follow-up 11a lab port.
 *
 * Asserts the lab posture survives onto the MTG card-browser surface:
 *   1. Caption rail surfaces the HD-GATHERER · MTG · LIBRARY · v4.7 telemetry.
 *   2. Masthead renders the italic-serif "/ Gatherer" + a numeric card-count
 *      stamp (tabular-nums mono).
 *   3. The `01 SECTION` head + Instrument Serif title with sodium italic
 *      renders.
 *   4. The set rack lists fetched sets (sidebar lab chrome).
 *   5. The card grid plate mounts once a set is selected and renders each
 *      card row by name (real card art lives inside the SketchCard cells —
 *      that's the seam where lab chrome ends).
 *
 * Mocks `gathererAPI` so the page mounts deterministically without network.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { CardDefinitionData } from '../types/deckbuilder';

vi.mock('../services/deckbuilderApi', () => ({
  gathererAPI: {
    getSets: vi.fn(),
    getSetDetails: vi.fn(),
    getSetCards: vi.fn(),
  },
}));

import { gathererAPI } from '../services/deckbuilderApi';
import { Gatherer } from './Gatherer';

function mtgCard(overrides: Partial<CardDefinitionData> = {}): CardDefinitionData {
  return {
    name: 'Lightning Bolt',
    game: 'mtg',
    domain: null,
    mana_cost: '{R}',
    types: ['INSTANT'],
    subtypes: [],
    power: null,
    toughness: null,
    text: 'Deal 3 damage to any target.',
    colors: ['R'],
    image_url: null,
    extras: {},
    ...overrides,
  };
}

function renderGatherer() {
  return render(
    <MemoryRouter>
      <Gatherer />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(gathererAPI.getSets).mockResolvedValue({
    sets: [
      {
        code: 'WOE',
        name: 'Wilds of Eldraine',
        card_count: 281,
        release_date: '2023-09-08',
        set_type: 'standard',
      },
      {
        code: 'LCI',
        name: 'Lost Caverns of Ixalan',
        card_count: 292,
        release_date: '2023-11-17',
        set_type: 'standard',
      },
    ],
    total: 2,
  });
  vi.mocked(gathererAPI.getSetDetails).mockResolvedValue({
    code: 'WOE',
    name: 'Wilds of Eldraine',
    card_count: 281,
    release_date: '2023-09-08',
    set_type: 'standard',
    rarity_breakdown: { mythic: 20, rare: 60, uncommon: 80, common: 121 },
  });
  vi.mocked(gathererAPI.getSetCards).mockResolvedValue({
    cards: [
      mtgCard({ name: 'Lightning Bolt' }),
      mtgCard({ name: 'Counterspell', mana_cost: '{U}{U}', colors: ['U'] }),
    ],
    total: 2,
    has_more: false,
    set_code: 'WOE',
    set_name: 'Wilds of Eldraine',
  });
});

describe('Gatherer (lab posture)', () => {
  it('renders the caption rail with HD-GATHERER telemetry', () => {
    renderGatherer();
    // Caption rail is a fixed-position node at the top of the page.
    const stamp = screen.getByText('HD-GATHERER');
    expect(stamp).toBeInTheDocument();
    // The "MTG · LIBRARY · v4.7" siblings live in the same parent node — assert
    // by walking up to the rail container and matching its full text content.
    const rail = stamp.parentElement;
    expect(rail?.textContent).toMatch(/HD-GATHERER/);
    expect(rail?.textContent).toMatch(/MTG/);
    expect(rail?.textContent).toMatch(/LIBRARY/);
    expect(rail?.textContent).toMatch(/v4\.7/);
  });

  it('renders the masthead + italic-serif "/ Gatherer" + card-count stamp', async () => {
    renderGatherer();

    expect(screen.getByText('HYPERDRAFT')).toBeInTheDocument();
    expect(screen.getByText('/ Gatherer')).toBeInTheDocument();

    // The card-count stamp lives in a dedicated testid because the formatting
    // (tabular-nums mono, locale-formatted numbers) is load-bearing.
    const stamp = await screen.findByTestId('gatherer-card-count-stamp');
    expect(stamp.textContent).toMatch(/v4\.7/);
    // 281 + 292 = 573 — locale-formatted so we just assert the digits appear.
    expect(stamp.textContent).toMatch(/573/);
    expect(stamp.textContent).toMatch(/2 sets/);
  });

  it('renders the "01 Section" head with Card library. title', () => {
    renderGatherer();

    expect(screen.getByText('01')).toBeInTheDocument();
    // The h2 contains "Card library." with sodium-italic on "library".
    const heading = screen.getByRole('heading', { level: 2 });
    expect(heading.textContent).toMatch(/Card\s+library\./);
  });

  it('lists fetched sets in the lab-styled rack and loads cards on select', async () => {
    renderGatherer();

    // Wait for sets to surface in the sidebar
    await waitFor(() => {
      expect(screen.getByText('Wilds of Eldraine')).toBeInTheDocument();
    });
    expect(screen.getByText('Lost Caverns of Ixalan')).toBeInTheDocument();

    // Set-rack container carries the lab data-testid hook
    expect(screen.getByTestId('gatherer-set-rack')).toBeInTheDocument();

    // Click WOE → grid loads
    fireEvent.click(screen.getByText('Wilds of Eldraine'));

    await waitFor(() => {
      expect(screen.getByText('Lightning Bolt')).toBeInTheDocument();
    });
    expect(screen.getByText('Counterspell')).toBeInTheDocument();

    // Card-grid plate is the lab chrome around the (per-card identity) SketchCard cells.
    expect(screen.getByTestId('gatherer-card-grid')).toBeInTheDocument();
  });

  it('renders the lab footer with uvicorn port + GATHERER stamp', () => {
    renderGatherer();
    expect(screen.getByText(/uvicorn src\.server\.main:socket_app · port 8030/)).toBeInTheDocument();
    expect(screen.getByText('HYPERDRAFT · GATHERER')).toBeInTheDocument();
  });
});
