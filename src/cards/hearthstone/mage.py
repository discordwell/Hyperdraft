"""Hearthstone Mage Cards - Basic + Classic"""
import random
from src.engine.game import make_minion, make_spell, make_secret
from src.engine.types import Event, EventType, CardType, GameObject, GameState, ZoneType, new_id
from src.engine.types import Interceptor, InterceptorPriority, InterceptorAction, InterceptorResult
from src.cards.interceptor_helpers import (
    make_spell_damage_boost, make_end_of_turn_trigger,
    get_enemy_targets, get_enemy_minions, get_all_minions,
    get_adjacent_enemy_minions, make_cost_reduction_aura,
    add_one_shot_cost_reduction
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
                'keywords': {'taunt'},
            }
        }, source=obj.id),
        Event(type=EventType.CREATE_TOKEN, payload={
            'controller': obj.controller,
            'token': {
                'name': 'Mirror Image',
                'power': 0,
                'toughness': 2,
                'types': {CardType.MINION},
                'keywords': {'taunt'},
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
        'amount': 1,
        'source': obj.id,
        'from_spell': True
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

def sorcerers_apprentice_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Your spells cost (1) less."""
    return make_cost_reduction_aura(obj, CardType.SPELL, 1, state=state)

SORCERERS_APPRENTICE = make_minion(
    name="Sorcerer's Apprentice",
    attack=3,
    health=2,
    mana_cost="{2}",
    text="Your spells cost (1) less.",
    setup_interceptors=sorcerers_apprentice_setup
)

def kirin_tor_mage_battlecry(obj: GameObject, state: GameState, targets=None) -> list[Event]:
    """Battlecry: The next Secret you play this turn costs (0)."""
    player = state.players.get(obj.controller)
    if player:
        # Secrets use CardType.SECRET - add a one-shot reduction of 99 (effectively free)
        add_one_shot_cost_reduction(player, CardType.SECRET, 99, duration='this_turn')
    return []

KIRIN_TOR_MAGE = make_minion(
    name="Kirin Tor Mage",
    attack=4,
    health=3,
    mana_cost="{3}",
    text="Battlecry: The next Secret you play this turn costs (0).",
    battlecry=kirin_tor_mage_battlecry
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
    for event in reversed(state.event_log[-5:]):
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

def ice_block_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Secret: When your hero takes fatal damage, prevent it and become Immune this turn."""
    def fatal_damage_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.DAMAGE:
            return False
        target_id = event.payload.get('target')
        if not target_id:
            return False
        # Check if target is the controller's hero
        player = state.players.get(obj.controller)
        if not player or player.hero_id != target_id:
            return False
        # Only trigger during opponent's turn (secret rule)
        if state.active_player == obj.controller:
            return False
        # Check if this damage would be fatal
        damage = event.payload.get('amount', 0)
        effective_hp = player.life + player.armor
        return damage >= effective_hp

    def prevent_fatal(event: Event, state: GameState) -> InterceptorResult:
        # Prevent the fatal damage
        # Also destroy the secret (move to graveyard)
        destroy_event = Event(
            type=EventType.ZONE_CHANGE,
            payload={
                'object_id': obj.id,
                'from_zone_type': obj.zone,
                'to_zone_type': ZoneType.GRAVEYARD
            },
            source=obj.id
        )
        return InterceptorResult(
            action=InterceptorAction.PREVENT,
            new_events=[destroy_event]
        )

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.PREVENT,
        filter=fatal_damage_filter,
        handler=prevent_fatal,
        duration='while_on_battlefield',
        uses_remaining=1
    )]

ICE_BLOCK = make_secret(
    name="Ice Block",
    mana_cost="{3}",
    text="Secret: When your hero takes fatal damage, prevent it and become Immune this turn.",
    setup_interceptors=ice_block_setup
)

def spellbender_filter(event: Event, state: GameState) -> bool:
    """Trigger when enemy casts a spell on a minion."""
    if event.type not in (EventType.CAST, EventType.SPELL_CAST):
        return False
    # Check if it's a spell (not a minion being played)
    types = event.payload.get('types', [])
    if CardType.SPELL not in types and 'SPELL' not in [str(t) for t in types]:
        return False
    # Check if the spell targets a minion (via spell_id targets)
    spell_id = event.payload.get('spell_id') or event.payload.get('card_id')
    if not spell_id:
        return False
    spell_obj = state.objects.get(spell_id)
    if not spell_obj:
        return False
    # Check if the spell has targets that are minions
    targets = event.payload.get('targets', [])
    if not targets:
        return False
    for tid in targets:
        target_obj = state.objects.get(tid)
        if target_obj and CardType.MINION in target_obj.characteristics.types:
            return True
    return False

def spellbender_effect(obj: GameObject, state: GameState) -> list[Event]:
    """Summon a 1/3 Spellbender minion (spell redirection is a simplification)."""
    return [Event(type=EventType.CREATE_TOKEN, payload={
        'controller': obj.controller,
        'token': {
            'name': 'Spellbender',
            'power': 1,
            'toughness': 3,
            'types': {CardType.MINION},
        }
    }, source=obj.id)]

SPELLBENDER = make_secret(
    name="Spellbender",
    mana_cost="{3}",
    text="Secret: When an enemy casts a spell on a minion, summon a 1/3 and it becomes the new target.",
    trigger_filter=spellbender_filter,
    trigger_effect=spellbender_effect
)

# ============================================================================
# CLASSIC SPELLS
# ============================================================================

def cone_of_cold_effect(obj: GameObject, state: GameState, targets=None) -> list[Event]:
    """Deal 1 damage to a minion and the minions next to it, and Freeze them."""
    enemy_minions = get_enemy_minions(obj, state)
    if not enemy_minions:
        return []

    # Pick a primary target from provided targets or random
    if targets:
        primary = targets[0] if isinstance(targets[0], str) else targets[0]
    else:
        primary = random.choice(enemy_minions)

    # Get actually adjacent minions using the adjacency helper
    adjacent = get_adjacent_enemy_minions(primary, state)
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
            'amount': 2,
            'source': obj.id,
            'from_spell': True
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

def ethereal_arcanist_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """If you control a Secret at the end of your turn, gain +2/+2."""
    def check_and_buff(event: Event, state: GameState) -> list[Event]:
        # Check if controller has a secret on the battlefield
        battlefield = state.zones.get('battlefield')
        if not battlefield:
            return []
        has_secret = False
        for oid in battlefield.objects:
            o = state.objects.get(oid)
            if (o and o.controller == obj.controller and o.id != obj.id and
                    CardType.SECRET in o.characteristics.types):
                has_secret = True
                break
        if has_secret:
            return [Event(type=EventType.PT_MODIFICATION, payload={
                'object_id': obj.id,
                'power_mod': 2,
                'toughness_mod': 2,
                'duration': 'permanent'
            }, source=obj.id)]
        return []

    return [make_end_of_turn_trigger(obj, check_and_buff)]

ETHEREAL_ARCANIST = make_minion(
    name="Ethereal Arcanist",
    attack=3,
    health=3,
    mana_cost="{4}",
    text="If you control a Secret at the end of your turn, gain +2/+2.",
    setup_interceptors=ethereal_arcanist_setup
)

def ice_lance_effect(obj: GameObject, state: GameState, targets=None) -> list[Event]:
    """Freeze a character. If it was already Frozen, deal 4 damage instead."""
    enemy_targets = get_enemy_targets(obj, state)
    if not enemy_targets:
        return []
    target_id = random.choice(enemy_targets)
    target = state.objects.get(target_id)
    if target and getattr(target.state, 'frozen', False):
        # Already frozen, deal 4 damage
        return [Event(type=EventType.DAMAGE, payload={
            'target': target_id, 'amount': 4, 'source': obj.id, 'from_spell': True
        }, source=obj.id)]
    else:
        # Freeze the character
        return [Event(type=EventType.FREEZE_TARGET, payload={'target': target_id}, source=obj.id)]

ICE_LANCE = make_spell(
    name="Ice Lance",
    mana_cost="{1}",
    text="Freeze a character. If it was already Frozen, deal 4 damage instead.",
    spell_effect=ice_lance_effect
)

def archmage_antonidas_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you cast a spell, add a Fireball to your hand."""
    def spell_cast_filter(event: Event, state: GameState) -> bool:
        if event.type not in (EventType.CAST, EventType.SPELL_CAST):
            return False
        caster = event.payload.get('caster') or event.controller
        return caster == obj.controller

    def add_fireball(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(type=EventType.ADD_TO_HAND, payload={
                'player': obj.controller,
                'card_def': FIREBALL
            }, source=obj.id)]
        )

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=spell_cast_filter,
        handler=add_fireball,
        duration='while_on_battlefield'
    )]

ARCHMAGE_ANTONIDAS = make_minion(
    name="Archmage Antonidas",
    attack=5,
    health=7,
    mana_cost="{7}",
    text="Whenever you cast a spell, add a Fireball to your hand.",
    rarity="Legendary",
    setup_interceptors=archmage_antonidas_setup
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
    ETHEREAL_ARCANIST,
    ICE_LANCE,
    ARCHMAGE_ANTONIDAS
]

MAGE_CARDS = MAGE_BASIC + MAGE_CLASSIC
