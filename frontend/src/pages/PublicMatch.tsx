/**
 * PublicMatch — HD-CRIT BIG MOVE 19. Public, unauthenticated spectator URLs.
 *
 *   /m/:gameId   →   anyone can watch any AI match
 *
 * The wrapper renders a lab-styled masthead (short-code, engine chip, acid
 * "Watching publicly" pulse, Copy-link) above the existing SpectatorView.
 *
 * The outer route uses `:gameId` (matching SpectatorView's own param name)
 * so SpectatorView's untouched `useParams()` picks up the id from this
 * route's match. No nested router needed, no signature change.
 *
 * Note: the spec calls the URL slot "matchId"; we keep "gameId" in the
 * route definition strictly to match SpectatorView's existing useParams
 * key. The user-facing concept (and on-page label / footer copy) is still
 * "match".
 */
import { lazy, Suspense, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useParams } from 'react-router-dom';

const SpectatorView = lazy(() => import('./SpectatorView'));

/**
 * Render a stable short code for a match identifier. Backend currently issues
 * UUID-style IDs; if/when it ships HD-XXXX shorts they'll fall through
 * unchanged. This is a frontend display projection only — the canonical ID
 * stays in the URL.
 */
export function shortCode(matchId: string | undefined): string {
  if (!matchId) return 'HD-????';
  const trimmed = matchId.trim();
  if (/^HD-[A-Z0-9]{4,}$/i.test(trimmed)) return trimmed.toUpperCase();
  // Strip non-alphanumerics, uppercase, take the first 4 chars — stable per ID.
  const cleaned = trimmed.replace(/[^a-zA-Z0-9]/g, '').toUpperCase();
  const head = cleaned.slice(0, 4) || '????';
  return `HD-${head.padEnd(4, '0')}`;
}

export function PublicMatch() {
  // Outer route is `/m/:gameId` so the same useParams key flows into
  // SpectatorView below without any signature change.
  const { gameId: matchId } = useParams<{ gameId: string }>();
  const [copied, setCopied] = useState(false);
  const copyTimer = useRef<number | null>(null);

  const code = useMemo(() => shortCode(matchId), [matchId]);

  useEffect(() => {
    return () => {
      if (copyTimer.current !== null) window.clearTimeout(copyTimer.current);
    };
  }, []);

  const handleCopy = async () => {
    try {
      // navigator.clipboard is available in modern browsers and in happy-dom
      // when the test mocks it. Wrap in try/catch so an absent clipboard or a
      // permissions-denied error never crashes the page.
      await navigator.clipboard.writeText(window.location.href);
      setCopied(true);
      if (copyTimer.current !== null) window.clearTimeout(copyTimer.current);
      copyTimer.current = window.setTimeout(() => setCopied(false), 1500);
    } catch {
      // Fall back to a brief flash so the user still gets feedback even if
      // clipboard access was denied.
      setCopied(true);
      if (copyTimer.current !== null) window.clearTimeout(copyTimer.current);
      copyTimer.current = window.setTimeout(() => setCopied(false), 1500);
    }
  };

  return (
    <div className="min-h-screen bg-brand-ink text-brand-cream flex flex-col">
      {/* === Masthead ====================================================== */}
      <header className="border-b border-brand-hairline/60 bg-brand-obsidian/85 backdrop-blur-xl sticky top-0 z-40">
        <div className="max-w-[1600px] mx-auto px-4 lg:px-8 py-3 flex flex-wrap items-center gap-x-6 gap-y-3">
          {/* short-code + wordmark */}
          <div className="flex items-baseline gap-3">
            <Link
              to="/"
              className="brand-eyebrow text-brand-dust hover:text-brand-foil transition-colors"
            >
              ← hyperdraft
            </Link>
            <span
              className="brand-mono text-base lg:text-lg tracking-tight text-brand-cream"
              data-testid="public-match-shortcode"
              aria-label="Match short code"
            >
              {code}
            </span>
          </div>

          {/* engine chip — placeholder until backend surfaces game_mode here.
              Kept visually so the chrome reads as designed; the chip reads
              "match" when the engine isn't yet known. */}
          <span className="px-2 py-0.5 border border-brand-hairline bg-brand-shelf brand-mono text-[11px] tracking-wider uppercase text-brand-chalk">
            match
          </span>

          {/* live / public pulse — uses .brand-live-dot keyframe but recoloured
              to the acid/spore token per HD-PAL "acid" indicator. */}
          <div className="flex items-center gap-2" aria-live="polite">
            <span
              aria-hidden
              className="inline-block w-2 h-2 rounded-full"
              style={{
                background: 'var(--brand-spore, #a3e635)',
                boxShadow:
                  '0 0 0 0 rgba(163, 230, 53, 0.55), 0 0 10px rgba(163, 230, 53, 0.65)',
                animation: 'public-match-acid-pulse 1.8s ease-in-out infinite',
              }}
            />
            <span className="brand-eyebrow text-brand-chalk">Watching publicly</span>
          </div>

          {/* Copy link — mono, ink-outlined */}
          <div className="ml-auto flex items-center gap-3">
            <button
              type="button"
              onClick={handleCopy}
              className="px-3 py-1.5 border border-brand-hairline hover:border-brand-foil/70 bg-brand-obsidian hover:bg-brand-shelf transition-colors brand-mono text-xs tracking-tight text-brand-cream flex items-center gap-2"
              aria-label="Copy public match link to clipboard"
            >
              <span aria-hidden>{copied ? '✓' : '⧉'}</span>
              <span>{copied ? 'Copied' : 'Copy link'}</span>
            </button>
          </div>
        </div>

        {/* Inline keyframe so we don't have to touch index.css for this
            one indicator. Scoped via a unique animation name. */}
        <style>{`
          @keyframes public-match-acid-pulse {
            0%, 100% {
              box-shadow: 0 0 0 0 rgba(163, 230, 53, 0.55),
                          0 0 10px rgba(163, 230, 53, 0.65);
            }
            50% {
              box-shadow: 0 0 0 6px rgba(163, 230, 53, 0),
                          0 0 14px rgba(163, 230, 53, 0.85);
            }
          }
        `}</style>
      </header>

      {/* === Spectator body =============================================== */}
      <main className="flex-1 relative">
        {matchId ? (
          <Suspense
            fallback={
              <div className="flex items-center justify-center min-h-[60vh]">
                <div className="flex flex-col items-center gap-3 text-brand-chalk">
                  <div className="w-10 h-10 border-2 border-brand-hairline border-t-brand-foil rounded-full animate-spin" />
                  <span className="brand-eyebrow">Joining match</span>
                </div>
              </div>
            }
          >
            {/* SpectatorView reads `gameId` from useParams; we mounted the
                outer route as `/m/:gameId` so the same id flows through
                without nesting a router or changing the signature. */}
            <SpectatorView />
          </Suspense>
        ) : (
          <div className="flex items-center justify-center min-h-[60vh]">
            <p className="text-brand-chalk">No match id supplied.</p>
          </div>
        )}
      </main>

      {/* === Footer rail ================================================== */}
      <footer className="border-t border-brand-hairline/60 mt-0 py-4 px-4 lg:px-8">
        <div className="max-w-[1600px] mx-auto flex flex-wrap items-center justify-between gap-3 brand-mono text-[10px] tracking-[0.2em] uppercase text-brand-dust">
          <span>HD-MATCH-PUBLIC · LINK YOURS · NO LOGIN</span>
          <span className="text-brand-dust">{code}</span>
        </div>
      </footer>
    </div>
  );
}

export default PublicMatch;
