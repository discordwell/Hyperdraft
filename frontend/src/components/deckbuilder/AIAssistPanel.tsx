/**
 * AIAssistPanel Component — lab-posture footer (Phase C / buildplan item 9).
 *
 * "AI Assist" + "Hybrid Build" rows sit in the bottom chrome strip. Per the
 * brief: mono caption, ink-outlined Build buttons, lab tokens. The W/U/B/R/G
 * pip cluster keeps its per-engine MTG color semantics — Hybrid Build is an
 * MTG-only flow (build a deck from a set code + colour identity), so the
 * pip colours encoding MTG colour identity is correct vocabulary.
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
    <div
      style={{
        background: 'var(--paper)',
        borderTop: '1px solid var(--rule)',
        padding: '14px 32px 16px',
      }}
      data-testid="deckbuilder-ai-assist"
    >
      {/* AI Input Row — lab posture */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
        <span style={captionStyle}>AI Assist</span>
        <input
          type="text"
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleAIBuild()}
          placeholder="Build me a red aggro deck with goblins..."
          style={inputStyle}
          aria-label="AI prompt"
        />
        <button
          onClick={handleAIBuild}
          disabled={aiLoading || !prompt.trim()}
          style={primaryButtonStyle(aiLoading || !prompt.trim())}
        >
          {aiLoading ? 'Building…' : 'Build'}
        </button>
      </div>

      {/* Hybrid Build Row — heuristic skeleton + LLM polish */}
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          alignItems: 'center',
          gap: 8,
          marginBottom: 8,
        }}
      >
        <span style={captionStyle}>Hybrid</span>
        <select
          value={hybridArchetype}
          onChange={(e) => setHybridArchetype(e.target.value as HybridArchetype)}
          style={selectStyle}
          aria-label="Archetype"
        >
          {HYBRID_ARCHETYPES.map((a) => (
            <option key={a} value={a}>{a}</option>
          ))}
        </select>

        {/* MTG colour pips — per-engine vocabulary (W/U/B/R/G keep their
            MTG colour identity hues; lab tokens drive the surrounding
            chrome but the pip semantics are MTG's). */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 4 }} role="group" aria-label="Colors">
          {HYBRID_COLORS.map(({ code, label }) => {
            const active = hybridColors.includes(code);
            return (
              <button
                key={code}
                type="button"
                onClick={() => toggleHybridColor(code)}
                style={{
                  width: 26,
                  height: 26,
                  background: active ? 'var(--ink)' : 'var(--paper)',
                  color: active ? 'var(--paper)' : 'var(--ink-2)',
                  border: `1px solid ${active ? 'var(--ink)' : 'var(--rule)'}`,
                  fontFamily: 'var(--font-mono)',
                  fontSize: 11,
                  fontWeight: 600,
                  cursor: 'pointer',
                  letterSpacing: '.04em',
                }}
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
          style={{ ...inputStyle, flex: '0 1 220px', minWidth: 160 }}
          aria-label="Set codes"
        />

        <button
          onClick={handleHybridBuild}
          disabled={
            hybridLoading || hybridColors.length === 0 || !hybridSetCodesInput.trim()
          }
          style={primaryButtonStyle(
            hybridLoading || hybridColors.length === 0 || !hybridSetCodesInput.trim(),
          )}
        >
          {hybridLoading ? 'Building…' : 'Hybrid Build'}
        </button>
      </div>

      {/* Swap audit subtitle — populated when LLM polish makes swaps */}
      {swapAudit && (
        <div
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 11,
            color: 'var(--ink-3)',
            marginBottom: 8,
            letterSpacing: '.04em',
          }}
        >
          {swapAudit}
        </div>
      )}

      {/* Status Display — lab posture */}
      {aiError && (
        <div
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 11,
            color: 'var(--sodium)',
            marginBottom: 8,
            letterSpacing: '.04em',
          }}
        >
          · {aiError}
        </div>
      )}
      {aiSuccess && (
        <div
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 11,
            color: 'var(--acid)',
            marginBottom: 8,
            letterSpacing: '.04em',
          }}
        >
          · {aiSuccess}
        </div>
      )}
      {llmAvailable === false && (
        <div
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 10.5,
            color: 'var(--ink-3)',
            marginBottom: 8,
            letterSpacing: '.04em',
          }}
        >
          AI deck building requires Ollama. Run:{' '}
          <code style={{ color: 'var(--ink-2)' }}>
            ollama serve && ollama pull qwen2.5:7b
          </code>
        </div>
      )}

      {/* Action Buttons Row */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 4 }}>
        <button onClick={onImport} disabled={isLoading} style={ghostButtonStyle(isLoading)}>
          Import Deck
        </button>
        <button onClick={onExport} disabled={isLoading} style={ghostButtonStyle(isLoading)}>
          Export
        </button>
        <div style={{ flex: 1 }} />
        <span
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 10.5,
            letterSpacing: '.08em',
            color: 'var(--ink-3)',
          }}
        >
          Click cards in the browser to add them to your deck
        </span>
      </div>
    </div>
  );
}

const captionStyle: React.CSSProperties = {
  fontFamily: 'var(--font-mono)',
  fontSize: 10.5,
  fontWeight: 500,
  letterSpacing: '.14em',
  textTransform: 'uppercase',
  color: 'var(--ink-3)',
  minWidth: 70,
};

const inputStyle: React.CSSProperties = {
  flex: 1,
  background: 'var(--paper)',
  border: '1px solid var(--rule)',
  padding: '8px 10px',
  fontFamily: 'var(--font-sans)',
  fontSize: 13,
  color: 'var(--ink)',
  outline: 'none',
};

const selectStyle: React.CSSProperties = {
  background: 'var(--paper)',
  color: 'var(--ink)',
  border: '1px solid var(--rule)',
  padding: '6px 10px',
  fontFamily: 'var(--font-mono)',
  fontSize: 12,
  outline: 'none',
};

function primaryButtonStyle(disabled: boolean): React.CSSProperties {
  return {
    fontFamily: 'var(--font-mono)',
    fontSize: 11,
    fontWeight: 500,
    letterSpacing: '.12em',
    textTransform: 'uppercase',
    padding: '8px 14px',
    background: disabled ? 'var(--ink-2)' : 'var(--ink)',
    color: 'var(--paper)',
    border: '1px solid var(--ink)',
    cursor: disabled ? 'not-allowed' : 'pointer',
    opacity: disabled ? 0.6 : 1,
  };
}

function ghostButtonStyle(disabled: boolean): React.CSSProperties {
  return {
    fontFamily: 'var(--font-mono)',
    fontSize: 11,
    fontWeight: 500,
    letterSpacing: '.12em',
    textTransform: 'uppercase',
    padding: '6px 12px',
    background: 'transparent',
    color: 'var(--ink-2)',
    border: '1px solid var(--rule)',
    cursor: disabled ? 'not-allowed' : 'pointer',
    opacity: disabled ? 0.5 : 1,
  };
}
