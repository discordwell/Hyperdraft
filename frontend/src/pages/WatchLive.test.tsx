/**
 * WatchLive smoke test — HD-ART-06 / Phase C3 lab port.
 *
 * Phase C3 follow-up (this slice): the lobby table reads real
 * BotGameStatus rows — engine code, player labels with brain/difficulty,
 * deck blurb — straight off the list API, with no mock fallback. The
 * featured panel only renders when a spectator-demo is active; otherwise
 * it shows an empty-state hint.
 *
 * Asserts:
 *   1. Masthead renders the "Now running" lab heading.
 *   2. The HD-ART-06 table headers are present in the lobby table.
 *   3. With no live matches, the table shows the empty-state line
 *      (no mock HD-2K1B / HD-9C77 / etc rows).
 *   4. The FEATURED panel renders its empty-state hint when no
 *      spectator demo is live.
 *   5. When the list API returns real rows, they show the engine code,
 *      player labels, and deck blurb supplied by the backend.
 *   6. Clicking a real row navigates to its spectate path.
 *
 * Mocks the api module so the page mounts without network. The spectator
 * fetches (/api/spectate/status) fall through to the catch path and the
 * empty-state featured panel — that's the lobby's "no demo live" steady
 * state.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../services/api', () => ({
  botGameAPI: { list: vi.fn().mockResolvedValue({ games: [], total: 0 }) },
  matchAPI: { listReplays: vi.fn().mockResolvedValue({ replays: [] }) },
}));

import { botGameAPI, matchAPI } from '../services/api';
import type { BotGameStatus } from '../types/game';
import { WatchLive } from './WatchLive';

const originalFetch = globalThis.fetch;

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/watch/live']}>
      <Routes>
        <Route path="/watch/live" element={<WatchLive />} />
        <Route path="/m/:gameId" element={<div data-testid="public-match" />} />
        <Route path="/spectate/:gameId" element={<div data-testid="spectate-game" />} />
        <Route path="/" element={<div data-testid="lab-home" />} />
        <Route path="/replays" element={<div data-testid="replays" />} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  // Re-prime mocks on the (module-scoped) mocked api so previous-test resets
  // can't strip the resolved values. Default state: no spectator demo, no
  // running bot games — exercises the empty-state empties.
  (botGameAPI.list as ReturnType<typeof vi.fn>).mockResolvedValue({ games: [], total: 0 });
  (matchAPI.listReplays as ReturnType<typeof vi.fn>).mockResolvedValue({ replays: [] });
  globalThis.fetch = vi.fn().mockResolvedValue({
    ok: true,
    json: () => Promise.resolve({ enabled: false, current_match_id: null }),
  }) as unknown as typeof fetch;
});

afterEach(() => {
  globalThis.fetch = originalFetch;
  vi.clearAllMocks();
});

describe('WatchLive (lab posture)', () => {
  it('renders the "Now running" masthead with a live-count pill', async () => {
    renderPage();

    expect(screen.getByRole('heading', { level: 1, name: /Now running/i })).toBeInTheDocument();
    expect(screen.getByTestId('live-count')).toBeInTheDocument();
  });

  it('renders the HD-ART-06 table headers', () => {
    renderPage();

    // Mono-caps headers exactly per HD-ART-06.
    for (const header of ['#', 'Match', 'Engine', 'Players', 'Turn', 'Watch']) {
      expect(screen.getByText(header)).toBeInTheDocument();
    }
  });

  it('renders the empty-state line when no matches are running', async () => {
    renderPage();

    await waitFor(() =>
      expect(screen.getByTestId('lobby-empty')).toBeInTheDocument(),
    );
    // No mock rows leak through anymore.
    expect(screen.queryByText('HD-2K1B')).not.toBeInTheDocument();
    expect(screen.queryByText('HD-9C77')).not.toBeInTheDocument();
  });

  it('renders the featured-panel empty state with no spectator demo', () => {
    renderPage();

    // The pinned-match "live" label and HD-8F4A mock both disappear; the
    // panel now reads as idle.
    expect(screen.getByText('FEATURED · IDLE')).toBeInTheDocument();
    expect(screen.getByText(/No featured match\. Start one from the lab\./)).toBeInTheDocument();
    expect(screen.queryByText('FEATURED · LIVE')).not.toBeInTheDocument();
    expect(screen.queryByText('HD-8F4A')).not.toBeInTheDocument();
  });

  it('renders real BotGameStatus rows with engine + brain/difficulty + deck blurb', async () => {
    const games: BotGameStatus[] = [
      {
        game_id: 'depths-test-001',
        status: 'running',
        turn: 7,
        winner: null,
        game_mode: 'depths',
        player1_label: 'Heuristic · hard',
        player2_label: 'Claude · ultra',
        deck_blurb: 'Subs Wolfpack',
      },
    ];
    (botGameAPI.list as ReturnType<typeof vi.fn>).mockResolvedValue({ games, total: 1 });

    renderPage();

    // Engine code from the brand registry: depths -> DPT.
    await waitFor(() => expect(screen.getByText('DPT')).toBeInTheDocument());
    // Both seat labels — concatenated with the engine row's ' · ' joiner.
    expect(screen.getByText(/Heuristic · hard · Claude · ultra/)).toBeInTheDocument();
    // Deck blurb appears under the short code.
    expect(screen.getByText('Subs Wolfpack')).toBeInTheDocument();
  });

  it('navigates to /spectate/<id> when a real list row is clicked', async () => {
    const games: BotGameStatus[] = [
      {
        game_id: 'mtg-test-002',
        status: 'running',
        turn: 3,
        winner: null,
        game_mode: 'mtg',
        player1_label: 'Heuristic · medium',
        player2_label: 'Heuristic · medium',
        deck_blurb: 'Mono-Red Netdeck',
      },
    ];
    (botGameAPI.list as ReturnType<typeof vi.fn>).mockResolvedValue({ games, total: 1 });

    renderPage();

    await waitFor(() => expect(screen.getByText('Mono-Red Netdeck')).toBeInTheDocument());
    fireEvent.click(screen.getByText('Mono-Red Netdeck'));
    expect(screen.getByTestId('spectate-game')).toBeInTheDocument();
  });

  it('exposes a visible masthead "← Lab" back-link', () => {
    renderPage();
    // The lobby now carries a visible masthead "← Lab" pill (in addition to
    // the footer crumb). Query it by accessible name so we assert the new
    // masthead affordance specifically, not the footer fallback.
    const back = screen.getByRole('button', { name: /Back to lab home/ });
    expect(back).toBeInTheDocument();
    expect(back).toHaveTextContent('← Lab');
  });
});
