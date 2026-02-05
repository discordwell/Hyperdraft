/**
 * AIAssistPanel Component
 *
 * Footer panel with AI deck building assistance and import/export options.
 * Uses LLM (Ollama) for deck building when available.
 */

import { useState, useEffect } from 'react';
import { useDeckbuilderStore } from '../../stores/deckbuilderStore';
import { deckbuilderAPI } from '../../services/deckbuilderApi';

interface AIAssistPanelProps {
  onImport: () => void;
  onExport: () => void;
}

export function AIAssistPanel({ onImport, onExport }: AIAssistPanelProps) {
  const { isLoading, currentDeck } = useDeckbuilderStore();
  const [prompt, setPrompt] = useState('');
  const [aiLoading, setAiLoading] = useState(false);
  const [aiError, setAiError] = useState<string | null>(null);
  const [aiSuccess, setAiSuccess] = useState<string | null>(null);
  const [llmAvailable, setLlmAvailable] = useState<boolean | null>(null);

  // Check LLM availability on mount
  useEffect(() => {
    deckbuilderAPI.llmStatus().then((status) => {
      setLlmAvailable(status.available);
    }).catch(() => {
      setLlmAvailable(false);
    });
  }, []);

  const handleAIBuild = async () => {
    if (!prompt.trim()) return;

    setAiLoading(true);
    setAiError(null);
    setAiSuccess(null);

    try {
      const result = await deckbuilderAPI.llmBuildDeck(
        prompt,
        currentDeck.colors.length > 0 ? currentDeck.colors : undefined,
        currentDeck.format
      );

      if (result.success && result.deck) {
        // Update the store with the AI-generated deck
        const store = useDeckbuilderStore.getState();
        store.setDeckName(result.deck.name || 'AI Generated Deck');
        store.setDeckArchetype(result.deck.archetype || 'Aggro');
        store.setDeckColors(result.deck.colors || []);
        store.setDeckDescription(result.deck.description || '');

        // Clear existing cards and add new ones
        store.clearDeck();
        for (const entry of result.deck.mainboard || []) {
          store.setCardQuantity(entry.card, entry.qty, false);
        }
        for (const entry of result.deck.sideboard || []) {
          store.setCardQuantity(entry.card, entry.qty, true);
        }

        setAiSuccess('Deck generated! Review and save when ready.');
        setPrompt('');
      } else {
        setAiError(result.error || 'Failed to generate deck');
      }
    } catch (err) {
      setAiError(err instanceof Error ? err.message : 'AI request failed');
    } finally {
      setAiLoading(false);
    }
  };

  return (
    <div className="bg-game-surface border-t border-gray-700 p-4">
      {/* AI Input Row */}
      <div className="flex items-center gap-2 mb-3">
        <div className="flex items-center gap-2 text-gray-400">
          <span className="text-lg">🤖</span>
          <span className="text-sm font-semibold">AI Assist:</span>
        </div>
        <input
          type="text"
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleAIBuild()}
          placeholder="Build me a red aggro deck with goblins..."
          className="flex-1 px-3 py-2 bg-gray-800 border border-gray-600 rounded text-white placeholder-gray-500 focus:outline-none focus:border-game-accent"
        />
        <button
          onClick={handleAIBuild}
          disabled={aiLoading || !prompt.trim()}
          className="px-4 py-2 bg-game-accent text-white rounded hover:bg-red-500 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {aiLoading ? 'Building...' : 'Build'}
        </button>
      </div>

      {/* Status Display */}
      {aiError && (
        <div className="mb-3 text-sm text-yellow-400">{aiError}</div>
      )}
      {aiSuccess && (
        <div className="mb-3 text-sm text-green-400">{aiSuccess}</div>
      )}
      {llmAvailable === false && (
        <div className="mb-3 text-xs text-gray-500">
          AI deck building requires Ollama. Run: <code className="text-gray-400">ollama serve && ollama pull qwen2.5:7b</code>
        </div>
      )}

      {/* Action Buttons Row */}
      <div className="flex items-center gap-2">
        <button
          onClick={onImport}
          disabled={isLoading}
          className="px-3 py-1.5 bg-gray-700 text-white rounded text-sm hover:bg-gray-600 transition-colors disabled:opacity-50"
        >
          Import Deck
        </button>
        <button
          onClick={onExport}
          disabled={isLoading}
          className="px-3 py-1.5 bg-gray-700 text-white rounded text-sm hover:bg-gray-600 transition-colors disabled:opacity-50"
        >
          Export
        </button>
        <div className="flex-1" />
        <span className="text-xs text-gray-500">
          Tip: Click cards in the browser to add them to your deck
        </span>
      </div>
    </div>
  );
}
