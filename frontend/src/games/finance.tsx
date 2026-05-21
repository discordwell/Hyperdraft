/**
 * Finance TCG — deckbuilder module + in-match game board.
 *
 * Two exports:
 *   1. `finance` — deckbuilder GameModule entry registered in registry.ts
 *   2. `FinanceGameBoard` — the in-match board frame
 *
 * Visual language:
 *   Background: deep navy midnight-blue trading room (#03080f).
 *   Capital Reserve bar: glowing emerald (#00FF88), PS1 flat-shaded polygon style.
 *   Liquidity: gold (#FFD700) crystal counter pips.
 *   Trader cards: sapphire-blue borders. Asset cards: gold borders.
 *   Order/Strategy cards: crimson borders.
 *   All labels: monospace uppercase — Bloomberg terminal aesthetic.
 *   No gradients, hard edges, stark shadows — flat-shaded luxury geometry.
 */

import { useState, useMemo } from 'react';
import type { CardData, GameState, PlayerData } from '../types';
import type { GameModule } from './types';
import type { DeckStats } from '../types/deckbuilder';
import { defaultFormatType } from './types';
import { StackedBar } from './StackedBar';
import { FinanceResponseWindow } from './finance/ResponseWindow';
import { useFinanceSounds } from '../hooks/useFinanceSounds';
import { getFinanceArtPaths } from '../utils/cardArt';

// ---- CSS keyframes (injected once into the document) --------------------

function FinanceCSSInjector() {
  return (
    <style dangerouslySetInnerHTML={{ __html: `
      @keyframes fin-ticker {
        0%   { transform: translateX(0); }
        100% { transform: translateX(-50%); }
      }
      @keyframes fin-phase-pulse {
        0%, 100% { text-shadow: 0 0 8px currentColor, 0 0 2px currentColor; }
        50%       { text-shadow: 0 0 24px currentColor, 0 0 8px currentColor, 0 0 1px #fff; }
      }
      @keyframes fin-pool-throb {
        0%, 100% { box-shadow: 0 0 12px #7c3aed40, inset 0 0 8px #7c3aed10; }
        50%       { box-shadow: 0 0 28px #7c3aed70, inset 0 0 18px #7c3aed30; }
      }
      @keyframes fin-scanline {
        0%   { background-position: 0 0; }
        100% { background-position: 0 4px; }
      }
      @keyframes fin-end-turn-glow {
        0%, 100% { box-shadow: 0 0 6px #00ff8830; }
        50%       { box-shadow: 0 0 18px #00ff8870, 0 0 4px #00ff88; }
      }
      @keyframes fin-atk-bounce {
        0%, 100% { transform: scale(1); }
        50%       { transform: scale(1.04); }
      }
      @keyframes fin-capital-danger {
        0%, 100% { filter: brightness(1); }
        50%       { filter: brightness(1.5); }
      }
    `}} />
  );
}

// ---- Animated price ticker across the top --------------------------------

const TICKER_ITEMS = [
  'HFT ALGO ▲ +3.2%', 'DARK ARB ▼ −1.8%', 'QUANT SIG ▲ +0.4%',
  'DERIV IDX ▲ +2.1%', 'VOL INDEX ▲ +8.5%', 'LEV RATIO ▼ −0.3%',
  'ALPHA STR ▲ +5.7%', 'DARK POOL ▲ +12.1%', 'CAP RES ▲ +1.0%',
  'MKTCAP ▼ −2.4%', 'SPREAD WID ▲ +0.9%', 'FLOW COST ▼ −0.6%',
];

function TickerTape() {
  const text = TICKER_ITEMS.join('   ·   ');
  const doubled = text + '   ·   ' + text; // seamless loop
  return (
    <div
      style={{
        overflow: 'hidden',
        borderBottom: '1px solid #0a1e30',
        background: '#010508',
        height: 18,
        display: 'flex',
        alignItems: 'center',
      }}
    >
      <span
        style={{
          display: 'inline-block',
          whiteSpace: 'nowrap',
          animation: 'fin-ticker 60s linear infinite',
          fontSize: 9,
          fontFamily: 'monospace',
          letterSpacing: '0.12em',
          textTransform: 'uppercase',
          color: '#2d5a40',
        }}
      >
        {doubled}
      </span>
    </div>
  );
}

// ---- Phase display names -----------------------------------------------

const PHASE_LABELS: Record<string, string> = {
  PRE_MARKET: 'PRE-MARKET',
  RESEARCH: 'RESEARCH',
  TRADING_SESSION: 'TRADING SESSION',
  SETTLEMENT: 'SETTLEMENT',
  MARKET_CLOSE: 'MARKET CLOSE',
  // Fallbacks for MTG phase strings the server might send before finance phases are wired
  BEGINNING: 'PRE-MARKET',
  PRECOMBAT_MAIN: 'TRADING SESSION',
  COMBAT: 'TRADING SESSION',
  POSTCOMBAT_MAIN: 'SETTLEMENT',
  ENDING: 'MARKET CLOSE',
};

// ---- Card type color map ------------------------------------------------

function cardBorderClass(card: CardData): string {
  if (card.types.some((t) => t === 'FIN_TRADER')) return 'border-sky-500';
  if (card.types.some((t) => t === 'FIN_ASSET')) return 'border-amber-400';
  if (card.types.some((t) => t === 'FIN_STRUCTURE')) return 'border-violet-400';
  if (card.types.some((t) => t === 'FIN_DERIVATIVE')) return 'border-teal-400';
  if (card.types.some((t) => t === 'FIN_ORDER')) return 'border-rose-500';
  if (card.types.some((t) => t === 'FIN_STRATEGY')) return 'border-orange-400';
  return 'border-slate-600';
}

function cardTypeLabel(card: CardData): string {
  if (card.types.some((t) => t === 'FIN_TRADER')) return 'TRADER';
  if (card.types.some((t) => t === 'FIN_ASSET')) return 'ASSET';
  if (card.types.some((t) => t === 'FIN_STRUCTURE')) return 'STRUCTURE';
  if (card.types.some((t) => t === 'FIN_DERIVATIVE')) return 'DERIV';
  if (card.types.some((t) => t === 'FIN_ORDER')) return 'ORDER';
  if (card.types.some((t) => t === 'FIN_STRATEGY')) return 'STRATEGY';
  return card.types[0] || 'CARD';
}

function isTrader(card: CardData) {
  return card.types.some((t) => t === 'FIN_TRADER');
}

function liquidityCost(card: CardData): number {
  if (!card.mana_cost) return 0;
  const n = parseInt(card.mana_cost.replace(/\D/g, ''), 10);
  return isNaN(n) ? 0 : n;
}

// ---- Card art (real PNG with candlestick fallback) ----------------------

/**
 * Card art slot. Tries the server-supplied `image_url` first (already a
 * /api/card-art/finance/<subset>/<slug>.png path), then falls back through
 * other subset folders. If every URL 404s, renders a flat-shaded candlestick
 * glyph in Finance's emerald/amber palette so the chrome still reads as
 * Finance and not "broken image".
 *
 * Why a candlestick: the chrome already speaks Bloomberg-terminal — gold
 * pips, emerald capital bars, a price ticker. A candlestick is the most
 * universally legible Finance signifier and stays within the established
 * flat-shaded luxury geometry (no gradients, hard edges).
 */
function CardArt({
  card,
  className,
  rounded = false,
}: {
  card: CardData;
  className?: string;
  rounded?: boolean;
}) {
  // Build URL list: server-provided image_url first (most accurate domain
  // hint), then the local-derived paths (handles missing image_url, e.g.
  // tokens or older server builds).
  const artPaths = useMemo(() => {
    const list: string[] = [];
    if (card.image_url) list.push(card.image_url);
    for (const p of getFinanceArtPaths(card.name, card.domain ?? null)) {
      if (!list.includes(p)) list.push(p);
    }
    return list;
  }, [card.image_url, card.name, card.domain]);

  const [idx, setIdx] = useState(0);
  const [loaded, setLoaded] = useState(false);
  const [failed, setFailed] = useState(false);

  const handleError = () => {
    if (idx < artPaths.length - 1) {
      setIdx((i) => i + 1);
      return;
    }
    setFailed(true);
  };

  // Candlestick fallback — bullish if Trader/Asset, bearish for Order/Strategy.
  const isBearish = card.types?.some(
    (t) => t === 'FIN_ORDER' || t === 'FIN_STRATEGY',
  );
  const stickColor = isBearish ? '#ef4444' : '#00ff88';
  const wickColor = isBearish ? '#7a1a1a' : '#0d4a30';

  return (
    <div
      className={`relative overflow-hidden ${rounded ? 'rounded-sm' : ''} ${className ?? ''}`}
      style={{
        background: '#020810',
        border: '1px solid #0a1f30',
      }}
      aria-hidden="true"
    >
      {!failed && artPaths.length > 0 && (
        <img
          src={artPaths[idx]}
          alt=""
          loading="lazy"
          className={`absolute inset-0 h-full w-full object-cover ${loaded ? 'opacity-100' : 'opacity-0'}`}
          style={{
            transition: 'opacity 120ms linear',
            // Crisp pixels: art is hand-drawn / flat-shaded
            imageRendering: 'auto',
          }}
          onLoad={() => setLoaded(true)}
          onError={handleError}
        />
      )}
      {(failed || !loaded) && (
        <svg
          viewBox="0 0 24 24"
          className="absolute inset-0 h-full w-full"
          preserveAspectRatio="xMidYMid meet"
          style={{ background: '#020810' }}
        >
          {/* Subtle baseline grid */}
          <line x1="0" y1="18" x2="24" y2="18" stroke="#0a1f30" strokeWidth="0.5" />
          <line x1="4" y1="0" x2="4" y2="24" stroke="#0a1f30" strokeWidth="0.3" />
          <line x1="20" y1="0" x2="20" y2="24" stroke="#0a1f30" strokeWidth="0.3" />
          {/* Wicks */}
          <line x1="12" y1="2" x2="12" y2="6" stroke={wickColor} strokeWidth="0.8" />
          <line x1="12" y1="18" x2="12" y2="22" stroke={wickColor} strokeWidth="0.8" />
          {/* Body — flat-shaded rectangle, no gradient */}
          <rect
            x="8"
            y="6"
            width="8"
            height="12"
            fill={stickColor}
            opacity="0.85"
            stroke={stickColor}
            strokeWidth="0.6"
          />
        </svg>
      )}
      {/* Bottom vignette so name text reads cleanly over art */}
      <div
        className="pointer-events-none absolute inset-x-0 bottom-0 h-1/2"
        style={{
          background: 'linear-gradient(to bottom, transparent, rgba(2,8,16,0.92))',
        }}
      />
    </div>
  );
}

// ---- Atoms --------------------------------------------------------------

/** Capital Reserve bar — segmented blocks, glowing when healthy, pulsing when critical. */
function CapitalBar({
  life,
  maxLife,
  compact = false,
}: {
  life: number;
  maxLife: number;
  compact?: boolean;
}) {
  const pct = maxLife > 0 ? Math.max(0, Math.min(100, (life / maxLife) * 100)) : 0;
  const color = pct > 50 ? '#00ff88' : pct > 25 ? '#ffd700' : '#ff3355';
  const segments = compact ? 8 : 10;
  const filled = Math.round((pct / 100) * segments);
  const critical = pct <= 25;

  return (
    <div
      className={`flex gap-px w-full ${compact ? 'h-2' : 'h-3'}`}
      style={critical ? { animation: 'fin-capital-danger 1.2s ease-in-out infinite' } : {}}
    >
      {Array.from({ length: segments }).map((_, i) => (
        <div
          key={i}
          className="flex-1 h-full transition-all duration-300"
          style={{
            background: i < filled ? color : '#0a100a',
            border: `1px solid ${i < filled ? color + '50' : '#141f14'}`,
            boxShadow: i < filled ? `0 0 3px ${color}50` : 'none',
          }}
        />
      ))}
    </div>
  );
}

/** Liquidity pip display — gold crystal counters. */
function LiquidityPips({ current, max }: { current: number; max: number }) {
  return (
    <div className="flex items-center gap-1 flex-wrap">
      {Array.from({ length: max }).map((_, i) => (
        <div
          key={i}
          className="h-3 w-3"
          style={{
            background: i < current ? '#ffd700' : '#1a1500',
            border: '1px solid #7a6000',
            boxShadow: i < current ? '0 0 4px #ffd700aa' : 'none',
            clipPath: 'polygon(50% 0%, 100% 38%, 82% 100%, 18% 100%, 0% 38%)',
          }}
        />
      ))}
      <span className="ml-1 font-mono text-[10px] font-bold text-amber-300 tracking-wider">
        {current}/{max}
      </span>
    </div>
  );
}

/** Trader tile on the Trading Floor. */
function TraderTile({
  card,
  isMe,
  selected = false,
  selectable = false,
  isAttacker = false,
  onClick,
  onShowDetail,
}: {
  card: CardData;
  isMe: boolean;
  selected?: boolean;
  selectable?: boolean;
  isAttacker?: boolean;
  onClick?: () => void;
  onShowDetail?: (card: CardData) => void;
}) {
  const tapped = card.tapped;
  const sick = !!card.summoning_sickness;
  const borderColor = isMe ? 'border-sky-600' : 'border-rose-600';
  const selectedBorder = selected ? 'border-yellow-300' : '';
  const attackerBadge = isAttacker;

  return (
    <button
      onClick={onClick}
      onContextMenu={onShowDetail ? (e => { e.preventDefault(); onShowDetail(card); }) : undefined}
      disabled={!selectable && !selected}
      className={`group relative border-2 bg-[#050d1a] text-left transition overflow-hidden
        ${selected ? selectedBorder : borderColor}
        ${selectable ? 'cursor-pointer hover:border-yellow-200' : 'cursor-default'}
        ${tapped ? 'opacity-60 rotate-6' : ''}
      `}
      title="Right-click to inspect"
      style={{
        minWidth: 100,
        maxWidth: 130,
        backgroundImage: !isMe
          ? 'repeating-linear-gradient(135deg, transparent 0px, transparent 8px, rgba(239,68,68,0.03) 8px, rgba(239,68,68,0.03) 9px)'
          : undefined,
      }}
    >
      {/* Art slot — fills tile, content rendered above */}
      <CardArt card={card} className="absolute inset-0 h-full w-full" />

      {/* Content overlay */}
      <div className="relative px-2 py-1.5">
        {attackerBadge && (
          <div className="absolute -top-2 left-1/2 -translate-x-1/2 border border-yellow-400 bg-yellow-900/80 px-1 text-[8px] font-black uppercase tracking-wider text-yellow-200">
            ATK
          </div>
        )}
        <div className="flex items-start justify-between gap-1">
          <div className="min-w-0 text-[11px] font-black leading-tight text-slate-100 uppercase tracking-wide truncate drop-shadow-[0_1px_1px_rgba(0,0,0,0.9)]">
            {card.name}
          </div>
          <div className="shrink-0 border border-amber-500/50 bg-black/80 px-1 text-[10px] font-bold text-amber-200 font-mono">
            {card.power ?? 0}/{card.toughness ?? 0}
          </div>
        </div>
        {(card.damage ?? 0) > 0 && (
          <div className="mt-0.5 h-1 w-full bg-black/60 border border-rose-800">
            <div
              className="h-full bg-rose-500"
              style={{
                width: `${Math.min(100, ((card.damage ?? 0) / (card.toughness ?? 1)) * 100)}%`,
              }}
            />
          </div>
        )}
        {/* Pushdown so the type/status row sits in the lower vignette */}
        <div className="h-8" />
        <div className="flex items-center justify-between text-[9px] uppercase tracking-wider">
          <span className="text-sky-300/90 drop-shadow-[0_1px_1px_rgba(0,0,0,0.95)]">TRADER</span>
          {sick && <span className="text-slate-300 drop-shadow-[0_1px_1px_rgba(0,0,0,0.95)]">FRESH</span>}
          {tapped && !sick && <span className="text-amber-300 drop-shadow-[0_1px_1px_rgba(0,0,0,0.95)]">COMMITTED</span>}
        </div>
      </div>
    </button>
  );
}

/** Asset / Structure tile — no power/toughness, tap-to-activate. */
function PermanentTile({
  card,
  isMe,
  onClick,
  onShowDetail,
}: {
  card: CardData;
  isMe: boolean;
  onClick?: () => void;
  onShowDetail?: (card: CardData) => void;
}) {
  const tapped = card.tapped;
  const border = cardBorderClass(card);
  const typeLabel = cardTypeLabel(card);

  return (
    <div
      onClick={onClick}
      onContextMenu={onShowDetail ? (e => { e.preventDefault(); onShowDetail(card); }) : undefined}
      className={`relative border ${border} bg-[#050d1a] text-left transition overflow-hidden
        ${onClick ? 'cursor-pointer hover:brightness-125' : ''}
        ${tapped ? 'opacity-60' : ''}
        ${!isMe ? 'opacity-80' : ''}
      `}
      style={{ minWidth: 90, maxWidth: 120 }}
      title="Right-click to inspect"
    >
      {/* Art slot */}
      <CardArt card={card} className="absolute inset-0 h-full w-full" />
      <div className="relative px-2 py-1.5">
        <div className="text-[11px] font-black leading-tight text-slate-100 uppercase tracking-wide truncate drop-shadow-[0_1px_1px_rgba(0,0,0,0.95)]">
          {card.name}
        </div>
        {/* Spacer for art visibility */}
        <div className="h-7" />
        <div className="text-[9px] uppercase tracking-widest text-slate-200 drop-shadow-[0_1px_1px_rgba(0,0,0,0.95)]">
          {typeLabel}
        </div>
        {tapped && (
          <div className="mt-0.5 text-[9px] uppercase tracking-wider text-amber-300 drop-shadow-[0_1px_1px_rgba(0,0,0,0.95)]">TAPPED</div>
        )}
      </div>
    </div>
  );
}

// ---- Card detail modal --------------------------------------------------

function CardDetailModal({ card, onClose }: { card: CardData; onClose: () => void }) {
  const borderColor = {
    FIN_TRADER: '#38bdf8',
    FIN_ASSET: '#fbbf24',
    FIN_STRUCTURE: '#a78bfa',
    FIN_DERIVATIVE: '#2dd4bf',
    FIN_ORDER: '#fb7185',
    FIN_STRATEGY: '#fb923c',
  }[card.types.find(t => t.startsWith('FIN_')) || ''] ?? '#64748b';

  const typeLabel = cardTypeLabel(card);
  const cost = liquidityCost(card);
  const hasStats = isTrader(card) || card.power != null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ background: 'rgba(0,0,0,0.82)' }}
      onClick={onClose}
    >
      <div
        className="relative border-2 p-5 font-mono"
        style={{
          borderColor,
          background: '#03080f',
          minWidth: 280,
          maxWidth: 400,
          boxShadow: `0 0 32px ${borderColor}55`,
        }}
        onClick={e => e.stopPropagation()}
      >
        {/* Close */}
        <button
          onClick={onClose}
          className="absolute right-2 top-2 z-10 text-slate-500 hover:text-slate-200 text-lg leading-none"
        >
          ✕
        </button>

        {/* Art panel */}
        <CardArt
          card={card}
          className="mb-3 h-44 w-full"
        />

        {/* Name + cost */}
        <div className="flex items-start justify-between gap-3 pr-6">
          <div className="text-base font-black uppercase tracking-wider text-slate-100">
            {card.name}
          </div>
          <div
            className="shrink-0 border px-2 py-0.5 text-sm font-bold"
            style={{ borderColor: '#ffd700', color: '#ffd700', background: '#0d0a00' }}
          >
            {cost}L
          </div>
        </div>

        {/* Type */}
        <div className="mt-1 text-[10px] uppercase tracking-widest" style={{ color: borderColor }}>
          {typeLabel}
          {card.subtypes?.length ? ` — ${card.subtypes.join(' ')}` : ''}
        </div>

        {/* P/T */}
        {hasStats && (
          <div className="mt-2 inline-block border border-sky-700/60 bg-black/60 px-3 py-0.5 text-sm font-bold text-sky-200">
            {card.power ?? 0} / {card.toughness ?? 0}
          </div>
        )}

        {/* Keywords */}
        {(card.keywords?.length ?? 0) > 0 && (
          <div className="mt-2 flex flex-wrap gap-1">
            {(card.keywords ?? []).map(kw => (
              <span key={kw} className="border border-slate-600 px-1.5 py-0.5 text-[9px] uppercase tracking-widest text-slate-400">
                {kw}
              </span>
            ))}
          </div>
        )}

        {/* Full text */}
        {card.text && (
          <div className="mt-3 border-t border-slate-800 pt-3 text-[11px] leading-relaxed text-slate-300 whitespace-pre-wrap">
            {card.text}
          </div>
        )}

        {/* Status chips */}
        <div className="mt-3 flex gap-2 text-[9px] uppercase tracking-widest">
          {card.tapped && <span className="border border-amber-600 px-1.5 py-0.5 text-amber-400">COMMITTED</span>}
          {card.summoning_sickness && <span className="border border-slate-600 px-1.5 py-0.5 text-slate-500">FRESH</span>}
          {(card.damage ?? 0) > 0 && (
            <span className="border border-rose-700 px-1.5 py-0.5 text-rose-400">
              {card.damage} DMG
            </span>
          )}
        </div>

        <div className="mt-3 text-[9px] text-slate-600 uppercase tracking-widest">
          RIGHT-CLICK ANY CARD TO INSPECT
        </div>
      </div>
    </div>
  );
}

/** Hand card. */
function HandCard({
  card,
  playable,
  selected,
  liquidity,
  onClick,
  onShowDetail,
}: {
  card: CardData;
  playable: boolean;
  selected: boolean;
  liquidity: number;
  onClick: () => void;
  onShowDetail: (card: CardData) => void;
}) {
  const border = selected
    ? 'border-yellow-300'
    : playable
      ? cardBorderClass(card)
      : 'border-slate-800';
  const cost = liquidityCost(card);
  const canAfford = liquidity >= cost;
  const typeLabel = cardTypeLabel(card);

  return (
    <button
      onClick={onClick}
      onContextMenu={e => { e.preventDefault(); onShowDetail(card); }}
      disabled={!playable}
      className={`relative border-2 ${border} bg-[#050d1a] text-left transition overflow-hidden
        ${playable ? 'hover:brightness-125 cursor-pointer' : 'cursor-default opacity-50'}
        ${selected ? 'shadow-[0_0_10px_#ffd70066]' : ''}
      `}
      title="Right-click to inspect"
      style={{ minWidth: 120, maxWidth: 160 }}
    >
      {/* Art header */}
      <CardArt card={card} className="h-16 w-full" />

      <div className="p-2">
        {/* Header row: name + cost */}
        <div className="flex items-start justify-between gap-1">
          <div className="min-w-0 text-[11px] font-black leading-tight text-slate-100 uppercase tracking-wide truncate">
            {card.name}
          </div>
          <div
            className="shrink-0 border px-1.5 font-mono text-[10px] font-bold"
            style={{
              borderColor: canAfford ? '#ffd700' : '#4a3800',
              color: canAfford ? '#ffd700' : '#7a6000',
              background: '#0d0a00',
            }}
          >
            {cost}L
          </div>
        </div>
        {/* Type badge */}
        <div className="mt-1 text-[9px] uppercase tracking-widest text-slate-500">{typeLabel}</div>
        {/* P/T for Traders */}
        {isTrader(card) && (card.power !== null || card.toughness !== null) && (
          <div className="mt-1 border border-sky-800/60 bg-black/50 px-1 text-center font-mono text-[10px] text-sky-200 font-bold">
            {card.power ?? 0} / {card.toughness ?? 0}
          </div>
        )}
        {/* Rules text snippet */}
        {card.text && (
          <div className="mt-1 line-clamp-2 text-[9px] leading-snug text-slate-400">{card.text}</div>
        )}
      </div>
    </button>
  );
}

// ---- Blocker assignment UI -----------------------------------------------

interface BlockerAssignment {
  attacker_id: string;
  blocker_id: string;
}

function BlockerPanel({
  attackers,
  myTraders,
  onConfirm,
  onPass,
  cardsById,
}: {
  attackers: { attacker_id: string; target_id?: string }[];
  myTraders: CardData[];
  onConfirm: (blocks: BlockerAssignment[]) => void;
  onPass: () => void;
  cardsById: Map<string, CardData>;
}) {
  const [assignments, setAssignments] = useState<Record<string, string>>({});

  const submit = () => {
    const blocks = Object.entries(assignments)
      .filter(([, bid]) => bid)
      .map(([aid, bid]) => ({ attacker_id: aid, blocker_id: bid }));
    onConfirm(blocks);
  };

  return (
    <div className="border-2 border-rose-500 bg-rose-950/30 p-3">
      <div className="mb-2 flex items-center justify-between gap-3">
        <div>
          <div className="text-xs font-black uppercase tracking-wide text-rose-200">
            DECLARE BLOCKERS
          </div>
          <div className="text-[11px] text-rose-100/70">
            Assign your Traders to intercept incoming attackers.
          </div>
        </div>
        <div className="flex gap-2">
          <button
            onClick={submit}
            className="border border-emerald-500 bg-emerald-800 px-3 py-1 text-[11px] font-black uppercase tracking-wider text-white hover:bg-emerald-600"
          >
            Confirm
          </button>
          <button
            onClick={onPass}
            className="border border-slate-600 bg-slate-800 px-3 py-1 text-[11px] font-black uppercase tracking-wider text-slate-200"
          >
            Take Hits
          </button>
        </div>
      </div>
      <div className="grid gap-2">
        {attackers.map((atk) => {
          const card = cardsById.get(atk.attacker_id);
          if (!card) return null;
          const usedElsewhere = new Set(
            Object.entries(assignments)
              .filter(([aid]) => aid !== atk.attacker_id)
              .map(([, bid]) => bid),
          );
          const eligible = myTraders.filter(
            (t) => !t.tapped && (!usedElsewhere.has(t.id) || assignments[atk.attacker_id] === t.id),
          );
          return (
            <div key={atk.attacker_id} className="grid gap-2 border border-rose-800 bg-black/30 p-2 sm:grid-cols-[1fr_1fr]">
              <div className="text-[11px]">
                <div className="font-bold text-rose-100 uppercase">{card.name}</div>
                <div className="text-rose-300/80">
                  {card.power ?? 0} AGG / {card.toughness ?? 0} DEF
                </div>
              </div>
              <select
                value={assignments[atk.attacker_id] || ''}
                onChange={(e) => setAssignments((prev) => ({
                  ...prev,
                  [atk.attacker_id]: e.target.value,
                }))}
                className="border border-rose-800 bg-slate-950 px-2 py-1 font-mono text-xs text-slate-100"
              >
                <option value="">No block</option>
                {eligible.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name} ({t.power ?? 0}/{t.toughness ?? 0})
                  </option>
                ))}
              </select>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ---- Trading Floor row --------------------------------------------------

function TradingFloorRow({
  label,
  traders,
  assets,
  structures,
  isMe,
  selectedId,
  selectableIds,
  onClickTrader,
  onShowDetail,
  flipped = false,
}: {
  label: string;
  traders: CardData[];
  assets: CardData[];
  structures: CardData[];
  isMe: boolean;
  selectedId: string | null;
  selectableIds: Set<string>;
  onClickTrader: (card: CardData) => void;
  onShowDetail: (card: CardData) => void;
  flipped?: boolean;
}) {
  const empty = traders.length === 0 && assets.length === 0 && structures.length === 0;

  return (
    <div
      className="border border-slate-700/50 bg-[#07101e]/80 px-3 py-2"
      style={{ borderLeft: isMe ? '3px solid #0ea5e9' : '3px solid #ef4444' }}
    >
      <div className="mb-1 text-[9px] font-bold uppercase tracking-[0.25em] text-slate-500">
        {label}
      </div>
      {empty ? (
        <div className="py-2 text-center text-[10px] uppercase tracking-wider text-slate-700">
          — trading floor empty —
        </div>
      ) : (
        <div className={`flex flex-wrap gap-2 ${flipped ? 'flex-row-reverse' : ''}`}>
          {traders.map((c) => (
            <TraderTile
              key={c.id}
              card={c}
              isMe={isMe}
              selected={selectedId === c.id}
              selectable={selectableIds.has(c.id)}
              isAttacker={false}
              onClick={selectableIds.has(c.id) || selectedId === c.id ? () => onClickTrader(c) : undefined}
              onShowDetail={onShowDetail}
            />
          ))}
          {assets.map((c) => (
            <PermanentTile key={c.id} card={c} isMe={isMe} onShowDetail={onShowDetail} />
          ))}
          {structures.map((c) => (
            <PermanentTile key={c.id} card={c} isMe={isMe} onShowDetail={onShowDetail} />
          ))}
        </div>
      )}
    </div>
  );
}

// ---- Game board props / component ---------------------------------------

export interface FinanceGameBoardProps {
  gameState: GameState;
  playerId: string;
  opponentId: string | null;
  myPlayer: PlayerData | null;
  opponentPlayer: PlayerData | null;
  myTraders: CardData[];
  myAssets: CardData[];
  myStructures: CardData[];
  myHand: CardData[];
  myDerivDesk: string[];
  oppTraders: CardData[];
  oppAssets: CardData[];
  currentPhase: string;
  myLiquidity: number;
  myLiquidityMax: number;
  darkPoolActive: boolean;
  isMyTurn: boolean;
  canPlayCard: (card: CardData) => boolean;
  canAttack: (card: CardData) => boolean;
  canBlock: (card: CardData) => boolean;
  onPlayCard: (cardId: string) => void;
  onDeclareAttackers: (attackers: { attacker_id: string; target_id?: string }[]) => void;
  onDeclareBlockers: (blockers: { attacker_id: string; blocker_id: string }[]) => void;
  onActivateAbility: (sourceId: string, abilityId?: string) => void;
  onEndTurn: () => void;
  onPlayResponse?: (cardId: string, targetStackCardId: string) => void;
  onPassResponse?: () => void;
}

export function FinanceGameBoard({
  gameState,
  playerId,
  opponentId,
  myPlayer,
  opponentPlayer,
  myTraders,
  myAssets,
  myStructures,
  myHand,
  myDerivDesk,
  oppTraders,
  oppAssets,
  currentPhase,
  myLiquidity,
  myLiquidityMax,
  darkPoolActive,
  isMyTurn,
  canPlayCard,
  canAttack,
  onPlayCard,
  onDeclareAttackers,
  onDeclareBlockers,
  onEndTurn,
  onPlayResponse,
  onPassResponse,
}: FinanceGameBoardProps) {
  // Wire trading-floor audio cues to engine stack + game events.
  useFinanceSounds(gameState, playerId);

  // Local UI state
  const [selectedAttackerId, setSelectedAttackerId] = useState<string | null>(null);
  const [selectedHandCardId, setSelectedHandCardId] = useState<string | null>(null);
  const [detailCard, setDetailCard] = useState<CardData | null>(null);

  // Combat prompt if server sends it (same shape as Depths)
  const combatPrompt = (gameState as unknown as Record<string, unknown>)['finance_combat'] as {
    phase?: string;
    attacking_player?: string;
    defending_player?: string;
    attackers?: { attacker_id: string; target_id?: string }[];
  } | undefined;

  const isCombatBlockStep = combatPrompt?.phase === 'declare_blockers'
    && combatPrompt?.defending_player === playerId;
  const pendingAttackers = combatPrompt?.attackers || [];

  // Build card lookup from all battlefield cards
  const cardsById = useMemo(() => {
    const m = new Map<string, CardData>();
    for (const c of gameState.battlefield) m.set(c.id, c);
    return m;
  }, [gameState.battlefield]);

  // Selectable IDs — attack declaration is only valid during TRADING_SESSION
  // (engine reads attackers_declared before Settlement starts; anything declared
  // in Settlement is wiped at the next turn's start and has no effect).
  const inTradingSession = currentPhase === 'TRADING_SESSION' || currentPhase === 'PRECOMBAT_MAIN';
  const selectableMyTraders = useMemo(
    () => new Set(isMyTurn && !isCombatBlockStep && inTradingSession ? myTraders.filter(canAttack).map((c) => c.id) : []),
    [isMyTurn, isCombatBlockStep, inTradingSession, myTraders, canAttack],
  );

  const selectableOppTraders = useMemo(
    () => new Set(selectedAttackerId ? oppTraders.map((c) => c.id) : []),
    [selectedAttackerId, oppTraders],
  );

  // Player life totals
  const myLife = myPlayer?.life ?? 30;
  const oppLife = opponentPlayer?.life ?? 30;
  const myMaxLife = (myPlayer as unknown as Record<string, number>)?.max_life ?? 30;
  const oppMaxLife = (opponentPlayer as unknown as Record<string, number>)?.max_life ?? 30;
  const oppLiquidity = opponentPlayer?.mana_crystals_available ?? 0;
  const oppLiquidityMax = opponentPlayer?.mana_crystals ?? 0;

  // Phase display
  const phaseLabel = PHASE_LABELS[currentPhase] || currentPhase.replace(/_/g, ' ');

  // Attack / block handlers
  const handleMyTraderClick = (card: CardData) => {
    if (selectedAttackerId === card.id) {
      setSelectedAttackerId(null);
    } else if (canAttack(card)) {
      setSelectedAttackerId(card.id);
    }
  };

  const handleOppTraderClick = (card: CardData) => {
    if (!selectedAttackerId) return;
    onDeclareAttackers([{ attacker_id: selectedAttackerId, target_id: card.id }]);
    setSelectedAttackerId(null);
  };

  const handleAttackPlayer = () => {
    if (!selectedAttackerId || !opponentId) return;
    onDeclareAttackers([{ attacker_id: selectedAttackerId, target_id: opponentId }]);
    setSelectedAttackerId(null);
  };

  const handleHandCardClick = (card: CardData) => {
    if (!canPlayCard(card)) return;
    if (selectedHandCardId === card.id) {
      onPlayCard(card.id);
      setSelectedHandCardId(null);
    } else {
      setSelectedHandCardId(card.id);
    }
  };

  // ---- Render --------------------------------------------------------

  return (
    <div
      className="min-h-screen text-slate-100 selection:bg-sky-700/30 font-mono"
      style={{ background: '#03080f', position: 'relative' }}
    >
      <FinanceCSSInjector />

      {/* MTG-style response overlay (visible when engine awaits a counter from us) */}
      <FinanceResponseWindow
        gameState={gameState}
        playerId={playerId}
        myHand={myHand}
        myLiquidity={myLiquidity}
        onPlayResponse={onPlayResponse || (() => {})}
        onPassResponse={onPassResponse || (() => {})}
      />

      {/* CRT scanline overlay — very subtle repeating horizontal lines */}
      <div
        aria-hidden="true"
        style={{
          position: 'fixed',
          inset: 0,
          pointerEvents: 'none',
          zIndex: 9999,
          backgroundImage: 'repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(0,0,0,0.08) 2px, rgba(0,0,0,0.08) 4px)',
          backgroundSize: '100% 4px',
        }}
      />

      {/* Price ticker */}
      <TickerTape />

      <div className="grid min-h-screen grid-rows-[auto_1fr_auto] gap-2 p-3">

        {/* === TOP HEADER BAR === */}
        <header
          className="grid grid-cols-1 gap-3 border-b pb-2 sm:grid-cols-[1fr_auto_1fr]"
          style={{ borderColor: '#0d2a45' }}
        >
          {/* Opponent info */}
          <div>
            <div className="text-[9px] uppercase tracking-[0.25em]" style={{ color: '#ef4444aa' }}>
              HOSTILE FIRM
            </div>
            <div className="flex items-baseline gap-2">
              <div className="text-lg font-black uppercase tracking-widest" style={{ color: '#fca5a5' }}>
                {opponentPlayer?.name || 'OPPONENT'}
              </div>
              <div className="text-sm font-black tabular-nums" style={{ color: '#ef4444' }}>
                {oppLife}
              </div>
            </div>
            <div className="mt-1 w-48 max-w-full">
              <div className="mb-0.5 text-[9px] uppercase tracking-widest text-slate-500">
                CAPITAL RESERVE
              </div>
              <CapitalBar life={oppLife} maxLife={oppMaxLife} compact />
            </div>
            <div className="mt-1 flex items-center gap-2 text-[10px]">
              <span className="text-slate-500 uppercase tracking-wide">Liquidity</span>
              <span className="font-black text-amber-300">{oppLiquidity}/{oppLiquidityMax}</span>
              <span className="text-slate-600">|</span>
              <span className="text-slate-500">Hand</span>
              <span className="font-black text-slate-300">
                {opponentPlayer?.hand_size ?? 0}
              </span>
            </div>
          </div>

          {/* Center: Phase + turn */}
          <div
            className="flex flex-col items-center justify-center gap-1 border px-6 py-2"
            style={{
              borderColor: isMyTurn ? '#1a4a3a' : '#1a3a5c',
              background: '#040d1a',
              transition: 'border-color 0.4s',
            }}
          >
            <div className="text-[8px] uppercase tracking-[0.35em] text-slate-500">PHASE</div>
            <div
              className="text-sm font-black uppercase tracking-widest"
              style={{
                color: isMyTurn ? '#00ff88' : '#6b8fa8',
                animation: isMyTurn ? 'fin-phase-pulse 2.5s ease-in-out infinite' : 'none',
              }}
            >
              {phaseLabel}
            </div>
            <div
              className="text-[9px] uppercase tracking-wider"
              style={{
                color: isMyTurn ? '#00cc66' : '#4a6a7a',
                letterSpacing: '0.25em',
              }}
            >
              TURN {gameState.turn_number}
            </div>
            {selectedAttackerId && (
              <button
                onClick={handleAttackPlayer}
                className="mt-1 border px-2 py-0.5 text-[9px] font-black uppercase tracking-widest"
                style={{
                  borderColor: '#ef4444',
                  color: '#ef4444',
                  background: '#1a0505',
                  animation: 'fin-atk-bounce 0.8s ease-in-out infinite',
                }}
              >
                ⚔ ATTACK DIRECT
              </button>
            )}
          </div>

          {/* My info */}
          <div className="text-right">
            <div className="text-[9px] uppercase tracking-[0.25em]" style={{ color: '#00ff8899' }}>
              YOUR FIRM
            </div>
            <div className="flex items-baseline justify-end gap-2">
              <div className="text-sm font-black tabular-nums" style={{ color: '#00ff88' }}>
                {myLife}
              </div>
              <div className="text-lg font-black uppercase tracking-widest text-emerald-200">
                {myPlayer?.name || 'PLAYER'}
              </div>
            </div>
            <div className="mt-1 ml-auto w-48 max-w-full">
              <div className="mb-0.5 text-right text-[9px] uppercase tracking-widest text-slate-500">
                CAPITAL RESERVE
              </div>
              <CapitalBar life={myLife} maxLife={myMaxLife} />
            </div>
            <div className="mt-2 flex items-center justify-end gap-2">
              <button
                onClick={onEndTurn}
                disabled={!isMyTurn}
                className="border px-3 py-1 text-[11px] font-black uppercase tracking-widest transition disabled:opacity-40"
                style={{
                  borderColor: isMyTurn ? '#00ff88' : '#0a3020',
                  color: isMyTurn ? '#00ff88' : '#0a3020',
                  background: '#03080f',
                  animation: isMyTurn ? 'fin-end-turn-glow 2s ease-in-out infinite' : 'none',
                }}
              >
                CLOSE MARKET
              </button>
            </div>
          </div>
        </header>

        {/* === MAIN BOARD === */}
        <main className="grid grid-cols-1 gap-2 overflow-y-auto xl:grid-cols-[minmax(200px,240px)_1fr_minmax(200px,240px)] xl:overflow-hidden">

          {/* Left rail: Liquidity + Derivatives Desk + Dark Pool */}
          <aside className="space-y-3 overflow-y-auto">

            {/* Liquidity panel */}
            <section
              className="border p-3"
              style={{ borderColor: '#1a3a1a', background: '#040d08' }}
            >
              <div className="mb-2 text-[9px] font-bold uppercase tracking-[0.25em]" style={{ color: '#00ff8899' }}>
                LIQUIDITY POOL
              </div>
              <LiquidityPips current={myLiquidity} max={Math.max(myLiquidityMax, 1)} />
            </section>

            {/* Derivatives Desk */}
            <section
              className="border p-3"
              style={{ borderColor: '#0d2a2a', background: '#030b0b' }}
            >
              <div className="mb-2 text-[9px] font-bold uppercase tracking-[0.25em] text-teal-400/70">
                DERIVATIVES DESK
              </div>
              {myDerivDesk.length === 0 ? (
                <div className="text-[10px] uppercase tracking-wider text-slate-600">
                  — EMPTY —
                </div>
              ) : (
                <div className="space-y-1">
                  {myDerivDesk.map((id) => {
                    const c = cardsById.get(id);
                    return c ? (
                      <div
                        key={id}
                        className="border border-teal-700 bg-teal-950/30 px-2 py-1 text-[11px] font-bold uppercase text-teal-200 tracking-wide"
                      >
                        {c.name}
                      </div>
                    ) : (
                      <div key={id} className="text-[10px] text-slate-600">
                        {id.slice(0, 8)}…
                      </div>
                    );
                  })}
                </div>
              )}
            </section>

            {/* Dark Pool indicator */}
            <section
              className="border p-3"
              style={{
                borderColor: darkPoolActive ? '#7c3aed' : '#1a1230',
                background: darkPoolActive ? '#0d0820' : '#02030a',
                animation: darkPoolActive ? 'fin-pool-throb 2s ease-in-out infinite' : 'none',
                transition: 'border-color 0.4s, background 0.4s',
              }}
            >
              <div
                className="mb-1 text-[9px] font-bold uppercase tracking-[0.25em]"
                style={{ color: darkPoolActive ? '#a78bfa' : '#2d1f5a' }}
              >
                DARK POOL
              </div>
              <div
                className="text-[11px] font-black uppercase tracking-widest"
                style={{ color: darkPoolActive ? '#c4b5fd' : '#3d2b6a' }}
              >
                {darkPoolActive ? '▮ ACTIVE' : '▯ VACANT'}
              </div>
              {darkPoolActive && (
                <div className="mt-1 text-[9px] uppercase tracking-wide" style={{ color: '#7c3aed90' }}>
                  Triggers on opponent's Trading Session
                </div>
              )}
            </section>

            {/* Library / Graveyard stats */}
            <section
              className="border p-3"
              style={{ borderColor: '#1a2a3a', background: '#030a12' }}
            >
              <div className="mb-2 text-[9px] font-bold uppercase tracking-[0.25em] text-slate-500">
                FIRM STATUS
              </div>
              <div className="grid grid-cols-2 gap-2 text-[10px]">
                <div className="border border-slate-700 bg-black/40 px-2 py-1">
                  <div className="text-slate-500 text-[9px] uppercase tracking-wide">HAND</div>
                  <div className="font-black text-slate-200">{myHand.length} / {gameState.max_hand_size ?? 7}</div>
                </div>
                <div className="border border-slate-700 bg-black/40 px-2 py-1">
                  <div className="text-slate-500 text-[9px] uppercase tracking-wide">BOOK</div>
                  <div className="font-black text-slate-200">{myPlayer?.library_size ?? 0}</div>
                </div>
                <div className="border border-slate-700 bg-black/40 px-2 py-1">
                  <div className="text-slate-500 text-[9px] uppercase tracking-wide">LIQUID'D</div>
                  <div className="font-black text-slate-200">
                    {(gameState.graveyard?.[playerId] || []).length}
                  </div>
                </div>
                <div className="border border-slate-700 bg-black/40 px-2 py-1">
                  <div className="text-slate-500 text-[9px] uppercase tracking-wide">STRUCTR</div>
                  <div className="font-black text-slate-200">{myStructures.length}/3</div>
                </div>
              </div>
            </section>
          </aside>

          {/* Center: Trading Floor */}
          <div className="flex min-w-0 flex-col gap-2">

            {/* Blocker prompt */}
            {isCombatBlockStep && (
              <BlockerPanel
                attackers={pendingAttackers}
                myTraders={myTraders}
                onConfirm={onDeclareBlockers}
                onPass={() => onDeclareBlockers([])}
                cardsById={cardsById}
              />
            )}

            {/* Attacker selection hint */}
            {selectedAttackerId && !isCombatBlockStep && (
              <div
                className="border p-2 text-[11px] font-bold uppercase tracking-wider text-center"
                style={{ borderColor: '#ffd700', color: '#ffd700', background: '#0d0a00' }}
              >
                TRADER SELECTED — CLICK AN ENEMY TRADER OR "ATTACK DIRECT"
              </div>
            )}

            {/* Trading Floor center label */}
            <div
              className="border px-3 py-1.5 text-center"
              style={{
                borderColor: '#0d2a45',
                background: 'repeating-linear-gradient(90deg, #020b16 0px, #020b16 39px, #040f1c 39px, #040f1c 40px), repeating-linear-gradient(0deg, #020b16 0px, #020b16 19px, #040f1c 19px, #040f1c 20px)',
              }}
            >
              <div className="text-[9px] uppercase tracking-[0.4em] text-slate-600">
                ─── TRADING FLOOR ───
              </div>
            </div>

            {/* Opponent's side */}
            <TradingFloorRow
              label={`${opponentPlayer?.name ?? 'OPPONENT'}'s TRADING FLOOR`}
              traders={oppTraders}
              assets={oppAssets}
              structures={(gameState.battlefield || []).filter(
                (c) => c.controller === opponentId && c.types.some((t) => t === 'FIN_STRUCTURE'),
              )}
              isMe={false}
              selectedId={selectedAttackerId ? oppTraders.find((c) => selectableOppTraders.has(c.id))?.id ?? null : null}
              selectableIds={selectableOppTraders}
              onClickTrader={handleOppTraderClick}
              onShowDetail={setDetailCard}
              flipped
            />

            {/* Divider */}
            <div className="flex items-center gap-2 px-3">
              <div className="h-px flex-1" style={{ background: '#1a3a5c' }} />
              <div className="text-[9px] uppercase tracking-[0.3em] text-slate-600">v s</div>
              <div className="h-px flex-1" style={{ background: '#1a3a5c' }} />
            </div>

            {/* My side */}
            <TradingFloorRow
              label="YOUR TRADING FLOOR"
              traders={myTraders}
              assets={myAssets}
              structures={myStructures}
              isMe
              selectedId={selectedAttackerId}
              selectableIds={selectableMyTraders}
              onClickTrader={handleMyTraderClick}
              onShowDetail={setDetailCard}
            />

          </div>

          {/* Right rail: Game log */}
          <aside className="space-y-3 overflow-y-auto">
            <section
              className="border p-3"
              style={{ borderColor: '#0e2030', background: '#020810' }}
            >
              <div className="mb-2 flex items-center gap-2">
                <div className="text-[9px] font-bold uppercase tracking-[0.25em] text-slate-500">
                  MARKET FEED
                </div>
                <div
                  className="h-1.5 w-1.5 rounded-full"
                  style={{ background: '#00ff88', boxShadow: '0 0 4px #00ff88', animation: 'fin-capital-danger 2s ease-in-out infinite' }}
                />
              </div>
              <ul className="max-h-80 space-y-0.5 overflow-y-auto">
                {(gameState.game_log || [])
                  .slice(-16)
                  .reverse()
                  .map((entry, idx) => (
                    <li
                      key={`${entry.timestamp ?? idx}-${idx}`}
                      className="flex gap-2 border-l-2 pl-2 py-0.5"
                      style={{
                        borderColor: idx === 0 ? '#00ff8840' : '#0e2030',
                        background: idx === 0 ? '#010f06' : 'transparent',
                      }}
                    >
                      <span
                        className="shrink-0 font-black tabular-nums"
                        style={{ fontSize: 9, color: '#004d26', letterSpacing: '0.1em' }}
                      >
                        T{entry.turn}
                      </span>
                      <span style={{ fontSize: 10, color: idx === 0 ? '#94a3b8' : '#475569', lineHeight: 1.4 }}>
                        {entry.text}
                      </span>
                    </li>
                  ))}
                {(!gameState.game_log || gameState.game_log.length === 0) && (
                  <li style={{ fontSize: 10, color: '#1e3a2a', fontFamily: 'monospace' }}>
                    — awaiting first transaction —
                  </li>
                )}
              </ul>
            </section>

            {/* Selected trader detail */}
            {selectedAttackerId && (
              (() => {
                const c = cardsById.get(selectedAttackerId);
                if (!c) return null;
                return (
                  <section
                    className="border p-3"
                    style={{ borderColor: '#ffd70040', background: '#0d0a00' }}
                  >
                    <div className="mb-1 text-[9px] font-bold uppercase tracking-[0.25em] text-amber-500">
                      SELECTED TRADER
                    </div>
                    <div className="text-sm font-black uppercase text-slate-100">{c.name}</div>
                    <div className="mt-1 font-mono text-[11px] text-amber-200">
                      {c.power ?? 0} AGG / {c.toughness ?? 0} DEF
                    </div>
                    {c.text && (
                      <div className="mt-2 text-[10px] leading-snug text-slate-400">{c.text}</div>
                    )}
                    <button
                      onClick={() => setSelectedAttackerId(null)}
                      className="mt-2 border border-slate-700 bg-slate-900 px-2 py-0.5 text-[10px] uppercase tracking-wide text-slate-400 hover:border-slate-500"
                    >
                      Deselect
                    </button>
                  </section>
                );
              })()
            )}
          </aside>
        </main>

        {/* === FOOTER: HAND === */}
        <footer
          className="border-t pt-2"
          style={{ borderColor: '#0d2a45', background: '#020810' }}
        >
          <div className="mb-1 flex items-center justify-between px-1">
            <div className="flex items-center gap-3">
              <div className="text-[9px] font-bold uppercase tracking-[0.25em]" style={{ color: '#00ff8899' }}>
                HAND
              </div>
              <div className="text-[9px] text-slate-600 uppercase tracking-wide">
                {myHand.length} CARDS
              </div>
            </div>
            <div className="text-[9px] uppercase tracking-wide text-slate-600">
              {isMyTurn
                ? selectedHandCardId
                  ? 'CLICK AGAIN TO PLAY'
                  : 'YOUR TURN — SELECT A CARD TO PLAY'
                : 'AWAITING OPPONENT'}
            </div>
          </div>

          {myHand.length === 0 ? (
            <div
              className="border border-dashed px-3 py-4 text-center text-[10px] uppercase tracking-widest"
              style={{ borderColor: '#0d2a45', color: '#1a3a5c' }}
            >
              HAND IS EMPTY
            </div>
          ) : (
            <div className="flex flex-wrap gap-2 overflow-x-auto px-1 pb-2">
              {myHand.map((card) => (
                <HandCard
                  key={card.id}
                  card={card}
                  playable={canPlayCard(card)}
                  selected={selectedHandCardId === card.id}
                  liquidity={myLiquidity}
                  onClick={() => handleHandCardClick(card)}
                  onShowDetail={setDetailCard}
                />
              ))}
            </div>
          )}
        </footer>

      </div>

      {/* Card detail modal */}
      {detailCard && (
        <CardDetailModal card={detailCard} onClose={() => setDetailCard(null)} />
      )}

    </div>
  );
}

// =========================================================================
// Deckbuilder GameModule export — registered in `registry.ts`.
// =========================================================================

const CARD_TYPE_FILTERS = [
  'FIN_TRADER',
  'FIN_ORDER',
  'FIN_STRATEGY',
  'FIN_ASSET',
  'FIN_DERIVATIVE',
  'FIN_STRUCTURE',
] as const;

const TYPE_COLORS: Record<string, string> = {
  Trader: '#0ea5e9',
  Order: '#ef4444',
  Strategy: '#f97316',
  Asset: '#fbbf24',
  Derivative: '#2dd4bf',
  Structure: '#a78bfa',
};

function FinanceStatsExtras({ stats }: { stats: DeckStats }) {
  const dist = (stats.extras?.type_distribution as Record<string, number>) || {};
  const keys = Object.keys(TYPE_COLORS);
  const ordered = [
    ...keys.filter((k) => dist[k]),
    ...Object.keys(dist).filter((k) => !keys.includes(k)),
  ];
  return (
    <StackedBar
      title="Card type breakdown"
      segments={ordered.map((k) => ({
        key: k,
        label: k,
        value: dist[k] || 0,
        color: TYPE_COLORS[k] || '#475569',
      }))}
    />
  );
}

function financeFormatType(t: string): string {
  if (t.startsWith('FIN_')) {
    const tail = t.slice('FIN_'.length);
    return tail.charAt(0) + tail.slice(1).toLowerCase();
  }
  return defaultFormatType(t);
}

export const finance: GameModule = {
  id: 'finance',
  label: 'Finance TCG',
  showColors: false,
  costLabel: 'Liquidity',
  typeFilters: CARD_TYPE_FILTERS,
  formatType: financeFormatType,
  tiles: (stats) => {
    if (!stats) return [];
    const ex = (stats.extras ?? {}) as Record<string, number>;
    return [
      { label: 'Traders', value: ex.trader_count ?? 0 },
      { label: 'Assets', value: ex.asset_count ?? 0 },
      { label: 'Orders', value: ex.order_count ?? 0 },
    ];
  },
  StatsExtras: FinanceStatsExtras,
};

export default finance;
