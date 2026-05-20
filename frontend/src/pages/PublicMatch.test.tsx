/**
 * PublicMatch — HD-CRIT 19 unit tests.
 *
 *   1. The short-code projection turns any match id into HD-XXXX.
 *   2. Rendering on /m/abcd1234 surfaces the short code in the masthead.
 *   3. Clicking "Copy link" writes window.location.href to navigator.clipboard
 *      and flashes a "Copied" confirmation.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

// SpectatorView's body fetches /api/* on mount; we mock the api module so the
// lazy-loaded view mounts cleanly inside happy-dom. We don't assert on the
// spectator body here — that's covered by SpectatorView's own tests; this
// suite only proves the public-match wrapper.
vi.mock('../services/api', () => ({
  botGameAPI: {
    getState: vi.fn().mockResolvedValue({ players: {} }),
    getStatus: vi.fn().mockResolvedValue({ status: 'running', turn: 1 }),
    getReplay: vi.fn().mockResolvedValue({ frames: [] }),
    start: vi.fn(),
  },
  matchAPI: { listReplays: vi.fn().mockResolvedValue({ replays: [] }) },
}));

// The GameBoard pulls in heavy game-state types and styling; for the wrapper
// test we only need it to render *something* so SpectatorView mounts cleanly.
vi.mock('../components/game', () => ({
  GameBoard: () => <div data-testid="game-board-mock" />,
}));

import { PublicMatch, shortCode } from './PublicMatch';

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/m/:gameId" element={<PublicMatch />} />
      </Routes>
    </MemoryRouter>,
  );
}

const originalClipboard = navigator.clipboard;
let writeText: ReturnType<typeof vi.fn>;

beforeEach(() => {
  vi.clearAllMocks();
  writeText = vi.fn().mockResolvedValue(undefined);
  Object.defineProperty(navigator, 'clipboard', {
    configurable: true,
    value: { writeText },
  });
});

afterEach(() => {
  Object.defineProperty(navigator, 'clipboard', {
    configurable: true,
    value: originalClipboard,
  });
});

describe('shortCode()', () => {
  it('passes through real HD-XXXX codes verbatim', () => {
    expect(shortCode('HD-8F4A')).toBe('HD-8F4A');
    expect(shortCode('hd-8f4a')).toBe('HD-8F4A');
  });

  it('projects UUID-style ids into a stable HD-XXXX head', () => {
    const id = '8f4a1234-abcd-ef01-2345-6789abcdef01';
    expect(shortCode(id)).toBe('HD-8F4A');
  });

  it('handles short / falsy inputs without throwing', () => {
    expect(shortCode('a')).toBe('HD-A000');
    expect(shortCode('')).toBe('HD-????');
    expect(shortCode(undefined)).toBe('HD-????');
  });
});

describe('PublicMatch page', () => {
  it('renders the short code in the masthead', () => {
    renderAt('/m/8f4a1234abcd');

    const shortCodeEl = screen.getByTestId('public-match-shortcode');
    expect(shortCodeEl).toHaveTextContent('HD-8F4A');
  });

  it('surfaces the "Watching publicly" indicator', () => {
    renderAt('/m/test-match-id');
    expect(screen.getByText(/Watching publicly/i)).toBeInTheDocument();
  });

  it('renders the no-login public-match footer rail', () => {
    renderAt('/m/test-match-id');
    expect(
      screen.getByText(/HD-MATCH-PUBLIC . LINK YOURS . NO LOGIN/i),
    ).toBeInTheDocument();
  });

  it('copies window.location.href to clipboard on click and flashes "Copied"', async () => {
    renderAt('/m/8f4a1234');

    const button = screen.getByRole('button', {
      name: /Copy public match link to clipboard/i,
    });
    expect(button).toHaveTextContent(/Copy link/);

    fireEvent.click(button);

    await waitFor(() => {
      expect(writeText).toHaveBeenCalledTimes(1);
    });
    expect(writeText).toHaveBeenCalledWith(window.location.href);

    await waitFor(() => {
      expect(button).toHaveTextContent(/Copied/);
    });
  });
});
