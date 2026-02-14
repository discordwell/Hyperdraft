"""Hearthstone Warlock Cards - Basic + Classic"""
import random
from src.engine.game import make_minion, make_spell
from src.engine.types import Event, EventType, CardType, GameObject, GameState, ZoneType
from src.cards.interceptor_helpers import (
    get_enemy_targets, get_enemy_minions, get_all_minions, get_enemy_hero_id,
    make_end_of_turn_trigger, make_whenever_takes_damage_trigger
)


# ============================================================================
# SPELL EFFECTS
# ============================================================================

def soulfire_effect(obj, state, targets):
    """Deal 4 damage. Discard a random card."""
    events = []
    enemies = get_enemy_targets(obj, state)
    if enemies:
        target = random.choice(enemies)
        events.append(Event(
            type=EventType.DAMAGE,
            payload={'target': target, 'amount': 4, 'source': obj.id, 'from_spell': True},
            source=obj.id
        ))
    # Discard random card
    hand_key = f"hand_{obj.controller}"
    hand = state.zones.get(hand_key)
    if hand and hand.objects:
        discard_id = random.choice(list(hand.objects))
        events.append(Event(
            type=EventType.DISCARD,
            payload={'player': obj.controller, 'card_id': discard_id},
            source=obj.id
        ))
    return events


def mortal_coil_effect(obj, state, targets):
    """Deal 1 damage to a minion. If that kills it, draw a card."""
    events = []
    enemy_minions = get_enemy_minions(obj, state)
    if enemy_minions:
        target = random.choice(enemy_minions)
        events.append(Event(
            type=EventType.DAMAGE,
            payload={'target': target, 'amount': 1, 'source': obj.id, 'from_spell': True},
            source=obj.id
        ))
        # Simplified: just draw a card
        events.append(Event(
            type=EventType.DRAW,
            payload={'player': obj.controller, 'count': 1},
            source=obj.id
        ))
    return events


def shadow_bolt_effect(obj, state, targets):
    """Deal 4 damage to a minion."""
    events = []
    enemy_minions = get_enemy_minions(obj, state)
    if enemy_minions:
        target = random.choice(enemy_minions)
        events.append(Event(
            type=EventType.DAMAGE,
            payload={'target': target, 'amount': 4, 'source': obj.id, 'from_spell': True},
            source=obj.id
        ))
    return events


def drain_life_effect(obj, state, targets):
    """Deal 2 damage. Restore 2 Health to your hero."""
    events = []
    enemies = get_enemy_targets(obj, state)
    if enemies:
        target = random.choice(enemies)
        events.append(Event(
            type=EventType.DAMAGE,
            payload={'target': target, 'amount': 2, 'source': obj.id, 'from_spell': True},
            source=obj.id
        ))
    # Heal your hero
    player = state.players.get(obj.controller)
    if player and player.hero_id:
        events.append(Event(
            type=EventType.LIFE_CHANGE,
            payload={'target': player.hero_id, 'amount': 2, 'source': obj.id},
            source=obj.id
        ))
    return events


def hellfire_effect(obj, state, targets):
    """Deal 3 damage to ALL characters."""
    events = []
    battlefield = state.zones.get('battlefield')
    if battlefield:
        for mid in list(battlefield.objects):
            m = state.objects.get(mid)
            if m and CardType.MINION in m.characteristics.types:
                events.append(Event(
                    type=EventType.DAMAGE,
                    payload={'target': mid, 'amount': 3, 'source': obj.id, 'from_spell': True},
                    source=obj.id
                ))
    # Damage all heroes
    for pid, player in state.players.items():
        if player.hero_id:
            events.append(Event(
                type=EventType.DAMAGE,
                payload={'target': player.hero_id, 'amount': 3, 'source': obj.id, 'from_spell': True},
                source=obj.id
            ))
    return events


def power_overwhelming_effect(obj, state, targets):
    """Give a friendly minion +4/+4 until end of turn."""
    events = []
    battlefield = state.zones.get('battlefield')
    friendly_minions = []
    if battlefield:
        for mid in battlefield.objects:
            m = state.objects.get(mid)
            if m and CardType.MINION in m.characteristics.types and m.controller == obj.controller:
                friendly_minions.append(mid)

    if friendly_minions:
        target = random.choice(friendly_minions)
        events.append(Event(
            type=EventType.PT_MODIFICATION,
            payload={
                'target': target,
                'power_mod': 4,
                'toughness_mod': 4,
                'duration': 'end_of_turn',
                'source': obj.id
            },
            source=obj.id
        ))
    return events


def demonfire_effect(obj, state, targets):
    """Deal 2 damage to a minion. If it's a friendly Demon, give it +2/+2 instead."""
    # Simplified: deal 2 to random enemy minion
    events = []
    enemy_minions = get_enemy_minions(obj, state)
    if enemy_minions:
        target = random.choice(enemy_minions)
        events.append(Event(
            type=EventType.DAMAGE,
            payload={'target': target, 'amount': 2, 'source': obj.id, 'from_spell': True},
            source=obj.id
        ))
    return events


def shadowflame_effect(obj, state, targets):
    """Destroy a friendly minion and deal its Attack damage to all enemy minions."""
    # Simplified: deal 3 damage to all enemy minions
    events = []
    enemy_minions = get_enemy_minions(obj, state)
    for mid in enemy_minions:
        events.append(Event(
            type=EventType.DAMAGE,
            payload={'target': mid, 'amount': 3, 'source': obj.id, 'from_spell': True},
            source=obj.id
        ))
    return events


def bane_of_doom_effect(obj, state, targets):
    """Deal 2 damage to a character. If that kills it, summon a random Demon."""
    # Simplified: deal 2 damage, summon a 6/6 Infernal token
    events = []
    enemies = get_enemy_targets(obj, state)
    if enemies:
        target = random.choice(enemies)
        events.append(Event(
            type=EventType.DAMAGE,
            payload={'target': target, 'amount': 2, 'source': obj.id, 'from_spell': True},
            source=obj.id
        ))
    # Summon 6/6 Infernal token
    events.append(Event(
        type=EventType.CREATE_TOKEN,
        payload={
            'controller': obj.controller,
            'name': 'Infernal',
            'power': 6,
            'toughness': 6,
            'mana_cost': '{6}',
            'subtypes': {'Demon'},
            'source': obj.id
        },
        source=obj.id
    ))
    return events


def siphon_soul_effect(obj, state, targets):
    """Destroy a minion. Restore 3 Health to your hero."""
    events = []
    enemy_minions = get_enemy_minions(obj, state)
    if enemy_minions:
        target = random.choice(enemy_minions)
        events.append(Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': target, 'reason': 'siphon_soul'},
            source=obj.id
        ))
    # Heal your hero
    player = state.players.get(obj.controller)
    if player and player.hero_id:
        events.append(Event(
            type=EventType.LIFE_CHANGE,
            payload={'target': player.hero_id, 'amount': 3, 'source': obj.id},
            source=obj.id
        ))
    return events


def twisting_nether_effect(obj, state, targets):
    """Destroy all minions."""
    events = []
    battlefield = state.zones.get('battlefield')
    if battlefield:
        for mid in list(battlefield.objects):
            m = state.objects.get(mid)
            if m and CardType.MINION in m.characteristics.types:
                events.append(Event(
                    type=EventType.OBJECT_DESTROYED,
                    payload={'object_id': mid, 'reason': 'twisting_nether'},
                    source=obj.id
                ))
    return events


def sense_demons_effect(obj, state, targets):
    """Draw 2 Demons from your deck. Simplified: Draw 2 cards."""
    events = []
    events.append(Event(
        type=EventType.DRAW,
        payload={'player': obj.controller, 'count': 2},
        source=obj.id
    ))
    return events


# ============================================================================
# BATTLECRY EFFECTS
# ============================================================================

def dread_infernal_battlecry(obj, state):
    """Deal 1 damage to ALL other characters."""
    events = []
    battlefield = state.zones.get('battlefield')
    if battlefield:
        for mid in list(battlefield.objects):
            if mid == obj.id:
                continue
            m = state.objects.get(mid)
            if m and CardType.MINION in m.characteristics.types:
                events.append(Event(
                    type=EventType.DAMAGE,
                    payload={'target': mid, 'amount': 1, 'source': obj.id, 'from_spell': False},
                    source=obj.id
                ))
    # Damage all heroes
    for pid, player in state.players.items():
        if player.hero_id:
            events.append(Event(
                type=EventType.DAMAGE,
                payload={'target': player.hero_id, 'amount': 1, 'source': obj.id, 'from_spell': False},
                source=obj.id
            ))
    return events


def succubus_battlecry(obj, state):
    """Discard a random card."""
    events = []
    hand_key = f"hand_{obj.controller}"
    hand = state.zones.get(hand_key)
    if hand and hand.objects:
        discard_id = random.choice(list(hand.objects))
        events.append(Event(
            type=EventType.DISCARD,
            payload={'player': obj.controller, 'card_id': discard_id},
            source=obj.id
        ))
    return events


def flame_imp_battlecry(obj, state):
    """Deal 3 damage to your hero."""
    events = []
    player = state.players.get(obj.controller)
    if player and player.hero_id:
        events.append(Event(
            type=EventType.DAMAGE,
            payload={'target': player.hero_id, 'amount': 3, 'source': obj.id, 'from_spell': False},
            source=obj.id
        ))
    return events


def felguard_battlecry(obj, state):
    """Destroy one of your Mana Crystals."""
    events = []
    player = state.players.get(obj.controller)
    if player and player.mana_crystals > 0:
        events.append(Event(
            type=EventType.ADD_MANA,
            payload={'player': obj.controller, 'amount': -1, 'permanent': True},
            source=obj.id
        ))
    return events


def pit_lord_battlecry(obj, state):
    """Deal 5 damage to your hero."""
    events = []
    player = state.players.get(obj.controller)
    if player and player.hero_id:
        events.append(Event(
            type=EventType.DAMAGE,
            payload={'target': player.hero_id, 'amount': 5, 'source': obj.id, 'from_spell': False},
            source=obj.id
        ))
    return events


def doomguard_battlecry(obj, state):
    """Discard 2 random cards."""
    events = []
    hand_key = f"hand_{obj.controller}"
    hand = state.zones.get(hand_key)
    if hand and hand.objects:
        cards_to_discard = min(2, len(hand.objects))
        for _ in range(cards_to_discard):
            if hand.objects:
                discard_id = random.choice(list(hand.objects))
                events.append(Event(
                    type=EventType.DISCARD,
                    payload={'player': obj.controller, 'card_id': discard_id},
                    source=obj.id
                ))
                if discard_id in hand.objects:
                    hand.objects.remove(discard_id)
    return events


# ============================================================================
# END OF TURN TRIGGER
# ============================================================================

def blood_imp_setup(obj: GameObject, state: GameState):
    """At end of turn, give another random friendly minion +1 Health."""
    def end_of_turn_fn(event: Event, state: GameState):
        if event.payload.get('player') != obj.controller:
            return []

        battlefield = state.zones.get('battlefield')
        friendly_minions = []
        if battlefield:
            for mid in battlefield.objects:
                if mid == obj.id:
                    continue
                m = state.objects.get(mid)
                if m and CardType.MINION in m.characteristics.types and m.controller == obj.controller:
                    friendly_minions.append(mid)

        if friendly_minions:
            target = random.choice(friendly_minions)
            return [Event(
                type=EventType.PT_MODIFICATION,
                payload={
                    'target': target,
                    'power_mod': 0,
                    'toughness_mod': 1,
                    'duration': 'permanent',
                    'source': obj.id
                },
                source=obj.id
            )]
        return []

    return [make_end_of_turn_trigger(obj, end_of_turn_fn)]


# ============================================================================
# BASIC WARLOCK CARDS
# ============================================================================

SOULFIRE = make_spell(
    name="Soulfire",
    mana_cost="{1}",
    spell_effect=soulfire_effect,
    text="Deal 4 damage. Discard a random card."
)

MORTAL_COIL = make_spell(
    name="Mortal Coil",
    mana_cost="{1}",
    spell_effect=mortal_coil_effect,
    text="Deal 1 damage to a minion. If that kills it, draw a card."
)

CORRUPTION = make_spell(
    name="Corruption",
    mana_cost="{1}",
    spell_effect=None,
    text="Choose an enemy minion. At the start of your turn, destroy it."
)

VOIDWALKER = make_minion(
    name="Voidwalker",
    attack=1,
    health=3,
    mana_cost="{1}",
    subtypes={"Demon"},
    keywords={"Taunt"},
    text="Taunt"
)

SHADOW_BOLT = make_spell(
    name="Shadow Bolt",
    mana_cost="{3}",
    spell_effect=shadow_bolt_effect,
    text="Deal 4 damage to a minion."
)

DRAIN_LIFE = make_spell(
    name="Drain Life",
    mana_cost="{3}",
    spell_effect=drain_life_effect,
    text="Deal 2 damage. Restore 2 Health to your hero."
)

HELLFIRE = make_spell(
    name="Hellfire",
    mana_cost="{4}",
    spell_effect=hellfire_effect,
    text="Deal 3 damage to ALL characters."
)

DREAD_INFERNAL = make_minion(
    name="Dread Infernal",
    attack=6,
    health=6,
    mana_cost="{6}",
    subtypes={"Demon"},
    battlecry=dread_infernal_battlecry,
    text="Battlecry: Deal 1 damage to ALL other characters."
)

SUCCUBUS = make_minion(
    name="Succubus",
    attack=4,
    health=3,
    mana_cost="{2}",
    subtypes={"Demon"},
    battlecry=succubus_battlecry,
    text="Battlecry: Discard a random card."
)


# ============================================================================
# CLASSIC WARLOCK CARDS
# ============================================================================

FLAME_IMP = make_minion(
    name="Flame Imp",
    attack=3,
    health=2,
    mana_cost="{1}",
    subtypes={"Demon"},
    battlecry=flame_imp_battlecry,
    text="Battlecry: Deal 3 damage to your hero."
)

BLOOD_IMP = make_minion(
    name="Blood Imp",
    attack=0,
    health=1,
    mana_cost="{1}",
    subtypes={"Demon"},
    keywords={"Stealth"},
    setup_interceptors=blood_imp_setup,
    text="Stealth. At the end of your turn, give another random friendly minion +1 Health."
)

POWER_OVERWHELMING = make_spell(
    name="Power Overwhelming",
    mana_cost="{1}",
    spell_effect=power_overwhelming_effect,
    text="Give a friendly minion +4/+4 until end of turn. Then, it dies."
)

DEMONFIRE = make_spell(
    name="Demonfire",
    mana_cost="{2}",
    spell_effect=demonfire_effect,
    text="Deal 2 damage to a minion. If it's a friendly Demon, give it +2/+2 instead."
)

SHADOWFLAME = make_spell(
    name="Shadowflame",
    mana_cost="{4}",
    spell_effect=shadowflame_effect,
    text="Destroy a friendly minion and deal its Attack damage to all enemy minions."
)

BANE_OF_DOOM = make_spell(
    name="Bane of Doom",
    mana_cost="{5}",
    spell_effect=bane_of_doom_effect,
    text="Deal 2 damage to a character. If that kills it, summon a random Demon."
)

SIPHON_SOUL = make_spell(
    name="Siphon Soul",
    mana_cost="{6}",
    spell_effect=siphon_soul_effect,
    text="Destroy a minion. Restore 3 Health to your hero."
)

TWISTING_NETHER = make_spell(
    name="Twisting Nether",
    mana_cost="{8}",
    spell_effect=twisting_nether_effect,
    text="Destroy all minions."
)

SUMMONING_PORTAL = make_minion(
    name="Summoning Portal",
    attack=0,
    health=4,
    mana_cost="{4}",
    subtypes=set(),
    text="Your minions cost (2) less."
)

FELGUARD = make_minion(
    name="Felguard",
    attack=3,
    health=5,
    mana_cost="{3}",
    subtypes={"Demon"},
    keywords={"Taunt"},
    battlecry=felguard_battlecry,
    text="Taunt. Battlecry: Destroy one of your Mana Crystals."
)

PIT_LORD = make_minion(
    name="Pit Lord",
    attack=5,
    health=6,
    mana_cost="{4}",
    subtypes={"Demon"},
    battlecry=pit_lord_battlecry,
    text="Battlecry: Deal 5 damage to your hero."
)

DOOMGUARD = make_minion(
    name="Doomguard",
    attack=5,
    health=7,
    mana_cost="{5}",
    subtypes={"Demon"},
    keywords={"Charge"},
    battlecry=doomguard_battlecry,
    text="Charge. Battlecry: Discard 2 random cards."
)

LORD_JARAXXUS = make_minion(
    name="Lord Jaraxxus",
    attack=3,
    health=15,
    mana_cost="{9}",
    subtypes={"Demon"},
    rarity="Legendary",
    text="Battlecry: Replace your hero with Lord Jaraxxus."
)

SENSE_DEMONS = make_spell(
    name="Sense Demons",
    mana_cost="{3}",
    spell_effect=sense_demons_effect,
    text="Draw 2 Demons from your deck."
)


# ============================================================================
# EXPORTS
# ============================================================================

WARLOCK_BASIC = [
    SOULFIRE,
    MORTAL_COIL,
    CORRUPTION,
    VOIDWALKER,
    SHADOW_BOLT,
    DRAIN_LIFE,
    HELLFIRE,
    DREAD_INFERNAL,
    SUCCUBUS
]

WARLOCK_CLASSIC = [
    FLAME_IMP,
    BLOOD_IMP,
    POWER_OVERWHELMING,
    DEMONFIRE,
    SHADOWFLAME,
    BANE_OF_DOOM,
    SIPHON_SOUL,
    TWISTING_NETHER,
    SUMMONING_PORTAL,
    FELGUARD,
    PIT_LORD,
    DOOMGUARD,
    LORD_JARAXXUS,
    SENSE_DEMONS
]

WARLOCK_CARDS = WARLOCK_BASIC + WARLOCK_CLASSIC
