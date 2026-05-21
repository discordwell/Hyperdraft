/**
 * EnginePicker — HD-ART-02 ⌘E overlay.
 *
 * Frosted scrim over the page. Engine cards in a 4×N grid. Arrow keys
 * move selection, Return loads the engine's deckbuilder, Escape closes. The
 * cards are intentionally identical in chassis — the 4-stat grid + serif
 * name + mono code — so the only difference between engines is the
 * configuration values, never the layout.
 *
 * Phase B2 (buildplan): adds a controls bar above the grid so the picker
 * still works once the engine list grows past 20+ entries. Search input on
 * the left filters by name / code / id / subtitle in real time. Sort
 * selector on the right cycles A→Z / Completeness / Untouched first. The
 * filter resets the keyboard cursor to 0 so arrow nav stays in the visible
 * subset.
 */

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { useNavigate } from 'react-router-dom';
import { LAB_ENGINES, type LabEngineMeta } from './engineMeta';
import { useCmdE } from '../../hooks/useCmdE';

interface EnginePickerProps {
  /** Hint where the picker came from — purely for footer copy. */
  context?: 'home' | 'match' | 'deckbuilder' | 'replay';
}

type SortMode = 'alpha' | 'completeness' | 'untouched';

const SORT_LABELS: Record<SortMode, string> = {
  alpha: 'A→Z',
  completeness: 'Completeness',
  untouched: 'Untouched first',
};

const SORT_ORDER: SortMode[] = ['alpha', 'completeness', 'untouched'];

/** Read localStorage.hd.played_engines defensively. */
function readPlayedEngines(): Set<string> {
  if (typeof window === 'undefined') return new Set();
  try {
    const raw = window.localStorage.getItem('hd.played_engines');
    if (!raw) return new Set();
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return new Set();
    return new Set(parsed.filter((v): v is string => typeof v === 'string'));
  } catch {
    return new Set();
  }
}

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

export function EnginePicker({ context = 'home' }: EnginePickerProps) {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [cursor, setCursor] = useState(0);
  const [query, setQuery] = useState('');
  const [sort, setSort] = useState<SortMode>('completeness');
  const rootRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);

  const toggle = useCallback(() => {
    setOpen((v) => {
      const next = !v;
      if (next) {
        // Fresh open — clear stale state.
        setCursor(0);
        setQuery('');
      }
      return next;
    });
  }, []);
  useCmdE(toggle);

  // The localStorage read happens on each open so we pick up any writes that
  // landed since last time. Stays cheap — list is tiny.
  const playedEngines = useMemo(
    () => (open ? readPlayedEngines() : new Set<string>()),
    [open],
  );

  const visibleEngines = useMemo(() => {
    const filtered = LAB_ENGINES.filter((e) => matchesQuery(e, query));
    const sorted = [...filtered];
    if (sort === 'alpha') {
      sorted.sort((a, b) => a.name.localeCompare(b.name));
    } else if (sort === 'completeness') {
      sorted.sort((a, b) => b.completeness - a.completeness);
    } else {
      // 'untouched' — untouched (not in playedEngines) first, then alpha
      // within each bucket. Falls back to pure alpha if playedEngines is
      // empty (e.g. localStorage absent or unreadable).
      sorted.sort((a, b) => {
        const aPlayed = playedEngines.has(a.id) ? 1 : 0;
        const bPlayed = playedEngines.has(b.id) ? 1 : 0;
        if (aPlayed !== bPlayed) return aPlayed - bPlayed;
        return a.name.localeCompare(b.name);
      });
    }
    return sorted;
  }, [query, sort, playedEngines]);

  const load = useCallback(
    (e: LabEngineMeta) => {
      setOpen(false);
      navigate(`/deckbuilder/${e.id}`);
    },
    [navigate],
  );

  // Reset cursor to 0 whenever the filter query (or sort, which reflows the
  // list) changes — the highlighted card might no longer exist.
  useEffect(() => {
    setCursor(0);
  }, [query, sort]);

  // Auto-focus the search input when the overlay opens.
  useEffect(() => {
    if (!open) return;
    // Defer a tick so the input is mounted before we focus it.
    const id = window.setTimeout(() => {
      searchRef.current?.focus();
    }, 0);
    return () => window.clearTimeout(id);
  }, [open]);

  // Arrow / Enter / Escape navigation while open. Operates over the
  // currently-visible filtered list. Typing into the search input does
  // NOT eat arrow keys here — happy path: user types to filter, then
  // arrows to the right card, Enter loads. Esc always closes.
  useEffect(() => {
    if (!open) return;
    const onKey = (ev: KeyboardEvent) => {
      if (ev.key === 'Escape') {
        ev.preventDefault();
        setOpen(false);
        return;
      }
      if (ev.key === 'Enter') {
        const target = visibleEngines[cursor];
        if (target) {
          ev.preventDefault();
          load(target);
        }
        return;
      }
      if (visibleEngines.length === 0) return;
      const cols = 4;
      const last = visibleEngines.length - 1;
      if (ev.key === 'ArrowRight') {
        ev.preventDefault();
        setCursor((c) => Math.min(c + 1, last));
      } else if (ev.key === 'ArrowLeft') {
        ev.preventDefault();
        setCursor((c) => Math.max(c - 1, 0));
      } else if (ev.key === 'ArrowDown') {
        ev.preventDefault();
        setCursor((c) => Math.min(c + cols, last));
      } else if (ev.key === 'ArrowUp') {
        ev.preventDefault();
        setCursor((c) => Math.max(c - cols, 0));
      }
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open, cursor, load, visibleEngines]);

  // Scroll-lock body while open
  useEffect(() => {
    if (!open) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = prev;
    };
  }, [open]);

  const footerCopy = useMemo(() => {
    switch (context) {
      case 'match':
        return 'Switching engine ends this match. Replay stays available.';
      case 'replay':
        return 'Switching engine opens the new engine\'s replay list.';
      case 'deckbuilder':
      case 'home':
      default:
        return 'Switching engine preserves your deck context. The deckbuilder reloads with the new card pool.';
    }
  }, [context]);

  if (!open) return null;

  return (
    <div
      ref={rootRef}
      role="dialog"
      aria-modal="true"
      aria-label="Switch engine"
      onClick={(e) => {
        if (e.target === rootRef.current) setOpen(false);
      }}
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 1000,
        background: 'color-mix(in oklab, var(--ink) 28%, transparent)',
        backdropFilter: 'blur(8px) saturate(1.05)',
        display: 'grid',
        placeItems: 'center',
        padding: 24,
      }}
    >
      <div
        style={{
          width: 'min(1100px, 100%)',
          maxHeight: 'calc(100vh - 48px)',
          background: 'var(--paper)',
          border: '1.5px solid var(--ink)',
          boxShadow: '0 30px 80px -30px rgba(20,24,40,.55)',
          padding: 26,
          display: 'grid',
          gridTemplateRows: 'auto auto 1fr auto',
          gap: 18,
          fontFamily: 'var(--font-sans)',
        }}
      >
        {/* Header */}
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'baseline',
            borderBottom: '1px solid var(--rule)',
            paddingBottom: 14,
          }}
        >
          <h2
            style={{
              margin: 0,
              fontFamily: 'var(--font-serif)',
              fontSize: 36,
              fontWeight: 400,
              lineHeight: 1,
              letterSpacing: '-.015em',
              color: 'var(--ink)',
            }}
          >
            Switch <em style={{ color: 'var(--sodium)', fontStyle: 'italic' }}>engine</em>.
          </h2>
          <span
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 11,
              letterSpacing: '.1em',
              textTransform: 'uppercase',
              color: 'var(--ink-3)',
            }}
          >
            ⌘E · arrows to navigate · return to load
          </span>
        </div>

        {/* Controls bar — search (left) + sort selector (right) */}
        <div
          data-testid="engine-picker-controls"
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            gap: 16,
          }}
        >
          <input
            ref={searchRef}
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Filter…"
            aria-label="Filter engines"
            data-testid="engine-picker-search"
            // Keep arrow keys from being intercepted by the input itself —
            // we want them to feed the grid cursor. Letting them bubble is
            // fine because our document-level listener preventDefaults them.
            style={{
              flex: '0 1 320px',
              padding: '6px 2px',
              background: 'transparent',
              border: 'none',
              borderBottom: '1px solid var(--rule)',
              outline: 'none',
              fontFamily: 'var(--font-mono)',
              fontSize: 12.5,
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
                  data-testid={`engine-picker-sort-${mode}`}
                  onClick={() => setSort(mode)}
                  style={{
                    padding: '6px 10px',
                    border: '1px solid var(--ink)',
                    borderLeftWidth: mode === SORT_ORDER[0] ? 1 : 0,
                    background: isActive ? 'var(--ink)' : 'transparent',
                    color: isActive ? 'var(--paper)' : 'var(--ink)',
                    fontFamily: 'var(--font-mono)',
                    fontSize: 10.5,
                    fontWeight: 500,
                    letterSpacing: '.12em',
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

        {/* Grid */}
        <div
          data-testid="engine-picker-grid"
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(4, 1fr)',
            gap: 14,
            alignContent: 'start',
            overflowY: 'auto',
          }}
        >
          {visibleEngines.length === 0 && (
            <div
              data-testid="engine-picker-empty"
              style={{
                gridColumn: '1 / -1',
                padding: '32px 14px',
                textAlign: 'center',
                fontFamily: 'var(--font-mono)',
                fontSize: 11,
                letterSpacing: '.12em',
                textTransform: 'uppercase',
                color: 'var(--ink-3)',
              }}
            >
              No engines match “{query}”.
            </div>
          )}
          {visibleEngines.map((e, i) => {
            const isActive = i === cursor;
            return (
              <button
                key={e.id}
                type="button"
                data-testid={`engine-picker-card-${e.id}`}
                onMouseEnter={() => setCursor(i)}
                onClick={() => load(e)}
                style={{
                  border: '1px solid var(--rule)',
                  outline: isActive ? '1px solid var(--ink)' : 'none',
                  outlineOffset: isActive ? -1 : 0,
                  background: 'var(--paper)',
                  padding: 14,
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 10,
                  position: 'relative',
                  minHeight: 170,
                  textAlign: 'left',
                  cursor: 'pointer',
                  fontFamily: 'var(--font-mono)',
                }}
              >
                {isActive && (
                  <span
                    style={{
                      position: 'absolute',
                      top: 10,
                      right: 10,
                      fontFamily: 'var(--font-mono)',
                      fontSize: 9.5,
                      fontWeight: 500,
                      letterSpacing: '.14em',
                      textTransform: 'uppercase',
                      color: 'var(--paper)',
                      background: 'var(--sodium)',
                      padding: '4px 6px',
                    }}
                  >
                    SELECT
                  </span>
                )}
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    fontFamily: 'var(--font-mono)',
                    fontSize: 10.5,
                    fontWeight: 500,
                    letterSpacing: '.14em',
                    textTransform: 'uppercase',
                    color: 'var(--ink-3)',
                  }}
                >
                  <span>{e.ix} · {e.code}</span>
                  <span>{e.completeness}%</span>
                </div>
                <div
                  style={{
                    display: 'grid',
                    gridTemplateColumns: '1fr 1fr',
                    gap: 8,
                    fontFamily: 'var(--font-mono)',
                    fontSize: 10.5,
                    lineHeight: 1.4,
                    color: 'var(--ink-2)',
                  }}
                >
                  {e.pickerStats.map((s, j) => (
                    <span key={j}>
                      <b style={{ color: 'var(--ink)', display: 'block', fontWeight: 600 }}>
                        {s.k}
                      </b>
                      {s.v}
                    </span>
                  ))}
                </div>
                <span
                  style={{
                    fontFamily: 'var(--font-serif)',
                    fontSize: 22,
                    fontWeight: 400,
                    letterSpacing: '-.015em',
                    color: 'var(--ink)',
                    marginTop: 'auto',
                    lineHeight: 1.05,
                  }}
                >
                  {e.name}
                  <small
                    style={{
                      display: 'block',
                      fontFamily: 'var(--font-mono)',
                      fontSize: 11,
                      fontWeight: 400,
                      color: 'var(--ink-3)',
                      textTransform: 'uppercase',
                      letterSpacing: '.08em',
                      marginTop: 6,
                    }}
                  >
                    {e.subtitle}
                  </small>
                </span>
              </button>
            );
          })}
        </div>

        {/* Footer */}
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            borderTop: '1px solid var(--rule)',
            paddingTop: 14,
            fontFamily: 'var(--font-mono)',
            fontSize: 11,
            letterSpacing: '.1em',
            textTransform: 'uppercase',
            color: 'var(--ink-3)',
          }}
        >
          <span style={{ textTransform: 'none', letterSpacing: 0 }}>{footerCopy}</span>
          <span>HD-ENGINE-PICKER</span>
        </div>
      </div>
    </div>
  );
}
