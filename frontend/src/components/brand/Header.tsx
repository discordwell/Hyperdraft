/**
 * Header — top nav with wordmark + right-side slot.
 *
 * Sticky, semi-transparent over the brand-ink canvas. The wordmark uses
 * variable Fraunces with a foil-gradient sweep that pans softly so it
 * reads as a stamped foil on a card-grading case rather than a flat logo.
 */

import { ReactNode } from 'react';
import { Link, useLocation } from 'react-router-dom';

export interface HeaderProps {
  /** Right-aligned slot — typically nav links or a sign-in pill. */
  right?: ReactNode;
}

const NAV_ITEMS: { label: string; to: string }[] = [
  { label: 'Play', to: '/' },
  { label: 'Watch', to: '/watch/live' },
  { label: 'Replays', to: '/replays' },
  { label: 'Decks', to: '/deckbuilder' },
  { label: 'Cards', to: '/gatherer' },
];

export function Header({ right }: HeaderProps) {
  const location = useLocation();
  const isHome = location.pathname === '/';
  return (
    <header className="sticky top-0 z-30 backdrop-blur-xl bg-brand-ink/70 border-b border-brand-hairline/60">
      <div className="mx-auto max-w-7xl px-6 lg:px-10 h-16 flex items-center gap-8">
        <Link
          to="/"
          className="brand-wordmark text-[1.55rem] leading-none brand-foil-text select-none"
          aria-label="Hyperdraft home"
        >
          hyperdraft
        </Link>

        <nav className="hidden md:flex items-center gap-1 -ml-1">
          {NAV_ITEMS.map((item) => {
            const active =
              item.to === '/'
                ? isHome
                : location.pathname.startsWith(item.to);
            return (
              <Link
                key={item.to}
                to={item.to}
                className={
                  'px-3 py-1.5 text-sm tracking-wide transition relative ' +
                  (active
                    ? 'text-brand-cream'
                    : 'text-brand-chalk hover:text-brand-cream')
                }
              >
                {item.label}
                {active && (
                  <span
                    className="absolute left-3 right-3 -bottom-[18px] h-[2px] bg-brand-foil"
                    aria-hidden
                  />
                )}
              </Link>
            );
          })}
        </nav>

        <div className="flex-1" />

        <div className="flex items-center gap-3 text-xs text-brand-chalk">
          {right}
        </div>
      </div>
    </header>
  );
}

export default Header;
