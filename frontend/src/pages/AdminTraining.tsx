/**
 * AdminTraining — operator-facing /ultra-loop dispatcher.
 *
 * Phase 4.4 of the Hosted Claude Code rollout. Triggers a server-side
 * training run via POST /api/admin/train and polls /status for completion.
 *
 * Auth: the operator enters the X-Admin-Auth secret in the form; it's
 * stored in localStorage so a refresh keeps the session. The server
 * requires HYPERDRAFT_ADMIN_SECRET to be set or it 404s every request.
 */

import { useState, useEffect, useCallback } from 'react';

const GAMES = ['mtg', 'hearthstone', 'pokemon', 'yugioh', 'minecraft', 'finance', 'depths', 'scp'] as const;
type Game = (typeof GAMES)[number];

const STORAGE_SECRET_KEY = 'hyperdraft_admin_secret';

interface TrainStartResponse {
  run_id: string;
  status: string;
  game: string;
  iterations: number;
}

interface TrainStatusResponse {
  run_id: string;
  status: string;
  log_path?: string;
  tar_path?: string | null;
  started_at?: number;
}

export function AdminTraining() {
  const [secret, setSecret] = useState<string>(() => localStorage.getItem(STORAGE_SECRET_KEY) || '');
  const [game, setGame] = useState<Game>('mtg');
  const [iterations, setIterations] = useState(1);
  const [activeRun, setActiveRun] = useState<TrainStartResponse | null>(null);
  const [status, setStatus] = useState<TrainStatusResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    if (secret) localStorage.setItem(STORAGE_SECRET_KEY, secret);
  }, [secret]);

  const fetchStatus = useCallback(async () => {
    if (!activeRun) return;
    try {
      const res = await fetch(`/api/admin/train/${activeRun.run_id}/status`, {
        headers: { 'X-Admin-Auth': secret },
      });
      if (!res.ok) {
        setError(`status ${res.status}`);
        return;
      }
      setStatus(await res.json());
    } catch (e) {
      setError(e instanceof Error ? e.message : 'status fetch failed');
    }
  }, [activeRun, secret]);

  useEffect(() => {
    if (!activeRun) return;
    if (status && !status.status.startsWith('running')) return;
    const interval = setInterval(fetchStatus, 5_000);
    return () => clearInterval(interval);
  }, [activeRun, status, fetchStatus]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      const res = await fetch(
        `/api/admin/train?game=${encodeURIComponent(game)}&iterations=${iterations}`,
        { method: 'POST', headers: { 'X-Admin-Auth': secret } },
      );
      if (!res.ok) {
        const msg = await res.text().catch(() => '');
        setError(`HTTP ${res.status} ${msg}`);
        return;
      }
      const data: TrainStartResponse = await res.json();
      setActiveRun(data);
      setStatus({ run_id: data.run_id, status: data.status });
    } catch (e) {
      setError(e instanceof Error ? e.message : 'submit failed');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-900 text-slate-200 p-8">
      <div className="max-w-2xl mx-auto space-y-6">
        <h1 className="text-2xl font-semibold">Admin · /ultra-loop dispatcher</h1>
        <p className="text-sm text-slate-400">
          Spawns ``claude -p '/ultra-loop --game=&lt;game&gt; --iterations=&lt;n&gt;'`` inside the production
          container against a hardlinked copy of <code>/app</code>. Patches are tarballed and
          picked up by the host-side watcher; nothing auto-merges.
        </p>

        <form onSubmit={submit} className="space-y-4 bg-slate-800/50 p-6 rounded-lg">
          <div>
            <label className="block text-sm font-medium mb-1">X-Admin-Auth secret</label>
            <input
              type="password"
              value={secret}
              onChange={(e) => setSecret(e.target.value)}
              placeholder="HYPERDRAFT_ADMIN_SECRET"
              className="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded text-sm font-mono"
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium mb-1">Game</label>
              <select
                value={game}
                onChange={(e) => setGame(e.target.value as Game)}
                className="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded text-sm"
              >
                {GAMES.map((g) => (
                  <option key={g} value={g}>{g}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Iterations (1-50)</label>
              <input
                type="number"
                min={1}
                max={50}
                value={iterations}
                onChange={(e) => setIterations(parseInt(e.target.value) || 1)}
                className="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded text-sm"
              />
            </div>
          </div>
          <button
            type="submit"
            disabled={isSubmitting || !secret}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-500 disabled:bg-slate-700 disabled:cursor-not-allowed rounded text-sm font-medium transition"
          >
            {isSubmitting ? 'Submitting...' : 'Start training run'}
          </button>
        </form>

        {error && (
          <div className="bg-red-900/40 border border-red-700 rounded p-4 text-sm">
            <strong>Error:</strong> {error}
          </div>
        )}

        {activeRun && (
          <div className="bg-slate-800/50 p-6 rounded-lg space-y-2 text-sm font-mono">
            <div><span className="text-slate-400">run_id:</span> {activeRun.run_id}</div>
            <div><span className="text-slate-400">game:</span> {activeRun.game}</div>
            <div><span className="text-slate-400">iterations:</span> {activeRun.iterations}</div>
            <div><span className="text-slate-400">status:</span> {status?.status || activeRun.status}</div>
            {status?.log_path && (
              <div><span className="text-slate-400">log:</span> {status.log_path}</div>
            )}
            {status?.tar_path && (
              <div><span className="text-slate-400">tarball:</span> {status.tar_path}</div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default AdminTraining;
