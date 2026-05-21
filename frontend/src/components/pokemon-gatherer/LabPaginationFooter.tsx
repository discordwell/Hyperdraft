/**
 * LabPaginationFooter — the "Showing X of Y · Load more" row beneath the
 * card grid.
 *
 * Hairline-ruled top border, mono counters on the left, sodium pulse for
 * loading state, ink-filled load-more button for the next page. Only renders
 * when a set is selected and at least one card has been fetched — otherwise
 * the grid above is showing its own empty / loading state.
 */

import { usePokemonGathererStore } from '../../stores/pokemonGathererStore';

export function LabPaginationFooter() {
  const {
    currentSet,
    cards,
    cardsTotal,
    cardsLoading,
    cardsHasMore,
    loadMoreCards,
  } = usePokemonGathererStore();

  if (!currentSet || cards.length === 0) return null;

  return (
    <div
      style={{
        marginTop: 20,
        paddingTop: 14,
        borderTop: '1px solid var(--rule-2)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        flexWrap: 'wrap',
        gap: 12,
      }}
      data-testid="pokemon-gatherer-pagination"
    >
      <span
        style={{
          fontFamily: 'var(--font-mono)',
          fontSize: 11,
          letterSpacing: '.06em',
          color: 'var(--ink-3)',
          fontVariantNumeric: 'tabular-nums',
        }}
      >
        Showing {cards.length} of {cardsTotal}
      </span>
      {cardsLoading && (
        <span
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 11,
            letterSpacing: '.14em',
            textTransform: 'uppercase',
            color: 'var(--sodium)',
            display: 'inline-flex',
            alignItems: 'center',
            gap: 8,
          }}
        >
          <span
            style={{
              width: 8,
              height: 8,
              borderRadius: '50%',
              background: 'var(--sodium)',
              animation: 'pulse 1.6s ease-in-out infinite',
            }}
          />
          Loading…
        </span>
      )}
      {!cardsLoading && cardsHasMore && (
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
            background: 'var(--ink)',
            color: 'var(--paper)',
            border: 'none',
            cursor: 'pointer',
          }}
        >
          Load more →
        </button>
      )}
      {!cardsLoading && !cardsHasMore && (
        <span
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 11,
            letterSpacing: '.14em',
            textTransform: 'uppercase',
            color: 'var(--ink-3)',
          }}
        >
          End of set
        </span>
      )}
    </div>
  );
}
