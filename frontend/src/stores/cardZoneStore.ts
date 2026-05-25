/**
 * cardZoneStore — shared engine-agnostic card-interaction state.
 *
 * Drives THREE interactions off a single store:
 *  1. Drag — hand card → drop zone (HTML5 DnD).
 *  2. Click-prime — click hand card → valid zones light up → click zone.
 *  3. Click-inspect — works alongside the CardInspector modal so users
 *     can also see art / text while choosing a target.
 *
 * Why a shared store: every engine has the same shape (hand of cards,
 * play zones, "valid plays for this card"). The dnd-kit-based store
 * (`stores/dragDropStore.ts`) couples to MTG's `CardData` and
 * `LegalActionData` types and is hard to retrofit for the non-MTG
 * engines. This store stays card-shape-agnostic — it only knows IDs.
 *
 * Naming: a "primed" card is one the user has clicked (selected to play)
 * but not yet committed to a zone. "Dragging" is the corresponding state
 * during an HTML5 drag. They share the same visual language: valid zones
 * light up in the engine's accent color in both cases.
 */

import { create } from 'zustand';

/**
 * Intent the active card is asking the destination zone to do. Engines
 * with multi-action cards (Pokemon energy attach vs basic play, YGO
 * normal summon vs set) inspect `activeIntent` in their `useCardZone`
 * `onPlay` callback to route to the right action.
 *
 * The verb taxonomy mirrors the legacy `dragDropStore` DragIntent so
 * engines migrating off dnd-kit keep their existing routing logic.
 *
 * `retreat` is field-card-origin (not from hand): the active Pokemon
 * primes itself, valid zones = the bench. Same primitive, different
 * source. Lets the retreat flow share the click-prime / lit-zone /
 * click-target vocabulary instead of running on its own state machine.
 */
export type CardIntent =
  | 'play'
  | 'attack'
  | 'attach'
  | 'evolve'
  | 'summon'
  | 'set'
  | 'activate'
  | 'retreat';

export interface CardZoneState {
  /** Card the user has clicked to commit (click-prime path). */
  primedCardId: string | null;
  /** Card currently being HTML5-dragged. */
  dragCardId: string | null;
  /** Which engine the active card belongs to — drives accent + namespacing. */
  engineId: string | null;
  /** What the active card wants the destination to do. Optional — single-action engines can ignore. */
  activeIntent: CardIntent | null;
  /** Zone IDs that accept the currently primed / dragged card. */
  validZoneIds: Set<string>;
  /** Hex accent color used to tint valid zones. */
  accentColor: string | null;
  /** Zone the user is currently dragging over (drag path). */
  hoveredZoneId: string | null;

  /** Begin a click-prime flow. Caller supplies the zones legal for this card. */
  primeCard: (
    cardId: string,
    engineId: string,
    validZones: string[],
    accent: string,
    intent?: CardIntent | null,
  ) => void;
  /** Cancel an in-progress click-prime (Esc, click off-board, invalid drop). */
  unprime: () => void;
  /** Mark the start of an HTML5 drag — same visual feedback as primeCard. */
  startDrag: (
    cardId: string,
    engineId: string,
    validZones: string[],
    accent: string,
    intent?: CardIntent | null,
  ) => void;
  /** Mark drag end (drop or cancel). Always clears drag state. */
  endDrag: () => void;
  /** Drag-over a zone — drives the "active hover" brightening. */
  setHoveredZone: (zoneId: string | null) => void;
  /** Clear both prime + drag (e.g. after a successful play). */
  clearAll: () => void;
}

export const useCardZoneStore = create<CardZoneState>((set) => ({
  primedCardId: null,
  dragCardId: null,
  engineId: null,
  activeIntent: null,
  validZoneIds: new Set(),
  accentColor: null,
  hoveredZoneId: null,

  primeCard: (cardId, engineId, validZones, accent, intent = null) =>
    set({
      primedCardId: cardId,
      dragCardId: null,
      engineId,
      activeIntent: intent,
      validZoneIds: new Set(validZones),
      accentColor: accent,
      hoveredZoneId: null,
    }),

  unprime: () =>
    set({
      primedCardId: null,
      dragCardId: null,
      engineId: null,
      activeIntent: null,
      validZoneIds: new Set(),
      accentColor: null,
      hoveredZoneId: null,
    }),

  startDrag: (cardId, engineId, validZones, accent, intent = null) =>
    set({
      dragCardId: cardId,
      primedCardId: null,
      engineId,
      activeIntent: intent,
      validZoneIds: new Set(validZones),
      accentColor: accent,
      hoveredZoneId: null,
    }),

  endDrag: () =>
    set({
      dragCardId: null,
      hoveredZoneId: null,
      // If a card was primed independently of the drag, leave it alone.
      // Otherwise the drop handler is responsible for calling clearAll.
    }),

  setHoveredZone: (zoneId) => set({ hoveredZoneId: zoneId }),

  clearAll: () =>
    set({
      primedCardId: null,
      dragCardId: null,
      engineId: null,
      activeIntent: null,
      validZoneIds: new Set(),
      accentColor: null,
      hoveredZoneId: null,
    }),
}));

/** Convenience selectors — used by the hooks below. */
export const selectActiveCardId = (s: CardZoneState): string | null =>
  s.dragCardId ?? s.primedCardId;
export const selectIsZoneValid = (zoneId: string) =>
  (s: CardZoneState): boolean => s.validZoneIds.has(zoneId);
export const selectIsZoneHovered = (zoneId: string) =>
  (s: CardZoneState): boolean => s.hoveredZoneId === zoneId;
