/**
 * FinanceGameView Page
 *
 * Dedicated view for Finance TCG games. Uses useFinanceGame for
 * Finance-specific action types and state derivations.
 */

import { useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useFinanceGame } from '../hooks/useFinanceGame';
import { useGameStore } from '../stores/gameStore';
import { FinanceGameBoard } from '../games/finance';
import { SettingsPopover } from '../games/finance/SettingsPopover';
import { matchAPI } from '../services/api';

export function FinanceGameView() {
  const { matchId } = useParams<{ matchId: string }>();
  const navigate = useNavigate();

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

  return (
    <div className="min-h-screen flex flex-col" style={{ background: '#03080f' }}>
      {/* Header bar */}
      <div className="flex items-center justify-between px-4 py-2 border-b" style={{ borderColor: '#1a2a1a' }}>
        <span className="font-mono uppercase text-xs" style={{ color: '#00FF88' }}>
          HYPERDRAFT // FINANCE TCG
        </span>
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-1">
            <div className={`w-2 h-2 rounded-full ${isConnected ? 'bg-green-500' : 'bg-red-500'}`} />
            <span className="font-mono text-xs text-gray-500">{isConnected ? 'LIVE' : 'OFFLINE'}</span>
          </div>
          <SettingsPopover />
          <button
            onClick={handleConcede}
            className="font-mono uppercase text-xs px-3 py-1 border border-red-800 text-red-600 hover:bg-red-900/20 transition-colors"
          >
            CONCEDE
          </button>
          <button
            onClick={() => navigate('/')}
            className="font-mono uppercase text-xs px-3 py-1 border border-gray-700 text-gray-500 hover:bg-gray-800 transition-colors"
          >
            LOBBY
          </button>
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
    </div>
  );
}
