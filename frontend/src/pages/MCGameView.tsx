import { useEffect, useMemo, useState } from 'react';
import { useLocation, useNavigate, useParams } from 'react-router-dom';
import { MCGameBoard } from '../components/game/MCGameBoard';
import { MCMulliganModal } from '../components/game/MCMulliganModal';
import { useMinecraftGame } from '../hooks/useMinecraftGame';
import { useGameStore } from '../stores/gameStore';
import { matchAPI } from '../services/api';
import { GameLog } from '../components/game/GameLog';

export function MCGameView() {
  const { matchId } = useParams<{ matchId: string }>();
  const location = useLocation();
  const navigate = useNavigate();
  const [sidebar, setSidebar] = useState<'state' | 'log'>('state');
  const {
    gameState,
    playerId,
    isConnected,
    myPlayer,
    opponentId,
    opponentPlayer,
    myMobs,
    opponentMobs,
    isMyTurn,
    canPlayCard,
    canUseMob,
    canBlockMob,
    playCard,
    mineWithWorker,
    avatarMine,
    avatarExplore,
    avatarAttack,
    attack,
    declareBlockers,
    endTurn,
    sendMulliganDecision,
    setError,
    error,
  } = useMinecraftGame();

  const storeMatchId = useGameStore((s) => s.matchId);
  const storePlayerId = useGameStore((s) => s.playerId);
  const setGameState = useGameStore((s) => s.setGameState);
  const setConnection = useGameStore((s) => s.setConnection);

  useEffect(() => {
    if (!matchId) return;
    if (!storeMatchId || storeMatchId !== matchId) {
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
        .catch((err) => setError(err instanceof Error ? err.message : 'Failed to fetch game state'));
    }
  }, [matchId, storeMatchId, storePlayerId, gameState, location.search, navigate, setConnection, setGameState, setError]);

  const playerNames = useMemo(() => {
    const names: Record<string, string> = {};
    if (gameState) {
      Object.entries(gameState.players).forEach(([id, player]) => { names[id] = player.name; });
    }
    return names;
  }, [gameState]);

  if (!gameState || !playerId) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-950">
        <div className="h-12 w-12 animate-spin border-4 border-slate-700 border-t-emerald-300" />
      </div>
    );
  }

  const mulliganPrompt = gameState.minecraft_mulligan_pending?.[playerId];

  return (
    <div className="flex min-h-screen bg-slate-950">
      {mulliganPrompt && (
        <MCMulliganModal
          prompt={mulliganPrompt}
          hand={gameState.hand || []}
          onKeep={() => sendMulliganDecision(true)}
          onMulligan={() => sendMulliganDecision(false)}
        />
      )}
      <div className="min-w-0 flex-1">
        <MCGameBoard
          gameState={gameState}
          playerId={playerId}
          opponentId={opponentId}
          myPlayer={myPlayer}
          opponentPlayer={opponentPlayer}
          myMobs={myMobs}
          opponentMobs={opponentMobs}
          isMyTurn={isMyTurn()}
          canPlayCard={canPlayCard}
          canUseMob={canUseMob}
          canBlockMob={canBlockMob}
          onPlayCard={playCard}
          onMineWorker={mineWithWorker}
          onAvatarMine={avatarMine}
          onAvatarExplore={avatarExplore}
          onAvatarAttack={avatarAttack}
          onAttack={attack}
          onDeclareBlockers={declareBlockers}
          onEndTurn={endTurn}
        />
      </div>
      <aside className="hidden w-72 border-l border-slate-800 bg-slate-950/95 text-slate-100 lg:flex lg:flex-col">
        <div className="flex items-center justify-between border-b border-slate-800 p-3">
          <div className="flex items-center gap-2 text-sm">
            <span className={`h-2 w-2 ${isConnected ? 'bg-emerald-400' : 'bg-red-400'}`} />
            {isConnected ? 'Connected' : 'Disconnected'}
          </div>
          <button onClick={() => navigate('/')} className="text-xs text-slate-400 hover:text-white">Menu</button>
        </div>
        <div className="grid grid-cols-2 border-b border-slate-800">
          <button onClick={() => setSidebar('state')} className={`py-2 text-xs font-bold ${sidebar === 'state' ? 'bg-slate-800 text-white' : 'text-slate-500'}`}>State</button>
          <button onClick={() => setSidebar('log')} className={`py-2 text-xs font-bold ${sidebar === 'log' ? 'bg-slate-800 text-white' : 'text-slate-500'}`}>Log</button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto p-3">
          {sidebar === 'state' ? (
            <div className="space-y-3 text-sm">
              <div>
                <div className="text-xs uppercase tracking-wide text-slate-500">Cycle</div>
                <div className="font-black">{gameState.minecraft_day_phase}</div>
              </div>
              <div>
                <div className="text-xs uppercase tracking-wide text-slate-500">Bed Rule</div>
                <p className="text-slate-300">Avatar death respawns at 20 if you control a Bed. Respawn discards all Avatar gear.</p>
              </div>
              {error && <div className="border border-red-800 bg-red-950 p-2 text-red-200">{error}</div>}
            </div>
          ) : (
            <GameLog entries={gameState.game_log || []} playerNames={playerNames} />
          )}
        </div>
      </aside>
    </div>
  );
}

export default MCGameView;
