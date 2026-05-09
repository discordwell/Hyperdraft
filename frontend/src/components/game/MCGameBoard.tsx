import { useEffect, useMemo, useState } from 'react';
import type { CardData, GameState, PlayerData } from '../../types';

const MATERIALS = [
  ['wood', 'Wood'],
  ['stone', 'Stone'],
  ['iron', 'Iron'],
  ['redstone', 'Redstone'],
  ['diamond', 'Diamond'],
] as const;

const COLUMN_COUNT = 3;

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
      className={`w-full text-left border-2 bg-slate-950/85 shadow-sm transition ${
        selected ? 'border-yellow-300' : isHostile ? 'border-red-700' : isStructure ? 'border-lime-700' : 'border-sky-700'
      } ${compact ? 'min-h-[58px] p-1.5' : 'min-h-[86px] p-2'} hover:border-white/70`}
    >
      <div className="flex items-start justify-between gap-1">
        <div className="min-w-0 text-[12px] font-bold text-white leading-tight break-words">{card.name}</div>
        {(card.power !== null || card.toughness !== null) && (
          <div className="shrink-0 rounded bg-black px-1 text-[11px] font-bold text-amber-100">
            {card.power ?? '-'} / {card.toughness ?? '-'}
          </div>
        )}
      </div>
      {!compact && <div className="mt-1 max-h-8 overflow-hidden text-[10px] text-slate-300 leading-snug">{card.text}</div>}
      {card.damage > 0 && <div className="mt-1 text-[10px] text-red-300">Damage {card.damage}</div>}
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

  const handleHandClick = (card: CardData) => {
    if (!canPlayCard(card)) return;
    if (card.types.includes('MC_STRUCTURE') || card.types.includes('MC_BLOCK')) {
      setPlacingCard(card);
      return;
    }
    onPlayCard(card.id);
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
                    <div key={card.id} className="border border-slate-800 bg-black/20 p-1">
                      <CardTile card={card} selected={placingCard?.id === card.id} onClick={() => handleHandClick(card)} />
                      <div className="mt-1 text-[10px] text-slate-300"><Cost cost={card.mc_cost} /></div>
                    </div>
                  ))}
                </div>
              </div>
            </section>
          </div>

          <div className="space-y-3 overflow-y-auto">
            <Grid
              title="Your 3x3 Base"
              rows={myGrid}
              exposed={[]}
              isMine
              placing={placingCard}
              onCell={(x, y) => {
                if (!placingCard) return;
                onPlayCard(placingCard.id, { x, y });
                setPlacingCard(null);
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
