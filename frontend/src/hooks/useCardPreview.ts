/**
 * useCardPreview
 *
 * Unified card-preview state + bindings for hover and pin across all 4 game modes.
 *
 * Architecture:
 * - A single zustand store holds the currently hovered card and the currently
 *   pinned card. The "active" card for display = pinned ?? hovered.
 * - Each mode's game board renders its own *CardDetailPanel fed by the store.
 * - Tiles (hand cards, battlefield minions, bench Pokemon, YGO cards) attach
 *   bindings via `useCardPreviewBindings(card)` which returns onMouseEnter /
 *   onMouseLeave / onContextMenu / onPointerDown handlers.
 *
 * Interaction model:
 * - Desktop hover: after a short delay the card becomes hovered. Leaving clears
 *   hover. If another card is already pinned, hover still works and the hovered
 *   card is shown (overriding the pin).
 * - Desktop right-click (contextmenu): pins / unpins the card. Right-clicking
 *   another card swaps the pin.
 * - Mobile long-press (~500ms pointer down without movement): pins the card.
 *   Pinned cards stay until the player taps the dismiss area (see store.unpin).
 *
 * We intentionally do NOT hijack onClick because every mode uses click for its
 * own primary action (cast/play/attack/etc). Right-click + long-press are the
 * pin affordances.
 */

import { useEffect, useMemo, useRef } from 'react';
import { create } from 'zustand';
import type { CardData } from '../types';

interface CardPreviewState {
  /** Currently hovered card (desktop). null if nothing is hovered. */
  hoveredCard: CardData | null;
  /** Pinned card - stays until explicitly unpinned. null if nothing pinned. */
  pinnedCard: CardData | null;

  setHover: (card: CardData | null) => void;
  togglePin: (card: CardData) => void;
  pin: (card: CardData) => void;
  unpin: () => void;
  clearAll: () => void;
}

export const useCardPreviewStore = create<CardPreviewState>((set) => ({
  hoveredCard: null,
  pinnedCard: null,

  setHover: (card) => set({ hoveredCard: card }),

  togglePin: (card) =>
    set((s) => ({
      pinnedCard: s.pinnedCard?.id === card.id ? null : card,
    })),

  pin: (card) => set({ pinnedCard: card }),
  unpin: () => set({ pinnedCard: null }),
  clearAll: () => set({ hoveredCard: null, pinnedCard: null }),
}));

/**
 * Selector hook returning the card currently shown in the detail panel:
 *   hoveredCard ?? pinnedCard
 * (hover takes precedence so that players can peek at other cards without
 * losing their pin.)
 */
export function useActivePreviewCard(): CardData | null {
  return useCardPreviewStore((s) => s.hoveredCard ?? s.pinnedCard);
}

export interface CardPreviewBindingsOptions {
  /** Delay before hover registers, ms. Defaults to 120ms (feels responsive). */
  hoverDelayMs?: number;
  /** Long-press duration for mobile pin, ms. Defaults to 500ms. */
  longPressMs?: number;
  /** If true, disables all preview bindings (e.g. while dragging). */
  disabled?: boolean;
}

export interface CardPreviewBindings {
  onMouseEnter: () => void;
  onMouseLeave: () => void;
  onContextMenu: (e: React.MouseEvent) => void;
  onPointerDown: (e: React.PointerEvent) => void;
  onPointerUp: () => void;
  onPointerCancel: () => void;
  onPointerMove: (e: React.PointerEvent) => void;
}

/**
 * Returns a stable set of handlers to spread onto a card tile. Opt-in per tile.
 *
 * Usage:
 *   const previewProps = useCardPreviewBindings(card);
 *   <div {...previewProps}>...</div>
 */
export function useCardPreviewBindings(
  card: CardData,
  options: CardPreviewBindingsOptions = {},
): CardPreviewBindings {
  const { hoverDelayMs = 120, longPressMs = 500, disabled = false } = options;
  const setHover = useCardPreviewStore((s) => s.setHover);
  const togglePin = useCardPreviewStore((s) => s.togglePin);
  const pin = useCardPreviewStore((s) => s.pin);

  const hoverTimer = useRef<number | null>(null);
  const pressTimer = useRef<number | null>(null);
  const pressOrigin = useRef<{ x: number; y: number } | null>(null);
  const disabledRef = useRef(disabled);
  disabledRef.current = disabled;

  // Keep a ref to card so handlers stay stable but always fire on latest card
  const cardRef = useRef(card);
  cardRef.current = card;

  // Cleanup timers on unmount
  useEffect(() => {
    return () => {
      if (hoverTimer.current != null) window.clearTimeout(hoverTimer.current);
      if (pressTimer.current != null) window.clearTimeout(pressTimer.current);
    };
  }, []);

  return useMemo<CardPreviewBindings>(() => ({
    onMouseEnter: () => {
      if (disabledRef.current) return;
      if (hoverTimer.current != null) window.clearTimeout(hoverTimer.current);
      hoverTimer.current = window.setTimeout(() => {
        setHover(cardRef.current);
      }, hoverDelayMs);
    },
    onMouseLeave: () => {
      if (hoverTimer.current != null) {
        window.clearTimeout(hoverTimer.current);
        hoverTimer.current = null;
      }
      setHover(null);
    },
    onContextMenu: (e) => {
      if (disabledRef.current) return;
      e.preventDefault();
      togglePin(cardRef.current);
    },
    onPointerDown: (e) => {
      if (disabledRef.current) return;
      // Only trigger long-press for touch / pen (not mouse — mouse has right-click).
      if (e.pointerType === 'mouse') return;
      pressOrigin.current = { x: e.clientX, y: e.clientY };
      if (pressTimer.current != null) window.clearTimeout(pressTimer.current);
      pressTimer.current = window.setTimeout(() => {
        pin(cardRef.current);
        pressTimer.current = null;
      }, longPressMs);
    },
    onPointerUp: () => {
      if (pressTimer.current != null) {
        window.clearTimeout(pressTimer.current);
        pressTimer.current = null;
      }
      pressOrigin.current = null;
    },
    onPointerCancel: () => {
      if (pressTimer.current != null) {
        window.clearTimeout(pressTimer.current);
        pressTimer.current = null;
      }
      pressOrigin.current = null;
    },
    onPointerMove: (e) => {
      // Cancel long-press if the finger moves (user is scrolling / dragging).
      if (pressTimer.current == null || pressOrigin.current == null) return;
      const dx = e.clientX - pressOrigin.current.x;
      const dy = e.clientY - pressOrigin.current.y;
      if (dx * dx + dy * dy > 64) {
        // moved > 8px
        window.clearTimeout(pressTimer.current);
        pressTimer.current = null;
        pressOrigin.current = null;
      }
    },
  }), [setHover, togglePin, pin, hoverDelayMs, longPressMs]);
}
