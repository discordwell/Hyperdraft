"""
Beyond Kamigawa — reusable archetype helpers.

Conventions:
- We encode YGO archetype membership in the existing ``subtypes`` field
  (e.g., ``subtypes={"Warrior", "Samurai"}`` puts a card in both the Warrior
  monster Type and the "Samurai" archetype). This avoids any engine change.
- Helpers in this file are thin wrappers over ``src.engine.yugioh_helpers``;
  they exist to keep card definitions readable, not to hide engine logic.
"""

from src.engine.types import (
    Event, EventType, GameState, GameObject, ZoneType,
    Interceptor, InterceptorAction, InterceptorPriority, InterceptorResult,
    new_id,
)
from src.engine.yugioh_helpers import (
    make_ygo_continuous_effect,
    make_ygo_destroy_trigger,
    make_ygo_summon_trigger,
    make_ygo_ignition_effect,
    revive_from_graveyard,
)


# =============================================================================
# Archetype-membership queries
# =============================================================================

def has_subtype(obj: GameObject, name: str) -> bool:
    """True if this object's card definition has subtype ``name``."""
    if obj is None or obj.card_def is None:
        return False
    return name in (obj.card_def.characteristics.subtypes or set())


def count_on_field(state: GameState, controller: str, subtype: str,
                   exclude_id: str = None) -> int:
    """Count monsters on ``controller``'s side of the field with ``subtype``."""
    zone = state.zones.get(f"monster_zone_{controller}")
    if not zone:
        return 0
    n = 0
    for oid in zone.objects:
        if not oid or oid == exclude_id:
            continue
        obj = state.objects.get(oid)
        if has_subtype(obj, subtype):
            n += 1
    return n


def find_in_graveyard(state: GameState, controller: str, subtype: str,
                      max_level: int = None) -> str | None:
    """Return the id of the first GY card with ``subtype`` (and optional level cap)."""
    gy = state.zones.get(f"graveyard_{controller}")
    if not gy:
        return None
    for cid in gy.objects:
        obj = state.objects.get(cid)
        if not obj or not obj.card_def:
            continue
        if subtype not in (obj.card_def.characteristics.subtypes or set()):
            continue
        if max_level is not None:
            lvl = getattr(obj.card_def, 'level', None) or 0
            if lvl > max_level:
                continue
        return cid
    return None


def is_modified(state: GameState, monster: GameObject) -> bool:
    """True if at least one Equip Spell is currently attached to this monster."""
    if monster is None:
        return False
    for obj in state.objects.values():
        if getattr(obj.state, 'equipped_to', None) == monster.id:
            return True
    return False


# =============================================================================
# Static lord effects
# =============================================================================

def make_archetype_lord(obj: GameObject, atk_bonus: int = 300,
                        def_bonus: int = 0, archetype: str = "Samurai"):
    """
    "While you control another <archetype> monster, this gains +atk_bonus / +def_bonus."

    Stacks per other monster of the archetype on the field — same as YGO's
    "Six Samurai" lords. Returns a single Interceptor.
    """
    def modifier_fn(event: Event, state: GameState) -> InterceptorResult:
        if event.payload.get('object_id') != obj.id:
            return InterceptorResult(action=InterceptorAction.PASS)
        n = count_on_field(state, obj.controller, archetype, exclude_id=obj.id)
        if n <= 0:
            return InterceptorResult(action=InterceptorAction.PASS)
        if event.type == EventType.QUERY_POWER and atk_bonus:
            event.payload['value'] = event.payload.get('value', 0) + atk_bonus * n
        elif event.type == EventType.QUERY_TOUGHNESS and def_bonus:
            event.payload['value'] = event.payload.get('value', 0) + def_bonus * n
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=event)
    return make_ygo_continuous_effect(obj, modifier_fn)


def make_archetype_team_lord(obj: GameObject, atk_bonus: int = 300,
                             def_bonus: int = 0, archetype: str = "Samurai",
                             *, affect_self: bool = False):
    """
    "<archetype> monsters you control gain +atk_bonus / +def_bonus."

    Unlike ``make_archetype_lord``, this modifies the queried teammate rather
    than the source object. It is used by banner-style glue cards whose text
    says "other" or "all" archetype monsters.
    """
    active_zones = {
        ZoneType.MONSTER_ZONE,
        ZoneType.SPELL_TRAP_ZONE,
        ZoneType.FIELD_SPELL_ZONE,
    }

    def _is_active_source(state: GameState) -> bool:
        source = state.objects.get(obj.id)
        return source is not None and source.zone in active_zones

    def modifier_fn(event: Event, state: GameState) -> InterceptorResult:
        if not _is_active_source(state):
            return InterceptorResult(action=InterceptorAction.PASS)
        target = state.objects.get(event.payload.get('object_id'))
        if target is None or target.controller != obj.controller:
            return InterceptorResult(action=InterceptorAction.PASS)
        if not affect_self and target.id == obj.id:
            return InterceptorResult(action=InterceptorAction.PASS)
        if not has_subtype(target, archetype):
            return InterceptorResult(action=InterceptorAction.PASS)
        if event.type == EventType.QUERY_POWER and atk_bonus:
            event.payload['value'] = event.payload.get('value', 0) + atk_bonus
        elif event.type == EventType.QUERY_TOUGHNESS and def_bonus:
            event.payload['value'] = event.payload.get('value', 0) + def_bonus
        else:
            return InterceptorResult(action=InterceptorAction.PASS)
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=event)

    return Interceptor(
        id=new_id(), source=obj.id, controller=obj.controller,
        priority=InterceptorPriority.QUERY,
        filter=lambda e, s: e.type in (EventType.QUERY_POWER, EventType.QUERY_TOUGHNESS),
        handler=modifier_fn, duration='until_leaves',
    )


# =============================================================================
# Soulshift (Kamigawa-block recursion)
# =============================================================================

def make_soulshift(obj: GameObject, max_level: int, archetype: str = "Spirit"):
    """
    "When this card is destroyed, you may Special Summon 1 <archetype> monster
    from your GY whose Level is <= max_level."

    Returns a destroy-trigger Interceptor.
    """
    def effect_fn(o: GameObject, state: GameState):
        target_id = find_in_graveyard(state, o.controller, archetype, max_level)
        if not target_id or target_id == o.id:
            return []
        return revive_from_graveyard(state, o.controller, target_id)
    return make_ygo_destroy_trigger(obj, effect_fn)


# =============================================================================
# Ninjutsu (Kamigawa-block hand-summon by bouncing another tribe member)
# =============================================================================

def _bounce_to_hand(state: GameState, target_id: str) -> None:
    """Internal: return ``target_id`` from monster zone to its owner's hand.

    Does not emit an event — the engine has no YGO_RETURN_TO_HAND yet, and
    the Ninjutsu observer chain only cares about the Special Summon that
    follows. Caller is responsible for the SS event.
    """
    target = state.objects.get(target_id)
    if not target:
        return
    zone = state.zones.get(f"monster_zone_{target.controller}")
    if zone:
        for i, oid in enumerate(zone.objects):
            if oid == target_id:
                zone.objects[i] = None
                break
    hand = state.zones.get(f"hand_{target.owner}")
    if hand is not None:
        hand.objects.append(target_id)
    target.zone = ZoneType.HAND
    target.state.face_down = False
    target.state.ygo_position = None
    target.controller = target.owner


def make_ninjutsu(obj: GameObject, archetype: str = "Ninja"):
    """
    "Once per turn (Quick Effect): you can Special Summon this card from your
    hand by returning 1 <archetype> monster you control to your hand."

    Mirrors MTG's Ninjutsu mechanic.
    """
    def effect_fn(o: GameObject, state: GameState):
        # Must be in hand to activate
        if o.zone != ZoneType.HAND:
            return []
        # Find an archetype member to bounce
        zone = state.zones.get(f"monster_zone_{o.controller}")
        if not zone:
            return []
        bounce_target = None
        for mid in zone.objects:
            if not mid or mid == o.id:
                continue
            cand = state.objects.get(mid)
            if has_subtype(cand, archetype):
                bounce_target = mid
                break
        if not bounce_target:
            return []
        _bounce_to_hand(state, bounce_target)
        events: list[Event] = []
        # Find empty slot for self
        slot = None
        for i in range(5):
            if i >= len(zone.objects) or zone.objects[i] is None:
                slot = i
                break
        if slot is None:
            return events
        while len(zone.objects) <= slot:
            zone.objects.append(None)
        # Remove from hand
        hand = state.zones.get(f"hand_{o.controller}")
        if hand and o.id in hand.objects:
            hand.objects.remove(o.id)
        zone.objects[slot] = o.id
        o.zone = ZoneType.MONSTER_ZONE
        o.state.ygo_position = 'face_up_atk'
        o.state.face_down = False
        events.append(Event(
            type=EventType.YGO_SPECIAL_SUMMON,
            payload={'player': o.controller, 'card_id': o.id,
                     'card_name': o.name, 'summon_type': 'ninjutsu'},
        ))
        return events
    return make_ygo_ignition_effect(obj, effect_fn)


# =============================================================================
# Bushido (legacy alias for archetype-lord with bonus on attack)
# =============================================================================

def make_bushido(obj: GameObject, atk_bonus: int = 300, archetype: str = "Samurai"):
    """
    "While you control another <archetype> monster, this gains +atk_bonus ATK."

    Simplified Bushido: continuous lord rather than battle-only.
    """
    return make_archetype_lord(obj, atk_bonus=atk_bonus, def_bonus=0, archetype=archetype)


__all__ = [
    "has_subtype", "count_on_field", "find_in_graveyard", "is_modified",
    "make_archetype_lord", "make_archetype_team_lord", "make_soulshift",
    "make_ninjutsu", "make_bushido",
]
