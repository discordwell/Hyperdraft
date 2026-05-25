/**
 * useCardZone — drop-zone hook behavior tests.
 *
 * The critical contract these tests pin is the ORDERING inside onClick /
 * onDrop: `onPlay(cardId)` MUST fire BEFORE `clearAll()`. Engines like
 * Pokemon read `useCardZoneStore.getState().activeIntent` inside their
 * onPlay callback to route between attach / evolve / play. clearAll
 * nulls activeIntent, so reading after-clear would route incorrectly.
 *
 * Original symptom: PKM energy attach click-through landed on Squirtle
 * with the modal open, but no energy attached — the onPlay callback
 * saw activeIntent === null and bailed out.
 */
import { renderHook, act } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useCardZoneStore } from '../stores/cardZoneStore';
import { useCardZone } from './useCardZone';

describe('useCardZone', () => {
  beforeEach(() => {
    useCardZoneStore.getState().clearAll();
  });

  it('onClick reads activeIntent BEFORE clearing the store', () => {
    let observedIntent: string | null | undefined = 'unread';
    const { result } = renderHook(() =>
      useCardZone({
        zoneId: 'pkm-pokemon-X',
        engineId: 'pokemon',
        onPlay: () => {
          // Mirror the PKM pattern: read intent from the store inside onPlay.
          observedIntent = useCardZoneStore.getState().activeIntent;
        },
      }),
    );

    act(() => {
      useCardZoneStore
        .getState()
        .primeCard('water-energy', 'pokemon', ['pkm-pokemon-X'], '#fca5a5', 'attach');
    });

    act(() => {
      result.current.onClick();
    });

    expect(observedIntent).toBe('attach');
    // After onPlay runs, clearAll happens — store is wiped.
    expect(useCardZoneStore.getState().activeIntent).toBeNull();
    expect(useCardZoneStore.getState().primedCardId).toBeNull();
  });

  it('onDrop also reads activeIntent before clearAll', () => {
    let observedIntent: string | null | undefined = 'unread';
    let observedCardId: string | undefined;
    const { result } = renderHook(() =>
      useCardZone({
        zoneId: 'pkm-pokemon-X',
        engineId: 'pokemon',
        onPlay: (cardId) => {
          observedCardId = cardId;
          observedIntent = useCardZoneStore.getState().activeIntent;
        },
      }),
    );

    act(() => {
      useCardZoneStore
        .getState()
        .startDrag('rare-candy', 'pokemon', ['pkm-pokemon-X'], '#fca5a5', 'evolve');
    });

    // Fake a DataTransfer for the drop. The onDrop reads the cardId from
    // the engine-prefixed MIME slot that useHandCard.onDragStart sets.
    const mockData: Record<string, string> = { 'application/x-pokemon-card': 'rare-candy' };
    const fakeEvt = {
      preventDefault: vi.fn(),
      dataTransfer: {
        getData: (type: string) => mockData[type] ?? '',
      },
    } as unknown as React.DragEvent;

    act(() => {
      result.current.onDrop(fakeEvt);
    });

    expect(observedCardId).toBe('rare-candy');
    expect(observedIntent).toBe('evolve');
    expect(useCardZoneStore.getState().activeIntent).toBeNull();
  });

  it('onClick is a no-op when no card is primed', () => {
    const onPlay = vi.fn();
    const { result } = renderHook(() =>
      useCardZone({ zoneId: 'cats-trick', engineId: 'cats', onPlay }),
    );

    act(() => {
      result.current.onClick();
    });

    expect(onPlay).not.toHaveBeenCalled();
  });

  it('onClick ignores clicks from a different engine', () => {
    const onPlay = vi.fn();
    const { result } = renderHook(() =>
      useCardZone({ zoneId: 'cats-trick', engineId: 'cats', onPlay }),
    );

    act(() => {
      useCardZoneStore
        .getState()
        .primeCard('mtg-card', 'mtg', ['mtg-battlefield-me'], '#a78bfa', 'play');
    });

    act(() => {
      result.current.onClick();
    });

    expect(onPlay).not.toHaveBeenCalled();
  });

  it('choice-driven path: onClick appends to pendingTargets and does NOT call onPlay', () => {
    // Arc A: when a server PendingChoice (or synthesized one) primes the
    // store, clicks on lit zones accumulate via togglePendingTarget. The
    // overlay pill submits the final selection — useCardZone.onPlay is
    // not invoked in the choice-driven path.
    const onPlay = vi.fn();
    const { result } = renderHook(() =>
      useCardZone({ zoneId: 'mtg-card-A', engineId: 'mtg', onPlay }),
    );

    act(() => {
      useCardZoneStore.getState().primeFromChoice({
        choiceId: 'mtg-multi-spell',
        sourceId: 'spell',
        prompt: 'Pick second target',
        engineId: 'mtg',
        accent: '#a78bfa',
        optionIds: ['mtg-card-A', 'mtg-card-B'],
        metadata: { label: '', predicate_description: '', min: 1, max: 1 },
      });
    });

    act(() => {
      result.current.onClick();
    });

    expect(onPlay).not.toHaveBeenCalled();
    expect(useCardZoneStore.getState().pendingTargets).toEqual(['mtg-card-A']);
    // Choice still active — pill drives the submit.
    expect(useCardZoneStore.getState().activeChoiceId).toBe('mtg-multi-spell');
  });

  it('choice-driven path: drag drop also toggles pendingTargets', () => {
    const onPlay = vi.fn();
    const { result } = renderHook(() =>
      useCardZone({ zoneId: 'mtg-card-A', engineId: 'mtg', onPlay }),
    );

    act(() => {
      useCardZoneStore.getState().primeFromChoice({
        choiceId: 'c', sourceId: null, prompt: '', engineId: 'mtg', accent: '#a78bfa',
        optionIds: ['mtg-card-A'],
        metadata: { label: '', predicate_description: '', min: 1, max: 1 },
      });
    });

    const mockData: Record<string, string> = { 'application/x-mtg-card': 'spell-id' };
    const fakeEvt = {
      preventDefault: vi.fn(),
      dataTransfer: { getData: (type: string) => mockData[type] ?? '' },
    } as unknown as React.DragEvent;

    act(() => {
      result.current.onDrop(fakeEvt);
    });

    expect(onPlay).not.toHaveBeenCalled();
    expect(useCardZoneStore.getState().pendingTargets).toEqual(['mtg-card-A']);
  });

  it('multi-target second pick: primeCard arms second-target zones', () => {
    // Mirrors MTG PR 3.3: after the user drops a multi-target spell on
    // the first target, GameBoard primes the spell with the second-
    // target options as valid zones. Click on a glowing permanent
    // converges to the same onCastMultiTargetSpell handler.
    let pickedCardId: string | undefined;
    const { result } = renderHook(() =>
      useCardZone({
        zoneId: 'mtg-card-CREATURE_B',
        engineId: 'mtg',
        onPlay: (cardId) => { pickedCardId = cardId; },
      }),
    );

    act(() => {
      useCardZoneStore
        .getState()
        .primeCard('SPELL', 'mtg', ['mtg-card-CREATURE_B', 'mtg-card-CREATURE_C'], '#a78bfa', 'play');
    });

    expect(result.current.isValid).toBe(true);

    act(() => {
      result.current.onClick();
    });

    // onPlay fires with the SPELL id (the hand card), not the target.
    // GameBoard.handleCardDrop reads the targetCard from its own scope.
    expect(pickedCardId).toBe('SPELL');
    expect(useCardZoneStore.getState().primedCardId).toBeNull();
  });

  it('routes retreat intent (PKM field-card flow)', () => {
    // Retreat is field-card-origin: the active Pokemon primes itself
    // with intent='retreat' and the bench zones are listed valid. A
    // bench Pokemon's onPlay reads activeIntent and dispatches a retreat
    // call. Pin the contract.
    let observedIntent: string | null | undefined = 'unread';
    const { result } = renderHook(() =>
      useCardZone({
        zoneId: 'pkm-pokemon-BENCH',
        engineId: 'pokemon',
        onPlay: () => {
          observedIntent = useCardZoneStore.getState().activeIntent;
        },
      }),
    );

    act(() => {
      useCardZoneStore
        .getState()
        .primeCard('ACTIVE', 'pokemon', ['pkm-pokemon-BENCH'], '#fca5a5', 'retreat');
    });

    act(() => {
      result.current.onClick();
    });

    expect(observedIntent).toBe('retreat');
    expect(useCardZoneStore.getState().activeIntent).toBeNull();
  });

  it('onClick ignores clicks on zones not in the validZoneIds set', () => {
    const onPlay = vi.fn();
    const { result } = renderHook(() =>
      useCardZone({ zoneId: 'cats-not-listed', engineId: 'cats', onPlay }),
    );

    act(() => {
      useCardZoneStore
        .getState()
        .primeCard('c1', 'cats', ['cats-trick'], '#fbbf24');
    });

    act(() => {
      result.current.onClick();
    });

    expect(onPlay).not.toHaveBeenCalled();
  });
});
