/**
 * GameViewLayout smoke tests.
 *
 * Verifies the header strip carries lab posture: HYPERDRAFT mark, mode
 * code, MATCH / TURN / PHASE breadcrumb, opponent vs player names,
 * ⌥P discoverability hint (hidden when pipelineOpen=true), and the
 * ← Lab exit button. Covers Phases C1 + D1 of docs/design/buildplan.md.
 *
 * The body below the strip is intentionally untouched — these tests
 * exercise the seam, not the per-engine game chrome.
 */

import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { GameViewLayout } from './GameViewLayout';

function renderLayout(props: Partial<React.ComponentProps<typeof GameViewLayout>> = {}) {
  return render(
    <MemoryRouter>
      <GameViewLayout mode="mtg" {...props}>
        <div data-testid="board-body">BOARD</div>
      </GameViewLayout>
    </MemoryRouter>,
  );
}

describe('GameViewLayout header strip', () => {
  it('renders the HYPERDRAFT mark, mode code, ← Lab button, and the body', () => {
    renderLayout({
      matchId: 'HD-ABC12345',
      turn: 4,
      phase: 'main 1',
      opponentName: 'Bot',
      playerName: 'Alice',
    });

    expect(screen.getByRole('button', { name: /HYPERDRAFT home/i })).toBeInTheDocument();
    expect(screen.getByText('MTG')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /← Lab/ })).toBeInTheDocument();
    expect(screen.getByTestId('board-body')).toBeInTheDocument();
  });

  it('builds the MATCH / TURN / PHASE breadcrumb from the props', () => {
    renderLayout({
      matchId: 'HD-1234CAFE',
      turn: 7,
      phase: 'declare attackers',
    });
    // shortMatchId is the first 8 chars uppercased; turn flows in; phase is uppercased.
    expect(
      screen.getByText('MATCH HD-1234C · TURN 7 · DECLARE ATTACKERS'),
    ).toBeInTheDocument();
  });

  it('renders the opponent vs player chip when names are provided', () => {
    renderLayout({ opponentName: 'Bot', playerName: 'Alice' });
    expect(screen.getByText('Bot')).toBeInTheDocument();
    expect(screen.getByText('Alice')).toBeInTheDocument();
    expect(screen.getByText('vs')).toBeInTheDocument();
  });

  it('shows the ⌥P · pipeline hint by default', () => {
    renderLayout();
    expect(screen.getByText(/⌥P · pipeline/i)).toBeInTheDocument();
  });

  it('hides the ⌥P · pipeline hint when pipelineOpen is true', () => {
    renderLayout({ pipelineOpen: true });
    expect(screen.queryByText(/⌥P · pipeline/i)).not.toBeInTheDocument();
  });

  it('hides the exit button when showExit is false', () => {
    renderLayout({ showExit: false });
    expect(screen.queryByRole('button', { name: /← Lab/ })).not.toBeInTheDocument();
  });
});
