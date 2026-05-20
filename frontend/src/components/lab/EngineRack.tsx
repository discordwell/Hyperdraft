/**
 * EngineRack — HD-ART-01 right-column engine rack.
 *
 * Eight engines, ranked by completeness, with a single accented stat and a
 * monochrome bar. Clicking a row dispatches navigateToEngine; the parent
 * decides where that goes (deckbuilder, new match, picker overlay).
 */

import { LAB_ENGINES } from './engineMeta';
import type { GameModeId } from '../brand/modes';

interface EngineRackProps {
  activeId?: GameModeId;
  onSelect?: (id: GameModeId) => void;
}

export function EngineRack({ activeId, onSelect }: EngineRackProps) {
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

      {LAB_ENGINES.map((e) => {
        const isActive = e.id === activeId;
        return (
          <button
            key={e.id}
            type="button"
            aria-label={e.name}
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
                  display: 'block',
                }}
              >
                {e.name}
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
