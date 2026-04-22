/**
 * PKMCard - Pokemon TCG card component.
 *
 * Renders a Pokemon card with official card art from pokemontcg.io when available.
 * Falls back to text-based rendering when no image_url is present.
 *
 * Overlays runtime game state on top of card images:
 * - Damage counter badge
 * - HP bar showing current HP
 * - Status condition indicators
 * - Attached energy dots
 * - Selection/targeting rings
 */

import { memo } from 'react';
import { motion } from 'framer-motion';
import { cardEnter, typeToBorderClass } from '../../utils/pkmAnimations';
import type { CardData } from '../../types';

// Pokemon type colors
const TYPE_COLORS: Record<string, string> = {
  G: 'bg-green-600',     // Grass
  R: 'bg-red-600',       // Fire
  W: 'bg-blue-500',      // Water
  L: 'bg-yellow-400',    // Lightning
  P: 'bg-purple-500',    // Psychic
  F: 'bg-orange-700',    // Fighting
  D: 'bg-gray-800',      // Darkness
  M: 'bg-gray-400',      // Metal
  N: 'bg-amber-600',     // Dragon
  C: 'bg-gray-300',      // Colorless
};

const TYPE_NAMES: Record<string, string> = {
  G: 'Grass', R: 'Fire', W: 'Water', L: 'Lightning',
  P: 'Psychic', F: 'Fighting', D: 'Darkness', M: 'Metal',
  N: 'Dragon', C: 'Colorless',
};

const STATUS_ICONS: Record<string, { label: string; color: string }> = {
  poisoned: { label: 'PSN', color: 'bg-purple-600' },
  burned: { label: 'BRN', color: 'bg-orange-600' },
  asleep: { label: 'SLP', color: 'bg-blue-800' },
  confused: { label: 'CNF', color: 'bg-yellow-600' },
  paralyzed: { label: 'PAR', color: 'bg-yellow-400' },
};

interface DragPropsType {
  draggable: boolean;
  onDragStart: (e: React.DragEvent) => void;
  onDragEnd: (e: React.DragEvent) => void;
}

interface DropPropsType {
  onDragOver: (e: React.DragEvent) => void;
  onDragEnter: (e: React.DragEvent) => void;
  onDragLeave: (e: React.DragEvent) => void;
  onDrop: (e: React.DragEvent) => void;
}

interface PKMCardProps {
  card: CardData;
  isActive?: boolean;
  isSelected?: boolean;
  isValidTarget?: boolean;
  isOpponent?: boolean;
  isBeingAttacked?: boolean;
  compact?: boolean;
  onClick?: () => void;
  onHover?: (card: CardData | null) => void;
  dragProps?: DragPropsType;
  isBeingDragged?: boolean;
  dropProps?: DropPropsType;
  isDropTarget?: boolean;
  isDropHovered?: boolean;
}

export const PKMCard = memo(function PKMCard({
  card,
  isActive = false,
  isSelected = false,
  isValidTarget = false,
  isOpponent = false,
  isBeingAttacked = false,
  compact = false,
  onClick,
  onHover,
  dragProps,
  isBeingDragged = false,
  dropProps,
  isDropTarget = false,
  isDropHovered = false,
}: PKMCardProps) {
  // Build drag/drop visual classes
  const dragDropClasses = [
    isBeingDragged ? 'opacity-50 scale-95' : '',
    isDropTarget && !isDropHovered ? 'ring-2 ring-amber-400 ring-opacity-60' : '',
    isDropHovered ? 'ring-2 ring-amber-300 bg-amber-900/20' : '',
  ].filter(Boolean).join(' ');
  const isEx = card.is_ex;
  const typeCode = card.pokemon_type || 'C';
  const typeColor = TYPE_COLORS[typeCode] || TYPE_COLORS.C;
  const hp = card.hp || 0;
  const damageCounters = card.damage_counters || 0;
  const remainingHp = Math.max(0, hp - damageCounters * 10);
  const hpPercent = hp > 0 ? (remainingHp / hp) * 100 : 100;
  const statusConditions = card.status_conditions || [];
  const attachedEnergy = card.attached_energy || [];
  const imageUrl = card.image_url;

  // Accessibility props for interactive card divs
  const a11y = onClick ? {
    role: 'button' as const,
    tabIndex: 0,
    'aria-label': card.name,
    onKeyDown: (e: React.KeyboardEvent) => {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onClick(); }
    },
  } : {};

  // Determine if this is an energy card
  const isEnergy = card.types?.includes('ENERGY');
  const isTrainer = card.types?.includes('ITEM') || card.types?.includes('SUPPORTER') || card.types?.includes('STADIUM') || card.types?.includes('POKEMON_TOOL');
  const isPokemon = card.types?.includes('POKEMON');

  // =========================================================================
  // ENERGY CARD
  // =========================================================================
  if (isEnergy) {
    if (imageUrl) {
      return (
        <div
          {...dragProps}
          {...dropProps}
          {...a11y}
          onClick={onClick}
          onMouseEnter={() => onHover?.(card)}
          onMouseLeave={() => onHover?.(null)}
          className={`
            w-16 h-[5.5rem] rounded-lg border-2 cursor-pointer overflow-hidden
            transition-all duration-150 border-gray-500
            ${isSelected ? 'ring-2 ring-yellow-400 scale-105' : ''}
            ${dragDropClasses}
            hover:scale-105
          `}
        >
          <img
            src={imageUrl}
            alt={card.name}
            className="w-full h-full object-cover"
            draggable={false}
          />
        </div>
      );
    }
    return (
      <div
        {...dragProps}
        {...dropProps}
        {...a11y}
        onClick={onClick}
        onMouseEnter={() => onHover?.(card)}
        onMouseLeave={() => onHover?.(null)}
        className={`
          w-16 h-[5.5rem] rounded-lg border-2 flex flex-col items-center justify-center cursor-pointer
          transition-all duration-150
          ${typeColor} bg-opacity-80 border-gray-500
          ${isSelected ? 'ring-2 ring-yellow-400 scale-105' : ''}
          ${dragDropClasses}
          hover:scale-105
        `}
      >
        <div className="text-white text-[10px] font-bold text-center leading-tight px-1">
          {card.name.replace(' Energy', '')}
        </div>
        <div className={`w-6 h-6 rounded-full ${typeColor} border border-white/50 mt-1`} />
      </div>
    );
  }

  // =========================================================================
  // TRAINER CARD
  // =========================================================================
  if (isTrainer && !isPokemon) {
    if (imageUrl) {
      return (
        <div
          {...dragProps}
          {...dropProps}
          {...a11y}
          onClick={onClick}
          onMouseEnter={() => onHover?.(card)}
          onMouseLeave={() => onHover?.(null)}
          className={`
            relative w-20 h-28 rounded-lg border-2 cursor-pointer overflow-hidden
            transition-all duration-150 border-gray-500
            ${isSelected ? 'ring-2 ring-yellow-400 scale-105 z-10' : ''}
            ${dragDropClasses}
            hover:scale-105
          `}
        >
          <img
            src={imageUrl}
            alt={card.name}
            className="w-full h-full object-cover"
            draggable={false}
          />
        </div>
      );
    }
    return (
      <div
        {...dragProps}
        {...dropProps}
        {...a11y}
        onClick={onClick}
        onMouseEnter={() => onHover?.(card)}
        onMouseLeave={() => onHover?.(null)}
        className={`
          w-20 h-28 rounded-lg border-2 flex flex-col cursor-pointer
          transition-all duration-150
          bg-gradient-to-b from-gray-600 to-gray-700 border-gray-500
          ${isSelected ? 'ring-2 ring-yellow-400 scale-105' : ''}
          ${dragDropClasses}
          hover:scale-105
        `}
      >
        <div className="text-[9px] text-gray-300 uppercase text-center mt-1">
          {card.types?.find(t => ['ITEM', 'SUPPORTER', 'STADIUM', 'POKEMON_TOOL'].includes(t)) || 'Trainer'}
        </div>
        <div className="text-white text-[10px] font-bold text-center px-1 mt-1 leading-tight">
          {card.name}
        </div>
        <div className="text-gray-300 text-[7px] text-center px-1 mt-1 leading-tight flex-1 overflow-hidden">
          {card.text}
        </div>
      </div>
    );
  }

  // =========================================================================
  // POKEMON CARD - COMPACT (bench view)
  // =========================================================================
  if (compact) {
    if (imageUrl) {
      return (
        <div
          data-card-id={card.id}
          {...dragProps}
          {...dropProps}
          {...a11y}
          onClick={onClick}
          onMouseEnter={() => onHover?.(card)}
          onMouseLeave={() => onHover?.(null)}
          className={`
            relative w-20 h-28 rounded-lg border-2 cursor-pointer overflow-hidden
            transition-all duration-150
            ${isEx ? 'border-indigo-400' : 'border-gray-600'}
            ${isSelected ? 'ring-2 ring-yellow-400' : ''}
            ${isValidTarget ? 'ring-2 ring-red-400 animate-pulse' : ''}
            ${dragDropClasses}
          `}
        >
          <img
            src={imageUrl}
            alt={card.name}
            className="w-full h-full object-cover"
            draggable={false}
          />
          {/* Overlay: Name + HP badge at bottom */}
          <div className="absolute bottom-0 left-0 right-0 bg-black/70 px-1 py-0.5">
            <div className="text-white text-[7px] font-bold truncate">{card.name}</div>
            <div className="flex items-center justify-between">
              <span className={`text-[7px] font-bold ${hpPercent < 30 ? 'text-red-400' : 'text-green-400'}`}>
                {remainingHp}/{hp}
              </span>
              {/* Attached energy dots */}
              {attachedEnergy.length > 0 && (
                <div className="flex gap-0.5">
                  {attachedEnergy.map((e, i) => (
                    <div key={i} className={`w-2 h-2 rounded-full ${TYPE_COLORS[e] || TYPE_COLORS.C} border border-white/40`} />
                  ))}
                </div>
              )}
            </div>
          </div>
          {/* HP bar */}
          {hp > 0 && (
            <div className="absolute top-0 left-0 right-0 h-1 bg-black/40">
              <div
                className={`h-full transition-all ${
                  hpPercent > 50 ? 'bg-green-500' : hpPercent > 25 ? 'bg-yellow-500' : 'bg-red-500'
                }`}
                style={{ width: `${hpPercent}%` }}
              />
            </div>
          )}
          {/* Damage counter badge */}
          {damageCounters > 0 && (
            <div className="absolute top-1 right-1 bg-red-600 text-white text-[7px] font-bold rounded-full w-4 h-4 flex items-center justify-center border border-red-400">
              {damageCounters}
            </div>
          )}
          {/* Status conditions */}
          {statusConditions.length > 0 && (
            <div className="absolute top-1 left-1 flex flex-col gap-0.5">
              {statusConditions.map((s) => {
                const info = STATUS_ICONS[s];
                if (!info) return null;
                return (
                  <div key={s} className={`${info.color} text-white text-[5px] font-bold px-0.5 rounded`}>
                    {info.label}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      );
    }
    // Fallback compact (no image)
    return (
      <div
        data-card-id={card.id}
        {...dragProps}
        {...dropProps}
        {...a11y}
        onClick={onClick}
        onMouseEnter={() => onHover?.(card)}
        onMouseLeave={() => onHover?.(null)}
        className={`
          w-20 h-12 rounded border-2 flex items-center gap-1 px-1 cursor-pointer
          transition-all duration-150
          ${isEx ? 'bg-gradient-to-r from-gray-800 to-indigo-900 border-indigo-400' : 'bg-gray-800 border-gray-600'}
          ${isSelected ? 'ring-2 ring-yellow-400' : ''}
          ${isValidTarget ? 'ring-2 ring-red-400 animate-pulse' : ''}
          ${dragDropClasses}
        `}
      >
        <div className={`w-3 h-3 rounded-full ${typeColor} flex-shrink-0`} />
        <div className="flex-1 min-w-0">
          <div className="text-white text-[8px] font-bold truncate">{card.name}</div>
          <div className="text-[7px]">
            <span className={hpPercent < 30 ? 'text-red-400' : 'text-green-400'}>
              {remainingHp}
            </span>
            <span className="text-gray-500">/{hp}</span>
          </div>
        </div>
      </div>
    );
  }

  // =========================================================================
  // POKEMON CARD - FULL SIZE (active or hand)
  // =========================================================================
  const typeBorder = typeToBorderClass(typeCode);

  if (imageUrl) {
    const motionEl = (
      <motion.div
        data-card-id={card.id}
        {...dropProps}
        {...a11y}
        onClick={onClick}
        onMouseEnter={() => onHover?.(card)}
        onMouseLeave={() => onHover?.(null)}
        variants={cardEnter}
        initial="initial"
        animate={isBeingAttacked ? { x: [0, -6, 6, -4, 4, 0], transition: { duration: 0.5 } } : "animate"}
        className={`
          relative rounded-lg border-2 cursor-pointer overflow-hidden
          transition-all duration-150
          ${isActive ? 'w-40 h-56' : 'w-24 h-36'}
          ${isEx ? 'border-indigo-400' : typeBorder}
          ${isSelected ? 'ring-2 ring-yellow-400 scale-105 z-10' : ''}
          ${isValidTarget ? 'ring-2 ring-red-400 animate-pulse' : ''}
          ${!isOpponent ? 'hover:scale-105 hover:z-10' : ''}
          ${dragDropClasses}
        `}
      >
        <img
          src={imageUrl}
          alt={card.name}
          className="w-full h-full object-cover"
          draggable={false}
        />

        {/* HP bar overlay at top */}
        {hp > 0 && (
          <div className="absolute top-0 left-0 right-0 h-1.5 bg-black/40">
            <div
              className={`h-full transition-all ${
                hpPercent > 50 ? 'bg-green-500' : hpPercent > 25 ? 'bg-yellow-500' : 'bg-red-500'
              }`}
              style={{ width: `${hpPercent}%` }}
            />
          </div>
        )}

        {/* Damage counter badge */}
        {damageCounters > 0 && (
          <div className={`absolute top-1 right-1 bg-red-600 text-white font-bold rounded-full flex items-center justify-center border border-red-400 shadow-lg ${
            isActive ? 'text-[10px] w-6 h-6' : 'text-[8px] w-5 h-5'
          }`}>
            {damageCounters}
          </div>
        )}

        {/* Attached energy overlay (bottom-right) */}
        {attachedEnergy.length > 0 && (
          <div className={`absolute ${isActive ? 'bottom-8 right-1' : 'bottom-1 right-1'} flex flex-wrap gap-0.5 max-w-[50%] justify-end`}>
            {attachedEnergy.map((e, i) => (
              <div key={i} className={`${isActive ? 'w-3.5 h-3.5' : 'w-2.5 h-2.5'} rounded-full ${TYPE_COLORS[e] || TYPE_COLORS.C} border border-white/50 shadow`} />
            ))}
          </div>
        )}

        {/* Status conditions (bottom-left) */}
        {statusConditions.length > 0 && (
          <div className={`absolute ${isActive ? 'bottom-8 left-1' : 'bottom-1 left-1'} flex flex-col gap-0.5`}>
            {statusConditions.map((s) => {
              const info = STATUS_ICONS[s];
              if (!info) return null;
              return (
                <div key={s} className={`${info.color} text-white text-[7px] font-bold px-1 rounded shadow`}>
                  {info.label}
                </div>
              );
            })}
          </div>
        )}

        {/* Bottom bar with current HP for active Pokemon */}
        {isActive && (
          <div className="absolute bottom-0 left-0 right-0 bg-black/60 px-2 py-1">
            <div className="flex items-center justify-between">
              <span className={`text-[10px] font-bold ${hpPercent < 30 ? 'text-red-400' : 'text-green-400'}`}>
                HP {remainingHp}/{hp}
              </span>
              {card.ability_name && (
                <div className="bg-red-700 text-white text-[7px] font-bold px-1 rounded" title={card.ability_text || ''}>
                  {card.ability_name}
                </div>
              )}
            </div>
          </div>
        )}
      </motion.div>
    );

    // Wrap in a plain div for HTML5 drag handlers (framer-motion overrides onDragStart/onDragEnd types)
    if (dragProps) {
      return (
        <div
          draggable={dragProps.draggable}
          onDragStart={dragProps.onDragStart}
          onDragEnd={dragProps.onDragEnd}
          className="relative"
        >
          {motionEl}
        </div>
      );
    }

    return motionEl;
  }

  // =========================================================================
  // POKEMON CARD - FALLBACK (no image, text-based)
  // =========================================================================
  return (
    <div
      data-card-id={card.id}
      {...dragProps}
      {...dropProps}
      {...a11y}
      onClick={onClick}
      onMouseEnter={() => onHover?.(card)}
      onMouseLeave={() => onHover?.(null)}
      className={`
        relative rounded-lg border-2 cursor-pointer
        transition-all duration-150
        ${isActive ? 'w-32 h-44' : 'w-24 h-36'}
        ${isEx
          ? 'bg-gradient-to-b from-gray-900 via-indigo-900 to-gray-900 border-indigo-400'
          : 'bg-gradient-to-b from-gray-800 to-gray-900 border-gray-600'
        }
        ${isSelected ? 'ring-2 ring-yellow-400 scale-105 z-10' : ''}
        ${isValidTarget ? 'ring-2 ring-red-400 animate-pulse' : ''}
        ${!isOpponent ? 'hover:scale-105 hover:z-10' : ''}
        ${dragDropClasses}
      `}
    >
      {/* Header: Type + Name + HP */}
      <div className="flex items-center justify-between px-1.5 pt-1">
        <div className="flex items-center gap-1">
          <div className={`w-3 h-3 rounded-full ${typeColor}`} />
          <span className="text-[8px] text-gray-400">{card.evolution_stage || 'Basic'}</span>
        </div>
        <div className="text-[9px] font-bold text-white">
          {hp} <span className="text-red-400">HP</span>
        </div>
      </div>

      {/* Name */}
      <div className={`text-center font-bold leading-tight px-1 ${isActive ? 'text-xs' : 'text-[10px]'}`}>
        <span className="text-white">{card.name}</span>
        {isEx && <span className="text-indigo-300 text-[8px] ml-0.5">ex</span>}
      </div>

      {/* HP Bar */}
      {hp > 0 && (
        <div className="mx-1.5 mt-1 h-1 bg-gray-700 rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full transition-all ${
              hpPercent > 50 ? 'bg-green-500' : hpPercent > 25 ? 'bg-yellow-500' : 'bg-red-500'
            }`}
            style={{ width: `${hpPercent}%` }}
          />
        </div>
      )}

      {/* Damage counters */}
      {damageCounters > 0 && (
        <div className="absolute top-0 right-0 -translate-y-1/4 translate-x-1/4 bg-red-600 text-white text-[8px] font-bold rounded-full w-5 h-5 flex items-center justify-center border border-red-400">
          {damageCounters}
        </div>
      )}

      {/* Attacks */}
      {isActive && card.attacks && card.attacks.length > 0 && (
        <div className="mt-1 px-1.5 space-y-0.5">
          {card.attacks.slice(0, 2).map((atk, i: number) => (
            <div key={i} className="flex items-center justify-between text-[7px]">
              <div className="flex items-center gap-0.5">
                {/* Energy cost dots */}
                {atk.cost && atk.cost.flatMap((c, j: number) =>
                  Array.from({ length: c.count || 1 }, (_, k) => (
                    <div key={`${j}-${k}`} className={`w-2 h-2 rounded-full ${TYPE_COLORS[c.type] || TYPE_COLORS.C}`} />
                  ))
                )}
                <span className="text-gray-300 ml-0.5">{atk.name}</span>
              </div>
              {atk.damage > 0 && (
                <span className="text-white font-bold">{atk.damage}</span>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Weakness / Resistance / Retreat */}
      {isActive && (
        <div className="flex items-center justify-center gap-2 mt-1 text-[6px] text-gray-400">
          {card.weakness_type && (
            <span>W: <span className={`${TYPE_COLORS[card.weakness_type] ? 'text-red-300' : ''}`}>{TYPE_NAMES[card.weakness_type] || '?'}</span></span>
          )}
          {card.resistance_type && (
            <span>R: <span className="text-green-300">{TYPE_NAMES[card.resistance_type] || '?'}</span></span>
          )}
          {(card.retreat_cost || 0) > 0 && (
            <span>RC: {card.retreat_cost}</span>
          )}
        </div>
      )}

      {/* Attached energy */}
      {attachedEnergy.length > 0 && (
        <div className="flex items-center justify-center gap-0.5 mt-1">
          {attachedEnergy.map((e, i) => (
            <div key={i} className={`w-2.5 h-2.5 rounded-full ${TYPE_COLORS[e] || TYPE_COLORS.C} border border-white/30`} />
          ))}
        </div>
      )}

      {/* Status conditions */}
      {statusConditions.length > 0 && (
        <div className="absolute bottom-0 left-1/2 -translate-x-1/2 translate-y-1/2 flex gap-0.5">
          {statusConditions.map((s) => {
            const info = STATUS_ICONS[s];
            if (!info) return null;
            return (
              <div key={s} className={`${info.color} text-white text-[6px] font-bold px-1 rounded`}>
                {info.label}
              </div>
            );
          })}
        </div>
      )}

      {/* Ability indicator */}
      {card.ability_name && (
        <div className="absolute top-1 left-1">
          <div className="bg-red-700 text-white text-[5px] font-bold px-0.5 rounded" title={card.ability_text || ''}>
            A
          </div>
        </div>
      )}
    </div>
  );
});
