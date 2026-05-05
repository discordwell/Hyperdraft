/**
 * PriorityPrompt smoke tests.
 *
 * Verifies the v1 prompt's gating logic — only renders for the player
 * with priority during a stack-active window — and that the buttons
 * fire the right callbacks.
 */

import { describe, it, expect, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { PriorityPrompt } from './PriorityPrompt';
import type { GameState } from '../../types';

const baseState: GameState = {
  match_id: 'm1',
  turn_number: 1,
  phase: 'PRECOMBAT_MAIN',
  step: 'MAIN',
  active_player: 'alice',
  priority_player: 'alice',
  players: {
    alice: {
      id: 'alice',
      name: 'Alice',
      life: 20,
      has_lost: false,
      hand_size: 7,
      library_size: 53,
    },
    bob: {
      id: 'bob',
      name: 'Bob',
      life: 20,
      has_lost: false,
      hand_size: 7,
      library_size: 53,
    },
  },
  battlefield: [],
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

describe('PriorityPrompt', () => {
  it('does not render when player does not have priority', () => {
    const stateBobsTurn: GameState = {
      ...baseState,
      priority_player: 'bob',
      stack: [{
        id: 's1',
        type: 'SPELL',
        source_id: 'card1',
        source_name: 'Lightning Bolt',
        controller: 'bob',
      }],
    };

    const { container } = render(
      <PriorityPrompt
        gameState={stateBobsTurn}
        playerId="alice"
        onPass={() => {}}
      />
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('does not render when stack is empty (default onlyWhenStackActive=true)', () => {
    const { container } = render(
      <PriorityPrompt
        gameState={baseState}
        playerId="alice"
        onPass={() => {}}
      />
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('renders when player has priority and a spell is on the stack', () => {
    const stateWithStack: GameState = {
      ...baseState,
      stack: [{
        id: 's1',
        type: 'SPELL',
        source_id: 'card1',
        source_name: 'Lightning Bolt',
        controller: 'bob',
      }],
    };

    render(
      <PriorityPrompt
        gameState={stateWithStack}
        playerId="alice"
        onPass={() => {}}
      />
    );

    expect(screen.getByTestId('priority-prompt')).toBeInTheDocument();
    expect(screen.getByText(/Top of stack: Lightning Bolt/i)).toBeInTheDocument();
    expect(screen.getByTestId('priority-pass')).toBeInTheDocument();
  });

  it('renders when triggers are queued (stack still empty)', () => {
    const stateWithTriggers: GameState = {
      ...baseState,
      pending_triggers: [{
        id: 't1',
        controller: 'alice',
        source_id: 'src1',
        source_name: 'Soul Warden',
        description: 'When a creature enters, you gain 1 life.',
      }],
    };

    render(
      <PriorityPrompt
        gameState={stateWithTriggers}
        playerId="alice"
        onPass={() => {}}
      />
    );

    expect(screen.getByTestId('priority-prompt')).toBeInTheDocument();
    expect(screen.getByText(/1 trigger queued/i)).toBeInTheDocument();
  });

  it('clicking Pass invokes onPass handler', () => {
    const onPass = vi.fn();
    const stateWithStack: GameState = {
      ...baseState,
      stack: [{
        id: 's1',
        type: 'SPELL',
        source_id: 'card1',
        source_name: 'Lightning Bolt',
        controller: 'bob',
      }],
    };

    render(
      <PriorityPrompt
        gameState={stateWithStack}
        playerId="alice"
        onPass={onPass}
      />
    );

    fireEvent.click(screen.getByTestId('priority-pass'));
    expect(onPass).toHaveBeenCalledTimes(1);
  });

  it('shows Respond button when actionable responses exist', () => {
    const onRespond = vi.fn();
    const stateWithStackAndAction: GameState = {
      ...baseState,
      stack: [{
        id: 's1',
        type: 'SPELL',
        source_id: 'card1',
        source_name: 'Lightning Bolt',
        controller: 'bob',
      }],
      legal_actions: [
        ...baseState.legal_actions,
        {
          type: 'CAST_SPELL',
          card_id: 'mycard',
          ability_id: null,
          source_id: null,
          description: 'Cast Counterspell',
          requires_targets: true,
          requires_mana: true,
        },
      ],
    };

    render(
      <PriorityPrompt
        gameState={stateWithStackAndAction}
        playerId="alice"
        onPass={() => {}}
        onRespond={onRespond}
      />
    );

    const respond = screen.getByTestId('priority-respond');
    fireEvent.click(respond);
    expect(onRespond).toHaveBeenCalledTimes(1);
  });
});
