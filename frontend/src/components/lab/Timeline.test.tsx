/**
 * Timeline unit tests — verify compact + full render, click-to-scrub
 * callback fires with the right turn number, and arrow keys work on
 * the interactive variant. Covers the three jobs from HD-CRIT 17:
 * lobby ticker, in-board rail, post-match scrubber.
 */

import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { Timeline } from './Timeline';

describe('Timeline', () => {
  it('renders compact mode without the T0/endLabel tick labels', () => {
    render(<Timeline currentTurn={4} totalTurns={8} mode="compact" />);

    const bar = screen.getByTestId('lab-timeline');
    expect(bar).toBeInTheDocument();
    expect(bar.getAttribute('data-mode')).toBe('compact');
    // Compact mode strips both the eyebrow header and the T0/endLabel row.
    expect(screen.queryByText('T0')).not.toBeInTheDocument();
    expect(screen.queryByText('T8')).not.toBeInTheDocument();
  });

  it('renders full mode with the match ID, T-of-T header, and T0/end tick labels', () => {
    render(
      <Timeline currentTurn={4} totalTurns={8} matchId="HD-8F4A" mode="full" />,
    );

    expect(screen.getByText('HD-8F4A')).toBeInTheDocument();
    expect(screen.getByText('T0')).toBeInTheDocument();
    expect(screen.getByText('T8')).toBeInTheDocument();
    // The "T4 of T8" header lives in the row above the bar — assert on
    // the parent row's combined text so inner span chunks don't matter.
    const headerRow = screen.getByText('HD-8F4A').parentElement!;
    expect(headerRow.textContent).toMatch(/T4\s*of\s*T8/);
  });

  it('falls back to "replay" + auto-derived endLabel when matchId/endLabel omitted', () => {
    render(<Timeline currentTurn={2} totalTurns={5} mode="full" />);

    expect(screen.getByText('replay')).toBeInTheDocument();
    // Default endLabel is T{totalTurns}; both the header span and the
    // right-edge tick render it.
    expect(screen.getAllByText('T5').length).toBeGreaterThanOrEqual(1);
  });

  it('honors a custom endLabel override (e.g. "LIVE")', () => {
    render(
      <Timeline currentTurn={3} totalTurns={3} endLabel="LIVE" mode="full" />,
    );

    expect(screen.getByText('LIVE')).toBeInTheDocument();
  });

  it('exposes ARIA progressbar semantics when read-only', () => {
    render(<Timeline currentTurn={4} totalTurns={8} mode="compact" />);

    const slider = screen.getByRole('progressbar');
    expect(slider).toHaveAttribute('aria-valuemin', '0');
    expect(slider).toHaveAttribute('aria-valuemax', '8');
    expect(slider).toHaveAttribute('aria-valuenow', '4');
    expect(slider).toHaveAttribute('tabIndex', '-1');
  });

  it('switches to slider role + becomes keyboard-focusable when onScrub is set', () => {
    const onScrub = vi.fn();
    render(
      <Timeline currentTurn={4} totalTurns={8} mode="compact" onScrub={onScrub} />,
    );

    const slider = screen.getByRole('slider');
    expect(slider).toHaveAttribute('aria-valuenow', '4');
    expect(slider).toHaveAttribute('tabIndex', '0');
  });

  it('fires onScrub with the correct turn computed from click x', () => {
    const onScrub = vi.fn();
    render(
      <Timeline currentTurn={0} totalTurns={10} mode="compact" onScrub={onScrub} />,
    );

    const slider = screen.getByRole('slider');
    // Force a stable width so the click ratio resolves to a known turn.
    // happy-dom returns 0 for getBoundingClientRect by default, so we
    // patch it on the rendered node for this assertion.
    vi.spyOn(slider, 'getBoundingClientRect').mockReturnValue({
      left: 0,
      top: 0,
      right: 200,
      bottom: 6,
      width: 200,
      height: 6,
      x: 0,
      y: 0,
      toJSON: () => ({}),
    } as DOMRect);

    // Click at 50% (x=100 of width=200) on a 10-turn timeline → turn 5.
    fireEvent.click(slider, { clientX: 100 });
    expect(onScrub).toHaveBeenCalledWith(5);

    // Click at 100% (x=200) → turn 10.
    fireEvent.click(slider, { clientX: 200 });
    expect(onScrub).toHaveBeenLastCalledWith(10);

    // Click past the right edge — clamped to total.
    fireEvent.click(slider, { clientX: 999 });
    expect(onScrub).toHaveBeenLastCalledWith(10);

    // Click before the left edge — clamped to 0.
    fireEvent.click(slider, { clientX: -5 });
    expect(onScrub).toHaveBeenLastCalledWith(0);
  });

  it('does NOT fire onScrub when the bar is read-only', () => {
    const onScrub = vi.fn();
    render(
      <Timeline currentTurn={4} totalTurns={8} mode="compact" />,
    );

    const bar = screen.getByRole('progressbar');
    fireEvent.click(bar, { clientX: 100 });
    expect(onScrub).not.toHaveBeenCalled();
  });

  it('responds to arrow / Home / End keys when interactive', () => {
    const onScrub = vi.fn();
    render(
      <Timeline currentTurn={4} totalTurns={8} mode="compact" onScrub={onScrub} />,
    );

    const slider = screen.getByRole('slider');
    fireEvent.keyDown(slider, { key: 'ArrowRight' });
    expect(onScrub).toHaveBeenLastCalledWith(5);

    fireEvent.keyDown(slider, { key: 'ArrowLeft' });
    expect(onScrub).toHaveBeenLastCalledWith(3);

    fireEvent.keyDown(slider, { key: 'Home' });
    expect(onScrub).toHaveBeenLastCalledWith(0);

    fireEvent.keyDown(slider, { key: 'End' });
    expect(onScrub).toHaveBeenLastCalledWith(8);
  });

  it('clamps malformed inputs (negative current, zero total) instead of crashing', () => {
    render(<Timeline currentTurn={-3} totalTurns={0} mode="compact" />);

    const bar = screen.getByRole('progressbar');
    // totalTurns=0 falls back to 1 internally so the pip lands somewhere
    // sensible; negative current clamps to 0.
    expect(bar).toHaveAttribute('aria-valuenow', '0');
    expect(bar).toHaveAttribute('aria-valuemax', '1');
  });
});
