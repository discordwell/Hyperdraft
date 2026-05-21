/**
 * SpectatorGameBody — dispatches the inner game render in SpectatorView
 * to the engine-specific board based on `gameState.game_mode`.
 *
 * Why this exists: `/spectate/:gameId` previously rendered `<GameBoard>`
 * unconditionally regardless of engine, so bot games for HS/PKM/YGO/MC/
 * FIN/DPT/SCP all rendered the MTG layout — wrong art frames, wrong
 * zones, mostly empty. This module supplies a tiny per-engine wrapper
 * for each board that derives state inline from `gameState` (mirroring
 * the production hooks' useMemo shapes) and passes noop handlers so the
 * board renders fully read-only.
 *
 * SCP and Cats currently fall back to the generic `<GameBoard>` plus a
 * console warning — SCPGameView is too tightly coupled to its socket-
 * driven hook to reuse here, and Cats is mock-data-only with no bot
 * games today. Wiring those properly is a follow-up.
 */

import { lazy, Suspense, useMemo } from 'react';
import type { CardData, GameState, PlayerData } from '../../types';

// Lazy-load each engine board so spectating an MTG match does NOT pull
// in PKM/YGO/MC/FIN/DPT JS — same code-splitting pattern App.tsx uses
// for the per-engine GameView pages.
const GameBoard = lazy(() =>
  import('../game').then((m) => ({ default: m.GameBoard })),
);
const HSGameBoard = lazy(() =>
  import('../game/HSGameBoard').then((m) => ({ default: m.HSGameBoard })),
);
const PKMGameBoard = lazy(() =>
  import('../game/PKMGameBoard').then((m) => ({ default: m.PKMGameBoard })),
);
const YGOGameBoard = lazy(() =>
  import('../game/YGOGameBoard').then((m) => ({ default: m.YGOGameBoard })),
);
const MCGameBoard = lazy(() =>
  import('../game/MCGameBoard').then((m) => ({ default: m.MCGameBoard })),
);
const FinanceGameBoard = lazy(() =>
  import('../../games/finance').then((m) => ({ default: m.FinanceGameBoard })),
);
const DepthsGameBoard = lazy(() =>
  import('../../games/depths').then((m) => ({ default: m.DepthsGameBoard })),
);

interface SpectatorGameBodyProps {
  gameState: GameState;
  playerId: string;
}

// Vessel/Mine type constants — keep in sync with useDepthsGame.ts.
const DEPTHS_VESSEL_TYPES = new Set(['DEPTHS_VESSEL']);
const DEPTHS_MINE_TYPES = new Set(['DEPTHS_MINE']);

// Noop handlers shared by every spectator wrapper — boards never see
// real interaction in spectator mode.
const noop = () => undefined;
const noopFalse = () => false;
const noopEmpty = () => [];

// ─── HS ────────────────────────────────────────────────────────────────
function SpectatorHSBoard({ gameState, playerId }: SpectatorGameBodyProps) {
  return (
    <HSGameBoard
      gameState={gameState}
      playerId={playerId}
      isMyTurn={false}
      canPlayCard={noopFalse}
      canAttuneCard={noopFalse}
      canAttack={noopFalse}
      canUseHeroPower={false}
      getAttackableTargets={noopEmpty as (id: string) => string[]}
      onPlayCard={noop}
      onAttuneCard={noop}
      onAttack={noop}
      onHeroPower={noop}
      onEndTurn={noop}
    />
  );
}

// ─── PKM ───────────────────────────────────────────────────────────────
function SpectatorPKMBoard({ gameState, playerId }: SpectatorGameBodyProps) {
  // Mirror usePokemonGame derivations — but from the spectated player's
  // POV (whichever id we picked first).
  const opponentId = useMemo(() => (
    Object.keys(gameState.players).find((id) => id !== playerId) || null
  ), [gameState.players, playerId]);

  const myPlayer = useMemo<PlayerData | null>(
    () => gameState.players[playerId] || null,
    [gameState.players, playerId],
  );
  const opponentPlayer = useMemo<PlayerData | null>(
    () => (opponentId ? gameState.players[opponentId] || null : null),
    [gameState.players, opponentId],
  );

  const myActivePokemon = gameState.active_pokemon?.[playerId] || null;
  const opponentActivePokemon = opponentId
    ? gameState.active_pokemon?.[opponentId] || null
    : null;

  const myBench = gameState.bench?.[playerId] || [];
  const opponentBench = opponentId ? gameState.bench?.[opponentId] || [] : [];

  const stadiumCard = gameState.stadium_card || null;
  const myGraveyard = gameState.graveyard?.[playerId] || [];
  const opponentGraveyard = opponentId
    ? gameState.graveyard?.[opponentId] || []
    : [];

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
      hand={gameState.hand || []}
      myGraveyard={myGraveyard}
      opponentGraveyard={opponentGraveyard}
      canPlayCard={noopFalse}
      canAttachEnergy={noopFalse}
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

// ─── YGO ───────────────────────────────────────────────────────────────
function SpectatorYGOBoard({ gameState, playerId }: SpectatorGameBodyProps) {
  const opponentId = useMemo(() => (
    Object.keys(gameState.players).find((id) => id !== playerId) || null
  ), [gameState.players, playerId]);

  const myPlayer = gameState.players[playerId] || null;
  const opponentPlayer = opponentId ? gameState.players[opponentId] || null : null;

  const emptyRow: (CardData | null)[] = [null, null, null, null, null];
  const myMonsterZones = gameState.monster_zones?.[playerId] || emptyRow;
  const oppMonsterZones = opponentId
    ? gameState.monster_zones?.[opponentId] || emptyRow
    : emptyRow;
  const mySpellTrapZones = gameState.spell_trap_zones?.[playerId] || emptyRow;
  const oppSpellTrapZones = opponentId
    ? gameState.spell_trap_zones?.[opponentId] || emptyRow
    : emptyRow;
  const myFieldSpell = gameState.field_spells?.[playerId] || null;
  const oppFieldSpell = opponentId
    ? gameState.field_spells?.[opponentId] || null
    : null;
  const myGraveyard = gameState.graveyard?.[playerId] || [];
  const oppGraveyard = opponentId ? gameState.graveyard?.[opponentId] || [] : [];
  const myBanished = gameState.banished?.[playerId] || [];
  const oppBanished = opponentId ? gameState.banished?.[opponentId] || [] : [];
  const myExtraDeckSize = gameState.extra_deck_sizes?.[playerId] || 0;
  const oppExtraDeckSize = opponentId
    ? gameState.extra_deck_sizes?.[opponentId] || 0
    : 0;
  const ygoPhase = gameState.ygo_phase || '';

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
      hand={gameState.hand || []}
      myGraveyard={myGraveyard}
      oppGraveyard={oppGraveyard}
      myBanished={myBanished}
      oppBanished={oppBanished}
      myExtraDeckSize={myExtraDeckSize}
      oppExtraDeckSize={oppExtraDeckSize}
      ygoPhase={ygoPhase}
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

// ─── MC ────────────────────────────────────────────────────────────────
function SpectatorMCBoard({ gameState, playerId }: SpectatorGameBodyProps) {
  const opponentId = useMemo(() => (
    Object.keys(gameState.players).find((id) => id !== playerId) || null
  ), [gameState.players, playerId]);

  const myPlayer = gameState.players[playerId] || null;
  const opponentPlayer = opponentId ? gameState.players[opponentId] || null : null;

  const myMobs = (gameState.battlefield || []).filter(
    (c) => c.controller === playerId && c.types.includes('MC_MOB'),
  );
  const opponentMobs = (gameState.battlefield || []).filter(
    (c) => c.controller !== playerId && c.types.includes('MC_MOB'),
  );

  return (
    <MCGameBoard
      gameState={gameState}
      playerId={playerId}
      opponentId={opponentId}
      myPlayer={myPlayer}
      opponentPlayer={opponentPlayer}
      myMobs={myMobs}
      opponentMobs={opponentMobs}
      isMyTurn={false}
      canPlayCard={noopFalse}
      canUseMob={noopFalse}
      canBlockMob={noopFalse}
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

// ─── Finance ───────────────────────────────────────────────────────────
function SpectatorFinanceBoard({ gameState, playerId }: SpectatorGameBodyProps) {
  const opponentId = useMemo(() => (
    Object.keys(gameState.players).find((id) => id !== playerId) || null
  ), [gameState.players, playerId]);

  const myPlayer = gameState.players[playerId] || null;
  const opponentPlayer = opponentId ? gameState.players[opponentId] || null : null;

  const has = (c: CardData, t: string) => c.types.some((tt) => tt === t);
  const myTraders = (gameState.battlefield || []).filter(
    (c) => c.controller === playerId && has(c, 'FIN_TRADER'),
  );
  const myAssets = (gameState.battlefield || []).filter(
    (c) => c.controller === playerId && has(c, 'FIN_ASSET'),
  );
  const myStructures = (gameState.battlefield || []).filter(
    (c) => c.controller === playerId && has(c, 'FIN_STRUCTURE'),
  );
  const oppTraders = (gameState.battlefield || []).filter(
    (c) => c.controller !== playerId && has(c, 'FIN_TRADER'),
  );
  const oppAssets = (gameState.battlefield || []).filter(
    (c) => c.controller !== playerId && has(c, 'FIN_ASSET'),
  );

  const myHand = gameState.hand || [];

  const gs = gameState as unknown as Record<string, unknown>;
  const currentPhase = ((gs.finance_phase as string) ?? gameState.phase ?? 'PRE_MARKET') as string;
  const turnData = gs.finance_turn_data as Record<string, unknown> | undefined;
  const rawDesk = turnData?.[`finance_deriv_desk_${playerId}`];
  const myDerivDesk: string[] = Array.isArray(rawDesk) ? (rawDesk as string[]) : [];
  const darkPoolActive = Boolean(gs.finance_dark_pool);

  const myLiquidity = myPlayer?.mana_crystals_available ?? 0;
  const myLiquidityMax = myPlayer?.mana_crystals ?? 0;

  return (
    <FinanceGameBoard
      gameState={gameState}
      playerId={playerId}
      opponentId={opponentId}
      myPlayer={myPlayer}
      opponentPlayer={opponentPlayer}
      myTraders={myTraders}
      myAssets={myAssets}
      myStructures={myStructures}
      myHand={myHand}
      myDerivDesk={myDerivDesk}
      oppTraders={oppTraders}
      oppAssets={oppAssets}
      currentPhase={currentPhase}
      myLiquidity={myLiquidity}
      myLiquidityMax={myLiquidityMax}
      darkPoolActive={darkPoolActive}
      isMyTurn={false}
      canPlayCard={noopFalse}
      canAttack={noopFalse}
      canBlock={noopFalse}
      onPlayCard={noop}
      onDeclareAttackers={noop}
      onDeclareBlockers={noop}
      onActivateAbility={noop}
      onEndTurn={noop}
    />
  );
}

// ─── Depths ────────────────────────────────────────────────────────────
function SpectatorDepthsBoard({ gameState, playerId }: SpectatorGameBodyProps) {
  const opponentId = useMemo(() => (
    Object.keys(gameState.players).find((id) => id !== playerId) || null
  ), [gameState.players, playerId]);

  const myPlayer = gameState.players[playerId] || null;
  const opponentPlayer = opponentId ? gameState.players[opponentId] || null : null;

  const isVessel = (c: CardData) =>
    c.types.some((t) => DEPTHS_VESSEL_TYPES.has(t));
  const isMine = (c: CardData) => c.types.some((t) => DEPTHS_MINE_TYPES.has(t));

  const myVessels = (gameState.battlefield || []).filter(
    (c) => c.controller === playerId && isVessel(c),
  );
  const opponentVessels = (gameState.battlefield || []).filter(
    (c) => c.controller !== playerId && isVessel(c),
  );
  const myMines = (gameState.battlefield || []).filter(
    (c) => c.controller === playerId && isMine(c),
  );
  const opponentMines = (gameState.battlefield || []).filter(
    (c) => c.controller !== playerId && isMine(c),
  );

  const myFlagship = (() => {
    const fid = myPlayer?.flagship_id;
    if (fid) {
      return (gameState.battlefield || []).find((c) => c.id === fid) || null;
    }
    return (
      myVessels.find((c) => c.is_flagship || c.subtypes.includes('Flagship')) ||
      null
    );
  })();
  const opponentFlagship = (() => {
    const fid = opponentPlayer?.flagship_id;
    if (fid) {
      return (gameState.battlefield || []).find((c) => c.id === fid) || null;
    }
    return (
      opponentVessels.find(
        (c) => c.is_flagship || c.subtypes.includes('Flagship'),
      ) || null
    );
  })();

  return (
    <DepthsGameBoard
      gameState={gameState}
      playerId={playerId}
      opponentId={opponentId}
      myPlayer={myPlayer}
      opponentPlayer={opponentPlayer}
      myFlagship={myFlagship}
      opponentFlagship={opponentFlagship}
      myVessels={myVessels}
      opponentVessels={opponentVessels}
      myMines={myMines}
      opponentMines={opponentMines}
      isMyTurn={false}
      canPlayCard={noopFalse}
      canUseVessel={noopFalse}
      canIntercept={noopFalse}
      onPlayCard={noop}
      onDive={noop}
      onSurface={noop}
      onLayMine={noop}
      onDeclareAttackers={noop}
      onDetect={noop}
      onDeclareInterceptors={noop}
      onActivateAbility={noop}
      onEndTurn={noop}
    />
  );
}

// ─── Dispatcher ────────────────────────────────────────────────────────
function SpectatorBodyFallback() {
  return (
    <div className="flex items-center justify-center h-full">
      <div className="text-center">
        <div className="w-10 h-10 border-2 border-brand-hairline border-t-brand-foil rounded-full animate-spin mx-auto mb-3" />
        <p className="brand-eyebrow text-brand-chalk">Loading board…</p>
      </div>
    </div>
  );
}

export function SpectatorGameBody({ gameState, playerId }: SpectatorGameBodyProps) {
  const mode = gameState.game_mode;

  // The Suspense boundary covers all lazy-loaded engine boards.
  return (
    <Suspense fallback={<SpectatorBodyFallback />}>
      {(() => {
        switch (mode) {
          case 'mtg':
            return <GameBoard gameState={gameState} playerId={playerId} />;
          case 'hearthstone':
            return <SpectatorHSBoard gameState={gameState} playerId={playerId} />;
          case 'pokemon':
            return <SpectatorPKMBoard gameState={gameState} playerId={playerId} />;
          case 'yugioh':
            return <SpectatorYGOBoard gameState={gameState} playerId={playerId} />;
          case 'minecraft':
            return <SpectatorMCBoard gameState={gameState} playerId={playerId} />;
          case 'finance':
            return <SpectatorFinanceBoard gameState={gameState} playerId={playerId} />;
          case 'depths':
            return <SpectatorDepthsBoard gameState={gameState} playerId={playerId} />;
          case 'scp':
          case 'cats':
            // SCPGameView / CatsGame are too tightly coupled to their
            // socket-driven hooks to reuse in spectator mode; fall back
            // to the generic GameBoard with a console warning so we
            // surface this gap rather than silently rendering an MTG
            // layout on top of the wrong shape.
            console.warn(
              `[SpectatorView] No dedicated spectator board for game_mode='${mode}'. ` +
              'Falling back to MTG GameBoard — the layout will not match.',
            );
            return <GameBoard gameState={gameState} playerId={playerId} />;
          default:
            // Unknown / undefined mode — likely the data hasn't fully
            // populated yet. Render GameBoard as a neutral fallback so
            // we don't blank the page on first paint.
            if (mode !== undefined) {
              console.warn(
                `[SpectatorView] Unknown game_mode='${mode}'. ` +
                'Falling back to MTG GameBoard.',
              );
            }
            return <GameBoard gameState={gameState} playerId={playerId} />;
        }
      })()}
    </Suspense>
  );
}

export default SpectatorGameBody;
