/**
 * HSHeroPortrait - Hero display with HP, armor, weapon, and hero power.
 */

import { memo } from 'react';
import type { PlayerData } from '../../types';
import { useDropTarget } from '../../hooks/useDropTarget';
import type { DragItem } from '../../hooks/useDragDrop';

interface HSHeroPortraitProps {
  player: PlayerData;
  isOpponent: boolean;
  isMyTurn: boolean;
  canUseHeroPower: boolean;
  isValidTarget: boolean;
  onHeroPowerClick?: () => void;
  onHeroClick?: () => void;
  heroDropZoneId?: string;
  onHeroDrop?: (item: DragItem) => void;
}

export const HSHeroPortrait = memo(function HSHeroPortrait({
  player,
  isOpponent,
  isMyTurn,
  canUseHeroPower,
  isValidTarget,
  onHeroPowerClick,
  onHeroClick,
  heroDropZoneId,
  onHeroDrop,
}: HSHeroPortraitProps) {
  const { dropProps, isHovered: isDropHovered } = useDropTarget({
    zoneId: heroDropZoneId || '__disabled__',
    onDrop: (item: DragItem) => {
      if (onHeroDrop) {
        onHeroDrop(item);
      } else if (onHeroClick) {
        onHeroClick();
      }
    },
    disabled: !heroDropZoneId,
  });

  const hpPercent = Math.max(0, (player.life / (player.max_life || 30)) * 100);

  // Accessibility props — only applied when the portrait is actually clickable
  const heroA11y = onHeroClick ? {
    role: 'button' as const,
    'aria-label': `${player.name} hero portrait`,
    tabIndex: 0,
    onKeyDown: (e: React.KeyboardEvent) => {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onHeroClick(); }
    },
  } : {};

  return (
    <div className="flex items-center gap-3">
      {/* Weapon (if equipped) */}
      {(player.weapon_attack ?? 0) > 0 && (
        <div className="w-12 h-14 rounded-lg bg-gray-700 border-2 border-orange-500 flex flex-col items-center justify-center">
          <span className="text-orange-300 font-bold text-sm">{player.weapon_attack}</span>
          <div className="w-4 h-px bg-gray-500" />
          <span className="text-gray-400 font-bold text-xs">{player.weapon_durability}</span>
        </div>
      )}

      {/* Hero portrait */}
      <div
        onClick={onHeroClick}
        {...heroA11y}
        {...(heroDropZoneId ? dropProps : {})}
        className={`
          relative w-16 h-16 rounded-full
          bg-gradient-to-b from-gray-600 to-gray-800
          border-2 flex items-center justify-center
          ${isValidTarget ? 'border-red-500 ring-[3px] ring-red-500 ring-offset-1 ring-offset-gray-900 animate-pulse cursor-crosshair' : isDropHovered ? 'border-red-400 ring-2 ring-red-400 animate-pulse cursor-pointer' : 'border-gray-500'}
          ${isDropHovered ? 'shadow-lg shadow-red-500/50' : ''}
          ${isOpponent ? '' : 'cursor-default'}
        `}
      >
        {/* HP text */}
        <span className={`font-bold text-lg ${
          player.life <= 10 ? 'text-red-400' :
          player.life <= 20 ? 'text-yellow-400' :
          'text-white'
        }`}>
          {player.life}
        </span>

        {/* HP bar background */}
        <div className="absolute bottom-0 left-0 right-0 h-1.5 bg-gray-900 rounded-b-full overflow-hidden">
          <div
            className={`h-full transition-all duration-300 ${
              hpPercent > 50 ? 'bg-green-500' :
              hpPercent > 25 ? 'bg-yellow-500' :
              'bg-red-500'
            }`}
            style={{ width: `${hpPercent}%` }}
          />
        </div>

        {/* Armor badge */}
        {(player.armor ?? 0) > 0 && (
          <div className="absolute -top-1 -right-1 w-6 h-6 rounded-full bg-gray-500 border border-gray-300 flex items-center justify-center">
            <span className="text-white font-bold text-[10px]">{player.armor}</span>
          </div>
        )}
      </div>

      {/* Player name + stats */}
      <div className="flex flex-col">
        <span className="text-white text-sm font-semibold">{player.name}</span>
        <div className="flex items-center gap-2 text-xs text-gray-400">
          <span>Deck: {player.library_size}</span>
          {isOpponent && <span>Hand: {player.hand_size}</span>}
        </div>
      </div>

      {/* Hero Power button (only for own hero, not opponent) */}
      {!isOpponent && player.hero_power_name && (
        <button
          onClick={onHeroPowerClick}
          disabled={!canUseHeroPower || !isMyTurn}
          className={`
            ml-auto w-14 h-14 rounded-full
            flex flex-col items-center justify-center
            transition-all text-center
            ${canUseHeroPower && isMyTurn
              ? 'bg-purple-700 border-2 border-purple-400 hover:bg-purple-600 cursor-pointer'
              : 'bg-gray-700 border-2 border-gray-600 opacity-50 cursor-not-allowed'
            }
            ${player.hero_power_used ? 'opacity-40' : ''}
          `}
          title={`${player.hero_power_name}: ${player.hero_power_text || ''} (Cost: ${player.hero_power_cost || 2})`}
        >
          <span className="text-[9px] text-white font-bold leading-tight">{player.hero_power_name}</span>
          <span className="text-[10px] text-blue-300 font-bold">{player.hero_power_cost || 2}</span>
        </button>
      )}
    </div>
  );
});
