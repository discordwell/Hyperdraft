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
