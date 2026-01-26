/**
 * CardBrowser Component
 *
 * Left panel containing search, filters, and card grid.
 */

import { SearchBar } from './SearchBar';
import { FilterPanel } from './FilterPanel';
import { CardGrid } from './CardGrid';

export function CardBrowser() {
  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="p-4 border-b border-gray-700">
        <h2 className="text-lg font-semibold text-white mb-3">Card Browser</h2>
        <SearchBar />
      </div>

      {/* Filters */}
      <FilterPanel />

      {/* Card Grid */}
      <CardGrid />
    </div>
  );
}
