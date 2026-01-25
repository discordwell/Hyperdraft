/**
 * Card Component
 *
 * Renders a single MTG-style card with proper frame styling.
 */

import { useMemo, useState } from 'react';
import clsx from 'clsx';
import type { CardData } from '../../types';
import { parseManaSymbols } from '../../types/cards';
import { getPossibleArtPaths } from '../../utils/cardArt';

interface CardProps {
  card: CardData;
  isSelected?: boolean;
  isTargetable?: boolean;
  isHighlighted?: boolean;
  isTapped?: boolean;
  onClick?: () => void;
  size?: 'small' | 'medium' | 'large';
  showDetails?: boolean;
}

// Card art component with fallback handling
interface CardArtProps {
  cardName: string;
  fallbackIcon: string;
  size: 'small' | 'medium' | 'large';
}

function CardArt({ cardName, fallbackIcon, size }: CardArtProps) {
  const [artLoaded, setArtLoaded] = useState(false);
  const [artError, setArtError] = useState(false);
  const [currentPathIndex, setCurrentPathIndex] = useState(0);

  const possiblePaths = useMemo(() => getPossibleArtPaths(cardName), [cardName]);

  const handleImageError = () => {
    // Try the next possible path
    if (currentPathIndex < possiblePaths.length - 1) {
      setCurrentPathIndex((prev) => prev + 1);
    } else {
      // All paths exhausted, show fallback
      setArtError(true);
    }
  };

  const handleImageLoad = () => {
    setArtLoaded(true);
  };

  const iconSize = size === 'small' ? 'text-2xl' : size === 'medium' ? 'text-3xl' : 'text-4xl';

  if (artError) {
    // Show fallback icon
    return (
      <span className={clsx('opacity-60', iconSize)}>
        {fallbackIcon}
      </span>
    );
  }

  return (
    <>
      {/* Show loading placeholder until image loads */}
      {!artLoaded && (
        <span className={clsx('opacity-40 animate-pulse', iconSize)}>
          {fallbackIcon}
        </span>
      )}
      <img
        src={possiblePaths[currentPathIndex]}
        alt={cardName}
        className={clsx(
          'w-full h-full object-cover object-center',
          artLoaded ? 'block' : 'hidden'
        )}
        onError={handleImageError}
        onLoad={handleImageLoad}
      />
    </>
  );
}

// Mana symbol component for consistent rendering
function ManaSymbol({ symbol, size = 'md' }: { symbol: string; size?: 'sm' | 'md' | 'lg' }) {
  const sizeClasses = {
    sm: 'w-4 h-4 text-[9px]',
    md: 'w-5 h-5 text-[10px]',
    lg: 'w-6 h-6 text-xs',
  };

  const colorMap: Record<string, string> = {
    W: 'bg-gradient-to-br from-amber-100 to-amber-200 text-amber-900 border-amber-400',
    U: 'bg-gradient-to-br from-blue-400 to-blue-600 text-white border-blue-700',
    B: 'bg-gradient-to-br from-gray-700 to-gray-900 text-gray-200 border-gray-950',
    R: 'bg-gradient-to-br from-red-500 to-red-700 text-white border-red-800',
    G: 'bg-gradient-to-br from-green-500 to-green-700 text-white border-green-800',
    C: 'bg-gradient-to-br from-gray-300 to-gray-400 text-gray-800 border-gray-500',
  };

  // Check if it's a number (generic mana)
  const isNumber = /^\d+$/.test(symbol);

  return (
    <span
      className={clsx(
        'rounded-full flex items-center justify-center font-bold border shadow-sm',
        sizeClasses[size],
        isNumber
          ? 'bg-gradient-to-br from-gray-200 to-gray-400 text-gray-800 border-gray-500'
          : colorMap[symbol] || 'bg-gray-400 text-white border-gray-500'
      )}
    >
      {symbol}
    </span>
  );
}

export function Card({
  card,
  isSelected = false,
  isTargetable = false,
  isHighlighted = false,
  isTapped,
  onClick,
  size = 'medium',
  showDetails = true,
}: CardProps) {
  const tapped = isTapped ?? card.tapped;
  const manaSymbols = useMemo(() => parseManaSymbols(card.mana_cost), [card.mana_cost]);

  // Determine card color identity for frame styling
  const cardColor = useMemo(() => {
    const types = card.types.map((t) => t.toLowerCase());
    if (types.includes('land')) return 'land';

    const colors: string[] = [];
    if (manaSymbols.includes('W')) colors.push('white');
    if (manaSymbols.includes('U')) colors.push('blue');
    if (manaSymbols.includes('B')) colors.push('black');
    if (manaSymbols.includes('R')) colors.push('red');
    if (manaSymbols.includes('G')) colors.push('green');

    if (colors.length === 0) return 'colorless';
    if (colors.length > 1) return 'gold'; // Multicolor
    return colors[0];
  }, [card.types, manaSymbols]);

  // Size configurations
  const sizeConfig = {
    small: { width: 'w-[110px]', height: 'h-[154px]', textSize: 'text-[9px]', nameSize: 'text-[10px]', manaSize: 'sm' as const },
    medium: { width: 'w-[150px]', height: 'h-[210px]', textSize: 'text-[10px]', nameSize: 'text-[11px]', manaSize: 'md' as const },
    large: { width: 'w-[200px]', height: 'h-[280px]', textSize: 'text-xs', nameSize: 'text-sm', manaSize: 'lg' as const },
  };

  const config = sizeConfig[size];

  // Frame colors based on card color
  const frameStyles: Record<string, { outer: string; inner: string; textBg: string }> = {
    white: {
      outer: 'bg-gradient-to-b from-amber-200 via-amber-100 to-amber-200',
      inner: 'bg-gradient-to-b from-amber-50 to-amber-100',
      textBg: 'bg-amber-50/90',
    },
    blue: {
      outer: 'bg-gradient-to-b from-blue-400 via-blue-300 to-blue-400',
      inner: 'bg-gradient-to-b from-blue-100 to-blue-200',
      textBg: 'bg-blue-50/90',
    },
    black: {
      outer: 'bg-gradient-to-b from-gray-700 via-gray-600 to-gray-700',
      inner: 'bg-gradient-to-b from-gray-800 to-gray-900',
      textBg: 'bg-gray-800/90',
    },
    red: {
      outer: 'bg-gradient-to-b from-red-400 via-red-300 to-red-400',
      inner: 'bg-gradient-to-b from-red-100 to-red-200',
      textBg: 'bg-red-50/90',
    },
    green: {
      outer: 'bg-gradient-to-b from-green-500 via-green-400 to-green-500',
      inner: 'bg-gradient-to-b from-green-100 to-green-200',
      textBg: 'bg-green-50/90',
    },
    gold: {
      outer: 'bg-gradient-to-b from-yellow-500 via-amber-400 to-yellow-500',
      inner: 'bg-gradient-to-b from-amber-100 to-yellow-100',
      textBg: 'bg-amber-50/90',
    },
    colorless: {
      outer: 'bg-gradient-to-b from-gray-400 via-gray-300 to-gray-400',
      inner: 'bg-gradient-to-b from-gray-100 to-gray-200',
      textBg: 'bg-gray-50/90',
    },
    land: {
      outer: 'bg-gradient-to-b from-stone-500 via-stone-400 to-stone-500',
      inner: 'bg-gradient-to-b from-stone-200 to-stone-300',
      textBg: 'bg-stone-100/90',
    },
  };

  const frame = frameStyles[cardColor] || frameStyles.colorless;
  const isBlackCard = cardColor === 'black';
  const isCreature = card.types.includes('CREATURE');

  // Card type icon
  const typeIcon = useMemo(() => {
    if (isCreature) return '⚔️';
    if (card.types.includes('INSTANT')) return '⚡';
    if (card.types.includes('SORCERY')) return '✨';
    if (card.types.includes('ENCHANTMENT')) return '🔮';
    if (card.types.includes('ARTIFACT')) return '⚙️';
    if (card.types.includes('LAND')) return '🏔️';
    if (card.types.includes('PLANESWALKER')) return '👁️';
    return '📜';
  }, [card.types, isCreature]);

  return (
    <div
      className={clsx(
        'relative rounded-xl shadow-lg transition-all duration-200 cursor-pointer select-none',
        config.width,
        config.height,
        frame.outer,
        'p-[3px]', // Outer frame border
        {
          'rotate-90 translate-x-4': tapped,
          'ring-4 ring-yellow-400 ring-offset-2 ring-offset-slate-900 scale-105': isSelected,
          'ring-4 ring-emerald-400 ring-offset-1 ring-offset-slate-900 animate-pulse': isTargetable,
          'ring-4 ring-cyan-400 shadow-xl shadow-cyan-400/30': isHighlighted,
          'hover:-translate-y-2 hover:shadow-2xl hover:z-10': onClick && !tapped,
          'opacity-60 saturate-50': tapped,
        }
      )}
      onClick={onClick}
      title={card.name}
    >
      {/* Inner card frame */}
      <div className={clsx('w-full h-full rounded-lg flex flex-col overflow-hidden', frame.inner)}>
        {/* Card Header: Name + Mana Cost */}
        <div
          className={clsx(
            'flex items-center justify-between px-2 py-1 border-b-2',
            isBlackCard ? 'border-gray-600 bg-gray-700' : 'border-black/20 bg-white/60'
          )}
        >
          <span
            className={clsx(
              'font-bold leading-tight truncate flex-1 font-serif',
              config.nameSize,
              isBlackCard ? 'text-gray-100' : 'text-gray-900'
            )}
          >
            {card.name}
          </span>
          {showDetails && manaSymbols.length > 0 && (
            <div className="flex gap-0.5 ml-1 flex-shrink-0">
              {manaSymbols.map((symbol, idx) => (
                <ManaSymbol key={idx} symbol={symbol} size={config.manaSize} />
              ))}
            </div>
          )}
        </div>

        {/* Card Art Box */}
        <div
          className={clsx(
            'mx-1.5 mt-1 flex-shrink-0 rounded border-2 flex items-center justify-center overflow-hidden',
            isBlackCard ? 'border-gray-600 bg-gray-800' : 'border-black/30 bg-gradient-to-br from-slate-700 to-slate-900',
            size === 'small' ? 'h-[50px]' : size === 'medium' ? 'h-[70px]' : 'h-[100px]'
          )}
        >
          <CardArt cardName={card.name} fallbackIcon={typeIcon} size={size} />
        </div>

        {/* Card Type Line */}
        {showDetails && (
          <div
            className={clsx(
              'mx-1.5 mt-1 px-1.5 py-0.5 rounded border text-center truncate font-medium',
              config.textSize,
              isBlackCard
                ? 'border-gray-600 bg-gray-700 text-gray-200'
                : 'border-black/20 bg-white/70 text-gray-800'
            )}
          >
            {card.types.join(' ')}
            {card.subtypes.length > 0 && ` — ${card.subtypes.join(' ')}`}
          </div>
        )}

        {/* Card Text Box */}
        {showDetails && size !== 'small' && (
          <div
            className={clsx(
              'mx-1.5 mt-1 mb-1.5 px-2 py-1 rounded border flex-1 overflow-y-auto',
              config.textSize,
              'leading-snug',
              isBlackCard
                ? 'border-gray-600 bg-gray-700/80 text-gray-200'
                : 'border-black/20 bg-white/80 text-gray-700'
            )}
          >
            {card.text || <span className="italic opacity-50">No abilities</span>}
          </div>
        )}

        {/* P/T Box for Creatures */}
        {isCreature && card.power !== null && card.toughness !== null && (
          <div
            className={clsx(
              'absolute bottom-2 right-2 px-2 py-0.5 rounded-lg font-bold shadow-lg border-2',
              size === 'small' ? 'text-xs' : 'text-sm',
              isBlackCard
                ? 'bg-gray-700 border-gray-500 text-white'
                : 'bg-white border-black/40 text-gray-900'
            )}
          >
            {card.power}/{card.toughness}
            {card.damage > 0 && <span className="text-red-500 ml-1">(-{card.damage})</span>}
          </div>
        )}

        {/* Counters */}
        {Object.keys(card.counters).length > 0 && (
          <div className="absolute top-10 left-2 flex flex-col gap-1">
            {Object.entries(card.counters).map(([type, count]) => (
              <span
                key={type}
                className="bg-purple-600 text-white text-[10px] px-1.5 py-0.5 rounded-full font-bold shadow-lg border border-purple-400"
              >
                +{count}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* Tapped Overlay */}
      {tapped && (
        <div className="absolute inset-0 bg-black/40 rounded-xl flex items-center justify-center">
          <span className="text-white/90 text-xs font-bold bg-black/70 px-3 py-1 rounded-full uppercase tracking-wide">
            Tapped
          </span>
        </div>
      )}
    </div>
  );
}

export default Card;
