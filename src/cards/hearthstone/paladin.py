"""Hearthstone Paladin Cards - Basic + Classic"""
import random
from src.engine.game import make_minion, make_spell, make_weapon, make_secret
from src.engine.types import Event, EventType, CardType, GameObject, GameState, ZoneType
from src.cards.interceptor_helpers import (
    get_enemy_targets, get_enemy_minions, get_friendly_minions, get_enemy_hero_id,
    other_friendly_minions, make_static_pt_boost
)

# Re-import from classic.py
from src.cards.hearthstone.classic import CONSECRATION, TRUESILVER_CHAMPION


# ============================================================================
# BASIC PALADIN CARDS
# ============================================================================

def blessing_of_might_effect(obj, state, targets):
    """Give a random friendly minion +3 Attack"""
    friendly = get_friendly_minions(obj, state, exclude_self=False)
    if friendly:
        target = random.choice(friendly)
        return [Event(type=EventType.PT_MODIFICATION,
                      payload={'object_id': target, 'power_mod': 3, 'toughness_mod': 0, 'duration': 'permanent'},
                      source=obj.id)]
    return []

BLESSING_OF_MIGHT = make_spell(
    name="Blessing of Might",
    mana_cost="{1}",
    text="Give a minion +3 Attack.",
    spell_effect=blessing_of_might_effect
)


def hand_of_protection_effect(obj, state, targets):
    """Give a random friendly minion Divine Shield"""
    friendly = get_friendly_minions(obj, state, exclude_self=False)
    if friendly:
        target = random.choice(friendly)
        target_obj = state.objects.get(target)
        if target_obj:
            target_obj.state.divine_shield = True
    return []

HAND_OF_PROTECTION = make_spell(
    name="Hand of Protection",
    mana_cost="{1}",
    text="Give a minion Divine Shield.",
    spell_effect=hand_of_protection_effect
)


def humility_effect(obj, state, targets):
    """Change a minion's Attack to 1"""
    enemies = get_enemy_minions(obj, state)
    if enemies:
        target = random.choice(enemies)
        target_obj = state.objects.get(target)
        if target_obj:
            target_obj.characteristics.power = 1
    return []

HUMILITY = make_spell(
    name="Humility",
    mana_cost="{1}",
    text="Change a minion's Attack to 1.",
    spell_effect=humility_effect
)


def holy_light_effect(obj, state, targets):
    """Restore 6 Health to your hero"""
    return [Event(type=EventType.LIFE_CHANGE,
                  payload={'player': obj.controller, 'amount': 6},
                  source=obj.id)]

HOLY_LIGHT = make_spell(
    name="Holy Light",
    mana_cost="{2}",
    text="Restore 6 Health.",
    spell_effect=holy_light_effect
)


def blessing_of_kings_effect(obj, state, targets):
    """Give a random friendly minion +4/+4"""
    friendly = get_friendly_minions(obj, state, exclude_self=False)
    if friendly:
        target = random.choice(friendly)
        return [Event(type=EventType.PT_MODIFICATION,
                      payload={'object_id': target, 'power_mod': 4, 'toughness_mod': 4, 'duration': 'permanent'},
                      source=obj.id)]
    return []

BLESSING_OF_KINGS = make_spell(
    name="Blessing of Kings",
    mana_cost="{4}",
    text="Give a minion +4/+4.",
    spell_effect=blessing_of_kings_effect
)


def hammer_of_wrath_effect(obj, state, targets):
    """Deal 3 damage. Draw a card."""
    events = []
    enemies = get_enemy_targets(obj, state)
    if enemies:
        target = random.choice(enemies)
        events.append(Event(type=EventType.DAMAGE,
                           payload={'target': target, 'amount': 3, 'source': obj.id, 'from_spell': True},
                           source=obj.id))
    events.append(Event(type=EventType.DRAW,
                       payload={'player': obj.controller, 'count': 1},
                       source=obj.id))
    return events

HAMMER_OF_WRATH = make_spell(
    name="Hammer of Wrath",
    mana_cost="{4}",
    text="Deal 3 damage. Draw a card.",
    spell_effect=hammer_of_wrath_effect
)


def guardian_of_kings_battlecry(obj, state):
    """Restore 6 Health to your hero"""
    return [Event(type=EventType.LIFE_CHANGE,
                  payload={'player': obj.controller, 'amount': 6},
                  source=obj.id)]

GUARDIAN_OF_KINGS = make_minion(
    name="Guardian of Kings",
    attack=5,
    health=6,
    mana_cost="{7}",
    text="Battlecry: Restore 6 Health to your hero.",
    battlecry=guardian_of_kings_battlecry
)


# ============================================================================
# CLASSIC PALADIN CARDS
# ============================================================================

def noble_sacrifice_filter(event, state):
    """Trigger when an enemy attacks"""
    return event.type == EventType.ATTACK_DECLARED

def noble_sacrifice_effect(obj, state):
    """Summon a 2/1 Defender as the new target"""
    return [Event(type=EventType.CREATE_TOKEN, payload={
        'controller': obj.controller,
        'token': {'name': 'Defender', 'power': 2, 'toughness': 1, 'types': {CardType.MINION}}
    }, source=obj.id)]

NOBLE_SACRIFICE = make_secret(
    name="Noble Sacrifice",
    mana_cost="{1}",
    text="Secret: When an enemy attacks, summon a 2/1 Defender as the new target.",
    trigger_filter=noble_sacrifice_filter,
    trigger_effect=noble_sacrifice_effect
)


def redemption_filter(event, state):
    """Trigger when a friendly minion dies"""
    return event.type == EventType.OBJECT_DESTROYED

def redemption_effect(obj, state):
    """Return the minion to life with 1 Health"""
    # Simplified: create a 1/1 token (actual implementation would copy the minion)
    return [Event(type=EventType.CREATE_TOKEN, payload={
        'controller': obj.controller,
        'token': {'name': 'Redeemed Minion', 'power': 1, 'toughness': 1, 'types': {CardType.MINION}}
    }, source=obj.id)]

REDEMPTION = make_secret(
    name="Redemption",
    mana_cost="{1}",
    text="Secret: When a friendly minion dies, return it to life with 1 Health.",
    trigger_filter=redemption_filter,
    trigger_effect=redemption_effect
)


def repentance_filter(event, state):
    """Trigger when opponent plays a minion"""
    return event.type == EventType.ZONE_CHANGE

def repentance_effect(obj, state):
    """Reduce the minion's Health to 1"""
    # Simplified: deal damage to reduce health to 1
    return []

REPENTANCE = make_secret(
    name="Repentance",
    mana_cost="{1}",
    text="Secret: When your opponent plays a minion, reduce its Health to 1.",
    trigger_filter=repentance_filter,
    trigger_effect=repentance_effect
)


def avenge_filter(event, state):
    """Trigger when a friendly minion dies"""
    return event.type == EventType.OBJECT_DESTROYED

def avenge_effect(obj, state):
    """Give a random friendly minion +3/+2"""
    friendly = get_friendly_minions(obj, state, exclude_self=True)
    if friendly:
        target = random.choice(friendly)
        return [Event(type=EventType.PT_MODIFICATION,
                     payload={'object_id': target, 'power_mod': 3, 'toughness_mod': 2, 'duration': 'permanent'},
                     source=obj.id)]
    return []

AVENGE = make_secret(
    name="Avenge",
    mana_cost="{1}",
    text="Secret: When a friendly minion dies, give a random friendly minion +3/+2.",
    trigger_filter=avenge_filter,
    trigger_effect=avenge_effect
)


def equality_effect(obj, state, targets):
    """Change the Health of ALL minions to 1"""
    from src.cards.interceptor_helpers import get_all_minions
    for mid in get_all_minions(state):
        m = state.objects.get(mid)
        if m:
            m.characteristics.toughness = 1
            m.state.damage = 0
    return []

EQUALITY = make_spell(
    name="Equality",
    mana_cost="{2}",
    text="Change the Health of ALL minions to 1.",
    spell_effect=equality_effect
)


def aldor_peacekeeper_battlecry(obj, state):
    """Change an enemy minion's Attack to 1"""
    enemies = get_enemy_minions(obj, state)
    if enemies:
        target = random.choice(enemies)
        target_obj = state.objects.get(target)
        if target_obj:
            target_obj.characteristics.power = 1
    return []

ALDOR_PEACEKEEPER = make_minion(
    name="Aldor Peacekeeper",
    attack=3,
    health=3,
    mana_cost="{3}",
    text="Battlecry: Change an enemy minion's Attack to 1.",
    battlecry=aldor_peacekeeper_battlecry
)


def divine_favor_effect(obj, state, targets):
    """Draw cards until you have as many in hand as your opponent (simplified: draw 2)"""
    return [Event(type=EventType.DRAW,
                  payload={'player': obj.controller, 'count': 2},
                  source=obj.id)]

DIVINE_FAVOR = make_spell(
    name="Divine Favor",
    mana_cost="{3}",
    text="Draw cards until you have as many in hand as your opponent.",
    spell_effect=divine_favor_effect
)


SWORD_OF_JUSTICE = make_weapon(
    name="Sword of Justice",
    attack=1,
    durability=5,
    mana_cost="{3}",
    text="Whenever you summon a minion, give it +1/+1 and this loses 1 Durability."
)


def avenging_wrath_effect(obj, state, targets):
    """Deal 8 damage randomly split among all enemies"""
    events = []
    for _ in range(8):
        enemies = get_enemy_targets(obj, state)
        if enemies:
            target = random.choice(enemies)
            events.append(Event(type=EventType.DAMAGE,
                               payload={'target': target, 'amount': 1, 'source': obj.id, 'from_spell': True},
                               source=obj.id))
    return events

AVENGING_WRATH = make_spell(
    name="Avenging Wrath",
    mana_cost="{6}",
    text="Deal 8 damage randomly split among all enemies.",
    spell_effect=avenging_wrath_effect
)


def lay_on_hands_effect(obj, state, targets):
    """Restore 8 Health. Draw 3 cards."""
    return [
        Event(type=EventType.LIFE_CHANGE,
              payload={'player': obj.controller, 'amount': 8},
              source=obj.id),
        Event(type=EventType.DRAW,
              payload={'player': obj.controller, 'count': 3},
              source=obj.id)
    ]

LAY_ON_HANDS = make_spell(
    name="Lay on Hands",
    mana_cost="{8}",
    text="Restore 8 Health. Draw 3 cards.",
    spell_effect=lay_on_hands_effect
)


def tirion_deathrattle(obj, state):
    """Equip a 5/3 Ashbringer"""
    return [Event(type=EventType.WEAPON_EQUIP, payload={
        'player': obj.controller, 'weapon_attack': 5, 'weapon_durability': 3, 'weapon_name': 'Ashbringer'
    }, source=obj.id)]

TIRION_FORDRING = make_minion(
    name="Tirion Fordring",
    attack=6,
    health=6,
    mana_cost="{8}",
    text="Divine Shield, Taunt. Deathrattle: Equip a 5/3 Ashbringer.",
    keywords={'divine_shield', 'taunt'},
    deathrattle=tirion_deathrattle
)


# ============================================================================
# CARD LISTS
# ============================================================================

PALADIN_BASIC = [
    BLESSING_OF_MIGHT,
    HAND_OF_PROTECTION,
    HUMILITY,
    HOLY_LIGHT,
    BLESSING_OF_KINGS,
    CONSECRATION,  # Re-imported from classic.py
    HAMMER_OF_WRATH,
    TRUESILVER_CHAMPION,  # Re-imported from classic.py
    GUARDIAN_OF_KINGS,
]

PALADIN_CLASSIC = [
    NOBLE_SACRIFICE,
    REDEMPTION,
    REPENTANCE,
    AVENGE,
    EQUALITY,
    ALDOR_PEACEKEEPER,
    DIVINE_FAVOR,
    SWORD_OF_JUSTICE,
    AVENGING_WRATH,
    LAY_ON_HANDS,
    TIRION_FORDRING,
]

PALADIN_CARDS = PALADIN_BASIC + PALADIN_CLASSIC
