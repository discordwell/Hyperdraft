"""Hearthstone Paladin Cards - Basic + Classic"""
import random
from src.engine.game import make_minion, make_spell, make_weapon, make_secret
from src.engine.types import Event, EventType, CardType, GameObject, GameState, ZoneType, Interceptor, InterceptorPriority, InterceptorAction, InterceptorResult, new_id
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
    """Give a friendly minion Divine Shield."""
    friendly = get_friendly_minions(obj, state, exclude_self=False)
    if not friendly:
        return []
    target = targets[0] if targets else random.choice(friendly)
    if target not in friendly:
        return []
    return [Event(
        type=EventType.KEYWORD_GRANT,
        payload={'object_id': target, 'keyword': 'divine_shield', 'duration': 'permanent'},
        source=obj.id
    )]

HAND_OF_PROTECTION = make_spell(
    name="Hand of Protection",
    mana_cost="{1}",
    text="Give a minion Divine Shield.",
    spell_effect=hand_of_protection_effect
)


def humility_effect(obj, state, targets):
    """Change a minion's Attack to 1."""
    enemies = get_enemy_minions(obj, state)
    if not enemies:
        return []
    target = targets[0] if targets else random.choice(enemies)
    if target not in enemies:
        return []
    return [Event(
        type=EventType.TRANSFORM,
        payload={'object_id': target, 'power': 1},
        source=obj.id
    )]

HUMILITY = make_spell(
    name="Humility",
    mana_cost="{1}",
    text="Change a minion's Attack to 1.",
    requires_target=True,
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


def blessing_of_wisdom_effect(obj, state, targets):
    """Choose a minion. Whenever it attacks, draw a card."""
    friendly = get_friendly_minions(obj, state, exclude_self=False)
    if not friendly:
        return []
    target_id = targets[0] if targets else random.choice(friendly)

    caster_controller = obj.controller

    def attack_filter(event, state):
        if event.type != EventType.ATTACK_DECLARED:
            return False
        return event.payload.get('attacker_id') == target_id

    def draw_card(event, state):
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(type=EventType.DRAW, payload={
                'player': caster_controller, 'count': 1
            }, source=target_id)]
        )

    interceptor = Interceptor(
        id=new_id(), source=obj.id, controller=caster_controller,
        priority=InterceptorPriority.REACT, filter=attack_filter,
        handler=draw_card, duration='while_on_battlefield'
    )
    state.interceptors[interceptor.id] = interceptor
    return []

BLESSING_OF_WISDOM = make_spell(
    name="Blessing of Wisdom",
    mana_cost="{1}",
    text="Choose a minion. Whenever it attacks, draw a card.",
    spell_effect=blessing_of_wisdom_effect
)


# ============================================================================
# CLASSIC PALADIN CARDS
# ============================================================================

def noble_sacrifice_filter(event, state):
    """Trigger when an enemy attacks your hero."""
    if event.type != EventType.ATTACK_DECLARED:
        return False
    attacker = state.objects.get(event.payload.get('attacker_id'))
    target = state.objects.get(event.payload.get('target_id'))
    if not attacker or not target:
        return False
    if CardType.HERO not in target.characteristics.types:
        return False
    return attacker.controller != target.controller

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


def _redemption_setup(obj, state):
    """Secret: When a friendly minion dies, return it to life with 1 Health."""

    def filter_fn(event, s):
        # Only trigger during opponent's turn
        if s.active_player == obj.controller:
            return False
        if event.type != EventType.OBJECT_DESTROYED:
            return False
        died_id = event.payload.get('object_id')
        died = s.objects.get(died_id)
        return (died is not None and CardType.MINION in died.characteristics.types
                and died.controller == obj.controller)

    def handler_fn(event, s):
        died_id = event.payload.get('object_id')
        died = s.objects.get(died_id)
        if not died:
            return InterceptorResult(action=InterceptorAction.PASS)

        # Resummon the specific minion that died with 1 Health
        token_payload = {
            'controller': obj.controller,
            'token': {
                'name': died.name,
                'power': died.characteristics.power,
                'toughness': 1,  # Returns with 1 Health
                'types': {CardType.MINION},
                'subtypes': set(died.characteristics.subtypes) if died.characteristics.subtypes else set(),
            }
        }
        # Preserve card_def so the resummoned minion has its abilities
        if died.card_def:
            token_payload['token']['card_def'] = died.card_def

        new_events = [
            Event(type=EventType.CREATE_TOKEN, payload=token_payload, source=obj.id),
            # Destroy the secret after triggering
            Event(type=EventType.ZONE_CHANGE, payload={
                'object_id': obj.id,
                'from_zone_type': obj.zone,
                'to_zone_type': ZoneType.GRAVEYARD
            }, source=obj.id),
        ]

        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=new_events
        )

    return [Interceptor(
        id=f"secret_{obj.id}",
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=filter_fn,
        handler=handler_fn,
        duration='while_on_battlefield',
        uses_remaining=1
    )]

REDEMPTION = make_secret(
    name="Redemption",
    mana_cost="{1}",
    text="Secret: When a friendly minion dies, return it to life with 1 Health.",
    setup_interceptors=_redemption_setup
)


def repentance_filter(event, state):
    """Trigger when opponent plays a minion"""
    if event.type != EventType.ZONE_CHANGE:
        return False
    obj_id = event.payload.get('object_id')
    obj_ref = state.objects.get(obj_id)
    return (obj_ref and CardType.MINION in obj_ref.characteristics.types
            and obj_ref.controller == state.active_player)

def repentance_effect(obj, state):
    """Reduce the minion's Health to 1"""
    # Find the most recently played enemy minion and set its health to 1
    battlefield = state.zones.get('battlefield')
    if battlefield:
        for mid in reversed(list(battlefield.objects)):
            m = state.objects.get(mid)
            if m and m.controller != obj.controller and CardType.MINION in m.characteristics.types:
                m.characteristics.toughness = 1
                m.state.damage = 0
                break
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
    if event.type != EventType.OBJECT_DESTROYED:
        return False
    died_id = event.payload.get('object_id')
    died = state.objects.get(died_id)
    return (died and CardType.MINION in died.characteristics.types
            and died.controller != state.active_player)

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
    """Change the Health of ALL minions to 1."""
    from src.cards.interceptor_helpers import get_all_minions
    events = []
    for mid in get_all_minions(state):
        m = state.objects.get(mid)
        if m:
            events.append(Event(
                type=EventType.TRANSFORM,
                payload={'object_id': mid, 'toughness': 1},
                source=obj.id
            ))
            if m.state.damage > 0:
                events.append(Event(
                    type=EventType.LIFE_CHANGE,
                    payload={'object_id': mid, 'amount': m.state.damage},
                    source=obj.id
                ))
    return events

EQUALITY = make_spell(
    name="Equality",
    mana_cost="{2}",
    text="Change the Health of ALL minions to 1.",
    spell_effect=equality_effect
)


def aldor_peacekeeper_battlecry(obj, state):
    """Change an enemy minion's Attack to 1."""
    enemies = get_enemy_minions(obj, state)
    if enemies:
        target = random.choice(enemies)
        return [Event(
            type=EventType.TRANSFORM,
            payload={'object_id': target, 'power': 1},
            source=obj.id
        )]
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
    """Draw cards until you have as many in hand as your opponent."""
    # Count cards in own hand
    own_hand_key = f"hand_{obj.controller}"
    own_hand = state.zones.get(own_hand_key)
    own_count = len(own_hand.objects) if own_hand else 0

    # Find opponent's hand size
    opponent_count = 0
    for pid in state.players:
        if pid != obj.controller:
            opp_hand_key = f"hand_{pid}"
            opp_hand = state.zones.get(opp_hand_key)
            opponent_count = len(opp_hand.objects) if opp_hand else 0
            break

    # Draw the difference (only if opponent has more)
    cards_to_draw = opponent_count - own_count
    if cards_to_draw > 0:
        return [Event(type=EventType.DRAW,
                      payload={'player': obj.controller, 'count': cards_to_draw},
                      source=obj.id)]
    return []

DIVINE_FAVOR = make_spell(
    name="Divine Favor",
    mana_cost="{3}",
    text="Draw cards until you have as many in hand as your opponent.",
    spell_effect=divine_favor_effect
)


def sword_of_justice_setup(obj, state):
    """Whenever you summon a minion, give it +1/+1 and this loses 1 Durability."""
    def _summoned_minion_ids(event, s):
        if event.type == EventType.ZONE_CHANGE:
            object_id = event.payload.get('object_id')
            return [object_id] if object_id else []
        if event.type == EventType.CREATE_TOKEN:
            object_ids = event.payload.get('object_ids')
            if isinstance(object_ids, list):
                return [oid for oid in object_ids if isinstance(oid, str)]
            object_id = event.payload.get('object_id')
            return [object_id] if isinstance(object_id, str) else []
        return []

    def summon_filter(event, s):
        if obj.zone != ZoneType.BATTLEFIELD:
            return False
        if event.type == EventType.ZONE_CHANGE and event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        for mid in _summoned_minion_ids(event, s):
            entering = s.objects.get(mid)
            if entering and entering.controller == obj.controller and entering.id != obj.id:
                if CardType.MINION in entering.characteristics.types:
                    return True
        return False

    def buff_and_lose_durability(event, s):
        events = []

        player = s.players.get(obj.controller)
        if not player:
            return InterceptorResult(action=InterceptorAction.PASS)

        summoned_ids = []
        for mid in _summoned_minion_ids(event, s):
            entering = s.objects.get(mid)
            if not entering:
                continue
            if entering.zone != ZoneType.BATTLEFIELD:
                continue
            if entering.controller != obj.controller or entering.id == obj.id:
                continue
            if CardType.MINION not in entering.characteristics.types:
                continue
            summoned_ids.append(mid)

        if not summoned_ids:
            return InterceptorResult(action=InterceptorAction.PASS)

        # One durability per buff, and no buffs once weapon is depleted.
        buffs_to_apply = min(len(summoned_ids), max(0, player.weapon_durability))
        for target_id in summoned_ids[:buffs_to_apply]:
            events.append(Event(
                type=EventType.PT_MODIFICATION,
                payload={'object_id': target_id, 'power_mod': 1, 'toughness_mod': 1, 'duration': 'permanent'},
                source=obj.id
            ))

        if buffs_to_apply > 0:
            player.weapon_durability -= buffs_to_apply
            hero = s.objects.get(player.hero_id)
            if hero:
                hero.state.weapon_durability = player.weapon_durability
            if player.weapon_durability <= 0:
                events.append(Event(
                    type=EventType.OBJECT_DESTROYED,
                    payload={'object_id': obj.id, 'reason': 'durability'},
                    source=obj.id
                ))
        return InterceptorResult(action=InterceptorAction.REACT, new_events=events)

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=summon_filter,
        handler=buff_and_lose_durability,
        duration='while_on_battlefield'
    )]

SWORD_OF_JUSTICE = make_weapon(
    name="Sword of Justice",
    attack=1,
    durability=5,
    mana_cost="{3}",
    text="Whenever you summon a minion, give it +1/+1 and this loses 1 Durability.",
    setup_interceptors=sword_of_justice_setup
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


def _eye_for_an_eye_filter(event, state):
    """Trigger when your hero takes damage."""
    if event.type != EventType.DAMAGE:
        return False
    target_id = event.payload.get('target')
    target = state.objects.get(target_id)
    return target and CardType.MINION not in target.characteristics.types

def _eye_for_an_eye_effect(obj, state):
    """Deal same damage to enemy hero."""
    # Find the most recent damage event to our hero
    for event in reversed(state.event_log[-10:]):
        if event.type == EventType.DAMAGE:
            amount = event.payload.get('amount', 0)
            hero_id = get_enemy_hero_id(obj, state)
            if hero_id and amount > 0:
                return [Event(type=EventType.DAMAGE,
                    payload={'target': hero_id, 'amount': amount, 'source': obj.id},
                    source=obj.id)]
    return []

EYE_FOR_AN_EYE = make_secret(
    name="Eye for an Eye",
    mana_cost="{1}",
    text="Secret: When your hero takes damage, deal that much damage to the enemy hero.",
    trigger_filter=_eye_for_an_eye_filter,
    trigger_effect=_eye_for_an_eye_effect
)


def argent_protector_battlecry(obj, state):
    """Battlecry: Give a friendly minion Divine Shield."""
    friendly = get_friendly_minions(obj, state, exclude_self=True)
    if friendly:
        target_id = random.choice(friendly)
        target_obj = state.objects.get(target_id)
        if target_obj:
            target_obj.state.divine_shield = True
    return []

ARGENT_PROTECTOR = make_minion(
    name="Argent Protector",
    attack=2,
    health=2,
    mana_cost="{2}",
    text="Battlecry: Give a friendly minion Divine Shield.",
    battlecry=argent_protector_battlecry
)


def blessed_champion_effect(obj, state, targets):
    """Double a minion's Attack."""
    friendly = get_friendly_minions(obj, state, exclude_self=False)
    if friendly:
        target_id = random.choice(friendly)
        m = state.objects.get(target_id)
        if m:
            current_attack = m.characteristics.power
            return [Event(type=EventType.PT_MODIFICATION,
                payload={'object_id': target_id, 'power_mod': current_attack, 'toughness_mod': 0, 'duration': 'permanent'},
                source=obj.id)]
    return []

BLESSED_CHAMPION = make_spell(
    name="Blessed Champion",
    mana_cost="{5}",
    text="Double a minion's Attack.",
    spell_effect=blessed_champion_effect
)


def holy_wrath_effect(obj, state, targets):
    """Draw a card and deal damage equal to its cost."""
    import re

    # Draw the card manually to inspect its cost
    lib_key = f"library_{obj.controller}"
    hand_key = f"hand_{obj.controller}"
    library = state.zones.get(lib_key)
    hand = state.zones.get(hand_key)

    if not library or not library.objects or not hand:
        return []

    # Check hand size limit (Hearthstone)
    if state.game_mode == "hearthstone" and len(hand.objects) >= state.max_hand_size:
        # Overdraw - burn the card, deal 0 damage
        card_id = library.objects.pop(0)
        graveyard_key = f"graveyard_{obj.controller}"
        if graveyard_key in state.zones:
            state.zones[graveyard_key].objects.append(card_id)
            card = state.objects.get(card_id)
            if card:
                card.zone = ZoneType.GRAVEYARD
                card.entered_zone_at = state.timestamp
        return []

    # Draw the card
    card_id = library.objects.pop(0)
    hand.objects.append(card_id)
    card = state.objects.get(card_id)
    drawn_cost = 0
    if card:
        card.zone = ZoneType.HAND
        card.entered_zone_at = state.timestamp
        # Parse the drawn card's mana cost
        cost_str = card.characteristics.mana_cost or "{0}"
        numbers = re.findall(r'\{(\d+)\}', cost_str)
        drawn_cost = sum(int(n) for n in numbers)

    # Deal damage equal to the drawn card's cost to a random enemy
    events = []
    enemy_targets = get_enemy_targets(obj, state)
    if enemy_targets:
        target = random.choice(enemy_targets)
        events.append(Event(type=EventType.DAMAGE,
            payload={'target': target, 'amount': drawn_cost, 'source': obj.id, 'from_spell': True},
            source=obj.id))
    return events

HOLY_WRATH = make_spell(
    name="Holy Wrath",
    mana_cost="{5}",
    text="Draw a card and deal damage equal to its cost.",
    spell_effect=holy_wrath_effect
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
    BLESSING_OF_WISDOM,
]

PALADIN_CLASSIC = [
    NOBLE_SACRIFICE,
    REDEMPTION,
    REPENTANCE,
    AVENGE,
    EYE_FOR_AN_EYE,
    EQUALITY,
    ARGENT_PROTECTOR,
    ALDOR_PEACEKEEPER,
    DIVINE_FAVOR,
    SWORD_OF_JUSTICE,
    BLESSED_CHAMPION,
    HOLY_WRATH,
    AVENGING_WRATH,
    LAY_ON_HANDS,
    TIRION_FORDRING,
]

PALADIN_CARDS = PALADIN_BASIC + PALADIN_CLASSIC
