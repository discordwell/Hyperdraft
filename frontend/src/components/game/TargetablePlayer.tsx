/**
 * TargetablePlayer Component
 *
 * Wrapper around PlayerInfo that can receive spell drops for player-targeting spells.
 * Used for burn spells, life gain targeting, etc.
 */

import { useCallback, useState } from 'react';
import clsx from 'clsx';
import { PlayerInfo } from './PlayerInfo';
import { useDragDropStore, type DragItem } from '../../hooks/useDragDrop';
import type { PlayerData } from '../../types';

interface TargetablePlayerProps {
  player: PlayerData;
  playerId: string;
  isActivePlayer?: boolean;
  hasPriority?: boolean;
  isOpponent?: boolean;
  onDrop?: (item: DragItem, playerId: string) => void;
  // Phase 5b overlay-mode targeting: when set, render a glow ring and
  // wire a click handler so the player can be picked as a target.
  isTargetable?: boolean;
  onTargetClick?: (playerId: string) => void;
}

export function TargetablePlayer({
  player,
  playerId,
  isActivePlayer = false,
  hasPriority = false,
  isOpponent = false,
  onDrop,
  isTargetable = false,
  onTargetClick,
}: TargetablePlayerProps) {
  const isDragging = useDragDropStore((s) => s.isDragging);
  const validDropZones = useDragDropStore((s) => s.validDropZones);
  const setHoveredZone = useDragDropStore((s) => s.setHoveredZone);
  const hoveredDropZone = useDragDropStore((s) => s.hoveredDropZone);
  const endDrag = useDragDropStore((s) => s.endDrag);
  const [isOver, setIsOver] = useState(false);

  const dropZoneId = `player-${playerId}`;
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
        onDrop(item, playerId);
        endDrag();
      }
    } catch (err) {
      console.error('Failed to parse drag data:', err);
    }
  }, [isValidDropTarget, onDrop, playerId, setHoveredZone, endDrag]);

  // Click-to-target (overlay-mode pending choice). Drop interactions
  // still go through the drag-and-drop handlers above; this click
  // handler only fires when the player is wired as a legal target.
  const handleClick = useCallback(() => {
    if (isTargetable && onTargetClick) {
      onTargetClick(playerId);
    }
  }, [isTargetable, onTargetClick, playerId]);

  return (
    <div
      data-testid={`targetable-player-${playerId}`}
      className={clsx(
        'relative transition-all duration-200 rounded-lg',
        {
          'ring-4 ring-cyan-400 ring-opacity-80 scale-105': isValidDropTarget && !isOver,
          'ring-4 ring-emerald-500 scale-110 bg-emerald-900/20': isActiveTarget || isOver,
          // Overlay-mode targetable glow (distinct from drag drop-target hint).
          'ring-4 ring-amber-400 ring-opacity-80 cursor-pointer hover:scale-105':
            isTargetable && !isValidDropTarget && !isActiveTarget && !isOver,
        }
      )}
      onClick={handleClick}
      onDragOver={handleDragOver}
      onDragEnter={handleDragEnter}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      <PlayerInfo
        player={player}
        isActivePlayer={isActivePlayer}
        hasPriority={hasPriority}
        isOpponent={isOpponent}
      />

      {/* Drop target indicator */}
      {isValidDropTarget && (
        <div className={clsx(
          'absolute inset-0 flex items-center justify-center pointer-events-none rounded-lg transition-opacity duration-200',
          isOver ? 'bg-emerald-500/30' : 'bg-cyan-500/10'
        )}>
          {isOver && (
            <div className="bg-emerald-600 text-white px-3 py-1.5 rounded-lg text-sm font-bold shadow-lg">
              Target {isOpponent ? 'Opponent' : 'You'}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default TargetablePlayer;
