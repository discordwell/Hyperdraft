/**
 * Home Page
 *
 * Main menu for starting games.
 */

import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { matchAPI, botGameAPI } from '../services/api';
import { useGameStore } from '../stores/gameStore';

interface DeckInfo {
  id: string;
  name: string;
  archetype: string;
  colors: string[];
  description: string;
  is_netdeck: boolean;
}

export function Home() {
  const navigate = useNavigate();
  const setConnection = useGameStore((state) => state.setConnection);

  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [gameMode, setGameMode] = useState<'mtg' | 'hearthstone'>('hearthstone');
  const [hsVariant, setHsVariant] = useState<string | null>('riftclash');
  const [heroClass, setHeroClass] = useState<string>('Pyromancer');
  const [playerName, setPlayerName] = useState('Player');
  const [difficulty, setDifficulty] = useState<'easy' | 'medium' | 'hard' | 'ultra'>('ultra');
  const [decks, setDecks] = useState<DeckInfo[]>([]);
  const [playerDeck, setPlayerDeck] = useState<string>('');
  const [aiDeck, setAiDeck] = useState<string>('');
  const [claudexModel, setClaudexModel] = useState('claude-opus-4.6');
  const [gptModel, setGptModel] = useState('gpt-5.3');
  const [recordPrompts, setRecordPrompts] = useState(false);

  useEffect(() => {
    matchAPI.listDecks().then((res) => {
      setDecks(res.decks);
      // Default to Azorius Simulacrum if available
      const azorius = res.decks.find((d: DeckInfo) => d.id === 'azorius_simulacrum_netdeck');
      if (azorius) setPlayerDeck(azorius.id);
      else if (res.decks.length > 0) setPlayerDeck(res.decks[0].id);
      // Default AI to mono red
      const monoRed = res.decks.find((d: DeckInfo) => d.id === 'mono_red_netdeck');
      if (monoRed) setAiDeck(monoRed.id);
      else if (res.decks.length > 0) setAiDeck(res.decks[0].id);
    }).catch(console.error);
  }, []);

  const handleStartGame = async () => {
    setIsLoading(true);
    setError(null);

    try {
      const isHearthstone = gameMode === 'hearthstone';

      // Create match
      const response = await matchAPI.create({
        mode: 'human_vs_bot',
        game_mode: gameMode,
        variant: isHearthstone ? (hsVariant || undefined) : undefined,
        hero_class: isHearthstone && hsVariant !== null ? heroClass : undefined,
        player_name: playerName,
        ai_difficulty: difficulty,
        player_deck_id: isHearthstone ? undefined : (playerDeck || undefined),
        ai_deck_id: isHearthstone ? undefined : (aiDeck || undefined),
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
        mode: gameMode,
        bot1_deck_id: playerDeck || undefined,
        bot2_deck_id: aiDeck || undefined,
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

  const handleStartLlmDuel = async () => {
    setIsLoading(true);
    setError(null);

    try {
      const response = await botGameAPI.start({
        bot1_deck_id: playerDeck || undefined,
        bot2_deck_id: aiDeck || undefined,
        bot1_brain: 'anthropic',
        bot2_brain: 'openai',
        bot1_model: claudexModel,
        bot2_model: gptModel,
        bot1_name: 'Claudex',
        bot2_name: 'GPT-5.3',
        bot1_difficulty: difficulty,
        bot2_difficulty: difficulty,
        bot1_temperature: 0.2,
        bot2_temperature: 0.2,
        record_prompts: recordPrompts,
        delay_ms: 800,
        max_replay_frames: 5000,
      });

      navigate(`/spectate/${response.game_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start LLM duel');
    } finally {
      setIsLoading(false);
    }
  };

  const handleStartUltraMirror = async () => {
    setIsLoading(true);
    setError(null);

    try {
      const response = await botGameAPI.start({
        bot1_deck_id: playerDeck || undefined,
        bot2_deck_id: aiDeck || undefined,
        bot1_brain: 'heuristic',
        bot2_brain: 'heuristic',
        bot1_name: 'Ultra Bot A',
        bot2_name: 'Ultra Bot B',
        bot1_difficulty: 'ultra',
        bot2_difficulty: 'ultra',
        delay_ms: 900,
        max_replay_frames: 5000,
      });

      navigate(`/spectate/${response.game_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start Ultra vs Ultra');
    } finally {
      setIsLoading(false);
    }
  };

  const handleStartClaudexVsUltra = async () => {
    setIsLoading(true);
    setError(null);

    try {
      const response = await botGameAPI.start({
        bot1_deck_id: playerDeck || undefined,
        bot2_deck_id: aiDeck || undefined,
        bot1_brain: 'anthropic',
        bot2_brain: 'heuristic',
        bot1_model: claudexModel,
        bot1_name: 'Claudex',
        bot2_name: 'Ultra Bot',
        bot1_difficulty: 'ultra',
        bot2_difficulty: 'ultra',
        bot1_temperature: 0.2,
        record_prompts: recordPrompts,
        delay_ms: 900,
        max_replay_frames: 5000,
      });

      navigate(`/spectate/${response.game_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start Claudex vs Ultra');
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
          <p className="text-gray-400">AI-Powered Card Game Engine</p>
        </div>

        {/* Error Display */}
        {error && (
          <div className="mb-4 p-3 bg-red-900/50 border border-red-500 rounded text-red-200">
            {error}
          </div>
        )}

        {/* Main Menu Card */}
        <div className="bg-game-surface rounded-lg border border-gray-700 p-6">
          {/* Game Mode */}
          <div className="mb-4">
            <label className="block text-sm text-gray-400 mb-1">
              Game Mode
            </label>
            <div className="flex gap-2">
              <button
                onClick={() => setGameMode('mtg')}
                className={`flex-1 px-4 py-2 rounded transition-colors ${
                  gameMode === 'mtg'
                    ? 'bg-game-accent text-white'
                    : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
                }`}
              >
                Magic: The Gathering
              </button>
              <button
                onClick={() => setGameMode('hearthstone')}
                className={`flex-1 px-4 py-2 rounded transition-colors ${
                  gameMode === 'hearthstone'
                    ? 'bg-game-accent text-white'
                    : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
                }`}
              >
                Hearthstone
              </button>
            </div>
          </div>

          {/* Hearthstone Variant & Class Picker */}
          {gameMode === 'hearthstone' && (
            <>
              <div className="mb-4">
                <label className="block text-sm text-gray-400 mb-1">Variant</label>
                <div className="flex gap-2">
                  <button
                    onClick={() => {
                      setHsVariant('riftclash');
                      if (heroClass !== 'Pyromancer' && heroClass !== 'Cryomancer') {
                        setHeroClass('Pyromancer');
                      }
                    }}
                    className={`flex-1 px-3 py-2 rounded text-sm font-semibold transition-colors ${
                      hsVariant === 'riftclash'
                        ? 'bg-amber-600 text-white'
                        : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
                    }`}
                  >
                    Riftclash
                  </button>
                  <button
                    onClick={() => {
                      setHsVariant('stormrift');
                      if (heroClass !== 'Pyromancer' && heroClass !== 'Cryomancer') {
                        setHeroClass('Pyromancer');
                      }
                    }}
                    className={`flex-1 px-3 py-2 rounded text-sm font-semibold transition-colors ${
                      hsVariant === 'stormrift'
                        ? 'bg-purple-600 text-white'
                        : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
                    }`}
                  >
                    Stormrift
                  </button>
                  <button
                    onClick={() => {
                      setHsVariant('frierenrift');
                      if (heroClass !== 'Frieren' && heroClass !== 'Macht') {
                        setHeroClass('Frieren');
                      }
                    }}
                    className={`flex-1 px-3 py-2 rounded text-sm font-semibold transition-colors ${
                      hsVariant === 'frierenrift'
                        ? 'bg-cyan-700 text-white'
                        : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
                    }`}
                  >
                    Frierenrift
                  </button>
                  <button
                    onClick={() => setHsVariant(null)}
                    className={`flex-1 px-3 py-2 rounded text-sm font-semibold transition-colors ${
                      hsVariant === null
                        ? 'bg-game-accent text-white'
                        : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
                    }`}
                  >
                    Vanilla HS
                  </button>
                </div>
              </div>

              {hsVariant !== null && (
                <div className="mb-4">
                  <label className="block text-sm text-gray-400 mb-1">Hero Class</label>
                  {hsVariant === 'frierenrift' ? (
                    <>
                      <div className="flex gap-2">
                        <button
                          onClick={() => setHeroClass('Frieren')}
                          className={`flex-1 px-3 py-2 rounded text-sm font-semibold transition-colors ${
                            heroClass === 'Frieren'
                              ? 'bg-cyan-700 text-white'
                              : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
                          }`}
                        >
                          Frieren
                        </button>
                        <button
                          onClick={() => setHeroClass('Macht')}
                          className={`flex-1 px-3 py-2 rounded text-sm font-semibold transition-colors ${
                            heroClass === 'Macht'
                              ? 'bg-amber-700 text-white'
                              : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
                          }`}
                        >
                          Macht
                        </button>
                      </div>
                      <p className="text-xs text-gray-500 mt-1">
                        {heroClass === 'Frieren'
                          ? 'Control mage shells with tri-color shard planning and high spell precision.'
                          : 'Demon pressure with shard-fueled removal and gold-curse tempo.'}
                      </p>
                    </>
                  ) : (
                    <>
                      <div className="flex gap-2">
                        <button
                          onClick={() => setHeroClass('Pyromancer')}
                          className={`flex-1 px-3 py-2 rounded text-sm font-semibold transition-colors ${
                            heroClass === 'Pyromancer'
                              ? 'bg-orange-600 text-white'
                              : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
                          }`}
                        >
                          Pyromancer
                        </button>
                        <button
                          onClick={() => setHeroClass('Cryomancer')}
                          className={`flex-1 px-3 py-2 rounded text-sm font-semibold transition-colors ${
                            heroClass === 'Cryomancer'
                              ? 'bg-cyan-600 text-white'
                              : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
                          }`}
                        >
                          Cryomancer
                        </button>
                      </div>
                      <p className="text-xs text-gray-500 mt-1">
                        {heroClass === 'Pyromancer'
                          ? (hsVariant === 'riftclash'
                            ? 'Burn tempo with deterministic spell pressure.'
                            : 'Fire & Storm. Aggressive burn and spell synergy.')
                          : (hsVariant === 'riftclash'
                            ? 'Freeze-control and armor value with board denial.'
                            : 'Ice & Void. Control, card advantage, defensive value.')}
                      </p>
                    </>
                  )}
                </div>
              )}
            </>
          )}

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
          <div className="mb-4">
            <label className="block text-sm text-gray-400 mb-1">
              AI Difficulty
            </label>
            <div className="flex gap-2">
              {(['easy', 'medium', 'hard', 'ultra'] as const).map((d) => (
                <button
                  key={d}
                  onClick={() => setDifficulty(d)}
                  className={`flex-1 px-3 py-2 rounded text-sm font-semibold transition-all ${
                    difficulty === d
                      ? d === 'ultra' ? 'bg-purple-600 text-white' : 'bg-game-accent text-white'
                      : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
                  }`}
                >
                  {d.charAt(0).toUpperCase() + d.slice(1)}
                </button>
              ))}
            </div>
            {difficulty === 'ultra' && (
              <p className="text-xs text-purple-400 mt-1">Full Ultra heuristics enabled.</p>
            )}
          </div>

          {/* Deck Selection (MTG only — HS variants use built-in decks) */}
          {gameMode === 'mtg' && (
            <>
              <div className="mb-4">
                <label className="block text-sm text-gray-400 mb-1">Your Deck</label>
                <select
                  value={playerDeck}
                  onChange={(e) => setPlayerDeck(e.target.value)}
                  className="w-full px-3 py-2 bg-gray-800 border border-gray-600 rounded text-white focus:outline-none focus:border-game-accent"
                >
                  <optgroup label="Tournament Netdecks">
                    {decks.filter(d => d.is_netdeck).map(d => (
                      <option key={d.id} value={d.id}>{d.name} ({d.archetype})</option>
                    ))}
                  </optgroup>
                  <optgroup label="Standard Decks">
                    {decks.filter(d => !d.is_netdeck).map(d => (
                      <option key={d.id} value={d.id}>{d.name} ({d.archetype})</option>
                    ))}
                  </optgroup>
                </select>
              </div>

              <div className="mb-6">
                <label className="block text-sm text-gray-400 mb-1">AI Deck</label>
                <select
                  value={aiDeck}
                  onChange={(e) => setAiDeck(e.target.value)}
                  className="w-full px-3 py-2 bg-gray-800 border border-gray-600 rounded text-white focus:outline-none focus:border-game-accent"
                >
                  <optgroup label="Tournament Netdecks">
                    {decks.filter(d => d.is_netdeck).map(d => (
                      <option key={d.id} value={d.id}>{d.name} ({d.archetype})</option>
                    ))}
                  </optgroup>
                  <optgroup label="Standard Decks">
                    {decks.filter(d => !d.is_netdeck).map(d => (
                      <option key={d.id} value={d.id}>{d.name} ({d.archetype})</option>
                    ))}
                  </optgroup>
                </select>
              </div>
            </>
          )}

          {/* Play vs Bot Button */}
          <button
            onClick={handleStartGame}
            disabled={isLoading}
            className="w-full px-4 py-3 bg-game-accent text-white rounded-lg font-bold text-lg hover:bg-red-500 transition-all disabled:opacity-50 disabled:cursor-not-allowed mb-3"
          >
            {isLoading
              ? 'Creating Game...'
              : (gameMode === 'hearthstone' && hsVariant === 'riftclash' && difficulty === 'ultra'
                ? 'Play Riftclash vs Codex Ultra'
                : (gameMode === 'hearthstone' && hsVariant === 'frierenrift' && difficulty === 'ultra'
                  ? 'Play Frierenrift vs Codex Ultra'
                  : 'Play vs AI'))}
          </button>

          {/* MTG-only bot game options */}
          {gameMode === 'mtg' && (
            <>
              {/* Spectate Bot Game Button */}
              <button
                onClick={handleStartBotGame}
                disabled={isLoading}
                className="w-full px-4 py-3 bg-gray-700 text-white rounded-lg font-semibold hover:bg-gray-600 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Watch Bot vs Bot
              </button>

              <div className="mt-3">
                <div className="text-xs text-gray-400 mb-2">Battle Presets</div>
                <div className="grid grid-cols-2 gap-2">
                  <button
                    onClick={handleStartUltraMirror}
                    disabled={isLoading}
                    className="px-3 py-2 bg-indigo-700 text-white rounded-lg text-sm font-semibold hover:bg-indigo-600 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    Ultra vs Ultra
                  </button>
                  <button
                    onClick={handleStartClaudexVsUltra}
                    disabled={isLoading}
                    className="px-3 py-2 bg-teal-700 text-white rounded-lg text-sm font-semibold hover:bg-teal-600 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    Claudex vs Ultra
                  </button>
                </div>
              </div>

              {/* LLM Duel */}
              <div className="mt-3 p-4 bg-gray-800/60 border border-gray-700 rounded-lg">
                <div className="flex items-center justify-between mb-3">
                  <div>
                    <div className="text-sm font-bold text-white">Custom LLM Duel</div>
                    <div className="text-xs text-gray-400">Anthropic vs OpenAI (requires API keys)</div>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-2 mb-3">
                  <div>
                    <label className="block text-xs text-gray-400 mb-1">Claudex model</label>
                    <input
                      type="text"
                      value={claudexModel}
                      onChange={(e) => setClaudexModel(e.target.value)}
                      className="w-full px-2 py-2 bg-gray-900 border border-gray-700 rounded text-white text-sm focus:outline-none focus:border-game-accent"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-gray-400 mb-1">GPT model</label>
                    <input
                      type="text"
                      value={gptModel}
                      onChange={(e) => setGptModel(e.target.value)}
                      className="w-full px-2 py-2 bg-gray-900 border border-gray-700 rounded text-white text-sm focus:outline-none focus:border-game-accent"
                    />
                  </div>
                </div>

                <label className="flex items-center gap-2 text-xs text-gray-400 mb-3 select-none">
                  <input
                    type="checkbox"
                    checked={recordPrompts}
                    onChange={(e) => setRecordPrompts(e.target.checked)}
                  />
                  Record prompts in replay
                </label>

                <button
                  onClick={handleStartLlmDuel}
                  disabled={isLoading}
                  className="w-full px-4 py-3 bg-purple-700 text-white rounded-lg font-semibold hover:bg-purple-600 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  Watch Claudex vs GPT
                </button>
              </div>
            </>
          )}

          {/* Deckbuilder Link */}
          <button
            onClick={() => navigate('/deckbuilder')}
            className="w-full px-4 py-3 mt-3 bg-gray-800 text-gray-300 rounded-lg font-semibold hover:bg-gray-700 hover:text-white transition-all border border-gray-600"
          >
            Deckbuilder
          </button>

          {/* Gatherer Link */}
          <button
            onClick={() => navigate('/gatherer')}
            className="w-full px-4 py-3 mt-3 bg-gray-800 text-gray-300 rounded-lg font-semibold hover:bg-gray-700 hover:text-white transition-all border border-gray-600"
          >
            Card Database
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
