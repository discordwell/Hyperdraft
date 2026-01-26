/**
 * HandView Component
 *
 * Displays the player's hand of cards in a fan layout.
 * Cards can be dragged to play lands or cast spells on targets.
 */

import { useMemo, useCallback } from 'react';
import clsx from 'clsx';
import { DraggableCard } from '../cards/DraggableCard';
import { CastIcon, PlayLandIcon } from '../ui/Icons';
import { useDragDropStore } from '../../hooks/useDragDrop';
import type { CardData, LegalActionData } from '../../types';

interface HandViewProps {
  cards: CardData[];
  selectedCardId?: string | null;
  castableCards?: string[];
  playableLands?: string[];
  legalActions?: LegalActionData[];
  onCardClick?: (card: CardData) => void;
  onGetValidDropZones?: (card: CardData) => string[];
  disabled?: boolean;
}

export function HandView({
  cards,
  selectedCardId,
  castableCards = [],
  playableLands = [],
  legalActions = [],
  onCardClick,
  onGetValidDropZones,
  disabled = false,
}: HandViewProps) {
  const { isDragging, dragItem, validDropZones } = useDragDropStore();

  // Get context about the currently dragged card
  const dragContext = useMemo(() => {
    if (!isDragging || !dragItem) return null;

    const isLand = dragItem.action?.type === 'PLAY_LAND';
    const isTargetedSpell = dragItem.action?.type === 'CAST_SPELL' && dragItem.action?.requires_targets;

    return {
      cardName: dragItem.card.name,
      isLand,
      isTargetedSpell,
      targetCount: validDropZones.length,
    };
  }, [isDragging, dragItem, validDropZones]);

  // Calculate card positions for fan effect
  const cardPositions = useMemo(() => {
    const count = cards.length;
    if (count === 0) return [];

    // Adjust spread based on card count
    const maxRotation = Math.min(count * 4, 30); // Max 30 degrees total spread
    const rotationStep = count > 1 ? maxRotation / (count - 1) : 0;
    const startRotation = -maxRotation / 2;

    // Card overlap - less overlap for fewer cards
    const overlapPercent = count <= 4 ? 0 : Math.min((count - 4) * 8, 50);

    return cards.map((_, index) => ({
      rotation: startRotation + index * rotationStep,
      translateY: Math.abs(index - (count - 1) / 2) * 4, // Arc effect
      zIndex: index,
      marginLeft: index === 0 ? 0 : -overlapPercent,
    }));
  }, [cards]); // Use cards array as dependency to ensure positions update

  // Get the legal action for a card
  const getCardAction = useCallback((cardId: string): LegalActionData | undefined => {
    return legalActions.find(
      (a) => (a.type === 'CAST_SPELL' || a.type === 'PLAY_LAND') && a.card_id === cardId
    );
  }, [legalActions]);

  // Handle drag start - return valid drop zones for this card
  const handleDragStart = useCallback((card: CardData): string[] => {
    if (onGetValidDropZones) {
      return onGetValidDropZones(card);
    }
    return [];
  }, [onGetValidDropZones]);

  return (
    <div className="relative">
      {/* Hand container */}
      <div className={clsx(
        'bg-gradient-to-t from-slate-900/95 to-slate-800/90 backdrop-blur-sm rounded-t-2xl border border-slate-600/50 border-b-0 px-6 py-4 shadow-2xl',
        'transition-all duration-200',
        {
          'border-cyan-500/50': isDragging,
        }
      )}>
        {/* Header */}
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <span className="text-slate-400 text-xs uppercase tracking-widest font-semibold">Your Hand</span>
            <span className="bg-slate-700 text-slate-300 text-xs px-2 py-0.5 rounded-full font-medium">
              {cards.length} {cards.length === 1 ? 'card' : 'cards'}
            </span>
          </div>
          {cards.length > 0 && (
            <div className="text-xs">
              {isDragging && dragContext ? (
                <span className={clsx(
                  'px-3 py-1 rounded-full font-medium',
                  dragContext.isLand
                    ? 'bg-emerald-600/80 text-emerald-100'
                    : dragContext.isTargetedSpell
                      ? 'bg-red-600/80 text-red-100'
                      : 'bg-blue-600/80 text-blue-100'
                )}>
                  {dragContext.isLand
                    ? 'Drop on your battlefield to play'
                    : dragContext.isTargetedSpell
                      ? `Drop on a target (${dragContext.targetCount} valid)`
                      : 'Drop on battlefield to cast'}
                </span>
              ) : (
                <span className="text-slate-500">
                  Drag cards to play lands or cast spells
                </span>
              )}
            </div>
          )}
        </div>

        {/* Cards */}
        {cards.length === 0 ? (
          <div className="text-slate-500 text-sm italic text-center py-8 border border-dashed border-slate-600 rounded-lg">
            No cards in hand
          </div>
        ) : (
          <div className="flex justify-center items-end min-h-[230px] pb-2">
            {cards.map((card, index) => {
              const isSelected = selectedCardId === card.id;
              const canCast = castableCards.includes(card.id);
              const canPlayLand = playableLands.includes(card.id);
              const isPlayable = canCast || canPlayLand;
              const position = cardPositions[index] || { rotation: 0, translateY: 0, zIndex: index, marginLeft: 0 };
              const action = getCardAction(card.id);

              return (
                <div
                  key={card.id}
                  className={clsx(
                    'relative transition-all duration-200 ease-out',
                    {
                      'cursor-pointer': !disabled || isPlayable,
                      'cursor-not-allowed': disabled && !isPlayable,
                    }
                  )}
                  style={{
                    transform: `rotate(${position.rotation}deg) translateY(${isSelected ? -30 : position.translateY}px)`,
                    transformOrigin: 'bottom center',
                    zIndex: isSelected ? 100 : position.zIndex,
                    marginLeft: index === 0 ? 0 : `${position.marginLeft}px`,
                  }}
                >
                  <div
                    className={clsx(
                      'transition-transform duration-200',
                      {
                        'hover:-translate-y-6 hover:scale-105': !disabled && !isSelected,
                        'scale-110': isSelected,
                        'opacity-40 grayscale': disabled && !isPlayable,
                      }
                    )}
                  >
                    <DraggableCard
                      card={card}
                      action={action}
                      size="medium"
                      isSelected={isSelected}
                      isHighlighted={isPlayable && !disabled}
                      onClick={disabled && !isPlayable ? undefined : () => onCardClick?.(card)}
                      onDragStart={isPlayable && !disabled ? handleDragStart : undefined}
                      showDetails={true}
                      disabled={disabled && !isPlayable}
                    />
                  </div>

                  {/* Playable badge */}
                  {isPlayable && !disabled && (
                    <div className="absolute -bottom-2 left-1/2 -translate-x-1/2 z-10">
                      <span
                        className={clsx(
                          'inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold uppercase tracking-wide shadow-lg',
                          'border-2',
                          canCast
                            ? 'bg-gradient-to-r from-blue-600 to-blue-500 text-white border-blue-400'
                            : 'bg-gradient-to-r from-emerald-600 to-emerald-500 text-white border-emerald-400'
                        )}
                      >
                        {canCast ? (
                          <>
                            <CastIcon size="sm" />
                            Cast
                          </>
                        ) : (
                          <>
                            <PlayLandIcon size="sm" />
                            Play
                          </>
                        )}
                      </span>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

export default HandView;
