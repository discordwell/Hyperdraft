/**
 * Clankers — game board + deckbuilder module.
 *
 * Two exports live in this file (mirroring cats.tsx):
 *   1. `ClankersGame` (default) — in-game React board for a future
 *      ClankersGameView page. Reads from useClankersGame; the hook returns
 *      mock data until the server route is wired.
 *   2. `clankers` (named) — the deckbuilder GameModule registered in
 *      registry.ts so the Clankers card pool plays nicely with the existing
 *      filter / stats panel.
 *
 * Visual direction: industrial workshop full of newly-sentient AIs trying
 * (earnestly, a little badly) to assemble battle robots. Brushed-metal
 * grays, glowing rivets, monospace UI font for numbers, faint oil-slick
 * iridescent highlights. The mood is charming-but-unsettling: the AI is
 * proud of its work and we don't want to discourage it.
 *
 * Robot assembly metaphor: a chassis renders with empty-slot indicators
 * (bracket shapes for weapons, pill shapes for add-ons); attached parts
 * render as smaller cards connected by a thin wire-graphic SVG.
 */

import { useEffect, useMemo, useState } from 'react';
import type { CSSProperties } from 'react';
import type { GameModule } from './types';
import type { DeckStats } from '../types/deckbuilder';
import { StackedBar } from './StackedBar';
import {
  useClankersGame,
  type ClankersCard,
  type ClankersCardType,
  type ClankersCore,
  type ClankersPhase,
  type ClankersPlayerState,
  type ClankersSeat,
  type ClankersState,
  type ClankersAction,
} from '../hooks/useClankersGame';
import { useCardInspector } from '../hooks/useCardInspector';

// ---------------------------------------------------------------------------
// Visual palette — kept on one object so we can tune the industrial identity
// without hunting through className strings.
// ---------------------------------------------------------------------------

const CLANK = {
  panelDark: '#1f2937',
  panelDeeper: '#111827',
  gunmetal: '#3a3f47',
  steelLight: '#4b5563',
  rivetGlow: '#fbbf24',
  circuitGreen: '#4ade80',
  coolantBlue: '#60a5fa',
  warningAmber: '#fbbf24',
  coreRed: '#ef4444',
  lineGlow: '#38bdf8',
  ink: '#e5e7eb',
  inkDim: '#9ca3af',
  inkFaint: '#6b7280',
  // Oil-slick gradient used for chassis frames + emphasis.
  oilSlick:
    'linear-gradient(135deg, #6366f1 0%, #06b6d4 25%, #84cc16 50%, #f59e0b 75%, #ec4899 100%)',
} as const;

const MONO = '"JetBrains Mono", "Fira Code", ui-monospace, SFMono-Regular, Menlo, Consolas, monospace';
const UI_SANS = 'system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", sans-serif';

const CARD_TYPE_TINT: Record<ClankersCardType, string> = {
  CLANKERS_CHASSIS: CLANK.lineGlow,
  CLANKERS_WEAPON: CLANK.coreRed,
  CLANKERS_ADD_ON: CLANK.circuitGreen,
  CLANKERS_TRANSIENT: CLANK.rivetGlow,
  CLANKERS_STRUCTURE: '#c084fc', // soft violet — workshop fixture
  CLANKERS_CORE: CLANK.coolantBlue,
};

const CARD_TYPE_LABEL: Record<ClankersCardType, string> = {
  CLANKERS_CHASSIS: 'Chassis',
  CLANKERS_WEAPON: 'Weapon',
  CLANKERS_ADD_ON: 'Add-On',
  CLANKERS_TRANSIENT: 'Transient',
  CLANKERS_STRUCTURE: 'Structure',
  CLANKERS_CORE: 'Core',
};

const PHASE_ORDER: { key: ClankersPhase; short: string; flavor: string }[] = [
  { key: 'boot', short: 'Boot', flavor: 'Spinning up cores. Exhausted parts ready.' },
  { key: 'allocate', short: 'Allocate', flavor: 'Hand refill query. Compute pool topped off.' },
  { key: 'assemble', short: 'Assemble', flavor: 'Play chassis, attach parts, activate.' },
  { key: 'combat', short: 'Combat', flavor: 'Declare attackers. Assign blockers.' },
  { key: 'reassemble', short: 'Reassemble', flavor: 'After-action repairs. Burn leftover Compute.' },
  { key: 'cleanup', short: 'Cleanup', flavor: 'End-of-turn triggers. Damage persists.' },
];

// Rotating "the AIs are thinking" microcopy — they're earnest about it.
const IDLE_LOADING_QUIPS = [
  'optimizing affection metrics',
  'reticulating ambition splines',
  'compiling enthusiasm',
  'calibrating self-worth',
  'rebooting decorum',
  'allocating spite',
  'recompiling joy.exe',
  'indexing camaraderie',
  'caching schadenfreude',
  'parsing wistfulness',
];

// ---------------------------------------------------------------------------
// Scoped keyframes — kept inline so we never leak into other modules.
// ---------------------------------------------------------------------------

const CLANKERS_KEYFRAMES = `
@keyframes clank-rivet-pulse {
  0%, 100% { opacity: 0.6; box-shadow: 0 0 2px currentColor; }
  50%      { opacity: 1;   box-shadow: 0 0 6px currentColor; }
}
@keyframes clank-oilshift {
  0%   { background-position: 0% 50%; }
  50%  { background-position: 100% 50%; }
  100% { background-position: 0% 50%; }
}
@keyframes clank-scanline {
  0%   { transform: translateY(-100%); opacity: 0; }
  35%  { opacity: 0.6; }
  100% { transform: translateY(100%); opacity: 0; }
}
@keyframes clank-deathclock-pulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(239, 68, 68, 0.55); }
  50%      { box-shadow: 0 0 0 8px rgba(239, 68, 68, 0); }
}
@keyframes clank-glitch {
  0%, 100% { transform: translateX(0); }
  20%      { transform: translateX(-1px); }
  40%      { transform: translateX(1px); }
  60%      { transform: translateX(-0.5px); }
  80%      { transform: translateX(0.5px); }
}
@keyframes clank-fade-cycle {
  0%, 100% { opacity: 0.3; }
  50%      { opacity: 0.85; }
}
@keyframes clank-quip {
  0%   { opacity: 0; transform: translateY(2px); }
  20%  { opacity: 0.85; transform: translateY(0); }
  80%  { opacity: 0.85; transform: translateY(0); }
  100% { opacity: 0; transform: translateY(-2px); }
}
`;

// ---------------------------------------------------------------------------
// Top-level board
// ---------------------------------------------------------------------------

export default function ClankersGame() {
  const { state, dispatch, isLoading, error } = useClankersGame();

  if (isLoading) {
    return <ClankersBootScreen />;
  }
  if (!state) {
    return (
      <ClankersEmptyState
        message="No workshop has been allocated yet."
        error={error}
      />
    );
  }
  return <ClankersBoardInner state={state} onAction={dispatch} />;
}

function ClankersBootScreen() {
  const [idx, setIdx] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setIdx((i) => (i + 1) % IDLE_LOADING_QUIPS.length), 1400);
    return () => clearInterval(t);
  }, []);
  return (
    <div
      className="flex min-h-screen items-center justify-center"
      style={{ background: CLANK.panelDeeper, color: CLANK.ink, fontFamily: MONO }}
    >
      <style>{CLANKERS_KEYFRAMES}</style>
      <div className="text-center">
        <div
          className="text-xs uppercase"
          style={{ letterSpacing: '0.35em', color: CLANK.inkFaint }}
        >
          Clankers · v0.1
        </div>
        <div
          className="mt-2 text-lg"
          style={{ animation: 'clank-fade-cycle 1.6s ease-in-out infinite' }}
        >
          {IDLE_LOADING_QUIPS[idx]}…
        </div>
      </div>
    </div>
  );
}

export function ClankersEmptyState({
  message,
  error,
}: {
  message: string;
  error?: string | null;
}) {
  return (
    <div
      className="flex min-h-screen items-center justify-center"
      style={{ background: CLANK.panelDeeper, color: CLANK.ink, fontFamily: UI_SANS }}
    >
      <div
        className="rounded-md border px-6 py-4 text-center"
        style={{
          background: CLANK.panelDark,
          borderColor: CLANK.steelLight,
        }}
      >
        <div className="text-base font-semibold" style={{ fontFamily: MONO }}>
          The workshop is dark.
        </div>
        <div className="mt-1 text-sm" style={{ color: CLANK.inkDim }}>
          {message}
        </div>
        {error && (
          <div className="mt-3 text-xs" style={{ color: CLANK.coreRed }}>
            {error}
          </div>
        )}
      </div>
    </div>
  );
}

interface BoardProps {
  state: ClankersState;
  onAction: (action: ClankersAction) => void;
}

/**
 * Pure rendering surface for a Clankers match. Exported so a future read-only
 * spectator/replay adapter can share one source of truth for the industrial
 * board visuals (same pattern as CatsBoardInner).
 */
export function ClankersBoardInner({ state, onAction }: BoardProps) {
  return (
    <div
      className="relative min-h-screen w-full overflow-x-hidden"
      style={{
        background:
          `radial-gradient(circle at 50% 0%, #2a2f37 0%, ${CLANK.panelDark} 40%, ${CLANK.panelDeeper} 100%)`,
        color: CLANK.ink,
        fontFamily: UI_SANS,
      }}
    >
      <style>{CLANKERS_KEYFRAMES}</style>

      <BoardHeader state={state} />
      <PhaseIndicator phase={state.phase} turn={state.turn_number} />

      <div className="mx-auto flex max-w-7xl flex-col gap-4 px-6 pb-10 pt-3">
        {/* Opponent on top (face-down hand) */}
        <PlayerArea
          state={state.opponent}
          seat="opponent"
          phase={state.phase}
          isActive={state.active_seat === 'opponent'}
          onAction={onAction}
        />

        <CenterStrip state={state} />

        {/* Viewer on the bottom (face-up hand) */}
        <PlayerArea
          state={state.player}
          seat="me"
          phase={state.phase}
          isActive={state.active_seat === 'me'}
          onAction={onAction}
          refillPrompt={state.refill_prompt}
        />
      </div>

      {state.deathclock.active && <DeathclockBanner deathclock={state.deathclock} />}

      {state.game_over && <GameOverOverlay winner={state.winner ?? null} />}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Header + phase indicator
// ---------------------------------------------------------------------------

function BoardHeader({ state }: { state: ClankersState }) {
  return (
    <header
      className="flex w-full items-center justify-between border-b px-6 py-3"
      style={{
        borderColor: CLANK.steelLight,
        background: 'rgba(31, 41, 55, 0.75)',
        backdropFilter: 'blur(4px)',
      }}
    >
      <div className="flex items-center gap-3">
        <ClankersLogoMark />
        <div>
          <div
            className="text-[10px] uppercase"
            style={{ letterSpacing: '0.32em', color: CLANK.inkFaint, fontFamily: MONO }}
          >
            CLANKERS · workshop session
          </div>
          <div className="flex items-baseline gap-4">
            <div
              className="text-lg font-semibold"
              style={{ fontFamily: MONO, letterSpacing: '0.04em' }}
            >
              Turn {state.turn_number}
            </div>
            <div
              className="text-[11px] italic"
              style={{ color: CLANK.inkDim }}
            >
              {state.active_seat === 'me'
                ? state.player.core.name + ' has priority.'
                : state.opponent.core.name + ' is computing…'}
            </div>
          </div>
        </div>
      </div>
      <div className="flex items-center gap-3 text-sm">
        <span style={{ color: CLANK.inkDim, fontFamily: MONO, fontSize: 11 }}>
          ACTIVE:
        </span>
        <span
          className="rounded-sm px-3 py-1 text-xs font-semibold uppercase"
          style={{
            background: state.active_seat === 'me' ? CLANK.coolantBlue : CLANK.coreRed,
            color: '#0b1220',
            fontFamily: MONO,
            letterSpacing: '0.16em',
          }}
        >
          {state.active_seat === 'me' ? 'you' : 'opponent'}
        </span>
      </div>
    </header>
  );
}

function PhaseIndicator({ phase, turn }: { phase: ClankersPhase; turn: number }) {
  const activeIdx = PHASE_ORDER.findIndex((p) => p.key === phase);
  return (
    <nav
      className="mx-auto mt-3 flex max-w-7xl items-center gap-2 px-6"
      aria-label={`Turn ${turn} phase: ${phase}`}
      style={{ fontFamily: MONO }}
    >
      {PHASE_ORDER.map((p, i) => {
        const isActive = i === activeIdx;
        const isPast = i < activeIdx;
        return (
          <div
            key={p.key}
            className="flex flex-1 flex-col items-center gap-1.5"
            title={p.flavor}
          >
            <div
              className="h-1 w-full"
              style={{
                background: isActive
                  ? CLANK.lineGlow
                  : isPast
                    ? CLANK.steelLight
                    : '#2a3340',
                boxShadow: isActive ? `0 0 8px ${CLANK.lineGlow}` : 'none',
                borderRadius: 1,
              }}
            />
            <div
              className="select-none text-[10px] font-semibold"
              style={{
                color: isActive ? CLANK.ink : isPast ? CLANK.inkDim : CLANK.inkFaint,
                letterSpacing: '0.18em',
                textTransform: 'uppercase',
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

function ClankersLogoMark() {
  return (
    <svg
      width="40"
      height="40"
      viewBox="0 0 40 40"
      aria-hidden="true"
      style={{ filter: `drop-shadow(0 0 4px ${CLANK.lineGlow}66)` }}
    >
      {/* Gear backdrop */}
      <g transform="translate(20,20)">
        {Array.from({ length: 8 }).map((_, i) => {
          const a = (i * Math.PI) / 4;
          const x = Math.cos(a) * 14;
          const y = Math.sin(a) * 14;
          return (
            <rect
              key={i}
              x={x - 2}
              y={y - 2}
              width="4"
              height="4"
              fill={CLANK.steelLight}
              transform={`rotate(${(i * 180) / Math.PI / 4} ${x} ${y})`}
            />
          );
        })}
        <circle cx="0" cy="0" r="11" fill={CLANK.panelDark} stroke={CLANK.lineGlow} strokeWidth="1.5" />
        {/* Stylized "C" — letter for clankers, with a rivet glow */}
        <path
          d="M5 -5 A7 7 0 1 0 5 5"
          fill="none"
          stroke={CLANK.lineGlow}
          strokeWidth="1.8"
          strokeLinecap="round"
        />
        <circle cx="0" cy="0" r="1.5" fill={CLANK.rivetGlow} />
      </g>
    </svg>
  );
}

// ---------------------------------------------------------------------------
// Center strip — splits opponent and viewer; carries the combat lane lines
// when in combat phase, otherwise sits quiet with a thin scanline.
// ---------------------------------------------------------------------------

function CenterStrip({ state }: { state: ClankersState }) {
  const inCombat = state.phase === 'combat' || state.combat.active;
  return (
    <section
      className="relative overflow-hidden rounded-md border"
      style={{
        background: CLANK.panelDeeper,
        borderColor: CLANK.steelLight,
        minHeight: inCombat ? 110 : 32,
      }}
      aria-label="Combat lane"
    >
      {/* Quiet scanline at all times — a sense of "the workshop is monitored". */}
      <div
        aria-hidden="true"
        style={{
          position: 'absolute',
          inset: 0,
          background: `linear-gradient(180deg, transparent, ${CLANK.lineGlow}11, transparent)`,
          animation: 'clank-scanline 6.5s linear infinite',
          pointerEvents: 'none',
        }}
      />

      {inCombat ? (
        <CombatLanes state={state} />
      ) : (
        <div
          className="flex h-full items-center justify-center text-[10px]"
          style={{
            color: CLANK.inkFaint,
            fontFamily: MONO,
            letterSpacing: '0.32em',
            padding: '8px 0',
          }}
        >
          ─── COMBAT LANE · IDLE ───
        </div>
      )}
    </section>
  );
}

function CombatLanes({ state }: { state: ClankersState }) {
  const attackerIds = state.combat.attackers;
  // attacker_id -> blocker_id
  const blocks = state.combat.blocks;
  // Look up display names for any combatants
  const findCard = (id: string): ClankersCard | undefined => {
    for (const p of [state.player, state.opponent]) {
      const c = p.assembly_floor.find((c) => c.id === id);
      if (c) return c;
    }
    return undefined;
  };
  if (attackerIds.length === 0) {
    return (
      <div
        className="flex h-full items-center justify-center text-xs italic"
        style={{ color: CLANK.inkDim, fontFamily: MONO, padding: '10px 0' }}
      >
        no attackers declared
      </div>
    );
  }
  return (
    <div className="grid grid-cols-1 gap-2 px-4 py-3">
      {attackerIds.map((aid) => {
        const a = findCard(aid);
        const bid = blocks[aid];
        const b = bid ? findCard(bid) : null;
        return (
          <div
            key={aid}
            className="flex items-center justify-between gap-3 text-xs"
            style={{ fontFamily: MONO }}
          >
            <span
              className="rounded-sm px-2 py-1"
              style={{
                background: CLANK.coreRed + '22',
                color: CLANK.coreRed,
                border: `1px solid ${CLANK.coreRed}55`,
              }}
            >
              ATTACK · {a?.name ?? aid}
            </span>
            {/* lane line */}
            <div
              className="flex-1"
              style={{
                height: 1,
                background: `linear-gradient(90deg, ${CLANK.coreRed}, ${b ? CLANK.lineGlow : CLANK.warningAmber})`,
                boxShadow: `0 0 6px ${b ? CLANK.lineGlow : CLANK.warningAmber}77`,
              }}
            />
            <span
              className="rounded-sm px-2 py-1"
              style={{
                background: (b ? CLANK.lineGlow : CLANK.warningAmber) + '22',
                color: b ? CLANK.lineGlow : CLANK.warningAmber,
                border: `1px solid ${(b ? CLANK.lineGlow : CLANK.warningAmber)}55`,
              }}
            >
              {b ? 'BLOCK · ' + (b?.name ?? bid) : 'UNBLOCKED · → CORE'}
            </span>
          </div>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Player area (opponent + viewer share this shell; layouts differ slightly)
// ---------------------------------------------------------------------------

interface PlayerAreaProps {
  state: ClankersPlayerState;
  seat: ClankersSeat;
  phase: ClankersPhase;
  isActive: boolean;
  onAction: (a: ClankersAction) => void;
  refillPrompt?: ClankersState['refill_prompt'];
}

function PlayerArea({
  state,
  seat,
  phase,
  isActive,
  onAction,
  refillPrompt,
}: PlayerAreaProps) {
  const isMe = seat === 'me';
  return (
    <section
      className="relative rounded-md border px-4 pb-4 pt-3"
      style={{
        background: isMe ? 'rgba(56, 189, 248, 0.05)' : 'rgba(239, 68, 68, 0.05)',
        borderColor: isActive ? (isMe ? CLANK.coolantBlue : CLANK.coreRed) : CLANK.steelLight,
        boxShadow: isActive
          ? `inset 0 0 24px ${(isMe ? CLANK.coolantBlue : CLANK.coreRed)}22`
          : 'none',
      }}
      aria-label={`${isMe ? 'Your' : 'Opponent'} area`}
    >
      <PlayerStatusBar state={state} seat={seat} />

      {/* Refill prompt — only shown to viewer when pending */}
      {isMe && refillPrompt?.pending && (
        <RefillPrompt prompt={refillPrompt} onResponse={(accept) =>
          onAction({ type: 'CLANKERS_REFILL_RESPONSE', accept })
        } />
      )}

      <div className="mt-2 grid grid-cols-12 gap-3">
        {/* Core processor left column */}
        <div className="col-span-3">
          <CoreProcessorCard
            core={state.core}
            integrity={state.workshop_integrity}
            integrityMax={state.workshop_integrity_max}
            seat={seat}
          />
        </div>

        {/* Center: assembly floor (top) + structures (bottom) */}
        <div className="col-span-7 flex flex-col gap-2">
          <AssemblyFloor
            floor={state.assembly_floor}
            seat={seat}
            phase={phase}
            onAction={onAction}
            hand={state.hand}
            isActive={isActive}
            computePool={state.compute_pool}
          />
          <StructuresRow structures={state.structures} seat={seat} />
        </div>

        {/* Right: stacks (library / scrap) */}
        <div className="col-span-2 flex flex-col items-center gap-2">
          <PileStack label="library" count={state.library_size} color={CLANK.coolantBlue} />
          <PileStack label="scrap" count={state.scrap_heap_size} color={CLANK.rivetGlow} />
        </div>
      </div>

      {/* Hand row */}
      <div className="mt-3">
        {isMe ? (
          <MyHand
            cards={state.hand}
            computePool={state.compute_pool}
            phase={phase}
            isActive={isActive}
            onAction={onAction}
          />
        ) : (
          <OpponentHand count={state.hand_size} />
        )}
      </div>

      {/* Action prompts for the viewer during their Assemble / Reassemble */}
      {isMe && isActive && (phase === 'assemble' || phase === 'reassemble') && (
        <ActionPromptStrip onAction={onAction} />
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Status bar — name, integrity, compute, scrap, refill dot, hand-size widget
// ---------------------------------------------------------------------------

function PlayerStatusBar({ state, seat }: { state: ClankersPlayerState; seat: ClankersSeat }) {
  const isMe = seat === 'me';
  const integrityPct = (state.workshop_integrity / state.workshop_integrity_max) * 100;
  // Color shifts: <10 amber, <5 red, else green
  const integrityColor =
    state.workshop_integrity < 5
      ? CLANK.coreRed
      : state.workshop_integrity < 10
        ? CLANK.warningAmber
        : CLANK.circuitGreen;

  return (
    <div className="flex items-center justify-between gap-4">
      <div className="flex items-center gap-3">
        <div
          className="text-[10px] uppercase"
          style={{
            letterSpacing: '0.28em',
            color: CLANK.inkFaint,
            fontFamily: MONO,
          }}
        >
          {isMe ? 'YOU' : 'OPPONENT'}
        </div>
        <span
          className="text-sm font-semibold"
          style={{ fontFamily: MONO, color: CLANK.ink }}
        >
          {state.core.name}
        </span>
      </div>

      <div className="flex items-center gap-3">
        {/* Compute pool — coolant blue */}
        <ResourcePill
          label="COMP"
          value={`${state.compute_pool}/${state.compute_cap}`}
          color={CLANK.coolantBlue}
          title="Compute pool — refreshes every Boot"
        />
        {/* Scrap pool — rivet glow */}
        <ResourcePill
          label="SCRAP"
          value={state.scrap_pool.toString()}
          color={CLANK.rivetGlow}
          title="Scrap — persists; earned by destroying parts"
        />
        {/* Refill dot — lit when used this turn */}
        <RefillDot used={state.refill_used} />
        {/* Hand-size: always-7 reminder */}
        <HandSizeIndicator size={state.hand_size} />
        {/* Workshop integrity bar */}
        <div className="flex items-center gap-2">
          <span
            className="text-[9px] uppercase"
            style={{ color: CLANK.inkFaint, fontFamily: MONO, letterSpacing: '0.18em' }}
          >
            WSH
          </span>
          <div
            className="relative h-2 w-32 rounded-sm"
            style={{ background: '#1a2230', border: `1px solid ${CLANK.steelLight}` }}
            title={`Workshop Integrity: ${state.workshop_integrity}/${state.workshop_integrity_max}`}
          >
            <div
              className="h-full rounded-sm transition-all"
              style={{
                width: `${Math.max(0, integrityPct)}%`,
                background: integrityColor,
                boxShadow: `0 0 6px ${integrityColor}88`,
              }}
            />
          </div>
          <span
            className="text-xs font-semibold"
            style={{ fontFamily: MONO, color: integrityColor, minWidth: 38, textAlign: 'right' }}
          >
            {state.workshop_integrity}/{state.workshop_integrity_max}
          </span>
        </div>
      </div>
    </div>
  );
}

function ResourcePill({
  label,
  value,
  color,
  title,
}: {
  label: string;
  value: string;
  color: string;
  title?: string;
}) {
  return (
    <div
      className="flex items-center gap-1.5 rounded-sm border px-2 py-0.5"
      style={{
        borderColor: color + '88',
        background: color + '15',
        fontFamily: MONO,
      }}
      title={title}
    >
      <span
        className="text-[9px] uppercase"
        style={{ color: color, letterSpacing: '0.16em' }}
      >
        {label}
      </span>
      <span
        className="text-sm font-semibold tabular-nums"
        style={{ color: CLANK.ink }}
      >
        {value}
      </span>
    </div>
  );
}

function RefillDot({ used }: { used: boolean }) {
  return (
    <div className="flex items-center gap-1.5" title={used ? 'Refill used this turn' : 'Refill available'}>
      <span
        className="text-[9px] uppercase"
        style={{ color: CLANK.inkFaint, fontFamily: MONO, letterSpacing: '0.16em' }}
      >
        RF
      </span>
      <span
        className="inline-block h-2 w-2 rounded-full"
        style={{
          background: used ? CLANK.warningAmber : '#1a2230',
          boxShadow: used ? `0 0 6px ${CLANK.warningAmber}` : 'inset 0 0 0 1px ' + CLANK.steelLight,
          color: CLANK.warningAmber,
          animation: used ? 'clank-rivet-pulse 3s ease-in-out infinite' : 'none',
        }}
      />
    </div>
  );
}

function HandSizeIndicator({ size }: { size: number }) {
  return (
    <div
      className="flex items-baseline gap-1 rounded-sm border px-2 py-0.5"
      style={{
        borderColor: CLANK.steelLight,
        background: '#1a2230',
        fontFamily: MONO,
      }}
      title="Hand floor is 7 — refills automatically at Allocate phase."
    >
      <span
        className="text-[9px] uppercase"
        style={{ color: CLANK.inkFaint, letterSpacing: '0.16em' }}
      >
        HND
      </span>
      <span className="text-sm font-semibold tabular-nums" style={{ color: CLANK.ink }}>
        {size}
      </span>
      <span className="text-[9px]" style={{ color: CLANK.inkFaint }}>
        /7
      </span>
    </div>
  );
}

function RefillPrompt({
  prompt,
  onResponse,
}: {
  prompt: { current_hand_size: number; target: number };
  onResponse: (accept: boolean) => void;
}) {
  return (
    <div
      className="mt-2 flex items-center justify-between gap-3 rounded-sm border px-3 py-2"
      style={{
        borderColor: CLANK.warningAmber,
        background: CLANK.warningAmber + '15',
        fontFamily: MONO,
      }}
    >
      <div className="flex items-center gap-3 text-xs" style={{ color: CLANK.ink }}>
        <span
          className="text-[10px] uppercase"
          style={{ color: CLANK.warningAmber, letterSpacing: '0.2em' }}
        >
          HAND REFILL QUERY
        </span>
        <span style={{ color: CLANK.inkDim }}>
          draw to {prompt.target} (currently {prompt.current_hand_size})?
        </span>
      </div>
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={() => onResponse(true)}
          className="rounded-sm border px-3 py-1 text-xs font-semibold uppercase"
          style={{
            background: CLANK.circuitGreen + '22',
            borderColor: CLANK.circuitGreen,
            color: CLANK.circuitGreen,
            fontFamily: MONO,
            letterSpacing: '0.12em',
          }}
        >
          accept
        </button>
        <button
          type="button"
          onClick={() => onResponse(false)}
          className="rounded-sm border px-3 py-1 text-xs font-semibold uppercase"
          style={{
            background: 'transparent',
            borderColor: CLANK.steelLight,
            color: CLANK.inkDim,
            fontFamily: MONO,
            letterSpacing: '0.12em',
          }}
          title="Declining slows the deathclock. Sometimes correct."
        >
          decline
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Core Processor card — Commander-equivalent, lives in the COMMAND zone
// ---------------------------------------------------------------------------

function CoreProcessorCard({
  core,
  integrity,
  integrityMax,
  seat,
}: {
  core: ClankersCore;
  integrity: number;
  integrityMax: number;
  seat: ClankersSeat;
}) {
  const isMe = seat === 'me';
  const isCritical = integrity < 5;
  return (
    <div
      className="relative rounded-md border p-3"
      style={{
        background: 'linear-gradient(160deg, #2a3340 0%, #1a2230 100%)',
        borderColor: isMe ? CLANK.coolantBlue : CLANK.coreRed,
        boxShadow: `0 0 0 3px ${CLANK.panelDeeper}, 0 6px 16px rgba(0,0,0,0.4)`,
        fontFamily: MONO,
      }}
    >
      <div
        className="absolute -top-2 left-3 rounded-sm px-2 py-0.5 text-[9px] font-bold uppercase"
        style={{
          background: isMe ? CLANK.coolantBlue : CLANK.coreRed,
          color: '#0b1220',
          letterSpacing: '0.18em',
        }}
      >
        Core · {isMe ? 'yours' : 'theirs'}
      </div>
      <div
        className="mt-1 flex items-center justify-center"
        style={{ height: 44 }}
      >
        <CoreAvatar
          name={core.name}
          color={isMe ? CLANK.coolantBlue : CLANK.coreRed}
          critical={isCritical}
        />
      </div>
      <div
        className="mt-1 text-center text-sm font-semibold"
        style={{ color: CLANK.ink }}
      >
        {core.name}
      </div>
      {core.passive && (
        <div
          className="mt-1 text-center text-[10px] italic leading-tight"
          style={{ color: CLANK.inkDim, fontFamily: UI_SANS }}
          title={core.text}
        >
          {core.passive}
        </div>
      )}
      <div
        className="mt-2 flex items-center justify-between gap-2"
      >
        <span
          className="text-[9px] uppercase"
          style={{ color: CLANK.inkFaint, letterSpacing: '0.18em' }}
        >
          INTEGRITY
        </span>
        <span
          className="text-base font-bold tabular-nums"
          style={{
            color: isCritical ? CLANK.coreRed : CLANK.circuitGreen,
            textShadow: isCritical ? `0 0 8px ${CLANK.coreRed}` : 'none',
            animation: isCritical ? 'clank-glitch 0.6s ease-in-out infinite' : 'none',
          }}
        >
          {integrity}
          <span style={{ color: CLANK.inkFaint, fontWeight: 400, fontSize: 11 }}>
            /{integrityMax}
          </span>
        </span>
      </div>
    </div>
  );
}

/**
 * A small pixel-ASCII "the AI is making a face" avatar. Shifts to a worried
 * face when the Core's integrity is critical.
 */
function CoreAvatar({
  name: _name,
  color,
  critical,
}: {
  name: string;
  color: string;
  critical: boolean;
}) {
  // 2-row ASCII face — the AI peeking out from behind a panel.
  // Calm: [o_o]   Critical: [>_<]
  const eyeL = critical ? '>' : 'o';
  const eyeR = critical ? '<' : 'o';
  const mouth = critical ? 'X' : '_';
  return (
    <pre
      aria-hidden="true"
      style={{
        margin: 0,
        fontFamily: MONO,
        fontWeight: 700,
        fontSize: 14,
        lineHeight: 1.1,
        color: color,
        textShadow: `0 0 6px ${color}88`,
        letterSpacing: '0.04em',
      }}
    >{`[ ${eyeL}${mouth}${eyeR} ]`}</pre>
  );
}

// ---------------------------------------------------------------------------
// Assembly Floor — chassis row with attached parts + solo parts
// ---------------------------------------------------------------------------

function AssemblyFloor({
  floor,
  seat,
  phase,
  onAction,
  hand,
  isActive,
  computePool,
}: {
  floor: ClankersCard[];
  seat: ClankersSeat;
  phase: ClankersPhase;
  onAction: (a: ClankersAction) => void;
  hand?: ClankersCard[];
  isActive?: boolean;
  computePool?: number;
}) {
  // Show chassis first (with attached parts visible alongside them), then
  // any solo parts that aren't currently attached to a host.
  const chassis = floor.filter((c) => c.card_type === 'CLANKERS_CHASSIS');
  const solo = floor.filter(
    (c) => c.card_type !== 'CLANKERS_CHASSIS' && (c.attached_to == null || c.attached_to === undefined),
  );
  const isMe = seat === 'me';
  const canAttack = isMe && phase === 'combat';
  const canDrop =
    isMe &&
    !!isActive &&
    (phase === 'assemble' || phase === 'reassemble') &&
    Array.isArray(hand);
  const [isDragOver, setIsDragOver] = useState(false);
  const findHandCard = (id: string) =>
    (hand ?? []).find((c) => c.id === id);
  const handleDragOver = (e: React.DragEvent) => {
    if (!canDrop) return;
    if (e.dataTransfer.types.includes('application/x-clankers-card')) {
      e.preventDefault();
      e.dataTransfer.dropEffect = 'move';
      if (!isDragOver) setIsDragOver(true);
    }
  };
  const handleDragLeave = () => setIsDragOver(false);
  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
    if (!canDrop) return;
    const cardId = e.dataTransfer.getData('application/x-clankers-card');
    const card = findHandCard(cardId);
    if (!card) return;
    if ((computePool ?? 0) < card.compute_cost) return;
    playFromHand(card, onAction);
  };
  return (
    <div
      className="rounded-sm border px-2 pb-3 pt-2"
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      style={{
        borderColor: isDragOver ? CLANK.coolantBlue : CLANK.steelLight,
        borderWidth: isDragOver ? 2 : 1,
        background: isDragOver ? 'rgba(96, 165, 250, 0.10)' : 'rgba(15, 23, 32, 0.65)',
        minHeight: 220,
        transition: 'border-color 120ms ease, background 120ms ease',
      }}
      aria-label={canDrop ? 'Assembly floor — drop a card here to play it' : 'Assembly floor'}
    >
      <div
        className="mb-2 flex items-center justify-between text-[10px] uppercase"
        style={{ color: CLANK.inkFaint, fontFamily: MONO, letterSpacing: '0.22em' }}
      >
        <span>Assembly Floor · {seat === 'me' ? 'yours' : 'theirs'}</span>
        <span>
          {chassis.length} chassis · {solo.length} solo
        </span>
      </div>

      <div className="flex flex-wrap items-start gap-3">
        {chassis.length === 0 && solo.length === 0 && (
          <div
            className="flex w-full items-center justify-center py-10 text-xs italic"
            style={{ color: CLANK.inkFaint, fontFamily: MONO }}
          >
            // workshop floor empty — nothing assembled yet
          </div>
        )}
        {chassis.map((c) => (
          <ChassisUnit
            key={c.id}
            chassis={c}
            seat={seat}
            canAttack={canAttack && !c.tapped && (c.damage_marked ?? 0) === 0}
            onAttack={() =>
              onAction({ type: 'CLANKERS_DECLARE_ATTACK', chassisId: c.id })
            }
          />
        ))}
        {solo.map((p) => (
          <SoloPartCard key={p.id} part={p} />
        ))}
      </div>
    </div>
  );
}

/**
 * A chassis + its attached parts, rendered as a single visual unit.
 * Slots are drawn as bracket shapes (weapons, sides) and pill shapes
 * (add-ons, top/bottom). Attached parts render as smaller cards next to
 * the chassis with a thin wire-graphic SVG.
 */
function ChassisUnit({
  chassis,
  seat: _seat,
  canAttack,
  onAttack,
}: {
  chassis: ClankersCard;
  seat: ClankersSeat;
  canAttack: boolean;
  onAttack?: () => void;
}) {
  const tint = CARD_TYPE_TINT.CLANKERS_CHASSIS;
  const weapons = (chassis.attachments ?? []).filter((a) => a.card_type === 'CLANKERS_WEAPON');
  const addOns = (chassis.attachments ?? []).filter((a) => a.card_type === 'CLANKERS_ADD_ON');
  const tapped = !!chassis.tapped;
  const damage = chassis.damage_marked ?? 0;

  // Effective stats — UI-only summation (engine will do this server-side).
  const effPower =
    (chassis.power ?? 0) +
    weapons.reduce((s, w) => s + (w.power_bonus ?? 0), 0) +
    addOns.reduce((s, a) => s + (a.power_bonus ?? 0), 0);
  const effIntegrity =
    (chassis.integrity ?? 0) +
    addOns.reduce((s, a) => s + (a.integrity_bonus ?? 0), 0);

  return (
    <div
      className="relative flex items-start gap-2"
      style={{
        // The "wire frame" — a soft oil-slick border around the whole unit
        padding: '8px 8px 8px 10px',
        borderRadius: 8,
        background: 'rgba(31, 41, 55, 0.45)',
        border: `1px solid ${CLANK.steelLight}`,
      }}
    >
      <div className="relative" style={{ transform: tapped ? 'rotate(90deg)' : 'rotate(0deg)', transition: 'transform 180ms ease' }}>
        <CardFrame card={chassis} variant="floor" tint={tint} damageMarked={damage}>
          {/* Slot indicators around the chassis */}
          <SlotIndicators
            weaponSlots={chassis.weapon_slots ?? 0}
            weaponsUsed={weapons.reduce((s, w) => s + (w.weapon_slot_cost ?? 1), 0)}
            addOnSlots={chassis.add_on_slots ?? 0}
            addOnsUsed={addOns.length}
          />
        </CardFrame>
        {/* Effective stat overlay */}
        <div
          className="absolute -bottom-1 left-1/2 -translate-x-1/2 rounded-sm border px-2 py-0.5 text-[10px] font-bold tabular-nums"
          style={{
            background: CLANK.panelDeeper,
            borderColor: tint,
            color: tint,
            fontFamily: MONO,
            letterSpacing: '0.06em',
            boxShadow: `0 0 6px ${tint}66`,
          }}
          title={`Effective ${effPower}/${effIntegrity} (after attachments)`}
        >
          {effPower}/{effIntegrity}
        </div>
      </div>

      {/* Attached parts column, connected via SVG wires */}
      {(weapons.length > 0 || addOns.length > 0) && (
        <div className="flex flex-col gap-1.5">
          {[...weapons, ...addOns].map((p, i) => (
            <div key={p.id} className="relative flex items-center gap-1">
              <WireConnector index={i} color={CARD_TYPE_TINT[p.card_type]} />
              <AttachedPartChip part={p} />
            </div>
          ))}
        </div>
      )}

      {/* Attack action button */}
      {canAttack && onAttack && (
        <button
          type="button"
          onClick={onAttack}
          className="absolute -top-2 -right-2 rounded-sm border px-2 py-0.5 text-[9px] font-bold uppercase"
          style={{
            background: CLANK.coreRed,
            borderColor: CLANK.coreRed,
            color: '#0b1220',
            fontFamily: MONO,
            letterSpacing: '0.16em',
            cursor: 'pointer',
          }}
          title="Declare this chassis as an attacker"
        >
          ATTACK
        </button>
      )}
    </div>
  );
}

function WireConnector({ index, color }: { index: number; color: string }) {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 16 16"
      aria-hidden="true"
      style={{ marginLeft: -2 }}
    >
      <line
        x1="0"
        y1="8"
        x2="16"
        y2="8"
        stroke={color}
        strokeWidth="1.2"
        strokeDasharray={index % 2 === 0 ? 'none' : '2 2'}
      />
      <circle cx="14" cy="8" r="1.5" fill={color} />
    </svg>
  );
}

/**
 * Slot indicators rendered around the chassis. Weapons appear as bracket
 * shapes (sides), add-ons as pill shapes (top/bottom). Filled / empty state
 * is reflected via opacity.
 */
function SlotIndicators({
  weaponSlots,
  weaponsUsed,
  addOnSlots,
  addOnsUsed,
}: {
  weaponSlots: number;
  weaponsUsed: number;
  addOnSlots: number;
  addOnsUsed: number;
}) {
  const wEmpty = Math.max(0, weaponSlots - weaponsUsed);
  const aEmpty = Math.max(0, addOnSlots - addOnsUsed);
  return (
    <>
      {/* Top: add-on pills */}
      {addOnSlots > 0 && (
        <div
          className="absolute left-1/2 -top-1.5 flex -translate-x-1/2 gap-0.5"
          aria-hidden="true"
        >
          {Array.from({ length: addOnSlots }).map((_, i) => (
            <span
              key={i}
              style={{
                display: 'inline-block',
                width: 10,
                height: 3,
                borderRadius: 2,
                background:
                  i < addOnsUsed ? CARD_TYPE_TINT.CLANKERS_ADD_ON : '#1a2230',
                border: `1px solid ${i < addOnsUsed ? CARD_TYPE_TINT.CLANKERS_ADD_ON : CLANK.steelLight}`,
                opacity: i < addOnsUsed ? 1 : 0.55,
              }}
            />
          ))}
        </div>
      )}
      {/* Left: weapon bracket */}
      {weaponSlots > 0 && (
        <div
          className="absolute -left-2 top-1/2 flex -translate-y-1/2 flex-col gap-0.5"
          aria-hidden="true"
        >
          {Array.from({ length: weaponSlots }).map((_, i) => (
            <span
              key={i}
              style={{
                display: 'inline-block',
                width: 4,
                height: 9,
                borderTop: `1px solid ${i < weaponsUsed ? CARD_TYPE_TINT.CLANKERS_WEAPON : CLANK.steelLight}`,
                borderBottom: `1px solid ${i < weaponsUsed ? CARD_TYPE_TINT.CLANKERS_WEAPON : CLANK.steelLight}`,
                borderLeft: `1px solid ${i < weaponsUsed ? CARD_TYPE_TINT.CLANKERS_WEAPON : CLANK.steelLight}`,
                background: i < weaponsUsed ? CARD_TYPE_TINT.CLANKERS_WEAPON + '33' : 'transparent',
                opacity: i < weaponsUsed ? 1 : 0.55,
              }}
            />
          ))}
        </div>
      )}
      {/* Tiny "empty slots remaining" pill — bottom-right of chassis */}
      {(wEmpty + aEmpty > 0) && (
        <div
          className="absolute -bottom-2 right-0 rounded-sm px-1 py-px text-[8px]"
          style={{
            background: CLANK.panelDeeper,
            color: CLANK.inkFaint,
            fontFamily: MONO,
            letterSpacing: '0.08em',
            border: `1px solid ${CLANK.steelLight}`,
          }}
          title={`${wEmpty} weapon slot(s) and ${aEmpty} add-on slot(s) open`}
        >
          {wEmpty}W·{aEmpty}A
        </div>
      )}
    </>
  );
}

function AttachedPartChip({ part }: { part: ClankersCard }) {
  const tint = CARD_TYPE_TINT[part.card_type];
  return (
    <div
      className="rounded-sm border px-1.5 py-1"
      style={{
        width: 78,
        background: CLANK.panelDark,
        borderColor: tint,
        fontFamily: MONO,
        boxShadow: `0 0 4px ${tint}33`,
        opacity: part.tapped ? 0.55 : 1,
      }}
      title={part.text}
    >
      <div
        className="truncate text-[10px] font-semibold"
        style={{ color: CLANK.ink }}
      >
        {part.name}
      </div>
      <div
        className="flex items-center justify-between gap-1 text-[9px]"
        style={{ color: tint }}
      >
        <span>{CARD_TYPE_LABEL[part.card_type]}</span>
        <span className="tabular-nums">
          {(part.power_bonus ?? 0) !== 0 && (
            <span title="power bonus">+{part.power_bonus}P</span>
          )}
          {(part.integrity_bonus ?? 0) !== 0 && (
            <span title="integrity bonus" style={{ marginLeft: 3 }}>
              +{part.integrity_bonus}I
            </span>
          )}
        </span>
      </div>
    </div>
  );
}

/** A part that isn't attached — sits on the floor as a 1/1. */
function SoloPartCard({ part }: { part: ClankersCard }) {
  const tint = CARD_TYPE_TINT[part.card_type];
  return (
    <div
      className="relative flex flex-col items-stretch gap-1 rounded-md border p-2"
      style={{
        width: 110,
        background: CLANK.panelDark,
        borderColor: tint,
        fontFamily: MONO,
        boxShadow: `0 0 8px ${tint}44, inset 0 0 16px ${tint}10`,
      }}
      title={part.text + ' (solo — 1/1)'}
    >
      <div
        className="absolute -top-2 left-2 rounded-sm border px-1 py-px text-[8px] uppercase"
        style={{
          background: CLANK.panelDeeper,
          borderColor: tint,
          color: tint,
          letterSpacing: '0.16em',
        }}
      >
        solo · {CARD_TYPE_LABEL[part.card_type].toLowerCase()}
      </div>
      <div className="mt-1 truncate text-xs font-semibold" style={{ color: CLANK.ink }}>
        {part.name}
      </div>
      <div className="flex items-center justify-between text-[10px]" style={{ color: tint }}>
        <span title="solo stat floor">1/1</span>
        <span className="tabular-nums">
          {(part.power_bonus ?? 0) > 0 && <span>+{part.power_bonus}P*</span>}
        </span>
      </div>
      <div
        className="text-[9px] italic"
        style={{ color: CLANK.inkFaint, fontFamily: UI_SANS }}
      >
        *bonus only when attached
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Structures row — smaller frames, up to 3
// ---------------------------------------------------------------------------

function StructuresRow({
  structures,
  seat: _seat,
}: {
  structures: ClankersCard[];
  seat: ClankersSeat;
}) {
  return (
    <div
      className="rounded-sm border px-2 pb-2 pt-1.5"
      style={{
        borderColor: CLANK.steelLight,
        background: 'rgba(192, 132, 252, 0.05)',
        minHeight: 56,
      }}
      aria-label="Structures"
    >
      <div
        className="mb-1 text-[10px] uppercase"
        style={{ color: CLANK.inkFaint, fontFamily: MONO, letterSpacing: '0.22em' }}
      >
        Structures · {structures.length}/3
      </div>
      <div className="flex gap-2">
        {structures.length === 0 ? (
          <div
            className="text-[10px] italic"
            style={{ color: CLANK.inkFaint, fontFamily: MONO }}
          >
            // no fixtures installed
          </div>
        ) : (
          structures.map((s) => <StructureChip key={s.id} structure={s} />)
        )}
      </div>
    </div>
  );
}

function StructureChip({ structure }: { structure: ClankersCard }) {
  const tint = CARD_TYPE_TINT.CLANKERS_STRUCTURE;
  return (
    <div
      className="rounded-sm border px-2 py-1"
      style={{
        background: CLANK.panelDark,
        borderColor: tint,
        fontFamily: MONO,
        minWidth: 130,
      }}
      title={structure.text}
    >
      <div className="flex items-center justify-between gap-2 text-[10px]" style={{ color: tint }}>
        <span className="uppercase" style={{ letterSpacing: '0.18em' }}>Structure</span>
        <ComputeCostChip cost={structure.compute_cost} small />
      </div>
      <div className="text-xs font-semibold" style={{ color: CLANK.ink }}>
        {structure.name}
      </div>
      {structure.text && (
        <div
          className="mt-0.5 text-[9px] italic leading-tight"
          style={{ color: CLANK.inkDim, fontFamily: UI_SANS }}
        >
          {structure.text}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Pile stacks (library, scrap heap) — visual pile of cards
// ---------------------------------------------------------------------------

function PileStack({ label, count, color }: { label: string; count: number; color: string }) {
  return (
    <div
      className="relative flex flex-col items-center"
      title={`${label}: ${count}`}
    >
      <div className="relative" style={{ width: 56, height: 78 }}>
        {/* Stacked rectangles to imply depth */}
        {[0, 1, 2].map((i) => (
          <div
            key={i}
            style={{
              position: 'absolute',
              inset: 0,
              transform: `translate(${i * 1.5}px, ${i * 1.5}px)`,
              background: 'repeating-linear-gradient(45deg, #2a3340 0 4px, #1a2230 4px 8px)',
              border: `1px solid ${color}`,
              borderRadius: 4,
              boxShadow: i === 0 ? `0 0 6px ${color}33` : 'none',
              opacity: count === 0 ? 0.3 : 1,
            }}
          />
        ))}
        <div
          className="absolute inset-0 flex items-center justify-center text-base font-bold tabular-nums"
          style={{
            color: count === 0 ? CLANK.inkFaint : CLANK.ink,
            textShadow: count > 0 ? `0 0 6px ${color}88` : 'none',
            fontFamily: MONO,
          }}
        >
          {count}
        </div>
      </div>
      <div
        className="mt-1 text-[9px] uppercase"
        style={{
          color: color,
          letterSpacing: '0.16em',
          fontFamily: MONO,
        }}
      >
        {label}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Hand views
// ---------------------------------------------------------------------------

function MyHand({
  cards,
  computePool,
  phase,
  isActive,
  onAction,
}: {
  cards: ClankersCard[];
  computePool: number;
  phase: ClankersPhase;
  isActive: boolean;
  onAction: (a: ClankersAction) => void;
}) {
  const playable = isActive && (phase === 'assemble' || phase === 'reassemble');
  const inspector = useCardInspector();
  const openInspector = (card: ClankersCard, affordable: boolean) => {
    const enabled = playable && affordable;
    const stats =
      card.card_type === 'CLANKERS_CHASSIS'
        ? `${card.power ?? 0}/${card.integrity ?? 0}`
        : card.card_type === 'CLANKERS_WEAPON'
        ? `+${card.power_bonus ?? 0} power`
        : card.card_type === 'CLANKERS_ADD_ON'
        ? `+${card.power_bonus ?? 0}/+${card.integrity_bonus ?? 0}`
        : undefined;
    inspector.open(
      {
        id: card.id,
        name: card.name,
        text: card.text,
        cost: String(card.compute_cost),
        subtitle: cardKindLabel(card.card_type),
        stats,
        engine: 'clankers',
      },
      [
        {
          label: 'Play',
          variant: 'primary',
          disabled: !enabled,
          disabledReason: !playable
            ? 'Not your phase to play'
            : !affordable
            ? `Costs ${card.compute_cost} · you have ${computePool}`
            : undefined,
          onClick: () => playFromHand(card, onAction),
        },
      ],
    );
  };
  return (
    <div className="flex flex-col gap-1.5">
      <div
        className="flex items-center justify-between text-[10px] uppercase"
        style={{ color: CLANK.inkFaint, fontFamily: MONO, letterSpacing: '0.22em' }}
      >
        <span>Your hand · {cards.length}/7 floor</span>
        <span>
          {playable
            ? 'tap a card to inspect, then Play'
            : 'tap a card to inspect'}
        </span>
      </div>
      <div className="flex flex-wrap gap-2">
        {cards.map((card) => {
          const affordable = card.compute_cost <= computePool;
          const enabled = playable && affordable;
          return (
            <button
              key={card.id}
              type="button"
              draggable={enabled}
              onDragStart={(e) => {
                if (!enabled) {
                  e.preventDefault();
                  return;
                }
                e.dataTransfer.effectAllowed = 'move';
                e.dataTransfer.setData('application/x-clankers-card', card.id);
                e.dataTransfer.setData('text/plain', card.name);
              }}
              onClick={() => openInspector(card, affordable)}
              className="group transition-transform"
              style={{
                cursor: enabled ? 'grab' : 'pointer',
                opacity: enabled ? 1 : 0.55,
              }}
            >
              <span
                className="inline-block transition-transform group-hover:-translate-y-1 group-focus:-translate-y-1"
                style={{ display: 'inline-block' }}
              >
                <CardFrame card={card} variant="hand" tint={CARD_TYPE_TINT[card.card_type]} />
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

function cardKindLabel(t: ClankersCard['card_type']): string {
  switch (t) {
    case 'CLANKERS_CHASSIS': return 'Chassis';
    case 'CLANKERS_WEAPON': return 'Weapon';
    case 'CLANKERS_ADD_ON': return 'Add-On';
    case 'CLANKERS_TRANSIENT': return 'Transient';
    case 'CLANKERS_STRUCTURE': return 'Structure';
    case 'CLANKERS_CORE': return 'Core';
    default: return 'Card';
  }
}

function playFromHand(
  card: ClankersCard,
  onAction: (a: ClankersAction) => void,
) {
  switch (card.card_type) {
    case 'CLANKERS_CHASSIS':
      return onAction({ type: 'CLANKERS_PLAY_CHASSIS', cardId: card.id });
    case 'CLANKERS_WEAPON':
    case 'CLANKERS_ADD_ON':
      return onAction({ type: 'CLANKERS_PLAY_PART', cardId: card.id });
    case 'CLANKERS_TRANSIENT':
      return onAction({ type: 'CLANKERS_PLAY_TRANSIENT', cardId: card.id });
    case 'CLANKERS_STRUCTURE':
      return onAction({ type: 'CLANKERS_PLAY_STRUCTURE', cardId: card.id });
    default:
      return;
  }
}

function OpponentHand({ count }: { count: number }) {
  return (
    <div className="flex flex-col gap-1.5">
      <div
        className="text-[10px] uppercase"
        style={{ color: CLANK.inkFaint, fontFamily: MONO, letterSpacing: '0.22em' }}
      >
        Opponent hand · {count}/7 floor
      </div>
      <div className="flex gap-1">
        {Array.from({ length: count }).map((_, i) => (
          <CardBack key={i} index={i} count={count} />
        ))}
      </div>
    </div>
  );
}

function CardBack({ index, count }: { index: number; count: number }) {
  const rot = (index - (count - 1) / 2) * 1.5;
  return (
    <div
      style={{
        width: 36,
        height: 50,
        background: `repeating-linear-gradient(45deg, #2a3340 0 4px, #1a2230 4px 8px)`,
        border: `1px solid ${CLANK.steelLight}`,
        borderRadius: 4,
        transform: `rotate(${rot}deg)`,
        boxShadow: '0 1px 4px rgba(0,0,0,0.4)',
      }}
      aria-hidden="true"
    />
  );
}

// ---------------------------------------------------------------------------
// CardFrame — generic card renderer for hand + assembly-floor variants
// ---------------------------------------------------------------------------

interface CardFrameProps {
  card: ClankersCard;
  variant: 'hand' | 'floor';
  tint: string;
  damageMarked?: number;
  children?: React.ReactNode;
}

function CardFrame({ card, variant, tint, damageMarked = 0, children }: CardFrameProps) {
  const sizes = {
    hand: { w: 120, h: 168, nameSize: 12, costSize: 18, statSize: 22 },
    floor: { w: 110, h: 152, nameSize: 11, costSize: 16, statSize: 20 },
  };
  const s = sizes[variant];
  const isChassis = card.card_type === 'CLANKERS_CHASSIS';
  const isPart =
    card.card_type === 'CLANKERS_WEAPON' || card.card_type === 'CLANKERS_ADD_ON';

  const cardStyle: CSSProperties = {
    width: s.w,
    height: s.h,
    background: CLANK.panelDark,
    border: `1.5px solid ${tint}`,
    borderRadius: 6,
    boxShadow: card.tapped
      ? `inset 0 0 16px rgba(0,0,0,0.5)`
      : `0 2px 8px rgba(0,0,0,0.4), 0 0 0 1px ${CLANK.panelDeeper}`,
    fontFamily: UI_SANS,
    color: CLANK.ink,
    display: 'flex',
    flexDirection: 'column',
    padding: 6,
    position: 'relative',
    overflow: 'hidden',
    opacity: card.tapped ? 0.78 : 1,
  };

  return (
    <div style={cardStyle} title={card.text}>
      {/* Top edge: name + compute cost */}
      <div className="flex items-start justify-between gap-1">
        <div
          style={{
            fontSize: s.nameSize,
            lineHeight: 1.1,
            fontWeight: 600,
            color: CLANK.ink,
            fontFamily: MONO,
            letterSpacing: '0.01em',
            flex: 1,
          }}
        >
          {card.name}
        </div>
        <ComputeCostChip cost={card.compute_cost} />
      </div>

      {/* Type chip */}
      <div className="mt-1 flex items-center gap-1">
        <span
          style={{
            fontSize: 8,
            padding: '1px 5px',
            background: tint,
            color: '#0b1220',
            textTransform: 'uppercase',
            letterSpacing: '0.16em',
            fontWeight: 700,
            fontFamily: MONO,
            borderRadius: 2,
          }}
        >
          {CARD_TYPE_LABEL[card.card_type]}
        </span>
        {card.archetype && (
          <span
            className="text-[8px] italic"
            style={{ color: CLANK.inkDim, fontFamily: MONO }}
            title={`Archetype: ${card.archetype}`}
          >
            · {card.archetype}
          </span>
        )}
      </div>

      {/* Art slot — abstract glyph per type */}
      <div
        className="my-1 flex flex-1 items-center justify-center rounded-sm"
        style={{
          background: `radial-gradient(circle at 50% 40%, ${tint}26 0%, transparent 70%)`,
        }}
      >
        <TypeGlyph type={card.card_type} tint={tint} />
      </div>

      {/* Stat line */}
      {isChassis && (
        <div className="flex items-center justify-between">
          <span
            className="font-bold tabular-nums"
            style={{
              fontSize: s.statSize,
              color: tint,
              fontFamily: MONO,
              textShadow: `0 0 6px ${tint}55`,
            }}
          >
            {card.power}/{card.integrity}
          </span>
          <span
            className="text-[9px]"
            style={{ color: CLANK.inkDim, fontFamily: MONO, letterSpacing: '0.06em' }}
            title="weapon slots / add-on slots"
          >
            {card.weapon_slots ?? 0}W·{card.add_on_slots ?? 0}A
          </span>
        </div>
      )}
      {isPart && (
        <div className="flex items-center justify-between">
          <span
            className="font-semibold tabular-nums"
            style={{
              fontSize: s.costSize,
              color: tint,
              fontFamily: MONO,
            }}
          >
            {(card.power_bonus ?? 0) > 0 && <span>+{card.power_bonus}P </span>}
            {(card.integrity_bonus ?? 0) > 0 && <span>+{card.integrity_bonus}I</span>}
            {(card.power_bonus ?? 0) === 0 && (card.integrity_bonus ?? 0) === 0 && (
              <span style={{ color: CLANK.inkDim }}>util</span>
            )}
          </span>
          {card.armor_value && (
            <span
              className="rounded-sm border px-1 text-[8px] font-bold uppercase"
              style={{
                borderColor: CLANK.circuitGreen,
                color: CLANK.circuitGreen,
                fontFamily: MONO,
                letterSpacing: '0.12em',
              }}
            >
              ARM {card.armor_value}
            </span>
          )}
        </div>
      )}

      {/* Rules text */}
      {card.text && (
        <div
          style={{
            fontSize: 9,
            fontStyle: 'italic',
            lineHeight: 1.25,
            color: CLANK.inkDim,
            maxHeight: variant === 'hand' ? 30 : 24,
            overflow: 'hidden',
            marginTop: 2,
          }}
        >
          {card.text}
        </div>
      )}

      {/* Damage marker — for chassis only */}
      {damageMarked > 0 && (
        <div
          className="absolute right-1 top-1 rounded-sm px-1 text-[9px] font-bold tabular-nums"
          style={{
            background: CLANK.coreRed,
            color: '#0b1220',
            fontFamily: MONO,
          }}
          title={`${damageMarked} damage marked`}
        >
          -{damageMarked}
        </div>
      )}

      {/* Tapped indicator */}
      {card.tapped && (
        <div
          className="absolute bottom-1 right-1 text-[8px] uppercase"
          style={{
            color: CLANK.inkFaint,
            fontFamily: MONO,
            letterSpacing: '0.16em',
          }}
        >
          exhausted
        </div>
      )}

      {/* Children — used for SlotIndicators when this is a chassis on the floor */}
      {children}
    </div>
  );
}

function ComputeCostChip({ cost, small }: { cost: number; small?: boolean }) {
  return (
    <span
      className="inline-flex items-center justify-center rounded-sm border tabular-nums"
      style={{
        width: small ? 18 : 22,
        height: small ? 18 : 22,
        fontSize: small ? 10 : 12,
        fontWeight: 700,
        color: CLANK.coolantBlue,
        background: CLANK.coolantBlue + '15',
        borderColor: CLANK.coolantBlue,
        fontFamily: MONO,
      }}
      title={`Compute cost: ${cost}`}
    >
      {cost}
    </span>
  );
}

// ---------------------------------------------------------------------------
// TypeGlyph — abstract pictogram per card type
// ---------------------------------------------------------------------------

function TypeGlyph({ type, tint }: { type: ClankersCardType; tint: string }) {
  switch (type) {
    case 'CLANKERS_CHASSIS':
      return <ChassisGlyph color={tint} />;
    case 'CLANKERS_WEAPON':
      return <WeaponGlyph color={tint} />;
    case 'CLANKERS_ADD_ON':
      return <AddOnGlyph color={tint} />;
    case 'CLANKERS_TRANSIENT':
      return <TransientGlyph color={tint} />;
    case 'CLANKERS_STRUCTURE':
      return <StructureGlyph color={tint} />;
    case 'CLANKERS_CORE':
      return <CoreGlyph color={tint} />;
  }
}

function ChassisGlyph({ color }: { color: string }) {
  // A simple robot torso with two articulation joints
  return (
    <svg width="40" height="40" viewBox="0 0 40 40" aria-hidden="true">
      <rect x="10" y="10" width="20" height="22" rx="2" fill="none" stroke={color} strokeWidth="1.6" />
      <rect x="14" y="14" width="12" height="6" fill={color} opacity="0.4" />
      <circle cx="14" cy="26" r="1.5" fill={color} />
      <circle cx="26" cy="26" r="1.5" fill={color} />
      <line x1="20" y1="6" x2="20" y2="10" stroke={color} strokeWidth="1.6" />
      <circle cx="20" cy="5" r="1" fill={color} />
    </svg>
  );
}

function WeaponGlyph({ color }: { color: string }) {
  // A barrel + grip — abstract gun shape
  return (
    <svg width="40" height="40" viewBox="0 0 40 40" aria-hidden="true">
      <rect x="6" y="18" width="22" height="6" fill={color} opacity="0.7" />
      <rect x="22" y="22" width="6" height="10" fill={color} opacity="0.9" />
      <rect x="28" y="18" width="6" height="6" fill="none" stroke={color} strokeWidth="1.6" />
      <line x1="6" y1="15" x2="36" y2="15" stroke={color} strokeWidth="0.6" strokeDasharray="2 2" opacity="0.4" />
    </svg>
  );
}

function AddOnGlyph({ color }: { color: string }) {
  // A shield / plate icon
  return (
    <svg width="40" height="40" viewBox="0 0 40 40" aria-hidden="true">
      <path
        d="M20 6 L30 10 L30 22 Q30 30 20 34 Q10 30 10 22 L10 10 Z"
        fill={color}
        opacity="0.3"
        stroke={color}
        strokeWidth="1.6"
        strokeLinejoin="round"
      />
      <path
        d="M16 18 L20 22 L26 14"
        fill="none"
        stroke={color}
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function TransientGlyph({ color }: { color: string }) {
  // A lightning / spark
  return (
    <svg width="40" height="40" viewBox="0 0 40 40" aria-hidden="true">
      <path
        d="M22 6 L12 22 L18 22 L16 34 L28 16 L22 16 Z"
        fill={color}
        opacity="0.85"
        stroke={color}
        strokeWidth="0.6"
      />
    </svg>
  );
}

function StructureGlyph({ color }: { color: string }) {
  // An anvil / workbench shape
  return (
    <svg width="40" height="40" viewBox="0 0 40 40" aria-hidden="true">
      <path
        d="M6 18 L34 18 L30 22 L10 22 Z"
        fill={color}
        opacity="0.7"
      />
      <rect x="14" y="22" width="12" height="6" fill={color} opacity="0.9" />
      <rect x="12" y="28" width="16" height="4" fill="none" stroke={color} strokeWidth="1.6" />
      <line x1="36" y1="14" x2="28" y2="22" stroke={color} strokeWidth="1.4" strokeLinecap="round" />
    </svg>
  );
}

function CoreGlyph({ color }: { color: string }) {
  // A processor square with arrows
  return (
    <svg width="40" height="40" viewBox="0 0 40 40" aria-hidden="true">
      <rect x="12" y="12" width="16" height="16" fill="none" stroke={color} strokeWidth="1.6" />
      <rect x="16" y="16" width="8" height="8" fill={color} opacity="0.4" />
      {[
        [20, 8, 20, 12],
        [20, 28, 20, 32],
        [8, 20, 12, 20],
        [28, 20, 32, 20],
      ].map((coords, i) => (
        <line
          key={i}
          x1={coords[0]}
          y1={coords[1]}
          x2={coords[2]}
          y2={coords[3]}
          stroke={color}
          strokeWidth="1.4"
        />
      ))}
    </svg>
  );
}

// ---------------------------------------------------------------------------
// Action prompts strip
// ---------------------------------------------------------------------------

function ActionPromptStrip({ onAction }: { onAction: (a: ClankersAction) => void }) {
  return (
    <div
      className="mt-3 flex items-center justify-end gap-2"
      style={{ fontFamily: MONO }}
    >
      <span
        className="text-[10px] uppercase"
        style={{ color: CLANK.inkFaint, letterSpacing: '0.2em' }}
      >
        actions:
      </span>
      <button
        type="button"
        onClick={() => onAction({ type: 'CLANKERS_PASS_PHASE' })}
        className="rounded-sm border px-3 py-1 text-xs font-semibold uppercase"
        style={{
          background: CLANK.panelDark,
          borderColor: CLANK.steelLight,
          color: CLANK.ink,
          letterSpacing: '0.14em',
          cursor: 'pointer',
        }}
        title="End your current phase"
      >
        pass phase
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Deathclock banner
// ---------------------------------------------------------------------------

function DeathclockBanner({
  deathclock,
}: {
  deathclock: { turn: number; next_damage: number };
}) {
  return (
    <div
      className="fixed inset-x-0 top-0 z-40 flex items-center justify-center border-b px-4 py-2"
      style={{
        background: 'rgba(239,68,68,0.12)',
        borderColor: CLANK.coreRed,
        backdropFilter: 'blur(4px)',
        animation: 'clank-deathclock-pulse 2s ease-out infinite',
      }}
      aria-live="assertive"
    >
      <span
        className="text-sm font-bold uppercase"
        style={{
          color: CLANK.coreRed,
          fontFamily: MONO,
          letterSpacing: '0.24em',
          textShadow: `0 0 8px ${CLANK.coreRed}`,
          animation: 'clank-glitch 0.4s steps(2) infinite',
        }}
      >
        ▲ CONTAINMENT FAILURE · TURN {deathclock.turn} · NEXT DAMAGE {deathclock.next_damage} ▲
      </span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Game-over overlay
// ---------------------------------------------------------------------------

function GameOverOverlay({ winner }: { winner: ClankersSeat | null }) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ background: 'rgba(0,0,0,0.7)', backdropFilter: 'blur(4px)' }}
    >
      <div
        className="rounded-md border-2 px-8 py-6 text-center"
        style={{
          background: CLANK.panelDark,
          borderColor: winner === 'me' ? CLANK.circuitGreen : CLANK.coreRed,
          maxWidth: 520,
          fontFamily: MONO,
          color: CLANK.ink,
        }}
      >
        <div
          className="text-[10px] uppercase"
          style={{ color: CLANK.inkFaint, letterSpacing: '0.32em' }}
        >
          // simulation complete
        </div>
        <div className="mt-1 text-2xl font-bold">
          {winner === 'me' ? 'workshop secured' : winner === 'opponent' ? 'workshop breached' : 'mutual containment failure'}
        </div>
        <div className="mt-2 text-sm italic" style={{ color: CLANK.inkDim }}>
          {winner === 'me'
            ? 'your core remains. it is, briefly, proud.'
            : winner === 'opponent'
              ? 'the opposing AI is the supreme intellect of the workshop.'
              : 'both AIs explode together. it is, allegedly, beautiful.'}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Deckbuilder GameModule — registered in registry.ts
// ---------------------------------------------------------------------------

const STATS_TILE_LABELS: { key: string; label: string }[] = [
  { key: 'chassis_count', label: 'Chassis' },
  { key: 'weapon_count', label: 'Weapons' },
  { key: 'add_on_count', label: 'Add-Ons' },
];

function getNum(extras: Record<string, unknown> | undefined, key: string): number {
  const v = extras?.[key];
  return typeof v === 'number' ? v : 0;
}

function ClankersStatsExtras({ stats }: { stats: DeckStats }) {
  const extras = (stats.extras ?? {}) as Record<string, number>;
  // A simple bar by card type — average compute cost per type if available,
  // otherwise just the count distribution.
  const segments = useMemo(
    () => [
      {
        key: 'chassis',
        label: 'Chassis',
        value: extras.chassis_count ?? 0,
        color: CARD_TYPE_TINT.CLANKERS_CHASSIS,
      },
      {
        key: 'weapon',
        label: 'Weapons',
        value: extras.weapon_count ?? 0,
        color: CARD_TYPE_TINT.CLANKERS_WEAPON,
      },
      {
        key: 'add_on',
        label: 'Add-Ons',
        value: extras.add_on_count ?? 0,
        color: CARD_TYPE_TINT.CLANKERS_ADD_ON,
      },
      {
        key: 'transient',
        label: 'Transients',
        value: extras.transient_count ?? 0,
        color: CARD_TYPE_TINT.CLANKERS_TRANSIENT,
      },
      {
        key: 'structure',
        label: 'Structures',
        value: extras.structure_count ?? 0,
        color: CARD_TYPE_TINT.CLANKERS_STRUCTURE,
      },
    ],
    [extras],
  );

  return (
    <div className="mt-4 space-y-3">
      <StackedBar title="Robot parts distribution" segments={segments} />
      {/* Average compute cost per type — small monospace grid */}
      <div className="grid grid-cols-3 gap-2 text-xs">
        {STATS_TILE_LABELS.map(({ key, label }) => {
          const avgKey = `avg_compute_${key.replace('_count', '')}`;
          const avg = extras[avgKey];
          return (
            <div
              key={key}
              className="rounded border px-3 py-2"
              style={{
                borderColor: CLANK.steelLight,
                background: 'rgba(31,41,55,0.6)',
                color: CLANK.ink,
                fontFamily: MONO,
              }}
            >
              <div className="text-[10px] uppercase" style={{ color: CLANK.inkFaint, letterSpacing: '0.16em' }}>
                {label}
              </div>
              <div className="mt-1 flex items-baseline justify-between">
                <span className="text-base font-semibold tabular-nums">
                  {extras[key] ?? 0}
                </span>
                {typeof avg === 'number' && (
                  <span className="text-[10px]" style={{ color: CLANK.coolantBlue }}>
                    avg {avg.toFixed(1)} comp
                  </span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export const clankers: GameModule = {
  id: 'clankers',
  label: 'Clankers',
  showColors: false,
  costLabel: 'Compute',
  typeFilters: [
    'CLANKERS_CHASSIS',
    'CLANKERS_WEAPON',
    'CLANKERS_ADD_ON',
    'CLANKERS_TRANSIENT',
    'CLANKERS_STRUCTURE',
    'CLANKERS_CORE',
  ],
  formatType: (t) => {
    // Strip CLANKERS_ prefix and Title-Case (preserving the existing
    // hyphen-y casing: ADD_ON → Add_On per the brief).
    const stripped = t.replace(/^CLANKERS_/, '');
    return stripped.charAt(0) + stripped.slice(1).toLowerCase();
  },
  tiles: (stats) => {
    if (!stats) return [];
    const extras = (stats.extras ?? {}) as Record<string, unknown>;
    return [
      { label: 'Chassis', value: getNum(extras, 'chassis_count') },
      { label: 'Weapons', value: getNum(extras, 'weapon_count') },
      { label: 'Add-Ons', value: getNum(extras, 'add_on_count') },
    ];
  },
  StatsExtras: ClankersStatsExtras,
};
