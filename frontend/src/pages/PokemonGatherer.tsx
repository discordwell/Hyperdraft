/**
 * Pokemon Gatherer Page
 *
 * Card database browser for Pokemon TCG cards (sv_starter + Beyond Ravnica).
 * Mirrors the MTG Gatherer layout but Pokemon-aware.
 */

import { useNavigate } from 'react-router-dom';
import {
  PokemonSetSidebar,
  PokemonFilterBar,
  PokemonCardGrid,
  PokemonCardDetailModal,
} from '../components/pokemon-gatherer';

export function PokemonGatherer() {
  const navigate = useNavigate();

  return (
    <div className="min-h-screen bg-game-bg flex flex-col">
      <header className="bg-gray-900 border-b border-gray-700 px-6 py-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <button
              onClick={() => navigate('/')}
              className="text-gray-400 hover:text-white transition-colors"
              title="Back to Home"
            >
              ← Back
            </button>
            <div>
              <h1 className="text-2xl font-bold text-white font-['Cinzel']">
                Pokemon Gatherer
              </h1>
              <p className="text-sm text-gray-400">Pokemon TCG Card Database</p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={() => navigate('/gatherer')}
              className="px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded transition-colors text-sm"
            >
              MTG Gatherer
            </button>
          </div>
        </div>
      </header>

      <div className="flex-1 flex overflow-hidden">
        <PokemonSetSidebar />
        <div className="flex-1 flex flex-col overflow-hidden">
          <PokemonFilterBar />
          <PokemonCardGrid />
        </div>
      </div>

      <PokemonCardDetailModal />
    </div>
  );
}

export default PokemonGatherer;
