/**
 * EngineRack unit tests — Wave 2 / Phase A1 (NEW pill) + Phase B1 (filters).
 *
 * Asserts:
 *  - rows for engines not in `playedEngines` render a NEW pill,
 *  - the search input narrows the visible rows by name / code / id / subtitle,
 *  - the sort selector cycles A→Z / Completeness / Untouched first,
 *  - the empty-state plate renders when no engine matches.
 *
 * The discovery store is reset between tests so each case controls its own
 * `playedEngines` set; localStorage gets the same Storage shim the
 * EnginePicker tests use, since happy-dom v15's bare object trips up the
 * defensive reads in both surfaces.
 */
import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { EngineRack } from './EngineRack';
import { LAB_ENGINES } from './engineMeta';
import { useDiscoveryStore } from '../../stores/discoveryStore';

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

function visibleRowIds(): string[] {
  return Array.from(document.querySelectorAll('[data-testid^="engine-rack-row-"]')).map(
    (el) => (el.getAttribute('data-testid') || '').replace('engine-rack-row-', ''),
  );
}

beforeEach(() => {
  installLocalStorageShim();
  act(() => {
    useDiscoveryStore.setState({ playedEngines: [] });
  });
});

afterEach(() => {
  act(() => {
    useDiscoveryStore.setState({ playedEngines: [] });
  });
});

describe('EngineRack — A1 NEW pill + B1 filters', () => {
  it('renders a NEW pill on every row when no engines have been played', () => {
    render(<EngineRack />);
    // Every registered engine should expose its NEW pill.
    for (const e of LAB_ENGINES) {
      expect(screen.getByTestId(`engine-rack-new-${e.id}`)).toBeInTheDocument();
    }
  });

  it('omits the NEW pill on engines the user has played', () => {
    act(() => {
      useDiscoveryStore.setState({ playedEngines: ['mtg', 'hearthstone'] });
    });
    render(<EngineRack />);

    expect(screen.queryByTestId('engine-rack-new-mtg')).toBeNull();
    expect(screen.queryByTestId('engine-rack-new-hearthstone')).toBeNull();
    // Other engines still get the pill.
    expect(screen.getByTestId('engine-rack-new-pokemon')).toBeInTheDocument();
  });

  it('search input narrows the visible row set by name', () => {
    render(<EngineRack />);
    const search = screen.getByTestId('engine-rack-search') as HTMLInputElement;

    fireEvent.change(search, { target: { value: 'Magic' } });
    expect(visibleRowIds()).toEqual(['mtg']);
  });

  it('search input matches code / id / subtitle case-insensitively', () => {
    render(<EngineRack />);
    const search = screen.getByTestId('engine-rack-search') as HTMLInputElement;

    fireEvent.change(search, { target: { value: 'ygo' } });
    expect(visibleRowIds()).toEqual(['yugioh']);

    fireEvent.change(search, { target: { value: 'finance' } });
    expect(visibleRowIds()).toEqual(['finance']);

    // Subtitle of depths mentions sonar.
    fireEvent.change(search, { target: { value: 'sonar' } });
    expect(visibleRowIds()).toEqual(['depths']);
  });

  it('renders the empty-state plate when nothing matches', () => {
    render(<EngineRack />);
    const search = screen.getByTestId('engine-rack-search') as HTMLInputElement;

    fireEvent.change(search, { target: { value: 'zzznotanengine' } });
    expect(visibleRowIds()).toEqual([]);
    expect(screen.getByTestId('engine-rack-empty')).toBeInTheDocument();
  });

  it('defaults to Completeness sort — highest completeness first', () => {
    render(<EngineRack />);
    const expected = [...LAB_ENGINES]
      .sort((a, b) => b.completeness - a.completeness)
      .map((e) => e.id);
    expect(visibleRowIds()).toEqual(expected);
  });

  it('sort selector cycles A→Z / Completeness / Untouched first', () => {
    // Pretend two engines have been played so untouched-first has work to do.
    act(() => {
      useDiscoveryStore.setState({ playedEngines: ['mtg', 'hearthstone'] });
    });
    render(<EngineRack />);

    // Alpha
    fireEvent.click(screen.getByTestId('engine-rack-sort-alpha'));
    const alpha = [...LAB_ENGINES].sort((a, b) => a.name.localeCompare(b.name)).map((e) => e.id);
    expect(visibleRowIds()).toEqual(alpha);

    // Completeness — restored sort.
    fireEvent.click(screen.getByTestId('engine-rack-sort-completeness'));
    const complete = [...LAB_ENGINES]
      .sort((a, b) => b.completeness - a.completeness)
      .map((e) => e.id);
    expect(visibleRowIds()).toEqual(complete);

    // Untouched-first — played engines (mtg, hearthstone) get pushed to the back.
    fireEvent.click(screen.getByTestId('engine-rack-sort-untouched'));
    const ids = visibleRowIds();
    const tail = ids.slice(-2);
    expect(new Set(tail)).toEqual(new Set(['mtg', 'hearthstone']));
    expect(['mtg', 'hearthstone']).not.toContain(ids[0]);
  });

  it('active sort button gets aria-checked=true', () => {
    render(<EngineRack />);
    const completeness = screen.getByTestId('engine-rack-sort-completeness');
    const alpha = screen.getByTestId('engine-rack-sort-alpha');

    expect(completeness.getAttribute('aria-checked')).toBe('true');
    expect(alpha.getAttribute('aria-checked')).toBe('false');

    fireEvent.click(alpha);
    expect(alpha.getAttribute('aria-checked')).toBe('true');
    expect(completeness.getAttribute('aria-checked')).toBe('false');
  });
});
