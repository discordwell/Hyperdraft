/**
 * useCardInspector — shared click-to-inspect modal store.
 *
 * The store is consumed by all 10 engine boards (cats, clankers, mtg, hs,
 * pokemon, ygo, mc, depths, finance, scp) — these tests pin the
 * contract so a future store refactor cannot silently break any of them.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

import { useCardInspectorStore } from './useCardInspector';

describe('useCardInspectorStore', () => {
  beforeEach(() => {
    useCardInspectorStore.getState().close();
  });

  it('starts empty', () => {
    const s = useCardInspectorStore.getState();
    expect(s.card).toBeNull();
    expect(s.actions).toEqual([]);
  });

  it('open() sets the card and action list', () => {
    useCardInspectorStore.getState().open(
      { id: 'c1', name: 'Test Card', text: 'Deal 2 damage.' },
      [{ label: 'Play', onClick: () => {} }],
    );
    const s = useCardInspectorStore.getState();
    expect(s.card?.name).toBe('Test Card');
    expect(s.actions).toHaveLength(1);
    expect(s.actions[0].label).toBe('Play');
  });

  it('open() with no actions defaults to empty list', () => {
    useCardInspectorStore.getState().open({ id: 'c1', name: 'Inspect Only' });
    expect(useCardInspectorStore.getState().actions).toEqual([]);
  });

  it('close() clears card + actions', () => {
    useCardInspectorStore.getState().open(
      { id: 'c1', name: 'X' },
      [{ label: 'Play', onClick: () => {} }],
    );
    useCardInspectorStore.getState().close();
    const s = useCardInspectorStore.getState();
    expect(s.card).toBeNull();
    expect(s.actions).toEqual([]);
  });

  it('open() replaces a prior card without leaking stale actions', () => {
    useCardInspectorStore.getState().open(
      { id: 'c1', name: 'First' },
      [
        { label: 'Activate', onClick: () => {} },
        { label: 'Tribute', onClick: () => {} },
      ],
    );
    useCardInspectorStore.getState().open(
      { id: 'c2', name: 'Second' },
      [{ label: 'Cast', onClick: () => {} }],
    );
    const s = useCardInspectorStore.getState();
    expect(s.card?.id).toBe('c2');
    expect(s.actions).toHaveLength(1);
    expect(s.actions[0].label).toBe('Cast');
  });

  it('actions carry through disabled + disabledReason metadata', () => {
    useCardInspectorStore.getState().open(
      { id: 'c1', name: 'Pricey' },
      [
        {
          label: 'Play',
          disabled: true,
          disabledReason: 'Not enough mana',
          onClick: () => {},
        },
      ],
    );
    const a = useCardInspectorStore.getState().actions[0];
    expect(a.disabled).toBe(true);
    expect(a.disabledReason).toBe('Not enough mana');
  });

  it('action variants survive the round-trip', () => {
    useCardInspectorStore.getState().open(
      { id: 'c1', name: 'X' },
      [
        { label: 'Cast', variant: 'primary', onClick: () => {} },
        { label: 'Activate', variant: 'secondary', onClick: () => {} },
        { label: 'Destroy', variant: 'danger', onClick: () => {} },
      ],
    );
    const actions = useCardInspectorStore.getState().actions;
    expect(actions.map((a) => a.variant)).toEqual(['primary', 'secondary', 'danger']);
  });

  it('onClick handlers are invoked exactly once per call', () => {
    const onPlay = vi.fn();
    useCardInspectorStore.getState().open(
      { id: 'c1', name: 'X' },
      [{ label: 'Play', onClick: onPlay }],
    );
    const action = useCardInspectorStore.getState().actions[0];
    action.onClick();
    expect(onPlay).toHaveBeenCalledTimes(1);
    action.onClick();
    expect(onPlay).toHaveBeenCalledTimes(2);
  });

  it('onClick returning false is preserved for the modal to read', () => {
    useCardInspectorStore.getState().open(
      { id: 'c1', name: 'X' },
      [{ label: 'Pick Target', onClick: () => false }],
    );
    const action = useCardInspectorStore.getState().actions[0];
    expect(action.onClick()).toBe(false);
  });
});
