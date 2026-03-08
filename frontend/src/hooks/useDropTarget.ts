/**
 * useDropTarget Hook
 *
 * Shared drop target hook that encapsulates HTML5 DnD boilerplate.
 * Works across all game modes (MTG, HS, PKM, YGO).
 */

import { useCallback, useState, useMemo, useEffect } from 'react';
import { useDragDropStore, type DragItem } from './useDragDrop';

interface UseDropTargetOptions {
  zoneId: string;
  onDrop: (item: DragItem) => void;
  disabled?: boolean;
}

interface DropProps {
  onDragOver: (e: React.DragEvent) => void;
  onDragEnter: (e: React.DragEvent) => void;
  onDragLeave: (e: React.DragEvent) => void;
  onDrop: (e: React.DragEvent) => void;
}

interface UseDropTargetResult {
  dropProps: DropProps;
  isValidTarget: boolean;
  isHovered: boolean;
}

export function useDropTarget({
  zoneId,
  onDrop,
  disabled = false,
}: UseDropTargetOptions): UseDropTargetResult {
  const { isDragging, validDropZones, setHoveredZone, hoveredDropZone } =
    useDragDropStore();
  const [isOver, setIsOver] = useState(false);

  // Clear local isOver when drag ends (handles drag-outside-window edge case)
  useEffect(() => {
    if (!isDragging && isOver) setIsOver(false);
  }, [isDragging, isOver]);

  const isValidTarget = isDragging && validDropZones.includes(zoneId);
  const isHovered = isValidTarget && (hoveredDropZone === zoneId || isOver);

  const handleDragOver = useCallback(
    (e: React.DragEvent) => {
      if (disabled || !isValidTarget) return;
      e.preventDefault();
      e.stopPropagation();
      e.dataTransfer.dropEffect = 'move';
    },
    [disabled, isValidTarget],
  );

  const handleDragEnter = useCallback(
    (e: React.DragEvent) => {
      if (disabled || !isValidTarget) return;
      e.preventDefault();
      e.stopPropagation();
      setIsOver(true);
      setHoveredZone(zoneId);
    },
    [disabled, isValidTarget, zoneId, setHoveredZone],
  );

  const handleDragLeave = useCallback(
    (e: React.DragEvent) => {
      if (e.currentTarget.contains(e.relatedTarget as Node)) return;
      setIsOver(false);
      setHoveredZone(null);
    },
    [setHoveredZone],
  );

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      if (disabled || !isValidTarget) return;
      e.preventDefault();
      e.stopPropagation();
      setIsOver(false);
      setHoveredZone(null);

      try {
        const data = e.dataTransfer.getData('application/json');
        if (data) {
          const item: DragItem = JSON.parse(data);
          onDrop(item);
        }
      } catch (err) {
        console.error('Failed to parse drag data:', err);
      }
    },
    [disabled, isValidTarget, onDrop, setHoveredZone],
  );

  const dropProps = useMemo<DropProps>(
    () => ({
      onDragOver: handleDragOver,
      onDragEnter: handleDragEnter,
      onDragLeave: handleDragLeave,
      onDrop: handleDrop,
    }),
    [handleDragOver, handleDragEnter, handleDragLeave, handleDrop],
  );

  return { dropProps, isValidTarget, isHovered };
}
