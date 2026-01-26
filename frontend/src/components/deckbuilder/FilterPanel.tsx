/**
 * FilterPanel Component
 *
 * Card filtering by type, color, and CMC.
 */

import { useDeckbuilderStore } from '../../stores/deckbuilderStore';
import { CARD_TYPES, COLORS, type ColorSymbol } from '../../types/deckbuilder';

export function FilterPanel() {
  const { cardFilter, setCardFilter, searchCards } = useDeckbuilderStore();

  const toggleType = (type: string) => {
    const current = cardFilter.types || [];
    const newTypes = current.includes(type)
      ? current.filter((t) => t !== type)
      : [...current, type];
    setCardFilter({ types: newTypes.length > 0 ? newTypes : undefined });
    searchCards();
  };

  const toggleColor = (color: string) => {
    const current = cardFilter.colors || [];
    const newColors = current.includes(color)
      ? current.filter((c) => c !== color)
      : [...current, color];
    setCardFilter({ colors: newColors.length > 0 ? newColors : undefined });
    searchCards();
  };

  const setCmcRange = (min: number | undefined, max: number | undefined) => {
    setCardFilter({ cmcMin: min, cmcMax: max });
    searchCards();
  };

  const clearFilters = () => {
    setCardFilter({
      types: undefined,
      colors: undefined,
      cmcMin: undefined,
      cmcMax: undefined,
      textSearch: undefined,
    });
    searchCards();
  };

  const hasFilters =
    (cardFilter.types && cardFilter.types.length > 0) ||
    (cardFilter.colors && cardFilter.colors.length > 0) ||
    cardFilter.cmcMin !== undefined ||
    cardFilter.cmcMax !== undefined;

  return (
    <div className="p-4 bg-gray-900/50 border-b border-gray-700">
      {/* Types */}
      <div className="mb-3">
        <div className="text-xs text-gray-500 uppercase mb-2">Types</div>
        <div className="flex flex-wrap gap-1">
          {CARD_TYPES.map((type) => (
            <button
              key={type}
              onClick={() => toggleType(type)}
              className={`px-2 py-1 text-xs rounded transition-colors ${
                cardFilter.types?.includes(type)
                  ? 'bg-game-accent text-white'
                  : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
              }`}
            >
              {type.charAt(0) + type.slice(1).toLowerCase()}
            </button>
          ))}
        </div>
      </div>

      {/* Colors */}
      <div className="mb-3">
        <div className="text-xs text-gray-500 uppercase mb-2">Colors</div>
        <div className="flex gap-2">
          {(Object.keys(COLORS) as ColorSymbol[]).map((color) => (
            <button
              key={color}
              onClick={() => toggleColor(color)}
              className={`w-8 h-8 rounded-full border-2 transition-all flex items-center justify-center font-bold text-sm ${
                cardFilter.colors?.includes(color)
                  ? 'border-white scale-110'
                  : 'border-transparent opacity-60 hover:opacity-100'
              }`}
              style={{ backgroundColor: COLORS[color].hex }}
              title={COLORS[color].name}
            >
              {color === 'B' || color === 'U' ? (
                <span className="text-white">{color}</span>
              ) : (
                <span className="text-black">{color}</span>
              )}
            </button>
          ))}
        </div>
      </div>

      {/* CMC Range */}
      <div className="mb-3">
        <div className="text-xs text-gray-500 uppercase mb-2">Mana Value</div>
        <div className="flex items-center gap-2">
          <select
            value={cardFilter.cmcMin ?? ''}
            onChange={(e) =>
              setCmcRange(
                e.target.value ? Number(e.target.value) : undefined,
                cardFilter.cmcMax
              )
            }
            className="px-2 py-1 bg-gray-700 border border-gray-600 rounded text-white text-sm"
          >
            <option value="">Min</option>
            {[0, 1, 2, 3, 4, 5, 6, 7].map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
          <span className="text-gray-500">to</span>
          <select
            value={cardFilter.cmcMax ?? ''}
            onChange={(e) =>
              setCmcRange(
                cardFilter.cmcMin,
                e.target.value ? Number(e.target.value) : undefined
              )
            }
            className="px-2 py-1 bg-gray-700 border border-gray-600 rounded text-white text-sm"
          >
            <option value="">Max</option>
            {[0, 1, 2, 3, 4, 5, 6, 7].map((n) => (
              <option key={n} value={n}>
                {n === 7 ? '7+' : n}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Clear Filters */}
      {hasFilters && (
        <button
          onClick={clearFilters}
          className="text-xs text-gray-400 hover:text-white underline"
        >
          Clear all filters
        </button>
      )}
    </div>
  );
}
