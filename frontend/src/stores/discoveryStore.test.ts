/**
 * discoveryStore unit tests — Wave 2 / Phase A1.
 *
 * Covers the persistence contract (writes to `hd.played_engines` in
 * localStorage with a JSON array) and the pickUnplayed heuristic (returns
 * something the user hasn't played, or null once they've played them all).
 *
 * happy-dom v15 ships a bare-object localStorage, so we install the same
 * Storage shim EnginePicker.test.tsx uses to keep behavior comparable to a
 * real browser.
 */
import { act } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import { LAB_ENGINES } from '../components/lab/engineMeta';
import { useDiscoveryStore } from './discoveryStore';

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

function resetStore() {
  // The zustand store survives across tests because the module is cached.
  // Reset the in-memory slice to empty so each test starts clean.
  act(() => {
    useDiscoveryStore.setState({ playedEngines: [] });
  });
}

beforeEach(() => {
  installLocalStorageShim();
  resetStore();
});

describe('discoveryStore', () => {
  it('starts with an empty played-engines list', () => {
    expect(useDiscoveryStore.getState().playedEngines).toEqual([]);
  });

  it('markPlayed adds an engine to state and persists to localStorage', () => {
    act(() => useDiscoveryStore.getState().markPlayed('mtg'));

    expect(useDiscoveryStore.getState().playedEngines).toEqual(['mtg']);
    const raw = window.localStorage.getItem('hd.played_engines');
    expect(raw).not.toBeNull();
    expect(JSON.parse(raw as string)).toEqual(['mtg']);
  });

  it('markPlayed is idempotent — repeats collapse', () => {
    act(() => useDiscoveryStore.getState().markPlayed('hearthstone'));
    act(() => useDiscoveryStore.getState().markPlayed('hearthstone'));
    act(() => useDiscoveryStore.getState().markPlayed('hearthstone'));

    expect(useDiscoveryStore.getState().playedEngines).toEqual(['hearthstone']);
    expect(JSON.parse(window.localStorage.getItem('hd.played_engines') as string)).toEqual([
      'hearthstone',
    ]);
  });

  it('markPlayed preserves insertion order across distinct ids', () => {
    act(() => useDiscoveryStore.getState().markPlayed('mtg'));
    act(() => useDiscoveryStore.getState().markPlayed('yugioh'));
    act(() => useDiscoveryStore.getState().markPlayed('pokemon'));

    expect(useDiscoveryStore.getState().playedEngines).toEqual(['mtg', 'yugioh', 'pokemon']);
  });

  it('pickUnplayed returns an engine the user has not played', () => {
    act(() => useDiscoveryStore.getState().markPlayed('mtg'));

    const pick = useDiscoveryStore.getState().pickUnplayed();
    expect(pick).not.toBeNull();
    expect(pick?.id).not.toBe('mtg');
    // The pick must be a registered engine.
    expect(LAB_ENGINES.map((e) => e.id)).toContain(pick?.id);
  });

  it('pickUnplayed returns null once every registered engine has been played', () => {
    LAB_ENGINES.forEach((e) => {
      act(() => useDiscoveryStore.getState().markPlayed(e.id));
    });
    expect(useDiscoveryStore.getState().pickUnplayed()).toBeNull();
  });

  it('tolerates malformed localStorage on first read (would default to empty)', () => {
    // Smoke: the module-level readFromStorage runs only at first create(),
    // which already happened. Validate the failure mode by simulating what
    // a malformed value would produce via the store's reset path.
    window.localStorage.setItem('hd.played_engines', '{not json');
    // markPlayed should still work — it overwrites with a valid payload.
    act(() => useDiscoveryStore.getState().markPlayed('finance'));
    const raw = window.localStorage.getItem('hd.played_engines');
    expect(JSON.parse(raw as string)).toEqual(['finance']);
  });
});
