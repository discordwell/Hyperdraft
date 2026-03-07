/**
 * YGOCardDetailPanel
 *
 * Fixed-position detail panel showing enlarged card info on hover.
 * Dark + Gold themed.
 */

import { AnimatePresence, motion } from 'framer-motion';
import { cardEnter } from '../../utils/ygoAnimations';
import { YGO_CARD_ART } from '../../data/ygoCardArt';
import type { CardData } from '../../types';

const ATTRIBUTE_COLORS: Record<string, string> = {
  DARK: 'bg-purple-700 text-white',
  LIGHT: 'bg-yellow-400 text-gray-900',
  FIRE: 'bg-red-600 text-white',
  WATER: 'bg-blue-600 text-white',
  EARTH: 'bg-amber-700 text-white',
  WIND: 'bg-green-600 text-white',
  DIVINE: 'bg-yellow-600 text-white',
};

const MONSTER_TYPE_BADGE: Record<string, string> = {
  Normal: 'bg-ygo-gold/80 text-white',
  Effect: 'bg-orange-600 text-white',
  Fusion: 'bg-purple-600 text-white',
  Synchro: 'bg-gray-300 text-gray-900',
  Xyz: 'bg-gray-700 text-white',
  Link: 'bg-blue-600 text-white',
  Ritual: 'bg-blue-800 text-white',
};

interface YGOCardDetailPanelProps {
  card: CardData | null;
}

export default function YGOCardDetailPanel({ card }: YGOCardDetailPanelProps) {
  const imageUrl = card ? (card.image_url || YGO_CARD_ART[card.name]) : null;

  return (
    <AnimatePresence mode="wait">
      {card && (
        <motion.div
          key={card.id}
          variants={cardEnter}
          initial="initial"
          animate="animate"
          exit="exit"
          className="fixed right-8 top-1/2 -translate-y-1/2 z-50 w-[260px] bg-ygo-dark/95 border border-ygo-gold-dim/50 rounded-xl shadow-2xl shadow-black/60 overflow-hidden pointer-events-auto"
        >
          {/* Card image */}
          {imageUrl && (
            <div className="p-3 pb-0">
              <img
                src={imageUrl}
                alt={card.name}
                className="w-full max-h-[200px] object-contain rounded-lg"
              />
            </div>
          )}

          {/* Body */}
          <div className="p-3 space-y-2 text-sm">
            {/* Name + type badges */}
            <div className="flex items-center gap-2 flex-wrap">
              <span className="font-bold text-ygo-gold-bright text-base truncate flex-1">
                {card.name}
              </span>
              {card.attribute && (
                <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${ATTRIBUTE_COLORS[card.attribute] || 'bg-gray-600 text-white'}`}>
                  {card.attribute}
                </span>
              )}
            </div>

            {/* Monster type badge */}
            {card.ygo_monster_type && (
              <div className="flex items-center gap-2">
                <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded ${MONSTER_TYPE_BADGE[card.ygo_monster_type] || 'bg-gray-600 text-white'}`}>
                  {card.ygo_monster_type} Monster
                </span>
                {card.is_tuner && (
                  <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-green-700 text-white">
                    Tuner
                  </span>
                )}
              </div>
            )}

            {/* Spell/Trap type */}
            {card.ygo_spell_type && (
              <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-teal-700 text-white">
                {card.ygo_spell_type} Spell
              </span>
            )}
            {card.ygo_trap_type && (
              <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-pink-700 text-white">
                {card.ygo_trap_type} Trap
              </span>
            )}

            {/* Level / Rank */}
            {(card.level || card.rank) && (
              <div className="flex items-center gap-2 text-xs">
                {card.level && (
                  <div className="flex items-center gap-1">
                    <span className="text-gray-400">{card.rank ? 'Rank' : 'Level'}:</span>
                    <div className="flex gap-0.5">
                      {Array.from({ length: Math.min(card.level, 12) }).map((_, i) => (
                        <svg key={i} viewBox="0 0 10 10" className="w-3 h-3">
                          <polygon
                            points="5,0.5 6.5,3.5 10,4 7.5,6.5 8,9.5 5,8 2,9.5 2.5,6.5 0,4 3.5,3.5"
                            fill={card.rank ? '#1f2937' : '#facc15'}
                            stroke={card.rank ? '#d4a843' : '#a16207'}
                            strokeWidth="0.5"
                          />
                        </svg>
                      ))}
                    </div>
                  </div>
                )}
                {card.rank && !card.level && (
                  <div className="flex items-center gap-1">
                    <span className="text-gray-400">Rank:</span>
                    <div className="flex gap-0.5">
                      {Array.from({ length: Math.min(card.rank, 12) }).map((_, i) => (
                        <svg key={i} viewBox="0 0 10 10" className="w-3 h-3">
                          <polygon
                            points="5,0.5 6.5,3.5 10,4 7.5,6.5 8,9.5 5,8 2,9.5 2.5,6.5 0,4 3.5,3.5"
                            fill="#1f2937" stroke="#d4a843" strokeWidth="0.8"
                          />
                        </svg>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* ATK / DEF */}
            {card.atk !== undefined && card.atk !== null && (
              <div className="flex items-center gap-3 text-sm">
                <div className="flex items-center gap-1">
                  <span className="text-gray-500 text-xs">ATK</span>
                  <span className="font-bold text-red-400">{card.atk}</span>
                </div>
                {card.def_val !== undefined && card.def_val !== null && (
                  <div className="flex items-center gap-1">
                    <span className="text-gray-500 text-xs">DEF</span>
                    <span className="font-bold text-blue-400">{card.def_val}</span>
                  </div>
                )}
                {card.link_rating !== undefined && card.link_rating !== null && (
                  <div className="flex items-center gap-1">
                    <span className="text-gray-500 text-xs">LINK</span>
                    <span className="font-bold text-blue-400">{card.link_rating}</span>
                  </div>
                )}
              </div>
            )}

            {/* Overlay units */}
            {card.overlay_units !== undefined && card.overlay_units > 0 && (
              <div className="text-purple-400 text-xs">
                Overlay Units: {card.overlay_units}
              </div>
            )}

            {/* Card text */}
            {card.text && (
              <p className="text-gray-400 text-xs leading-relaxed border-t border-ygo-gold-dim/20 pt-2">
                {card.text}
              </p>
            )}

            {/* Position */}
            {card.ygo_position && (
              <div className="text-gray-500 text-[10px] uppercase tracking-wide">
                {card.ygo_position.replace(/_/g, ' ')}
              </div>
            )}
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
