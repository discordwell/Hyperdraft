/**
 * LabFilterBar — inline lab-styled filter row (search + sort + chips).
 *
 * Wraps:
 *   - Current-set header line (serif name + mono code/count) and sort controls.
 *   - Search input (form-submit, syncs into `setFilter`).
 *   - 9 energy-type swatches — Grass/Fire/Water/Lightning/Psychic/Fighting/
 *     Darkness/Metal/Colorless. These keep their *real Pokemon TCG colors*
 *     verbatim (per docs/design/brand.md: per-engine semantic encoding stays
 *     in the game's vocabulary; the surrounding chrome is the only thing the
 *     lab port owns).
 *   - Pokemon-only filters (Stage / EX / HP / Retreat) — gated by supertype.
 *   - Trainer subtype chips — gated by supertype === 'Trainer'.
 *   - Guild select — gated by current set having guilds.
 *
 * Decomposed out of PokemonGatherer.tsx in the same wave as LabSetRack.
 */

import { useEffect, useState } from 'react';
import { usePokemonGathererStore } from '../../stores/pokemonGathererStore';
import {
  POKEMON_TYPE_INFO,
  POKEMON_TYPE_ORDER,
  POKEMON_SORT_FIELDS,
  hasActivePokemonFilters,
} from '../../types/pokemonGatherer';
import type {
  PokemonEvolutionStage,
  PokemonSortField,
  PokemonSupertype,
  PokemonTrainerSubtype,
} from '../../types/pokemonGatherer';

const SUPERTYPES: PokemonSupertype[] = ['Pokemon', 'Trainer', 'Energy'];
const TRAINER_SUBTYPES: PokemonTrainerSubtype[] = [
  'Item',
  'Supporter',
  'Stadium',
  'Tool',
];
const STAGES: PokemonEvolutionStage[] = ['Basic', 'Stage 1', 'Stage 2'];

export function LabFilterBar() {
  const {
    currentSet,
    cardsTotal,
    filter,
    sortBy,
    sortOrder,
    setFilter,
    clearFilter,
    setSortBy,
    toggleSortOrder,
  } = usePokemonGathererStore();

  // Local input mirror so the search reads correctly during keystrokes; the
  // store fetch only fires on form submit / clear.
  const [textSearch, setTextSearch] = useState(filter.textSearch ?? '');

  // Keep the local mirror in sync when the store-side filter changes from
  // elsewhere (e.g. Clear filters click, set switch, etc.).
  useEffect(() => {
    setTextSearch(filter.textSearch ?? '');
  }, [filter.textSearch]);

  const hasActiveFilters = hasActivePokemonFilters(filter);
  const showPokemonOnlyFilters = !filter.supertype || filter.supertype === 'Pokemon';
  const showTrainerSubtype = filter.supertype === 'Trainer';
  const guilds = currentSet?.guilds ?? [];

  const handleTextSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setFilter({ textSearch: textSearch || undefined });
  };

  return (
    <div
      style={{
        border: '1px solid var(--rule)',
        background: 'var(--paper-2)',
        padding: '14px 18px',
        display: 'flex',
        flexDirection: 'column',
        gap: 12,
      }}
      data-testid="pokemon-gatherer-filter-bar"
    >
      {/* Header line — current set + result count + sort */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'baseline',
          gap: 14,
          flexWrap: 'wrap',
        }}
      >
        <div>
          <div
            style={{
              fontFamily: 'var(--font-serif)',
              fontSize: 22,
              color: 'var(--ink)',
              letterSpacing: '-.01em',
              lineHeight: 1.1,
            }}
          >
            {currentSet ? currentSet.name : 'Select a set'}
          </div>
          <div
            style={{
              marginTop: 2,
              fontFamily: 'var(--font-mono)',
              fontSize: 11,
              letterSpacing: '.06em',
              color: 'var(--ink-3)',
              fontVariantNumeric: 'tabular-nums',
            }}
          >
            {currentSet
              ? `${cardsTotal} card${cardsTotal !== 1 ? 's' : ''} · ${currentSet.code}`
              : 'No set picked'}
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 10.5,
              fontWeight: 500,
              letterSpacing: '.14em',
              textTransform: 'uppercase',
              color: 'var(--ink-3)',
            }}
          >
            Sort
          </span>
          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value as PokemonSortField)}
            style={selectStyle}
          >
            {POKEMON_SORT_FIELDS.map((f) => (
              <option key={f.value} value={f.value}>
                {f.label}
              </option>
            ))}
          </select>
          <button
            type="button"
            onClick={toggleSortOrder}
            style={chipButtonStyle(false)}
            title={`Sort order: ${sortOrder}`}
          >
            {sortOrder === 'asc' ? '↑ asc' : '↓ desc'}
          </button>
        </div>
      </div>

      {/* Search + supertype + type + stage + EX + HP + retreat (set required) */}
      {currentSet && (
        <div
          style={{
            display: 'flex',
            flexWrap: 'wrap',
            gap: '10px 18px',
            alignItems: 'center',
          }}
        >
          <form
            onSubmit={handleTextSearchSubmit}
            style={{ flex: '1 1 220px', minWidth: 180, maxWidth: 320 }}
          >
            <div style={{ position: 'relative' }}>
              <input
                type="text"
                value={textSearch}
                onChange={(e) => setTextSearch(e.target.value)}
                placeholder="Search Pokémon…"
                style={{ ...inputStyle, paddingRight: 28 }}
              />
              {textSearch && (
                <button
                  type="button"
                  aria-label="Clear search"
                  onClick={() => {
                    setTextSearch('');
                    setFilter({ textSearch: undefined });
                  }}
                  style={{
                    position: 'absolute',
                    right: 4,
                    top: '50%',
                    transform: 'translateY(-50%)',
                    background: 'transparent',
                    border: 'none',
                    color: 'var(--ink-3)',
                    cursor: 'pointer',
                    fontFamily: 'var(--font-mono)',
                    fontSize: 14,
                    padding: '0 6px',
                    lineHeight: 1,
                  }}
                >
                  ×
                </button>
              )}
            </div>
          </form>

          <FilterGroup label="Category">
            {SUPERTYPES.map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => {
                  const next = filter.supertype === s ? undefined : s;
                  const switchedAway = next !== 'Pokemon';
                  setFilter({
                    supertype: next,
                    trainerSubtype: undefined,
                    evolutionStage: switchedAway ? undefined : filter.evolutionStage,
                    isEx: switchedAway ? undefined : filter.isEx,
                    hpMin: switchedAway ? undefined : filter.hpMin,
                    hpMax: switchedAway ? undefined : filter.hpMax,
                    retreatCostMin: switchedAway ? undefined : filter.retreatCostMin,
                    retreatCostMax: switchedAway ? undefined : filter.retreatCostMax,
                  });
                }}
                style={chipButtonStyle(filter.supertype === s)}
              >
                {s}
              </button>
            ))}
          </FilterGroup>

          {showTrainerSubtype && (
            <FilterGroup label="Trainer">
              {TRAINER_SUBTYPES.map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() =>
                    setFilter({
                      trainerSubtype: filter.trainerSubtype === s ? undefined : s,
                    })
                  }
                  style={chipButtonStyle(filter.trainerSubtype === s)}
                >
                  {s}
                </button>
              ))}
            </FilterGroup>
          )}

          {/* Energy-type swatches — Pokemon-specific per-card identity: each
              type retains its real-card color (Grass/Fire/Water/etc.). This is
              the seam where lab chrome around the filter group ends and
              Pokemon's own palette begins. */}
          <FilterGroup label="Type">
            {POKEMON_TYPE_ORDER.map((t) => {
              const info = POKEMON_TYPE_INFO[t];
              const active = filter.pokemonType === t;
              return (
                <button
                  key={t}
                  type="button"
                  onClick={() =>
                    setFilter({ pokemonType: active ? undefined : t })
                  }
                  title={info.label}
                  style={{
                    width: 24,
                    height: 24,
                    borderRadius: '50%',
                    border: active
                      ? '2px solid var(--ink)'
                      : '1px solid var(--rule)',
                    background: info.color,
                    color: '#000',
                    fontFamily: 'var(--font-mono)',
                    fontWeight: 700,
                    fontSize: 10,
                    cursor: 'pointer',
                    padding: 0,
                    display: 'inline-flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    transform: active ? 'scale(1.08)' : 'none',
                    transition: 'transform 120ms ease',
                  }}
                >
                  {info.symbol}
                </button>
              );
            })}
          </FilterGroup>

          {showPokemonOnlyFilters && (
            <>
              <FilterGroup label="Stage">
                {STAGES.map((s) => (
                  <button
                    key={s}
                    type="button"
                    onClick={() =>
                      setFilter({
                        evolutionStage:
                          filter.evolutionStage === s ? undefined : s,
                      })
                    }
                    style={chipButtonStyle(filter.evolutionStage === s)}
                  >
                    {s}
                  </button>
                ))}
              </FilterGroup>

              <FilterGroup label="EX">
                <button
                  type="button"
                  onClick={() =>
                    setFilter({ isEx: filter.isEx === true ? undefined : true })
                  }
                  style={chipButtonStyle(filter.isEx === true, 'sodium')}
                >
                  ex only
                </button>
                <button
                  type="button"
                  onClick={() =>
                    setFilter({ isEx: filter.isEx === false ? undefined : false })
                  }
                  style={chipButtonStyle(filter.isEx === false)}
                >
                  non-ex
                </button>
              </FilterGroup>

              <FilterGroup label="HP">
                <input
                  type="number"
                  min={0}
                  max={400}
                  step={10}
                  placeholder="min"
                  value={filter.hpMin ?? ''}
                  onChange={(e) =>
                    setFilter({
                      hpMin: e.target.value ? parseInt(e.target.value) : undefined,
                    })
                  }
                  style={numberInputStyle}
                />
                <span style={dashStyle}>–</span>
                <input
                  type="number"
                  min={0}
                  max={400}
                  step={10}
                  placeholder="max"
                  value={filter.hpMax ?? ''}
                  onChange={(e) =>
                    setFilter({
                      hpMax: e.target.value ? parseInt(e.target.value) : undefined,
                    })
                  }
                  style={numberInputStyle}
                />
              </FilterGroup>

              <FilterGroup label="Retreat">
                <input
                  type="number"
                  min={0}
                  max={5}
                  placeholder="min"
                  value={filter.retreatCostMin ?? ''}
                  onChange={(e) =>
                    setFilter({
                      retreatCostMin: e.target.value
                        ? parseInt(e.target.value)
                        : undefined,
                    })
                  }
                  style={{ ...numberInputStyle, width: 52 }}
                />
                <span style={dashStyle}>–</span>
                <input
                  type="number"
                  min={0}
                  max={5}
                  placeholder="max"
                  value={filter.retreatCostMax ?? ''}
                  onChange={(e) =>
                    setFilter({
                      retreatCostMax: e.target.value
                        ? parseInt(e.target.value)
                        : undefined,
                    })
                  }
                  style={{ ...numberInputStyle, width: 52 }}
                />
              </FilterGroup>
            </>
          )}

          {guilds.length > 0 && (
            <FilterGroup label="Guild">
              <select
                value={filter.guild ?? ''}
                onChange={(e) => setFilter({ guild: e.target.value || undefined })}
                style={selectStyle}
              >
                <option value="">All</option>
                {guilds.map((g) => (
                  <option key={g} value={g}>
                    {g.charAt(0).toUpperCase() + g.slice(1)}
                  </option>
                ))}
              </select>
            </FilterGroup>
          )}

          {hasActiveFilters && (
            <button
              type="button"
              onClick={() => {
                setTextSearch('');
                clearFilter();
              }}
              style={{
                ...chipButtonStyle(false, 'halt'),
                marginLeft: 'auto',
              }}
            >
              Clear filters
            </button>
          )}
        </div>
      )}
    </div>
  );
}

// === Local helpers ======================================================

function FilterGroup({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div style={{ display: 'inline-flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
      <span
        style={{
          fontFamily: 'var(--font-mono)',
          fontSize: 10.5,
          fontWeight: 500,
          letterSpacing: '.14em',
          textTransform: 'uppercase',
          color: 'var(--ink-3)',
          marginRight: 2,
        }}
      >
        {label}
      </span>
      {children}
    </div>
  );
}

const inputStyle: React.CSSProperties = {
  width: '100%',
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
  border: '1px solid var(--rule)',
  padding: '6px 8px',
  fontFamily: 'var(--font-sans)',
  fontSize: 12,
  color: 'var(--ink)',
  outline: 'none',
  cursor: 'pointer',
};

const numberInputStyle: React.CSSProperties = {
  width: 56,
  background: 'var(--paper)',
  border: '1px solid var(--rule)',
  padding: '6px 8px',
  fontFamily: 'var(--font-mono)',
  fontSize: 12,
  color: 'var(--ink)',
  outline: 'none',
  fontVariantNumeric: 'tabular-nums',
};

const dashStyle: React.CSSProperties = {
  color: 'var(--ink-3)',
  fontFamily: 'var(--font-mono)',
  fontSize: 12,
};

function chipButtonStyle(
  active: boolean,
  tone: 'ink' | 'sodium' | 'halt' = 'ink',
): React.CSSProperties {
  const activeBg =
    tone === 'sodium' ? 'var(--sodium)' : tone === 'halt' ? 'var(--halt)' : 'var(--ink)';
  return {
    fontFamily: 'var(--font-mono)',
    fontSize: 11,
    fontWeight: 500,
    letterSpacing: '.12em',
    textTransform: 'uppercase',
    padding: '6px 10px',
    background: active ? activeBg : 'var(--paper)',
    color: active ? 'var(--paper)' : tone === 'halt' ? 'var(--halt)' : 'var(--ink-2)',
    border: `1px solid ${active ? activeBg : tone === 'halt' ? 'var(--halt)' : 'var(--rule)'}`,
    cursor: 'pointer',
  };
}
