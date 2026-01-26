/**
 * TargetableCard Component
 *
 * A card on the battlefield that can be a drop target for spells.
 * Used for targeted spells like removal, auras, etc.
 */

import { useCallback, useState } from 'react';
import clsx from 'clsx';
import { Card } from './Card';
import { useDragDropStore, type DragItem } from '../../hooks/useDragDrop';
import type { CardData } from '../../types';

interface TargetableCardProps {
  card: CardData;
  isSelected?: boolean;
  isTargetable?: boolean;
  isHighlighted?: boolean;
  isAttacking?: boolean;
  isBlocking?: boolean;
  onClick?: () => void;
  onDrop?: (item: DragItem, target: CardData) => void;
  size?: 'small' | 'medium' | 'large';
}

export function TargetableCard({
  card,
  isSelected = false,
  isTargetable = false,
  isHighlighted = false,
  isAttacking = false,
  isBlocking = false,
  onClick,
  onDrop,
  size = 'small',
}: TargetableCardProps) {
  const { isDragging, validDropZones, setHoveredZone, hoveredDropZone } = useDragDropStore();
  const [isOver, setIsOver] = useState(false);

  const dropZoneId = `card-${card.id}`;
  const isValidDropTarget = isDragging && validDropZones.includes(dropZoneId);
  const isActiveTarget = hoveredDropZone === dropZoneId;

  const handleDragOver = useCallback((e: React.DragEvent) => {
    if (!isValidDropTarget) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
  }, [isValidDropTarget]);

  const handleDragEnter = useCallback((e: React.DragEvent) => {
    if (!isValidDropTarget) return;
    e.preventDefault();
    setIsOver(true);
    setHoveredZone(dropZoneId);
  }, [isValidDropTarget, dropZoneId, setHoveredZone]);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    if (e.currentTarget.contains(e.relatedTarget as Node)) return;
    setIsOver(false);
    setHoveredZone(null);
  }, [setHoveredZone]);

  const handleDrop = useCallback((e: React.DragEvent) => {
    if (!isValidDropTarget || !onDrop) return;
    e.preventDefault();
    e.stopPropagation();
    setIsOver(false);
    setHoveredZone(null);

    try {
      const data = e.dataTransfer.getData('application/json');
      if (data) {
        const item: DragItem = JSON.parse(data);
        onDrop(item, card);
      }
    } catch (err) {
      console.error('Failed to parse drag data:', err);
    }
  }, [isValidDropTarget, onDrop, card, setHoveredZone]);

  return (
    <div
      className={clsx(
        'relative transition-all duration-300',
        {
          'ring-4 ring-cyan-400 ring-opacity-80 rounded-xl scale-105 animate-pulse': isValidDropTarget && !isOver,
          'ring-4 ring-emerald-400 rounded-xl scale-110 shadow-lg shadow-emerald-500/30': isActiveTarget || isOver,
        }
      )}
      onDragOver={handleDragOver}
      onDragEnter={handleDragEnter}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      <Card
        card={card}
        size={size}
        isSelected={isSelected || isAttacking || isBlocking}
        isTargetable={isTargetable || isValidDropTarget}
        isHighlighted={isHighlighted}
        onClick={onClick}
      />

      {/* Attack indicator */}
      {isAttacking && (
        <div className="absolute -top-1 -right-1 inline-flex items-center gap-1 bg-gradient-to-br from-red-500 to-red-700 text-white text-[10px] px-2 py-0.5 rounded-full font-bold shadow-lg border border-red-400 z-10">
          ATK
        </div>
      )}

      {/* Block indicator */}
      {isBlocking && (
        <div className="absolute -top-1 -right-1 inline-flex items-center gap-1 bg-gradient-to-br from-blue-500 to-blue-700 text-white text-[10px] px-2 py-0.5 rounded-full font-bold shadow-lg border border-blue-400 z-10">
          BLK
        </div>
      )}

      {/* Valid drop target indicator */}
      {isValidDropTarget && !isOver && (
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none rounded-xl bg-cyan-500/10">
          <div className="absolute -top-3 left-1/2 -translate-x-1/2 bg-cyan-600 text-white px-2 py-0.5 rounded text-[10px] font-bold shadow-lg whitespace-nowrap">
            Valid Target
          </div>
        </div>
      )}

      {/* Active hover drop indicator */}
      {isOver && (
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none rounded-xl bg-emerald-500/25">
          <div className="bg-emerald-500 text-white px-3 py-1.5 rounded-lg text-sm font-bold shadow-xl border border-emerald-400">
            Release to Target
          </div>
        </div>
      )}
    </div>
  );
}

export default TargetableCard;
