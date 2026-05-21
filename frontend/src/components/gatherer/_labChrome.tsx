/**
 * Internal lab-chrome helpers shared across the Gatherer sub-components.
 *
 * Phase C / follow-up 11a. These primitives (mono `Eyebrow` label, paper
 * inputs / selects / chip buttons) were inlined into `Gatherer.tsx` during
 * the lab port. They're factored here so the Lab* sub-components can share
 * the same vocabulary without re-declaring identical CSS. Underscore prefix
 * keeps this file out of the public `index.ts` barrel — these are an
 * implementation detail of the gatherer surface.
 */

import type { CSSProperties, ReactNode } from 'react';

export function Eyebrow({ children }: { children: ReactNode }) {
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

export const inputStyle: CSSProperties = {
  background: 'var(--paper)',
  border: '1px solid var(--rule)',
  padding: '7px 10px',
  fontFamily: 'var(--font-mono)',
  fontSize: 12,
  color: 'var(--ink)',
  outline: 'none',
  width: '100%',
};

export const selectStyle: CSSProperties = {
  background: 'var(--paper)',
  border: '1px solid var(--rule)',
  padding: '7px 10px',
  fontFamily: 'var(--font-mono)',
  fontSize: 12,
  color: 'var(--ink)',
  outline: 'none',
  cursor: 'pointer',
};

export function chipButtonStyle(active: boolean): CSSProperties {
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
