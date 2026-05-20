/**
 * DepthsGameView Page
 *
 * Dedicated view for Depths: Submarine Fleet games.
 * Uses useDepthsGame for depths-specific action types and state derivations.
 * Mirrors FinanceGameView in structure.
 */

import { useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useDepthsGame } from '../hooks/useDepthsGame';
import { useGameStore } from '../stores/gameStore';
import { DepthsGameBoard } from '../games/depths';
import { matchAPI } from '../services/api';
import { GameViewLayout } from '../components/brand';

export function DepthsGameView() {
  const { matchId } = useParams<{ matchId: string }>();
  const navigate = useNavigate();

  const {
    gameState,
    playerId,
    isConnected,
    myPlayer,
    opponentId,
    opponentPlayer,
    myFlagship,
    opponentFlagship,
    myVessels,
    opponentVessels,
    myMines,
    opponentMines,
    isMyTurn,
    canPlayCard,
    canUseVessel,
    canIntercept,
    playCard,
    dive,
    surface,
    layMine,
    declareAttackers,
    detect,
    declareInterceptors,
    activateAbility,
    endTurn,
    setError,
    error,
  } = useDepthsGame();

  const storeMatchId = useGameStore((state) => state.matchId);
  const storePlayerId = useGameStore((state) => state.playerId);
  const setGameState = useGameStore((state) => state.setGameState);

  useEffect(() => {
    if (!matchId) return;
    if (!storeMatchId || storeMatchId !== matchId) {
      navigate('/');
      return;
    }
    if (!gameState && storePlayerId) {
      matchAPI.getState(matchId, storePlayerId)
        .then(setGameState)
        .catch((err) => setError(err instanceof Error ? err.message : 'Failed to fetch state'));
    }
  }, [matchId, storeMatchId, storePlayerId, gameState, navigate, setGameState, setError]);

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
      <div className="min-h-screen flex items-center justify-center bg-slate-950">
        <div className="text-center">
          <div
            className="w-16 h-16 border-4 border-t-transparent rounded-full animate-spin mx-auto mb-4"
            style={{ borderColor: '#22d3ee', borderTopColor: 'transparent' }}
          />
          <p className="font-mono uppercase text-sm text-cyan-400">
            Diving to depth...
          </p>
        </div>
      </div>
    );
  }

  if (gameState.is_game_over) {
    const winnerId = gameState.winner;
    const didWin = winnerId === playerId;
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-950">
        <div
          className="text-center p-8 border"
          style={{ borderColor: '#22d3ee' }}
        >
          <p className="font-mono uppercase text-2xl mb-4 text-amber-300">
            {didWin ? 'ENEMY FLAGSHIP SUNK' : 'FLAGSHIP LOST'}
          </p>
          <button
            onClick={() => navigate('/')}
            className="font-mono uppercase px-6 py-2 border border-cyan-400 text-cyan-400 hover:bg-cyan-900/20 transition-colors"
          >
            SURFACE
          </button>
        </div>
      </div>
    );
  }

  const opponentEntryDpt =
    gameState?.players && Object.entries(gameState.players).find(([id]) => id !== playerId);
  const opponentNameDpt = opponentEntryDpt
    ? (opponentEntryDpt[1] as { name?: string }).name
    : undefined;
  const meDpt = gameState?.players?.[playerId] as { name?: string } | undefined;

  return (
    <GameViewLayout
      mode="depths"
      matchId={matchId}
      turn={(gameState as unknown as { turn_number?: number }).turn_number}
      phase={isConnected ? 'sonar lock' : 'offline'}
      opponentName={opponentNameDpt}
      playerName={meDpt?.name}
      onExit={handleConcede}
    >
    <div className="min-h-[calc(100vh-3.5rem)] flex flex-col bg-slate-950">
      {error && (
        <div className="px-4 py-2 text-xs font-mono text-red-400 bg-red-900/20 border-b border-red-800">
          {error}
        </div>
      )}

      {/* Game board */}
      <div className="flex-1">
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
          isMyTurn={isMyTurn()}
          canPlayCard={canPlayCard}
          canUseVessel={canUseVessel}
          canIntercept={canIntercept}
          onPlayCard={playCard}
          onDive={dive}
          onSurface={surface}
          onLayMine={layMine}
          onDeclareAttackers={declareAttackers}
          onDetect={detect}
          onDeclareInterceptors={declareInterceptors}
          onActivateAbility={activateAbility}
          onEndTurn={endTurn}
        />
      </div>
    </div>
    </GameViewLayout>
  );
}

export default DepthsGameView;
