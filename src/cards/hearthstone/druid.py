"""Hearthstone Druid Cards - Basic + Classic"""
import random
from src.engine.game import make_minion, make_spell
from src.engine.types import Event, EventType, CardType, GameObject, GameState, ZoneType, Interceptor, InterceptorPriority, InterceptorAction, InterceptorResult, new_id
from src.cards.interceptor_helpers import (
    get_enemy_targets, get_enemy_minions, get_friendly_minions, get_all_minions,
    get_enemy_hero_id
)


# ============================================================================
# BASIC DRUID CARDS
# ============================================================================

def claw_effect(obj, state, targets):
    """Give your hero +2 Attack this turn and 2 Armor."""
    player = state.players.get(obj.controller)
    if not player:
        return []

    player.weapon_attack += 2
    player.armor += 2

    # Register end-of-turn cleanup interceptor to remove the +2 attack
    def end_turn_filter(event, s):
        return event.type == EventType.TURN_END and event.payload.get('player') == obj.controller

    def end_turn_handler(event, s):
        p = s.players.get(obj.controller)
        if p:
            p.weapon_attack = max(0, p.weapon_attack - 2)
        # Self-remove this interceptor
        int_id = end_turn_handler._interceptor_id
        if int_id in s.interceptors:
            del s.interceptors[int_id]
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

    return []

CLAW = make_spell(
    name="Claw",
    mana_cost="{1}",
    text="Give your hero +2 Attack this turn and 2 Armor.",
    rarity="Free",
    spell_effect=claw_effect
)


def mark_of_the_wild_effect(obj, state, targets):
    """Give a minion Taunt and +2/+2."""
    friendly = get_friendly_minions(obj, state, exclude_self=False)
    if not friendly:
        return []
    target = random.choice(friendly)
    target_obj = state.objects.get(target)
    if target_obj:
        if not target_obj.characteristics.abilities:
            target_obj.characteristics.abilities = []
        target_obj.characteristics.abilities.append({'keyword': 'taunt'})
    return [Event(type=EventType.PT_MODIFICATION,
                  payload={'object_id': target, 'power_mod': 2, 'toughness_mod': 2, 'duration': 'permanent'},
                  source=obj.id)]

MARK_OF_THE_WILD = make_spell(
    name="Mark of the Wild",
    mana_cost="{2}",
    text="Give a minion Taunt and +2/+2.",
    rarity="Free",
    spell_effect=mark_of_the_wild_effect
)


def wild_growth_effect(obj, state, targets):
    """Gain an empty Mana Crystal."""
    player = state.players.get(obj.controller)
    if player and player.mana_crystals < 10:
        player.mana_crystals += 1
    return []

WILD_GROWTH = make_spell(
    name="Wild Growth",
    mana_cost="{2}",
    text="Gain an empty Mana Crystal.",
    rarity="Free",
    spell_effect=wild_growth_effect
)


def savage_roar_effect(obj, state, targets):
    """Give your characters +2 Attack this turn."""
    events = []
    # Buff all friendly minions (+2 Attack this turn)
    for mid in get_friendly_minions(obj, state, exclude_self=False):
        events.append(Event(type=EventType.PT_MODIFICATION,
            payload={'object_id': mid, 'power_mod': 2, 'toughness_mod': 0, 'duration': 'end_of_turn'},
            source=obj.id))
    # Give hero +2 attack this turn
    player = state.players.get(obj.controller)
    if not player:
        return events

    player.weapon_attack += 2

    # Register end-of-turn cleanup interceptor to remove the hero +2 attack
    def end_turn_filter(event, s):
        return event.type == EventType.TURN_END and event.payload.get('player') == obj.controller

    def end_turn_handler(event, s):
        p = s.players.get(obj.controller)
        if p:
            p.weapon_attack = max(0, p.weapon_attack - 2)
        # Self-remove this interceptor
        int_id = end_turn_handler._interceptor_id
        if int_id in s.interceptors:
            del s.interceptors[int_id]
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

    return events

SAVAGE_ROAR = make_spell(
    name="Savage Roar",
    mana_cost="{3}",
    text="Give your characters +2 Attack this turn.",
    rarity="Free",
    spell_effect=savage_roar_effect
)


def healing_touch_effect(obj, state, targets):
    """Restore 8 Health."""
    # Heal hero
    return [Event(
        type=EventType.LIFE_CHANGE,
        payload={'player': obj.controller, 'amount': 8},
        source=obj.id
    )]

HEALING_TOUCH = make_spell(
    name="Healing Touch",
    mana_cost="{3}",
    text="Restore 8 Health.",
    rarity="Free",
    spell_effect=healing_touch_effect
)


def swipe_effect(obj, state, targets):
    """Deal 4 damage to an enemy and 1 damage to all other enemies."""
    events = []
    enemies = get_enemy_targets(obj, state)
    if not enemies:
        return []
    # Primary target: prefer enemy minions, then hero
    enemy_minions = get_enemy_minions(obj, state)
    primary = random.choice(enemy_minions) if enemy_minions else get_enemy_hero_id(obj, state)
    if primary:
        events.append(Event(type=EventType.DAMAGE,
                           payload={'target': primary, 'amount': 4, 'source': obj.id, 'from_spell': True},
                           source=obj.id))
        # 1 damage to all other enemies
        for eid in enemies:
            if eid != primary:
                events.append(Event(type=EventType.DAMAGE,
                                   payload={'target': eid, 'amount': 1, 'source': obj.id, 'from_spell': True},
                                   source=obj.id))
    return events

SWIPE = make_spell(
    name="Swipe",
    mana_cost="{4}",
    text="Deal 4 damage to an enemy and 1 damage to all other enemies.",
    rarity="Free",
    spell_effect=swipe_effect
)


def starfire_effect(obj, state, targets):
    """Deal 5 damage. Draw a card."""
    events = []
    enemies = get_enemy_targets(obj, state)
    if enemies:
        target = random.choice(enemies)
        events.append(Event(type=EventType.DAMAGE,
                           payload={'target': target, 'amount': 5, 'source': obj.id, 'from_spell': True},
                           source=obj.id))
    events.append(Event(type=EventType.DRAW, payload={'player': obj.controller, 'count': 1}, source=obj.id))
    return events

STARFIRE = make_spell(
    name="Starfire",
    mana_cost="{6}",
    text="Deal 5 damage. Draw a card.",
    rarity="Free",
    spell_effect=starfire_effect
)


IRONBARK_PROTECTOR = make_minion(
    name="Ironbark Protector",
    attack=8,
    health=8,
    mana_cost="{8}",
    text="Taunt",
    rarity="Free",
    abilities=[{'keyword': 'taunt'}]
)


def moonfire_effect(obj, state, targets):
    """Deal 1 damage."""
    enemies = get_enemy_targets(obj, state)
    if enemies:
        target = random.choice(enemies)
        return [Event(type=EventType.DAMAGE,
                     payload={'target': target, 'amount': 1, 'source': obj.id, 'from_spell': True},
                     source=obj.id)]
    return []

MOONFIRE = make_spell(
    name="Moonfire",
    mana_cost="{0}",
    text="Deal 1 damage.",
    rarity="Free",
    spell_effect=moonfire_effect
)


DRUID_BASIC = [
    CLAW,
    MARK_OF_THE_WILD,
    WILD_GROWTH,
    SAVAGE_ROAR,
    HEALING_TOUCH,
    SWIPE,
    STARFIRE,
    IRONBARK_PROTECTOR,
    MOONFIRE,
]


# ============================================================================
# CLASSIC DRUID CARDS
# ============================================================================

def innervate_effect(obj, state, targets):
    """Gain 2 Mana Crystals this turn only."""
    player = state.players.get(obj.controller)
    if player:
        player.mana_crystals_available += 2
    return []

INNERVATE = make_spell(
    name="Innervate",
    mana_cost="{0}",
    text="Gain 2 Mana Crystals this turn only.",
    rarity="Common",
    spell_effect=innervate_effect
)


def naturalize_effect(obj, state, targets):
    """Destroy a minion. Your opponent draws 2 cards."""
    events = []
    enemies = get_enemy_minions(obj, state)
    if enemies:
        target = random.choice(enemies)
        events.append(Event(type=EventType.OBJECT_DESTROYED,
                           payload={'object_id': target, 'reason': 'naturalize'},
                           source=obj.id))
    # Opponent draws 2
    for pid in state.players:
        if pid != obj.controller:
            events.append(Event(type=EventType.DRAW, payload={'player': pid, 'count': 2}, source=obj.id))
    return events

NATURALIZE = make_spell(
    name="Naturalize",
    mana_cost="{1}",
    text="Destroy a minion. Your opponent draws 2 cards.",
    rarity="Common",
    spell_effect=naturalize_effect
)


def power_of_the_wild_effect(obj, state, targets):
    """Choose One - Give your minions +1/+1; or Summon a 3/2 Panther."""
    friendly = get_friendly_minions(obj, state, exclude_self=False)
    if len(friendly) >= 2:
        # Buff all minions +1/+1
        events = []
        for mid in friendly:
            events.append(Event(type=EventType.PT_MODIFICATION,
                payload={'object_id': mid, 'power_mod': 1, 'toughness_mod': 1, 'duration': 'permanent'},
                source=obj.id))
        return events
    else:
        # Summon 3/2 Panther
        return [Event(type=EventType.CREATE_TOKEN, payload={
            'controller': obj.controller,
            'token': {'name': 'Panther', 'power': 3, 'toughness': 2, 'types': {CardType.MINION}, 'subtypes': {'Beast'}}
        }, source=obj.id)]

POWER_OF_THE_WILD = make_spell(
    name="Power of the Wild",
    mana_cost="{2}",
    text="Choose One - Give your minions +1/+1; or Summon a 3/2 Panther.",
    rarity="Common",
    spell_effect=power_of_the_wild_effect
)


def wrath_effect(obj, state, targets):
    """Choose One - Deal 3 damage to a minion; or Deal 1 damage and draw a card."""
    enemies = get_enemy_minions(obj, state)
    if not enemies:
        return []
    # AI: If there's a low-health minion, deal 3 damage; else deal 1 and draw
    low_health = [mid for mid in enemies if state.objects.get(mid) and
                  state.objects[mid].characteristics.toughness - state.objects[mid].state.damage <= 3]
    if low_health:
        target = random.choice(low_health)
        return [Event(type=EventType.DAMAGE,
                     payload={'target': target, 'amount': 3, 'source': obj.id, 'from_spell': True},
                     source=obj.id)]
    else:
        target = random.choice(enemies)
        return [
            Event(type=EventType.DAMAGE,
                  payload={'target': target, 'amount': 1, 'source': obj.id, 'from_spell': True},
                  source=obj.id),
            Event(type=EventType.DRAW, payload={'player': obj.controller, 'count': 1}, source=obj.id)
        ]

WRATH = make_spell(
    name="Wrath",
    mana_cost="{2}",
    text="Choose One - Deal 3 damage to a minion; or Deal 1 damage and draw a card.",
    rarity="Common",
    spell_effect=wrath_effect
)


def keeper_of_the_grove_battlecry(obj, state):
    """Choose One - Deal 2 damage; or Silence a minion."""
    # Check if there's a high-value silence target
    enemies = get_enemy_minions(obj, state)
    silence_targets = [mid for mid in enemies if state.objects.get(mid) and
                       len(state.objects[mid].interceptor_ids) > 0]
    if silence_targets:
        target = random.choice(silence_targets)
        return [Event(type=EventType.SILENCE_TARGET, payload={'target': target}, source=obj.id)]
    elif enemies:
        target = random.choice(enemies)
        return [Event(type=EventType.DAMAGE,
                     payload={'target': target, 'amount': 2, 'source': obj.id},
                     source=obj.id)]
    return []

KEEPER_OF_THE_GROVE = make_minion(
    name="Keeper of the Grove",
    attack=2,
    health=4,
    mana_cost="{4}",
    text="Choose One - Deal 2 damage; or Silence a minion.",
    rarity="Rare",
    battlecry=keeper_of_the_grove_battlecry
)


def druid_of_the_claw_battlecry(obj, state):
    """Choose One - Charge; or +2 Health and Taunt."""
    # AI: Always pick Bear form (Taunt + bonus health)
    if not obj.characteristics.abilities:
        obj.characteristics.abilities = []
    obj.characteristics.abilities.append({'keyword': 'taunt'})
    return [Event(type=EventType.PT_MODIFICATION,
                  payload={'object_id': obj.id, 'power_mod': 0, 'toughness_mod': 2, 'duration': 'permanent'},
                  source=obj.id)]

DRUID_OF_THE_CLAW = make_minion(
    name="Druid of the Claw",
    attack=4,
    health=4,
    mana_cost="{5}",
    text="Choose One - Charge; or +2 Health and Taunt.",
    rarity="Common",
    battlecry=druid_of_the_claw_battlecry
)


def nourish_effect(obj, state, targets):
    """Choose One - Gain 2 Mana Crystals; or Draw 3 cards."""
    player = state.players.get(obj.controller)
    if player and player.mana_crystals < 8:
        # Ramp
        player.mana_crystals = min(10, player.mana_crystals + 2)
        return []
    else:
        # Draw
        return [Event(type=EventType.DRAW, payload={'player': obj.controller, 'count': 3}, source=obj.id)]

NOURISH = make_spell(
    name="Nourish",
    mana_cost="{5}",
    text="Choose One - Gain 2 Mana Crystals; or Draw 3 cards.",
    rarity="Rare",
    spell_effect=nourish_effect
)


def starfall_effect(obj, state, targets):
    """Choose One - Deal 5 damage to a minion; or Deal 2 damage to all enemy minions."""
    enemy_minions = get_enemy_minions(obj, state)
    if not enemy_minions:
        return []
    # AI: If there's a single high-priority target, use single-target; else AOE
    if len(enemy_minions) >= 3:
        # AOE mode
        events = []
        for mid in enemy_minions:
            events.append(Event(type=EventType.DAMAGE,
                               payload={'target': mid, 'amount': 2, 'source': obj.id, 'from_spell': True},
                               source=obj.id))
        return events
    else:
        # Single target mode
        target = random.choice(enemy_minions)
        return [Event(type=EventType.DAMAGE,
                     payload={'target': target, 'amount': 5, 'source': obj.id, 'from_spell': True},
                     source=obj.id)]

STARFALL = make_spell(
    name="Starfall",
    mana_cost="{5}",
    text="Choose One - Deal 5 damage to a minion; or Deal 2 damage to all enemy minions.",
    rarity="Rare",
    spell_effect=starfall_effect
)


def force_of_nature_effect(obj, state, targets):
    """Summon three 2/2 Treants."""
    events = []
    for _ in range(3):
        events.append(Event(type=EventType.CREATE_TOKEN, payload={
            'controller': obj.controller,
            'token': {'name': 'Treant', 'power': 2, 'toughness': 2, 'types': {CardType.MINION}}
        }, source=obj.id))
    return events

FORCE_OF_NATURE = make_spell(
    name="Force of Nature",
    mana_cost="{6}",
    text="Summon three 2/2 Treants.",
    rarity="Epic",
    spell_effect=force_of_nature_effect
)


def ancient_of_lore_battlecry(obj, state):
    """Choose One - Draw 2 cards; or Restore 5 Health."""
    player = state.players.get(obj.controller)
    if player and player.life < 15:
        # Heal
        player.life = min(30, player.life + 5)
        return []
    else:
        # Draw
        return [Event(type=EventType.DRAW, payload={'player': obj.controller, 'count': 2}, source=obj.id)]

ANCIENT_OF_LORE = make_minion(
    name="Ancient of Lore",
    attack=5,
    health=5,
    mana_cost="{7}",
    text="Choose One - Draw 2 cards; or Restore 5 Health.",
    rarity="Epic",
    battlecry=ancient_of_lore_battlecry
)


def ancient_of_war_battlecry(obj, state):
    """Choose One - +5 Attack; or +5 Health and Taunt."""
    # AI: Always pick Taunt form
    if not obj.characteristics.abilities:
        obj.characteristics.abilities = []
    obj.characteristics.abilities.append({'keyword': 'taunt'})
    return [Event(type=EventType.PT_MODIFICATION,
                  payload={'object_id': obj.id, 'power_mod': 0, 'toughness_mod': 5, 'duration': 'permanent'},
                  source=obj.id)]

ANCIENT_OF_WAR = make_minion(
    name="Ancient of War",
    attack=5,
    health=5,
    mana_cost="{7}",
    text="Choose One - +5 Attack; or +5 Health and Taunt.",
    rarity="Epic",
    battlecry=ancient_of_war_battlecry
)


def cenarius_battlecry(obj, state):
    """Choose One - Give your other minions +2/+2; or Summon two 2/4 Treants with Taunt."""
    friendly = [mid for mid in get_friendly_minions(obj, state, exclude_self=False) if mid != obj.id]
    if len(friendly) >= 3:
        # Buff mode
        events = []
        for mid in friendly:
            events.append(Event(type=EventType.PT_MODIFICATION,
                payload={'object_id': mid, 'power_mod': 2, 'toughness_mod': 2, 'duration': 'permanent'},
                source=obj.id))
        return events
    else:
        # Summon mode
        events = []
        for _ in range(2):
            events.append(Event(type=EventType.CREATE_TOKEN, payload={
                'controller': obj.controller,
                'token': {
                    'name': 'Treant',
                    'power': 2,
                    'toughness': 4,
                    'types': {CardType.MINION},
                    'abilities': [{'keyword': 'taunt'}]
                }
            }, source=obj.id))
        return events

CENARIUS = make_minion(
    name="Cenarius",
    attack=5,
    health=8,
    mana_cost="{9}",
    text="Choose One - Give your other minions +2/+2; or Summon two 2/4 Treants with Taunt.",
    rarity="Legendary",
    battlecry=cenarius_battlecry
)


def bite_effect(obj, state, targets):
    """Give your hero +4 Attack this turn and 4 Armor."""
    player = state.players.get(obj.controller)
    if not player:
        return []

    player.weapon_attack += 4
    player.armor += 4

    # Register end-of-turn cleanup interceptor to remove the +4 attack
    def end_turn_filter(event, s):
        return event.type == EventType.TURN_END and event.payload.get('player') == obj.controller

    def end_turn_handler(event, s):
        p = s.players.get(obj.controller)
        if p:
            p.weapon_attack = max(0, p.weapon_attack - 4)
        # Self-remove this interceptor
        int_id = end_turn_handler._interceptor_id
        if int_id in s.interceptors:
            del s.interceptors[int_id]
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

    return []

BITE = make_spell(
    name="Bite",
    mana_cost="{4}",
    text="Give your hero +4 Attack this turn and 4 Armor.",
    rarity="Rare",
    spell_effect=bite_effect
)


def mark_of_nature_effect(obj, state, targets):
    """Choose One - Give a minion +4 Attack; or Give a minion +4 Health and Taunt."""
    friendly = get_friendly_minions(obj, state, exclude_self=False)
    if not friendly:
        return []
    target = random.choice(friendly)
    target_obj = state.objects.get(target)

    # AI: Prefer health/taunt on low-health minions, attack on high-health
    if target_obj and target_obj.characteristics.toughness <= 3:
        # Health + Taunt mode
        if not target_obj.characteristics.abilities:
            target_obj.characteristics.abilities = []
        target_obj.characteristics.abilities.append({'keyword': 'taunt'})
        return [Event(type=EventType.PT_MODIFICATION,
                      payload={'object_id': target, 'power_mod': 0, 'toughness_mod': 4, 'duration': 'permanent'},
                      source=obj.id)]
    else:
        # Attack mode
        return [Event(type=EventType.PT_MODIFICATION,
                      payload={'object_id': target, 'power_mod': 4, 'toughness_mod': 0, 'duration': 'permanent'},
                      source=obj.id)]

MARK_OF_NATURE = make_spell(
    name="Mark of Nature",
    mana_cost="{3}",
    text="Choose One - Give a minion +4 Attack; or Give a minion +4 Health and Taunt.",
    rarity="Common",
    spell_effect=mark_of_nature_effect
)


def savagery_effect(obj, state, targets):
    """Deal damage equal to your hero's Attack to a minion."""
    player = state.players.get(obj.controller)
    hero_attack = player.weapon_attack if player else 0
    if hero_attack > 0:
        enemies = get_enemy_minions(obj, state)
        if enemies:
            target = random.choice(enemies)
            return [Event(type=EventType.DAMAGE,
                         payload={'target': target, 'amount': hero_attack, 'source': obj.id, 'from_spell': True},
                         source=obj.id)]
    return []

SAVAGERY = make_spell(
    name="Savagery",
    mana_cost="{1}",
    text="Deal damage equal to your hero's Attack to a minion.",
    rarity="Rare",
    spell_effect=savagery_effect
)


def soul_of_the_forest_effect(obj, state, targets):
    """Give your minions 'Deathrattle: Summon a 2/2 Treant.'"""
    friendly = get_friendly_minions(obj, state, exclude_self=False)

    for mid in friendly:
        minion = state.objects.get(mid)
        if not minion:
            continue

        captured_mid = mid
        captured_controller = minion.controller

        def make_dr_filter(target_id):
            def dr_filter(event, state):
                if event.type != EventType.OBJECT_DESTROYED:
                    return False
                return event.payload.get('object_id') == target_id
            return dr_filter

        def make_dr_handler(controller_id):
            def dr_handler(event, state):
                return InterceptorResult(
                    action=InterceptorAction.REACT,
                    new_events=[Event(type=EventType.CREATE_TOKEN, payload={
                        'controller': controller_id,
                        'token': {
                            'name': 'Treant',
                            'power': 2,
                            'toughness': 2,
                            'types': {CardType.MINION},
                        }
                    }, source=event.payload.get('object_id', ''))]
                )
            return dr_handler

        interceptor = Interceptor(
            id=new_id(), source=captured_mid, controller=captured_controller,
            priority=InterceptorPriority.REACT,
            filter=make_dr_filter(captured_mid),
            handler=make_dr_handler(captured_controller),
            duration='once'
        )
        state.interceptors[interceptor.id] = interceptor

    return []

SOUL_OF_THE_FOREST = make_spell(
    name="Soul of the Forest",
    mana_cost="{4}",
    text="Give your minions \"Deathrattle: Summon a 2/2 Treant.\"",
    rarity="Common",
    spell_effect=soul_of_the_forest_effect
)


def gift_of_the_wild_effect(obj, state, targets):
    """Give all friendly minions +2/+2 and Taunt."""
    events = []
    friendly = get_friendly_minions(obj, state, exclude_self=False)
    for mid in friendly:
        events.append(Event(type=EventType.PT_MODIFICATION,
            payload={'object_id': mid, 'power_mod': 2, 'toughness_mod': 2, 'duration': 'permanent'},
            source=obj.id))
        events.append(Event(type=EventType.KEYWORD_GRANT,
            payload={'object_id': mid, 'keyword': 'taunt', 'duration': 'permanent'},
            source=obj.id))
    return events

GIFT_OF_THE_WILD = make_spell(
    name="Gift of the Wild",
    mana_cost="{8}",
    text="Give your minions +2/+2 and Taunt.",
    rarity="Common",
    spell_effect=gift_of_the_wild_effect
)


DRUID_CLASSIC = [
    INNERVATE,
    NATURALIZE,
    POWER_OF_THE_WILD,
    WRATH,
    KEEPER_OF_THE_GROVE,
    DRUID_OF_THE_CLAW,
    NOURISH,
    STARFALL,
    FORCE_OF_NATURE,
    ANCIENT_OF_LORE,
    ANCIENT_OF_WAR,
    CENARIUS,
    BITE,
    MARK_OF_NATURE,
    SAVAGERY,
    SOUL_OF_THE_FOREST,
    GIFT_OF_THE_WILD,
]


# ============================================================================
# EXPORTS
# ============================================================================

DRUID_CARDS = DRUID_BASIC + DRUID_CLASSIC
