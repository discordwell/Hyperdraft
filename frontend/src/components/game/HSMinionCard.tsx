/**
 * HSMinionCard - A minion on the Hearthstone battlefield.
 *
 * Shows attack/health, keywords (taunt border, divine shield glow),
 * summoning sickness indicator, can-attack highlight.
 */

import type { CardData } from '../../types';
import { getHearthstoneArtPaths } from '../../utils/cardArt';
import { useMemo, useState } from 'react';

interface HSMinionCardProps {
  card: CardData;
  canAttack: boolean;
  isSelected: boolean;
  isValidTarget: boolean;
  onClick: () => void;
  variant?: string | null;
}

export function HSMinionCard({
  card,
  canAttack,
  isSelected,
  isValidTarget,
  onClick,
  variant,
}: HSMinionCardProps) {
  const hasTaunt = card.keywords?.includes('taunt');
  const hasDivineShield = card.divine_shield;
  const isFrozen = card.frozen;
  const isStealth = card.stealth;

  // Compute effective health (toughness - damage)
  const maxHealth = card.toughness ?? 0;
  const currentHealth = maxHealth - (card.damage || 0);
  const isDamaged = currentHealth < maxHealth;
  const artPaths = useMemo(() => getHearthstoneArtPaths(card.name, variant), [card.name, variant]);
  const [artIndex, setArtIndex] = useState(0);
  const [artLoaded, setArtLoaded] = useState(false);
  const [artFailed, setArtFailed] = useState(false);

  const handleArtError = () => {
    if (artIndex < artPaths.length - 1) {
      setArtIndex((prev) => prev + 1);
      return;
    }
    setArtFailed(true);
  };

  return (
    <div
      onClick={onClick}
      className={`
        relative w-20 h-24 rounded-lg cursor-pointer
        flex flex-col items-center justify-center
        transition-all duration-150
        ${hasTaunt ? 'border-[3px] border-yellow-500' : 'border-2 border-gray-600'}
        ${hasDivineShield ? 'ring-2 ring-yellow-300 ring-opacity-75' : ''}
        ${canAttack ? 'bg-gradient-to-b from-green-900/60 to-gray-800 hover:from-green-800/80' : 'bg-gradient-to-b from-gray-700 to-gray-800'}
        ${isSelected ? 'ring-2 ring-blue-400 scale-110 z-10' : ''}
        ${isValidTarget ? 'ring-2 ring-red-400 animate-pulse' : ''}
        ${isFrozen ? 'opacity-60 bg-gradient-to-b from-blue-900/60 to-gray-800' : ''}
        ${isStealth ? 'opacity-50' : ''}
        ${card.summoning_sickness && !canAttack ? 'border-dashed' : ''}
      `}
    >
      {/* Card art */}
      <div className="absolute inset-0 rounded-md overflow-hidden">
        {!artFailed && (
          <img
            src={artPaths[artIndex]}
            alt={card.name}
            className={`w-full h-full object-cover ${artLoaded ? 'block' : 'hidden'}`}
            onLoad={() => setArtLoaded(true)}
            onError={handleArtError}
          />
        )}
        {(!artLoaded || artFailed) && (
          <div className="w-full h-full bg-gradient-to-br from-gray-700 to-gray-900" />
        )}
        <div className="absolute inset-0 bg-gradient-to-b from-black/20 via-transparent to-black/55" />
      </div>

      {/* Card name */}
      <div className="relative z-[1] text-[10px] text-white font-semibold text-center leading-tight px-1 line-clamp-2 mt-1">
        {card.name}
      </div>

      {/* Keywords badges */}
      {card.keywords && card.keywords.length > 0 && (
        <div className="relative z-[1] flex gap-0.5 mt-0.5">
          {card.keywords.slice(0, 2).map((kw, i) => (
            <span key={i} className="text-[7px] bg-gray-900/80 text-gray-300 px-1 rounded uppercase font-bold">
              {kw}
            </span>
          ))}
        </div>
      )}

      {/* Frozen indicator */}
      {isFrozen && (
        <div className="relative z-[1] text-[8px] text-blue-300 font-bold mt-0.5">FROZEN</div>
      )}

      {/* Attack stat */}
      <div className="absolute -bottom-1 -left-1 w-7 h-7 rounded-full bg-yellow-600 border-2 border-yellow-400 flex items-center justify-center shadow-md z-10">
        <span className="text-white font-bold text-sm">{card.power ?? 0}</span>
      </div>

      {/* Health stat */}
      <div className={`absolute -bottom-1 -right-1 w-7 h-7 rounded-full border-2 flex items-center justify-center shadow-md z-10 ${
        isDamaged ? 'bg-red-700 border-red-400' : 'bg-red-600 border-red-400'
      }`}>
        <span className={`font-bold text-sm ${isDamaged ? 'text-yellow-300' : 'text-white'}`}>
          {currentHealth}
        </span>
      </div>

      {/* Divine Shield glow effect */}
      {hasDivineShield && (
        <div className="absolute inset-0 rounded-lg bg-yellow-400/10 pointer-events-none" />
      )}
    </div>
  );
}
