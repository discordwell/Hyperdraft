/**
 * RulesDiff — HD-CRIT-20 lab inspector.
 *
 * Side-by-side rules inspector: pick any two engines + any event, see what
 * fires on each side as the event flows through `Event → TRANSFORM → PREVENT
 * → RESOLVE → REACT`. Below the columns, a "Differences" ledger calls out
 * what's structurally distinct between the two engines for the picked event.
 *
 * Data sourcing strategy:
 *   - MTG / Hearthstone / Pokémon / Yu-Gi-Oh entries for TURN_START / DAMAGE
 *     / ZONE_CHANGE are hand-curated from `src/engine/{turn,hearthstone_turn,
 *     pokemon_turn,yugioh_turn,pipeline/handlers/*}.py`. Each interceptor line
 *     names a real handler / step that the corresponding engine module emits
 *     or registers.
 *   - The four remaining engines (Minecraft, Finance, Depths, SCP) ship in
 *     the picker but have empty datasets — they render an "instrumentation
 *     pending" caption rather than fake interceptor names, so the diff stays
 *     honest as those engines mature.
 *
 * Hover an interceptor line on either side: any same-name counterpart on the
 * opposite side highlights in sodium so structural parallels read at a
 * glance (e.g. the DAMAGE pipeline's `damage` handler matches across MTG /
 * HS / PKM / YGO; the TURN_START `draw` step matches everywhere except MTG
 * turn-1-going-first).
 */

import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { GAME_MODES, type GameModeId } from '../components/brand';
import { getLabEngine } from '../components/lab/engineMeta';
import { Ledger, type LedgerRow } from '../components/lab/Ledger';

// === Public type — exported so other tooling could feed live data later. ==

export type RulesDiffStage = 'transform' | 'prevent' | 'resolve' | 'react';

export interface RulesDiffEntry {
  engine: GameModeId;
  event: string;
  interceptors: Array<{
    name: string;
    stage: RulesDiffStage;
    what: string;
  }>;
}

// === Curated dataset =====================================================
//
// Each entry below is read from the engine source files referenced in the
// comment. Stage assignments follow the pipeline names used by
// `src/engine/pipeline/core.py`: TRANSFORM rewrites the event in flight,
// PREVENT short-circuits resolution, RESOLVE mutates state, REACT emits
// follow-up events.

const DATA: RulesDiffEntry[] = [
  // ─── TURN_START ──────────────────────────────────────────────────────
  // src/engine/turn.py — MTG TurnManager.run_turn calls _emit_turn_start
  // then _run_beginning_phase (untap → upkeep → draw) before main.
  {
    engine: 'mtg',
    event: 'TURN_START',
    interceptors: [
      {
        name: 'until_next_turn_cleanup',
        stage: 'transform',
        what: 'Sweeps "until your next turn" grants whose owner is the new active player before TURN_START fires.',
      },
      {
        name: 'turn_state_tracker',
        stage: 'react',
        what: 'SYSTEM REACT — clears land_played, lands_played_count, skip_combat / skip_untap / skip_draw flags.',
      },
      {
        name: 'untap_step',
        stage: 'resolve',
        what: 'Emits an UNTAP event per tapped permanent the active player controls (skipped if turn_state.skip_untap).',
      },
      {
        name: 'upkeep_triggers',
        stage: 'react',
        what: 'Fires every `at_beginning_of_upkeep` interceptor registered by cards in play (e.g. Phyrexian Arena, sagas).',
      },
      {
        name: 'draw_step',
        stage: 'resolve',
        what: 'Emits DRAW(count=draw_step_cards). Skipped for the going-first player on turn 1.',
      },
      {
        name: 'priority_loop',
        stage: 'react',
        what: 'Opens a priority window — active player first, then non-active. Instants / triggered abilities resolve here.',
      },
    ],
  },

  // src/engine/hearthstone_turn.py — HearthstoneTurnManager.run_turn emits
  // TURN_START then _run_draw_phase (mana crystal → refill → hero power
  // reset → unfreeze → draw or fatigue).
  {
    engine: 'hearthstone',
    event: 'TURN_START',
    interceptors: [
      {
        name: 'mana_crystal_gain',
        stage: 'resolve',
        what: 'Active player gains 1 mana crystal (capped at 10) and refills to the new max — Hearthstone\'s ramp model.',
      },
      {
        name: 'hero_power_reset',
        stage: 'resolve',
        what: 'Clears the once-per-turn hero-power usage flag so the player can re-tap their power this turn.',
      },
      {
        name: 'unfreeze_check',
        stage: 'transform',
        what: 'Unfreezes friendly characters that did NOT attack while frozen — Water Elemental-style freeze persists otherwise.',
      },
      {
        name: 'reset_combat',
        stage: 'react',
        what: 'Resets attacks_this_turn / charge / windfury state for the active player\'s minions.',
      },
      {
        name: 'draw_step',
        stage: 'resolve',
        what: 'Emits DRAW(count=1). Empty deck = increment fatigue, deal escalating self-damage instead.',
      },
      {
        name: 'turn_start_triggers',
        stage: 'react',
        what: 'Battlecry-equivalent start-of-turn triggers fire (e.g. Brewmaster, Coldlight Oracle on enter).',
      },
    ],
  },

  // src/engine/pokemon_turn.py — PokemonTurnManager.run_turn emits
  // TURN_START then _run_draw_phase (single card, deck-out = lose).
  {
    engine: 'pokemon',
    event: 'TURN_START',
    interceptors: [
      {
        name: 'reset_turn_flags',
        stage: 'react',
        what: 'Clears energy_attached_this_turn / retreat_this_turn / supporter_played_this_turn for the active player.',
      },
      {
        name: 'draw_step',
        stage: 'resolve',
        what: 'Draw 1. Empty deck → PLAYER_LOSES(reason="deck_out"). Going-first player skips on game-turn 1.',
      },
      {
        name: 'status_no_act',
        stage: 'prevent',
        what: 'Asleep / Paralyzed active Pokémon cannot attack this turn — those actions are removed from legal moves.',
      },
      {
        name: 'between_turns_skip',
        stage: 'transform',
        what: 'Pokémon has no upkeep — checkup runs between turns, not at TURN_START.',
      },
    ],
  },

  // src/engine/yugioh_turn.py — YugiohTurnManager.run_turn appends
  // TURN_START, then DRAW (skipped on game_turn 1), then STANDBY.
  {
    engine: 'yugioh',
    event: 'TURN_START',
    interceptors: [
      {
        name: 'increment_set_turns',
        stage: 'transform',
        what: 'Increments turns_set counter on every set spell/trap — chain-triggered traps need this for activation legality.',
      },
      {
        name: 'reset_per_turn',
        stage: 'react',
        what: 'Clears normal_summon_used, battle_phase_entered, position_changes, attacks_declared.',
      },
      {
        name: 'draw_step',
        stage: 'resolve',
        what: 'Draw 1 card. Going-first player skips draw on game-turn 1 (Yu-Gi-Oh\'s starting-hand parity rule).',
      },
      {
        name: 'standby_phase',
        stage: 'react',
        what: 'PHASE_START(phase="standby") opens a chain window for upkeep traps before Main Phase 1.',
      },
    ],
  },

  // ─── DAMAGE ──────────────────────────────────────────────────────────
  // src/engine/pipeline/handlers/damage.py — _handle_damage routes through
  // mode_adapter for player damage / hero damage / creature damage.
  {
    engine: 'mtg',
    event: 'DAMAGE',
    interceptors: [
      {
        name: 'replacement_effects',
        stage: 'transform',
        what: 'Pre-damage rewrite — "if damage would be dealt" replacement effects (e.g. Stuffy Doll redirect) fire here.',
      },
      {
        name: 'prevention_shields',
        stage: 'prevent',
        what: 'Prevention effects ("the next X damage that would be dealt is prevented") short-circuit before _handle_damage.',
      },
      {
        name: 'apply_player_damage',
        stage: 'resolve',
        what: 'mode_adapter.apply_player_damage — life loss, no armor model. MTG has no concept of armor.',
      },
      {
        name: 'creature_marks_damage',
        stage: 'resolve',
        what: 'obj.state.damage += amount. State-based actions later destroy if damage ≥ toughness.',
      },
      {
        name: 'damage_triggers',
        stage: 'react',
        what: 'Fires `damage_dealt` triggers (lifelink → LIFE_CHANGE, deathtouch → marker, infect → -1/-1 counters).',
      },
    ],
  },

  {
    engine: 'hearthstone',
    event: 'DAMAGE',
    interceptors: [
      {
        name: 'divine_shield',
        stage: 'prevent',
        what: 'Divine Shield PREVENT interceptor registered in Game.__init__ — absorbs the first damage event entirely.',
      },
      {
        name: 'armor_absorb',
        stage: 'transform',
        what: 'Hero damage subtracts from player.armor first; only the remainder reaches player.life.',
      },
      {
        name: 'apply_hero_damage',
        stage: 'resolve',
        what: 'mode_adapter.apply_hero_damage — also syncs hero.state.damage so the board UI shows the hero portrait HP.',
      },
      {
        name: 'minion_marks_damage',
        stage: 'resolve',
        what: 'obj.state.damage += amount, then post_creature_damage_destroy_check runs spell-damage-lethal destruction synchronously.',
      },
      {
        name: 'enrage_recheck',
        stage: 'react',
        what: 'Enrage / damaged-trigger interceptors re-evaluate their PT_MODIFICATION (Frothing Berserker, Spiteful Smith).',
      },
    ],
  },

  {
    engine: 'pokemon',
    event: 'DAMAGE',
    interceptors: [
      {
        name: 'weakness_resistance',
        stage: 'transform',
        what: 'PokemonCombatManager doubles damage on weakness (×2), subtracts on resistance (-30) BEFORE handler runs.',
      },
      {
        name: 'protection_orb',
        stage: 'prevent',
        what: 'Effect-prevent attachments (Bright Powder, Focus Sash, Cape of Toughness) prevent damage before resolve.',
      },
      {
        name: 'apply_pokemon_damage',
        stage: 'resolve',
        what: 'Damage counters placed on the active / benched Pokémon. No armor / life pool — HP is per-card.',
      },
      {
        name: 'ko_check',
        stage: 'react',
        what: 'If damage ≥ HP, _check_pokemon_knockouts moves the card to discard and awards a Prize card to the attacker.',
      },
    ],
  },

  {
    engine: 'yugioh',
    event: 'DAMAGE',
    interceptors: [
      {
        name: 'battle_damage_calc',
        stage: 'transform',
        what: 'YugiohCombatManager resolves ATK vs DEF / ATK vs ATK BEFORE emitting DAMAGE — the event already carries the delta.',
      },
      {
        name: 'trap_window',
        stage: 'prevent',
        what: 'Opens a chain window — Negate Attack / Magic Cylinder / Mirror Force trigger as PREVENT interceptors here.',
      },
      {
        name: 'apply_life_damage',
        stage: 'resolve',
        what: 'Life points decrement directly. Yu-Gi-Oh has no hero object — damage targets the player, monsters just get destroyed.',
      },
      {
        name: 'send_to_graveyard',
        stage: 'react',
        what: 'Defeated monster\'s ZONE_CHANGE(field → graveyard) fires here. Trigger traps (Sangan, Tribe-Infecting Virus) react.',
      },
    ],
  },

  // ─── ZONE_CHANGE ─────────────────────────────────────────────────────
  // src/engine/pipeline/handlers/zone.py — _handle_zone_change at line 311.
  {
    engine: 'mtg',
    event: 'ZONE_CHANGE',
    interceptors: [
      {
        name: 'destination_rewrite',
        stage: 'transform',
        what: 'Replacement effects (Rest in Peace, Leyline of the Void) rewrite destination — e.g. graveyard → exile.',
      },
      {
        name: 'leaves_battlefield_capture',
        stage: 'transform',
        what: 'Snapshots last-known-information for cards leaving the battlefield so their triggers see the right state.',
      },
      {
        name: 'cleanup_departed_interceptors',
        stage: 'resolve',
        what: 'Removes static / triggered interceptors registered by the departing object via obj.interceptor_ids.',
      },
      {
        name: 'etb_triggers',
        stage: 'react',
        what: 'On battlefield entry, runs setup_interceptors → fires `make_etb_trigger` lines (Mulldrifter, Snapcaster, etc).',
      },
      {
        name: 'dies_triggers',
        stage: 'react',
        what: 'On graveyard entry from battlefield, fires `make_death_trigger` and `leaves_battlefield` interceptors.',
      },
    ],
  },

  {
    engine: 'hearthstone',
    event: 'ZONE_CHANGE',
    interceptors: [
      {
        name: 'deathrattle_sequencing',
        stage: 'transform',
        what: 'HS resolves deathrattles in order of play — interceptors capture obj.id at move time, not at trigger time.',
      },
      {
        name: 'hand_size_cap',
        stage: 'prevent',
        what: 'Library → Hand on a full (10-card) hand burns the card to graveyard instead. PREVENT-rewrites to BURN.',
      },
      {
        name: 'battlecry_fire',
        stage: 'react',
        what: 'Hand → battlefield triggers the card\'s battlecry function — wired via make_minion(battlecry=fn).',
      },
      {
        name: 'deathrattle_fire',
        stage: 'react',
        what: 'Battlefield → graveyard triggers the deathrattle function (multiplied by Baron Rivendare-style auras).',
      },
      {
        name: 'reborn_redo',
        stage: 'react',
        what: 'Reborn keyword — on first death, re-emits ZONE_CHANGE back to battlefield with 1 HP.',
      },
    ],
  },

  {
    engine: 'pokemon',
    event: 'ZONE_CHANGE',
    interceptors: [
      {
        name: 'attached_energy_followthrough',
        stage: 'transform',
        what: 'When a Pokémon is KO\'d, all attached Energy / Tools go to discard simultaneously — payload carries the dependents.',
      },
      {
        name: 'prize_award',
        stage: 'react',
        what: 'Battlefield → discard (KO) hands the opponent 1 prize card (2 for ex, 3 for VMAX). Updates player.prizes_remaining.',
      },
      {
        name: 'forced_promotion',
        stage: 'react',
        what: 'If the active Pokémon was KO\'d, the controller must promote a benched Pokémon before the next turn starts.',
      },
    ],
  },

  {
    engine: 'yugioh',
    event: 'ZONE_CHANGE',
    interceptors: [
      {
        name: 'flip_effect_trigger',
        stage: 'transform',
        what: 'Face-down → face-up zone change activates flip effects (Man-Eater Bug, Penguin Soldier) as the first chain link.',
      },
      {
        name: 'graveyard_triggers',
        stage: 'react',
        what: 'Field → graveyard fires `setup_in_graveyard` interceptors (Sangan, Witch of the Black Forest tutor effects).',
      },
      {
        name: 'extra_deck_return',
        stage: 'react',
        what: 'Fusion / Synchro / Xyz monsters in the graveyard return to the extra deck when sent from anywhere except field.',
      },
    ],
  },
];

// Engines that are pickable but not yet instrumented — keeping them in the
// picker (and showing a clean "no data" caption) is more honest than padding
// the dataset with invented interceptor names.
const INSTRUMENTED: ReadonlySet<GameModeId> = new Set<GameModeId>([
  'mtg',
  'hearthstone',
  'pokemon',
  'yugioh',
]);

const EVENTS = ['TURN_START', 'DAMAGE', 'ZONE_CHANGE'] as const;
type EventName = (typeof EVENTS)[number];

// Per-event differences ledger — handwritten because the divergences cross
// multiple files and aren't trivially queryable. Keys are the two engines
// joined with `__`, alphabetically. Add more pairs as the picker matures.
const DIFFERENCES: Record<EventName, Array<[GameModeId, GameModeId, string, string]>> = {
  TURN_START: [
    ['mtg', 'hearthstone',
      'Untap step',
      'MTG: every tapped permanent gets a discrete UNTAP event. HS has no tapped/untapped state — minions are eligible-to-attack as a flag, refreshed by reset_combat.'],
    ['mtg', 'hearthstone',
      'Mana economy',
      'MTG: untap → tap-for-mana on demand. HS: gain crystal + refill, all at TURN_START. The HS player\'s mana max IS their turn count.'],
    ['mtg', 'hearthstone',
      'Priority window',
      'MTG: priority opens during upkeep and after each step — instants resolve via stack. HS: no priority window during start — only between actions, and only via Secrets.'],
    ['mtg', 'pokemon',
      'Draw rule',
      'MTG: draw_step_cards (default 1) on every turn except going-first turn 1. Pokémon: also 1, also skipped on turn 1, but deck-out at TURN_START is an instant loss instead of fatigue damage.'],
    ['hearthstone', 'yugioh',
      'Per-turn reset',
      'HS resets attacks_this_turn / freeze. YGO resets normal_summon_used + position_changes + attacks_declared. Both share a per-turn-flags pattern but track different per-card limits.'],
    ['pokemon', 'yugioh',
      'Upkeep semantics',
      'Pokémon has no upkeep — checkup runs between turns. YGO has an explicit STANDBY phase that opens a chain window before Main Phase 1.'],
  ],
  DAMAGE: [
    ['mtg', 'hearthstone',
      'Hero vs face',
      'MTG: player damage decrements life directly. HS: hero damage goes through armor first, then life; the hero object also syncs damage so the board UI shows portrait HP.'],
    ['mtg', 'hearthstone',
      'Divine Shield',
      'HS Divine Shield is a PREVENT interceptor that absorbs the entire damage event. MTG has no equivalent — the closest is "X damage is prevented" replacement effects, which scale numerically.'],
    ['mtg', 'pokemon',
      'Weakness / Resistance',
      'Pokémon multiplies / subtracts damage in the combat manager BEFORE emitting DAMAGE. MTG has no type-based modifier — damage is a flat number.'],
    ['hearthstone', 'pokemon',
      'Lethal check timing',
      'HS post_creature_damage_destroy_check runs synchronously during DAMAGE for spell damage. Pokémon KO check waits until after the attack fully resolves, then awards prizes.'],
    ['mtg', 'yugioh',
      'Combat math location',
      'MTG combat assigns damage during the combat damage step, multiple combatants at once. YGO YugiohCombatManager computes ATK-vs-DEF before emitting DAMAGE — the event carries the final delta.'],
  ],
  ZONE_CHANGE: [
    ['mtg', 'hearthstone',
      'Battlecry vs ETB',
      'MTG: ETB triggers go on the stack and can be countered. HS battlecries resolve immediately as part of the play, cannot be interrupted.'],
    ['mtg', 'hearthstone',
      'Hand overflow',
      'HS PREVENTs library→hand at 10 cards by rewriting to BURN. MTG has no hand-cap on draw — only a discard-to-7 at cleanup step.'],
    ['mtg', 'pokemon',
      'Death payload',
      'MTG: card to graveyard is a single ZONE_CHANGE. Pokémon KO sends the Pokémon AND its attached Energy / Tools simultaneously — one event carries multiple dependents.'],
    ['hearthstone', 'yugioh',
      'Reborn vs flip',
      'HS reborn re-emits ZONE_CHANGE back to battlefield as a REACT. YGO flip is the opposite — a face-down → face-up TRANSFORM that activates a flip effect as the first chain link.'],
    ['pokemon', 'yugioh',
      'Prize vs life',
      'Pokémon prize award is the win condition (take 6). YGO graveyard transitions trigger card effects (Sangan tutor) but don\'t advance a win track — life points do.'],
  ],
};

// === Component ===========================================================

function findEntry(engine: GameModeId, event: EventName): RulesDiffEntry | undefined {
  return DATA.find((e) => e.engine === engine && e.event === event);
}

function findDifferences(a: GameModeId, b: GameModeId, event: EventName): string[][] {
  if (a === b) return [];
  const rows = DIFFERENCES[event] ?? [];
  const matches: string[][] = [];
  for (const [x, y, k, v] of rows) {
    if ((x === a && y === b) || (x === b && y === a)) {
      matches.push([k, v]);
    }
  }
  return matches;
}

function stageTone(stage: RulesDiffStage): string {
  switch (stage) {
    case 'transform':
      return 'var(--sodium)';
    case 'prevent':
      return 'var(--halt)';
    case 'resolve':
      return 'var(--plasma)';
    case 'react':
      return 'var(--acid)';
  }
}

export function RulesDiff() {
  const navigate = useNavigate();
  const [engineA, setEngineA] = useState<GameModeId>('mtg');
  const [engineB, setEngineB] = useState<GameModeId>('hearthstone');
  const [event, setEvent] = useState<EventName>('TURN_START');
  const [hoverName, setHoverName] = useState<string | null>(null);

  const entryA = useMemo(() => findEntry(engineA, event), [engineA, event]);
  const entryB = useMemo(() => findEntry(engineB, event), [engineB, event]);

  const diffRows: LedgerRow[] = useMemo(() => {
    const matches = findDifferences(engineA, engineB, event);
    return matches.map(([k, v], i) => ({
      n: String(i + 1).padStart(2, '0'),
      k,
      v,
    }));
  }, [engineA, engineB, event]);

  return (
    <div style={{ background: 'var(--paper)', color: 'var(--ink)', minHeight: '100vh' }}>
      {/* ─── Caption rail ──────────────────────────────────────────────── */}
      <div
        style={{
          position: 'fixed',
          top: 14,
          left: '50%',
          transform: 'translateX(-50%)',
          fontFamily: 'var(--font-mono)',
          fontSize: 10.5,
          letterSpacing: '.14em',
          textTransform: 'uppercase',
          color: 'var(--ink-3)',
          background: 'var(--paper)',
          padding: '6px 14px',
          border: '1px solid var(--rule)',
          zIndex: 10,
        }}
      >
        <b style={{ color: 'var(--ink)', fontWeight: 500 }}>HD-RULES-DIFF</b>
        &nbsp;·&nbsp; Engine vs engine inspector
      </div>

      <main
        style={{
          maxWidth: 1240,
          margin: '0 auto',
          padding: '88px 56px 160px',
          position: 'relative',
        }}
      >
        {/* ─── Masthead ────────────────────────────────────────────────── */}
        <header
          style={{
            display: 'grid',
            gridTemplateColumns: '1fr auto',
            alignItems: 'end',
            borderTop: '1.5px solid var(--ink)',
            borderBottom: '1.5px solid var(--ink)',
            padding: '18px 0 22px',
            marginBottom: 32,
          }}
        >
          <span
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 12,
              fontWeight: 500,
              letterSpacing: '.12em',
              textTransform: 'uppercase',
              color: 'var(--ink-2)',
            }}
          >
            HYPERDRAFT
          </span>
          <button
            onClick={() => navigate('/')}
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 11,
              fontWeight: 500,
              letterSpacing: '.1em',
              textTransform: 'uppercase',
              background: 'transparent',
              border: 'none',
              color: 'var(--ink-2)',
              cursor: 'pointer',
            }}
          >
            ← Home
          </button>
        </header>

        <section style={{ marginBottom: 24 }}>
          <span className="lab-chip">
            <span className="dot" />
            BIG MOVE 20 · the inspector
          </span>
          <h1
            style={{
              margin: '14px 0 0',
              fontFamily: 'var(--font-serif)',
              fontSize: 'clamp(54px, 7.5vw, 88px)',
              fontWeight: 400,
              lineHeight: 0.95,
              letterSpacing: '-.025em',
              color: 'var(--ink)',
            }}
          >
            Rules{' '}
            <em style={{ color: 'var(--sodium)', fontStyle: 'italic' }}>diff.</em>
          </h1>
          <p
            style={{
              margin: '14px 0 0',
              fontFamily: 'var(--font-serif)',
              fontSize: 18,
              fontStyle: 'italic',
              lineHeight: 1.5,
              color: 'var(--ink-2)',
              maxWidth: '54ch',
            }}
          >
            Two engines, one event. What fires, in what order, against what state.
            This is the page that makes the multi-engine premise sing.
          </p>
        </section>

        {/* ─── Pickers ─────────────────────────────────────────────────── */}
        <section
          style={{
            display: 'grid',
            gap: 18,
            gridTemplateColumns: '1fr 1fr 1fr',
            margin: '40px 0 28px',
            paddingTop: 24,
            borderTop: '1px solid var(--rule)',
          }}
          aria-label="diff pickers"
        >
          <PickerGroup
            label="Engine A"
            value={engineA}
            options={GAME_MODES.map((m) => ({
              value: m.id,
              label: m.name,
              disabled: !INSTRUMENTED.has(m.id),
            }))}
            onChange={(v) => setEngineA(v as GameModeId)}
          />
          <PickerGroup
            label="Engine B"
            value={engineB}
            options={GAME_MODES.map((m) => ({
              value: m.id,
              label: m.name,
              disabled: !INSTRUMENTED.has(m.id),
            }))}
            onChange={(v) => setEngineB(v as GameModeId)}
          />
          <PickerGroup
            label="Event type"
            value={event}
            options={EVENTS.map((e) => ({ value: e, label: e, disabled: false }))}
            onChange={(v) => setEvent(v as EventName)}
          />
        </section>

        {/* ─── Diff columns ────────────────────────────────────────────── */}
        <section
          style={{
            display: 'grid',
            gap: 0,
            gridTemplateColumns: '1fr 1fr',
            border: '1px solid var(--rule)',
            background: 'var(--paper-2)',
            marginBottom: 36,
          }}
          aria-label="diff columns"
        >
          <EngineColumn
            engine={engineA}
            event={event}
            entry={entryA}
            hoverName={hoverName}
            setHoverName={setHoverName}
            side="left"
          />
          <EngineColumn
            engine={engineB}
            event={event}
            entry={entryB}
            hoverName={hoverName}
            setHoverName={setHoverName}
            side="right"
          />
        </section>

        {/* ─── Differences ledger ──────────────────────────────────────── */}
        <section>
          <div
            style={{
              display: 'flex',
              alignItems: 'baseline',
              justifyContent: 'space-between',
              borderBottom: '1px solid var(--rule)',
              padding: '0 0 12px',
              marginBottom: 12,
            }}
          >
            <h2
              style={{
                margin: 0,
                fontFamily: 'var(--font-serif)',
                fontSize: 26,
                fontWeight: 400,
                letterSpacing: '-.015em',
              }}
            >
              Differences
            </h2>
            <span
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: 11,
                letterSpacing: '.12em',
                textTransform: 'uppercase',
                color: 'var(--ink-3)',
              }}
            >
              {diffRows.length} divergence{diffRows.length === 1 ? '' : 's'}
            </span>
          </div>
          {diffRows.length > 0 ? (
            <Ledger rows={diffRows} />
          ) : (
            <div
              style={{
                fontFamily: 'var(--font-sans)',
                fontSize: 13,
                color: 'var(--ink-2)',
                padding: '16px 18px',
                border: '1px dashed var(--rule)',
                background: 'var(--paper)',
              }}
            >
              {engineA === engineB
                ? 'Pick two different engines to see the divergence ledger.'
                : 'No curated differences yet for this engine pair on this event. Both columns above are the source of truth.'}
            </div>
          )}
        </section>

        {/* ─── Legend ──────────────────────────────────────────────────── */}
        <section
          style={{
            marginTop: 40,
            paddingTop: 20,
            borderTop: '1px solid var(--rule)',
            display: 'flex',
            gap: 18,
            flexWrap: 'wrap',
            fontFamily: 'var(--font-mono)',
            fontSize: 10.5,
            letterSpacing: '.1em',
            textTransform: 'uppercase',
            color: 'var(--ink-3)',
          }}
        >
          <StageLegend stage="transform" />
          <StageLegend stage="prevent" />
          <StageLegend stage="resolve" />
          <StageLegend stage="react" />
          <span style={{ marginLeft: 'auto', color: 'var(--ink-3)' }}>
            Pipeline: Event → TRANSFORM → PREVENT → RESOLVE → REACT
          </span>
        </section>

        {/* ─── Footer ──────────────────────────────────────────────────── */}
        <footer
          style={{
            marginTop: 60,
            paddingTop: 22,
            borderTop: '1.5px solid var(--ink)',
            display: 'flex',
            justifyContent: 'space-between',
            flexWrap: 'wrap',
            gap: 14,
            fontFamily: 'var(--font-mono)',
            fontSize: 11,
            color: 'var(--ink-3)',
            letterSpacing: '.06em',
          }}
        >
          <span>src/engine/{`{turn,hearthstone_turn,pokemon_turn,yugioh_turn,pipeline}`}.py</span>
          <span style={{ letterSpacing: '.1em', textTransform: 'uppercase' }}>
            HD-CRIT-20 — engine vs engine
          </span>
        </footer>
      </main>
    </div>
  );
}

// === Pieces ==============================================================

function PickerGroup({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: Array<{ value: string; label: string; disabled: boolean }>;
  onChange: (v: string) => void;
}) {
  return (
    <div>
      <div
        style={{
          fontFamily: 'var(--font-mono)',
          fontSize: 10.5,
          fontWeight: 500,
          letterSpacing: '.14em',
          textTransform: 'uppercase',
          color: 'var(--ink-3)',
          marginBottom: 10,
        }}
      >
        {label}
      </div>
      <div
        role="group"
        aria-label={label}
        style={{
          display: 'grid',
          gap: 6,
          gridTemplateColumns: options.length > 4 ? 'repeat(4, 1fr)' : `repeat(${options.length}, 1fr)`,
        }}
      >
        {options.map((o) => {
          const active = o.value === value;
          return (
            <button
              key={o.value}
              onClick={() => !o.disabled && onChange(o.value)}
              disabled={o.disabled}
              aria-pressed={active}
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: 10.5,
                fontWeight: 500,
                letterSpacing: '.12em',
                textTransform: 'uppercase',
                padding: '8px 8px',
                background: active ? 'var(--ink)' : 'var(--paper)',
                color: active
                  ? 'var(--paper)'
                  : o.disabled
                  ? 'var(--ink-3)'
                  : 'var(--ink-2)',
                border: `1px solid ${active ? 'var(--ink)' : 'var(--rule)'}`,
                cursor: o.disabled ? 'not-allowed' : 'pointer',
                opacity: o.disabled ? 0.5 : 1,
              }}
              title={o.disabled ? 'Instrumentation pending — see source file note in component header.' : undefined}
            >
              {o.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function EngineColumn({
  engine,
  event,
  entry,
  hoverName,
  setHoverName,
  side,
}: {
  engine: GameModeId;
  event: EventName;
  entry: RulesDiffEntry | undefined;
  hoverName: string | null;
  setHoverName: (n: string | null) => void;
  side: 'left' | 'right';
}) {
  const meta = getLabEngine(engine);
  return (
    <div
      style={{
        padding: '24px 26px',
        borderRight: side === 'left' ? '1px solid var(--rule)' : 'none',
        background: 'var(--paper-2)',
        minHeight: 320,
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'baseline',
          justifyContent: 'space-between',
          paddingBottom: 14,
          marginBottom: 16,
          borderBottom: '1px solid var(--rule)',
        }}
      >
        <div>
          <div
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 10.5,
              letterSpacing: '.14em',
              textTransform: 'uppercase',
              color: 'var(--ink-3)',
              marginBottom: 4,
            }}
          >
            {meta?.ix ?? ''}
            <span style={{ marginLeft: 6 }}>· {event}</span>
          </div>
          <h3
            style={{
              margin: 0,
              fontFamily: 'var(--font-serif)',
              fontSize: 26,
              fontWeight: 400,
              letterSpacing: '-.015em',
              color: 'var(--ink)',
            }}
          >
            {meta?.name ?? engine}
          </h3>
        </div>
        <span
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 11,
            letterSpacing: '.08em',
            color: 'var(--ink-3)',
          }}
        >
          {entry?.interceptors.length ?? 0} fire{(entry?.interceptors.length ?? 0) === 1 ? 's' : ''}
        </span>
      </div>

      {entry && entry.interceptors.length > 0 ? (
        <ul style={{ margin: 0, padding: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 14 }}>
          {entry.interceptors.map((it) => {
            const matched = hoverName !== null && hoverName === it.name;
            return (
              <li
                key={`${engine}-${it.name}`}
                onMouseEnter={() => setHoverName(it.name)}
                onMouseLeave={() => setHoverName(null)}
                data-interceptor={it.name}
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'auto 1fr',
                  gap: 12,
                  paddingBottom: 12,
                  borderBottom: '1px solid var(--rule-2)',
                  background: matched ? 'color-mix(in oklab, var(--sodium) 8%, transparent)' : 'transparent',
                  padding: '6px 8px 12px',
                  marginLeft: -8,
                  marginRight: -8,
                  borderRadius: 2,
                  transition: 'background 80ms ease-out',
                }}
              >
                <StageBadge stage={it.stage} />
                <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                  <span
                    style={{
                      fontFamily: 'var(--font-mono)',
                      fontSize: 13,
                      color: 'var(--ink)',
                      letterSpacing: '-.005em',
                    }}
                  >
                    {it.name}
                  </span>
                  <span
                    style={{
                      fontFamily: 'var(--font-sans)',
                      fontSize: 13,
                      color: 'var(--ink-2)',
                      lineHeight: 1.5,
                    }}
                  >
                    {it.what}
                  </span>
                </div>
              </li>
            );
          })}
        </ul>
      ) : (
        <div
          style={{
            fontFamily: 'var(--font-sans)',
            fontSize: 13,
            color: 'var(--ink-3)',
            fontStyle: 'italic',
            padding: '20px 4px',
          }}
        >
          {INSTRUMENTED.has(engine)
            ? `No interceptors curated for ${event} on this engine yet.`
            : `Instrumentation pending — this engine’s ${event} pipeline isn’t yet mirrored into the rules-diff dataset.`}
        </div>
      )}
    </div>
  );
}

function StageBadge({ stage }: { stage: RulesDiffStage }) {
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        height: 22,
        padding: '0 8px',
        fontFamily: 'var(--font-mono)',
        fontSize: 9.5,
        fontWeight: 500,
        letterSpacing: '.14em',
        textTransform: 'uppercase',
        color: 'var(--paper)',
        background: stageTone(stage),
        whiteSpace: 'nowrap',
        alignSelf: 'start',
      }}
    >
      {stage}
    </span>
  );
}

function StageLegend({ stage }: { stage: RulesDiffStage }) {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
      <span
        style={{
          width: 10,
          height: 10,
          background: stageTone(stage),
        }}
      />
      {stage}
    </span>
  );
}

export default RulesDiff;
