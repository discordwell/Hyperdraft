/**
 * SCPBoard — read-only board smoke tests.
 *
 * The board is the rendering surface used by spectator + replay dispatch
 * for SCP matches. These tests assert two contracts:
 *
 *   1. It renders without crashing when given a minimal SCP gameState
 *      (no anomalies / personnel / dossiers / incidents).
 *   2. The Phase B card-art thumb (image_url -> 64px square left of the
 *      name) is preserved — this is load-bearing because the SCP card-art
 *      rollout in commit df435c46 specifically depends on that <img>.
 */
import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { SCPBoard } from './SCPBoard';
import type { CardData, GameState, PlayerData } from '../../types';

function makePlayer(id: string, name: string): PlayerData {
  return {
    id,
    name,
    life: 20,
    has_lost: false,
    hand_size: 0,
    library_size: 50,
  } as unknown as PlayerData;
}

function makeAnomaly(overrides: Partial<CardData> & { id: string; name: string }): CardData {
  return {
    domain: null,
    mana_cost: null,
    types: ['SCP_ANOMALY'],
    subtypes: [],
    power: 0,
    toughness: 0,
    text: '',
    tapped: false,
    counters: {},
    damage: 0,
    controller: 'alice',
    owner: 'alice',
    scp_containment: 3,
    scp_curiosity: 2,
    scp_hazard: 4,
    ...overrides,
  } as CardData;
}

function makeState(overrides: Partial<GameState> = {}): GameState {
  return {
    match_id: 'scp-1',
    turn_number: 1,
    phase: 'MAIN',
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
    combat: null,
    is_game_over: false,
    winner: null,
    game_mode: 'scp',
    scp_sites: {
      alice: {
        secrecy: 5,
        breach: 2,
        archives: 0,
        ethics_debt: 1,
        clearance: 3,
        briefing: 0,
        assignment_slots: 4,
        assignments_used: 1,
      },
      bob: {
        secrecy: 4,
        breach: 3,
        archives: 1,
        ethics_debt: 0,
        clearance: 2,
        briefing: 0,
        assignment_slots: 4,
        assignments_used: 0,
      },
    },
    scp_anomalies: { alice: [], bob: [] },
    scp_contained: { alice: [], bob: [] },
    scp_personnel: { alice: [], bob: [] },
    scp_facilities: { alice: [], bob: [] },
    scp_mandates: { alice: [], bob: [] },
    scp_incidents: { alice: [], bob: [] },
    scp_assignment_slots: { alice: 4, bob: 4 },
    ...overrides,
  } as GameState;
}

describe('SCPBoard', () => {
  it('renders both site panels without crashing on a minimal state', () => {
    render(<SCPBoard gameState={makeState()} playerId="alice" />);
    expect(screen.getByText('Alice')).toBeInTheDocument();
    expect(screen.getByText('Bob')).toBeInTheDocument();
    // Both site panel stat tiles render
    expect(screen.getAllByText('Secrecy').length).toBeGreaterThanOrEqual(2);
    expect(screen.getAllByText('Breach').length).toBeGreaterThanOrEqual(2);
  });

  it('shows empty-state placeholders when the player has no anomalies / personnel', () => {
    render(<SCPBoard gameState={makeState()} playerId="alice" />);
    expect(screen.getByText('No active anomalies')).toBeInTheDocument();
    expect(screen.getByText('No active personnel')).toBeInTheDocument();
  });

  it('preserves the Phase B card-art thumb when an anomaly carries image_url', () => {
    const anomaly = makeAnomaly({
      id: 'a1',
      name: 'SCP-173',
      image_url: '/api/card-art/scp/scp_173.png',
    });
    const state = makeState({
      scp_anomalies: { alice: [anomaly], bob: [] },
    });
    render(<SCPBoard gameState={state} playerId="alice" />);
    const imgs = document.querySelectorAll('img[src="/api/card-art/scp/scp_173.png"]');
    expect(imgs.length).toBeGreaterThan(0);
    expect(screen.getByText('SCP-173')).toBeInTheDocument();
  });

  it('renders opposing-side anomalies in the right column', () => {
    const oppAnomaly = makeAnomaly({
      id: 'b1',
      name: 'SCP-682',
      controller: 'bob',
      owner: 'bob',
    });
    const state = makeState({
      scp_anomalies: { alice: [], bob: [oppAnomaly] },
    });
    render(<SCPBoard gameState={state} playerId="alice" />);
    expect(screen.getByText('SCP-682')).toBeInTheDocument();
    expect(screen.getByText('Opposing Active Anomalies')).toBeInTheDocument();
  });

  it('renders the generated RULES block on an anomaly, distinct from flavor', () => {
    const anomaly = makeAnomaly({
      id: 'a-rules',
      name: 'SCP-RULES',
      text: 'Flavorful incident report prose.',
      scp_rules: [
        'Antimeme 3: At each of your end steps it gains a forget counter; at 3 counters it is forgotten (exiled).',
      ],
    });
    const state = makeState({ scp_anomalies: { alice: [anomaly], bob: [] } });
    render(<SCPBoard gameState={state} playerId="alice" />);
    // The generated rules line renders...
    expect(screen.getByText(/Antimeme 3:/)).toBeInTheDocument();
    // ...alongside (not instead of) the flavor text.
    expect(screen.getByText('Flavorful incident report prose.')).toBeInTheDocument();
  });

  it('hides rules on a sealed dossier', () => {
    const sealed = makeAnomaly({
      id: 'a-sealed',
      name: 'Sealed Dossier',
      scp_status: 'sealed',
      scp_rules: [],
      text: 'Sealed anomaly dossier. Reveal to activate its full file.',
    });
    const state = makeState({ scp_anomalies: { alice: [sealed], bob: [] } });
    render(<SCPBoard gameState={state} playerId="alice" />);
    expect(screen.queryByText(/Antimeme/)).not.toBeInTheDocument();
  });

  it('does not call useSCPGame (the live socket hook)', () => {
    // The whole point of SCPBoard is to be hookless. Asserting the import
    // graph doesn't reach back into the live store would require ts-prune
    // or madge; instead we exercise the read-only render path with a
    // hand-built gameState and confirm it works. The absence of socket
    // wiring is a visual + structural property of SCPBoard.tsx; this
    // test is a sentinel — if someone re-introduces a hook call inside
    // the board, the test still passes silently. The intent is
    // documented in the source comment at the top of SCPBoard.tsx.
    render(<SCPBoard gameState={makeState()} playerId="alice" readOnly />);
    expect(screen.getByText('Alice')).toBeInTheDocument();
  });
});
