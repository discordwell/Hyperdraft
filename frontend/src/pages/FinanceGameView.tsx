/**
 * FinanceGameView Page
 *
 * Dedicated view for Finance TCG games. Uses useFinanceGame for
 * Finance-specific action types and state derivations.
 */

import { useEffect, useCallback } from 'react';
import { useParams, useNavigate, useLocation } from 'react-router-dom';
import { useFinanceGame } from '../hooks/useFinanceGame';
import { useGameStore } from '../stores/gameStore';
import { FinanceGameBoard } from '../games/finance';
import { SettingsPopover } from '../games/finance/SettingsPopover';
import { matchAPI } from '../services/api';
import { ChoiceModal } from '../components/actions/ChoiceModal';
import { usePendingChoice } from '../hooks/usePendingChoice';
import { GameViewLayout } from '../components/brand';

export function FinanceGameView() {
  const { matchId } = useParams<{ matchId: string }>();
  const navigate = useNavigate();
  const location = useLocation();

  const {
    gameState,
    playerId,
    isConnected,
    myPlayer,
    opponentId,
    opponentPlayer,
    myHand,
    myTraders,
    myAssets,
    myStructures,
    myDerivDesk,
    oppTraders,
    oppAssets,
    currentPhase,
    myLiquidity,
    myLiquidityMax,
    darkPoolActive,
    isMyTurn,
    canPlayCard,
    canAttack,
    canBlock,
    playCard,
    declareAttackers,
    declareBlockers,
    activateAbility,
    endTurn,
    playResponse,
    passResponse,
    setError,
    error,
  } = useFinanceGame();

  const storeMatchId = useGameStore((state) => state.matchId);
  const storePlayerId = useGameStore((state) => state.playerId);
  const setGameState = useGameStore((state) => state.setGameState);
  const setConnection = useGameStore((state) => state.setConnection);

  const {
    pendingChoice,
    handleChoiceSubmit,
    isLoading: isSubmittingChoice,
  } = usePendingChoice();

  useEffect(() => {
    if (!matchId) return;
    if (!storeMatchId || storeMatchId !== matchId) {
      // Allow joining a finance match by URL alone — useful for sharing
      // links and for headless rendering. Falls back to home if the URL
      // has no player_id and the store is empty.
      const queryPlayerId = new URLSearchParams(location.search).get('player_id');
      if (!queryPlayerId) {
        navigate('/');
        return;
      }
      setConnection(matchId, queryPlayerId, false);
      return;
    }
    if (!gameState && storePlayerId) {
      matchAPI.getState(matchId, storePlayerId)
        .then(setGameState)
        .catch((err) => setError(err instanceof Error ? err.message : 'Failed to fetch state'));
    }
  }, [matchId, storeMatchId, storePlayerId, gameState, location.search, navigate, setConnection, setGameState, setError]);

  const handleConcede = useCallback(async () => {
    if (!matchId || !playerId) return;
    if (!confirm('Concede?')) return;
    try {
      await matchAPI.concede(matchId, playerId);
      navigate('/');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to concede');
    }
  }, [matchId, playerId, navigate, setError]);

  if (!gameState || !playerId) {
    return (
      <div className="min-h-screen flex items-center justify-center" style={{ background: '#03080f' }}>
        <div className="text-center">
          <div className="w-16 h-16 border-4 border-t-transparent rounded-full animate-spin mx-auto mb-4" style={{ borderColor: '#00FF88', borderTopColor: 'transparent' }} />
          <p className="font-mono uppercase text-sm" style={{ color: '#00FF88' }}>Loading Trading Floor…</p>
        </div>
      </div>
    );
  }

  if (gameState.is_game_over) {
    const winnerId = gameState.winner;
    const didWin = winnerId === playerId;
    return (
      <div className="min-h-screen flex items-center justify-center" style={{ background: '#03080f' }}>
        <div className="text-center p-8 border" style={{ borderColor: '#00FF88' }}>
          <p className="font-mono uppercase text-2xl mb-4" style={{ color: '#FFD700' }}>
            {didWin ? 'MARKET DOMINANCE' : 'BANKRUPTCY'}
          </p>
          <button
            onClick={() => navigate('/')}
            className="font-mono uppercase px-6 py-2 border"
            style={{ borderColor: '#00FF88', color: '#00FF88' }}
          >
            NEW TRADE
          </button>
        </div>
      </div>
    );
  }

  const opponentEntryFin =
    gameState?.players && Object.entries(gameState.players).find(([id]) => id !== playerId);
  const opponentNameFin = opponentEntryFin
    ? (opponentEntryFin[1] as { name?: string }).name
    : undefined;
  const meFin = gameState?.players?.[playerId] as { name?: string } | undefined;

  return (
    <GameViewLayout
      mode="finance"
      matchId={matchId}
      turn={(gameState as unknown as { turn_number?: number }).turn_number}
      phase={String(currentPhase ?? '').toLowerCase()}
      opponentName={opponentNameFin}
      playerName={meFin?.name}
      onExit={handleConcede}
    >
    <div className="min-h-[calc(100vh-3.5rem)] flex flex-col" style={{ background: '#03080f' }}>
      {/* Finance-specific local header retained for the SettingsPopover */}
      <div className="flex items-center justify-between px-4 py-2 border-b" style={{ borderColor: '#1a2a1a' }}>
        <span className="font-mono uppercase text-xs" style={{ color: '#00FF88' }}>
          Finance TCG · trading floor
        </span>
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-1">
            <div className={`w-2 h-2 rounded-full ${isConnected ? 'bg-emerald-400' : 'bg-red-500'}`} />
            <span className="font-mono text-xs text-gray-500">{isConnected ? 'LIVE' : 'OFFLINE'}</span>
          </div>
          <SettingsPopover />
        </div>
      </div>

      {error && (
        <div className="px-4 py-2 text-xs font-mono text-red-400 bg-red-900/20 border-b border-red-800">
          {error}
        </div>
      )}

      {/* Game board */}
      <div className="flex-1">
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
          isMyTurn={isMyTurn()}
          canPlayCard={canPlayCard}
          canAttack={canAttack}
          canBlock={canBlock}
          onPlayCard={playCard}
          onDeclareAttackers={declareAttackers}
          onDeclareBlockers={declareBlockers}
          onActivateAbility={activateAbility}
          onEndTurn={endTurn}
          onPlayResponse={playResponse}
          onPassResponse={passResponse}
        />
      </div>
      {pendingChoice && gameState && (
        <ChoiceModal
          pendingChoice={pendingChoice}
          battlefield={[]}
          hand={[]}
          graveyard={{}}
          players={gameState.players}
          onSubmit={handleChoiceSubmit}
          isLoading={isSubmittingChoice}
        />
      )}
    </div>
    </GameViewLayout>
  );
}
