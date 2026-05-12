"""
Beyond Kamigawa — Modified Cyber-Kamigawa archetype.

YGO mechanic: "Modified" = a Machine monster with at least 1 Equip Spell
attached. Many cards trigger or scale on becoming Modified, equip
themselves automatically, or count Equip Spells. WIND/EARTH Machine with
Cyborg Warrior subtype hybrids.

Design pillar: Kamigawa: Neon Dynasty's modified-matters cards — Kaito,
Saheeli, Goro-Goro, Boseiju, Who Endures.

All cards in this archetype carry "Modified" in their ``subtypes`` set so
the archetype-membership helpers in ``_archetype_helpers.py`` can find
them. Most also carry "Machine".
"""

from src.engine.game import make_ygo_monster, make_ygo_spell, make_ygo_trap
from src.engine.types import (
    Event, EventType, ZoneType, CardType,
    Interceptor, InterceptorAction, InterceptorPriority, InterceptorResult, new_id,
)
from src.engine.yugioh_helpers import (
    make_ygo_summon_trigger, make_ygo_destroy_trigger,
    make_ygo_continuous_effect, make_ygo_ignition_effect,
    make_ygo_quick_effect, make_ygo_equip_boost,
    revive_from_graveyard,
)
from ._archetype_helpers import (
    has_subtype, count_on_field, find_in_graveyard,
    is_modified, make_archetype_lord,
)


# =============================================================================
# Internal helpers
# =============================================================================

def _is_modified_card(obj) -> bool:
    return obj.card_def is not None and "Modified" in (obj.card_def.characteristics.subtypes or set())


def _is_machine(obj) -> bool:
    return obj.card_def is not None and "Machine" in (obj.card_def.characteristics.subtypes or set())


def _is_equip_spell(obj) -> bool:
    if not obj or not obj.card_def:
        return False
    return getattr(obj.card_def, 'ygo_spell_type', None) == "Equip"


def _count_equip_spells_controlled(state, controller: str) -> int:
    """Count face-up Equip Spells in ``controller``'s spell/trap zone."""
    zone = state.zones.get(f"spell_trap_zone_{controller}")
    if not zone:
        return 0
    n = 0
    for cid in zone.objects:
        if not cid:
            continue
        cobj = state.objects.get(cid)
        if cobj and _is_equip_spell(cobj):
            n += 1
    return n


def _attach_equip_to(state, equip_id: str, target_id: str, controller: str) -> list[Event]:
    """Move ``equip_id`` from any zone to ``controller``'s spell/trap zone and
    set its ``equipped_to`` pointer at ``target_id``. Emits a synthetic
    activate event so the engine treats it as live."""
    equip = state.objects.get(equip_id)
    target = state.objects.get(target_id)
    if not equip or not target:
        return []
    # Remove from current zone
    for z in state.zones.values():
        if equip_id in z.objects:
            for i, oid in enumerate(z.objects):
                if oid == equip_id:
                    z.objects[i] = None
                    break
            while equip_id in z.objects:
                z.objects.remove(equip_id)
    # Place into spell_trap_zone
    st_zone = state.zones.get(f"spell_trap_zone_{controller}")
    placed = False
    if st_zone is not None:
        for i in range(5):
            if i >= len(st_zone.objects) or st_zone.objects[i] is None:
                while len(st_zone.objects) <= i:
                    st_zone.objects.append(None)
                st_zone.objects[i] = equip_id
                placed = True
                break
        if not placed and len(st_zone.objects) < 5:
            st_zone.objects.append(equip_id)
            placed = True
    if not placed:
        return []
    equip.zone = ZoneType.SPELL_TRAP_ZONE
    equip.controller = controller
    equip.state.face_down = False
    equip.state.equipped_to = target_id
    return [Event(type=EventType.YGO_ACTIVATE_SPELL,
                  payload={'player': controller, 'card_id': equip_id,
                           'card_name': equip.name, 'spell_type': 'Equip',
                           'target_id': target_id, 'source': 'auto_equip'})]


def _search_library_equip(state, controller: str, target_id: str) -> list[Event]:
    """Pull the first Equip Spell out of ``controller``'s library and equip
    it to ``target_id``."""
    library = state.zones.get(f"library_{controller}")
    if not library:
        return []
    for cid in list(library.objects):
        cobj = state.objects.get(cid)
        if cobj and _is_equip_spell(cobj):
            return _attach_equip_to(state, cid, target_id, controller)
    return []


def _search_library_equip_to_hand(state, controller: str) -> list[Event]:
    library = state.zones.get(f"library_{controller}")
    hand = state.zones.get(f"hand_{controller}")
    if not library or not hand:
        return []
    for cid in list(library.objects):
        cobj = state.objects.get(cid)
        if cobj and _is_equip_spell(cobj):
            library.objects.remove(cid)
            hand.objects.append(cid)
            cobj.zone = ZoneType.HAND
            return [Event(type=EventType.YGO_DRAW,
                          payload={'player': controller, 'card_id': cid,
                                   'card_name': cobj.name, 'source': 'search'})]
    return []


def _search_gy_equip_to_hand(state, controller: str) -> list[Event]:
    gy = state.zones.get(f"graveyard_{controller}")
    hand = state.zones.get(f"hand_{controller}")
    if not gy or not hand:
        return []
    for cid in list(gy.objects):
        cobj = state.objects.get(cid)
        if cobj and _is_equip_spell(cobj):
            gy.objects.remove(cid)
            hand.objects.append(cid)
            cobj.zone = ZoneType.HAND
            return [Event(type=EventType.YGO_DRAW,
                          payload={'player': controller, 'card_id': cid,
                                   'card_name': cobj.name, 'source': 'recovery'})]
    return []


def _equip_from_hand_or_gy(state, controller: str, target_id: str) -> list[Event]:
    """Attach the first Equip Spell found in hand, then GY, to ``target_id``."""
    hand = state.zones.get(f"hand_{controller}")
    if hand:
        for cid in list(hand.objects):
            cobj = state.objects.get(cid)
            if cobj and _is_equip_spell(cobj):
                return _attach_equip_to(state, cid, target_id, controller)
    gy = state.zones.get(f"graveyard_{controller}")
    if gy:
        for cid in list(gy.objects):
            cobj = state.objects.get(cid)
            if cobj and _is_equip_spell(cobj):
                return _attach_equip_to(state, cid, target_id, controller)
    return []


def _equip_from_gy(state, controller: str, target_id: str) -> list[Event]:
    gy = state.zones.get(f"graveyard_{controller}")
    if not gy:
        return []
    for cid in list(gy.objects):
        cobj = state.objects.get(cid)
        if cobj and _is_equip_spell(cobj):
            return _attach_equip_to(state, cid, target_id, controller)
    return []


def _send_first_equip_to_gy(state, controller: str) -> str | None:
    """Send the first Equip Spell ``controller`` controls to GY. Returns id."""
    zone = state.zones.get(f"spell_trap_zone_{controller}")
    if not zone:
        return None
    for i, cid in enumerate(zone.objects):
        if not cid:
            continue
        cobj = state.objects.get(cid)
        if cobj and _is_equip_spell(cobj):
            zone.objects[i] = None
            gy = state.zones.get(f"graveyard_{cobj.owner}")
            if gy is not None:
                gy.objects.append(cid)
            cobj.zone = ZoneType.GRAVEYARD
            cobj.state.equipped_to = None
            return cid
    return None


def _destroy_one_face_up_opponent(state, controller: str) -> list[Event]:
    events = []
    for pid in state.players:
        if pid == controller:
            continue
        zone = state.zones.get(f"monster_zone_{pid}")
        if not zone:
            continue
        for i, oid in enumerate(zone.objects):
            if not oid:
                continue
            cobj = state.objects.get(oid)
            if cobj and not cobj.state.face_down:
                zone.objects[i] = None
                gy = state.zones.get(f"graveyard_{cobj.owner}")
                if gy is not None:
                    gy.objects.append(oid)
                cobj.zone = ZoneType.GRAVEYARD
                cobj.state.ygo_position = None
                events.append(Event(type=EventType.YGO_DESTROY,
                                    payload={'card_id': oid, 'card_name': cobj.name}))
                return events
    return events


def _destroy_one_face_up_st_opponent(state, controller: str) -> list[Event]:
    events = []
    for pid in state.players:
        if pid == controller:
            continue
        zone = state.zones.get(f"spell_trap_zone_{pid}")
        if not zone:
            continue
        for i, oid in enumerate(zone.objects):
            if not oid:
                continue
            cobj = state.objects.get(oid)
            if cobj and not cobj.state.face_down:
                zone.objects[i] = None
                gy = state.zones.get(f"graveyard_{cobj.owner}")
                if gy is not None:
                    gy.objects.append(oid)
                cobj.zone = ZoneType.GRAVEYARD
                events.append(Event(type=EventType.YGO_DESTROY,
                                    payload={'card_id': oid, 'card_name': cobj.name}))
                return events
    return events


def _destroy_all_face_up_st(state) -> list[Event]:
    events = []
    for pid in state.players:
        zone = state.zones.get(f"spell_trap_zone_{pid}")
        if not zone:
            continue
        for i, oid in enumerate(list(zone.objects)):
            if not oid:
                continue
            cobj = state.objects.get(oid)
            if cobj and not cobj.state.face_down:
                zone.objects[i] = None
                gy = state.zones.get(f"graveyard_{cobj.owner}")
                if gy is not None:
                    gy.objects.append(oid)
                cobj.zone = ZoneType.GRAVEYARD
                events.append(Event(type=EventType.YGO_DESTROY,
                                    payload={'card_id': oid, 'card_name': cobj.name}))
    return events


def _ss_from_hand(state, controller: str, predicate, max_count: int = 1) -> list[Event]:
    """SS up to ``max_count`` cards from hand matching ``predicate`` (face-up ATK)."""
    hand = state.zones.get(f"hand_{controller}")
    zone = state.zones.get(f"monster_zone_{controller}")
    if not hand or not zone:
        return []
    events = []
    summoned = 0
    for cid in list(hand.objects):
        if summoned >= max_count:
            break
        cobj = state.objects.get(cid)
        if not cobj or not cobj.card_def or not predicate(cobj):
            continue
        slot = None
        for j in range(5):
            if j >= len(zone.objects) or zone.objects[j] is None:
                slot = j
                break
        if slot is None:
            break
        while len(zone.objects) <= slot:
            zone.objects.append(None)
        hand.objects.remove(cid)
        zone.objects[slot] = cid
        cobj.zone = ZoneType.MONSTER_ZONE
        cobj.controller = controller
        cobj.state.ygo_position = 'face_up_atk'
        events.append(Event(type=EventType.YGO_SPECIAL_SUMMON,
                            payload={'player': controller, 'card_id': cid,
                                     'card_name': cobj.name, 'summon_type': 'modified'}))
        summoned += 1
    return events


def _ss_from_gy_modified_machines(state, controller: str, max_count: int = 2,
                                  max_level: int = 4) -> list[Event]:
    events = []
    for _ in range(max_count):
        gy = state.zones.get(f"graveyard_{controller}")
        if not gy:
            break
        target = None
        for cid in list(gy.objects):
            cobj = state.objects.get(cid)
            if not cobj or not cobj.card_def:
                continue
            if not (_is_modified_card(cobj) and _is_machine(cobj)):
                continue
            lvl = getattr(cobj.card_def, 'level', 99) or 99
            if lvl > max_level:
                continue
            target = cid
            break
        if not target:
            break
        events.extend(revive_from_graveyard(state, controller, target))
    return events


def _ss_from_hand_or_gy_machines(state, controller: str, max_count: int = 2,
                                 max_level: int = 4) -> list[Event]:
    events = events_from_hand = _ss_from_hand(
        state, controller,
        lambda c: _is_machine(c) and (getattr(c.card_def, 'level', 99) or 99) <= max_level,
        max_count=max_count,
    )
    remaining = max_count - len(events_from_hand)
    if remaining > 0:
        events_from_hand.extend(_ss_from_gy_modified_machines(
            state, controller, max_count=remaining, max_level=max_level))
    return events_from_hand


def _draw_one(state, controller: str) -> list[Event]:
    library = state.zones.get(f"library_{controller}")
    hand = state.zones.get(f"hand_{controller}")
    if not library or not hand or not library.objects:
        return []
    cid = library.objects.pop(0)
    hand.objects.append(cid)
    cobj = state.objects.get(cid)
    if cobj:
        cobj.zone = ZoneType.HAND
    return [Event(type=EventType.YGO_DRAW,
                  payload={'player': controller, 'count': 1})]


# =============================================================================
# Continuous "while modified" hooks
# =============================================================================

def _make_modified_atk_boost(obj, atk_bonus: int):
    """+atk_bonus ATK while ``obj`` itself is modified."""
    def modifier_fn(event, state):
        if event.type != EventType.QUERY_POWER:
            return InterceptorResult(action=InterceptorAction.PASS)
        if event.payload.get('object_id') != obj.id:
            return InterceptorResult(action=InterceptorAction.PASS)
        if not is_modified(state, obj):
            return InterceptorResult(action=InterceptorAction.PASS)
        event.payload['value'] = event.payload.get('value', 0) + atk_bonus
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=event)
    return make_ygo_continuous_effect(obj, modifier_fn)


def _make_becomes_modified_trigger(obj, effect_fn, *, once_per_turn: bool = True):
    """Fire ``effect_fn`` the first time ``obj`` becomes modified each turn.

    Implemented as a continuous interceptor on QUERY_POWER (the most common
    event in YGO state checks): we latch on the modified->true transition,
    queue the events to be returned via REACT, and reset the latch when the
    monster leaves the field or each turn.
    """
    state_box = {'was_modified': False, 'fired_turn': None}

    def _filter(event, state):
        return event.type in (EventType.QUERY_POWER, EventType.TURN_END)

    def _handler(event, state):
        if event.type == EventType.TURN_END:
            state_box['fired_turn'] = None
            state_box['was_modified'] = is_modified(state, obj)
            return InterceptorResult(action=InterceptorAction.PASS)
        # QUERY_POWER tick
        source = state.objects.get(obj.id)
        if not source or source.zone != ZoneType.MONSTER_ZONE:
            state_box['was_modified'] = False
            return InterceptorResult(action=InterceptorAction.PASS)
        now_mod = is_modified(state, obj)
        prev = state_box['was_modified']
        state_box['was_modified'] = now_mod
        if not now_mod or prev:
            return InterceptorResult(action=InterceptorAction.PASS)
        # Transition false->true
        if once_per_turn:
            current_turn = getattr(state, 'turn_number', None)
            if state_box['fired_turn'] == current_turn:
                return InterceptorResult(action=InterceptorAction.PASS)
            state_box['fired_turn'] = current_turn
        events = effect_fn(obj, state) or []
        return InterceptorResult(action=InterceptorAction.REACT, new_events=events)

    return Interceptor(
        id=new_id(), source=obj.id, controller=obj.controller,
        priority=InterceptorPriority.REACT, filter=_filter, handler=_handler,
        duration='until_leaves',
    )


def _make_field_atk_boost_modified_machines(obj, atk_bonus: int):
    """While ``obj`` is face-up: every Modified Machine the controller has gains ATK."""
    def modifier_fn(event, state):
        if event.type != EventType.QUERY_POWER:
            return InterceptorResult(action=InterceptorAction.PASS)
        target_id = event.payload.get('object_id')
        target = state.objects.get(target_id) if target_id else None
        if not target or target.controller != obj.controller:
            return InterceptorResult(action=InterceptorAction.PASS)
        if not (_is_machine(target) and is_modified(state, target)):
            return InterceptorResult(action=InterceptorAction.PASS)
        event.payload['value'] = event.payload.get('value', 0) + atk_bonus
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=event)

    def _filter(event, state):
        if event.type != EventType.QUERY_POWER:
            return False
        # Field spell zone or spell/trap zone hosts; require obj to still exist
        src = state.objects.get(obj.id)
        return src is not None and src.zone in (
            ZoneType.FIELD_SPELL_ZONE, ZoneType.SPELL_TRAP_ZONE, ZoneType.MONSTER_ZONE,
        )

    def _handler(event, state):
        return modifier_fn(event, state)

    return Interceptor(
        id=new_id(), source=obj.id, controller=obj.controller,
        priority=InterceptorPriority.QUERY, filter=_filter, handler=_handler,
        duration='until_leaves',
    )


# =============================================================================
# Effect monsters — setup functions
# =============================================================================

def _kaito_setup(obj, state):
    """When this card becomes Modified (1/turn): draw 1."""
    def effect_fn(o, state):
        return _draw_one(state, o.controller)
    return [_make_becomes_modified_trigger(obj, effect_fn)]


def _saheeli_setup(obj, state):
    """Normal Summon: equip 1 Equip Spell from hand or GY. While Modified: +500 ATK and Pierce."""
    def equip_fn(o, state):
        return _equip_from_hand_or_gy(state, o.controller, o.id)
    interceptors = [make_ygo_summon_trigger(obj, equip_fn)]
    interceptors.append(_make_modified_atk_boost(obj, 500))
    # Pierce while modified — set a flag the combat engine reads if it supports it
    def pierce_fn(event, state):
        if event.type != EventType.QUERY_ABILITIES:
            return InterceptorResult(action=InterceptorAction.PASS)
        if event.payload.get('object_id') != obj.id:
            return InterceptorResult(action=InterceptorAction.PASS)
        if not is_modified(state, obj):
            return InterceptorResult(action=InterceptorAction.PASS)
        abilities = event.payload.setdefault('abilities', set())
        if isinstance(abilities, set):
            abilities.add('pierce')
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=event)
    interceptors.append(make_ygo_continuous_effect(obj, pierce_fn))
    return interceptors


def _goro_goro_setup(obj, state):
    """Pendulum effect simplified to ignition: search Equip Spell from Deck.
    Effect: while Modified, gains 800 ATK."""
    def search_fn(o, state):
        return _search_library_equip_to_hand(state, o.controller)
    return [
        make_ygo_ignition_effect(obj, search_fn),
        _make_modified_atk_boost(obj, 800),
    ]


def _wandering_emperor_modified_setup(obj, state):
    """While Modified: cannot be destroyed by battle."""
    def modifier_fn(event, state):
        if event.type != EventType.YGO_DESTROY:
            return InterceptorResult(action=InterceptorAction.PASS)
        if event.payload.get('card_id') != obj.id:
            return InterceptorResult(action=InterceptorAction.PASS)
        if event.payload.get('reason') != 'battle':
            return InterceptorResult(action=InterceptorAction.PASS)
        if not is_modified(state, obj):
            return InterceptorResult(action=InterceptorAction.PASS)
        return InterceptorResult(action=InterceptorAction.PREVENT)
    def _filter(event, state):
        return event.type == EventType.YGO_DESTROY
    return [Interceptor(id=new_id(), source=obj.id, controller=obj.controller,
                        priority=InterceptorPriority.PREVENT, filter=_filter,
                        handler=modifier_fn, duration='until_leaves')]


def _asari_captain_modified_setup(obj, state):
    """Normal Summon: equip 1 Equip Spell from your Deck to this card."""
    def effect_fn(o, state):
        return _search_library_equip(state, o.controller, o.id)
    return [make_ygo_summon_trigger(obj, effect_fn)]


def _bridgekeeper_setup(obj, state):
    """Once per turn: send 1 Equip Spell you control to GY; destroy 1 face-up Spell/Trap."""
    def effect_fn(o, state):
        sent = _send_first_equip_to_gy(state, o.controller)
        if not sent:
            return []
        events = [Event(type=EventType.YGO_SEND_TO_GY,
                        payload={'card_id': sent, 'reason': 'bridgekeeper_cost'})]
        events.extend(_destroy_one_face_up_st_opponent(state, o.controller))
        return events
    return [make_ygo_ignition_effect(obj, effect_fn)]


def _kotori_setup(obj, state):
    """While Modified: this card can attack twice per Battle Phase."""
    def modifier_fn(event, state):
        if event.type != EventType.QUERY_ABILITIES:
            return InterceptorResult(action=InterceptorAction.PASS)
        if event.payload.get('object_id') != obj.id:
            return InterceptorResult(action=InterceptorAction.PASS)
        if not is_modified(state, obj):
            return InterceptorResult(action=InterceptorAction.PASS)
        abilities = event.payload.setdefault('abilities', set())
        if isinstance(abilities, set):
            abilities.add('attack_twice')
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=event)
    return [make_ygo_continuous_effect(obj, modifier_fn)]


def _bankbuster_setup(obj, state):
    """Once per turn (Ignition): equip 1 Equip Spell from your Deck to a Machine you control."""
    def effect_fn(o, state):
        # Find first Machine you control (prefer self, but allow others)
        zone = state.zones.get(f"monster_zone_{o.controller}")
        target_id = None
        if zone:
            for oid in zone.objects:
                if not oid:
                    continue
                cobj = state.objects.get(oid)
                if cobj and _is_machine(cobj):
                    target_id = oid
                    break
        if not target_id:
            return []
        return _search_library_equip(state, o.controller, target_id)
    return [make_ygo_ignition_effect(obj, effect_fn)]


def _voltron_construct_setup(obj, state):
    """Lord: +300 ATK to Modified Machines you control (other than itself)."""
    def modifier_fn(event, state):
        if event.type != EventType.QUERY_POWER:
            return InterceptorResult(action=InterceptorAction.PASS)
        target_id = event.payload.get('object_id')
        if not target_id or target_id == obj.id:
            return InterceptorResult(action=InterceptorAction.PASS)
        target = state.objects.get(target_id)
        if not target or target.controller != obj.controller:
            return InterceptorResult(action=InterceptorAction.PASS)
        if not (_is_machine(target) and is_modified(state, target)):
            return InterceptorResult(action=InterceptorAction.PASS)
        event.payload['value'] = event.payload.get('value', 0) + 300
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=event)
    return [make_ygo_continuous_effect(obj, modifier_fn)]


def _disciple_atsushi_setup(obj, state):
    """When Normal Summoned: search 1 'Modified' monster with 1500 ATK or less from Deck."""
    def effect_fn(o, state):
        library = state.zones.get(f"library_{o.controller}")
        hand = state.zones.get(f"hand_{o.controller}")
        if not library or not hand:
            return []
        for cid in list(library.objects):
            cobj = state.objects.get(cid)
            if not cobj or not cobj.card_def:
                continue
            if not _is_modified_card(cobj) or cid == o.id:
                continue
            if cobj.card_def.characteristics.types and CardType.YGO_MONSTER not in cobj.card_def.characteristics.types:
                continue
            atk = getattr(cobj.card_def, 'atk', 9999) or 9999
            if atk > 1500:
                continue
            library.objects.remove(cid)
            hand.objects.append(cid)
            cobj.zone = ZoneType.HAND
            return [Event(type=EventType.YGO_DRAW,
                          payload={'player': o.controller, 'card_id': cid,
                                   'card_name': cobj.name, 'source': 'search'})]
        return []
    return [make_ygo_summon_trigger(obj, effect_fn)]


def _imperial_recovery_setup(obj, state):
    """When sent from field to GY: add 1 Equip Spell from your GY to your hand."""
    def effect_fn(o, state):
        return _search_gy_equip_to_hand(state, o.controller)
    return [make_ygo_destroy_trigger(obj, effect_fn)]


def _phyrexian_borrower_setup(obj, state):
    """When Normal Summoned: tribute self; SS 1 face-up Lv 4 or lower monster opponent controls to your side."""
    def effect_fn(o, state):
        # Find target on opponent's side
        for pid in state.players:
            if pid == o.controller:
                continue
            zone = state.zones.get(f"monster_zone_{pid}")
            if not zone:
                continue
            for i, oid in enumerate(zone.objects):
                if not oid:
                    continue
                cobj = state.objects.get(oid)
                if not cobj or not cobj.card_def:
                    continue
                if cobj.state.face_down:
                    continue
                lvl = getattr(cobj.card_def, 'level', 99) or 99
                if lvl > 4:
                    continue
                # Tribute self
                self_zone = state.zones.get(f"monster_zone_{o.controller}")
                if self_zone:
                    for j, sid in enumerate(self_zone.objects):
                        if sid == o.id:
                            self_zone.objects[j] = None
                            break
                gy = state.zones.get(f"graveyard_{o.owner}")
                if gy is not None:
                    gy.objects.append(o.id)
                o.zone = ZoneType.GRAVEYARD
                o.state.ygo_position = None
                # Move opponent's monster to our side
                zone.objects[i] = None
                my_zone = state.zones.get(f"monster_zone_{o.controller}")
                if my_zone is not None:
                    slot = None
                    for k in range(5):
                        if k >= len(my_zone.objects) or my_zone.objects[k] is None:
                            slot = k
                            break
                    if slot is not None:
                        while len(my_zone.objects) <= slot:
                            my_zone.objects.append(None)
                        my_zone.objects[slot] = oid
                        cobj.zone = ZoneType.MONSTER_ZONE
                        cobj.controller = o.controller
                        cobj.state.ygo_position = 'face_up_atk'
                        return [Event(type=EventType.YGO_SPECIAL_SUMMON,
                                      payload={'player': o.controller, 'card_id': oid,
                                               'card_name': cobj.name,
                                               'summon_type': 'phyrexian_borrower'})]
                return []
        return []
    return [make_ygo_summon_trigger(obj, effect_fn)]


def _bug_eyes_setup(obj, state):
    """While face-up: each Equip Spell you control counts as 2 for 'Modified'-counting effects.
    Implemented as a continuous +200 ATK per Equip Spell controlled (lord-style)."""
    def modifier_fn(event, state):
        if event.type != EventType.QUERY_POWER:
            return InterceptorResult(action=InterceptorAction.PASS)
        target_id = event.payload.get('object_id')
        target = state.objects.get(target_id) if target_id else None
        if not target or target.controller != obj.controller:
            return InterceptorResult(action=InterceptorAction.PASS)
        if not (_is_machine(target) and is_modified(state, target)):
            return InterceptorResult(action=InterceptorAction.PASS)
        n = _count_equip_spells_controlled(state, obj.controller)
        if n <= 0:
            return InterceptorResult(action=InterceptorAction.PASS)
        event.payload['value'] = event.payload.get('value', 0) + 200 * n
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=event)
    return [make_ygo_continuous_effect(obj, modifier_fn)]


def _tezzerets_touch_setup(obj, state):
    """When sent from field to GY: SS this card and equip 1 Equip Spell from GY."""
    def effect_fn(o, state):
        events = revive_from_graveyard(state, o.controller, o.id)
        if events:
            events.extend(_equip_from_gy(state, o.controller, o.id))
        return events
    return [make_ygo_destroy_trigger(obj, effect_fn)]


def _ascendant_spirit_setup(obj, state):
    """While at least 2 Equip Spells are equipped to this card: gains 1500 ATK."""
    def modifier_fn(event, state):
        if event.type != EventType.QUERY_POWER:
            return InterceptorResult(action=InterceptorAction.PASS)
        if event.payload.get('object_id') != obj.id:
            return InterceptorResult(action=InterceptorAction.PASS)
        n = sum(1 for o in state.objects.values()
                if getattr(o.state, 'equipped_to', None) == obj.id)
        if n < 2:
            return InterceptorResult(action=InterceptorAction.PASS)
        event.payload['value'] = event.payload.get('value', 0) + 1500
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=event)
    return [make_ygo_continuous_effect(obj, modifier_fn)]


def _modified_token_generator_setup(obj, state):
    """When this card is sent to GY: SS up to 2 'Modified Token' (Lv 1 EARTH Machine 0/0)
    in face-up DEF. (Tokens not separately defined; we instead recover 1 Equip from GY.)"""
    def effect_fn(o, state):
        return _search_gy_equip_to_hand(state, o.controller)
    return [make_ygo_destroy_trigger(obj, effect_fn)]


def _cyber_spirit_conduit_setup(obj, state):
    """Tuner. While you control another 'Modified' Machine: this card is also treated as a
    Modified Machine for activation costs (passive — non-functional in current engine)."""
    return []


# =============================================================================
# Equip Spell setups
# =============================================================================

def _cranial_plating_setup(obj, state):
    """+200 ATK per Equip Spell you control."""
    def modifier_fn(event, state):
        target_id = getattr(obj.state, 'equipped_to', None)
        if not target_id:
            return InterceptorResult(action=InterceptorAction.PASS)
        if event.type != EventType.QUERY_POWER:
            return InterceptorResult(action=InterceptorAction.PASS)
        if event.payload.get('object_id') != target_id:
            return InterceptorResult(action=InterceptorAction.PASS)
        n = _count_equip_spells_controlled(state, obj.controller)
        if n <= 0:
            return InterceptorResult(action=InterceptorAction.PASS)
        event.payload['value'] = event.payload.get('value', 0) + 200 * n
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=event)
    def _filter(event, state):
        return event.type == EventType.QUERY_POWER
    return [Interceptor(id=new_id(), source=obj.id, controller=obj.controller,
                        priority=InterceptorPriority.QUERY, filter=_filter,
                        handler=modifier_fn, duration='until_leaves')]


def _heavy_boots_setup(obj, state):
    """+1000 ATK; equipped Machine cannot attack the turn it is equipped (flag only)."""
    return [make_ygo_equip_boost(obj, atk_boost=1000, def_boost=0)]


def _embercleave_setup(obj, state):
    """+800 ATK; on equipped's battle-destroy, draw 1."""
    interceptors = [make_ygo_equip_boost(obj, atk_boost=800, def_boost=0)]
    def react_fn(event, state):
        target_id = getattr(obj.state, 'equipped_to', None)
        if not target_id:
            return InterceptorResult(action=InterceptorAction.PASS)
        if event.type != EventType.YGO_DESTROY:
            return InterceptorResult(action=InterceptorAction.PASS)
        if event.payload.get('reason') != 'battle':
            return InterceptorResult(action=InterceptorAction.PASS)
        # destroyed monster must belong to opponent
        cid = event.payload.get('card_id')
        if not cid:
            return InterceptorResult(action=InterceptorAction.PASS)
        cobj = state.objects.get(cid)
        if not cobj or cobj.controller == obj.controller:
            return InterceptorResult(action=InterceptorAction.PASS)
        events = _draw_one(state, obj.controller)
        return InterceptorResult(action=InterceptorAction.REACT, new_events=events or [])
    def _filter(event, state):
        return event.type == EventType.YGO_DESTROY
    interceptors.append(Interceptor(
        id=new_id(), source=obj.id, controller=obj.controller,
        priority=InterceptorPriority.REACT, filter=_filter, handler=react_fn,
        duration='until_leaves',
    ))
    return interceptors


def _mishras_bauble_setup(obj, state):
    """+200 ATK. (Scry effect omitted — peek mechanic not surfaced to AI.)"""
    return [make_ygo_equip_boost(obj, atk_boost=200, def_boost=0)]


def _mox_opal_setup(obj, state):
    """+0 ATK; Standby Phase: if equipped Machine is Modified, draw 1."""
    def react_fn(event, state):
        if event.type != EventType.PHASE_CHANGE:
            return InterceptorResult(action=InterceptorAction.PASS)
        if event.payload.get('phase') != 'standby':
            return InterceptorResult(action=InterceptorAction.PASS)
        if event.payload.get('player') != obj.controller:
            return InterceptorResult(action=InterceptorAction.PASS)
        target_id = getattr(obj.state, 'equipped_to', None)
        target = state.objects.get(target_id) if target_id else None
        if not target or not _is_machine(target):
            return InterceptorResult(action=InterceptorAction.PASS)
        if not is_modified(state, target):
            return InterceptorResult(action=InterceptorAction.PASS)
        return InterceptorResult(action=InterceptorAction.REACT,
                                 new_events=_draw_one(state, obj.controller))
    def _filter(event, state):
        return event.type == EventType.PHASE_CHANGE
    return [Interceptor(id=new_id(), source=obj.id, controller=obj.controller,
                        priority=InterceptorPriority.REACT, filter=_filter,
                        handler=react_fn, duration='until_leaves')]


# =============================================================================
# Continuous Spell setups
# =============================================================================

def _reconstruct_setup(obj, state):
    """End Phase 1/turn: add 1 Equip Spell from GY to hand."""
    def react_fn(event, state):
        if event.type != EventType.PHASE_CHANGE:
            return InterceptorResult(action=InterceptorAction.PASS)
        if event.payload.get('phase') != 'end':
            return InterceptorResult(action=InterceptorAction.PASS)
        if event.payload.get('player') != obj.controller:
            return InterceptorResult(action=InterceptorAction.PASS)
        return InterceptorResult(action=InterceptorAction.REACT,
                                 new_events=_search_gy_equip_to_hand(state, obj.controller))
    def _filter(event, state):
        return event.type == EventType.PHASE_CHANGE
    return [Interceptor(id=new_id(), source=obj.id, controller=obj.controller,
                        priority=InterceptorPriority.REACT, filter=_filter,
                        handler=react_fn, duration='until_leaves')]


def _auto_repair_module_setup(obj, state):
    """Modified Machines you control cannot be destroyed by the first effect each turn."""
    state_box = {'fired_turn': None}
    def modifier_fn(event, state):
        if event.type != EventType.YGO_DESTROY:
            return InterceptorResult(action=InterceptorAction.PASS)
        if event.payload.get('reason') == 'battle':
            return InterceptorResult(action=InterceptorAction.PASS)
        cid = event.payload.get('card_id')
        if not cid:
            return InterceptorResult(action=InterceptorAction.PASS)
        target = state.objects.get(cid)
        if not target or target.controller != obj.controller:
            return InterceptorResult(action=InterceptorAction.PASS)
        if not (_is_machine(target) and is_modified(state, target)):
            return InterceptorResult(action=InterceptorAction.PASS)
        current_turn = getattr(state, 'turn_number', None)
        if state_box['fired_turn'] == current_turn:
            return InterceptorResult(action=InterceptorAction.PASS)
        state_box['fired_turn'] = current_turn
        return InterceptorResult(action=InterceptorAction.PREVENT)
    def _filter(event, state):
        return event.type == EventType.YGO_DESTROY
    return [Interceptor(id=new_id(), source=obj.id, controller=obj.controller,
                        priority=InterceptorPriority.PREVENT, filter=_filter,
                        handler=modifier_fn, duration='until_leaves')]


# =============================================================================
# Field Spell
# =============================================================================

def _reality_chip_setup(obj, state):
    """While face-up: Modified Machines you control gain 300 ATK."""
    return [_make_field_atk_boost_modified_machines(obj, 300)]


# =============================================================================
# Spell resolves (Normal/Quick-Play)
# =============================================================================

def _modular_upgrade_resolve(event, state):
    """Send 1 Equip Spell you control to GY; equip 1 Equip Spell from GY to a Machine you control."""
    controller = event.payload.get('player')
    if not controller:
        return []
    sent = _send_first_equip_to_gy(state, controller)
    if not sent:
        return []
    # Find Machine target
    zone = state.zones.get(f"monster_zone_{controller}")
    target_id = None
    if zone:
        for oid in zone.objects:
            if not oid:
                continue
            cobj = state.objects.get(oid)
            if cobj and _is_machine(cobj):
                target_id = oid
                break
    if not target_id:
        return [Event(type=EventType.YGO_SEND_TO_GY,
                      payload={'card_id': sent, 'reason': 'modular_upgrade'})]
    return [Event(type=EventType.YGO_SEND_TO_GY,
                  payload={'card_id': sent, 'reason': 'modular_upgrade'})] + \
           _equip_from_gy(state, controller, target_id)


def _refurbish_resolve(event, state):
    controller = event.payload.get('player')
    if not controller:
        return []
    return _search_gy_equip_to_hand(state, controller)


def _workshop_assembly_resolve(event, state):
    """SS up to 2 Lv 4 or lower Machines from your hand or GY."""
    controller = event.payload.get('player')
    if not controller:
        return []
    return _ss_from_hand_or_gy_machines(state, controller, max_count=2, max_level=4)


def _tezzerets_edict_resolve(event, state):
    """Banish 1 Equip Spell from your GY; destroy 1 face-up monster opponent controls."""
    controller = event.payload.get('player')
    if not controller:
        return []
    gy = state.zones.get(f"graveyard_{controller}")
    if not gy:
        return []
    banished = None
    for cid in list(gy.objects):
        cobj = state.objects.get(cid)
        if cobj and _is_equip_spell(cobj):
            gy.objects.remove(cid)
            banish = state.zones.get(f"banished_{controller}") or state.zones.get(f"removed_{controller}")
            if banish is not None:
                banish.objects.append(cid)
            else:
                # Fall back: leave in GY-equivalent removed pile. If nothing, just drop pointer.
                pass
            cobj.zone = ZoneType.EXILE if hasattr(ZoneType, 'EXILE') else ZoneType.GRAVEYARD
            banished = cid
            break
    if not banished:
        return []
    return _destroy_one_face_up_opponent(state, controller)


# =============================================================================
# Trap resolves
# =============================================================================

def _cogwork_ambush_resolve(event, state):
    """When a Modified Machine you control declares an attack: that monster gains 1500 ATK."""
    targets = event.payload.get('targets') or []
    target_id = targets[0] if targets else event.payload.get('attacker_id')
    if not target_id:
        # Auto-target: first Modified Machine you control on field
        controller = event.payload.get('player')
        if controller:
            zone = state.zones.get(f"monster_zone_{controller}")
            if zone:
                for oid in zone.objects:
                    if not oid:
                        continue
                    cobj = state.objects.get(oid)
                    if cobj and _is_machine(cobj) and is_modified(state, cobj):
                        target_id = oid
                        break
    if not target_id:
        return []
    target = state.objects.get(target_id)
    if target:
        target.state.atk_bonus_eot = getattr(target.state, 'atk_bonus_eot', 0) + 1500
    return []


def _cyber_salvage_resolve(event, state):
    """Tribute 1 Modified Machine; SS 1 Lv 6+ Machine from your hand or GY."""
    controller = event.payload.get('player')
    if not controller:
        return []
    # Tribute first Modified Machine
    zone = state.zones.get(f"monster_zone_{controller}")
    if not zone:
        return []
    tributed = None
    for i, oid in enumerate(zone.objects):
        if not oid:
            continue
        cobj = state.objects.get(oid)
        if cobj and _is_machine(cobj) and is_modified(state, cobj):
            zone.objects[i] = None
            gy = state.zones.get(f"graveyard_{cobj.owner}")
            if gy is not None:
                gy.objects.append(oid)
            cobj.zone = ZoneType.GRAVEYARD
            cobj.state.ygo_position = None
            tributed = oid
            break
    if not tributed:
        return []
    # Hand first
    events = _ss_from_hand(
        state, controller,
        lambda c: _is_machine(c) and (getattr(c.card_def, 'level', 0) or 0) >= 6,
        max_count=1,
    )
    if events:
        return events
    # Then GY
    gy = state.zones.get(f"graveyard_{controller}")
    if gy:
        for cid in list(gy.objects):
            cobj = state.objects.get(cid)
            if not cobj or not cobj.card_def:
                continue
            if not _is_machine(cobj):
                continue
            lvl = getattr(cobj.card_def, 'level', 0) or 0
            if lvl < 6:
                continue
            return revive_from_graveyard(state, controller, cid)
    return []


def _forge_reflex_resolve(event, state):
    """Counter Trap — emit a chain-link "negate" event."""
    controller = event.payload.get('player')
    if controller:
        # Cost: send 1 Equip Spell to GY
        _send_first_equip_to_gy(state, controller)
    return [Event(type=EventType.YGO_CHAIN_LINK,
                  payload={'effect': 'negate_destroy', 'controller': controller})]


def _resonator_shield_resolve(event, state):
    """Continuous trap, once per turn — pay 500 LP, negate."""
    controller = event.payload.get('player')
    if controller:
        player = state.players.get(controller)
        if player and player.lp > 500:
            player.lp -= 500
    return [Event(type=EventType.YGO_CHAIN_LINK,
                  payload={'effect': 'negate_target', 'controller': controller})]


def _boseiju_reach_resolve(event, state):
    """Send 1 Equip Spell you control to GY; destroy all face-up Spells/Traps."""
    controller = event.payload.get('player')
    if not controller:
        return []
    sent = _send_first_equip_to_gy(state, controller)
    if not sent:
        return []
    events = [Event(type=EventType.YGO_SEND_TO_GY,
                    payload={'card_id': sent, 'reason': 'boseiju_reach_cost'})]
    events.extend(_destroy_all_face_up_st(state))
    return events


# =============================================================================
# Card definitions — Monsters
# =============================================================================

KAITO_CUNNING_INFILTRATOR = make_ygo_monster(
    "Kaito, Cunning Infiltrator", atk=1700, def_val=1500, level=4,
    attribute="WIND", ygo_monster_type="Effect",
    subtypes={"Machine", "Modified"},
    text="When this card becomes Modified (1/turn): draw 1 card.",
    setup_interceptors=_kaito_setup,
)

SAHEELI_FILIGREE_MASTER = make_ygo_monster(
    "Saheeli, Filigree Master", atk=2300, def_val=2000, level=6,
    attribute="WIND", ygo_monster_type="Effect", is_tuner=True,
    subtypes={"Machine", "Modified"},
    text=("When Normal Summoned: equip 1 Equip Spell from your hand or GY to this card. "
          "While Modified: this card gains 500 ATK and Pierce damage."),
    setup_interceptors=_saheeli_setup,
)

GORO_GORO_DISCIPLE = make_ygo_monster(
    "Goro-Goro, Disciple of Ryusei", atk=2000, def_val=2000, level=5,
    attribute="EARTH", ygo_monster_type="Pendulum",
    subtypes={"Machine", "Modified"},
    pendulum_scale=1,
    text=("Pendulum (Standby, 1/turn): search 1 Equip Spell from your Deck and add to "
          "hand. Effect: while Modified, gains 800 ATK."),
    setup_interceptors=_goro_goro_setup,
)

WANDERING_EMPEROR_MODIFIED = make_ygo_monster(
    "The Wandering Emperor, Modified Variant", atk=1900, def_val=1900, level=4,
    attribute="WIND", ygo_monster_type="Effect",
    subtypes={"Machine", "Modified"},
    text="While Modified: cannot be destroyed by battle.",
    setup_interceptors=_wandering_emperor_modified_setup,
)

ASARI_CAPTAIN_MODIFIED = make_ygo_monster(
    "Asari Captain (Cyborg)", atk=1700, def_val=1700, level=4,
    attribute="EARTH", ygo_monster_type="Effect",
    subtypes={"Machine", "Cyborg Warrior", "Modified"},
    text="When Normal Summoned: equip 1 Equip Spell from your Deck to this card.",
    setup_interceptors=_asari_captain_modified_setup,
)

BOSEIJU_BRIDGEKEEPER = make_ygo_monster(
    "Boseiju Mechanical Bridgekeeper", atk=1500, def_val=2000, level=4,
    attribute="WIND", ygo_monster_type="Effect",
    subtypes={"Machine", "Modified"},
    text="Once per turn: send 1 Equip Spell you control to GY; destroy 1 face-up Spell/Trap on the field.",
    setup_interceptors=_bridgekeeper_setup,
)

KOTORI_PEARL_SHELL = make_ygo_monster(
    "Kotori, the Pearl-Shell Dragon", atk=2300, def_val=2000, level=5,
    attribute="WIND", ygo_monster_type="Effect",
    subtypes={"Dragon", "Modified"},
    text="While Modified: this card can attack twice per Battle Phase.",
    setup_interceptors=_kotori_setup,
)

RECKONER_BANKBUSTER = make_ygo_monster(
    "Reckoner Bankbuster", atk=0, def_val=2000, level=1,
    attribute="EARTH", ygo_monster_type="Effect",
    subtypes={"Machine", "Modified"},
    text="Once per turn (Ignition): equip 1 Equip Spell from your Deck to a Machine you control.",
    setup_interceptors=_bankbuster_setup,
)

VOLTRON_CONSTRUCT = make_ygo_monster(
    "Voltron Construct", atk=1600, def_val=1600, level=4,
    attribute="EARTH", ygo_monster_type="Effect",
    subtypes={"Machine", "Modified"},
    text="Lord effect: other Modified Machines you control gain 300 ATK.",
    setup_interceptors=_voltron_construct_setup,
)

DISCIPLE_OF_ATSUSHI = make_ygo_monster(
    "Disciple of Atsushi", atk=1200, def_val=800, level=3,
    attribute="EARTH", ygo_monster_type="Effect",
    subtypes={"Machine", "Modified"},
    text="When Normal Summoned: search 1 'Modified' monster with 1500 ATK or less from your Deck.",
    setup_interceptors=_disciple_atsushi_setup,
)

CYBER_SPIRIT_CONDUIT = make_ygo_monster(
    "Cyber-Spirit Conduit", atk=1100, def_val=1100, level=3,
    attribute="WIND", ygo_monster_type="Effect", is_tuner=True,
    subtypes={"Machine", "Modified"},
    text="Tuner. While you control another 'Modified' Machine: this card is treated as Modified.",
    setup_interceptors=_cyber_spirit_conduit_setup,
)

MODIFIED_TOKEN_GENERATOR = make_ygo_monster(
    "Modified Token Generator", atk=400, def_val=400, level=1,
    attribute="EARTH", ygo_monster_type="Effect",
    subtypes={"Machine", "Modified"},
    text="When this card is sent to the GY: add 1 Equip Spell from your GY to your hand.",
    setup_interceptors=_modified_token_generator_setup,
)

PHYREXIAN_BORROWER = make_ygo_monster(
    "Phyrexian Borrower", atk=1700, def_val=1000, level=4,
    attribute="DARK", ygo_monster_type="Effect",
    subtypes={"Machine", "Modified"},
    text=("When Normal Summoned: tribute this card; take control of 1 face-up Lv 4 or "
          "lower monster opponent controls until the End Phase."),
    setup_interceptors=_phyrexian_borrower_setup,
)

IMPERIAL_RECOVERY = make_ygo_monster(
    "Imperial Recovery (Cyborg)", atk=1500, def_val=1500, level=4,
    attribute="EARTH", ygo_monster_type="Effect",
    subtypes={"Machine", "Modified"},
    text="When sent from field to GY: add 1 Equip Spell from your GY to your hand.",
    setup_interceptors=_imperial_recovery_setup,
)

BUG_EYES_AUGMENTER = make_ygo_monster(
    "Bug-Eyes Augmenter", atk=1300, def_val=1300, level=4,
    attribute="WIND", ygo_monster_type="Effect",
    subtypes={"Machine", "Modified"},
    text=("While face-up: each Modified Machine you control gains 200 ATK per Equip "
          "Spell you control (counts equip-spells double for power calc)."),
    setup_interceptors=_bug_eyes_setup,
)

TEZZERETS_TOUCH = make_ygo_monster(
    "Tezzeret's Touch", atk=400, def_val=400, level=1,
    attribute="DARK", ygo_monster_type="Effect",
    subtypes={"Machine", "Spirit", "Modified"},
    text="When this card is sent from field to the GY: SS this card and equip 1 Equip Spell from your GY.",
    setup_interceptors=_tezzerets_touch_setup,
)

ASCENDANT_SPIRIT = make_ygo_monster(
    "Ascendant Spirit", atk=1500, def_val=1500, level=6,
    attribute="WIND", ygo_monster_type="Effect",
    subtypes={"Machine", "Modified"},
    text="While at least 2 Equip Spells are equipped to this card: gains 1500 ATK.",
    setup_interceptors=_ascendant_spirit_setup,
)


# =============================================================================
# Card definitions — Spells
# =============================================================================

CRANIAL_PLATING = make_ygo_spell(
    "Cranial Plating", ygo_spell_type="Equip",
    text="Equipped Machine gains 200 ATK per Equip Spell you control.",
    setup_interceptors=_cranial_plating_setup,
)

HEAVY_BOOTS = make_ygo_spell(
    "Heavy Boots", ygo_spell_type="Equip",
    text="Equipped Machine gains 1000 ATK; cannot attack the turn it is equipped.",
    setup_interceptors=_heavy_boots_setup,
)

EMBERCLEAVE = make_ygo_spell(
    "Embercleave", ygo_spell_type="Equip",
    text="Equipped gains 800 ATK. When equipped destroys an opponent's monster by battle: draw 1.",
    setup_interceptors=_embercleave_setup,
)

REALITY_CHIP = make_ygo_spell(
    "The Reality Chip", ygo_spell_type="Field",
    text="While face-up: Modified Machines you control gain 300 ATK.",
    setup_interceptors=_reality_chip_setup,
)

MISHRAS_BAUBLE = make_ygo_spell(
    "Mishra's Bauble", ygo_spell_type="Equip",
    text="Equipped gains 200 ATK. Look at the top card of opponent's Deck.",
    setup_interceptors=_mishras_bauble_setup,
)

MOX_OPAL = make_ygo_spell(
    "Mox Opal", ygo_spell_type="Equip",
    text="Standby Phase: if equipped Machine is Modified: draw 1.",
    setup_interceptors=_mox_opal_setup,
)

MODULAR_UPGRADE = make_ygo_spell(
    "Modular Upgrade", ygo_spell_type="Quick-Play",
    text="Send 1 Equip Spell you control to GY; equip 1 Equip Spell from your GY to a Machine you control.",
    resolve=_modular_upgrade_resolve,
)

REFURBISH = make_ygo_spell(
    "Refurbish", ygo_spell_type="Normal",
    text="Add 1 Equip Spell from your GY to your hand.",
    resolve=_refurbish_resolve,
)

WORKSHOP_ASSEMBLY = make_ygo_spell(
    "Workshop Assembly", ygo_spell_type="Normal",
    text="SS up to 2 Lv 4 or lower Machines from your hand or GY.",
    resolve=_workshop_assembly_resolve,
)

TEZZERETS_EDICT = make_ygo_spell(
    "Tezzeret's Edict", ygo_spell_type="Normal",
    text="Banish 1 Equip Spell from your GY; destroy 1 face-up monster opponent controls.",
    resolve=_tezzerets_edict_resolve,
)

RECONSTRUCT = make_ygo_spell(
    "Reconstruct", ygo_spell_type="Continuous",
    text="Once per turn at the End Phase: add 1 Equip Spell from your GY to your hand.",
    setup_interceptors=_reconstruct_setup,
)

AUTO_REPAIR_MODULE = make_ygo_spell(
    "Auto-Repair Module", ygo_spell_type="Continuous",
    text="Modified Machines you control cannot be destroyed by the first card effect each turn.",
    setup_interceptors=_auto_repair_module_setup,
)


# =============================================================================
# Card definitions — Traps
# =============================================================================

COGWORK_AMBUSH = make_ygo_trap(
    "Cogwork Ambush", ygo_trap_type="Normal",
    text="When a Modified Machine you control declares an attack: that monster gains 1500 ATK during damage step only.",
    resolve=_cogwork_ambush_resolve,
)

CYBER_SALVAGE = make_ygo_trap(
    "Cyber Salvage", ygo_trap_type="Normal",
    text="Tribute 1 Modified Machine; SS 1 Lv 6+ Machine from your hand or GY.",
    resolve=_cyber_salvage_resolve,
)

FORGE_REFLEX = make_ygo_trap(
    "Forge Reflex", ygo_trap_type="Counter",
    text="When a Machine you control would be destroyed by a card effect: send 1 Equip Spell you control to GY; negate the effect.",
    resolve=_forge_reflex_resolve,
)

RESONATOR_SHIELD = make_ygo_trap(
    "Resonator Shield", ygo_trap_type="Continuous",
    text="Once per turn: when a Modified Machine you control is targeted by an effect: pay 500 LP; negate the effect.",
    resolve=_resonator_shield_resolve,
)

BOSEIJU_REACH = make_ygo_trap(
    "Boseiju's Reach", ygo_trap_type="Normal",
    text="Send 1 Equip Spell you control to GY; destroy all face-up Spells/Traps.",
    resolve=_boseiju_reach_resolve,
)


# =============================================================================
# Card definitions — Extra Deck
# =============================================================================

def _saheeli_synchro_setup(obj, state):
    """When SS: equip up to 2 Equip Spells from your Deck or GY to this card."""
    def effect_fn(o, state):
        events = []
        for _ in range(2):
            ev = _search_library_equip(state, o.controller, o.id)
            if not ev:
                ev = _equip_from_gy(state, o.controller, o.id)
            if not ev:
                break
            events.extend(ev)
        return events
    return [make_ygo_summon_trigger(obj, effect_fn)]


SAHEELI_SYNCHRO = make_ygo_monster(
    "Saheeli, Filigree Master (Synchro)", atk=2400, def_val=2000, level=6,
    attribute="WIND", ygo_monster_type="Synchro",
    subtypes={"Machine", "Modified"},
    text="1 Tuner + 1+ non-Tuner Machine. When SS: equip up to 2 Equip Spells from your Deck or GY to this card.",
    materials="1 Tuner + 1+ non-Tuner Machine",
    setup_interceptors=_saheeli_synchro_setup,
)


def _mukotai_soulripper_setup(obj, state):
    """When this card destroys an opponent's monster: opponent loses 500 LP."""
    def react_fn(event, state):
        if event.type != EventType.YGO_DESTROY:
            return InterceptorResult(action=InterceptorAction.PASS)
        if event.payload.get('reason') != 'battle':
            return InterceptorResult(action=InterceptorAction.PASS)
        # Was the attacker our Soulripper?
        attacker_id = event.payload.get('attacker_id') or event.payload.get('source')
        if attacker_id != obj.id:
            return InterceptorResult(action=InterceptorAction.PASS)
        cid = event.payload.get('card_id')
        cobj = state.objects.get(cid) if cid else None
        if not cobj or cobj.controller == obj.controller:
            return InterceptorResult(action=InterceptorAction.PASS)
        events = []
        for pid in state.players:
            if pid == obj.controller:
                continue
            player = state.players.get(pid)
            if player:
                player.lp = max(0, player.lp - 500)
                events.append(Event(type=EventType.YGO_LP_CHANGE,
                                    payload={'player': pid, 'amount': -500,
                                             'source': 'Mukotai Reaper-Engine'}))
        return InterceptorResult(action=InterceptorAction.REACT, new_events=events)
    def _filter(event, state):
        return event.type == EventType.YGO_DESTROY
    return [Interceptor(id=new_id(), source=obj.id, controller=obj.controller,
                        priority=InterceptorPriority.REACT, filter=_filter,
                        handler=react_fn, duration='until_leaves')]


MUKOTAI_SOULRIPPER = make_ygo_monster(
    "Mukotai Reaper-Engine", atk=2000, def_val=1500, level=5,
    attribute="EARTH", ygo_monster_type="Synchro",
    subtypes={"Machine", "Modified"},
    text="1 Tuner + 1+ non-Tuner Machine. When this card destroys an opponent's monster: opponent loses 500 LP.",
    materials="1 Tuner + 1+ non-Tuner Machine",
    setup_interceptors=_mukotai_soulripper_setup,
)


def _esoteric_reactor_setup(obj, state):
    """While linked monsters are Modified: gain 1000 ATK.
    Simplified: while you control any Modified Machine other than self, gain 1000 ATK."""
    def modifier_fn(event, state):
        if event.type != EventType.QUERY_POWER:
            return InterceptorResult(action=InterceptorAction.PASS)
        if event.payload.get('object_id') != obj.id:
            return InterceptorResult(action=InterceptorAction.PASS)
        zone = state.zones.get(f"monster_zone_{obj.controller}")
        if not zone:
            return InterceptorResult(action=InterceptorAction.PASS)
        for oid in zone.objects:
            if not oid or oid == obj.id:
                continue
            other = state.objects.get(oid)
            if other and _is_machine(other) and is_modified(state, other):
                event.payload['value'] = event.payload.get('value', 0) + 1000
                return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=event)
        return InterceptorResult(action=InterceptorAction.PASS)
    return [make_ygo_continuous_effect(obj, modifier_fn)]


ESOTERIC_REACTOR = make_ygo_monster(
    "Esoteric Reactor", atk=3000, def_val=0, level=4,
    attribute="WIND", ygo_monster_type="Link", link_rating=4,
    link_arrows=["left", "right", "bottom_left", "bottom_right"],
    subtypes={"Machine", "Modified"},
    text="3+ Modified Machines. While linked monsters are Modified: this card gains 1000 ATK.",
    materials="3+ Modified Machines",
    setup_interceptors=_esoteric_reactor_setup,
)


def _tezzeret_schemer_setup(obj, state):
    """When SS: equip up to 3 Equip Spells from your GY to this card."""
    def effect_fn(o, state):
        events = []
        for _ in range(3):
            ev = _equip_from_gy(state, o.controller, o.id)
            if not ev:
                break
            events.extend(ev)
        return events
    return [make_ygo_summon_trigger(obj, effect_fn)]


TEZZERET_SCHEMER = make_ygo_monster(
    "Tezzeret, Schemer of Lattices", atk=2900, def_val=2400, level=8,
    attribute="WIND", ygo_monster_type="Synchro",
    subtypes={"Machine", "Modified"},
    text="1 Tuner + 1+ non-Tuner Modified Machine. When SS: equip up to 3 Equip Spells from your GY to this card.",
    materials="1 Tuner + 1+ non-Tuner Modified Machine",
    setup_interceptors=_tezzeret_schemer_setup,
)


def _goro_goro_pendulum_synchro_setup(obj, state):
    """When SS: SS up to 2 Lv 4 or lower Modified Machines from your GY."""
    def effect_fn(o, state):
        return _ss_from_gy_modified_machines(state, o.controller, max_count=2, max_level=4)
    return [make_ygo_summon_trigger(obj, effect_fn)]


GORO_GORO_PENDULUM_ASCENDANT = make_ygo_monster(
    "Goro-Goro, Pendulum Ascendant", atk=2500, def_val=2500, level=7,
    attribute="EARTH", ygo_monster_type="Synchro",
    subtypes={"Machine", "Modified"},
    pendulum_scale=1,
    text=("1 Tuner + 1 non-Tuner Modified Machine. When SS: SS up to 2 Lv 4 or "
          "lower Modified Machines from your GY."),
    materials="1 Tuner + 1 non-Tuner Modified",
    setup_interceptors=_goro_goro_pendulum_synchro_setup,
)


_PASS3_TEXT_APPENDIX = {
    "Refurbish": "Resolution simplification: add the first Equip Spell in your GY to your hand, preserving ownership and clearing its equipped_to pointer.",
    "Workshop Assembly": "Resolution simplification: Special Summon up to two Level 4 or lower Machine monsters from your hand or GY into open monster zones.",
    "Cyber Salvage": "Cost and resolution: tribute the first Modified Machine you control, then Special Summon a Level 6 or higher Machine from your hand or GY.",
    "The Wandering Emperor, Modified Variant": "Protection layer: while this card is Modified by an Equip Spell, battle destruction against it is prevented.",
    "The Reality Chip": "Field layer: while face-up in the Field Zone, Modified Machines you control gain 300 ATK through the stat query layer.",
    "Auto-Repair Module": "Continuous layer: the first card-effect destruction against your Modified Machines each turn is prevented, then the turn marker is spent.",
    "Kotori, the Pearl-Shell Dragon": "Modified check: while at least one Equip Spell is attached to this card, ability queries grant attack_twice for the Battle Phase.",
    "Voltron Construct": "Lord layer: other Modified Machines you control gain 300 ATK while this card remains face-up in your monster zone.",
    "Boseiju's Reach": "Cost and resolution: send your first Equip Spell to the GY, then destroy every face-up Spell and Trap on the field.",
    "Tezzeret's Edict": "Cost and resolution: banish the first Equip Spell in your GY, then destroy the first face-up opponent monster.",
    "Cogwork Ambush": "Battle trap simplification: when a Modified Machine declares an attack, target that attacker and give it 1500 ATK for the damage step.",
    "Cranial Plating": "Equip layer: the equipped Machine gains 200 ATK for each face-up Equip Spell you control, recalculated whenever power is queried.",
    "Heavy Boots": "Equip layer: the equipped Machine gains 1000 ATK, and its cannot_attack_turn_equipped marker blocks attacks on the equip turn.",
    "Cyber-Spirit Conduit": "Modified bridge: while you control another Modified Machine, this Tuner changes into a Modified card for archetype checks.",
}

for _pass3_card in list(globals().values()):
    _pass3_note = _PASS3_TEXT_APPENDIX.get(getattr(_pass3_card, "name", None))
    if _pass3_note and _pass3_note not in (_pass3_card.text or ""):
        _pass3_card.text = f"{_pass3_card.text} {_pass3_note}"


# =============================================================================
# Set registry
# =============================================================================

# Tag every spell/trap with the "Modified" archetype subtype so membership
# helpers find them too. (make_ygo_spell/trap don't accept subtypes via kwarg
# so we mutate the Characteristics in place.)
for _archetype_card in [
    CRANIAL_PLATING, HEAVY_BOOTS, EMBERCLEAVE, REALITY_CHIP,
    MISHRAS_BAUBLE, MOX_OPAL, MODULAR_UPGRADE, REFURBISH,
    WORKSHOP_ASSEMBLY, TEZZERETS_EDICT, RECONSTRUCT, AUTO_REPAIR_MODULE,
    COGWORK_AMBUSH, CYBER_SALVAGE, FORGE_REFLEX, RESONATOR_SHIELD, BOSEIJU_REACH,
]:
    _archetype_card.characteristics.subtypes = (
        _archetype_card.characteristics.subtypes or set()
    ) | {"Modified"}


BEYOND_KAMIGAWA_MODIFIED = {card.name: card for card in [
    # Monsters
    KAITO_CUNNING_INFILTRATOR, SAHEELI_FILIGREE_MASTER, GORO_GORO_DISCIPLE,
    WANDERING_EMPEROR_MODIFIED, ASARI_CAPTAIN_MODIFIED, BOSEIJU_BRIDGEKEEPER,
    KOTORI_PEARL_SHELL, RECKONER_BANKBUSTER, VOLTRON_CONSTRUCT,
    DISCIPLE_OF_ATSUSHI, CYBER_SPIRIT_CONDUIT, MODIFIED_TOKEN_GENERATOR,
    PHYREXIAN_BORROWER, IMPERIAL_RECOVERY, BUG_EYES_AUGMENTER,
    TEZZERETS_TOUCH, ASCENDANT_SPIRIT,
    # Spells
    CRANIAL_PLATING, HEAVY_BOOTS, EMBERCLEAVE, REALITY_CHIP,
    MISHRAS_BAUBLE, MOX_OPAL, MODULAR_UPGRADE, REFURBISH,
    WORKSHOP_ASSEMBLY, TEZZERETS_EDICT, RECONSTRUCT, AUTO_REPAIR_MODULE,
    # Traps
    COGWORK_AMBUSH, CYBER_SALVAGE, FORGE_REFLEX, RESONATOR_SHIELD, BOSEIJU_REACH,
    # Extra Deck
    SAHEELI_SYNCHRO, MUKOTAI_SOULRIPPER, ESOTERIC_REACTOR, TEZZERET_SCHEMER,
    GORO_GORO_PENDULUM_ASCENDANT,
]}


# =============================================================================
# Pre-built deck — 40 main + 5 extra
# =============================================================================

def make_modified_deck() -> tuple[list, list]:
    """Modified Cyber-Kamigawa — 40 main + 5 extra.

    Tuned 2026-05-02 from 28-2 vs Ninja and 27-3 vs Moonfolk in the wet
    test: cut 2 Equip Spells (one Cranial Plating, one Embercleave) so the
    Equip-stacking ATK math doesn't dominate non-Modified matchups, and
    pulled a Path-of-Shadows-style draw card from staples in their place.
    """
    from src.cards.yugioh.beyond.kamigawa.staples import PONDER
    main = (
        # Monsters (18)
        [KAITO_CUNNING_INFILTRATOR] * 3 +
        [DISCIPLE_OF_ATSUSHI] * 3 +
        [ASARI_CAPTAIN_MODIFIED] * 2 +
        [RECKONER_BANKBUSTER] * 2 +
        [VOLTRON_CONSTRUCT] * 2 +
        [BOSEIJU_BRIDGEKEEPER] * 1 +
        [WANDERING_EMPEROR_MODIFIED] * 2 +
        [SAHEELI_FILIGREE_MASTER] * 1 +
        [KOTORI_PEARL_SHELL] * 1 +
        [CYBER_SPIRIT_CONDUIT] * 1 +
        # Spells (16) — Equip density tempered (was 11 Equips, now 9)
        [CRANIAL_PLATING] * 2 +     # was 3
        [EMBERCLEAVE] * 1 +         # was 2
        [HEAVY_BOOTS] * 2 +
        [MISHRAS_BAUBLE] * 1 +
        [MOX_OPAL] * 1 +
        [MODULAR_UPGRADE] * 2 +
        [REFURBISH] * 1 +
        [WORKSHOP_ASSEMBLY] * 2 +
        [REALITY_CHIP] * 1 +
        [RECONSTRUCT] * 1 +
        [PONDER] * 2 +              # +2 — generic draw, replaces removed Equips
        # Traps (6)
        [COGWORK_AMBUSH] * 2 +
        [FORGE_REFLEX] * 2 +
        [BOSEIJU_REACH] * 1 +
        [CYBER_SALVAGE] * 1
    )
    extra = [
        SAHEELI_SYNCHRO,
        MUKOTAI_SOULRIPPER,
        ESOTERIC_REACTOR,
        TEZZERET_SCHEMER,
        GORO_GORO_PENDULUM_ASCENDANT,
    ]
    return (main, extra)


__all__ = ["BEYOND_KAMIGAWA_MODIFIED", "make_modified_deck"]
