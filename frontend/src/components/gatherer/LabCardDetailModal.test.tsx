/**
 * LabCardDetailModal smoke tests — verify the modal mounts only when a
 * card is selected, surfaces the close affordances (button click + Escape
 * key + backdrop click), and wraps `<SketchCardDetail>` in lab chrome.
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
import { LabCardDetailModal } from './LabCardDetailModal';
import type { CardDefinitionData } from '../../types/deckbuilder';

function card(): CardDefinitionData {
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
  };
}

beforeEach(() => {
  useGathererStore.setState({
    selectedCard: null,
    currentSet: null,
  });
});

describe('LabCardDetailModal', () => {
  it('renders nothing when no card is selected', () => {
    const { container } = render(<LabCardDetailModal />);
    // The component returns null pre-selection; the wrapping div is empty.
    expect(container.firstChild).toBeNull();
  });

  it('renders the modal with role="dialog" once a card is selected', () => {
    useGathererStore.setState({ selectedCard: card() });
    render(<LabCardDetailModal />);

    const dialog = screen.getByRole('dialog');
    expect(dialog).toBeInTheDocument();
    expect(dialog).toHaveAttribute('aria-label', 'Card detail: Lightning Bolt');
  });

  it('dispatches selectCard(null) when the close button is clicked', () => {
    useGathererStore.setState({ selectedCard: card() });
    render(<LabCardDetailModal />);

    fireEvent.click(screen.getByLabelText('Close card detail'));
    expect(useGathererStore.getState().selectedCard).toBeNull();
  });

  it('dispatches selectCard(null) when the backdrop is clicked', () => {
    useGathererStore.setState({ selectedCard: card() });
    render(<LabCardDetailModal />);

    fireEvent.click(screen.getByRole('dialog'));
    expect(useGathererStore.getState().selectedCard).toBeNull();
  });

  it('closes on Escape keypress', () => {
    useGathererStore.setState({ selectedCard: card() });
    render(<LabCardDetailModal />);

    fireEvent.keyDown(document, { key: 'Escape' });
    expect(useGathererStore.getState().selectedCard).toBeNull();
  });
});
