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
  | 'retreat'
  // Choice-driven flow: a server PendingChoice with choice_type='target'
  // has primed the store. Lit zones come from `choice.options`; clicks
  // accumulate into `pendingTargets` until min/max satisfied; Confirm
  // submits via matchAPI.submitChoice. Distinct from card-driven primes
  // so engines can route accordingly.
  | 'target';

/**
 * Target group metadata mirrored from the server's PendingChoice. Populated
 * when Arc B lands and the engine surfaces structured target metadata. Until
 * then, `primeFromChoice` synthesizes a minimal shape from `min_choices` /
 * `max_choices` / `prompt` so the UI keeps working.
 */
export interface CardZoneTargetMetadata {
  label: string;
  predicate_description: string;
  min: number;
  max: number;
  unique?: boolean;
  group_index?: number;
  total_groups?: number;
}

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

  // ---------------------------------------------------------------------
  // Choice-driven flow (Arc A) — a server PendingChoice has primed the
  // store. Independent of card-driven primes; they can coexist (a hand
  // card primed for inspection while a separate choice asks for a target,
  // though in practice the choice flow auto-clears card primes).
  // ---------------------------------------------------------------------

  /** ID of the active PendingChoice driving the prime; null if not choice-driven. */
  activeChoiceId: string | null;
  /** Source card/ability ID from the choice — for label rendering. */
  activeChoiceSourceId: string | null;
  /** Prompt text from the choice — fallback label when no metadata. */
  activeChoicePrompt: string | null;
  /** Structured metadata (Arc B-populated; minimal shape until then). */
  targetMetadata: CardZoneTargetMetadata | null;
  /** Accumulated selections for the active choice (multi-target). */
  pendingTargets: string[];

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

  /**
   * Prime the store from a server PendingChoice. Used by the GameView
   * effect that watches `gameState.pending_choice` with
   * `interaction_mode='overlay'`. After this call, valid zones glow in
   * the engine accent and each click on a lit zone appends to
   * `pendingTargets`.
   */
  primeFromChoice: (params: {
    choiceId: string;
    sourceId: string | null;
    prompt: string;
    engineId: string;
    accent: string;
    optionIds: string[];
    metadata?: CardZoneTargetMetadata | null;
  }) => void;
  /**
   * Toggle a single target id in `pendingTargets`. Adds if absent,
   * removes if present (unless `unique:false` would allow duplicates —
   * not supported in v1; engines that need it can extend later).
   */
  togglePendingTarget: (targetId: string) => void;
  /**
   * Clear only the choice-driven state. Used when the server emits a
   * new choice (id transition) or when the choice resolves.
   */
  clearChoice: () => void;
}

export const useCardZoneStore = create<CardZoneState>((set, get) => ({
  primedCardId: null,
  dragCardId: null,
  engineId: null,
  activeIntent: null,
  validZoneIds: new Set(),
  accentColor: null,
  hoveredZoneId: null,
  activeChoiceId: null,
  activeChoiceSourceId: null,
  activeChoicePrompt: null,
  targetMetadata: null,
  pendingTargets: [],

  primeCard: (cardId, engineId, validZones, accent, intent = null) =>
    set({
      primedCardId: cardId,
      dragCardId: null,
      engineId,
      activeIntent: intent,
      validZoneIds: new Set(validZones),
      accentColor: accent,
      hoveredZoneId: null,
      // Card-driven primes don't touch the choice-driven state, but they
      // also can't coexist visually with a choice. The GameView effect
      // is responsible for clearing the choice when a new card is primed,
      // and the choice flow is responsible for clearing any card prime.
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
      activeChoiceId: null,
      activeChoiceSourceId: null,
      activeChoicePrompt: null,
      targetMetadata: null,
      pendingTargets: [],
    }),

  primeFromChoice: ({ choiceId, sourceId, prompt, engineId, accent, optionIds, metadata = null }) =>
    set({
      // Choice-driven prime takes over: clear any card-driven state.
      primedCardId: null,
      dragCardId: null,
      activeIntent: 'target',
      engineId,
      validZoneIds: new Set(optionIds),
      accentColor: accent,
      hoveredZoneId: null,
      activeChoiceId: choiceId,
      activeChoiceSourceId: sourceId,
      activeChoicePrompt: prompt,
      targetMetadata: metadata,
      pendingTargets: [],
    }),

  togglePendingTarget: (targetId) => {
    const state = get();
    if (!state.activeChoiceId) return;
    const current = state.pendingTargets;
    const idx = current.indexOf(targetId);
    const max = state.targetMetadata?.max ?? Infinity;
    let next: string[];
    if (idx >= 0) {
      next = [...current.slice(0, idx), ...current.slice(idx + 1)];
    } else {
      if (current.length >= max) {
        // At max — replace the oldest pick (FIFO) so the user can swap
        // a selection without explicitly deselecting first. Cleanest UX
        // for the common case where min=max=1.
        next = max === 1 ? [targetId] : [...current.slice(1), targetId];
      } else {
        next = [...current, targetId];
      }
    }
    set({ pendingTargets: next });
  },

  clearChoice: () =>
    set({
      activeChoiceId: null,
      activeChoiceSourceId: null,
      activeChoicePrompt: null,
      targetMetadata: null,
      pendingTargets: [],
      // Also clear the lit zones — the choice owned them.
      validZoneIds: new Set(),
      accentColor: null,
      hoveredZoneId: null,
      activeIntent: null,
      engineId: null,
    }),
}));

/** Convenience selectors — used by the hooks below. */
export const selectActiveCardId = (s: CardZoneState): string | null =>
  s.dragCardId ?? s.primedCardId;
export const selectIsZoneValid = (zoneId: string) =>
  (s: CardZoneState): boolean => s.validZoneIds.has(zoneId);
export const selectIsZoneHovered = (zoneId: string) =>
  (s: CardZoneState): boolean => s.hoveredZoneId === zoneId;
