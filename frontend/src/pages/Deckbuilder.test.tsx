/**
 * Deckbuilder smoke test — Phase C / buildplan item 9 lab port.
 *
 * Asserts:
 *   1. The lab masthead renders the `Deckbuilder` mark + lobby link.
 *   2. The caption rail (`HD-DECKBUILDER · LIBRARY · v4.7`) is present.
 *   3. The card grid section (per-engine body) is still mounted alongside
 *      the lab-posture deck rail — i.e. the seam exists.
 *   4. The engine select renders, with MTG as the default.
 *
 * Mocks the deckbuilderAPI so the page mounts without network. The store
 * effects (loadSavedDecks, searchCards) fire on mount; both resolve to
 * empty results to exercise the empty-state without per-engine card data.
 */
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../services/deckbuilderApi', () => ({
  deckbuilderAPI: {
    searchCards: vi.fn().mockResolvedValue({ cards: [], total: 0 }),
    listDecks: vi.fn().mockResolvedValue({ decks: [] }),
    llmStatus: vi.fn().mockResolvedValue({ available: false }),
    getDeckStats: vi.fn().mockResolvedValue({
      card_count: 0,
      type_breakdown: {},
      validation: { is_valid: true, errors: [] },
    }),
  },
}));

import { Deckbuilder } from './Deckbuilder';

function renderPage(path = '/deckbuilder') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/deckbuilder" element={<Deckbuilder />} />
        <Route path="/deckbuilder/:game" element={<Deckbuilder />} />
        <Route path="/" element={<div data-testid="lab-home" />} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  // Reset the deckbuilderStore between tests by resetting modules.
});

afterEach(() => {
  vi.clearAllMocks();
});

describe('Deckbuilder (lab posture)', () => {
  it('renders the lab masthead with the Deckbuilder heading + lobby link', () => {
    renderPage();

    // The masthead block uses Instrument Serif "Deckbuilder" heading.
    expect(
      screen.getByRole('heading', { level: 1, name: /Deckbuilder/i }),
    ).toBeInTheDocument();
    // Lobby back-link is a button with the visible "← Lobby" text + an
    // aria-label of "Back to lobby" (the accessible name takes the latter).
    expect(screen.getByRole('button', { name: /Back to lobby/i })).toBeInTheDocument();
  });

  it('renders the caption rail with HD-DECKBUILDER mark', () => {
    renderPage();

    const caption = screen.getByTestId('deckbuilder-caption');
    expect(caption).toBeInTheDocument();
    expect(caption.textContent).toMatch(/HD-DECKBUILDER/);
    expect(caption.textContent).toMatch(/LIBRARY/);
    expect(caption.textContent).toMatch(/v4\.7/);
  });

  it('still mounts the per-engine card grid section alongside the deck rail', () => {
    renderPage();

    // The seam: both the per-engine card grid and the lab deck rail
    // are present in the body. The grid section is the per-engine body
    // (CardBrowser inside) — staying intact is the whole point of the
    // wrapper-only port.
    expect(screen.getByTestId('deckbuilder-grid-section')).toBeInTheDocument();
    expect(screen.getByTestId('deckbuilder-deck-rail')).toBeInTheDocument();
    expect(screen.getByTestId('deckbuilder-body')).toBeInTheDocument();
  });

  it('exposes the engine selector with MTG as the default', () => {
    renderPage();

    const select = screen.getByLabelText('Game') as HTMLSelectElement;
    expect(select).toBeInTheDocument();
    expect(select.value).toBe('mtg');
  });

  it('renders the AI Assist + Hybrid Build footer', () => {
    renderPage();

    // Lab-posture footer is mounted with its testid.
    expect(screen.getByTestId('deckbuilder-ai-assist')).toBeInTheDocument();
    // The "AI Assist" caption + "Hybrid" caption are mono uppercase labels.
    expect(screen.getByText('AI Assist')).toBeInTheDocument();
    expect(screen.getByText('Hybrid')).toBeInTheDocument();
  });
});
