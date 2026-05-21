/**
 * LabSetRack — hairline-ruled left rail listing Pokémon sets.
 *
 * Lab chrome only (paper / ink / sodium / hairline rules). The set rows are
 * grouped by Starter / Beyond when no set-type filter is active, otherwise
 * flat. Selecting a row dispatches `selectSet(code)`; chip clicks dispatch
 * `setSetTypeFilter`.
 *
 * Decomposed out of PokemonGatherer.tsx (see commit `42bcb0c8` for the
 * Deckbuilder pattern this mirrors).
 */

import { useMemo } from 'react';
import { usePokemonGathererStore } from '../../stores/pokemonGathererStore';
import {
  POKEMON_SET_TYPE_INFO,
  type PokemonSetInfo,
} from '../../types/pokemonGatherer';

type PokemonSetType = 'starter' | 'beyond';
const SET_TYPES: PokemonSetType[] = ['starter', 'beyond'];

export function LabSetRack() {
  const {
    sets,
    setsLoading,
    currentSet,
    setTypeFilter,
    selectSet,
    setSetTypeFilter,
  } = usePokemonGathererStore();

  const grouped = useMemo(() => {
    return sets.reduce(
      (acc, s) => {
        const t = s.set_type as PokemonSetType;
        if (!acc[t]) acc[t] = [];
        acc[t].push(s);
        return acc;
      },
      {} as Record<PokemonSetType, PokemonSetInfo[]>,
    );
  }, [sets]);

  const totalSetCards = useMemo(
    () => sets.reduce((sum, s) => sum + s.card_count, 0),
    [sets],
  );

  return (
    <aside
      style={{
        border: '1px solid var(--rule)',
        background: 'var(--paper-2)',
        position: 'sticky',
        top: 88,
        maxHeight: 'calc(100vh - 120px)',
        overflowY: 'auto',
      }}
      data-testid="pokemon-gatherer-set-rack"
    >
      {/* Header — eyebrow + mono count line */}
      <div
        style={{
          padding: '14px 16px 10px',
          borderBottom: '1px solid var(--rule)',
        }}
      >
        <div
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 10.5,
            fontWeight: 500,
            letterSpacing: '.14em',
            textTransform: 'uppercase',
            color: 'var(--ink-3)',
            marginBottom: 4,
          }}
        >
          Sets
        </div>
        <div
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 11,
            color: 'var(--ink-3)',
            letterSpacing: '.04em',
          }}
        >
          {sets.length} · {totalSetCards.toLocaleString()} cards
        </div>
      </div>

      {/* Set-type filter chips */}
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          gap: 6,
          padding: '10px 12px',
          borderBottom: '1px solid var(--rule)',
        }}
      >
        <button
          type="button"
          onClick={() => setSetTypeFilter(null)}
          style={chipButtonStyle(!setTypeFilter)}
        >
          All
        </button>
        {SET_TYPES.map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setSetTypeFilter(t)}
            style={chipButtonStyle(setTypeFilter === t)}
          >
            {POKEMON_SET_TYPE_INFO[t].label}
          </button>
        ))}
      </div>

      {/* Set list — grouped (Starter / Beyond) or flat depending on filter */}
      <div style={{ padding: '8px 0' }}>
        {setsLoading ? (
          <LoadingRow label="Loading sets…" />
        ) : setTypeFilter ? (
          <div>
            {sets.map((s) =>
              renderSetRow(s, currentSet?.code === s.code, selectSet),
            )}
          </div>
        ) : (
          SET_TYPES.map((type) => {
            const list = grouped[type] ?? [];
            if (list.length === 0) return null;
            const info = POKEMON_SET_TYPE_INFO[type];
            return (
              <div key={type} style={{ marginBottom: 8 }}>
                <div
                  style={{
                    padding: '8px 16px 6px',
                    fontFamily: 'var(--font-mono)',
                    fontSize: 10.5,
                    fontWeight: 500,
                    letterSpacing: '.14em',
                    textTransform: 'uppercase',
                    color: 'var(--ink-3)',
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'baseline',
                  }}
                >
                  <span>{info.label}</span>
                  <span style={{ color: 'var(--ink-3)' }}>{list.length}</span>
                </div>
                <div>
                  {list.map((s) =>
                    renderSetRow(s, currentSet?.code === s.code, selectSet),
                  )}
                </div>
              </div>
            );
          })
        )}
      </div>
    </aside>
  );
}

// === Local helpers ======================================================
// Mirrored across Lab* sub-components on purpose (Deckbuilder pattern: each
// component owns the small style helpers it needs; consolidation would mean
// dragging a shared module across the seam).

function chipButtonStyle(active: boolean): React.CSSProperties {
  return {
    fontFamily: 'var(--font-mono)',
    fontSize: 11,
    fontWeight: 500,
    letterSpacing: '.12em',
    textTransform: 'uppercase',
    padding: '6px 10px',
    background: active ? 'var(--ink)' : 'var(--paper)',
    color: active ? 'var(--paper)' : 'var(--ink-2)',
    border: `1px solid ${active ? 'var(--ink)' : 'var(--rule)'}`,
    cursor: 'pointer',
  };
}

function LoadingRow({ label }: { label: string }) {
  return (
    <div
      style={{
        padding: '16px 18px',
        fontFamily: 'var(--font-mono)',
        fontSize: 11,
        letterSpacing: '.14em',
        textTransform: 'uppercase',
        color: 'var(--ink-3)',
        display: 'flex',
        alignItems: 'center',
        gap: 10,
      }}
    >
      <span
        style={{
          width: 10,
          height: 10,
          borderRadius: '50%',
          background: 'var(--sodium)',
          animation: 'pulse 1.6s ease-in-out infinite',
        }}
      />
      {label}
    </div>
  );
}

// Set-row renderer used by both grouped + flat layouts. Returns a button
// styled as a hairline-ruled rack row.
function renderSetRow(
  s: PokemonSetInfo,
  active: boolean,
  onSelect: (code: string) => void,
) {
  return (
    <button
      key={s.code}
      type="button"
      onClick={() => onSelect(s.code)}
      style={{
        display: 'grid',
        gridTemplateColumns: '1fr auto',
        gap: 8,
        alignItems: 'baseline',
        width: '100%',
        textAlign: 'left',
        padding: '10px 16px',
        background: active ? 'var(--ink)' : 'transparent',
        color: active ? 'var(--paper)' : 'var(--ink)',
        border: 'none',
        borderTop: '1px solid var(--rule-2)',
        cursor: 'pointer',
        fontFamily: 'var(--font-sans)',
      }}
      onMouseEnter={(e) => {
        if (!active) {
          e.currentTarget.style.background =
            'color-mix(in oklab, var(--sodium) 6%, transparent)';
        }
      }}
      onMouseLeave={(e) => {
        if (!active) e.currentTarget.style.background = 'transparent';
      }}
    >
      <span style={{ display: 'flex', flexDirection: 'column', gap: 2, minWidth: 0 }}>
        <span
          style={{
            fontFamily: 'var(--font-serif)',
            fontSize: 15,
            letterSpacing: '-.01em',
            color: active ? 'var(--paper)' : 'var(--ink)',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
        >
          {s.name}
        </span>
        <span
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 10.5,
            letterSpacing: '.08em',
            textTransform: 'uppercase',
            color: active ? 'var(--paper)' : 'var(--ink-3)',
          }}
        >
          {s.code}
        </span>
      </span>
      <span
        style={{
          fontFamily: 'var(--font-mono)',
          fontSize: 11,
          fontVariantNumeric: 'tabular-nums',
          color: active ? 'var(--paper)' : 'var(--ink-3)',
        }}
      >
        {s.card_count}
      </span>
    </button>
  );
}
