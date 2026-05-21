/**
 * PipelineGame — HD-CRIT-002 §06, v0.2 (server-backed).
 *
 * Replaces the v0.1 in-memory mock with a real game running on the existing
 * Hyperdraft engine. `pipelineAPI` talks to /api/pipeline/* endpoints:
 *   - POST /pipeline/start          → opens a match, returns HD-XXXX
 *   - POST /pipeline/{id}/play      → human plays, AI auto-plays, trick
 *                                     resolves on the real engine
 *   - POST /pipeline/{id}/reshuffle → reset state, keep the match id
 *
 * The lab shell + components (InterceptorCard, EventCard, PipelineColumn)
 * are unchanged from v0.1 — only the state machine pivots.
 */

import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  pipelineAPI,
  type PipelineCardSnapshot,
  type PipelineSnapshot,
  type PipelineResolution,
} from '../services/api';
import {
  InterceptorCard,
  EventCard,
  PipelineColumn,
} from '../components/pipeline';

const STAGES: Array<'TRANSFORM' | 'PREVENT' | 'RESOLVE' | 'REACT'> = [
  'TRANSFORM',
  'PREVENT',
  'RESOLVE',
  'REACT',
];
const WIN_TRICKS = 6;
const RESOLVE_FLASH_MS = 1600;

export default function PipelineGame() {
  const navigate = useNavigate();
  const [matchId, setMatchId] = useState<string | null>(null);
  const [playerId, setPlayerId] = useState<string | null>(null);
  const [snapshot, setSnapshot] = useState<PipelineSnapshot | null>(null);
  const [resolveFlash, setResolveFlash] = useState<PipelineResolution | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const start = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await pipelineAPI.start({});
      setMatchId(res.match_id);
      setPlayerId(res.player_id);
      setSnapshot(res.snapshot);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'failed to start match');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void start();
  }, [start]);

  const playCard = useCallback(
    async (card: PipelineCardSnapshot) => {
      if (!matchId || !playerId || !snapshot || busy) return;
      if (snapshot.phase !== 'slot') return;
      if (snapshot.slots[playerId][card.stage]) return;
      setBusy(true);
      try {
        const res = await pipelineAPI.playCard(matchId, playerId, card.id);
        setSnapshot(res.snapshot);
        if (res.trick_resolved && res.resolution) {
          setResolveFlash(res.resolution);
          window.setTimeout(() => setResolveFlash(null), RESOLVE_FLASH_MS);
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : 'play failed');
      } finally {
        setBusy(false);
      }
    },
    [matchId, playerId, snapshot, busy],
  );

  const reshuffle = useCallback(async () => {
    if (!matchId) {
      void start();
      return;
    }
    setBusy(true);
    try {
      const res = await pipelineAPI.reshuffle(matchId);
      setSnapshot(res.snapshot);
      setResolveFlash(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'reshuffle failed');
    } finally {
      setBusy(false);
    }
  }, [matchId, start]);

  // ── loading / error gates ───────────────────────────────────────────
  if (loading) {
    return <StatusShell label="Connecting to engine…" sub="HD-PIPELINE · v0.2" />;
  }
  if (error || !snapshot || !playerId) {
    return (
      <StatusShell
        label="Disconnected"
        sub={error ?? 'engine unreachable'}
        onRetry={() => void start()}
      />
    );
  }

  const opponentId =
    snapshot.player_a_id === playerId
      ? snapshot.player_b_id
      : snapshot.player_a_id;
  const playerHand = snapshot.hands[playerId];
  const opponentHand = snapshot.hands[opponentId];
  const playerSlots = snapshot.slots[playerId];
  const opponentSlots = snapshot.slots[opponentId];
  const playerTricks = snapshot.tricks[playerId];
  const opponentTricks = snapshot.tricks[opponentId];
  const playerDeck = snapshot.deck_count[playerId];
  const opponentDeck = snapshot.deck_count[opponentId];
  const wonBy = snapshot.phase === 'won' ? snapshot.winner : null;

  // Build a synthetic Event for the EventCard component. The api returns
  // `current_event.type` as a string (e.g. 'DAMAGE') with a payload dict;
  // the EventCard formatter expects `event.payload` to be a readable
  // single-line summary.
  const ev = snapshot.current_event;
  const payloadStr = Object.entries(ev.payload)
    .map(([k, v]) => `${k}: ${JSON.stringify(v)}`)
    .join(' · ');
  const eventForCard = {
    id: ev.id,
    type: ev.type,
    name: humanizeEventName(ev.type, ev.payload),
    payload: payloadStr,
  };

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
        <b style={{ color: 'var(--ink)', fontWeight: 500 }}>{snapshot.match_id}</b>
        &nbsp;·&nbsp; Pipeline · the 9th mode &nbsp;·&nbsp; v0.2
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
              Hyperdraft / Pipeline · {snapshot.match_id}
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

        {/* Resolution flash (transient) */}
        {resolveFlash && (
          <div
            role="status"
            style={{
              marginBottom: 12,
              padding: '10px 16px',
              background: 'var(--ink)',
              color: 'var(--paper)',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              gap: 18,
              fontFamily: 'var(--font-mono)',
              fontSize: 11,
              letterSpacing: '.1em',
            }}
          >
            <span style={{ color: 'var(--sodium)', textTransform: 'uppercase' }}>
              Trick →&nbsp;
              {resolveFlash.winner ?? 'no winner'}
            </span>
            <span style={{ color: 'var(--paper-2)' }}>
              {resolveFlash.log.slice(-1)[0] ?? ''}
            </span>
            <span>
              you {resolveFlash.a_impact.total} · opp {resolveFlash.b_impact.total}
            </span>
          </div>
        )}

        {/* Opponent rail */}
        <PlayerRail
          who="OPPONENT"
          name="Claudex"
          deckLabel="cross-engine deck"
          tricks={opponentTricks}
          handCount={opponentHand.length}
          deckCount={opponentDeck}
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
                transform: `rotate(${(i - (arr.length - 1) / 2) * 2}deg) translateY(${
                  Math.abs(i - (arr.length - 1) / 2) * 2
                }px)`,
              }}
            >
              <InterceptorCard
                card={asInterceptor(c)}
                faceDown
                width={68}
                height={94}
              />
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
            <EventCard
              event={eventForCard}
              index={snapshot.turn}
              total={Math.max(snapshot.turn + 1, 14)}
            />
          </div>

          {STAGES.map((stage) => {
            const opp = opponentSlots[stage];
            const me = playerSlots[stage];
            const mandatory =
              stage === 'RESOLVE' && !me && snapshot.phase === 'slot';
            return (
              <PipelineColumn
                key={stage}
                stage={stage}
                opponentCard={opp ? <InterceptorCard card={asInterceptor(opp)} /> : null}
                playerCard={me ? <InterceptorCard card={asInterceptor(me)} sodium /> : null}
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
          deckCount={playerDeck}
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
            const disabled = alreadySlotted || busy || snapshot.phase !== 'slot';
            return (
              <InterceptorCard
                key={card.id}
                card={asInterceptor(card)}
                dim={alreadySlotted}
                onClick={disabled ? undefined : () => void playCard(card)}
              />
            );
          })}
        </div>

        {/* Status rail */}
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
            <Stamp label="Phase" value={snapshot.phase.toUpperCase()} sodium={busy} />
            <Stamp label="Turn" value={String(snapshot.turn + 1).padStart(2, '0')} />
            <Stamp
              label="Last trick"
              value={snapshot.last_trick?.winner ? snapshot.last_trick.winner.toUpperCase() : '—'}
            />
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
            <span style={{ fontSize: 12, color: 'var(--ink-2)', letterSpacing: '.05em' }}>
              First to {WIN_TRICKS} tricks · {playerTricks} – {opponentTricks}
            </span>
            <button
              type="button"
              onClick={() => void reshuffle()}
              disabled={busy}
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: 11,
                letterSpacing: '.14em',
                textTransform: 'uppercase',
                padding: '8px 14px',
                border: '1px solid var(--ink)',
                background: 'transparent',
                color: 'var(--ink)',
                cursor: busy ? 'wait' : 'pointer',
                opacity: busy ? 0.6 : 1,
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
              {wonBy === playerId
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
              {snapshot.match_id} · END · {playerTricks}–{opponentTricks}
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
          <span>Pipeline v0.2 · engine-backed · /api/pipeline/{snapshot.match_id}</span>
          <span style={{ letterSpacing: '.1em', textTransform: 'uppercase' }}>
            HD-PIPELINE · v0.2
          </span>
        </footer>
      </main>
    </div>
  );
}

// ── helpers ──────────────────────────────────────────────────────────────

/** Server snapshot → InterceptorCardDef shape that the component expects. */
function asInterceptor(c: PipelineCardSnapshot) {
  return {
    id: c.id,
    engine: c.engine as 'MTG' | 'HS' | 'PKM' | 'YGO' | 'MNR' | 'FIN' | 'DPT' | 'SCP',
    stage: c.stage,
    cost: c.cost,
    name: c.name,
    text: c.text,
    art: c.art,
  };
}

/** Render a human-friendly title from a server EventType + payload. */
function humanizeEventName(type: string, payload: Record<string, unknown>): string {
  switch (type) {
    case 'DAMAGE':
      return `A source deals ${payload.amount} damage to ${payload.target ?? 'a player'}.`;
    case 'LIFE_CHANGE':
      return `${payload.player ?? 'A player'} would ${Number(payload.amount) >= 0 ? 'gain' : 'lose'} ${Math.abs(Number(payload.amount))} life.`;
    case 'DRAW':
      return `${payload.player ?? 'A player'} draws ${payload.count ?? 1} card${Number(payload.count) === 1 ? '' : 's'}.`;
    case 'ZONE_CHANGE':
      return `An object moves from ${payload.from_zone ?? '?'} to ${payload.to_zone ?? '?'}.`;
    case 'TURN_START':
      return `A new turn begins for ${payload.active ?? 'a player'}.`;
    case 'OBJECT_CREATED':
      return `An object enters the battlefield.`;
    case 'OBJECT_DESTROYED':
      return `${payload.object_id ?? 'An object'} is destroyed.`;
    case 'CAST':
      return `A spell is cast and goes on the stack.`;
    case 'ATTACK_DECLARED':
      return `An attack is declared at ${payload.target ?? 'a target'}.`;
    default:
      return type.replace(/_/g, ' ').toLowerCase();
  }
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

interface StatusShellProps {
  label: string;
  sub?: string;
  onRetry?: () => void;
}

function StatusShell({ label, sub, onRetry }: StatusShellProps) {
  return (
    <div
      style={{
        background: 'var(--paper)',
        color: 'var(--ink)',
        minHeight: '100vh',
        display: 'grid',
        placeItems: 'center',
        padding: 24,
      }}
    >
      <div
        style={{
          maxWidth: 520,
          padding: '36px 40px',
          border: '1.5px solid var(--ink)',
          background: 'var(--paper-2)',
          textAlign: 'left',
          fontFamily: 'var(--font-sans)',
        }}
      >
        <div
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 11,
            letterSpacing: '.14em',
            textTransform: 'uppercase',
            color: 'var(--ink-3)',
            marginBottom: 6,
          }}
        >
          {sub ?? 'HD-PIPELINE'}
        </div>
        <div
          style={{
            fontFamily: 'var(--font-serif)',
            fontStyle: 'italic',
            fontSize: 36,
            lineHeight: 1.05,
            color: 'var(--ink)',
            marginBottom: 14,
          }}
        >
          {label}
        </div>
        {onRetry && (
          <button
            type="button"
            onClick={onRetry}
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 11,
              letterSpacing: '.14em',
              textTransform: 'uppercase',
              padding: '10px 16px',
              border: '1px solid var(--ink)',
              background: 'var(--ink)',
              color: 'var(--paper)',
              cursor: 'pointer',
            }}
          >
            Retry
          </button>
        )}
      </div>
    </div>
  );
}
