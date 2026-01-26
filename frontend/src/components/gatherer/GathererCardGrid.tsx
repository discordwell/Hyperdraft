/**
 * Gatherer Card Grid Component
 *
 * Displays cards in a responsive grid with infinite scroll.
 * Uses intersection observer for loading more cards.
 */

import { useEffect, useRef, useCallback } from 'react';
import { useGathererStore } from '../../stores/gathererStore';
import { SketchCard } from './SketchCard';

function EmptyState() {
  const { currentSet, filter } = useGathererStore();

  if (!currentSet) {
    return (
      <div className="flex-1 flex items-center justify-center text-gray-400">
        <div className="text-center">
          <div className="text-6xl mb-4">📚</div>
          <h3 className="text-xl font-semibold mb-2">Select a Set</h3>
          <p className="text-sm">Choose a set from the sidebar to browse cards</p>
        </div>
      </div>
    );
  }

  const hasFilters =
    (filter.types && filter.types.length > 0) ||
    (filter.colors && filter.colors.length > 0) ||
    filter.rarity ||
    filter.textSearch;

  return (
    <div className="flex-1 flex items-center justify-center text-gray-400">
      <div className="text-center">
        <div className="text-6xl mb-4">🔍</div>
        <h3 className="text-xl font-semibold mb-2">No Cards Found</h3>
        <p className="text-sm">
          {hasFilters
            ? 'Try adjusting your filters'
            : 'This set appears to be empty'}
        </p>
      </div>
    </div>
  );
}

function LoadingState() {
  return (
    <div className="flex items-center justify-center py-8">
      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-game-accent"></div>
      <span className="ml-3 text-gray-400">Loading cards...</span>
    </div>
  );
}

export function GathererCardGrid() {
  const {
    cards,
    cardsLoading,
    cardsHasMore,
    currentSet,
    loadMoreCards,
    selectCard,
  } = useGathererStore();

  const observerRef = useRef<IntersectionObserver | null>(null);
  const loadMoreRef = useRef<HTMLDivElement>(null);

  // Set up intersection observer for infinite scroll
  const handleObserver = useCallback(
    (entries: IntersectionObserverEntry[]) => {
      const [entry] = entries;
      if (entry.isIntersecting && cardsHasMore && !cardsLoading) {
        loadMoreCards();
      }
    },
    [cardsHasMore, cardsLoading, loadMoreCards]
  );

  useEffect(() => {
    if (observerRef.current) {
      observerRef.current.disconnect();
    }

    observerRef.current = new IntersectionObserver(handleObserver, {
      root: null,
      rootMargin: '200px',
      threshold: 0,
    });

    if (loadMoreRef.current) {
      observerRef.current.observe(loadMoreRef.current);
    }

    return () => {
      if (observerRef.current) {
        observerRef.current.disconnect();
      }
    };
  }, [handleObserver]);

  if (!currentSet) {
    return <EmptyState />;
  }

  if (cards.length === 0 && cardsLoading) {
    return (
      <div className="flex-1 p-6">
        <LoadingState />
      </div>
    );
  }

  if (cards.length === 0) {
    return <EmptyState />;
  }

  return (
    <div className="flex-1 overflow-y-auto p-6">
      {/* Card grid */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 2xl:grid-cols-6 gap-4">
        {cards.map((card) => (
          <SketchCard
            key={card.name}
            card={card}
            setCode={currentSet?.code}
            onClick={() => selectCard(card)}
          />
        ))}
      </div>

      {/* Load more trigger */}
      <div ref={loadMoreRef} className="py-4">
        {cardsLoading && <LoadingState />}
        {!cardsLoading && cardsHasMore && (
          <div className="text-center text-gray-500 text-sm">
            Scroll for more...
          </div>
        )}
        {!cardsLoading && !cardsHasMore && cards.length > 0 && (
          <div className="text-center text-gray-500 text-sm py-4">
            Showing all {cards.length} cards
          </div>
        )}
      </div>
    </div>
  );
}

export default GathererCardGrid;
