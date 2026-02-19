import React from 'react';
import { CardData } from '../../types';

interface HSHandCardProps {
  card: CardData;
  isPlayable: boolean;
  onClick: () => void;
}

export const HSHandCard: React.FC<HSHandCardProps> = ({ card, isPlayable, onClick }) => {
  // Parse mana cost from "{3}" format
  const parseMana = (manaCost: string | null): number => {
    if (!manaCost) return 0;
    const match = manaCost.match(/\{(\d+)\}/);
    return match ? parseInt(match[1], 10) : 0;
  };

  const manaValue = parseMana(card.mana_cost);
  const isMinion = card.types.includes('MINION') || card.types.includes('CREATURE');
  const isWeapon = card.types.includes('WEAPON');

  // Determine card type display
  let cardTypeLabel = 'SPELL';
  if (isMinion) cardTypeLabel = 'MINION';
  if (isWeapon) cardTypeLabel = 'WEAPON';

  // Truncate long card text
  const truncateText = (text: string, maxLength: number = 60): string => {
    if (text.length <= maxLength) return text;
    return text.substring(0, maxLength) + '...';
  };

  return (
    <div
      onClick={onClick}
      className={`
        relative w-[120px] h-[170px] rounded-lg cursor-pointer
        bg-gradient-to-b from-gray-700 to-gray-800
        border-2 transition-all duration-200
        hover:scale-110 hover:z-10
        ${isPlayable
          ? 'border-game-accent shadow-lg shadow-game-accent/50'
          : 'border-gray-600 opacity-75'
        }
      `}
    >
      {/* Mana Cost Gem */}
      <div className="absolute -top-2 -left-2 w-10 h-10 rounded-full bg-blue-600 border-2 border-blue-400 flex items-center justify-center shadow-md z-10">
        <span className="text-white font-bold text-lg">{manaValue}</span>
      </div>

      {/* Card Type Label */}
      <div className="absolute top-1 right-1 px-2 py-0.5 bg-gray-900/80 rounded text-[10px] font-bold text-gray-300">
        {cardTypeLabel}
      </div>

      {/* Card Name */}
      <div className="absolute top-8 left-0 right-0 px-2 text-center">
        <h3 className="text-white font-bold text-sm leading-tight line-clamp-2">
          {card.name}
        </h3>
      </div>

      {/* Card Art Placeholder */}
      <div className="absolute top-16 left-2 right-2 h-16 bg-gradient-to-br from-gray-600 to-gray-700 rounded border border-gray-500 flex items-center justify-center">
        <div className="text-gray-400 text-xs text-center px-1">
          {card.subtypes.length > 0 ? card.subtypes.join(' ') : 'Card Art'}
        </div>
      </div>

      {/* Card Text */}
      <div className="absolute top-[136px] left-2 right-2 text-center">
        <p className="text-gray-300 text-[9px] leading-tight line-clamp-2">
          {truncateText(card.text)}
        </p>
      </div>

      {/* Attack/Health for Minions */}
      {isMinion && (
        <>
          {/* Attack */}
          <div className="absolute bottom-1 left-1 w-7 h-7 rounded-full bg-yellow-600 border-2 border-yellow-400 flex items-center justify-center shadow-md">
            <span className="text-white font-bold text-sm">{card.power ?? 0}</span>
          </div>

          {/* Health */}
          <div className="absolute bottom-1 right-1 w-7 h-7 rounded-full bg-red-600 border-2 border-red-400 flex items-center justify-center shadow-md">
            <span className="text-white font-bold text-sm">{card.toughness ?? 0}</span>
          </div>
        </>
      )}

      {/* Weapon Attack/Durability */}
      {isWeapon && (
        <>
          <div className="absolute bottom-1 left-1 w-7 h-7 rounded-full bg-orange-600 border-2 border-orange-400 flex items-center justify-center shadow-md">
            <span className="text-white font-bold text-sm">{card.power ?? 0}</span>
          </div>

          <div className="absolute bottom-1 right-1 w-7 h-7 rounded-full bg-gray-600 border-2 border-gray-400 flex items-center justify-center shadow-md">
            <span className="text-white font-bold text-sm">{card.toughness ?? 0}</span>
          </div>
        </>
      )}

      {/* Keywords Display */}
      {card.keywords && card.keywords.length > 0 && (
        <div className="absolute bottom-9 left-1 right-1 flex flex-wrap gap-0.5 justify-center">
          {card.keywords.slice(0, 3).map((keyword, idx) => (
            <span
              key={idx}
              className="px-1 py-0.5 bg-purple-900/80 text-purple-200 text-[8px] font-bold rounded uppercase"
            >
              {keyword}
            </span>
          ))}
        </div>
      )}
    </div>
  );
};
