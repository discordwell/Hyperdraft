"""Hearthstone Rogue Cards - Basic + Classic"""
import random
from src.engine.game import make_minion, make_spell, make_weapon
from src.engine.types import Event, EventType, CardType, GameObject, GameState, ZoneType
from src.cards.interceptor_helpers import (
    get_enemy_targets, get_enemy_minions, get_friendly_minions, get_enemy_hero_id
)

# Re-import from classic.py
from src.cards.hearthstone.classic import BACKSTAB, SPRINT


# ============================================================================
# BASIC ROGUE CARDS
# ============================================================================

# DEADLY_POISON - 1 mana spell, Give your weapon +2 Attack
def deadly_poison_effect(obj, state, targets):
    """Increase weapon attack by 2"""
    player = state.players.get(obj.controller)
    if player and player.weapon_attack > 0:
        player.weapon_attack += 2
    return []

DEADLY_POISON = make_spell(
    name="Deadly Poison",
    mana_cost="{1}",
    text="Give your weapon +2 Attack.",
    spell_effect=deadly_poison_effect
)

# SINISTER_STRIKE - 1 mana spell, Deal 3 damage to enemy hero
def sinister_strike_effect(obj, state, targets):
    """Deal 3 damage to enemy hero"""
    enemy_hero = get_enemy_hero_id(obj, state)
    if enemy_hero:
        return [Event(
            type=EventType.DAMAGE,
            payload={'target': enemy_hero, 'amount': 3, 'source': obj.id, 'from_spell': True},
            source=obj.id
        )]
    return []

SINISTER_STRIKE = make_spell(
    name="Sinister Strike",
    mana_cost="{1}",
    text="Deal 3 damage to the enemy hero.",
    spell_effect=sinister_strike_effect
)

# SAP - 2 mana spell, Return an enemy minion to hand
def sap_effect(obj, state, targets):
    """Return enemy minion to hand"""
    enemies = get_enemy_minions(obj, state)
    if enemies:
        target = random.choice(enemies)
        return [Event(
            type=EventType.RETURN_TO_HAND,
            payload={'object_id': target},
            source=obj.id
        )]
    return []

SAP = make_spell(
    name="Sap",
    mana_cost="{2}",
    text="Return an enemy minion to its owner's hand.",
    spell_effect=sap_effect
)

# SHIV - 2 mana spell, Deal 1 damage, draw a card
def shiv_effect(obj, state, targets):
    """Deal 1 damage and draw a card"""
    events = []
    enemies = get_enemy_targets(obj, state)
    if enemies:
        target = random.choice(enemies)
        events.append(Event(
            type=EventType.DAMAGE,
            payload={'target': target, 'amount': 1, 'source': obj.id, 'from_spell': True},
            source=obj.id
        ))
    events.append(Event(
        type=EventType.DRAW,
        payload={'player': obj.controller, 'count': 1},
        source=obj.id
    ))
    return events

SHIV = make_spell(
    name="Shiv",
    mana_cost="{2}",
    text="Deal 1 damage. Draw a card.",
    spell_effect=shiv_effect
)

# FAN_OF_KNIVES - 3 mana spell, Deal 1 to all enemy minions, draw a card
def fan_of_knives_effect(obj, state, targets):
    """Deal 1 damage to all enemy minions and draw a card"""
    events = []
    enemies = get_enemy_minions(obj, state)
    for enemy_id in enemies:
        events.append(Event(
            type=EventType.DAMAGE,
            payload={'target': enemy_id, 'amount': 1, 'source': obj.id, 'from_spell': True},
            source=obj.id
        ))
    events.append(Event(
        type=EventType.DRAW,
        payload={'player': obj.controller, 'count': 1},
        source=obj.id
    ))
    return events

FAN_OF_KNIVES = make_spell(
    name="Fan of Knives",
    mana_cost="{3}",
    text="Deal 1 damage to all enemy minions. Draw a card.",
    spell_effect=fan_of_knives_effect
)

# ASSASSINATE - 5 mana spell, Destroy an enemy minion
def assassinate_effect(obj, state, targets):
    """Destroy an enemy minion"""
    enemies = get_enemy_minions(obj, state)
    if enemies:
        target = random.choice(enemies)
        return [Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': target, 'reason': 'assassinate'},
            source=obj.id
        )]
    return []

ASSASSINATE = make_spell(
    name="Assassinate",
    mana_cost="{5}",
    text="Destroy an enemy minion.",
    spell_effect=assassinate_effect
)

# ASSASSINS_BLADE - 3/4 weapon, cost 5
ASSASSINS_BLADE = make_weapon(
    name="Assassin's Blade",
    mana_cost="{5}",
    attack=3,
    durability=4,
    text=""
)

# VANISH - 6 mana spell, Return all minions to their owner's hand
def vanish_effect(obj, state, targets):
    """Return all minions to hand"""
    events = []
    # Get all minions on board
    for zone_id, zone in state.zones.items():
        if zone.type == ZoneType.BATTLEFIELD:
            for obj_id in list(zone.objects):
                game_obj = state.objects.get(obj_id)
                if game_obj and CardType.MINION in game_obj.characteristics.types:
                    events.append(Event(
                        type=EventType.RETURN_TO_HAND,
                        payload={'object_id': obj_id},
                        source=obj.id
                    ))
    return events

VANISH = make_spell(
    name="Vanish",
    mana_cost="{6}",
    text="Return all minions to their owner's hand.",
    spell_effect=vanish_effect
)


# ============================================================================
# CLASSIC ROGUE CARDS
# ============================================================================

# COLD_BLOOD - 1 mana spell, Give +2 Attack. Combo: +4 instead
def cold_blood_effect(obj, state, targets):
    """Give a minion +2 Attack. Combo: +4 Attack instead"""
    player = state.players.get(obj.controller)
    combo = player and player.cards_played_this_turn > 0
    bonus = 4 if combo else 2

    friendly = get_friendly_minions(obj, state, exclude_self=False)
    if friendly:
        target = random.choice(friendly)
        return [Event(
            type=EventType.PT_MODIFICATION,
            payload={'object_id': target, 'power_mod': bonus, 'toughness_mod': 0, 'duration': 'permanent'},
            source=obj.id
        )]
    return []

COLD_BLOOD = make_spell(
    name="Cold Blood",
    mana_cost="{1}",
    text="Give a minion +2 Attack. Combo: +4 Attack instead.",
    spell_effect=cold_blood_effect
)

# CONCEAL - 1 mana spell, Give all friendly minions Stealth until your next turn
def conceal_effect(obj, state, targets):
    """Give all friendly minions Stealth until your next turn."""
    friendly = get_friendly_minions(obj, state, exclude_self=False)
    for mid in friendly:
        m = state.objects.get(mid)
        if m:
            m.state.stealth = True
    return []

CONCEAL = make_spell(
    name="Conceal",
    mana_cost="{1}",
    text="Give your minions Stealth until your next turn.",
    spell_effect=conceal_effect
)

# BETRAYAL - 2 mana spell, Enemy minion deals its damage to the minions next to it
def betrayal_effect(obj, state, targets):
    """An enemy minion deals its damage to the minions next to it."""
    from src.cards.interceptor_helpers import get_adjacent_enemy_minions
    enemy_minions = get_enemy_minions(obj, state)
    if not enemy_minions:
        return []
    target_id = targets[0] if targets else random.choice(enemy_minions)
    target = state.objects.get(target_id)
    if not target:
        return []
    adjacent = get_adjacent_enemy_minions(target_id, state)
    damage = target.characteristics.power or 0
    events = []
    for adj_id in adjacent:
        events.append(Event(
            type=EventType.DAMAGE,
            payload={'target': adj_id, 'amount': damage, 'source': target_id},
            source=obj.id
        ))
    return events

BETRAYAL = make_spell(
    name="Betrayal",
    mana_cost="{2}",
    text="An enemy minion deals its damage to the minions next to it.",
    spell_effect=betrayal_effect
)

# EVISCERATE - 2 mana spell, Deal 2 damage. Combo: 4 damage
def eviscerate_effect(obj, state, targets):
    """Deal 2 damage. Combo: Deal 4 damage instead"""
    player = state.players.get(obj.controller)
    combo = player and player.cards_played_this_turn > 0
    damage = 4 if combo else 2

    enemies = get_enemy_targets(obj, state)
    if enemies:
        target = random.choice(enemies)
        return [Event(
            type=EventType.DAMAGE,
            payload={'target': target, 'amount': damage, 'source': obj.id, 'from_spell': True},
            source=obj.id
        )]
    return []

EVISCERATE = make_spell(
    name="Eviscerate",
    mana_cost="{2}",
    text="Deal 2 damage. Combo: Deal 4 damage instead.",
    spell_effect=eviscerate_effect
)

# BLADE_FLURRY - 4 mana spell, Destroy weapon and deal its damage to all enemies
def blade_flurry_effect(obj, state, targets):
    """Destroy your weapon and deal its damage to all enemy minions"""
    events = []
    player = state.players.get(obj.controller)
    if player and player.weapon_attack > 0:
        damage = player.weapon_attack
        # Deal damage to all enemy minions
        enemies = get_enemy_minions(obj, state)
        for enemy_id in enemies:
            events.append(Event(
                type=EventType.DAMAGE,
                payload={'target': enemy_id, 'amount': damage, 'source': obj.id, 'from_spell': True},
                source=obj.id
            ))
        # Destroy weapon
        player.weapon_attack = 0
        player.weapon_durability = 0
    return events

BLADE_FLURRY = make_spell(
    name="Blade Flurry",
    mana_cost="{4}",
    text="Destroy your weapon and deal its damage to all enemy minions.",
    spell_effect=blade_flurry_effect
)

# DEFIAS_RINGLEADER - 2/2, cost 2, Combo: Summon 2/1 Defias Bandit
def defias_ringleader_battlecry(obj, state):
    """Combo: Summon a 2/1 Defias Bandit"""
    player = state.players.get(obj.controller)
    if player and player.cards_played_this_turn > 0:
        return [Event(
            type=EventType.CREATE_TOKEN,
            payload={
                'controller': obj.controller,
                'token': {'name': 'Defias Bandit', 'power': 2, 'toughness': 1, 'types': {CardType.MINION}}
            },
            source=obj.id
        )]
    return []

DEFIAS_RINGLEADER = make_minion(
    name="Defias Ringleader",
    mana_cost="{2}",
    attack=2,
    health=2,
    text="Combo: Summon a 2/1 Defias Bandit.",
    battlecry=defias_ringleader_battlecry
)

# PATIENT_ASSASSIN - 1/1, cost 2, Stealth. Destroy any minion damaged by this minion.
def patient_assassin_setup(obj, state):
    """Destroy any minion damaged by this minion."""
    from src.cards.interceptor_helpers import make_damage_trigger

    def destroy_damaged(event, s):
        target_id = event.payload.get('target')
        target = s.objects.get(target_id)
        if target and CardType.MINION in target.characteristics.types:
            return [Event(
                type=EventType.OBJECT_DESTROYED,
                payload={'object_id': target_id, 'reason': 'patient_assassin'},
                source=obj.id
            )]
        return []

    return [make_damage_trigger(obj, destroy_damaged)]

PATIENT_ASSASSIN = make_minion(
    name="Patient Assassin",
    mana_cost="{2}",
    attack=1,
    health=1,
    text="Stealth. Destroy any minion damaged by this minion.",
    keywords={"stealth"},
    setup_interceptors=patient_assassin_setup
)

# SI7_AGENT - 3/3, cost 3, Combo: Deal 2 damage
def si7_agent_battlecry(obj, state):
    """Combo: Deal 2 damage"""
    player = state.players.get(obj.controller)
    if player and player.cards_played_this_turn > 0:
        enemies = get_enemy_targets(obj, state)
        if enemies:
            target = random.choice(enemies)
            return [Event(
                type=EventType.DAMAGE,
                payload={'target': target, 'amount': 2, 'source': obj.id},
                source=obj.id
            )]
    return []

SI7_AGENT = make_minion(
    name="SI:7 Agent",
    mana_cost="{3}",
    attack=3,
    health=3,
    text="Combo: Deal 2 damage.",
    battlecry=si7_agent_battlecry
)

# PERDITIONS_BLADE - 2/2 weapon, cost 3, Battlecry: Deal 1 damage. Combo: Deal 2 instead.
def perditions_blade_setup(obj, state):
    """Battlecry: Deal 1 damage. Combo: Deal 2 instead."""
    from src.engine.types import Interceptor, InterceptorPriority, InterceptorAction, InterceptorResult, new_id

    def etb_filter(event, s):
        return (event.type == EventType.ZONE_CHANGE and
                event.payload.get('object_id') == obj.id and
                event.payload.get('to_zone_type') == ZoneType.BATTLEFIELD)

    def etb_handler(event, s):
        player = s.players.get(obj.controller)
        combo = player and player.cards_played_this_turn > 0
        damage = 2 if combo else 1
        enemies = get_enemy_targets(obj, s)
        if enemies:
            target = random.choice(enemies)
            return InterceptorResult(
                action=InterceptorAction.REACT,
                new_events=[Event(
                    type=EventType.DAMAGE,
                    payload={'target': target, 'amount': damage, 'source': obj.id},
                    source=obj.id
                )]
            )
        return InterceptorResult(action=InterceptorAction.PASS)

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=etb_filter,
        handler=etb_handler,
        duration='while_on_battlefield'
    )]

PERDITIONS_BLADE = make_weapon(
    name="Perdition's Blade",
    mana_cost="{3}",
    attack=2,
    durability=2,
    text="Battlecry: Deal 1 damage. Combo: Deal 2 instead.",
    setup_interceptors=perditions_blade_setup
)

# MASTER_OF_DISGUISE - 4/4, cost 4, Battlecry: Give Stealth (text only)
def master_of_disguise_battlecry(obj, state):
    """Battlecry: Give a friendly minion Stealth (text only)"""
    return []

MASTER_OF_DISGUISE = make_minion(
    name="Master of Disguise",
    mana_cost="{4}",
    attack=4,
    health=4,
    text="Battlecry: Give a friendly minion Stealth.",
    battlecry=master_of_disguise_battlecry
)

# KIDNAPPER - 5/3, cost 6, Combo: Return enemy minion to hand
def kidnapper_battlecry(obj, state):
    """Combo: Return an enemy minion to its owner's hand"""
    player = state.players.get(obj.controller)
    if player and player.cards_played_this_turn > 0:
        enemies = get_enemy_minions(obj, state)
        if enemies:
            target = random.choice(enemies)
            return [Event(
                type=EventType.RETURN_TO_HAND,
                payload={'object_id': target},
                source=obj.id
            )]
    return []

KIDNAPPER = make_minion(
    name="Kidnapper",
    mana_cost="{6}",
    attack=5,
    health=3,
    text="Combo: Return an enemy minion to its owner's hand.",
    battlecry=kidnapper_battlecry
)

# EDWIN_VANCLEEF - 2/2, cost 3, Combo: +2/+2 per card played this turn (Legendary)
def edwin_vancleef_battlecry(obj, state):
    """Combo: Gain +2/+2 for each card played earlier this turn"""
    player = state.players.get(obj.controller)
    if player and player.cards_played_this_turn > 0:
        bonus = player.cards_played_this_turn * 2
        return [Event(
            type=EventType.PT_MODIFICATION,
            payload={'object_id': obj.id, 'power_mod': bonus, 'toughness_mod': bonus, 'duration': 'permanent'},
            source=obj.id
        )]
    return []

EDWIN_VANCLEEF = make_minion(
    name="Edwin VanCleef",
    mana_cost="{3}",
    attack=2,
    health=2,
    text="Combo: Gain +2/+2 for each card played earlier this turn.",
    battlecry=edwin_vancleef_battlecry,
)

# PREPARATION - 0 mana spell, The next spell you cast this turn costs (3) less
def preparation_effect(obj, state, targets):
    """The next spell you cast this turn costs (3) less."""
    from src.cards.interceptor_helpers import add_one_shot_cost_reduction
    player = state.players.get(obj.controller)
    if player:
        add_one_shot_cost_reduction(player, CardType.SPELL, 3, duration='this_turn')
    return []

PREPARATION = make_spell(
    name="Preparation",
    mana_cost="{0}",
    text="The next spell you cast this turn costs (3) less.",
    spell_effect=preparation_effect
)

# SHADOWSTEP - 0 mana spell, Return a friendly minion to your hand. It costs (2) less.
def shadowstep_effect(obj, state, targets):
    """Return a friendly minion to your hand. It costs (2) less."""
    friendly = get_friendly_minions(obj, state, exclude_self=False)
    if friendly:
        target = random.choice(friendly)
        return [Event(
            type=EventType.RETURN_TO_HAND,
            payload={'object_id': target},
            source=obj.id
        )]
    return []

SHADOWSTEP = make_spell(
    name="Shadowstep",
    mana_cost="{0}",
    text="Return a friendly minion to your hand. It costs (2) less.",
    spell_effect=shadowstep_effect
)

# HEADCRACK - 3 mana spell, Deal 2 damage to the enemy hero
def headcrack_effect(obj, state, targets):
    """Deal 2 damage to the enemy hero."""
    hero_id = get_enemy_hero_id(obj, state)
    if hero_id:
        return [Event(
            type=EventType.DAMAGE,
            payload={'target': hero_id, 'amount': 2, 'source': obj.id, 'from_spell': True},
            source=obj.id
        )]
    return []

HEADCRACK = make_spell(
    name="Headcrack",
    mana_cost="{3}",
    text="Deal 2 damage to the enemy hero. Combo: Return this to your hand next turn.",
    spell_effect=headcrack_effect
)


# ============================================================================
# EXPORTS
# ============================================================================

ROGUE_BASIC = [
    BACKSTAB,  # Re-imported from classic.py
    DEADLY_POISON,
    SINISTER_STRIKE,
    SAP,
    SHIV,
    FAN_OF_KNIVES,
    ASSASSINATE,
    SPRINT,  # Re-imported from classic.py
    ASSASSINS_BLADE,
    VANISH,
]

ROGUE_CLASSIC = [
    COLD_BLOOD,
    CONCEAL,
    BETRAYAL,
    EVISCERATE,
    BLADE_FLURRY,
    DEFIAS_RINGLEADER,
    PATIENT_ASSASSIN,
    SI7_AGENT,
    PERDITIONS_BLADE,
    MASTER_OF_DISGUISE,
    KIDNAPPER,
    EDWIN_VANCLEEF,
    PREPARATION,
    SHADOWSTEP,
    HEADCRACK,
]

ROGUE_CARDS = ROGUE_BASIC + ROGUE_CLASSIC
