/**
 * CardGrid Component
 *
 * Displays search results in a scrollable grid.
 * Uses simple CSS grid with lazy loading instead of full virtualization
 * for better compatibility.
 */

import { useCallback, useRef, useEffect } from 'react';
import { useDeckbuilderStore } from '../../stores/deckbuilderStore';
import type { CardDefinitionData } from '../../types/deckbuilder';
import { COLORS, type ColorSymbol } from '../../types/deckbuilder';

interface CardItemProps {
  card: CardDefinitionData;
  onAdd: (cardName: string) => void;
}

function CardItem({ card, onAdd }: CardItemProps) {
  const getColorGradient = () => {
    if (!card.colors || card.colors.length === 0) {
      return 'from-gray-700 to-gray-800';
    }
    if (card.colors.length === 1) {
      const colorKey = card.colors[0][0] as ColorSymbol;
      const hex = COLORS[colorKey]?.hex || '#666';
      return `from-[${hex}]/30 to-gray-800`;
    }
    return 'from-amber-700/30 to-gray-800'; // Multi-color (gold)
  };

  const getPowerToughness = () => {
    if (card.power !== null && card.toughness !== null) {
      return `${card.power}/${card.toughness}`;
    }
    return null;
  };

  return (
    <div
      className={`bg-gradient-to-b ${getColorGradient()} border border-gray-600 rounded-lg p-3 hover:border-game-accent transition-colors cursor-pointer group relative`}
      onClick={() => onAdd(card.name)}
    >
      {/* Card Name */}
      <div className="flex justify-between items-start mb-1">
        <span className="text-sm font-semibold text-white truncate flex-1 mr-1">
          {card.name}
        </span>
        {card.mana_cost && (
          <span className="text-xs text-gray-400 font-mono whitespace-nowrap">
            {card.mana_cost}
          </span>
        )}
      </div>

      {/* Type Line */}
      <div className="text-xs text-gray-400 mb-2">
        {card.types.map((t) => t.charAt(0) + t.slice(1).toLowerCase()).join(' ')}
        {card.subtypes.length > 0 && ` - ${card.subtypes.join(' ')}`}
      </div>

      {/* Card Text (truncated) */}
      {card.text && (
        <div className="text-xs text-gray-300 line-clamp-2 mb-2">
          {card.text}
        </div>
      )}

      {/* Power/Toughness */}
      {getPowerToughness() && (
        <div className="absolute bottom-2 right-2 text-sm font-bold text-white bg-gray-900/80 px-2 py-0.5 rounded">
          {getPowerToughness()}
        </div>
      )}

      {/* Add button (appears on hover) */}
      <div className="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center rounded-lg">
        <span className="px-3 py-1 bg-game-accent text-white rounded text-sm font-semibold">
          + Add
        </span>
      </div>
    </div>
  );
}

export function CardGrid() {
  const {
    searchResults,
    searchTotal,
    searchLoading,
    loadMoreCards,
    addCard,
  } = useDeckbuilderStore();

  const containerRef = useRef<HTMLDivElement>(null);
  const loadingRef = useRef<HTMLDivElement>(null);

  // Intersection observer for infinite scroll
  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        if (
          entries[0].isIntersecting &&
          !searchLoading &&
          searchResults.length < searchTotal
        ) {
          loadMoreCards();
        }
      },
      { threshold: 0.1 }
    );

    if (loadingRef.current) {
      observer.observe(loadingRef.current);
    }

    return () => observer.disconnect();
  }, [searchLoading, searchResults.length, searchTotal, loadMoreCards]);

  const handleAdd = useCallback(
    (cardName: string) => {
      addCard(cardName);
    },
    [addCard]
  );

  return (
    <div ref={containerRef} className="flex-1 overflow-y-auto p-4">
      {/* Results count */}
      <div className="text-sm text-gray-500 mb-3">
        {searchTotal.toLocaleString()} cards found
      </div>

      {/* Card Grid */}
      <div className="grid grid-cols-2 lg:grid-cols-3 gap-3">
        {searchResults.map((card) => (
          <CardItem key={card.name} card={card} onAdd={handleAdd} />
        ))}
      </div>

      {/* Loading indicator / load more trigger */}
      <div ref={loadingRef} className="py-4 text-center">
        {searchLoading && (
          <div className="text-gray-400">Loading more cards...</div>
        )}
        {!searchLoading && searchResults.length < searchTotal && (
          <button
            onClick={() => loadMoreCards()}
            className="text-game-accent hover:underline"
          >
            Load more ({searchTotal - searchResults.length} remaining)
          </button>
        )}
        {!searchLoading && searchResults.length === 0 && (
          <div className="text-gray-500">No cards found matching your filters.</div>
        )}
      </div>
    </div>
  );
}
