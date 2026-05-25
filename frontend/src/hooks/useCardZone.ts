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
  const setHoveredZone = useCardZoneStore((s) => s.setHoveredZone);
  const clearAll = useCardZoneStore((s) => s.clearAll);

  const activeCardId = dragCardId ?? primedCardId;
  const hasActiveCard = activeCardId !== null;
  const isValid =
    hasActiveCard && activeEngine === engineId && validZoneIds.has(zoneId);
  const isHovered = hoveredZoneId === zoneId;

  const onClick = useCallback(() => {
    // Only the click-prime path triggers here — drag path uses onDrop.
    if (!primedCardId) return;
    if (activeEngine !== engineId) return;
    if (!validZoneIds.has(zoneId)) return;
    const cardId = primedCardId;
    clearAll();
    onPlay(cardId);
  }, [primedCardId, activeEngine, engineId, validZoneIds, zoneId, clearAll, onPlay]);

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
      clearAll();
      onPlay(cardId);
    },
    [engineId, validZoneIds, zoneId, clearAll, onPlay],
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
