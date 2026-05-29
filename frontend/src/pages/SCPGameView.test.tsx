/**
 * AbilityButtons — the Activate affordance for SCP activated/modal abilities.
 * The rest of the modal-human path (ChoiceModal render + /choice submit) is the
 * shared, separately-tested usePendingChoice flow.
 */
import { describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

import { AbilityButtons } from './SCPGameView';
import type { CardData } from '../types';

function card(overrides: Partial<CardData>): CardData {
  return {
    id: 'c1',
    name: 'Operative',
    types: ['SCP_PERSONNEL'],
    subtypes: [],
    ...overrides,
  } as CardData;
}

describe('AbilityButtons', () => {
  it('renders an Activate button for an affordable, non-spent ability and fires onActivate', () => {
    const onActivate = vi.fn();
    render(
      <AbilityButtons
        card={card({
          scp_abilities: [
            { index: 0, description: 'Do X', cost: 'Exhaust', is_modal: false, affordable: true, spent: false },
          ],
        })}
        onActivate={onActivate}
        disabled={false}
      />,
    );
    fireEvent.click(screen.getByText(/Activate \(Exhaust\)/));
    expect(onActivate).toHaveBeenCalledWith('c1', 0);
  });

  it('labels a modal ability as "choose one"', () => {
    render(
      <AbilityButtons
        card={card({
          scp_abilities: [
            {
              index: 1, description: 'Choose one', cost: 'Free', is_modal: true, affordable: true, spent: false,
              modes: [{ index: 0, label: 'A' }, { index: 1, label: 'B' }],
            },
          ],
        })}
        onActivate={vi.fn()}
        disabled={false}
      />,
    );
    expect(screen.getByText(/choose one/i)).toBeInTheDocument();
  });

  it('hides spent or unaffordable abilities (renders nothing)', () => {
    const { container } = render(
      <AbilityButtons
        card={card({
          scp_abilities: [
            { index: 0, description: 'Spent', cost: 'Free', is_modal: false, affordable: true, spent: true },
            { index: 1, description: 'Too costly', cost: 'Pay 5 briefing', is_modal: false, affordable: false, spent: false },
          ],
        })}
        onActivate={vi.fn()}
        disabled={false}
      />,
    );
    expect(container.querySelectorAll('button')).toHaveLength(0);
  });
});
