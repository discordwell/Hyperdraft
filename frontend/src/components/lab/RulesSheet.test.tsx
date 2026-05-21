/**
 * RulesSheet unit tests — verify the panel mounts closed, opens on `?`,
 * closes on Esc, and renders engine-correct content when an engine
 * override is supplied.
 */

import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';

import { RulesSheet } from './RulesSheet';

function renderAt(path: string, engineId?: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <RulesSheet engineId={engineId} />
    </MemoryRouter>,
  );
}

describe('RulesSheet', () => {
  it('mounts closed by default', () => {
    renderAt('/');
    expect(screen.queryByTestId('lab-rules-sheet')).not.toBeInTheDocument();
  });

  it('opens when the user hits `?` and closes on Esc', () => {
    renderAt('/');
    // Open via the global ? keybind.
    fireEvent.keyDown(document, { key: '?' });
    const panel = screen.getByTestId('lab-rules-sheet');
    expect(panel).toBeInTheDocument();
    // The MTG fallback title should appear on `/` (no route-derived engine,
    // no localStorage hint in the happy-dom test env).
    expect(
      screen.getByRole('dialog', { name: /rules sheet/i }),
    ).toBeInTheDocument();

    // Esc closes.
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.queryByTestId('lab-rules-sheet')).not.toBeInTheDocument();
  });

  it('renders MTG content with at least one markdown section heading', () => {
    renderAt('/', 'mtg');
    fireEvent.keyDown(document, { key: '?' });

    // The MTG sheet uses `## Zones`, `## Turn structure`, `## Win condition`,
    // `## One quirk to know` — assert that the first one renders as a
    // section label (h2 with our mono-uppercase styling).
    const heading = screen.getByText(/^Zones$/i, { selector: 'h2' });
    expect(heading).toBeInTheDocument();

    // Engine title appears in the panel header.
    expect(screen.getByText(/Magic: The Gathering/i)).toBeInTheDocument();
  });

  it('honors an explicit engineId override (Yu-Gi-Oh!)', () => {
    renderAt('/', 'yugioh');
    fireEvent.keyDown(document, { key: '?' });

    expect(screen.getByText(/Yu-Gi-Oh!/i)).toBeInTheDocument();
    // YGO sheet mentions Life Points; smoke-check the body actually
    // swapped (not just the title).
    expect(screen.getByText(/8000/)).toBeInTheDocument();
  });

  it('ignores `?` keystrokes while the user is typing in an input', () => {
    render(
      <MemoryRouter initialEntries={['/']}>
        <input data-testid="search" defaultValue="" />
        <RulesSheet />
      </MemoryRouter>,
    );
    const input = screen.getByTestId('search') as HTMLInputElement;
    input.focus();
    fireEvent.keyDown(input, { key: '?' });
    expect(screen.queryByTestId('lab-rules-sheet')).not.toBeInTheDocument();
  });
});
