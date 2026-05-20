/**
 * Replays — index of archived match replays.
 *
 * Phase 4 of the replay rollout. Reads /api/match/replays/list and
 * renders a sortable list of completed matches (newest first) with
 * mode badge + winner + duration + a single foil "Watch" CTA.
 */

import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { matchAPI } from '../services/api';
import { AppShell, Section, getMode } from '../components/brand';

interface ReplayEntry {
  match_id: string;
  game_mode: string | null;
  winner: string | null;
  total_turns: number | null;
  total_frames: number;
  archived_at: number;
}

function fmtAgo(ts: number): string {
  const seconds = Math.floor(Date.now() / 1000 - ts);
  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
}

export function Replays() {
  const [entries, setEntries] = useState<ReplayEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    matchAPI.listReplays(50)
      .then((r) => { if (!cancelled) setEntries(r.replays); })
      .catch((e) => { if (!cancelled) setError(e instanceof Error ? e.message : 'Failed to load replays'); });
    return () => { cancelled = true; };
  }, []);

  return (
    <AppShell>
      <Section eyebrow="Archive" title="Replays" trailing={entries ? `${entries.length} stored` : ''}>
        {error && (
          <div className="border border-brand-ember/50 bg-brand-ember/10 px-4 py-3 text-sm text-brand-ember mb-6">
            {error}
          </div>
        )}

        {entries === null && !error && (
          <div className="flex items-center gap-3 text-brand-chalk">
            <div className="w-5 h-5 border-2 border-brand-foil border-t-transparent rounded-full animate-spin" />
            <span className="brand-eyebrow">Loading archive</span>
          </div>
        )}

        {entries !== null && entries.length === 0 && (
          <div className="text-center py-16 brand-frame">
            <p className="brand-eyebrow text-brand-foil mb-3">Archive empty</p>
            <p className="text-brand-chalk max-w-md mx-auto">
              No completed matches have been archived yet. Enable the spectator demo
              (<code className="brand-mono text-brand-foil">HYPERDRAFT_SPECTATOR_ENABLED=true</code>)
              or finish a human-vs-bot match and it'll appear here.
            </p>
          </div>
        )}

        {entries !== null && entries.length > 0 && (
          <div className="grid gap-3">
            {entries.map((e) => {
              const meta = e.game_mode ? getMode(e.game_mode) : undefined;
              return (
                <Link
                  key={e.match_id}
                  to={`/replay/match/${e.match_id}`}
                  className="brand-tile brand-frame p-4 lg:p-5 group transition-shadow hover:shadow-[0_22px_50px_-20px_rgba(0,0,0,0.7)] flex flex-wrap items-center gap-x-6 gap-y-2"
                >
                  <div className="flex items-center gap-3 min-w-[140px]">
                    <span className="brand-eyebrow text-brand-foil">{meta?.code ?? (e.game_mode ?? 'UNKNOWN').toUpperCase()}</span>
                    <span className="text-base font-display font-semibold text-brand-cream">
                      {meta?.name ?? e.game_mode ?? 'unknown mode'}
                    </span>
                  </div>

                  <div className="flex items-baseline gap-1.5 text-xs text-brand-chalk min-w-[160px]">
                    <span className="brand-eyebrow text-brand-dust">match</span>
                    <span className="brand-mono text-brand-cream">{e.match_id.slice(0, 8)}</span>
                  </div>

                  <div className="flex items-baseline gap-1.5 text-xs text-brand-chalk min-w-[110px]">
                    <span className="brand-eyebrow text-brand-dust">turns</span>
                    <span className="brand-mono text-brand-cream">{e.total_turns ?? '?'}</span>
                  </div>

                  <div className="flex items-baseline gap-1.5 text-xs text-brand-chalk min-w-[110px]">
                    <span className="brand-eyebrow text-brand-dust">frames</span>
                    <span className="brand-mono text-brand-cream">{e.total_frames}</span>
                  </div>

                  <div className="text-xs text-brand-dust min-w-[80px]">{fmtAgo(e.archived_at)}</div>

                  <div className="flex-1" />

                  <span className="text-brand-foil opacity-0 group-hover:opacity-100 transition-opacity flex items-center gap-1">
                    Watch <span aria-hidden>→</span>
                  </span>
                </Link>
              );
            })}
          </div>
        )}
      </Section>
    </AppShell>
  );
}

export default Replays;
