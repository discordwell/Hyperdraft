/**
 * PipelineView smoke tests.
 *
 * Verifies the four-column TRANSFORM / PREVENT / RESOLVE / REACT layout
 * renders all stages, an empty stage shows the placeholder, and clicking
 * an event line fires the onSelect callback with the event id.
 */

import { describe, it, expect, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { PipelineView, type PipelineEvent } from './PipelineView';

const sampleEvents: PipelineEvent[] = [
  {
    id: 'e1',
    stage: 'transform',
    type: 'DAMAGE',
    source: 'Lightning Bolt',
    description: 'Damage modified by Boros Reckoner (redirect).',
    t: 'T1 +01',
    turn: 1,
    relatedId: 'g1',
  },
  {
    id: 'e2',
    stage: 'prevent',
    type: 'DAMAGE',
    source: 'Leyline of Sanctity',
    description: 'Damage to Alice prevented (hexproof).',
    t: 'T1 +02',
    turn: 1,
    relatedId: 'g1',
  },
  {
    id: 'e3',
    stage: 'resolve',
    type: 'LIFE_CHANGE',
    source: 'Lightning Bolt',
    description: 'Bob loses 3 life (20 → 17).',
    t: 'T1 +03',
    turn: 1,
    relatedId: 'g1',
  },
  {
    id: 'e4',
    stage: 'react',
    type: 'ETB',
    source: 'Soul Warden',
    description: 'Soul Warden triggers: Alice gains 1 life.',
    t: 'T2 +01',
    turn: 2,
  },
];

describe('PipelineView', () => {
  it('renders all four stage columns', () => {
    render(<PipelineView events={sampleEvents} />);

    expect(screen.getByText('TRANSFORM')).toBeInTheDocument();
    expect(screen.getByText('PREVENT')).toBeInTheDocument();
    expect(screen.getByText('RESOLVE')).toBeInTheDocument();
    expect(screen.getByText('REACT')).toBeInTheDocument();

    // All four data-testid columns exist regardless of population.
    expect(screen.getByTestId('pipeline-column-transform')).toBeInTheDocument();
    expect(screen.getByTestId('pipeline-column-prevent')).toBeInTheDocument();
    expect(screen.getByTestId('pipeline-column-resolve')).toBeInTheDocument();
    expect(screen.getByTestId('pipeline-column-react')).toBeInTheDocument();
  });

  it('renders one event line per supplied event', () => {
    render(<PipelineView events={sampleEvents} />);

    for (const ev of sampleEvents) {
      expect(screen.getByTestId(`pipeline-event-${ev.id}`)).toBeInTheDocument();
    }
  });

  it('shows the empty-state placeholder when a stage has no events', () => {
    const onlyTransform: PipelineEvent[] = [sampleEvents[0]];
    render(<PipelineView events={onlyTransform} />);

    // Three empty columns means three "No events" placeholders.
    const placeholders = screen.getAllByText(/No events/i);
    expect(placeholders.length).toBe(3);
  });

  it('fires onSelect with the event id when an event line is clicked', () => {
    const onSelect = vi.fn();
    render(<PipelineView events={sampleEvents} onSelect={onSelect} />);

    fireEvent.click(screen.getByTestId('pipeline-event-e3'));
    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(onSelect).toHaveBeenCalledWith('e3');
  });

  it('marks related events via data-related when a sibling is selected', () => {
    // Selected event = e1 (relatedId="g1"). e2 and e3 also have relatedId="g1"
    // so all three should be marked related. e4 has no relatedId and a
    // different source/turn, so it should NOT be related.
    render(
      <PipelineView events={sampleEvents} selectedEventId="e1" />,
    );

    expect(
      screen.getByTestId('pipeline-event-e1').getAttribute('data-selected'),
    ).toBe('true');
    expect(
      screen.getByTestId('pipeline-event-e2').getAttribute('data-related'),
    ).toBe('true');
    expect(
      screen.getByTestId('pipeline-event-e3').getAttribute('data-related'),
    ).toBe('true');
    expect(
      screen.getByTestId('pipeline-event-e4').getAttribute('data-related'),
    ).toBe('false');
  });
});
