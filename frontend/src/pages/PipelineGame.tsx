/**
 * PipelineGame — HD-CRIT-002 §06, v0.1 prototype.
 *
 * The ninth mode. Each turn an Event drops; both players simultaneously
 * slot one interceptor card from their hand into the corresponding stage
 * column (TRANSFORM / PREVENT / RESOLVE / REACT). The pipeline resolves:
 * whoever benefited takes the trick. First to 6 wins.
 *
 * v0.1 scope: single-screen, in-memory, no backend. AI opponent picks
 * randomly. Trick winner is computed from a simple heuristic — whoever
 * had a card in RESOLVE wins; tied/empty RESOLVE = no trick. The real
 * engine pipeline at `src/engine/types.py::InterceptorPriority` will run
 * the resolution when the backend manager lands (sequence step 11).
 */

import { useCallback, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  PIPELINE_CARD_POOL,
  drawStartingHand,
  type InterceptorCardDef,
  type PipelineStage,
} from '../data/pipelineCards';
import { PIPELINE_EVENT_DECK, rotateEvent } from '../data/pipelineEvents';
import {
  InterceptorCard,
  EventCard,
  PipelineColumn,
} from '../components/pipeline';

const STAGES: PipelineStage[] = ['TRANSFORM', 'PREVENT', 'RESOLVE', 'REACT'];
const WIN_TRICKS = 6;

type SlotMap = Record<PipelineStage, InterceptorCardDef | null>;

const emptySlots = (): SlotMap => ({
  TRANSFORM: null,
  PREVENT: null,
  RESOLVE: null,
  REACT: null,
});

type Phase = 'slot' | 'resolving' | 'won';

function pickAiCard(hand: InterceptorCardDef[]): InterceptorCardDef {
  const resolves = hand.filter((c) => c.stage === 'RESOLVE');
  const pool = resolves.length > 0 && Math.random() < 0.55 ? resolves : hand;
  return pool[Math.floor(Math.random() * pool.length)];
}

function computeTrickWinner(
  player: SlotMap,
  opponent: SlotMap,
): 'player' | 'opponent' | 'tie' {
  const pr = player.RESOLVE;
  const or = opponent.RESOLVE;
  if (pr && !or) return 'player';
  if (or && !pr) return 'opponent';
  if (pr && or) {
    if (pr.cost > or.cost) return 'player';
    if (or.cost > pr.cost) return 'opponent';
    return 'tie';
  }
  return 'tie';
}

export default function PipelineGame() {
  const navigate = useNavigate();
  const [turn, setTurn] = useState(0);
  const [playerHand, setPlayerHand] = useState<InterceptorCardDef[]>(() =>
    drawStartingHand(1),
  );
  const [opponentHand, setOpponentHand] = useState<InterceptorCardDef[]>(() =>
    drawStartingHand(3),
  );
  const [playerSlots, setPlayerSlots] = useState<SlotMap>(emptySlots);
  const [opponentSlots, setOpponentSlots] = useState<SlotMap>(emptySlots);
  const [playerTricks, setPlayerTricks] = useState(0);
  const [opponentTricks, setOpponentTricks] = useState(0);
  const [phase, setPhase] = useState<Phase>('slot');
  const [lastTrick, setLastTrick] = useState<'player' | 'opponent' | 'tie' | null>(null);

  const currentEvent = useMemo(
    () => rotateEvent(PIPELINE_EVENT_DECK, turn),
    [turn],
  );

  const drawOne = useCallback((existing: InterceptorCardDef[]): InterceptorCardDef => {
    const out = PIPELINE_CARD_POOL[Math.floor(Math.random() * PIPELINE_CARD_POOL.length)];
    if (existing.some((c) => c.id === out.id)) {
      return PIPELINE_CARD_POOL[(PIPELINE_CARD_POOL.indexOf(out) + 1) % PIPELINE_CARD_POOL.length];
    }
    return out;
  }, []);

  const nextTurn = useCallback(
    (winner: 'player' | 'opponent' | 'tie') => {
      const nextPlayerTricks = winner === 'player' ? playerTricks + 1 : playerTricks;
      const nextOpponentTricks = winner === 'opponent' ? opponentTricks + 1 : opponentTricks;
      setPlayerTricks(nextPlayerTricks);
      setOpponentTricks(nextOpponentTricks);
      if (nextPlayerTricks >= WIN_TRICKS || nextOpponentTricks >= WIN_TRICKS) {
        setPhase('won');
        return;
      }
      setPlayerHand((h) => [...h, drawOne(h)]);
      setOpponentHand((h) => [...h, drawOne(h)]);
      setPlayerSlots(emptySlots());
      setOpponentSlots(emptySlots());
      setTurn((t) => t + 1);
      setPhase('slot');
    },
    [playerTricks, opponentTricks, drawOne],
  );

  const handlePlayerSlot = useCallback(
    (card: InterceptorCardDef) => {
      if (phase !== 'slot') return;
      if (playerSlots[card.stage]) return;
      const aiCard = pickAiCard(opponentHand);
      const nextPlayerSlots: SlotMap = { ...playerSlots, [card.stage]: card };
      const nextOpponentSlots: SlotMap = { ...opponentSlots, [aiCard.stage]: aiCard };
      setPlayerSlots(nextPlayerSlots);
      setOpponentSlots(nextOpponentSlots);
      setPlayerHand((h) => h.filter((c) => c.id !== card.id));
      setOpponentHand((h) => h.filter((c) => c.id !== aiCard.id));
      setPhase('resolving');
      const winner = computeTrickWinner(nextPlayerSlots, nextOpponentSlots);
      setLastTrick(winner);
      window.setTimeout(() => nextTurn(winner), 1400);
    },
    [phase, playerSlots, opponentSlots, opponentHand, nextTurn],
  );

  const restart = () => {
    setTurn(0);
    setPlayerHand(drawStartingHand(1));
    setOpponentHand(drawStartingHand(3));
    setPlayerSlots(emptySlots());
    setOpponentSlots(emptySlots());
    setPlayerTricks(0);
    setOpponentTricks(0);
    setPhase('slot');
    setLastTrick(null);
  };

  const wonBy = playerTricks >= WIN_TRICKS ? 'player' : opponentTricks >= WIN_TRICKS ? 'opponent' : null;

  return (
    <div style={{ background: 'var(--paper)', color: 'var(--ink)', minHeight: '100vh' }}>
      {/* Caption rail */}
      <div
        style={{
          position: 'fixed',
          top: 14,
          left: '50%',
          transform: 'translateX(-50%)',
          fontFamily: 'var(--font-mono)',
          fontSize: 10.5,
          letterSpacing: '.14em',
          textTransform: 'uppercase',
          color: 'var(--ink-3)',
          background: 'var(--paper)',
          padding: '6px 14px',
          border: '1px solid var(--rule)',
          zIndex: 10,
        }}
      >
        <b style={{ color: 'var(--ink)', fontWeight: 500 }}>HD-PIPELINE</b>
        &nbsp;·&nbsp; Pipeline · the 9th mode &nbsp;·&nbsp; v0.1 prototype
      </div>

      <main style={{ maxWidth: 1320, margin: '0 auto', padding: '88px 32px 40px' }}>
        {/* Masthead */}
        <header
          style={{
            display: 'grid',
            gridTemplateColumns: '1fr auto',
            alignItems: 'end',
            borderTop: '1.5px solid var(--ink)',
            borderBottom: '1.5px solid var(--ink)',
            padding: '18px 0 22px',
            marginBottom: 24,
          }}
        >
          <div>
            <span
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: 12,
                fontWeight: 500,
                letterSpacing: '.12em',
                textTransform: 'uppercase',
                color: 'var(--ink-2)',
                display: 'block',
                marginBottom: 4,
              }}
            >
              Hyperdraft / Pipeline
            </span>
            <h1
              style={{
                margin: 0,
                fontFamily: 'var(--font-serif)',
                fontSize: 52,
                fontWeight: 400,
                lineHeight: 1,
                letterSpacing: '-.02em',
                color: 'var(--ink)',
              }}
            >
              The pipeline is the <em style={{ color: 'var(--sodium)', fontStyle: 'italic' }}>playmat</em>.
            </h1>
          </div>
          <button
            type="button"
            onClick={() => navigate('/')}
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 11,
              letterSpacing: '.14em',
              textTransform: 'uppercase',
              padding: '8px 14px',
              border: '1px solid var(--ink)',
              background: 'transparent',
              color: 'var(--ink)',
              cursor: 'pointer',
            }}
          >
            ← Lobby
          </button>
        </header>

        {/* Opponent rail */}
        <PlayerRail
          who="OPPONENT"
          name="Claudex"
          deckLabel="cross-engine deck"
          tricks={opponentTricks}
          handCount={opponentHand.length}
          deckCount={Math.max(0, 30 - turn - opponentHand.length)}
          align="left"
        />

        {/* Opponent face-down hand */}
        <div
          style={{
            display: 'flex',
            gap: 4,
            margin: '12px 0',
            justifyContent: 'center',
          }}
        >
          {opponentHand.slice(0, Math.min(6, opponentHand.length)).map((c, i, arr) => (
            <div
              key={c.id}
              style={{
                transform: `rotate(${(i - (arr.length - 1) / 2) * 2}deg) translateY(${Math.abs(i - (arr.length - 1) / 2) * 2}px)`,
              }}
            >
              <InterceptorCard card={c} faceDown width={68} height={94} />
            </div>
          ))}
        </div>

        {/* THE PIPELINE BOARD */}
        <div
          style={{
            position: 'relative',
            display: 'grid',
            gridTemplateColumns: 'repeat(4, 1fr)',
            gap: 12,
            padding: '20px 12px',
            borderTop: '2px solid var(--ink)',
            borderBottom: '2px solid var(--ink)',
            background: 'var(--paper-2)',
          }}
        >
          {/* Center event card overlays the pipeline columns */}
          <div
            style={{
              position: 'absolute',
              top: '50%',
              left: '50%',
              transform: 'translate(-50%, -50%)',
              zIndex: 5,
            }}
          >
            <EventCard event={currentEvent} index={turn} total={PIPELINE_EVENT_DECK.length} />
          </div>

          {STAGES.map((stage) => {
            const opp = opponentSlots[stage];
            const me = playerSlots[stage];
            const mandatory = stage === 'RESOLVE' && !me && phase === 'slot';
            return (
              <PipelineColumn
                key={stage}
                stage={stage}
                opponentCard={opp ? <InterceptorCard card={opp} /> : null}
                playerCard={
                  me ? (
                    <InterceptorCard
                      card={me}
                      sodium={phase === 'resolving' && stage === 'RESOLVE'}
                    />
                  ) : null
                }
                mandatory={mandatory}
              />
            );
          })}
        </div>

        {/* Player rail */}
        <PlayerRail
          who="YOU"
          name="Player"
          deckLabel="cross-engine deck"
          tricks={playerTricks}
          handCount={playerHand.length}
          deckCount={Math.max(0, 30 - turn - playerHand.length)}
          align="right"
          highlight
        />

        {/* Player hand */}
        <div
          style={{
            display: 'flex',
            gap: 6,
            marginTop: 16,
            justifyContent: 'center',
            flexWrap: 'wrap',
          }}
        >
          {playerHand.map((card) => {
            const alreadySlotted = playerSlots[card.stage] !== null;
            return (
              <InterceptorCard
                key={card.id}
                card={card}
                dim={alreadySlotted}
                onClick={
                  phase === 'slot' && !alreadySlotted
                    ? () => handlePlayerSlot(card)
                    : undefined
                }
              />
            );
          })}
        </div>

        {/* Status / resolution rail */}
        <div
          style={{
            marginTop: 22,
            padding: '14px 18px',
            border: '1px solid var(--rule)',
            background: 'var(--paper-2)',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            gap: 18,
            fontFamily: 'var(--font-mono)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
            <Stamp label="Phase" value={phase.toUpperCase()} sodium={phase === 'resolving'} />
            <Stamp label="Turn" value={String(turn + 1).padStart(2, '0')} />
            <Stamp label="Last trick" value={lastTrick ? lastTrick.toUpperCase() : '—'} />
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
            <span style={{ fontSize: 12, color: 'var(--ink-2)', letterSpacing: '.05em' }}>
              First to {WIN_TRICKS} tricks · {playerTricks} – {opponentTricks}
            </span>
            <button
              type="button"
              onClick={restart}
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: 11,
                letterSpacing: '.14em',
                textTransform: 'uppercase',
                padding: '8px 14px',
                border: '1px solid var(--ink)',
                background: 'transparent',
                color: 'var(--ink)',
                cursor: 'pointer',
              }}
            >
              Reshuffle
            </button>
          </div>
        </div>

        {/* Won-state banner */}
        {wonBy && (
          <div
            role="status"
            style={{
              marginTop: 16,
              padding: '22px 28px',
              background: 'var(--ink)',
              color: 'var(--paper)',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              gap: 18,
            }}
          >
            <span
              style={{
                fontFamily: 'var(--font-serif)',
                fontStyle: 'italic',
                fontSize: 28,
                lineHeight: 1.1,
              }}
            >
              {wonBy === 'player'
                ? 'You take the match.'
                : 'Claudex takes the match.'}
            </span>
            <span
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: 11,
                letterSpacing: '.14em',
                color: 'var(--sodium)',
                textTransform: 'uppercase',
              }}
            >
              HD-PIPELINE · END · {playerTricks}–{opponentTricks}
            </span>
          </div>
        )}

        {/* Footer */}
        <footer
          style={{
            marginTop: 48,
            paddingTop: 18,
            borderTop: '1.5px solid var(--ink)',
            display: 'flex',
            justifyContent: 'space-between',
            fontFamily: 'var(--font-mono)',
            fontSize: 11,
            color: 'var(--ink-3)',
            letterSpacing: '.06em',
          }}
        >
          <span>Pipeline v0.1 · client-only · AI = random RESOLVE-biased</span>
          <span style={{ letterSpacing: '.1em', textTransform: 'uppercase' }}>
            HD-PIPELINE · prototype
          </span>
        </footer>
      </main>
    </div>
  );
}

interface PlayerRailProps {
  who: string;
  name: string;
  deckLabel: string;
  tricks: number;
  handCount: number;
  deckCount: number;
  align: 'left' | 'right';
  highlight?: boolean;
}

function PlayerRail({ who, name, deckLabel, tricks, handCount, deckCount, align, highlight }: PlayerRailProps) {
  const left = (
    <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
      <span
        style={{
          fontFamily: 'var(--font-mono)',
          fontSize: 11,
          letterSpacing: '.14em',
          color: highlight ? 'var(--ink)' : 'var(--ink-2)',
          fontWeight: highlight ? 600 : 500,
        }}
      >
        {who}
      </span>
      <span style={{ fontFamily: 'var(--font-serif)', fontStyle: 'italic', fontSize: 18, color: 'var(--ink)' }}>
        {name}
      </span>
      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--ink-3)' }}>· {deckLabel}</span>
    </div>
  );
  const right = (
    <div style={{ display: 'flex', gap: 14 }}>
      <Stamp label="Tricks" value={String(tricks)} sodium={tricks > 0} />
      <Stamp label="Hand" value={String(handCount)} />
      <Stamp label="Deck" value={String(deckCount)} />
    </div>
  );
  return (
    <div
      style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        padding: '6px 0',
      }}
    >
      {align === 'left' ? left : right}
      {align === 'left' ? right : left}
    </div>
  );
}

function Stamp({ label, value, sodium }: { label: string; value: string; sodium?: boolean }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start' }}>
      <span
        style={{
          fontFamily: 'var(--font-mono)',
          fontSize: 9,
          letterSpacing: '.16em',
          textTransform: 'uppercase',
          color: 'var(--ink-3)',
        }}
      >
        {label}
      </span>
      <span
        style={{
          fontFamily: 'var(--font-mono)',
          fontSize: 16,
          fontWeight: 600,
          color: sodium ? 'var(--sodium)' : 'var(--ink)',
          letterSpacing: '.04em',
        }}
      >
        {value}
      </span>
    </div>
  );
}
