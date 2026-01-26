/**
 * Sketch Card Detail Component
 *
 * A larger card view for the modal with full card details.
 * Features art prominently with scrollable text area.
 */

import { useState, useEffect } from 'react';
import type { CardDefinitionData } from '../../types/deckbuilder';
import { getLocalImageUrl, getScryfallFuzzyImageUrl } from '../../utils/cardArt';
import { getCardColorGradient } from '../../utils/cardColors';
import { ManaCostDisplay, parseManaSymbols } from '../shared/cards/ManaCostDisplay';

interface SketchCardDetailProps {
  card: CardDefinitionData;
  setCode?: string;
  setName?: string;
}

export function SketchCardDetail({ card, setCode, setName }: SketchCardDetailProps) {
  const [imageStatus, setImageStatus] = useState<'loading' | 'loaded' | 'error'>('loading');
  const [useScryfall, setUseScryfall] = useState(false);

  // Get the image URL
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

  const colorBarClass = getCardColorGradient(card.colors, card.types);

  // Format type line
  const typeLine = card.subtypes.length > 0
    ? `${card.types.join(' ')} - ${card.subtypes.join(' ')}`
    : card.types.join(' ');

  // Format card text with line breaks
  const textParagraphs = card.text?.split('\n').filter(line => line.trim()) || [];

  // Calculate mana value
  const manaSymbols = parseManaSymbols(card.mana_cost);
  const manaValue = manaSymbols.reduce((sum, symbol) => {
    const inner = symbol.replace(/[{}]/g, '');
    if (/^\d+$/.test(inner)) return sum + parseInt(inner);
    if (['W', 'U', 'B', 'R', 'G', 'C'].includes(inner.toUpperCase())) return sum + 1;
    if (inner.includes('/')) return sum + 1;
    return sum;
  }, 0);

  return (
    <div
      className="bg-card-parchment rounded-xl overflow-hidden shadow-2xl border-2 border-stone-400 flex flex-col"
      style={{ width: '320px', minHeight: '480px', maxHeight: '90vh' }}
    >
      {/* Card Name + Mana Cost Header */}
      <div className="px-4 py-3 bg-stone-800 flex items-center justify-between gap-2">
        <h2 className="font-card-name font-bold text-white text-lg leading-tight truncate flex-1">
          {card.name}
        </h2>
        <ManaCostDisplay manaCost={card.mana_cost} size="lg" />
      </div>

      {/* Color Bar */}
      <div className={`h-1.5 ${colorBarClass}`} />

      {/* Art Area */}
      <div className="relative bg-stone-700" style={{ height: '200px' }}>
        {imageStatus === 'loading' && (
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-game-accent" />
          </div>
        )}
        {imageStatus === 'error' && (
          <div className="absolute inset-0 flex items-center justify-center bg-stone-800">
            <div className="text-center p-4">
              <div className="text-5xl mb-2 opacity-50">🎨</div>
              <p className="text-stone-500 text-sm">No artwork available</p>
            </div>
          </div>
        )}
        <img
          src={imageUrl}
          alt={card.name}
          className={`w-full h-full object-cover transition-opacity ${imageStatus === 'loaded' ? 'opacity-100' : 'opacity-0'}`}
          onLoad={() => setImageStatus('loaded')}
          onError={handleImageError}
        />
      </div>

      {/* Type Line */}
      <div className="px-4 py-2 bg-stone-200 border-y border-stone-300">
        <p className="text-sm text-stone-700 font-medium">
          {typeLine}
        </p>
      </div>

      {/* Text Area (scrollable) */}
      <div className="flex-1 overflow-y-auto px-4 py-3 bg-card-parchment min-h-[100px]">
        {textParagraphs.length > 0 ? (
          <div className="space-y-2">
            {textParagraphs.map((paragraph, i) => (
              <p key={i} className="text-sm text-stone-800 font-card-text leading-relaxed">
                {paragraph}
              </p>
            ))}
          </div>
        ) : (
          <p className="text-sm text-stone-400 italic">No rules text</p>
        )}

        {/* Power/Toughness for creatures */}
        {card.power !== null && card.toughness !== null && (
          <div className="flex justify-end mt-3">
            <span className="bg-stone-800 text-white text-lg font-bold px-3 py-1 rounded-lg shadow-md">
              {card.power}/{card.toughness}
            </span>
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="px-4 py-2 bg-stone-200 border-t border-stone-300 flex items-center justify-between">
        <div className="text-xs text-stone-600">
          {setName && <span>{setName}</span>}
          {setCode && <span className="ml-1 opacity-60">({setCode})</span>}
        </div>
        <div className="flex items-center gap-3 text-xs text-stone-600">
          <span>MV: {manaValue}</span>
          {card.colors.length > 0 && (
            <span>{card.colors.join(', ')}</span>
          )}
        </div>
      </div>
    </div>
  );
}

export default SketchCardDetail;
