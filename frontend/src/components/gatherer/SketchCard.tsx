/**
 * Sketch Card Component
 *
 * A card design inspired by Slay the Spire and indie roguelikes.
 * Features art prominently with a parchment-style text area below.
 */

import { useState, useEffect } from 'react';
import type { CardDefinitionData } from '../../types/deckbuilder';
import { getLocalImageUrl, getScryfallFuzzyImageUrl } from '../../utils/cardArt';
import { getCardColorClass } from '../../utils/cardColors';
import { ManaCostDisplay } from '../shared/cards/ManaCostDisplay';

interface SketchCardProps {
  card: CardDefinitionData;
  setCode?: string;
  onClick?: () => void;
  onAdd?: (cardName: string) => void;
  showAddOverlay?: boolean;
}

export function SketchCard({ card, setCode, onClick, onAdd, showAddOverlay = false }: SketchCardProps) {
  const [imageStatus, setImageStatus] = useState<'loading' | 'loaded' | 'error'>('loading');
  const [useScryfall, setUseScryfall] = useState(false);

  // Get the image URL - try local first, then Scryfall art_crop
  const localUrl = setCode ? getLocalImageUrl(card.name, setCode) : null;
  const scryfallUrl = getScryfallFuzzyImageUrl(card.name, 'art_crop');
  const imageUrl = useScryfall ? scryfallUrl : (localUrl || scryfallUrl);

  // Reset state when card changes
  useEffect(() => {
    setImageStatus('loading');
    setUseScryfall(false);
  }, [card.name, setCode]);

  const handleImageError = () => {
    if (!useScryfall && localUrl) {
      setUseScryfall(true);
      setImageStatus('loading');
    } else {
      setImageStatus('error');
    }
  };

  const colorStripeClass = getCardColorClass(card.colors, card.types);

  // Format type line
  const typeLine = card.subtypes.length > 0
    ? `${card.types.join(' ')} - ${card.subtypes.join(' ')}`
    : card.types.join(' ');

  // Truncate text for grid display
  const truncatedText = card.text
    ? card.text.split('\n')[0].slice(0, 60) + (card.text.length > 60 ? '...' : '')
    : '';

  const handleClick = () => {
    if (onAdd) {
      onAdd(card.name);
    } else if (onClick) {
      onClick();
    }
  };

  return (
    <button
      onClick={handleClick}
      className="w-full bg-card-parchment rounded-lg overflow-hidden shadow-md hover:shadow-xl transition-all hover:scale-[1.02] text-left group border border-stone-300 relative"
      style={{ aspectRatio: '5/7' }}
    >
      {/* Card Name + Mana Cost Header */}
      <div className="px-2 py-1.5 bg-stone-800 flex items-center justify-between gap-1">
        <h3 className="font-card-name font-semibold text-white text-xs leading-tight truncate flex-1">
          {card.name}
        </h3>
        <ManaCostDisplay manaCost={card.mana_cost} size="sm" maxSymbols={5} />
      </div>

      {/* Color Stripe */}
      <div className={`h-1 ${colorStripeClass}`} />

      {/* Art Area - 55% of remaining space */}
      <div className="relative bg-stone-700" style={{ height: '52%' }}>
        {imageStatus === 'loading' && (
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="animate-pulse bg-stone-600 w-full h-full" />
          </div>
        )}
        {imageStatus === 'error' && (
          <div className="absolute inset-0 flex items-center justify-center bg-stone-800">
            <div className="text-center p-2">
              <div className="text-3xl mb-1 opacity-50">🎨</div>
              <p className="text-[10px] text-stone-500">No art</p>
            </div>
          </div>
        )}
        <img
          src={imageUrl}
          alt={card.name}
          className={`w-full h-full object-cover transition-opacity ${imageStatus === 'loaded' ? 'opacity-100' : 'opacity-0'}`}
          onLoad={() => setImageStatus('loaded')}
          onError={handleImageError}
          loading="lazy"
        />
      </div>

      {/* Text Area */}
      <div className="p-2 bg-card-parchment flex-1 flex flex-col">
        {/* Type Line */}
        <p className="text-[10px] text-stone-600 font-medium truncate border-b border-stone-300 pb-1 mb-1">
          {typeLine}
        </p>

        {/* Rules Text (truncated) */}
        {truncatedText && (
          <p className="text-[9px] text-stone-700 font-card-text leading-tight line-clamp-2 flex-1">
            {truncatedText}
          </p>
        )}

        {/* Power/Toughness for creatures */}
        {card.power !== null && card.toughness !== null && (
          <div className="flex justify-end mt-1">
            <span className="bg-stone-800 text-white text-xs font-bold px-1.5 py-0.5 rounded">
              {card.power}/{card.toughness}
            </span>
          </div>
        )}
      </div>

      {/* Add overlay for deckbuilder mode */}
      {showAddOverlay && (
        <div className="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center rounded-lg">
          <span className="px-4 py-2 bg-game-accent text-white rounded-lg text-sm font-bold shadow-lg">
            + Add
          </span>
        </div>
      )}
    </button>
  );
}

export default SketchCard;
