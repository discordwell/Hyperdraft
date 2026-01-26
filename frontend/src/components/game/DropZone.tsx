/**
 * DropZone Component
 *
 * A wrapper component that handles HTML5 drop events.
 * Used to create drop targets for dragged cards.
 */

import { useCallback, useState } from 'react';
import clsx from 'clsx';
import { useDragDropStore, type DragItem } from '../../hooks/useDragDrop';

interface DropZoneProps {
  id: string;
  children: React.ReactNode;
  onDrop: (item: DragItem) => void;
  disabled?: boolean;
  className?: string;
  highlightClassName?: string;
  activeClassName?: string;
}

export function DropZone({
  id,
  children,
  onDrop,
  disabled = false,
  className = '',
  highlightClassName = 'ring-4 ring-emerald-400 ring-opacity-50 bg-emerald-900/20',
  activeClassName = 'ring-4 ring-emerald-500 bg-emerald-800/30',
}: DropZoneProps) {
  const { isDragging, validDropZones, setHoveredZone, hoveredDropZone } = useDragDropStore();
  const [isOver, setIsOver] = useState(false);

  const isValidDropTarget = isDragging && validDropZones.includes(id);
  const isActiveTarget = isValidDropTarget && hoveredDropZone === id;

  const handleDragOver = useCallback((e: React.DragEvent) => {
    if (disabled || !isValidDropTarget) return;

    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
  }, [disabled, isValidDropTarget]);

  const handleDragEnter = useCallback((e: React.DragEvent) => {
    if (disabled || !isValidDropTarget) return;

    e.preventDefault();
    setIsOver(true);
    setHoveredZone(id);
  }, [disabled, isValidDropTarget, id, setHoveredZone]);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    // Only handle if we're actually leaving this element, not entering a child
    if (e.currentTarget.contains(e.relatedTarget as Node)) return;

    setIsOver(false);
    setHoveredZone(null);
  }, [setHoveredZone]);

  const handleDrop = useCallback((e: React.DragEvent) => {
    if (disabled || !isValidDropTarget) return;

    e.preventDefault();
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
  }, [disabled, isValidDropTarget, onDrop, setHoveredZone]);

  return (
    <div
      onDragOver={handleDragOver}
      onDragEnter={handleDragEnter}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      className={clsx(
        className,
        'transition-all duration-200',
        {
          [highlightClassName]: isValidDropTarget && !isOver,
          [activeClassName]: isActiveTarget || isOver,
        }
      )}
    >
      {children}

      {/* Drop indicator overlay */}
      {isValidDropTarget && (
        <div className={clsx(
          'absolute inset-0 pointer-events-none rounded-xl transition-opacity duration-200',
          'flex items-center justify-center',
          isOver ? 'opacity-100' : 'opacity-0'
        )}>
          <div className="bg-emerald-500/90 text-white px-4 py-2 rounded-lg font-bold text-sm shadow-lg">
            Drop Here
          </div>
        </div>
      )}
    </div>
  );
}

export default DropZone;
