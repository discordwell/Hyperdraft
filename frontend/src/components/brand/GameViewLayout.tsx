/**
 * GameViewLayout — the seam between lab and game.
 *
 * Wraps every in-game view with a thin header strip (HYPERDRAFT mark,
 * mode code, match breadcrumb, opponent/player names, ⌥P discoverability
 * hint, ← Lab button) and renders the per-engine board into {children}
 * unchanged. The strip carries the player from the lab into the
 * experiment and back; each match's interior keeps its own chrome.
 *
 * The strip itself is rendered with the lab tokens (paper / ink /
 * sodium, Geist Mono telemetry, hairline rule below) so it reads as a
 * lab surface; the body below is the game's domain — do not lab-ify it.
 *
 * Phases C1 + D1 of docs/design/buildplan.md.
 */

import { CSSProperties, ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import { getMode, type GameModeId } from './modes';

export interface GameViewLayoutProps {
  mode: GameModeId;
  matchId?: string;
  turn?: number | string;
  phase?: string;
  opponentName?: string;
  playerName?: string;
  /** Right-rail slot — usually a game log or reasoning panel. */
  rightRail?: ReactNode;
  /** Whether to show the back-to-lab button. */
  showExit?: boolean;
  /** Render content edge-to-edge (default) vs in a centered max-width container. */
  contained?: boolean;
  /** Optional callback fired when the exit chip is clicked (e.g. concede). */
  onExit?: () => void;
  /**
   * Whether the ⌥P PipelineView overlay is currently open. When true the
   * discoverability hint hides, since the overlay is doing its own
   * teaching. Optional — defaults to false.
   */
  pipelineOpen?: boolean;
  children: ReactNode;
}

export function GameViewLayout({
  mode,
  matchId,
  turn,
  phase,
  opponentName,
  playerName,
  rightRail,
  showExit = true,
  contained = false,
  onExit,
  pipelineOpen = false,
  children,
}: GameViewLayoutProps) {
  const navigate = useNavigate();
  const meta = getMode(mode);
  const handleExit = () => {
    if (onExit) onExit();
    navigate('/');
  };
  const modeCode = meta?.code ?? mode.toUpperCase();
  const shortMatchId = matchId ? matchId.slice(0, 8).toUpperCase() : null;
  const turnStr =
    turn !== undefined && turn !== null && turn !== '' ? String(turn) : null;
  const phaseStr = phase ? phase.toUpperCase() : null;

  // Breadcrumb segments — only render the dots between segments that actually
  // exist, so a match with no turn yet doesn't show "MATCH HD · · PHASE".
  const crumbSegments: string[] = [];
  if (shortMatchId) crumbSegments.push(`MATCH ${shortMatchId}`);
  if (turnStr) crumbSegments.push(`TURN ${turnStr}`);
  if (phaseStr) crumbSegments.push(phaseStr);

  return (
    <div style={{ minHeight: '100vh', background: 'var(--paper)', color: 'var(--ink)' }}>
      <header style={headerStyle}>
        <div style={contained ? containedInner : edgeInner}>
          <div style={stripRow}>
            {/* HYPERDRAFT mark — mono micro-caps, click → Home. */}
            <button
              type="button"
              onClick={() => navigate('/')}
              style={wordmarkBtn}
              aria-label="HYPERDRAFT home"
            >
              HYPERDRAFT
            </button>

            <Divider />

            {/* Mode code — micro-caps, sodium accent. */}
            <span style={modeCodeStyle} aria-label={meta?.title ?? mode}>
              {modeCode}
            </span>

            {/* Breadcrumb — MATCH HD-XXXX · TURN N · PHASE. */}
            {crumbSegments.length > 0 && (
              <>
                <Divider />
                <span style={crumbStyle}>{crumbSegments.join(' · ')}</span>
              </>
            )}

            <div style={{ flex: 1 }} />

            {/* Opponent · vs · player. */}
            {(opponentName || playerName) && (
              <span style={vsStyle}>
                {opponentName && <span style={oppName}>{opponentName}</span>}
                {opponentName && playerName && (
                  <span style={vsToken} aria-hidden>
                    vs
                  </span>
                )}
                {playerName && <span style={meName}>{playerName}</span>}
              </span>
            )}

            {/* ⌥P · pipeline discoverability hint. Hidden when the
                overlay is open — at that point the overlay itself is the
                teacher. */}
            {!pipelineOpen && <span style={pipelineHint}>⌥P · pipeline</span>}

            {showExit && (
              <button
                type="button"
                onClick={handleExit}
                style={exitBtn}
                onMouseEnter={(e) => {
                  e.currentTarget.style.background = 'var(--ink)';
                  e.currentTarget.style.color = 'var(--paper)';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.background = 'transparent';
                  e.currentTarget.style.color = 'var(--ink)';
                }}
              >
                ← Lab
              </button>
            )}
          </div>
        </div>
      </header>

      {/* Main board + optional right rail — body is the per-engine chrome's
          domain. Do not apply lab tokens here. */}
      <div style={{ position: 'relative' }}>
        {rightRail ? (
          <div
            className="grid grid-cols-1 lg:grid-cols-[1fr_320px]"
            style={{ minHeight: 'calc(100vh - 3.5rem)' }}
          >
            <main style={{ position: 'relative' }}>{children}</main>
            <aside
              className="border-l border-brand-hairline/60 bg-brand-obsidian/40 overflow-y-auto"
              style={{ maxHeight: 'calc(100vh - 3.5rem)' }}
            >
              {rightRail}
            </aside>
          </div>
        ) : (
          <main style={{ position: 'relative', minHeight: 'calc(100vh - 3.5rem)' }}>
            {children}
          </main>
        )}
      </div>
    </div>
  );
}

function Divider() {
  return (
    <span
      aria-hidden
      style={{
        color: 'var(--ink-3)',
        fontFamily: 'var(--font-mono)',
        fontSize: 11,
      }}
    >
      ·
    </span>
  );
}

// === Style tokens — lab posture only on the header strip. =================

const headerStyle: CSSProperties = {
  position: 'sticky',
  top: 0,
  zIndex: 30,
  background: 'var(--paper)',
  borderBottom: '1px solid var(--rule)',
};

const edgeInner: CSSProperties = { padding: '0 18px' };
const containedInner: CSSProperties = {
  maxWidth: 1280,
  margin: '0 auto',
  padding: '0 24px',
};

const stripRow: CSSProperties = {
  height: 56,
  display: 'flex',
  alignItems: 'center',
  gap: 14,
  fontFamily: 'var(--font-sans)',
};

const wordmarkBtn: CSSProperties = {
  fontFamily: 'var(--font-mono)',
  fontSize: 12,
  fontWeight: 500,
  letterSpacing: '.14em',
  textTransform: 'uppercase',
  color: 'var(--ink)',
  background: 'transparent',
  border: 'none',
  padding: 0,
  cursor: 'pointer',
};

const modeCodeStyle: CSSProperties = {
  fontFamily: 'var(--font-mono)',
  fontSize: 10.5,
  fontWeight: 500,
  letterSpacing: '.18em',
  textTransform: 'uppercase',
  color: 'var(--sodium)',
};

const crumbStyle: CSSProperties = {
  fontFamily: 'var(--font-mono)',
  fontSize: 11,
  fontWeight: 500,
  letterSpacing: '.1em',
  textTransform: 'uppercase',
  color: 'var(--ink-2)',
  fontVariantNumeric: 'tabular-nums',
};

const vsStyle: CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  gap: 8,
  fontFamily: 'var(--font-mono)',
  fontSize: 11,
  letterSpacing: '.04em',
  color: 'var(--ink-2)',
};

const oppName: CSSProperties = {
  color: 'var(--ink)',
};

const vsToken: CSSProperties = {
  color: 'var(--ink-3)',
  textTransform: 'uppercase',
  letterSpacing: '.14em',
  fontSize: 10,
};

const meName: CSSProperties = {
  color: 'var(--ink)',
  borderBottom: '1.5px solid var(--sodium)',
  paddingBottom: 1,
};

const pipelineHint: CSSProperties = {
  fontFamily: 'var(--font-mono)',
  fontSize: 10,
  letterSpacing: '.08em',
  color: 'var(--ink-3)',
  whiteSpace: 'nowrap',
};

const exitBtn: CSSProperties = {
  fontFamily: 'var(--font-mono)',
  fontSize: 11,
  fontWeight: 500,
  letterSpacing: '.12em',
  textTransform: 'uppercase',
  padding: '6px 10px',
  background: 'transparent',
  color: 'var(--ink)',
  border: '1px solid var(--ink)',
  cursor: 'pointer',
  transition: 'background 120ms, color 120ms',
};

export default GameViewLayout;
