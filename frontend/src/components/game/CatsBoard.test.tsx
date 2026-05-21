/**
 * CatsBoard — read-only board smoke tests.
 *
 * The board is the rendering surface used by spectator + replay dispatch
 * for Cats matches. These tests assert two contracts:
 *
 *   1. It renders an empty/placeholder state when `gameState.cats` is
 *      missing — bot games that crash during setup must not blank the page.
 *   2. It renders the cozy CatsBoardInner board (cream/butterscotch
 *      palette, paw glyph) when given a minimal valid `cats` payload.
 */
import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { CatsBoard } from './CatsBoard';
import type { CatsState } from '../../hooks/useCatsGame';
import type { GameState, PlayerData } from '../../types';

function makePlayer(id: string, name: string): PlayerData {
  return {
    id,
    name,
    life: 20,
    has_lost: false,
    hand_size: 0,
    library_size: 50,
  } as unknown as PlayerData;
}

function makeBaseState(): GameState {
  return {
    match_id: 'cats-1',
    turn_number: 1,
    phase: 'MAIN',
    step: 'MAIN',
    active_player: 'alice',
    priority_player: 'alice',
    players: {
      alice: makePlayer('alice', 'Alice'),
      bob: makePlayer('bob', 'Bob'),
    },
    battlefield: [],
    stack: [],
    pending_triggers: [],
    hand: [],
    graveyard: { alice: [], bob: [] },
    legal_actions: [],
    combat: null,
    is_game_over: false,
    winner: null,
    game_mode: 'cats',
  } as unknown as GameState;
}

function makeCatsPayload(): CatsState {
  return {
    round_number: 1,
    phase: 'stretch',
    lead_player: 'me',
    current_trick: {
      pounce_card: null,
      counter_card: null,
      winner: null,
      installed_rule: null,
    },
    player: {
      hand: [],
      piles: { territory: [], nap: [], snack: [], attention: [] },
      commander: null,
    },
    opponent: {
      hand: [],
      piles: { territory: [], nap: [], snack: [], attention: [] },
      commander: null,
    },
    game_over: false,
  };
}

describe('CatsBoard', () => {
  it('renders an empty placeholder when gameState.cats is missing', () => {
    render(<CatsBoard gameState={makeBaseState()} playerId="alice" />);
    expect(screen.getByText('No game in session.')).toBeInTheDocument();
    expect(screen.getByText('No Cats state on this frame.')).toBeInTheDocument();
  });

  it('renders the round header + phase chips when given a valid cats payload', () => {
    const state = makeBaseState();
    (state as unknown as { cats: CatsState }).cats = makeCatsPayload();
    render(<CatsBoard gameState={state} playerId="alice" />);
    expect(screen.getByText('Round 1 of 9')).toBeInTheDocument();
    expect(screen.getByText('A day in the life of a cat')).toBeInTheDocument();
  });

  it('routes the read-only board against the seat-relative Cats payload (no hook)', () => {
    // Cats's payload is already seat-relative (me vs opponent), so the
    // board does NOT need to flip layout based on playerId. The prop is
    // accepted for API symmetry with SCPBoard.
    const state = makeBaseState();
    (state as unknown as { cats: CatsState }).cats = makeCatsPayload();
    const { rerender } = render(
      <CatsBoard gameState={state} playerId="alice" readOnly />,
    );
    expect(screen.getByText('Round 1 of 9')).toBeInTheDocument();
    rerender(<CatsBoard gameState={state} playerId="bob" readOnly />);
    expect(screen.getByText('Round 1 of 9')).toBeInTheDocument();
  });
});
