/**
 * Cats — game board + deckbuilder module.
 *
 * Two exports live in this file:
 *   1. `CatsGame` (default) — the in-game React board used by a future
 *      CatsGameView page. Reads from useCatsGame; the hook returns mock
 *      data until the server route is wired.
 *   2. `cats` (named) — the deckbuilder GameModule registered in
 *      registry.ts so the cats card pool plays nicely with the existing
 *      filter/stats panel.
 *
 * Visual direction: warm, cozy, charmingly irreverent. We deliberately
 * step away from the dark "card-game UI" palette other engines use here.
 * Cream, butterscotch, dusty rose, soft sage; rounded serif card names;
 * SVG paw prints and yarn balls; piles render as actual pile-of-cards
 * with rotation + offset, not stacks of squares.
 */

import { useState } from 'react';
import type { CSSProperties } from 'react';
import type { GameModule } from './types';
import type { DeckStats } from '../types/deckbuilder';
import { defaultFormatType } from './types';
import {
  useCatsGame,
  type CatsCard,
  type CatsState,
  type CatsPhase,
  type CatsPileName,
  type CatsCategory,
  type PlayerState,
  type CatsTrick,
  type CatsAction,
} from '../hooks/useCatsGame';

// ---------------------------------------------------------------------------
// Visual palette — kept on a single object so the cozy/cream identity is
// easy to tweak without hunting through className strings.
// ---------------------------------------------------------------------------

const COZY = {
  cream: '#fdf6e3',
  butterscotch: '#e7b35a',
  dustyRose: '#d39a9a',
  softSage: '#a7b89a',
  warmTan: '#d9b896',
  inkBrown: '#3e2c1c',
  parchment: '#f4e6c8',
  cardBg: '#fff8e7',
} as const;

const CATEGORY_TINT: Record<CatsCategory, string> = {
  Sleek: '#bda378',
  Fluffy: '#e3c9b8',
  Scrappy: '#c46a4f',
  Sneaky: '#7d5b89',
};

const PILE_META: Record<
  CatsPileName,
  { label: string; helper: string; icon: JSX.Element; tint: string; cap?: number }
> = {
  territory: {
    label: 'Territory',
    helper: '1 pt / card · +2 per Trinket · +5 if 6+',
    icon: <PawIcon />,
    tint: COZY.butterscotch,
    cap: 8,
  },
  nap: {
    label: 'Nap',
    helper: '2 pt / card · capped at 12',
    icon: <SunbeamIcon />,
    tint: '#f0c97a',
    cap: 6,
  },
  snack: {
    label: 'Snack',
    helper: '3 pt under 5 cards · 1 pt over (greed)',
    icon: <FishBoneIcon />,
    tint: COZY.dustyRose,
    cap: 5,
  },
  attention: {
    label: 'Attention',
    helper: 'Tiebreaker only · unlimited',
    icon: <YarnBallIcon />,
    tint: COZY.softSage,
  },
};

const PHASE_ORDER: { key: CatsPhase; short: string; flavor: string }[] = [
  { key: 'stretch', short: 'Stretch', flavor: 'Round opens. Stretch out. Triggers fire.' },
  { key: 'pounce', short: 'Pounce', flavor: 'Follower plays first. Commit before you know.' },
  { key: 'counter_pounce', short: 'Counter-pounce', flavor: 'Lead reacts. Reframe the round.' },
  { key: 'resolve', short: 'Resolve', flavor: 'Compare values under the installed rule.' },
  { key: 'claim', short: 'Claim', flavor: 'Winner picks a pile. Choose carefully.' },
  { key: 'curl_up', short: 'Curl up', flavor: 'Round ends. Pile caps re-check.' },
];

// ---------------------------------------------------------------------------
// Top-level board
// ---------------------------------------------------------------------------

export default function CatsGame() {
  const { state, sendAction, isLoading, error } = useCatsGame();

  if (isLoading) {
    return (
      <div
        className="flex min-h-screen items-center justify-center"
        style={{ background: COZY.cream }}
      >
        <div
          className="text-lg"
          style={{ color: COZY.inkBrown, fontFamily: 'Georgia, serif' }}
        >
          Stretching…
        </div>
      </div>
    );
  }
  if (!state) {
    return (
      <div
        className="flex min-h-screen items-center justify-center"
        style={{ background: COZY.cream }}
      >
        <div
          className="rounded-lg border px-6 py-4 text-center"
          style={{
            borderColor: COZY.warmTan,
            background: COZY.parchment,
            color: COZY.inkBrown,
            fontFamily: 'Georgia, serif',
          }}
        >
          <div className="text-base font-semibold">No game in session.</div>
          <div className="mt-1 text-sm opacity-70">
            The cats have not yet convened.
          </div>
          {error && (
            <div className="mt-3 text-xs text-red-700">{error}</div>
          )}
        </div>
      </div>
    );
  }

  return <CatsBoard state={state} onAction={sendAction} />;
}

interface BoardProps {
  state: CatsState;
  onAction: (action: CatsAction) => void;
}

function CatsBoard({ state, onAction }: BoardProps) {
  return (
    <div
      className="relative min-h-screen w-full overflow-x-hidden"
      style={{
        background: `radial-gradient(circle at 50% 12%, ${COZY.parchment} 0%, ${COZY.cream} 55%, #f0e3c4 100%)`,
        fontFamily: 'Georgia, "Iowan Old Style", serif',
        color: COZY.inkBrown,
      }}
    >
      <RoundHeader state={state} />
      <PhaseIndicator phase={state.phase} round={state.round_number} />

      <div className="mx-auto flex max-w-7xl flex-col gap-4 px-6 pb-10 pt-2">
        <OpponentArea state={state.opponent} />
        <TrickZone trick={state.current_trick} lead={state.lead_player} phase={state.phase} />
        <MyArea state={state.player} onAction={onAction} phase={state.phase} />
      </div>

      {state.game_over && state.final_scores && (
        <EndOfDayOverlay scores={state.final_scores} />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Header / phase indicator
// ---------------------------------------------------------------------------

function RoundHeader({ state }: { state: CatsState }) {
  return (
    <header
      className="flex w-full items-center justify-between border-b px-6 py-3"
      style={{ borderColor: COZY.warmTan, background: 'rgba(255, 248, 231, 0.85)' }}
    >
      <div className="flex items-center gap-3">
        <PawIcon size={28} color={COZY.butterscotch} />
        <div>
          <div className="text-xs uppercase tracking-[0.22em] opacity-60">
            A day in the life of a cat
          </div>
          <div className="text-lg font-semibold" style={{ letterSpacing: '0.04em' }}>
            Round {state.round_number} of 9
          </div>
        </div>
      </div>
      <div className="flex items-center gap-3 text-sm">
        <span className="opacity-70">Leading this round:</span>
        <span
          className="rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-wider"
          style={{
            background: state.lead_player === 'me' ? COZY.butterscotch : COZY.dustyRose,
            color: '#fff',
          }}
        >
          {state.lead_player === 'me' ? 'you' : 'opponent'}
        </span>
      </div>
    </header>
  );
}

function PhaseIndicator({
  phase,
  round,
}: {
  phase: CatsPhase;
  round: number;
}) {
  const activeIdx = PHASE_ORDER.findIndex((p) => p.key === phase);
  return (
    <nav
      className="mx-auto mt-3 flex max-w-7xl items-center gap-1.5 px-6 text-[11px]"
      aria-label={`Round ${round} phase: ${phase}`}
    >
      {PHASE_ORDER.map((p, i) => {
        const isActive = i === activeIdx;
        const isPast = i < activeIdx;
        return (
          <div
            key={p.key}
            className="flex flex-1 flex-col items-center gap-1"
            title={p.flavor}
          >
            <div
              className="h-1.5 w-full rounded-full transition-all"
              style={{
                background: isActive
                  ? COZY.butterscotch
                  : isPast
                    ? COZY.warmTan
                    : '#e8dab9',
                boxShadow: isActive
                  ? `0 0 0 2px ${COZY.parchment}, 0 0 8px ${COZY.butterscotch}`
                  : 'none',
              }}
            />
            <div
              className="select-none font-semibold tracking-wider"
              style={{
                color: isActive ? COZY.inkBrown : '#8a7a5d',
                fontVariant: 'small-caps',
              }}
            >
              {p.short}
            </div>
          </div>
        );
      })}
    </nav>
  );
}

// ---------------------------------------------------------------------------
// Opponent / my areas
// ---------------------------------------------------------------------------

function OpponentArea({ state }: { state: PlayerState }) {
  return (
    <section
      className="rounded-xl border px-4 pb-4 pt-3"
      style={{
        background: 'rgba(231, 179, 90, 0.07)',
        borderColor: COZY.warmTan,
      }}
      aria-label="Opponent area"
    >
      <div className="mb-2 flex items-center justify-between text-xs uppercase tracking-[0.18em] opacity-70">
        <span>Opponent</span>
        <span>{state.hand.length} cards in paw</span>
      </div>
      <div className="grid grid-cols-12 gap-3">
        <div className="col-span-3 flex items-center justify-center">
          <CommanderCard card={state.commander} owner="opponent" />
        </div>
        <div className="col-span-9 flex flex-col gap-3">
          <OpponentHand count={state.hand.length} />
          <PileRow piles={state.piles} owner="opponent" />
        </div>
      </div>
    </section>
  );
}

function MyArea({
  state,
  onAction,
  phase,
}: {
  state: PlayerState;
  onAction: (action: CatsAction) => void;
  phase: CatsPhase;
}) {
  const canPlay = phase === 'pounce' || phase === 'counter_pounce';
  const canClaim = phase === 'claim';

  return (
    <section
      className="rounded-xl border px-4 pb-4 pt-3"
      style={{
        background: 'rgba(167, 184, 154, 0.08)',
        borderColor: COZY.softSage,
      }}
      aria-label="Your area"
    >
      <div className="mb-2 flex items-center justify-between text-xs uppercase tracking-[0.18em] opacity-70">
        <span>You</span>
        <span>{state.hand.length} cards in paw</span>
      </div>
      <div className="grid grid-cols-12 gap-3">
        <div className="col-span-9 flex flex-col gap-3">
          <PileRow
            piles={state.piles}
            owner="me"
            onClaim={
              canClaim
                ? (pile) => {
                    if (pile === 'attention') return; // attention only via forced overflow
                    onAction({ type: 'CATS_CLAIM_PILE', pile });
                  }
                : undefined
            }
          />
          <MyHand
            cards={state.hand}
            playable={canPlay}
            onPlay={(cardId) => onAction({ type: 'CATS_PLAY_CARD', cardId })}
          />
        </div>
        <div className="col-span-3 flex items-center justify-center">
          <CommanderCard card={state.commander} owner="me" />
        </div>
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Trick zone — the dramatic center stage
// ---------------------------------------------------------------------------

function TrickZone({
  trick,
  lead,
  phase,
}: {
  trick: CatsTrick;
  lead: 'me' | 'opponent';
  phase: CatsPhase;
}) {
  const ruleLabel = trick.installed_rule ?? 'Default · highest Value wins';
  const ruleColor = trick.installed_rule ? CATEGORY_TINT[trick.installed_rule] : COZY.inkBrown;

  // Visualize the squaring-off: pounce card slides in from the lead's side,
  // counter card from the opposite. Order on screen mirrors lead direction.
  const pounceFrom = lead === 'me' ? 'left' : 'right';
  const counterFrom = lead === 'me' ? 'right' : 'left';

  return (
    <section
      className="relative flex items-center justify-center rounded-xl border px-6 py-6"
      style={{
        background:
          'radial-gradient(ellipse at center, rgba(255,248,231,0.95) 0%, rgba(244,230,200,0.6) 100%)',
        borderColor: COZY.warmTan,
        minHeight: 180,
      }}
      aria-label="Trick zone"
    >
      <div className="absolute left-4 top-3 text-[10px] uppercase tracking-[0.2em] opacity-60">
        Trick rule
      </div>
      <div
        className="absolute right-4 top-3 rounded-full px-3 py-0.5 text-[10px] font-semibold uppercase tracking-wider"
        style={{ background: ruleColor, color: '#fff' }}
      >
        {ruleLabel}
      </div>

      <div className="flex w-full items-center justify-center gap-10">
        <TrickSlot
          card={pounceFrom === 'left' ? trick.pounce_card : trick.counter_card}
          label={pounceFrom === 'left' ? 'Pounce' : 'Counter'}
          side="left"
          isWinner={
            trick.winner != null &&
            ((pounceFrom === 'left' && trick.winner === lead) ||
              (pounceFrom === 'right' && trick.winner !== lead))
          }
        />
        <div
          className="flex flex-col items-center gap-1 text-xs uppercase tracking-[0.2em]"
          style={{ color: COZY.inkBrown }}
        >
          <WhiskerIcon />
          <span className="opacity-70">vs</span>
        </div>
        <TrickSlot
          card={counterFrom === 'right' ? trick.counter_card : trick.pounce_card}
          label={counterFrom === 'right' ? 'Counter' : 'Pounce'}
          side="right"
          isWinner={
            trick.winner != null &&
            ((counterFrom === 'right' && trick.winner === lead) ||
              (counterFrom === 'left' && trick.winner !== lead))
          }
        />
      </div>

      {phase === 'resolve' && trick.winner && (
        <div
          className="absolute bottom-3 left-1/2 -translate-x-1/2 rounded-full px-4 py-1 text-xs font-semibold uppercase tracking-wider"
          style={{ background: COZY.softSage, color: '#fff' }}
        >
          {trick.winner === 'me' ? 'You won the trick' : 'Opponent took the trick'}
        </div>
      )}
    </section>
  );
}

function TrickSlot({
  card,
  label,
  side,
  isWinner,
}: {
  card: CatsCard | null;
  label: string;
  side: 'left' | 'right';
  isWinner: boolean;
}) {
  return (
    <div className="flex flex-col items-center gap-2">
      <div className="text-[10px] uppercase tracking-[0.22em] opacity-60">{label}</div>
      <div
        className="transition-transform"
        style={{
          transform: card
            ? `rotate(${side === 'left' ? -4 : 4}deg) scale(${isWinner ? 1.05 : 1})`
            : 'rotate(0deg)',
          filter: isWinner ? `drop-shadow(0 0 16px ${COZY.butterscotch})` : 'none',
        }}
      >
        {card ? (
          <CatCard card={card} variant="trick" />
        ) : (
          <EmptyCardSlot label="awaiting paw" />
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Hand views
// ---------------------------------------------------------------------------

function MyHand({
  cards,
  playable,
  onPlay,
}: {
  cards: CatsCard[];
  playable: boolean;
  onPlay: (cardId: string) => void;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <div className="text-[10px] uppercase tracking-[0.22em] opacity-60">
        Your paw {playable ? '· tap a card to play' : ''}
      </div>
      <div className="flex flex-wrap gap-3">
        {cards.map((card) => (
          <button
            key={card.id}
            type="button"
            disabled={!playable}
            onClick={() => onPlay(card.id)}
            className="group transition-transform"
            style={{
              transform: playable ? 'translateY(0)' : 'translateY(0)',
              cursor: playable ? 'pointer' : 'not-allowed',
              opacity: playable ? 1 : 0.78,
            }}
          >
            <span
              className="block group-hover:-translate-y-2 group-focus:-translate-y-2 transition-transform"
              style={{ display: 'inline-block' }}
            >
              <CatCard card={card} variant="hand" />
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}

function OpponentHand({ count }: { count: number }) {
  return (
    <div className="flex flex-col gap-1.5">
      <div className="text-[10px] uppercase tracking-[0.22em] opacity-60">
        Opponent paw
      </div>
      <div className="flex gap-1.5">
        {Array.from({ length: count }).map((_, i) => (
          <CardBack key={i} index={i} />
        ))}
      </div>
    </div>
  );
}

function CardBack({ index }: { index: number }) {
  // Slight fan: rotate around the deck mid-point.
  const rot = (index - 2) * 3;
  return (
    <div
      className="rounded-md border"
      style={{
        width: 38,
        height: 56,
        background: `repeating-linear-gradient(45deg, ${COZY.dustyRose} 0 6px, #b67c7c 6px 12px)`,
        borderColor: COZY.inkBrown,
        transform: `rotate(${rot}deg)`,
        boxShadow: '0 2px 4px rgba(62,44,28,0.18)',
      }}
      aria-hidden="true"
    />
  );
}

// ---------------------------------------------------------------------------
// Pile row + PileStack
// ---------------------------------------------------------------------------

function PileRow({
  piles,
  owner,
  onClaim,
}: {
  piles: PlayerState['piles'];
  owner: 'me' | 'opponent';
  onClaim?: (pile: CatsPileName) => void;
}) {
  const order: CatsPileName[] = ['territory', 'nap', 'snack', 'attention'];
  return (
    <div className="grid grid-cols-4 gap-3">
      {order.map((p) => (
        <PileStack
          key={p}
          pile={p}
          cards={piles[p]}
          owner={owner}
          onClaim={onClaim ? () => onClaim(p) : undefined}
        />
      ))}
    </div>
  );
}

function PileStack({
  pile,
  cards,
  owner,
  onClaim,
}: {
  pile: CatsPileName;
  cards: CatsCard[];
  owner: 'me' | 'opponent';
  onClaim?: () => void;
}) {
  const meta = PILE_META[pile];
  const [hovered, setHovered] = useState(false);
  const claimable = !!onClaim && pile !== 'attention';
  const atCap = meta.cap != null && cards.length >= meta.cap;

  return (
    <div
      className="relative rounded-lg border px-2 pb-3 pt-2 transition-colors"
      style={{
        borderColor: claimable && hovered ? meta.tint : COZY.warmTan,
        background: 'rgba(255, 248, 231, 0.55)',
        cursor: claimable ? 'pointer' : 'default',
      }}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      onClick={onClaim}
      role={claimable ? 'button' : undefined}
      aria-label={`${owner === 'me' ? 'Your' : 'Opponent'} ${meta.label} pile · ${cards.length} cards`}
    >
      <div className="flex items-center justify-between text-[11px] font-semibold uppercase tracking-wider">
        <span className="flex items-center gap-1" style={{ color: meta.tint }}>
          {meta.icon}
          {meta.label}
        </span>
        <span
          className="rounded-full px-1.5 py-0.5 text-[10px]"
          style={{
            background: atCap ? COZY.dustyRose : meta.tint,
            color: '#fff',
          }}
          title={meta.cap ? `cap ${meta.cap}` : 'no cap'}
        >
          {cards.length}
          {meta.cap ? ` / ${meta.cap}` : ''}
        </span>
      </div>
      <div className="mt-1 line-clamp-2 text-[10px] italic opacity-60">{meta.helper}</div>

      {/* The pile itself — actual rotated/offset stack */}
      <div
        className="relative mt-2"
        style={{ height: cards.length > 0 ? 110 : 80 }}
      >
        {cards.length === 0 ? (
          <div
            className="flex h-full items-center justify-center rounded-md border border-dashed text-[10px] italic opacity-40"
            style={{ borderColor: COZY.warmTan }}
          >
            empty
          </div>
        ) : (
          cards.map((card, i) => {
            const fanAngle = hovered ? (i - (cards.length - 1) / 2) * 18 : (i - cards.length / 2) * 3;
            const fanX = hovered ? (i - (cards.length - 1) / 2) * 28 : (i - cards.length / 2) * 4;
            const fanY = hovered ? -i * 2 : i * 3;
            const style: CSSProperties = {
              position: 'absolute',
              left: '50%',
              top: 0,
              transform: `translateX(calc(-50% + ${fanX}px)) translateY(${fanY}px) rotate(${fanAngle}deg)`,
              transition: 'transform 220ms ease',
              zIndex: i,
            };
            return (
              <div key={card.id} style={style}>
                <CatCard card={card} variant="pile" />
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// CatCard — the card itself
// ---------------------------------------------------------------------------

function CatCard({
  card,
  variant,
}: {
  card: CatsCard;
  variant: 'hand' | 'trick' | 'pile';
}) {
  const sizes: Record<
    typeof variant,
    { w: number; h: number; nameSize: number; valueSize: number; textSize: number }
  > = {
    hand: { w: 130, h: 184, nameSize: 13, valueSize: 28, textSize: 10 },
    trick: { w: 150, h: 212, nameSize: 15, valueSize: 36, textSize: 11 },
    pile: { w: 96, h: 140, nameSize: 11, valueSize: 22, textSize: 9 },
  };
  const s = sizes[variant];
  const tint = card.category ? CATEGORY_TINT[card.category] : COZY.inkBrown;

  const cardStyle: CSSProperties = {
    width: s.w,
    height: s.h,
    background: card.tapped
      ? `linear-gradient(140deg, ${COZY.cardBg} 0%, #e8d8b3 100%)`
      : COZY.cardBg,
    border: `1.5px solid ${tint}`,
    borderRadius: 10,
    boxShadow: card.tapped
      ? 'inset 0 0 18px rgba(62,44,28,0.18), 0 1px 2px rgba(62,44,28,0.08)'
      : '0 2px 6px rgba(62,44,28,0.18)',
    fontFamily: 'Georgia, "Iowan Old Style", serif',
    color: COZY.inkBrown,
    display: 'flex',
    flexDirection: 'column',
    padding: 8,
    position: 'relative',
    overflow: 'hidden',
    opacity: card.tapped ? 0.82 : 1,
    transform: card.tapped ? 'rotate(-2deg)' : 'rotate(0deg)',
  };

  return (
    <div style={cardStyle} title={card.text}>
      {/* Top row: name + value */}
      <div className="flex items-start justify-between gap-2">
        <div
          style={{
            fontSize: s.nameSize,
            lineHeight: 1.1,
            fontWeight: 600,
            letterSpacing: '0.005em',
          }}
        >
          {card.name}
        </div>
        {card.card_type !== 'Mood' && card.card_type !== 'Trinket' && (
          <div
            style={{
              fontSize: s.valueSize,
              lineHeight: 1,
              fontWeight: 700,
              color: tint,
              fontFamily: '"Iowan Old Style", Georgia, serif',
            }}
          >
            {card.value}
          </div>
        )}
      </div>

      {/* Category + type chip */}
      <div className="mt-1 flex items-center gap-1">
        {card.category && (
          <span
            style={{
              fontSize: 9,
              padding: '1px 6px',
              borderRadius: 999,
              background: tint,
              color: '#fff',
              textTransform: 'uppercase',
              letterSpacing: '0.08em',
              fontWeight: 600,
            }}
          >
            {card.category}
          </span>
        )}
        <span
          style={{
            fontSize: 9,
            padding: '1px 6px',
            borderRadius: 999,
            background: '#e8dab9',
            color: COZY.inkBrown,
            textTransform: 'uppercase',
            letterSpacing: '0.08em',
            fontWeight: 600,
          }}
        >
          {card.card_type}
        </span>
      </div>

      {/* Art slot — single-glyph reflection of the type */}
      <div
        className="my-1 flex flex-1 items-center justify-center"
        style={{
          background: `radial-gradient(circle at 50% 40%, ${tint}26 0%, transparent 70%)`,
          borderRadius: 6,
        }}
      >
        <TypeGlyph type={card.card_type} category={card.category} />
      </div>

      {/* Flavor / rules text */}
      {card.text && variant !== 'pile' && (
        <div
          style={{
            fontSize: s.textSize,
            fontStyle: 'italic',
            lineHeight: 1.25,
            color: '#5a4528',
            maxHeight: variant === 'hand' ? 44 : 60,
            overflow: 'hidden',
          }}
        >
          {card.text}
        </div>
      )}

      {/* Knocked-over indicator */}
      {card.tapped && (
        <div
          style={{
            position: 'absolute',
            bottom: 6,
            right: 6,
            fontSize: 9,
            background: COZY.inkBrown,
            color: COZY.parchment,
            padding: '1px 6px',
            borderRadius: 999,
            fontVariant: 'small-caps',
            letterSpacing: '0.06em',
          }}
        >
          knocked over
        </div>
      )}
    </div>
  );
}

function CommanderCard({
  card,
  owner,
}: {
  card: CatsCard | null;
  owner: 'me' | 'opponent';
}) {
  if (!card) {
    return (
      <div
        className="flex h-32 w-28 items-center justify-center rounded-lg border border-dashed text-[10px] italic opacity-50"
        style={{ borderColor: COZY.warmTan }}
      >
        no commander
      </div>
    );
  }
  return (
    <div
      className="relative rounded-lg border-2 px-2 pb-2 pt-2"
      style={{
        width: 132,
        background: 'linear-gradient(160deg, #fff8e7 0%, #f0d8a0 100%)',
        borderColor: COZY.butterscotch,
        boxShadow: `0 0 0 3px ${COZY.parchment}, 0 6px 14px rgba(62,44,28,0.18)`,
      }}
      title={card.text}
    >
      <div
        className="absolute -top-2 left-1/2 -translate-x-1/2 rounded-full px-2 py-0.5 text-[9px] font-semibold uppercase tracking-wider"
        style={{ background: COZY.butterscotch, color: '#fff' }}
      >
        Commander · {owner === 'me' ? 'yours' : 'theirs'}
      </div>
      <div
        className="mt-2 flex items-center justify-center"
        style={{ height: 56 }}
      >
        <CrownPawIcon />
      </div>
      <div
        className="text-center font-semibold"
        style={{ fontSize: 12, lineHeight: 1.1, color: COZY.inkBrown }}
      >
        {card.name}
      </div>
      {card.text && (
        <div
          className="mt-1 text-center italic"
          style={{ fontSize: 9, lineHeight: 1.25, color: '#5a4528' }}
        >
          {card.text}
        </div>
      )}
    </div>
  );
}

function EmptyCardSlot({ label }: { label: string }) {
  return (
    <div
      className="flex items-center justify-center rounded-md border border-dashed"
      style={{
        width: 150,
        height: 212,
        borderColor: COZY.warmTan,
        color: COZY.warmTan,
        fontSize: 10,
        fontStyle: 'italic',
        letterSpacing: '0.08em',
        textTransform: 'uppercase',
      }}
    >
      {label}
    </div>
  );
}

// ---------------------------------------------------------------------------
// End-of-day overlay
// ---------------------------------------------------------------------------

function EndOfDayOverlay({
  scores,
}: {
  scores: NonNullable<CatsState['final_scores']>;
}) {
  return (
    <div
      className="fixed inset-0 flex items-center justify-center"
      style={{ background: 'rgba(62,44,28,0.55)' }}
    >
      <div
        className="rounded-2xl border-2 px-8 py-6 text-center"
        style={{
          background: COZY.cream,
          borderColor: COZY.butterscotch,
          color: COZY.inkBrown,
          fontFamily: 'Georgia, serif',
          maxWidth: 520,
        }}
      >
        <div className="text-xs uppercase tracking-[0.22em] opacity-60">
          The day curls up.
        </div>
        <div className="mt-1 text-2xl font-semibold">Final scores</div>
        <div className="mt-4 grid grid-cols-2 gap-4 text-sm">
          <ScoreColumn label="You" breakdown={scores.me} />
          <ScoreColumn label="Opponent" breakdown={scores.opponent} />
        </div>
      </div>
    </div>
  );
}

function ScoreColumn({
  label,
  breakdown,
}: {
  label: string;
  breakdown: {
    territory: number;
    nap: number;
    snack: number;
    attention: number;
    total: number;
  };
}) {
  return (
    <div
      className="rounded-lg border px-4 py-3 text-left"
      style={{ borderColor: COZY.warmTan, background: COZY.parchment }}
    >
      <div className="text-xs uppercase tracking-wider opacity-70">{label}</div>
      <div className="mt-1 grid grid-cols-2 gap-x-3 gap-y-0.5 text-[12px]">
        <span className="opacity-70">Territory</span>
        <span className="text-right">{breakdown.territory}</span>
        <span className="opacity-70">Nap</span>
        <span className="text-right">{breakdown.nap}</span>
        <span className="opacity-70">Snack</span>
        <span className="text-right">{breakdown.snack}</span>
        <span className="opacity-70">Attention</span>
        <span className="text-right">{breakdown.attention}</span>
      </div>
      <div className="mt-2 border-t pt-1 text-sm font-semibold" style={{ borderColor: COZY.warmTan }}>
        Total <span className="float-right">{breakdown.total}</span>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Inline SVG icons — paw, sunbeam, fish-bone, yarn ball, whiskers, crown-paw
// ---------------------------------------------------------------------------

function PawIcon({ size = 14, color = 'currentColor' }: { size?: number; color?: string } = {}) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true">
      <circle cx="6" cy="9" r="2" fill={color} />
      <circle cx="10" cy="6" r="2" fill={color} />
      <circle cx="14" cy="6" r="2" fill={color} />
      <circle cx="18" cy="9" r="2" fill={color} />
      <path d="M7 17c0-3 2.5-5 5-5s5 2 5 5c0 2-2 3-5 3s-5-1-5-3z" fill={color} />
    </svg>
  );
}

function SunbeamIcon({ color = 'currentColor' }: { color?: string } = {}) {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" aria-hidden="true">
      <circle cx="12" cy="12" r="4" fill={color} />
      {Array.from({ length: 8 }).map((_, i) => {
        const a = (i * Math.PI) / 4;
        const x1 = 12 + Math.cos(a) * 6;
        const y1 = 12 + Math.sin(a) * 6;
        const x2 = 12 + Math.cos(a) * 10;
        const y2 = 12 + Math.sin(a) * 10;
        return (
          <line
            key={i}
            x1={x1}
            y1={y1}
            x2={x2}
            y2={y2}
            stroke={color}
            strokeWidth="2"
            strokeLinecap="round"
          />
        );
      })}
    </svg>
  );
}

function FishBoneIcon({ color = 'currentColor' }: { color?: string } = {}) {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" aria-hidden="true">
      <circle cx="5" cy="12" r="2" fill={color} />
      <path d="M7 12h12" stroke={color} strokeWidth="1.5" strokeLinecap="round" />
      <path d="M9 9v6" stroke={color} strokeWidth="1.5" strokeLinecap="round" />
      <path d="M13 8v8" stroke={color} strokeWidth="1.5" strokeLinecap="round" />
      <path d="M17 9v6" stroke={color} strokeWidth="1.5" strokeLinecap="round" />
      <path
        d="M19 12l3-2v4z"
        fill="none"
        stroke={color}
        strokeWidth="1.5"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function YarnBallIcon({ color = 'currentColor' }: { color?: string } = {}) {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" aria-hidden="true">
      <circle cx="12" cy="12" r="7" fill="none" stroke={color} strokeWidth="1.4" />
      <path
        d="M5 12c4-1 8-1 14 0M7 8c4 1 8 3 12 6M7 16c4-1 8-3 12-6"
        fill="none"
        stroke={color}
        strokeWidth="1"
      />
      <path d="M19 19l4 4" stroke={color} strokeWidth="1.4" strokeLinecap="round" />
    </svg>
  );
}

function WhiskerIcon({ color = COZY.inkBrown }: { color?: string } = {}) {
  return (
    <svg width="40" height="20" viewBox="0 0 40 20" aria-hidden="true">
      <path
        d="M3 6 L18 10 M3 10 L18 10 M3 14 L18 10"
        stroke={color}
        strokeWidth="1"
        strokeLinecap="round"
      />
      <path
        d="M37 6 L22 10 M37 10 L22 10 M37 14 L22 10"
        stroke={color}
        strokeWidth="1"
        strokeLinecap="round"
      />
      <circle cx="20" cy="10" r="2" fill={color} />
    </svg>
  );
}

function CrownPawIcon() {
  return (
    <svg width="48" height="48" viewBox="0 0 48 48" aria-hidden="true">
      <path
        d="M8 22 L14 12 L20 20 L24 8 L28 20 L34 12 L40 22 L40 32 L8 32 Z"
        fill={COZY.butterscotch}
        stroke={COZY.inkBrown}
        strokeWidth="1.3"
        strokeLinejoin="round"
      />
      <g transform="translate(15,30)">
        <circle cx="3" cy="3" r="2" fill={COZY.inkBrown} />
        <circle cx="7" cy="1.5" r="2" fill={COZY.inkBrown} />
        <circle cx="11" cy="1.5" r="2" fill={COZY.inkBrown} />
        <circle cx="15" cy="3" r="2" fill={COZY.inkBrown} />
        <path d="M4 9c0-3 2.5-5 5-5s5 2 5 5c0 2-2 3-5 3s-5-1-5-3z" fill={COZY.inkBrown} />
      </g>
    </svg>
  );
}

function TypeGlyph({
  type,
  category,
}: {
  type: CatsCard['card_type'];
  category?: CatsCategory;
}) {
  const color = category ? CATEGORY_TINT[category] : COZY.inkBrown;
  switch (type) {
    case 'Mood':
      return (
        <svg width="32" height="32" viewBox="0 0 32 32" aria-hidden="true">
          <circle cx="16" cy="16" r="9" fill="none" stroke={color} strokeWidth="1.6" />
          <circle cx="12" cy="14" r="1.4" fill={color} />
          <circle cx="20" cy="14" r="1.4" fill={color} />
          <path d="M11 20q5-3 10 0" stroke={color} strokeWidth="1.5" fill="none" strokeLinecap="round" />
        </svg>
      );
    case 'Snack':
      return <FishBoneIcon color={color} />;
    case 'Trinket':
      return <YarnBallIcon color={color} />;
    case 'Commander':
      return <CrownPawIcon />;
    case 'Cat':
    default:
      return <PawIcon size={32} color={color} />;
  }
}

// ---------------------------------------------------------------------------
// Deckbuilder GameModule — registered in registry.ts
// ---------------------------------------------------------------------------

function CatsStatsExtras({ stats }: { stats: DeckStats }) {
  const extras = (stats.extras ?? {}) as Record<string, number>;
  const tile = (label: string, value: number) => (
    <div
      key={label}
      className="rounded border px-3 py-2"
      style={{
        borderColor: '#d9b896',
        background: 'rgba(255, 248, 231, 0.85)',
        color: '#3e2c1c',
      }}
    >
      <div className="text-[10px] uppercase tracking-wider opacity-60">{label}</div>
      <div className="mt-1 text-lg font-semibold">{value}</div>
    </div>
  );
  return (
    <div className="mt-4 grid grid-cols-2 gap-2 text-xs">
      {tile('Cats', extras.cats_count ?? 0)}
      {tile('Moods', extras.mood_count ?? 0)}
      {tile('Snacks', extras.snack_count ?? 0)}
      {tile('Trinkets', extras.trinket_count ?? 0)}
    </div>
  );
}

export const cats: GameModule = {
  id: 'cats',
  label: 'Cats',
  showColors: false,
  costLabel: 'Value',
  typeFilters: ['CATS_CAT', 'CATS_MOOD', 'CATS_SNACK', 'CATS_TRINKET', 'CATS_COMMANDER'],
  formatType: (t) => {
    const stripped = t.replace(/^CATS_/, '');
    return stripped.charAt(0) + stripped.slice(1).toLowerCase();
  },
  tiles: (stats) => {
    if (!stats) return [];
    const ex = (stats.extras ?? {}) as Record<string, number>;
    return [
      { label: 'Cats', value: ex.cats_count ?? 0 },
      { label: 'Moods', value: ex.mood_count ?? 0 },
      { label: 'Snacks', value: ex.snack_count ?? 0 },
    ];
  },
  StatsExtras: CatsStatsExtras,
};

// Silence the "unused defaultFormatType" warning when not used. Kept for
// parity with other modules in case future filters want it.
void defaultFormatType;
