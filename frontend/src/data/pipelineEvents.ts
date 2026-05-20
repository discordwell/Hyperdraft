/**
 * Pipeline-the-Game v0.1 event deck — HD-CRIT-002 §06.
 *
 * Each turn, one Event drops at center-board. Both players slot interceptors
 * into the four stages to handle it. Events here are realistic
 * `EventType.*` instances flattened to a single shape the prototype consumes
 * directly; the backend manager will eventually emit them from
 * `src/engine/types.py` enums.
 */

export interface PipelineEventDef {
  id: string;
  /** EventType-like family. */
  type: string;
  /** Player-facing title. */
  name: string;
  /** One-line payload summary, mono-styled below the title. */
  payload: string;
}

export const PIPELINE_EVENT_DECK: PipelineEventDef[] = [
  { id: 'e-dmg-3',       type: 'DAMAGE',       name: 'A creature deals 3 damage to a player.',   payload: 'amount: 3 · source: red_creature_07 · target: player_b' },
  { id: 'e-life-2',      type: 'LIFE_CHANGE',  name: 'A player gains 2 life.',                    payload: 'amount: 2 · player: player_a · source: cleric_03' },
  { id: 'e-zone-grave',  type: 'ZONE_CHANGE',  name: 'A creature dies and would enter the graveyard.', payload: 'object: wolf_02 · from: battlefield · to: graveyard' },
  { id: 'e-draw-2',      type: 'CARD_DRAW',    name: 'A player draws 2 cards.',                   payload: 'amount: 2 · player: player_a · trigger: upkeep' },
  { id: 'e-turn-start',  type: 'TURN_START',   name: 'A new turn begins.',                        payload: 'turn: 5 · active: player_a' },
  { id: 'e-etb-3-3',     type: 'ETB',          name: 'A 3/3 creature enters the battlefield.',    payload: 'object: bear_05 · controller: player_b · stats: 3/3' },
  { id: 'e-burn-7',      type: 'DAMAGE',       name: 'A burn spell would deal 7 damage to a player.', payload: 'amount: 7 · source: meteor_01 · target: player_a' },
  { id: 'e-trigger-etb', type: 'TRIGGER',      name: 'An ETB trigger looks at the top 3 cards.',  payload: 'trigger: etb_scry · source: augur_02' },
  { id: 'e-poison',      type: 'STATUS_APPLY', name: 'Apply Poisoned status to a Pokémon.',       payload: 'condition: poisoned · target: charmander_03' },
  { id: 'e-anomaly',     type: 'ANOMALY_BREACH', name: 'An anomaly breaches containment.',         payload: 'object: scp_173_token · level: keter · containment: failed' },
  { id: 'e-energy-att',  type: 'ENERGY_ATTACH', name: 'A player attaches energy to a Pokémon.',   payload: 'energy: lightning · target: pikachu_01' },
  { id: 'e-attack',      type: 'COMBAT_ATTACK', name: 'Two creatures declare an attack.',          payload: 'attackers: [wolf_02, bear_05] · target: player_a' },
  { id: 'e-counter',     type: 'CAST',         name: 'A spell is cast and goes on the stack.',    payload: 'spell: fireball_01 · cost: {4R} · controller: player_b' },
  { id: 'e-life-loss-5', type: 'LIFE_CHANGE',  name: 'A player would lose 5 life.',               payload: 'amount: -5 · player: player_a · source: burn_chain' },
];

export function rotateEvent(deck: PipelineEventDef[], turn: number): PipelineEventDef {
  return deck[turn % deck.length];
}
