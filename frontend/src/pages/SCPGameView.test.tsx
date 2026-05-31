/**
 * SCPGameView back-link smoke test.
 *
 * The SCP board is reachable directly via /scp and as a spectator surface.
 * Crucially it must offer a way back to HYPERDRAFT main *even when the socket
 * never resolves* — otherwise a stuck "Connecting…" screen is a dead-end.
 * Mocks useSCPGame to a null state so the loading screen renders without a
 * live socket; the back-link lives on that screen as well as the live board.
 */
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('../hooks/useSCPGame', () => ({
  useSCPGame: () => ({ state: null, dispatch: vi.fn(), isConnected: false }),
}));

import { SCPGameView } from './SCPGameView';

afterEach(() => {
  vi.clearAllMocks();
});

describe('SCPGameView', () => {
  it('exposes a "← Home" back-link on the connecting screen', () => {
    render(
      <MemoryRouter>
        <SCPGameView />
      </MemoryRouter>,
    );
    // Before any board state resolves, the user can still leave.
    expect(
      screen.getByText(/Connecting…|Loading containment site…/),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: /Back to HYPERDRAFT main/ }),
    ).toBeInTheDocument();
  });
});
