/**
 * Deckbuilder Page
 *
 * Main deckbuilding interface with card browser and deck editor.
 */

import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useDeckbuilderStore } from '../stores/deckbuilderStore';
import { CardBrowser } from '../components/deckbuilder/CardBrowser';
import { DeckPanel } from '../components/deckbuilder/DeckPanel';
import { AIAssistPanel } from '../components/deckbuilder/AIAssistPanel';
import { LoadDeckModal } from '../components/deckbuilder/LoadDeckModal';
import { ImportModal } from '../components/deckbuilder/ImportModal';
import { GAMES, GAME_LABELS } from '../types/deckbuilder';
import type { Game } from '../types/deckbuilder';

function isGame(value: string | undefined): value is Game {
  return !!value && (GAMES as readonly string[]).includes(value);
}

export function Deckbuilder() {
  const navigate = useNavigate();
  const { game: gameParam } = useParams<{ game?: string }>();
  const urlGame: Game = isGame(gameParam) ? gameParam : 'mtg';

  const {
    currentGame,
    error,
    hasUnsavedChanges,
    isSaving,
    newDeck,
    saveDeck,
    setGame,
    clearError,
  } = useDeckbuilderStore();

  const [showLoadModal, setShowLoadModal] = useState(false);
  const [showImportModal, setShowImportModal] = useState(false);
  const [showExportText, setShowExportText] = useState<string | null>(null);

  // Sync game from URL → store. setGame handles loading saved decks + cards.
  useEffect(() => {
    if (currentGame !== urlGame) {
      setGame(urlGame);
    } else {
      // Same game on remount — kick off the initial fetches.
      const store = useDeckbuilderStore.getState();
      store.loadSavedDecks();
      store.searchCards();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [urlGame]);

  const handleGameChange = (next: Game) => {
    if (next === currentGame) return;
    if (hasUnsavedChanges) {
      if (!confirm('You have unsaved changes. Switch games anyway?')) return;
    }
    navigate(`/deckbuilder/${next}`);
  };

  const handleNew = () => {
    if (hasUnsavedChanges) {
      if (!confirm('You have unsaved changes. Create a new deck anyway?')) {
        return;
      }
    }
    newDeck();
  };

  const handleSave = async () => {
    await saveDeck();
  };

  const handleExport = async () => {
    const store = useDeckbuilderStore.getState();
    try {
      const text = await store.exportDeck();
      setShowExportText(text);
    } catch (err) {
      console.error('Export failed:', err);
    }
  };

  return (
    <div className="min-h-screen bg-game-bg flex flex-col">
      {/* Header */}
      <header className="bg-game-surface border-b border-gray-700 px-6 py-3 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <button
            onClick={() => navigate('/')}
            className="text-gray-400 hover:text-white transition-colors"
          >
            &larr; Home
          </button>
          <h1 className="text-2xl font-bold text-white font-['Cinzel']">
            Hyperdraft Deckbuilder
          </h1>
          <select
            value={currentGame}
            onChange={(e) => handleGameChange(e.target.value as Game)}
            className="bg-gray-800 text-white border border-gray-600 rounded px-3 py-1.5 text-sm hover:border-gray-400 focus:outline-none focus:ring-2 focus:ring-game-accent"
            aria-label="Game"
          >
            {GAMES.map((g) => (
              <option key={g} value={g}>
                {GAME_LABELS[g]}
              </option>
            ))}
          </select>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={handleNew}
            className="px-4 py-2 bg-gray-700 text-white rounded hover:bg-gray-600 transition-colors"
          >
            New
          </button>
          <button
            onClick={() => setShowLoadModal(true)}
            className="px-4 py-2 bg-gray-700 text-white rounded hover:bg-gray-600 transition-colors"
          >
            Load
          </button>
          <button
            onClick={handleSave}
            disabled={isSaving}
            className="px-4 py-2 bg-game-accent text-white rounded hover:bg-red-500 transition-colors disabled:opacity-50"
          >
            {isSaving ? 'Saving...' : 'Save'}
          </button>
        </div>
      </header>

      {/* Error Banner */}
      {error && (
        <div className="bg-red-900/50 border-b border-red-500 px-6 py-2 flex items-center justify-between">
          <span className="text-red-200">{error}</span>
          <button
            onClick={clearError}
            className="text-red-300 hover:text-white"
          >
            &times;
          </button>
        </div>
      )}

      {/* Main Content */}
      <div className="flex-1 flex overflow-hidden">
        {/* Card Browser (Left Panel) */}
        <div className="w-1/2 border-r border-gray-700 flex flex-col">
          <CardBrowser />
        </div>

        {/* Deck Panel (Right Panel) */}
        <div className="w-1/2 flex flex-col">
          <DeckPanel />
        </div>
      </div>

      {/* AI Assist Footer */}
      <AIAssistPanel
        onImport={() => setShowImportModal(true)}
        onExport={handleExport}
      />

      {/* Modals */}
      {showLoadModal && (
        <LoadDeckModal onClose={() => setShowLoadModal(false)} />
      )}

      {showImportModal && (
        <ImportModal onClose={() => setShowImportModal(false)} />
      )}

      {/* Export Text Modal */}
      {showExportText && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-game-surface border border-gray-700 rounded-lg p-6 max-w-lg w-full mx-4">
            <h2 className="text-xl font-bold text-white mb-4">Export Deck</h2>
            <textarea
              readOnly
              value={showExportText}
              className="w-full h-64 p-3 bg-gray-800 border border-gray-600 rounded text-white font-mono text-sm"
              onClick={(e) => (e.target as HTMLTextAreaElement).select()}
            />
            <div className="flex justify-end gap-2 mt-4">
              <button
                onClick={() => {
                  navigator.clipboard.writeText(showExportText);
                }}
                className="px-4 py-2 bg-game-accent text-white rounded hover:bg-red-500 transition-colors"
              >
                Copy to Clipboard
              </button>
              <button
                onClick={() => setShowExportText(null)}
                className="px-4 py-2 bg-gray-700 text-white rounded hover:bg-gray-600 transition-colors"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default Deckbuilder;
