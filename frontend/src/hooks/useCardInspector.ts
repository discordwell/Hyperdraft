/**
 * useCardInspector
 *
 * Shared "click to inspect, second click to play" model used by every
 * Hyperdraft engine. The current visible card and its action list live
 * in a single zustand store; each engine's hand-card click handler calls
 * `inspector.open(card, actions)`, and the `<CardInspector />` modal
 * (rendered once near the app root) reads the same store.
 *
 * The previous hover-only `useCardPreview` model stays for desktop —
 * hover/right-click affordances on MTG, HS, Pokemon, and YGO continue
 * to work. The inspector is additive: click anywhere on a card to open
 * the modal, then confirm Play (or any other action the engine offers).
 */

import { create } from 'zustand';
import type { ReactNode } from 'react';

export type InspectableCardType =
  | 'creature'
  | 'spell'
  | 'land'
  | 'minion'
  | 'pokemon'
  | 'energy'
  | 'trainer'
  | 'monster'
  | 'spell_trap'
  | 'cats'
  | 'clankers'
  | 'depths'
  | 'finance'
  | 'minecraft'
  | 'scp'
  | 'other';

export interface InspectableCard {
  id: string;
  name: string;
  /** Body text — full rules text, no truncation. */
  text?: string;
  /** Cost label rendered next to the name (e.g. "{2}{W}", "4", "5⚡"). */
  cost?: string;
  /** Stat line (e.g. "3/5", "P 4 · HP 60"). */
  stats?: string;
  /** Optional sub-line under the name (type / archetype / flavor). */
  subtitle?: string;
  /** Absolute or relative URL to card art. Falls back to a placeholder. */
  artUrl?: string | null;
  /** Engine identifier — drives accent color / icon. */
  engine?: InspectableCardType;
  /** Optional flavor / footer text rendered below the rules text. */
  flavor?: string;
  /** Extra metadata rows — rendered as label/value pairs in the modal. */
  meta?: Array<{ label: string; value: string }>;
}

export interface InspectorAction {
  /** Visible label (e.g. "Play", "Attach", "Activate"). */
  label: string;
  /** Primary action gets a filled button; secondary actions are outlined. */
  variant?: 'primary' | 'secondary' | 'danger';
  /** Disabled actions still render but cannot be clicked (e.g. not enough mana). */
  disabled?: boolean;
  /** Optional reason text shown under the button when disabled. */
  disabledReason?: string;
  /**
   * Click handler. Returning `true` (or void) closes the modal after firing;
   * return `false` to keep it open (e.g. to await a target selection that
   * will close it from the engine side).
   */
  onClick: () => void | boolean;
  /** Optional icon node rendered to the left of the label. */
  icon?: ReactNode;
}

export interface InspectorState {
  card: InspectableCard | null;
  actions: InspectorAction[];
  /** Open the modal for `card` with the given action buttons. */
  open: (card: InspectableCard, actions?: InspectorAction[]) => void;
  /** Close the modal. */
  close: () => void;
}

export const useCardInspectorStore = create<InspectorState>((set) => ({
  card: null,
  actions: [],
  open: (card, actions = []) => set({ card, actions }),
  close: () => set({ card: null, actions: [] }),
}));

/**
 * Sugar accessor — call inside any engine's hand component to drive the
 * shared modal. Stable references (zustand guarantees) so it's safe to
 * pass into onClick without useCallback.
 */
export function useCardInspector(): {
  open: InspectorState['open'];
  close: InspectorState['close'];
  isOpen: boolean;
} {
  const open = useCardInspectorStore((s) => s.open);
  const close = useCardInspectorStore((s) => s.close);
  const card = useCardInspectorStore((s) => s.card);
  return { open, close, isOpen: card !== null };
}
