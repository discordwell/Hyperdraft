/**
 * DeckPanel Component — lab-posture deck rail header + stats; per-engine
 * deck list underneath.
 *
 * Phase C / buildplan item 9. The deck-meta input cluster (name / archetype
 * / format / description) is the *chrome* that wraps the per-engine deck
 * card list. Per `docs/design/brand.md`, the chrome ports to lab tokens
 * while the deck list interior keeps its per-engine vocabulary (card names
 * grouped by engine-specific types).
 */

import { useDeckbuilderStore } from '../../stores/deckbuilderStore';
import { DeckStats } from './DeckStats';
import { DeckList } from './DeckList';
import { ARCHETYPES, FORMATS } from '../../types/deckbuilder';

export function DeckPanel() {
  const {
    currentDeck,
    setDeckName,
    setDeckArchetype,
    setDeckFormat,
    setDeckDescription,
  } = useDeckbuilderStore();

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        minHeight: 0,
        overflow: 'hidden',
      }}
    >
      {/* ─── Deck Header — lab tokens =============================== */}
      <div
        style={{
          padding: 18,
          borderBottom: '1px solid var(--rule)',
          background: 'var(--paper-2)',
        }}
        data-testid="deckbuilder-deck-header"
      >
        <span
          style={{
            display: 'block',
            fontFamily: 'var(--font-mono)',
            fontSize: 10.5,
            letterSpacing: '.14em',
            textTransform: 'uppercase',
            color: 'var(--ink-3)',
            marginBottom: 6,
          }}
        >
          Deck
        </span>
        <input
          type="text"
          value={currentDeck.name}
          onChange={(e) => setDeckName(e.target.value)}
          style={{
            width: '100%',
            background: 'var(--paper)',
            border: '1px solid var(--rule)',
            padding: '10px 12px',
            fontFamily: 'var(--font-serif)',
            fontSize: 22,
            fontWeight: 400,
            letterSpacing: '-.01em',
            color: 'var(--ink)',
            outline: 'none',
          }}
          placeholder="Untitled deck"
          aria-label="Deck name"
        />

        {/* Archetype & Format — paired select row, lab tokens */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginTop: 10 }}>
          <select
            value={currentDeck.archetype}
            onChange={(e) => setDeckArchetype(e.target.value)}
            style={labSelectStyle}
            aria-label="Archetype"
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
            style={labSelectStyle}
            aria-label="Format"
          >
            {FORMATS.map((fmt) => (
              <option key={fmt} value={fmt}>
                {fmt}
              </option>
            ))}
          </select>
        </div>

        <textarea
          value={currentDeck.description}
          onChange={(e) => setDeckDescription(e.target.value)}
          placeholder="Description — what does this deck want to do?"
          style={{
            width: '100%',
            marginTop: 10,
            padding: '8px 12px',
            background: 'var(--paper)',
            border: '1px solid var(--rule)',
            fontFamily: 'var(--font-sans)',
            fontSize: 13,
            color: 'var(--ink)',
            outline: 'none',
            resize: 'none',
            height: 56,
            lineHeight: 1.45,
          }}
          aria-label="Description"
        />
      </div>

      {/* ─── Stats sidebar — lab tokens (composed inside DeckStats) === */}
      <DeckStats />

      {/* ─── Deck list — PER-ENGINE BODY (untouched grouping; card names
          stay in per-engine vocabulary) =============================== */}
      <DeckList />
    </div>
  );
}

const labSelectStyle: React.CSSProperties = {
  background: 'var(--paper)',
  color: 'var(--ink)',
  border: '1px solid var(--rule)',
  padding: '6px 10px',
  fontFamily: 'var(--font-mono)',
  fontSize: 12,
  outline: 'none',
};
