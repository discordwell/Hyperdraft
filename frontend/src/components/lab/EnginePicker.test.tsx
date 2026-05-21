/**
 * EnginePicker unit tests — Phase B2 (search + sort controls).
 *
 * Opens the picker via the ⌘E chord (same path users hit), then asserts
 * the filter input narrows the visible grid, sort buttons reorder it,
 * and keyboard nav still loads the highlighted engine via useNavigate.
 */

import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { EnginePicker } from './EnginePicker';
import { LAB_ENGINES } from './engineMeta';

const navigateMock = vi.fn();

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>(
    'react-router-dom',
  );
  return {
    ...actual,
    useNavigate: () => navigateMock,
  };
});

/**
 * happy-dom v15 ships `window.localStorage` as a bare object with no
 * methods, so install a minimal in-memory Storage shim per test. This
 * matches the behavior our component code expects from a real browser.
 */
function installLocalStorageShim() {
  const store = new Map<string, string>();
  const shim: Storage = {
    get length() {
      return store.size;
    },
    clear: () => store.clear(),
    getItem: (key) => (store.has(key) ? store.get(key)! : null),
    key: (i) => Array.from(store.keys())[i] ?? null,
    removeItem: (key) => {
      store.delete(key);
    },
    setItem: (key, value) => {
      store.set(key, String(value));
    },
  };
  Object.defineProperty(window, 'localStorage', {
    value: shim,
    configurable: true,
    writable: true,
  });
}

function renderPicker() {
  return render(
    <MemoryRouter>
      <EnginePicker />
    </MemoryRouter>,
  );
}

/** Fire the ⌘E chord at document level — same path useCmdE listens on. */
function openPicker() {
  fireEvent.keyDown(document, { key: 'e', metaKey: true });
}

function cardIds(): string[] {
  // engine-picker-card-<id> data-testids are emitted on each visible card,
  // in render order. Strip the prefix and return the engine ids.
  return Array.from(
    document.querySelectorAll('[data-testid^="engine-picker-card-"]'),
  ).map((el) => (el.getAttribute('data-testid') || '').replace('engine-picker-card-', ''));
}

beforeEach(() => {
  navigateMock.mockReset();
  installLocalStorageShim();
});

afterEach(() => {
  // Make sure body scroll-lock doesn't leak across tests.
  document.body.style.overflow = '';
});

describe('EnginePicker — search + sort (Phase B2)', () => {
  it('is closed by default and renders nothing', () => {
    renderPicker();
    expect(screen.queryByRole('dialog', { name: /switch engine/i })).toBeNull();
  });

  it('opens via ⌘E and auto-focuses the search input', async () => {
    renderPicker();
    act(() => openPicker());

    expect(
      screen.getByRole('dialog', { name: /switch engine/i }),
    ).toBeInTheDocument();
    const search = screen.getByTestId('engine-picker-search') as HTMLInputElement;
    await waitFor(() => expect(document.activeElement).toBe(search));
  });

  it('defaults to Completeness sort — highest completeness first', () => {
    renderPicker();
    act(() => openPicker());

    const ids = cardIds();
    expect(ids).toHaveLength(LAB_ENGINES.length);

    const expected = [...LAB_ENGINES]
      .sort((a, b) => b.completeness - a.completeness)
      .map((e) => e.id);
    expect(ids).toEqual(expected);
  });

  it('filters by name / code / id / subtitle as the user types', () => {
    renderPicker();
    act(() => openPicker());

    const search = screen.getByTestId('engine-picker-search') as HTMLInputElement;

    // Name match — "Magic" should match the MTG engine.
    fireEvent.change(search, { target: { value: 'Magic' } });
    expect(cardIds()).toEqual(['mtg']);

    // Code match (case-insensitive) — "ygo" → yugioh only.
    fireEvent.change(search, { target: { value: 'ygo' } });
    expect(cardIds()).toEqual(['yugioh']);

    // ID match.
    fireEvent.change(search, { target: { value: 'finance' } });
    expect(cardIds()).toEqual(['finance']);

    // Subtitle match — only depths mentions "sonar".
    fireEvent.change(search, { target: { value: 'sonar' } });
    expect(cardIds()).toEqual(['depths']);

    // Empty query restores the full list.
    fireEvent.change(search, { target: { value: '' } });
    expect(cardIds()).toHaveLength(LAB_ENGINES.length);

    // No-match query renders the empty-state.
    fireEvent.change(search, { target: { value: 'zzznotanengine' } });
    expect(cardIds()).toEqual([]);
    expect(screen.getByTestId('engine-picker-empty')).toBeInTheDocument();
  });

  it('A→Z sort orders alphabetically by name', () => {
    renderPicker();
    act(() => openPicker());

    fireEvent.click(screen.getByTestId('engine-picker-sort-alpha'));

    const expected = [...LAB_ENGINES]
      .sort((a, b) => a.name.localeCompare(b.name))
      .map((e) => e.id);
    expect(cardIds()).toEqual(expected);
  });

  it('Untouched-first sort moves played engines to the back', () => {
    // Pretend two engines have been played.
    window.localStorage.setItem(
      'hd.played_engines',
      JSON.stringify(['mtg', 'hearthstone']),
    );

    renderPicker();
    act(() => openPicker());
    fireEvent.click(screen.getByTestId('engine-picker-sort-untouched'));

    const ids = cardIds();
    const lastTwo = ids.slice(-2);
    expect(new Set(lastTwo)).toEqual(new Set(['mtg', 'hearthstone']));

    // Untouched engines come first; first card should not be one of the
    // played ones.
    expect(['mtg', 'hearthstone']).not.toContain(ids[0]);
  });

  it('Untouched-first falls back to A→Z when localStorage is absent', () => {
    // No localStorage key set.
    renderPicker();
    act(() => openPicker());
    fireEvent.click(screen.getByTestId('engine-picker-sort-untouched'));

    const expected = [...LAB_ENGINES]
      .sort((a, b) => a.name.localeCompare(b.name))
      .map((e) => e.id);
    expect(cardIds()).toEqual(expected);
  });

  it('Untouched-first tolerates malformed localStorage (no crash, no sort effect)', () => {
    window.localStorage.setItem('hd.played_engines', '{not json');

    renderPicker();
    act(() => openPicker());
    fireEvent.click(screen.getByTestId('engine-picker-sort-untouched'));

    // Treated as "no engines played" → pure A→Z fallback.
    const expected = [...LAB_ENGINES]
      .sort((a, b) => a.name.localeCompare(b.name))
      .map((e) => e.id);
    expect(cardIds()).toEqual(expected);
  });

  it('Enter loads the engine at the current cursor in the filtered list', () => {
    renderPicker();
    act(() => openPicker());

    // Filter to a single engine so cursor=0 is unambiguous.
    const search = screen.getByTestId('engine-picker-search') as HTMLInputElement;
    fireEvent.change(search, { target: { value: 'depths' } });
    expect(cardIds()).toEqual(['depths']);

    act(() => {
      fireEvent.keyDown(document, { key: 'Enter' });
    });
    expect(navigateMock).toHaveBeenCalledWith('/deckbuilder/depths');
  });

  it('arrow keys move the cursor within the filtered set', () => {
    renderPicker();
    act(() => openPicker());

    // Switch to alpha sort for a predictable order.
    fireEvent.click(screen.getByTestId('engine-picker-sort-alpha'));
    const orderedIds = cardIds();
    expect(orderedIds.length).toBeGreaterThan(1);

    // ArrowRight moves cursor 0 → 1; Enter loads engine at idx 1.
    act(() => fireEvent.keyDown(document, { key: 'ArrowRight' }));
    act(() => fireEvent.keyDown(document, { key: 'Enter' }));
    expect(navigateMock).toHaveBeenCalledWith(`/deckbuilder/${orderedIds[1]}`);
  });

  it('resets cursor to 0 when the query changes — Enter loads first visible engine', () => {
    renderPicker();
    act(() => openPicker());

    // Move cursor off 0 first.
    act(() => fireEvent.keyDown(document, { key: 'ArrowRight' }));
    act(() => fireEvent.keyDown(document, { key: 'ArrowRight' }));

    // Now narrow the filter — cursor should snap back to 0.
    const search = screen.getByTestId('engine-picker-search') as HTMLInputElement;
    fireEvent.change(search, { target: { value: 'pok' } });
    const visible = cardIds();
    expect(visible[0]).toBe('pokemon');

    act(() => fireEvent.keyDown(document, { key: 'Enter' }));
    expect(navigateMock).toHaveBeenLastCalledWith('/deckbuilder/pokemon');
  });

  it('Enter is a no-op when the filter matches nothing', () => {
    renderPicker();
    act(() => openPicker());

    const search = screen.getByTestId('engine-picker-search') as HTMLInputElement;
    fireEvent.change(search, { target: { value: 'zzznoengine' } });
    expect(cardIds()).toEqual([]);

    act(() => fireEvent.keyDown(document, { key: 'Enter' }));
    expect(navigateMock).not.toHaveBeenCalled();
  });

  it('Escape closes the overlay', () => {
    renderPicker();
    act(() => openPicker());
    expect(
      screen.getByRole('dialog', { name: /switch engine/i }),
    ).toBeInTheDocument();

    act(() => fireEvent.keyDown(document, { key: 'Escape' }));
    expect(screen.queryByRole('dialog', { name: /switch engine/i })).toBeNull();
  });

  it('active sort button gets ink fill + paper text', () => {
    renderPicker();
    act(() => openPicker());

    const completenessBtn = screen.getByTestId('engine-picker-sort-completeness');
    const alphaBtn = screen.getByTestId('engine-picker-sort-alpha');

    expect(completenessBtn.getAttribute('aria-checked')).toBe('true');
    expect(alphaBtn.getAttribute('aria-checked')).toBe('false');

    fireEvent.click(alphaBtn);
    expect(alphaBtn.getAttribute('aria-checked')).toBe('true');
    expect(completenessBtn.getAttribute('aria-checked')).toBe('false');
  });

  it('renders the controls bar above the grid', () => {
    renderPicker();
    act(() => openPicker());
    const controls = screen.getByTestId('engine-picker-controls');
    const grid = screen.getByTestId('engine-picker-grid');
    expect(controls).toBeInTheDocument();
    // The dialog has rows: header, controls, grid, footer. Controls'
    // compareDocumentPosition with grid should report it precedes grid.
    expect(
      controls.compareDocumentPosition(grid) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    // Sanity: at least one card lives inside the grid.
    expect(within(grid).getAllByTestId(/engine-picker-card-/).length).toBeGreaterThan(0);
  });
});
