/**
 * WatchLive smoke test — HD-ART-06 / Phase C3 lab port.
 *
 * Asserts:
 *   1. Masthead renders the "Now running" lab heading.
 *   2. The HD-ART-06 table headers are present in the lobby table.
 *   3. The FEATURED · LIVE panel renders with the sodium-italic "vs"
 *      separator between two named seats.
 *   4. Clicking a non-queued row navigates to its watch path.
 *
 * Mocks the api module so the page mounts without network. The spectator
 * fetches (/api/spectate/status) fall through to the catch path and the
 * fallback featured match — that's the lobby's "no demo live" steady state.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../services/api', () => ({
  botGameAPI: { list: vi.fn().mockResolvedValue({ games: [], total: 0 }) },
  matchAPI: { listReplays: vi.fn().mockResolvedValue({ replays: [] }) },
}));

import { botGameAPI, matchAPI } from '../services/api';
import { WatchLive } from './WatchLive';

const originalFetch = globalThis.fetch;

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/watch/live']}>
      <Routes>
        <Route path="/watch/live" element={<WatchLive />} />
        <Route path="/m/:gameId" element={<div data-testid="public-match" />} />
        <Route path="/" element={<div data-testid="lab-home" />} />
        <Route path="/replays" element={<div data-testid="replays" />} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  // Re-prime mocks on the (module-scoped) mocked api so previous-test resets
  // can't strip the resolved values. Default state: no spectator demo, no
  // running bot games — exercises the fallback featured match.
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

  it('renders the FEATURED · LIVE panel with a sodium "vs" separator', () => {
    renderPage();

    expect(screen.getByText('FEATURED · LIVE')).toBeInTheDocument();
    // Fallback featured match exposes both seat labels + commentary.
    expect(screen.getByText('vs.')).toBeInTheDocument();
    expect(screen.getAllByText('Ultra-AI').length).toBeGreaterThan(0);
    expect(screen.getByText('Hard-AI')).toBeInTheDocument();
  });

  it('navigates to /m/<short> when a non-queued row is clicked', async () => {
    renderPage();

    // The HD-2K1B mock row is the first non-live entry — not queued, so it
    // should route. Resolve via its short-code label inside the table.
    await waitFor(() => expect(screen.getByText('HD-2K1B')).toBeInTheDocument());
    fireEvent.click(screen.getByText('HD-2K1B'));

    expect(screen.getByTestId('public-match')).toBeInTheDocument();
  });

  it('exposes the "← Lab" footer back-link', () => {
    renderPage();
    expect(screen.getByRole('button', { name: /← Lab/ })).toBeInTheDocument();
  });
});

