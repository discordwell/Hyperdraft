/**
 * LoadDeckModal Component
 *
 * Modal for selecting a saved deck to load.
 */

import { useEffect } from 'react';
import { useDeckbuilderStore } from '../../stores/deckbuilderStore';
import { COLORS, type ColorSymbol } from '../../types/deckbuilder';

interface LoadDeckModalProps {
  onClose: () => void;
}

export function LoadDeckModal({ onClose }: LoadDeckModalProps) {
  const {
    savedDecks,
    loadSavedDecks,
    loadDeck,
    deleteDeck,
    isLoading,
    hasUnsavedChanges,
  } = useDeckbuilderStore();

  useEffect(() => {
    loadSavedDecks();
  }, [loadSavedDecks]);

  const handleLoad = async (deckId: string) => {
    if (hasUnsavedChanges) {
      if (!confirm('You have unsaved changes. Load a different deck anyway?')) {
        return;
      }
    }
    await loadDeck(deckId);
    onClose();
  };

  const handleDelete = async (deckId: string, deckName: string) => {
    if (confirm(`Delete deck "${deckName}"? This cannot be undone.`)) {
      await deleteDeck(deckId);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-game-surface border border-gray-700 rounded-lg p-6 max-w-lg w-full mx-4 max-h-[80vh] flex flex-col">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-bold text-white">Load Deck</h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-white text-2xl leading-none"
          >
            &times;
          </button>
        </div>

        {isLoading ? (
          <div className="text-center text-gray-400 py-8">Loading...</div>
        ) : savedDecks.length === 0 ? (
          <div className="text-center text-gray-500 py-8">
            No saved decks found. Create a new deck to get started!
          </div>
        ) : (
          <div className="overflow-y-auto flex-1 -mx-2 px-2">
            {savedDecks.map((deck) => (
              <div
                key={deck.id}
                className="flex items-center justify-between p-3 hover:bg-gray-800/50 rounded-lg mb-2 group"
              >
                <div
                  className="flex-1 cursor-pointer"
                  onClick={() => handleLoad(deck.id)}
                >
                  <div className="flex items-center gap-2">
                    <span className="text-white font-semibold">{deck.name}</span>
                    <div className="flex gap-0.5">
                      {deck.colors.map((color) => {
                        const colorKey = color as ColorSymbol;
                        return (
                          <div
                            key={color}
                            className="w-4 h-4 rounded-full border border-white/30"
                            style={{
                              backgroundColor: COLORS[colorKey]?.hex || '#666',
                            }}
                          />
                        );
                      })}
                    </div>
                  </div>
                  <div className="text-sm text-gray-400">
                    {deck.archetype} &bull; {deck.mainboard_count} cards &bull;{' '}
                    {deck.format}
                  </div>
                </div>

                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    handleDelete(deck.id, deck.name);
                  }}
                  className="px-2 py-1 text-red-400 hover:text-red-300 hover:bg-red-900/30 rounded opacity-0 group-hover:opacity-100 transition-opacity"
                >
                  Delete
                </button>
              </div>
            ))}
          </div>
        )}

        <div className="mt-4 pt-4 border-t border-gray-700">
          <button
            onClick={onClose}
            className="w-full px-4 py-2 bg-gray-700 text-white rounded hover:bg-gray-600 transition-colors"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}
