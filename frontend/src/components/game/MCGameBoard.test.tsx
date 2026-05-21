/**
 * Minecraft card-art rendering smoke test.
 *
 * Confirms two contracts:
 *   1. When a mob carries an `image_url`, the CardTile renders an <img>
 *      whose src matches the backend-supplied URL.
 *   2. When `image_url` is missing, the CardTile falls back to the
 *      derived `/api/card-art/minecraft/<slug>.png` path so art still
 *      shows for any card whose PNG happens to be on disk.
 *
 * The fallback voxel glyph rendering itself is exercised by triggering
 * an onError on the <img> — happy-dom doesn't load the image at all
 * during tests, so we drive the error path explicitly.
 */

import { describe, it, expect } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { MCGameBoard } from './MCGameBoard';
import type { CardData, GameState, PlayerData } from '../../types';

function makeCard(overrides: Partial<CardData> & { id: string; name: string }): CardData {
  return {
    domain: null,
    mana_cost: null,
    types: ['MC_MOB'],
    subtypes: [],
    power: 2,
    toughness: 2,
    text: '',
    tapped: false,
    counters: {},
    damage: 0,
    controller: 'bob',
    owner: 'bob',
    ...overrides,
  } as CardData;
}

function makePlayer(id: string, name: string): PlayerData {
  return {
    id,
    name,
    life: 20,
    has_lost: false,
    hand_size: 0,
    library_size: 50,
    mc_materials: { wood: 0, stone: 0, iron: 0, redstone: 0, diamond: 0 },
    mc_avatar_gear: {},
    mc_avatar_action_used: false,
  };
}

const baseState: GameState = {
  match_id: 'm1',
  turn_number: 1,
  phase: 'PRECOMBAT_MAIN',
  step: 'MAIN',
  active_player: 'alice',
  priority_player: 'alice',
  players: {
    alice: makePlayer('alice', 'Alice'),
    bob: makePlayer('bob', 'Bob'),
  },
  battlefield: [],
  stack: [],
  pending_triggers: [],
  hand: [],
  graveyard: { alice: [], bob: [] },
  legal_actions: [],
  game_mode: 'minecraft',
  minecraft_day_phase: 'day',
  minecraft_grid: {
    alice: [[null, null, null], [null, null, null], [null, null, null]],
    bob: [[null, null, null], [null, null, null], [null, null, null]],
  },
  minecraft_biomes: { alice: [], bob: [] },
  minecraft_combat: {},
  minecraft_exposed_targets: { alice: [], bob: [] },
} as unknown as GameState;

const noop = () => undefined;
const callbacks = {
  canPlayCard: () => false,
  canUseMob: () => false,
  canBlockMob: () => false,
  onPlayCard: noop,
  onMineWorker: noop,
  onAvatarMine: noop,
  onAvatarExplore: noop,
  onAvatarAttack: noop,
  onAttack: noop,
  onDeclareBlockers: noop,
  onEndTurn: noop,
};

describe('MCGameBoard card art', () => {
  it('renders an <img> using the backend image_url when supplied', () => {
    const card = makeCard({
      id: 'mob-1',
      name: 'Lantern of the Lost',
      image_url: '/api/card-art/minecraft/lantern_of_the_lost.png',
    });

    render(
      <MCGameBoard
        gameState={baseState}
        playerId="alice"
        opponentId="bob"
        myPlayer={baseState.players.alice}
        opponentPlayer={baseState.players.bob}
        myMobs={[]}
        opponentMobs={[card]}
        isMyTurn
        {...callbacks}
      />,
    );

    // CardTile passes alt="" because the art is decorative — query by src instead.
    const imgs = document.querySelectorAll('img[src="/api/card-art/minecraft/lantern_of_the_lost.png"]');
    expect(imgs.length).toBeGreaterThan(0);
  });

  it('derives the canonical /api/card-art/minecraft path when image_url is absent', () => {
    const card = makeCard({ id: 'mob-2', name: 'Lantern of the Lost' });

    render(
      <MCGameBoard
        gameState={baseState}
        playerId="alice"
        opponentId="bob"
        myPlayer={baseState.players.alice}
        opponentPlayer={baseState.players.bob}
        myMobs={[]}
        opponentMobs={[card]}
        isMyTurn
        {...callbacks}
      />,
    );

    const imgs = document.querySelectorAll('img[src="/api/card-art/minecraft/lantern_of_the_lost.png"]');
    expect(imgs.length).toBeGreaterThan(0);
  });

  it('falls back to a voxel glyph when the <img> errors past every candidate', () => {
    const card = makeCard({ id: 'mob-3', name: 'Lantern of the Lost' });

    render(
      <MCGameBoard
        gameState={baseState}
        playerId="alice"
        opponentId="bob"
        myPlayer={baseState.players.alice}
        opponentPlayer={baseState.players.bob}
        myMobs={[]}
        opponentMobs={[card]}
        isMyTurn
        {...callbacks}
      />,
    );

    const imgs = Array.from(document.querySelectorAll('img[src*="/api/card-art/minecraft/"]'));
    expect(imgs.length).toBeGreaterThan(0);
    // Trigger the error path on every art img — only one in this fixture.
    imgs.forEach((img) => fireEvent.error(img));

    expect(screen.getAllByTestId('mc-card-art-fallback').length).toBeGreaterThan(0);
  });
});
