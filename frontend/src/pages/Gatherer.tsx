/**
 * Gatherer Page
 *
 * Card database browser similar to Gatherer/Scryfall.
 * Browse cards by set with filtering and sorting.
 */

import { useNavigate } from 'react-router-dom';
import {
  SetSidebar,
  GathererFilterBar,
  GathererCardGrid,
  CardDetailModal,
} from '../components/gatherer';

export function Gatherer() {
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
              <p className="brand-eyebrow text-brand-foil">MTG Gatherer</p>
              <h1 className="text-xl font-display font-bold text-brand-cream leading-tight">
                Card database
              </h1>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={() => navigate('/deckbuilder')}
              className="px-4 py-2 bg-brand-shelf hover:bg-brand-glass border border-brand-hairline hover:border-brand-foil/40 text-brand-cream transition-colors text-sm"
            >
              Deckbuilder
            </button>
          </div>
        </div>
      </header>

      <div className="flex-1 flex overflow-hidden">
        <SetSidebar />
        <div className="flex-1 flex flex-col overflow-hidden">
          <GathererFilterBar />
          <GathererCardGrid />
        </div>
      </div>

      <CardDetailModal />
    </div>
  );
}

export default Gatherer;
