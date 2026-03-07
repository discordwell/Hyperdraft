/**
 * YGOGameView Page
 *
 * Dedicated game view for Yu-Gi-Oh! engine games.
 * Uses the useYGOGame hook for YGO-specific action types.
 */

import { useEffect, useCallback, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useYGOGame } from '../hooks/useYGOGame';
import { useGameStore } from '../stores/gameStore';
import { YGOGameBoard } from '../components/game/YGOGameBoard';
import { matchAPI } from '../services/api';
import { AnimatePresence, motion } from 'framer-motion';

export function YGOGameView() {
  const { matchId } = useParams<{ matchId: string }>();
  const navigate = useNavigate();
  const [errorVisible, setErrorVisible] = useState(false);

  const {
    gameState,
    playerId,
    isConnected,
    myPlayer,
    opponentPlayer,
    isMyTurn,
    myMonsterZones,
    oppMonsterZones,
    mySpellTrapZones,
    oppSpellTrapZones,
    myFieldSpell,
    oppFieldSpell,
    myGraveyard,
    oppGraveyard,
    ygoPhase,
    gameLog,
    normalSummon,
    setMonster,
    flipSummon,
    changePosition,
    activateCard,
    setSpellTrap,
    declareAttack,
    directAttack,
    endPhase,
    endTurn,
    setError,
    error,
  } = useYGOGame();

  const storeMatchId = useGameStore((state) => state.matchId);
  const storePlayerId = useGameStore((state) => state.playerId);
  const setGameState = useGameStore((state) => state.setGameState);

  // Error auto-dismiss
  useEffect(() => {
    if (error) {
      setErrorVisible(true);
      const timer = setTimeout(() => {
        setErrorVisible(false);
        setTimeout(() => setError(''), 300);
      }, 4000);
      return () => clearTimeout(timer);
    }
  }, [error, setError]);

  // Fetch initial state
  useEffect(() => {
    if (!matchId) return;

    if (!storeMatchId || storeMatchId !== matchId) {
      navigate('/');
      return;
    }

    const fetchState = async () => {
      try {
        const state = await matchAPI.getState(matchId, storePlayerId || undefined);
        setGameState(state);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to fetch game state');
      }
    };

    if (!gameState && storePlayerId) {
      fetchState();
    }
  }, [matchId, storeMatchId, storePlayerId, gameState, navigate, setGameState, setError]);

  // Concede handler
  const handleConcede = useCallback(async () => {
    if (!matchId || !playerId) return;
    if (!confirm('Are you sure you want to concede?')) return;

    try {
      await matchAPI.concede(matchId, playerId);
      navigate('/');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to concede');
    }
  }, [matchId, playerId, navigate, setError]);

  // Loading state
  if (!gameState || !playerId) {
    return (
      <div className="min-h-screen bg-gray-950 flex items-center justify-center">
        <div className="text-center">
          <div className="w-16 h-16 border-4 border-yellow-500 border-t-transparent rounded-full animate-spin mx-auto mb-4" />
          <p className="text-gray-400">Loading duel...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-950 flex">
      {/* Main Game Area */}
      <div className="flex-1 relative">
        <YGOGameBoard
          gameState={gameState}
          playerId={playerId}
          isMyTurn={isMyTurn()}
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
          ygoPhase={ygoPhase}
          gameLog={gameLog}
          onNormalSummon={normalSummon}
          onSetMonster={setMonster}
          onFlipSummon={flipSummon}
          onChangePosition={changePosition}
          onActivateCard={activateCard}
          onSetSpellTrap={setSpellTrap}
          onDeclareAttack={declareAttack}
          onDirectAttack={directAttack}
          onEndPhase={endPhase}
          onEndTurn={endTurn}
        />

        {/* Toast-style error */}
        <AnimatePresence>
          {errorVisible && error && (
            <motion.div
              initial={{ opacity: 0, y: 40 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 40 }}
              className="fixed bottom-20 left-1/2 -translate-x-1/2 bg-red-900/90 border border-red-500 rounded-lg px-4 py-2 text-red-200 text-sm shadow-lg z-50 max-w-md"
              onClick={() => setErrorVisible(false)}
            >
              {error}
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Sidebar */}
      <div className="w-56 bg-gray-900 border-l border-indigo-900/50 flex flex-col">
        {/* Connection Status */}
        <div className="p-3 border-b border-indigo-900/50 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className={`w-2 h-2 rounded-full ${isConnected ? 'bg-green-500' : 'bg-red-500'}`} />
            <span className="text-xs text-gray-400">
              {isConnected ? 'Connected' : 'Disconnected'}
            </span>
          </div>
          <button
            onClick={handleConcede}
            className="text-xs text-red-400 hover:text-red-300"
          >
            Concede
          </button>
        </div>

        {/* Turn info */}
        <div className="p-3 border-b border-indigo-900/50">
          <div className="text-xs text-gray-400 uppercase tracking-wide mb-1">Status</div>
          <div className={`text-sm font-bold ${isMyTurn() ? 'text-yellow-400' : 'text-gray-500'}`}>
            {isMyTurn() ? 'Your Turn' : "Waiting..."}
          </div>
          <div className="text-xs text-gray-500 mt-1">
            Turn {gameState.turn_number} | {PHASE_LABELS[ygoPhase] || ygoPhase}
          </div>
        </div>

        {/* Turn actions info */}
        {myPlayer && isMyTurn() && (
          <div className="p-3 border-b border-indigo-900/50 space-y-1">
            <div className="text-xs text-gray-400 uppercase tracking-wide mb-1">Actions</div>
            <div className={`text-xs ${myPlayer.normal_summon_used ? 'text-gray-500 line-through' : 'text-green-400'}`}>
              Normal Summon {myPlayer.normal_summon_used ? '(used)' : '(available)'}
            </div>
          </div>
        )}

        {/* Game log */}
        <div className="flex-1 p-3 overflow-y-auto">
          <div className="text-xs text-gray-400 uppercase tracking-wide mb-2">Game Log</div>
          <div className="space-y-1">
            {gameLog.slice(-20).reverse().map((entry, i) => (
              <div key={i} className="text-[10px] text-gray-400 leading-tight">
                <span className="text-gray-600">[T{entry.turn}]</span> {entry.text}
              </div>
            ))}
            {gameLog.length === 0 && (
              <div className="text-xs text-gray-600">No log entries yet</div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

const PHASE_LABELS: Record<string, string> = {
  DRAW: 'Draw Phase',
  STANDBY: 'Standby Phase',
  MAIN1: 'Main Phase 1',
  BATTLE_START: 'Battle Phase',
  BATTLE_STEP: 'Battle Step',
  DAMAGE_STEP: 'Damage Step',
  DAMAGE_CALC: 'Damage Calc',
  BATTLE_END: 'Battle End',
  MAIN2: 'Main Phase 2',
  END: 'End Phase',
};
