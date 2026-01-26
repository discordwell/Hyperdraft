/**
 * DraggableCard Component
 *
 * Wraps the Card component with HTML5 drag and drop functionality.
 * Provides smooth drag animations and visual feedback.
 */

import { useCallback, useRef, useState, useEffect } from 'react';
import clsx from 'clsx';
import { Card } from './Card';
import { useDragDropStore, type DragItem } from '../../hooks/useDragDrop';
import type { CardData, LegalActionData } from '../../types';

interface DraggableCardProps {
  card: CardData;
  action?: LegalActionData;
  isSelected?: boolean;
  isHighlighted?: boolean;
  size?: 'small' | 'medium' | 'large';
  showDetails?: boolean;
  onClick?: () => void;
  onDragStart?: (card: CardData) => string[]; // Returns valid drop zone IDs
  disabled?: boolean;
}

export function DraggableCard({
  card,
  action,
  isSelected = false,
  isHighlighted = false,
  size = 'medium',
  showDetails = true,
  onClick,
  onDragStart,
  disabled = false,
}: DraggableCardProps) {
  const { startDrag, endDrag, isDragging, dragItem, validDropZones } = useDragDropStore();
  const [isBeingDragged, setIsBeingDragged] = useState(false);
  const [dragHint, setDragHint] = useState<string | null>(null);
  const dragImageRef = useRef<HTMLDivElement>(null);

  // Determine drag hint based on action type
  useEffect(() => {
    if (isBeingDragged && action) {
      if (action.type === 'PLAY_LAND') {
        setDragHint('Drop on battlefield to play');
      } else if (action.type === 'CAST_SPELL') {
        if (action.requires_targets) {
          setDragHint('Drop on a target');
        } else {
          setDragHint('Drop on battlefield to cast');
        }
      }
    } else {
      setDragHint(null);
    }
  }, [isBeingDragged, action]);

  const handleDragStart = useCallback((e: React.DragEvent) => {
    if (disabled || !onDragStart) {
      e.preventDefault();
      return;
    }

    const dragData: DragItem = {
      type: 'hand-card',
      card,
      action,
    };

    // Set drag data
    e.dataTransfer.setData('application/json', JSON.stringify(dragData));
    e.dataTransfer.effectAllowed = 'move';

    // Create a custom drag image
    if (dragImageRef.current) {
      const rect = dragImageRef.current.getBoundingClientRect();
      e.dataTransfer.setDragImage(
        dragImageRef.current,
        rect.width / 2,
        rect.height / 2
      );
    }

    // Get valid drop zones from callback
    const validZones = onDragStart(card);

    // Update store
    startDrag(dragData, validZones);
    setIsBeingDragged(true);
  }, [card, action, disabled, onDragStart, startDrag]);

  const handleDragEnd = useCallback(() => {
    endDrag();
    setIsBeingDragged(false);
  }, [endDrag]);

  const isOtherCardDragging = isDragging && dragItem?.card.id !== card.id;
  const hasValidTargets = isBeingDragged && validDropZones.length > 0;
  const isLand = action?.type === 'PLAY_LAND';
  const isTargetedSpell = action?.type === 'CAST_SPELL' && action?.requires_targets;

  return (
    <div className="relative">
      <div
        draggable={!disabled && !!onDragStart}
        onDragStart={handleDragStart}
        onDragEnd={handleDragEnd}
        className={clsx(
          'transition-all duration-200',
          {
            'opacity-50 scale-95 shadow-2xl': isBeingDragged,
            'opacity-30': isOtherCardDragging,
            'cursor-grab active:cursor-grabbing': !disabled && onDragStart,
          }
        )}
        ref={dragImageRef}
      >
        <Card
          card={card}
          size={size}
          isSelected={isSelected}
          isHighlighted={isHighlighted && !isBeingDragged}
          onClick={onClick}
          showDetails={showDetails}
        />

        {/* Drag type indicator badge */}
        {!disabled && onDragStart && !isBeingDragged && !isOtherCardDragging && (
          <div className="absolute -top-2 -right-2 z-20">
            <div className={clsx(
              'px-2 py-0.5 rounded-full text-[10px] font-bold shadow-lg border',
              isLand
                ? 'bg-emerald-500 text-white border-emerald-400'
                : isTargetedSpell
                  ? 'bg-red-500 text-white border-red-400'
                  : 'bg-blue-500 text-white border-blue-400'
            )}>
              {isLand ? 'LAND' : isTargetedSpell ? 'TARGET' : 'CAST'}
            </div>
          </div>
        )}
      </div>

      {/* Drag feedback tooltip */}
      {isBeingDragged && dragHint && hasValidTargets && (
        <div className="absolute -top-10 left-1/2 -translate-x-1/2 z-50 whitespace-nowrap">
          <div className="bg-slate-800 text-white text-xs px-3 py-1.5 rounded-lg shadow-xl border border-slate-600">
            {dragHint}
          </div>
        </div>
      )}
    </div>
  );
}

export default DraggableCard;
