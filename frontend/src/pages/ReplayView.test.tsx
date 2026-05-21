/**
 * ReplayView dispatch tests — confirms the inner board switch picks the
 * right per-engine component off the current frame's `game_mode`. The
 * outer chrome (scrubber, phase panel, timeline) is untouched by the
 * dispatch fix, so this suite focuses on the board-rendering boundary.
 *
 * The per-engine board components themselves are mocked to lightweight
 * stubs so the test doesn't need to satisfy their full prop surface; we
 * only need to prove that the right component is selected.
 */

import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { GameState, ReplayFrame, ReplayResponse } from '../types';

// Mock every per-engine board to a tagged stub. The mocks must be declared
// before the ReplayView import so vitest's module hoist picks them up.
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
vi.mock('../games/finance', () => ({
  FinanceGameBoard: () => <div data-testid="board-finance" />,
}));
vi.mock('../games/depths', () => ({
  DepthsGameBoard: () => <div data-testid="board-depths" />,
}));
vi.mock('../components/game/SCPBoard', () => ({
  SCPBoard: () => <div data-testid="board-scp" />,
}));
vi.mock('../components/game/CatsBoard', () => ({
  CatsBoard: () => <div data-testid="board-cats" />,
}));

// Timeline pulls in browser-only Canvas / SVG measurement on render; stub
// it so the dispatch suite stays focused on the board switch.
vi.mock('../components/lab', () => ({
  Timeline: () => <div data-testid="replay-timeline" />,
}));

vi.mock('../services/api', () => ({
  botGameAPI: { getReplay: vi.fn() },
  matchAPI: { getReplay: vi.fn() },
}));

import { botGameAPI } from '../services/api';
import { ReplayView } from './ReplayView';

function makeGameState(overrides: Partial<GameState>): GameState {
  return {
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
    battlefield: [],
    stack: [],
    pending_triggers: [],
    hand: [],
    graveyard: { alice: [], bob: [] },
    legal_actions: [],
    combat: null,
    is_game_over: false,
    winner: null,
    ...overrides,
  } as GameState;
}

function makeFrame(state: GameState): ReplayFrame {
  return {
    turn: state.turn_number,
    phase: state.phase,
    step: state.step,
    action: null,
    state,
    timestamp: 0,
  };
}

function makeReplay(state: GameState): ReplayResponse {
  return {
    game_id: 'replay-test',
    winner: null,
    total_turns: 1,
    frames: [makeFrame(state)],
  };
}

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/replay/:gameId" element={<ReplayView />} />
        <Route path="/replay/match/:matchId" element={<ReplayView />} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('ReplayView — per-engine board dispatch', () => {
  it('renders the Minecraft board for a Minecraft replay frame', async () => {
    (botGameAPI.getReplay as ReturnType<typeof vi.fn>).mockResolvedValue(
      makeReplay(
        makeGameState({
          game_mode: 'minecraft',
          minecraft_grid: {
            alice: [[null, null, null], [null, null, null], [null, null, null]],
            bob: [[null, null, null], [null, null, null], [null, null, null]],
          },
          minecraft_biomes: { alice: [], bob: [] },
        }),
      ),
    );

    renderAt('/replay/mc-game-1');

    await waitFor(() => {
      expect(screen.getByTestId('board-mc')).toBeInTheDocument();
    });

    // None of the other engine boards should have mounted.
    expect(screen.queryByTestId('board-mtg')).not.toBeInTheDocument();
    expect(screen.queryByTestId('board-hs')).not.toBeInTheDocument();
  });

  it('renders the Hearthstone board for an HS replay frame', async () => {
    (botGameAPI.getReplay as ReturnType<typeof vi.fn>).mockResolvedValue(
      makeReplay(makeGameState({ game_mode: 'hearthstone' })),
    );

    renderAt('/replay/hs-game-1');

    await waitFor(() => {
      expect(screen.getByTestId('board-hs')).toBeInTheDocument();
    });
    expect(screen.queryByTestId('board-mtg')).not.toBeInTheDocument();
  });

  it('renders the MTG GameBoard for an MTG replay frame (regression)', async () => {
    (botGameAPI.getReplay as ReturnType<typeof vi.fn>).mockResolvedValue(
      makeReplay(makeGameState({ game_mode: 'mtg' })),
    );

    renderAt('/replay/mtg-game-1');

    await waitFor(() => {
      expect(screen.getByTestId('board-mtg')).toBeInTheDocument();
    });
    expect(screen.queryByTestId('board-hs')).not.toBeInTheDocument();
    expect(screen.queryByTestId('board-mc')).not.toBeInTheDocument();
  });

  it('renders the SCP board for an SCP replay frame', async () => {
    (botGameAPI.getReplay as ReturnType<typeof vi.fn>).mockResolvedValue(
      makeReplay(makeGameState({ game_mode: 'scp' as GameState['game_mode'] })),
    );

    renderAt('/replay/scp-game-1');

    await waitFor(() => {
      expect(screen.getByTestId('board-scp')).toBeInTheDocument();
    });
    expect(screen.queryByTestId('board-mtg')).not.toBeInTheDocument();
  });

  it('renders the Cats board for a Cats replay frame', async () => {
    (botGameAPI.getReplay as ReturnType<typeof vi.fn>).mockResolvedValue(
      makeReplay(makeGameState({ game_mode: 'cats' as GameState['game_mode'] })),
    );

    renderAt('/replay/cats-game-1');

    await waitFor(() => {
      expect(screen.getByTestId('board-cats')).toBeInTheDocument();
    });
    expect(screen.queryByTestId('board-mtg')).not.toBeInTheDocument();
  });

  it('falls back to the MTG GameBoard + warns for genuinely unmapped modes', async () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => undefined);

    (botGameAPI.getReplay as ReturnType<typeof vi.fn>).mockResolvedValue(
      makeReplay(makeGameState({ game_mode: 'unknown-engine' as GameState['game_mode'] })),
    );

    renderAt('/replay/unknown-game-1');

    await waitFor(() => {
      expect(screen.getByTestId('board-mtg')).toBeInTheDocument();
    });

    expect(warnSpy).toHaveBeenCalled();
    expect(warnSpy.mock.calls[0][0]).toMatch(/unknown-engine/);

    warnSpy.mockRestore();
  });
});
