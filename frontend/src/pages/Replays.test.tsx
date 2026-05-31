/**
 * Replays back-link smoke test.
 *
 * The replay library is a between-games surface reached from Home's lab grid;
 * it must offer a visible way back to HYPERDRAFT main rather than being a
 * navigational dead-end. Mocks matchAPI.listReplays to an empty archive — the
 * masthead (and its "← Lab" crumb) render regardless of how many rows load.
 */
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('../services/api', () => ({
  matchAPI: {
    listReplays: vi.fn().mockResolvedValue({ replays: [] }),
  },
}));

import { Replays } from './Replays';

afterEach(() => {
  vi.clearAllMocks();
});

describe('Replays (lab posture)', () => {
  it('exposes a visible "← Lab" back-link in the masthead', async () => {
    render(
      <MemoryRouter>
        <Replays />
      </MemoryRouter>,
    );
    // The masthead "← Lab" button exposes its accessible name via aria-label.
    // findBy* flushes the pending listReplays promise inside act() so the
    // empty-archive state settles without a React act warning.
    const back = await screen.findByRole('button', { name: /Back to lab home/ });
    expect(back).toBeInTheDocument();
    expect(back).toHaveTextContent('← Lab');
  });
});
