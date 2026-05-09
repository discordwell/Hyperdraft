# Hyperdraft

AI-powered deckbuilder with an event-driven MTG rules engine.

## Claude Preferences

- When spawning >5 agents in a single command, ask user if they want to use `model: "sonnet"` instead of opus to reduce cost/latency.
- When following a skill and a turn uncovers bugs, gaps, or errors, instead of moving on to the next step first fix those bugs then move on.

## Architecture

**Core Philosophy**: Everything is an Event, everything else is an Interceptor.

### Event Pipeline
```
Event → TRANSFORM → PREVENT → RESOLVE → REACT
```

### Key Directories
- `src/engine/` - Core rules engine (events, interceptors, combat, mana, stack)
- `src/cards/` - Card definitions and interceptor implementations
- `src/ai/` - AI strategies (aggro, control, midrange)
- `src/server/` - FastAPI game server
- `frontend/` - React + TypeScript game client
- `tests/` - Test suites

## Implementing Cards

See `.claude/skills/implement-mtg-cards.md` for the complete guide.

### Quick Reference

```python
# Setup function pattern
def card_name_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.LIFE_CHANGE,
                      payload={'player': obj.controller, 'amount': 3},
                      source=obj.id)]
    return [make_etb_trigger(obj, effect_fn)]

# Card definition
CARD_NAME = make_creature(
    name="Card Name",
    power=3, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human"},
    text="When Card Name enters, you gain 3 life.",
    setup_interceptors=card_name_setup
)
```

### Available Helpers (interceptor_helpers.py)

Triggers / static effects:
- `make_etb_trigger`, `make_death_trigger`, `make_attack_trigger`,
  `make_damage_trigger`, `make_upkeep_trigger`, `make_end_step_trigger`,
  `make_spell_cast_trigger`, `make_leaves_battlefield_trigger`
- `make_static_pt_boost` — flat lord effect (+X/+Y)
- `make_dynamic_pt_boost` / `make_attached_dynamic_pt_boost` — "+X/+Y per
  Forest" via state-time `mod_fn`
- `make_keyword_grant` — grant keywords statically

Activated abilities (Phase 4):
- `make_activated_ability(obj, cost, effect_fn, ...)` — generic registration
- Specialised wrappers: `make_pump_self_ability`, `make_draw_ability`,
  `make_loot_ability`, `make_life_gain_ability`, `make_damage_ability`,
  `make_destroy_ability`, `make_counter_ability`,
  `make_token_creation_ability`, `make_sac_destroy_ability`

Equipment / Aura attach (Phase 3):
- `make_equipment_setup` and `make_aura_setup` accept
  `power_mod`, `toughness_mod`, `keywords`, `subtypes_to_add`,
  `equip_cost`, `ward_cost`

Set mechanics (Phase 5):
- `suspect_creature(target_id, source_id, controller, state)`
- `collect_evidence(player_id, n, state)` — greedy MV cost
- `was_bargained(state, card_name)` — read the WOE Bargain marker
- `make_room_setup(...)` + `is_door_unlocked(obj, door_name)`

Sweep helpers:
- `becomes_creature(target, state, *, power, toughness, subtypes, keywords)`
- `threaten_creature(target_id, new_controller, source_id)` — gain control + untap + haste EOT
- `grant_death_trigger(target, source, state, effect_fn, *, duration='end_of_turn')`
- `grant_triggered_ability(target, source, state, *, event_filter, effect_fn, duration, one_shot=False)`
- `make_cost_reduction(source, *, applies_to, amount, self_only=False)` — spell-cast cost reduction
- `make_ward(source, *, mana_cost=None, life_cost=None, custom_cost=None)` — ward replacement

Counts / queries:
- `count_permanents_with_subtype`, `count_permanents_of_type`,
  `count_cards_in_graveyard`, `count_cards_in_hand`

Pipeline events you may emit directly:
- `EventType.ATTACH` / `UNATTACH` (attach mechanic)
- `EventType.MANIFEST_DREAD` (DSK manifest dread)
- `EventType.UNLOCK_DOOR` (DSK Rooms)
- `EventType.TARGET_CHOSEN` (ward post-target hook)
- `EventType.QUERY_COST` (cost reduction query)

CardDefinition fields beyond setup_interceptors:
- `setup_in_graveyard` — runs when the card enters the GRAVEYARD zone
  (for graveyard-activated abilities)

### Filter Factories
- `other_creatures_you_control(obj)`
- `other_creatures_with_subtype(obj, "Elf")`
- `creatures_you_control(obj)`

## Card Sets

### Real MTG Sets (from Scryfall API)
Located in `src/cards/`. ~3,450 cards with accurate data. **2,486 cards have wired interceptors** across the 12 sets. ~744 instants/sorceries use cast-effect dispatch (no setup_interceptors). ~230 truly vanilla cards (keyword-only or stat-line). Of the wired cards, ~1,146 have real effect implementations (~46%), ~736 register a trigger or static interceptor whose effect_fn is `return []` pending engine support, and ~604 are bare `return []` stubs (cards with replacement effects, sagas, equipment statics, modal/target choices, or mechanic-specific patterns the engine doesn't yet express). See `engine_gaps.md` for the punch list grouped by missing capability.

| Set | Code | Cards |
|-----|------|-------|
| Wilds of Eldraine | WOE | 281 |
| Lost Caverns of Ixalan | LCI | 292 |
| Murders at Karlov Manor | MKM | 279 |
| Outlaws of Thunder Junction | OTJ | 276 |
| Bloomburrow | BLB | 280 |
| Duskmourn | DSK | 277 |
| Foundations | FDN | 517 |
| Edge of Eternities | EOE | 266 |
| Lorwyn Eclipsed | ECL | 273 |
| Spider-Man | SPM | 193 |
| Avatar: TLA | TLA | 286 |
| Final Fantasy | FIN | 313 |

### Custom Sets (Fan-Made with Interceptors)
Located in `src/cards/custom/`. ~4,400 cards with working interceptors for testing.

| Set | Cards | Notes |
|-----|-------|-------|
| Lorwyn Custom | 408 | Has interceptors, used by tests |
| Temporal Horizons | 276 | Has interceptors |
| + 16 crossover sets | ~3,700 | Star Wars, anime, games |

To regenerate real sets from Scryfall:
```bash
python scripts/fetch_scryfall_set.py <set_code> <module_name> "<Set Name>"
```

## Running Tests
```bash
python tests/test_lorwyn.py
python tests/test_layer_nightmares.py
python tests/test_degenerate.py
```

## Running the Server

Port **8030** (see `~/Projects/PORTS.md` for registry).

```bash
pip install -r requirements-server.txt
uvicorn src.server.main:socket_app --host 0.0.0.0 --port 8030
```

## Running the Frontend
```bash
cd frontend
npm install
npm run dev
```
