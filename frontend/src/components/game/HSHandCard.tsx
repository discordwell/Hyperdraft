import React, { useMemo, useState } from 'react';
import { CardData } from '../../types';
import { getHearthstoneArtPaths } from '../../utils/cardArt';

interface HSHandCardProps {
  card: CardData;
  isPlayable: boolean;
  onClick: () => void;
  variant?: string | null;
  showAttune?: boolean;
  canAttune?: boolean;
  onAttune?: () => void;
}

export const HSHandCard: React.FC<HSHandCardProps> = ({
  card,
  isPlayable,
  onClick,
  variant,
  showAttune = false,
  canAttune = false,
  onAttune,
}) => {
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
  const displayText = (card.text || '').replace(/\[AF:\d+\/\d+\/\d+\]\s*/i, '');
  const affinityMatch = card.text?.match(/\[AF:(\d+)\/(\d+)\/(\d+)\]/i);
  const affinity = affinityMatch
    ? {
        azure: Number.parseInt(affinityMatch[1] || '0', 10) || 0,
        ember: Number.parseInt(affinityMatch[2] || '0', 10) || 0,
        verdant: Number.parseInt(affinityMatch[3] || '0', 10) || 0,
      }
    : null;

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

      {showAttune && (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            if (canAttune) {
              onAttune?.();
            }
          }}
          disabled={!canAttune}
          className={`
            absolute top-1 left-8 px-1.5 py-0.5 rounded text-[9px] font-bold uppercase z-20
            ${canAttune
              ? 'bg-emerald-700/90 text-emerald-100 hover:bg-emerald-600'
              : 'bg-gray-700/70 text-gray-400 cursor-not-allowed'
            }
          `}
        >
          Attune
        </button>
      )}

      {/* Card Name */}
      <div className="absolute top-8 left-0 right-0 px-2 text-center">
        <h3 className="text-white font-bold text-sm leading-tight line-clamp-2">
          {card.name}
        </h3>
      </div>

      {affinity && (affinity.azure > 0 || affinity.ember > 0 || affinity.verdant > 0) && (
        <div className="absolute top-[51px] left-1 right-1 flex items-center justify-center gap-1 text-[8px] font-bold">
          {affinity.azure > 0 && <span className="px-1 rounded bg-cyan-900/80 text-cyan-200">A{affinity.azure}</span>}
          {affinity.ember > 0 && <span className="px-1 rounded bg-orange-900/80 text-orange-200">E{affinity.ember}</span>}
          {affinity.verdant > 0 && <span className="px-1 rounded bg-emerald-900/80 text-emerald-200">V{affinity.verdant}</span>}
        </div>
      )}

      {/* Card Art */}
      <div className="absolute top-[62px] left-2 right-2 h-16 bg-gradient-to-br from-gray-600 to-gray-700 rounded border border-gray-500 overflow-hidden">
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
          <div className="w-full h-full flex items-center justify-center">
            <div className="text-gray-300 text-xs text-center px-1">
              {card.subtypes.length > 0 ? card.subtypes.join(' ') : 'Card Art'}
            </div>
          </div>
        )}
      </div>

      {/* Card Text */}
      <div className="absolute top-[136px] left-2 right-2 text-center">
        <p className="text-gray-300 text-[9px] leading-tight line-clamp-2">
          {truncateText(displayText)}
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
