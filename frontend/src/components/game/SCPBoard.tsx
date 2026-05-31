/**
 * SCPBoard — read-only board for SCP: SECURE / CONTAIN / SUBVERT
 * (asymmetric Foundation vs Chaos Insurgency).
 *
 * Used by ReplayView + SpectatorGameBody to render a recorded/spectated match.
 * Projects the server's `gameState.scp` payload (session.py:_serialize_scp_state)
 * via the same `projectSCPState` the live hook uses, then renders both seats'
 * win tracks (containment / liberation / total breach), containment cells with
 * public advancement "heat", the Insurgency rig, and Foundation assets.
 *
 * Read-only: no action buttons. Hands stay hidden (spectators don't see them);
 * fog-of-war identities arrive pre-redacted as [FACE-DOWN] from the server.
 */
import type { GameState } from '../../types';
import {
  projectSCPState,
  type SCPCard,
  type SCPCell,
  type SCPSeat,
} from '../../hooks/useSCPGame';

const ACCENT = { foundation: '#a78bfa', insurgency: '#f87171' } as const;

function Track({ label, value, target, color }: { label: string; value: number; target: number; color: string }) {
  const pct = Math.min(100, Math.round((value / Math.max(1, target)) * 100));
  return (
    <div className="min-w-[140px]">
      <div className="flex justify-between text-[11px] text-slate-400">
        <span>{label}</span>
        <span className="font-mono">{value}/{target}</span>
      </div>
      <div className="mt-1 h-1.5 rounded bg-slate-800">
        <div className="h-1.5 rounded" style={{ width: `${pct}%`, background: color }} />
      </div>
    </div>
  );
}

function Chip({ card }: { card: SCPCard }) {
  if (card.hidden) {
    return (
      <span className="px-2 py-1 rounded border border-slate-700 bg-slate-900/80 text-[11px] font-mono tracking-widest text-slate-500">
        [CLASSIFIED]
      </span>
    );
  }
  return (
    <span className="px-2 py-1 rounded border border-slate-700 bg-slate-900 text-[11px] text-slate-200">
      {card.name}
    </span>
  );
}

function CellView({ cell }: { cell: SCPCell }) {
  const a = cell.anomaly;
  return (
    <div className="rounded-lg border border-slate-700 bg-slate-900/60 p-2 min-w-[150px]">
      <div className="text-[10px] uppercase tracking-widest text-slate-500">Cell {cell.id}</div>
      {a ? (
        <div className="mt-0.5 text-sm text-slate-100">
          {a.hidden ? <span className="font-mono tracking-widest text-slate-500">[FACE-DOWN]</span> : a.name}
          <span className="ml-1 text-amber-300" title="advancement heat">{'●'.repeat(Math.min(a.advancement, 8)) || '·'}</span>
        </div>
      ) : (
        <div className="mt-0.5 text-[11px] italic text-slate-600">empty</div>
      )}
      <div className="mt-1 flex flex-wrap gap-1">
        {cell.layers.length === 0 && <span className="text-[10px] text-slate-600">no layers</span>}
        {cell.layers.map((l) => (
          <span key={l.id} className={[
            'px-1.5 py-0.5 rounded text-[10px] font-mono border',
            l.rezzed ? 'border-amber-500/60 text-amber-300 bg-amber-950/30' : 'border-slate-700 text-slate-500 bg-slate-900',
          ].join(' ')}>
            {l.hidden ? '##' : l.name}
          </span>
        ))}
      </div>
    </div>
  );
}

function SeatBoard({ seat, label }: { seat: SCPSeat; label: string }) {
  const isFoundation = seat.faction === 'foundation';
  const accent = isFoundation ? ACCENT.foundation : ACCENT.insurgency;
  return (
    <section className="rounded-xl border border-slate-800 bg-slate-900/40 p-3 flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <div>
          <span className="text-xs uppercase tracking-widest" style={{ color: accent }}>
            {label} · {isFoundation ? 'Foundation' : 'Chaos Insurgency'}
          </span>
          {seat.identity && <span className="ml-2 text-[11px] text-slate-500">{seat.identity}</span>}
        </div>
        <div className="flex gap-3 text-[11px] text-slate-400 font-mono">
          <span>{isFoundation ? 'Funding' : 'Cells'} {seat.credits}</span>
          <span>AP {seat.ap}</span>
          <span>hand {seat.hand_count}</span>
          <span>deck {seat.deck_count}</span>
        </div>
      </div>

      {isFoundation ? (
        <div className="flex flex-wrap gap-2">
          {seat.cells.length === 0 && <span className="text-[11px] italic text-slate-600">no containment cells</span>}
          {seat.cells.map((c) => <CellView key={c.id} cell={c} />)}
        </div>
      ) : (
        <div className="flex flex-wrap gap-1">
          <span className="text-[10px] uppercase tracking-widest text-slate-500 mr-1">rig:</span>
          {seat.rig.length === 0 && <span className="text-[11px] italic text-slate-600">no operatives</span>}
          {seat.rig.map((c) => <Chip key={c.id} card={c} />)}
        </div>
      )}

      {seat.assets.length > 0 && (
        <div className="flex flex-wrap gap-1">
          <span className="text-[10px] uppercase tracking-widest text-slate-500 mr-1">assets:</span>
          {seat.assets.map((c) => <Chip key={c.id} card={c} />)}
        </div>
      )}
    </section>
  );
}

export function SCPBoard({ gameState }: { gameState: GameState; playerId?: string | null; readOnly?: boolean }) {
  const raw = (gameState as unknown as { scp?: Record<string, unknown> }).scp;
  if (!raw) {
    return <div className="p-6 text-slate-500 text-sm">SCP match state unavailable.</div>;
  }
  const state = projectSCPState(raw);
  const foundationSeat = state.me?.faction === 'foundation' ? state.me : state.opponent;
  const insurgencySeat = state.me?.faction === 'insurgency' ? state.me : state.opponent;

  return (
    <div className="min-h-screen bg-slate-950 text-slate-200 p-4 flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-800 bg-slate-900/60 p-3">
        <div>
          <div className="text-lg font-semibold tracking-tight">SCP — SECURE / CONTAIN / SUBVERT</div>
          <div className="text-[11px] uppercase tracking-widest text-slate-500">
            {state.gameOver ? `GAME OVER · ${state.winReason ?? ''}` : 'spectating'}
          </div>
        </div>
        <div className="flex gap-4 flex-wrap">
          <Track label="Containment" value={foundationSeat?.containment_points ?? 0} target={state.targets.containment} color="#34d399" />
          <Track label="Liberation" value={insurgencySeat?.liberation_points ?? 0} target={state.targets.liberation} color="#f87171" />
          <Track label="Total Breach" value={foundationSeat?.total_breach ?? 0} target={state.targets.breach} color="#fbbf24" />
        </div>
      </div>

      {!foundationSeat && !insurgencySeat && (
        <div className="p-6 text-slate-500 text-sm">No seat detail available for this viewer.</div>
      )}
      {foundationSeat && <SeatBoard seat={foundationSeat} label="Site" />}
      {insurgencySeat && <SeatBoard seat={insurgencySeat} label="Cell" />}
    </div>
  );
}

export default SCPBoard;
