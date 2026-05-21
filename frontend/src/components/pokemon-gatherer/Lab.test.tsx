/**
 * Smoke tests for the Lab* sub-components extracted out of PokemonGatherer.tsx.
 *
 * Each component reads zustand state directly, so the tests prime the store
 * with a tiny happy-path fixture (one set, no cards) and assert each sub-
 * component mounts with its data-testid + the expected lab-chrome label.
 *
 * These are deliberately *smoke* — they prove the wiring of state → JSX, not
 * the chrome's exact pixels. The page-level PokemonGatherer.test.tsx already
 * covers the masthead end-to-end render.
 */

import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../services/deckbuilderApi', () => ({
  pokemonGathererAPI: {
    getSets: vi.fn(),
    getSetDetails: vi.fn(),
    getSetCards: vi.fn(),
  },
}));

import { usePokemonGathererStore } from '../../stores/pokemonGathererStore';
import { LabSetRack } from './LabSetRack';
import { LabFilterBar } from './LabFilterBar';
import { LabCardGrid } from './LabCardGrid';
import { LabPaginationFooter } from './LabPaginationFooter';
import type { PokemonCardData } from '../../types/pokemonGatherer';

const fixtureSet = {
  code: 'SVS',
  name: 'SV Starter',
  card_count: 41,
  release_date: '2024-01-01',
  set_type: 'starter' as const,
};

const fixtureSetDetail = {
  ...fixtureSet,
  supertype_breakdown: { Pokemon: 21, Trainer: 12, Energy: 8 },
  type_breakdown: { G: 5, R: 5 },
  guilds: [],
};

const fixtureCard: PokemonCardData = {
  name: 'Pikachu',
  supertype: 'Pokemon',
  trainer_subtype: null,
  text: '',
  rarity: 'Common',
  image_url: null,
  guild: null,
  hp: 60,
  pokemon_type: 'L',
  evolution_stage: 'Basic',
  evolves_from: null,
  weakness_type: 'F',
  weakness_modifier: 'x2',
  resistance_type: null,
  resistance_modifier: null,
  retreat_cost: 1,
  is_ex: false,
  rule_box: null,
  prize_count: 1,
  attacks: [],
  ability: null,
  energy_type: 'L',
};

beforeEach(() => {
  usePokemonGathererStore.setState({
    sets: [fixtureSet],
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
});

describe('LabSetRack', () => {
  it('mounts the set-rack with the Sets eyebrow + chip filters', () => {
    render(<LabSetRack />);

    expect(screen.getByTestId('pokemon-gatherer-set-rack')).toBeInTheDocument();
    // Lab-eyebrow header
    expect(screen.getByText('Sets')).toBeInTheDocument();
    // Set-type chips
    expect(screen.getByRole('button', { name: 'All' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Starter' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Beyond' })).toBeInTheDocument();
    // The fixture set should render as a row
    expect(screen.getByText('SV Starter')).toBeInTheDocument();
  });
});

describe('LabFilterBar', () => {
  it('mounts the filter bar with the Sort label and a "Select a set" header line when no set is picked', () => {
    render(<LabFilterBar />);

    expect(screen.getByTestId('pokemon-gatherer-filter-bar')).toBeInTheDocument();
    expect(screen.getByText('Select a set')).toBeInTheDocument();
    expect(screen.getByText('Sort')).toBeInTheDocument();
  });

  it('exposes the energy-type swatch row + supertype chips once a set is selected', () => {
    usePokemonGathererStore.setState({ currentSet: fixtureSetDetail });
    render(<LabFilterBar />);

    // Set name is now in the header line
    expect(screen.getByText('SV Starter')).toBeInTheDocument();
    // Search field
    expect(screen.getByPlaceholderText('Search Pokémon…')).toBeInTheDocument();
    // Supertype chips (Category group label appears twice — once as the
    // FilterGroup eyebrow, once as a Sort <option> — so just assert both
    // mounts are present.)
    expect(screen.getAllByText('Category').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByRole('button', { name: 'Pokemon' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Trainer' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Energy' })).toBeInTheDocument();
    // Energy-type swatches keep their per-card colors — each rendered as a
    // titled button with the type label.
    expect(screen.getByTitle('Grass')).toBeInTheDocument();
    expect(screen.getByTitle('Fire')).toBeInTheDocument();
    expect(screen.getByTitle('Lightning')).toBeInTheDocument();
  });
});

describe('LabCardGrid', () => {
  it('renders the empty-state when no set is selected', () => {
    render(<LabCardGrid />);

    expect(screen.getByTestId('pokemon-gatherer-grid')).toBeInTheDocument();
    expect(screen.getByText('Pick a Pokémon set from the rack')).toBeInTheDocument();
  });

  it('renders cells when a set is selected and cards exist', () => {
    usePokemonGathererStore.setState({
      currentSet: fixtureSetDetail,
      cards: [fixtureCard],
      cardsTotal: 1,
    });
    render(<LabCardGrid />);

    expect(screen.getByTestId('pokemon-gatherer-grid')).toBeInTheDocument();
    // One PokemonCardCell rendered for Pikachu — its accessible name comes
    // from the title attribute on the cell button.
    expect(screen.getByTitle('Pikachu')).toBeInTheDocument();
  });

  it('passes the footer slot through into the panel', () => {
    usePokemonGathererStore.setState({
      currentSet: fixtureSetDetail,
      cards: [fixtureCard],
      cardsTotal: 1,
    });
    render(<LabCardGrid footer={<div data-testid="lab-grid-footer-slot">footer</div>} />);

    expect(screen.getByTestId('lab-grid-footer-slot')).toBeInTheDocument();
  });
});

describe('LabPaginationFooter', () => {
  it('renders nothing when no set is selected', () => {
    const { container } = render(<LabPaginationFooter />);
    expect(container.firstChild).toBeNull();
  });

  it('renders the count line + load-more button when cards exist and more remain', () => {
    usePokemonGathererStore.setState({
      currentSet: fixtureSetDetail,
      cards: [fixtureCard],
      cardsTotal: 30,
      cardsHasMore: true,
    });
    render(<LabPaginationFooter />);

    expect(screen.getByTestId('pokemon-gatherer-pagination')).toBeInTheDocument();
    expect(screen.getByText(/Showing 1 of 30/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Load more/ })).toBeInTheDocument();
  });

  it('renders "End of set" when no more cards remain', () => {
    usePokemonGathererStore.setState({
      currentSet: fixtureSetDetail,
      cards: [fixtureCard],
      cardsTotal: 1,
      cardsHasMore: false,
    });
    render(<LabPaginationFooter />);

    expect(screen.getByText('End of set')).toBeInTheDocument();
  });
});
