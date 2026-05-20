/**
 * EnginePicker — HD-ART-02 ⌘E overlay.
 *
 * Frosted scrim over the page. Eight engine cards in a 4×2 grid. Arrow keys
 * move selection, Return loads the engine's deckbuilder, Escape closes. The
 * cards are intentionally identical in chassis — the 4-stat grid + serif
 * name + mono code — so the only difference between engines is the
 * configuration values, never the layout.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { LAB_ENGINES, type LabEngineMeta } from './engineMeta';
import { useCmdE } from '../../hooks/useCmdE';

interface EnginePickerProps {
  /** Hint where the picker came from — purely for footer copy. */
  context?: 'home' | 'match' | 'deckbuilder' | 'replay';
}

export function EnginePicker({ context = 'home' }: EnginePickerProps) {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [cursor, setCursor] = useState(0);
  const rootRef = useRef<HTMLDivElement>(null);

  const toggle = useCallback(() => {
    setOpen((v) => !v);
    setCursor(0);
  }, []);
  useCmdE(toggle);

  const load = useCallback(
    (e: LabEngineMeta) => {
      setOpen(false);
      navigate(`/deckbuilder/${e.id}`);
    },
    [navigate],
  );

  // Arrow / Enter / Escape navigation while open
  useEffect(() => {
    if (!open) return;
    const onKey = (ev: KeyboardEvent) => {
      if (ev.key === 'Escape') {
        ev.preventDefault();
        setOpen(false);
        return;
      }
      if (ev.key === 'Enter') {
        ev.preventDefault();
        load(LAB_ENGINES[cursor]);
        return;
      }
      const cols = 4;
      const last = LAB_ENGINES.length - 1;
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
  }, [open, cursor, load]);

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
          gridTemplateRows: 'auto 1fr auto',
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

        {/* Grid */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(4, 1fr)',
            gap: 14,
          }}
        >
          {LAB_ENGINES.map((e, i) => {
            const isActive = i === cursor;
            return (
              <button
                key={e.id}
                type="button"
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
