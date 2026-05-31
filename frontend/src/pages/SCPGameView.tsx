/**
 * SCPGameView — SCP: SECURE / CONTAIN / SUBVERT (asymmetric Foundation vs Chaos Insurgency).
 *
 * Functional fog-of-war board. The Foundation builds containment cells (face-down anomalies
 * advanced "in the open" — token count public, identity not — behind layer stacks); the Chaos
 * Insurgency builds a rig of breakers and infiltrates. Dossier aesthetic: dark slate, monospace
 * stat lines, [CLASSIFIED] / [FACE-DOWN] bars for anything the viewer can't see.
 *
 * Self-bootstraps from the route (mirrors GameView's spectator join) so a direct
 * /game/:matchId/scp link works; reads the viewer-redacted state via useSCPGame.
 */
import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useGameStore } from '../stores/gameStore';
import { matchAPI } from '../services/api';
import {
  useSCPGame,
  type SCPCard,
  type SCPCell,
  type SCPSeat,
} from '../hooks/useSCPGame';

const ACCENT = { foundation: '#a78bfa', insurgency: '#f87171' } as const;

function Bar({ label, value, target, color }: { label: string; value: number; target: number; color: string }) {
  const pct = Math.min(100, Math.round((value / Math.max(1, target)) * 100));
  return (
    <div className="flex flex-col gap-1 min-w-[140px]">
      <div className="flex justify-between text-[11px] uppercase tracking-widest text-slate-400">
        <span>{label}</span>
        <span className="font-mono text-slate-200">{value}/{target}</span>
      </div>
      <div className="h-2 rounded bg-slate-800 overflow-hidden">
        <div className="h-full rounded transition-all" style={{ width: `${pct}%`, background: color }} />
      </div>
    </div>
  );
}

function CardChip({ card, onClick, selected }: { card: SCPCard; onClick?: () => void; selected?: boolean }) {
  if (card.hidden) {
    return (
      <div className="px-2 py-1 rounded border border-slate-700 bg-slate-900/80 text-[11px] font-mono tracking-widest text-slate-500 select-none">
        ▮▮ CLASSIFIED
      </div>
    );
  }
  const stat =
    card.kind === 'SCP_ANOMALY' ? `${card.trap ? 'TRAP ' : ''}${card.threshold}/${card.value}`
    : card.kind === 'SCP_LAYER' ? `${card.ltype?.[0]?.toUpperCase()} ${card.strength}/${card.rez}`
    : card.kind === 'SCP_OPERATIVE' ? `${card.breaks?.[0]?.toUpperCase()} p${card.power}+${card.boost}`
    : card.cost != null ? `⌑${card.cost}` : '';
  return (
    <button
      onClick={onClick}
      disabled={!onClick}
      title={card.text || ''}
      className={[
        'px-2 py-1 rounded border text-left transition-colors',
        selected ? 'border-violet-400 bg-violet-950/60' : 'border-slate-700 bg-slate-900 hover:bg-slate-800',
        onClick ? 'cursor-pointer' : 'cursor-default',
      ].join(' ')}
    >
      <div className="text-[12px] text-slate-100 leading-tight max-w-[150px] truncate">{card.name}</div>
      <div className="text-[10px] font-mono text-slate-400">{stat}</div>
    </button>
  );
}

function CellView({
  cell, mine, canAct, onAdvance, onContain, onInfiltrate,
}: {
  cell: SCPCell; mine: boolean; canAct: boolean;
  onAdvance?: (anomalyId: string) => void;
  onContain?: (anomalyId: string) => void;
  onInfiltrate?: (cellId: number) => void;
}) {
  const a = cell.anomaly;
  return (
    <div className="flex flex-col gap-1 p-2 rounded-lg border border-slate-700 bg-slate-900/60 min-w-[150px]">
      <div className="text-[10px] uppercase tracking-widest text-slate-500">Cell {cell.id}</div>
      {a ? (
        <div className="flex flex-col gap-1">
          <div className="text-[12px] text-slate-100 truncate">
            {a.hidden ? <span className="font-mono text-slate-500">▮▮ FACE-DOWN</span> : a.name}
          </div>
          <div className="flex items-center gap-1" title="advancement (public)">
            {Array.from({ length: Math.max(a.advancement, 0) }).map((_, i) => (
              <span key={i} className="w-2 h-2 rounded-full" style={{ background: ACCENT.foundation }} />
            ))}
            <span className="text-[10px] font-mono text-slate-400 ml-1">heat {a.advancement}</span>
          </div>
        </div>
      ) : (
        <div className="text-[11px] text-slate-600 italic">empty</div>
      )}
      <div className="flex flex-wrap gap-1 mt-1">
        {cell.layers.length === 0 && <span className="text-[10px] text-slate-600">no layers</span>}
        {cell.layers.map((l) => (
          <span key={l.id} className={[
            'px-1.5 py-0.5 rounded text-[10px] font-mono border',
            l.rezzed ? 'border-amber-500/60 text-amber-300 bg-amber-950/30' : 'border-slate-700 text-slate-500 bg-slate-900',
          ].join(' ')}>
            {l.hidden ? '▮ ICE' : l.name}{l.rezzed ? ' ⚡' : ''}
          </span>
        ))}
      </div>
      <div className="flex gap-1 mt-1">
        {mine && canAct && a && onAdvance && (
          <button onClick={() => onAdvance(a.id)} className="text-[10px] px-1.5 py-0.5 rounded bg-violet-900/70 hover:bg-violet-800 text-violet-100">advance</button>
        )}
        {mine && canAct && a && onContain && (
          <button onClick={() => onContain(a.id)} className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-900/70 hover:bg-emerald-800 text-emerald-100">contain</button>
        )}
        {!mine && canAct && onInfiltrate && (
          <button onClick={() => onInfiltrate(cell.id)} className="text-[10px] px-1.5 py-0.5 rounded bg-rose-900/70 hover:bg-rose-800 text-rose-100">infiltrate ▸</button>
        )}
      </div>
    </div>
  );
}

function SeatHeader({ seat, label }: { seat: SCPSeat; label: string }) {
  const accent = ACCENT[seat.faction];
  return (
    <div className="flex items-center gap-4 flex-wrap">
      <div className="flex items-center gap-2">
        <span className="w-2.5 h-2.5 rounded-full" style={{ background: accent }} />
        <span className="text-sm font-semibold text-slate-100">{label}</span>
        <span className="text-[11px] uppercase tracking-widest" style={{ color: accent }}>{seat.faction}</span>
        {seat.identity && <span className="text-[11px] text-slate-500">· {seat.identity}</span>}
      </div>
      <div className="flex gap-3 text-[12px] font-mono text-slate-300">
        <span title="credits">⌑ {seat.credits}</span>
        <span title="actions">◇ {seat.ap}</span>
        <span title="hand">✋ {seat.hand_count}</span>
        <span title="deck">⛁ {seat.deck_count}</span>
        {seat.exposed > 0 && <span className="text-rose-400" title="exposed">⊘ {seat.exposed}</span>}
      </div>
    </div>
  );
}

function SeatBoard({
  seat, mine, canAct, onAdvance, onContain, onInfiltrate,
}: {
  seat: SCPSeat; mine: boolean; canAct: boolean;
  onAdvance?: (anomalyId: string) => void;
  onContain?: (anomalyId: string) => void;
  onInfiltrate?: (cellId: number) => void;
}) {
  const isFoundation = seat.faction === 'foundation';
  return (
    <div className="flex flex-col gap-2">
      {isFoundation ? (
        <div className="flex flex-wrap gap-2">
          {seat.cells.length === 0 && <span className="text-[11px] text-slate-600 italic">no containment cells yet</span>}
          {seat.cells.map((cell) => (
            <CellView key={cell.id} cell={cell} mine={mine} canAct={canAct}
              onAdvance={onAdvance} onContain={onContain} onInfiltrate={onInfiltrate} />
          ))}
        </div>
      ) : (
        <div className="flex flex-wrap gap-2">
          <span className="text-[10px] uppercase tracking-widest text-slate-500 w-full">Rig</span>
          {seat.rig.length === 0 && <span className="text-[11px] text-slate-600 italic">no operatives/tools</span>}
          {seat.rig.map((c) => <CardChip key={c.id} card={c} />)}
        </div>
      )}
      {seat.assets.length > 0 && (
        <div className="flex flex-wrap gap-2">
          <span className="text-[10px] uppercase tracking-widest text-slate-500 w-full">Assets</span>
          {seat.assets.map((c) => <CardChip key={c.id} card={c} />)}
        </div>
      )}
    </div>
  );
}

export function SCPGameView() {
  const { matchId } = useParams<{ matchId: string }>();
  const navigate = useNavigate();
  const storeMatchId = useGameStore((s) => s.matchId);
  const storePlayerId = useGameStore((s) => s.playerId);
  const setConnection = useGameStore((s) => s.setConnection);
  const setGameState = useGameStore((s) => s.setGameState);

  useEffect(() => {
    if (!matchId || storeMatchId === matchId) return;
    (async () => {
      try {
        const initial = await matchAPI.getState(matchId);
        const pids = Object.keys((initial.players as Record<string, unknown>) || {});
        const me = pids[0];
        if (!me) return;
        setConnection(matchId, me, false);
        const full = await matchAPI.getState(matchId, me);
        setGameState(full);
      } catch {
        /* board shows "connecting" */
      }
    })();
  }, [matchId, storeMatchId, setConnection, setGameState]);

  const { state, dispatch, isConnected } = useSCPGame();
  const [selected, setSelected] = useState<string | null>(null);

  if (!state || !state.me) {
    return (
      <div className="min-h-screen bg-slate-950 text-slate-300 flex items-center justify-center relative">
        <button
          onClick={() => navigate('/')}
          className="absolute left-4 top-4 text-[11px] uppercase tracking-widest text-slate-500 hover:text-slate-200 transition-colors"
          aria-label="Back to HYPERDRAFT main"
        >
          ← Home
        </button>
        <div className="text-sm tracking-widest uppercase text-slate-500">
          {isConnected ? 'Loading containment site…' : 'Connecting…'}
        </div>
      </div>
    );
  }

  const me = state.me;
  const opp = state.opponent;
  const foundationSeat = me.faction === 'foundation' ? me : opp;
  const insurgencySeat = me.faction === 'insurgency' ? me : opp;
  const selectedCard = me.hand?.find((c) => c.id === selected) || null;
  const canAct = state.yourTurn && !state.gameOver;
  const iWon = state.winner != null && state.winner === storePlayerId;

  const playSelected = () => {
    if (!selectedCard) return;
    dispatch({ type: 'PLAY', cardId: selectedCard.id });
    setSelected(null);
  };
  const infiltrateCell = (cellId: number) => dispatch({ type: 'INFILTRATE', target: ['cell', String(cellId)] });

  return (
    <div className="min-h-screen bg-slate-950 text-slate-200 p-4 flex flex-col gap-3">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3 border-b border-slate-800 pb-3">
        <div>
          <button
            onClick={() => navigate('/')}
            className="mb-1 text-[11px] uppercase tracking-widest text-slate-500 hover:text-slate-200 transition-colors"
            aria-label="Back to HYPERDRAFT main"
          >
            ← Home
          </button>
          <div className="text-lg font-semibold tracking-tight">SCP — SECURE / CONTAIN / SUBVERT</div>
          <div className="text-[11px] uppercase tracking-widest text-slate-500">
            {state.gameOver ? `GAME OVER · ${state.winReason ?? ''}` : state.yourTurn ? 'YOUR TURN' : "OPPONENT'S TURN"}
          </div>
        </div>
        <div className="flex gap-4 flex-wrap">
          <Bar label="Containment" value={foundationSeat?.containment_points ?? 0} target={state.targets.containment} color="#34d399" />
          <Bar label="Liberation" value={insurgencySeat?.liberation_points ?? 0} target={state.targets.liberation} color="#f87171" />
          <Bar label="Total Breach" value={foundationSeat?.total_breach ?? 0} target={state.targets.breach} color="#fbbf24" />
        </div>
      </div>

      {state.gameOver && (
        <div className={[
          'rounded-lg border px-4 py-2 text-sm',
          iWon ? 'border-emerald-600/50 bg-emerald-950/30 text-emerald-200' : 'border-rose-600/50 bg-rose-950/30 text-rose-200',
        ].join(' ')}>
          {iWon ? 'You win' : 'You lose'} — {state.winReason}
        </div>
      )}

      {/* Opponent */}
      {opp && (
        <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-3 flex flex-col gap-2">
          <SeatHeader seat={opp} label="Opponent" />
          <SeatBoard seat={opp} mine={false} canAct={canAct && me.faction === 'insurgency'} onInfiltrate={infiltrateCell} />
          {me.faction === 'insurgency' && canAct && (
            <div className="flex gap-2">
              {(['hq', 'research', 'archives'] as const).map((c) => (
                <button key={c} onClick={() => dispatch({ type: 'INFILTRATE', target: ['central', c] })}
                  className="text-[11px] px-2 py-1 rounded bg-rose-900/60 hover:bg-rose-800 text-rose-100 uppercase tracking-widest">
                  raid {c} ▸
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Me */}
      <div className="rounded-xl border border-slate-700 bg-slate-900/70 p-3 flex flex-col gap-3">
        <SeatHeader seat={me} label="You" />
        <SeatBoard seat={me} mine canAct={canAct}
          onAdvance={(id) => dispatch({ type: 'ADVANCE', anomalyId: id })}
          onContain={(id) => dispatch({ type: 'CONTAIN', anomalyId: id })} />

        {/* Hand */}
        <div className="flex flex-col gap-1">
          <span className="text-[10px] uppercase tracking-widest text-slate-500">Hand</span>
          <div className="flex flex-wrap gap-2">
            {(me.hand ?? []).map((c) => (
              <CardChip key={c.id} card={c} selected={selected === c.id}
                onClick={canAct ? () => setSelected(selected === c.id ? null : c.id) : undefined} />
            ))}
            {(me.hand ?? []).length === 0 && <span className="text-[11px] text-slate-600 italic">empty</span>}
          </div>
        </div>

        {/* Action bar */}
        <div className="flex items-center gap-2 flex-wrap border-t border-slate-800 pt-3">
          <button disabled={!canAct} onClick={() => dispatch({ type: 'GAIN' })}
            className="px-3 py-1.5 rounded bg-slate-800 hover:bg-slate-700 disabled:opacity-40 text-sm">Gain ⌑+2</button>
          <button disabled={!canAct} onClick={() => dispatch({ type: 'DRAW' })}
            className="px-3 py-1.5 rounded bg-slate-800 hover:bg-slate-700 disabled:opacity-40 text-sm">Draw</button>
          <button disabled={!canAct || !selectedCard} onClick={playSelected}
            className="px-3 py-1.5 rounded bg-violet-800 hover:bg-violet-700 disabled:opacity-40 text-sm">
            Play{selectedCard ? ` ${selectedCard.name}` : ''}
          </button>
          <div className="flex-1" />
          <button disabled={!canAct} onClick={() => { setSelected(null); dispatch({ type: 'END_TURN' }); }}
            className="px-4 py-1.5 rounded bg-emerald-800 hover:bg-emerald-700 disabled:opacity-40 text-sm font-semibold">End Turn ▸</button>
        </div>
      </div>
    </div>
  );
}

export default SCPGameView;
