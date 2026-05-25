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

  it('primeCard accepts an optional intent and stores it', () => {
    useCardZoneStore
      .getState()
      .primeCard('c1', 'pokemon', ['pkm-pokemon-x'], '#fca5a5', 'attach');
    expect(useCardZoneStore.getState().activeIntent).toBe('attach');
  });

  it('startDrag accepts an optional intent', () => {
    useCardZoneStore
      .getState()
      .startDrag('c1', 'ygo', ['ygo-mzone-0-me'], '#c4b5fd', 'summon');
    expect(useCardZoneStore.getState().activeIntent).toBe('summon');
  });

  it('activeIntent defaults to null when omitted', () => {
    useCardZoneStore.getState().primeCard('c1', 'cats', ['cats-trick'], '#fbbf24');
    expect(useCardZoneStore.getState().activeIntent).toBeNull();
  });

  it('clearAll wipes activeIntent', () => {
    useCardZoneStore
      .getState()
      .primeCard('c1', 'pokemon', ['pkm-pokemon-x'], '#fca5a5', 'evolve');
    useCardZoneStore.getState().clearAll();
    expect(useCardZoneStore.getState().activeIntent).toBeNull();
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

  // -------------------------------------------------------------------------
  // Arc A — choice-driven flow (PR A1).
  // -------------------------------------------------------------------------
  describe('primeFromChoice (Arc A)', () => {
    it('lights up option zones with engine accent + intent=target', () => {
      useCardZoneStore.getState().primeFromChoice({
        choiceId: 'choice-1',
        sourceId: 'spell-bolt',
        prompt: 'Pick a target',
        engineId: 'mtg',
        accent: '#a78bfa',
        optionIds: ['mtg-card-A', 'mtg-card-B'],
      });
      const s = useCardZoneStore.getState();
      expect(s.activeChoiceId).toBe('choice-1');
      expect(s.activeIntent).toBe('target');
      expect(s.engineId).toBe('mtg');
      expect(s.accentColor).toBe('#a78bfa');
      expect(Array.from(s.validZoneIds).sort()).toEqual(['mtg-card-A', 'mtg-card-B']);
      expect(s.pendingTargets).toEqual([]);
    });

    it('clears any card-driven prime when a choice arrives', () => {
      useCardZoneStore.getState().primeCard('hand-spell', 'mtg', ['mtg-battlefield-me'], '#a78bfa');
      useCardZoneStore.getState().primeFromChoice({
        choiceId: 'choice-1',
        sourceId: 'spell-bolt',
        prompt: 'Pick',
        engineId: 'mtg',
        accent: '#a78bfa',
        optionIds: ['mtg-card-A'],
      });
      expect(useCardZoneStore.getState().primedCardId).toBeNull();
      expect(useCardZoneStore.getState().activeChoiceId).toBe('choice-1');
    });

    it('togglePendingTarget appends new picks', () => {
      useCardZoneStore.getState().primeFromChoice({
        choiceId: 'c', sourceId: null, prompt: '', engineId: 'mtg', accent: '#a78bfa',
        optionIds: ['A', 'B', 'C'],
        metadata: { label: '', predicate_description: '', min: 1, max: 3 },
      });
      useCardZoneStore.getState().togglePendingTarget('A');
      useCardZoneStore.getState().togglePendingTarget('B');
      expect(useCardZoneStore.getState().pendingTargets).toEqual(['A', 'B']);
    });

    it('togglePendingTarget toggles off when re-clicked', () => {
      useCardZoneStore.getState().primeFromChoice({
        choiceId: 'c', sourceId: null, prompt: '', engineId: 'mtg', accent: '#a78bfa',
        optionIds: ['A', 'B'],
        metadata: { label: '', predicate_description: '', min: 0, max: 2 },
      });
      useCardZoneStore.getState().togglePendingTarget('A');
      useCardZoneStore.getState().togglePendingTarget('A');
      expect(useCardZoneStore.getState().pendingTargets).toEqual([]);
    });

    it('togglePendingTarget swaps when at max=1 (FIFO replacement)', () => {
      useCardZoneStore.getState().primeFromChoice({
        choiceId: 'c', sourceId: null, prompt: '', engineId: 'mtg', accent: '#a78bfa',
        optionIds: ['A', 'B'],
        metadata: { label: '', predicate_description: '', min: 1, max: 1 },
      });
      useCardZoneStore.getState().togglePendingTarget('A');
      expect(useCardZoneStore.getState().pendingTargets).toEqual(['A']);
      // Click another option — should replace.
      useCardZoneStore.getState().togglePendingTarget('B');
      expect(useCardZoneStore.getState().pendingTargets).toEqual(['B']);
    });

    it('togglePendingTarget evicts oldest when at max>1', () => {
      useCardZoneStore.getState().primeFromChoice({
        choiceId: 'c', sourceId: null, prompt: '', engineId: 'mtg', accent: '#a78bfa',
        optionIds: ['A', 'B', 'C'],
        metadata: { label: '', predicate_description: '', min: 2, max: 2 },
      });
      useCardZoneStore.getState().togglePendingTarget('A');
      useCardZoneStore.getState().togglePendingTarget('B');
      expect(useCardZoneStore.getState().pendingTargets).toEqual(['A', 'B']);
      // At max, pick C — should drop A (oldest).
      useCardZoneStore.getState().togglePendingTarget('C');
      expect(useCardZoneStore.getState().pendingTargets).toEqual(['B', 'C']);
    });

    it('togglePendingTarget is a no-op when no choice active', () => {
      useCardZoneStore.getState().togglePendingTarget('A');
      expect(useCardZoneStore.getState().pendingTargets).toEqual([]);
    });

    it('clearChoice wipes choice state and lit zones but leaves other primes alone', () => {
      useCardZoneStore.getState().primeFromChoice({
        choiceId: 'c', sourceId: null, prompt: '', engineId: 'mtg', accent: '#a78bfa',
        optionIds: ['A', 'B'],
      });
      useCardZoneStore.getState().togglePendingTarget('A');
      useCardZoneStore.getState().clearChoice();
      const s = useCardZoneStore.getState();
      expect(s.activeChoiceId).toBeNull();
      expect(s.pendingTargets).toEqual([]);
      expect(s.validZoneIds.size).toBe(0);
      expect(s.activeIntent).toBeNull();
    });
  });
});
