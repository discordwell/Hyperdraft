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
import { useNavigate } from 'react-router-dom';

interface SpectateLiveResponse {
  match_id: string;
  spectator_enabled: boolean;
}

export function WatchLive() {
  const navigate = useNavigate();
  const [status, setStatus] = useState<'loading' | 'redirecting' | 'paused' | 'disabled'>(
    'loading'
  );

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
    <div className="flex items-center justify-center min-h-screen bg-slate-900 p-8">
      <div className="max-w-md text-center text-slate-200 space-y-4">
        <h1 className="text-2xl font-semibold">Watch Claude play</h1>
        {status === 'disabled' ? (
          <p className="text-slate-400">
            The spectator demo is not currently enabled on this server. Operators can opt in
            via <code className="text-slate-300">HYPERDRAFT_SPECTATOR_ENABLED=true</code>.
          </p>
        ) : status === 'paused' ? (
          <p className="text-slate-400">
            No live demo right now &mdash; the previous match just ended. The supervisor will
            start the next one shortly. This page will redirect automatically.
          </p>
        ) : (
          <div className="flex items-center justify-center gap-3 text-slate-400">
            <div className="w-6 h-6 border-2 border-slate-600 border-t-blue-400 rounded-full animate-spin" />
            <span className="text-sm uppercase tracking-widest">Checking for live match...</span>
          </div>
        )}
      </div>
    </div>
  );
}

export default WatchLive;
