/**
 * Battlefield Component
 *
 * Displays permanents on the battlefield for one player.
 * Supports drag and drop for playing lands and targeting spells.
 */

import { useCallback } from 'react';
import clsx from 'clsx';
import { TargetableCard } from '../cards/TargetableCard';
import {
  CreatureIcon,
  ArtifactIcon,
  PlayLandIcon,
  PlayerIcon,
  GamepadIcon,
} from '../ui/Icons';
import { useDragDropStore, type DragItem } from '../../hooks/useDragDrop';
import type { CardData } from '../../types';

interface BattlefieldProps {
  permanents: CardData[];
  isOpponent?: boolean;
  selectedCardId?: string | null;
  validTargets?: string[];
  selectedAttackers?: string[];
  selectedBlockers?: Map<string, string>;
  combatAttackers?: string[];
  onCardClick?: (card: CardData) => void;
  onCardDrop?: (item: DragItem, targetCard: CardData) => void;
  onBattlefieldDrop?: (item: DragItem) => void;
}

export function Battlefield({
  permanents,
  isOpponent = false,
  selectedCardId,
  validTargets = [],
  selectedAttackers = [],
  selectedBlockers = new Map(),
  combatAttackers = [],
  onCardClick,
  onCardDrop,
  onBattlefieldDrop,
}: BattlefieldProps) {
  const { isDragging, validDropZones, setHoveredZone, hoveredDropZone, endDrag } = useDragDropStore();

  // Group permanents by type
  const creatures = permanents.filter((p) => p.types.includes('CREATURE'));
  const lands = permanents.filter((p) => p.types.includes('LAND'));
  const others = permanents.filter(
    (p) => !p.types.includes('CREATURE') && !p.types.includes('LAND')
  );

  const dropZoneId = isOpponent ? 'battlefield-opponent' : 'battlefield-self';
  const isValidDropTarget = isDragging && validDropZones.includes(dropZoneId);
  const isHovered = hoveredDropZone === dropZoneId;

  // Handle drop on the battlefield (for lands)
  const handleDragOver = useCallback((e: React.DragEvent) => {
    if (!isValidDropTarget) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
  }, [isValidDropTarget]);

  const handleDragEnter = useCallback((e: React.DragEvent) => {
    if (!isValidDropTarget) return;
    e.preventDefault();
    setHoveredZone(dropZoneId);
  }, [isValidDropTarget, dropZoneId, setHoveredZone]);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    // Only handle if we're actually leaving this element
    const rect = e.currentTarget.getBoundingClientRect();
    const x = e.clientX;
    const y = e.clientY;
    if (x >= rect.left && x <= rect.right && y >= rect.top && y <= rect.bottom) {
      return;
    }
    setHoveredZone(null);
  }, [setHoveredZone]);

  const handleDrop = useCallback((e: React.DragEvent) => {
    if (!isValidDropTarget || !onBattlefieldDrop) return;
    e.preventDefault();
    setHoveredZone(null);

    try {
      const data = e.dataTransfer.getData('application/json');
      if (data) {
        const item: DragItem = JSON.parse(data);
        onBattlefieldDrop(item);
        endDrag();
      }
    } catch (err) {
      console.error('Failed to parse drag data:', err);
    }
  }, [isValidDropTarget, onBattlefieldDrop, setHoveredZone, endDrag]);

  const renderCardGroup = (cards: CardData[], label: string, IconComponent: React.ComponentType<{ className?: string; size?: 'xs' | 'sm' | 'md' | 'lg' }>) => {
    if (cards.length === 0) return null;

    return (
      <div className="flex flex-col gap-2">
        <div className="flex items-center gap-2">
          <IconComponent className="text-slate-400" size="md" />
          <span className="text-xs text-slate-400 uppercase tracking-wider font-semibold">
            {label}
          </span>
          <span className="text-xs text-slate-500">({cards.length})</span>
        </div>
        <div className="flex flex-wrap gap-3">
          {cards.map((card) => {
            const isSelected = selectedCardId === card.id;
            const isTargetable = validTargets.includes(card.id);
            const isAttacking = selectedAttackers.includes(card.id);
            const isBlockingAttacker = combatAttackers.includes(card.id);
            const isBlocking = selectedBlockers.has(card.id);

            return (
              <TargetableCard
                key={card.id}
                card={card}
                size="small"
                isSelected={isSelected}
                isTargetable={isTargetable}
                isHighlighted={isBlockingAttacker}
                isAttacking={isAttacking}
                isBlocking={isBlocking}
                onClick={() => onCardClick?.(card)}
                onDrop={onCardDrop}
              />
            );
          })}
        </div>
      </div>
    );
  };

  return (
    <div
      className={clsx(
        'p-4 rounded-xl min-h-[140px] relative',
        'border-2 transition-all duration-200',
        isOpponent
          ? 'bg-gradient-to-b from-red-950/30 via-slate-900/50 to-slate-900/30 border-red-900/40'
          : 'bg-gradient-to-b from-emerald-950/30 via-slate-900/50 to-slate-900/30 border-emerald-900/40',
        {
          'order-first': isOpponent,
          'ring-4 ring-cyan-400/50': isValidDropTarget && !isHovered,
          'ring-4 ring-emerald-500 bg-emerald-900/20': isHovered,
        }
      )}
      onDragOver={handleDragOver}
      onDragEnter={handleDragEnter}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      {/* Header */}
      <div className="flex items-center gap-2 mb-3 pb-2 border-b border-slate-700/50">
        {isOpponent ? (
          <PlayerIcon className="text-red-400" size="md" />
        ) : (
          <GamepadIcon className="text-emerald-400" size="md" />
        )}
        <span className="text-xs text-slate-300 uppercase tracking-wider font-semibold">
          {isOpponent ? "Opponent's Battlefield" : 'Your Battlefield'}
        </span>
        <span className="text-xs text-slate-500">
          ({permanents.length} {permanents.length === 1 ? 'permanent' : 'permanents'})
        </span>
      </div>

      {permanents.length === 0 ? (
        <div className={clsx(
          'text-sm italic text-center py-8 border-2 border-dashed rounded-xl transition-all duration-300',
          isValidDropTarget && !isHovered && 'text-cyan-400 border-cyan-500/60 bg-cyan-900/10 animate-pulse',
          isValidDropTarget && isHovered && 'text-emerald-300 border-emerald-400 bg-emerald-900/20 scale-[1.02]',
          !isValidDropTarget && 'text-slate-600 border-slate-700'
        )}>
          {isValidDropTarget ? (
            <div className="flex flex-col items-center gap-2">
              <span className="text-2xl">{isHovered ? '✓' : '↓'}</span>
              <span className="font-medium">
                {isHovered ? 'Release to play!' : 'Drop here to play'}
              </span>
            </div>
          ) : (
            'No permanents in play'
          )}
        </div>
      ) : (
        <div
          className={clsx('flex gap-8', {
            'flex-row-reverse': isOpponent,
          })}
        >
          {/* Creatures - main area */}
          <div className="flex-1">{renderCardGroup(creatures, 'Creatures', CreatureIcon)}</div>

          {/* Other permanents */}
          {others.length > 0 && (
            <div className="flex-shrink-0">{renderCardGroup(others, 'Other', ArtifactIcon)}</div>
          )}

          {/* Lands - compact on the side */}
          {lands.length > 0 && (
            <div className="flex-shrink-0 max-w-[250px]">
              {renderCardGroup(lands, 'Lands', PlayLandIcon)}
            </div>
          )}
        </div>
      )}

      {/* Drop indicator overlay */}
      {isValidDropTarget && (
        <div className={clsx(
          'absolute inset-0 rounded-xl pointer-events-none flex items-center justify-center transition-all duration-300',
          isHovered ? 'bg-emerald-500/15' : 'bg-cyan-500/5'
        )}>
          {isHovered && (
            <div className="bg-gradient-to-r from-emerald-600 to-emerald-500 text-white px-6 py-3 rounded-xl font-bold shadow-xl border-2 border-emerald-400 animate-bounce">
              Release to Play!
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default Battlefield;
