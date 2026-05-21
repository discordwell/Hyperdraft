/**
 * SectionHead — the lab section header.
 *
 * 160px sidebar on the left (mono "Section" caption + big sodium serial),
 * 1fr column on the right (Instrument Serif title + optional sans meta
 * paragraph). Hairline rule above the whole row.
 *
 * Extracted from Home.tsx / Replays.tsx / Gatherer.tsx where this same
 * ~80-LOC block had been inlined three times. The `metaMaxWidth` prop
 * exists because Gatherer's inline copy capped its meta at 70ch while
 * Home and Replays didn't — kept as an opt-in to preserve exact behavior.
 */

import type { ReactNode } from 'react';

interface SectionHeadProps {
  num: string;
  title: ReactNode;
  meta?: ReactNode;
  /** Optional max-width on the meta paragraph (e.g. `'70ch'`). */
  metaMaxWidth?: string;
}

export function SectionHead({ num, title, meta, metaMaxWidth }: SectionHeadProps) {
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
              ...(metaMaxWidth ? { maxWidth: metaMaxWidth } : {}),
            }}
          >
            {meta}
          </p>
        )}
      </div>
    </div>
  );
}
