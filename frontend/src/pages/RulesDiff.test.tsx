/**
 * RulesDiff smoke test — HD-CRIT-20.
 *
 * Asserts the default render (MTG vs Hearthstone on TURN_START) lights up
 * both columns with multiple interceptors, and that flipping the event
 * picker to DAMAGE swaps the content while preserving the engine selection.
 */

import { fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';

import { RulesDiff } from './RulesDiff';

function renderPage() {
  return render(
    <MemoryRouter>
      <RulesDiff />
    </MemoryRouter>,
  );
}

describe('RulesDiff', () => {
  it('renders the default MTG vs Hearthstone diff on TURN_START', () => {
    renderPage();

    // Page title + lead engines visible.
    expect(screen.getByRole('heading', { level: 1, name: /Rules/ })).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 3, name: 'Magic' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 3, name: 'Hearthstone' })).toBeInTheDocument();

    // MTG TURN_START data is present (untap_step is in src/engine/turn.py).
    expect(screen.getByText('untap_step')).toBeInTheDocument();

    // Hearthstone TURN_START data is present (mana_crystal_gain is in
    // src/engine/hearthstone_turn.py:_run_draw_phase).
    expect(screen.getByText('mana_crystal_gain')).toBeInTheDocument();

    // Differences ledger has at least one row for this default pair.
    expect(screen.getByText('Differences')).toBeInTheDocument();
    expect(screen.getByText(/Untap step/)).toBeInTheDocument();
  });

  it('swaps interceptor content when the event picker changes', () => {
    renderPage();

    // Sanity: TURN_START-specific interceptor present.
    expect(screen.getByText('mana_crystal_gain')).toBeInTheDocument();
    expect(screen.queryByText('divine_shield')).not.toBeInTheDocument();

    // Find the DAMAGE button inside the "Event type" picker group and click.
    const eventGroup = screen.getByRole('group', { name: 'Event type' });
    fireEvent.click(within(eventGroup).getByRole('button', { name: 'DAMAGE' }));

    // DAMAGE-only rows now visible.
    expect(screen.getByText('divine_shield')).toBeInTheDocument();
    expect(screen.getByText('apply_player_damage')).toBeInTheDocument();

    // TURN_START-only rows now gone.
    expect(screen.queryByText('mana_crystal_gain')).not.toBeInTheDocument();
  });
});
