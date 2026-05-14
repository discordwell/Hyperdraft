/**
 * ChoiceModal overlay-mode tests (Phase 5b polish).
 *
 * Phase 5b shipped engine-authoritative cast-time targeting: MTG cards
 * with ``target_requirements`` emit a ``PendingChoice`` with
 * ``interaction_mode='overlay'``. ChoiceModal switches to a floating
 * cancel-pill rendering (no backdrop, no panel) and GameBoard handles
 * the click-to-target highlighting + submission.
 *
 * These tests cover the ChoiceModal contract in isolation:
 *   1. overlay mode hides the modal panel and renders the cancel pill
 *   2. modal mode (default) still renders the full panel
 *
 * The GameBoard click-intercept path is covered in GameBoard.overlay.test.tsx.
 */

import { describe, it, expect, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { ChoiceModal } from './ChoiceModal';
import type { PendingChoice } from '../../types';

const baseChoice: PendingChoice = {
  id: 'pc-1',
  choice_type: 'target',
  player: 'alice',
  prompt: 'Choose a target creature',
  options: [
    { id: 'card-1', label: 'Grizzly Bears' },
    { id: 'card-2', label: 'Llanowar Elves' },
  ],
  source_id: 'spell-1',
  min_choices: 1,
  max_choices: 1,
};

describe('ChoiceModal overlay mode', () => {
  it('renders the cancel pill but NOT the modal panel when interaction_mode is overlay', () => {
    const onSubmit = vi.fn();
    const onCancel = vi.fn();
    const overlayChoice: PendingChoice = {
      ...baseChoice,
      interaction_mode: 'overlay',
    };

    render(
      <ChoiceModal
        pendingChoice={overlayChoice}
        battlefield={[]}
        hand={[]}
        graveyard={{}}
        onSubmit={onSubmit}
        onCancel={onCancel}
      />
    );

    // Overlay container is mounted with its testid.
    expect(screen.getByTestId('choice-overlay')).toBeInTheDocument();
    // Cancel button is rendered when onCancel is provided.
    expect(screen.getByTestId('choice-overlay-cancel')).toBeInTheDocument();

    // The big "Select Target" header (used by the modal panel) must NOT
    // appear; the prompt copy lives in a small pill instead. The modal
    // panel ships a "Confirm" button — its absence is the key signal that
    // the panel did not render.
    expect(screen.queryByRole('button', { name: /^Confirm/i })).not.toBeInTheDocument();
  });

  it('cancel button invokes onCancel and does NOT submit', () => {
    const onSubmit = vi.fn();
    const onCancel = vi.fn();
    const overlayChoice: PendingChoice = {
      ...baseChoice,
      interaction_mode: 'overlay',
    };

    render(
      <ChoiceModal
        pendingChoice={overlayChoice}
        battlefield={[]}
        hand={[]}
        graveyard={{}}
        onSubmit={onSubmit}
        onCancel={onCancel}
      />
    );

    fireEvent.click(screen.getByTestId('choice-overlay-cancel'));
    expect(onCancel).toHaveBeenCalledTimes(1);
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('falls back to the modal panel rendering when interaction_mode is absent', () => {
    const onSubmit = vi.fn();

    render(
      <ChoiceModal
        pendingChoice={baseChoice}
        battlefield={[]}
        hand={[]}
        graveyard={{}}
        onSubmit={onSubmit}
      />
    );

    // No overlay container.
    expect(screen.queryByTestId('choice-overlay')).not.toBeInTheDocument();
    // Modal panel header is present.
    expect(screen.getByText(/Select Target/i)).toBeInTheDocument();
    // Modal panel's Confirm button is present.
    expect(screen.getByRole('button', { name: /^Confirm/i })).toBeInTheDocument();
  });

  it('falls back to the modal panel when interaction_mode is explicitly "modal"', () => {
    const onSubmit = vi.fn();
    const modalChoice: PendingChoice = {
      ...baseChoice,
      interaction_mode: 'modal',
    };

    render(
      <ChoiceModal
        pendingChoice={modalChoice}
        battlefield={[]}
        hand={[]}
        graveyard={{}}
        onSubmit={onSubmit}
      />
    );

    expect(screen.queryByTestId('choice-overlay')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^Confirm/i })).toBeInTheDocument();
  });
});
