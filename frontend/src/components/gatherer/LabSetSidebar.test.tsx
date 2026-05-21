/**
 * LabSetSidebar smoke tests — verify the lab-posture set rack renders
 * grouped sets, surfaces loading / error states, and dispatches the
 * `selectSet` store action when a set is clicked.
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
import { LabSetSidebar } from './LabSetSidebar';
import type { SetInfo } from '../../types/gatherer';

function setInfo(overrides: Partial<SetInfo> = {}): SetInfo {
  return {
    code: 'WOE',
    name: 'Wilds of Eldraine',
    card_count: 281,
    release_date: '2023-09-08',
    set_type: 'standard',
    ...overrides,
  };
}

beforeEach(() => {
  // Reset Zustand store between tests so prior sets don't leak.
  useGathererStore.setState({
    sets: [],
    setsLoading: false,
    setsError: null,
    currentSet: null,
    setTypeFilter: null,
  });
});

describe('LabSetSidebar', () => {
  it('renders the lab-posture rack container with the data-testid hook', () => {
    render(<LabSetSidebar />);
    expect(screen.getByTestId('gatherer-set-rack')).toBeInTheDocument();
  });

  it('groups sets by type under their SET_TYPE_INFO labels', () => {
    useGathererStore.setState({
      sets: [
        setInfo({ code: 'WOE', name: 'Wilds of Eldraine', set_type: 'standard' }),
        setInfo({ code: 'SPM', name: 'Spider-Man', set_type: 'universes_beyond' }),
      ],
    });

    render(<LabSetSidebar />);

    // Both sets surface in the rack
    expect(screen.getByText('Wilds of Eldraine')).toBeInTheDocument();
    expect(screen.getByText('Spider-Man')).toBeInTheDocument();
    // Group headers appear above their members
    expect(screen.getByText('Standard')).toBeInTheDocument();
    expect(screen.getByText('Universes Beyond')).toBeInTheDocument();
  });

  it('shows the loading pulse while sets fetch', () => {
    useGathererStore.setState({ setsLoading: true });
    render(<LabSetSidebar />);
    expect(screen.getByText(/Loading sets…/i)).toBeInTheDocument();
  });

  it('shows an error banner when fetch fails', () => {
    useGathererStore.setState({ setsError: 'Network down' });
    render(<LabSetSidebar />);
    expect(screen.getByText('Network down')).toBeInTheDocument();
  });

  it('dispatches selectSet via store action when a set is clicked', () => {
    useGathererStore.setState({
      sets: [setInfo({ code: 'WOE', name: 'Wilds of Eldraine' })],
    });

    render(<LabSetSidebar />);
    fireEvent.click(screen.getByText('Wilds of Eldraine'));

    // selectSet kicks the store into currentSetLoading=true synchronously
    // (before the async API call resolves). We don't need to mock the API
    // here — just confirm the click reached the store path.
    expect(useGathererStore.getState().currentSetLoading).toBe(true);
  });
});
