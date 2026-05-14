/**
 * GameBoard overlay-mode targeting tests (Phase 5b polish).
 *
 * When an overlay-mode ``PendingChoice`` is active, GameBoard intercepts
 * clicks on legal targets and submits the choice directly via
 * ``onSubmitOverlayChoice``. Clicks on non-target cards fall through to
 * the regular ``onCardClick`` handler.
 *
 * The test stubs the surface ChoiceModal/ChoiceModal-related deps that
 * GameBoard pulls in transitively (battlefield events / card preview /
 * drag-drop store) by rendering against the real implementations — these
 * have no API or browser-only side effects beyond happy-dom.
 */

import { describe, it, expect, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { GameBoard } from './GameBoard';
import type { GameState, CardData, PendingChoice } from '../../types';

function makeCard(overrides: Partial<CardData> & { id: string; name: string; controller: string }): CardData {
  return {
    domain: null,
    mana_cost: '{2}',
    types: ['CREATURE'],
    subtypes: [],
    power: 2,
    toughness: 2,
    text: '',
    tapped: false,
    counters: {},
    damage: 0,
    owner: overrides.controller,
    ...overrides,
  } as CardData;
}

const bears = makeCard({ id: 'card-bears', name: 'Grizzly Bears', controller: 'alice' });
const elves = makeCard({ id: 'card-elves', name: 'Llanowar Elves', controller: 'bob' });

const baseState: GameState = {
  match_id: 'm1',
  turn_number: 1,
  phase: 'PRECOMBAT_MAIN',
  step: 'MAIN',
  active_player: 'alice',
  priority_player: 'alice',
  players: {
    alice: { id: 'alice', name: 'Alice', life: 20, has_lost: false, hand_size: 0, library_size: 50 },
    bob: { id: 'bob', name: 'Bob', life: 20, has_lost: false, hand_size: 0, library_size: 50 },
  },
  battlefield: [bears, elves],
  stack: [],
  pending_triggers: [],
  hand: [],
  graveyard: { alice: [], bob: [] },
  legal_actions: [{
    type: 'PASS',
    card_id: null,
    ability_id: null,
    source_id: null,
    description: 'Pass priority',
    requires_targets: false,
    requires_mana: false,
  }],
  combat: null,
  is_game_over: false,
  winner: null,
};

const overlayChoice: PendingChoice = {
  id: 'pc-1',
  choice_type: 'target',
  player: 'alice',
  prompt: 'Choose a creature to bolt',
  options: [
    { id: 'card-elves', label: 'Llanowar Elves' },
    { id: 'bob', label: 'Bob' },
  ],
  source_id: 'spell-1',
  min_choices: 1,
  max_choices: 1,
  interaction_mode: 'overlay',
};

describe('GameBoard overlay-mode targeting', () => {
  it('clicking a legal target card submits the choice and does NOT trigger onCardClick', () => {
    const onCardClick = vi.fn();
    const onSubmitOverlayChoice = vi.fn();

    render(
      <GameBoard
        gameState={baseState}
        playerId="alice"
        onCardClick={onCardClick}
        overlayPendingChoice={overlayChoice}
        onSubmitOverlayChoice={onSubmitOverlayChoice}
      />
    );

    // Llanowar Elves is in the option list — click should submit.
    fireEvent.click(screen.getAllByRole('button', { name: 'Llanowar Elves' })[0]);
    expect(onSubmitOverlayChoice).toHaveBeenCalledWith(['card-elves']);
    expect(onCardClick).not.toHaveBeenCalled();
  });

  it('clicking a non-target card falls through to onCardClick', () => {
    const onCardClick = vi.fn();
    const onSubmitOverlayChoice = vi.fn();

    render(
      <GameBoard
        gameState={baseState}
        playerId="alice"
        onCardClick={onCardClick}
        overlayPendingChoice={overlayChoice}
        onSubmitOverlayChoice={onSubmitOverlayChoice}
      />
    );

    // Grizzly Bears is NOT in the option list — click should pass through.
    fireEvent.click(screen.getAllByRole('button', { name: 'Grizzly Bears' })[0]);
    expect(onSubmitOverlayChoice).not.toHaveBeenCalled();
    expect(onCardClick).toHaveBeenCalledTimes(1);
    expect(onCardClick.mock.calls[0][0].id).toBe('card-bears');
  });

  it('clicking a legal target player submits the choice', () => {
    const onSubmitOverlayChoice = vi.fn();

    render(
      <GameBoard
        gameState={baseState}
        playerId="alice"
        overlayPendingChoice={overlayChoice}
        onSubmitOverlayChoice={onSubmitOverlayChoice}
      />
    );

    // Bob is a legal target — clicking the opponent's portrait fires the choice.
    const bobPortrait = screen.getByTestId('targetable-player-bob');
    fireEvent.click(bobPortrait);
    expect(onSubmitOverlayChoice).toHaveBeenCalledWith(['bob']);
  });

  it('without an overlay choice, card clicks behave normally', () => {
    const onCardClick = vi.fn();
    const onSubmitOverlayChoice = vi.fn();

    render(
      <GameBoard
        gameState={baseState}
        playerId="alice"
        onCardClick={onCardClick}
        overlayPendingChoice={null}
        onSubmitOverlayChoice={onSubmitOverlayChoice}
      />
    );

    fireEvent.click(screen.getAllByRole('button', { name: 'Grizzly Bears' })[0]);
    expect(onSubmitOverlayChoice).not.toHaveBeenCalled();
    expect(onCardClick).toHaveBeenCalledTimes(1);
  });
});
