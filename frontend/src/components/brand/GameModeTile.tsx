/**
 * GameModeTile — the foil-sweeping selector card on the Home grid.
 *
 * On hover, the diagonal holographic gradient sweeps across (driven by the
 * .brand-tile::before pseudo in index.css). The corner brackets evoke a
 * card-grading-case crop, and the monogram + blurb anchor the bottom.
 *
 * Clickable when used as a selector (default); add `as="a"` style routing
 * via the wrapping <Link> in the caller — the tile itself is a button
 * for the "pick this mode" action.
 */

import { motion } from 'framer-motion';
import { ACCENT_CLASSES, type GameModeMeta } from './modes';
import { Monogram } from './Monogram';

export interface GameModeTileProps {
  mode: GameModeMeta;
  selected?: boolean;
  onClick?: () => void;
  /** Optional metric line, e.g. "281 cards · 12 decks". */
  meta?: string;
  /** Stagger delay for the entrance animation (rise + fade). */
  delaySeconds?: number;
}

export function GameModeTile({
  mode,
  selected,
  onClick,
  meta,
  delaySeconds = 0,
}: GameModeTileProps) {
  const accent = ACCENT_CLASSES[mode.accent];
  return (
    <motion.button
      type="button"
      onClick={onClick}
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.6, delay: delaySeconds, ease: [0.22, 0.8, 0.3, 1] }}
      whileHover={{ y: -2 }}
      className={
        'brand-tile brand-frame group text-left flex flex-col gap-4 ' +
        'p-5 lg:p-6 min-h-[210px] shadow-brand-tile ' +
        'transition-shadow duration-300 ' +
        (selected
          ? `ring-1 ${accent.ring} ${accent.glow}`
          : 'hover:shadow-[0_28px_60px_-22px_rgba(0,0,0,0.7)]')
      }
      aria-pressed={selected}
      aria-label={mode.name}
    >
      <div className="flex items-start justify-between">
        <div className="flex flex-col gap-1">
          <span className="brand-eyebrow">{mode.code}</span>
          <span className="text-lg lg:text-xl font-display font-semibold text-brand-cream leading-tight">
            {mode.name}
          </span>
        </div>
        <Monogram mode={mode} variant={selected ? 'mode' : 'foil'} size={42} />
      </div>

      <p className="text-sm text-brand-chalk leading-relaxed flex-1">{mode.blurb}</p>

      <footer className="flex items-center justify-between text-xs text-brand-dust">
        {meta ? <span className="brand-mono tracking-tight">{meta}</span> : <span />}
        <span
          className={
            'opacity-0 group-hover:opacity-100 transition-opacity duration-300 ' +
            'flex items-center gap-1 ' +
            accent.text
          }
        >
          Choose <span aria-hidden>→</span>
        </span>
      </footer>
    </motion.button>
  );
}

export default GameModeTile;
