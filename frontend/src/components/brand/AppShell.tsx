/**
 * AppShell — top-level page wrapper.
 *
 * Provides the atmospheric backdrop (gradient mesh + caliper grid) and the
 * max-width container that all page bodies sit inside. Use directly inside
 * route components instead of duplicating the wrapper divs.
 */

import { ReactNode } from 'react';
import { Header } from './Header';

export interface AppShellProps {
  /** Optional page-specific header content (renders inside <Header>). */
  headerRight?: ReactNode;
  /** Disable the caliper-grid backdrop for views that want a clean canvas. */
  noGrid?: boolean;
  /** Render content edge-to-edge instead of inside the centered container. */
  flush?: boolean;
  children: ReactNode;
}

export function AppShell({ headerRight, noGrid, flush, children }: AppShellProps) {
  return (
    <div className="min-h-screen bg-brand-ink text-brand-cream relative">
      {!noGrid && (
        <div
          className="pointer-events-none fixed inset-0 brand-grid-bg opacity-60"
          aria-hidden
        />
      )}
      {/* Top-of-canvas warm haze, like cabinet-light spilling over the shelf */}
      <div
        className="pointer-events-none fixed inset-x-0 top-0 h-[320px] opacity-70"
        style={{
          background:
            'radial-gradient(ellipse 80% 80% at 50% 0%, rgba(203,161,78,0.12) 0%, transparent 60%)',
        }}
        aria-hidden
      />
      <Header right={headerRight} />
      <main className={flush ? 'relative' : 'relative mx-auto max-w-7xl px-6 lg:px-10'}>
        {children}
      </main>
    </div>
  );
}

export default AppShell;
