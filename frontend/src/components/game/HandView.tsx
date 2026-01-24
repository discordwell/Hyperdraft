/**
 * HandView Component
 *
 * Displays the player's hand of cards in a fan layout.
 */

import { useMemo } from 'react';
import clsx from 'clsx';
import { Card } from '../cards';
import type { CardData } from '../../types';

interface HandViewProps {
  cards: CardData[];
  selectedCardId?: string | null;
  castableCards?: string[];
  playableLands?: string[];
  onCardClick?: (card: CardData) => void;
  disabled?: boolean;
}

export function HandView({
  cards,
  selectedCardId,
  castableCards = [],
  playableLands = [],
  onCardClick,
  disabled = false,
}: HandViewProps) {
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

  return (
    <div className="relative">
      {/* Hand container */}
      <div className="bg-gradient-to-t from-slate-900/95 to-slate-800/90 backdrop-blur-sm rounded-t-2xl border border-slate-600/50 border-b-0 px-6 py-4 shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <span className="text-slate-400 text-xs uppercase tracking-widest font-semibold">Your Hand</span>
            <span className="bg-slate-700 text-slate-300 text-xs px-2 py-0.5 rounded-full font-medium">
              {cards.length} {cards.length === 1 ? 'card' : 'cards'}
            </span>
          </div>
          {cards.length > 0 && (
            <span className="text-slate-500 text-xs">Hover to preview • Click to select</span>
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
                    <Card
                      card={card}
                      size="medium"
                      isSelected={isSelected}
                      isHighlighted={isPlayable && !disabled}
                      onClick={disabled && !isPlayable ? undefined : () => onCardClick?.(card)}
                      showDetails={true}
                    />
                  </div>

                  {/* Playable badge */}
                  {isPlayable && !disabled && (
                    <div className="absolute -bottom-2 left-1/2 -translate-x-1/2 z-10">
                      <span
                        className={clsx(
                          'px-3 py-1 rounded-full text-xs font-bold uppercase tracking-wide shadow-lg',
                          'border-2',
                          canCast
                            ? 'bg-blue-600 text-white border-blue-400'
                            : 'bg-emerald-600 text-white border-emerald-400'
                        )}
                      >
                        {canCast ? '✨ Cast' : '🏔️ Play'}
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
