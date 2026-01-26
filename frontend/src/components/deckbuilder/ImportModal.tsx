/**
 * ImportModal Component
 *
 * Modal for importing a deck from text format.
 */

import { useState } from 'react';
import { useDeckbuilderStore } from '../../stores/deckbuilderStore';

interface ImportModalProps {
  onClose: () => void;
}

export function ImportModal({ onClose }: ImportModalProps) {
  const { importDeck, isLoading, hasUnsavedChanges } = useDeckbuilderStore();
  const [deckText, setDeckText] = useState('');
  const [error, setError] = useState<string | null>(null);

  const handleImport = async () => {
    if (!deckText.trim()) {
      setError('Please paste a deck list');
      return;
    }

    if (hasUnsavedChanges) {
      if (!confirm('You have unsaved changes. Import a deck anyway?')) {
        return;
      }
    }

    try {
      setError(null);
      await importDeck(deckText);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to import deck');
    }
  };

  const exampleFormat = `4 Lightning Bolt
4 Monastery Swiftspear
4 Goblin Guide
20 Mountain

Sideboard
2 Searing Blood
3 Smash to Smithereens`;

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-game-surface border border-gray-700 rounded-lg p-6 max-w-lg w-full mx-4">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-bold text-white">Import Deck</h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-white text-2xl leading-none"
          >
            &times;
          </button>
        </div>

        {error && (
          <div className="mb-4 p-3 bg-red-900/50 border border-red-500 rounded text-red-200 text-sm">
            {error}
          </div>
        )}

        <div className="mb-4">
          <label className="block text-sm text-gray-400 mb-2">
            Paste deck list
          </label>
          <textarea
            value={deckText}
            onChange={(e) => setDeckText(e.target.value)}
            placeholder={exampleFormat}
            className="w-full h-64 p-3 bg-gray-800 border border-gray-600 rounded text-white font-mono text-sm focus:outline-none focus:border-game-accent"
          />
        </div>

        <div className="text-xs text-gray-500 mb-4">
          <p className="mb-1">Supported formats:</p>
          <ul className="list-disc list-inside">
            <li>4 Card Name</li>
            <li>4x Card Name</li>
            <li>Card Name x4</li>
          </ul>
          <p className="mt-2">
            Use "Sideboard" on its own line to start the sideboard section.
          </p>
        </div>

        <div className="flex gap-2">
          <button
            onClick={onClose}
            className="flex-1 px-4 py-2 bg-gray-700 text-white rounded hover:bg-gray-600 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleImport}
            disabled={isLoading || !deckText.trim()}
            className="flex-1 px-4 py-2 bg-game-accent text-white rounded hover:bg-red-500 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isLoading ? 'Importing...' : 'Import Deck'}
          </button>
        </div>
      </div>
    </div>
  );
}
