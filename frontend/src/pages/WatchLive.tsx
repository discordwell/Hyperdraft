/**
 * WatchLive — lab-posture live-matches lobby (HD-ART-06 / Phase C3).
 *
 * HYPERDRAFT is a cabinet of TCGs; WatchLive is the *between-games* lobby
 * surface — the player is still in the lab. Per `docs/design/brand.md`, full
 * lab posture applies here (paper / ink / sodium, hairline rules, mono
 * telemetry). The match interiors keep their own per-engine chrome; this
 * page only routes the spectator into them.
 *
 * Wired data:
 *   - /api/spectate/live + /api/spectate/status drive the featured "LIVE"
 *     panel; the spectator-demo match (if any) gets pinned there.
 *   - /api/bot-game/list?status=running surfaces any other Bot-vs-Bot games
 *     currently mid-match.
 *
 * BotGameStatus is intentionally narrow (game_id / status / turn / winner)
 * so the table enriches running matches with mock metadata (engine code,
 * deck blurb, player labels) — the design needs richer columns than the
 * backend exposes today. The headers match HD-ART-06 exactly; populating
 * them properly is a backend slice for a future phase.
 */

import { useEffect, useMemo, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { botGameAPI, matchAPI } from '../services/api';
import { getMode, type GameModeId } from '../components/brand';
import { shortCode } from './PublicMatch';

interface SpectateStatus {
  enabled: boolean;
  current_match_id: string | null;
  game_mode?: string;
}

interface LiveMatchRow {
  matchId: string;
  shortCode: string;
  blurb: string;
  engineCode: string;
  engineLabel: string;
  players: string;
  turn: number | null;
  watchPath: string;
  live: boolean;
  queued?: boolean;
}

interface FeaturedMatch {
  matchId: string;
  shortCode: string;
  engineCode: string;
  watching: number;
  p1Name: string;
  p1Note: string;
  p2Name: string;
  p2Note: string;
  commentary: { who: string; line: string }[];
  watchPath: string;
}

interface RecentReplay {
  match_id: string;
  game_mode: string | null;
  total_turns: number | null;
  archived_at: number;
}

// ─── Mock data — see file header. Mirrors HD-ART-06's lobby artboard so the
// design composes correctly before the backend grows engine + player columns.
const MOCK_ROWS: LiveMatchRow[] = [
  {
    matchId: 'HD-2K1B',
    shortCode: 'HD-2K1B',
    blurb: 'goat control mirror',
    engineCode: 'YGO',
    engineLabel: 'Yu-Gi-Oh!',
    players: 'Hard-AI · Hard-AI',
    turn: 9,
    watchPath: '/m/HD-2K1B',
    live: false,
  },
  {
    matchId: 'HD-9C77',
    shortCode: 'HD-9C77',
    blurb: 'raichu vs charizard · prize 2–3',
    engineCode: 'PKM',
    engineLabel: 'Pokémon',
    players: 'Medium-AI · Hard-AI',
    turn: 6,
    watchPath: '/m/HD-9C77',
    live: true,
  },
  {
    matchId: 'HD-5018',
    shortCode: 'HD-5018',
    blurb: 'aggro shaman vs ramp druid',
    engineCode: 'HS',
    engineLabel: 'Hearthstone',
    players: 'Ultra-AI · Medium-AI',
    turn: 7,
    watchPath: '/m/HD-5018',
    live: false,
  },
  {
    matchId: 'HD-E110',
    shortCode: 'HD-E110',
    blurb: 'euclid midrange vs keter rush',
    engineCode: 'SCP',
    engineLabel: 'SCP',
    players: 'Hard-AI · Hard-AI',
    turn: 3,
    watchPath: '/m/HD-E110',
    live: false,
  },
  {
    matchId: 'HD-E219',
    shortCode: 'HD-E219',
    blurb: 'queued — opens in 14s',
    engineCode: 'MTG',
    engineLabel: 'Magic',
    players: 'Ultra-AI · Ultra-AI',
    turn: null,
    watchPath: '/m/HD-E219',
    live: false,
    queued: true,
  },
];

// Mock commentary for the featured panel when no spectator demo is live.
const FALLBACK_FEATURED: FeaturedMatch = {
  matchId: 'HD-8F4A',
  shortCode: 'HD-8F4A',
  engineCode: 'MTG',
  watching: 12,
  p1Name: 'Ultra-AI',
  p1Note: 'burn · LLM-guided · 17 life',
  p2Name: 'Hard-AI',
  p2Note: 'UW control · 20 life',
  watchPath: '/m/HD-8F4A',
  commentary: [
    {
      who: 'Ultra',
      line: "P1 keeps a 1-lander on the play. Acceptable — bolts twice and a probe. If we don't see a second red source by turn 3 we mulligan-equivalent through ponders.",
    },
    {
      who: 'Hard',
      line: 'P2 leads Brainstorm into Force Spike — saving counters for a turn-3 threat from P1.',
    },
    {
      who: 'Ultra',
      line: 'Reading the chain — RESOLVE Lightning Bolt → 3 dmg → P2 has open mana for Counterspell. I cast Bolt anyway: bait.',
    },
  ],
};

export function WatchLive() {
  const navigate = useNavigate();
  const [spectator, setSpectator] = useState<SpectateStatus | null>(null);
  const [botRows, setBotRows] = useState<LiveMatchRow[]>([]);
  const [recent, setRecent] = useState<RecentReplay | null>(null);

  // Recent archived replay — surfaces under the featured panel as the
  // "replay available at end of match" line when no demo is live.
  useEffect(() => {
    matchAPI
      .listReplays(1)
      .then((r) => {
        if (r.replays.length) setRecent(r.replays[0] as RecentReplay);
      })
      .catch(() => {
        /* non-fatal */
      });
  }, []);

  const pollLive = useCallback(async () => {
    // Pull the spectator-demo state + running bot games in parallel; one
    // failing shouldn't blank the whole lobby.
    try {
      const statusResp = await fetch('/api/spectate/status').then((r) => (r.ok ? r.json() : null));
      setSpectator(statusResp as SpectateStatus | null);
    } catch {
      setSpectator(null);
    }
    try {
      const { games } = await botGameAPI.list('running');
      const rows: LiveMatchRow[] = games.map((g) => ({
        matchId: g.game_id,
        shortCode: shortCode(g.game_id),
        blurb: 'bot vs bot · live',
        engineCode: 'BOT',
        engineLabel: 'Bot game',
        players: 'Bot · Bot',
        turn: g.turn,
        watchPath: `/spectate/${g.game_id}`,
        live: true,
      }));
      setBotRows(rows);
    } catch {
      setBotRows([]);
    }
  }, []);

  useEffect(() => {
    pollLive();
    const interval = setInterval(pollLive, 10_000);
    return () => clearInterval(interval);
  }, [pollLive]);

  // Compose the table: featured spectator-demo first (if any), real bot
  // games next, then the mock-rich rows so the page never reads as empty.
  const rows = useMemo<LiveMatchRow[]>(() => {
    const out: LiveMatchRow[] = [];
    if (spectator?.enabled && spectator.current_match_id) {
      const meta = spectator.game_mode ? getMode(spectator.game_mode as GameModeId) : undefined;
      out.push({
        matchId: spectator.current_match_id,
        shortCode: shortCode(spectator.current_match_id),
        blurb: 'spectator demo · ultra mirror',
        engineCode: meta?.code ?? 'MTG',
        engineLabel: meta?.name ?? 'Magic',
        players: 'Ultra-AI · Ultra-AI',
        turn: null,
        watchPath: `/m/${spectator.current_match_id}`,
        live: true,
      });
    }
    out.push(...botRows);
    out.push(...MOCK_ROWS);
    return out;
  }, [spectator, botRows]);

  const featured = useMemo<FeaturedMatch>(() => {
    if (spectator?.enabled && spectator.current_match_id) {
      const meta = spectator.game_mode ? getMode(spectator.game_mode as GameModeId) : undefined;
      return {
        matchId: spectator.current_match_id,
        shortCode: shortCode(spectator.current_match_id),
        engineCode: meta?.code ?? 'MTG',
        watching: 12,
        p1Name: 'Ultra-AI',
        p1Note: 'claude-pilot · seat 1',
        p2Name: 'Ultra-AI',
        p2Note: 'heuristic ultra · seat 2',
        watchPath: `/m/${spectator.current_match_id}`,
        commentary: FALLBACK_FEATURED.commentary,
      };
    }
    return FALLBACK_FEATURED;
  }, [spectator]);

  const liveCount = rows.filter((r) => r.live).length;

  return (
    <div style={{ background: 'var(--paper)', color: 'var(--ink)', minHeight: '100vh' }}>
      {/* ─── Caption rail (fixed crumb, like Home) ─────────────────────── */}
      <div
        style={{
          position: 'fixed',
          top: 14,
          left: '50%',
          transform: 'translateX(-50%)',
          fontFamily: 'var(--font-mono)',
          fontSize: 10.5,
          letterSpacing: '.14em',
          textTransform: 'uppercase',
          color: 'var(--ink-3)',
          background: 'var(--paper)',
          padding: '6px 14px',
          border: '1px solid var(--rule)',
          zIndex: 10,
        }}
      >
        <b style={{ color: 'var(--ink)', fontWeight: 500 }}>HD-WATCH</b>
        &nbsp;·&nbsp; HYPERDRAFT &nbsp;·&nbsp; live lobby
      </div>

      <main
        style={{
          maxWidth: 1280,
          margin: '0 auto',
          padding: '88px 56px 120px',
          position: 'relative',
        }}
      >
        {/* ─── Masthead — HD-ART-06 "Now running" with live-count pill ─── */}
        <header
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'end',
            borderBottom: '1px solid var(--rule)',
            paddingBottom: 14,
            marginBottom: 28,
          }}
        >
          <div>
            <div
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: 11,
                fontWeight: 500,
                letterSpacing: '.14em',
                textTransform: 'uppercase',
                color: 'var(--ink-3)',
                marginBottom: 8,
              }}
            >
              HYPERDRAFT
            </div>
            <h1
              style={{
                margin: 0,
                fontFamily: 'var(--font-serif)',
                fontSize: 'clamp(40px, 5vw, 56px)',
                fontWeight: 400,
                lineHeight: 1,
                letterSpacing: '-.015em',
                color: 'var(--ink)',
              }}
            >
              Now <em style={{ color: 'var(--sodium)', fontStyle: 'italic' }}>running</em>
            </h1>
          </div>

          <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
            <span className="lab-chip" data-testid="live-count">
              <span className="dot lobby-pulse-dot" />
              {liveCount} live
            </span>
            <button
              type="button"
              onClick={() => navigate('/replays')}
              style={lobbyPillButtonStyle}
            >
              Replays →
            </button>
          </div>
        </header>

        {/* ─── Body grid — 1.4fr table + 1fr featured panel ─────────────── */}
        <div className="lobby-body" style={lobbyBodyStyle}>
          {/* Live-matches table */}
          <div
            style={{
              border: '1px solid var(--rule)',
              background: 'var(--paper-2)',
              display: 'flex',
              flexDirection: 'column',
            }}
          >
            <TableRow header>
              <span>#</span>
              <span>Match</span>
              <span>Engine</span>
              <span>Players</span>
              <span>Turn</span>
              <span>Watch</span>
            </TableRow>

            {rows.map((row, ix) => (
              <TableRow
                key={row.matchId}
                onClick={() => navigate(row.watchPath)}
                clickable={!row.queued}
              >
                <span style={{ color: 'var(--ink-3)' }}>
                  {String(ix + 1).padStart(2, '0')}
                </span>
                <span>
                  <b
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 6,
                      color: 'var(--ink)',
                      fontFamily: 'var(--font-serif)',
                      fontSize: 15,
                      fontWeight: 400,
                      letterSpacing: 0,
                      lineHeight: 1.1,
                    }}
                  >
                    {row.live && <span className="lobby-pulse-dot" aria-hidden />}
                    {row.shortCode}
                  </b>
                  <small
                    style={{
                      display: 'block',
                      fontFamily: 'var(--font-mono)',
                      fontSize: 10.5,
                      color: 'var(--ink-3)',
                      textTransform: 'uppercase',
                      letterSpacing: '.1em',
                      marginTop: 3,
                    }}
                  >
                    {row.blurb}
                  </small>
                </span>
                <span style={{ color: 'var(--ink-2)' }}>{row.engineCode}</span>
                <span style={{ color: 'var(--ink-2)', fontSize: 11 }}>{row.players}</span>
                <span style={{ fontFeatureSettings: '"tnum"' }}>
                  <span
                    style={{
                      display: 'inline-block',
                      background: 'var(--ink)',
                      color: 'var(--paper)',
                      padding: '3px 6px',
                      fontSize: 10.5,
                      letterSpacing: '.04em',
                      fontFamily: 'var(--font-mono)',
                    }}
                  >
                    T {row.turn === null ? '—' : String(row.turn).padStart(2, '0')}
                  </span>
                </span>
                <span
                  style={{
                    fontFamily: 'var(--font-mono)',
                    fontSize: 10,
                    fontWeight: 500,
                    letterSpacing: '.14em',
                    textTransform: 'uppercase',
                    color: row.live ? 'var(--sodium)' : 'var(--ink)',
                    textAlign: 'right',
                  }}
                >
                  {row.queued ? '▸ Soon' : '▸ Watch'}
                </span>
              </TableRow>
            ))}
          </div>

          {/* Featured-live panel */}
          <aside
            style={{
              border: '1px solid var(--ink)',
              background: 'var(--paper-2)',
              padding: 18,
              display: 'flex',
              flexDirection: 'column',
              gap: 14,
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
              <h3
                style={{
                  margin: 0,
                  fontFamily: 'var(--font-serif)',
                  fontSize: 22,
                  fontWeight: 400,
                  letterSpacing: '-.01em',
                  color: 'var(--ink)',
                }}
              >
                <small
                  style={{
                    display: 'block',
                    fontFamily: 'var(--font-mono)',
                    fontSize: 10.5,
                    fontWeight: 500,
                    letterSpacing: '.14em',
                    textTransform: 'uppercase',
                    color: 'var(--sodium)',
                    marginBottom: 5,
                  }}
                >
                  FEATURED · LIVE
                </small>
                {featured.shortCode}
              </h3>
              <span className="lab-chip" style={{ borderColor: 'var(--rule)' }}>
                <span className="dot lobby-pulse-dot" />
                {featured.watching} watching
              </span>
            </div>

            <div
              style={{
                display: 'grid',
                gridTemplateColumns: '1fr auto 1fr',
                gap: 8,
                alignItems: 'center',
                padding: '10px 0',
                borderTop: '1px solid var(--rule)',
                borderBottom: '1px solid var(--rule)',
              }}
            >
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, lineHeight: 1.3, color: 'var(--ink-2)' }}>
                <b
                  style={{
                    display: 'block',
                    color: 'var(--ink)',
                    fontFamily: 'var(--font-serif)',
                    fontSize: 17,
                    fontWeight: 400,
                    letterSpacing: 0,
                    marginBottom: 3,
                  }}
                >
                  {featured.p1Name}
                </b>
                {featured.p1Note}
              </div>
              <div
                style={{
                  fontFamily: 'var(--font-serif)',
                  fontSize: 22,
                  fontStyle: 'italic',
                  color: 'var(--sodium)',
                  textAlign: 'center',
                  lineHeight: 1,
                }}
              >
                vs.
              </div>
              <div
                style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: 11,
                  lineHeight: 1.3,
                  color: 'var(--ink-2)',
                  textAlign: 'right',
                }}
              >
                <b
                  style={{
                    display: 'block',
                    color: 'var(--ink)',
                    fontFamily: 'var(--font-serif)',
                    fontSize: 17,
                    fontWeight: 400,
                    letterSpacing: 0,
                    marginBottom: 3,
                  }}
                >
                  {featured.p2Name}
                </b>
                {featured.p2Note}
              </div>
            </div>

            <div
              style={{
                fontFamily: 'var(--font-sans)',
                fontSize: 12.5,
                lineHeight: 1.55,
                color: 'var(--ink-2)',
                maxHeight: 140,
                overflow: 'auto',
                paddingRight: 4,
              }}
            >
              {featured.commentary.map((entry, ix) => (
                <p key={ix} style={{ margin: '0 0 8px' }}>
                  <span
                    style={{
                      fontFamily: 'var(--font-mono)',
                      fontSize: 10.5,
                      fontWeight: 500,
                      letterSpacing: '.1em',
                      textTransform: 'uppercase',
                      color: 'var(--sodium)',
                      marginRight: 6,
                    }}
                  >
                    {entry.who}
                  </span>
                  {entry.line}
                </p>
              ))}
            </div>

            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                fontFamily: 'var(--font-mono)',
                fontSize: 11,
                fontWeight: 500,
                letterSpacing: '.1em',
                textTransform: 'uppercase',
                color: 'var(--ink-3)',
                borderTop: '1px solid var(--rule)',
                paddingTop: 10,
              }}
            >
              <span>
                {recent
                  ? `Last archive · ${recent.match_id.slice(0, 8)}`
                  : 'Replay available at end of match'}
              </span>
              <button
                type="button"
                onClick={() => navigate(featured.watchPath)}
                style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: 11,
                  letterSpacing: '.14em',
                  textTransform: 'uppercase',
                  color: 'var(--ink)',
                  background: 'transparent',
                  border: 'none',
                  cursor: 'pointer',
                  padding: 0,
                }}
              >
                ▸ Open
              </button>
            </div>
          </aside>
        </div>

        {/* ─── Footer telemetry strip ───────────────────────────────────── */}
        <footer
          style={{
            marginTop: 56,
            paddingTop: 18,
            borderTop: '1px solid var(--rule)',
            display: 'flex',
            justifyContent: 'space-between',
            flexWrap: 'wrap',
            gap: 14,
            fontFamily: 'var(--font-mono)',
            fontSize: 11,
            color: 'var(--ink-3)',
            letterSpacing: '.08em',
            textTransform: 'uppercase',
          }}
        >
          <span>HD-WATCH-001 / 2026 · poll every 10s</span>
          <button
            type="button"
            onClick={() => navigate('/')}
            style={{
              background: 'transparent',
              border: 'none',
              cursor: 'pointer',
              color: 'var(--ink-3)',
              fontFamily: 'var(--font-mono)',
              fontSize: 11,
              letterSpacing: '.08em',
              textTransform: 'uppercase',
            }}
          >
            ← Lab
          </button>
        </footer>
      </main>

      {/* Component-scoped CSS — pulse dot + responsive collapse. Avoids
          touching the global stylesheet for a single-page feature. */}
      <style>{lobbyCSS}</style>
    </div>
  );
}

// ─── Table row helper — keeps the grid template + hover behaviour in one
// place so header + body rows stay aligned without copy-paste drift. ────
function TableRow({
  children,
  header,
  clickable,
  onClick,
}: {
  children: React.ReactNode;
  header?: boolean;
  clickable?: boolean;
  onClick?: () => void;
}) {
  const base: React.CSSProperties = {
    display: 'grid',
    gridTemplateColumns: '40px 1.4fr 1fr 1fr .8fr 70px',
    gap: 10,
    alignItems: 'center',
    padding: '11px 14px',
    borderTop: header ? '0' : '1px solid var(--rule-2)',
    fontFamily: 'var(--font-mono)',
    fontSize: 11.5,
    lineHeight: 1.2,
    fontWeight: 500,
    background: header ? 'var(--paper-3)' : 'transparent',
    color: header ? 'var(--ink-3)' : 'var(--ink-2)',
    letterSpacing: header ? '.12em' : 'normal',
    textTransform: header ? 'uppercase' : 'none',
    cursor: clickable ? 'pointer' : 'default',
    textAlign: 'left',
    width: '100%',
    border: 'none',
    borderBottom: 'none',
  };
  if (header) {
    return <div style={{ ...base, fontSize: 10.5 }}>{children}</div>;
  }
  return (
    <button type="button" onClick={onClick} disabled={!clickable} style={base}>
      {children}
    </button>
  );
}

const lobbyPillButtonStyle: React.CSSProperties = {
  fontFamily: 'var(--font-mono)',
  fontSize: 10.5,
  fontWeight: 500,
  letterSpacing: '.1em',
  textTransform: 'uppercase',
  padding: '6px 10px',
  border: '1px solid var(--ink)',
  background: 'transparent',
  color: 'var(--ink)',
  cursor: 'pointer',
};

const lobbyBodyStyle: React.CSSProperties = {
  display: 'grid',
  gridTemplateColumns: '1.4fr 1fr',
  gap: 20,
};

// Pulsing acid dot — HD-ART-06 uses --acid (mint-green) for the live
// heartbeat. Self-contained keyframe so the file stays portable.
const lobbyCSS = `
  .lobby-pulse-dot {
    display: inline-block;
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: var(--acid);
    box-shadow: 0 0 0 0 color-mix(in oklab, var(--acid) 60%, transparent);
    animation: lobby-pulse 1.6s ease-in-out infinite;
  }
  @keyframes lobby-pulse {
    0%, 100% { box-shadow: 0 0 0 0 color-mix(in oklab, var(--acid) 50%, transparent), 0 0 6px color-mix(in oklab, var(--acid) 55%, transparent); }
    50%      { box-shadow: 0 0 0 5px color-mix(in oklab, var(--acid) 0%,  transparent), 0 0 10px color-mix(in oklab, var(--acid) 80%, transparent); }
  }
  @media (max-width: 900px) {
    .lobby-body { grid-template-columns: 1fr !important; }
  }
`;

export default WatchLive;
