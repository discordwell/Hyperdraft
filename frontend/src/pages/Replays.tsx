/**
 * Replays — lab-port index of archived match replays (Phase C2 of the buildplan).
 *
 * Between-games surface: full lab posture (paper / ink / sodium, Instrument
 * Serif headings, Geist Mono telemetry, hairline rules). The per-engine
 * GameViews keep their own chrome — this is the lobby, not a match.
 *
 * Layout mirrors Home.tsx: fixed caption rail at top, ink-ruled masthead,
 * `01 SECTION` head with a sodium italic word in the title, then a tabular
 * rack of completed matches. Each row clicks through to /replay/match/:id —
 * ReplayView itself was lab-ported separately via BIG MOVE 17 Timeline.
 */

import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { matchAPI } from '../services/api';
import { getMode } from '../components/brand';
import { SectionHead } from '../components/lab';

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

/**
 * Stable 4-char hex short-code for a match ID, prefixed with `HD-`. The match
 * IDs persisted by the server are arbitrary strings; for the rack we want the
 * `HD-8F4A`-style label used elsewhere in the lab UI (cf. the live-now widget
 * on Home.tsx). Hash the input deterministically so the same match always
 * gets the same code across reloads.
 */
function shortCode(matchId: string): string {
  // Tiny FNV-1a — deterministic, no external dep.
  let h = 0x811c9dc5;
  for (let i = 0; i < matchId.length; i += 1) {
    h ^= matchId.charCodeAt(i);
    h = (h + ((h << 1) + (h << 4) + (h << 7) + (h << 8) + (h << 24))) >>> 0;
  }
  return `HD-${h.toString(16).slice(0, 4).toUpperCase()}`;
}

export function Replays() {
  const navigate = useNavigate();
  const [entries, setEntries] = useState<ReplayEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    matchAPI.listReplays(50)
      .then((r) => { if (!cancelled) setEntries(r.replays); })
      .catch((e) => { if (!cancelled) setError(e instanceof Error ? e.message : 'Failed to load replays'); });
    return () => { cancelled = true; };
  }, []);

  const count = entries?.length ?? 0;

  return (
    <div style={{ background: 'var(--paper)', color: 'var(--ink)', minHeight: '100vh' }}>
      {/* ─── Caption rail ─────────────────────────────────────────────── */}
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
        <b style={{ color: 'var(--ink)', fontWeight: 500 }}>HD-REPLAYS</b>
        &nbsp;·&nbsp; LIBRARY &nbsp;·&nbsp; v4.7
      </div>

      <main
        style={{
          maxWidth: 1240,
          margin: '0 auto',
          padding: '88px 56px 160px',
          position: 'relative',
        }}
      >
        {/* ─── Masthead ───────────────────────────────────────────────── */}
        <header
          style={{
            display: 'grid',
            gridTemplateColumns: '1fr auto',
            alignItems: 'end',
            borderTop: '1.5px solid var(--ink)',
            borderBottom: '1.5px solid var(--ink)',
            padding: '18px 0 22px',
            marginBottom: 40,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 14, flexWrap: 'wrap' }}>
            <span
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: 12,
                fontWeight: 500,
                letterSpacing: '.12em',
                textTransform: 'uppercase',
                color: 'var(--ink-2)',
              }}
            >
              HYPERDRAFT
            </span>
            <span
              style={{
                fontFamily: 'var(--font-serif)',
                fontSize: 34,
                fontStyle: 'italic',
                color: 'var(--ink)',
                letterSpacing: '-.02em',
                lineHeight: 1,
              }}
            >
              / Replays
            </span>
          </div>
          <span
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 12,
              fontWeight: 500,
              letterSpacing: '.06em',
              color: 'var(--ink-2)',
              textAlign: 'right',
            }}
          >
            v4.7 · {count} archived
          </span>
        </header>

        {/* ─── Section 01 · Replay library ─────────────────────────────── */}
        <section>
          <SectionHead
            num="01"
            title={
              <>
                Replay <em style={{ color: 'var(--sodium)', fontStyle: 'italic' }}>library</em>.
              </>
            }
            meta="Past matches across every engine on the shelf. Click a row to scrub the recording."
          />

          {/* Error band */}
          {error && (
            <div
              style={{
                marginTop: 24,
                border: '1px solid var(--halt)',
                background: 'color-mix(in oklab, var(--halt) 8%, transparent)',
                padding: '12px 16px',
                fontSize: 13,
                color: 'var(--halt)',
                fontFamily: 'var(--font-mono)',
                letterSpacing: '.04em',
              }}
            >
              {error}
            </div>
          )}

          {/* Loading state */}
          {entries === null && !error && (
            <div
              style={{
                marginTop: 24,
                padding: '24px 18px',
                border: '1px solid var(--rule)',
                background: 'var(--paper-2)',
                fontFamily: 'var(--font-mono)',
                fontSize: 11,
                letterSpacing: '.14em',
                textTransform: 'uppercase',
                color: 'var(--ink-3)',
                display: 'flex',
                alignItems: 'center',
                gap: 10,
              }}
            >
              <span
                style={{
                  width: 10,
                  height: 10,
                  borderRadius: '50%',
                  background: 'var(--sodium)',
                  animation: 'pulse 1.6s ease-in-out infinite',
                }}
              />
              Loading archive…
            </div>
          )}

          {/* Empty state */}
          {entries !== null && entries.length === 0 && (
            <div
              style={{
                marginTop: 24,
                padding: '40px 28px',
                border: '1px solid var(--rule)',
                background: 'var(--paper-2)',
                textAlign: 'center',
              }}
            >
              <span
                style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: 10.5,
                  fontWeight: 500,
                  letterSpacing: '.14em',
                  textTransform: 'uppercase',
                  color: 'var(--sodium)',
                }}
              >
                Archive empty
              </span>
              <p
                style={{
                  margin: '12px auto 0',
                  fontFamily: 'var(--font-serif)',
                  fontStyle: 'italic',
                  fontSize: 18,
                  lineHeight: 1.5,
                  color: 'var(--ink-2)',
                  maxWidth: '52ch',
                }}
              >
                No completed matches have been archived yet. Enable the spectator demo
                (
                <code
                  style={{
                    fontFamily: 'var(--font-mono)',
                    fontSize: 13,
                    fontStyle: 'normal',
                    color: 'var(--sodium)',
                  }}
                >
                  HYPERDRAFT_SPECTATOR_ENABLED=true
                </code>
                ) or finish a human-vs-bot match and it'll appear here.
              </p>
            </div>
          )}

          {/* Rack of replays */}
          {entries !== null && entries.length > 0 && (
            <div
              style={{
                marginTop: 24,
                border: '1px solid var(--rule)',
                background: 'var(--paper-2)',
              }}
            >
              {/* Column header strip — mono, ink-3 */}
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: '56px 110px 1fr 90px 110px 100px 24px',
                  gap: 14,
                  alignItems: 'center',
                  padding: '12px 16px',
                  borderBottom: '1px solid var(--rule)',
                  fontFamily: 'var(--font-mono)',
                  fontSize: 10.5,
                  fontWeight: 500,
                  letterSpacing: '.14em',
                  textTransform: 'uppercase',
                  color: 'var(--ink-3)',
                }}
              >
                <span>Engine</span>
                <span>Match</span>
                <span>Archetype</span>
                <span>Turns</span>
                <span>Winner</span>
                <span>Archived</span>
                <span />
              </div>

              {entries.map((e, idx) => {
                const meta = e.game_mode ? getMode(e.game_mode) : undefined;
                const code = meta?.code ?? (e.game_mode ?? 'UNK').toUpperCase();
                const name = meta?.name ?? e.game_mode ?? 'unknown mode';
                const stripe = idx % 2 === 0 ? 'transparent' : 'var(--paper-3)';
                return (
                  <button
                    key={e.match_id}
                    type="button"
                    aria-label={`Open replay ${shortCode(e.match_id)} · ${name}`}
                    onClick={() => navigate(`/replay/match/${e.match_id}`)}
                    style={{
                      display: 'grid',
                      gridTemplateColumns: '56px 110px 1fr 90px 110px 100px 24px',
                      gap: 14,
                      alignItems: 'center',
                      padding: '14px 16px',
                      width: '100%',
                      textAlign: 'left',
                      background: stripe,
                      borderTop: idx === 0 ? 'none' : '1px solid var(--rule-2)',
                      border: 'none',
                      borderRadius: 0,
                      cursor: 'pointer',
                      fontFamily: 'var(--font-sans)',
                      color: 'var(--ink)',
                    }}
                    onMouseEnter={(ev) => {
                      ev.currentTarget.style.background = 'color-mix(in oklab, var(--sodium) 6%, var(--paper-2))';
                    }}
                    onMouseLeave={(ev) => {
                      ev.currentTarget.style.background = stripe;
                    }}
                  >
                    {/* Engine code — mono, ink-3 */}
                    <span
                      style={{
                        fontFamily: 'var(--font-mono)',
                        fontSize: 11,
                        fontWeight: 500,
                        letterSpacing: '.1em',
                        color: 'var(--ink-3)',
                      }}
                    >
                      {code}
                    </span>

                    {/* Match short-code — mono, ink */}
                    <span
                      style={{
                        fontFamily: 'var(--font-mono)',
                        fontSize: 12,
                        fontWeight: 500,
                        letterSpacing: '.04em',
                        color: 'var(--ink)',
                      }}
                    >
                      {shortCode(e.match_id)}
                    </span>

                    {/* Archetype / mode name — Instrument Serif */}
                    <span
                      style={{
                        fontFamily: 'var(--font-serif)',
                        fontSize: 18,
                        fontWeight: 400,
                        letterSpacing: '-.01em',
                        color: 'var(--ink)',
                      }}
                    >
                      {name}
                    </span>

                    {/* Turn count — mono, ink-2 tabular */}
                    <span
                      style={{
                        fontFamily: 'var(--font-mono)',
                        fontSize: 12,
                        fontWeight: 500,
                        letterSpacing: '.04em',
                        color: 'var(--ink-2)',
                        fontVariantNumeric: 'tabular-nums',
                      }}
                    >
                      {e.total_turns ?? '—'}
                      <span style={{ color: 'var(--ink-3)', marginLeft: 4 }}>turns</span>
                    </span>

                    {/* Winner — mono, ink-2 */}
                    <span
                      style={{
                        fontFamily: 'var(--font-mono)',
                        fontSize: 11,
                        fontWeight: 500,
                        letterSpacing: '.06em',
                        color: e.winner ? 'var(--ink-2)' : 'var(--ink-3)',
                      }}
                    >
                      {e.winner ?? '—'}
                    </span>

                    {/* Timestamp — mono, ink-3 */}
                    <span
                      style={{
                        fontFamily: 'var(--font-mono)',
                        fontSize: 11,
                        fontWeight: 500,
                        letterSpacing: '.06em',
                        color: 'var(--ink-3)',
                      }}
                    >
                      {fmtAgo(e.archived_at)}
                    </span>

                    {/* Trailing arrow — sodium */}
                    <span
                      aria-hidden
                      style={{
                        fontFamily: 'var(--font-mono)',
                        fontSize: 14,
                        color: 'var(--sodium)',
                        textAlign: 'right',
                      }}
                    >
                      →
                    </span>
                  </button>
                );
              })}
            </div>
          )}
        </section>

        {/* ─── Footer ──────────────────────────────────────────────────── */}
        <footer
          style={{
            marginTop: 96,
            paddingTop: 28,
            borderTop: '1.5px solid var(--ink)',
            display: 'flex',
            justifyContent: 'space-between',
            flexWrap: 'wrap',
            gap: 14,
            fontFamily: 'var(--font-mono)',
            fontSize: 11,
            color: 'var(--ink-3)',
            letterSpacing: '.06em',
          }}
        >
          <span>uvicorn src.server.main:socket_app · port 8030</span>
          <span style={{ letterSpacing: '.1em', textTransform: 'uppercase' }}>
            HYPERDRAFT · REPLAYS
          </span>
        </footer>
      </main>

      {/* Inline keyframes for the loading dot — scoped to this surface. */}
      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.35; }
        }
      `}</style>
    </div>
  );
}

// === Lab composition helpers ============================================
// Mirrors the SectionHead used by Home.tsx so the two between-games surfaces
// read as one continuous lab. Kept local rather than extracted because the
// numbering / metadata semantics are page-specific.


export default Replays;
