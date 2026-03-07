/**
 * YGOCard Component
 *
 * Renders a Yu-Gi-Oh! card with attribute icon, level stars,
 * ATK/DEF display, and position-aware orientation.
 */

import type { CardData } from '../../types';

const ATTRIBUTE_COLORS: Record<string, string> = {
  DARK: 'bg-purple-800',
  LIGHT: 'bg-yellow-400',
  FIRE: 'bg-red-600',
  WATER: 'bg-blue-600',
  EARTH: 'bg-amber-700',
  WIND: 'bg-green-600',
  DIVINE: 'bg-yellow-600',
};

const CARD_TYPE_BORDERS: Record<string, string> = {
  YGO_MONSTER: 'border-amber-600',
  YGO_SPELL: 'border-teal-500',
  YGO_TRAP: 'border-pink-600',
};

function getCardBorderColor(card: CardData): string {
  if (card.face_down) return 'border-amber-900';
  for (const type of card.types || []) {
    if (CARD_TYPE_BORDERS[type]) return CARD_TYPE_BORDERS[type];
  }
  return 'border-gray-600';
}

function getCardBgColor(card: CardData): string {
  if (card.face_down) return 'bg-amber-950';
  if (card.types?.includes('YGO_SPELL')) return 'bg-teal-950';
  if (card.types?.includes('YGO_TRAP')) return 'bg-pink-950';
  if (card.ygo_monster_type === 'Effect') return 'bg-orange-950';
  if (card.ygo_monster_type === 'Fusion') return 'bg-purple-950';
  if (card.ygo_monster_type === 'Synchro') return 'bg-gray-200 text-gray-900';
  if (card.ygo_monster_type === 'Xyz') return 'bg-gray-950';
  if (card.ygo_monster_type === 'Link') return 'bg-blue-950';
  if (card.ygo_monster_type === 'Ritual') return 'bg-blue-900';
  return 'bg-amber-950/80'; // Normal monster
}

interface YGOCardProps {
  card: CardData;
  size?: 'sm' | 'md' | 'lg';
  onClick?: () => void;
  selected?: boolean;
  isDefensePosition?: boolean;
  className?: string;
}

export function YGOCard({
  card,
  size = 'md',
  onClick,
  selected = false,
  isDefensePosition = false,
  className = '',
}: YGOCardProps) {
  const sizeClasses = {
    sm: 'w-14 h-20',
    md: 'w-20 h-28',
    lg: 'w-28 h-40',
  };

  const isFaceDown = card.face_down;
  const isDef = card.ygo_position === 'face_up_def' || card.ygo_position === 'face_down_def' || isDefensePosition;
  const borderColor = getCardBorderColor(card);
  const bgColor = getCardBgColor(card);

  return (
    <div
      onClick={onClick}
      className={`
        ${isDef ? 'rotate-90' : ''}
        ${sizeClasses[size]}
        ${borderColor}
        ${bgColor}
        border-2 rounded-md cursor-pointer transition-all duration-150
        ${selected ? 'ring-2 ring-yellow-400 ring-offset-1 ring-offset-gray-900 scale-105' : ''}
        ${onClick ? 'hover:scale-105 hover:brightness-110' : ''}
        flex flex-col overflow-hidden relative
        ${className}
      `}
    >
      {isFaceDown ? (
        // Face-down card back
        <div className="flex-1 flex items-center justify-center bg-amber-900 rounded-sm m-0.5">
          <div className="w-3/4 h-3/4 border border-amber-700 rounded-sm bg-amber-800 flex items-center justify-center">
            <div className="text-amber-600 text-[8px] font-bold">YGO</div>
          </div>
        </div>
      ) : (
        <>
          {/* Attribute badge */}
          {card.attribute && size !== 'sm' && (
            <div className={`absolute top-0.5 right-0.5 w-3.5 h-3.5 rounded-full ${ATTRIBUTE_COLORS[card.attribute] || 'bg-gray-600'} flex items-center justify-center`}>
              <span className="text-[6px] font-bold text-white">{card.attribute?.[0]}</span>
            </div>
          )}

          {/* Level stars */}
          {card.level && card.level > 0 && size !== 'sm' && (
            <div className="flex justify-center gap-px pt-0.5 px-0.5">
              {Array.from({ length: Math.min(card.level, 12) }).map((_, i) => (
                <div key={i} className="w-1.5 h-1.5 bg-yellow-400 rounded-full" />
              ))}
            </div>
          )}

          {/* Rank stars (Xyz) */}
          {card.rank && card.rank > 0 && size !== 'sm' && (
            <div className="flex justify-center gap-px pt-0.5 px-0.5">
              {Array.from({ length: Math.min(card.rank, 12) }).map((_, i) => (
                <div key={i} className="w-1.5 h-1.5 bg-yellow-400 rounded-full border border-yellow-600" />
              ))}
            </div>
          )}

          {/* Card name */}
          <div className="px-1 pt-0.5 flex-1 min-h-0">
            <div className={`font-bold leading-tight truncate ${size === 'sm' ? 'text-[6px]' : 'text-[8px]'} text-white`}>
              {card.name}
            </div>
            {size === 'lg' && card.text && (
              <div className="text-[7px] text-gray-400 leading-tight mt-0.5 line-clamp-3">
                {card.text}
              </div>
            )}
          </div>

          {/* ATK/DEF display */}
          {card.atk !== undefined && card.atk !== null && (
            <div className="flex justify-between px-1 pb-0.5 bg-black/30">
              <span className={`font-bold ${size === 'sm' ? 'text-[6px]' : 'text-[8px]'} text-red-400`}>
                {card.atk}
              </span>
              {card.def_val !== undefined && card.def_val !== null && (
                <span className={`font-bold ${size === 'sm' ? 'text-[6px]' : 'text-[8px]'} text-blue-400`}>
                  {card.def_val}
                </span>
              )}
              {card.link_rating !== undefined && card.link_rating !== null && (
                <span className={`font-bold ${size === 'sm' ? 'text-[6px]' : 'text-[8px]'} text-blue-400`}>
                  L{card.link_rating}
                </span>
              )}
            </div>
          )}

          {/* Spell/Trap type badge */}
          {!card.types?.includes('YGO_MONSTER') && size !== 'sm' && (
            <div className="px-1 pb-0.5">
              <span className="text-[7px] text-gray-400 uppercase">
                {card.ygo_spell_type || card.ygo_trap_type || ''}
              </span>
            </div>
          )}

          {/* Overlay units (Xyz) */}
          {card.overlay_units !== undefined && card.overlay_units > 0 && (
            <div className="absolute bottom-0.5 left-0.5 bg-purple-600 text-white text-[6px] font-bold rounded-full w-3 h-3 flex items-center justify-center">
              {card.overlay_units}
            </div>
          )}
        </>
      )}
    </div>
  );
}
