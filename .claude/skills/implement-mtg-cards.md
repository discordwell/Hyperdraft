# Skill: Implement MTG Cards for Hyperdraft

## Overview
This skill guides the implementation of Magic: The Gathering-style cards in the Hyperdraft engine. The engine uses an event-driven architecture where **everything is an Event, and everything else is an Interceptor**.

## Core Architecture

### Event Pipeline
```
Event → TRANSFORM → PREVENT → RESOLVE → REACT
```

### Interceptor Priorities
| Priority | Purpose | Example |
|----------|---------|---------|
| TRANSFORM (1) | Modify events before resolution | Wither (damage → counters) |
| PREVENT (2) | Cancel events | Protection, prevention shields |
| REACT (3) | Trigger after resolution | ETB effects, death triggers |
| QUERY (4) | Modify state reads | Lord effects (+1/+1), keyword grants |

### Key Event Types
```python
EventType.ZONE_CHANGE      # ETB, death, exile, bounce
EventType.ATTACK_DECLARED  # Attack triggers
EventType.BLOCK_DECLARED   # Block triggers
EventType.DAMAGE           # Damage triggers, lifelink
EventType.LIFE_CHANGE      # Life gain/loss triggers
EventType.COUNTER_ADDED    # +1/+1, -1/-1, time counters
EventType.CAST             # Spell cast triggers
EventType.TAP / UNTAP      # Tap triggers
EventType.PHASE_START      # Upkeep, end step triggers
EventType.QUERY_POWER      # P/T modifications
EventType.QUERY_TOUGHNESS  # P/T modifications
EventType.QUERY_ABILITIES  # Keyword grants
```

## File Locations
- **Card definitions**: `src/cards/<set_name>.py`
- **Universal helpers**: `src/cards/interceptor_helpers.py`
- **Engine types**: `src/engine/types.py`

## Card Definition Pattern

### Basic Structure
```python
from src.engine import (
    Event, EventType, Interceptor, InterceptorPriority,
    InterceptorAction, InterceptorResult,
    GameObject, GameState, ZoneType, CardType, Color,
    make_creature, make_instant, make_enchantment,
    new_id
)
from src.cards.interceptor_helpers import (
    make_etb_trigger, make_death_trigger, make_attack_trigger,
    make_static_pt_boost, make_keyword_grant,
    other_creatures_you_control, other_creatures_with_subtype
)

# Setup function pattern
def card_name_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': obj.controller, 'amount': 3},
            source=obj.id
        )]
    return [make_etb_trigger(obj, effect_fn)]

# Card definition
CARD_NAME = make_creature(
    name="Card Name",
    power=3,
    toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    text="When Card Name enters, you gain 3 life.",
    setup_interceptors=card_name_setup
)
```

## Available Helper Functions

### Trigger Helpers (from interceptor_helpers.py)
```python
# ETB - "When ~ enters the battlefield"
make_etb_trigger(obj, effect_fn, filter_fn=None) -> Interceptor

# Death - "When ~ dies"
make_death_trigger(obj, effect_fn, filter_fn=None) -> Interceptor

# Attack - "Whenever ~ attacks"
make_attack_trigger(obj, effect_fn, filter_fn=None) -> Interceptor

# Block - "Whenever ~ blocks"
make_block_trigger(obj, effect_fn, filter_fn=None) -> Interceptor

# Damage - "Whenever ~ deals damage"
make_damage_trigger(obj, effect_fn, combat_only=False, noncombat_only=False) -> Interceptor

# Tap - "Whenever ~ becomes tapped"
make_tap_trigger(obj, effect_fn) -> Interceptor

# Upkeep - "At the beginning of your upkeep"
make_upkeep_trigger(obj, effect_fn, controller_only=True) -> Interceptor

# End step - "At the beginning of your end step"
make_end_step_trigger(obj, effect_fn, controller_only=True) -> Interceptor

# Spell cast - "Whenever you cast a spell"
make_spell_cast_trigger(obj, effect_fn, controller_only=True,
                        spell_type_filter=None, color_filter=None) -> Interceptor

# Life gain - "Whenever you gain life"
make_life_gain_trigger(obj, effect_fn, controller_only=True) -> Interceptor

# Life loss - "Whenever an opponent loses life"
make_life_loss_trigger(obj, effect_fn, opponent_only=True) -> Interceptor

# Draw - "Whenever you draw a card"
make_draw_trigger(obj, effect_fn, controller_only=True) -> Interceptor

# Counter added - "Whenever a counter is put on ~"
make_counter_added_trigger(obj, effect_fn, counter_type=None, self_only=True) -> Interceptor
```

### Static Effect Helpers
```python
# Lord effect - "Other creatures you control get +1/+1"
make_static_pt_boost(obj, power_mod, toughness_mod, affects_filter) -> list[Interceptor]

# Keyword grant - "Creatures you control have flying"
make_keyword_grant(obj, keywords=['flying'], affects_filter) -> Interceptor
```

### Filter Factories
```python
# "Other creatures you control"
other_creatures_you_control(source_obj) -> Callable

# "All creatures you control"
creatures_you_control(source_obj) -> Callable

# "Other Elves you control"
other_creatures_with_subtype(source_obj, "Elf") -> Callable

# "Elves you control"
creatures_with_subtype(source_obj, "Elf") -> Callable
```

## Common Implementation Patterns

### 1. ETB with Life Gain
```python
def soul_warden_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def other_creature_etb(event: Event, state: GameState, src: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entered_id = event.payload.get('object_id')
        if entered_id == src.id:
            return False
        entered = state.objects.get(entered_id)
        return entered and CardType.CREATURE in entered.characteristics.types

    def gain_life(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id
        )]

    return [make_etb_trigger(obj, gain_life,
            filter_fn=lambda e, s, o: other_creature_etb(e, s, obj))]
```

### 2. Lord Effect (+1/+1 to tribe)
```python
def elvish_archdruid_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return make_static_pt_boost(obj, 1, 1, other_creatures_with_subtype(obj, "Elf"))
```

### 3. Death Trigger
```python
def doomed_dissenter_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def create_zombie(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'controller': obj.controller,
                'name': 'Zombie',
                'power': 2, 'toughness': 2,
                'types': {CardType.CREATURE},
                'subtypes': {'Zombie'},
                'is_token': True
            },
            source=obj.id
        )]
    return [make_death_trigger(obj, create_zombie)]
```

### 4. Combat Damage Trigger
```python
def thief_of_sanity_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def combat_damage_to_player(event: Event, state: GameState, src: GameObject) -> bool:
        if event.type != EventType.DAMAGE:
            return False
        if event.payload.get('source') != src.id:
            return False
        if not event.payload.get('is_combat', False):
            return False
        target = event.payload.get('target')
        return target in state.players

    def exile_and_cast(event: Event, state: GameState) -> list[Event]:
        # Implementation for exile top 3, cast one
        return []

    return [make_damage_trigger(obj, exile_and_cast, combat_only=True,
            filter_fn=lambda e, s, o: combat_damage_to_player(e, s, obj))]
```

### 5. Wither (Transform damage to counters)
```python
def wither_creature_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def wither_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.DAMAGE:
            return False
        if event.payload.get('source') != obj.id:
            return False
        target = state.objects.get(event.payload.get('target'))
        return target and CardType.CREATURE in target.characteristics.types

    def wither_handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(
            action=InterceptorAction.REPLACE,
            new_events=[Event(
                type=EventType.COUNTER_ADDED,
                payload={
                    'object_id': event.payload.get('target'),
                    'counter_type': '-1/-1',
                    'amount': event.payload.get('amount', 0)
                },
                source=obj.id
            )]
        )

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.TRANSFORM,
        filter=wither_filter,
        handler=wither_handler,
        duration='while_on_battlefield'
    )]
```

### 6. Keyword Grant (Conditional)
```python
def archetype_of_courage_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # Your creatures have first strike
    def your_creatures(target: GameObject, state: GameState) -> bool:
        return (target.controller == obj.controller and
                CardType.CREATURE in target.characteristics.types and
                target.zone == ZoneType.BATTLEFIELD)

    return [make_keyword_grant(obj, ['first_strike'], your_creatures)]
```

### 7. Upkeep Trigger
```python
def bitterblossom_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def upkeep_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(type=EventType.LIFE_CHANGE,
                  payload={'player': obj.controller, 'amount': -1},
                  source=obj.id),
            Event(type=EventType.OBJECT_CREATED,
                  payload={'controller': obj.controller, 'name': 'Faerie Rogue',
                           'power': 1, 'toughness': 1, 'types': {CardType.CREATURE},
                           'subtypes': {'Faerie', 'Rogue'}, 'abilities': ['flying'],
                           'is_token': True},
                  source=obj.id)
        ]
    return [make_upkeep_trigger(obj, upkeep_effect)]
```

## Creating Custom Keywords

When a set has unique mechanics, create keyword helpers in the set file:

```python
# Example: "Heroic — Whenever you cast a spell that targets this creature"
def make_heroic(source_obj: GameObject, effect_fn: Callable) -> Interceptor:
    def heroic_filter(event: Event, state: GameState, obj: GameObject) -> bool:
        if event.type != EventType.CAST:
            return False
        if event.payload.get('caster') != obj.controller:
            return False
        targets = event.payload.get('targets', [])
        return obj.id in targets

    return Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.REACT,
        filter=lambda e, s: heroic_filter(e, s, source_obj),
        handler=lambda e, s: InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=effect_fn(e, s)
        ),
        duration='while_on_battlefield'
    )
```

## Card Type Helpers

```python
# Creature
make_creature(name, power, toughness, mana_cost, colors, subtypes,
              text, supertypes=None, setup_interceptors=None)

# Instant
make_instant(name, mana_cost, colors, text, resolve=None)

# Sorcery
make_sorcery(name, mana_cost, colors, text, resolve=None)

# Enchantment
make_enchantment(name, mana_cost, colors, text, subtypes=None,
                 setup_interceptors=None)

# Artifact
make_artifact(name, mana_cost, text, subtypes=None, setup_interceptors=None)

# Land
make_land(name, subtypes=None, supertypes=None, text="")
```

## Testing Cards

```python
def test_card_ability():
    game = Game()
    p1 = game.add_player("Alice")

    # Create the card
    card_def = YOUR_CARDS["Card Name"]
    creature = game.create_object(
        name="Card Name",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=card_def.characteristics,
        card_def=card_def
    )

    # Trigger ETB
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': creature.id,
            'from_zone': 'hand',
            'to_zone': 'battlefield',
            'to_zone_type': ZoneType.BATTLEFIELD
        }
    ))

    # Assert expected state
    assert p1.life == 23  # Gained 3 life
```

## Workflow for Implementing Cards

1. **Read the card text** - Identify triggers, effects, and conditions
2. **Choose the right helper** - Match mechanics to existing helpers
3. **Write setup function** - Create the interceptor(s)
4. **Update card definition** - Add `setup_interceptors=function_name`
5. **Test** - Verify the card works as expected

## Cards That DON'T Need Interceptors

- **Instants/Sorceries** without triggers → Use `resolve` function
- **Vanilla creatures** (no abilities)
- **Cards with only activated abilities** → Handled by priority system
- **Static keyword-only cards** (flying, trample) → Already in characteristics

## Common Pitfalls

1. **Forgetting to check `obj.id`** in filters → Triggers for wrong objects
2. **Not returning a list** from effect_fn → Crashes
3. **Using wrong priority** → Effects happen at wrong time
4. **Circular triggers** → Infinite loops (add safeguards)
5. **Missing `source=obj.id`** in events → Can't track source
