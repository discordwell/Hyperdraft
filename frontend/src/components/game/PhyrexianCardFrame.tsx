/**
 * PhyrexianCardFrame
 *
 * Industrial-occult chrome for Phyrexia Bedrock Edition cards. Wraps generated
 * card art with a stepped voxel frame, oil-slicked plating, and rune-seam
 * highlights that change colour by card type.
 *
 *   Mob              -> obsidian + crimson seams
 *   Compleated mob   -> darker obsidian + sickly-green seams + oil drips
 *   Praetor          -> obsidian + crimson seams + gold halo crown
 *   Boss             -> larger crimson-tinged frame
 *   Structure        -> stone-blue plate, architectural cornice
 *   Block            -> heavy uniform stone plate
 *   Tool             -> bronze-and-leather plate
 *   Action           -> torn parchment with crimson runes
 *
 * Two sizes:
 *   - 'compact' (~120x170): hand thumbnail; name + art + stats
 *   - 'full'    (~280x400): detail panel; name + cost + art + keywords + rules + flavor
 */

import React from 'react';
import type { CardData } from '../../types';

// =============================================================================
// Variant resolution
// =============================================================================

export type FrameVariant =
  | 'mob'
  | 'compleated'
  | 'praetor'
  | 'boss'
  | 'structure'
  | 'block'
  | 'tool'
  | 'action';

export function resolveVariant(card: CardData): FrameVariant {
  const types = new Set(card.types || []);
  const subs = new Set(card.subtypes || []);
  if (types.has('MC_ACTION')) return 'action';
  if (types.has('MC_TOOL')) return 'tool';
  if (types.has('MC_BLOCK')) return 'block';
  if (types.has('MC_STRUCTURE')) return 'structure';
  if (types.has('MC_MOB')) {
    if (subs.has('Praetor')) return 'praetor';
    if (subs.has('Boss')) return 'boss';
    if (subs.has('Compleated')) return 'compleated';
    return 'mob';
  }
  return 'mob';
}

interface VariantStyle {
  plateTop: string;
  plateMid: string;
  plateBot: string;
  seam: string;        // class
  clip: string;        // class
  accent: string;      // hex used for rune-seam glow tints
  textbox: string;     // class
  typeLineLabel: string;
  glyphAccent: string;
  oil?: boolean;       // overlay
  halo?: boolean;
}

const VARIANTS: Record<FrameVariant, VariantStyle> = {
  mob: {
    plateTop: '#1f181a',
    plateMid: '#0d0a0e',
    plateBot: '#06050a',
    seam: 'phx-seam-crimson',
    clip: 'phx-clip-step',
    accent: '#a31420',
    textbox: 'phx-textbox',
    typeLineLabel: 'MOB',
    glyphAccent: '#d83242',
  },
  compleated: {
    plateTop: '#181614',
    plateMid: '#0a0908',
    plateBot: '#040504',
    seam: 'phx-seam-bile',
    clip: 'phx-clip-step',
    accent: '#7ad24c',
    textbox: 'phx-textbox',
    typeLineLabel: 'COMPLEATED',
    glyphAccent: '#76c83c',
    oil: true,
  },
  praetor: {
    plateTop: '#231a13',
    plateMid: '#0e0a07',
    plateBot: '#06040a',
    seam: 'phx-seam-gold',
    clip: 'phx-clip-step-heavy',
    accent: '#e2b454',
    textbox: 'phx-textbox-praetor',
    typeLineLabel: 'PRAETOR',
    glyphAccent: '#f0c860',
    halo: true,
  },
  boss: {
    plateTop: '#251416',
    plateMid: '#100507',
    plateBot: '#070306',
    seam: 'phx-seam-crimson',
    clip: 'phx-clip-step-heavy',
    accent: '#e64a3a',
    textbox: 'phx-textbox',
    typeLineLabel: 'BOSS',
    glyphAccent: '#e64a3a',
  },
  structure: {
    plateTop: '#23303a',
    plateMid: '#101820',
    plateBot: '#0a1018',
    seam: 'phx-seam-stone',
    clip: 'phx-clip-step',
    accent: '#7a99b8',
    textbox: 'phx-textbox',
    typeLineLabel: 'STRUCTURE',
    glyphAccent: '#92a8c0',
  },
  block: {
    plateTop: '#2a2a2c',
    plateMid: '#161618',
    plateBot: '#0c0c10',
    seam: 'phx-seam-stone',
    clip: 'phx-clip-step',
    accent: '#a0a0a4',
    textbox: 'phx-textbox',
    typeLineLabel: 'BLOCK',
    glyphAccent: '#bcbcc0',
  },
  tool: {
    plateTop: '#2a1f12',
    plateMid: '#150e07',
    plateBot: '#0c0703',
    seam: 'phx-seam-bronze',
    clip: 'phx-clip-step',
    accent: '#c79560',
    textbox: 'phx-textbox',
    typeLineLabel: 'TOOL',
    glyphAccent: '#c79560',
  },
  action: {
    plateTop: '#1c0a0e',
    plateMid: '#0c0405',
    plateBot: '#06010a',
    seam: 'phx-seam-crimson',
    clip: 'phx-clip-tear',
    accent: '#d62232',
    textbox: 'phx-textbox',
    typeLineLabel: 'ACTION',
    glyphAccent: '#e84252',
  },
};

// =============================================================================
// Cost icons — 5 resources, voxel-flavored 14x14 SVG.
// =============================================================================

const COST_ORDER: string[] = ['wood', 'stone', 'iron', 'redstone', 'diamond'];

function CostIcon({ kind, value, size = 18 }: { kind: string; value: number; size?: number }) {
  // Stylised voxel block with cost number stamped in pixel mono.
  const palette: Record<string, { base: string; edge: string; hilite: string; glyph: string }> = {
    wood:     { base: '#6b3f20', edge: '#3a2110', hilite: '#a06234', glyph: '#fbd9a1' },
    stone:    { base: '#6c6c70', edge: '#2c2c30', hilite: '#9a9a9e', glyph: '#f0f0f4' },
    iron:     { base: '#b6b6bc', edge: '#5a5a60', hilite: '#e6e6ec', glyph: '#1a1a1c' },
    redstone: { base: '#a01418', edge: '#3a0608', hilite: '#e63040', glyph: '#fff2a8' },
    diamond:  { base: '#3aa6c0', edge: '#0e3848', hilite: '#7ee6f5', glyph: '#0a1a20' },
  };
  const c = palette[kind] || palette.stone;
  return (
    <span
      title={`${kind} ${value}`}
      className="inline-flex items-center justify-center phx-mono"
      style={{
        width: size,
        height: size,
        background: `linear-gradient(135deg, ${c.hilite} 0%, ${c.base} 35%, ${c.base} 65%, ${c.edge} 100%)`,
        border: `1px solid ${c.edge}`,
        boxShadow: `inset 0 1px 0 rgba(255,255,255,0.18), inset 0 -1px 0 rgba(0,0,0,0.5)`,
        color: c.glyph,
        fontSize: size * 0.78,
        lineHeight: 1,
      }}
    >
      {value}
    </span>
  );
}

function CostCluster({ cost, size = 18 }: { cost?: Record<string, number>; size?: number }) {
  const entries = COST_ORDER
    .map((k) => [k, cost?.[k] || 0] as const)
    .filter(([, v]) => v > 0);
  if (!entries.length) return <span className="phx-mono text-[11px] tracking-wider text-emerald-300">FREE</span>;
  return (
    <span className="inline-flex flex-wrap gap-1">
      {entries.map(([k, v]) => <CostIcon key={k} kind={k} value={v} size={size} />)}
    </span>
  );
}

// =============================================================================
// Keyword glyphs — minimal pixel-leaning SVG icons.
// =============================================================================

interface KeywordGlyphProps { keyword: string; color?: string; size?: number; }

function KeywordGlyph({ keyword, color = '#d83242', size = 16 }: KeywordGlyphProps) {
  const k = keyword.toLowerCase();
  const stroke = color;
  const common = { fill: 'none', stroke, strokeWidth: 1.6, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const };
  const sw = size;
  switch (k) {
    case 'aerial':
      // Two upward chevrons + central spine.
      return (
        <svg width={sw} height={sw} viewBox="0 0 16 16" {...{ role: 'img', 'aria-label': k }}>
          <path d="M3 11 L8 4 L13 11" {...common} />
          <path d="M5 13 L8 9 L11 13" {...common} />
        </svg>
      );
    case 'climb':
      // Stair zigzag.
      return (
        <svg width={sw} height={sw} viewBox="0 0 16 16" role="img" aria-label={k}>
          <path d="M2 13 H6 V10 H9 V7 H12 V4 H14" {...common} />
        </svg>
      );
    case 'ranged':
      // Arrow flying right.
      return (
        <svg width={sw} height={sw} viewBox="0 0 16 16" role="img" aria-label={k}>
          <path d="M2 8 H12" {...common} />
          <path d="M9 5 L13 8 L9 11" {...common} />
          <path d="M2 6 L2 10" {...common} />
        </svg>
      );
    case 'reach':
      // Outstretched spear.
      return (
        <svg width={sw} height={sw} viewBox="0 0 16 16" role="img" aria-label={k}>
          <path d="M3 13 L10 6" {...common} />
          <path d="M10 6 L13 3" {...common} />
          <path d="M11 5 L13 3 L11 3 Z" fill={color} stroke={color} />
          <path d="M2 13 L4 13 L4 11" {...common} />
        </svg>
      );
    case 'siege':
      // Crushing hammer over cracked block.
      return (
        <svg width={sw} height={sw} viewBox="0 0 16 16" role="img" aria-label={k}>
          <rect x={2} y={9} width={12} height={5} stroke={color} strokeWidth={1.4} fill="none" />
          <path d="M5 11 L8 13 L11 11" {...common} />
          <rect x={6} y={2} width={4} height={4} stroke={color} strokeWidth={1.4} fill="none" />
          <path d="M8 6 L8 9" {...common} />
        </svg>
      );
    case 'infect':
      // Drop with internal cross — biohazard distillate.
      return (
        <svg width={sw} height={sw} viewBox="0 0 16 16" role="img" aria-label={k}>
          <path d="M8 2 C5 6 4 9 4 11 A4 4 0 0 0 12 11 C12 9 11 6 8 2 Z" {...common} />
          <path d="M6 10 L10 10 M8 8 L8 12" {...common} />
        </svg>
      );
    case 'haste':
      // Lightning bolt.
      return (
        <svg width={sw} height={sw} viewBox="0 0 16 16" role="img" aria-label={k}>
          <path d="M9 2 L4 9 H8 L7 14 L12 7 H8 Z" stroke={color} strokeWidth={1.4} fill={color} fillOpacity={0.18} />
        </svg>
      );
    default:
      return (
        <svg width={sw} height={sw} viewBox="0 0 16 16" role="img" aria-label={k}>
          <circle cx={8} cy={8} r={4} {...common} />
        </svg>
      );
  }
}

const KEYWORD_LABEL: Record<string, string> = {
  aerial: 'Aerial', climb: 'Climb', ranged: 'Ranged', reach: 'Reach',
  siege: 'Siege', infect: 'Infect', haste: 'Haste',
};

// =============================================================================
// Decorative ornaments
// =============================================================================

function PraetorHalo({ size = 90 }: { size?: number }) {
  // Cracked gold ring with three taller spikes — a battered crown of inquisition.
  return (
    <svg width={size} height={size / 2} viewBox="0 0 90 45" className="absolute" style={{ top: -size / 4, left: '50%', transform: 'translateX(-50%)', pointerEvents: 'none' }}>
      <defs>
        <linearGradient id="halo-grad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#f4d068" />
          <stop offset="55%" stopColor="#a06822" />
          <stop offset="100%" stopColor="#3a2406" />
        </linearGradient>
      </defs>
      {/* halo arc */}
      <path d="M5 38 Q45 -10 85 38" stroke="url(#halo-grad)" strokeWidth="2" fill="none" />
      <path d="M9 39 Q45 -4 81 39" stroke="rgba(255,220,120,0.4)" strokeWidth="1" fill="none" />
      {/* spikes */}
      <path d="M45 4 L45 -4 M30 9 L26 1 M60 9 L64 1" stroke="url(#halo-grad)" strokeWidth="1.6" />
      {/* fractures in the halo */}
      <path d="M25 24 L29 22 M55 19 L60 21 M67 28 L71 26" stroke="rgba(255,255,255,0.18)" strokeWidth="0.7" />
      {/* crimson rune drops dangling */}
      <circle cx="22" cy="36" r="1.6" fill="#a31420" />
      <circle cx="68" cy="36" r="1.6" fill="#a31420" />
    </svg>
  );
}

function OilDrips({ width = 280 }: { width?: number }) {
  // Sickly-green ichor leaking down the top edge of the frame.
  const drips = [
    { x: 18, h: 14 }, { x: 58, h: 22 }, { x: 96, h: 10 },
    { x: 138, h: 28 }, { x: 178, h: 14 }, { x: 220, h: 20 }, { x: 258, h: 12 },
  ];
  return (
    <svg width={width} height={32} viewBox="0 0 280 32" className="absolute phx-drip-shadow" style={{ top: 0, left: 0, pointerEvents: 'none' }}>
      <defs>
        <linearGradient id="ichor" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#9aff58" />
          <stop offset="40%" stopColor="#3a8a1c" />
          <stop offset="100%" stopColor="#0c280a" />
        </linearGradient>
      </defs>
      {drips.map((d, i) => (
        <path
          key={i}
          d={`M${d.x - 3} 0 Q${d.x} ${d.h * 0.4} ${d.x - 1} ${d.h - 2} Q${d.x} ${d.h + 2} ${d.x + 1} ${d.h - 2} Q${d.x + 2} ${d.h * 0.4} ${d.x + 3} 0 Z`}
          fill="url(#ichor)"
        />
      ))}
      {/* ambient highlight specks */}
      <circle cx={36} cy={3} r={1.2} fill="#bfff80" opacity={0.7} />
      <circle cx={120} cy={3} r={1} fill="#bfff80" opacity={0.5} />
      <circle cx={240} cy={2} r={1.2} fill="#bfff80" opacity={0.6} />
    </svg>
  );
}

function CornerRivets() {
  // Four corner rivets positioned via absolute layout.
  return (
    <>
      <span className="phx-rivet absolute top-1.5 left-1.5" />
      <span className="phx-rivet absolute top-1.5 right-1.5" />
      <span className="phx-rivet absolute bottom-1.5 left-1.5" />
      <span className="phx-rivet absolute bottom-1.5 right-1.5" />
    </>
  );
}

// =============================================================================
// Sub-panels
// =============================================================================

function PlateBackground({ style, variant, size }: { style: VariantStyle; variant: FrameVariant; size: 'full' | 'compact'; }) {
  return (
    <div
      className={`absolute inset-0 phx-plate ${style.clip} ${style.seam}`}
      style={{
        // CSS variables consumed by .phx-plate
        ['--plate-top' as any]: style.plateTop,
        ['--plate-mid' as any]: style.plateMid,
        ['--plate-bot' as any]: style.plateBot,
      }}
    >
      {style.oil && <div className="absolute inset-0 phx-oil-overlay" />}
      {/* outer rim glow synced to accent */}
      <div
        className="absolute inset-0"
        style={{
          boxShadow: `inset 0 0 ${size === 'full' ? 28 : 16}px rgba(${hexToRgb(style.accent)}, 0.18)`,
        }}
      />
      {/* Action-card flickering ember edge */}
      {variant === 'action' && (
        <div
          className="absolute inset-0"
          style={{
            background:
              'radial-gradient(ellipse at 50% 0%, rgba(220, 60, 60, 0.22) 0%, transparent 38%),' +
              'radial-gradient(ellipse at 50% 100%, rgba(180, 30, 40, 0.2) 0%, transparent 42%)',
          }}
        />
      )}
    </div>
  );
}

function hexToRgb(hex: string): string {
  const h = hex.replace('#', '');
  const bigint = parseInt(h, 16);
  return `${(bigint >> 16) & 255}, ${(bigint >> 8) & 255}, ${bigint & 255}`;
}

// Italicize _word_ snippets in flavor / rules text.
function FormattedText({ text, italicClass }: { text: string; italicClass?: string }) {
  const parts: React.ReactNode[] = [];
  const re = /_([^_]+)_/g;
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text))) {
    if (m.index > last) parts.push(text.slice(last, m.index));
    parts.push(<em key={m.index} className={italicClass || 'italic'}>{m[1]}</em>);
    last = m.index + m[0].length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return <>{parts}</>;
}

// =============================================================================
// Main component
// =============================================================================

export interface PhyrexianCardFrameProps {
  card: CardData;
  size?: 'full' | 'compact';
  selected?: boolean;
  onClick?: () => void;
  className?: string;
}

export function PhyrexianCardFrame({
  card,
  size = 'full',
  selected = false,
  onClick,
  className = '',
}: PhyrexianCardFrameProps) {
  const variant = resolveVariant(card);
  const style = VARIANTS[variant];
  const accent = style.accent;

  const width = size === 'full' ? 280 : 120;
  const height = size === 'full' ? 400 : 170;

  const subtypes = (card.subtypes || []).filter(
    (s) => !['Compleated', 'Praetor', 'Boss', 'Mob'].includes(s),
  );
  const typeLine = [style.typeLineLabel, ...subtypes].join(' · ');

  const keywords = (card.mc_keywords || []).filter((k) => k && KEYWORD_LABEL[k.toLowerCase()]);

  const hasStats = card.power != null || card.toughness != null;
  const isMob = (card.types || []).includes('MC_MOB');
  const isStructureLike = (card.types || []).some((t) => t === 'MC_STRUCTURE' || t === 'MC_BLOCK');

  // Flavor text: sniff out "_text_" italic phrases — we treat the trailing
  // sentence in quotes as flavor when present, otherwise it all renders as rules.
  const text = card.text || '';
  const flavorMatch = text.match(/(.*?)\s*("[^"]+\.")$/s);
  const rulesText = flavorMatch ? flavorMatch[1].trim() : text;
  const flavorText = flavorMatch ? flavorMatch[2] : '';

  return (
    <button
      onClick={onClick}
      className={`relative overflow-hidden ${selected ? 'ring-2 ring-amber-300 ring-offset-2 ring-offset-black' : ''} ${className}`}
      style={{ width, height, padding: 0, background: 'transparent', border: 0 }}
    >
      <PlateBackground style={style} variant={variant} size={size} />

      {/* Compleated oil drips along top edge */}
      {style.oil && <OilDrips width={width} />}

      {/* Praetor halo */}
      {style.halo && size === 'full' && <PraetorHalo size={Math.round(width * 0.32)} />}

      {/* Corner rivets — except for action (torn frame) */}
      {variant !== 'action' && <CornerRivets />}

      {/* INNER LAYOUT */}
      <div className="absolute inset-0 flex flex-col" style={{ padding: size === 'full' ? 10 : 6 }}>
        {/* HEADER: name + cost */}
        <div className="flex items-start justify-between gap-1.5" style={{ marginTop: size === 'full' ? 4 : 0 }}>
          <div
            className="phx-name truncate text-white"
            style={{
              fontSize: size === 'full' ? 13 : 9.5,
              lineHeight: 1.05,
              flex: 1,
              textShadow: '0 1px 0 rgba(0,0,0,0.95), 0 0 5px rgba(0,0,0,0.7)',
            }}
            title={card.name}
          >
            {card.name.toUpperCase()}
          </div>
          <CostCluster cost={card.mc_cost} size={size === 'full' ? 16 : 11} />
        </div>

        {/* TYPE LINE STRIP — only on full size */}
        {size === 'full' && (
          <div className="phx-typeline mt-2 px-2 py-1 flex items-center justify-between" style={{ borderLeft: `2px solid ${accent}80`, borderRight: `2px solid ${accent}80` }}>
            <div className="phx-mono uppercase tracking-[0.18em] text-[11px]" style={{ color: accent }}>
              {typeLine}
            </div>
            {variant === 'compleated' && (
              <span className="phx-sigil text-[14px]" style={{ color: '#9aff58', textShadow: '0 0 4px #2a5a18' }}>Φ</span>
            )}
          </div>
        )}

        {/* ART SLOT */}
        <div
          className="relative phx-noise overflow-hidden mt-2 flex items-center justify-center"
          style={{
            // Heavy black inset frame around art so it reads as set into the plate.
            background: `linear-gradient(180deg, #050304 0%, #0a0709 100%)`,
            border: `1px solid ${accent}55`,
            boxShadow: `inset 0 0 0 2px #000, inset 0 0 12px rgba(${hexToRgb(accent)}, 0.22)`,
            flexBasis: size === 'full' ? '46%' : '64%',
            flexGrow: 0,
            flexShrink: 0,
          }}
        >
          {card.image_url ? (
            <img
              src={card.image_url}
              alt={card.name}
              className="absolute inset-0 w-full h-full object-cover"
              style={{ filter: 'contrast(1.05) saturate(0.92)' }}
            />
          ) : (
            <ArtPlaceholder variant={variant} accent={accent} />
          )}
          {/* art-frame inner shadow vignette */}
          <div className="pointer-events-none absolute inset-0" style={{
            boxShadow: 'inset 0 0 24px rgba(0,0,0,0.55), inset 0 0 0 1px rgba(255,255,255,0.04)',
          }} />
        </div>

        {/* KEYWORD STRIP — full only */}
        {size === 'full' && keywords.length > 0 && (
          <div className="mt-2 flex items-center gap-1.5 flex-wrap">
            {keywords.map((k) => (
              <span
                key={k}
                className="inline-flex items-center gap-1 px-1.5 py-0.5"
                style={{
                  background: 'rgba(0,0,0,0.55)',
                  border: `1px solid ${style.glyphAccent}55`,
                  color: style.glyphAccent,
                  fontFamily: "'Cinzel', serif",
                  fontSize: 9.5,
                  letterSpacing: '0.14em',
                  textTransform: 'uppercase',
                }}
              >
                <KeywordGlyph keyword={k} color={style.glyphAccent} size={11} />
                {KEYWORD_LABEL[k.toLowerCase()] || k}
              </span>
            ))}
          </div>
        )}

        {/* RULES TEXT BOX — full only */}
        {size === 'full' && (
          <div
            className={`mt-2 flex-1 ${style.textbox} px-2 py-1.5 overflow-hidden`}
            style={{
              border: `1px solid ${accent}40`,
              boxShadow: `inset 0 0 0 1px rgba(0,0,0,0.6)`,
              minHeight: 64,
            }}
          >
            {rulesText && (
              <p className="phx-rules text-[11px] leading-snug" style={{ color: '#e9dcc4' }}>
                <FormattedText text={rulesText} italicClass="italic text-amber-200" />
              </p>
            )}
            {flavorText && (
              <p className="phx-rules italic text-[10px] leading-snug mt-1.5 pt-1.5" style={{ color: '#b29476', borderTop: `1px solid ${accent}30` }}>
                <FormattedText text={flavorText} italicClass="italic" />
              </p>
            )}
          </div>
        )}

        {/* FOOTER: type label (compact) + stat badge */}
        <div className="mt-1.5 flex items-end justify-between" style={{ minHeight: size === 'full' ? 28 : 20 }}>
          {size === 'compact' ? (
            <span className="phx-mono uppercase tracking-[0.2em] text-[8.5px]" style={{ color: accent }}>
              {style.typeLineLabel}
            </span>
          ) : (
            <span className="phx-mono uppercase tracking-[0.16em] text-[9.5px] opacity-60" style={{ color: accent }}>
              ⌬ {variant === 'praetor' ? 'NEW PHYREXIA · BEDROCK' : 'PHYREXIA BEDROCK EDITION'}
            </span>
          )}

          {hasStats && (isMob || isStructureLike || (card.types || []).includes('MC_TOOL')) && (
            <StatBadge
              power={card.power}
              toughness={card.toughness}
              variant={variant}
              accent={accent}
              size={size}
            />
          )}
        </div>
      </div>
    </button>
  );
}

// =============================================================================
// Stat badge
// =============================================================================

function StatBadge({
  power,
  toughness,
  variant,
  accent,
  size,
}: {
  power: number | null;
  toughness: number | null;
  variant: FrameVariant;
  accent: string;
  size: 'full' | 'compact';
}) {
  // Rendering rules:
  //   Mob/Compleated/Praetor/Boss: ATK / HP
  //   Structure/Block:             ⌂ HP
  //   Tool:                        nothing rendered here (cost is the only stat
  //                                relevant; weapon ATK appears in card text)
  const isStructure = variant === 'structure' || variant === 'block';
  const dim = size === 'full' ? 28 : 20;

  if (isStructure) {
    return (
      <span
        className="phx-mono inline-flex items-center justify-center"
        style={{
          width: size === 'full' ? 56 : 36,
          height: dim,
          background: 'linear-gradient(180deg, #131418 0%, #060709 100%)',
          border: `1px solid ${accent}80`,
          color: '#e8e8ee',
          fontSize: size === 'full' ? 18 : 13,
          letterSpacing: '0.05em',
          boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.08), inset 0 -1px 0 rgba(0,0,0,0.5)',
        }}
      >
        <span className="phx-sigil mr-1" style={{ color: accent, fontSize: size === 'full' ? 16 : 11 }}>⌂</span>
        {toughness ?? '-'}
      </span>
    );
  }

  if (variant === 'tool') return null;

  // Combat stats: power / toughness in a stamped iron plaque.
  return (
    <span
      className="phx-mono inline-flex items-center justify-center"
      style={{
        minWidth: size === 'full' ? 64 : 42,
        height: dim,
        background: 'linear-gradient(180deg, #2a0d12 0%, #0c0306 100%)',
        border: `1px solid ${accent}`,
        color: '#fff7d6',
        fontSize: size === 'full' ? 22 : 14,
        letterSpacing: '0.08em',
        padding: '0 6px',
        boxShadow: `inset 0 1px 0 rgba(255,200,120,0.18), inset 0 -1px 0 rgba(0,0,0,0.6), 0 0 8px rgba(${hexToRgb(accent)}, 0.45)`,
      }}
    >
      {power ?? '-'}<span className="opacity-50 mx-1">/</span>{toughness ?? '-'}
    </span>
  );
}

// =============================================================================
// Art placeholder — when no image_url is present yet.
// =============================================================================

function ArtPlaceholder({ variant, accent }: { variant: FrameVariant; accent: string }) {
  // Voxel silhouette specific to variant.
  const fill = accent;
  return (
    <svg viewBox="0 0 100 100" className="absolute inset-0 w-full h-full" preserveAspectRatio="xMidYMid slice">
      <defs>
        <linearGradient id={`bg-${variant}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#1a1014" />
          <stop offset="100%" stopColor="#040308" />
        </linearGradient>
        <pattern id={`grid-${variant}`} x="0" y="0" width="6" height="6" patternUnits="userSpaceOnUse">
          <rect width="6" height="6" fill="transparent" />
          <path d="M0 6 L6 6 M6 0 L6 6" stroke="rgba(255,255,255,0.04)" strokeWidth="0.5" />
        </pattern>
      </defs>
      <rect width="100" height="100" fill={`url(#bg-${variant})`} />
      <rect width="100" height="100" fill={`url(#grid-${variant})`} />

      {variant === 'praetor' || variant === 'boss' ? (
        <g fill={fill} fillOpacity={0.35}>
          {/* towering blocky idol */}
          <rect x="40" y="32" width="20" height="20" />
          <rect x="36" y="52" width="28" height="28" />
          <rect x="42" y="80" width="16" height="14" />
          <rect x="32" y="40" width="6" height="20" />
          <rect x="62" y="40" width="6" height="20" />
        </g>
      ) : variant === 'compleated' ? (
        <g fill={fill} fillOpacity={0.32}>
          {/* humanoid voxel with augments */}
          <rect x="44" y="28" width="12" height="12" />
          <rect x="38" y="40" width="24" height="24" />
          <rect x="32" y="46" width="6" height="18" />
          <rect x="62" y="46" width="6" height="18" />
          <rect x="44" y="64" width="6" height="22" />
          <rect x="50" y="64" width="6" height="22" />
          {/* augment glyphs */}
          <rect x="46" y="32" width="2" height="2" fill="#a31420" />
          <rect x="52" y="32" width="2" height="2" fill="#a31420" />
        </g>
      ) : variant === 'structure' || variant === 'block' ? (
        <g fill={fill} fillOpacity={0.28}>
          {/* squat structure */}
          <rect x="20" y="36" width="60" height="48" />
          <rect x="20" y="32" width="60" height="6" />
          <rect x="34" y="56" width="14" height="20" />
          <rect x="52" y="56" width="14" height="20" />
        </g>
      ) : variant === 'tool' ? (
        <g fill={fill} fillOpacity={0.4}>
          {/* sword silhouette */}
          <rect x="46" y="14" width="8" height="56" />
          <rect x="40" y="60" width="20" height="6" />
          <rect x="48" y="66" width="4" height="18" />
        </g>
      ) : variant === 'action' ? (
        <g fill={fill} fillOpacity={0.3}>
          {/* exploding rune */}
          <circle cx="50" cy="50" r="20" />
          <rect x="48" y="22" width="4" height="12" />
          <rect x="48" y="66" width="4" height="12" />
          <rect x="22" y="48" width="12" height="4" />
          <rect x="66" y="48" width="12" height="4" />
          <rect x="48" y="48" width="4" height="4" fill="#ffd060" />
        </g>
      ) : (
        <g fill={fill} fillOpacity={0.3}>
          {/* generic voxel beast */}
          <rect x="36" y="36" width="28" height="20" />
          <rect x="32" y="40" width="6" height="16" />
          <rect x="62" y="40" width="6" height="16" />
          <rect x="38" y="56" width="6" height="22" />
          <rect x="56" y="56" width="6" height="22" />
        </g>
      )}
      <text x="50" y="98" textAnchor="middle" fontFamily="VT323, monospace" fontSize="6" fill="rgba(255,255,255,0.35)">no art</text>
    </svg>
  );
}

export default PhyrexianCardFrame;
