/**
 * useHandCard — the hand-card side of the shared card-zone primitive.
 *
 * One hook per hand card. Returns event handlers + visual flags the
 * engine's hand-card button binds to. Drives both interaction paths:
 *
 *  - Drag: onDragStart writes the card+engine+valid-zones to the store,
 *    so `useCardZone` consumers can highlight their zones.
 *  - Click-prime: onClick toggles the primed card. If a card is already
 *    primed, clicking the same card unprimes. Clicking a different
 *    playable card re-primes.
 *
 * The engine separately calls `inspector.open(...)` when it wants the
 * full-card modal — this hook does NOT open the inspector. The two
 * concerns are independent so a card can be primed without a modal
 * (e.g. after the user dismisses the modal but the card stays primed).
 */

import { useCallback } from 'react';
import { useCardZoneStore } from '../stores/cardZoneStore';

export interface UseHandCardOptions {
  cardId: string;
  cardName: string;
  /** Engine id (e.g. 'cats', 'clankers'). Used to namespace drag MIME. */
  engineId: string;
  /** Hex accent color used to tint valid zones while this card is active. */
  accent: string;
  /** Zone IDs this card can legally be played on. Empty = unplayable. */
  validZones: string[];
  /** True if the card cannot be played right now (wrong phase, no resources). */
  disabled?: boolean;
}

export interface UseHandCardResult {
  draggable: boolean;
  isPrimed: boolean;
  isDragging: boolean;
  onClick: () => void;
  onDragStart: (e: React.DragEvent) => void;
  onDragEnd: () => void;
}

export function useHandCard(opts: UseHandCardOptions): UseHandCardResult {
  const { cardId, cardName, engineId, accent, validZones, disabled = false } = opts;
  const primedCardId = useCardZoneStore((s) => s.primedCardId);
  const dragCardId = useCardZoneStore((s) => s.dragCardId);
  const primeCard = useCardZoneStore((s) => s.primeCard);
  const unprime = useCardZoneStore((s) => s.unprime);
  const startDrag = useCardZoneStore((s) => s.startDrag);
  const endDrag = useCardZoneStore((s) => s.endDrag);

  const isPrimed = primedCardId === cardId;
  const isDragging = dragCardId === cardId;
  const canPlay = !disabled && validZones.length > 0;

  const onClick = useCallback(() => {
    if (!canPlay) return;
    if (isPrimed) unprime();
    else primeCard(cardId, engineId, validZones, accent);
  }, [canPlay, isPrimed, unprime, primeCard, cardId, engineId, validZones, accent]);

  const onDragStart = useCallback(
    (e: React.DragEvent) => {
      if (!canPlay) {
        e.preventDefault();
        return;
      }
      e.dataTransfer.effectAllowed = 'move';
      // Engine-namespaced MIME so drop handlers can ignore cross-engine drags.
      e.dataTransfer.setData(`application/x-${engineId}-card`, cardId);
      e.dataTransfer.setData('text/plain', cardName);
      startDrag(cardId, engineId, validZones, accent);
    },
    [canPlay, engineId, cardId, cardName, validZones, accent, startDrag],
  );

  const onDragEnd = useCallback(() => {
    endDrag();
  }, [endDrag]);

  return {
    draggable: canPlay,
    isPrimed,
    isDragging,
    onClick,
    onDragStart,
    onDragEnd,
  };
}
