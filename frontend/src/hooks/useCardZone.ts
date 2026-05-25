/**
 * useCardZone — the drop-zone side of the shared card-zone primitive.
 *
 * One hook per zone. Returns event handlers + visual flags. Drives both
 * paths:
 *
 *  - Click-prime: when a card is primed and this zone is in its valid
 *    set, click on the zone fires onPlay(cardId) and clears prime state.
 *  - Drag: drop fires onPlay(cardId) and clears drag state. Drag-over /
 *    drag-leave maintains the hovered-zone state so the zone can
 *    brighten when the cursor is over it.
 *
 * The engine decides what onPlay(cardId) means — it looks up the card,
 * dispatches the right action (CATS_PLAY_CARD, CLANKERS_PLAY_CHASSIS,
 * etc.), and clears any local UI state.
 */

import { useCallback } from 'react';
import { useCardZoneStore, type CardIntent } from '../stores/cardZoneStore';

export interface UseCardZoneOptions {
  /** Stable id for this zone (e.g. 'cats-trick-zone', 'clankers-assembly-floor'). */
  zoneId: string;
  /** Engine id — drop handler ignores drags from other engines. */
  engineId: string;
  /** Called with the card id when the user drops or clicks-while-primed. */
  onPlay: (cardId: string) => void;
}

export interface UseCardZoneResult {
  /** True if the active card lists this zone as a legal target. */
  isValid: boolean;
  /** True if the cursor is currently dragging over this zone. */
  isHovered: boolean;
  /** True if there's any active card (primed or dragging). */
  hasActiveCard: boolean;
  /** Engine accent color of the active card (for visual tinting). */
  activeAccent: string | null;
  /**
   * What the active card is asking this zone to do. Drop handlers
   * inspect this to route between engine actions (energy attach vs
   * basic play vs trainer activation, etc.). Null when no card is
   * active or the engine doesn't surface intents.
   */
  activeIntent: CardIntent | null;
  /** Drop handlers — spread onto the zone container. */
  onClick: () => void;
  onDragOver: (e: React.DragEvent) => void;
  onDragLeave: () => void;
  onDrop: (e: React.DragEvent) => void;
}

export function useCardZone(opts: UseCardZoneOptions): UseCardZoneResult {
  const { zoneId, engineId, onPlay } = opts;
  const primedCardId = useCardZoneStore((s) => s.primedCardId);
  const dragCardId = useCardZoneStore((s) => s.dragCardId);
  const validZoneIds = useCardZoneStore((s) => s.validZoneIds);
  const hoveredZoneId = useCardZoneStore((s) => s.hoveredZoneId);
  const accentColor = useCardZoneStore((s) => s.accentColor);
  const activeEngine = useCardZoneStore((s) => s.engineId);
  const activeIntent = useCardZoneStore((s) => s.activeIntent);
  const activeChoiceId = useCardZoneStore((s) => s.activeChoiceId);
  const setHoveredZone = useCardZoneStore((s) => s.setHoveredZone);
  const clearAll = useCardZoneStore((s) => s.clearAll);
  const togglePendingTarget = useCardZoneStore((s) => s.togglePendingTarget);

  // The "active card" is either: a click-primed card, a drag-in-progress
  // card, or a choice-driven target hunt. All three light up the same
  // valid zones and show the same accent.
  const activeCardId = dragCardId ?? primedCardId;
  const hasActiveCard = activeCardId !== null || activeChoiceId !== null;
  const isValid =
    hasActiveCard && activeEngine === engineId && validZoneIds.has(zoneId);
  const isHovered = hoveredZoneId === zoneId;

  const onClick = useCallback(() => {
    if (activeEngine !== engineId) return;
    if (!validZoneIds.has(zoneId)) return;

    // Choice-driven path: zone is a target option for a PendingChoice.
    // Append to pendingTargets; do NOT call onPlay (the choice modal /
    // overlay pill submits the accumulated selection to the server).
    if (activeChoiceId) {
      togglePendingTarget(zoneId);
      return;
    }

    // Card-driven path: hand card primed, click commits the play.
    if (!primedCardId) return;
    const cardId = primedCardId;
    // Fire onPlay BEFORE clearAll: engines like Pokemon read
    // `useCardZoneStore.getState().activeIntent` inside onPlay to route
    // attach/evolve/play. clearAll() nulls activeIntent, so reading
    // after-clear gives the wrong answer.
    onPlay(cardId);
    clearAll();
  }, [primedCardId, activeEngine, engineId, validZoneIds, zoneId, clearAll, onPlay, activeChoiceId, togglePendingTarget]);

  const onDragOver = useCallback(
    (e: React.DragEvent) => {
      if (!e.dataTransfer.types.includes(`application/x-${engineId}-card`)) return;
      if (!validZoneIds.has(zoneId)) return;
      e.preventDefault();
      e.dataTransfer.dropEffect = 'move';
      if (hoveredZoneId !== zoneId) setHoveredZone(zoneId);
    },
    [engineId, validZoneIds, zoneId, hoveredZoneId, setHoveredZone],
  );

  const onDragLeave = useCallback(() => {
    if (hoveredZoneId === zoneId) setHoveredZone(null);
  }, [hoveredZoneId, zoneId, setHoveredZone]);

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      const cardId = e.dataTransfer.getData(`application/x-${engineId}-card`);
      if (!cardId) return;
      if (!validZoneIds.has(zoneId)) return;
      e.preventDefault();

      // Choice-driven: a drag landed on a target option. Same as click.
      if (activeChoiceId) {
        togglePendingTarget(zoneId);
        return;
      }

      // Card-driven: same ordering as onClick — onPlay reads activeIntent
      // (and other store state); clearAll only after dispatch.
      onPlay(cardId);
      clearAll();
    },
    [engineId, validZoneIds, zoneId, clearAll, onPlay, activeChoiceId, togglePendingTarget],
  );

  return {
    isValid,
    isHovered,
    hasActiveCard,
    activeAccent: accentColor,
    activeIntent,
    onClick,
    onDragOver,
    onDragLeave,
    onDrop,
  };
}
