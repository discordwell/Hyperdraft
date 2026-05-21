/**
 * LabPaginationFooter — Gatherer load-more / pagination controls
 * (Phase C / follow-up 11a).
 *
 * Lives inside the LabCardGrid body. Owns:
 *   - the IntersectionObserver sentinel that auto-loads the next page when
 *     it scrolls into view (`rootMargin: 200px` so we trigger before the
 *     user actually hits the bottom),
 *   - the streaming-pulse "Loading more…" eyebrow,
 *   - the explicit "Load more" button (fallback when the observer hasn't
 *     fired — e.g. very short viewports or accessibility users without
 *     intersection observers),
 *   - the terminal "Showing all N" stamp when the page is fully loaded.
 *
 * Reads `cards.length` / `cardsLoading` / `cardsHasMore` and dispatches
 * `loadMoreCards` from `useGathererStore`.
 */

import { useEffect, useRef, useCallback } from 'react';
import { useGathererStore } from '../../stores/gathererStore';

export function LabPaginationFooter() {
  const { cards, cardsLoading, cardsHasMore, loadMoreCards } = useGathererStore();
  const loadMoreRef = useRef<HTMLDivElement>(null);

  const handleObserver = useCallback(
    (entries: IntersectionObserverEntry[]) => {
      const [entry] = entries;
      if (entry.isIntersecting && cardsHasMore && !cardsLoading) {
        loadMoreCards();
      }
    },
    [cardsHasMore, cardsLoading, loadMoreCards],
  );

  useEffect(() => {
    const obs = new IntersectionObserver(handleObserver, {
      root: null,
      rootMargin: '200px',
      threshold: 0,
    });
    const node = loadMoreRef.current;
    if (node) obs.observe(node);
    return () => obs.disconnect();
  }, [handleObserver]);

  return (
    <div ref={loadMoreRef} style={{ paddingTop: cards.length > 0 ? 20 : 0 }}>
      {cardsLoading && cards.length > 0 && (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 10,
            fontFamily: 'var(--font-mono)',
            fontSize: 11,
            letterSpacing: '.14em',
            textTransform: 'uppercase',
            color: 'var(--ink-3)',
            padding: '8px 0',
          }}
        >
          <span
            style={{
              width: 9,
              height: 9,
              borderRadius: '50%',
              background: 'var(--sodium)',
              animation: 'gatherer-pulse 1.6s ease-in-out infinite',
            }}
          />
          Loading more…
        </div>
      )}
      {!cardsLoading && cardsHasMore && cards.length > 0 && (
        <div
          style={{
            display: 'flex',
            justifyContent: 'center',
            padding: '8px 0',
          }}
        >
          <button
            type="button"
            onClick={() => loadMoreCards()}
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 11,
              fontWeight: 500,
              letterSpacing: '.14em',
              textTransform: 'uppercase',
              padding: '8px 14px',
              background: 'transparent',
              color: 'var(--ink)',
              border: '1px solid var(--ink)',
              cursor: 'pointer',
            }}
          >
            Load more
          </button>
        </div>
      )}
      {!cardsLoading && !cardsHasMore && cards.length > 0 && (
        <div
          style={{
            textAlign: 'center',
            padding: '8px 0',
            fontFamily: 'var(--font-mono)',
            fontSize: 11,
            letterSpacing: '.1em',
            textTransform: 'uppercase',
            color: 'var(--ink-3)',
          }}
        >
          Showing all {cards.length}
        </div>
      )}
    </div>
  );
}
