/**
 * GameViewLayout — unified chrome for every game view.
 *
 * Wraps the mode-specific board (which stays untouched) with a brand top
 * bar (mode monogram + match metadata + exit button) and an optional
 * right rail (game log, reasoning panel). The board's own internal
 * scroll / layout is preserved; this component only owns the surround.
 *
 * Pages opt in by replacing their outer <div className="min-h-screen ...">
 * with a <GameViewLayout mode="..." matchId="...">; the rest of the page
 * body becomes its children.
 */

import { ReactNode } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Monogram } from './Monogram';
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
  /** Whether to show the back-to-home button. */
  showExit?: boolean;
  /** Render content edge-to-edge (default) vs in a centered max-width container. */
  contained?: boolean;
  /** Optional callback fired when the exit chip is clicked (e.g. concede). */
  onExit?: () => void;
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
  children,
}: GameViewLayoutProps) {
  const navigate = useNavigate();
  const meta = getMode(mode);
  const handleExit = () => {
    if (onExit) onExit();
    navigate('/');
  };

  return (
    <div className="min-h-screen bg-brand-ink text-brand-cream">
      <header className="sticky top-0 z-30 border-b border-brand-hairline/60 bg-brand-ink/85 backdrop-blur-xl">
        <div className={contained ? 'mx-auto max-w-7xl px-6 lg:px-8' : 'px-4 lg:px-6'}>
          <div className="h-14 flex items-center gap-5">
            {/* Mode badge */}
            <Link
              to="/"
              className="flex items-center gap-3 group"
              aria-label="HYPERDRAFT home"
            >
              {meta && <Monogram mode={meta} size={26} variant="foil" />}
              <span className="hidden md:flex flex-col leading-tight -mt-0.5">
                <span className="brand-eyebrow text-brand-foil group-hover:text-brand-foil-bright transition-colors">
                  {meta?.code ?? mode.toUpperCase()}
                </span>
                <span className="text-[13px] text-brand-cream tracking-wide font-display">
                  {meta?.title ?? mode}
                </span>
              </span>
            </Link>

            <span className="text-brand-mist" aria-hidden>·</span>

            {/* Match metadata strip */}
            <div className="flex items-center gap-5 brand-mono text-[11px] text-brand-chalk">
              {matchId && (
                <MetaPair label="match" value={matchId.slice(0, 8)} />
              )}
              {(turn !== undefined && turn !== null && turn !== '') && (
                <MetaPair label="turn" value={String(turn)} />
              )}
              {phase && <MetaPair label="phase" value={phase.toLowerCase()} />}
            </div>

            <div className="flex-1" />

            {/* Opponent / player chips */}
            {(opponentName || playerName) && (
              <div className="hidden lg:flex items-center gap-3 text-xs text-brand-chalk">
                {opponentName && (
                  <span className="px-2.5 py-1 border border-brand-hairline">
                    <span className="brand-eyebrow text-brand-dust mr-1.5">vs</span>
                    <span className="text-brand-cream">{opponentName}</span>
                  </span>
                )}
                {playerName && (
                  <span className="px-2.5 py-1 border border-brand-foil/40 bg-brand-foil/5">
                    <span className="brand-eyebrow text-brand-foil mr-1.5">you</span>
                    <span className="text-brand-cream">{playerName}</span>
                  </span>
                )}
              </div>
            )}

            {showExit && (
              <button
                onClick={handleExit}
                className="text-xs text-brand-chalk hover:text-brand-foil border border-brand-hairline hover:border-brand-foil/50 px-3 py-1.5 transition-colors"
              >
                ← Lobby
              </button>
            )}
          </div>
        </div>
      </header>

      {/* Main board + right rail */}
      <div className="relative">
        {rightRail ? (
          <div className="grid grid-cols-1 lg:grid-cols-[1fr_320px] min-h-[calc(100vh-3.5rem)]">
            <main className="relative">{children}</main>
            <aside className="border-l border-brand-hairline/60 bg-brand-obsidian/40 overflow-y-auto max-h-[calc(100vh-3.5rem)]">
              {rightRail}
            </aside>
          </div>
        ) : (
          <main className="relative min-h-[calc(100vh-3.5rem)]">{children}</main>
        )}
      </div>
    </div>
  );
}

function MetaPair({ label, value }: { label: string; value: string }) {
  return (
    <span className="flex items-baseline gap-1.5">
      <span className="brand-eyebrow text-brand-dust">{label}</span>
      <span className="text-brand-cream tracking-tight">{value}</span>
    </span>
  );
}

export default GameViewLayout;
