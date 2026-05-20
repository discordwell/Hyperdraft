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
    <div className="min-h-screen bg-brand-ink flex flex-col text-brand-cream">
      {/* Header — brand-aware local bar (Deckbuilder doesn't use AppShell
          because the deck-edit flow wants its own header layout with the
          Save/Load/New action cluster). */}
      <header className="bg-brand-obsidian/85 backdrop-blur-xl border-b border-brand-hairline/60 px-6 py-3 flex items-center justify-between sticky top-0 z-30">
        <div className="flex items-center gap-4">
          <button
            onClick={() => navigate('/')}
            className="text-brand-chalk hover:text-brand-foil transition-colors text-sm tracking-wide"
          >
            ← Lobby
          </button>
          <h1 className="text-xl font-display font-bold text-brand-cream">
            Deckbuilder
          </h1>
          <select
            value={currentGame}
            onChange={(e) => handleGameChange(e.target.value as Game)}
            className="bg-brand-obsidian text-brand-cream border border-brand-hairline px-3 py-1.5 text-sm hover:border-brand-foil/40 focus:outline-none focus:border-brand-foil/60"
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
            className="px-4 py-2 bg-brand-shelf hover:bg-brand-glass border border-brand-hairline hover:border-brand-foil/40 text-brand-cream transition-colors text-sm"
          >
            New
          </button>
          <button
            onClick={() => setShowLoadModal(true)}
            className="px-4 py-2 bg-brand-shelf hover:bg-brand-glass border border-brand-hairline hover:border-brand-foil/40 text-brand-cream transition-colors text-sm"
          >
            Load
          </button>
          <button
            onClick={handleSave}
            disabled={isSaving}
            className="px-4 py-2 bg-gradient-to-b from-brand-foil-bright via-brand-foil to-brand-foil-deep text-brand-ink shadow-brand-foil hover:shadow-brand-foil-strong transition-all disabled:opacity-50 text-sm font-medium"
          >
            {isSaving ? 'Saving…' : 'Save'}
          </button>
        </div>
      </header>

      {/* Error Banner */}
      {error && (
        <div className="bg-brand-ember/10 border-b border-brand-ember/50 px-6 py-2 flex items-center justify-between">
          <span className="text-brand-ember text-sm">{error}</span>
          <button
            onClick={clearError}
            className="text-brand-ember hover:text-brand-cream"
          >
            ×
          </button>
        </div>
      )}

      {/* Main Content */}
      <div className="flex-1 flex overflow-hidden">
        <div className="w-1/2 border-r border-brand-hairline/60 flex flex-col">
          <CardBrowser />
        </div>
        <div className="w-1/2 flex flex-col">
          <DeckPanel />
        </div>
      </div>

      <AIAssistPanel
        onImport={() => setShowImportModal(true)}
        onExport={handleExport}
      />

      {showLoadModal && <LoadDeckModal onClose={() => setShowLoadModal(false)} />}
      {showImportModal && <ImportModal onClose={() => setShowImportModal(false)} />}

      {/* Export Text Modal */}
      {showExportText && (
        <div className="fixed inset-0 bg-brand-ink/80 backdrop-blur-sm flex items-center justify-center z-50">
          <div className="bg-brand-obsidian border border-brand-hairline brand-frame p-6 max-w-lg w-full mx-4 shadow-brand-tile">
            <p className="brand-eyebrow mb-2">Export</p>
            <h2 className="text-xl font-display font-bold text-brand-cream mb-4">Export deck</h2>
            <textarea
              readOnly
              value={showExportText}
              className="w-full h-64 p-3 bg-brand-ink border border-brand-hairline text-brand-cream brand-mono text-sm focus:outline-none focus:border-brand-foil/60"
              onClick={(e) => (e.target as HTMLTextAreaElement).select()}
            />
            <div className="flex justify-end gap-2 mt-4">
              <button
                onClick={() => navigator.clipboard.writeText(showExportText)}
                className="px-4 py-2 bg-gradient-to-b from-brand-foil-bright via-brand-foil to-brand-foil-deep text-brand-ink shadow-brand-foil hover:shadow-brand-foil-strong transition-all text-sm font-medium"
              >
                Copy to clipboard
              </button>
              <button
                onClick={() => setShowExportText(null)}
                className="px-4 py-2 bg-brand-shelf hover:bg-brand-glass border border-brand-hairline text-brand-cream transition-colors text-sm"
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
