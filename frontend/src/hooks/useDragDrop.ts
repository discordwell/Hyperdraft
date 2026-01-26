/**
 * useDragDrop Hook
 *
 * Manages drag and drop state for card interactions.
 * Uses native HTML5 drag and drop API.
 */

import { create } from 'zustand';
import type { CardData, LegalActionData } from '../types';

export type DragItemType = 'hand-card';

export interface DragItem {
  type: DragItemType;
  card: CardData;
  action?: LegalActionData;
}

export interface DropZone {
  id: string;
  type: 'battlefield' | 'creature' | 'player' | 'permanent';
  accepts: (item: DragItem) => boolean;
}

interface DragDropState {
  // Current drag state
  isDragging: boolean;
  dragItem: DragItem | null;

  // Drop zone highlighting
  validDropZones: string[];
  hoveredDropZone: string | null;

  // Multi-target state
  multiTargetMode: boolean;
  multiTargetSpell: LegalActionData | null;
  multiTargetCardId: string | null;
  firstTarget: string | null;
  secondTargetOptions: string[];

  // Actions
  startDrag: (item: DragItem, validZones: string[]) => void;
  endDrag: () => void;
  setHoveredZone: (zoneId: string | null) => void;

  // Multi-target actions
  startMultiTargetMode: (spell: LegalActionData, cardId: string, firstTarget: string, secondOptions: string[]) => void;
  selectSecondTarget: (targetId: string) => void;
  cancelMultiTarget: () => void;
}

export const useDragDropStore = create<DragDropState>((set) => ({
  isDragging: false,
  dragItem: null,
  validDropZones: [],
  hoveredDropZone: null,
  multiTargetMode: false,
  multiTargetSpell: null,
  multiTargetCardId: null,
  firstTarget: null,
  secondTargetOptions: [],

  startDrag: (item, validZones) => set({
    isDragging: true,
    dragItem: item,
    validDropZones: validZones,
    hoveredDropZone: null,
  }),

  endDrag: () => set({
    isDragging: false,
    dragItem: null,
    validDropZones: [],
    hoveredDropZone: null,
  }),

  setHoveredZone: (zoneId) => set({ hoveredDropZone: zoneId }),

  startMultiTargetMode: (spell, cardId, firstTarget, secondOptions) => set({
    multiTargetMode: true,
    multiTargetSpell: spell,
    multiTargetCardId: cardId,
    firstTarget,
    secondTargetOptions: secondOptions,
    // Also end the drag
    isDragging: false,
    dragItem: null,
    validDropZones: [],
    hoveredDropZone: null,
  }),

  selectSecondTarget: (_targetId) => set({
    multiTargetMode: false,
    multiTargetSpell: null,
    multiTargetCardId: null,
    firstTarget: null,
    secondTargetOptions: [],
  }),

  cancelMultiTarget: () => set({
    multiTargetMode: false,
    multiTargetSpell: null,
    multiTargetCardId: null,
    firstTarget: null,
    secondTargetOptions: [],
  }),
}));

/**
 * Hook for using drag and drop in components
 */
export function useDragDrop() {
  const store = useDragDropStore();
  return store;
}
