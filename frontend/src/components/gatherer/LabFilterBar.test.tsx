/**
 * LabFilterBar / LabFilterToolbar smoke tests — verify the filter rows
 * mount, render their lab-posture controls, and dispatch the right store
 * actions on user input.
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
import { LabFilterBar, LabFilterToolbar } from './LabFilterBar';

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
    sortBy: 'name',
    sortOrder: 'asc',
    selectedCard: null,
    setTypeFilter: null,
  });
});

describe('LabFilterToolbar', () => {
  it('renders the toolbar with set-type chips and sort controls', () => {
    render(<LabFilterToolbar />);
    expect(screen.getByTestId('gatherer-toolbar')).toBeInTheDocument();
    expect(screen.getByText('All')).toBeInTheDocument();
    expect(screen.getByText('Standard')).toBeInTheDocument();
    expect(screen.getByLabelText(/Sort cards by field/i)).toBeInTheDocument();
  });

  it('dispatches setSetTypeFilter when a set-type chip is clicked', () => {
    render(<LabFilterToolbar />);
    fireEvent.click(screen.getByText('Universes Beyond'));
    expect(useGathererStore.getState().setTypeFilter).toBe('universes_beyond');
  });

  it('toggles sort order via the Asc/Desc button', () => {
    render(<LabFilterToolbar />);
    expect(useGathererStore.getState().sortOrder).toBe('asc');
    fireEvent.click(screen.getByTitle(/Ascending/i));
    expect(useGathererStore.getState().sortOrder).toBe('desc');
  });
});

describe('LabFilterBar', () => {
  it('renders the filter row with search + chips + color dots + rarity + MV inputs', () => {
    render(<LabFilterBar />);

    expect(screen.getByTestId('gatherer-filter-row')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('Search cards…')).toBeInTheDocument();
    expect(screen.getByText('Creature')).toBeInTheDocument();
    expect(screen.getByLabelText(/Filter by White/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Filter by rarity/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Minimum mana value/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Maximum mana value/i)).toBeInTheDocument();
  });

  it('toggles a card-type filter into the store on click', () => {
    render(<LabFilterBar />);
    fireEvent.click(screen.getByText('Creature'));
    expect(useGathererStore.getState().filter.types).toEqual(['CREATURE']);
  });

  it('toggles a color identity dot into the store on click', () => {
    render(<LabFilterBar />);
    fireEvent.click(screen.getByLabelText(/Filter by Red/i));
    expect(useGathererStore.getState().filter.colors).toEqual(['R']);
  });

  it('writes textSearch on form submit (not on every keystroke)', () => {
    render(<LabFilterBar />);
    const input = screen.getByPlaceholderText('Search cards…') as HTMLInputElement;

    fireEvent.change(input, { target: { value: 'lightning' } });
    // Pre-submit: store stays empty (text input is locally committed)
    expect(useGathererStore.getState().filter.textSearch).toBeUndefined();

    fireEvent.submit(input.closest('form')!);
    expect(useGathererStore.getState().filter.textSearch).toBe('lightning');
  });

  it('reveals the "Clear filters" button only when a filter is active', () => {
    const { rerender } = render(<LabFilterBar />);
    expect(screen.queryByText(/Clear filters/i)).not.toBeInTheDocument();

    useGathererStore.setState({ filter: { types: ['CREATURE'] } });
    rerender(<LabFilterBar />);
    expect(screen.getByText(/Clear filters/i)).toBeInTheDocument();
  });
});
