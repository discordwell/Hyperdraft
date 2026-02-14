"""Hearthstone Warlock Cards - Basic + Classic"""
import random
from src.engine.game import make_minion, make_spell
from src.engine.types import Event, EventType, CardType, GameObject, GameState, ZoneType, Interceptor, InterceptorPriority, InterceptorAction, InterceptorResult, Characteristics, ObjectState, new_id
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
            payload={'player': obj.controller, 'object_id': discard_id},
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
        # Check if target will die from this damage
        target_obj = state.objects.get(target)
        if target_obj:
            effective_hp = target_obj.characteristics.toughness - target_obj.state.damage
            if effective_hp <= 1:
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
    events.append(Event(
        type=EventType.LIFE_CHANGE,
        payload={'player': obj.controller, 'amount': 2},
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
    """Give a friendly minion +4/+4 until end of turn. Then, it dies."""
    battlefield = state.zones.get('battlefield')
    friendly_minions = []
    if battlefield:
        for mid in battlefield.objects:
            m = state.objects.get(mid)
            if m and CardType.MINION in m.characteristics.types and m.controller == obj.controller:
                friendly_minions.append(mid)

    if not friendly_minions:
        return []

    target = random.choice(friendly_minions)

    # Register end-of-turn interceptor to destroy the minion
    def end_turn_filter(event, s):
        return event.type == EventType.TURN_END and event.payload.get('player') == obj.controller

    def end_turn_handler(event, s):
        # Self-remove this interceptor
        int_id = end_turn_handler._interceptor_id
        if int_id in s.interceptors:
            del s.interceptors[int_id]
        # Destroy the buffed minion
        target_obj = s.objects.get(target)
        if target_obj and target_obj.zone == ZoneType.BATTLEFIELD:
            return InterceptorResult(
                action=InterceptorAction.REACT,
                new_events=[Event(
                    type=EventType.OBJECT_DESTROYED,
                    payload={'object_id': target, 'reason': 'power_overwhelming'},
                    source=obj.id
                )]
            )
        return InterceptorResult(action=InterceptorAction.REACT)

    int_obj = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=end_turn_filter,
        handler=end_turn_handler,
        duration='until_end_of_turn'
    )
    end_turn_handler._interceptor_id = int_obj.id
    state.interceptors[int_obj.id] = int_obj

    return [Event(
        type=EventType.PT_MODIFICATION,
        payload={
            'object_id': target,
            'power_mod': 4,
            'toughness_mod': 4,
            'duration': 'end_of_turn',
        },
        source=obj.id
    )]


def demonfire_effect(obj, state, targets):
    """Deal 2 damage to a minion. If it's a friendly Demon, give it +2/+2 instead."""
    events = []
    # Check for friendly Demons first
    battlefield = state.zones.get('battlefield')
    friendly_demons = []
    if battlefield:
        for mid in battlefield.objects:
            m = state.objects.get(mid)
            if (m and m.controller == obj.controller and
                CardType.MINION in m.characteristics.types and
                'Demon' in m.characteristics.subtypes):
                friendly_demons.append(mid)
    if friendly_demons:
        target = random.choice(friendly_demons)
        events.append(Event(
            type=EventType.PT_MODIFICATION,
            payload={'object_id': target, 'power_mod': 2, 'toughness_mod': 2, 'duration': 'permanent'},
            source=obj.id
        ))
    else:
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
    events = []
    # Find a friendly minion to sacrifice
    battlefield = state.zones.get('battlefield')
    friendly_minions = []
    if battlefield:
        for mid in battlefield.objects:
            m = state.objects.get(mid)
            if m and CardType.MINION in m.characteristics.types and m.controller == obj.controller:
                friendly_minions.append(mid)
    if not friendly_minions:
        return []
    # Pick the highest-attack friendly minion for AI
    sacrifice = max(friendly_minions, key=lambda mid: state.objects[mid].characteristics.power)
    sacrifice_attack = state.objects[sacrifice].characteristics.power
    # Destroy the sacrificed minion
    events.append(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': sacrifice, 'reason': 'shadowflame'},
        source=obj.id
    ))
    # Deal its attack damage to all enemy minions
    enemy_minions = get_enemy_minions(obj, state)
    for mid in enemy_minions:
        events.append(Event(
            type=EventType.DAMAGE,
            payload={'target': mid, 'amount': sacrifice_attack, 'source': obj.id, 'from_spell': True},
            source=obj.id
        ))
    return events


def bane_of_doom_effect(obj, state, targets):
    """Deal 2 damage to a character. If that kills it, summon a random Demon."""
    events = []
    enemies = get_enemy_targets(obj, state)
    if enemies:
        target = random.choice(enemies)
        events.append(Event(
            type=EventType.DAMAGE,
            payload={'target': target, 'amount': 2, 'source': obj.id, 'from_spell': True},
            source=obj.id
        ))
        # Only summon if target will die
        target_obj = state.objects.get(target)
        if target_obj:
            effective_hp = target_obj.characteristics.toughness - target_obj.state.damage
            if effective_hp <= 2:
                events.append(Event(
                    type=EventType.CREATE_TOKEN,
                    payload={
                        'controller': obj.controller,
                        'token': {
                            'name': 'Infernal',
                            'power': 6,
                            'toughness': 6,
                            'types': {CardType.MINION},
                            'subtypes': {'Demon'},
                        }
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
    events.append(Event(
        type=EventType.LIFE_CHANGE,
        payload={'player': obj.controller, 'amount': 3},
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
    """Draw 2 Demons from your deck. If you can't, draw Worthless Imps instead."""
    events = []
    lib_key = f"library_{obj.controller}"
    hand_key = f"hand_{obj.controller}"
    library = state.zones.get(lib_key)
    hand = state.zones.get(hand_key)

    if not library or not hand:
        return events

    # Find all Demons in the deck
    demon_ids = []
    for card_id in library.objects:
        card = state.objects.get(card_id)
        if card and 'Demon' in card.characteristics.subtypes:
            demon_ids.append(card_id)

    # Draw up to 2 Demons
    demons_drawn = 0
    for demon_id in demon_ids[:2]:
        if state.game_mode == "hearthstone" and len(hand.objects) >= state.max_hand_size:
            break  # Hand is full
        # Move demon from library to hand
        if demon_id in library.objects:
            library.objects.remove(demon_id)
            hand.objects.append(demon_id)
            demon = state.objects.get(demon_id)
            if demon:
                demon.zone = ZoneType.HAND
                demon.entered_zone_at = state.timestamp
            demons_drawn += 1

    # For each Demon not found, create a Worthless Imp (1/1 Demon, 0 mana)
    imps_needed = 2 - demons_drawn
    for _ in range(imps_needed):
        events.append(Event(
            type=EventType.ADD_TO_HAND,
            payload={
                'player': obj.controller,
                'card_def': {
                    'name': 'Worthless Imp',
                    'mana_cost': '{0}',
                    'types': {CardType.MINION},
                    'subtypes': {'Demon'},
                    'power': 1,
                    'toughness': 1,
                }
            },
            source=obj.id
        ))

    return events


def corruption_effect(obj, state, targets):
    """Choose an enemy minion. At the start of your next turn, destroy it."""
    enemy_minions = get_enemy_minions(obj, state)
    if not enemy_minions:
        return []
    target_id = targets[0] if targets else random.choice(enemy_minions)

    # Set up a delayed destroy interceptor that fires at start of the caster's next turn
    def turn_start_filter(event, s):
        return event.type == EventType.TURN_START and event.payload.get('player') == obj.controller

    def destroy_target(event, s):
        target = s.objects.get(target_id)
        if target and target.zone == ZoneType.BATTLEFIELD:
            return InterceptorResult(
                action=InterceptorAction.REACT,
                new_events=[Event(
                    type=EventType.OBJECT_DESTROYED,
                    payload={'object_id': target_id, 'reason': 'corruption'},
                    source=obj.id
                )]
            )
        return InterceptorResult(action=InterceptorAction.PASS)

    int_obj = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=turn_start_filter,
        handler=destroy_target,
        uses_remaining=1
    )
    state.interceptors[int_obj.id] = int_obj
    return []


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
            payload={'player': obj.controller, 'object_id': discard_id},
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
        discard_ids = random.sample(list(hand.objects), cards_to_discard)
        for discard_id in discard_ids:
            events.append(Event(
                type=EventType.DISCARD,
                payload={'player': obj.controller, 'object_id': discard_id},
                source=obj.id
            ))
    return events


def void_terror_battlecry(obj, state):
    """Destroy the minions on either side of this minion and gain their Attack and Health."""
    from src.cards.interceptor_helpers import get_adjacent_minions
    left_id, right_id = get_adjacent_minions(obj.id, state)
    total_power = 0
    total_toughness = 0
    events = []

    for adj_id in [left_id, right_id]:
        if adj_id:
            adj = state.objects.get(adj_id)
            if adj:
                total_power += adj.characteristics.power or 0
                total_toughness += adj.characteristics.toughness or 0
                events.append(Event(
                    type=EventType.OBJECT_DESTROYED,
                    payload={'object_id': adj_id, 'reason': 'void_terror'},
                    source=obj.id
                ))

    if total_power > 0 or total_toughness > 0:
        events.append(Event(
            type=EventType.PT_MODIFICATION,
            payload={
                'object_id': obj.id,
                'power_mod': total_power,
                'toughness_mod': total_toughness,
                'duration': 'permanent'
            },
            source=obj.id
        ))

    return events


def lord_jaraxxus_battlecry(obj, state):
    """Replace your hero with Lord Jaraxxus (15 HP, 3/8 weapon, INFERNO! hero power)."""
    player = state.players.get(obj.controller)
    if not player:
        return []

    # Replace hero HP to 15
    player.life = 15
    player.max_life = 15
    player.armor = 0

    # Equip Blood Fury (3/8 weapon)
    player.weapon_attack = 3
    player.weapon_durability = 8
    hero = state.objects.get(player.hero_id)
    if hero:
        hero.state.weapon_attack = 3
        hero.state.weapon_durability = 8

    # Replace hero power with INFERNO! (summon a 6/6 Infernal)
    from src.cards.hearthstone.hero_powers import INFERNO_HERO_POWER
    new_hp_id = new_id()
    new_hp = GameObject(
        id=new_hp_id,
        name=INFERNO_HERO_POWER.name,
        owner=obj.controller,
        controller=obj.controller,
        zone=ZoneType.COMMAND,
        characteristics=Characteristics(
            types=INFERNO_HERO_POWER.characteristics.types,
            mana_cost=INFERNO_HERO_POWER.mana_cost,
        ),
        state=ObjectState(),
        card_def=INFERNO_HERO_POWER,
    )
    state.objects[new_hp_id] = new_hp
    player.hero_power_id = new_hp_id
    player.hero_power_used = False

    # Register hero power interceptors so it actually activates
    if hasattr(INFERNO_HERO_POWER, 'setup_interceptors') and INFERNO_HERO_POWER.setup_interceptors:
        interceptors = INFERNO_HERO_POWER.setup_interceptors(new_hp, state)
        for interceptor in (interceptors or []):
            interceptor.timestamp = state.next_timestamp()
            state.interceptors[interceptor.id] = interceptor
            new_hp.interceptor_ids.append(interceptor.id)

    return []


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
                    'object_id': target,
                    'power_mod': 0,
                    'toughness_mod': 1,
                    'duration': 'permanent',
                },
                source=obj.id
            )]
        return []

    return [make_end_of_turn_trigger(obj, end_of_turn_fn)]


def summoning_portal_setup(obj, state):
    """Your minions cost (2) less, but not less than (1)."""
    from src.cards.interceptor_helpers import make_cost_reduction_aura
    return make_cost_reduction_aura(obj, CardType.MINION, 2, floor=1)


# ============================================================================
# BASIC WARLOCK CARDS
# ============================================================================

SOULFIRE = make_spell(
    name="Soulfire",
    mana_cost="{0}",
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
    spell_effect=corruption_effect,
    text="Choose an enemy minion. At the start of your turn, destroy it."
)

VOIDWALKER = make_minion(
    name="Voidwalker",
    attack=1,
    health=3,
    mana_cost="{1}",
    subtypes={"Demon"},
    keywords={"taunt"},
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
    keywords={"stealth"},
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
    setup_interceptors=summoning_portal_setup,
    text="Your minions cost (2) less."
)

FELGUARD = make_minion(
    name="Felguard",
    attack=3,
    health=5,
    mana_cost="{3}",
    subtypes={"Demon"},
    keywords={"taunt"},
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
    keywords={"charge"},
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
    battlecry=lord_jaraxxus_battlecry,
    text="Battlecry: Replace your hero with Lord Jaraxxus."
)

SENSE_DEMONS = make_spell(
    name="Sense Demons",
    mana_cost="{3}",
    spell_effect=sense_demons_effect,
    text="Draw 2 Demons from your deck."
)


def sacrificial_pact_effect(obj, state, targets):
    """Destroy a friendly Demon. Restore 5 Health to your hero."""
    events = []
    battlefield = state.zones.get('battlefield')
    friendly_demons = []
    if battlefield:
        for mid in battlefield.objects:
            m = state.objects.get(mid)
            if (m and m.controller == obj.controller and
                CardType.MINION in m.characteristics.types and
                'Demon' in m.characteristics.subtypes):
                friendly_demons.append(mid)
    if friendly_demons:
        target = random.choice(friendly_demons)
        events.append(Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': target, 'reason': 'sacrificial_pact'},
            source=obj.id
        ))
        events.append(Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': obj.controller, 'amount': 5},
            source=obj.id
        ))
    return events

SACRIFICIAL_PACT = make_spell(
    name="Sacrificial Pact",
    mana_cost="{0}",
    spell_effect=sacrificial_pact_effect,
    text="Destroy a Demon. Restore 5 Health to your hero."
)

VOID_TERROR = make_minion(
    name="Void Terror",
    attack=3,
    health=3,
    mana_cost="{3}",
    subtypes={"Demon"},
    battlecry=void_terror_battlecry,
    text="Battlecry: Destroy the minions on either side of this minion and gain their Attack and Health."
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
    SENSE_DEMONS,
    SACRIFICIAL_PACT,
    VOID_TERROR
]

WARLOCK_CARDS = WARLOCK_BASIC + WARLOCK_CLASSIC
