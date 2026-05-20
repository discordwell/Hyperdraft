import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { botGameAPI, matchAPI } from '../services/api';
import { Home, MINECRAFT_STARTER_DECK_OPTIONS } from './Home';

vi.mock('../services/api', () => ({
  matchAPI: {
    listDecks: vi.fn(),
    listYgoDecks: vi.fn(),
  },
  botGameAPI: {
    start: vi.fn(),
  },
}));

function renderHome() {
  return render(
    <MemoryRouter>
      <Home />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(matchAPI.listDecks).mockResolvedValue({
    decks: [
      {
        id: 'azorius_simulacrum_netdeck',
        name: 'Azorius Simulacrum',
        archetype: 'Control',
        colors: [],
        format: 'standard',
        mainboard_count: 60,
        land_count: 24,
        updated_at: '2026-05-10T00:00:00Z',
      },
      {
        id: 'mono_red_netdeck',
        name: 'Mono Red',
        archetype: 'Aggro',
        colors: [],
        format: 'standard',
        mainboard_count: 60,
        land_count: 20,
        updated_at: '2026-05-10T00:00:00Z',
      },
    ],
    total: 2,
  });
  vi.mocked(matchAPI.listYgoDecks).mockResolvedValue({ decks: [] });
  vi.mocked(botGameAPI.start).mockResolvedValue({ game_id: 'bot-game-1', status: 'running' });
});

describe('Home Minecraft starter deck options', () => {
  it('exposes every registered Minecraft starter deck', () => {
    const values = MINECRAFT_STARTER_DECK_OPTIONS.map((deck) => deck.value);

    expect(values).toEqual(expect.arrayContaining([
      'builder',
      'miner',
      'raider',
      'compleated_dominion',
      'box_of_horrors',
      'trial_chambers',
      'tamed_trails',
      'copper_pulse',
      'deep_dark_echo',
      'bastion_raid',
      'end_voyage',
      'ender_warboss_midrange',
    ]));
    expect(new Set(values).size).toBe(values.length);
  });

  it('hides MTG-only bot presets in Minecraft mode and starts bot games as Minecraft', async () => {
    renderHome();

    // Pick the Minecraft tile from the engine grid.
    fireEvent.click(screen.getByRole('button', { name: 'Minecraft' }));

    expect(screen.getByRole('button', { name: 'Watch Bot vs Bot' })).toBeInTheDocument();

    // Ultra mirror + LLM duel are gated to mtg / yugioh; Minecraft hides the
    // entire Advanced section, so neither the section header nor any of its
    // buttons should render.
    expect(screen.queryByText(/Ultra mirror/i)).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Ultra vs Ultra' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Claudex vs Ultra' })).not.toBeInTheDocument();
    expect(screen.queryByText(/LLM duel/i)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Watch Bot vs Bot' }));

    await waitFor(() => {
      expect(botGameAPI.start).toHaveBeenCalledWith(expect.objectContaining({
        mode: 'minecraft',
        bot1_deck_id: 'builder',
        bot2_deck_id: 'raider',
      }));
    });
  });
});
