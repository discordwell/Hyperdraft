/**
 * PokemonCardGrid
 *
 * Infinite-scroll grid for the Pokemon gatherer.
 */

import { useEffect, useRef } from 'react';
import { usePokemonGathererStore } from '../../stores/pokemonGathererStore';
import { hasActivePokemonFilters } from '../../types/pokemonGatherer';
import { PokemonCardCell } from './PokemonCardCell';

function LoadingState() {
  return (
    <div className="flex items-center justify-center py-8">
      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-game-accent" />
      <span className="ml-3 text-gray-400">Loading cards...</span>
    </div>
  );
}

function EmptyState({ withFilters }: { withFilters: boolean }) {
  return (
    <div className="flex-1 flex items-center justify-center text-gray-400">
      <div className="text-center">
        <div className="text-6xl mb-4">{withFilters ? '🔍' : '📚'}</div>
        <h3 className="text-xl font-semibold mb-2">
          {withFilters ? 'No Cards Found' : 'Select a Set'}
        </h3>
        <p className="text-sm">
          {withFilters
            ? 'Try adjusting your filters'
            : 'Choose a Pokemon set from the sidebar'}
        </p>
      </div>
    </div>
  );
}

export function PokemonCardGrid() {
  const {
    cards,
    cardsLoading,
    cardsHasMore,
    currentSet,
    filter,
    loadMoreCards,
    selectCard,
  } = usePokemonGathererStore();

  const observerRef = useRef<IntersectionObserver | null>(null);
  const loadMoreRef = useRef<HTMLDivElement>(null);
  // Stash the live state in refs so the IntersectionObserver can be
  // built once on mount instead of being torn down on every cards /
  // cardsLoading change. Without this, every page-load mid-scroll
  // disconnects + recreates the observer, which can spuriously re-fire
  // `isIntersecting` immediately and request the same offset twice.
  const stateRef = useRef({ cardsHasMore, cardsLoading, loadMoreCards });
  stateRef.current = { cardsHasMore, cardsLoading, loadMoreCards };

  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        const [entry] = entries;
        const { cardsHasMore, cardsLoading, loadMoreCards } = stateRef.current;
        if (entry.isIntersecting && cardsHasMore && !cardsLoading) {
          loadMoreCards();
        }
      },
      { root: null, rootMargin: '200px', threshold: 0 }
    );
    observerRef.current = observer;
    if (loadMoreRef.current) observer.observe(loadMoreRef.current);
    return () => observer.disconnect();
  }, []);

  // Keep the observer pointed at loadMoreRef even if React swaps the
  // node (e.g. when cards transition from empty to non-empty).
  useEffect(() => {
    const obs = observerRef.current;
    const node = loadMoreRef.current;
    if (!obs || !node) return;
    obs.observe(node);
    return () => obs.unobserve(node);
  }, [cards.length === 0]);

  if (!currentSet) return <EmptyState withFilters={false} />;
  if (cards.length === 0 && cardsLoading) {
    return (
      <div className="flex-1 p-6">
        <LoadingState />
      </div>
    );
  }

  if (cards.length === 0) {
    return <EmptyState withFilters={hasActivePokemonFilters(filter)} />;
  }

  return (
    <div className="flex-1 overflow-y-auto p-6">
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 2xl:grid-cols-6 gap-4">
        {cards.map((card) => (
          <PokemonCardCell
            key={`${card.name}-${card.supertype}`}
            card={card}
            onClick={() => selectCard(card)}
          />
        ))}
      </div>

      <div ref={loadMoreRef} className="py-4">
        {cardsLoading && <LoadingState />}
        {!cardsLoading && cardsHasMore && (
          <div className="text-center text-gray-500 text-sm">Scroll for more...</div>
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

export default PokemonCardGrid;
