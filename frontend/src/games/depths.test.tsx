/**
 * Depths board art coverage tests.
 *
 * Pins down the JSX paths that render card art via <DepthsArt>:
 *   1. Depth-ladder VesselTile (own + opponent sides of each band).
 *   2. Mines on the band-edge MineTile row.
 *   3. The hand-tile footer.
 *
 * Before this suite was added, Phase A's `DepthsArt` slot lived only on
 * VesselTile + the hand-tile, AND VesselTile suppressed art for ghosted
 * (opponent's undetected) vessels via `{!ghosted && ...}`. The wet test
 * spectator view picks one player's POV, so the 8 opponent-side
 * undetected vessels rendered with no <img>. Removing the ghosted-gate
 * + adding art to MineTile + Selected-Vessel sidebar means art shows on
 * every vessel-render path.
 *
 * Each test pins the URL the backend already populates (via
 * src/cards/depths/submarine_fleet/__init__.py::_wire_image_urls).
 */

import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { CardData, GameState, PlayerData } from '../types';

import { DepthsGameBoard } from './depths';

// ── Test fixtures ──────────────────────────────────────────────────────

function makeVessel(overrides: Partial<CardData>): CardData {
  return {
    id: 'v1',
    name: 'U-Boat Wolf Cub',
    domain: null,
    mana_cost: null,
    types: ['DEPTHS_VESSEL'],
    subtypes: ['Submarine'],
    power: 2,
    toughness: 3,
    text: '',
    tapped: false,
    counters: {},
    damage: 0,
    controller: 'p1',
    owner: 'p1',
    depth_band: 'PERISCOPE',
    detected: false,
    hull: 3,
    is_flagship: false,
    image_url: '/api/card-art/depths/submarine_fleet/u_boat_wolf_cub.png',
    ...overrides,
  };
}

function makeMine(overrides: Partial<CardData>): CardData {
  return {
    id: 'm1',
    name: 'Acoustic Decoy',
    domain: null,
    mana_cost: null,
    types: ['DEPTHS_MINE'],
    subtypes: [],
    power: null,
    toughness: null,
    text: '',
    tapped: false,
    counters: {},
    damage: 0,
    controller: 'p1',
    owner: 'p1',
    depth_band: 'MID',
    detected: false,
    hull: 0,
    is_flagship: false,
    image_url: '/api/card-art/depths/submarine_fleet/acoustic_decoy.png',
    ...overrides,
  };
}

function makePlayer(id: string, name: string): PlayerData {
  return {
    id,
    name,
    life: 25,
    has_lost: false,
    hand_size: 0,
    library_size: 30,
    tc: 3,
    sc: 3,
    tc_max: 5,
    sc_max: 5,
    flagship_id: null,
  };
}

function makeGameState(overrides: Partial<GameState> = {}): GameState {
  return {
    match_id: 'depths-test',
    turn_number: 5,
    phase: 'PRECOMBAT_MAIN',
    step: 'MAIN',
    active_player: 'p1',
    priority_player: 'p1',
    players: { p1: makePlayer('p1', 'You'), p2: makePlayer('p2', 'Opponent') },
    battlefield: [],
    stack: [],
    hand: [],
    graveyard: { p1: [], p2: [] },
    legal_actions: [],
    combat: null,
    is_game_over: false,
    winner: null,
    game_mode: 'depths',
    depths_phase: 'maneuver',
    ...overrides,
  };
}

function noop() {
  /* no-op */
}
function noopFalse() {
  return false;
}

function renderBoard(
  vessels: { mine: CardData[]; opp: CardData[] },
  options: { hand?: CardData[]; myMines?: CardData[]; oppMines?: CardData[] } = {},
) {
  const hand = options.hand ?? [];
  const myMines = options.myMines ?? [];
  const oppMines = options.oppMines ?? [];
  const battlefield = [...vessels.mine, ...vessels.opp, ...myMines, ...oppMines];
  return render(
    <DepthsGameBoard
      gameState={makeGameState({ battlefield, hand })}
      playerId="p1"
      opponentId="p2"
      myPlayer={makePlayer('p1', 'You')}
      opponentPlayer={makePlayer('p2', 'Opponent')}
      myFlagship={null}
      opponentFlagship={null}
      myVessels={vessels.mine}
      opponentVessels={vessels.opp}
      myMines={myMines}
      opponentMines={oppMines}
      isMyTurn={false}
      canPlayCard={noopFalse}
      canUseVessel={noopFalse}
      canIntercept={noopFalse}
      onPlayCard={noop}
      onDive={noop}
      onSurface={noop}
      onLayMine={noop}
      onDeclareAttackers={noop}
      onDetect={noop}
      onDeclareInterceptors={noop}
      onActivateAbility={noop}
      onEndTurn={noop}
    />,
  );
}

// ── Tests ──────────────────────────────────────────────────────────────

describe('DepthsGameBoard depth-ladder art slot', () => {
  it('renders <img> with backend-populated src for an own vessel on the ladder', () => {
    const mine = makeVessel({
      id: 'mine-1',
      name: 'U-Boat Wolf Cub',
      controller: 'p1',
      image_url: '/api/card-art/depths/submarine_fleet/u_boat_wolf_cub.png',
    });
    renderBoard({ mine: [mine], opp: [] });

    // The ladder tile should mount an <img> with the backend-supplied src.
    const imgs = screen
      .getAllByRole('img', { hidden: true })
      .filter((el) => el.getAttribute('src')?.includes('u_boat_wolf_cub.png'));
    expect(imgs.length).toBeGreaterThanOrEqual(1);
  });

  it('renders <img> for opponent ghosted (undetected) vessel on the ladder', () => {
    // Previously the {!ghosted && ...} guard suppressed DepthsArt entirely.
    // Now opponent-undetected vessels render the same art with a blur/saturate
    // dim so the silent silhouette stays readable as "this is a hostile sub".
    const opp = makeVessel({
      id: 'opp-1',
      name: 'Acoustic Decoy',
      controller: 'p2',
      owner: 'p2',
      detected: false,
      depth_band: 'DEEP',
      image_url: '/api/card-art/depths/submarine_fleet/acoustic_decoy.png',
    });
    renderBoard({ mine: [], opp: [opp] });

    const imgs = screen
      .getAllByRole('img', { hidden: true })
      .filter((el) => el.getAttribute('src')?.includes('acoustic_decoy.png'));
    expect(imgs.length).toBeGreaterThanOrEqual(1);
  });

  it('renders <img> on MineTile (band-edge mine row)', () => {
    // Mines previously rendered only the ◇ glyph + name. Adding DepthsArt
    // means the mine slot shows the same per-card art as Vessels.
    const mine = makeMine({
      id: 'mine-tile-1',
      name: 'Acoustic Decoy',
      image_url: '/api/card-art/depths/submarine_fleet/acoustic_decoy.png',
    });
    renderBoard({ mine: [], opp: [] }, { myMines: [mine] });

    const imgs = screen
      .getAllByRole('img', { hidden: true })
      .filter((el) => el.getAttribute('src')?.includes('acoustic_decoy.png'));
    expect(imgs.length).toBeGreaterThanOrEqual(1);
  });

  it('renders <img> on the hand tile (Phase A baseline)', () => {
    // Pin the hand-tile art slot — Phase A already wired this; this test
    // protects the spot from accidental regression as the sidebar slots
    // expand.
    const card = makeVessel({
      id: 'hand-1',
      name: 'Coelacanth Class',
      controller: 'p1',
      image_url: '/api/card-art/depths/submarine_fleet/coelacanth_class.png',
    });
    renderBoard({ mine: [], opp: [] }, { hand: [card] });

    const imgs = screen
      .getAllByRole('img', { hidden: true })
      .filter((el) => el.getAttribute('src')?.includes('coelacanth_class.png'));
    expect(imgs.length).toBeGreaterThanOrEqual(1);
  });
});
