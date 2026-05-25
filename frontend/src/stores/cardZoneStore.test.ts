/**
 * cardZoneStore — shared card-interaction state used by all engines'
 * hand cards + drop zones. Tests pin the state transitions so a future
 * refactor can't silently break drag-and-drop on any engine.
 */

import { beforeEach, describe, expect, it } from 'vitest';

import {
  useCardZoneStore,
  selectActiveCardId,
  selectIsZoneValid,
  selectIsZoneHovered,
} from './cardZoneStore';

describe('cardZoneStore', () => {
  beforeEach(() => {
    useCardZoneStore.getState().clearAll();
  });

  it('starts empty', () => {
    const s = useCardZoneStore.getState();
    expect(s.primedCardId).toBeNull();
    expect(s.dragCardId).toBeNull();
    expect(s.engineId).toBeNull();
    expect(s.validZoneIds.size).toBe(0);
    expect(s.accentColor).toBeNull();
    expect(s.hoveredZoneId).toBeNull();
  });

  it('primeCard records cardId + engine + valid zones + accent', () => {
    useCardZoneStore.getState().primeCard('c1', 'cats', ['cats-trick'], '#fbbf24');
    const s = useCardZoneStore.getState();
    expect(s.primedCardId).toBe('c1');
    expect(s.engineId).toBe('cats');
    expect(Array.from(s.validZoneIds)).toEqual(['cats-trick']);
    expect(s.accentColor).toBe('#fbbf24');
  });

  it('primeCard clears any in-progress drag', () => {
    useCardZoneStore.getState().startDrag('c1', 'cats', ['cats-trick'], '#fbbf24');
    useCardZoneStore.getState().primeCard('c2', 'cats', ['cats-trick'], '#fbbf24');
    const s = useCardZoneStore.getState();
    expect(s.dragCardId).toBeNull();
    expect(s.primedCardId).toBe('c2');
  });

  it('unprime clears everything', () => {
    useCardZoneStore.getState().primeCard('c1', 'cats', ['cats-trick'], '#fbbf24');
    useCardZoneStore.getState().unprime();
    const s = useCardZoneStore.getState();
    expect(s.primedCardId).toBeNull();
    expect(s.engineId).toBeNull();
    expect(s.validZoneIds.size).toBe(0);
  });

  it('startDrag records dragCardId + clears primedCardId', () => {
    useCardZoneStore.getState().primeCard('c1', 'cats', ['cats-trick'], '#fbbf24');
    useCardZoneStore.getState().startDrag('c1', 'cats', ['cats-trick'], '#fbbf24');
    const s = useCardZoneStore.getState();
    expect(s.dragCardId).toBe('c1');
    expect(s.primedCardId).toBeNull();
  });

  it('endDrag clears drag state but preserves engine/valid (so post-drop UI can still query)', () => {
    useCardZoneStore.getState().startDrag('c1', 'cats', ['cats-trick'], '#fbbf24');
    useCardZoneStore.getState().endDrag();
    const s = useCardZoneStore.getState();
    expect(s.dragCardId).toBeNull();
    expect(s.hoveredZoneId).toBeNull();
  });

  it('setHoveredZone updates the active hover target', () => {
    useCardZoneStore.getState().startDrag('c1', 'cats', ['z1', 'z2'], '#fbbf24');
    useCardZoneStore.getState().setHoveredZone('z1');
    expect(useCardZoneStore.getState().hoveredZoneId).toBe('z1');
    useCardZoneStore.getState().setHoveredZone('z2');
    expect(useCardZoneStore.getState().hoveredZoneId).toBe('z2');
    useCardZoneStore.getState().setHoveredZone(null);
    expect(useCardZoneStore.getState().hoveredZoneId).toBeNull();
  });

  it('clearAll wipes everything regardless of source', () => {
    useCardZoneStore.getState().startDrag('c1', 'cats', ['z1'], '#fbbf24');
    useCardZoneStore.getState().setHoveredZone('z1');
    useCardZoneStore.getState().clearAll();
    const s = useCardZoneStore.getState();
    expect(s.primedCardId).toBeNull();
    expect(s.dragCardId).toBeNull();
    expect(s.engineId).toBeNull();
    expect(s.hoveredZoneId).toBeNull();
    expect(s.validZoneIds.size).toBe(0);
  });

  describe('selectors', () => {
    it('selectActiveCardId returns the dragCardId when dragging', () => {
      useCardZoneStore.getState().startDrag('c1', 'cats', ['z1'], '#fbbf24');
      expect(selectActiveCardId(useCardZoneStore.getState())).toBe('c1');
    });

    it('selectActiveCardId falls back to primedCardId', () => {
      useCardZoneStore.getState().primeCard('c2', 'cats', ['z1'], '#fbbf24');
      expect(selectActiveCardId(useCardZoneStore.getState())).toBe('c2');
    });

    it('selectIsZoneValid reflects validZoneIds membership', () => {
      useCardZoneStore.getState().primeCard('c1', 'cats', ['z1', 'z2'], '#fbbf24');
      const s = useCardZoneStore.getState();
      expect(selectIsZoneValid('z1')(s)).toBe(true);
      expect(selectIsZoneValid('z2')(s)).toBe(true);
      expect(selectIsZoneValid('z3')(s)).toBe(false);
    });

    it('selectIsZoneHovered matches the currently hovered zone', () => {
      useCardZoneStore.getState().startDrag('c1', 'cats', ['z1', 'z2'], '#fbbf24');
      useCardZoneStore.getState().setHoveredZone('z1');
      const s = useCardZoneStore.getState();
      expect(selectIsZoneHovered('z1')(s)).toBe(true);
      expect(selectIsZoneHovered('z2')(s)).toBe(false);
    });
  });
});
