"""
STORMRIFT - A Hybrid MTG/Hearthstone Game Mode

In the Stormrift, elemental storms tear open rifts between realities.
Two factions battle for control of the rift nexus:

  PYROMANCER - Fire & Storm. Aggressive, spell-synergy, burn damage.
  CRYOMANCER - Ice & Void. Control, card advantage, defensive value.

Global Modifiers (installed at game start):
  1. Rift Storm   - Start of each turn, deal 1 damage to ALL minions.
  2. Soul Residue - First minion to die each turn creates a 1/1 Spirit for owner.
  3. Arcane Feedback - Whenever a spell is cast, deal 1 damage to a random enemy minion.

Two classes, 30-card decks, custom heroes + hero powers.
"""

import random
from src.engine.game import make_minion, make_spell, make_hero, make_hero_power
from src.engine.types import (
    Event, EventType, GameObject, GameState, CardType, ZoneType,
    Interceptor, InterceptorPriority, InterceptorAction, InterceptorResult, new_id,
)
from src.cards.interceptor_helpers import (
    make_etb_trigger, make_death_trigger, make_spell_cast_trigger,
    make_static_pt_boost, make_spell_damage_boost,
    get_enemy_targets, get_enemy_minions, get_friendly_minions,
    get_enemy_hero_id, other_friendly_minions,
)


# =============================================================================
# HEROES
# =============================================================================

IGNIS_HERO = make_hero(
    name="Ignis, the Riftburner",
    hero_class="Pyromancer",
    starting_life=30,
    text="Hero Power: Rift Spark (Deal 1 damage to the enemy hero)",
)

GLACIEL_HERO = make_hero(
    name="Glaciel, the Voidfrost",
    hero_class="Cryomancer",
    starting_life=30,
    text="Hero Power: Frost Rift (Gain 2 Armor)",
)

STORMRIFT_HEROES = {
    "Pyromancer": IGNIS_HERO,
    "Cryomancer": GLACIEL_HERO,
}


# =============================================================================
# HERO POWERS
# =============================================================================

def rift_spark_effect(obj: GameObject, state: GameState) -> list[Event]:
    """Deal 1 damage to the enemy hero."""
    hero_id = get_enemy_hero_id(obj, state)
    if not hero_id:
        return []
    return [Event(
        type=EventType.DAMAGE,
        payload={'target': hero_id, 'amount': 1, 'source': obj.id},
        source=obj.id,
    )]

RIFT_SPARK = make_hero_power(
    name="Rift Spark",
    cost=2,
    text="Deal 1 damage to the enemy hero",
    effect=rift_spark_effect,
)

def frost_rift_effect(obj: GameObject, state: GameState) -> list[Event]:
    """Gain 2 Armor."""
    return [Event(
        type=EventType.ARMOR_GAIN,
        payload={'player': obj.controller, 'amount': 2},
        source=obj.id,
    )]

FROST_RIFT = make_hero_power(
    name="Frost Rift",
    cost=2,
    text="Gain 2 Armor",
    effect=frost_rift_effect,
)

STORMRIFT_HERO_POWERS = {
    "Pyromancer": RIFT_SPARK,
    "Cryomancer": FROST_RIFT,
}


# =============================================================================
# PYROMANCER MINIONS
# =============================================================================

# --- 1-cost ---

RIFT_SPARK_ELEMENTAL = make_minion(
    name="Rift Spark Elemental",
    attack=2, health=1,
    mana_cost="{1}",
    subtypes={"Elemental"},
    keywords={"charge"},
    text="Charge",
    rarity="common",
)

KINDLING_IMP = make_minion(
    name="Kindling Imp",
    attack=1, health=2,
    mana_cost="{1}",
    subtypes={"Demon", "Elemental"},
    text="Deathrattle: Deal 1 damage to the enemy hero.",
    rarity="common",
    deathrattle=lambda obj, state: [Event(
        type=EventType.DAMAGE,
        payload={'target': get_enemy_hero_id(obj, state) or '', 'amount': 1, 'source': obj.id},
        source=obj.id,
    )] if get_enemy_hero_id(obj, state) else [],
)

# --- 2-cost ---

def ember_channeler_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """After you cast a spell, gain +1 Attack."""
    def spell_filter(event, s):
        if event.type not in (EventType.CAST, EventType.SPELL_CAST):
            return False
        source = s.objects.get(event.source)
        return source is not None and source.controller == obj.controller

    def spell_handler(event, s):
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.PT_MODIFICATION,
                payload={'object_id': obj.id, 'power_mod': 1, 'toughness_mod': 0, 'duration': 'permanent'},
                source=obj.id,
            )],
        )

    return [Interceptor(
        id=new_id(), source=obj.id, controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=spell_filter, handler=spell_handler,
        duration='while_on_battlefield',
    )]

EMBER_CHANNELER = make_minion(
    name="Ember Channeler",
    attack=2, health=3,
    mana_cost="{2}",
    subtypes={"Elemental"},
    text="After you cast a spell, gain +1 Attack.",
    rarity="rare",
    setup_interceptors=ember_channeler_setup,
)

STORM_ACOLYTE = make_minion(
    name="Storm Acolyte",
    attack=1, health=3,
    mana_cost="{2}",
    subtypes={"Elemental"},
    text="Spell Damage +1",
    rarity="common",
    setup_interceptors=lambda obj, state: [make_spell_damage_boost(obj, amount=1)],
)

# --- 3-cost ---

def rift_firehound_battlecry(obj: GameObject, state: GameState) -> list[Event]:
    """Deal 2 damage to a random enemy minion."""
    targets = get_enemy_minions(obj, state)
    if not targets:
        return []
    target = random.choice(targets)
    return [Event(
        type=EventType.DAMAGE,
        payload={'target': target, 'amount': 2, 'source': obj.id, 'from_spell': False},
        source=obj.id,
    )]

RIFT_FIREHOUND = make_minion(
    name="Rift Firehound",
    attack=3, health=2,
    mana_cost="{3}",
    subtypes={"Beast", "Elemental"},
    text="Battlecry: Deal 2 damage to a random enemy minion.",
    rarity="common",
    battlecry=rift_firehound_battlecry,
)

PYROCLASM_ADEPT = make_minion(
    name="Pyroclasm Adept",
    attack=3, health=4,
    mana_cost="{3}",
    subtypes={"Elemental"},
    text="",
    rarity="common",
)

# --- 4-cost ---

def pyroclasm_drake_battlecry(obj: GameObject, state: GameState) -> list[Event]:
    """Deal 1 damage to all enemy minions."""
    targets = get_enemy_minions(obj, state)
    return [
        Event(
            type=EventType.DAMAGE,
            payload={'target': t, 'amount': 1, 'source': obj.id},
            source=obj.id,
        )
        for t in targets
    ]

PYROCLASM_DRAKE = make_minion(
    name="Pyroclasm Drake",
    attack=4, health=4,
    mana_cost="{4}",
    subtypes={"Dragon", "Elemental"},
    text="Battlecry: Deal 1 damage to all enemy minions.",
    rarity="rare",
    battlecry=pyroclasm_drake_battlecry,
)

RIFT_BERSERKER = make_minion(
    name="Rift Berserker",
    attack=5, health=3,
    mana_cost="{4}",
    subtypes={"Elemental"},
    text="Charge",
    keywords={"charge"},
    rarity="rare",
)

# --- 5-cost ---

INFERNO_GOLEM = make_minion(
    name="Inferno Golem",
    attack=5, health=6,
    mana_cost="{5}",
    subtypes={"Elemental"},
    text="Taunt",
    keywords={"taunt"},
    rarity="common",
)

def volatilerift_mage_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """After you cast a spell, deal 1 damage to all enemy minions."""
    def spell_filter(event, s):
        if event.type not in (EventType.CAST, EventType.SPELL_CAST):
            return False
        source = s.objects.get(event.source)
        return source is not None and source.controller == obj.controller

    def spell_handler(event, s):
        targets = get_enemy_minions(obj, s)
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[
                Event(
                    type=EventType.DAMAGE,
                    payload={'target': t, 'amount': 1, 'source': obj.id},
                    source=obj.id,
                )
                for t in targets
            ],
        )

    return [Interceptor(
        id=new_id(), source=obj.id, controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=spell_filter, handler=spell_handler,
        duration='while_on_battlefield',
    )]

VOLATILERIFT_MAGE = make_minion(
    name="Volatilerift Mage",
    attack=4, health=5,
    mana_cost="{5}",
    subtypes={"Elemental"},
    text="After you cast a spell, deal 1 damage to all enemy minions.",
    rarity="epic",
    setup_interceptors=volatilerift_mage_setup,
)

# --- 6-cost ---

STORMRIFT_PHOENIX = make_minion(
    name="Stormrift Phoenix",
    attack=5, health=5,
    mana_cost="{6}",
    subtypes={"Elemental", "Beast"},
    text="Deathrattle: Deal 3 damage to the enemy hero.",
    rarity="rare",
    deathrattle=lambda obj, state: [Event(
        type=EventType.DAMAGE,
        payload={'target': get_enemy_hero_id(obj, state) or '', 'amount': 3, 'source': obj.id},
        source=obj.id,
    )] if get_enemy_hero_id(obj, state) else [],
)

# --- 7-cost ---

def riftborn_titan_battlecry(obj: GameObject, state: GameState) -> list[Event]:
    """Deal 3 damage to all enemies (hero + minions)."""
    targets = get_enemy_targets(obj, state)
    return [
        Event(
            type=EventType.DAMAGE,
            payload={'target': t, 'amount': 3, 'source': obj.id},
            source=obj.id,
        )
        for t in targets
    ]

RIFTBORN_TITAN = make_minion(
    name="Riftborn Titan",
    attack=7, health=7,
    mana_cost="{7}",
    subtypes={"Elemental"},
    text="Battlecry: Deal 3 damage to all enemies.",
    rarity="legendary",
    battlecry=riftborn_titan_battlecry,
)


# =============================================================================
# PYROMANCER SPELLS
# =============================================================================

def singe_effect(obj, state, targets=None):
    """Deal 2 damage to a random enemy."""
    enemy_targets = get_enemy_targets(obj, state)
    if not enemy_targets:
        return []
    target = random.choice(enemy_targets)
    return [Event(
        type=EventType.DAMAGE,
        payload={'target': target, 'amount': 2, 'source': obj.id, 'from_spell': True},
        source=obj.id,
    )]

SINGE = make_spell(
    name="Singe",
    mana_cost="{1}",
    text="Deal 2 damage to a random enemy.",
    spell_effect=singe_effect,
    rarity="common",
)

def rift_bolt_effect(obj, state, targets=None):
    """Deal 3 damage to a random enemy."""
    enemy_targets = get_enemy_targets(obj, state)
    if not enemy_targets:
        return []
    target = random.choice(enemy_targets)
    return [Event(
        type=EventType.DAMAGE,
        payload={'target': target, 'amount': 3, 'source': obj.id, 'from_spell': True},
        source=obj.id,
    )]

RIFT_BOLT = make_spell(
    name="Rift Bolt",
    mana_cost="{2}",
    text="Deal 3 damage to a random enemy.",
    spell_effect=rift_bolt_effect,
    rarity="common",
)

def searing_rift_effect(obj, state, targets=None):
    """Deal 4 damage to a random enemy."""
    enemy_targets = get_enemy_targets(obj, state)
    if not enemy_targets:
        return []
    target = random.choice(enemy_targets)
    return [Event(
        type=EventType.DAMAGE,
        payload={'target': target, 'amount': 4, 'source': obj.id, 'from_spell': True},
        source=obj.id,
    )]

SEARING_RIFT = make_spell(
    name="Searing Rift",
    mana_cost="{4}",
    text="Deal 4 damage to a random enemy.",
    spell_effect=searing_rift_effect,
    rarity="rare",
)

def inferno_wave_effect(obj, state, targets=None):
    """Deal 3 damage to all enemy minions."""
    targets_list = get_enemy_minions(obj, state)
    return [
        Event(
            type=EventType.DAMAGE,
            payload={'target': t, 'amount': 3, 'source': obj.id, 'from_spell': True},
            source=obj.id,
        )
        for t in targets_list
    ]

INFERNO_WAVE = make_spell(
    name="Inferno Wave",
    mana_cost="{5}",
    text="Deal 3 damage to all enemy minions.",
    spell_effect=inferno_wave_effect,
    rarity="rare",
)

def pyroclasm_effect(obj, state, targets=None):
    """Deal 5 damage to all enemies."""
    enemy_targets = get_enemy_targets(obj, state)
    return [
        Event(
            type=EventType.DAMAGE,
            payload={'target': t, 'amount': 5, 'source': obj.id, 'from_spell': True},
            source=obj.id,
        )
        for t in enemy_targets
    ]

PYROCLASM = make_spell(
    name="Pyroclasm",
    mana_cost="{7}",
    text="Deal 5 damage to all enemies.",
    spell_effect=pyroclasm_effect,
    rarity="epic",
)

def chain_lightning_effect(obj, state, targets=None):
    """Deal 2 damage to a random enemy, then 2 to another."""
    enemy_targets = get_enemy_targets(obj, state)
    if not enemy_targets:
        return []
    events = []
    t1 = random.choice(enemy_targets)
    events.append(Event(
        type=EventType.DAMAGE,
        payload={'target': t1, 'amount': 2, 'source': obj.id, 'from_spell': True},
        source=obj.id,
    ))
    remaining = [t for t in enemy_targets if t != t1]
    if remaining:
        t2 = random.choice(remaining)
    else:
        t2 = t1
    events.append(Event(
        type=EventType.DAMAGE,
        payload={'target': t2, 'amount': 2, 'source': obj.id, 'from_spell': True},
        source=obj.id,
    ))
    return events

CHAIN_LIGHTNING = make_spell(
    name="Chain Lightning",
    mana_cost="{3}",
    text="Deal 2 damage to a random enemy, then 2 damage to another random enemy.",
    spell_effect=chain_lightning_effect,
    rarity="rare",
)


# =============================================================================
# CRYOMANCER MINIONS
# =============================================================================

# --- 1-cost ---

FROST_WISP = make_minion(
    name="Frost Wisp",
    attack=1, health=2,
    mana_cost="{1}",
    subtypes={"Elemental"},
    text="Deathrattle: Draw a card.",
    rarity="common",
    deathrattle=lambda obj, state: [Event(
        type=EventType.DRAW,
        payload={'player': obj.controller, 'count': 1},
        source=obj.id,
    )],
)

VOID_SPRITE = make_minion(
    name="Void Sprite",
    attack=1, health=3,
    mana_cost="{1}",
    subtypes={"Elemental"},
    text="Taunt",
    keywords={"taunt"},
    rarity="common",
)

# --- 2-cost ---

GLACIAL_SENTINEL = make_minion(
    name="Glacial Sentinel",
    attack=2, health=3,
    mana_cost="{2}",
    subtypes={"Elemental"},
    text="Taunt",
    keywords={"taunt"},
    rarity="common",
)

def rift_watcher_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """At the end of your turn, draw a card."""
    def end_turn_filter(event, s):
        return (event.type in (EventType.TURN_END, EventType.PHASE_END) and
                event.payload.get('player') == obj.controller)

    def end_turn_handler(event, s):
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.DRAW,
                payload={'player': obj.controller, 'count': 1},
                source=obj.id,
            )],
        )

    return [Interceptor(
        id=new_id(), source=obj.id, controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=end_turn_filter, handler=end_turn_handler,
        duration='while_on_battlefield',
    )]

RIFT_WATCHER = make_minion(
    name="Rift Watcher",
    attack=1, health=4,
    mana_cost="{2}",
    subtypes={"Elemental"},
    text="At the end of your turn, draw a card.",
    rarity="epic",
    setup_interceptors=rift_watcher_setup,
)

# --- 3-cost ---

VOID_SEER = make_minion(
    name="Void Seer",
    attack=2, health=4,
    mana_cost="{3}",
    subtypes={"Elemental"},
    text="Battlecry: Draw a card.",
    rarity="common",
    battlecry=lambda obj, state: [Event(
        type=EventType.DRAW,
        payload={'player': obj.controller, 'count': 1},
        source=obj.id,
    )],
)

FROZEN_REVENANT = make_minion(
    name="Frozen Revenant",
    attack=3, health=4,
    mana_cost="{3}",
    subtypes={"Elemental"},
    text="Taunt",
    keywords={"taunt"},
    rarity="common",
)

# --- 4-cost ---

ABYSSAL_LURKER = make_minion(
    name="Abyssal Lurker",
    attack=3, health=5,
    mana_cost="{4}",
    subtypes={"Elemental"},
    text="Deathrattle: Draw 2 cards.",
    rarity="rare",
    deathrattle=lambda obj, state: [Event(
        type=EventType.DRAW,
        payload={'player': obj.controller, 'count': 2},
        source=obj.id,
    )],
)

def voidcrystal_golem_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Your other minions have +0/+1."""
    return make_static_pt_boost(
        obj, power_mod=0, toughness_mod=1,
        affects_filter=other_friendly_minions(obj),
    )

VOIDCRYSTAL_GOLEM = make_minion(
    name="Voidcrystal Golem",
    attack=2, health=5,
    mana_cost="{4}",
    subtypes={"Elemental"},
    text="Your other minions have +0/+1.",
    rarity="rare",
    setup_interceptors=voidcrystal_golem_setup,
)

# --- 5-cost ---

def blizzard_golem_battlecry(obj: GameObject, state: GameState) -> list[Event]:
    """Deal 2 damage to all enemy minions."""
    targets = get_enemy_minions(obj, state)
    return [
        Event(
            type=EventType.DAMAGE,
            payload={'target': t, 'amount': 2, 'source': obj.id},
            source=obj.id,
        )
        for t in targets
    ]

BLIZZARD_GOLEM = make_minion(
    name="Blizzard Golem",
    attack=4, health=6,
    mana_cost="{5}",
    subtypes={"Elemental"},
    text="Battlecry: Deal 2 damage to all enemy minions.",
    rarity="rare",
    battlecry=blizzard_golem_battlecry,
)

RIFT_GUARDIAN = make_minion(
    name="Rift Guardian",
    attack=3, health=8,
    mana_cost="{5}",
    subtypes={"Elemental"},
    text="Taunt",
    keywords={"taunt"},
    rarity="common",
)

# --- 6-cost ---

def voidfrost_dragon_battlecry(obj: GameObject, state: GameState) -> list[Event]:
    """Deal 2 damage to all enemies."""
    targets = get_enemy_targets(obj, state)
    return [
        Event(
            type=EventType.DAMAGE,
            payload={'target': t, 'amount': 2, 'source': obj.id},
            source=obj.id,
        )
        for t in targets
    ]

VOIDFROST_DRAGON = make_minion(
    name="Voidfrost Dragon",
    attack=5, health=6,
    mana_cost="{6}",
    subtypes={"Dragon", "Elemental"},
    text="Battlecry: Deal 2 damage to all enemies.",
    rarity="epic",
    battlecry=voidfrost_dragon_battlecry,
)

# --- 7-cost ---

def glaciels_avatar_deathrattle(obj: GameObject, state: GameState) -> list[Event]:
    """Deal 2 damage to all enemy minions."""
    targets = get_enemy_minions(obj, state)
    return [
        Event(
            type=EventType.DAMAGE,
            payload={'target': t, 'amount': 2, 'source': obj.id},
            source=obj.id,
        )
        for t in targets
    ]

GLACIELS_AVATAR = make_minion(
    name="Glaciel's Avatar",
    attack=4, health=8,
    mana_cost="{7}",
    subtypes={"Elemental"},
    text="Taunt. Deathrattle: Deal 2 damage to all enemy minions.",
    keywords={"taunt"},
    rarity="legendary",
    deathrattle=glaciels_avatar_deathrattle,
)

# --- 9-cost ---

def rift_colossus_battlecry(obj: GameObject, state: GameState) -> list[Event]:
    """Deal 4 damage to all enemies."""
    targets = get_enemy_targets(obj, state)
    return [
        Event(
            type=EventType.DAMAGE,
            payload={'target': t, 'amount': 4, 'source': obj.id},
            source=obj.id,
        )
        for t in targets
    ]

RIFT_COLOSSUS = make_minion(
    name="Rift Colossus",
    attack=8, health=8,
    mana_cost="{9}",
    subtypes={"Elemental"},
    text="Battlecry: Deal 4 damage to all enemies.",
    rarity="legendary",
    battlecry=rift_colossus_battlecry,
)


# =============================================================================
# CRYOMANCER SPELLS
# =============================================================================

def frost_spike_effect(obj, state, targets=None):
    """Deal 1 damage to a random enemy. Draw a card."""
    enemy_targets = get_enemy_targets(obj, state)
    events = []
    if enemy_targets:
        target = random.choice(enemy_targets)
        events.append(Event(
            type=EventType.DAMAGE,
            payload={'target': target, 'amount': 1, 'source': obj.id, 'from_spell': True},
            source=obj.id,
        ))
    events.append(Event(
        type=EventType.DRAW,
        payload={'player': obj.controller, 'count': 1},
        source=obj.id,
    ))
    return events

FROST_SPIKE = make_spell(
    name="Frost Spike",
    mana_cost="{1}",
    text="Deal 1 damage to a random enemy. Draw a card.",
    spell_effect=frost_spike_effect,
    rarity="common",
)

def rift_sight_effect(obj, state, targets=None):
    """Draw 2 cards."""
    return [Event(
        type=EventType.DRAW,
        payload={'player': obj.controller, 'count': 2},
        source=obj.id,
    )]

RIFT_SIGHT = make_spell(
    name="Rift Sight",
    mana_cost="{3}",
    text="Draw 2 cards.",
    spell_effect=rift_sight_effect,
    rarity="common",
)

def void_barrier_effect(obj, state, targets=None):
    """Give all friendly minions +0/+2."""
    friendlies = get_friendly_minions(obj, state, exclude_self=False)
    return [
        Event(
            type=EventType.PT_MODIFICATION,
            payload={'object_id': t, 'power_mod': 0, 'toughness_mod': 2, 'duration': 'permanent'},
            source=obj.id,
        )
        for t in friendlies
    ]

VOID_BARRIER = make_spell(
    name="Void Barrier",
    mana_cost="{4}",
    text="Give all friendly minions +0/+2.",
    spell_effect=void_barrier_effect,
    rarity="rare",
)

def glacial_tomb_effect(obj, state, targets=None):
    """Deal 4 damage to a random enemy minion. Draw a card."""
    events = []
    enemies = get_enemy_minions(obj, state)
    if enemies:
        target = random.choice(enemies)
        events.append(Event(
            type=EventType.DAMAGE,
            payload={'target': target, 'amount': 4, 'source': obj.id, 'from_spell': True},
            source=obj.id,
        ))
    events.append(Event(
        type=EventType.DRAW,
        payload={'player': obj.controller, 'count': 1},
        source=obj.id,
    ))
    return events

GLACIAL_TOMB = make_spell(
    name="Glacial Tomb",
    mana_cost="{5}",
    text="Deal 4 damage to a random enemy minion. Draw a card.",
    spell_effect=glacial_tomb_effect,
    rarity="rare",
)

def absolute_zero_effect(obj, state, targets=None):
    """Deal 3 damage to all enemies."""
    enemy_targets = get_enemy_targets(obj, state)
    return [
        Event(
            type=EventType.DAMAGE,
            payload={'target': t, 'amount': 3, 'source': obj.id, 'from_spell': True},
            source=obj.id,
        )
        for t in enemy_targets
    ]

ABSOLUTE_ZERO = make_spell(
    name="Absolute Zero",
    mana_cost="{8}",
    text="Deal 3 damage to all enemies.",
    spell_effect=absolute_zero_effect,
    rarity="epic",
)

def void_drain_effect(obj, state, targets=None):
    """Deal 2 damage to a random enemy minion. Gain 2 Armor."""
    events = []
    enemies = get_enemy_minions(obj, state)
    if enemies:
        target = random.choice(enemies)
        events.append(Event(
            type=EventType.DAMAGE,
            payload={'target': target, 'amount': 2, 'source': obj.id, 'from_spell': True},
            source=obj.id,
        ))
    events.append(Event(
        type=EventType.ARMOR_GAIN,
        payload={'player': obj.controller, 'amount': 2},
        source=obj.id,
    ))
    return events

VOID_DRAIN = make_spell(
    name="Void Drain",
    mana_cost="{2}",
    text="Deal 2 damage to a random enemy minion. Gain 2 Armor.",
    spell_effect=void_drain_effect,
    rarity="common",
)


# =============================================================================
# NEUTRAL MINIONS (shared between both classes)
# =============================================================================

RIFT_WALKER = make_minion(
    name="Rift Walker",
    attack=1, health=1,
    mana_cost="{1}",
    subtypes={"Elemental"},
    text="Battlecry: Draw a card.",
    rarity="common",
    battlecry=lambda obj, state: [Event(
        type=EventType.DRAW,
        payload={'player': obj.controller, 'count': 1},
        source=obj.id,
    )],
)

STORM_HERALD = make_minion(
    name="Storm Herald",
    attack=2, health=2,
    mana_cost="{2}",
    subtypes={"Elemental"},
    text="",
    rarity="common",
)

RIFT_IMP = make_minion(
    name="Rift Imp",
    attack=3, health=3,
    mana_cost="{3}",
    subtypes={"Demon", "Elemental"},
    text="",
    rarity="common",
)

NEXUS_GUARDIAN = make_minion(
    name="Nexus Guardian",
    attack=4, health=5,
    mana_cost="{4}",
    subtypes={"Elemental"},
    text="Taunt",
    keywords={"taunt"},
    rarity="common",
)

RIFT_CHAMPION = make_minion(
    name="Rift Champion",
    attack=5, health=5,
    mana_cost="{5}",
    subtypes={"Elemental"},
    text="",
    rarity="common",
)

RIFT_BEHEMOTH = make_minion(
    name="Rift Behemoth",
    attack=6, health=7,
    mana_cost="{6}",
    subtypes={"Elemental"},
    text="Taunt",
    keywords={"taunt"},
    rarity="common",
)


# =============================================================================
# DECKS
# =============================================================================

PYROMANCER_DECK = [
    # 1-cost (6)
    RIFT_SPARK_ELEMENTAL, RIFT_SPARK_ELEMENTAL,
    KINDLING_IMP, KINDLING_IMP,
    SINGE, SINGE,
    # 2-cost (6)
    EMBER_CHANNELER, EMBER_CHANNELER,
    STORM_ACOLYTE, STORM_ACOLYTE,
    RIFT_BOLT, RIFT_BOLT,
    # 3-cost (4)
    RIFT_FIREHOUND, RIFT_FIREHOUND,
    CHAIN_LIGHTNING, CHAIN_LIGHTNING,
    # 4-cost (4)
    PYROCLASM_DRAKE, PYROCLASM_DRAKE,
    SEARING_RIFT, SEARING_RIFT,
    # 5-cost (4)
    INFERNO_GOLEM, VOLATILERIFT_MAGE,
    INFERNO_WAVE, INFERNO_WAVE,
    # 6-cost (2)
    STORMRIFT_PHOENIX, STORMRIFT_PHOENIX,
    # 7-cost (2)
    RIFTBORN_TITAN, PYROCLASM,
    # Neutral filler (2)
    RIFT_WALKER, RIFT_WALKER,
]

CRYOMANCER_DECK = [
    # 1-cost (6)
    FROST_WISP, FROST_WISP,
    VOID_SPRITE, VOID_SPRITE,
    FROST_SPIKE, FROST_SPIKE,
    # 2-cost (6)
    GLACIAL_SENTINEL, GLACIAL_SENTINEL,
    RIFT_WATCHER, VOID_DRAIN,
    VOID_DRAIN, STORM_HERALD,
    # 3-cost (4)
    VOID_SEER, VOID_SEER,
    RIFT_SIGHT, RIFT_SIGHT,
    # 4-cost (4)
    ABYSSAL_LURKER, ABYSSAL_LURKER,
    VOIDCRYSTAL_GOLEM, VOID_BARRIER,
    # 5-cost (4)
    BLIZZARD_GOLEM, BLIZZARD_GOLEM,
    GLACIAL_TOMB, GLACIAL_TOMB,
    # 6-cost (2)
    VOIDFROST_DRAGON, RIFT_BEHEMOTH,
    # 7-cost (2)
    GLACIELS_AVATAR, GLACIELS_AVATAR,
    # 8-cost + 9-cost (2)
    ABSOLUTE_ZERO, RIFT_COLOSSUS,
]

STORMRIFT_DECKS = {
    "Pyromancer": PYROMANCER_DECK,
    "Cryomancer": CRYOMANCER_DECK,
}

assert len(PYROMANCER_DECK) == 30, f"Pyromancer deck has {len(PYROMANCER_DECK)} cards, expected 30"
assert len(CRYOMANCER_DECK) == 30, f"Cryomancer deck has {len(CRYOMANCER_DECK)} cards, expected 30"


# =============================================================================
# GLOBAL MODIFIERS (installed at game start via stress test)
# =============================================================================

def install_stormrift_modifiers(game) -> None:
    """
    Install the three global Stormrift modifiers as persistent interceptors.

    1. Rift Storm   - Start of each player's turn, deal 1 damage to ALL minions.
    2. Soul Residue - First minion death each turn creates a 1/1 Spirit for owner.
    3. Arcane Feedback - Whenever a spell is cast, deal 1 to a random enemy minion.
    """
    state = game.state
    player_ids = list(state.players.keys())
    if len(player_ids) < 2:
        return

    # Tracking state for Soul Residue (per-turn death tracking)
    _soul_residue_state = {'deaths_this_turn': set()}

    # --- MODIFIER 1: Rift Storm ---
    def rift_storm_filter(event, s):
        return event.type == EventType.TURN_START

    def rift_storm_handler(event, s):
        battlefield = s.zones.get('battlefield')
        if not battlefield:
            return InterceptorResult(action=InterceptorAction.PASS)
        damage_events = []
        for oid in list(battlefield.objects):
            obj = s.objects.get(oid)
            if obj and CardType.MINION in obj.characteristics.types:
                damage_events.append(Event(
                    type=EventType.DAMAGE,
                    payload={'target': oid, 'amount': 1, 'source': 'rift_storm'},
                    source='rift_storm',
                ))
        if damage_events:
            return InterceptorResult(action=InterceptorAction.REACT, new_events=damage_events)
        return InterceptorResult(action=InterceptorAction.PASS)

    rift_storm = Interceptor(
        id=f"mod_rift_storm_{new_id()}",
        source='global_modifier',
        controller=player_ids[0],  # Global, but needs a controller
        priority=InterceptorPriority.REACT,
        filter=rift_storm_filter,
        handler=rift_storm_handler,
        duration='permanent',
    )

    # --- MODIFIER 2: Soul Residue ---
    # Reset tracker at turn start (registered BEFORE Rift Storm so reset fires first)
    def soul_residue_reset_filter(event, s):
        return event.type == EventType.TURN_START

    def soul_residue_reset_handler(event, s):
        _soul_residue_state['deaths_this_turn'] = set()
        return InterceptorResult(action=InterceptorAction.PASS)

    soul_residue_reset = Interceptor(
        id=f"mod_soul_residue_reset_{new_id()}",
        source='global_modifier',
        controller=player_ids[0],
        priority=InterceptorPriority.REACT,
        filter=soul_residue_reset_filter,
        handler=soul_residue_reset_handler,
        duration='permanent',
    )
    # Register Soul Residue reset FIRST (earlier timestamp -> fires before Rift Storm)
    game.register_interceptor(soul_residue_reset)
    # Then Rift Storm (deaths from Rift Storm count toward "first death this turn")
    game.register_interceptor(rift_storm)

    # Create Spirit on first death
    def soul_residue_filter(event, s):
        if event.type != EventType.OBJECT_DESTROYED:
            return False
        oid = event.payload.get('object_id')
        obj = s.objects.get(oid)
        if not obj or CardType.MINION not in obj.characteristics.types:
            return False
        return obj.controller not in _soul_residue_state['deaths_this_turn']

    def soul_residue_handler(event, s):
        oid = event.payload.get('object_id')
        obj = s.objects.get(oid)
        if not obj:
            return InterceptorResult(action=InterceptorAction.PASS)
        controller = obj.controller
        _soul_residue_state['deaths_this_turn'].add(controller)
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.CREATE_TOKEN,
                payload={
                    'controller': controller,
                    'token': {
                        'name': 'Rift Spirit',
                        'power': 1,
                        'toughness': 1,
                        'types': {CardType.MINION},
                        'subtypes': {'Spirit', 'Elemental'},
                    },
                },
                source='soul_residue',
            )],
        )

    soul_residue = Interceptor(
        id=f"mod_soul_residue_{new_id()}",
        source='global_modifier',
        controller=player_ids[0],
        priority=InterceptorPriority.REACT,
        filter=soul_residue_filter,
        handler=soul_residue_handler,
        duration='permanent',
    )
    game.register_interceptor(soul_residue)

    # --- MODIFIER 3: Arcane Feedback ---
    def arcane_feedback_filter(event, s):
        return event.type in (EventType.CAST, EventType.SPELL_CAST)

    def arcane_feedback_handler(event, s):
        source_obj = s.objects.get(event.source)
        if not source_obj:
            return InterceptorResult(action=InterceptorAction.PASS)
        caster_id = source_obj.controller
        # Find enemy minions
        battlefield = s.zones.get('battlefield')
        if not battlefield:
            return InterceptorResult(action=InterceptorAction.PASS)
        enemy_minions = [
            oid for oid in battlefield.objects
            if oid in s.objects
            and s.objects[oid].controller != caster_id
            and CardType.MINION in s.objects[oid].characteristics.types
        ]
        if not enemy_minions:
            return InterceptorResult(action=InterceptorAction.PASS)
        target = random.choice(enemy_minions)
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.DAMAGE,
                payload={'target': target, 'amount': 1, 'source': 'arcane_feedback'},
                source='arcane_feedback',
            )],
        )

    arcane_feedback = Interceptor(
        id=f"mod_arcane_feedback_{new_id()}",
        source='global_modifier',
        controller=player_ids[0],
        priority=InterceptorPriority.REACT,
        filter=arcane_feedback_filter,
        handler=arcane_feedback_handler,
        duration='permanent',
    )
    game.register_interceptor(arcane_feedback)
