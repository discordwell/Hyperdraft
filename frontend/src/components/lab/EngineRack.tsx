/**
 * EngineRack — HD-ART-01 right-column engine rack.
 *
 * All registered engines, ranked by completeness, with a single accented stat
 * and a monochrome bar. The count grows as engines are added — never hardcode
 * it. Clicking a row dispatches navigateToEngine; the parent decides where
 * that goes (deckbuilder, new match, picker overlay).
 *
 * Phase A1 (buildplan): annotate untouched rows with a sodium "NEW" pill so
 * returning users can spot the engines they haven't tried.
 *
 * Phase B1 (buildplan): mirror the Wave 1 EnginePicker (B2) controls — a mono
 * search input narrows the list by name/code/id/subtitle, and a 3-button sort
 * selector cycles A→Z / Completeness / Untouched first. Default sort stays
 * `completeness` to match the pre-filter behavior.
 */

import { useMemo, useState } from 'react';
import { LAB_ENGINES, type LabEngineMeta } from './engineMeta';
import type { GameModeId } from '../brand/modes';
import { useDiscoveryStore } from '../../stores/discoveryStore';

interface EngineRackProps {
  activeId?: GameModeId;
  onSelect?: (id: GameModeId) => void;
}

type SortMode = 'alpha' | 'completeness' | 'untouched';

const SORT_LABELS: Record<SortMode, string> = {
  alpha: 'A→Z',
  completeness: 'Completeness',
  untouched: 'Untouched first',
};

const SORT_ORDER: SortMode[] = ['alpha', 'completeness', 'untouched'];

function matchesQuery(e: LabEngineMeta, q: string): boolean {
  if (!q) return true;
  const needle = q.toLowerCase();
  return (
    e.name.toLowerCase().includes(needle) ||
    e.code.toLowerCase().includes(needle) ||
    e.id.toLowerCase().includes(needle) ||
    e.subtitle.toLowerCase().includes(needle)
  );
}

export function EngineRack({ activeId, onSelect }: EngineRackProps) {
  const [query, setQuery] = useState('');
  const [sort, setSort] = useState<SortMode>('completeness');

  const playedEngines = useDiscoveryStore((s) => s.playedEngines);
  const playedSet = useMemo(() => new Set(playedEngines), [playedEngines]);

  const visibleEngines = useMemo(() => {
    const filtered = LAB_ENGINES.filter((e) => matchesQuery(e, query));
    const sorted = [...filtered];
    if (sort === 'alpha') {
      sorted.sort((a, b) => a.name.localeCompare(b.name));
    } else if (sort === 'completeness') {
      sorted.sort((a, b) => b.completeness - a.completeness);
    } else {
      // 'untouched' — untouched (not in playedEngines) first, then alpha
      // within each bucket. Falls back to pure alpha when nothing has
      // been played yet.
      sorted.sort((a, b) => {
        const aPlayed = playedSet.has(a.id) ? 1 : 0;
        const bPlayed = playedSet.has(b.id) ? 1 : 0;
        if (aPlayed !== bPlayed) return aPlayed - bPlayed;
        return a.name.localeCompare(b.name);
      });
    }
    return sorted;
  }, [query, sort, playedSet]);

  return (
    <div
      style={{
        border: '1px solid var(--rule)',
        background: 'var(--paper-2)',
        fontFamily: 'var(--font-mono)',
      }}
    >
      <div
        style={{
          padding: '12px 14px',
          borderBottom: '1px solid var(--rule)',
          fontSize: 10.5,
          letterSpacing: '.14em',
          textTransform: 'uppercase',
          color: 'var(--ink-3)',
          display: 'flex',
          justifyContent: 'space-between',
        }}
      >
        <span>Engine rack</span>
        <b style={{ color: 'var(--ink)', fontWeight: 600 }}>
          {LAB_ENGINES.length} LOADED
        </b>
      </div>

      {/* Controls bar — search (left) + sort selector (right). Mirrors the
          EnginePicker (Wave 1 B2) so the rack and the ⌘E overlay share a
          single muscle-memory for filtering. */}
      <div
        data-testid="engine-rack-controls"
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          gap: 10,
          padding: '10px 14px',
          borderBottom: '1px solid var(--rule)',
        }}
      >
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Filter…"
          aria-label="Filter engines"
          data-testid="engine-rack-search"
          style={{
            flex: '1 1 auto',
            minWidth: 0,
            padding: '4px 2px',
            background: 'transparent',
            border: 'none',
            borderBottom: '1px solid var(--rule)',
            outline: 'none',
            fontFamily: 'var(--font-mono)',
            fontSize: 11.5,
            letterSpacing: '.04em',
            color: 'var(--ink)',
          }}
        />
        <div
          role="radiogroup"
          aria-label="Sort engines"
          style={{ display: 'flex', gap: 0, fontFamily: 'var(--font-mono)' }}
        >
          {SORT_ORDER.map((mode) => {
            const isActive = mode === sort;
            return (
              <button
                key={mode}
                type="button"
                role="radio"
                aria-checked={isActive}
                data-testid={`engine-rack-sort-${mode}`}
                onClick={() => setSort(mode)}
                style={{
                  padding: '4px 7px',
                  border: '1px solid var(--ink)',
                  borderLeftWidth: mode === SORT_ORDER[0] ? 1 : 0,
                  background: isActive ? 'var(--ink)' : 'transparent',
                  color: isActive ? 'var(--paper)' : 'var(--ink)',
                  fontFamily: 'var(--font-mono)',
                  fontSize: 9.5,
                  fontWeight: 500,
                  letterSpacing: '.1em',
                  textTransform: 'uppercase',
                  cursor: 'pointer',
                }}
              >
                {SORT_LABELS[mode]}
              </button>
            );
          })}
        </div>
      </div>

      {visibleEngines.length === 0 && (
        <div
          data-testid="engine-rack-empty"
          style={{
            padding: '20px 14px',
            textAlign: 'center',
            fontFamily: 'var(--font-mono)',
            fontSize: 11,
            letterSpacing: '.1em',
            textTransform: 'uppercase',
            color: 'var(--ink-3)',
          }}
        >
          No engines match “{query}”.
        </div>
      )}

      {visibleEngines.map((e) => {
        const isActive = e.id === activeId;
        const isUnplayed = !playedSet.has(e.id);
        return (
          <button
            key={e.id}
            type="button"
            aria-label={e.name}
            data-testid={`engine-rack-row-${e.id}`}
            onClick={() => onSelect?.(e.id)}
            style={{
              display: 'grid',
              gridTemplateColumns: '36px 1fr auto 90px',
              alignItems: 'center',
              gap: 12,
              padding: '10px 14px',
              borderTop: '1px solid var(--rule-2)',
              fontFamily: 'var(--font-mono)',
              fontSize: 12,
              fontWeight: 500,
              lineHeight: 1.2,
              width: '100%',
              textAlign: 'left',
              background: isActive ? 'var(--paper-3)' : 'transparent',
              color: 'var(--ink-2)',
              cursor: 'pointer',
              border: 'none',
              borderBottom: 0,
            }}
          >
            <span style={{ color: 'var(--ink-3)' }}>{e.ix}</span>
            <span>
              <span
                style={{
                  fontFamily: 'var(--font-serif)',
                  fontSize: 18,
                  fontWeight: 400,
                  letterSpacing: '-.01em',
                  color: 'var(--ink)',
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 8,
                }}
              >
                {e.name}
                {isUnplayed && (
                  <span
                    data-testid={`engine-rack-new-${e.id}`}
                    style={{
                      fontFamily: 'var(--font-mono)',
                      fontSize: 9,
                      fontWeight: 500,
                      letterSpacing: '.14em',
                      textTransform: 'uppercase',
                      color: 'var(--paper)',
                      background: 'var(--sodium)',
                      padding: '2px 5px 1px',
                      lineHeight: 1,
                    }}
                  >
                    NEW
                  </span>
                )}
              </span>
              <small
                style={{
                  display: 'block',
                  fontFamily: 'var(--font-mono)',
                  fontSize: 11,
                  fontWeight: 400,
                  lineHeight: 1,
                  color: 'var(--ink-3)',
                  textTransform: 'uppercase',
                  letterSpacing: '.1em',
                  marginTop: 3,
                }}
              >
                {e.subtitle}
              </small>
            </span>
            <span style={{ color: 'var(--ink-2)', fontSize: 11, letterSpacing: '.05em' }}>
              {e.stat}
            </span>
            <span className="lab-bar" style={{ '--w': `${e.completeness}%` } as React.CSSProperties}>
              <i className={e.leadEngine ? 'sodium' : ''} />
            </span>
          </button>
        );
      })}
    </div>
  );
}
