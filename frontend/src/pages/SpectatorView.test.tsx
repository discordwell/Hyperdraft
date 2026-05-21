/**
 * SpectatorView — per-engine board dispatch tests.
 *
 * Confirms that `/spectate/:gameId` renders the engine-specific board
 * matching `gameState.game_mode`, not the unconditional MTG GameBoard
 * that the pre-fix version used. The bug was visible when MC/FIN/DPT
 * card art landed: art rendered to PNG endpoints fine, but spectating
 * the bot game still showed the MTG layout, so the art was invisible.
 *
 * Three assertions:
 *   1. game_mode='mtg'        → MTG GameBoard renders
 *   2. game_mode='minecraft'  → MCGameBoard renders, NOT MTG GameBoard
 *   3. game_mode='hearthstone' → HSGameBoard renders, NOT MTG GameBoard
 */
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { GameState } from '../types';

// botGameAPI is hit on mount — mock so we can inject the engine-specific
// game state directly. getStatus returns 'running' so the match-complete
// overlay doesn't render and steal the assertion.
const getState = vi.fn();
const getStatus = vi.fn().mockResolvedValue({ status: 'running', turn: 1 });
const getReplay = vi.fn().mockResolvedValue({ frames: [] });

vi.mock('../services/api', () => ({
  botGameAPI: {
    getState: (...args: unknown[]) => getState(...args),
    getStatus: (...args: unknown[]) => getStatus(...args),
    getReplay: (...args: unknown[]) => getReplay(...args),
    start: vi.fn(),
  },
  matchAPI: { listReplays: vi.fn().mockResolvedValue({ replays: [] }) },
}));

// Stub every engine board to a tagged div so we can assert which one
// the dispatcher mounted without pulling in their heavy deps. The MTG
// GameBoard already has its own complex DnD store; mocking it the same
// way keeps the regression test cheap.
vi.mock('../components/game', () => ({
  GameBoard: () => <div data-testid="board-mtg" />,
}));
vi.mock('../components/game/HSGameBoard', () => ({
  HSGameBoard: () => <div data-testid="board-hs" />,
}));
vi.mock('../components/game/PKMGameBoard', () => ({
  PKMGameBoard: () => <div data-testid="board-pkm" />,
}));
vi.mock('../components/game/YGOGameBoard', () => ({
  YGOGameBoard: () => <div data-testid="board-ygo" />,
}));
vi.mock('../components/game/MCGameBoard', () => ({
  MCGameBoard: () => <div data-testid="board-mc" />,
}));
vi.mock('../../games/finance', () => ({
  FinanceGameBoard: () => <div data-testid="board-finance" />,
}));
vi.mock('../../games/depths', () => ({
  DepthsGameBoard: () => <div data-testid="board-depths" />,
}));
// Also block the registry import chain that finance/depths siblings may
// pull in via React module graph — none of these matter for the dispatch
// assertion; we only need the lazy import to resolve to a tagged stub.
vi.mock('../games/finance', () => ({
  FinanceGameBoard: () => <div data-testid="board-finance" />,
}));
vi.mock('../games/depths', () => ({
  DepthsGameBoard: () => <div data-testid="board-depths" />,
}));

import SpectatorView from './SpectatorView';

function makeState(mode: GameState['game_mode']): GameState {
  // Minimum shape — SpectatorView only needs players + game_mode to
  // pick a spectator player id and route the dispatcher.
  return {
    match_id: 'g-1',
    turn_number: 1,
    phase: 'MAIN',
    step: 'MAIN',
    active_player: 'alice',
    priority_player: 'alice',
    players: {
      alice: {
        id: 'alice',
        name: 'Alice',
        life: 20,
        has_lost: false,
        hand_size: 0,
        library_size: 50,
      } as unknown as GameState['players'][string],
      bob: {
        id: 'bob',
        name: 'Bob',
        life: 20,
        has_lost: false,
        hand_size: 0,
        library_size: 50,
      } as unknown as GameState['players'][string],
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
    game_mode: mode,
  } as unknown as GameState;
}

function renderAt(path = '/spectate/test-id') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/spectate/:gameId" element={<SpectatorView />} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  getStatus.mockResolvedValue({ status: 'running', turn: 1 });
});

afterEach(() => {
  vi.clearAllMocks();
});

describe('SpectatorView dispatch', () => {
  it('renders the MTG GameBoard for game_mode=mtg (regression)', async () => {
    getState.mockResolvedValue(makeState('mtg'));

    renderAt();

    await waitFor(() => {
      expect(screen.getByTestId('board-mtg')).toBeInTheDocument();
    });
    expect(screen.queryByTestId('board-mc')).toBeNull();
    expect(screen.queryByTestId('board-hs')).toBeNull();
  });

  it('renders the MCGameBoard for game_mode=minecraft, NOT GameBoard', async () => {
    getState.mockResolvedValue(makeState('minecraft'));

    renderAt();

    await waitFor(() => {
      expect(screen.getByTestId('board-mc')).toBeInTheDocument();
    });
    expect(screen.queryByTestId('board-mtg')).toBeNull();
  });

  it('renders the HSGameBoard for game_mode=hearthstone, NOT GameBoard', async () => {
    getState.mockResolvedValue(makeState('hearthstone'));

    renderAt();

    await waitFor(() => {
      expect(screen.getByTestId('board-hs')).toBeInTheDocument();
    });
    expect(screen.queryByTestId('board-mtg')).toBeNull();
  });
});
