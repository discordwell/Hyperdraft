/**
 * HandView Component
 *
 * Displays the player's hand of cards in a fan layout.
 * Cards can be dragged to play lands or cast spells on targets.
 */

import { useMemo, useCallback } from 'react';
import clsx from 'clsx';
import { Card } from '../cards/Card';
import { useDraggable } from '../../hooks/useDraggable';
import { CastIcon, PlayLandIcon } from '../ui/Icons';
import { useDragDropStore } from '../../hooks/useDragDrop';
import type { DragItem } from '../../hooks/useDragDrop';
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

// ---------------------------------------------------------------------------
// HandCard — inline card with useDraggable (replaces DraggableCard wrapper)
// Badges (LAND / TARGET / CAST) are MTG-specific and preserved here.
// ---------------------------------------------------------------------------
interface HandCardProps {
  card: CardData;
  action: LegalActionData | undefined;
  isSelected: boolean;
  isPlayable: boolean;
  disabled: boolean;
  onClick?: () => void;
  validDropZones: string[];
}

function HandCard({
  card,
  action,
  isSelected,
  isPlayable,
  disabled,
  onClick,
  validDropZones,
}: HandCardProps) {
  const isDragging = useDragDropStore((s) => s.isDragging);
  const dragItem = useDragDropStore((s) => s.dragItem);

  const dragItemPayload = useMemo<DragItem>(() => ({
    type: 'hand-card',
    card,
    action,
  }), [card, action]);

  const { dragProps, isBeingDragged } = useDraggable({
    item: dragItemPayload,
    validDropZones,
    disabled: disabled || !isPlayable,
  });

  const isLand = action?.type === 'PLAY_LAND';
  const isTargetedSpell = action?.type === 'CAST_SPELL' && action.requires_targets;
  const isOtherCardDragging = isDragging && dragItem?.card.id !== card.id;

  return (
    <div
      {...dragProps}
      className={clsx(
        'transition-all duration-200',
        {
          'opacity-50 scale-95 shadow-2xl': isBeingDragged,
          'opacity-30': isOtherCardDragging,
          'cursor-grab active:cursor-grabbing': !disabled && isPlayable,
        },
      )}
    >
      <Card
        card={card}
        size="medium"
        isSelected={isSelected}
        isHighlighted={isPlayable && !disabled && !isBeingDragged}
        onClick={onClick}
        showDetails
      />

      {/* MTG-specific drag-intent badge */}
      {!disabled && isPlayable && !isBeingDragged && !isOtherCardDragging && (
        <div className="absolute -top-2 -right-2 z-20">
          <div
            className={clsx(
              'px-2 py-0.5 rounded-full text-[10px] font-bold shadow-lg border',
              isLand
                ? 'bg-emerald-500 text-white border-emerald-400'
                : isTargetedSpell
                  ? 'bg-red-500 text-white border-red-400'
                  : 'bg-blue-500 text-white border-blue-400',
            )}
          >
            {/* Human-requested label: LAND / TARGET / CAST */}
            {isLand ? 'LAND' : isTargetedSpell ? 'TARGET' : 'CAST'}
          </div>
        </div>
      )}
    </div>
  );
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
  const isDragging = useDragDropStore((s) => s.isDragging);
  const dragItem = useDragDropStore((s) => s.dragItem);
  const validDropZones = useDragDropStore((s) => s.validDropZones);

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

    const maxRotation = Math.min(count * 4, 30);
    const rotationStep = count > 1 ? maxRotation / (count - 1) : 0;
    const startRotation = -maxRotation / 2;
    const overlapPercent = count <= 4 ? 0 : Math.min((count - 4) * 8, 50);

    return cards.map((_, index) => ({
      rotation: startRotation + index * rotationStep,
      translateY: Math.abs(index - (count - 1) / 2) * 4,
      zIndex: index,
      marginLeft: index === 0 ? 0 : -overlapPercent,
    }));
  }, [cards]);

  // Get the legal action for a card
  const getCardAction = useCallback((cardId: string): LegalActionData | undefined => {
    return legalActions.find(
      (a) => (a.type === 'CAST_SPELL' || a.type === 'PLAY_LAND') && a.card_id === cardId
    );
  }, [legalActions]);

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
              const cardValidDropZones = isPlayable && !disabled && onGetValidDropZones
                ? onGetValidDropZones(card)
                : [];

              return (
                <div
                  key={card.id}
                  role="button"
                  tabIndex={!disabled || isPlayable ? 0 : -1}
                  aria-label={card.name}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      if (!disabled || isPlayable) onCardClick?.(card);
                    }
                  }}
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
                    <HandCard
                      card={card}
                      action={action}
                      isSelected={isSelected}
                      isPlayable={isPlayable}
                      disabled={disabled}
                      onClick={disabled && !isPlayable ? undefined : () => onCardClick?.(card)}
                      validDropZones={cardValidDropZones}
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
