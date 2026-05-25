/**
 * dropChoiceStore — post-drop "what would you like to do?" popup.
 *
 * Used by Yu-Gi-Oh! ("Normal Summon" vs "Set"), and any other engine
 * where the drop target accepts multiple actions. Tests pin the
 * minimal state contract so engines can rely on it.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

import { useDropChoiceStore } from './dropChoiceStore';

describe('dropChoiceStore', () => {
  beforeEach(() => {
    useDropChoiceStore.getState().close();
  });

  it('starts empty', () => {
    const s = useDropChoiceStore.getState();
    expect(s.card).toBeNull();
    expect(s.options).toEqual([]);
    expect(s.position).toBeNull();
  });

  it('open() records card + options + position', () => {
    const onClick = vi.fn();
    useDropChoiceStore.getState().open(
      { id: 'm1', name: 'Blue-Eyes', subtitle: 'Dragon' },
      [
        { label: 'Normal Summon', variant: 'primary', onClick },
        { label: 'Set face-down', variant: 'secondary', onClick: () => {} },
      ],
      { x: 200, y: 320 },
    );
    const s = useDropChoiceStore.getState();
    expect(s.card?.name).toBe('Blue-Eyes');
    expect(s.options).toHaveLength(2);
    expect(s.options[0].label).toBe('Normal Summon');
    expect(s.position).toEqual({ x: 200, y: 320 });
  });

  it('open() without position defaults to centered (null)', () => {
    useDropChoiceStore.getState().open(
      { id: 'm1', name: 'X' },
      [{ label: 'OK', onClick: () => {} }],
    );
    expect(useDropChoiceStore.getState().position).toBeNull();
  });

  it('close() wipes everything', () => {
    useDropChoiceStore.getState().open(
      { id: 'm1', name: 'X' },
      [{ label: 'OK', onClick: () => {} }],
      { x: 10, y: 10 },
    );
    useDropChoiceStore.getState().close();
    const s = useDropChoiceStore.getState();
    expect(s.card).toBeNull();
    expect(s.options).toEqual([]);
    expect(s.position).toBeNull();
  });

  it('open() replaces a prior popup without leaking stale options', () => {
    useDropChoiceStore.getState().open(
      { id: 'm1', name: 'First' },
      [
        { label: 'A', onClick: () => {} },
        { label: 'B', onClick: () => {} },
        { label: 'C', onClick: () => {} },
      ],
    );
    useDropChoiceStore.getState().open(
      { id: 'm2', name: 'Second' },
      [{ label: 'X', onClick: () => {} }],
    );
    const s = useDropChoiceStore.getState();
    expect(s.card?.id).toBe('m2');
    expect(s.options).toHaveLength(1);
    expect(s.options[0].label).toBe('X');
  });

  it('option onClick handlers fire when invoked', () => {
    const summon = vi.fn();
    const set = vi.fn();
    useDropChoiceStore.getState().open(
      { id: 'm1', name: 'X' },
      [
        { label: 'Summon', onClick: summon },
        { label: 'Set', onClick: set },
      ],
    );
    const s = useDropChoiceStore.getState();
    s.options[0].onClick();
    expect(summon).toHaveBeenCalledTimes(1);
    expect(set).not.toHaveBeenCalled();
  });

  it('disabled options round-trip the disabled flag + reason', () => {
    useDropChoiceStore.getState().open(
      { id: 'm1', name: 'Pricey' },
      [
        {
          label: 'Tribute summon',
          disabled: true,
          disabledReason: 'Need 1 monster on the field',
          onClick: () => {},
        },
      ],
    );
    const opt = useDropChoiceStore.getState().options[0];
    expect(opt.disabled).toBe(true);
    expect(opt.disabledReason).toBe('Need 1 monster on the field');
  });
});
