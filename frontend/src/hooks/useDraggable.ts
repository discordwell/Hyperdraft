/**
 * useDraggable Hook
 *
 * Shared drag source hook that encapsulates HTML5 DnD boilerplate.
 * Works across all game modes (MTG, HS, PKM, YGO).
 */

import { useCallback, useEffect, useMemo } from 'react';
import { useDragDropStore, type DragItem } from './useDragDrop';

interface UseDraggableOptions {
  item: DragItem;
  validDropZones: string[];
  disabled?: boolean;
}

interface DragProps {
  draggable: boolean;
  onDragStart: (e: React.DragEvent) => void;
  onDragEnd: (e: React.DragEvent) => void;
}

interface UseDraggableResult {
  dragProps: DragProps;
  isBeingDragged: boolean;
}

export function useDraggable({
  item,
  validDropZones,
  disabled = false,
}: UseDraggableOptions): UseDraggableResult {
  const { isDragging, dragItem, startDrag, endDrag } = useDragDropStore();

  const isBeingDragged = isDragging && dragItem?.card?.id === item.card.id;

  // Safety net: if a drag is interrupted (alt-tab, window blur), clear state
  useEffect(() => {
    if (!isDragging) return;
    const clearDrag = () => endDrag();
    document.addEventListener('dragend', clearDrag);
    window.addEventListener('blur', clearDrag);
    return () => {
      document.removeEventListener('dragend', clearDrag);
      window.removeEventListener('blur', clearDrag);
    };
  }, [isDragging, endDrag]);

  const onDragStart = useCallback(
    (e: React.DragEvent) => {
      if (disabled) {
        e.preventDefault();
        return;
      }
      e.dataTransfer.setData('application/json', JSON.stringify(item));
      e.dataTransfer.effectAllowed = 'move';
      // Small timeout so the drag image renders before we update state
      requestAnimationFrame(() => {
        startDrag(item, validDropZones);
      });
    },
    [disabled, item, validDropZones, startDrag],
  );

  const onDragEnd = useCallback(
    (_e: React.DragEvent) => {
      endDrag();
    },
    [endDrag],
  );

  const dragProps = useMemo<DragProps>(
    () => ({
      draggable: !disabled,
      onDragStart,
      onDragEnd,
    }),
    [disabled, onDragStart, onDragEnd],
  );

  return { dragProps, isBeingDragged };
}
