/**
 * projectClankersState — backend MVP shape → ClankersState UI contract.
 *
 * Pins the field renames + nesting transforms so the next backend tweak
 * cannot silently break ClankersBoardInner rendering. Originally landed
 * because `state.deathclock.active` crashed on the flat `deathclock_active`
 * key the serializer emitted; payload here mirrors session.py:2950.
 */

import { describe, expect, it } from 'vitest';

import { projectClankersState } from './useClankersGame';

// Trimmed sample of what _serialize_clankers_state actually puts under
// `state.clankers` (turn 0, FORGE-Δ vs ETHOS-7, viewer = FORGE-Δ).
const backendPayload = {
  turn_number: 0,
  phase: 'assemble',
  active_player: 'me',
  active_player_id: 'cd93433b',
  first_turn: true,
  deathclock_active: false,
  deathclock_turn: 0,
  player: {
    workshop_integrity: 25,
    compute_pool: 4,
    compute_cap: 10,
    scrap_pool: 0,
    hand: [
      { id: 'h1', name: 'Ironclad Foreman', kind: 'Chassis', compute_cost: 4, power: 4, integrity: 5, hidden: false },
      { id: 'h2', name: 'Forge Stoke', kind: 'Transient', compute_cost: 1, hidden: false },
    ],
    hand_size: 7,
    library_size: 53,
    scrap_heap_size: 0,
    floor: {
      chassis: [
        {
          id: 'c1',
          name: 'Heavy Assembly',
          effective_power: 5,
          effective_integrity: 6,
          damage: 0,
          tapped: false,
          attached_parts: [
            { id: 'w1', name: 'Buzzsaw Arm', kind: 'Weapon', power_bonus: 2 },
          ],
        },
      ],
      solo_parts: [
        { id: 'p1', name: 'Spark Whip', kind: 'Weapon', effective_power: 3, effective_integrity: 1 },
      ],
    },
    structures: [],
    core: { id: 'core_me', name: 'FORGE-Δ', text: 'Chassis ≥5 integrity cost 1 less.' },
  },
  opponent: {
    workshop_integrity: 22,
    compute_pool: 0,
    compute_cap: 10,
    scrap_pool: 0,
    hand: [],
    hand_size: 7,
    library_size: 53,
    scrap_heap_size: 0,
    floor: { chassis: [], solo_parts: [] },
    structures: [],
    core: { id: 'core_opp', name: 'ETHOS-7', text: 'First Transient costs 1 less.' },
  },
};

describe('projectClankersState', () => {
  it('renames active_player → active_seat', () => {
    const s = projectClankersState({ ...backendPayload });
    expect(s.active_seat).toBe('me');
    const opp = projectClankersState({ ...backendPayload, active_player: 'opponent' });
    expect(opp.active_seat).toBe('opponent');
  });

  it('nests deathclock_active/turn into a single deathclock object', () => {
    const s = projectClankersState({ ...backendPayload, deathclock_active: true, deathclock_turn: 3 });
    expect(s.deathclock).toEqual({ active: true, turn: 3, next_damage: 8 });
  });

  it('defaults next_damage to ≥2 even when deathclock_turn is 0', () => {
    const s = projectClankersState(backendPayload);
    expect(s.deathclock.next_damage).toBe(2);
  });

  it('flattens player.floor {chassis, solo_parts} into assembly_floor[]', () => {
    const s = projectClankersState(backendPayload);
    expect(s.player.assembly_floor).toHaveLength(2);
    expect(s.player.assembly_floor[0].name).toBe('Heavy Assembly');
    expect(s.player.assembly_floor[1].name).toBe('Spark Whip');
  });

  it('prefers effective_power/integrity over base power/integrity on floor cards', () => {
    const s = projectClankersState(backendPayload);
    const heavy = s.player.assembly_floor[0];
    expect(heavy.power).toBe(5);     // effective, not base
    expect(heavy.integrity).toBe(6);
  });

  it('projects attached parts via attachments[]', () => {
    const s = projectClankersState(backendPayload);
    const heavy = s.player.assembly_floor[0];
    expect(heavy.attachments).toHaveLength(1);
    expect(heavy.attachments?.[0].name).toBe('Buzzsaw Arm');
    expect(heavy.attachments?.[0].card_type).toBe('CLANKERS_WEAPON');
  });

  it('maps kind strings to ClankersCardType', () => {
    const s = projectClankersState(backendPayload);
    expect(s.player.hand[0].card_type).toBe('CLANKERS_CHASSIS');
    expect(s.player.hand[1].card_type).toBe('CLANKERS_TRANSIENT');
  });

  it('synthesizes core, display_name, workshop_integrity_max from backend player', () => {
    const s = projectClankersState(backendPayload);
    expect(s.player.core.name).toBe('FORGE-Δ');
    expect(s.player.display_name).toBe('You');
    expect(s.opponent.display_name).toBe('Opponent');
    expect(s.player.workshop_integrity_max).toBeGreaterThanOrEqual(s.player.workshop_integrity);
  });

  it('stubs combat/refill_prompt/game_over/winner so the board does not crash', () => {
    const s = projectClankersState(backendPayload);
    expect(s.combat).toEqual({ active: false, attackers: [], blocks: {} });
    expect(s.refill_prompt.target).toBe(7);
    expect(s.game_over).toBe(false);
    expect(s.winner).toBeNull();
  });

  it('survives a totally empty payload without throwing', () => {
    expect(() => projectClankersState({})).not.toThrow();
    const s = projectClankersState({});
    expect(s.active_seat).toBe('me');
    expect(s.deathclock.active).toBe(false);
    expect(s.player.assembly_floor).toEqual([]);
  });
});
