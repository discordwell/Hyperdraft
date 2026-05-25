/**
 * dropChoiceStore — shared post-drop "what do you want to do with this
 * card here?" popup state.
 *
 * Some engines fire a popup AFTER drop and BEFORE action dispatch. The
 * canonical example is Yu-Gi-Oh!: dropping a monster on a monster zone
 * needs a "Normal Summon" vs "Set" choice. Dropping a spell on a
 * spell/trap zone needs an "Activate" vs "Set" choice.
 *
 * Engines call `dropChoice.open(card, options, position)` from their
 * `useCardZone` `onPlay` callback when the drop is ambiguous. The
 * `<DropChoicePopup />` component (mounted once near the App root)
 * reads this store and renders the popup. Selecting an option fires
 * the option's `onClick` and closes the popup.
 *
 * Pure UI state — does not couple to any engine's card types or actions.
 */

import { create } from 'zustand';
import type { ReactNode } from 'react';

export interface DropChoiceOption {
  /** Label shown on the button (e.g. "Normal Summon", "Set face-down"). */
  label: string;
  /** Visual emphasis — primary is filled, secondary is outlined, danger is red. */
  variant?: 'primary' | 'secondary' | 'danger';
  /** Optional disabled state with a tooltip-style reason. */
  disabled?: boolean;
  disabledReason?: string;
  /** Optional icon to render to the left of the label. */
  icon?: ReactNode;
  /** Fired when the user picks this option. Popup closes after firing. */
  onClick: () => void;
}

export interface DropChoiceCardSummary {
  /** Card id — used for the popup's title chip / keyed for transitions. */
  id: string;
  /** Card name — shown as the popup title. */
  name: string;
  /** Optional subtitle (type line, rarity, etc.). */
  subtitle?: string;
}

export interface DropChoiceState {
  card: DropChoiceCardSummary | null;
  options: DropChoiceOption[];
  /** Anchor position (viewport coords). Null = center the popup. */
  position: { x: number; y: number } | null;
  open: (
    card: DropChoiceCardSummary,
    options: DropChoiceOption[],
    position?: { x: number; y: number } | null,
  ) => void;
  close: () => void;
}

export const useDropChoiceStore = create<DropChoiceState>((set) => ({
  card: null,
  options: [],
  position: null,
  open: (card, options, position = null) =>
    set({ card, options, position }),
  close: () => set({ card: null, options: [], position: null }),
}));
