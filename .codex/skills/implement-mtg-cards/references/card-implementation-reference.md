# Card Implementation Reference

## File Locations

- Card definitions: `src/cards/<set_name>.py`
- Custom set definitions: `src/cards/custom/<set_name>.py`
- Universal helpers: `src/cards/interceptor_helpers.py`
- Engine types: `src/engine/types.py`
- Targeting, stack, and handlers: `src/engine/targeting.py`, `src/engine/stack.py`, `src/engine/pipeline/handlers/`

## Common Imports

```python
from src.engine import (
    Event, EventType, Interceptor, InterceptorPriority,
    InterceptorAction, InterceptorResult,
    GameObject, GameState, ZoneType, CardType, Color,
    make_creature, make_instant, make_sorcery, make_enchantment,
    make_artifact, make_land, new_id,
)
from src.cards.interceptor_helpers import (
    make_etb_trigger, make_death_trigger, make_attack_trigger,
    make_block_trigger, make_damage_trigger, make_static_pt_boost,
    make_dynamic_pt_boost, make_keyword_grant, make_cost_reduction,
    make_ward, make_spell_cast_trigger, make_tap_trigger,
    make_upkeep_trigger, make_end_step_trigger,
    other_creatures_you_control, creatures_you_control,
    other_creatures_with_subtype, creatures_with_subtype,
)
```

## Event Types Worth Knowing

Object lifecycle: `OBJECT_CREATED`, `OBJECT_DESTROYED`, `ZONE_CHANGE`, `CREATE_TOKEN`, `SACRIFICE`.

Combat: `ATTACK_DECLARED`, `BLOCK_DECLARED`, `DAMAGE`.

Resources/state: `MANA_PRODUCED`, `MANA_SPENT`, `LIFE_CHANGE`, `COUNTER_ADDED`, `COUNTER_REMOVED`, `PT_MODIFICATION`.

Cards/actions: `DRAW`, `DISCARD`, `CAST`, `SPELL_CAST`, `ACTIVATE`.

Queries: `QUERY_POWER`, `QUERY_TOUGHNESS`, `QUERY_ABILITIES`, `QUERY_COST`, `QUERY_ACTIVATION_COST`, plus type/subtype/color/supertype queries.

Targeting/library/misc: `TARGET_CHOSEN`, `SEARCH_LIBRARY`, `EXILE_TOP_PLAY`, `RETURN_FROM_GRAVEYARD`, `EXTRA_TURN`, `EXTRA_COMBAT`, `GRANT_KEYWORD`, `ATTACH`, `UNATTACH`, `UNLOCK_DOOR`, `MANIFEST_DREAD`.

## Helper Surface

Frequently used trigger helpers:

- `make_etb_trigger(obj, effect_fn, filter_fn=None)`
- `make_death_trigger(obj, effect_fn, filter_fn=None)`
- `make_attack_trigger(obj, effect_fn, filter_fn=None)`
- `make_block_trigger(obj, effect_fn, filter_fn=None)`
- `make_damage_trigger(obj, effect_fn, combat_only=False, noncombat_only=False, filter_fn=None)`
- `make_tap_trigger(obj, effect_fn)`
- `make_upkeep_trigger(obj, effect_fn, controller_only=True)`
- `make_end_step_trigger(obj, effect_fn, controller_only=True)`
- `make_spell_cast_trigger(obj, effect_fn, controller_only=True, spell_type_filter=None, color_filter=None)`
- `make_life_gain_trigger(obj, effect_fn, controller_only=True)`
- `make_life_loss_trigger(obj, effect_fn, opponent_only=True)`
- `make_draw_trigger(obj, effect_fn, controller_only=True)`
- `make_counter_added_trigger(obj, effect_fn, counter_type=None, self_only=True)`
- `make_leaves_battlefield_trigger(...)`
- Targeted variants: `make_targeted_etb_trigger`, `make_targeted_attack_trigger`, `make_targeted_death_trigger`, `make_targeted_damage_trigger`, `make_targeted_spell_cast_trigger`

Static/replacement helpers:

- `make_static_pt_boost(obj, power_mod, toughness_mod, affects_filter)`
- `make_dynamic_pt_boost(obj, mod_fn, affects_filter)`
- `make_attached_dynamic_pt_boost(...)`
- `make_keyword_grant(obj, keywords, affects_filter)`
- `make_cost_reduction(obj, applies_to, amount, condition_fn=...)`
- `make_ward(obj, mana_cost=..., life_cost=..., custom_cost=...)`
- `make_replacement_effect(obj, event_filter, replace_fn, duration="end_of_turn")`

Activated, equipment, and aura helpers:

- `make_activated_ability(obj, cost, effect_fn, precondition_fn=...)`
- `make_exhaust_ability`, `make_pump_self_ability`, `make_draw_ability`, `make_loot_ability`, `make_life_gain_ability`, `make_damage_ability`, `make_destroy_ability`, `make_counter_ability`, `make_token_creation_ability`, `make_sac_destroy_ability`
- `make_equipment_setup(power_mod=..., toughness_mod=..., keywords=..., equip_cost=..., subtypes_to_add=...)`
- `make_aura_setup(...)`
- `make_granted_activated_ability(...)`

Set/mechanic helpers:

- `make_spree_setup`, `make_saga_setup`, `make_modal_etb_trigger`, `make_modal_resolve`
- `make_castable_from_zone`, `make_castable_from_graveyard`, `make_castable_from_exile`, `make_castable_from_library_top`
- `make_face_down_setup`, `make_manifest_etb_event`
- `make_warp_setup`, `make_web_slinging_setup`, `make_mayhem_setup`
- `suspect_creature`, `collect_evidence`, `was_bargained`, `is_door_unlocked`, `make_room_setup`
- `becomes_creature`, `becomes_copy_of`, `threaten_creature`, `grant_death_trigger`, `grant_triggered_ability`

Counting/query helpers:

- `count_permanents_with_subtype(controller, subtype, state)`
- `count_permanents_of_type(controller, card_type, state)`
- `count_cards_in_graveyard(controller, state, ...)`
- `count_cards_in_hand(controller, state)`
- `count_attachments(target, kind_filter=None)`
- `was_destroyed_this_turn(obj_id, state)`

Filter factories:

- `other_creatures_you_control(obj)`
- `creatures_you_control(obj)`
- `other_creatures_with_subtype(obj, "Elf")`
- `creatures_with_subtype(obj, "Elf")`

## Card Definition Helpers

```python
make_creature(name, power, toughness, mana_cost, colors, subtypes, text, supertypes=None, setup_interceptors=None)
make_instant(name, mana_cost, colors, text, resolve=None)
make_sorcery(name, mana_cost, colors, text, resolve=None)
make_enchantment(name, mana_cost, colors, text, subtypes=None, setup_interceptors=None)
make_artifact(name, mana_cost, text, subtypes=None, setup_interceptors=None)
make_land(name, subtypes=None, supertypes=None, text="")
```

`CardDefinition` also supports `setup_in_graveyard` for cards that gain abilities while in the graveyard.

## Common Patterns

Life-gain ETB:

```python
def healer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def gain_life(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.LIFE_CHANGE,
            payload={"player": obj.controller, "amount": 3},
            source=obj.id,
        )]
    return [make_etb_trigger(obj, gain_life)]
```

Trigger on another creature entering:

```python
def soul_warden_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def another_creature_entered(event: Event, state: GameState, src: GameObject) -> bool:
        if event.type == EventType.ZONE_CHANGE:
            if event.payload.get("to_zone_type") != ZoneType.BATTLEFIELD:
                return False
            entered_id = event.payload.get("object_id")
        elif event.type == EventType.CREATE_TOKEN:
            if event.source == src.id:
                return False
            entered_id = event.payload.get("object_id")
        else:
            return False
        if entered_id == src.id:
            return False
        entered = state.objects.get(entered_id)
        return bool(entered and CardType.CREATURE in entered.characteristics.types)

    def gain_life(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.LIFE_CHANGE, payload={"player": obj.controller, "amount": 1}, source=obj.id)]

    return [make_etb_trigger(obj, gain_life, filter_fn=another_creature_entered)]
```

Death trigger:

```python
def doomed_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def create_token(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.CREATE_TOKEN,
            payload={
                "controller": obj.controller,
                "token": {
                    "name": "Zombie",
                    "types": {CardType.CREATURE},
                    "subtypes": {"Zombie"},
                    "power": 2,
                    "toughness": 2,
                },
            },
            source=obj.id,
        )]
    return [make_death_trigger(obj, create_token)]
```

Combat-damage-to-player trigger:

```python
def saboteur_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def hit_player(event: Event, state: GameState, src: GameObject) -> bool:
        return (
            event.type == EventType.DAMAGE
            and event.payload.get("source") == src.id
            and event.payload.get("is_combat", False)
            and event.payload.get("target") in state.players
        )

    def draw(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DRAW, payload={"player": obj.controller, "amount": 1}, source=obj.id)]

    return [make_damage_trigger(obj, draw, combat_only=True, filter_fn=hit_player)]
```

Transform damage into counters:

```python
def wither_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def filt(event: Event, state: GameState) -> bool:
        target = state.objects.get(event.payload.get("target"))
        return (
            event.type == EventType.DAMAGE
            and event.payload.get("source") == obj.id
            and target is not None
            and CardType.CREATURE in target.characteristics.types
        )

    def handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(
            action=InterceptorAction.REPLACE,
            new_events=[Event(
                type=EventType.COUNTER_ADDED,
                payload={
                    "object_id": event.payload.get("target"),
                    "counter_type": "-1/-1",
                    "amount": event.payload.get("amount", 0),
                },
                source=obj.id,
            )],
        )

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.TRANSFORM,
        filter=filt,
        handler=handler,
        duration="while_on_battlefield",
    )]
```

## Canonical Payload Keys

Use these keys unless the local handler proves otherwise:

- `CREATE_TOKEN`: `{"controller": player_id, "token": {...}}`; the handler writes `payload["object_id"]` after creation.
- `EXILE_TOP_PLAY`: use `caster`, not `controller`.
- `ATTACH`: `{"object_id": equipment_or_aura_id, "target_id": creature_id}`.
- `SACRIFICE`: system interceptors rewrite this to `ZONE_CHANGE` with `reason == "sacrifice"` before `REACT`; sacrifice listeners should watch the rewritten `ZONE_CHANGE`.
- `SEARCH_LIBRARY`: synthetic library objects must have `obj.card_def is not None` or library filters reject them.
- Upkeep tests must set `game.state.active_player`; `make_upkeep_trigger` ignores payload-only active-player data.

## Targeting

Prebuilt target filters from `src.engine` include `target_creature()`, `target_any()`, `target_player()`, `target_spell()`, `creature_filter()`, `permanent_filter()`, and `player_filter()`.

Custom `TargetFilter` examples:

```python
from src.engine import TargetFilter

red_creature_you_control = TargetFilter(
    types={CardType.CREATURE},
    colors={Color.RED},
    controller="you",
)

small_creature = TargetFilter(
    types={CardType.CREATURE},
    power_max=3,
)

graveyard_card = TargetFilter(
    zones=[ZoneType.GRAVEYARD],
)
```

## Testing Patterns

Load test:

- Card exists in the expected registry dict/list.
- Types, subtypes, supertypes, mana cost, power/toughness, and text are correct enough.
- Interceptor count or named setup exists where expected.

Positive path:

- Put the card into the right zone through the engine path.
- Emit the event that should trigger the behavior.
- Assert state or `game.state.event_log` contains the emitted event.

Edge cases:

- Opponent's event does not trigger controller-only behavior.
- "Another" filters exclude the source.
- Wrong subtype/card type is ignored.
- Empty library or no legal target does not crash.
- Activated ability precondition false means not legal.
- Replacement/prevention does not loop on its own emitted event.

For sagas, mirror `tests/test_saga.py` and advance chapters by setting `state.active_player` and emitting `PHASE_START` with `phase="draw"`.

## Common Gotchas

- Flavor text alone does not grant keywords if the card's characteristics do not already include them. Use `make_keyword_grant` for static self-keywords.
- `ObjectState` has no `flags` dict; use private attributes with `setattr(obj.state, "_name", value)` and `getattr`.
- `ManaCost` exposes properties such as `mana_value`, `is_free`, `colors`, and `to_string`; do not call `total_cost()`.
- Activated costs must be comma-separated: `"{4}, {T}, Sacrifice this artifact"`, not `"{4}{T}"`.
- Tokens from `CREATE_TOKEN` do not necessarily fire the same event path as normal ETB; include `CREATE_TOKEN` in filters that care about token entries.
- `pending_choice` is singular.
- AI heuristics may penalize broad words like "exile", "destroy", or "damage" in parenthetical text; if a card evaluates strangely, inspect scorer heuristics before blaming the card.
- Do not pass `card_def` directly when creating a battlefield object for an ETB setup test unless you deliberately want setup to run during object creation.

## Standard Set Mechanics

- WOE: Adventure, Bargain, Role tokens, Celebration
- LCI: Descend, Discover, Craft, Map tokens, Explore
- MKM: Clue tokens, Suspect, Collect evidence, Disguise, Cases
- OTJ: Outlaw, Plot, Crimes, Spree, Saddle
- BLB: Valiant, Offspring, Gift, Forage, Expend
- DSK: Rooms, Delirium, Manifest Dread, Survival, Eerie
- FDN: classic keywords and tribal support

## Card Set Organization

Main rotation files live under `src/cards/`: WOE, LCI, MKM, OTJ, BLB, DSK, FDN, EOE, ECL, SPM, TLA, FIN, plus newer set modules.

Custom franchise sets live under `src/cards/custom/`. Access aggregate custom cards through:

```python
from src.cards.custom import CUSTOM_CARDS, build_custom_registry
```
