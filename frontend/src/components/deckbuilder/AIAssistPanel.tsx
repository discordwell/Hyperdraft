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

// Archetype enum mirrors the W3 /hybrid/build route's pattern check.
const HYBRID_ARCHETYPES = ['Aggro', 'Control', 'Midrange', 'Tempo', 'Ramp'] as const;
type HybridArchetype = typeof HYBRID_ARCHETYPES[number];
const HYBRID_COLORS: ReadonlyArray<{ code: string; label: string }> = [
  { code: 'W', label: 'W' },
  { code: 'U', label: 'U' },
  { code: 'B', label: 'B' },
  { code: 'R', label: 'R' },
  { code: 'G', label: 'G' },
];

export function AIAssistPanel({ onImport, onExport }: AIAssistPanelProps) {
  const { isLoading, currentDeck } = useDeckbuilderStore();
  const [prompt, setPrompt] = useState('');
  const [aiLoading, setAiLoading] = useState(false);
  const [aiError, setAiError] = useState<string | null>(null);
  const [aiSuccess, setAiSuccess] = useState<string | null>(null);
  const [llmAvailable, setLlmAvailable] = useState<boolean | null>(null);

  // Hybrid-build state. Defaults are intentionally aligned with the
  // /hybrid/build smoke-test in the round-10 plan (Aggro / mono-R / FDN)
  // so a first-time click on a clean session yields a working deck.
  const [hybridArchetype, setHybridArchetype] = useState<HybridArchetype>('Aggro');
  const [hybridColors, setHybridColors] = useState<string[]>(['R']);
  const [hybridSetCodesInput, setHybridSetCodesInput] = useState<string>('FDN');
  const [hybridLoading, setHybridLoading] = useState(false);
  const [swapAudit, setSwapAudit] = useState<string | null>(null);

  const toggleHybridColor = (code: string) => {
    setHybridColors((prev) =>
      prev.includes(code) ? prev.filter((c) => c !== code) : [...prev, code]
    );
  };

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

  const handleHybridBuild = async () => {
    const setCodes = hybridSetCodesInput
      .split(',')
      .map((s) => s.trim().toUpperCase())
      .filter(Boolean);

    if (setCodes.length === 0) {
      setAiError('Hybrid build needs at least one set code (e.g. FDN)');
      return;
    }
    if (hybridColors.length === 0) {
      setAiError('Hybrid build needs at least one color');
      return;
    }

    setHybridLoading(true);
    setAiError(null);
    setAiSuccess(null);
    setSwapAudit(null);

    try {
      const result = await deckbuilderAPI.hybridBuildDeck(
        hybridArchetype,
        hybridColors,
        setCodes,
      );

      if (result.success && result.deck) {
        // Reuse the same store-update logic as the LLM path above so
        // the deck panel populates identically.
        const store = useDeckbuilderStore.getState();
        store.setDeckName(result.deck.name || 'Hybrid Deck');
        store.setDeckArchetype(result.deck.archetype || hybridArchetype);
        store.setDeckColors(result.deck.colors || hybridColors);
        store.setDeckDescription(result.deck.description || '');

        store.clearDeck();
        for (const entry of result.deck.mainboard || []) {
          store.setCardQuantity(entry.card, entry.qty, false);
        }
        for (const entry of result.deck.sideboard || []) {
          store.setCardQuantity(entry.card, entry.qty, true);
        }

        const swaps = result.swaps ?? [];
        if (swaps.length > 0) {
          const first = swaps[0];
          const tail = swaps.length > 1 ? `, ... (+${swaps.length - 1} more)` : '';
          setSwapAudit(`AI swapped ${swaps.length} card${swaps.length === 1 ? '' : 's'}: ${first.out} -> ${first.in}${tail}`);
        }
        setAiSuccess('Hybrid deck generated! Review and save when ready.');
      } else {
        setAiError(result.error || 'Failed to generate hybrid deck');
      }
    } catch (err) {
      setAiError(err instanceof Error ? err.message : 'Hybrid build request failed');
    } finally {
      setHybridLoading(false);
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

      {/* Hybrid Build Row — heuristic skeleton + LLM polish */}
      <div className="flex flex-wrap items-center gap-2 mb-3">
        <div className="flex items-center gap-2 text-gray-400">
          <span className="text-lg">⚙️</span>
          <span className="text-sm font-semibold">Hybrid:</span>
        </div>
        <select
          value={hybridArchetype}
          onChange={(e) => setHybridArchetype(e.target.value as HybridArchetype)}
          className="px-2 py-1.5 bg-gray-800 border border-gray-600 rounded text-white text-sm focus:outline-none focus:border-game-accent"
          aria-label="Archetype"
        >
          {HYBRID_ARCHETYPES.map((a) => (
            <option key={a} value={a}>{a}</option>
          ))}
        </select>
        <div className="flex items-center gap-1" role="group" aria-label="Colors">
          {HYBRID_COLORS.map(({ code, label }) => {
            const active = hybridColors.includes(code);
            return (
              <button
                key={code}
                type="button"
                onClick={() => toggleHybridColor(code)}
                className={`w-7 h-7 rounded text-xs font-bold transition-colors ${
                  active
                    ? 'bg-game-accent text-white'
                    : 'bg-gray-800 border border-gray-600 text-gray-400 hover:bg-gray-700'
                }`}
                aria-pressed={active}
              >
                {label}
              </button>
            );
          })}
        </div>
        <input
          type="text"
          value={hybridSetCodesInput}
          onChange={(e) => setHybridSetCodesInput(e.target.value)}
          placeholder="Set codes (e.g. FDN,WOE)"
          className="flex-1 min-w-[120px] px-3 py-1.5 bg-gray-800 border border-gray-600 rounded text-white placeholder-gray-500 text-sm focus:outline-none focus:border-game-accent"
          aria-label="Set codes"
        />
        <button
          onClick={handleHybridBuild}
          disabled={hybridLoading || hybridColors.length === 0 || !hybridSetCodesInput.trim()}
          className="px-4 py-2 bg-game-accent text-white rounded hover:bg-red-500 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {hybridLoading ? 'Building...' : 'Hybrid Build'}
        </button>
      </div>

      {/* Swap audit subtitle — populated when LLM polish makes swaps */}
      {swapAudit && (
        <div className="mb-3 text-xs text-gray-400">{swapAudit}</div>
      )}

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
