/**
 * PokemonGatherer smoke test — lab-port (buildplan follow-up 11b).
 *
 * Asserts the page mounts with the new lab posture:
 *   1. Caption rail + masthead render the HYPERDRAFT mark and the
 *      "/ Pokémon Gatherer" italic-serif slash.
 *   2. The card-grid container is present (testid `pokemon-gatherer-grid`),
 *      proving the body lives inside lab chrome.
 *
 * Mocks the deckbuilderApi pokemonGathererAPI surface so the store hits the
 * happy path with one fake set + a card, populating the grid; otherwise the
 * grid would only render the "Pick a Pokémon set" empty-state — fine for
 * masthead assertions but doesn't prove the grid wiring.
 */

import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../services/deckbuilderApi', () => ({
  pokemonGathererAPI: {
    getSets: vi.fn(),
    getSetDetails: vi.fn(),
    getSetCards: vi.fn(),
  },
}));

import { pokemonGathererAPI } from '../services/deckbuilderApi';
import { usePokemonGathererStore } from '../stores/pokemonGathererStore';
import { PokemonGatherer } from './PokemonGatherer';

function renderPage() {
  return render(
    <MemoryRouter>
      <PokemonGatherer />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  // Reset the zustand store between tests so previous selections don't leak
  // (matchers like getByText('SV Starter') would otherwise fire on stale
  // currentSet state if a prior test populated it).
  usePokemonGathererStore.setState({
    sets: [],
    setsLoading: false,
    setsError: null,
    currentSet: null,
    currentSetLoading: false,
    cards: [],
    cardsTotal: 0,
    cardsLoading: false,
    cardsHasMore: false,
    filter: {},
    sortBy: 'name',
    sortOrder: 'asc',
    selectedCard: null,
    setTypeFilter: null,
  });

  vi.mocked(pokemonGathererAPI.getSets).mockResolvedValue({
    sets: [
      {
        code: 'SVS',
        name: 'SV Starter',
        card_count: 41,
        release_date: '2024-01-01',
        set_type: 'starter',
      },
    ],
    total: 1,
  });
  vi.mocked(pokemonGathererAPI.getSetDetails).mockResolvedValue({
    code: 'SVS',
    name: 'SV Starter',
    card_count: 41,
    release_date: '2024-01-01',
    set_type: 'starter',
    supertype_breakdown: { Pokemon: 21, Trainer: 12, Energy: 8 },
    type_breakdown: { G: 5, R: 5 },
    guilds: [],
  });
  vi.mocked(pokemonGathererAPI.getSetCards).mockResolvedValue({
    cards: [],
    total: 0,
    has_more: false,
  });
});

afterEach(() => {
  vi.clearAllMocks();
});

describe('PokemonGatherer (lab posture)', () => {
  it('renders the lab masthead with the HYPERDRAFT mark and italic Gatherer slash', async () => {
    renderPage();

    // Wait until the sets fetch settles so the masthead's "1 sets" stamp has
    // the real count rather than the initial "0 sets".
    await waitFor(() => {
      expect(pokemonGathererAPI.getSets).toHaveBeenCalled();
    });

    // Caption rail
    expect(screen.getByText('HD-PKM-GATHERER')).toBeInTheDocument();

    // Masthead — HYPERDRAFT mark + the italic "Gatherer" slash. The masthead
    // headline splits "/ Pokémon" + an <em>Gatherer</em> across two nodes;
    // the caption rail also matches /Gatherer/ via HD-PKM-GATHERER, so use
    // getAllByText and just assert both nodes are present.
    expect(screen.getByText('HYPERDRAFT')).toBeInTheDocument();
    expect(screen.getAllByText(/Gatherer/).length).toBeGreaterThanOrEqual(2);
    // Exact-match assertion on the italic word — the <em>Gatherer</em> in
    // the masthead title is the only node where the bare word appears alone.
    expect(screen.getByText('Gatherer')).toBeInTheDocument();
  });

  it('mounts the card-grid container inside lab chrome', () => {
    renderPage();

    // The body of the page — where real Pokemon card art renders verbatim —
    // is the data-testid grid container. Its presence proves the lab page
    // wired through to the card surface (even with zero cards in the
    // current empty-state).
    expect(screen.getByTestId('pokemon-gatherer-grid')).toBeInTheDocument();
  });
});
