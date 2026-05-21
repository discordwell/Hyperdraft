/**
 * ReplayView Page
 *
 * Watch a completed bot-vs-bot replay (or a live game's frames so far).
 */

import { useEffect, useMemo, useState } from 'react';
import { useLocation, useNavigate, useParams } from 'react-router-dom';
import { botGameAPI, matchAPI } from '../services/api';
import { GameBoard } from '../components/game';
import { HSGameBoard } from '../components/game/HSGameBoard';
import { PKMGameBoard } from '../components/game/PKMGameBoard';
import { YGOGameBoard } from '../components/game/YGOGameBoard';
import { MCGameBoard } from '../components/game/MCGameBoard';
import { FinanceGameBoard } from '../games/finance';
import { DepthsGameBoard } from '../games/depths';
import type { DepthBand } from '../games/depths';
import { SCPBoard } from '../components/game/SCPBoard';
import { CatsBoard } from '../components/game/CatsBoard';
import { Timeline } from '../components/lab';
import type { ReplayFrame, ReplayResponse, GameState, CardData } from '../types';

// ---------------------------------------------------------------------------
// Replay board dispatch — pick the per-engine board for the current frame.
//
// `/replay/:gameId` (and `/replay/match/:matchId`) historically always
// rendered the MTG `<GameBoard>` regardless of what engine actually played
// the game out, which made e.g. a Minecraft replay try to render MC cards
// inside an MTG "battlefield / stack / phases" frame — meaningless for the
// audience.
//
// `ReplayBoardSwitch` selects on the frame's `game_mode` and renders the
// matching per-engine board. Each board's interactive callbacks (play /
// attack / end-turn) are wired to no-ops because a replay is read-only by
// definition — the user is scrubbing recorded frames, not driving the game.
//
// Mapping (must stay in lock-step with SpectatorView's same dispatch):
//   'mtg'        → GameBoard
//   'hearthstone'→ HSGameBoard
//   'pokemon'    → PKMGameBoard
//   'yugioh'     → YGOGameBoard
//   'minecraft'  → MCGameBoard
//   'finance'    → FinanceGameBoard
//   'depths'     → DepthsGameBoard
//   'scp'        → SCPBoard (read-only adapter; see components/game/SCPBoard.tsx)
//   'cats'       → CatsBoard (read-only adapter; see components/game/CatsBoard.tsx)
//   unknown      → MTG GameBoard + console.warn
//
// SCP and Cats no longer fall back to GameBoard — both now have dedicated
// read-only board adapters that accept `{ gameState, playerId, readOnly }`
// and share visual primitives with their respective live GameView pages.
// ---------------------------------------------------------------------------

const noop = () => undefined;

interface ReplayBoardSwitchProps {
  gameState: GameState;
  playerId: string;
}

function ReplayBoardSwitch({ gameState, playerId }: ReplayBoardSwitchProps) {
  const mode = gameState.game_mode ?? 'mtg';

  if (mode === 'mtg') {
    return <GameBoard gameState={gameState} playerId={playerId} />;
  }

  if (mode === 'hearthstone') {
    return (
      <HSGameBoard
        gameState={gameState}
        playerId={playerId}
        isMyTurn={false}
        canPlayCard={() => false}
        canAttuneCard={() => false}
        canAttack={() => false}
        canUseHeroPower={false}
        getAttackableTargets={() => []}
        onPlayCard={noop}
        onAttuneCard={noop}
        onAttack={noop}
        onHeroPower={noop}
        onEndTurn={noop}
      />
    );
  }

  if (mode === 'pokemon') {
    const opponentId = Object.keys(gameState.players).find((id) => id !== playerId) || '';
    const myPlayer = gameState.players[playerId] || null;
    const opponentPlayer = opponentId ? gameState.players[opponentId] : null;
    const myActivePokemon = gameState.active_pokemon?.[playerId] ?? null;
    const opponentActivePokemon = opponentId ? gameState.active_pokemon?.[opponentId] ?? null : null;
    const myBench = gameState.bench?.[playerId] ?? [];
    const opponentBench = opponentId ? gameState.bench?.[opponentId] ?? [] : [];
    const stadiumCard = gameState.stadium_card ?? null;
    const hand = gameState.hand ?? [];
    const myGraveyard = gameState.graveyard?.[playerId] ?? [];
    const opponentGraveyard = opponentId ? gameState.graveyard?.[opponentId] ?? [] : [];

    return (
      <PKMGameBoard
        gameState={gameState}
        playerId={playerId}
        isMyTurn={false}
        myPlayer={myPlayer}
        opponentPlayer={opponentPlayer}
        myActivePokemon={myActivePokemon}
        opponentActivePokemon={opponentActivePokemon}
        myBench={myBench}
        opponentBench={opponentBench}
        stadiumCard={stadiumCard}
        hand={hand}
        myGraveyard={myGraveyard}
        opponentGraveyard={opponentGraveyard}
        canPlayCard={() => false}
        canAttachEnergy={() => false}
        onPlayCard={noop}
        onAttachEnergy={noop}
        onAttack={noop}
        onRetreat={noop}
        onEvolve={noop}
        onUseAbility={noop}
        onEndTurn={noop}
      />
    );
  }

  if (mode === 'yugioh') {
    const opponentId = Object.keys(gameState.players).find((id) => id !== playerId) || '';
    const myPlayer = gameState.players[playerId] || null;
    const opponentPlayer = opponentId ? gameState.players[opponentId] : null;
    const myMonsterZones = gameState.monster_zones?.[playerId] ?? [null, null, null, null, null];
    const oppMonsterZones = opponentId
      ? gameState.monster_zones?.[opponentId] ?? [null, null, null, null, null]
      : [null, null, null, null, null];
    const mySpellTrapZones = gameState.spell_trap_zones?.[playerId] ?? [null, null, null, null, null];
    const oppSpellTrapZones = opponentId
      ? gameState.spell_trap_zones?.[opponentId] ?? [null, null, null, null, null]
      : [null, null, null, null, null];
    const myFieldSpell = gameState.field_spells?.[playerId] ?? null;
    const oppFieldSpell = opponentId ? gameState.field_spells?.[opponentId] ?? null : null;
    const hand = gameState.hand ?? [];
    const myGraveyard = gameState.graveyard?.[playerId] ?? [];
    const oppGraveyard = opponentId ? gameState.graveyard?.[opponentId] ?? [] : [];
    const myBanished = gameState.banished?.[playerId] ?? [];
    const oppBanished = opponentId ? gameState.banished?.[opponentId] ?? [] : [];
    const myExtraDeckSize = gameState.extra_deck_sizes?.[playerId] ?? 0;
    const oppExtraDeckSize = opponentId ? gameState.extra_deck_sizes?.[opponentId] ?? 0 : 0;

    return (
      <YGOGameBoard
        gameState={gameState}
        playerId={playerId}
        isMyTurn={false}
        myPlayer={myPlayer}
        opponentPlayer={opponentPlayer}
        myMonsterZones={myMonsterZones}
        oppMonsterZones={oppMonsterZones}
        mySpellTrapZones={mySpellTrapZones}
        oppSpellTrapZones={oppSpellTrapZones}
        myFieldSpell={myFieldSpell}
        oppFieldSpell={oppFieldSpell}
        hand={hand}
        myGraveyard={myGraveyard}
        oppGraveyard={oppGraveyard}
        myBanished={myBanished}
        oppBanished={oppBanished}
        myExtraDeckSize={myExtraDeckSize}
        oppExtraDeckSize={oppExtraDeckSize}
        ygoPhase={gameState.ygo_phase ?? 'MAIN1'}
        onNormalSummon={noop}
        onSetMonster={noop}
        onFlipSummon={noop}
        onChangePosition={noop}
        onActivateCard={noop}
        onSetSpellTrap={noop}
        onDeclareAttack={noop}
        onDirectAttack={noop}
        onEndPhase={noop}
        onEndTurn={noop}
      />
    );
  }

  if (mode === 'minecraft') {
    const opponentId = Object.keys(gameState.players).find((id) => id !== playerId) || '';
    const myPlayer = gameState.players[playerId] || null;
    const opponentPlayer = opponentId ? gameState.players[opponentId] : null;
    const myMobs = gameState.battlefield.filter((c: CardData) => c.controller === playerId);
    const opponentMobs = opponentId
      ? gameState.battlefield.filter((c: CardData) => c.controller === opponentId)
      : [];

    return (
      <MCGameBoard
        gameState={gameState}
        playerId={playerId}
        opponentId={opponentId || null}
        myPlayer={myPlayer}
        opponentPlayer={opponentPlayer}
        myMobs={myMobs}
        opponentMobs={opponentMobs}
        isMyTurn={false}
        canPlayCard={() => false}
        canUseMob={() => false}
        canBlockMob={() => false}
        onPlayCard={noop}
        onMineWorker={noop}
        onAvatarMine={noop}
        onAvatarExplore={noop}
        onAvatarAttack={noop}
        onAttack={noop}
        onDeclareBlockers={noop}
        onEndTurn={noop}
      />
    );
  }

  if (mode === 'finance') {
    const opponentId = Object.keys(gameState.players).find((id) => id !== playerId) || '';
    const myPlayer = gameState.players[playerId] || null;
    const opponentPlayer = opponentId ? gameState.players[opponentId] : null;
    const battlefield = gameState.battlefield ?? [];
    const myTraders = battlefield.filter(
      (c) => c.controller === playerId && c.types.includes('FIN_TRADER'),
    );
    const myAssets = battlefield.filter(
      (c) => c.controller === playerId && c.types.includes('FIN_ASSET'),
    );
    const myStructures = battlefield.filter(
      (c) => c.controller === playerId && c.types.includes('FIN_STRUCTURE'),
    );
    const oppTraders = opponentId
      ? battlefield.filter((c) => c.controller === opponentId && c.types.includes('FIN_TRADER'))
      : [];
    const oppAssets = opponentId
      ? battlefield.filter((c) => c.controller === opponentId && c.types.includes('FIN_ASSET'))
      : [];

    const gs = gameState as unknown as Record<string, unknown>;
    const turnData = gs['finance_turn_data'] as Record<string, unknown> | undefined;
    const rawDeriv = turnData?.[`finance_deriv_desk_${playerId}`];
    const myDerivDesk: string[] = Array.isArray(rawDeriv) ? (rawDeriv as string[]) : [];

    return (
      <FinanceGameBoard
        gameState={gameState}
        playerId={playerId}
        opponentId={opponentId || null}
        myPlayer={myPlayer}
        opponentPlayer={opponentPlayer}
        myTraders={myTraders}
        myAssets={myAssets}
        myStructures={myStructures}
        myHand={gameState.hand ?? []}
        myDerivDesk={myDerivDesk}
        oppTraders={oppTraders}
        oppAssets={oppAssets}
        currentPhase={gameState.finance_phase ?? gameState.phase ?? 'PRE_MARKET'}
        myLiquidity={myPlayer?.mana_crystals_available ?? 0}
        myLiquidityMax={myPlayer?.mana_crystals ?? 0}
        darkPoolActive={!!gameState.finance_dark_pool}
        isMyTurn={false}
        canPlayCard={() => false}
        canAttack={() => false}
        canBlock={() => false}
        onPlayCard={noop}
        onDeclareAttackers={noop}
        onDeclareBlockers={noop}
        onActivateAbility={noop}
        onEndTurn={noop}
      />
    );
  }

  if (mode === 'depths') {
    const opponentId = Object.keys(gameState.players).find((id) => id !== playerId) || '';
    const myPlayer = gameState.players[playerId] || null;
    const opponentPlayer = opponentId ? gameState.players[opponentId] : null;
    const battlefield = gameState.battlefield ?? [];
    const myVessels = battlefield.filter(
      (c) => c.controller === playerId && !c.is_flagship && !c.types.includes('DEPTHS_MINE'),
    );
    const oppVessels = opponentId
      ? battlefield.filter(
          (c) =>
            c.controller === opponentId && !c.is_flagship && !c.types.includes('DEPTHS_MINE'),
        )
      : [];
    const myFlagship = battlefield.find((c) => c.controller === playerId && c.is_flagship) ?? null;
    const opponentFlagship = opponentId
      ? battlefield.find((c) => c.controller === opponentId && c.is_flagship) ?? null
      : null;
    const myMines = battlefield.filter(
      (c) => c.controller === playerId && c.types.includes('DEPTHS_MINE'),
    );
    const oppMines = opponentId
      ? battlefield.filter(
          (c) => c.controller === opponentId && c.types.includes('DEPTHS_MINE'),
        )
      : [];

    // DepthsGameBoard's onPlayCard / onLayMine take a DepthBand; pass-throughs
    // are no-ops in replay mode, so we cast the noop to swallow whatever
    // signature it receives.
    const noopDepth = (_a?: string, _b?: DepthBand) => undefined;

    return (
      <DepthsGameBoard
        gameState={gameState}
        playerId={playerId}
        opponentId={opponentId || null}
        myPlayer={myPlayer}
        opponentPlayer={opponentPlayer}
        myFlagship={myFlagship}
        opponentFlagship={opponentFlagship}
        myVessels={myVessels}
        opponentVessels={oppVessels}
        myMines={myMines}
        opponentMines={oppMines}
        isMyTurn={false}
        canPlayCard={() => false}
        canUseVessel={() => false}
        canIntercept={() => false}
        onPlayCard={noopDepth}
        onDive={noop}
        onSurface={noop}
        onLayMine={(_id, _band) => undefined}
        onDeclareAttackers={noop}
        onDetect={noop}
        onDeclareInterceptors={noop}
        onActivateAbility={noop}
        onEndTurn={noop}
      />
    );
  }

  if (mode === 'scp') {
    return <SCPBoard gameState={gameState} playerId={playerId} readOnly />;
  }

  if (mode === 'cats') {
    return <CatsBoard gameState={gameState} playerId={playerId} readOnly />;
  }

  // Unknown engine — surface the gap loudly and fall back to GameBoard so the
  // page doesn't blank.
  console.warn(
    `[ReplayBoardSwitch] No per-engine board for game_mode='${mode}'; falling back to GameBoard.`,
  );
  return <GameBoard gameState={gameState} playerId={playerId} />;
}

type ReplayMode = 'action' | 'phase';

interface PhaseSlice {
  start: number;
  end: number;
  turn: number;
  phase: string;
  step: string;
}

function getSpectatorPlayerId(state: GameState | null): string {
  if (!state) return '';
  const ids = Object.keys(state.players);
  return ids.length ? ids[0] : '';
}

function summarizeFrameAction(frame: ReplayFrame | null): { title: string; reasoning?: string; model?: string; prompt?: string } {
  if (!frame || !frame.action) return { title: 'No action' };

  const a = frame.action as Record<string, unknown>;

  if (a.kind === 'action_processed') {
    const who = String(a.player_name || a.player_id || 'Player');
    const what = String(a.action_type || 'ACTION');
    const card = a.card_name ? ` ${String(a.card_name)}` : '';
    const dataObj = a.data as Record<string, unknown> | undefined;
    const ai = dataObj?.ai as Record<string, unknown> | undefined;
    const reasoning = typeof ai?.reasoning === 'string' ? ai.reasoning : undefined;
    const model = typeof ai?.model === 'string' ? ai.model : undefined;
    const prompt = typeof ai?.prompt === 'string' ? ai.prompt : undefined;
    return { title: `${who}: ${what}${card}`, reasoning, model, prompt };
  }

  if (a.kind === 'ai_choice') {
    const who = String(a.player_name || a.player_id || 'Player');
    return { title: `${who}: choice (${String(a.choice_type || 'unknown')})` };
  }

  if (typeof a.type === 'string') {
    return { title: a.type };
  }

  return { title: 'Action' };
}

function isInteresting(frame: ReplayFrame): boolean {
  const a = frame.action as Record<string, unknown> | null;
  return a?.kind === 'action_processed' && typeof a.action_type === 'string' && a.action_type !== 'PASS';
}

function findPrevInteresting(frames: ReplayFrame[], fromIndex: number): number | null {
  for (let i = Math.min(fromIndex - 1, frames.length - 1); i >= 0; i -= 1) {
    if (isInteresting(frames[i])) return i;
  }
  return null;
}

function findNextInteresting(frames: ReplayFrame[], fromIndex: number): number | null {
  for (let i = Math.max(0, fromIndex + 1); i < frames.length; i += 1) {
    if (isInteresting(frames[i])) return i;
  }
  return null;
}

function buildPhaseSlices(frames: ReplayFrame[]): PhaseSlice[] {
  const slices: PhaseSlice[] = [];

  for (let i = 0; i < frames.length; i += 1) {
    const frame = frames[i];
    const prev = slices[slices.length - 1];

    if (!prev || prev.turn !== frame.turn || prev.phase !== frame.phase || prev.step !== frame.step) {
      slices.push({
        start: i,
        end: i,
        turn: frame.turn,
        phase: frame.phase,
        step: frame.step,
      });
      continue;
    }

    prev.end = i;
  }

  return slices;
}

function countInterestingInSlice(frames: ReplayFrame[], slice: PhaseSlice): number {
  let count = 0;
  for (let i = slice.start; i <= slice.end; i += 1) {
    if (isInteresting(frames[i])) count += 1;
  }
  return count;
}

function findPrevTurnSlice(slices: PhaseSlice[], currentPhaseIndex: number): number | null {
  if (currentPhaseIndex <= 0) return null;

  const currentTurn = slices[currentPhaseIndex].turn;
  for (let i = currentPhaseIndex - 1; i >= 0; i -= 1) {
    if (slices[i].turn < currentTurn) {
      const turn = slices[i].turn;
      let firstForTurn = i;
      while (firstForTurn > 0 && slices[firstForTurn - 1].turn === turn) {
        firstForTurn -= 1;
      }
      return firstForTurn;
    }
  }

  return null;
}

function findNextTurnSlice(slices: PhaseSlice[], currentPhaseIndex: number): number | null {
  if (currentPhaseIndex >= slices.length - 1) return null;

  const currentTurn = slices[currentPhaseIndex].turn;
  for (let i = currentPhaseIndex + 1; i < slices.length; i += 1) {
    if (slices[i].turn > currentTurn) {
      return i;
    }
  }

  return null;
}

export function ReplayView() {
  // The route resolves into one of two shapes:
  //   /replay/:gameId          — bot_game replay (legacy)
  //   /replay/match/:matchId   — match replay (Phase 3 of the replay rollout)
  //
  // We branch by location.pathname rather than splitting into two
  // components because every control + render path is identical;
  // only the data fetcher differs.
  const { gameId, matchId } = useParams<{ gameId?: string; matchId?: string }>();
  const location = useLocation();
  const navigate = useNavigate();

  const isMatchReplay = location.pathname.startsWith('/replay/match/');
  const replayId = (isMatchReplay ? matchId : gameId) ?? '';

  const [replay, setReplay] = useState<ReplayResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const [frameIndex, setFrameIndex] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [speedMs, setSpeedMs] = useState(300);
  // FFWD = skip past non-interesting frames during auto-advance so the
  // replay races through PASS_PRIORITY chains and stops on each real
  // action. Independent of speedMs so the user can combine "4x speed" +
  // "skip noise" if they want maximum velocity.
  const [skipNoise, setSkipNoise] = useState(false);
  const [viewMode, setViewMode] = useState<ReplayMode>('phase');

  // Load replay frames (up to the server cap). Source depends on route.
  useEffect(() => {
    if (!replayId) return;

    let cancelled = false;
    setIsLoading(true);
    setError(null);

    const fetcher = isMatchReplay
      ? matchAPI.getReplay(replayId, { since: 0, limit: 8000 })
      : botGameAPI.getReplay(replayId, { since: 0, limit: 5000 });

    fetcher
      .then((r) => {
        if (cancelled) return;
        setReplay(r);
        setFrameIndex(0);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : 'Failed to load replay');
      })
      .finally(() => {
        if (cancelled) return;
        setIsLoading(false);
      });

    return () => { cancelled = true; };
  }, [replayId, isMatchReplay]);

  const frames = replay?.frames || [];
  const phaseSlices = useMemo(() => buildPhaseSlices(frames), [frames]);

  const phaseIndexByFrame = useMemo(() => {
    const indexMap: number[] = Array(frames.length).fill(0);
    phaseSlices.forEach((slice, phaseIndex) => {
      for (let i = slice.start; i <= slice.end; i += 1) {
        indexMap[i] = phaseIndex;
      }
    });
    return indexMap;
  }, [frames.length, phaseSlices]);

  const clampedIndex = Math.max(0, Math.min(frameIndex, Math.max(0, frames.length - 1)));
  const currentFrame = frames.length ? frames[clampedIndex] : null;
  const currentState = currentFrame?.state ?? null;

  const currentPhaseIndex = frames.length ? phaseIndexByFrame[clampedIndex] || 0 : 0;
  const currentPhaseSlice = phaseSlices[currentPhaseIndex] || null;

  const visibleIndex = viewMode === 'phase' ? currentPhaseIndex : clampedIndex;
  const visibleTotal = viewMode === 'phase' ? phaseSlices.length : frames.length;

  const spectatorPlayerId = useMemo(() => getSpectatorPlayerId(currentState), [currentState]);

  const phaseRepresentativeFrame = useMemo(() => {
    if (!currentPhaseSlice) return currentFrame;

    for (let i = currentPhaseSlice.end; i >= currentPhaseSlice.start; i -= 1) {
      if (isInteresting(frames[i])) return frames[i];
    }

    return frames[currentPhaseSlice.end] || currentFrame;
  }, [currentFrame, currentPhaseSlice, frames]);

  const actionSummary = useMemo(
    () => summarizeFrameAction(viewMode === 'phase' ? phaseRepresentativeFrame : currentFrame),
    [currentFrame, phaseRepresentativeFrame, viewMode],
  );

  const prevJumpDisabled = useMemo(() => {
    if (!frames.length) return true;
    if (viewMode === 'phase') {
      return findPrevTurnSlice(phaseSlices, currentPhaseIndex) === null;
    }
    return findPrevInteresting(frames, clampedIndex) === null;
  }, [clampedIndex, currentPhaseIndex, frames, phaseSlices, viewMode]);

  const nextJumpDisabled = useMemo(() => {
    if (!frames.length) return true;
    if (viewMode === 'phase') {
      return findNextTurnSlice(phaseSlices, currentPhaseIndex) === null;
    }
    return findNextInteresting(frames, clampedIndex) === null;
  }, [clampedIndex, currentPhaseIndex, frames, phaseSlices, viewMode]);

  const canStepBackward = viewMode === 'phase' ? currentPhaseIndex > 0 : clampedIndex > 0;
  const canStepForward = viewMode === 'phase'
    ? currentPhaseIndex < phaseSlices.length - 1
    : clampedIndex < frames.length - 1;

  // Playback loop. In ⏩ FFWD mode (skipNoise=true) we hop directly to
  // the next "interesting" frame (any non-PASS_PRIORITY action) so a
  // 200-frame MTG game with lots of priority noise replays in ~30s.
  useEffect(() => {
    if (!isPlaying) return;
    if (!frames.length) return;

    const t = setInterval(() => {
      setFrameIndex((i) => {
        if (skipNoise) {
          const next = findNextInteresting(frames, i);
          if (next === null) return i;
          return next;
        }
        if (viewMode === 'phase') {
          const phaseIndex = phaseIndexByFrame[i] || 0;
          const nextPhase = phaseIndex + 1;
          if (nextPhase >= phaseSlices.length) return i;
          return phaseSlices[nextPhase].start;
        }

        const nextFrame = i + 1;
        if (nextFrame >= frames.length) return i;
        return nextFrame;
      });
    }, speedMs);

    return () => clearInterval(t);
  }, [frames.length, isPlaying, phaseIndexByFrame, phaseSlices, speedMs, viewMode, skipNoise]);

  // Auto-stop at end
  useEffect(() => {
    if (!isPlaying) return;

    const atEnd = viewMode === 'phase'
      ? phaseSlices.length > 0 && currentPhaseIndex >= phaseSlices.length - 1
      : frames.length > 0 && clampedIndex >= frames.length - 1;

    if (atEnd) {
      setIsPlaying(false);
    }
  }, [clampedIndex, currentPhaseIndex, frames.length, isPlaying, phaseSlices.length, viewMode]);

  if (isLoading) {
    return (
      <div className="min-h-screen bg-brand-ink flex items-center justify-center">
        <div className="text-center">
          <div className="w-16 h-16 border-4 border-brand-foil border-t-transparent rounded-full animate-spin mx-auto mb-4" />
          <p className="brand-eyebrow text-brand-chalk">Loading replay</p>
        </div>
      </div>
    );
  }

  if (error || !replay) {
    return (
      <div className="min-h-screen bg-brand-ink flex items-center justify-center">
        <div className="text-center">
          <p className="text-brand-ember mb-4">{error || 'Replay not found'}</p>
          <button
            onClick={() => navigate('/')}
            className="px-4 py-2 bg-gradient-to-b from-brand-foil-bright via-brand-foil to-brand-foil-deep text-brand-ink shadow-brand-foil"
          >
            Back to lobby
          </button>
        </div>
      </div>
    );
  }

  const currentPhaseLabel = currentPhaseSlice
    ? `Turn ${currentPhaseSlice.turn} • ${currentPhaseSlice.phase}/${currentPhaseSlice.step}`
    : `Turn ${currentFrame?.turn ?? 0} • ${currentFrame?.phase ?? ''}/${currentFrame?.step ?? ''}`;

  return (
    <div className="min-h-screen bg-brand-ink text-brand-cream flex flex-col">
      <div className="bg-brand-obsidian/85 backdrop-blur-xl border-b border-brand-hairline/60 p-4 flex items-center justify-between gap-4 sticky top-0 z-30">
        <div className="flex items-center gap-4 min-w-0">
          <button onClick={() => navigate(-1)} className="text-brand-chalk hover:text-brand-foil transition-colors text-sm tracking-wide">
            ← Back
          </button>
          <div className="min-w-0">
            <p className="brand-eyebrow text-brand-foil">Replay</p>
            <p className="text-xs text-brand-chalk truncate brand-mono">
              {currentPhaseLabel}
              {actionSummary.model ? ` · ${actionSummary.model}` : ''}
            </p>
          </div>
        </div>

        {/* Controls */}
        <div className="flex items-center gap-3">
          <div className="flex items-center bg-gray-800 rounded border border-gray-700 overflow-hidden">
            <button
              onClick={() => setViewMode('phase')}
              className={`px-2 py-1 text-xs ${viewMode === 'phase' ? 'bg-game-accent text-white' : 'text-gray-300 hover:bg-gray-700'}`}
            >
              Phase
            </button>
            <button
              onClick={() => setViewMode('action')}
              className={`px-2 py-1 text-xs ${viewMode === 'action' ? 'bg-game-accent text-white' : 'text-gray-300 hover:bg-gray-700'}`}
            >
              Action
            </button>
          </div>

          <button
            onClick={() => {
              if (viewMode === 'phase') {
                const prevTurnPhase = findPrevTurnSlice(phaseSlices, currentPhaseIndex);
                if (prevTurnPhase !== null) setFrameIndex(phaseSlices[prevTurnPhase].start);
                return;
              }

              const i = findPrevInteresting(frames, clampedIndex);
              if (i !== null) setFrameIndex(i);
            }}
            className="px-2 py-1 bg-gray-800 text-white rounded hover:bg-gray-700 border border-gray-700"
            disabled={prevJumpDisabled}
            title={viewMode === 'phase' ? 'Previous turn' : 'Previous non-PASS action'}
          >
            ⏮
          </button>
          <button
            onClick={() => {
              if (viewMode === 'phase') {
                const prevPhase = Math.max(0, currentPhaseIndex - 1);
                setFrameIndex(phaseSlices[prevPhase]?.start ?? clampedIndex);
                return;
              }

              setFrameIndex((i) => Math.max(0, i - 1));
            }}
            className="px-2 py-1 bg-gray-700 text-white rounded hover:bg-gray-600"
            disabled={!canStepBackward}
          >
            ◀
          </button>
          <button
            onClick={() => setIsPlaying((p) => !p)}
            className={
              'px-3 py-1 border text-sm transition-colors ' +
              (isPlaying
                ? 'border-brand-foil/60 bg-brand-foil/10 text-brand-foil hover:bg-brand-foil/20'
                : 'border-brand-sheen/60 bg-brand-sheen/10 text-brand-sheen hover:bg-brand-sheen/20')
            }
            disabled={!frames.length}
          >
            {isPlaying ? '⏸ Pause' : '▶ Play'}
          </button>
          <button
            onClick={() => {
              setSkipNoise((v) => !v);
              if (!isPlaying) setIsPlaying(true);
            }}
            className={
              'px-3 py-1 border text-sm transition-colors ' +
              (skipNoise
                ? 'border-brand-foil/60 bg-brand-foil/15 text-brand-foil-bright hover:bg-brand-foil/25'
                : 'border-brand-hairline bg-brand-obsidian text-brand-chalk hover:border-brand-foil/40 hover:text-brand-foil')
            }
            title={skipNoise ? 'FFWD on — jumping to next non-pass action' : 'FFWD — skip pass-priority noise'}
            disabled={!frames.length}
          >
            ⏩ FFWD
          </button>
          <button
            onClick={() => {
              if (viewMode === 'phase') {
                const nextPhase = Math.min(phaseSlices.length - 1, currentPhaseIndex + 1);
                setFrameIndex(phaseSlices[nextPhase]?.start ?? clampedIndex);
                return;
              }

              setFrameIndex((i) => Math.min(frames.length - 1, i + 1));
            }}
            className="px-2 py-1 bg-gray-700 text-white rounded hover:bg-gray-600"
            disabled={!canStepForward}
          >
            ▶
          </button>
          <button
            onClick={() => {
              if (viewMode === 'phase') {
                const nextTurnPhase = findNextTurnSlice(phaseSlices, currentPhaseIndex);
                if (nextTurnPhase !== null) setFrameIndex(phaseSlices[nextTurnPhase].start);
                return;
              }

              const i = findNextInteresting(frames, clampedIndex);
              if (i !== null) setFrameIndex(i);
            }}
            className="px-2 py-1 bg-gray-800 text-white rounded hover:bg-gray-700 border border-gray-700"
            disabled={nextJumpDisabled}
            title={viewMode === 'phase' ? 'Next turn' : 'Next non-PASS action'}
          >
            ⏭
          </button>

          <div className="text-gray-400 text-sm tabular-nums">
            {visibleTotal ? `${visibleIndex + 1}/${visibleTotal}` : '0/0'}
          </div>

          <select
            value={speedMs}
            onChange={(e) => setSpeedMs(parseInt(e.target.value, 10))}
            className="px-2 py-1 bg-gray-800 border border-gray-600 rounded text-white text-sm"
          >
            <option value={800}>0.5x</option>
            <option value={300}>1x</option>
            <option value={150}>2x</option>
            <option value={80}>4x</option>
          </select>
        </div>
      </div>

      {/* Lab Timeline — HD-CRIT 17. Same widget as the lobby ticker and
          the live-game rail, here in scrubber-mode against the active
          phase/action axis (whichever viewMode is selected). The legacy
          <input type=range> + bottom caption row was replaced by this. */}
      <div
        className="px-4 py-4 border-b"
        style={{
          background: 'var(--paper)',
          color: 'var(--ink)',
          borderColor: 'var(--rule-2)',
        }}
      >
        <Timeline
          currentTurn={visibleIndex}
          totalTurns={Math.max(0, visibleTotal - 1)}
          matchId={replayId}
          endLabel={`T${Math.max(0, visibleTotal)}`}
          mode="full"
          onScrub={(idx) => {
            const target = Math.max(0, Math.min(idx, Math.max(0, visibleTotal - 1)));
            if (viewMode === 'phase') {
              setFrameIndex(phaseSlices[target]?.start ?? 0);
            } else {
              setFrameIndex(target);
            }
          }}
          ariaLabel={`Replay scrubber — ${viewMode} view, position ${visibleIndex + 1} of ${visibleTotal}`}
        />
        <div
          className="mt-2"
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: '11px',
            color: 'var(--ink-3)',
            letterSpacing: '0.04em',
          }}
        >
          {viewMode === 'phase' ? (
            <>{currentPhaseLabel} · {currentPhaseSlice ? `${currentPhaseSlice.end - currentPhaseSlice.start + 1} frames` : '0 frames'}</>
          ) : (
            <>Turn {currentFrame?.turn ?? 0} · {currentFrame?.phase ?? ''}/{currentFrame?.step ?? ''}</>
          )}
        </div>
      </div>

      {/* Body */}
      <div className="flex-1 grid grid-cols-1 lg:grid-cols-[1fr_420px]">
        <div className="relative">
          {currentState && spectatorPlayerId ? (
            <ReplayBoardSwitch gameState={currentState} playerId={spectatorPlayerId} />
          ) : (
            <div className="flex items-center justify-center h-full">
              <p className="text-gray-500">No game state available</p>
            </div>
          )}
        </div>

        <div className="border-l border-gray-700 bg-game-surface p-4 overflow-auto">
          <h2 className="text-white font-bold mb-2">
            {viewMode === 'phase' ? 'Phase Summary' : 'Decision'}
          </h2>
          <div className="text-gray-300 text-sm mb-1">{currentPhaseLabel}</div>
          <div className="text-gray-400 text-xs mb-3">{actionSummary.title}</div>

          {viewMode === 'phase' && currentPhaseSlice && (
            <div className="mb-4 text-xs text-gray-400">
              {countInterestingInSlice(frames, currentPhaseSlice)} non-pass action(s) in this phase window
            </div>
          )}

          {actionSummary.reasoning && (
            <div className="mb-4">
              <div className="text-xs text-gray-400 mb-1">Reasoning</div>
              <div className="text-sm text-gray-200 whitespace-pre-wrap">{actionSummary.reasoning}</div>
            </div>
          )}
          {actionSummary.prompt && (
            <div>
              <div className="text-xs text-gray-400 mb-1">Prompt (record_prompts=true)</div>
              <pre className="text-xs text-gray-300 whitespace-pre-wrap bg-gray-900/60 border border-gray-700 rounded p-2 max-h-[40vh] overflow-auto">
                {actionSummary.prompt}
              </pre>
            </div>
          )}

          <div className="mt-6">
            <h3 className="text-white font-bold mb-2">{viewMode === 'phase' ? 'Phases' : 'Frames'}</h3>
            <div className="text-xs text-gray-400 mb-2">Click to jump</div>

            {viewMode === 'phase' ? (
              <div className="space-y-1">
                {phaseSlices
                  .slice(Math.max(0, currentPhaseIndex - 20), Math.min(phaseSlices.length, currentPhaseIndex + 21))
                  .map((slice, offset) => {
                    const phaseListStart = Math.max(0, currentPhaseIndex - 20);
                    const phaseIdx = phaseListStart + offset;
                    const isActive = phaseIdx === currentPhaseIndex;
                    const interestingCount = countInterestingInSlice(frames, slice);

                    return (
                      <button
                        key={`${slice.start}-${slice.end}`}
                        onClick={() => setFrameIndex(slice.start)}
                        className={`w-full text-left px-2 py-1 rounded border ${
                          isActive
                            ? 'bg-gray-800 border-game-accent text-white'
                            : 'bg-gray-900/30 border-gray-700 text-gray-300 hover:bg-gray-800/60'
                        }`}
                      >
                        <div className="text-xs truncate">
                          <span className="text-gray-500 mr-2">#{phaseIdx + 1}</span>
                          Turn {slice.turn} {slice.phase}/{slice.step}
                        </div>
                        <div className="text-[11px] text-gray-500">
                          {slice.end - slice.start + 1} frame(s) • {interestingCount} non-pass
                        </div>
                      </button>
                    );
                  })}
              </div>
            ) : (
              <div className="space-y-1">
                {frames.slice(Math.max(0, clampedIndex - 30), Math.min(frames.length, clampedIndex + 31)).map((f, offset) => {
                  const i = Math.max(0, clampedIndex - 30) + offset;
                  const s = summarizeFrameAction(f);
                  const isActive = i === clampedIndex;
                  return (
                    <button
                      key={i}
                      onClick={() => setFrameIndex(i)}
                      className={`w-full text-left px-2 py-1 rounded border ${
                        isActive
                          ? 'bg-gray-800 border-game-accent text-white'
                          : 'bg-gray-900/30 border-gray-700 text-gray-300 hover:bg-gray-800/60'
                      }`}
                    >
                      <div className="text-xs truncate">
                        <span className="text-gray-500 mr-2">#{i + 1}</span>
                        {s.title}
                      </div>
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export default ReplayView;
