/**
 * Main Application Component
 *
 * Sets up routing and global providers.
 */

import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { Home, GameView, SpectatorView, Deckbuilder } from './pages';

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/game/:matchId" element={<GameView />} />
        <Route path="/spectate/:gameId" element={<SpectatorView />} />
        <Route path="/deckbuilder" element={<Deckbuilder />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
