/**
 * DeckList Component
 *
 * Displays the current deck contents grouped by card type.
 */

import { useMemo } from 'react';
import { useDeckbuilderStore } from '../../stores/deckbuilderStore';
import type { DeckEntry } from '../../types/deckbuilder';

interface DeckCardItemProps {
  entry: DeckEntry;
  onRemove: (cardName: string) => void;
  onSetQuantity: (cardName: string, qty: number) => void;
}

function DeckCardItem({ entry, onRemove, onSetQuantity }: DeckCardItemProps) {
  return (
    <div className="flex items-center justify-between py-1 px-2 hover:bg-gray-800/50 rounded group">
      <div className="flex items-center gap-2 flex-1 min-w-0">
        <span className="text-sm font-mono text-gray-400 w-6">
          {entry.qty}x
        </span>
        <span className="text-sm text-white truncate">{entry.card}</span>
      </div>
      <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
        <button
          onClick={() => onSetQuantity(entry.card, entry.qty - 1)}
          className="w-5 h-5 flex items-center justify-center text-gray-400 hover:text-white hover:bg-gray-700 rounded"
        >
          -
        </button>
        <button
          onClick={() => onSetQuantity(entry.card, entry.qty + 1)}
          className="w-5 h-5 flex items-center justify-center text-gray-400 hover:text-white hover:bg-gray-700 rounded"
        >
          +
        </button>
        <button
          onClick={() => onRemove(entry.card)}
          className="w-5 h-5 flex items-center justify-center text-red-400 hover:text-red-300 hover:bg-gray-700 rounded ml-1"
        >
          &times;
        </button>
      </div>
    </div>
  );
}

interface CardGroup {
  name: string;
  cards: DeckEntry[];
  count: number;
}

export function DeckList() {
  const { currentDeck, searchResults, removeCard, setCardQuantity, clearDeck } =
    useDeckbuilderStore();

  // Group cards by type
  const cardGroups = useMemo(() => {
    const groups: Record<string, DeckEntry[]> = {
      Creatures: [],
      Instants: [],
      Sorceries: [],
      Enchantments: [],
      Artifacts: [],
      Planeswalkers: [],
      Lands: [],
      Other: [],
    };

    // Create a lookup from search results
    const cardLookup = new Map(searchResults.map((c) => [c.name, c]));

    for (const entry of currentDeck.mainboard) {
      const cardDef = cardLookup.get(entry.card);
      const types = cardDef?.types || [];

      if (types.includes('CREATURE')) {
        groups.Creatures.push(entry);
      } else if (types.includes('INSTANT')) {
        groups.Instants.push(entry);
      } else if (types.includes('SORCERY')) {
        groups.Sorceries.push(entry);
      } else if (types.includes('ENCHANTMENT')) {
        groups.Enchantments.push(entry);
      } else if (types.includes('ARTIFACT')) {
        groups.Artifacts.push(entry);
      } else if (types.includes('PLANESWALKER')) {
        groups.Planeswalkers.push(entry);
      } else if (types.includes('LAND')) {
        groups.Lands.push(entry);
      } else {
        groups.Other.push(entry);
      }
    }

    // Convert to array and filter empty groups
    return Object.entries(groups)
      .filter(([_, cards]) => cards.length > 0)
      .map(([name, cards]) => ({
        name,
        cards: cards.sort((a, b) => a.card.localeCompare(b.card)),
        count: cards.reduce((sum, e) => sum + e.qty, 0),
      }));
  }, [currentDeck.mainboard, searchResults]);

  const handleRemove = (cardName: string) => {
    setCardQuantity(cardName, 0);
  };

  const handleSetQuantity = (cardName: string, qty: number) => {
    setCardQuantity(cardName, Math.max(0, qty));
  };

  if (currentDeck.mainboard.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center text-gray-500">
        <div className="text-center">
          <p className="mb-2">No cards in deck yet.</p>
          <p className="text-sm">Click cards in the browser to add them.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto">
      {/* Clear Button */}
      <div className="p-2 border-b border-gray-700">
        <button
          onClick={clearDeck}
          className="text-xs text-red-400 hover:text-red-300"
        >
          Clear All Cards
        </button>
      </div>

      {/* Card Groups */}
      {cardGroups.map((group) => (
        <div key={group.name} className="border-b border-gray-800">
          <div className="px-3 py-2 bg-gray-900/30 sticky top-0">
            <span className="text-xs text-gray-400 uppercase font-semibold">
              {group.name} ({group.count})
            </span>
          </div>
          <div className="px-1 py-1">
            {group.cards.map((entry) => (
              <DeckCardItem
                key={entry.card}
                entry={entry}
                onRemove={handleRemove}
                onSetQuantity={handleSetQuantity}
              />
            ))}
          </div>
        </div>
      ))}

      {/* Sideboard Section */}
      {currentDeck.sideboard.length > 0 && (
        <div className="border-t border-gray-700 mt-2">
          <div className="px-3 py-2 bg-gray-900/30 sticky top-0">
            <span className="text-xs text-gray-400 uppercase font-semibold">
              Sideboard ({currentDeck.sideboard.reduce((s, e) => s + e.qty, 0)})
            </span>
          </div>
          <div className="px-1 py-1">
            {currentDeck.sideboard.map((entry) => (
              <DeckCardItem
                key={`sb-${entry.card}`}
                entry={entry}
                onRemove={(name) => setCardQuantity(name, 0, true)}
                onSetQuantity={(name, qty) =>
                  setCardQuantity(name, Math.max(0, qty), true)
                }
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
