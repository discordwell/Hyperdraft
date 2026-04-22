/**
 * YGOGameView Page
 *
 * Dedicated game view for Yu-Gi-Oh! engine games.
 * Dark + Gold themed with tabbed sidebar (Info / Log).
 */

import { useEffect, useCallback, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useYGOGame } from '../hooks/useYGOGame';
import { useGameStore } from '../stores/gameStore';
import { YGOGameBoard } from '../components/game/YGOGameBoard';
import { YGOGameLog } from '../components/game/YGOGameLog';
import { AnimationsToggle } from '../components/game/shared/AnimationsToggle';
import { DragHintOverlay } from '../components/game/DragHintOverlay';
import { matchAPI } from '../services/api';
import { AnimatePresence, motion } from 'framer-motion';

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

export function YGOGameView() {
  const { matchId } = useParams<{ matchId: string }>();
  const navigate = useNavigate();
  const [errorVisible, setErrorVisible] = useState(false);
  const [sidebarTab, setSidebarTab] = useState<'info' | 'log'>('info');

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
    myBanished,
    oppBanished,
    myExtraDeckSize,
    oppExtraDeckSize,
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
      <div className="min-h-screen flex items-center justify-center"
        style={{ background: 'linear-gradient(to bottom, #0a0e1a, #0f1425, #0a0e1a)' }}
      >
        <div className="text-center">
          <div className="w-16 h-16 border-4 border-ygo-gold border-t-transparent rounded-full animate-spin mx-auto mb-4" />
          <p className="text-ygo-gold-dim text-sm tracking-wide">Loading duel...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex"
      style={{ background: 'linear-gradient(to bottom, #0a0e1a, #0f1425, #0a0e1a)' }}
    >
      {/* Main Game Area */}
      <div className="flex-1 relative">
        <DragHintOverlay />
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
          myBanished={myBanished}
          oppBanished={oppBanished}
          myExtraDeckSize={myExtraDeckSize}
          oppExtraDeckSize={oppExtraDeckSize}
          ygoPhase={ygoPhase}
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
              className="fixed bottom-52 left-1/2 -translate-x-1/2 bg-red-900/90 border border-red-500/50 rounded-lg px-4 py-2 text-red-200 text-sm shadow-lg z-50 max-w-md cursor-pointer"
              onClick={() => setErrorVisible(false)}
            >
              {error}
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Sidebar */}
      <div className="w-64 bg-ygo-dark/90 backdrop-blur-sm border-l border-ygo-gold-dim/20 flex flex-col">
        {/* Connection Status */}
        <div className="p-3 border-b border-ygo-gold-dim/15 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className={`w-2 h-2 rounded-full ${isConnected ? 'bg-ygo-gold' : 'bg-red-500'}`} />
            <span className="text-xs text-gray-400">
              {isConnected ? 'Connected' : 'Disconnected'}
            </span>
          </div>
          <button
            onClick={handleConcede}
            className="text-xs text-red-400 hover:text-red-300 transition-colors"
          >
            Concede
          </button>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-ygo-gold-dim/15">
          {(['info', 'log'] as const).map(tab => (
            <button
              key={tab}
              onClick={() => setSidebarTab(tab)}
              className={`flex-1 px-3 py-2 text-xs font-bold uppercase tracking-wider transition-colors ${
                sidebarTab === tab
                  ? 'text-ygo-gold border-b-2 border-ygo-gold'
                  : 'text-gray-500 hover:text-gray-300'
              }`}
            >
              {tab}
            </button>
          ))}
        </div>

        {/* Tab content */}
        <div className="flex-1 overflow-y-auto">
          {sidebarTab === 'info' ? (
            <div className="p-3 space-y-3">
              {/* Turn status */}
              <div>
                <div className="text-[10px] text-ygo-gold-dim uppercase tracking-widest mb-1">Status</div>
                <div className={`text-sm font-bold ${isMyTurn() ? 'text-ygo-gold-bright' : 'text-gray-500'}`}>
                  {isMyTurn() ? 'Your Turn' : "Waiting..."}
                </div>
                <div className="text-xs text-gray-500 mt-1">
                  Turn {gameState.turn_number} | {PHASE_LABELS[ygoPhase] || ygoPhase}
                </div>
              </div>

              {/* Normal summon status */}
              {myPlayer && isMyTurn() && (
                <div>
                  <div className="text-[10px] text-ygo-gold-dim uppercase tracking-widest mb-1">Actions</div>
                  <div className={`text-xs ${myPlayer.normal_summon_used ? 'text-gray-600 line-through' : 'text-ygo-gold'}`}>
                    Normal Summon {myPlayer.normal_summon_used ? '(used)' : '(available)'}
                  </div>
                </div>
              )}

              {/* LP Summary */}
              <div>
                <div className="text-[10px] text-ygo-gold-dim uppercase tracking-widest mb-1">Life Points</div>
                <div className="space-y-1">
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-gray-400">You</span>
                    <span className="text-ygo-gold-bright font-bold">{myPlayer?.lp ?? 8000}</span>
                  </div>
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-gray-400">Opp</span>
                    <span className="text-ygo-gold font-bold">{opponentPlayer?.lp ?? 8000}</span>
                  </div>
                </div>
              </div>

              {/* Zone counts */}
              <div>
                <div className="text-[10px] text-ygo-gold-dim uppercase tracking-widest mb-1">Zones</div>
                <div className="grid grid-cols-2 gap-x-4 gap-y-0.5 text-xs">
                  <span className="text-gray-400">Deck</span>
                  <span className="text-gray-300 text-right">{myPlayer?.library_size ?? 0}</span>
                  <span className="text-gray-400">Graveyard</span>
                  <span className="text-gray-300 text-right">{myGraveyard.length}</span>
                  <span className="text-gray-400">Banished</span>
                  <span className="text-gray-300 text-right">{myBanished.length}</span>
                  <span className="text-gray-400">Extra Deck</span>
                  <span className="text-purple-400 text-right">{myExtraDeckSize}</span>
                </div>
              </div>

              {/* Animations preference */}
              <div className="pt-2 border-t border-ygo-gold-dim/20">
                <AnimationsToggle />
              </div>
            </div>
          ) : (
            <div className="p-3">
              <YGOGameLog
                entries={gameLog}
                playerNames={Object.fromEntries(Object.entries(gameState.players).map(([id, p]) => [id, p.name]))}
              />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
