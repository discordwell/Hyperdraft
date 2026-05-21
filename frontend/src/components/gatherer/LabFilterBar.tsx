/**
 * LabFilterBar — Gatherer filter controls (Phase C / follow-up 11a).
 *
 * Two stacked filter rows in one component:
 *
 *   1. Toolbar  — set-type chips + sort field / order. Sits above the
 *      sidebar + grid columns; spans the full content width.
 *   2. Filter   — search input, card-type chips, color identity (MTG hex
 *      kept per spec), rarity dropdown, MV min/max range, clear-all.
 *
 * Both rows talk straight to `useGathererStore`. Lab tokens only — paper-2
 * panels with hairline borders, mono inputs, sodium accent on the active
 * color dot.
 */

import { useState, useEffect } from 'react';
import { useGathererStore } from '../../stores/gathererStore';
import { COLORS } from '../../types/deckbuilder';
import { SET_TYPE_INFO, RARITY_INFO, SORT_FIELDS } from '../../types/gatherer';
import type { SetType, SortField } from '../../types/gatherer';
import { Eyebrow, inputStyle, selectStyle, chipButtonStyle } from './_labChrome';

const SET_TYPE_ORDER: SetType[] = ['standard', 'universes_beyond', 'custom'];
const CARD_TYPE_FILTERS = ['CREATURE', 'INSTANT', 'SORCERY', 'ENCHANTMENT', 'ARTIFACT'] as const;

// === Toolbar (set-type + sort) ==========================================

export function LabFilterToolbar() {
  const {
    sortBy,
    sortOrder,
    setTypeFilter,
    setSortBy,
    toggleSortOrder,
    setSetTypeFilter,
  } = useGathererStore();

  return (
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
  );
}

// === Main filter row (search / type / color / rarity / MV) =============

export function LabFilterBar() {
  const { filter, setFilter, clearFilter } = useGathererStore();

  // Keep the text input local — only commit to the store on submit so we
  // don't refetch on every keystroke. Reset when the store filter changes
  // externally (e.g. "Clear filters").
  const [textSearch, setTextSearch] = useState(filter.textSearch || '');
  useEffect(() => {
    setTextSearch(filter.textSearch || '');
  }, [filter.textSearch]);

  const handleTextSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setFilter({ textSearch: textSearch || undefined });
  };

  const handleTypeToggle = (type: string) => {
    const current = filter.types || [];
    const next = current.includes(type)
      ? current.filter((t) => t !== type)
      : [...current, type];
    setFilter({ types: next.length > 0 ? next : undefined });
  };

  const handleColorToggle = (color: string) => {
    const current = filter.colors || [];
    const next = current.includes(color)
      ? current.filter((c) => c !== color)
      : [...current, color];
    setFilter({ colors: next.length > 0 ? next : undefined });
  };

  const hasActiveFilters =
    (filter.types && filter.types.length > 0) ||
    (filter.colors && filter.colors.length > 0) ||
    Boolean(filter.rarity) ||
    Boolean(filter.textSearch) ||
    filter.cmcMin !== undefined ||
    filter.cmcMax !== undefined;

  return (
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
          onChange={(e) => setFilter({ rarity: e.target.value || undefined })}
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
  );
}
