/**
 * Depths — submarine-fleet engine.
 *
 * Two exports:
 *   1. `depths` — deckbuilder GameModule entry (registered in registry.ts)
 *   2. `DepthsGameBoard` — the in-match board frame, mirroring MCGameBoard
 *      in layout density and styling vocabulary but laid out around the
 *      5-band Depth Ladder (SURFACE / PERISCOPE / MID / DEEP / CRUSH)
 *      instead of the 3x3 build grid.
 *
 * Visual language:
 *   - Dark abyss palette, slate-950 base. Each depth band is a horizontal
 *     row tinted from pale blue at SURFACE down to near-black at CRUSH.
 *   - Cyan/teal sonar pings. Red/orange torpedo accents. Detection state
 *     drops Vessel opacity to ~40% with a dashed cyan ghost border when
 *     undetected; solid steel border when detected.
 *   - The Flagship sits permanently in its owner's PERISCOPE row with a
 *     gold-chrome outline and a horizontal hull bar (since it doubles as
 *     life total).
 *   - Resource counters show TC (torpedo) and SC (sonar) as `5/7` style
 *     pill counters in distinct red and cyan.
 */

import { useEffect, useMemo, useState } from 'react';
import type { CardData, GameState, PlayerData } from '../types';
import type { GameModule } from './types';
import type { DeckStats } from '../types/deckbuilder';
import { defaultFormatType } from './types';
import { StackedBar } from './StackedBar';
import { getDepthsArtPaths } from '../utils/cardArt';

// -- Depth ladder ----------------------------------------------------------

export type DepthBand = 'SURFACE' | 'PERISCOPE' | 'MID' | 'DEEP' | 'CRUSH';

const DEPTH_BANDS: DepthBand[] = ['SURFACE', 'PERISCOPE', 'MID', 'DEEP', 'CRUSH'];

// Top-down tint palette: surface is sun-lit, crush is the abyss.
const BAND_BG: Record<DepthBand, string> = {
  SURFACE: 'linear-gradient(180deg,#1e3a5f 0%, #16334f 100%)',
  PERISCOPE: 'linear-gradient(180deg,#152d49 0%, #102339 100%)',
  MID: 'linear-gradient(180deg,#0e1f33 0%, #0a172a 100%)',
  DEEP: 'linear-gradient(180deg,#08111f 0%, #050b15 100%)',
  CRUSH: 'linear-gradient(180deg,#03070d 0%, #000204 100%)',
};

// Per-band sonar-ping accent (used for the row label and band markers).
const BAND_ACCENT: Record<DepthBand, string> = {
  SURFACE: '#7dd3fc',    // sky-300
  PERISCOPE: '#22d3ee',  // cyan-400
  MID: '#06b6d4',        // cyan-500
  DEEP: '#0891b2',       // cyan-600
  CRUSH: '#155e75',      // cyan-800
};

// Detection cost-difficulty hint shown on each band header.
const DETECT_DIFFICULTY: Record<DepthBand, number> = {
  SURFACE: 0,
  PERISCOPE: 0,
  MID: 1,
  DEEP: 2,
  CRUSH: 3,
};

const MINE_TYPES = new Set(['DEPTHS_MINE']);

function isMine(c: CardData) {
  return c.types.some((t) => MINE_TYPES.has(t));
}

function bandOf(c: CardData): DepthBand {
  const raw = (c.depth_band || 'PERISCOPE').toString().toUpperCase();
  return (DEPTH_BANDS as string[]).includes(raw) ? (raw as DepthBand) : 'PERISCOPE';
}

// -- Card art ------------------------------------------------------------

/**
 * Sonar-themed fallback glyphs. Each variant matches a card category so the
 * empty art slot still reads as a Depths card and not a generic placeholder.
 *
 * Vessels: submarine silhouette.
 * Mines: pressure-gauge diamond.
 * Doctrines: sonar ping.
 * Actions / unknown: stylised wave.
 */
const DEPTHS_FALLBACK_GLYPH: Record<string, string> = {
  vessel: '⌖',     // crosshair / sub silhouette read
  flagship: '★',
  mine: '◇',
  doctrine: '⌬',   // sonar ping
  action: '∿',
  unknown: '∿',
};

type DepthsArtVariant = keyof typeof DEPTHS_FALLBACK_GLYPH;

function DepthsArt({
  cardName,
  imageUrl,
  variant = 'unknown',
  className,
}: {
  cardName: string;
  imageUrl?: string | null;
  variant?: DepthsArtVariant;
  className?: string;
}) {
  const paths = useMemo(() => {
    const out: string[] = [];
    if (imageUrl) out.push(imageUrl);
    out.push(...getDepthsArtPaths(cardName));
    return [...new Set(out)];
  }, [cardName, imageUrl]);

  const [idx, setIdx] = useState(0);
  const [loaded, setLoaded] = useState(false);
  const [failed, setFailed] = useState(false);

  // Reset attempt counters when the card name changes (re-render on swap).
  useEffect(() => {
    setIdx(0);
    setLoaded(false);
    setFailed(false);
  }, [cardName, imageUrl]);

  const onError = () => {
    if (idx < paths.length - 1) {
      setIdx((i) => i + 1);
    } else {
      setFailed(true);
    }
  };

  const glyph = DEPTHS_FALLBACK_GLYPH[variant] || DEPTHS_FALLBACK_GLYPH.unknown;

  if (failed || paths.length === 0) {
    return (
      <div
        aria-hidden
        className={`flex items-center justify-center bg-gradient-to-b from-cyan-950/40 to-slate-950/80 text-cyan-500/60 ${className ?? ''}`}
      >
        <span className="text-lg leading-none">{glyph}</span>
      </div>
    );
  }

  return (
    <div className={`relative overflow-hidden bg-gradient-to-b from-cyan-950/40 to-slate-950/80 ${className ?? ''}`}>
      {!loaded && (
        <div className="absolute inset-0 flex items-center justify-center text-cyan-700/60">
          <span className="text-lg leading-none opacity-40 animate-pulse">{glyph}</span>
        </div>
      )}
      <img
        src={paths[idx]}
        alt={cardName}
        loading="lazy"
        decoding="async"
        onLoad={() => setLoaded(true)}
        onError={onError}
        className={`h-full w-full object-cover object-center ${loaded ? 'opacity-100' : 'opacity-0'} transition-opacity duration-150`}
      />
    </div>
  );
}

function variantForCard(card: CardData, isFlagship: boolean): DepthsArtVariant {
  if (isFlagship) return 'flagship';
  if (card.types.some((t) => t === 'DEPTHS_MINE')) return 'mine';
  if (card.types.some((t) => t === 'ENCHANTMENT' || t === 'DEPTHS_DOCTRINE')) return 'doctrine';
  if (
    card.types.some(
      (t) =>
        t === 'DEPTHS_VESSEL' ||
        t === 'CREATURE' ||
        t === 'DEPTHS_CREW' ||
        t === 'DEPTHS_WEAPON',
    )
  ) {
    return 'vessel';
  }
  if (card.types.some((t) => t === 'INSTANT' || t === 'SORCERY')) return 'action';
  return 'unknown';
}

// -- Tiny presentational atoms --------------------------------------------

function ChargePill({
  label,
  current,
  max,
  fg,
  bg,
}: {
  label: string;
  current: number;
  max: number;
  fg: string;
  bg: string;
}) {
  return (
    <div
      className="flex items-center gap-1.5 border px-2 py-1 text-[11px] font-bold uppercase tracking-wider"
      style={{ borderColor: fg, color: fg, background: bg }}
    >
      <span>{label}</span>
      <span className="text-base">{current}</span>
      <span className="opacity-60">/ {max}</span>
    </div>
  );
}

function HullBar({ damage, hull, compact = false }: { damage: number; hull: number; compact?: boolean }) {
  const pct = hull > 0 ? Math.max(0, Math.min(100, ((hull - damage) / hull) * 100)) : 0;
  const tone = pct > 60 ? '#22c55e' : pct > 30 ? '#facc15' : '#ef4444';
  return (
    <div className={`w-full border border-slate-700 bg-black/40 ${compact ? 'h-1' : 'h-1.5'}`}>
      <div className="h-full" style={{ width: `${pct}%`, background: tone }} />
    </div>
  );
}

function Cost({ cost }: { cost?: { tc?: number; sc?: number } }) {
  const tc = cost?.tc ?? 0;
  const sc = cost?.sc ?? 0;
  if (!tc && !sc) return <span className="text-emerald-200">Free</span>;
  return (
    <span className="flex flex-wrap gap-1">
      {tc > 0 && (
        <span className="rounded-sm border border-red-500/60 bg-red-950/60 px-1.5 py-0.5 text-red-200">
          {tc}T
        </span>
      )}
      {sc > 0 && (
        <span className="rounded-sm border border-cyan-500/60 bg-cyan-950/60 px-1.5 py-0.5 text-cyan-200">
          {sc}S
        </span>
      )}
    </span>
  );
}

// -- Vessel / Mine tile ---------------------------------------------------

function VesselTile({
  card,
  ownerIsMe,
  selected = false,
  selectable = false,
  isFlagship = false,
  onClick,
}: {
  card: CardData;
  ownerIsMe: boolean;
  selected?: boolean;
  selectable?: boolean;
  isFlagship?: boolean;
  onClick?: () => void;
}) {
  const detected = !!card.detected;
  const tapped = card.tapped || card.mc_exhausted;
  // Detection rule: opponent's undetected vessels render ghosted with a
  // dashed cyan outline. Own vessels are always solid (you always know
  // where your own subs are).
  const ghosted = !ownerIsMe && !detected && !isFlagship;

  const flagshipFrame = isFlagship
    ? 'border-amber-300 shadow-[0_0_0_2px_rgba(251,191,36,0.25)]'
    : '';
  const baseBorder = ghosted
    ? 'border-cyan-500/40 border-dashed'
    : ownerIsMe
      ? 'border-sky-700'
      : 'border-red-700';
  const selectedFrame = selected ? 'border-yellow-300' : '';
  const opacity = ghosted ? 'opacity-40' : tapped ? 'opacity-70' : '';

  const hull = card.hull ?? card.toughness ?? 0;
  const power = card.power ?? 0;
  const damage = card.damage ?? 0;

  const Tag = onClick ? 'button' : 'div';

  return (
    <Tag
      onClick={onClick}
      disabled={onClick ? !selectable : undefined}
      className={`group relative w-full text-left border-2 bg-slate-950/90 px-1.5 py-1 transition shadow-[inset_0_0_18px_rgba(8,47,73,0.6)] ${baseBorder} ${selectedFrame} ${flagshipFrame} ${opacity} ${selectable ? 'hover:border-cyan-200 cursor-pointer' : ''}`}
      title={`${card.name} — ${bandOf(card)}${detected ? ' · detected' : ''}`}
    >
      <div className="flex items-start justify-between gap-1">
        <div className="min-w-0 text-[11px] font-bold leading-tight text-slate-100">
          {isFlagship && <span className="mr-1 text-amber-300">{'★'}</span>}
          <span className="truncate">{card.name}</span>
        </div>
        <div className="shrink-0 rounded-sm bg-black/70 px-1 text-[10px] font-bold text-amber-200 border border-amber-500/40">
          {power}/{hull}
        </div>
      </div>
      {!ghosted && (
        <DepthsArt
          cardName={card.name}
          imageUrl={card.image_url}
          variant={variantForCard(card, isFlagship)}
          className={`mt-1 ${isFlagship ? 'h-12' : 'h-10'} border border-cyan-900/50`}
        />
      )}
      {hull > 0 && (
        <div className="mt-1">
          <HullBar damage={damage} hull={hull} compact={!isFlagship} />
        </div>
      )}
      <div className="mt-1 flex items-center justify-between gap-1 text-[9px] uppercase tracking-wide">
        <span className="text-cyan-300/80">{bandOf(card).slice(0, 4)}</span>
        {tapped && <span className="text-amber-400">FIRED</span>}
        {!ownerIsMe && (detected ? (
          <span className="text-rose-300">PINGED</span>
        ) : (
          <span className="text-cyan-400/70">SILENT</span>
        ))}
      </div>
    </Tag>
  );
}

function MineTile({ card, ownerIsMe }: { card: CardData; ownerIsMe: boolean }) {
  return (
    <div
      className={`flex h-7 items-center gap-1 border px-1.5 text-[10px] font-bold uppercase tracking-wide ${
        ownerIsMe
          ? 'border-amber-700/70 bg-amber-950/40 text-amber-200'
          : 'border-rose-700/70 bg-rose-950/40 text-rose-200'
      }`}
      title={`${card.name} (Mine @ ${bandOf(card)})`}
    >
      <span aria-hidden>{'◇'}</span>
      <span className="truncate">{card.name}</span>
    </div>
  );
}

// -- Depth ladder row -----------------------------------------------------

function DepthRow({
  band,
  myVessels,
  oppVessels,
  myMines,
  oppMines,
  myFlagship,
  oppFlagship,
  selectedAttackerId,
  selectedTargetId,
  detectMode,
  onClickOppVessel,
  onClickOppFlagship,
  onClickMyVessel,
}: {
  band: DepthBand;
  myVessels: CardData[];
  oppVessels: CardData[];
  myMines: CardData[];
  oppMines: CardData[];
  myFlagship: CardData | null;
  oppFlagship: CardData | null;
  selectedAttackerId: string | null;
  selectedTargetId: string | null;
  detectMode: boolean;
  onClickOppVessel: (card: CardData) => void;
  onClickOppFlagship: () => void;
  onClickMyVessel: (card: CardData) => void;
}) {
  const accent = BAND_ACCENT[band];
  const showOppFlagship = oppFlagship && bandOf(oppFlagship) === band;
  const showMyFlagship = myFlagship && bandOf(myFlagship) === band;

  return (
    <div
      className="grid grid-cols-[88px_1fr] gap-2 border-y border-cyan-900/30"
      style={{ background: BAND_BG[band] }}
    >
      <div
        className="flex flex-col items-start justify-center px-2 py-2"
        style={{ borderRight: `1px solid ${accent}33` }}
      >
        <div className="text-[10px] uppercase tracking-[0.18em]" style={{ color: accent }}>
          {band}
        </div>
        <div className="mt-0.5 text-[9px] uppercase text-slate-500 tracking-wide">
          ping +{DETECT_DIFFICULTY[band]}S
        </div>
      </div>
      <div className="flex flex-col gap-1 py-1.5 pr-1">
        {/* Opponent half (top of band) */}
        <div className="grid grid-cols-[1fr_auto] items-center gap-2">
          <div className="flex flex-wrap gap-1.5">
            {showOppFlagship && (
              <div className="min-w-[120px] max-w-[160px]">
                <VesselTile
                  card={oppFlagship!}
                  ownerIsMe={false}
                  isFlagship
                  selectable={!!selectedAttackerId}
                  selected={selectedTargetId === oppFlagship!.id}
                  onClick={onClickOppFlagship}
                />
              </div>
            )}
            {oppVessels.map((v) => (
              <div key={v.id} className="min-w-[112px] max-w-[140px]">
                <VesselTile
                  card={v}
                  ownerIsMe={false}
                  selectable={!!selectedAttackerId || detectMode}
                  selected={selectedTargetId === v.id}
                  onClick={() => onClickOppVessel(v)}
                />
              </div>
            ))}
            {!showOppFlagship && oppVessels.length === 0 && (
              <div className="text-[10px] uppercase tracking-wider text-slate-600">
                {' '}empty
              </div>
            )}
          </div>
          {oppMines.length > 0 && (
            <div className="flex flex-col items-end gap-0.5">
              {oppMines.map((m) => <MineTile key={m.id} card={m} ownerIsMe={false} />)}
            </div>
          )}
        </div>
        {/* Mirror line — subtle waterline divider */}
        <div className="h-px bg-cyan-500/10" />
        {/* Own half (bottom of band) */}
        <div className="grid grid-cols-[1fr_auto] items-center gap-2">
          <div className="flex flex-wrap gap-1.5">
            {showMyFlagship && (
              <div className="min-w-[120px] max-w-[160px]">
                <VesselTile
                  card={myFlagship!}
                  ownerIsMe
                  isFlagship
                  selected={selectedAttackerId === myFlagship!.id}
                />
              </div>
            )}
            {myVessels.map((v) => (
              <div key={v.id} className="min-w-[112px] max-w-[140px]">
                <VesselTile
                  card={v}
                  ownerIsMe
                  selectable={!v.tapped && !v.summoning_sickness}
                  selected={selectedAttackerId === v.id}
                  onClick={() => onClickMyVessel(v)}
                />
              </div>
            ))}
            {!showMyFlagship && myVessels.length === 0 && (
              <div className="text-[10px] uppercase tracking-wider text-slate-600">
                {' '}empty
              </div>
            )}
          </div>
          {myMines.length > 0 && (
            <div className="flex flex-col items-end gap-0.5">
              {myMines.map((m) => <MineTile key={m.id} card={m} ownerIsMe />)}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// -- Combat prompt --------------------------------------------------------

interface DepthsCombatPrompt {
  phase?: string;
  attacking_player?: string;
  defending_player?: string;
  attackers?: { attacker_id: string; target_id?: string; firing_band?: string }[];
  legal_interceptors?: string[];
}

// -- Game board frame -----------------------------------------------------

export interface DepthsGameBoardProps {
  gameState: GameState;
  playerId: string;
  opponentId: string | null;
  myPlayer: PlayerData | null;
  opponentPlayer: PlayerData | null;
  myFlagship: CardData | null;
  opponentFlagship: CardData | null;
  myVessels: CardData[];
  opponentVessels: CardData[];
  myMines: CardData[];
  opponentMines: CardData[];
  isMyTurn: boolean;
  canPlayCard: (card: CardData) => boolean;
  canUseVessel: (card: CardData) => boolean;
  canIntercept: (card: CardData) => boolean;
  onPlayCard: (cardId: string, depthBand?: DepthBand) => void;
  onDive: (vesselId: string) => void;
  onSurface: (vesselId: string) => void;
  onLayMine: (cardId: string, depthBand: DepthBand) => void;
  onDeclareAttackers: (
    attackers: { attacker_id: string; target_id?: string; firing_band?: string }[],
  ) => void;
  onDetect: (targets: string[]) => void;
  onDeclareInterceptors: (
    interceptors: { attacker_id: string; interceptor_id: string }[],
  ) => void;
  onActivateAbility: (sourceId: string, abilityId?: string) => void;
  onEndTurn: () => void;
}

export function DepthsGameBoard({
  gameState,
  playerId,
  opponentId,
  myPlayer,
  opponentPlayer,
  myFlagship,
  opponentFlagship,
  myVessels,
  opponentVessels,
  myMines,
  opponentMines,
  isMyTurn,
  canPlayCard,
  canUseVessel,
  canIntercept,
  onPlayCard,
  onDive,
  onSurface,
  onLayMine,
  onDeclareAttackers,
  onDetect,
  onDeclareInterceptors,
  onEndTurn,
}: DepthsGameBoardProps) {
  const [selectedAttackerId, setSelectedAttackerId] = useState<string | null>(null);
  const [pendingMineCardId, setPendingMineCardId] = useState<string | null>(null);
  const [detectMode, setDetectMode] = useState(false);
  const [pendingDetections, setPendingDetections] = useState<string[]>([]);
  const [interceptorAssignments, setInterceptorAssignments] = useState<Record<string, string>>({});

  // Combat prompt — depths uses the same shape Minecraft does for blockers,
  // but with detection-resolution and interceptor sub-steps.
  const combatPrompt = (gameState.depths_combat || {}) as DepthsCombatPrompt;
  const pendingAttacks = combatPrompt.attackers || [];
  const isInterceptor = combatPrompt.phase === 'declare_interceptors' && combatPrompt.defending_player === playerId;
  const isDetectionWindow = combatPrompt.phase === 'detection_resolution' && combatPrompt.defending_player === playerId;
  const attackKey = pendingAttacks.map((a) => a.attacker_id).join('|');

  useEffect(() => {
    setInterceptorAssignments({});
    if (!isDetectionWindow) setPendingDetections([]);
  }, [isInterceptor, isDetectionWindow, attackKey]);

  // Group vessels + mines by band for fast row rendering.
  const myByBand = useMemo(() => groupByBand(myVessels, myFlagship), [myVessels, myFlagship]);
  const oppByBand = useMemo(() => groupByBand(opponentVessels, opponentFlagship), [opponentVessels, opponentFlagship]);
  const myMinesByBand = useMemo(() => groupMinesByBand(myMines), [myMines]);
  const oppMinesByBand = useMemo(() => groupMinesByBand(opponentMines), [opponentMines]);

  const cardsLookup = useMemo(() => {
    const map = new Map<string, CardData>();
    for (const c of gameState.battlefield) map.set(c.id, c);
    return map;
  }, [gameState.battlefield]);

  // Hand interactions --------------------------------------------------------
  const handleHandClick = (card: CardData) => {
    if (!canPlayCard(card)) return;
    if (isMine(card)) {
      // Mines need a depth-band pick; toggle the placement prompt.
      setPendingMineCardId(pendingMineCardId === card.id ? null : card.id);
      setSelectedAttackerId(null);
      return;
    }
    onPlayCard(card.id);
  };

  // Combat interactions -----------------------------------------------------
  const handleClickMyVessel = (card: CardData) => {
    if (!canUseVessel(card) && selectedAttackerId !== card.id) return;
    if (selectedAttackerId === card.id) {
      setSelectedAttackerId(null);
      return;
    }
    setSelectedAttackerId(card.id);
  };

  const handleClickOppVessel = (card: CardData) => {
    if (detectMode) {
      if (card.detected) return;
      setPendingDetections((prev) => (
        prev.includes(card.id) ? prev.filter((id) => id !== card.id) : [...prev, card.id]
      ));
      return;
    }
    if (!selectedAttackerId) return;
    onDeclareAttackers([{ attacker_id: selectedAttackerId, target_id: card.id }]);
    setSelectedAttackerId(null);
  };

  const handleClickOppFlagship = () => {
    if (!selectedAttackerId || !opponentFlagship) return;
    onDeclareAttackers([{ attacker_id: selectedAttackerId, target_id: opponentFlagship.id }]);
    setSelectedAttackerId(null);
  };

  // Detection submit
  const submitDetections = () => {
    onDetect(pendingDetections);
    setPendingDetections([]);
    setDetectMode(false);
  };

  // Interceptor declaration
  const submitInterceptors = (assignments: Record<string, string>) => {
    const interceptors = Object.entries(assignments)
      .filter(([, blockerId]) => blockerId)
      .map(([attacker_id, interceptor_id]) => ({ attacker_id, interceptor_id }));
    onDeclareInterceptors(interceptors);
  };

  const interceptorEligibles = useMemo(() => {
    const legal = new Set(combatPrompt.legal_interceptors || []);
    return myVessels.filter((v) => canIntercept(v) && (!legal.size || legal.has(v.id)));
  }, [combatPrompt.legal_interceptors, myVessels, canIntercept]);

  // Mine placement: picks a band, then dispatches.
  const handleMineBandPick = (band: DepthBand) => {
    if (!pendingMineCardId) return;
    onLayMine(pendingMineCardId, band);
    setPendingMineCardId(null);
  };

  const tc = myPlayer?.tc ?? 0;
  const sc = myPlayer?.sc ?? 0;
  const tcMax = myPlayer?.tc_max ?? Math.max(tc, gameState.turn_number);
  const scMax = myPlayer?.sc_max ?? Math.max(sc, gameState.turn_number);
  const oppTc = opponentPlayer?.tc ?? 0;
  const oppSc = opponentPlayer?.sc ?? 0;

  const flagshipHull = myFlagship?.hull ?? myFlagship?.toughness ?? 25;
  const flagshipDamage = myFlagship?.damage ?? 0;
  const oppFlagshipHull = opponentFlagship?.hull ?? opponentFlagship?.toughness ?? 25;
  const oppFlagshipDamage = opponentFlagship?.damage ?? 0;

  return (
    <div className="min-h-screen bg-[#03070d] text-slate-100 selection:bg-cyan-700/40">
      <div className="grid min-h-screen grid-rows-[auto_1fr_auto] gap-2 p-3">
        {/* === Header bar === */}
        <header className="grid grid-cols-1 items-center gap-3 border-b border-cyan-900/40 pb-2 sm:grid-cols-[1fr_auto_1fr]">
          <div>
            <div className="text-[10px] uppercase tracking-[0.2em] text-cyan-700/80">Hostile Fleet</div>
            <div className="flex items-baseline gap-2">
              <div className="text-lg font-black text-rose-200">
                {opponentPlayer?.name || 'Opponent'}
              </div>
              <div className="text-xs text-rose-300/80">
                {opponentFlagship ? `${Math.max(0, oppFlagshipHull - oppFlagshipDamage)}/${oppFlagshipHull}` : '— / —'} HULL
              </div>
            </div>
            <div className="mt-1 flex gap-1.5">
              <ChargePill label="T" current={oppTc} max={Math.max(oppTc, gameState.turn_number)} fg="#fb7185" bg="#3f0c14" />
              <ChargePill label="S" current={oppSc} max={Math.max(oppSc, gameState.turn_number)} fg="#67e8f9" bg="#082f3f" />
              <span className="border border-slate-700 bg-black/40 px-2 py-1 text-[10px] uppercase tracking-wider text-slate-400">
                fleet {opponentVessels.length}{opponentFlagship ? ' + flag' : ''}
              </span>
            </div>
          </div>

          <div className="flex flex-col items-center gap-1 border border-cyan-700/50 bg-cyan-950/50 px-5 py-2 text-cyan-100">
            <div className="text-[9px] uppercase tracking-[0.3em] text-cyan-400">Phase</div>
            <div className="text-base font-black uppercase tracking-widest">
              {(gameState.depths_phase || gameState.phase || 'maneuver').toString()}
            </div>
            <div className="text-[10px] uppercase tracking-wider text-cyan-300/80">
              Turn {gameState.turn_number}
            </div>
          </div>

          <div className="text-right">
            <div className="text-[10px] uppercase tracking-[0.2em] text-cyan-700/80">Your Fleet</div>
            <div className="flex items-baseline justify-end gap-2">
              <div className="text-lg font-black text-emerald-200">{myPlayer?.name || 'Player'}</div>
              <div className="text-xs text-emerald-300/80">
                {myFlagship ? `${Math.max(0, flagshipHull - flagshipDamage)}/${flagshipHull}` : '— / —'} HULL
              </div>
            </div>
            <div className="mt-1 flex justify-end gap-1.5">
              <ChargePill label="T" current={tc} max={tcMax} fg="#fb923c" bg="#451a07" />
              <ChargePill label="S" current={sc} max={scMax} fg="#22d3ee" bg="#082f3f" />
              <button
                onClick={onEndTurn}
                disabled={!isMyTurn}
                className="border border-rose-700 bg-rose-900/60 px-3 py-1 text-[11px] font-black uppercase tracking-wider text-rose-100 hover:border-rose-300 disabled:opacity-40"
              >
                Surface (End)
              </button>
            </div>
          </div>
        </header>

        {/* === Main board: 3-col split === */}
        <main className="grid grid-cols-1 gap-3 overflow-y-auto xl:grid-cols-[minmax(220px,260px)_minmax(420px,1fr)_minmax(220px,260px)] xl:overflow-hidden">
          {/* Left rail: detection + ordnance summary */}
          <div className="space-y-3 overflow-y-auto">
            <section className="border border-cyan-900/50 bg-slate-950/70 p-3">
              <div className="mb-2 flex items-center justify-between">
                <div className="text-[10px] font-bold uppercase tracking-[0.2em] text-cyan-300">Sonar</div>
                <button
                  onClick={() => {
                    setDetectMode((v) => !v);
                    setSelectedAttackerId(null);
                    setPendingMineCardId(null);
                    setPendingDetections([]);
                  }}
                  className={`border px-2 py-1 text-[10px] font-bold uppercase tracking-wide ${detectMode ? 'border-cyan-300 bg-cyan-700/30 text-cyan-100' : 'border-cyan-800 bg-cyan-950/50 text-cyan-300 hover:border-cyan-400'}`}
                >
                  {detectMode ? 'Cancel' : 'Ping'}
                </button>
              </div>
              {detectMode ? (
                <div className="text-[11px] text-cyan-200/80">
                  Click any silent (ghosted) hostile Vessel to add it to the detection batch.
                  Cost paid in Sonar Charges per band difficulty.
                </div>
              ) : (
                <div className="text-[11px] text-slate-400">
                  Hostile vessels marked SILENT are untargetable until pinged.
                </div>
              )}
              {pendingDetections.length > 0 && (
                <div className="mt-2 space-y-1">
                  {pendingDetections.map((id) => {
                    const card = cardsLookup.get(id);
                    if (!card) return null;
                    const cost = 1 + DETECT_DIFFICULTY[bandOf(card)];
                    return (
                      <div key={id} className="flex justify-between border border-cyan-900 bg-black/40 px-2 py-1 text-[11px]">
                        <span className="truncate text-cyan-100">{card.name}</span>
                        <span className="text-cyan-300">{cost}S</span>
                      </div>
                    );
                  })}
                  <button
                    onClick={submitDetections}
                    className="mt-1 w-full border border-cyan-400 bg-cyan-700 px-2 py-1 text-[11px] font-black uppercase tracking-wider text-white hover:bg-cyan-600"
                  >
                    Confirm Pings ({pendingDetections.reduce((acc, id) => {
                      const c = cardsLookup.get(id);
                      return acc + (c ? 1 + DETECT_DIFFICULTY[bandOf(c)] : 0);
                    }, 0)}S)
                  </button>
                </div>
              )}
            </section>

            <section className="border border-slate-800 bg-slate-950/70 p-3">
              <div className="mb-2 text-[10px] font-bold uppercase tracking-[0.2em] text-slate-400">Selected Vessel</div>
              {selectedAttackerId ? (
                (() => {
                  const v = cardsLookup.get(selectedAttackerId);
                  if (!v) return <div className="text-[11px] text-slate-500">Lost contact.</div>;
                  return (
                    <div className="space-y-2">
                      <div className="text-sm font-bold text-slate-100">{v.name}</div>
                      <div className="text-[11px] text-slate-400">
                        {v.power ?? 0} power · {v.hull ?? v.toughness ?? 0} hull · @ {bandOf(v)}
                      </div>
                      <div className="flex flex-wrap gap-1">
                        <button
                          onClick={() => onDive(v.id)}
                          disabled={!isMyTurn || bandOf(v) === 'CRUSH'}
                          className="border border-cyan-800 bg-cyan-950/60 px-2 py-1 text-[11px] font-bold uppercase tracking-wide text-cyan-200 hover:border-cyan-300 disabled:opacity-40"
                        >
                          {'↓'} Dive (1S)
                        </button>
                        <button
                          onClick={() => onSurface(v.id)}
                          disabled={!isMyTurn || bandOf(v) === 'SURFACE'}
                          className="border border-sky-800 bg-sky-950/60 px-2 py-1 text-[11px] font-bold uppercase tracking-wide text-sky-200 hover:border-sky-300 disabled:opacity-40"
                        >
                          {'↑'} Surface
                        </button>
                      </div>
                      <div className="text-[10px] uppercase tracking-wide text-slate-500">
                        Click an enemy Vessel or the enemy Flagship to fire.
                      </div>
                    </div>
                  );
                })()
              ) : (
                <div className="text-[11px] text-slate-500">
                  Click one of your vessels in the depth ladder to pick a firing platform.
                </div>
              )}
            </section>

            {/* TODO: Stage 4 — replace this stub with a real CardDetailPanel
                once depths cards land with full text/keyword rules data. */}
            <section className="border border-slate-800 bg-slate-950/70 p-3 text-[11px] text-slate-400">
              <div className="mb-1 text-[10px] font-bold uppercase tracking-[0.2em] text-slate-500">Doctrine</div>
              <div className="text-slate-300">No active Doctrines.</div>
            </section>
          </div>

          {/* Center: depth ladder */}
          <div className="flex min-w-0 flex-col gap-2 overflow-hidden">
            {(isInterceptor || isDetectionWindow) && (
              <section className="border-2 border-rose-500 bg-rose-950/40 p-3">
                <div className="mb-2 flex items-center justify-between gap-2">
                  <div>
                    <div className="text-xs font-bold uppercase tracking-wide text-rose-200">
                      {isDetectionWindow ? 'Detection Window' : 'Declare Interceptors'}
                    </div>
                    <div className="text-[11px] text-rose-100/80">
                      {isDetectionWindow
                        ? 'Spend Sonar to ping incoming attackers, then confirm to enter blocker step.'
                        : 'Match each detected attacker with one of your ready Vessels (within 1 band). Take the hit otherwise.'}
                    </div>
                  </div>
                  {isInterceptor && (
                    <div className="flex gap-2">
                      <button
                        onClick={() => submitInterceptors(interceptorAssignments)}
                        className="bg-emerald-700 px-3 py-1 text-[11px] font-black uppercase tracking-wider text-white"
                      >
                        Confirm Intercept
                      </button>
                      <button
                        onClick={() => submitInterceptors({})}
                        className="bg-slate-800 px-3 py-1 text-[11px] font-black uppercase tracking-wider text-white"
                      >
                        Take Hit
                      </button>
                    </div>
                  )}
                </div>
                {isInterceptor && (
                  <div className="grid gap-2">
                    {pendingAttacks.map((attack) => {
                      const card = cardsLookup.get(attack.attacker_id);
                      if (!card) return null;
                      if (!card.detected) {
                        return (
                          <div key={attack.attacker_id} className="border border-rose-800 bg-black/30 p-2 text-[11px] text-rose-200">
                            <span className="font-bold">{card.name}</span> — undetected, cannot intercept.
                          </div>
                        );
                      }
                      const assignedElsewhere = new Set(
                        Object.entries(interceptorAssignments)
                          .filter(([attackerId]) => attackerId !== attack.attacker_id)
                          .map(([, vid]) => vid),
                      );
                      const target = attack.target_id === opponentId
                        ? 'Flagship'
                        : cardsLookup.get(attack.target_id || '')?.name || 'Target';
                      return (
                        <div key={attack.attacker_id} className="grid gap-2 border border-rose-800 bg-black/30 p-2 sm:grid-cols-[1fr_1fr]">
                          <div className="text-[11px]">
                            <div className="font-bold text-rose-100">{card.name}</div>
                            <div className="text-rose-300/80">{card.power ?? 0} pow @ {bandOf(card)} → {target}</div>
                          </div>
                          <select
                            value={interceptorAssignments[attack.attacker_id] || ''}
                            onChange={(e) => setInterceptorAssignments((prev) => ({
                              ...prev,
                              [attack.attacker_id]: e.target.value,
                            }))}
                            className="border border-rose-800 bg-slate-950 px-2 py-1 text-xs text-slate-100"
                          >
                            <option value="">No intercept</option>
                            {interceptorEligibles
                              .filter((v) => !assignedElsewhere.has(v.id) || interceptorAssignments[attack.attacker_id] === v.id)
                              .map((v) => (
                                <option key={v.id} value={v.id}>
                                  {v.name} ({v.power ?? 0}/{v.hull ?? v.toughness ?? 0}) @ {bandOf(v)}
                                </option>
                              ))}
                          </select>
                        </div>
                      );
                    })}
                  </div>
                )}
              </section>
            )}

            {/* The Depth Ladder itself */}
            <section className="border border-cyan-900/50 bg-black/40 shadow-[inset_0_0_60px_rgba(8,47,73,0.5)]">
              <div className="flex items-center justify-between border-b border-cyan-900/30 bg-cyan-950/40 px-3 py-1.5">
                <div className="text-[10px] font-bold uppercase tracking-[0.3em] text-cyan-300">
                  Depth Ladder
                </div>
                {pendingMineCardId && (
                  <div className="flex items-center gap-1.5">
                    <span className="text-[10px] uppercase tracking-wide text-amber-300">Lay Mine</span>
                    {DEPTH_BANDS.map((b) => (
                      <button
                        key={b}
                        onClick={() => handleMineBandPick(b)}
                        className="border border-amber-700 bg-amber-950/40 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wider text-amber-200 hover:border-amber-300"
                      >
                        {b.slice(0, 4)}
                      </button>
                    ))}
                    <button
                      onClick={() => setPendingMineCardId(null)}
                      className="ml-1 border border-slate-700 bg-slate-900 px-1.5 py-0.5 text-[10px] uppercase text-slate-400"
                    >
                      x
                    </button>
                  </div>
                )}
              </div>
              <div>
                {DEPTH_BANDS.map((band) => (
                  <DepthRow
                    key={band}
                    band={band}
                    myVessels={myByBand[band] || []}
                    oppVessels={oppByBand[band] || []}
                    myMines={myMinesByBand[band] || []}
                    oppMines={oppMinesByBand[band] || []}
                    myFlagship={myFlagship}
                    oppFlagship={opponentFlagship}
                    selectedAttackerId={selectedAttackerId}
                    selectedTargetId={null}
                    detectMode={detectMode}
                    onClickMyVessel={handleClickMyVessel}
                    onClickOppVessel={handleClickOppVessel}
                    onClickOppFlagship={handleClickOppFlagship}
                  />
                ))}
              </div>
            </section>
          </div>

          {/* Right rail: hand metadata + game log placeholder */}
          <aside className="space-y-3 overflow-y-auto">
            <section className="border border-slate-800 bg-slate-950/70 p-3">
              <div className="mb-1 text-[10px] font-bold uppercase tracking-[0.2em] text-slate-400">Bridge Status</div>
              <div className="grid grid-cols-2 gap-2 text-[11px]">
                <div className="border border-slate-700 bg-black/40 px-2 py-1">
                  <div className="text-slate-500">Hand</div>
                  <div className="font-black">{gameState.hand.length} / {gameState.max_hand_size ?? 8}</div>
                </div>
                <div className="border border-slate-700 bg-black/40 px-2 py-1">
                  <div className="text-slate-500">Library</div>
                  <div className="font-black">{myPlayer?.library_size ?? 0}</div>
                </div>
                <div className="border border-slate-700 bg-black/40 px-2 py-1">
                  <div className="text-slate-500">Wreckage</div>
                  <div className="font-black">{(gameState.graveyard?.[playerId] || []).length}</div>
                </div>
                <div className="border border-slate-700 bg-black/40 px-2 py-1">
                  <div className="text-slate-500">Mines</div>
                  <div className="font-black">{myMines.length}</div>
                </div>
              </div>
            </section>

            <section className="border border-slate-800 bg-slate-950/70 p-3">
              <div className="mb-1 text-[10px] font-bold uppercase tracking-[0.2em] text-slate-400">Detection Log</div>
              <ul className="max-h-44 space-y-1 overflow-y-auto text-[11px] text-slate-400">
                {(gameState.game_log || [])
                  .slice(-12)
                  .reverse()
                  .map((entry, idx) => (
                    <li key={`${entry.timestamp ?? idx}-${idx}`} className="border-l border-cyan-900/40 pl-2">
                      <span className="text-cyan-700">T{entry.turn}</span> {entry.text}
                    </li>
                  ))}
                {(!gameState.game_log || gameState.game_log.length === 0) && (
                  <li className="text-slate-600">No contact events yet.</li>
                )}
              </ul>
            </section>
          </aside>
        </main>

        {/* === Footer: Hand === */}
        <footer className="border-t border-cyan-900/40 bg-slate-950/80 pt-2">
          <div className="mb-1 flex items-center justify-between px-1">
            <div className="text-[10px] font-bold uppercase tracking-[0.2em] text-cyan-300">Hand</div>
            <div className="text-[10px] uppercase tracking-wide text-slate-500">
              {isMyTurn ? 'Your turn — deploy / dive / engage.' : 'Awaiting opponent maneuver.'}
            </div>
          </div>
          <div className="grid grid-cols-[repeat(auto-fit,minmax(140px,1fr))] gap-2 overflow-x-auto px-1 pb-1">
            {gameState.hand.map((card) => {
              const playable = canPlayCard(card);
              const isMineCard = isMine(card);
              return (
                <button
                  key={card.id}
                  onClick={() => handleHandClick(card)}
                  disabled={!playable}
                  className={`border bg-slate-950/80 p-1.5 text-left transition ${
                    pendingMineCardId === card.id
                      ? 'border-amber-300'
                      : playable
                        ? 'border-cyan-700 hover:border-cyan-300'
                        : 'border-slate-800 opacity-50'
                  }`}
                  title={card.text}
                >
                  <div className="flex items-start justify-between gap-1">
                    <div className="text-[11px] font-bold text-slate-100 leading-tight">{card.name}</div>
                    {(card.power !== null || card.toughness !== null) && (
                      <span className="rounded-sm bg-black/70 px-1 text-[10px] font-bold text-amber-200 border border-amber-500/40">
                        {card.power ?? 0}/{card.hull ?? card.toughness ?? 0}
                      </span>
                    )}
                  </div>
                  <DepthsArt
                    cardName={card.name}
                    imageUrl={card.image_url}
                    variant={variantForCard(card, false)}
                    className="mt-1 h-16 border border-cyan-900/50"
                  />
                  <div className="mt-1 line-clamp-2 text-[10px] text-slate-400 leading-snug">{card.text}</div>
                  <div className="mt-1 flex items-center justify-between text-[10px]">
                    <Cost cost={card.depths_cost} />
                    {isMineCard && (
                      <span className="text-amber-300 uppercase tracking-wider">Mine</span>
                    )}
                  </div>
                </button>
              );
            })}
            {gameState.hand.length === 0 && (
              <div className="border border-dashed border-slate-800 bg-black/20 px-3 py-4 text-center text-[10px] uppercase tracking-wider text-slate-500">
                No cards in hand
              </div>
            )}
          </div>
        </footer>
      </div>
    </div>
  );
}

// -- Helpers --------------------------------------------------------------

function groupByBand(vessels: CardData[], flagship: CardData | null) {
  const out: Record<DepthBand, CardData[]> = {
    SURFACE: [], PERISCOPE: [], MID: [], DEEP: [], CRUSH: [],
  };
  for (const v of vessels) {
    if (flagship && v.id === flagship.id) continue;
    out[bandOf(v)].push(v);
  }
  return out;
}

function groupMinesByBand(mines: CardData[]) {
  const out: Record<DepthBand, CardData[]> = {
    SURFACE: [], PERISCOPE: [], MID: [], DEEP: [], CRUSH: [],
  };
  for (const m of mines) out[bandOf(m)].push(m);
  return out;
}

// =========================================================================
// Deckbuilder GameModule export — registered in `registry.ts`.
// =========================================================================

const VESSEL_FILTERS = [
  'DEPTHS_VESSEL',
  'DEPTHS_CREW',
  'DEPTHS_WEAPON',
  'DEPTHS_MINE',
  'INSTANT',     // re-skinned as Action
  'ENCHANTMENT', // re-skinned as Doctrine
] as const;

const ARCHETYPE_COLORS: Record<string, string> = {
  Submarine: '#0891b2',
  Destroyer: '#9ca3af',
  Carrier: '#f59e0b',
  Drone: '#a78bfa',
  Flagship: '#fbbf24',
};

function DepthsStatsExtras({ stats }: { stats: DeckStats }) {
  const dist = (stats.extras?.fleet_distribution as Record<string, number>) || {};
  const keys = Object.keys(ARCHETYPE_COLORS);
  const ordered = [
    ...keys.filter((k) => dist[k]),
    ...Object.keys(dist).filter((k) => !keys.includes(k)),
  ];
  return (
    <StackedBar
      title="Fleet composition"
      segments={ordered.map((k) => ({
        key: k,
        label: k,
        value: dist[k] || 0,
        color: ARCHETYPE_COLORS[k] || '#475569',
      }))}
    />
  );
}

function depthsFormatType(t: string): string {
  // INSTANT → Action, ENCHANTMENT → Doctrine; otherwise strip DEPTHS_ prefix.
  if (t === 'INSTANT') return 'Action';
  if (t === 'ENCHANTMENT') return 'Doctrine';
  if (t.startsWith('DEPTHS_')) {
    const tail = t.slice('DEPTHS_'.length);
    return tail.charAt(0) + tail.slice(1).toLowerCase();
  }
  return defaultFormatType(t);
}

export const depths: GameModule = {
  id: 'depths',
  label: 'Depths: Submarine Fleet',
  showColors: false,
  costLabel: 'Charges',
  typeFilters: VESSEL_FILTERS,
  formatType: depthsFormatType,
  tiles: (stats) => {
    if (!stats) return [];
    const ex = (stats.extras ?? {}) as Record<string, number>;
    return [
      { label: 'Vessels', value: ex.vessel_count ?? 0 },
      { label: 'Mines', value: ex.mine_count ?? 0 },
      { label: 'Doctrine', value: ex.doctrine_count ?? 0 },
    ];
  },
  StatsExtras: DepthsStatsExtras,
};

export default depths;
