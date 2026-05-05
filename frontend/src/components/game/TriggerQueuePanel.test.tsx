/**
 * TriggerQueuePanel smoke tests.
 *
 * Verifies the v1 panel renders the queued triggers from
 * ``state.pending_triggers`` and stays out of the way when the queue is
 * empty (returns null).
 */

import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { TriggerQueuePanel } from './TriggerQueuePanel';
import type { PendingTriggerData } from '../../types';

describe('TriggerQueuePanel', () => {
  it('returns null when no triggers are queued', () => {
    const { container } = render(
      <TriggerQueuePanel pendingTriggers={[]} playerId="alice" />
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('renders one row per pending trigger', () => {
    const triggers: PendingTriggerData[] = [
      {
        id: 'trig1',
        controller: 'alice',
        source_id: 'card1',
        source_name: 'Soul Warden',
        description: 'When a creature enters, you gain 1 life.',
      },
      {
        id: 'trig2',
        controller: 'bob',
        source_id: 'card2',
        source_name: 'Suture Priest',
        description: 'Whenever a creature enters, target opponent loses 1 life.',
      },
    ];

    render(<TriggerQueuePanel pendingTriggers={triggers} playerId="alice" />);

    const items = screen.getAllByTestId('trigger-queue-item');
    expect(items).toHaveLength(2);
    expect(screen.getByText('Soul Warden')).toBeInTheDocument();
    expect(screen.getByText('Suture Priest')).toBeInTheDocument();
    expect(
      screen.getByText('When a creature enters, you gain 1 life.')
    ).toBeInTheDocument();
  });

  it('marks own vs opponent triggers with controller labels', () => {
    const triggers: PendingTriggerData[] = [
      {
        id: 't1',
        controller: 'alice',
        source_id: 'src1',
        source_name: 'Mine',
      },
      {
        id: 't2',
        controller: 'bob',
        source_id: 'src2',
        source_name: 'Theirs',
      },
    ];

    render(<TriggerQueuePanel pendingTriggers={triggers} playerId="alice" />);

    expect(screen.getByText('Yours')).toBeInTheDocument();
    expect(screen.getByText('Opponent')).toBeInTheDocument();
  });

  it('renders even when description is missing', () => {
    const triggers: PendingTriggerData[] = [
      {
        id: 't1',
        controller: 'alice',
        source_id: 'src1',
        source_name: 'Mystery',
        // no description
      },
    ];

    render(<TriggerQueuePanel pendingTriggers={triggers} playerId="alice" />);
    expect(screen.getByText('Mystery')).toBeInTheDocument();
  });
});
