/**
 * LabPaginationFooter smoke tests — verify the load-more affordance,
 * streaming pulse, and terminal "Showing all" stamp surface based on
 * `cards.length` / `cardsLoading` / `cardsHasMore`.
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
import { LabPaginationFooter } from './LabPaginationFooter';
import type { CardDefinitionData } from '../../types/deckbuilder';
import type { SetDetail } from '../../types/gatherer';

function card(name = 'Lightning Bolt'): CardDefinitionData {
  return {
    name,
    game: 'mtg',
    domain: null,
    mana_cost: '{R}',
    types: ['INSTANT'],
    subtypes: [],
    power: null,
    toughness: null,
    text: '',
    colors: ['R'],
    image_url: null,
    extras: {},
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
    currentSet: null,
    cards: [],
    cardsLoading: false,
    cardsHasMore: false,
  });
});

describe('LabPaginationFooter', () => {
  it('renders nothing user-visible when the card list is empty', () => {
    render(<LabPaginationFooter />);
    expect(screen.queryByText(/Loading more/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Load more/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Showing all/i)).not.toBeInTheDocument();
  });

  it('shows the "Load more" button when more pages remain', () => {
    useGathererStore.setState({
      currentSet: setDetail(),
      cards: [card('A'), card('B')],
      cardsHasMore: true,
      cardsLoading: false,
    });
    render(<LabPaginationFooter />);
    expect(screen.getByRole('button', { name: /Load more/i })).toBeInTheDocument();
  });

  it('shows the streaming pulse while loading more cards', () => {
    useGathererStore.setState({
      currentSet: setDetail(),
      cards: [card('A')],
      cardsHasMore: true,
      cardsLoading: true,
    });
    render(<LabPaginationFooter />);
    expect(screen.getByText(/Loading more…/i)).toBeInTheDocument();
  });

  it('shows the terminal "Showing all" stamp once the page is complete', () => {
    useGathererStore.setState({
      currentSet: setDetail(),
      cards: [card('A'), card('B')],
      cardsHasMore: false,
      cardsLoading: false,
    });
    render(<LabPaginationFooter />);
    expect(screen.getByText(/Showing all 2/i)).toBeInTheDocument();
  });

  it('dispatches loadMoreCards on explicit "Load more" click', () => {
    const loadMoreCards = vi.fn();
    useGathererStore.setState({
      currentSet: setDetail(),
      cards: [card('A')],
      cardsHasMore: true,
      cardsLoading: false,
      loadMoreCards,
    });
    render(<LabPaginationFooter />);

    fireEvent.click(screen.getByRole('button', { name: /Load more/i }));
    expect(loadMoreCards).toHaveBeenCalled();
  });
});
