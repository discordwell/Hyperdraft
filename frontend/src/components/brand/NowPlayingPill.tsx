/**
 * NowPlayingPill — live demo-match indicator with a heartbeat pulse.
 *
 * Polls /api/spectate/live every 15s and shows a "watch live" pill when
 * a spectator demo is active. Silent (returns null) when the demo
 * supervisor is off OR between matches — avoids advertising features
 * the user can't actually see right now.
 */

import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { getMode, type GameModeId } from './modes';

interface SpectateStatus {
  enabled: boolean;
  current_match_id: string | null;
  game_mode?: string;
}

export function NowPlayingPill() {
  const [status, setStatus] = useState<SpectateStatus | null>(null);

  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      try {
        const res = await fetch('/api/spectate/status');
        if (!res.ok) return;
        const data: SpectateStatus = await res.json();
        if (!cancelled) setStatus(data);
      } catch {
        /* network blip; try again next tick */
      }
    };
    poll();
    const interval = setInterval(poll, 15_000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  if (!status?.enabled || !status.current_match_id) return null;

  const modeMeta = status.game_mode ? getMode(status.game_mode as GameModeId) : undefined;

  return (
    <Link
      to="/watch/live"
      className="group inline-flex items-center gap-3 px-3.5 py-1.5 border border-brand-hairline hover:border-brand-sheen/50 bg-brand-obsidian/70 hover:bg-brand-shelf transition-colors"
    >
      <span className="brand-live-dot" aria-hidden />
      <span className="brand-eyebrow text-brand-sheen group-hover:text-brand-sheen-glow">
        Live
      </span>
      <span className="text-xs text-brand-cream tracking-wide">
        {modeMeta ? modeMeta.name : 'Demo'} match in play
      </span>
      <span className="text-xs text-brand-chalk group-hover:text-brand-foil transition-colors">
        watch →
      </span>
    </Link>
  );
}

export default NowPlayingPill;
