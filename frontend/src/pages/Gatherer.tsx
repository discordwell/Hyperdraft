/**
 * Gatherer — lab-posture MTG card-database browser (Phase C / follow-up 11a).
 *
 * HYPERDRAFT is a cabinet of TCGs; the Gatherer is a *between-games* surface
 * — players use it to browse cards while not in a match. Per
 * `docs/design/brand.md` and `docs/design/buildplan.md`, that makes it a
 * meta-frame and full lab posture applies (paper / ink / sodium, Instrument
 * Serif masthead, Geist Mono telemetry, hairline rules).
 *
 * Lab chrome ends and per-card identity begins inside the card grid. Each
 * `<SketchCard>` cell renders the real MTG card art (served from
 * `/api/card-art/` or Scryfall's `art_crop`) plus the card's parchment face —
 * that's the body of the page and stays as-is. The lab chrome lives in:
 *
 *   - caption rail   (`HD-GATHERER · MTG · LIBRARY · v4.7`)
 *   - masthead       (HYPERDRAFT / Gatherer + card-count stamp)
 *   - section head   (`01 SECTION` mono + Instrument Serif title)
 *   - sidebar        (sets listed as a tabular rack, hairline-ruled)
 *   - filter row     (mono inputs, hairline borders, sodium accents)
 *   - card grid      (paper-2 plate with mono header strip; cells = SketchCard)
 *   - load-more      (mono pill, sodium dot when streaming)
 *   - modal chrome   (paper backdrop, hairline-ruled close button; inner
 *                     SketchCardDetail card-face stays unchanged)
 *   - footer         (mono ink-3, uvicorn left + GATHERER stamp right)
 *
 * The five MTG color-identity dots in the filter row keep their hex (W/U/B/R/G)
 * — per-game identity is load-bearing, and the colors are a primitive of the
 * game itself, not lab decoration.
 *
 * State / data come straight from `useGathererStore`; the previous version
 * delegated to <SetSidebar /> + <GathererFilterBar /> + <GathererCardGrid />
 * sub-components, but those still carry slate/zinc tailwind chrome. Inlining
 * the layout here keeps the lab posture intact without rewriting four files.
 */

import { useEffect, useMemo, useRef, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useGathererStore } from '../stores/gathererStore';
import { COLORS } from '../types/deckbuilder';
import { SET_TYPE_INFO, RARITY_INFO, SORT_FIELDS } from '../types/gatherer';
import type { SetInfo, SetType, SortField } from '../types/gatherer';
import { SketchCard } from '../components/gatherer/SketchCard';
import { SketchCardDetail } from '../components/gatherer/SketchCardDetail';

const SET_TYPE_ORDER: SetType[] = ['standard', 'universes_beyond', 'custom'];
const CARD_TYPE_FILTERS = ['CREATURE', 'INSTANT', 'SORCERY', 'ENCHANTMENT', 'ARTIFACT'] as const;

export function Gatherer() {
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
    selectedCard,
    setTypeFilter,
    loadSets,
    selectSet,
    loadMoreCards,
    setFilter,
    clearFilter,
    setSortBy,
    toggleSortOrder,
    selectCard,
    setSetTypeFilter,
  } = useGathererStore();

  const [textSearch, setTextSearch] = useState(filter.textSearch || '');

  useEffect(() => {
    loadSets();
  }, [loadSets]);

  // Group sets by type for the sidebar rack
  const groupedSets = useMemo(() => {
    return sets.reduce(
      (acc, set) => {
        const t = (set.set_type as SetType) ?? 'custom';
        if (!acc[t]) acc[t] = [];
        acc[t].push(set);
        return acc;
      },
      {} as Record<SetType, SetInfo[]>,
    );
  }, [sets]);

  // ─── Infinite-scroll sentinel ─────────────────────────────────────────
  const loadMoreRef = useRef<HTMLDivElement>(null);
  const handleObserver = useCallback(
    (entries: IntersectionObserverEntry[]) => {
      const [entry] = entries;
      if (entry.isIntersecting && cardsHasMore && !cardsLoading) {
        loadMoreCards();
      }
    },
    [cardsHasMore, cardsLoading, loadMoreCards],
  );
  useEffect(() => {
    const obs = new IntersectionObserver(handleObserver, {
      root: null,
      rootMargin: '200px',
      threshold: 0,
    });
    const node = loadMoreRef.current;
    if (node) obs.observe(node);
    return () => obs.disconnect();
  }, [handleObserver]);

  // ─── Modal: Escape to close + body-scroll lock ────────────────────────
  useEffect(() => {
    if (!selectedCard) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') selectCard(null);
    };
    document.addEventListener('keydown', handleKeyDown);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      document.body.style.overflow = prevOverflow;
    };
  }, [selectedCard, selectCard]);

  const handleTextSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setFilter({ textSearch: textSearch || undefined });
  };

  const handleTypeToggle = (type: string) => {
    const current = filter.types || [];
    const next = current.includes(type) ? current.filter((t) => t !== type) : [...current, type];
    setFilter({ types: next.length > 0 ? next : undefined });
  };

  const handleColorToggle = (color: string) => {
    const current = filter.colors || [];
    const next = current.includes(color) ? current.filter((c) => c !== color) : [...current, color];
    setFilter({ colors: next.length > 0 ? next : undefined });
  };

  const hasActiveFilters =
    (filter.types && filter.types.length > 0) ||
    (filter.colors && filter.colors.length > 0) ||
    Boolean(filter.rarity) ||
    Boolean(filter.textSearch) ||
    filter.cmcMin !== undefined ||
    filter.cmcMax !== undefined;

  const totalCards = sets.reduce((sum, s) => sum + s.card_count, 0);

  return (
    <div style={{ background: 'var(--paper)', color: 'var(--ink)', minHeight: '100vh' }}>
      {/* ─── Caption rail ─────────────────────────────────────────────── */}
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
          zIndex: 30,
        }}
      >
        <b style={{ color: 'var(--ink)', fontWeight: 500 }}>HD-GATHERER</b>
        &nbsp;·&nbsp; MTG &nbsp;·&nbsp; LIBRARY &nbsp;·&nbsp; v4.7
      </div>

      <main
        style={{
          maxWidth: 1320,
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
            <button
              type="button"
              onClick={() => navigate('/')}
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: 11,
                fontWeight: 500,
                letterSpacing: '.1em',
                textTransform: 'uppercase',
                color: 'var(--ink-3)',
                background: 'transparent',
                border: 'none',
                cursor: 'pointer',
                padding: 0,
                marginRight: 4,
              }}
              aria-label="Back to lab home"
            >
              ← Lab
            </button>
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
                fontStyle: 'italic',
                color: 'var(--ink)',
                letterSpacing: '-.02em',
                lineHeight: 1,
              }}
            >
              / Gatherer
            </span>
          </div>
          <span
            data-testid="gatherer-card-count-stamp"
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 12,
              fontWeight: 500,
              letterSpacing: '.06em',
              color: 'var(--ink-2)',
              textAlign: 'right',
              fontVariantNumeric: 'tabular-nums',
            }}
          >
            v4.7 · {totalCards.toLocaleString()} cards · {sets.length} sets
          </span>
        </header>

        {/* ─── Section 01 · Card library ──────────────────────────────── */}
        <section>
          <SectionHead
            num="01"
            title={
              <>
                Card <em style={{ color: 'var(--sodium)', fontStyle: 'italic' }}>library</em>.
              </>
            }
            meta="Every standard-legal printing across the cabinet's MTG sets. Pick a set on the left; filter by color, type, rarity, or mana value."
          />

          {/* ─── Set-type / sort strip ─────────────────────────────── */}
          <div
            data-testid="gatherer-toolbar"
            style={{
              marginTop: 24,
              display: 'flex',
              flexWrap: 'wrap',
              alignItems: 'center',
              gap: 14,
              padding: '14px 18px',
              border: '1px solid var(--rule)',
              background: 'var(--paper-2)',
            }}
          >
            <Eyebrow>Set type</Eyebrow>
            <button
              type="button"
              onClick={() => setSetTypeFilter(null)}
              style={chipButtonStyle(!setTypeFilter)}
            >
              All
            </button>
            {SET_TYPE_ORDER.map((t) => (
              <button
                key={t}
                type="button"
                onClick={() => setSetTypeFilter(t)}
                style={chipButtonStyle(setTypeFilter === t)}
              >
                {SET_TYPE_INFO[t].label}
              </button>
            ))}
            <span style={{ flex: 1 }} />
            <Eyebrow>Sort</Eyebrow>
            <select
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value as SortField)}
              style={selectStyle}
              aria-label="Sort cards by field"
            >
              {SORT_FIELDS.map((f) => (
                <option key={f.value} value={f.value}>
                  {f.label}
                </option>
              ))}
            </select>
            <button
              type="button"
              onClick={toggleSortOrder}
              style={chipButtonStyle(false)}
              title={sortOrder === 'asc' ? 'Ascending' : 'Descending'}
            >
              {sortOrder === 'asc' ? '↑ Asc' : '↓ Desc'}
            </button>
          </div>

          {/* ─── Main grid: sidebar + content ──────────────────────── */}
          <div
            style={{
              marginTop: 24,
              display: 'grid',
              gridTemplateColumns: '260px 1fr',
              gap: 24,
              alignItems: 'start',
            }}
          >
            {/* ─── Sidebar: set rack ──────────────────────────────── */}
            <aside
              data-testid="gatherer-set-rack"
              style={{
                border: '1px solid var(--rule)',
                background: 'var(--paper-2)',
                minHeight: 420,
                display: 'flex',
                flexDirection: 'column',
              }}
            >
              <div
                style={{
                  display: 'flex',
                  alignItems: 'baseline',
                  justifyContent: 'space-between',
                  padding: '12px 14px',
                  borderBottom: '1px solid var(--rule)',
                }}
              >
                <Eyebrow>Sets</Eyebrow>
                <span
                  style={{
                    fontFamily: 'var(--font-mono)',
                    fontSize: 11,
                    color: 'var(--ink-3)',
                    fontVariantNumeric: 'tabular-nums',
                  }}
                >
                  {sets.length}
                </span>
              </div>

              {setsLoading && (
                <div
                  style={{
                    padding: '24px 14px',
                    display: 'flex',
                    alignItems: 'center',
                    gap: 10,
                    fontFamily: 'var(--font-mono)',
                    fontSize: 11,
                    letterSpacing: '.14em',
                    textTransform: 'uppercase',
                    color: 'var(--ink-3)',
                  }}
                >
                  <span
                    style={{
                      width: 10,
                      height: 10,
                      borderRadius: '50%',
                      background: 'var(--sodium)',
                      animation: 'gatherer-pulse 1.6s ease-in-out infinite',
                    }}
                  />
                  Loading sets…
                </div>
              )}

              {setsError && (
                <div
                  style={{
                    margin: 14,
                    padding: '10px 12px',
                    border: '1px solid var(--halt)',
                    background: 'color-mix(in oklab, var(--halt) 8%, transparent)',
                    fontFamily: 'var(--font-mono)',
                    fontSize: 11,
                    color: 'var(--halt)',
                  }}
                >
                  {setsError}
                </div>
              )}

              <div style={{ flex: 1, overflowY: 'auto', maxHeight: '70vh' }}>
                {setTypeFilter ? (
                  <SetList
                    sets={sets}
                    currentCode={currentSet?.code ?? null}
                    onSelect={selectSet}
                  />
                ) : (
                  SET_TYPE_ORDER.map((t) => {
                    const list = groupedSets[t] || [];
                    if (list.length === 0) return null;
                    return (
                      <div key={t}>
                        <div
                          style={{
                            padding: '12px 14px 6px',
                            fontFamily: 'var(--font-mono)',
                            fontSize: 10.5,
                            fontWeight: 500,
                            letterSpacing: '.14em',
                            textTransform: 'uppercase',
                            color: 'var(--ink-3)',
                            borderTop: '1px solid var(--rule-2)',
                          }}
                        >
                          {SET_TYPE_INFO[t].label}
                        </div>
                        <SetList sets={list} currentCode={currentSet?.code ?? null} onSelect={selectSet} />
                      </div>
                    );
                  })
                )}
              </div>
            </aside>

            {/* ─── Right pane: filters + grid ─────────────────────── */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 18, minWidth: 0 }}>
              {/* Filter row */}
              <div
                data-testid="gatherer-filter-row"
                style={{
                  display: 'flex',
                  flexWrap: 'wrap',
                  alignItems: 'center',
                  gap: 12,
                  padding: '14px 16px',
                  border: '1px solid var(--rule)',
                  background: 'var(--paper-2)',
                }}
              >
                {/* Search */}
                <form
                  onSubmit={handleTextSearchSubmit}
                  style={{ flex: '1 1 220px', maxWidth: 320, position: 'relative' }}
                >
                  <input
                    type="text"
                    value={textSearch}
                    onChange={(e) => setTextSearch(e.target.value)}
                    placeholder="Search cards…"
                    aria-label="Search cards"
                    style={{ ...inputStyle, paddingRight: 28 }}
                  />
                  {textSearch && (
                    <button
                      type="button"
                      onClick={() => {
                        setTextSearch('');
                        setFilter({ textSearch: undefined });
                      }}
                      aria-label="Clear search"
                      style={{
                        position: 'absolute',
                        right: 6,
                        top: '50%',
                        transform: 'translateY(-50%)',
                        background: 'transparent',
                        border: 'none',
                        color: 'var(--ink-3)',
                        fontFamily: 'var(--font-mono)',
                        fontSize: 14,
                        cursor: 'pointer',
                        padding: '4px 6px',
                      }}
                    >
                      ×
                    </button>
                  )}
                </form>

                {/* Type chips */}
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <Eyebrow>Type</Eyebrow>
                  {CARD_TYPE_FILTERS.map((type) => (
                    <button
                      key={type}
                      type="button"
                      onClick={() => handleTypeToggle(type)}
                      style={chipButtonStyle(filter.types?.includes(type) ?? false)}
                    >
                      {type.charAt(0) + type.slice(1).toLowerCase()}
                    </button>
                  ))}
                </div>

                {/* Color identity — keeps the MTG hex per spec */}
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <Eyebrow>Color</Eyebrow>
                  {Object.entries(COLORS).map(([code, info]) => {
                    const active = filter.colors?.includes(code) ?? false;
                    return (
                      <button
                        key={code}
                        type="button"
                        onClick={() => handleColorToggle(code)}
                        title={info.name}
                        aria-label={`Filter by ${info.name}`}
                        aria-pressed={active}
                        style={{
                          width: 22,
                          height: 22,
                          borderRadius: '50%',
                          background: info.hex,
                          border: active
                            ? '2px solid var(--sodium)'
                            : '1px solid var(--rule)',
                          boxShadow: active
                            ? '0 0 0 2px color-mix(in oklab, var(--sodium) 30%, transparent)'
                            : 'none',
                          cursor: 'pointer',
                          padding: 0,
                          transform: active ? 'scale(1.08)' : 'scale(1)',
                          transition: 'transform 120ms ease',
                        }}
                      />
                    );
                  })}
                </div>

                {/* Rarity */}
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <Eyebrow>Rarity</Eyebrow>
                  <select
                    value={filter.rarity || ''}
                    onChange={(e) =>
                      setFilter({ rarity: e.target.value || undefined })
                    }
                    aria-label="Filter by rarity"
                    style={selectStyle}
                  >
                    <option value="">All</option>
                    {Object.entries(RARITY_INFO).map(([r, info]) => (
                      <option key={r} value={r}>
                        {info.label}
                      </option>
                    ))}
                  </select>
                </div>

                {/* CMC */}
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <Eyebrow>MV</Eyebrow>
                  <input
                    type="number"
                    min={0}
                    max={20}
                    placeholder="Min"
                    aria-label="Minimum mana value"
                    value={filter.cmcMin ?? ''}
                    onChange={(e) =>
                      setFilter({
                        cmcMin: e.target.value ? parseInt(e.target.value) : undefined,
                      })
                    }
                    style={{ ...inputStyle, width: 56, fontFamily: 'var(--font-mono)' }}
                  />
                  <span style={{ color: 'var(--ink-3)', fontFamily: 'var(--font-mono)' }}>–</span>
                  <input
                    type="number"
                    min={0}
                    max={20}
                    placeholder="Max"
                    aria-label="Maximum mana value"
                    value={filter.cmcMax ?? ''}
                    onChange={(e) =>
                      setFilter({
                        cmcMax: e.target.value ? parseInt(e.target.value) : undefined,
                      })
                    }
                    style={{ ...inputStyle, width: 56, fontFamily: 'var(--font-mono)' }}
                  />
                </div>

                {hasActiveFilters && (
                  <button
                    type="button"
                    onClick={() => {
                      setTextSearch('');
                      clearFilter();
                    }}
                    style={{
                      fontFamily: 'var(--font-mono)',
                      fontSize: 11,
                      fontWeight: 500,
                      letterSpacing: '.12em',
                      textTransform: 'uppercase',
                      padding: '7px 10px',
                      background: 'transparent',
                      color: 'var(--halt)',
                      border: '1px solid var(--halt)',
                      cursor: 'pointer',
                    }}
                  >
                    Clear filters
                  </button>
                )}
              </div>

              {/* Card-grid plate */}
              <div
                data-testid="gatherer-card-grid"
                style={{
                  border: '1px solid var(--rule)',
                  background: 'var(--paper-2)',
                  display: 'flex',
                  flexDirection: 'column',
                }}
              >
                {/* Grid header strip */}
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'baseline',
                    justifyContent: 'space-between',
                    padding: '12px 16px',
                    borderBottom: '1px solid var(--rule)',
                    flexWrap: 'wrap',
                    gap: 8,
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'baseline', gap: 12 }}>
                    <Eyebrow>Set</Eyebrow>
                    <span
                      style={{
                        fontFamily: 'var(--font-serif)',
                        fontSize: 22,
                        lineHeight: 1,
                        color: 'var(--ink)',
                        letterSpacing: '-.01em',
                      }}
                    >
                      {currentSet?.name ?? 'No set selected'}
                    </span>
                    {currentSet?.code && (
                      <span
                        style={{
                          fontFamily: 'var(--font-mono)',
                          fontSize: 11,
                          letterSpacing: '.1em',
                          textTransform: 'uppercase',
                          color: 'var(--ink-3)',
                        }}
                      >
                        {currentSet.code}
                      </span>
                    )}
                  </div>
                  <span
                    style={{
                      fontFamily: 'var(--font-mono)',
                      fontSize: 11,
                      letterSpacing: '.06em',
                      color: 'var(--ink-3)',
                      fontVariantNumeric: 'tabular-nums',
                    }}
                  >
                    {currentSet
                      ? `${cardsTotal} card${cardsTotal !== 1 ? 's' : ''} matching filters`
                      : 'pick a set →'}
                  </span>
                </div>

                {/* Grid body */}
                <div style={{ padding: 16, minHeight: 360 }}>
                  {!currentSet && (
                    <EmptyState
                      headline="Pick a set."
                      detail="Choose one from the rack on the left to start browsing."
                    />
                  )}

                  {currentSet && cards.length === 0 && cardsLoading && (
                    <LoadingState />
                  )}

                  {currentSet && cards.length === 0 && !cardsLoading && (
                    <EmptyState
                      headline="No cards match."
                      detail={
                        hasActiveFilters
                          ? 'Try widening your filters or clearing them.'
                          : 'This set appears to be empty.'
                      }
                    />
                  )}

                  {cards.length > 0 && (
                    <div
                      style={{
                        display: 'grid',
                        gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))',
                        gap: 16,
                      }}
                    >
                      {cards.map((card) => (
                        <SketchCard
                          key={card.name}
                          card={card}
                          setCode={currentSet?.code}
                          onClick={() => selectCard(card)}
                        />
                      ))}
                    </div>
                  )}

                  {/* Sentinel + load-more affordance */}
                  <div ref={loadMoreRef} style={{ paddingTop: cards.length > 0 ? 20 : 0 }}>
                    {cardsLoading && cards.length > 0 && (
                      <div
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: 10,
                          fontFamily: 'var(--font-mono)',
                          fontSize: 11,
                          letterSpacing: '.14em',
                          textTransform: 'uppercase',
                          color: 'var(--ink-3)',
                          padding: '8px 0',
                        }}
                      >
                        <span
                          style={{
                            width: 9,
                            height: 9,
                            borderRadius: '50%',
                            background: 'var(--sodium)',
                            animation: 'gatherer-pulse 1.6s ease-in-out infinite',
                          }}
                        />
                        Loading more…
                      </div>
                    )}
                    {!cardsLoading && cardsHasMore && cards.length > 0 && (
                      <div
                        style={{
                          display: 'flex',
                          justifyContent: 'center',
                          padding: '8px 0',
                        }}
                      >
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
                            background: 'transparent',
                            color: 'var(--ink)',
                            border: '1px solid var(--ink)',
                            cursor: 'pointer',
                          }}
                        >
                          Load more
                        </button>
                      </div>
                    )}
                    {!cardsLoading && !cardsHasMore && cards.length > 0 && (
                      <div
                        style={{
                          textAlign: 'center',
                          padding: '8px 0',
                          fontFamily: 'var(--font-mono)',
                          fontSize: 11,
                          letterSpacing: '.1em',
                          textTransform: 'uppercase',
                          color: 'var(--ink-3)',
                        }}
                      >
                        Showing all {cards.length}
                      </div>
                    )}
                  </div>
                </div>
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
          <span style={{ letterSpacing: '.1em', textTransform: 'uppercase' }}>
            HYPERDRAFT · GATHERER
          </span>
        </footer>
      </main>

      {/* ─── Modal — lab chrome around the SketchCardDetail face ──────── */}
      {selectedCard && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label={`Card detail: ${selectedCard.name}`}
          onClick={() => selectCard(null)}
          style={{
            position: 'fixed',
            inset: 0,
            background: 'color-mix(in oklab, var(--ink) 35%, transparent)',
            backdropFilter: 'blur(4px)',
            WebkitBackdropFilter: 'blur(4px)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: 16,
            zIndex: 40,
          }}
        >
          <div style={{ position: 'relative' }} onClick={(e) => e.stopPropagation()}>
            <button
              type="button"
              onClick={() => selectCard(null)}
              aria-label="Close card detail"
              style={{
                position: 'absolute',
                top: -14,
                right: -14,
                width: 32,
                height: 32,
                background: 'var(--paper)',
                color: 'var(--ink)',
                border: '1px solid var(--ink)',
                cursor: 'pointer',
                fontFamily: 'var(--font-mono)',
                fontSize: 16,
                lineHeight: 1,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                zIndex: 50,
              }}
            >
              ×
            </button>
            <SketchCardDetail
              card={selectedCard}
              setCode={currentSet?.code}
              setName={currentSet?.name}
            />
          </div>
        </div>
      )}

      {/* Local keyframes — keep scoped to this surface so the dot pulse
          doesn't leak into other lab pages that don't define `gatherer-pulse`. */}
      <style>{`
        @keyframes gatherer-pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.32; }
        }
      `}</style>
    </div>
  );
}

// === Sidebar set list ====================================================

function SetList({
  sets,
  currentCode,
  onSelect,
}: {
  sets: SetInfo[];
  currentCode: string | null;
  onSelect: (code: string) => void;
}) {
  return (
    <div role="list">
      {sets.map((s) => {
        const active = s.code === currentCode;
        return (
          <button
            key={s.code}
            type="button"
            role="listitem"
            onClick={() => onSelect(s.code)}
            aria-current={active ? 'true' : undefined}
            style={{
              display: 'grid',
              gridTemplateColumns: '1fr auto',
              gap: 8,
              alignItems: 'baseline',
              width: '100%',
              textAlign: 'left',
              padding: '10px 14px',
              border: 'none',
              borderTop: '1px solid var(--rule-2)',
              background: active ? 'color-mix(in oklab, var(--sodium) 12%, var(--paper))' : 'transparent',
              color: 'var(--ink)',
              cursor: 'pointer',
              fontFamily: 'var(--font-sans)',
            }}
            onMouseEnter={(ev) => {
              if (!active) {
                ev.currentTarget.style.background = 'color-mix(in oklab, var(--sodium) 6%, var(--paper-2))';
              }
            }}
            onMouseLeave={(ev) => {
              if (!active) {
                ev.currentTarget.style.background = 'transparent';
              }
            }}
          >
            <div style={{ minWidth: 0 }}>
              <div
                style={{
                  fontFamily: 'var(--font-serif)',
                  fontSize: 15,
                  lineHeight: 1.2,
                  color: 'var(--ink)',
                  letterSpacing: '-.01em',
                  whiteSpace: 'nowrap',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                }}
              >
                {s.name}
              </div>
              <div
                style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: 10.5,
                  letterSpacing: '.1em',
                  textTransform: 'uppercase',
                  color: active ? 'var(--sodium)' : 'var(--ink-3)',
                  marginTop: 2,
                }}
              >
                {s.code}
              </div>
            </div>
            <span
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: 11,
                color: 'var(--ink-3)',
                fontVariantNumeric: 'tabular-nums',
              }}
            >
              {s.card_count}
            </span>
          </button>
        );
      })}
    </div>
  );
}

// === Lab composition helpers =============================================
// Mirrors Home.tsx + Replays.tsx so the three between-games surfaces read as
// one continuous lab. Kept local — page-specific numbering / metadata.

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
              maxWidth: '70ch',
            }}
          >
            {meta}
          </p>
        )}
      </div>
    </div>
  );
}

function Eyebrow({ children }: { children: React.ReactNode }) {
  return (
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
      {children}
    </span>
  );
}

function EmptyState({ headline, detail }: { headline: string; detail: string }) {
  return (
    <div
      style={{
        padding: '40px 28px',
        border: '1px dashed var(--rule)',
        background: 'var(--paper)',
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
        {headline}
      </span>
      <p
        style={{
          margin: '12px auto 0',
          fontFamily: 'var(--font-serif)',
          fontStyle: 'italic',
          fontSize: 18,
          lineHeight: 1.5,
          color: 'var(--ink-2)',
          maxWidth: '52ch',
        }}
      >
        {detail}
      </p>
    </div>
  );
}

function LoadingState() {
  return (
    <div
      style={{
        padding: '24px 18px',
        display: 'flex',
        alignItems: 'center',
        gap: 10,
        fontFamily: 'var(--font-mono)',
        fontSize: 11,
        letterSpacing: '.14em',
        textTransform: 'uppercase',
        color: 'var(--ink-3)',
        border: '1px solid var(--rule)',
        background: 'var(--paper)',
      }}
    >
      <span
        style={{
          width: 10,
          height: 10,
          borderRadius: '50%',
          background: 'var(--sodium)',
          animation: 'gatherer-pulse 1.6s ease-in-out infinite',
        }}
      />
      Loading cards…
    </div>
  );
}

// === Inline-style helpers ================================================

const inputStyle: React.CSSProperties = {
  background: 'var(--paper)',
  border: '1px solid var(--rule)',
  padding: '7px 10px',
  fontFamily: 'var(--font-mono)',
  fontSize: 12,
  color: 'var(--ink)',
  outline: 'none',
  width: '100%',
};

const selectStyle: React.CSSProperties = {
  background: 'var(--paper)',
  border: '1px solid var(--rule)',
  padding: '7px 10px',
  fontFamily: 'var(--font-mono)',
  fontSize: 12,
  color: 'var(--ink)',
  outline: 'none',
  cursor: 'pointer',
};

function chipButtonStyle(active: boolean): React.CSSProperties {
  return {
    fontFamily: 'var(--font-mono)',
    fontSize: 11,
    fontWeight: 500,
    letterSpacing: '.1em',
    textTransform: 'uppercase',
    padding: '7px 10px',
    background: active ? 'var(--ink)' : 'var(--paper)',
    color: active ? 'var(--paper)' : 'var(--ink-2)',
    border: `1px solid ${active ? 'var(--ink)' : 'var(--rule)'}`,
    cursor: 'pointer',
    whiteSpace: 'nowrap',
  };
}

export default Gatherer;
