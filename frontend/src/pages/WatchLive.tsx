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
 *   - /api/bot-game/list?status=running surfaces every Bot-vs-Bot game
 *     currently mid-match. BotGameStatus carries engine code, brain +
 *     difficulty per seat, and a deck archetype blurb; the table renders
 *     those directly with no mock fallback.
 */

import { useEffect, useMemo, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { botGameAPI, matchAPI } from '../services/api';
import { getMode, type GameModeId } from '../components/brand';
import { shortCode } from './PublicMatch';

interface SpectateStatus {
  enabled: boolean;
  current_match_id: string | null;
  game_mode?: string | null;
  single_shot?: boolean;
  started_at?: number | null;
  cooldown_seconds_remaining?: number;
  supported_game_modes?: string[];
}

const GAME_MODE_LABELS: Record<string, string> = {
  mtg: 'Magic',
  pokemon: 'Pokémon',
  hearthstone: 'Hearthstone',
  yugioh: 'Yu-Gi-Oh!',
};

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
  p1Name: string;
  p1Note: string;
  p2Name: string;
  p2Note: string;
  watchPath: string;
}

interface RecentReplay {
  match_id: string;
  game_mode: string | null;
  total_turns: number | null;
  archived_at: number;
}

// Format a single BotGameStatus row into the table model. Pulled out so
// the spectator-demo row and the API rows compose with identical chrome.
function rowFromStatus(g: import('../types/game').BotGameStatus): LiveMatchRow {
  const meta = g.game_mode ? getMode(g.game_mode as GameModeId) : undefined;
  const engineCode = meta?.code ?? (g.game_mode ? g.game_mode.toUpperCase() : 'BOT');
  const engineLabel = meta?.name ?? 'Bot game';
  // "Heuristic · medium · vs · Claude · ultra" — the table is mono-cramped
  // so we join with ' · ' between seats; the per-seat string already
  // contains its own ' · ' between brain and difficulty.
  const p1 = g.player1_label ?? 'Bot 1';
  const p2 = g.player2_label ?? 'Bot 2';
  return {
    matchId: g.game_id,
    shortCode: shortCode(g.game_id),
    blurb: g.deck_blurb ?? 'bot vs bot · live',
    engineCode,
    engineLabel,
    players: `${p1} · ${p2}`,
    turn: g.turn,
    watchPath: `/spectate/${g.game_id}`,
    live: g.status === 'running',
  };
}

export function WatchLive() {
  const navigate = useNavigate();
  const [spectator, setSpectator] = useState<SpectateStatus | null>(null);
  const [botRows, setBotRows] = useState<LiveMatchRow[]>([]);
  const [recent, setRecent] = useState<RecentReplay | null>(null);
  const [selectedMode, setSelectedMode] = useState<string>('mtg');
  const [toggleBusy, setToggleBusy] = useState<boolean>(false);
  const [toggleError, setToggleError] = useState<string | null>(null);

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
      // BotGameStatus now carries engine + brain/difficulty + deck blurb,
      // so the row factory can lift everything off the response. No
      // padding rows, no mock fallback.
      setBotRows(games.map(rowFromStatus));
    } catch {
      setBotRows([]);
    }
  }, []);

  useEffect(() => {
    pollLive();
    const interval = setInterval(pollLive, 10_000);
    return () => clearInterval(interval);
  }, [pollLive]);

  const triggerStart = useCallback(async () => {
    setToggleBusy(true);
    setToggleError(null);
    try {
      const resp = await fetch('/api/spectate/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ game_mode: selectedMode }),
      });
      if (!resp.ok) {
        const data = (await resp.json().catch(() => ({}))) as { detail?: string };
        setToggleError(data.detail ?? `Start failed (${resp.status})`);
      } else {
        setSpectator((await resp.json()) as SpectateStatus);
      }
    } catch (e) {
      setToggleError(e instanceof Error ? e.message : 'Start failed');
    } finally {
      setToggleBusy(false);
      // Re-poll so we pick up the supervisor's match_id once it spawns.
      // Two polls: immediate (catches fast spawn) + ~6s (after supervisor
      // wakes from its 5s sleep and writes _current_match_id).
      void pollLive();
      setTimeout(() => void pollLive(), 6000);
    }
  }, [selectedMode, pollLive]);

  const triggerStop = useCallback(async () => {
    setToggleBusy(true);
    setToggleError(null);
    try {
      const resp = await fetch('/api/spectate/stop', { method: 'POST' });
      if (!resp.ok) {
        const data = (await resp.json().catch(() => ({}))) as { detail?: string };
        setToggleError(data.detail ?? `Stop failed (${resp.status})`);
      } else {
        setSpectator((await resp.json()) as SpectateStatus);
      }
    } catch (e) {
      setToggleError(e instanceof Error ? e.message : 'Stop failed');
    } finally {
      setToggleBusy(false);
      void pollLive();
    }
  }, [pollLive]);

  const supportedModes = spectator?.supported_game_modes ?? ['mtg', 'pokemon', 'hearthstone', 'yugioh'];
  const cooldownLeft = Math.ceil(spectator?.cooldown_seconds_remaining ?? 0);
  const startDisabled = toggleBusy || Boolean(spectator?.enabled) || cooldownLeft > 0;
  const stopDisabled = toggleBusy || !spectator?.enabled;

  // Compose the table: featured spectator-demo first (if any), then
  // real bot games. Empty state shows a hint instead of mock rows.
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
        players: 'Claude · ultra · Heuristic · ultra',
        turn: null,
        watchPath: `/m/${spectator.current_match_id}`,
        live: true,
      });
    }
    out.push(...botRows);
    return out;
  }, [spectator, botRows]);

  // Featured panel mirrors the active spectator demo when one is live;
  // otherwise null, in which case the panel renders its empty state.
  const featured = useMemo<FeaturedMatch | null>(() => {
    if (spectator?.enabled && spectator.current_match_id) {
      const meta = spectator.game_mode ? getMode(spectator.game_mode as GameModeId) : undefined;
      return {
        matchId: spectator.current_match_id,
        shortCode: shortCode(spectator.current_match_id),
        engineCode: meta?.code ?? 'MTG',
        p1Name: 'Claude',
        p1Note: 'ultra · seat 1',
        p2Name: 'Heuristic',
        p2Note: 'ultra · seat 2',
        watchPath: `/m/${spectator.current_match_id}`,
      };
    }
    return null;
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

        {/* ─── Demo controls — lab-styled Start/Stop for the spectator demo.
            Anyone can flip the toggle; single-shot by default. ─────────── */}
        <section
          aria-label="Spectator demo controls"
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 14,
            flexWrap: 'wrap',
            border: '1px solid var(--rule)',
            background: 'var(--paper-2)',
            padding: '12px 16px',
            marginBottom: 20,
            fontFamily: 'var(--font-mono)',
            fontSize: 11,
          }}
        >
          <span
            style={{
              fontWeight: 500,
              letterSpacing: '.14em',
              textTransform: 'uppercase',
              color: 'var(--ink-3)',
            }}
          >
            Demo
          </span>

          <span
            data-testid="demo-state"
            style={{
              padding: '3px 8px',
              border: '1px solid var(--rule)',
              color: spectator?.enabled ? 'var(--sodium)' : 'var(--ink-2)',
              letterSpacing: '.08em',
              textTransform: 'uppercase',
            }}
          >
            {spectator?.enabled ? '● Running' : '○ Idle'}
            {spectator?.enabled && spectator?.game_mode
              ? ` · ${GAME_MODE_LABELS[spectator.game_mode] ?? spectator.game_mode}`
              : ''}
          </span>

          <label
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              color: 'var(--ink-3)',
              letterSpacing: '.08em',
              textTransform: 'uppercase',
            }}
          >
            Game
            <select
              value={selectedMode}
              onChange={(e) => setSelectedMode(e.target.value)}
              disabled={toggleBusy || spectator?.enabled}
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: 11,
                padding: '4px 6px',
                border: '1px solid var(--rule)',
                background: 'var(--paper)',
                color: 'var(--ink)',
              }}
            >
              {supportedModes.map((m) => (
                <option key={m} value={m}>
                  {GAME_MODE_LABELS[m] ?? m}
                </option>
              ))}
            </select>
          </label>

          <button
            type="button"
            onClick={triggerStart}
            disabled={startDisabled}
            data-testid="demo-start"
            style={{
              ...demoButtonStyle,
              borderColor: 'var(--ink)',
              color: startDisabled ? 'var(--ink-3)' : 'var(--ink)',
              cursor: startDisabled ? 'not-allowed' : 'pointer',
              opacity: startDisabled ? 0.5 : 1,
            }}
          >
            ▶ Start a match
          </button>

          <button
            type="button"
            onClick={triggerStop}
            disabled={stopDisabled}
            data-testid="demo-stop"
            title="Stops queuing new matches. The currently-running match continues to its natural end."
            style={{
              ...demoButtonStyle,
              borderColor: stopDisabled ? 'var(--rule)' : 'var(--sodium)',
              color: stopDisabled ? 'var(--ink-3)' : 'var(--sodium)',
              cursor: stopDisabled ? 'not-allowed' : 'pointer',
              opacity: stopDisabled ? 0.5 : 1,
            }}
          >
            ■ Stop
          </button>

          {cooldownLeft > 0 && (
            <span style={{ color: 'var(--ink-3)', letterSpacing: '.04em' }}>
              cooldown {cooldownLeft}s
            </span>
          )}

          <span style={{ flex: 1 }} />

          <span
            style={{
              color: 'var(--ink-3)',
              letterSpacing: '.04em',
              fontSize: 10.5,
            }}
          >
            single-shot · auto-stops when match ends
          </span>

          {toggleError && (
            <div
              role="alert"
              data-testid="demo-error"
              style={{
                width: '100%',
                marginTop: 4,
                padding: '6px 10px',
                border: '1px solid var(--sodium)',
                color: 'var(--sodium)',
                fontSize: 11,
                letterSpacing: '.04em',
              }}
            >
              {toggleError}
            </div>
          )}
        </section>

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

            {/* Empty state — no spectator demo, no running bot games.
                The lab voice tells the user where to start one. */}
            {rows.length === 0 && (
              <div
                data-testid="lobby-empty"
                style={{
                  padding: '22px 14px',
                  fontFamily: 'var(--font-mono)',
                  fontSize: 11.5,
                  color: 'var(--ink-3)',
                  textAlign: 'left',
                  letterSpacing: '.04em',
                  borderTop: '1px solid var(--rule-2)',
                }}
              >
                No matches running. Start a bot vs bot run from the lab.
              </div>
            )}

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

          {/* Featured-live panel — pinned to the active spectator demo if
              one is running; otherwise an empty-state hint so the panel
              never lies about a fake live match. */}
          <aside
            data-testid="featured-panel"
            style={{
              border: '1px solid var(--ink)',
              background: 'var(--paper-2)',
              padding: 18,
              display: 'flex',
              flexDirection: 'column',
              gap: 14,
            }}
          >
            {featured ? (
              <>
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
                    {featured.engineCode}
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
              </>
            ) : (
              // Empty state — no spectator-demo is running, so don't
              // pretend with HD-8F4A mock data. Match the lab voice.
              <div
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 10,
                  minHeight: 140,
                  justifyContent: 'center',
                  alignItems: 'flex-start',
                }}
              >
                <small
                  style={{
                    fontFamily: 'var(--font-mono)',
                    fontSize: 10.5,
                    fontWeight: 500,
                    letterSpacing: '.14em',
                    textTransform: 'uppercase',
                    color: 'var(--ink-3)',
                  }}
                >
                  FEATURED · IDLE
                </small>
                <div
                  style={{
                    fontFamily: 'var(--font-serif)',
                    fontSize: 17,
                    color: 'var(--ink)',
                    lineHeight: 1.35,
                  }}
                >
                  No featured match. Start one from the lab.
                </div>
              </div>
            )}
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

const demoButtonStyle: React.CSSProperties = {
  fontFamily: 'var(--font-mono)',
  fontSize: 11,
  fontWeight: 500,
  letterSpacing: '.1em',
  textTransform: 'uppercase',
  padding: '5px 12px',
  border: '1px solid var(--ink)',
  background: 'transparent',
};

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
