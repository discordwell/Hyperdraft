/**
 * DeckPanel Component
 *
 * Right panel containing deck metadata, stats, and card list.
 */

import { useDeckbuilderStore } from '../../stores/deckbuilderStore';
import { DeckStats } from './DeckStats';
import { DeckList } from './DeckList';
import { ARCHETYPES, FORMATS } from '../../types/deckbuilder';

export function DeckPanel() {
  const {
    currentDeck,
    hasUnsavedChanges,
    setDeckName,
    setDeckArchetype,
    setDeckFormat,
    setDeckDescription,
  } = useDeckbuilderStore();

  return (
    <div className="flex flex-col h-full">
      {/* Deck Header */}
      <div className="p-4 border-b border-gray-700">
        <div className="flex items-center gap-2 mb-3">
          <input
            type="text"
            value={currentDeck.name}
            onChange={(e) => setDeckName(e.target.value)}
            className="flex-1 px-3 py-2 bg-gray-800 border border-gray-600 rounded text-white font-semibold focus:outline-none focus:border-game-accent"
            placeholder="Deck name..."
          />
          {hasUnsavedChanges && (
            <span className="text-xs text-yellow-500">Unsaved</span>
          )}
        </div>

        {/* Archetype & Format */}
        <div className="flex gap-2">
          <select
            value={currentDeck.archetype}
            onChange={(e) => setDeckArchetype(e.target.value)}
            className="flex-1 px-2 py-1 bg-gray-800 border border-gray-600 rounded text-white text-sm focus:outline-none focus:border-game-accent"
          >
            {ARCHETYPES.map((arch) => (
              <option key={arch} value={arch}>
                {arch}
              </option>
            ))}
          </select>

          <select
            value={currentDeck.format}
            onChange={(e) => setDeckFormat(e.target.value)}
            className="flex-1 px-2 py-1 bg-gray-800 border border-gray-600 rounded text-white text-sm focus:outline-none focus:border-game-accent"
          >
            {FORMATS.map((fmt) => (
              <option key={fmt} value={fmt}>
                {fmt}
              </option>
            ))}
          </select>
        </div>

        {/* Description */}
        <textarea
          value={currentDeck.description}
          onChange={(e) => setDeckDescription(e.target.value)}
          placeholder="Deck description..."
          className="w-full mt-2 px-2 py-1 bg-gray-800 border border-gray-600 rounded text-white text-sm resize-none h-12 focus:outline-none focus:border-game-accent"
        />
      </div>

      {/* Stats */}
      <DeckStats />

      {/* Card List */}
      <DeckList />
    </div>
  );
}
