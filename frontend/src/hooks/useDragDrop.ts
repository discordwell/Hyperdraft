/**
 * useDragDrop Hook
 *
 * Re-exports the drag-drop store and types from stores/dragDropStore.ts.
 * The canonical store definition lives there; this file is kept for
 * backward-compat imports throughout the codebase.
 */

export type {
  DragItemType,
  DragIntent,
  GameMode,
  DragItem,
  DropZone,
} from '../stores/dragDropStore';

export { useDragDropStore } from '../stores/dragDropStore';

import { useDragDropStore as _store } from '../stores/dragDropStore';

/**
 * Hook for using drag and drop in components.
 */
export function useDragDrop() {
  return _store();
}
