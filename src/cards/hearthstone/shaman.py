"""Hearthstone Shaman Cards - Basic + Classic"""
import random
from src.engine.game import make_minion, make_spell, make_weapon
from src.engine.types import Event, EventType, CardType, GameObject, GameState, ZoneType
from src.cards.interceptor_helpers import (
    get_enemy_targets, get_enemy_minions, get_friendly_minions, get_all_minions,
    get_enemy_hero_id, other_friendly_minions, make_static_pt_boost,
    make_end_of_turn_trigger
)


# ============================================================================
# BASIC SHAMAN CARDS
# ============================================================================

def frost_shock_effect(obj: GameObject, state: GameState, targets: list) -> list[Event]:
    """Deal 1 damage to an enemy character and Freeze it."""
    enemies = get_enemy_targets(obj, state)
    events = []
    if enemies:
        target = random.choice(enemies)
        events.append(Event(
            type=EventType.DAMAGE,
            payload={'target': target, 'amount': 1, 'source': obj.id, 'from_spell': True},
            source=obj.id
        ))
        events.append(Event(
            type=EventType.FREEZE_TARGET,
            payload={'target': target},
            source=obj.id
        ))
    return events


FROST_SHOCK = make_spell(
    name="Frost Shock",
    mana_cost="{1}",
    text="Deal 1 damage to an enemy character and Freeze it.",
    spell_effect=frost_shock_effect
)


def rockbiter_weapon_effect(obj: GameObject, state: GameState, targets: list) -> list[Event]:
    """Give a friendly character +3 Attack this turn."""
    friendly_targets = get_friendly_minions(obj, state, exclude_self=False)
    friendly_targets.append(obj.controller)  # Can target own hero
    events = []
    if friendly_targets:
        target = random.choice(friendly_targets)
        events.append(Event(
            type=EventType.PT_MODIFICATION,
            payload={'object_id': target, 'power_mod': 3, 'toughness_mod': 0, 'duration': 'end_of_turn'},
            source=obj.id
        ))
    return events


ROCKBITER_WEAPON = make_spell(
    name="Rockbiter Weapon",
    mana_cost="{2}",
    text="Give a friendly character +3 Attack this turn.",
    spell_effect=rockbiter_weapon_effect
)


def windfury_spell_effect(obj: GameObject, state: GameState, targets: list) -> list[Event]:
    """Give a minion Windfury."""
    all_minions = get_all_minions(state)
    if all_minions:
        target_id = random.choice(all_minions)
        target = state.objects.get(target_id)
        if target and target.zone == ZoneType.BATTLEFIELD:
            target.state.windfury = True
    return []


WINDFURY_SPELL = make_spell(
    name="Windfury",
    mana_cost="{2}",
    text="Give a minion Windfury.",
    spell_effect=windfury_spell_effect
)


def flametongue_totem_setup(obj: GameObject, state: GameState) -> list:
    """Adjacent minions have +2 Attack. (Simplified: other friendly minions +2 Attack)"""
    return make_static_pt_boost(
        obj,
        power_mod=2,
        toughness_mod=0,
        affects_filter=other_friendly_minions(obj)
    )


FLAMETONGUE_TOTEM = make_minion(
    name="Flametongue Totem",
    attack=0,
    health=3,
    mana_cost="{2}",
    subtypes={"Totem"},
    text="Adjacent minions have +2 Attack.",
    setup_interceptors=flametongue_totem_setup
)


def hex_effect(obj: GameObject, state: GameState, targets: list) -> list[Event]:
    """Transform a minion into a 0/1 Frog with Taunt."""
    enemies = get_enemy_minions(obj, state)
    if not enemies:
        return []

    target_id = random.choice(enemies)
    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    # Transform into Frog
    target.characteristics.power = 0
    target.characteristics.toughness = 1
    target.characteristics.abilities = [{'keyword': 'taunt'}]
    target.characteristics.subtypes = {"Beast"}
    target.name = "Frog"
    target.state.damage = 0
    target.state.divine_shield = False
    target.state.stealth = False
    target.state.windfury = False
    target.state.frozen = False
    target.state.summoning_sickness = True

    if hasattr(target.state, 'pt_modifiers'):
        target.state.pt_modifiers = []

    # Remove all interceptors
    for int_id in list(target.interceptor_ids):
        if int_id in state.interceptors:
            del state.interceptors[int_id]
    target.interceptor_ids.clear()
    target.card_def = None

    return [Event(
        type=EventType.TRANSFORM,
        payload={'object_id': target_id, 'new_name': 'Frog'},
        source=obj.id
    )]


HEX = make_spell(
    name="Hex",
    mana_cost="{3}",
    text="Transform a minion into a 0/1 Frog with Taunt.",
    spell_effect=hex_effect
)


def lightning_bolt_effect(obj: GameObject, state: GameState, targets: list) -> list[Event]:
    """Deal 3 damage. Overload: (1)."""
    enemies = get_enemy_targets(obj, state)
    events = []

    if enemies:
        target = random.choice(enemies)
        events.append(Event(
            type=EventType.DAMAGE,
            payload={'target': target, 'amount': 3, 'source': obj.id, 'from_spell': True},
            source=obj.id
        ))

    player = state.players.get(obj.controller)
    if player:
        player.overloaded_mana += 1

    return events


LIGHTNING_BOLT = make_spell(
    name="Lightning Bolt",
    mana_cost="{1}",
    text="Deal 3 damage. Overload: (1).",
    spell_effect=lightning_bolt_effect
)


def feral_spirit_effect(obj: GameObject, state: GameState, targets: list) -> list[Event]:
    """Summon two 2/3 Spirit Wolves with Taunt. Overload: (2)."""
    events = [
        Event(
            type=EventType.CREATE_TOKEN,
            payload={
                'controller': obj.controller,
                'token': {
                    'name': 'Spirit Wolf',
                    'power': 2,
                    'toughness': 3,
                    'types': {CardType.MINION},
                    'keywords': {'taunt'}
                }
            },
            source=obj.id
        ),
        Event(
            type=EventType.CREATE_TOKEN,
            payload={
                'controller': obj.controller,
                'token': {
                    'name': 'Spirit Wolf',
                    'power': 2,
                    'toughness': 3,
                    'types': {CardType.MINION},
                    'keywords': {'taunt'}
                }
            },
            source=obj.id
        )
    ]

    player = state.players.get(obj.controller)
    if player:
        player.overloaded_mana += 2

    return events


FERAL_SPIRIT = make_spell(
    name="Feral Spirit",
    mana_cost="{3}",
    text="Summon two 2/3 Spirit Wolves with Taunt. Overload: (2).",
    spell_effect=feral_spirit_effect
)


def lava_burst_effect(obj: GameObject, state: GameState, targets: list) -> list[Event]:
    """Deal 5 damage. Overload: (2)."""
    enemies = get_enemy_targets(obj, state)
    events = []

    if enemies:
        target = random.choice(enemies)
        events.append(Event(
            type=EventType.DAMAGE,
            payload={'target': target, 'amount': 5, 'source': obj.id, 'from_spell': True},
            source=obj.id
        ))

    player = state.players.get(obj.controller)
    if player:
        player.overloaded_mana += 2

    return events


LAVA_BURST = make_spell(
    name="Lava Burst",
    mana_cost="{3}",
    text="Deal 5 damage. Overload: (2).",
    spell_effect=lava_burst_effect
)


def bloodlust_effect(obj: GameObject, state: GameState, targets: list) -> list[Event]:
    """Give your minions +3 Attack this turn."""
    events = []
    for mid in get_friendly_minions(obj, state, exclude_self=False):
        events.append(Event(
            type=EventType.PT_MODIFICATION,
            payload={'object_id': mid, 'power_mod': 3, 'toughness_mod': 0, 'duration': 'end_of_turn'},
            source=obj.id
        ))
    return events


BLOODLUST = make_spell(
    name="Bloodlust",
    mana_cost="{5}",
    text="Give your minions +3 Attack this turn.",
    spell_effect=bloodlust_effect
)


def fire_elemental_effect(obj: GameObject, state: GameState) -> list[Event]:
    """Battlecry: Deal 3 damage."""
    enemies = get_enemy_targets(obj, state)
    if enemies:
        target = random.choice(enemies)
        return [Event(
            type=EventType.DAMAGE,
            payload={'target': target, 'amount': 3, 'source': obj.id},
            source=obj.id
        )]
    return []


FIRE_ELEMENTAL = make_minion(
    name="Fire Elemental",
    attack=6,
    health=5,
    mana_cost="{6}",
    subtypes={"Elemental"},
    text="Battlecry: Deal 3 damage.",
    battlecry=fire_elemental_effect
)


# ============================================================================
# CLASSIC SHAMAN CARDS
# ============================================================================

def earth_shock_effect(obj: GameObject, state: GameState, targets: list) -> list[Event]:
    """Silence a minion, then deal 1 damage to it. Overload: (1)."""
    enemies = get_enemy_minions(obj, state)
    events = []

    if enemies:
        target = random.choice(enemies)
        events.append(Event(
            type=EventType.SILENCE_TARGET,
            payload={'target': target},
            source=obj.id
        ))
        events.append(Event(
            type=EventType.DAMAGE,
            payload={'target': target, 'amount': 1, 'source': obj.id, 'from_spell': True},
            source=obj.id
        ))

    player = state.players.get(obj.controller)
    if player:
        player.overloaded_mana += 1

    return events


EARTH_SHOCK = make_spell(
    name="Earth Shock",
    mana_cost="{1}",
    text="Silence a minion, then deal 1 damage to it. Overload: (1).",
    spell_effect=earth_shock_effect
)


def forked_lightning_effect(obj: GameObject, state: GameState, targets: list) -> list[Event]:
    """Deal 2 damage to 2 random enemy minions. Overload: (2)."""
    enemies = get_enemy_minions(obj, state)
    events = []

    if enemies:
        # Pick up to 2 random targets
        targets_to_hit = random.sample(enemies, min(2, len(enemies)))
        for target in targets_to_hit:
            events.append(Event(
                type=EventType.DAMAGE,
                payload={'target': target, 'amount': 2, 'source': obj.id, 'from_spell': True},
                source=obj.id
            ))

    player = state.players.get(obj.controller)
    if player:
        player.overloaded_mana += 2

    return events


FORKED_LIGHTNING = make_spell(
    name="Forked Lightning",
    mana_cost="{1}",
    text="Deal 2 damage to 2 random enemy minions. Overload: (2).",
    spell_effect=forked_lightning_effect
)


def lightning_storm_effect(obj: GameObject, state: GameState, targets: list) -> list[Event]:
    """Deal 2-3 damage to all enemy minions. Overload: (2)."""
    events = []

    for mid in get_enemy_minions(obj, state):
        damage = random.choice([2, 3])
        events.append(Event(
            type=EventType.DAMAGE,
            payload={'target': mid, 'amount': damage, 'source': obj.id, 'from_spell': True},
            source=obj.id
        ))

    player = state.players.get(obj.controller)
    if player:
        player.overloaded_mana += 2

    return events


LIGHTNING_STORM = make_spell(
    name="Lightning Storm",
    mana_cost="{3}",
    text="Deal 2-3 damage to all enemy minions. Overload: (2).",
    spell_effect=lightning_storm_effect
)


def stormforged_axe_setup(obj, state):
    # Apply overload immediately when weapon is equipped
    player = state.players.get(obj.controller)
    if player:
        player.overloaded_mana += 1
    return []


STORMFORGED_AXE = make_weapon(
    name="Stormforged Axe",
    attack=2,
    durability=3,
    mana_cost="{2}",
    text="Overload: (1).",
    setup_interceptors=stormforged_axe_setup
)


UNBOUND_ELEMENTAL = make_minion(
    name="Unbound Elemental",
    attack=2,
    health=4,
    mana_cost="{3}",
    subtypes={"Elemental"},
    text="Whenever you play a card with Overload, gain +1/+1."
)


def mana_tide_totem_setup(obj: GameObject, state: GameState) -> list:
    """At the end of your turn, draw a card."""
    def draw_effect(event: Event, s: GameState) -> list[Event]:
        return [Event(
            type=EventType.DRAW,
            payload={'player': obj.controller, 'count': 1},
            source=obj.id
        )]

    return [make_end_of_turn_trigger(obj, draw_effect)]


MANA_TIDE_TOTEM = make_minion(
    name="Mana Tide Totem",
    attack=0,
    health=3,
    mana_cost="{3}",
    subtypes={"Totem"},
    text="At the end of your turn, draw a card.",
    setup_interceptors=mana_tide_totem_setup
)


def earth_elemental_on_play(obj: GameObject, state: GameState) -> list[Event]:
    """Overload: (3)."""
    player = state.players.get(obj.controller)
    if player:
        player.overloaded_mana += 3
    return []


EARTH_ELEMENTAL = make_minion(
    name="Earth Elemental",
    attack=7,
    health=8,
    mana_cost="{5}",
    subtypes={"Elemental"},
    keywords={"taunt"},
    text="Taunt. Overload: (3).",
    battlecry=earth_elemental_on_play
)


def doomhammer_setup(obj, state):
    # Apply overload immediately when weapon is equipped
    player = state.players.get(obj.controller)
    if player:
        player.overloaded_mana += 2
    return []


DOOMHAMMER = make_weapon(
    name="Doomhammer",
    attack=2,
    durability=8,
    mana_cost="{5}",
    text="Windfury. Overload: (2).",
    setup_interceptors=doomhammer_setup
)


AL_AKIR_THE_WINDLORD = make_minion(
    name="Al'Akir the Windlord",
    attack=3,
    health=5,
    mana_cost="{8}",
    subtypes={"Elemental"},
    keywords={"charge", "taunt"},
    text="Windfury, Charge, Divine Shield, Taunt.",
)


def far_sight_effect(obj: GameObject, state: GameState, targets: list) -> list[Event]:
    """Draw a card. It costs (3) less. (Simplified: draw a card)."""
    return [Event(
        type=EventType.DRAW,
        payload={'player': obj.controller, 'count': 1},
        source=obj.id
    )]


FAR_SIGHT = make_spell(
    name="Far Sight",
    mana_cost="{3}",
    text="Draw a card. It costs (3) less.",
    spell_effect=far_sight_effect
)


ANCESTRAL_SPIRIT = make_spell(
    name="Ancestral Spirit",
    mana_cost="{2}",
    text="Give a minion \"Deathrattle: Resummon this minion.\"",
    spell_effect=lambda obj, state, targets: []  # Text only for now
)


def ancestral_healing_effect(obj: GameObject, state: GameState, targets: list) -> list[Event]:
    """Restore a minion to full Health and give it Taunt."""
    all_minions = get_all_minions(state)
    if not all_minions:
        return []

    target_id = random.choice(all_minions)
    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    # Heal to full
    target.state.damage = 0

    # Grant Taunt
    if not target.characteristics.abilities:
        target.characteristics.abilities = []
    target.characteristics.abilities.append({'keyword': 'taunt'})

    return [Event(
        type=EventType.LIFE_CHANGE,
        payload={'target': target_id, 'amount': 999, 'source': obj.id},
        source=obj.id
    )]


ANCESTRAL_HEALING = make_spell(
    name="Ancestral Healing",
    mana_cost="{0}",
    text="Restore a minion to full Health and give it Taunt.",
    spell_effect=ancestral_healing_effect
)


def dust_devil_on_play(obj: GameObject, state: GameState) -> list[Event]:
    """Overload: (2)."""
    player = state.players.get(obj.controller)
    if player:
        player.overloaded_mana += 2
    return []


DUST_DEVIL = make_minion(
    name="Dust Devil",
    attack=3,
    health=1,
    mana_cost="{1}",
    subtypes={"Elemental"},
    text="Windfury. Overload: (2).",
    battlecry=dust_devil_on_play
)


# ============================================================================
# CARD LISTS
# ============================================================================

SHAMAN_BASIC = [
    FROST_SHOCK,
    ROCKBITER_WEAPON,
    WINDFURY_SPELL,
    FLAMETONGUE_TOTEM,
    HEX,
    LIGHTNING_BOLT,
    FERAL_SPIRIT,
    LAVA_BURST,
    BLOODLUST,
    FIRE_ELEMENTAL,
]

SHAMAN_CLASSIC = [
    EARTH_SHOCK,
    FORKED_LIGHTNING,
    LIGHTNING_STORM,
    STORMFORGED_AXE,
    UNBOUND_ELEMENTAL,
    MANA_TIDE_TOTEM,
    EARTH_ELEMENTAL,
    DOOMHAMMER,
    AL_AKIR_THE_WINDLORD,
    FAR_SIGHT,
    ANCESTRAL_SPIRIT,
    ANCESTRAL_HEALING,
    DUST_DEVIL,
]

SHAMAN_CARDS = SHAMAN_BASIC + SHAMAN_CLASSIC
