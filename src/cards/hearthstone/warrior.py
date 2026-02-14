"""Hearthstone Warrior Cards - Basic + Classic"""
import random
from src.engine.game import make_minion, make_spell, make_weapon
from src.engine.types import Event, EventType, CardType, GameObject, GameState, ZoneType, Interceptor, InterceptorPriority, InterceptorAction, InterceptorResult, new_id
from src.cards.interceptor_helpers import (
    get_enemy_targets, get_enemy_minions, get_friendly_minions, get_enemy_hero_id,
    make_enrage_trigger, make_whenever_takes_damage_trigger, get_all_minions
)
from src.cards.hearthstone.basic import FIERY_WAR_AXE, ARCANITE_REAPER


# ============================================================================
# BASIC WARRIOR CARDS
# ============================================================================

def execute_effect(obj, state, targets):
    """Destroy a damaged enemy minion."""
    enemies = get_enemy_minions(obj, state)
    damaged = [mid for mid in enemies if state.objects.get(mid) and state.objects[mid].state.damage > 0]
    if damaged:
        target = random.choice(damaged)
        return [Event(type=EventType.OBJECT_DESTROYED, payload={'object_id': target, 'reason': 'execute'}, source=obj.id)]
    return []

EXECUTE = make_spell(
    name="Execute",
    mana_cost="{1}",
    text="Destroy a damaged enemy minion.",
    spell_effect=execute_effect
)

def whirlwind_effect(obj, state, targets):
    """Deal 1 damage to ALL minions."""
    events = []
    for mid in get_all_minions(state):
        events.append(Event(type=EventType.DAMAGE, payload={'target': mid, 'amount': 1, 'source': obj.id, 'from_spell': True}, source=obj.id))
    return events

WHIRLWIND = make_spell(
    name="Whirlwind",
    mana_cost="{1}",
    text="Deal 1 damage to ALL minions.",
    spell_effect=whirlwind_effect
)

def heroic_strike_effect(obj, state, targets):
    """Give your hero +4 Attack this turn."""
    player = state.players.get(obj.controller)
    if not player:
        return []

    player.weapon_attack += 4

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

HEROIC_STRIKE = make_spell(
    name="Heroic Strike",
    mana_cost="{2}",
    text="Give your hero +4 Attack this turn.",
    spell_effect=heroic_strike_effect
)

def cleave_effect(obj, state, targets):
    """Deal 2 damage to 2 random enemy minions."""
    enemies = get_enemy_minions(obj, state)
    if not enemies:
        return []

    events = []
    targets_to_hit = min(2, len(enemies))
    chosen = random.sample(enemies, targets_to_hit)

    for target in chosen:
        events.append(Event(type=EventType.DAMAGE, payload={'target': target, 'amount': 2, 'source': obj.id, 'from_spell': True}, source=obj.id))

    return events

CLEAVE = make_spell(
    name="Cleave",
    mana_cost="{2}",
    text="Deal 2 damage to 2 random enemy minions.",
    spell_effect=cleave_effect
)

def shield_block_effect(obj, state, targets):
    """Gain 5 Armor. Draw a card."""
    return [
        Event(type=EventType.ARMOR_GAIN, payload={'player': obj.controller, 'amount': 5}, source=obj.id),
        Event(type=EventType.DRAW, payload={'player': obj.controller, 'count': 1}, source=obj.id)
    ]

SHIELD_BLOCK = make_spell(
    name="Shield Block",
    mana_cost="{3}",
    text="Gain 5 Armor. Draw a card.",
    spell_effect=shield_block_effect
)

def charge_spell_effect(obj, state, targets):
    """Give a friendly minion Charge."""
    friendlies = get_friendly_minions(obj, state)
    if friendlies:
        target = random.choice(friendlies)
        minion = state.objects.get(target)
        if minion:
            minion.characteristics.abilities.append({'keyword': 'charge'})
            minion.state.summoning_sickness = False
    return []

CHARGE_SPELL = make_spell(
    name="Charge",
    mana_cost="{1}",
    text="Give a friendly minion Charge.",
    spell_effect=charge_spell_effect
)

def warsong_commander_setup(obj, state):
    """Whenever you summon a minion with 3 or less Attack, give it Charge."""
    def summon_filter(event, s):
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        if entering_id == obj.id:
            return False
        entering = s.objects.get(entering_id)
        return (entering and entering.controller == obj.controller and
                CardType.MINION in entering.characteristics.types and
                entering.characteristics.power <= 3)

    def grant_charge(event, s):
        entering_id = event.payload.get('object_id')
        entering = s.objects.get(entering_id)
        if entering:
            if not any(a.get('keyword') == 'charge' for a in (entering.characteristics.abilities or [])):
                entering.characteristics.abilities.append({'keyword': 'charge'})
            entering.state.summoning_sickness = False
        return InterceptorResult(action=InterceptorAction.REACT)

    return [Interceptor(
        id=new_id(), source=obj.id, controller=obj.controller,
        priority=InterceptorPriority.REACT, filter=summon_filter, handler=grant_charge,
        duration='while_on_battlefield'
    )]

WARSONG_COMMANDER = make_minion(
    name="Warsong Commander",
    attack=2,
    health=3,
    mana_cost="{3}",
    text="Whenever you summon a minion with 3 or less Attack, give it Charge.",
    setup_interceptors=warsong_commander_setup
)

KOR_KRON_ELITE = make_minion(
    name="Kor'kron Elite",
    attack=4,
    health=3,
    mana_cost="{4}",
    keywords={"charge"},
    text="Charge"
)


# ============================================================================
# CLASSIC WARRIOR CARDS
# ============================================================================

def inner_rage_effect(obj, state, targets):
    """Deal 1 damage to a minion and give it +2 Attack."""
    all_minions = get_all_minions(state)
    if all_minions:
        target = random.choice(all_minions)
        return [
            Event(type=EventType.DAMAGE, payload={'target': target, 'amount': 1, 'source': obj.id, 'from_spell': True}, source=obj.id),
            Event(type=EventType.PT_MODIFICATION, payload={'object_id': target, 'power_mod': 2, 'toughness_mod': 0, 'duration': 'permanent'}, source=obj.id)
        ]
    return []

INNER_RAGE = make_spell(
    name="Inner Rage",
    mana_cost="{0}",
    text="Deal 1 damage to a minion and give it +2 Attack.",
    spell_effect=inner_rage_effect
)

def upgrade_effect(obj, state, targets):
    """If you have a weapon, give it +1/+1. Otherwise, equip a 1/3 weapon."""
    player = state.players.get(obj.controller)
    if not player:
        return []

    # Check if player has a weapon equipped
    weapon_id = None
    for oid, gobj in state.objects.items():
        if (gobj.controller == obj.controller and
            CardType.WEAPON in gobj.characteristics.types and
            gobj.zone == ZoneType.BATTLEFIELD):
            weapon_id = oid
            break

    if weapon_id:
        # Upgrade existing weapon - modify player stats (combat reads these)
        player.weapon_attack += 1
        player.weapon_durability += 1
        # Also sync hero state
        hero = state.objects.get(player.hero_id)
        if hero:
            hero.state.weapon_attack = player.weapon_attack
            hero.state.weapon_durability = player.weapon_durability
        return []
    else:
        # Equip 1/3 weapon
        return [Event(
            type=EventType.WEAPON_EQUIP,
            payload={'player': obj.controller, 'attack': 1, 'durability': 3},
            source=obj.id
        )]

UPGRADE = make_spell(
    name="Upgrade!",
    mana_cost="{1}",
    text="If you have a weapon, give it +1/+1. Otherwise, equip a 1/3 weapon.",
    spell_effect=upgrade_effect
)

def slam_effect(obj, state, targets):
    """Deal 2 damage to a minion. If it survives, draw a card."""
    all_minions = get_all_minions(state)
    if not all_minions:
        return []

    target = random.choice(all_minions)
    events = [Event(type=EventType.DAMAGE, payload={'target': target, 'amount': 2, 'source': obj.id, 'from_spell': True}, source=obj.id)]

    # Check if minion will survive (simple check - doesn't account for interceptors)
    minion = state.objects.get(target)
    if minion and (minion.characteristics.toughness - minion.state.damage) > 2:
        events.append(Event(type=EventType.DRAW, payload={'player': obj.controller, 'count': 1}, source=obj.id))

    return events

SLAM = make_spell(
    name="Slam",
    mana_cost="{2}",
    text="Deal 2 damage to a minion. If it survives, draw a card.",
    spell_effect=slam_effect
)

def cruel_taskmaster_battlecry(obj, state):
    """Battlecry: Deal 1 damage to a minion and give it +2 Attack."""
    all_minions = get_all_minions(state)
    # Exclude self
    all_minions = [mid for mid in all_minions if mid != obj.id]

    if all_minions:
        target = random.choice(all_minions)
        return [
            Event(type=EventType.DAMAGE, payload={'target': target, 'amount': 1, 'source': obj.id}, source=obj.id),
            Event(type=EventType.PT_MODIFICATION, payload={'object_id': target, 'power_mod': 2, 'toughness_mod': 0, 'duration': 'permanent'}, source=obj.id)
        ]
    return []

CRUEL_TASKMASTER = make_minion(
    name="Cruel Taskmaster",
    attack=2,
    health=2,
    mana_cost="{2}",
    text="Battlecry: Deal 1 damage to a minion and give it +2 Attack.",
    battlecry=cruel_taskmaster_battlecry
)

def frothing_berserker_setup(obj, state):
    """Whenever a minion takes damage, gain +1 Attack."""

    def any_minion_damaged(event, s):
        if event.type != EventType.DAMAGE:
            return False
        target = s.objects.get(event.payload.get('target'))
        return target is not None and CardType.MINION in target.characteristics.types

    def gain_attack(event, s):
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.PT_MODIFICATION,
                payload={'object_id': obj.id, 'power_mod': 1, 'toughness_mod': 0, 'duration': 'permanent'},
                source=obj.id
            )]
        )

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=any_minion_damaged,
        handler=gain_attack,
        duration='while_on_battlefield'
    )]

FROTHING_BERSERKER = make_minion(
    name="Frothing Berserker",
    attack=2,
    health=4,
    mana_cost="{3}",
    text="Whenever a minion takes damage, gain +1 Attack.",
    setup_interceptors=frothing_berserker_setup
)

def arathi_weaponsmith_battlecry(obj, state):
    """Battlecry: Equip a 2/2 weapon."""
    return [Event(
        type=EventType.WEAPON_EQUIP,
        payload={'player': obj.controller, 'attack': 2, 'durability': 2},
        source=obj.id
    )]

ARATHI_WEAPONSMITH = make_minion(
    name="Arathi Weaponsmith",
    attack=3,
    health=3,
    mana_cost="{4}",
    text="Battlecry: Equip a 2/2 weapon.",
    battlecry=arathi_weaponsmith_battlecry
)

def mortal_strike_effect(obj, state, targets):
    """Deal 4 damage. If you have 12 or less Health, deal 6 instead."""
    player = state.players.get(obj.controller)
    damage = 4

    if player and player.life <= 12:
        damage = 6

    enemies = get_enemy_targets(obj, state)
    if enemies:
        target = random.choice(enemies)
        return [Event(type=EventType.DAMAGE, payload={'target': target, 'amount': damage, 'source': obj.id, 'from_spell': True}, source=obj.id)]

    return []

MORTAL_STRIKE = make_spell(
    name="Mortal Strike",
    mana_cost="{4}",
    text="Deal 4 damage. If you have 12 or less Health, deal 6 instead.",
    spell_effect=mortal_strike_effect
)

def brawl_effect(obj, state, targets):
    """Destroy all minions except one (chosen randomly)."""
    all_m = get_all_minions(state)
    if len(all_m) <= 1:
        return []

    survivor = random.choice(all_m)
    events = []

    for mid in all_m:
        if mid != survivor:
            events.append(Event(
                type=EventType.OBJECT_DESTROYED,
                payload={'object_id': mid, 'reason': 'brawl'},
                source=obj.id
            ))

    return events

BRAWL = make_spell(
    name="Brawl",
    mana_cost="{5}",
    text="Destroy all minions except one (chosen randomly).",
    spell_effect=brawl_effect
)

def shield_slam_effect(obj, state, targets):
    """Deal 1 damage for each Armor you have."""
    player = state.players.get(obj.controller)
    if not player or player.armor <= 0:
        return []

    enemies = get_enemy_minions(obj, state)
    if enemies:
        target = random.choice(enemies)
        return [Event(
            type=EventType.DAMAGE,
            payload={'target': target, 'amount': player.armor, 'source': obj.id, 'from_spell': True},
            source=obj.id
        )]

    return []

SHIELD_SLAM = make_spell(
    name="Shield Slam",
    mana_cost="{1}",
    text="Deal 1 damage for each Armor you have.",
    spell_effect=shield_slam_effect
)

def battle_rage_effect(obj, state, targets):
    """Draw a card for each damaged friendly character."""
    damaged_count = 0

    # Check friendly minions
    for mid in get_friendly_minions(obj, state):
        minion = state.objects.get(mid)
        if minion and minion.state.damage > 0:
            damaged_count += 1

    # Check hero
    player = state.players.get(obj.controller)
    if player and player.life < player.max_life:
        damaged_count += 1

    if damaged_count > 0:
        return [Event(
            type=EventType.DRAW,
            payload={'player': obj.controller, 'count': damaged_count},
            source=obj.id
        )]

    return []

BATTLE_RAGE = make_spell(
    name="Battle Rage",
    mana_cost="{2}",
    text="Draw a card for each damaged friendly character.",
    spell_effect=battle_rage_effect
)

def commanding_shout_effect(obj, state, targets):
    """Your minions can't be reduced below 1 Health this turn. Draw a card."""
    # Min-1-health effect not implemented, but at minimum draw the card
    return [Event(
        type=EventType.DRAW,
        payload={'player': obj.controller, 'count': 1},
        source=obj.id
    )]

COMMANDING_SHOUT = make_spell(
    name="Commanding Shout",
    mana_cost="{2}",
    text="Your minions can't be reduced below 1 Health this turn. Draw a card.",
    spell_effect=commanding_shout_effect
)

def rampage_effect(obj, state, targets):
    """Give a damaged minion +3/+3."""
    all_minions = get_all_minions(state)
    damaged = [mid for mid in all_minions if state.objects.get(mid) and state.objects[mid].state.damage > 0]

    if damaged:
        target = random.choice(damaged)
        return [Event(
            type=EventType.PT_MODIFICATION,
            payload={'object_id': target, 'power_mod': 3, 'toughness_mod': 3, 'duration': 'permanent'},
            source=obj.id
        )]

    return []

RAMPAGE = make_spell(
    name="Rampage",
    mana_cost="{2}",
    text="Give a damaged minion +3/+3.",
    spell_effect=rampage_effect
)

GOREHOWL = make_weapon(
    name="Gorehowl",
    attack=7,
    durability=1,
    mana_cost="{7}",
    text="Attacking a minion costs 1 Attack instead of 1 Durability.",
    rarity="Epic"
    # Note: Text only - special attack mechanic not implemented
)

def grommash_setup(obj, state):
    """Enrage: +6 Attack."""
    return make_enrage_trigger(obj, attack_bonus=6)

GROMMASH_HELLSCREAM = make_minion(
    name="Grommash Hellscream",
    attack=4,
    health=9,
    mana_cost="{8}",
    keywords={"charge"},
    text="Charge. Enrage: +6 Attack.",
    rarity="Legendary",
    setup_interceptors=grommash_setup
)

def armorsmith_setup(obj, state):
    """Whenever a friendly minion takes damage, gain 1 Armor."""

    def friendly_damaged(event, s):
        if event.type != EventType.DAMAGE:
            return False
        target = s.objects.get(event.payload.get('target'))
        return (target is not None and
                target.controller == obj.controller and
                CardType.MINION in target.characteristics.types)

    def gain_armor(event, s):
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.ARMOR_GAIN,
                payload={'player': obj.controller, 'amount': 1},
                source=obj.id
            )]
        )

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=friendly_damaged,
        handler=gain_armor,
        duration='while_on_battlefield'
    )]

ARMORSMITH = make_minion(
    name="Armorsmith",
    attack=1,
    health=4,
    mana_cost="{2}",
    text="Whenever a friendly minion takes damage, gain 1 Armor.",
    setup_interceptors=armorsmith_setup
)


# ============================================================================
# EXPORTS
# ============================================================================

WARRIOR_BASIC = [
    EXECUTE,
    WHIRLWIND,
    HEROIC_STRIKE,
    CLEAVE,
    FIERY_WAR_AXE,
    SHIELD_BLOCK,
    CHARGE_SPELL,
    WARSONG_COMMANDER,
    KOR_KRON_ELITE,
    ARCANITE_REAPER
]

WARRIOR_CLASSIC = [
    INNER_RAGE,
    UPGRADE,
    SLAM,
    CRUEL_TASKMASTER,
    FROTHING_BERSERKER,
    ARATHI_WEAPONSMITH,
    MORTAL_STRIKE,
    BRAWL,
    SHIELD_SLAM,
    BATTLE_RAGE,
    COMMANDING_SHOUT,
    RAMPAGE,
    GOREHOWL,
    GROMMASH_HELLSCREAM,
    ARMORSMITH
]

WARRIOR_CARDS = WARRIOR_BASIC + WARRIOR_CLASSIC
