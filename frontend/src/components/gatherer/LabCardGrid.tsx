/**
 * LabCardGrid — Gatherer card-grid plate (Phase C / follow-up 11a).
 *
 * The right-pane grid plate that wraps the SketchCard cells. Lab chrome
 * lives in the outer paper-2 plate, hairline header strip (current set
 * name + match count), and the empty / loading / "no matches" placeholders.
 * The per-card identity stays *inside* each `<SketchCard>` — that's the
 * seam where lab chrome ends and the parchment card face begins.
 *
 * The load-more sentinel + pagination eyebrow live in
 * `<LabPaginationFooter>` which is composed inside the grid body so the
 * IntersectionObserver root sits next to the cards it's measuring.
 */

import { useGathererStore } from '../../stores/gathererStore';
import { SketchCard } from './SketchCard';
import { Eyebrow } from './_labChrome';
import { LabPaginationFooter } from './LabPaginationFooter';

export function LabCardGrid() {
  const {
    currentSet,
    cards,
    cardsTotal,
    cardsLoading,
    filter,
    selectCard,
  } = useGathererStore();

  const hasActiveFilters =
    (filter.types && filter.types.length > 0) ||
    (filter.colors && filter.colors.length > 0) ||
    Boolean(filter.rarity) ||
    Boolean(filter.textSearch) ||
    filter.cmcMin !== undefined ||
    filter.cmcMax !== undefined;

  return (
    <div
      data-testid="gatherer-card-grid"
      style={{
        border: '1px solid var(--rule)',
        background: 'var(--paper-2)',
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      {/* Grid header strip */}
      <div
        style={{
          display: 'flex',
          alignItems: 'baseline',
          justifyContent: 'space-between',
          padding: '12px 16px',
          borderBottom: '1px solid var(--rule)',
          flexWrap: 'wrap',
          gap: 8,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 12 }}>
          <Eyebrow>Set</Eyebrow>
          <span
            style={{
              fontFamily: 'var(--font-serif)',
              fontSize: 22,
              lineHeight: 1,
              color: 'var(--ink)',
              letterSpacing: '-.01em',
            }}
          >
            {currentSet?.name ?? 'No set selected'}
          </span>
          {currentSet?.code && (
            <span
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: 11,
                letterSpacing: '.1em',
                textTransform: 'uppercase',
                color: 'var(--ink-3)',
              }}
            >
              {currentSet.code}
            </span>
          )}
        </div>
        <span
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 11,
            letterSpacing: '.06em',
            color: 'var(--ink-3)',
            fontVariantNumeric: 'tabular-nums',
          }}
        >
          {currentSet
            ? `${cardsTotal} card${cardsTotal !== 1 ? 's' : ''} matching filters`
            : 'pick a set →'}
        </span>
      </div>

      {/* Grid body */}
      <div style={{ padding: 16, minHeight: 360 }}>
        {!currentSet && (
          <EmptyState
            headline="Pick a set."
            detail="Choose one from the rack on the left to start browsing."
          />
        )}

        {currentSet && cards.length === 0 && cardsLoading && <LoadingState />}

        {currentSet && cards.length === 0 && !cardsLoading && (
          <EmptyState
            headline="No cards match."
            detail={
              hasActiveFilters
                ? 'Try widening your filters or clearing them.'
                : 'This set appears to be empty.'
            }
          />
        )}

        {cards.length > 0 && (
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))',
              gap: 16,
            }}
          >
            {cards.map((card) => (
              <SketchCard
                key={card.name}
                card={card}
                setCode={currentSet?.code}
                onClick={() => selectCard(card)}
              />
            ))}
          </div>
        )}

        <LabPaginationFooter />
      </div>
    </div>
  );
}

// === Placeholder states ==================================================

function EmptyState({ headline, detail }: { headline: string; detail: string }) {
  return (
    <div
      style={{
        padding: '40px 28px',
        border: '1px dashed var(--rule)',
        background: 'var(--paper)',
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
        {headline}
      </span>
      <p
        style={{
          margin: '12px auto 0',
          fontFamily: 'var(--font-serif)',
          fontStyle: 'italic',
          fontSize: 18,
          lineHeight: 1.5,
          color: 'var(--ink-2)',
          maxWidth: '52ch',
        }}
      >
        {detail}
      </p>
    </div>
  );
}

function LoadingState() {
  return (
    <div
      style={{
        padding: '24px 18px',
        display: 'flex',
        alignItems: 'center',
        gap: 10,
        fontFamily: 'var(--font-mono)',
        fontSize: 11,
        letterSpacing: '.14em',
        textTransform: 'uppercase',
        color: 'var(--ink-3)',
        border: '1px solid var(--rule)',
        background: 'var(--paper)',
      }}
    >
      <span
        style={{
          width: 10,
          height: 10,
          borderRadius: '50%',
          background: 'var(--sodium)',
          animation: 'gatherer-pulse 1.6s ease-in-out infinite',
        }}
      />
      Loading cards…
    </div>
  );
}
