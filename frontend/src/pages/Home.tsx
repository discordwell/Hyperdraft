/**
 * Home Page
 *
 * Main menu for starting games.
 */

import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { matchAPI, botGameAPI } from '../services/api';
import { useGameStore } from '../stores/gameStore';

export function Home() {
  const navigate = useNavigate();
  const setConnection = useGameStore((state) => state.setConnection);

  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [playerName, setPlayerName] = useState('Player');
  const [difficulty, setDifficulty] = useState<'easy' | 'medium' | 'hard'>('medium');

  const handleStartGame = async () => {
    setIsLoading(true);
    setError(null);

    try {
      // Create match
      const response = await matchAPI.create({
        mode: 'human_vs_bot',
        player_name: playerName,
        ai_difficulty: difficulty,
        player_deck: [],
        ai_deck: [],
      });

      // Set connection info in store
      setConnection(response.match_id, response.player_id, false);

      // Start the match
      await matchAPI.start(response.match_id);

      // Navigate to game
      navigate(`/game/${response.match_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create game');
    } finally {
      setIsLoading(false);
    }
  };

  const handleStartBotGame = async () => {
    setIsLoading(true);
    setError(null);

    try {
      const response = await botGameAPI.start({
        bot1_difficulty: difficulty,
        bot2_difficulty: difficulty,
        delay_ms: 1500,
      });

      navigate(`/spectate/${response.game_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start bot game');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-game-bg flex items-center justify-center p-8">
      <div className="max-w-md w-full">
        {/* Logo/Title */}
        <div className="text-center mb-8">
          <h1 className="text-5xl font-bold text-white mb-2 font-['Cinzel']">
            Hyperdraft
          </h1>
          <p className="text-gray-400">MTG Arena-Style Card Game</p>
        </div>

        {/* Error Display */}
        {error && (
          <div className="mb-4 p-3 bg-red-900/50 border border-red-500 rounded text-red-200">
            {error}
          </div>
        )}

        {/* Main Menu Card */}
        <div className="bg-game-surface rounded-lg border border-gray-700 p-6">
          {/* Player Name */}
          <div className="mb-4">
            <label className="block text-sm text-gray-400 mb-1">
              Player Name
            </label>
            <input
              type="text"
              value={playerName}
              onChange={(e) => setPlayerName(e.target.value)}
              className="w-full px-3 py-2 bg-gray-800 border border-gray-600 rounded text-white focus:outline-none focus:border-game-accent"
              placeholder="Enter your name"
            />
          </div>

          {/* Difficulty */}
          <div className="mb-6">
            <label className="block text-sm text-gray-400 mb-1">
              AI Difficulty
            </label>
            <div className="flex gap-2">
              {(['easy', 'medium', 'hard'] as const).map((d) => (
                <button
                  key={d}
                  onClick={() => setDifficulty(d)}
                  className={`flex-1 px-3 py-2 rounded text-sm font-semibold transition-all ${
                    difficulty === d
                      ? 'bg-game-accent text-white'
                      : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
                  }`}
                >
                  {d.charAt(0).toUpperCase() + d.slice(1)}
                </button>
              ))}
            </div>
          </div>

          {/* Play vs Bot Button */}
          <button
            onClick={handleStartGame}
            disabled={isLoading}
            className="w-full px-4 py-3 bg-game-accent text-white rounded-lg font-bold text-lg hover:bg-red-500 transition-all disabled:opacity-50 disabled:cursor-not-allowed mb-3"
          >
            {isLoading ? 'Creating Game...' : 'Play vs AI'}
          </button>

          {/* Spectate Bot Game Button */}
          <button
            onClick={handleStartBotGame}
            disabled={isLoading}
            className="w-full px-4 py-3 bg-gray-700 text-white rounded-lg font-semibold hover:bg-gray-600 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Watch Bot vs Bot
          </button>
        </div>

        {/* Info */}
        <div className="mt-6 text-center text-gray-500 text-sm">
          <p>Uses test cards from the Hyperdraft engine.</p>
          <p className="mt-1">
            Backend:{' '}
            <code className="text-gray-400">uvicorn src.server.main:socket_app</code>
          </p>
        </div>
      </div>
    </div>
  );
}

export default Home;
