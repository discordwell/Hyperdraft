"""Hearthstone Mage Cards - Basic + Classic"""
import random
from src.engine.game import make_minion, make_spell, make_secret
from src.engine.types import Event, EventType, CardType, GameObject, GameState, ZoneType, new_id
from src.engine.types import Interceptor, InterceptorPriority, InterceptorAction, InterceptorResult
from src.cards.interceptor_helpers import (
    make_spell_damage_boost, make_end_of_turn_trigger,
    get_enemy_targets, get_enemy_minions, get_all_minions
)

# Re-export cards already defined in classic.py
from src.cards.hearthstone.classic import (
    ARCANE_MISSILES, FROSTBOLT, ARCANE_INTELLECT, FIREBALL,
    POLYMORPH, FLAMESTRIKE, WATER_ELEMENTAL
)

# ============================================================================
# BASIC MAGE CARDS (NEW)
# ============================================================================

def mirror_image_effect(obj: GameObject, state: GameState, targets=None) -> list[Event]:
    """Summon two 0/2 minions with Taunt."""
    return [
        Event(type=EventType.CREATE_TOKEN, payload={
            'controller': obj.controller,
            'token': {
                'name': 'Mirror Image',
                'power': 0,
                'toughness': 2,
                'types': {CardType.MINION},
                'keywords': {'Taunt'},
            }
        }, source=obj.id),
        Event(type=EventType.CREATE_TOKEN, payload={
            'controller': obj.controller,
            'token': {
                'name': 'Mirror Image',
                'power': 0,
                'toughness': 2,
                'types': {CardType.MINION},
                'keywords': {'Taunt'},
            }
        }, source=obj.id)
    ]

MIRROR_IMAGE = make_spell(
    name="Mirror Image",
    mana_cost="{1}",
    text="Summon two 0/2 minions with Taunt.",
    spell_effect=mirror_image_effect
)

def arcane_explosion_effect(obj: GameObject, state: GameState, targets=None) -> list[Event]:
    """Deal 1 damage to all enemy minions."""
    enemy_minions = get_enemy_minions(obj, state)
    return [Event(type=EventType.DAMAGE, payload={
        'target': minion_id,
        'amount': 1
    }, source=obj.id) for minion_id in enemy_minions]

ARCANE_EXPLOSION = make_spell(
    name="Arcane Explosion",
    mana_cost="{2}",
    text="Deal 1 damage to all enemy minions.",
    spell_effect=arcane_explosion_effect
)

def frost_nova_effect(obj: GameObject, state: GameState, targets=None) -> list[Event]:
    """Freeze all enemy minions."""
    enemy_minions = get_enemy_minions(obj, state)
    return [Event(type=EventType.FREEZE_TARGET, payload={
        'target': minion_id
    }, source=obj.id) for minion_id in enemy_minions]

FROST_NOVA = make_spell(
    name="Frost Nova",
    mana_cost="{3}",
    text="Freeze all enemy minions.",
    spell_effect=frost_nova_effect
)

# ============================================================================
# CLASSIC MAGE CARDS
# ============================================================================

def mana_wyrm_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you cast a spell, gain +1 Attack."""
    def spell_cast_filter(event: Event, state: GameState) -> bool:
        if event.type not in (EventType.CAST, EventType.SPELL_CAST):
            return False
        caster = event.payload.get('caster') or event.controller
        return caster == obj.controller

    def boost_attack(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(type=EventType.PT_MODIFICATION, payload={
                'object_id': obj.id,
                'power_mod': 1,
                'toughness_mod': 0,
                'duration': 'permanent'
            }, source=obj.id)]
        )

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=spell_cast_filter,
        handler=boost_attack,
        duration='while_on_battlefield'
    )]

MANA_WYRM = make_minion(
    name="Mana Wyrm",
    attack=1,
    health=3,
    mana_cost="{1}",
    text="Whenever you cast a spell, gain +1 Attack.",
    setup_interceptors=mana_wyrm_setup
)

SORCERERS_APPRENTICE = make_minion(
    name="Sorcerer's Apprentice",
    attack=3,
    health=2,
    mana_cost="{2}",
    text="Your spells cost (1) less."
)

KIRIN_TOR_MAGE = make_minion(
    name="Kirin Tor Mage",
    attack=4,
    health=3,
    mana_cost="{3}",
    text="Battlecry: The next Secret you play this turn costs (0)."
)

# ============================================================================
# SECRETS
# ============================================================================

def counterspell_filter(event: Event, state: GameState) -> bool:
    """Trigger when opponent casts a spell."""
    if event.type not in (EventType.CAST, EventType.SPELL_CAST):
        return False
    # Secret will check if caster is opponent
    return True

def counterspell_effect(obj: GameObject, state: GameState) -> list[Event]:
    """Counter the spell."""
    return [Event(type=EventType.SPELL_COUNTERED, payload={}, source=obj.id)]

COUNTERSPELL = make_secret(
    name="Counterspell",
    mana_cost="{3}",
    text="Secret: When your opponent casts a spell, Counter it.",
    trigger_filter=counterspell_filter,
    trigger_effect=counterspell_effect
)

def mirror_entity_filter(event: Event, state: GameState) -> bool:
    """Trigger when opponent plays a minion."""
    if event.type != EventType.ZONE_CHANGE:
        return False
    if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
        return False
    entering = state.objects.get(event.payload.get('object_id'))
    if not entering:
        return False
    return CardType.MINION in entering.characteristics.types

def mirror_entity_effect(obj: GameObject, state: GameState) -> list[Event]:
    """Summon a copy of the minion."""
    # Find the last minion that entered battlefield by opponent
    battlefield = state.zones.get('battlefield')
    if not battlefield:
        return []

    for oid in reversed(battlefield.objects):
        o = state.objects.get(oid)
        if o and o.controller != obj.controller and CardType.MINION in o.characteristics.types:
            return [Event(type=EventType.CREATE_TOKEN, payload={
                'controller': obj.controller,
                'token': {
                    'name': o.name,
                    'power': o.characteristics.power,
                    'toughness': o.characteristics.toughness,
                    'types': {CardType.MINION},
                    'subtypes': set(o.characteristics.subtypes),
                }
            }, source=obj.id)]
    return []

MIRROR_ENTITY = make_secret(
    name="Mirror Entity",
    mana_cost="{3}",
    text="Secret: When your opponent plays a minion, summon a copy of it.",
    trigger_filter=mirror_entity_filter,
    trigger_effect=mirror_entity_effect
)

def vaporize_filter(event: Event, state: GameState) -> bool:
    """Trigger when a minion attacks your hero."""
    if event.type != EventType.ATTACK_DECLARED:
        return False
    target = event.payload.get('target_id')
    if not target:
        return False
    target_obj = state.objects.get(target)
    if not target_obj:
        return False
    # Check if target is the hero (not a minion)
    return CardType.MINION not in target_obj.characteristics.types

def vaporize_effect(obj: GameObject, state: GameState) -> list[Event]:
    """Destroy the attacking minion."""
    # Find the attacker from recent events
    for event in reversed(state.events[-5:]):
        if event.type == EventType.ATTACK_DECLARED:
            attacker_id = event.payload.get('attacker_id')
            if attacker_id:
                return [Event(type=EventType.OBJECT_DESTROYED, payload={
                    'object_id': attacker_id, 'reason': 'vaporize'
                }, source=obj.id)]
    return []

VAPORIZE = make_secret(
    name="Vaporize",
    mana_cost="{3}",
    text="Secret: When a minion attacks your hero, destroy it.",
    trigger_filter=vaporize_filter,
    trigger_effect=vaporize_effect
)

def ice_barrier_filter(event: Event, state: GameState) -> bool:
    """Trigger when your hero is attacked."""
    if event.type != EventType.ATTACK_DECLARED:
        return False
    target = event.payload.get('target_id')
    if not target:
        return False
    target_obj = state.objects.get(target)
    if not target_obj:
        return False
    # Check if target is the hero (not a minion)
    return CardType.MINION not in target_obj.characteristics.types

def ice_barrier_effect(obj: GameObject, state: GameState) -> list[Event]:
    """Gain 8 Armor."""
    return [Event(type=EventType.ARMOR_GAIN, payload={
        'player': obj.controller,
        'amount': 8
    }, source=obj.id)]

ICE_BARRIER = make_secret(
    name="Ice Barrier",
    mana_cost="{3}",
    text="Secret: When your hero is attacked, gain 8 Armor.",
    trigger_filter=ice_barrier_filter,
    trigger_effect=ice_barrier_effect
)

ICE_BLOCK = make_secret(
    name="Ice Block",
    mana_cost="{3}",
    text="Secret: When your hero takes fatal damage, prevent it and become Immune this turn."
)

SPELLBENDER = make_secret(
    name="Spellbender",
    mana_cost="{3}",
    text="Secret: When an enemy casts a spell on a minion, summon a 1/3 and it becomes the new target."
)

# ============================================================================
# CLASSIC SPELLS
# ============================================================================

def cone_of_cold_effect(obj: GameObject, state: GameState, targets=None) -> list[Event]:
    """Deal 1 damage to a minion and the minions next to it, and Freeze them."""
    enemy_minions = get_enemy_minions(obj, state)
    if not enemy_minions:
        return []

    # Pick a primary target, then up to 2 "adjacent" (random others)
    primary = random.choice(enemy_minions)
    others = [m for m in enemy_minions if m != primary]
    adjacent = random.sample(others, min(2, len(others)))
    hit_targets = [primary] + adjacent

    events = []
    for tid in hit_targets:
        events.append(Event(type=EventType.DAMAGE, payload={
            'target': tid, 'amount': 1, 'source': obj.id, 'from_spell': True
        }, source=obj.id))
        events.append(Event(type=EventType.FREEZE_TARGET, payload={
            'target': tid
        }, source=obj.id))
    return events

CONE_OF_COLD = make_spell(
    name="Cone of Cold",
    mana_cost="{3}",
    text="Freeze a minion and the minions next to it, and deal 1 damage to them.",
    spell_effect=cone_of_cold_effect
)

def blizzard_effect(obj: GameObject, state: GameState, targets=None) -> list[Event]:
    """Deal 2 damage to all enemy minions and Freeze them."""
    enemy_minions = get_enemy_minions(obj, state)
    events = []
    for minion_id in enemy_minions:
        events.append(Event(type=EventType.DAMAGE, payload={
            'target': minion_id,
            'amount': 2
        }, source=obj.id))
        events.append(Event(type=EventType.FREEZE_TARGET, payload={
            'target': minion_id
        }, source=obj.id))
    return events

BLIZZARD = make_spell(
    name="Blizzard",
    mana_cost="{6}",
    text="Deal 2 damage to all enemy minions and Freeze them.",
    spell_effect=blizzard_effect
)

def pyroblast_effect(obj: GameObject, state: GameState, targets=None) -> list[Event]:
    """Deal 10 damage."""
    if targets:
        target = targets[0] if isinstance(targets[0], str) else targets[0]
    else:
        enemy_targets = get_enemy_targets(obj, state)
        if not enemy_targets:
            return []
        target = random.choice(enemy_targets)
    return [Event(type=EventType.DAMAGE, payload={
        'target': target,
        'amount': 10,
        'source': obj.id,
        'from_spell': True,
    }, source=obj.id)]

PYROBLAST = make_spell(
    name="Pyroblast",
    mana_cost="{10}",
    text="Deal 10 damage.",
    spell_effect=pyroblast_effect
)

# ============================================================================
# CLASSIC MINIONS
# ============================================================================

ETHEREAL_ARCANIST = make_minion(
    name="Ethereal Arcanist",
    attack=3,
    health=3,
    mana_cost="{4}",
    text="If you control a Secret at the end of your turn, gain +2/+2."
)

# ============================================================================
# EXPORTS
# ============================================================================

MAGE_BASIC = [
    MIRROR_IMAGE,
    ARCANE_EXPLOSION,
    FROST_NOVA,
    # Re-exported from classic.py
    ARCANE_MISSILES,
    FROSTBOLT,
    ARCANE_INTELLECT,
    FIREBALL,
    POLYMORPH,
    WATER_ELEMENTAL,
    FLAMESTRIKE
]

MAGE_CLASSIC = [
    MANA_WYRM,
    SORCERERS_APPRENTICE,
    KIRIN_TOR_MAGE,
    COUNTERSPELL,
    MIRROR_ENTITY,
    VAPORIZE,
    ICE_BARRIER,
    ICE_BLOCK,
    SPELLBENDER,
    CONE_OF_COLD,
    BLIZZARD,
    PYROBLAST,
    ETHEREAL_ARCANIST
]

MAGE_CARDS = MAGE_BASIC + MAGE_CLASSIC
