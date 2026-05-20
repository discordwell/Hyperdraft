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
    <div className="min-h-screen bg-brand-ink text-brand-cream flex flex-col">
      <header className="bg-brand-obsidian/85 backdrop-blur-xl border-b border-brand-hairline/60 px-6 py-4 sticky top-0 z-30">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <button
              onClick={() => navigate('/')}
              className="text-brand-chalk hover:text-brand-foil transition-colors text-sm tracking-wide"
              title="Back to Lobby"
            >
              ← Lobby
            </button>
            <div>
              <p className="brand-eyebrow text-brand-sheen">Pokémon Gatherer</p>
              <h1 className="text-xl font-display font-bold text-brand-cream leading-tight">
                Pokémon TCG database
              </h1>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={() => navigate('/gatherer')}
              className="px-4 py-2 bg-brand-shelf hover:bg-brand-glass border border-brand-hairline hover:border-brand-foil/40 text-brand-cream transition-colors text-sm"
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
