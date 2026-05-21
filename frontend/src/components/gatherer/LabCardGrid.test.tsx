/**
 * LabCardGrid smoke tests — verify the grid plate mounts, surfaces the
 * empty / no-set / no-match placeholders, and renders SketchCard cells
 * once a set + cards land in the store.
 */

import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../services/deckbuilderApi', () => ({
  gathererAPI: {
    getSets: vi.fn().mockResolvedValue({ sets: [], total: 0 }),
    getSetDetails: vi.fn().mockResolvedValue({
      code: 'WOE',
      name: 'Wilds of Eldraine',
      card_count: 281,
      release_date: '2023-09-08',
      set_type: 'standard',
      rarity_breakdown: {},
    }),
    getSetCards: vi.fn().mockResolvedValue({
      cards: [],
      total: 0,
      has_more: false,
      set_code: 'WOE',
      set_name: 'Wilds of Eldraine',
    }),
  },
}));

import { useGathererStore } from '../../stores/gathererStore';
import { LabCardGrid } from './LabCardGrid';
import type { CardDefinitionData } from '../../types/deckbuilder';
import type { SetDetail } from '../../types/gatherer';

function card(overrides: Partial<CardDefinitionData> = {}): CardDefinitionData {
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

function setDetail(): SetDetail {
  return {
    code: 'WOE',
    name: 'Wilds of Eldraine',
    card_count: 281,
    release_date: '2023-09-08',
    set_type: 'standard',
    rarity_breakdown: { mythic: 0, rare: 0, uncommon: 0, common: 0 },
  };
}

beforeEach(() => {
  useGathererStore.setState({
    sets: [],
    setsLoading: false,
    setsError: null,
    currentSet: null,
    cards: [],
    cardsTotal: 0,
    cardsLoading: false,
    cardsHasMore: false,
    filter: {},
    selectedCard: null,
  });
});

describe('LabCardGrid', () => {
  it('renders the grid plate container with the data-testid hook', () => {
    render(<LabCardGrid />);
    expect(screen.getByTestId('gatherer-card-grid')).toBeInTheDocument();
  });

  it('shows the "Pick a set." placeholder when no set is selected', () => {
    render(<LabCardGrid />);
    expect(screen.getByText('Pick a set.')).toBeInTheDocument();
    expect(screen.getByText(/pick a set →/i)).toBeInTheDocument();
  });

  it('renders the current set name + match count in the header', () => {
    useGathererStore.setState({
      currentSet: setDetail(),
      cards: [card({ name: 'Lightning Bolt' })],
      cardsTotal: 1,
    });
    render(<LabCardGrid />);
    expect(screen.getByText('Wilds of Eldraine')).toBeInTheDocument();
    expect(screen.getByText('WOE')).toBeInTheDocument();
    expect(screen.getByText(/1 card matching filters/i)).toBeInTheDocument();
  });

  it('renders SketchCard cells for each card in the store', () => {
    useGathererStore.setState({
      currentSet: setDetail(),
      cards: [
        card({ name: 'Lightning Bolt' }),
        card({ name: 'Counterspell', mana_cost: '{U}{U}', colors: ['U'] }),
      ],
      cardsTotal: 2,
    });
    render(<LabCardGrid />);
    expect(screen.getByText('Lightning Bolt')).toBeInTheDocument();
    expect(screen.getByText('Counterspell')).toBeInTheDocument();
  });

  it('dispatches selectCard when a card cell is clicked', () => {
    useGathererStore.setState({
      currentSet: setDetail(),
      cards: [card({ name: 'Lightning Bolt' })],
      cardsTotal: 1,
    });
    render(<LabCardGrid />);

    fireEvent.click(screen.getByText('Lightning Bolt'));
    expect(useGathererStore.getState().selectedCard?.name).toBe('Lightning Bolt');
  });

  it('shows the "No cards match." placeholder when a set is selected but the page is empty', () => {
    useGathererStore.setState({
      currentSet: setDetail(),
      cards: [],
      cardsLoading: false,
    });
    render(<LabCardGrid />);
    expect(screen.getByText('No cards match.')).toBeInTheDocument();
  });
});
