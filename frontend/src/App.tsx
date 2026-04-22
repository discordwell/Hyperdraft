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
const SpectatorView = lazy(() => import('./pages/SpectatorView'));
const ReplayView = lazy(() => import('./pages/ReplayView'));
const Deckbuilder = lazy(() => import('./pages/Deckbuilder'));
const Gatherer = lazy(() => import('./pages/Gatherer'));

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
          <Route path="/spectate/:gameId" element={<SpectatorView />} />
          <Route path="/replay/:gameId" element={<ReplayView />} />
          <Route path="/deckbuilder" element={<Deckbuilder />} />
          <Route path="/gatherer" element={<Gatherer />} />
        </Routes>
      </Suspense>
    </BrowserRouter>
  );
}

export default App;
