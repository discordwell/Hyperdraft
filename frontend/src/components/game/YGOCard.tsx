/**
 * YGOCard Component
 *
 * Renders a Yu-Gi-Oh! card with proper frame colors, card art,
 * attribute icons, level/rank stars, ATK/DEF bar, and animations.
 */

import { motion } from 'framer-motion';
import { YGO_CARD_ART } from '../../data/ygoCardArt';
import { cardEnter } from '../../utils/ygoAnimations';
import type { CardData } from '../../types';

// ---------- Attribute colors ----------

const ATTRIBUTE_COLORS: Record<string, { bg: string; text: string }> = {
  DARK: { bg: 'bg-purple-800', text: 'text-white' },
  LIGHT: { bg: 'bg-yellow-400', text: 'text-gray-900' },
  FIRE: { bg: 'bg-red-600', text: 'text-white' },
  WATER: { bg: 'bg-blue-600', text: 'text-white' },
  EARTH: { bg: 'bg-amber-700', text: 'text-white' },
  WIND: { bg: 'bg-green-600', text: 'text-white' },
  DIVINE: { bg: 'bg-yellow-600', text: 'text-white' },
};

// ---------- Frame colors by card type ----------

function getFrameBorder(card: CardData): string {
  if (card.face_down) return 'border-ygo-gold-dim/60';
  if (card.types?.includes('YGO_SPELL')) return 'border-teal-500';
  if (card.types?.includes('YGO_TRAP')) return 'border-pink-500';
  switch (card.ygo_monster_type) {
    case 'Normal': return 'border-ygo-gold';
    case 'Effect': return 'border-orange-500';
    case 'Fusion': return 'border-purple-500';
    case 'Synchro': return 'border-gray-300';
    case 'Xyz': return 'border-gray-600';
    case 'Link': return 'border-blue-600';
    case 'Ritual': return 'border-blue-800';
    default: return 'border-ygo-gold';
  }
}

function getFrameBg(card: CardData): string {
  if (card.face_down) return '';
  if (card.types?.includes('YGO_SPELL')) return 'bg-gradient-to-b from-teal-900/90 to-teal-950';
  if (card.types?.includes('YGO_TRAP')) return 'bg-gradient-to-b from-pink-900/90 to-pink-950';
  switch (card.ygo_monster_type) {
    case 'Normal': return 'bg-gradient-to-b from-amber-800/90 to-amber-950';
    case 'Effect': return 'bg-gradient-to-b from-orange-700/90 to-orange-950';
    case 'Fusion': return 'bg-gradient-to-b from-purple-700/90 to-purple-950';
    case 'Synchro': return 'bg-gradient-to-b from-gray-100 to-gray-300';
    case 'Xyz': return 'bg-gradient-to-b from-gray-800 to-gray-950';
    case 'Link': return 'bg-gradient-to-b from-blue-700/90 to-blue-950';
    case 'Ritual': return 'bg-gradient-to-b from-blue-800/90 to-blue-950';
    default: return 'bg-gradient-to-b from-amber-800/90 to-amber-950';
  }
}

function isSynchro(card: CardData): boolean {
  return card.ygo_monster_type === 'Synchro';
}

// ---------- Component ----------

interface YGOCardProps {
  card: CardData;
  size?: 'sm' | 'md' | 'lg';
  onClick?: () => void;
  selected?: boolean;
  isTarget?: boolean;
  isDefensePosition?: boolean;
  className?: string;
  animate?: boolean;
  onHoverStart?: () => void;
  onHoverEnd?: () => void;
}

export function YGOCard({
  card,
  size = 'md',
  onClick,
  selected = false,
  isTarget = false,
  isDefensePosition = false,
  className = '',
  animate = true,
  onHoverStart,
  onHoverEnd,
}: YGOCardProps) {
  const sizeStyles: Record<string, { width: number; height: number }> = {
    sm: { width: 64, height: 88 },
    md: { width: 96, height: 136 },
    lg: { width: 128, height: 184 },
  };

  const isFaceDown = card.face_down;
  const isDef = card.ygo_position === 'face_up_def' || card.ygo_position === 'face_down_def' || isDefensePosition;
  const frameBorder = getFrameBorder(card);
  const frameBg = getFrameBg(card);
  const synchro = !isFaceDown && isSynchro(card);
  const textColor = synchro ? 'text-gray-900' : 'text-white';

  const imageUrl = card.image_url || YGO_CARD_ART[card.name];

  const cardContent = (
    <>
      {isFaceDown ? (
        // Face-down card back — dark maroon with gold elliptical pattern
        <div className="flex-1 rounded-sm m-0.5 relative overflow-hidden"
          style={{
            background: 'radial-gradient(ellipse at center, #5c2121 0%, #3a1010 40%, #1a0505 100%)',
          }}
        >
          <div className="absolute inset-0" style={{
            background: 'radial-gradient(ellipse at 50% 50%, rgba(212,168,67,0.15) 0%, transparent 60%)',
          }} />
          <div className="absolute inset-2 border border-ygo-gold-dim/30 rounded-sm" />
          <div className="absolute inset-4 border border-ygo-gold-dim/15 rounded-sm" />
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="w-6 h-6 rounded-full border-2 border-ygo-gold-dim/40"
              style={{ background: 'radial-gradient(circle, rgba(212,168,67,0.2) 0%, transparent 70%)' }}
            />
          </div>
        </div>
      ) : (
        <>
          {/* Attribute badge */}
          {card.attribute && size !== 'sm' && (
            <div className="absolute top-1 right-1 z-10">
              <div className={`w-5 h-5 rounded-full ${ATTRIBUTE_COLORS[card.attribute]?.bg || 'bg-gray-600'} flex items-center justify-center shadow-md border border-black/30`}>
                <span className={`text-[8px] font-bold ${ATTRIBUTE_COLORS[card.attribute]?.text || 'text-white'}`}>
                  {card.attribute?.[0]}
                </span>
              </div>
            </div>
          )}

          {/* Level stars */}
          {card.level && card.level > 0 && size !== 'sm' && (
            <div className="flex justify-center gap-px pt-1 px-1 flex-wrap">
              {Array.from({ length: Math.min(card.level, 12) }).map((_, i) => (
                <svg key={i} viewBox="0 0 10 10" className={`${size === 'lg' ? 'w-2.5 h-2.5' : 'w-2 h-2'}`}>
                  <polygon points="5,0.5 6.5,3.5 10,4 7.5,6.5 8,9.5 5,8 2,9.5 2.5,6.5 0,4 3.5,3.5"
                    fill="#facc15" stroke="#a16207" strokeWidth="0.5" />
                </svg>
              ))}
            </div>
          )}

          {/* Rank stars (Xyz — black with gold outline) */}
          {card.rank && card.rank > 0 && size !== 'sm' && (
            <div className="flex justify-center gap-px pt-1 px-1 flex-wrap">
              {Array.from({ length: Math.min(card.rank, 12) }).map((_, i) => (
                <svg key={i} viewBox="0 0 10 10" className={`${size === 'lg' ? 'w-2.5 h-2.5' : 'w-2 h-2'}`}>
                  <polygon points="5,0.5 6.5,3.5 10,4 7.5,6.5 8,9.5 5,8 2,9.5 2.5,6.5 0,4 3.5,3.5"
                    fill="#1f2937" stroke="#d4a843" strokeWidth="0.8" />
                </svg>
              ))}
            </div>
          )}

          {/* Card art / name area */}
          <div className="px-1 pt-0.5 flex-1 min-h-0 flex flex-col">
            {imageUrl && size !== 'sm' ? (
              <div className="flex-1 min-h-0 relative overflow-hidden rounded-sm">
                <img
                  src={imageUrl}
                  alt={card.name}
                  className="w-full h-full object-cover"
                  loading="lazy"
                />
                {/* Name overlay at bottom of image */}
                <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/80 to-transparent px-1 py-0.5">
                  <div className={`font-bold leading-tight truncate ${size === 'lg' ? 'text-[9px]' : 'text-[7px]'} text-white`}>
                    {card.name}
                  </div>
                </div>
              </div>
            ) : (
              <>
                <div className={`font-bold leading-tight truncate ${size === 'sm' ? 'text-[6px]' : 'text-[8px]'} ${textColor}`}>
                  {card.name}
                </div>
                {size === 'lg' && card.text && (
                  <div className={`text-[7px] ${synchro ? 'text-gray-600' : 'text-gray-400'} leading-tight mt-0.5 line-clamp-3`}>
                    {card.text}
                  </div>
                )}
              </>
            )}
          </div>

          {/* ATK/DEF bar */}
          {card.atk !== undefined && card.atk !== null && (
            <div className="flex items-center justify-between px-1.5 py-0.5 bg-gradient-to-r from-black/50 via-black/40 to-black/50 mt-auto">
              <span className={`font-bold ${size === 'sm' ? 'text-[6px]' : 'text-[9px]'} text-red-400`}>
                {card.atk}
              </span>
              <span className={`${size === 'sm' ? 'text-[5px]' : 'text-[7px]'} text-gray-500`}>/</span>
              {card.def_val !== undefined && card.def_val !== null && (
                <span className={`font-bold ${size === 'sm' ? 'text-[6px]' : 'text-[9px]'} text-blue-400`}>
                  {card.def_val}
                </span>
              )}
              {card.link_rating !== undefined && card.link_rating !== null && (
                <span className={`font-bold ${size === 'sm' ? 'text-[6px]' : 'text-[9px]'} text-blue-400`}>
                  L{card.link_rating}
                </span>
              )}
            </div>
          )}

          {/* Spell/Trap type badge */}
          {!card.types?.includes('YGO_MONSTER') && size !== 'sm' && (
            <div className="px-1 pb-0.5">
              <span className={`text-[7px] ${synchro ? 'text-gray-500' : 'text-gray-400'} uppercase tracking-wide`}>
                {card.ygo_spell_type || card.ygo_trap_type || ''}
              </span>
            </div>
          )}

          {/* Tuner badge */}
          {card.is_tuner && size !== 'sm' && (
            <div className="absolute bottom-0.5 left-0.5 bg-green-700 text-white text-[6px] font-bold rounded w-3 h-3 flex items-center justify-center">
              T
            </div>
          )}

          {/* Overlay units (Xyz) */}
          {card.overlay_units !== undefined && card.overlay_units > 0 && (
            <div className="absolute bottom-0.5 left-0.5 bg-purple-600 text-white text-[7px] font-bold rounded-full w-4 h-4 flex items-center justify-center shadow-md">
              {card.overlay_units}
            </div>
          )}
        </>
      )}
    </>
  );

  const selectedRing = selected
    ? 'ring-2 ring-ygo-gold ring-offset-1 ring-offset-ygo-dark shadow-[0_0_12px_rgba(212,168,67,0.5)]'
    : '';
  const targetRing = isTarget
    ? 'ring-2 ring-red-500 ring-offset-1 ring-offset-ygo-dark animate-pulse'
    : '';

  if (!animate) {
    return (
      <div
        onClick={onClick}
        onMouseEnter={onHoverStart}
        onMouseLeave={onHoverEnd}
        style={sizeStyles[size]}
        className={`
          ${isDef ? 'rotate-90' : ''}
          ${frameBorder}
          ${frameBg}
          border-2 rounded-md cursor-pointer transition-all duration-150
          ${selectedRing}
          ${targetRing}
          ${onClick ? 'hover:-translate-y-1 hover:scale-105' : ''}
          flex flex-col overflow-hidden relative
          ${className}
        `}
      >
        {cardContent}
      </div>
    );
  }

  return (
    <motion.div
      onClick={onClick}
      onHoverStart={onHoverStart}
      onHoverEnd={onHoverEnd}
      variants={cardEnter}
      initial="initial"
      animate="animate"
      exit="exit"
      whileHover={onClick ? { y: -8, scale: 1.05, zIndex: 20 } : undefined}
      style={sizeStyles[size]}
      className={`
        ${isDef ? 'rotate-90' : ''}
        ${frameBorder}
        ${frameBg}
        border-2 rounded-md cursor-pointer transition-shadow duration-150
        ${selectedRing}
        ${targetRing}
        flex flex-col overflow-hidden relative
        ${className}
      `}
    >
      {cardContent}
    </motion.div>
  );
}
