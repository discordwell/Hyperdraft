/**
 * PKMCardDetailPanel
 *
 * Fixed-position detail panel for Pokemon TCG cards.
 * Appears on the right side of the game board when hovering or clicking a card.
 * Shows full card stats, attacks, ability, energy, status conditions, etc.
 */

import React from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { cardEnter } from '../../utils/pkmAnimations';
import type { CardData } from '../../types';

// ---------- Type color maps ----------

const TYPE_COLOR_MAP: Record<string, string> = {
  G: 'bg-green-500',
  R: 'bg-red-500',
  W: 'bg-blue-500',
  L: 'bg-yellow-400',
  P: 'bg-purple-500',
  F: 'bg-orange-500',
  D: 'bg-gray-700',
  M: 'bg-gray-400',
  N: 'bg-amber-500',
  C: 'bg-gray-300',
};

const TYPE_NAME_MAP: Record<string, string> = {
  G: 'Grass',
  R: 'Fire',
  W: 'Water',
  L: 'Lightning',
  P: 'Psychic',
  F: 'Fighting',
  D: 'Darkness',
  M: 'Metal',
  N: 'Dragon',
  C: 'Colorless',
};

const TYPE_BADGE_MAP: Record<string, string> = {
  G: 'bg-green-600 text-white',
  R: 'bg-red-600 text-white',
  W: 'bg-blue-600 text-white',
  L: 'bg-yellow-500 text-black',
  P: 'bg-purple-600 text-white',
  F: 'bg-orange-600 text-white',
  D: 'bg-gray-800 text-white',
  M: 'bg-gray-500 text-white',
  N: 'bg-amber-600 text-white',
  C: 'bg-gray-400 text-black',
};

const STATUS_COLOR_MAP: Record<string, string> = {
  poisoned: 'bg-purple-600 text-white',
  burned: 'bg-red-600 text-white',
  asleep: 'bg-blue-800 text-white',
  confused: 'bg-yellow-600 text-black',
  paralyzed: 'bg-yellow-400 text-black',
};

// ---------- Sub-components ----------

/** Small colored circle representing an energy type */
function EnergyCostDot({ type }: { type: string }) {
  const bgClass = TYPE_COLOR_MAP[type] || TYPE_COLOR_MAP.C;
  return (
    <span
      className={`inline-block w-4 h-4 rounded-full ${bgClass} border border-black/30 flex-shrink-0`}
      title={TYPE_NAME_MAP[type] || type}
    />
  );
}

/** Renders the attack cost as a row of energy dots */
function AttackCost({ cost }: { cost: { type: string; count: number }[] }) {
  const dots: React.ReactNode[] = [];
  cost.forEach((entry, i) => {
    for (let j = 0; j < entry.count; j++) {
      dots.push(<EnergyCostDot key={`${i}-${j}`} type={entry.type} />);
    }
  });
  return <span className="flex items-center gap-0.5">{dots}</span>;
}

// ---------- Main component ----------

interface PKMCardDetailPanelProps {
  card: CardData | null;
}

export default function PKMCardDetailPanel({ card }: PKMCardDetailPanelProps) {
  // Group attached energy by type
  const groupedEnergy = React.useMemo(() => {
    if (!card?.attached_energy?.length) return null;
    const grouped: Record<string, number> = {};
    for (const e of card.attached_energy) {
      grouped[e] = (grouped[e] || 0) + 1;
    }
    return grouped;
  }, [card?.attached_energy]);

  const remainingHp = card ? Math.max(0, (card.hp ?? 0) - (card.damage_counters ?? 0) * 10) : 0;
  const hpPercent = card?.hp ? Math.max(0, Math.min(100, (remainingHp / card.hp) * 100)) : 0;

  return (
    <AnimatePresence mode="wait">
      {card && (
        <motion.div
          key={card.id}
          variants={cardEnter}
          initial="initial"
          animate="animate"
          exit="exit"
          className="fixed right-8 top-1/2 -translate-y-1/2 z-50 w-[280px] bg-gray-900/95 border border-gray-700 rounded-xl shadow-2xl overflow-hidden pointer-events-auto"
        >
          {/* Card image */}
          {card.image_url && (
            <div className="p-3 pb-0">
              <img
                src={card.image_url}
                alt={card.name}
                className="w-full max-h-[180px] object-contain rounded-lg"
              />
            </div>
          )}

          {/* Body */}
          <div className="p-3 space-y-2.5 text-sm">
            {/* Name row + type badge + EX badge */}
            <div className="flex items-center gap-2">
              <span className="font-bold text-white text-base truncate flex-1">
                {card.name}
              </span>
              {card.is_ex && (
                <span className="text-[10px] font-bold bg-yellow-500 text-black px-1.5 py-0.5 rounded uppercase tracking-wide flex-shrink-0">
                  EX
                </span>
              )}
              {card.pokemon_type && (
                <span
                  className={`text-[10px] font-semibold px-1.5 py-0.5 rounded flex-shrink-0 ${TYPE_BADGE_MAP[card.pokemon_type] || 'bg-gray-600 text-white'}`}
                >
                  {TYPE_NAME_MAP[card.pokemon_type] || card.pokemon_type}
                </span>
              )}
            </div>

            {/* Evolution stage */}
            {card.evolution_stage && (
              <div className="text-gray-400 text-xs">
                {card.evolution_stage}
              </div>
            )}

            {/* HP bar */}
            {card.hp != null && (
              <div>
                <div className="flex items-center justify-between text-xs mb-1">
                  <span className="text-gray-400">HP</span>
                  <span className="text-white font-semibold">
                    {remainingHp} / {card.hp}
                  </span>
                </div>
                <div className="w-full h-2 bg-gray-800 rounded-full overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all duration-300 ${
                      hpPercent > 50 ? 'bg-green-500' : hpPercent > 25 ? 'bg-yellow-500' : 'bg-red-500'
                    }`}
                    style={{ width: `${hpPercent}%` }}
                  />
                </div>
                {(card.damage_counters ?? 0) > 0 && (
                  <div className="text-red-400 text-xs mt-0.5">
                    {card.damage_counters} damage counter{card.damage_counters !== 1 ? 's' : ''}
                  </div>
                )}
              </div>
            )}

            {/* Attacks */}
            {card.attacks && card.attacks.length > 0 && (
              <div className="space-y-2">
                <div className="text-gray-500 text-[10px] uppercase tracking-wider font-semibold">
                  Attacks
                </div>
                {card.attacks.map((atk, i) => (
                  <div key={i} className="bg-gray-800/60 rounded-lg p-2 space-y-1">
                    <div className="flex items-center gap-2">
                      <AttackCost cost={atk.cost} />
                      <span className="font-semibold text-white flex-1 truncate">
                        {atk.name}
                      </span>
                      {atk.damage > 0 && (
                        <span className="text-yellow-400 font-bold text-base">
                          {atk.damage}
                        </span>
                      )}
                    </div>
                    {atk.text && (
                      <p className="text-gray-400 text-xs leading-relaxed">
                        {atk.text}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            )}

            {/* Ability */}
            {card.ability_name && (
              <div className="bg-red-900/30 border border-red-800/40 rounded-lg p-2">
                <div className="flex items-center gap-1.5 mb-0.5">
                  <span className="text-[10px] font-bold bg-red-700 text-white px-1.5 py-0.5 rounded uppercase">
                    Ability
                  </span>
                  <span className="font-semibold text-red-300 text-xs">
                    {card.ability_name}
                  </span>
                </div>
                {card.ability_text && (
                  <p className="text-gray-400 text-xs leading-relaxed">
                    {card.ability_text}
                  </p>
                )}
              </div>
            )}

            {/* Weakness / Resistance / Retreat */}
            {(card.weakness_type || card.resistance_type || card.retreat_cost != null) && (
              <div className="flex items-center gap-3 text-xs">
                {card.weakness_type && (
                  <div className="flex items-center gap-1">
                    <span className="text-gray-500">Weak:</span>
                    <EnergyCostDot type={card.weakness_type} />
                  </div>
                )}
                {card.resistance_type && (
                  <div className="flex items-center gap-1">
                    <span className="text-gray-500">Resist:</span>
                    <EnergyCostDot type={card.resistance_type} />
                  </div>
                )}
                {card.retreat_cost != null && (
                  <div className="flex items-center gap-1">
                    <span className="text-gray-500">Retreat:</span>
                    <span className="flex gap-0.5">
                      {Array.from({ length: card.retreat_cost }).map((_, i) => (
                        <EnergyCostDot key={i} type="C" />
                      ))}
                      {card.retreat_cost === 0 && (
                        <span className="text-green-400 font-semibold">Free</span>
                      )}
                    </span>
                  </div>
                )}
              </div>
            )}

            {/* Attached energy grouped by type */}
            {groupedEnergy && (
              <div>
                <div className="text-gray-500 text-[10px] uppercase tracking-wider font-semibold mb-1">
                  Attached Energy
                </div>
                <div className="flex items-center gap-2 flex-wrap">
                  {Object.entries(groupedEnergy).map(([type, count]) => (
                    <div key={type} className="flex items-center gap-1">
                      <EnergyCostDot type={type} />
                      <span className="text-gray-300 text-xs">
                        x{count}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Attached tool */}
            {card.attached_tool_name && (
              <div className="flex items-center gap-1.5 text-xs">
                <span className="text-gray-500">Tool:</span>
                <span className="text-blue-300 font-semibold">
                  {card.attached_tool_name}
                </span>
              </div>
            )}

            {/* Status conditions */}
            {card.status_conditions && card.status_conditions.length > 0 && (
              <div className="flex items-center gap-1.5 flex-wrap">
                {card.status_conditions.map((status) => (
                  <span
                    key={status}
                    className={`text-[10px] font-semibold px-1.5 py-0.5 rounded capitalize ${STATUS_COLOR_MAP[status.toLowerCase()] || 'bg-gray-600 text-white'}`}
                  >
                    {status}
                  </span>
                ))}
              </div>
            )}

            {/* Card text fallback (for trainers, etc.) */}
            {card.text && !card.attacks?.length && !card.ability_name && (
              <p className="text-gray-400 text-xs leading-relaxed italic">
                {card.text}
              </p>
            )}

            {/* Prize count for EX cards */}
            {card.prize_count != null && card.prize_count > 1 && (
              <div className="text-yellow-500 text-xs">
                Worth {card.prize_count} prize cards when KO'd
              </div>
            )}
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
