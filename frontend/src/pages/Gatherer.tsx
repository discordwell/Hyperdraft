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
    <div className="min-h-screen bg-game-bg flex flex-col">
      {/* Header */}
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
                Gatherer
              </h1>
              <p className="text-sm text-gray-400">Card Database Browser</p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={() => navigate('/deckbuilder')}
              className="px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded transition-colors text-sm"
            >
              Deckbuilder
            </button>
          </div>
        </div>
      </header>

      {/* Main content */}
      <div className="flex-1 flex overflow-hidden">
        {/* Sidebar */}
        <SetSidebar />

        {/* Main area */}
        <div className="flex-1 flex flex-col overflow-hidden">
          {/* Filter bar */}
          <GathererFilterBar />

          {/* Card grid */}
          <GathererCardGrid />
        </div>
      </div>

      {/* Card detail modal */}
      <CardDetailModal />
    </div>
  );
}

export default Gatherer;
