/**
 * PokemonGatherer — lab-port library surface (buildplan follow-up 11b).
 *
 * Between-games library surface — full lab posture (paper / ink / sodium,
 * Instrument Serif headings, Geist Mono telemetry, hairline rules). Mirrors
 * the C2 Replays port: caption rail at top, ink-ruled masthead, `01 SECTION`
 * head with a sodium italic word in the title, hairline-ruled set rack, an
 * inline filter row, and the existing card-cell grid below it.
 *
 * The per-card identity (real Pokemon card art via PokemonCardCell, per-type
 * energy swatches — Grass/Fire/Water/Lightning/Psychic/Fighting/Darkness/
 * Metal/Colorless) is preserved verbatim; that's the *body* of this surface.
 * Lab chrome wraps it. The seam: meta-frame outside, game identity inside,
 * per docs/design/brand.md.
 *
 * The previous brand-* / bg-gray-* Tailwind chrome on this page has been
 * replaced with inline lab tokens; the PokemonCardCell + PokemonCardDetail-
 * Modal children own their own internal chrome (out of scope here).
 */

import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { usePokemonGathererStore } from '../stores/pokemonGathererStore';
import {
  POKEMON_TYPE_INFO,
  POKEMON_TYPE_ORDER,
  POKEMON_SET_TYPE_INFO,
  POKEMON_SORT_FIELDS,
  hasActivePokemonFilters,
} from '../types/pokemonGatherer';
import type {
  PokemonEvolutionStage,
  PokemonSetInfo,
  PokemonSortField,
  PokemonSupertype,
  PokemonTrainerSubtype,
} from '../types/pokemonGatherer';
import { PokemonCardCell, PokemonCardDetailModal } from '../components/pokemon-gatherer';

type PokemonSetType = 'starter' | 'beyond';

const SET_TYPES: PokemonSetType[] = ['starter', 'beyond'];
const SUPERTYPES: PokemonSupertype[] = ['Pokemon', 'Trainer', 'Energy'];
const TRAINER_SUBTYPES: PokemonTrainerSubtype[] = ['Item', 'Supporter', 'Stadium', 'Tool'];
const STAGES: PokemonEvolutionStage[] = ['Basic', 'Stage 1', 'Stage 2'];

export function PokemonGatherer() {
  const navigate = useNavigate();
  const {
    sets,
    setsLoading,
    setsError,
    currentSet,
    cards,
    cardsTotal,
    cardsLoading,
    cardsHasMore,
    filter,
    sortBy,
    sortOrder,
    setTypeFilter,
    loadSets,
    selectSet,
    setFilter,
    clearFilter,
    setSortBy,
    toggleSortOrder,
    selectCard,
    loadMoreCards,
    setSetTypeFilter,
  } = usePokemonGathererStore();

  // Local input mirror so the search reads correctly during keystrokes; the
  // store fetch only fires on form submit / clear. (Matches PokemonFilterBar
  // behaviour.)
  const [textSearch, setTextSearch] = useState(filter.textSearch ?? '');

  useEffect(() => {
    loadSets();
  }, [loadSets]);

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

  const hasActiveFilters = hasActivePokemonFilters(filter);
  const showPokemonOnlyFilters = !filter.supertype || filter.supertype === 'Pokemon';
  const showTrainerSubtype = filter.supertype === 'Trainer';
  const guilds = currentSet?.guilds ?? [];

  const handleTextSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setFilter({ textSearch: textSearch || undefined });
  };

  const totalSetCards = useMemo(
    () => sets.reduce((sum, s) => sum + s.card_count, 0),
    [sets],
  );

  return (
    <div style={{ background: 'var(--paper)', color: 'var(--ink)', minHeight: '100vh' }}>
      {/* ─── Caption rail (fixed crumb at top, like a printed-book header) */}
      <div
        style={{
          position: 'fixed',
          top: 14,
          left: '50%',
          transform: 'translateX(-50%)',
          fontFamily: 'var(--font-mono)',
          fontSize: 10.5,
          letterSpacing: '.14em',
          textTransform: 'uppercase',
          color: 'var(--ink-3)',
          background: 'var(--paper)',
          padding: '6px 14px',
          border: '1px solid var(--rule)',
          zIndex: 10,
        }}
      >
        <b style={{ color: 'var(--ink)', fontWeight: 500 }}>HD-PKM-GATHERER</b>
        &nbsp;·&nbsp; POKÉMON &nbsp;·&nbsp; LIBRARY &nbsp;·&nbsp; v4.7
      </div>

      <main
        style={{
          maxWidth: 1240,
          margin: '0 auto',
          padding: '88px 56px 160px',
          position: 'relative',
        }}
      >
        {/* ─── Masthead ───────────────────────────────────────────────── */}
        <header
          style={{
            display: 'grid',
            gridTemplateColumns: '1fr auto',
            alignItems: 'end',
            borderTop: '1.5px solid var(--ink)',
            borderBottom: '1.5px solid var(--ink)',
            padding: '18px 0 22px',
            marginBottom: 40,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 14, flexWrap: 'wrap' }}>
            <span
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: 12,
                fontWeight: 500,
                letterSpacing: '.12em',
                textTransform: 'uppercase',
                color: 'var(--ink-2)',
              }}
            >
              HYPERDRAFT
            </span>
            <span
              style={{
                fontFamily: 'var(--font-serif)',
                fontSize: 34,
                color: 'var(--ink)',
                letterSpacing: '-.02em',
                lineHeight: 1,
              }}
            >
              / Pokémon{' '}
              <em style={{ fontStyle: 'italic', color: 'var(--ink)' }}>Gatherer</em>
            </span>
          </div>
          <span
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 12,
              fontWeight: 500,
              letterSpacing: '.06em',
              color: 'var(--ink-2)',
              textAlign: 'right',
            }}
          >
            v4.7 · {sets.length} sets · {totalSetCards.toLocaleString()} cards
          </span>
        </header>

        {/* ─── Section 01 · Browse ─────────────────────────────────────── */}
        <section>
          <SectionHead
            num="01"
            title={
              <>
                Pokémon <em style={{ color: 'var(--sodium)', fontStyle: 'italic' }}>library</em>.
              </>
            }
            meta="The SV starter pack plus Beyond crossover sets. Pick a set on the left, narrow with type / stage / HP, tap a card to read it whole."
          />

          {/* Sets-error band */}
          {setsError && (
            <div
              style={{
                marginTop: 24,
                border: '1px solid var(--halt)',
                background: 'color-mix(in oklab, var(--halt) 8%, transparent)',
                padding: '12px 16px',
                fontSize: 13,
                color: 'var(--halt)',
                fontFamily: 'var(--font-mono)',
                letterSpacing: '.04em',
              }}
            >
              {setsError}
            </div>
          )}

          {/* Sets rack + cards body */}
          <div
            style={{
              marginTop: 24,
              display: 'grid',
              gridTemplateColumns: '260px 1fr',
              gap: 20,
              alignItems: 'start',
            }}
          >
            {/* ── Sets rack — hairline-ruled left rail ──────────────────── */}
            <aside
              style={{
                border: '1px solid var(--rule)',
                background: 'var(--paper-2)',
                position: 'sticky',
                top: 88,
                maxHeight: 'calc(100vh - 120px)',
                overflowY: 'auto',
              }}
            >
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

              {/* Set list */}
              <div style={{ padding: '8px 0' }}>
                {setsLoading ? (
                  <LoadingRow label="Loading sets…" />
                ) : setTypeFilter ? (
                  <div>{sets.map((s) => renderSetRow(s, currentSet?.code === s.code, selectSet))}</div>
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
                        <div>{list.map((s) => renderSetRow(s, currentSet?.code === s.code, selectSet))}</div>
                      </div>
                    );
                  })
                )}
              </div>
            </aside>

            {/* ── Filters + card grid ─────────────────────────────────── */}
            <div style={{ minWidth: 0 }}>
              {/* Filter / search / sort row */}
              <div
                style={{
                  border: '1px solid var(--rule)',
                  background: 'var(--paper-2)',
                  padding: '14px 18px',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 12,
                }}
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

                {/* Search + supertype + type + stage + EX + HP + retreat */}
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
                              retreatCostMin: switchedAway
                                ? undefined
                                : filter.retreatCostMin,
                              retreatCostMax: switchedAway
                                ? undefined
                                : filter.retreatCostMax,
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

                    {/* Energy-type swatches — Pokemon-specific per-card identity:
                        each type retains its real-card color (Grass/Fire/Water/
                        etc.). This is the seam where lab chrome around the
                        filter group ends and Pokemon's own palette begins. */}
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
                          onChange={(e) =>
                            setFilter({ guild: e.target.value || undefined })
                          }
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

              {/* ── Card grid body ──────────────────────────────────────── */}
              <div
                data-testid="pokemon-gatherer-grid"
                style={{
                  marginTop: 16,
                  border: '1px solid var(--rule)',
                  background: 'var(--paper-2)',
                  padding: 20,
                  minHeight: 320,
                }}
              >
                {!currentSet && (
                  <EmptyState
                    eyebrow="Set required"
                    title="Pick a Pokémon set from the rack"
                    body="The left rail lists the SV starter pack plus the Beyond crossover sets. Pick one to load its cards."
                  />
                )}

                {currentSet && cards.length === 0 && cardsLoading && (
                  <LoadingRow label="Loading cards…" big />
                )}

                {currentSet && cards.length === 0 && !cardsLoading && (
                  <EmptyState
                    eyebrow={hasActiveFilters ? 'No matches' : 'Empty set'}
                    title={
                      hasActiveFilters ? 'No cards match these filters' : 'No cards in this set'
                    }
                    body={
                      hasActiveFilters
                        ? 'Loosen a constraint or clear the filters and try again.'
                        : 'This set is empty. Pick another from the rack.'
                    }
                  />
                )}

                {currentSet && cards.length > 0 && (
                  <>
                    <div
                      style={{
                        display: 'grid',
                        gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))',
                        gap: 14,
                      }}
                    >
                      {cards.map((card) => (
                        <PokemonCardCell
                          key={`${card.name}-${card.supertype}`}
                          card={card}
                          onClick={() => selectCard(card)}
                        />
                      ))}
                    </div>

                    {/* Pagination / load-more — lab tokens */}
                    <div
                      style={{
                        marginTop: 20,
                        paddingTop: 14,
                        borderTop: '1px solid var(--rule-2)',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        flexWrap: 'wrap',
                        gap: 12,
                      }}
                    >
                      <span
                        style={{
                          fontFamily: 'var(--font-mono)',
                          fontSize: 11,
                          letterSpacing: '.06em',
                          color: 'var(--ink-3)',
                          fontVariantNumeric: 'tabular-nums',
                        }}
                      >
                        Showing {cards.length} of {cardsTotal}
                      </span>
                      {cardsLoading && cards.length > 0 && (
                        <span
                          style={{
                            fontFamily: 'var(--font-mono)',
                            fontSize: 11,
                            letterSpacing: '.14em',
                            textTransform: 'uppercase',
                            color: 'var(--sodium)',
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: 8,
                          }}
                        >
                          <span
                            style={{
                              width: 8,
                              height: 8,
                              borderRadius: '50%',
                              background: 'var(--sodium)',
                              animation: 'pulse 1.6s ease-in-out infinite',
                            }}
                          />
                          Loading…
                        </span>
                      )}
                      {!cardsLoading && cardsHasMore && (
                        <button
                          type="button"
                          onClick={() => loadMoreCards()}
                          style={{
                            fontFamily: 'var(--font-mono)',
                            fontSize: 11,
                            fontWeight: 500,
                            letterSpacing: '.14em',
                            textTransform: 'uppercase',
                            padding: '8px 14px',
                            background: 'var(--ink)',
                            color: 'var(--paper)',
                            border: 'none',
                            cursor: 'pointer',
                          }}
                        >
                          Load more →
                        </button>
                      )}
                      {!cardsLoading && !cardsHasMore && (
                        <span
                          style={{
                            fontFamily: 'var(--font-mono)',
                            fontSize: 11,
                            letterSpacing: '.14em',
                            textTransform: 'uppercase',
                            color: 'var(--ink-3)',
                          }}
                        >
                          End of set
                        </span>
                      )}
                    </div>
                  </>
                )}
              </div>
            </div>
          </div>
        </section>

        {/* ─── Footer ──────────────────────────────────────────────────── */}
        <footer
          style={{
            marginTop: 96,
            paddingTop: 28,
            borderTop: '1.5px solid var(--ink)',
            display: 'flex',
            justifyContent: 'space-between',
            flexWrap: 'wrap',
            gap: 14,
            fontFamily: 'var(--font-mono)',
            fontSize: 11,
            color: 'var(--ink-3)',
            letterSpacing: '.06em',
          }}
        >
          <span>uvicorn src.server.main:socket_app · port 8030</span>
          <button
            type="button"
            onClick={() => navigate('/gatherer')}
            style={{
              background: 'transparent',
              border: 'none',
              cursor: 'pointer',
              color: 'var(--ink-3)',
              fontFamily: 'var(--font-mono)',
              fontSize: 11,
              letterSpacing: '.08em',
              textTransform: 'uppercase',
              padding: 0,
            }}
          >
            MTG Gatherer →
          </button>
          <button
            type="button"
            onClick={() => navigate('/')}
            style={{
              background: 'transparent',
              border: 'none',
              cursor: 'pointer',
              color: 'var(--ink-3)',
              fontFamily: 'var(--font-mono)',
              fontSize: 11,
              letterSpacing: '.08em',
              textTransform: 'uppercase',
              padding: 0,
            }}
          >
            ← Lab
          </button>
        </footer>
      </main>

      <PokemonCardDetailModal />

      {/* Inline keyframes for the loading dot — scoped to this surface. */}
      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.35; }
        }
      `}</style>
    </div>
  );
}

// === Lab composition helpers ============================================
// Mirrors SectionHead used by Home / Replays so the between-games lab reads
// as one continuous surface across pages.

function SectionHead({
  num,
  title,
  meta,
}: {
  num: string;
  title: React.ReactNode;
  meta?: React.ReactNode;
}) {
  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: '160px 1fr',
        gap: 48,
        paddingTop: 28,
        borderTop: '1px solid var(--rule)',
      }}
    >
      <div
        style={{
          fontFamily: 'var(--font-mono)',
          fontSize: 11,
          fontWeight: 500,
          letterSpacing: '.14em',
          textTransform: 'uppercase',
          color: 'var(--ink-3)',
          paddingTop: 6,
        }}
      >
        <span
          style={{
            display: 'block',
            fontFamily: 'var(--font-serif)',
            fontSize: 32,
            fontWeight: 400,
            lineHeight: 1,
            color: 'var(--sodium)',
            marginBottom: 6,
            letterSpacing: '-.02em',
          }}
        >
          {num}
        </span>
        Section
      </div>
      <div>
        <h2
          style={{
            margin: 0,
            fontFamily: 'var(--font-serif)',
            fontSize: 38,
            fontWeight: 400,
            lineHeight: 1.05,
            letterSpacing: '-.015em',
            color: 'var(--ink)',
          }}
        >
          {title}
        </h2>
        {meta && (
          <p
            style={{
              margin: '8px 0 0',
              fontFamily: 'var(--font-sans)',
              fontSize: 14,
              color: 'var(--ink-2)',
              lineHeight: 1.5,
            }}
          >
            {meta}
          </p>
        )}
      </div>
    </div>
  );
}

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

function EmptyState({
  eyebrow,
  title,
  body,
}: {
  eyebrow: string;
  title: string;
  body: string;
}) {
  return (
    <div
      style={{
        padding: '40px 28px',
        textAlign: 'center',
      }}
    >
      <span
        style={{
          fontFamily: 'var(--font-mono)',
          fontSize: 10.5,
          fontWeight: 500,
          letterSpacing: '.14em',
          textTransform: 'uppercase',
          color: 'var(--sodium)',
        }}
      >
        {eyebrow}
      </span>
      <h3
        style={{
          margin: '12px auto 6px',
          fontFamily: 'var(--font-serif)',
          fontSize: 24,
          fontWeight: 400,
          letterSpacing: '-.015em',
          color: 'var(--ink)',
        }}
      >
        {title}
      </h3>
      <p
        style={{
          margin: '0 auto',
          fontFamily: 'var(--font-serif)',
          fontStyle: 'italic',
          fontSize: 16,
          lineHeight: 1.5,
          color: 'var(--ink-2)',
          maxWidth: '50ch',
        }}
      >
        {body}
      </p>
    </div>
  );
}

function LoadingRow({ label, big = false }: { label: string; big?: boolean }) {
  return (
    <div
      style={{
        padding: big ? '40px 18px' : '16px 18px',
        fontFamily: 'var(--font-mono)',
        fontSize: 11,
        letterSpacing: '.14em',
        textTransform: 'uppercase',
        color: 'var(--ink-3)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: big ? 'center' : 'flex-start',
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

// === Inline-style helpers ===============================================

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

export default PokemonGatherer;
