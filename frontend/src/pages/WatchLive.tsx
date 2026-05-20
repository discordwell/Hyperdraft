/**
 * WatchLive — public "Watch Claude play" landing page.
 *
 * Phase 4.2 of the Hosted Claude Code rollout. Fetches the currently-live
 * spectator-demo match from /api/spectate/live and redirects to /game/<id>
 * so the existing GameView renders both ultra-AI seats.
 *
 * If no demo is live (spectator supervisor disabled or between matches),
 * shows a "demo paused" message and polls every 10s for the next match.
 */

import { useEffect, useState, useCallback } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { matchAPI } from '../services/api';

interface SpectateLiveResponse {
  match_id: string;
  spectator_enabled: boolean;
}

interface RecentReplay {
  match_id: string;
  game_mode: string | null;
  total_turns: number | null;
  archived_at: number;
}

export function WatchLive() {
  const navigate = useNavigate();
  const [status, setStatus] = useState<'loading' | 'redirecting' | 'paused' | 'disabled'>(
    'loading'
  );
  const [recent, setRecent] = useState<RecentReplay | null>(null);

  // Fetch the most-recent archived replay so the "paused" state has a
  // useful "watch the previous match" CTA instead of just spinning.
  useEffect(() => {
    matchAPI.listReplays(1)
      .then((r) => { if (r.replays.length) setRecent(r.replays[0] as RecentReplay); })
      .catch(() => { /* non-fatal */ });
  }, []);

  const poll = useCallback(async () => {
    try {
      const res = await fetch('/api/spectate/live');
      if (res.status === 404) {
        // Check whether the supervisor is enabled at all
        const statusResp = await fetch('/api/spectate/status')
          .then((r) => r.json())
          .catch(() => null);
        setStatus(statusResp && statusResp.enabled === false ? 'disabled' : 'paused');
        return;
      }
      if (!res.ok) {
        setStatus('paused');
        return;
      }
      const data: SpectateLiveResponse = await res.json();
      if (data.match_id) {
        setStatus('redirecting');
        navigate(`/game/${data.match_id}`, { replace: true });
      }
    } catch (e) {
      setStatus('paused');
    }
  }, [navigate]);

  useEffect(() => {
    poll();
    const interval = setInterval(poll, 10_000);
    return () => clearInterval(interval);
  }, [poll]);

  if (status === 'redirecting') {
    return (
      <div className="flex items-center justify-center min-h-screen bg-slate-900">
        <div className="flex flex-col items-center gap-4 text-slate-400">
          <div className="w-12 h-12 border-4 border-slate-600 border-t-blue-400 rounded-full animate-spin" />
          <span className="text-sm uppercase tracking-widest">Joining live match...</span>
        </div>
      </div>
    );
  }

  return (
    <div className="flex items-center justify-center min-h-screen bg-brand-ink p-8">
      <div className="max-w-lg text-center text-brand-cream space-y-5 brand-frame px-10 py-12">
        <p className="brand-eyebrow text-brand-foil">Spectator</p>
        <h1 className="text-3xl font-display font-bold">Watch Claude play</h1>
        {status === 'disabled' ? (
          <p className="text-brand-chalk">
            The spectator demo is not enabled on this server right now. Operators flip it on with
            <code className="brand-mono text-brand-foil ml-1">HYPERDRAFT_SPECTATOR_ENABLED=true</code>.
          </p>
        ) : status === 'paused' ? (
          <p className="text-brand-chalk">
            No live demo right now &mdash; the previous match just ended. The supervisor will
            start the next one shortly; this page redirects automatically when it does.
          </p>
        ) : (
          <div className="flex items-center justify-center gap-3 text-brand-chalk">
            <div className="w-6 h-6 border-2 border-brand-hairline border-t-brand-foil rounded-full animate-spin" />
            <span className="brand-eyebrow">Checking for live match</span>
          </div>
        )}

        {recent && (
          <div className="pt-4 border-t border-brand-hairline/60">
            <p className="brand-eyebrow text-brand-dust mb-2">Or replay the previous match</p>
            <Link
              to={`/replay/match/${recent.match_id}`}
              className="inline-flex items-center gap-2 px-4 py-2 border border-brand-foil/40 hover:border-brand-foil/80 bg-brand-foil/10 hover:bg-brand-foil/20 text-brand-foil-bright transition-colors text-sm"
            >
              <span className="brand-mono">{recent.match_id.slice(0, 8)}</span>
              <span className="text-brand-chalk">·</span>
              <span>{recent.game_mode ?? 'match'}</span>
              <span className="text-brand-chalk">·</span>
              <span>{recent.total_turns ?? '?'} turns</span>
              <span aria-hidden>→</span>
            </Link>
          </div>
        )}

        <div className="pt-2">
          <Link to="/replays" className="text-xs text-brand-chalk hover:text-brand-foil transition-colors">
            Browse all replays →
          </Link>
        </div>
      </div>
    </div>
  );
}

export default WatchLive;
