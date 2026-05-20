/**
 * Main Application Component
 *
 * Sets up routing and global providers.
 * Uses React.lazy + Suspense for code-splitting heavy mode views.
 */

import { lazy, Suspense } from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { Home } from './pages';

// Code-split: mode views + heavyweight pages are loaded on-demand
const GameView = lazy(() => import('./pages/GameView'));
const HSGameView = lazy(() => import('./pages/HSGameView'));
const PKMGameView = lazy(() => import('./pages/PKMGameView'));
const YGOGameView = lazy(() => import('./pages/YGOGameView').then(m => ({ default: m.YGOGameView })));
const MCGameView = lazy(() => import('./pages/MCGameView'));
const FinanceGameView = lazy(() => import('./pages/FinanceGameView').then(m => ({ default: m.FinanceGameView })));
const DepthsGameView = lazy(() => import('./pages/DepthsGameView').then(m => ({ default: m.DepthsGameView })));
const SCPGameView = lazy(() => import('./pages/SCPGameView').then(m => ({ default: m.SCPGameView })));
const SpectatorView = lazy(() => import('./pages/SpectatorView'));
const WatchLive = lazy(() => import('./pages/WatchLive'));
const AdminTraining = lazy(() => import('./pages/AdminTraining'));
const Replays = lazy(() => import('./pages/Replays'));
const ReplayView = lazy(() => import('./pages/ReplayView'));
const Deckbuilder = lazy(() => import('./pages/Deckbuilder'));
const Gatherer = lazy(() => import('./pages/Gatherer'));
const PokemonGatherer = lazy(() => import('./pages/PokemonGatherer'));
const SCPCardViewer = lazy(() => import('./pages/SCPCardViewer'));
const PhyrexianFrameDemo = lazy(() => import('./pages/PhyrexianFrameDemo'));

function LoadingFallback() {
  return (
    <div className="flex items-center justify-center min-h-screen bg-slate-900">
      <div className="flex flex-col items-center gap-4">
        <div className="w-12 h-12 border-4 border-slate-600 border-t-blue-400 rounded-full animate-spin" />
        <span className="text-slate-400 text-sm font-medium uppercase tracking-widest">Loading...</span>
      </div>
    </div>
  );
}

export function App() {
  return (
    <BrowserRouter>
      <Suspense fallback={<LoadingFallback />}>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/game/:matchId" element={<GameView />} />
          <Route path="/game/:matchId/hs" element={<HSGameView />} />
          <Route path="/game/:matchId/pkm" element={<PKMGameView />} />
          <Route path="/game/:matchId/ygo" element={<YGOGameView />} />
          <Route path="/game/:matchId/mc" element={<MCGameView />} />
          <Route path="/game/:matchId/fin" element={<FinanceGameView />} />
          <Route path="/game/:matchId/depths" element={<DepthsGameView />} />
          <Route path="/game/:matchId/scp" element={<SCPGameView />} />
          <Route path="/spectate/:gameId" element={<SpectatorView />} />
          <Route path="/watch/live" element={<WatchLive />} />
          <Route path="/admin/training" element={<AdminTraining />} />
          <Route path="/replays" element={<Replays />} />
          <Route path="/replay/match/:matchId" element={<ReplayView />} />
          <Route path="/replay/:gameId" element={<ReplayView />} />
          <Route path="/watch/:matchId" element={<GameView />} />
          {/* /watch/:matchId reuses GameView; bot_vs_bot ultra renders both AI seats. */}
          <Route path="/deckbuilder" element={<Deckbuilder />} />
          <Route path="/deckbuilder/:game" element={<Deckbuilder />} />
          <Route path="/gatherer" element={<Gatherer />} />
          <Route path="/pokemon-gatherer" element={<PokemonGatherer />} />
          <Route path="/scp-cards" element={<SCPCardViewer />} />
          <Route path="/cards/scp" element={<SCPCardViewer />} />
          <Route path="/demo/phyrexian-frame" element={<PhyrexianFrameDemo />} />
        </Routes>
      </Suspense>
    </BrowserRouter>
  );
}

export default App;
