/**
 * LabCardGrid — the boxed card grid container.
 *
 * Renders the data-testid `pokemon-gatherer-grid` plate (the test relies on
 * this for the lab-chrome assertion), and resolves one of three states:
 *
 *   - No set selected → empty-state prompt to pick from the rack.
 *   - Set selected, loading initial cards → loading row.
 *   - Set selected, no matches → empty-state (with filter / empty-set copy).
 *   - Set selected, cards present → the auto-fill grid of `<PokemonCardCell>`s
 *     plus an optional pagination `footer` slot (see `LabPaginationFooter`).
 *
 * The card cells themselves keep their per-card identity (real Pokemon art);
 * this component owns only the lab chrome around them — the seam per
 * docs/design/brand.md.
 *
 * Accepting a `footer` render-prop (rather than rendering pagination directly)
 * keeps the panel's hairline border intact across grid + pagination while
 * letting the page wire its own pagination slot — mirrors the Deckbuilder
 * pattern where the composer page owns composition of sub-blocks.
 */

import { usePokemonGathererStore } from '../../stores/pokemonGathererStore';
import { hasActivePokemonFilters } from '../../types/pokemonGatherer';
import { PokemonCardCell } from './PokemonCardCell';

export interface LabCardGridProps {
  /** Optional pagination footer slot — rendered inside the panel so the
   *  hairline border wraps both the grid and the load-more row. */
  footer?: React.ReactNode;
}

export function LabCardGrid({ footer }: LabCardGridProps = {}) {
  const {
    currentSet,
    cards,
    cardsLoading,
    filter,
    selectCard,
  } = usePokemonGathererStore();

  const hasActiveFilters = hasActivePokemonFilters(filter);

  return (
    <div
      data-testid="pokemon-gatherer-grid"
      style={{
        marginTop: 16,
        border: '1px solid var(--rule)',
        background: 'var(--paper-2)',
        padding: 20,
        minHeight: 320,
      }}
    >
      {!currentSet && (
        <EmptyState
          eyebrow="Set required"
          title="Pick a Pokémon set from the rack"
          body="The left rail lists the SV starter pack plus the Beyond crossover sets. Pick one to load its cards."
        />
      )}

      {currentSet && cards.length === 0 && cardsLoading && (
        <LoadingRow label="Loading cards…" big />
      )}

      {currentSet && cards.length === 0 && !cardsLoading && (
        <EmptyState
          eyebrow={hasActiveFilters ? 'No matches' : 'Empty set'}
          title={
            hasActiveFilters
              ? 'No cards match these filters'
              : 'No cards in this set'
          }
          body={
            hasActiveFilters
              ? 'Loosen a constraint or clear the filters and try again.'
              : 'This set is empty. Pick another from the rack.'
          }
        />
      )}

      {currentSet && cards.length > 0 && (
        <>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))',
              gap: 14,
            }}
          >
            {cards.map((card) => (
              <PokemonCardCell
                key={`${card.name}-${card.supertype}`}
                card={card}
                onClick={() => selectCard(card)}
              />
            ))}
          </div>
          {footer}
        </>
      )}
    </div>
  );
}

// === Local helpers ======================================================

function EmptyState({
  eyebrow,
  title,
  body,
}: {
  eyebrow: string;
  title: string;
  body: string;
}) {
  return (
    <div
      style={{
        padding: '40px 28px',
        textAlign: 'center',
      }}
    >
      <span
        style={{
          fontFamily: 'var(--font-mono)',
          fontSize: 10.5,
          fontWeight: 500,
          letterSpacing: '.14em',
          textTransform: 'uppercase',
          color: 'var(--sodium)',
        }}
      >
        {eyebrow}
      </span>
      <h3
        style={{
          margin: '12px auto 6px',
          fontFamily: 'var(--font-serif)',
          fontSize: 24,
          fontWeight: 400,
          letterSpacing: '-.015em',
          color: 'var(--ink)',
        }}
      >
        {title}
      </h3>
      <p
        style={{
          margin: '0 auto',
          fontFamily: 'var(--font-serif)',
          fontStyle: 'italic',
          fontSize: 16,
          lineHeight: 1.5,
          color: 'var(--ink-2)',
          maxWidth: '50ch',
        }}
      >
        {body}
      </p>
    </div>
  );
}

function LoadingRow({ label, big = false }: { label: string; big?: boolean }) {
  return (
    <div
      style={{
        padding: big ? '40px 18px' : '16px 18px',
        fontFamily: 'var(--font-mono)',
        fontSize: 11,
        letterSpacing: '.14em',
        textTransform: 'uppercase',
        color: 'var(--ink-3)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: big ? 'center' : 'flex-start',
        gap: 10,
      }}
    >
      <span
        style={{
          width: 10,
          height: 10,
          borderRadius: '50%',
          background: 'var(--sodium)',
          animation: 'pulse 1.6s ease-in-out infinite',
        }}
      />
      {label}
    </div>
  );
}
