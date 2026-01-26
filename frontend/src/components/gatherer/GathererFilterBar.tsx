/**
 * Gatherer Filter Bar Component
 *
 * Provides filtering and sorting controls for the card grid.
 */

import { useState } from 'react';
import { useGathererStore } from '../../stores/gathererStore';
import { COLORS } from '../../types/deckbuilder';
import { SORT_FIELDS, RARITY_INFO } from '../../types/gatherer';
import type { SortField } from '../../types/gatherer';

export function GathererFilterBar() {
  const {
    currentSet,
    cardsTotal,
    filter,
    sortBy,
    sortOrder,
    setFilter,
    clearFilter,
    setSortBy,
    toggleSortOrder,
  } = useGathererStore();

  const [textSearch, setTextSearch] = useState(filter.textSearch || '');

  if (!currentSet) return null;

  const handleTextSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setFilter({ textSearch: textSearch || undefined });
  };

  const handleTypeToggle = (type: string) => {
    const currentTypes = filter.types || [];
    const newTypes = currentTypes.includes(type)
      ? currentTypes.filter((t) => t !== type)
      : [...currentTypes, type];
    setFilter({ types: newTypes.length > 0 ? newTypes : undefined });
  };

  const handleColorToggle = (color: string) => {
    const currentColors = filter.colors || [];
    const newColors = currentColors.includes(color)
      ? currentColors.filter((c) => c !== color)
      : [...currentColors, color];
    setFilter({ colors: newColors.length > 0 ? newColors : undefined });
  };

  const handleRarityChange = (rarity: string) => {
    setFilter({ rarity: rarity || undefined });
  };

  const hasActiveFilters =
    (filter.types && filter.types.length > 0) ||
    (filter.colors && filter.colors.length > 0) ||
    filter.rarity ||
    filter.textSearch ||
    filter.cmcMin !== undefined ||
    filter.cmcMax !== undefined;

  return (
    <div className="bg-gray-800 border-b border-gray-700 p-4">
      {/* Set header and card count */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-xl font-bold text-white">{currentSet.name}</h2>
          <p className="text-sm text-gray-400">
            {cardsTotal} card{cardsTotal !== 1 ? 's' : ''} found
          </p>
        </div>

        {/* Sort controls */}
        <div className="flex items-center gap-2">
          <span className="text-sm text-gray-400">Sort by:</span>
          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value as SortField)}
            className="px-3 py-1.5 bg-gray-700 border border-gray-600 rounded text-white text-sm focus:outline-none focus:border-game-accent"
          >
            {SORT_FIELDS.map((field) => (
              <option key={field.value} value={field.value}>
                {field.label}
              </option>
            ))}
          </select>
          <button
            onClick={toggleSortOrder}
            className="px-3 py-1.5 bg-gray-700 border border-gray-600 rounded text-white text-sm hover:bg-gray-600 transition-colors"
            title={sortOrder === 'asc' ? 'Ascending' : 'Descending'}
          >
            {sortOrder === 'asc' ? '↑ Asc' : '↓ Desc'}
          </button>
        </div>
      </div>

      {/* Filter row */}
      <div className="flex flex-wrap items-center gap-4">
        {/* Text search */}
        <form onSubmit={handleTextSearchSubmit} className="flex-1 min-w-[200px] max-w-[300px]">
          <div className="relative">
            <input
              type="text"
              value={textSearch}
              onChange={(e) => setTextSearch(e.target.value)}
              placeholder="Search cards..."
              className="w-full px-3 py-1.5 pr-8 bg-gray-700 border border-gray-600 rounded text-white text-sm placeholder-gray-400 focus:outline-none focus:border-game-accent"
            />
            {textSearch && (
              <button
                type="button"
                onClick={() => {
                  setTextSearch('');
                  setFilter({ textSearch: undefined });
                }}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-white"
              >
                ×
              </button>
            )}
          </div>
        </form>

        {/* Type filter */}
        <div className="flex items-center gap-1">
          <span className="text-xs text-gray-400 mr-1">Type:</span>
          {['CREATURE', 'INSTANT', 'SORCERY', 'ENCHANTMENT', 'ARTIFACT'].map((type) => (
            <button
              key={type}
              onClick={() => handleTypeToggle(type)}
              className={`px-2 py-1 text-xs rounded transition-colors ${
                filter.types?.includes(type)
                  ? 'bg-game-accent text-white'
                  : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
              }`}
            >
              {type.charAt(0) + type.slice(1).toLowerCase()}
            </button>
          ))}
        </div>

        {/* Color filter */}
        <div className="flex items-center gap-1">
          <span className="text-xs text-gray-400 mr-1">Color:</span>
          {Object.entries(COLORS).map(([code, info]) => (
            <button
              key={code}
              onClick={() => handleColorToggle(code)}
              className={`w-6 h-6 rounded-full border-2 transition-all ${
                filter.colors?.includes(code)
                  ? 'border-white scale-110'
                  : 'border-gray-600 hover:border-gray-400'
              }`}
              style={{ backgroundColor: info.hex }}
              title={info.name}
            />
          ))}
        </div>

        {/* Rarity filter */}
        <div className="flex items-center gap-1">
          <span className="text-xs text-gray-400 mr-1">Rarity:</span>
          <select
            value={filter.rarity || ''}
            onChange={(e) => handleRarityChange(e.target.value)}
            className="px-2 py-1 bg-gray-700 border border-gray-600 rounded text-white text-sm focus:outline-none focus:border-game-accent"
          >
            <option value="">All</option>
            {Object.entries(RARITY_INFO).map(([rarity, info]) => (
              <option key={rarity} value={rarity}>
                {info.label}
              </option>
            ))}
          </select>
        </div>

        {/* CMC filter */}
        <div className="flex items-center gap-1">
          <span className="text-xs text-gray-400 mr-1">CMC:</span>
          <input
            type="number"
            min="0"
            max="20"
            placeholder="Min"
            value={filter.cmcMin ?? ''}
            onChange={(e) =>
              setFilter({
                cmcMin: e.target.value ? parseInt(e.target.value) : undefined,
              })
            }
            className="w-14 px-2 py-1 bg-gray-700 border border-gray-600 rounded text-white text-sm focus:outline-none focus:border-game-accent"
          />
          <span className="text-gray-500">-</span>
          <input
            type="number"
            min="0"
            max="20"
            placeholder="Max"
            value={filter.cmcMax ?? ''}
            onChange={(e) =>
              setFilter({
                cmcMax: e.target.value ? parseInt(e.target.value) : undefined,
              })
            }
            className="w-14 px-2 py-1 bg-gray-700 border border-gray-600 rounded text-white text-sm focus:outline-none focus:border-game-accent"
          />
        </div>

        {/* Clear filters */}
        {hasActiveFilters && (
          <button
            onClick={() => {
              setTextSearch('');
              clearFilter();
            }}
            className="px-3 py-1 text-xs bg-red-600 hover:bg-red-500 text-white rounded transition-colors"
          >
            Clear Filters
          </button>
        )}
      </div>
    </div>
  );
}

export default GathererFilterBar;
