"""
Beyond Kamigawa — Umezawa Ninja archetype.

YGO mechanic: Ninjutsu hand-summon — once per turn (Ignition), Special Summon
this Ninja from your hand by returning 1 'Ninja' you control to your hand.
Search-engine triggers fire when a Ninja is destroyed; heavy graveyard
recursion via Toshiro Umezawa's Quick-Play recovery.

Identity: DARK/WATER Warriors. Hand-replay tempo combo. The deck wants
~6 small (Lv 4-) Ninjas as Ninjutsu fodder, ~4 high-level (Lv 5+) Ninjas to
hand-summon for value, and ~3 Tuners feeding the Synchro engine.

Design pillars: Toshiro Umezawa, Higure the Still Wind, Ink-Eyes (Champions
of Kamigawa) plus Kaito Shizuki and Satoru Umezawa (Neon Dynasty).

All cards in this archetype carry "Ninja" in their ``subtypes`` set so the
archetype-membership helpers in ``_archetype_helpers.py`` can find them.
"""

from src.engine.game import make_ygo_monster, make_ygo_spell, make_ygo_trap
from src.engine.types import Event, EventType, ZoneType
from src.engine.yugioh_helpers import (
    make_ygo_summon_trigger, make_ygo_destroy_trigger,
    make_ygo_continuous_effect, make_ygo_ignition_effect,
    make_ygo_equip_boost,
    revive_from_graveyard,
)
from ._archetype_helpers import (
    has_subtype, count_on_field, find_in_graveyard,
    make_archetype_lord, make_ninjutsu,
)


# =============================================================================
# Internal helpers — searches, hand/zone moves, board scans
# =============================================================================

def _search_library(state, controller: str, predicate) -> list[Event]:
    """Move the first matching card from library to hand. Empty list on miss."""
    library = state.zones.get(f"library_{controller}")
    hand = state.zones.get(f"hand_{controller}")
    if not library or not hand:
        return []
    for cid in list(library.objects):
        obj = state.objects.get(cid)
        if not obj or not obj.card_def:
            continue
        if not predicate(obj):
            continue
        library.objects.remove(cid)
        hand.objects.append(cid)
        obj.zone = ZoneType.HAND
        return [Event(type=EventType.YGO_DRAW,
                      payload={'player': controller, 'card_id': cid,
                               'card_name': obj.name, 'source': 'search'})]
    return []


def _is_ninja(obj) -> bool:
    return (obj is not None and obj.card_def is not None and
            "Ninja" in (obj.card_def.characteristics.subtypes or set()))


def _is_quick_play(obj) -> bool:
    if not obj or not obj.card_def:
        return False
    return getattr(obj.card_def, 'ygo_spell_type', None) == "Quick-Play"


def _draw_n(state, controller: str, n: int) -> list[Event]:
    """Draw ``n`` cards. Stops short if library empty."""
    library = state.zones.get(f"library_{controller}")
    hand = state.zones.get(f"hand_{controller}")
    if not library or not hand:
        return []
    events = []
    for _ in range(n):
        if not library.objects:
            break
        cid = library.objects.pop(0)
        hand.objects.append(cid)
        cobj = state.objects.get(cid)
        if cobj:
            cobj.zone = ZoneType.HAND
        events.append(Event(type=EventType.YGO_DRAW,
                            payload={'player': controller, 'count': 1}))
    return events


def _move_to_hand(state, controller: str, card_id: str) -> list[Event]:
    """Take a card from any zone and move it to ``controller``'s hand."""
    obj = state.objects.get(card_id)
    if not obj:
        return []
    for z in state.zones.values():
        # Clear all occurrences (including slot positions in monster_zone)
        for i, oid in enumerate(z.objects):
            if oid == card_id:
                z.objects[i] = None
        while card_id in z.objects:
            z.objects.remove(card_id)
    hand = state.zones.get(f"hand_{controller}")
    if hand is not None:
        hand.objects.append(card_id)
    obj.zone = ZoneType.HAND
    obj.state.face_down = False
    obj.state.ygo_position = None
    return [Event(type=EventType.YGO_DRAW,
                  payload={'player': controller, 'card_id': card_id,
                           'card_name': obj.name, 'source': 'recovery'})]


def _bounce_one_opponent_monster(state, controller: str) -> list[Event]:
    """Return the first face-up monster opponent controls to its owner's hand."""
    for pid in state.players:
        if pid == controller:
            continue
        zone = state.zones.get(f"monster_zone_{pid}")
        if not zone:
            continue
        for i, oid in enumerate(zone.objects):
            if not oid:
                continue
            obj = state.objects.get(oid)
            if obj and not obj.state.face_down:
                zone.objects[i] = None
                hand = state.zones.get(f"hand_{obj.owner}")
                if hand is not None:
                    hand.objects.append(oid)
                obj.zone = ZoneType.HAND
                obj.state.ygo_position = None
                obj.state.face_down = False
                obj.controller = obj.owner
                return [Event(type=EventType.YGO_DRAW,
                              payload={'player': obj.owner, 'card_id': oid,
                                       'card_name': obj.name,
                                       'source': 'bounce'})]
    return []


def _destroy_one_face_up_opponent(state, controller: str) -> list[Event]:
    """Destroy the first face-up monster opponent controls."""
    for pid in state.players:
        if pid == controller:
            continue
        zone = state.zones.get(f"monster_zone_{pid}")
        if not zone:
            continue
        for i, oid in enumerate(zone.objects):
            if not oid:
                continue
            obj = state.objects.get(oid)
            if obj and not obj.state.face_down:
                zone.objects[i] = None
                gy = state.zones.get(f"graveyard_{obj.owner}")
                if gy:
                    gy.objects.append(oid)
                obj.zone = ZoneType.GRAVEYARD
                obj.state.ygo_position = None
                return [Event(type=EventType.YGO_DESTROY,
                              payload={'card_id': oid, 'card_name': obj.name})]
    return []


def _tribute_one(state, controller: str, predicate=None,
                 exclude_id: str = None) -> str | None:
    """Send the first matching face-up monster on ``controller``'s side to GY."""
    zone = state.zones.get(f"monster_zone_{controller}")
    if not zone:
        return None
    for i, oid in enumerate(zone.objects):
        if not oid or oid == exclude_id:
            continue
        obj = state.objects.get(oid)
        if not obj:
            continue
        if predicate is not None and not predicate(obj):
            continue
        zone.objects[i] = None
        gy = state.zones.get(f"graveyard_{obj.owner}")
        if gy:
            gy.objects.append(oid)
        obj.zone = ZoneType.GRAVEYARD
        obj.state.face_down = False
        obj.state.ygo_position = None
        return oid
    return None


def _bounce_own_ninja_to_hand(state, controller: str,
                               exclude_id: str = None) -> str | None:
    """Return the first Ninja you control (other than ``exclude_id``) to hand.

    Used for spells/effects that bounce a Ninja as a cost. Returns the bounced
    card's id, or None if no eligible Ninja exists.
    """
    zone = state.zones.get(f"monster_zone_{controller}")
    if not zone:
        return None
    for i, oid in enumerate(zone.objects):
        if not oid or oid == exclude_id:
            continue
        obj = state.objects.get(oid)
        if not obj or not _is_ninja(obj):
            continue
        zone.objects[i] = None
        hand = state.zones.get(f"hand_{obj.owner}")
        if hand is not None:
            hand.objects.append(oid)
        obj.zone = ZoneType.HAND
        obj.state.face_down = False
        obj.state.ygo_position = None
        obj.controller = obj.owner
        return oid
    return None


def _ss_from_hand(state, controller: str, card_id: str,
                  position: str = 'face_up_atk',
                  summon_type: str = 'effect') -> list[Event]:
    """Special Summon ``card_id`` from ``controller``'s hand to a free monster slot."""
    obj = state.objects.get(card_id)
    if not obj:
        return []
    hand = state.zones.get(f"hand_{controller}")
    zone = state.zones.get(f"monster_zone_{controller}")
    if not hand or not zone or card_id not in hand.objects:
        return []
    slot = None
    for j in range(5):
        if j >= len(zone.objects) or zone.objects[j] is None:
            slot = j
            break
    if slot is None:
        return []
    while len(zone.objects) <= slot:
        zone.objects.append(None)
    hand.objects.remove(card_id)
    zone.objects[slot] = card_id
    obj.zone = ZoneType.MONSTER_ZONE
    obj.controller = controller
    obj.state.ygo_position = position
    obj.state.face_down = False
    return [Event(type=EventType.YGO_SPECIAL_SUMMON,
                  payload={'player': controller, 'card_id': card_id,
                           'card_name': obj.name, 'summon_type': summon_type})]


# =============================================================================
# Effect monsters — setup functions
# =============================================================================

def _ninjutsu_apprentice_setup(obj, state):
    """When sent to GY (e.g., as Ninjutsu fodder bounce-then-die proxy): search 1 Lv 4 or
    lower 'Ninja' from your Deck. Simplified to a destroy-trigger search."""
    def effect_fn(o, state):
        return _search_library(
            state, o.controller,
            lambda c: _is_ninja(c) and c.id != o.id and
                      (getattr(c.card_def, 'level', 99) or 99) <= 4
        )
    return [make_ygo_destroy_trigger(obj, effect_fn)]


def _walker_of_secret_ways_setup(obj, state):
    """When Normal Summoned: search 1 'Ninja' Spell or Trap from your Deck.

    "Ninja" Spell/Trap = a Spell or Trap whose name contains 'Ninja' or 'Ninjitsu'.
    """
    def is_ninja_st(c):
        if not c.card_def:
            return False
        name = c.card_def.name or ""
        if "Ninja" not in name and "Ninjitsu" not in name and "Shadow" not in name and "Smoke" not in name:
            return False
        # Spell or Trap?
        from src.engine.types import CardType
        types = c.card_def.characteristics.types or set()
        return CardType.YGO_SPELL in types or CardType.YGO_TRAP in types

    def effect_fn(o, state):
        return _search_library(state, o.controller, is_ninja_st)
    return [make_ygo_summon_trigger(obj, effect_fn)]


def _iga_style_cooper_setup(obj, state):
    """Once per turn (Ignition): bounce 1 'Ninja' you control; SS 1 Lv 4 or lower
    'Ninja' from your hand. (Cycles a small Ninja for value.)"""
    def effect_fn(o, state):
        bounced = _bounce_own_ninja_to_hand(state, o.controller, exclude_id=o.id)
        if not bounced:
            return []
        events: list[Event] = []
        # SS a Lv 4 or lower Ninja from hand
        hand = state.zones.get(f"hand_{o.controller}")
        if not hand:
            return events
        for cid in list(hand.objects):
            cobj = state.objects.get(cid)
            if not cobj or not _is_ninja(cobj):
                continue
            lvl = getattr(cobj.card_def, 'level', 99) or 99
            if lvl > 4:
                continue
            events.extend(_ss_from_hand(state, o.controller, cid,
                                         summon_type='cooper'))
            return events
        return events
    return [make_ygo_ignition_effect(obj, effect_fn)]


def _kabuto_mushi_setup(obj, state):
    """When Normal Summoned: SS 1 'Kabuto-Mushi' from your hand or Deck."""
    def effect_fn(o, state):
        # Try hand first
        hand = state.zones.get(f"hand_{o.controller}")
        if hand:
            for cid in list(hand.objects):
                if cid == o.id:
                    continue
                cobj = state.objects.get(cid)
                if cobj and cobj.name == "Kabuto-Mushi":
                    return _ss_from_hand(state, o.controller, cid,
                                          summon_type='swarm')
        # Fall back to library
        library = state.zones.get(f"library_{o.controller}")
        zone = state.zones.get(f"monster_zone_{o.controller}")
        if not library or not zone:
            return []
        for cid in list(library.objects):
            if cid == o.id:
                continue
            cobj = state.objects.get(cid)
            if cobj and cobj.name == "Kabuto-Mushi":
                slot = None
                for j in range(5):
                    if j >= len(zone.objects) or zone.objects[j] is None:
                        slot = j
                        break
                if slot is None:
                    return []
                while len(zone.objects) <= slot:
                    zone.objects.append(None)
                library.objects.remove(cid)
                zone.objects[slot] = cid
                cobj.zone = ZoneType.MONSTER_ZONE
                cobj.controller = o.controller
                cobj.state.ygo_position = 'face_up_def'
                return [Event(type=EventType.YGO_SPECIAL_SUMMON,
                              payload={'player': o.controller, 'card_id': cid,
                                       'card_name': cobj.name,
                                       'summon_type': 'swarm'})]
        return []
    return [make_ygo_summon_trigger(obj, effect_fn)]


def _cloak_of_mists_setup(obj, state):
    """When Normal Summoned: search 1 Lv 5+ 'Ninja' from your Deck."""
    def effect_fn(o, state):
        return _search_library(
            state, o.controller,
            lambda c: _is_ninja(c) and c.id != o.id and
                      (getattr(c.card_def, 'level', 0) or 0) >= 5
        )
    return [make_ygo_summon_trigger(obj, effect_fn)]


def _ninja_deep_hours_setup(obj, state):
    """Ninjutsu. When SS by Ninjutsu: draw 1 (gated on summon_type)."""
    def effect_fn(o, state):
        # Only fires when Ninjutsu-summoned. The summon-trigger filter checks for
        # this card_id, so we additionally inspect the GO's recent summon path.
        # Simplified: always draw 1 on any SS — Ninjutsu is by far the typical path.
        return _draw_n(state, o.controller, 1)
    def filter_fn(event, state):
        return (event.type == EventType.YGO_SPECIAL_SUMMON and
                event.payload.get('card_id') == obj.id and
                event.payload.get('summon_type') == 'ninjutsu')
    from src.engine.types import (Interceptor, InterceptorAction,
                                  InterceptorPriority, InterceptorResult, new_id)
    def handler(event, state):
        return InterceptorResult(action=InterceptorAction.REACT,
                                 new_events=effect_fn(obj, state) or [])
    return [
        make_ninjutsu(obj),
        Interceptor(id=new_id(), source=obj.id, controller=obj.controller,
                    priority=InterceptorPriority.REACT, filter=filter_fn,
                    handler=handler, duration='until_leaves'),
    ]


def _mistblade_shinobi_setup(obj, state):
    """Ninjutsu. When SS by Ninjutsu: bounce 1 monster opponent controls."""
    def effect_fn(o, state):
        return _bounce_one_opponent_monster(state, o.controller)
    def filter_fn(event, state):
        return (event.type == EventType.YGO_SPECIAL_SUMMON and
                event.payload.get('card_id') == obj.id and
                event.payload.get('summon_type') == 'ninjutsu')
    from src.engine.types import (Interceptor, InterceptorAction,
                                  InterceptorPriority, InterceptorResult, new_id)
    def handler(event, state):
        return InterceptorResult(action=InterceptorAction.REACT,
                                 new_events=effect_fn(obj, state) or [])
    return [
        make_ninjutsu(obj),
        Interceptor(id=new_id(), source=obj.id, controller=obj.controller,
                    priority=InterceptorPriority.REACT, filter=filter_fn,
                    handler=handler, duration='until_leaves'),
    ]


def _higures_apprentice_setup(obj, state):
    """When Normal or Special Summoned: search 1 Lv 4 or lower 'Ninja' from your Deck."""
    def effect_fn(o, state):
        return _search_library(
            state, o.controller,
            lambda c: _is_ninja(c) and c.id != o.id and
                      (getattr(c.card_def, 'level', 99) or 99) <= 4
        )
    return [make_ygo_summon_trigger(obj, effect_fn)]


def _ninja_grandmaster_sasuke_setup(obj, state):
    """When this card declares an attack on a face-down monster: banish it without flipping."""
    def modifier_fn(event, state):
        from src.engine.types import (InterceptorAction, InterceptorResult)
        # When attack is declared by this card against a face-down target, skip
        # damage step and banish target. We hook YGO_BATTLE_DECLARE.
        if event.payload.get('attacker_id') != obj.id:
            return InterceptorResult(action=InterceptorAction.PASS)
        target_id = event.payload.get('target_id')
        if not target_id:
            return InterceptorResult(action=InterceptorAction.PASS)
        target = state.objects.get(target_id)
        if not target or not target.state.face_down:
            return InterceptorResult(action=InterceptorAction.PASS)
        # Banish target
        for z in state.zones.values():
            for i, oid in enumerate(z.objects):
                if oid == target_id:
                    z.objects[i] = None
        banish = state.zones.get(f"banished_{target.owner}")
        if banish is None:
            banish = state.zones.get(f"graveyard_{target.owner}")
        if banish is not None:
            banish.objects.append(target_id)
        target.zone = ZoneType.EXILE if hasattr(ZoneType, 'EXILE') else ZoneType.GRAVEYARD
        target.state.ygo_position = None
        target.state.face_down = False
        # Cancel the battle by returning PREVENT
        return InterceptorResult(action=InterceptorAction.PREVENT)
    from src.engine.types import (Interceptor, InterceptorAction,
                                  InterceptorPriority, InterceptorResult, new_id)
    def filter_fn(event, state):
        return event.type == EventType.YGO_BATTLE_DECLARE
    return [Interceptor(id=new_id(), source=obj.id, controller=obj.controller,
                        priority=InterceptorPriority.PREVENT, filter=filter_fn,
                        handler=modifier_fn, duration='until_leaves')]


def _sakashima_imposter_setup(obj, state):
    """When Normal Summoned: copy the name of 1 face-up 'Ninja' you control.

    Simplified: copy the first 'Ninja' subtype set onto self by adding the source
    monster's name as an alias and inheriting its ATK. Acts as a hand-replay
    enabler since two same-named Ninjas cannot exist in classical YGO, but in
    this engine we just adopt the ATK value.
    """
    def effect_fn(o, state):
        zone = state.zones.get(f"monster_zone_{o.controller}")
        if not zone:
            return []
        for mid in zone.objects:
            if not mid or mid == o.id:
                continue
            target = state.objects.get(mid)
            if target and _is_ninja(target):
                # Inherit ATK as bonus until EP
                their_atk = getattr(target.card_def, 'atk', 0) or 0
                our_atk = getattr(o.card_def, 'atk', 0) or 0
                bonus = max(0, their_atk - our_atk)
                if bonus:
                    o.state.atk_bonus_eot = (
                        getattr(o.state, 'atk_bonus_eot', 0) + bonus
                    )
                return []
        return []
    return [make_ygo_summon_trigger(obj, effect_fn)]


def _satoru_umezawa_setup(obj, state):
    """While face-up: Lv 5+ Warriors in your hand are also treated as 'Ninja' and can
    be Ninjutsu-summoned by bouncing a Lv 3- 'Ninja'.

    Simplified continuous: while Satoru is face-up on the field, automatically
    tag every Lv 5+ Warrior in the controller's hand with the 'Ninja' subtype.
    The Ninjutsu helper then picks them up for free.
    """
    def modifier_fn(event, state):
        from src.engine.types import (InterceptorAction, InterceptorResult)
        # Re-tag on every QUERY_POWER pulse — the engine pulses these often.
        source = state.objects.get(obj.id)
        if not source or source.zone != ZoneType.MONSTER_ZONE:
            return InterceptorResult(action=InterceptorAction.PASS)
        hand = state.zones.get(f"hand_{obj.controller}")
        if hand:
            for cid in hand.objects:
                cobj = state.objects.get(cid)
                if not cobj or not cobj.card_def:
                    continue
                if "Warrior" not in (cobj.card_def.characteristics.subtypes or set()):
                    continue
                lvl = getattr(cobj.card_def, 'level', 0) or 0
                if lvl < 5:
                    continue
                # Add Ninja tag
                if cobj.card_def.characteristics.subtypes is None:
                    cobj.card_def.characteristics.subtypes = set()
                cobj.card_def.characteristics.subtypes.add("Ninja")
        return InterceptorResult(action=InterceptorAction.PASS)
    return [make_ygo_continuous_effect(obj, modifier_fn)]


def _throat_slitter_setup(obj, state):
    """Ninjutsu. When SS by Ninjutsu: destroy 1 face-up monster opponent controls
    during End Phase. Simplified to immediate destroy on Ninjutsu summon."""
    def effect_fn(o, state):
        return _destroy_one_face_up_opponent(state, o.controller)
    def filter_fn(event, state):
        return (event.type == EventType.YGO_SPECIAL_SUMMON and
                event.payload.get('card_id') == obj.id and
                event.payload.get('summon_type') == 'ninjutsu')
    from src.engine.types import (Interceptor, InterceptorAction,
                                  InterceptorPriority, InterceptorResult, new_id)
    def handler(event, state):
        return InterceptorResult(action=InterceptorAction.REACT,
                                 new_events=effect_fn(obj, state) or [])
    return [
        make_ninjutsu(obj),
        Interceptor(id=new_id(), source=obj.id, controller=obj.controller,
                    priority=InterceptorPriority.REACT, filter=filter_fn,
                    handler=handler, duration='until_leaves'),
    ]


def _higure_still_wind_setup(obj, state):
    """Ninjutsu. When destroyed: search 1 'Ninja' from your Deck."""
    def search_fn(o, state):
        return _search_library(state, o.controller,
                               lambda c: _is_ninja(c) and c.id != o.id)
    return [make_ninjutsu(obj), make_ygo_destroy_trigger(obj, search_fn)]


def _ink_eyes_setup(obj, state):
    """Ninjutsu (Lv 4+ Ninja). When this card destroys an opponent's monster by
    battle: SS that monster from their GY to your side of the field."""
    def steal_fn(event, state):
        from src.engine.types import (Interceptor, InterceptorAction,
                                      InterceptorPriority, InterceptorResult,
                                      new_id)
        # Look at the destroy payload — was Ink-Eyes the attacker?
        if event.type != EventType.YGO_DESTROY:
            return InterceptorResult(action=InterceptorAction.PASS)
        attacker_id = event.payload.get('attacker_id')
        if attacker_id != obj.id:
            return InterceptorResult(action=InterceptorAction.PASS)
        target_id = event.payload.get('card_id')
        if not target_id or target_id == obj.id:
            return InterceptorResult(action=InterceptorAction.PASS)
        target = state.objects.get(target_id)
        if not target:
            return InterceptorResult(action=InterceptorAction.PASS)
        # The destroy already moves it to its owner's GY. We then revive it under us.
        new_events = revive_from_graveyard(state, obj.controller, target_id)
        return InterceptorResult(action=InterceptorAction.REACT,
                                 new_events=new_events or [])
    from src.engine.types import (Interceptor, InterceptorAction,
                                  InterceptorPriority, InterceptorResult, new_id)
    def filter_fn(event, state):
        return event.type == EventType.YGO_DESTROY
    return [
        make_ninjutsu(obj),
        Interceptor(id=new_id(), source=obj.id, controller=obj.controller,
                    priority=InterceptorPriority.REACT, filter=filter_fn,
                    handler=steal_fn, duration='until_leaves'),
    ]


def _toshiro_umezawa_setup(obj, state):
    """Ninjutsu. Once per turn (Ignition): target 1 Quick-Play Spell in your GY;
    add it to your hand."""
    def effect_fn(o, state):
        gy = state.zones.get(f"graveyard_{o.controller}")
        if not gy:
            return []
        for cid in list(gy.objects):
            cobj = state.objects.get(cid)
            if cobj and _is_quick_play(cobj):
                return _move_to_hand(state, o.controller, cid)
        return []
    return [make_ninjutsu(obj), make_ygo_ignition_effect(obj, effect_fn)]


def _kaito_shizuki_setup(obj, state):
    """Ninjutsu. When SS by Ninjutsu: draw 1 card. (Pendulum scale 5 effect, when in
    the Pendulum Zone, would protect named Ninjas — simplified: draw on summon.)"""
    def effect_fn(o, state):
        return _draw_n(state, o.controller, 1)
    def filter_fn(event, state):
        return (event.type == EventType.YGO_SPECIAL_SUMMON and
                event.payload.get('card_id') == obj.id and
                event.payload.get('summon_type') == 'ninjutsu')
    from src.engine.types import (Interceptor, InterceptorAction,
                                  InterceptorPriority, InterceptorResult, new_id)
    def handler(event, state):
        return InterceptorResult(action=InterceptorAction.REACT,
                                 new_events=effect_fn(obj, state) or [])
    return [
        make_ninjutsu(obj),
        Interceptor(id=new_id(), source=obj.id, controller=obj.controller,
                    priority=InterceptorPriority.REACT, filter=filter_fn,
                    handler=handler, duration='until_leaves'),
    ]


# =============================================================================
# Card definitions — Monsters
# =============================================================================

NINJUTSU_APPRENTICE = make_ygo_monster(
    "Ninjutsu Apprentice", atk=400, def_val=400, level=2,
    attribute="DARK", ygo_monster_type="Effect",
    subtypes={"Warrior", "Ninja"},
    text="When this card is destroyed: add 1 Lv 4 or lower 'Ninja' from your Deck to your hand.",
    setup_interceptors=_ninjutsu_apprentice_setup,
)

KABUTO_MUSHI = make_ygo_monster(
    "Kabuto-Mushi", atk=300, def_val=300, level=1,
    attribute="DARK", ygo_monster_type="Effect",
    subtypes={"Insect", "Ninja"},
    text="When Normal Summoned: SS 1 'Kabuto-Mushi' from your hand or Deck in face-up DEF.",
    setup_interceptors=_kabuto_mushi_setup,
)

WALKER_OF_SECRET_WAYS = make_ygo_monster(
    "Walker of Secret Ways", atk=1100, def_val=900, level=3,
    attribute="WATER", ygo_monster_type="Effect",
    subtypes={"Warrior", "Ninja"},
    text="When Normal Summoned: search 1 'Ninja' Spell or Trap from your Deck.",
    setup_interceptors=_walker_of_secret_ways_setup,
)

IGA_STYLE_COOPER = make_ygo_monster(
    "Iga-Style Cooper", atk=900, def_val=800, level=2,
    attribute="WATER", ygo_monster_type="Effect", is_tuner=True,
    subtypes={"Warrior", "Ninja"},
    text="Once per turn: bounce 1 'Ninja' you control; SS 1 Lv 4 or lower 'Ninja' from your hand.",
    setup_interceptors=_iga_style_cooper_setup,
)

CLOAK_OF_MISTS = make_ygo_monster(
    "Cloak of Mists", atk=400, def_val=200, level=1,
    attribute="DARK", ygo_monster_type="Effect",
    subtypes={"Warrior", "Ninja"},
    text="When Normal Summoned: search 1 Lv 5+ 'Ninja' from your Deck.",
    setup_interceptors=_cloak_of_mists_setup,
)

NINJA_OF_THE_DEEP_HOURS = make_ygo_monster(
    "Ninja of the Deep Hours", atk=1500, def_val=1200, level=4,
    attribute="WATER", ygo_monster_type="Effect",
    subtypes={"Warrior", "Ninja"},
    text="Ninjutsu. When Special Summoned by Ninjutsu: draw 1 card.",
    setup_interceptors=_ninja_deep_hours_setup,
)

MISTBLADE_SHINOBI = make_ygo_monster(
    "Mistblade Shinobi", atk=1600, def_val=1200, level=4,
    attribute="WATER", ygo_monster_type="Effect",
    subtypes={"Warrior", "Ninja"},
    text="Ninjutsu. When Special Summoned by Ninjutsu: bounce 1 monster opponent controls.",
    setup_interceptors=_mistblade_shinobi_setup,
)

HIGURES_APPRENTICE = make_ygo_monster(
    "Higure's Apprentice", atk=1400, def_val=1200, level=4,
    attribute="WATER", ygo_monster_type="Effect",
    subtypes={"Warrior", "Ninja"},
    text="When Normal or Special Summoned: search 1 Lv 4 or lower 'Ninja' from your Deck.",
    setup_interceptors=_higures_apprentice_setup,
)

NINJA_GRANDMASTER_SASUKE = make_ygo_monster(
    "Ninja Grandmaster Sasuke", atk=1800, def_val=1000, level=4,
    attribute="DARK", ygo_monster_type="Effect",
    subtypes={"Warrior", "Ninja"},
    text="When this card attacks a face-down monster: banish that monster without flipping it.",
    setup_interceptors=_ninja_grandmaster_sasuke_setup,
)

SAKASHIMA_THE_IMPOSTER = make_ygo_monster(
    "Sakashima the Imposter", atk=1500, def_val=1500, level=4,
    attribute="WATER", ygo_monster_type="Effect",
    subtypes={"Warrior", "Ninja"},
    text="When Normal Summoned: copy a face-up 'Ninja' you control's ATK until End Phase.",
    setup_interceptors=_sakashima_imposter_setup,
)

SATORU_UMEZAWA = make_ygo_monster(
    "Satoru Umezawa", atk=1700, def_val=1500, level=4,
    attribute="DARK", ygo_monster_type="Effect",
    subtypes={"Warrior", "Ninja"},
    text="While face-up: Lv 5+ Warrior monsters in your hand are also treated as 'Ninja' and can be Ninjutsu-summoned.",
    setup_interceptors=_satoru_umezawa_setup,
)

THROAT_SLITTER = make_ygo_monster(
    "Throat Slitter", atk=1900, def_val=1300, level=5,
    attribute="DARK", ygo_monster_type="Effect",
    subtypes={"Warrior", "Ninja"},
    text="Ninjutsu. When Special Summoned by Ninjutsu: destroy 1 face-up monster opponent controls.",
    setup_interceptors=_throat_slitter_setup,
)

HIGURE_THE_STILL_WIND = make_ygo_monster(
    "Higure, the Still Wind", atk=2000, def_val=1800, level=5,
    attribute="DARK", ygo_monster_type="Effect",
    subtypes={"Warrior", "Ninja"},
    text="Ninjutsu. When this card is destroyed: search 1 'Ninja' from your Deck.",
    setup_interceptors=_higure_still_wind_setup,
)

INK_EYES_SERVANT_OF_ONI = make_ygo_monster(
    "Ink-Eyes, Servant of Oni", atk=2200, def_val=1700, level=5,
    attribute="DARK", ygo_monster_type="Effect",
    subtypes={"Beast", "Ninja"},
    text="Ninjutsu (using Lv 4+ 'Ninja'). When this card destroys an opponent's monster by battle: SS that monster from their GY to your side of the field.",
    setup_interceptors=_ink_eyes_setup,
)

TOSHIRO_UMEZAWA = make_ygo_monster(
    "Toshiro Umezawa", atk=2300, def_val=2000, level=6,
    attribute="DARK", ygo_monster_type="Effect", is_tuner=True,
    subtypes={"Warrior", "Ninja"},
    text="Ninjutsu. Once per turn: target 1 Quick-Play Spell in your GY; add it to your hand.",
    setup_interceptors=_toshiro_umezawa_setup,
)

KAITO_SHIZUKI = make_ygo_monster(
    "Kaito Shizuki", atk=2500, def_val=2000, level=7,
    attribute="WATER", ygo_monster_type="Effect",
    subtypes={"Warrior", "Ninja"},
    text="Pendulum Scale 5: 'Ninja' you control cannot be targeted by opponent's effects. Ninjutsu. When SS by Ninjutsu: draw 1 card.",
    setup_interceptors=_kaito_shizuki_setup,
    pendulum_scale=5,
)


# =============================================================================
# Card definitions — Spells
# =============================================================================

def _ninjitsu_decoy_setup(obj, state):
    """Continuous: 'Ninja' you control cannot be targeted by opponent's card effects.

    Simplified: register a pseudo-immunity flag we cannot enforce engine-wide,
    so this is essentially a flavor placeholder. Returns no interceptors yet.
    """
    return []


NINJITSU_ART_OF_DECOY = make_ygo_spell(
    "Ninjitsu Art of Decoy", ygo_spell_type="Continuous",
    text="'Ninja' monsters you control cannot be targeted by opponent's card effects.",
    setup_interceptors=_ninjitsu_decoy_setup,
)


def _ninjitsu_transformation_resolve(event, state):
    """Quick-Play: tribute 1 face-up 'Ninja' you control; SS 1 Spirit-Dragon Synchro
    or Lv 5+ 'Ninja' from your Extra Deck or GY.

    Simplified: SS the first Lv 5+ Ninja from your GY in place of the tribute.
    """
    controller = event.payload.get('player')
    if not controller:
        return []
    sacrificed = _tribute_one(state, controller, _is_ninja)
    if not sacrificed:
        return []
    gy = state.zones.get(f"graveyard_{controller}")
    if gy:
        for cid in list(gy.objects):
            if cid == sacrificed:
                continue
            cobj = state.objects.get(cid)
            if cobj and _is_ninja(cobj):
                lvl = getattr(cobj.card_def, 'level', 0) or 0
                if lvl >= 5:
                    return revive_from_graveyard(state, controller, cid)
    return []


NINJITSU_ART_OF_TRANSFORMATION = make_ygo_spell(
    "Ninjitsu Art of Transformation", ygo_spell_type="Quick-Play",
    text="Tribute 1 face-up 'Ninja' you control; SS 1 Lv 5+ 'Ninja' from your GY.",
    resolve=_ninjitsu_transformation_resolve,
)


def _mistblades_cunning_resolve(event, state):
    """Quick-Play: target 1 'Ninja' you control; it gains 1500 ATK and bounces 1
    monster when it inflicts battle damage. Simplified: +1500 ATK EOT.
    """
    targets = event.payload.get('targets') or []
    controller = event.payload.get('player')
    target_id = targets[0] if targets else None
    if not target_id and controller:
        zone = state.zones.get(f"monster_zone_{controller}")
        if zone:
            for oid in zone.objects:
                if oid:
                    cobj = state.objects.get(oid)
                    if cobj and _is_ninja(cobj):
                        target_id = oid
                        break
    if not target_id:
        return []
    target = state.objects.get(target_id)
    if target and _is_ninja(target):
        target.state.atk_bonus_eot = (
            getattr(target.state, 'atk_bonus_eot', 0) + 1500
        )
    return []


MISTBLADES_CUNNING = make_ygo_spell(
    "Mistblade's Cunning", ygo_spell_type="Quick-Play",
    text="Target 1 'Ninja' you control: gains 1500 ATK until End Phase.",
    resolve=_mistblades_cunning_resolve,
)


def _path_of_the_shadow_resolve(event, state):
    """Field Spell — flavor only; piercing not modeled."""
    return []


PATH_OF_THE_SHADOW = make_ygo_spell(
    "Path of the Shadow", ygo_spell_type="Field",
    text="'Ninja' monsters you control inflict piercing battle damage.",
    resolve=_path_of_the_shadow_resolve,
)


def _smoke_bomb_resolve(event, state):
    """Normal: bounce 1 'Ninja' you control to your hand; draw 2."""
    controller = event.payload.get('player')
    if not controller:
        return []
    bounced = _bounce_own_ninja_to_hand(state, controller)
    if not bounced:
        return []
    return _draw_n(state, controller, 2)


SMOKE_BOMB = make_ygo_spell(
    "Smoke Bomb", ygo_spell_type="Normal",
    text="Return 1 'Ninja' you control to your hand; draw 2 cards.",
    resolve=_smoke_bomb_resolve,
)


def _brilliant_halberd_setup(obj, state):
    """Equip: equipped 'Ninja' gains 500 ATK. (Extra-attack flavor not modeled.)"""
    return [make_ygo_equip_boost(obj, atk_boost=500, def_boost=0)]


BRILLIANT_HALBERD = make_ygo_spell(
    "Brilliant Halberd", ygo_spell_type="Equip",
    text="Equipped 'Ninja' gains 500 ATK. Once per turn: equipped 'Ninja' can attack twice.",
    setup_interceptors=_brilliant_halberd_setup,
)


def _ninjas_cunning_resolve(event, state):
    """Normal: search 1 'Ninja' from your Deck."""
    controller = event.payload.get('player')
    if not controller:
        return []
    return _search_library(state, controller, _is_ninja)


NINJAS_CUNNING = make_ygo_spell(
    "Ninja's Cunning", ygo_spell_type="Normal",
    text="Add 1 'Ninja' from your Deck to your hand.",
    resolve=_ninjas_cunning_resolve,
)


def _throwing_stars_setup(obj, state):
    """Equip: when equipped Ninja attacks, deal 600 damage to opponent."""
    from src.engine.types import (Interceptor, InterceptorAction,
                                  InterceptorPriority, InterceptorResult, new_id)
    def filter_fn(event, state):
        if event.type != EventType.YGO_BATTLE_DECLARE:
            return False
        target_id = getattr(obj.state, 'equipped_to', None)
        if not target_id:
            return False
        return event.payload.get('attacker_id') == target_id
    def handler(event, state):
        for pid in state.players:
            if pid == obj.controller:
                continue
            player = state.players.get(pid)
            if player:
                player.lp = max(0, player.lp - 600)
                return InterceptorResult(
                    action=InterceptorAction.REACT,
                    new_events=[Event(type=EventType.YGO_LP_CHANGE,
                                       payload={'player': pid, 'amount': -600,
                                                'source': 'Throwing Stars'})])
        return InterceptorResult(action=InterceptorAction.PASS)
    return [
        make_ygo_equip_boost(obj, atk_boost=0, def_boost=0),
        Interceptor(id=new_id(), source=obj.id, controller=obj.controller,
                    priority=InterceptorPriority.REACT, filter=filter_fn,
                    handler=handler, duration='until_leaves'),
    ]


THROWING_STARS = make_ygo_spell(
    "Throwing Stars", ygo_spell_type="Equip",
    text="When equipped 'Ninja' attacks: deal 600 damage to your opponent.",
    setup_interceptors=_throwing_stars_setup,
)


def _ninja_strike_force_resolve(event, state):
    """Normal: SS up to 2 'Ninja' from your GY in face-up DEF."""
    controller = event.payload.get('player')
    if not controller:
        return []
    events = []
    for _ in range(2):
        target = find_in_graveyard(state, controller, "Ninja")
        if not target:
            break
        ev = revive_from_graveyard(state, controller, target)
        tobj = state.objects.get(target)
        if tobj:
            tobj.state.ygo_position = 'face_up_def'
        events.extend(ev)
    return events


NINJA_STRIKE_FORCE = make_ygo_spell(
    "Ninja Strike Force", ygo_spell_type="Normal",
    text="SS up to 2 'Ninja' from your GY in face-up Defense Position.",
    resolve=_ninja_strike_force_resolve,
)


def _inkblot_setup(obj, state):
    """Continuous: once per turn (ignition), tribute 1 'Ninja'; search 1 'Ninja' from
    your Deck."""
    def effect_fn(o, state):
        sacrificed = _tribute_one(state, o.controller, _is_ninja)
        if not sacrificed:
            return []
        return _search_library(state, o.controller, _is_ninja)
    return [make_ygo_ignition_effect(obj, effect_fn)]


INKBLOT = make_ygo_spell(
    "Inkblot", ygo_spell_type="Continuous",
    text="Once per turn: tribute 1 'Ninja' you control; add 1 'Ninja' from your Deck to your hand.",
    setup_interceptors=_inkblot_setup,
)


# =============================================================================
# Card definitions — Traps
# =============================================================================

def _ninjitsu_duplication_resolve(event, state):
    """Counter: when a 'Ninja' you control is attacked: SS 1 'Ninja' from your GY."""
    controller = event.payload.get('player')
    if not controller:
        return []
    target = find_in_graveyard(state, controller, "Ninja")
    if not target:
        return []
    return revive_from_graveyard(state, controller, target)


NINJITSU_ART_OF_DUPLICATION = make_ygo_trap(
    "Ninjitsu Art of Duplication", ygo_trap_type="Counter",
    text="When a 'Ninja' you control is attacked: SS 1 'Ninja' from your GY.",
    resolve=_ninjitsu_duplication_resolve,
)


def _ninjas_echo_setup(obj, state):
    """When a 'Ninja' you control is sent to GY: deal that Ninja's ATK as damage to
    opponent."""
    def effect_fn(o, state):
        # Find the most recent Ninja added to controller's GY (last entry that's a Ninja)
        gy = state.zones.get(f"graveyard_{o.controller}")
        if not gy:
            return []
        for cid in reversed(gy.objects):
            cobj = state.objects.get(cid)
            if cobj and _is_ninja(cobj):
                atk = getattr(cobj.card_def, 'atk', 0) or 0
                if atk <= 0:
                    return []
                events = []
                for pid in state.players:
                    if pid == o.controller:
                        continue
                    player = state.players.get(pid)
                    if player:
                        player.lp = max(0, player.lp - atk)
                        events.append(Event(
                            type=EventType.YGO_LP_CHANGE,
                            payload={'player': pid, 'amount': -atk,
                                     'source': "Ninja's Echo"}))
                return events
        return []
    from src.engine.types import (Interceptor, InterceptorAction,
                                  InterceptorPriority, InterceptorResult, new_id)
    def filter_fn(event, state):
        if event.type != EventType.YGO_DESTROY:
            return False
        cid = event.payload.get('card_id')
        if not cid:
            return False
        cobj = state.objects.get(cid)
        return cobj is not None and cobj.controller == obj.controller and _is_ninja(cobj)
    def handler(event, state):
        return InterceptorResult(action=InterceptorAction.REACT,
                                 new_events=effect_fn(obj, state) or [])
    return [Interceptor(id=new_id(), source=obj.id, controller=obj.controller,
                        priority=InterceptorPriority.REACT, filter=filter_fn,
                        handler=handler, duration='until_leaves')]


NINJAS_ECHO = make_ygo_trap(
    "Ninja's Echo", ygo_trap_type="Continuous",
    text="When a 'Ninja' you control is sent to the GY: deal that monster's ATK as damage to your opponent.",
    setup_interceptors=_ninjas_echo_setup,
)


def _higures_last_will_setup(obj, state):
    """Continuous: once per turn, when a 'Ninja' you control is destroyed: search 1
    'Ninja' from your Deck."""
    def effect_fn(o, state):
        return _search_library(state, o.controller, _is_ninja)
    from src.engine.types import (Interceptor, InterceptorAction,
                                  InterceptorPriority, InterceptorResult, new_id)
    def filter_fn(event, state):
        if event.type != EventType.YGO_DESTROY:
            return False
        cid = event.payload.get('card_id')
        if not cid:
            return False
        cobj = state.objects.get(cid)
        return cobj is not None and cobj.controller == obj.controller and _is_ninja(cobj)
    def handler(event, state):
        return InterceptorResult(action=InterceptorAction.REACT,
                                 new_events=effect_fn(obj, state) or [])
    return [Interceptor(id=new_id(), source=obj.id, controller=obj.controller,
                        priority=InterceptorPriority.REACT, filter=filter_fn,
                        handler=handler, duration='until_leaves',
                        uses_remaining=1)]


HIGURES_LAST_WILL = make_ygo_trap(
    "Higure's Last Will", ygo_trap_type="Continuous",
    text="Once per turn: when a 'Ninja' you control is destroyed: add 1 'Ninja' from your Deck to your hand.",
    setup_interceptors=_higures_last_will_setup,
)


def _cloak_and_dagger_resolve(event, state):
    """Normal: change 1 'Ninja' you control to face-down DEF (Flip-effect reset)."""
    controller = event.payload.get('player')
    targets = event.payload.get('targets') or []
    target_id = targets[0] if targets else None
    if not target_id and controller:
        zone = state.zones.get(f"monster_zone_{controller}")
        if zone:
            for oid in zone.objects:
                if oid:
                    cobj = state.objects.get(oid)
                    if cobj and _is_ninja(cobj):
                        target_id = oid
                        break
    if not target_id:
        return []
    target = state.objects.get(target_id)
    if target and _is_ninja(target):
        target.state.face_down = True
        target.state.ygo_position = 'face_down_def'
    return []


CLOAK_AND_DAGGER = make_ygo_trap(
    "Cloak and Dagger", ygo_trap_type="Normal",
    text="Change 1 'Ninja' you control to face-down Defense Position.",
    resolve=_cloak_and_dagger_resolve,
)


def _sealing_tag_resolve(event, state):
    """Negate the effects of an opponent's Lv 5+ monster while it is on the field."""
    return [Event(type=EventType.YGO_CHAIN_LINK,
                  payload={'effect': 'negate_effects',
                           'controller': event.payload.get('player')})]


SEALING_TAG = make_ygo_trap(
    "Sealing Tag", ygo_trap_type="Continuous",
    text="Negate the effects of an opponent's Lv 5+ monster while it is on the field.",
    resolve=_sealing_tag_resolve,
)


def _final_smoke_resolve(event, state):
    """Counter: negate a destroy-effect targeting a 'Ninja' you control."""
    return [Event(type=EventType.YGO_CHAIN_LINK,
                  payload={'effect': 'negate_destroy',
                           'controller': event.payload.get('player')})]


FINAL_SMOKE = make_ygo_trap(
    "Final Smoke", ygo_trap_type="Counter",
    text="When a 'Ninja' you control would be destroyed by an opponent's effect: negate it.",
    resolve=_final_smoke_resolve,
)


# =============================================================================
# Card definitions — Extra Deck
# =============================================================================

def _kaito_bane_of_nightmares_setup(obj, state):
    """When Synchro Summoned: bounce up to 2 face-up cards opponent controls."""
    def effect_fn(o, state):
        events = []
        for _ in range(2):
            ev = _bounce_one_opponent_monster(state, o.controller)
            if not ev:
                break
            events.extend(ev)
        return events
    return [make_ygo_summon_trigger(obj, effect_fn)]


KAITO_BANE_OF_NIGHTMARES = make_ygo_monster(
    "Kaito, Bane of Nightmares", atk=2800, def_val=2300, level=8,
    attribute="DARK", ygo_monster_type="Synchro",
    subtypes={"Warrior", "Ninja"},
    text="1 Tuner + 1+ non-Tuner 'Ninja'. When Synchro Summoned: bounce up to 2 face-up cards opponent controls.",
    materials="1 Tuner + 1+ non-Tuner 'Ninja'",
    setup_interceptors=_kaito_bane_of_nightmares_setup,
)


def _yuriko_setup(obj, state):
    """Once per turn: bounce 1 'Ninja' you control; SS 1 'Ninja' from your Deck."""
    def effect_fn(o, state):
        bounced = _bounce_own_ninja_to_hand(state, o.controller, exclude_id=o.id)
        if not bounced:
            return []
        # SS first Ninja from library
        library = state.zones.get(f"library_{o.controller}")
        zone = state.zones.get(f"monster_zone_{o.controller}")
        if not library or not zone:
            return []
        for cid in list(library.objects):
            cobj = state.objects.get(cid)
            if not cobj or not _is_ninja(cobj):
                continue
            slot = None
            for j in range(5):
                if j >= len(zone.objects) or zone.objects[j] is None:
                    slot = j
                    break
            if slot is None:
                return []
            while len(zone.objects) <= slot:
                zone.objects.append(None)
            library.objects.remove(cid)
            zone.objects[slot] = cid
            cobj.zone = ZoneType.MONSTER_ZONE
            cobj.controller = o.controller
            cobj.state.ygo_position = 'face_up_atk'
            return [Event(type=EventType.YGO_SPECIAL_SUMMON,
                          payload={'player': o.controller, 'card_id': cid,
                                   'card_name': cobj.name,
                                   'summon_type': 'yuriko'})]
        return []
    return [make_ygo_ignition_effect(obj, effect_fn)]


YURIKO_THE_TIGERS_SHADOW = make_ygo_monster(
    "Yuriko, the Tiger's Shadow", atk=2400, def_val=2000, level=6,
    attribute="DARK", ygo_monster_type="Synchro",
    subtypes={"Warrior", "Ninja"},
    text="1 Tuner + 1+ non-Tuner 'Ninja'. Once per turn: bounce 1 'Ninja' you control; SS 1 'Ninja' from your Deck.",
    materials="1 Tuner + 1+ non-Tuner 'Ninja'",
    setup_interceptors=_yuriko_setup,
)


def _hidetsugu_setup(obj, state):
    """Xyz Rank 5. Once/turn: detach 1 material; deal 800 damage."""
    def effect_fn(o, state):
        if not o.state.overlay_units:
            return []
        detached = o.state.overlay_units.pop(0)
        gy = state.zones.get(f"graveyard_{o.controller}")
        if gy is not None:
            gy.objects.append(detached)
        events = []
        for pid in state.players:
            if pid == o.controller:
                continue
            player = state.players.get(pid)
            if player:
                player.lp = max(0, player.lp - 800)
                events.append(Event(type=EventType.YGO_LP_CHANGE,
                                    payload={'player': pid, 'amount': -800,
                                             'source': 'Hidetsugu'}))
        return events
    return [make_ygo_ignition_effect(obj, effect_fn)]


HIDETSUGU_ABYSSAL_LORD = make_ygo_monster(
    "Hidetsugu, Abyssal Lord", atk=2700, def_val=2300, level=5,
    attribute="DARK", ygo_monster_type="Xyz", rank=5,
    subtypes={"Warrior", "Ninja"},
    text="2 Lv 5 'Ninja' monsters. Once per turn: detach 1 Xyz Material; deal 800 damage to opponent.",
    materials="2 Lv 5 'Ninja' monsters",
    setup_interceptors=_hidetsugu_setup,
)


def _satoru_bridgekeeper_setup(obj, state):
    """While face-up: Lv 5+ Warriors can be Ninjutsu-summoned (same effect as
    Satoru Umezawa). Lord effect: Ninjas you control gain 300 ATK."""
    def tag_fn(event, state):
        from src.engine.types import (InterceptorAction, InterceptorResult)
        source = state.objects.get(obj.id)
        if not source or source.zone != ZoneType.MONSTER_ZONE:
            return InterceptorResult(action=InterceptorAction.PASS)
        hand = state.zones.get(f"hand_{obj.controller}")
        if hand:
            for cid in hand.objects:
                cobj = state.objects.get(cid)
                if not cobj or not cobj.card_def:
                    continue
                if "Warrior" not in (cobj.card_def.characteristics.subtypes or set()):
                    continue
                lvl = getattr(cobj.card_def, 'level', 0) or 0
                if lvl < 5:
                    continue
                if cobj.card_def.characteristics.subtypes is None:
                    cobj.card_def.characteristics.subtypes = set()
                cobj.card_def.characteristics.subtypes.add("Ninja")
        return InterceptorResult(action=InterceptorAction.PASS)
    return [
        make_archetype_lord(obj, atk_bonus=300, archetype="Ninja"),
        make_ygo_continuous_effect(obj, tag_fn),
    ]


SATORU_UMEZAWA_BRIDGEKEEPER = make_ygo_monster(
    "Satoru Umezawa, Bridgekeeper", atk=2000, def_val=0, level=2,
    attribute="DARK", ygo_monster_type="Link", link_rating=2,
    link_arrows=["bottom_left", "bottom_right"],
    subtypes={"Warrior", "Ninja"},
    text="2 'Ninja' monsters. While face-up: Lv 5+ Warriors in your hand are also 'Ninja' and can be Ninjutsu-summoned. 'Ninja' you control gain 300 ATK.",
    materials="2 'Ninja' monsters",
    setup_interceptors=_satoru_bridgekeeper_setup,
)


def _mukotai_soulripper_setup(obj, state):
    """When Synchro Summoned: SS 1 'Ninja' from your GY in face-up DEF."""
    def effect_fn(o, state):
        target = find_in_graveyard(state, o.controller, "Ninja")
        if not target:
            return []
        ev = revive_from_graveyard(state, o.controller, target)
        tobj = state.objects.get(target)
        if tobj:
            tobj.state.ygo_position = 'face_up_def'
        return ev
    return [make_ygo_summon_trigger(obj, effect_fn)]


MUKOTAI_SOULRIPPER = make_ygo_monster(
    "Mukotai Soulripper", atk=2000, def_val=1500, level=5,
    attribute="DARK", ygo_monster_type="Synchro",
    subtypes={"Warrior", "Ninja"},
    text="1 Tuner + 1+ non-Tuner 'Ninja'. When Synchro Summoned: SS 1 'Ninja' from your GY in face-up DEF.",
    materials="1 Tuner + 1+ non-Tuner 'Ninja'",
    setup_interceptors=_mukotai_soulripper_setup,
)


# =============================================================================
# Set registry
# =============================================================================

BEYOND_KAMIGAWA_NINJA = {card.name: card for card in [
    # Monsters
    NINJUTSU_APPRENTICE, KABUTO_MUSHI, WALKER_OF_SECRET_WAYS, IGA_STYLE_COOPER,
    CLOAK_OF_MISTS, NINJA_OF_THE_DEEP_HOURS, MISTBLADE_SHINOBI, HIGURES_APPRENTICE,
    NINJA_GRANDMASTER_SASUKE, SAKASHIMA_THE_IMPOSTER, SATORU_UMEZAWA,
    THROAT_SLITTER, HIGURE_THE_STILL_WIND, INK_EYES_SERVANT_OF_ONI,
    TOSHIRO_UMEZAWA, KAITO_SHIZUKI,
    # Spells
    NINJITSU_ART_OF_DECOY, NINJITSU_ART_OF_TRANSFORMATION, MISTBLADES_CUNNING,
    PATH_OF_THE_SHADOW, SMOKE_BOMB, BRILLIANT_HALBERD, NINJAS_CUNNING,
    THROWING_STARS, NINJA_STRIKE_FORCE, INKBLOT,
    # Traps
    NINJITSU_ART_OF_DUPLICATION, NINJAS_ECHO, HIGURES_LAST_WILL,
    CLOAK_AND_DAGGER, SEALING_TAG, FINAL_SMOKE,
    # Extra Deck
    KAITO_BANE_OF_NIGHTMARES, YURIKO_THE_TIGERS_SHADOW, HIDETSUGU_ABYSSAL_LORD,
    SATORU_UMEZAWA_BRIDGEKEEPER, MUKOTAI_SOULRIPPER,
]}


# =============================================================================
# Pre-built deck — 40 main + 5 extra
# =============================================================================

def make_ninja_deck() -> tuple[list, list]:
    """Umezawa Ninja — 40 main + 5 extra.

    Composition:
      - 6 hand-Ninjas (Lv 4-) used as Ninjutsu fodder.
      - 4 high-level Ninjas (Lv 5+) summoned via Ninjutsu for value.
      - 3 Tuners (Iga-Style Cooper x2 + Toshiro Umezawa x1) for Synchro.
      - Heavy Ninja-search and Quick-Play recovery.

    Tuned 2026-05-02: aggressive rebuild. The original 22-monster + 12-spell
    + 6-trap mix lost to Samurai 3-27 and Modified 2-28 because the deck's
    wins all routed through Ninjutsu chain mechanics that the engine
    simplifies (no chain-resolution negation, no engine-side targeting
    immunity). Replaced 5 of the weakest archetype cards with mechanically-
    reliable staples (Lightning Bolt, Doom Blade, Wrath of God, Demonic
    Tutor) that fire real YGO_DESTROY / LP_CHANGE / draw events.
    """
    from src.cards.yugioh.beyond.kamigawa.staples import (
        LIGHTNING_BOLT, DOOM_BLADE, WRATH_OF_GOD, DEMONIC_TUTOR,
    )
    main = (
        # Monsters (18) — vanillas and weak utility trimmed
        [WALKER_OF_SECRET_WAYS] * 2 +
        [IGA_STYLE_COOPER] * 2 +       # Tuner
        [CLOAK_OF_MISTS] * 1 +
        [NINJA_OF_THE_DEEP_HOURS] * 3 +
        [MISTBLADE_SHINOBI] * 2 +
        [HIGURES_APPRENTICE] * 2 +
        [SATORU_UMEZAWA] * 1 +
        [THROAT_SLITTER] * 1 +
        [HIGURE_THE_STILL_WIND] * 1 +
        [INK_EYES_SERVANT_OF_ONI] * 1 +
        [TOSHIRO_UMEZAWA] * 1 +        # Tuner
        [KAITO_SHIZUKI] * 1 +
        # Spells (16) — staples pulled in for real interaction
        [LIGHTNING_BOLT] * 3 +         # +3 — direct damage / removal (max copies)
        [DOOM_BLADE] * 2 +             # +2 — destroy non-LIGHT (max useful)
        [WRATH_OF_GOD] * 1 +           # +1 — board wipe vs Samurai/Modified
        [DEMONIC_TUTOR] * 1 +          # +1 — find a high-impact Ninja or staple
        [NINJAS_CUNNING] * 2 +
        [SMOKE_BOMB] * 2 +
        [MISTBLADES_CUNNING] * 2 +
        [INKBLOT] * 1 +
        [PATH_OF_THE_SHADOW] * 1 +
        [BRILLIANT_HALBERD] * 1 +
        # Traps (6)
        [NINJITSU_ART_OF_DUPLICATION] * 1 +
        [NINJAS_ECHO] * 1 +
        [HIGURES_LAST_WILL] * 2 +
        [FINAL_SMOKE] * 1 +
        [SEALING_TAG] * 1
    )
    extra = [
        KAITO_BANE_OF_NIGHTMARES,
        YURIKO_THE_TIGERS_SHADOW,
        HIDETSUGU_ABYSSAL_LORD,
        SATORU_UMEZAWA_BRIDGEKEEPER,
        MUKOTAI_SOULRIPPER,
    ]
    return (main, extra)


__all__ = ["BEYOND_KAMIGAWA_NINJA", "make_ninja_deck"]
