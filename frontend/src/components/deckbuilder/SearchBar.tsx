/**
 * SearchBar Component
 *
 * Text input for searching cards by name or text.
 */

import { useState, useEffect, useCallback } from 'react';
import { useDeckbuilderStore } from '../../stores/deckbuilderStore';

export function SearchBar() {
  const { cardFilter, setCardFilter, searchCards } = useDeckbuilderStore();
  const [localQuery, setLocalQuery] = useState(cardFilter.query || '');

  // Debounce search
  useEffect(() => {
    const timer = setTimeout(() => {
      if (localQuery !== cardFilter.query) {
        setCardFilter({ query: localQuery || undefined });
        searchCards();
      }
    }, 300);

    return () => clearTimeout(timer);
  }, [localQuery, cardFilter.query, setCardFilter, searchCards]);

  const handleClear = useCallback(() => {
    setLocalQuery('');
    setCardFilter({ query: undefined });
    searchCards();
  }, [setCardFilter, searchCards]);

  return (
    <div className="relative">
      <input
        type="text"
        value={localQuery}
        onChange={(e) => setLocalQuery(e.target.value)}
        placeholder="Search cards..."
        className="w-full px-4 py-2 pl-10 bg-gray-800 border border-gray-600 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-game-accent"
      />
      <svg
        className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
        />
      </svg>
      {localQuery && (
        <button
          onClick={handleClear}
          className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500 hover:text-white"
        >
          &times;
        </button>
      )}
    </div>
  );
}
