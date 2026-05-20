/**
 * Section — content block with an eyebrow + display heading + optional rule.
 *
 * The vertical foil tick on the left margin is the "shelf marker" — a
 * 2px bar in foil-gold that visually anchors each section to the
 * archive-cabinet metaphor.
 */

import { ReactNode } from 'react';

export interface SectionProps {
  /** Tracked-out micro-caps eyebrow (e.g. "01 · Choose your engine"). */
  eyebrow?: string;
  /** Display heading (renders in Fraunces). */
  title?: ReactNode;
  /** Right-aligned slot next to the title (e.g. links, filters). */
  trailing?: ReactNode;
  /** Hide the bottom hairline divider beneath the heading. */
  noRule?: boolean;
  /** Disable the left foil-tick marker for hero / borderless sections. */
  noMarker?: boolean;
  className?: string;
  children: ReactNode;
}

export function Section({
  eyebrow,
  title,
  trailing,
  noRule,
  noMarker,
  className,
  children,
}: SectionProps) {
  return (
    <section className={'relative py-10 lg:py-14 ' + (className ?? '')}>
      {!noMarker && (
        <span
          className="absolute left-[-16px] top-12 h-12 w-[2px] bg-brand-foil"
          aria-hidden
        />
      )}
      {(eyebrow || title || trailing) && (
        <header className="flex items-end justify-between gap-6 mb-6">
          <div>
            {eyebrow && <p className="brand-eyebrow mb-2">{eyebrow}</p>}
            {title && (
              <h2 className="text-3xl md:text-4xl font-display font-bold leading-tight text-brand-cream">
                {title}
              </h2>
            )}
          </div>
          {trailing && <div className="text-sm text-brand-chalk">{trailing}</div>}
        </header>
      )}
      {!noRule && (title || eyebrow) && <div className="brand-hairline mb-8" />}
      {children}
    </section>
  );
}

export default Section;
