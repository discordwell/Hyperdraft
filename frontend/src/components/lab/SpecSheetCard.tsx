/**
 * SpecSheetCard — engine-agnostic card chip.
 *
 * The three lines (cost/kind, name, stats) stay constant across all eight
 * engines — only the labels change. When `imageUrl` is provided the card
 * renders the real art in the middle slot with a paper title bar at the
 * bottom; without it the middle slot is a name-only spec-sheet (the
 * original geometric-glyph-free layout).
 */

import type { CSSProperties } from 'react';

export type CardState = 'idle' | 'tapped' | 'selected' | 'face-down';

interface SpecSheetCardProps {
  cost?: string;     // {2R}, {1U}, "land", "—", etc.
  kind?: string;     // cr, inst, sorc, art, land, mon, trap, ene
  name: string;
  primary?: string;  // "3/3", "70 HP", "1500 ATK"
  secondary?: string; // "haste", "fly", "+counter"
  /** Optional real card art. URL pattern: `/api/card-art/<engine>/<set>/<slug>.png`. */
  imageUrl?: string;
  state?: CardState;
  width?: number;
  height?: number;
  className?: string;
  onClick?: () => void;
}

export function SpecSheetCard({
  cost,
  kind,
  name,
  primary,
  secondary,
  imageUrl,
  state = 'idle',
  width = 62,
  height = 84,
  className,
  onClick,
}: SpecSheetCardProps) {
  const style: CSSProperties = {
    width,
    height,
    border: '1px solid var(--ink)',
    background: state === 'face-down' ? undefined : 'var(--paper)',
    display: 'grid',
    gridTemplateRows: 'auto 1fr auto',
    padding: 5,
    font: '500 9px/1 var(--font-mono)',
    letterSpacing: '.04em',
    color: 'var(--ink)',
    position: 'relative',
    boxShadow: '0 1px 0 var(--ink) inset',
    cursor: onClick ? 'pointer' : 'default',
    transform: state === 'tapped' ? 'rotate(7deg)' : undefined,
    opacity: state === 'tapped' ? 0.85 : 1,
    outline: state === 'selected' ? '2px solid var(--sodium)' : undefined,
    outlineOffset: state === 'selected' ? 1 : undefined,
  };

  if (state === 'face-down') {
    return (
      <div
        className={`lab-hatch ${className ?? ''}`.trim()}
        style={style}
        onClick={onClick}
        aria-label="face-down card"
      />
    );
  }

  return (
    <div className={className} style={style} onClick={onClick}>
      <div style={{ display: 'flex', justifyContent: 'space-between', color: 'var(--ink-3)' }}>
        <span>{cost ?? ''}</span>
        <span>{kind ?? ''}</span>
      </div>
      {imageUrl ? (
        <div
          style={{
            position: 'relative',
            overflow: 'hidden',
            margin: '2px -3px 0',
            border: '1px solid var(--rule-2)',
          }}
        >
          <img
            src={imageUrl}
            alt={name}
            loading="lazy"
            style={{
              width: '100%',
              height: '100%',
              objectFit: 'cover',
              display: 'block',
            }}
          />
          <div
            style={{
              position: 'absolute',
              left: 0,
              right: 0,
              bottom: 0,
              padding: '2px 4px',
              background: 'color-mix(in oklab, var(--paper) 88%, transparent)',
              borderTop: '1px solid var(--rule-2)',
              fontFamily: 'var(--font-serif)',
              fontSize: 10,
              lineHeight: 1.05,
              letterSpacing: '-.005em',
              color: 'var(--ink)',
              fontWeight: 400,
            }}
          >
            {name}
          </div>
        </div>
      ) : (
        <div
          style={{
            fontFamily: 'var(--font-serif)',
            fontSize: 11,
            letterSpacing: '-.005em',
            lineHeight: 1.05,
            textAlign: 'left',
            color: 'var(--ink)',
            alignSelf: 'end',
            fontWeight: 400,
          }}
        >
          {name}
        </div>
      )}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          color: 'var(--ink-2)',
          fontSize: 8.5,
          letterSpacing: '.04em',
        }}
      >
        <span>{primary ?? ''}</span>
        <span>{secondary ?? ''}</span>
      </div>
    </div>
  );
}
