/**
 * Monogram — per-mode 3-letter glyph in a Fraunces variable display.
 *
 * Used in GameModeTile + the GameView header chip + breadcrumbs. Renders
 * as type, NOT an emoji — so it scales crisp at any size and inherits the
 * surrounding color (foil for primary, cream for secondary).
 */

import { CSSProperties } from 'react';
import type { GameModeMeta } from './modes';

export interface MonogramProps {
  mode: GameModeMeta;
  /** Pixel size of the glyph (the surrounding frame scales 1.6x). */
  size?: number;
  /** Render mode: 'foil' (gold gradient), 'cream' (flat), or 'mode' (uses mode accent). */
  variant?: 'foil' | 'cream' | 'mode';
  className?: string;
}

const ACCENT_TEXT: Record<GameModeMeta['accent'], string> = {
  gold: 'text-brand-foil',
  sheen: 'text-brand-sheen',
  ember: 'text-brand-ember',
  spore: 'text-brand-spore',
  violet: 'text-brand-violet',
};

export function Monogram({ mode, size = 48, variant = 'foil', className }: MonogramProps) {
  const style: CSSProperties = {
    fontSize: `${size}px`,
    fontVariationSettings: `"opsz" 144, "wght" 800`,
  };
  const tone =
    variant === 'foil'
      ? 'brand-foil-text'
      : variant === 'cream'
      ? 'text-brand-cream'
      : ACCENT_TEXT[mode.accent];
  return (
    <span
      className={
        'inline-block font-display leading-none tracking-[-0.06em] ' +
        tone +
        ' ' +
        (className ?? '')
      }
      style={style}
      aria-label={mode.title}
    >
      {mode.code}
    </span>
  );
}

export default Monogram;
