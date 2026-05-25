import { useEffect, useMemo, useState } from 'react';
import type { CardData, GameState, PlayerData } from '../../types';
import { getMinecraftArtPaths } from '../../utils/cardArt';
import { useCardInspector } from '../../hooks/useCardInspector';
import { useHandCard } from '../../hooks/useHandCard';
import { useCardZone } from '../../hooks/useCardZone';
import ZoneHighlight from '../cards/ZoneHighlight';

const MATERIALS = [
  ['wood', 'Wood'],
  ['stone', 'Stone'],
  ['iron', 'Iron'],
  ['redstone', 'Redstone'],
  ['diamond', 'Diamond'],
] as const;

const COLUMN_COUNT = 3;

// Shared card-zone primitive — engine constants.
// Drop zones are scoped to the viewer's own 3x3 base columns; the opponent
// grid is read-only so it never appears in any hand card's validZones.
const MC_ENGINE_ID = 'minecraft';
const MC_ACCENT = '#a3e635'; // grass / leaves green
const MC_COLUMN_ZONE_ME = (col: number) => `mc-column-${col}-me`;

interface MCGameBoardProps {
  gameState: GameState;
  playerId: string;
  opponentId: string | null;
  myPlayer: PlayerData | null;
  opponentPlayer: PlayerData | null;
  myMobs: CardData[];
  opponentMobs: CardData[];
  isMyTurn: boolean;
  canPlayCard: (card: CardData) => boolean;
  canUseMob: (card: CardData) => boolean;
  canBlockMob: (card: CardData) => boolean;
  onPlayCard: (cardId: string, cell?: { x: number; y: number }, targetColumn?: number) => void;
  onMineWorker: (workerId: string, biomeIndex: number) => void;
  onAvatarMine: (biomeIndex: number) => void;
  onAvatarExplore: (biomeIndex: number) => void;
  onAvatarAttack: (targetColumn: number) => void;
  onAttack: (attackerId: string, targetColumn: number) => void;
  onDeclareBlockers: (blockers: { attacker_id: string; blocker_id: string }[]) => void;
  onEndTurn: () => void;
}

interface MCCombatPrompt {
  phase?: string;
  attacking_player?: string;
  defending_player?: string;
  attackers?: { attacker_id: string; target_id?: string }[];
  legal_blockers?: string[];
}

function Cost({ cost }: { cost?: Record<string, number> }) {
  const entries = Object.entries(cost || {}).filter(([, v]) => v > 0);
  if (!entries.length) return <span className="text-emerald-200">Free</span>;
  return (
    <span className="flex flex-wrap gap-1">
      {entries.map(([k, v]) => <span key={k} className="rounded bg-black/30 px-1.5 py-0.5">{k[0].toUpperCase()}{v}</span>)}
    </span>
  );
}

/**
 * Minecraft card art slot. Renders the on-disk PNG at
 * `/api/card-art/minecraft/<slug>.png` (or the backend-supplied `image_url`)
 * underneath the existing CardTile chrome, falling back to a small voxel
 * glyph when art is missing — matches Minecraft's block idiom and never
 * leaves the slot empty.
 */
function MCCardArt({ card }: { card: CardData }) {
  const paths = useMemo(
     () => getMinecraftArtPaths(card.name, card.image_url ?? null),
     [card.name, card.image_url],
  );
  const [idx, setIdx] = useState(0);
  const [failed, setFailed] = useState(false);

  // Reset fallback state if the card identity (or its image_url) changes.
  useEffect(() => {
    setIdx(0);
    setFailed(false);
  }, [card.id, card.image_url]);

  if (!paths.length || failed) {
    // Voxel "block" mark — geometric, ink-coloured, matches MC's pixel idiom.
    return (
      <div
        data-testid="mc-card-art-fallback"
        aria-hidden="true"
        className="absolute inset-0 flex items-center justify-center bg-slate-900/60"
      >
        <svg
          viewBox="0 0 16 16"
          shapeRendering="crispEdges"
          className="h-1/2 w-1/2 opacity-60"
          aria-hidden="true"
        >
          <rect x="2"  y="2" width="6" height="6" fill="#94a3b8" />
          <rect x="8"  y="2" width="6" height="6" fill="#64748b" />
          <rect x="2"  y="8" width="6" height="6" fill="#475569" />
          <rect x="8"  y="8" width="6" height="6" fill="#334155" />
        </svg>
      </div>
    );
  }

  return (
    <img
      src={paths[idx]}
      alt=""
      aria-hidden="true"
      loading="lazy"
      className="absolute inset-0 h-full w-full object-cover opacity-80"
      onError={() => {
        if (idx < paths.length - 1) {
          setIdx((prev) => prev + 1);
        } else {
          setFailed(true);
        }
      }}
    />
  );
}

function CardTile({
  card,
  compact = false,
  selected = false,
  onClick,
}: {
  card: CardData;
  compact?: boolean;
  selected?: boolean;
  onClick?: () => void;
}) {
  const isHostile = card.subtypes.includes('Hostile');
  const isStructure = card.types.includes('MC_STRUCTURE') || card.types.includes('MC_BLOCK');
  return (
    <button
      onClick={onClick}
      className={`relative w-full overflow-hidden text-left border-2 bg-slate-950/85 shadow-sm transition ${
        selected ? 'border-yellow-300' : isHostile ? 'border-red-700' : isStructure ? 'border-lime-700' : 'border-sky-700'
      } ${compact ? 'min-h-[58px] p-1.5' : 'min-h-[86px] p-2'} hover:border-white/70`}
    >
      <MCCardArt card={card} />
      {/* Darken the art so the existing white/amber chrome stays readable
          without changing colours or layout of the frame itself. */}
      <div className="pointer-events-none absolute inset-0 bg-gradient-to-b from-black/30 via-black/55 to-black/80" />
      <div className="relative flex items-start justify-between gap-1">
        <div className="min-w-0 text-[12px] font-bold text-white leading-tight break-words">{card.name}</div>
        {(card.power !== null || card.toughness !== null) && (
          <div className="shrink-0 rounded bg-black px-1 text-[11px] font-bold text-amber-100">
            {card.power ?? '-'} / {card.toughness ?? '-'}
          </div>
        )}
      </div>
      {!compact && <div className="relative mt-1 max-h-8 overflow-hidden text-[10px] text-slate-300 leading-snug">{card.text}</div>}
      {card.damage > 0 && <div className="relative mt-1 text-[10px] text-red-300">Damage {card.damage}</div>}
    </button>
  );
}

function Grid({
  title,
  rows,
  exposed,
  isMine,
  placing,
  onCell,
}: {
  title: string;
  rows: (CardData | null)[][];
  exposed: string[];
  isMine: boolean;
  placing: CardData | null;
  onCell: (x: number, y: number) => void;
}) {
  return (
    <section className="min-w-0">
      <div className="mb-1 flex items-center justify-between">
        <div className="text-xs font-bold uppercase tracking-wide text-stone-200">{title}</div>
        {isMine && placing && <div className="text-[11px] text-yellow-200">Place {placing.name}</div>}
      </div>
      <div className="grid grid-cols-3 gap-1">
        {rows.map((row, y) => row.map((card, x) => (
          <button
            key={`${x}-${y}`}
            onClick={() => onCell(x, y)}
            disabled={!isMine || !placing || !!card}
            className={`aspect-square border bg-[linear-gradient(135deg,#254d31_0_50%,#2f5938_50%)] p-1 text-left transition ${
              card && exposed.includes(card.id) ? 'border-red-300' : 'border-black/40'
            } ${!card && isMine && placing ? 'hover:border-yellow-300' : ''}`}
          >
            {card ? <CardTile card={card} compact /> : <div className="h-full border border-white/5 bg-black/10" />}
          </button>
        )))}
      </div>
    </section>
  );
}

/**
 * Player-side 3x3 base, laid out as three column drop zones. Each column is
 * a `useCardZone` target: dropping or click-priming + clicking a column
 * fires `onColumnPlay(card, col)`. Cells inside the column still drive the
 * legacy onCell click flow so cell-specific placement (structures / blocks)
 * keeps working after the drop. The opponent's read-only grid continues to
 * use the original `Grid` component.
 */
function MyGridZones({
  rows,
  placing,
  onCell,
  onColumnPlay,
}: {
  rows: (CardData | null)[][];
  placing: CardData | null;
  onCell: (x: number, y: number) => void;
  onColumnPlay: (cardId: string, col: number) => void;
}) {
  return (
    <section className="min-w-0">
      <div className="mb-1 flex items-center justify-between">
        <div className="text-xs font-bold uppercase tracking-wide text-stone-200">Your 3x3 Base</div>
        {placing && <div className="text-[11px] text-yellow-200">Place {placing.name}</div>}
      </div>
      <div className="grid grid-cols-3 gap-1">
        {[0, 1, 2].map((col) => (
          <MCColumnZone
            key={`col-${col}`}
            col={col}
            rows={rows}
            placing={placing}
            onCell={onCell}
            onColumnPlay={onColumnPlay}
          />
        ))}
      </div>
    </section>
  );
}

function MCColumnZone({
  col,
  rows,
  placing,
  onCell,
  onColumnPlay,
}: {
  col: number;
  rows: (CardData | null)[][];
  placing: CardData | null;
  onCell: (x: number, y: number) => void;
  onColumnPlay: (cardId: string, col: number) => void;
}) {
  const zone = useCardZone({
    zoneId: MC_COLUMN_ZONE_ME(col),
    engineId: MC_ENGINE_ID,
    onPlay: (cardId) => onColumnPlay(cardId, col),
  });
  return (
    <div
      className="relative flex flex-col gap-1"
      onClick={zone.onClick}
      onDragOver={zone.onDragOver}
      onDragLeave={zone.onDragLeave}
      onDrop={zone.onDrop}
      style={{ cursor: zone.isValid ? 'pointer' : 'default' }}
      aria-label={`Column ${col + 1} drop zone`}
    >
      <ZoneHighlight
        isValid={zone.isValid}
        isHovered={zone.isHovered}
        hasActiveCard={zone.hasActiveCard}
        activeAccent={zone.activeAccent}
      />
      {[0, 1, 2].map((y) => {
        const card = rows[y]?.[col] ?? null;
        return (
          <button
            key={`${col}-${y}`}
            onClick={() => {
              // When a card is primed and this column is valid, the outer
              // column click handles the play via `zone.onClick` (the cell
              // button is disabled while `placing` is null, so this branch
              // only fires from the structure / block cell-picker flow).
              if (zone.isValid) return;
              onCell(col, y);
            }}
            disabled={!placing || !!card}
            className={`aspect-square border bg-[linear-gradient(135deg,#254d31_0_50%,#2f5938_50%)] p-1 text-left transition border-black/40 ${
              !card && placing ? 'hover:border-yellow-300' : ''
            }`}
          >
            {card ? <CardTile card={card} compact /> : <div className="h-full border border-white/5 bg-black/10" />}
          </button>
        );
      })}
    </div>
  );
}

/**
 * Single hand card slot. Wraps the existing CardTile in the shared
 * `useHandCard` primitive so the card can be clicked (prime) or dragged
 * onto one of the three column drop zones. The inspector modal still opens
 * on click — both flows are independent (matching Cats / Clankers).
 */
function MCHandCard({
  card,
  playable,
  selected,
  onInspect,
}: {
  card: CardData;
  playable: boolean;
  selected: boolean;
  onInspect: () => void;
}) {
  const handCard = useHandCard({
    cardId: card.id,
    cardName: card.name,
    engineId: MC_ENGINE_ID,
    accent: MC_ACCENT,
    validZones: playable
      ? [MC_COLUMN_ZONE_ME(0), MC_COLUMN_ZONE_ME(1), MC_COLUMN_ZONE_ME(2)]
      : [],
    disabled: !playable,
  });
  return (
    <div
      draggable={handCard.draggable}
      onDragStart={handCard.onDragStart}
      onDragEnd={handCard.onDragEnd}
      className="border border-slate-800 bg-black/20 p-1"
      style={{
        cursor: handCard.draggable ? 'grab' : 'pointer',
        transform: handCard.isPrimed ? 'translateY(-4px)' : undefined,
        filter: handCard.isPrimed ? `drop-shadow(0 0 8px ${MC_ACCENT})` : undefined,
        transition: 'transform 120ms ease, filter 120ms ease',
      }}
    >
      <CardTile
        card={card}
        selected={selected}
        onClick={() => {
          handCard.onClick();
          onInspect();
        }}
      />
      <div className="mt-1 text-[10px] text-slate-300"><Cost cost={card.mc_cost} /></div>
    </div>
  );
}

function BiomeRow({
  biomes,
  canAvatarAct,
  isMyTurn,
  workers,
  onAvatarMine,
  onAvatarExplore,
  onMineWorker,
}: {
  biomes: { name: string; yields: Record<string, number>; mined?: boolean; level?: number }[];
  canAvatarAct: boolean;
  isMyTurn: boolean;
  workers: CardData[];
  onAvatarMine: (idx: number) => void;
  onAvatarExplore: (idx: number) => void;
  onMineWorker: (workerId: string, idx: number) => void;
}) {
  const [workerId, setWorkerId] = useState<string>('');
  return (
    <div className="grid grid-cols-[repeat(auto-fit,minmax(94px,1fr))] gap-2">
      {biomes.map((b, idx) => (
        <div key={`${b.name}-${idx}`} className={`border p-2 ${b.mined ? 'border-slate-700 bg-slate-900/70' : 'border-emerald-700 bg-emerald-950/50'}`}>
          <div className="text-sm font-bold text-emerald-100">{b.name}</div>
          <div className="mt-1 text-[11px] text-slate-300">
            {Object.entries(b.yields || {}).map(([k, v]) => `${k} ${v}`).join(' / ')}
          </div>
          <div className="mt-2 flex flex-wrap gap-1">
            <button disabled={!canAvatarAct || b.mined} onClick={() => onAvatarMine(idx)} className="bg-emerald-700 px-2 py-1 text-[11px] font-bold text-white disabled:opacity-40">Avatar</button>
            <button disabled={!isMyTurn || b.mined || !workerId} onClick={() => workerId && onMineWorker(workerId, idx)} className="bg-sky-700 px-2 py-1 text-[11px] font-bold text-white disabled:opacity-40">Worker</button>
            <button disabled={!canAvatarAct} onClick={() => onAvatarExplore(idx)} className="bg-violet-700 px-2 py-1 text-[11px] font-bold text-white disabled:opacity-40">Explore</button>
          </div>
        </div>
      ))}
      <select value={workerId} onChange={(e) => setWorkerId(e.target.value)} className="col-span-full bg-slate-900 border border-slate-700 px-2 py-1 text-xs text-slate-100">
        <option value="">Select worker</option>
        {workers.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}
      </select>
    </div>
  );
}

export function MCGameBoard({
  gameState,
  playerId,
  opponentId,
  myPlayer,
  opponentPlayer,
  myMobs,
  opponentMobs,
  isMyTurn,
  canPlayCard,
  canUseMob,
  canBlockMob,
  onPlayCard,
  onMineWorker,
  onAvatarMine,
  onAvatarExplore,
  onAvatarAttack,
  onAttack,
  onDeclareBlockers,
  onEndTurn,
}: MCGameBoardProps) {
  const [placingCard, setPlacingCard] = useState<CardData | null>(null);
  const [blockAssignments, setBlockAssignments] = useState<Record<string, string>>({});
  const [attackingMobId, setAttackingMobId] = useState<string | null>(null);
  const [avatarTargeting, setAvatarTargeting] = useState(false);
  const [showOppBiomes, setShowOppBiomes] = useState(false);
  const inspector = useCardInspector();

  const myGrid = gameState.minecraft_grid?.[playerId] || Array.from({ length: COLUMN_COUNT }, () => Array(COLUMN_COUNT).fill(null));
  const oppGrid = opponentId
    ? gameState.minecraft_grid?.[opponentId] || Array.from({ length: COLUMN_COUNT }, () => Array(COLUMN_COUNT).fill(null))
    : Array.from({ length: COLUMN_COUNT }, () => Array(COLUMN_COUNT).fill(null));
  const myBiomes = gameState.minecraft_biomes?.[playerId] || [];
  const oppBiomes = opponentId ? (gameState.minecraft_biomes?.[opponentId] || []) : [];

  // Frontmost-per-column on opponent grid (what each column attack would hit).
  const columnFrontmost: (CardData | null)[] = useMemo(() => {
    const out: (CardData | null)[] = [];
    for (let col = 0; col < COLUMN_COUNT; col += 1) {
      let occupant: CardData | null = null;
      for (let y = COLUMN_COUNT - 1; y >= 0; y -= 1) {
        const cell = oppGrid[y]?.[col];
        if (cell) { occupant = cell as CardData; break; }
      }
      out.push(occupant);
    }
    return out;
  }, [oppGrid]);

  const gearNames = useMemo(() => {
    const all = gameState.battlefield;
    const gear = myPlayer?.mc_avatar_gear || {};
    return Object.fromEntries(Object.entries(gear).map(([slot, id]) => [slot, all.find((c) => c.id === id)?.name || 'Empty']));
  }, [gameState.battlefield, myPlayer?.mc_avatar_gear]);

  const combatPrompt = (gameState.minecraft_combat || {}) as MCCombatPrompt;
  const pendingAttacks = combatPrompt.attackers || [];
  const isBlocking = combatPrompt.phase === 'declare_blockers' && combatPrompt.defending_player === playerId;
  const attackKey = pendingAttacks.map((a) => a.attacker_id).join('|');
  const attackingCards = useMemo(() => pendingAttacks
    .map((attack) => ({
      attack,
      card: gameState.battlefield.find((c) => c.id === attack.attacker_id) || null,
      target: attack.target_id === opponentId
        ? 'Avatar'
        : gameState.battlefield.find((c) => c.id === attack.target_id)?.name || 'Target',
    }))
    .filter((entry) => entry.card), [pendingAttacks, gameState.battlefield, opponentId]);
  const blockableMobs = useMemo(() => {
    const legal = new Set(combatPrompt.legal_blockers || []);
    return myMobs.filter((mob) => canBlockMob(mob) && (!legal.size || legal.has(mob.id)));
  }, [combatPrompt.legal_blockers, myMobs, canBlockMob]);

  // Per-attacker eligibility: aerial attackers can only be blocked by aerial / reach.
  const blockersForAttacker = (attackerCard: CardData | null) => {
    if (!attackerCard) return blockableMobs;
    const attackerKw = new Set((attackerCard.mc_keywords || []).map((k) => k.toLowerCase()));
    if (!attackerKw.has('aerial')) return blockableMobs;
    return blockableMobs.filter((mob) => {
      const kw = new Set((mob.mc_keywords || []).map((k) => k.toLowerCase()));
      return kw.has('aerial') || kw.has('reach');
    });
  };

  useEffect(() => {
    setBlockAssignments({});
  }, [isBlocking, attackKey]);

  const submitBlocks = (assignments: Record<string, string>) => {
    const blockers = Object.entries(assignments)
      .filter(([, blockerId]) => blockerId)
      .map(([attacker_id, blocker_id]) => ({ attacker_id, blocker_id }));
    onDeclareBlockers(blockers);
  };

  // Resolve the actual play once the user confirms in the inspector.
  // For structures / blocks, we still want the existing column-pick flow
  // on the 3x3 grid — Play just stages the card via setPlacingCard, and
  // the next grid cell click commits via onPlayCard(id, {x,y}).
  const resolveHandPlay = (card: CardData) => {
    if (card.types.includes('MC_STRUCTURE') || card.types.includes('MC_BLOCK')) {
      setPlacingCard(card);
      return;
    }
    onPlayCard(card.id);
  };

  // Format the MC mana-cost record as a compact "W2 S1" string for the modal.
  const formatMcCost = (cost?: Record<string, number>): string | undefined => {
    if (!cost) return undefined;
    const entries = Object.entries(cost).filter(([, v]) => v > 0);
    if (!entries.length) return 'Free';
    return entries.map(([k, v]) => `${k[0].toUpperCase()}${v}`).join(' ');
  };

  const handleHandClick = (card: CardData) => {
    const playable = canPlayCard(card);
    const stats =
      card.power !== null || card.toughness !== null
        ? `${card.power ?? '-'} / ${card.toughness ?? '-'}`
        : undefined;
    const types = card.types.map((t) => t.replace(/^MC_/, '')).join(' · ');
    const subtypes = card.subtypes.length ? card.subtypes.join(' · ') : '';
    const subtitle = [types, subtypes].filter(Boolean).join(' — ');
    inspector.open(
      {
        id: card.id,
        name: card.name,
        text: card.text,
        cost: formatMcCost(card.mc_cost),
        stats,
        subtitle,
        engine: 'minecraft',
      },
      [
        {
          label: 'Play',
          variant: 'primary',
          disabled: !playable,
          disabledReason: !playable ? 'Cannot play this card right now' : undefined,
          onClick: () => {
            resolveHandPlay(card);
          },
        },
      ],
    );
  };

  const handleColumnAttack = (column: number) => {
    if (avatarTargeting) {
      onAvatarAttack(column);
      setAvatarTargeting(false);
      return;
    }
    if (attackingMobId) {
      onAttack(attackingMobId, column);
      setAttackingMobId(null);
    }
  };

  const isTargeting = !!attackingMobId || avatarTargeting;

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <div className="grid min-h-screen grid-rows-[auto_1fr_auto] gap-3 p-3">
        <header className="grid grid-cols-1 items-center gap-3 border-b border-slate-800 pb-2 sm:grid-cols-[1fr_auto_1fr]">
          <div>
            <div className="text-xs uppercase tracking-wide text-slate-500">Opponent</div>
            <div className="text-xl font-black text-red-200">{opponentPlayer?.name || 'Opponent'} {opponentPlayer?.life ?? 20} HP</div>
          </div>
          <div className={`border px-5 py-2 text-center ${gameState.minecraft_day_phase === 'night' ? 'border-indigo-400 bg-indigo-950 text-indigo-100' : 'border-yellow-300 bg-yellow-900/40 text-yellow-100'}`}>
            <div className="text-xs uppercase tracking-widest">Cycle</div>
            <div className="text-2xl font-black">{(gameState.minecraft_day_phase || 'day').toUpperCase()}</div>
          </div>
          <div className="text-right">
            <div className="text-xs uppercase tracking-wide text-slate-500">You</div>
            <div className="text-xl font-black text-emerald-200">{myPlayer?.name || 'Player'} {myPlayer?.life ?? 20} HP</div>
          </div>
        </header>

        <main className="grid grid-cols-1 gap-3 overflow-y-auto xl:grid-cols-[minmax(220px,300px)_minmax(360px,1fr)_minmax(220px,320px)] xl:overflow-hidden">
          <div className="space-y-3 overflow-y-auto">
            <section>
              <div className="mb-1 flex items-center justify-between">
                <div className="text-xs font-bold uppercase tracking-wide text-stone-200">Opponent Base</div>
                {isTargeting && <div className="text-[11px] text-yellow-200">Pick a column</div>}
              </div>
              {/* Column-attack targets sit above the grid so it's clear what each column hits. */}
              <div className="mb-2 grid grid-cols-3 gap-1">
                {columnFrontmost.map((occupant, col) => (
                  <button
                    key={`coltarget-${col}`}
                    disabled={!isTargeting}
                    onClick={() => handleColumnAttack(col)}
                    className={`border p-1.5 text-[11px] font-bold transition ${
                      isTargeting
                        ? 'border-yellow-400 bg-yellow-900/30 text-yellow-100 hover:bg-yellow-700/40'
                        : occupant ? 'border-red-700 bg-slate-900 text-red-200' : 'border-slate-700 bg-slate-900 text-emerald-200'
                    }`}
                  >
                    <div className="text-[9px] uppercase tracking-wide opacity-70">Col {col + 1}</div>
                    <div className="truncate">{occupant ? occupant.name : 'Avatar'}</div>
                  </button>
                ))}
              </div>
              <Grid title="" rows={oppGrid} exposed={[]} isMine={false} placing={null} onCell={() => undefined} />
            </section>
            <section>
              <div className="mb-1 text-xs font-bold uppercase tracking-wide text-slate-300">Opponent Mobs</div>
              <div className="grid grid-cols-2 gap-2">
                {opponentMobs.map((card) => <CardTile key={card.id} card={card} />)}
              </div>
            </section>
            <section>
              <div className="mb-1 flex items-center justify-between">
                <div className="text-xs font-bold uppercase tracking-wide text-slate-300">Opponent Biomes</div>
                <button
                  onClick={() => setShowOppBiomes((v) => !v)}
                  className="border border-slate-700 bg-slate-900 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-slate-300 hover:border-slate-500 hover:text-slate-100"
                >
                  {showOppBiomes ? 'Hide' : 'Reveal'}
                </button>
              </div>
              {showOppBiomes ? (
                <div className="grid grid-cols-[repeat(auto-fit,minmax(94px,1fr))] gap-2">
                  {oppBiomes.map((b, idx) => (
                    <div
                      key={`opp-${b.name}-${idx}`}
                      className={`border p-2 ${b.mined ? 'border-slate-700 bg-slate-900/70' : 'border-emerald-700 bg-emerald-950/50'}`}
                    >
                      <div className="flex items-baseline justify-between gap-1">
                        <div className="text-sm font-bold text-emerald-100">{b.name}</div>
                        {b.level ? <div className="text-[10px] text-slate-400">L{b.level}</div> : null}
                      </div>
                      <div className="mt-1 text-[11px] text-slate-300">
                        {Object.entries(b.yields || {}).map(([k, v]) => `${k} ${v}`).join(' / ')}
                      </div>
                    </div>
                  ))}
                  {!oppBiomes.length && <div className="text-[11px] text-slate-500">No biome data.</div>}
                </div>
              ) : (
                <div className="border border-dashed border-slate-700 bg-black/20 px-2 py-3 text-center text-[11px] text-slate-500">
                  Hidden. Click Reveal to see exploration progress.
                </div>
              )}
            </section>
          </div>

          <div className="flex min-w-0 flex-col gap-3 overflow-hidden">
            {isBlocking && (
              <section className="border-2 border-orange-500 bg-orange-950/50 p-3">
                <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <div className="text-xs font-bold uppercase tracking-wide text-orange-200">Declare Blocks</div>
                    <div className="text-sm text-orange-100">Choose blockers for the incoming attack, or take the hit.</div>
                  </div>
                  <div className="flex gap-2">
                    <button
                      onClick={() => submitBlocks(blockAssignments)}
                      className="bg-emerald-700 px-3 py-1.5 text-xs font-black text-white"
                    >
                      Submit Blocks
                    </button>
                    <button
                      onClick={() => submitBlocks({})}
                      className="bg-slate-800 px-3 py-1.5 text-xs font-black text-white"
                    >
                      Take Damage
                    </button>
                  </div>
                </div>
                <div className="grid gap-2">
                  {attackingCards.map(({ attack, card, target }) => {
                    const assignedElsewhere = new Set(
                      Object.entries(blockAssignments)
                        .filter(([attackerId]) => attackerId !== attack.attacker_id)
                        .map(([, blockerId]) => blockerId),
                    );
                    const eligible = blockersForAttacker(card);
                    const isAerial = (card?.mc_keywords || []).map((k) => k.toLowerCase()).includes('aerial');
                    return (
                      <div key={attack.attacker_id} className="grid gap-2 border border-orange-800 bg-black/25 p-2 sm:grid-cols-[1fr_1fr]">
                        {card && <CardTile card={card} compact />}
                        <div className="grid content-center gap-1">
                          <div className="text-[11px] uppercase tracking-wide text-orange-200">
                            Targeting {target}{isAerial && <span className="ml-1 text-cyan-300">· Aerial</span>}
                          </div>
                          <select
                            value={blockAssignments[attack.attacker_id] || ''}
                            onChange={(e) => setBlockAssignments((prev) => ({ ...prev, [attack.attacker_id]: e.target.value }))}
                            className="border border-orange-800 bg-slate-950 px-2 py-1 text-xs text-slate-100"
                          >
                            <option value="">No block</option>
                            {eligible
                              .filter((mob) => !assignedElsewhere.has(mob.id) || blockAssignments[attack.attacker_id] === mob.id)
                              .map((mob) => <option key={mob.id} value={mob.id}>{mob.name} ({mob.power}/{mob.toughness})</option>)}
                          </select>
                          {isAerial && eligible.length === 0 && (
                            <div className="text-[10px] text-orange-300">No Aerial / Reach defender.</div>
                          )}
                        </div>
                      </div>
                    );
                  })}
                  {!blockableMobs.length && <div className="text-sm text-orange-100">No ready mobs can block.</div>}
                </div>
              </section>
            )}

            <section className="border border-slate-800 bg-slate-900/60 p-3">
              <div className="mb-2 flex items-center justify-between">
                <div className="text-xs font-bold uppercase tracking-wide text-slate-300">Materials</div>
                <button onClick={onEndTurn} disabled={!isMyTurn} className="shrink-0 bg-red-700 px-4 py-1.5 text-sm font-black text-white disabled:opacity-40">End Turn</button>
              </div>
              <div className="grid grid-cols-[repeat(auto-fit,minmax(70px,1fr))] gap-2">
                {MATERIALS.map(([key, label]) => (
                  <div key={key} className="border border-slate-700 bg-black/30 p-2 text-center">
                    <div className="break-words text-[11px] text-slate-400">{label}</div>
                    <div className="text-xl font-black">{myPlayer?.mc_materials?.[key] || 0}</div>
                  </div>
                ))}
              </div>
            </section>

            <section className="border border-slate-800 bg-slate-900/60 p-3">
              <div className="mb-2 text-xs font-bold uppercase tracking-wide text-slate-300">Biomes</div>
              <BiomeRow
                biomes={myBiomes}
                canAvatarAct={isMyTurn && !myPlayer?.mc_avatar_action_used}
                isMyTurn={isMyTurn}
                workers={myMobs.filter((mob) => canUseMob(mob) && mob.subtypes.includes('Worker'))}
                onAvatarMine={onAvatarMine}
                onAvatarExplore={onAvatarExplore}
                onMineWorker={onMineWorker}
              />
            </section>

            <section className="grid flex-1 grid-rows-2 gap-3 overflow-hidden">
              <div className="overflow-y-auto border border-slate-800 bg-slate-900/50 p-2">
                <div className="mb-1 text-xs font-bold uppercase tracking-wide text-slate-300">Your Mobs</div>
                <div className="grid grid-cols-[repeat(auto-fit,minmax(112px,1fr))] gap-2">
                  {myMobs.map((card) => {
                    const targeting = attackingMobId === card.id;
                    return (
                      <div key={card.id} className={targeting ? 'border border-yellow-400 p-0.5' : ''}>
                        <CardTile card={card} selected={targeting} />
                        <button
                          disabled={!canUseMob(card)}
                          onClick={() => {
                            setAvatarTargeting(false);
                            setAttackingMobId(targeting ? null : card.id);
                          }}
                          className={`mt-1 w-full px-2 py-1 text-[11px] font-bold text-white disabled:opacity-40 ${targeting ? 'bg-yellow-600' : 'bg-orange-700'}`}
                        >
                          {targeting ? 'Cancel' : 'Attack'}
                        </button>
                      </div>
                    );
                  })}
                </div>
              </div>
              <div className="overflow-y-auto border border-slate-800 bg-slate-900/50 p-2">
                <div className="mb-1 text-xs font-bold uppercase tracking-wide text-slate-300">Hand</div>
                <div className="grid grid-cols-[repeat(auto-fit,minmax(118px,1fr))] gap-2">
                  {gameState.hand.map((card) => (
                    <MCHandCard
                      key={card.id}
                      card={card}
                      playable={canPlayCard(card)}
                      selected={placingCard?.id === card.id}
                      onInspect={() => handleHandClick(card)}
                    />
                  ))}
                </div>
              </div>
            </section>
          </div>

          <div className="space-y-3 overflow-y-auto">
            <MyGridZones
              rows={myGrid}
              placing={placingCard}
              onCell={(x, y) => {
                if (!placingCard) return;
                onPlayCard(placingCard.id, { x, y });
                setPlacingCard(null);
              }}
              onColumnPlay={(cardId, col) => {
                const card = gameState.hand.find((c) => c.id === cardId);
                if (!card) return;
                // Structures / blocks need a specific cell — defer to the
                // existing cell-picker via placingCard. The user drags onto
                // the column, then clicks a cell in that column to commit.
                if (
                  card.types.includes('MC_STRUCTURE') ||
                  card.types.includes('MC_BLOCK')
                ) {
                  setPlacingCard(card);
                  return;
                }
                // Everything else plays into the column directly.
                onPlayCard(card.id, undefined, col);
              }}
            />
            <section className="border border-slate-800 bg-slate-900/60 p-3">
              <div className="text-xs font-bold uppercase tracking-wide text-slate-300">Avatar Gear</div>
              <div className="mt-2 grid gap-2 text-sm">
                {['weapon', 'armor', 'tool'].map((slot) => (
                  <div key={slot} className="flex justify-between border border-slate-700 bg-black/30 px-2 py-1">
                    <span className="capitalize text-slate-400">{slot}</span>
                    <span className="font-bold text-slate-100">{gearNames[slot] || 'Empty'}</span>
                  </div>
                ))}
              </div>
              <button
                disabled={!isMyTurn || !!myPlayer?.mc_avatar_action_used}
                onClick={() => {
                  setAttackingMobId(null);
                  setAvatarTargeting(!avatarTargeting);
                }}
                className={`mt-3 w-full px-3 py-2 text-sm font-black text-white disabled:opacity-40 ${avatarTargeting ? 'bg-yellow-600' : 'bg-cyan-700'}`}
              >
                {avatarTargeting ? 'Cancel Avatar Attack' : 'Avatar Attack'}
              </button>
            </section>
          </div>
        </main>

        <footer className="border-t border-slate-800 pt-2 text-xs text-slate-400">
          {isBlocking ? 'Choose blockers for the incoming attack.' : (isMyTurn ? 'Your turn: craft, mine, attack, then end turn.' : 'Waiting for opponent.')}
          {placingCard && <span className="ml-3 text-yellow-200">Select an empty cell for {placingCard.name}.</span>}
        </footer>
      </div>
    </div>
  );
}
