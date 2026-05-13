"""
Beyond Kamigawa — Eiganjo Samurai archetype.

YGO mechanic: "Six Samurai"-style archetype lord. Bushido = continuous +ATK
while another Samurai is on your field. EARTH/LIGHT Warriors. Aggressive
swarm with Equip-Spell-as-katana support.

Design pillar: Konda's army from Champions of Kamigawa (classic block) and
the Wandering Emperor's loyalists from Neon Dynasty.

All cards in this archetype carry "Samurai" in their ``subtypes`` set so
the archetype-membership helpers in ``_archetype_helpers.py`` can find them.
"""

from src.engine.game import make_ygo_monster, make_ygo_spell, make_ygo_trap
from src.engine.types import Event, EventType, ZoneType, InterceptorAction, InterceptorResult
from src.engine.yugioh_helpers import (
    make_ygo_summon_trigger, make_ygo_destroy_trigger,
    make_ygo_continuous_effect, make_ygo_ignition_effect, make_ygo_flip_trigger,
    make_ygo_quick_effect,
    revive_from_graveyard,
)
from ._archetype_helpers import (
    has_subtype, count_on_field, find_in_graveyard,
    make_archetype_lord, make_archetype_team_lord, make_bushido,
)


# =============================================================================
# Internal helpers — deck/GY searches, tribute-as-cost
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


def _is_samurai(obj) -> bool:
    return obj.card_def is not None and "Samurai" in (obj.card_def.characteristics.subtypes or set())


def _is_equip_spell(obj) -> bool:
    if not obj.card_def:
        return False
    return getattr(obj.card_def, 'ygo_spell_type', None) == "Equip"


def _tribute_one(state, controller: str, predicate=None, exclude_id: str = None) -> str | None:
    """Send the first matching face-up monster on ``controller``'s side to GY.

    Returns the tributed monster's id, or None if no eligible target exists.
    """
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
        # Move to GY
        zone.objects[i] = None
        gy = state.zones.get(f"graveyard_{obj.owner}")
        if gy:
            gy.objects.append(oid)
        obj.zone = ZoneType.GRAVEYARD
        obj.state.face_down = False
        obj.state.ygo_position = None
        return oid
    return None


def _destroy_one_face_up_opponent(state, controller: str) -> list[Event]:
    """Destroy the first face-up monster the opponent controls."""
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
            obj = state.objects.get(oid)
            if obj and not obj.state.face_down:
                zone.objects[i] = None
                gy = state.zones.get(f"graveyard_{obj.owner}")
                if gy:
                    gy.objects.append(oid)
                obj.zone = ZoneType.GRAVEYARD
                obj.state.ygo_position = None
                events.append(Event(type=EventType.YGO_DESTROY,
                                    payload={'card_id': oid, 'card_name': obj.name}))
                return events
    return events


def _move_to_hand(state, controller: str, card_id: str) -> list[Event]:
    """Take a card from any zone and move it to ``controller``'s hand."""
    obj = state.objects.get(card_id)
    if not obj:
        return []
    for z in state.zones.values():
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


# =============================================================================
# Effect monsters — setup functions
# =============================================================================

def _devoted_retainer_setup(obj, state):
    """When Normal Summoned: search 1 'Samurai' with 1500 ATK or less from Deck."""
    def effect_fn(o, state):
        return _search_library(
            state, o.controller,
            lambda c: _is_samurai(c) and (getattr(c.card_def, 'atk', 9999) or 9999) <= 1500
                       and c.id != o.id
        )
    return [make_ygo_summon_trigger(obj, effect_fn)]


def _kitsune_diviner_flip(obj, state):
    """FLIP: add 1 Equip Spell from your Deck or GY to your hand."""
    events = _search_library(state, obj.controller, _is_equip_spell)
    if events:
        return events
    # Fallback: scan GY
    gy = state.zones.get(f"graveyard_{obj.controller}")
    if gy:
        for cid in list(gy.objects):
            cobj = state.objects.get(cid)
            if cobj and _is_equip_spell(cobj):
                events.extend(_move_to_hand(state, obj.controller, cid))
                return events
    return events


def _kitsune_diviner_setup(obj, state):
    """Register the FLIP search through the interceptor scorer path."""
    return [make_ygo_flip_trigger(obj, _kitsune_diviner_flip)]


def _eiganjo_free_rider_setup(obj, state):
    """Once per turn (ignition): change this card's Battle Position. If from DEF to ATK: draw 1."""
    def effect_fn(o, state):
        pos = o.state.ygo_position
        if pos == 'face_up_def':
            o.state.ygo_position = 'face_up_atk'
            # draw 1
            lib = state.zones.get(f"library_{o.controller}")
            hand = state.zones.get(f"hand_{o.controller}")
            if lib and hand and lib.objects:
                cid = lib.objects.pop(0)
                hand.objects.append(cid)
                cobj = state.objects.get(cid)
                if cobj:
                    cobj.zone = ZoneType.HAND
                return [Event(type=EventType.YGO_DRAW,
                              payload={'player': o.controller, 'count': 1})]
        elif pos == 'face_up_atk':
            o.state.ygo_position = 'face_up_def'
        return []
    return [make_ygo_ignition_effect(obj, effect_fn)]


def _eight_and_a_half_tails_setup(obj, state):
    """Once per turn: target 1 face-up monster you control; until EP it becomes LIGHT and gains 200 ATK."""
    def effect_fn(o, state):
        # Simplification: pick the first non-self face-up monster you control and tag it
        zone = state.zones.get(f"monster_zone_{o.controller}")
        if not zone:
            return []
        for mid in zone.objects:
            if not mid or mid == o.id:
                continue
            target = state.objects.get(mid)
            if target and not target.state.face_down and target.card_def:
                # Mutate card_def attribute for the rest of the turn (engine cleans up via duration)
                target.card_def.attribute = "LIGHT"
                # +200 ATK lasts until EP — implement as a flat field bump on state
                target.state.atk_bonus_eot = getattr(target.state, 'atk_bonus_eot', 0) + 200
                return []
        return []
    return [make_ygo_ignition_effect(obj, effect_fn)]


def _general_fumiko_setup(obj, state):
    """When Normal Summoned: SS 1 Lv 4 or lower 'Samurai' from your hand."""
    def effect_fn(o, state):
        hand = state.zones.get(f"hand_{o.controller}")
        zone = state.zones.get(f"monster_zone_{o.controller}")
        if not hand or not zone:
            return []
        for cid in list(hand.objects):
            cobj = state.objects.get(cid)
            if not cobj or not cobj.card_def or not _is_samurai(cobj):
                continue
            lvl = getattr(cobj.card_def, 'level', 99) or 99
            if lvl > 4:
                continue
            # Find empty slot
            slot = None
            for j in range(5):
                if j >= len(zone.objects) or zone.objects[j] is None:
                    slot = j
                    break
            if slot is None:
                return []
            while len(zone.objects) <= slot:
                zone.objects.append(None)
            hand.objects.remove(cid)
            zone.objects[slot] = cid
            cobj.zone = ZoneType.MONSTER_ZONE
            cobj.state.ygo_position = 'face_up_atk'
            return [Event(type=EventType.YGO_SPECIAL_SUMMON,
                          payload={'player': o.controller, 'card_id': cid,
                                   'card_name': cobj.name, 'summon_type': 'fumiko'})]
        return []
    return [make_ygo_summon_trigger(obj, effect_fn)]


def _imperial_recovery_unit_setup(obj, state):
    """When sent from field to GY: add 1 'Samurai' from your GY to your hand."""
    def effect_fn(o, state):
        gy = state.zones.get(f"graveyard_{o.controller}")
        if not gy:
            return []
        for cid in list(gy.objects):
            if cid == o.id:
                continue
            cobj = state.objects.get(cid)
            if cobj and _is_samurai(cobj):
                return _move_to_hand(state, o.controller, cid)
        return []
    return [make_ygo_destroy_trigger(obj, effect_fn)]


def _mukotai_ambusher_setup(obj, state):
    """Once per turn: tribute 1 'Samurai' you control; destroy 1 face-up monster opponent controls."""
    def effect_fn(o, state):
        tributed = _tribute_one(state, o.controller, _is_samurai, exclude_id=o.id)
        if not tributed:
            return []
        events = [Event(type=EventType.YGO_SEND_TO_GY,
                        payload={'card_id': tributed, 'reason': 'mukotai_tribute'})]
        events.extend(_destroy_one_face_up_opponent(state, o.controller))
        return events
    return [make_ygo_ignition_effect(obj, effect_fn)]


def _asari_captain_setup(obj, state):
    """When this card declares an attack: gain 500 LP per 'Samurai' in your GY (max 2500)."""
    def effect_fn(o, state):
        gy = state.zones.get(f"graveyard_{o.controller}")
        if not gy:
            return []
        n = sum(1 for cid in gy.objects
                if (cob := state.objects.get(cid)) and _is_samurai(cob))
        gain = min(500 * n, 2500)
        if gain <= 0:
            return []
        player = state.players.get(o.controller)
        if player:
            player.lp += gain
        return [Event(type=EventType.YGO_LP_CHANGE,
                      payload={'player': o.controller, 'amount': gain,
                               'source': 'Asari Captain'})]
    def _filter(event, state):
        return (event.type == EventType.YGO_BATTLE_DECLARE and
                event.payload.get('attacker_id') == obj.id)
    from src.engine.types import (Interceptor, InterceptorAction,
                                  InterceptorPriority, InterceptorResult, new_id)
    def _handler(event, state):
        return InterceptorResult(action=InterceptorAction.REACT,
                                 new_events=effect_fn(obj, state) or [])
    return [Interceptor(id=new_id(), source=obj.id, controller=obj.controller,
                        priority=InterceptorPriority.REACT, filter=_filter,
                        handler=_handler, duration='until_leaves')]


def _kira_setup(obj, state):
    """Quick Effect (once per turn): negate 1 effect that targets a face-up monster you control."""
    def effect_fn(o, state):
        # Simplification: emit a "negate" event that the chain resolution honors
        return [Event(type=EventType.YGO_CHAIN_LINK,
                      payload={'source_id': o.id, 'effect': 'negate_target',
                               'controller': o.controller})]
    return [make_ygo_quick_effect(obj, effect_fn)]


def _heiko_yamazaki_setup(obj, state):
    """When Tribute Summoned: SS 2 Lv 4 or lower 'Samurai' from your GY in face-up DEF."""
    def effect_fn(o, state):
        events = []
        for _ in range(2):
            target = find_in_graveyard(state, o.controller, "Samurai", max_level=4)
            if not target:
                break
            ev = revive_from_graveyard(state, o.controller, target)
            # Force DEF position
            tobj = state.objects.get(target)
            if tobj:
                tobj.state.ygo_position = 'face_up_def'
            events.extend(ev)
        return events
    def _filter(event, state):
        return (event.type == EventType.YGO_TRIBUTE_SUMMON and
                event.payload.get('card_id') == obj.id)
    from src.engine.types import (Interceptor, InterceptorAction,
                                  InterceptorPriority, InterceptorResult, new_id)
    def _handler(event, state):
        return InterceptorResult(action=InterceptorAction.REACT,
                                 new_events=effect_fn(obj, state) or [])
    return [Interceptor(id=new_id(), source=obj.id, controller=obj.controller,
                        priority=InterceptorPriority.REACT, filter=_filter,
                        handler=_handler, duration='until_leaves')]


def _light_paws_setup(obj, state):
    """When Special Summoned: search 1 Equip Spell from Deck."""
    def effect_fn(o, state):
        return _search_library(state, o.controller, _is_equip_spell)
    return [make_ygo_summon_trigger(obj, effect_fn)]


def _wandering_heir_setup(obj, state):
    """When Normal Summoned: SS 1 'Samurai' from your GY in face-up DEF."""
    def effect_fn(o, state):
        target = find_in_graveyard(state, o.controller, "Samurai")
        if not target:
            return []
        ev = revive_from_graveyard(state, o.controller, target)
        tobj = state.objects.get(target)
        if tobj:
            tobj.state.ygo_position = 'face_up_def'
        return ev
    return [make_ygo_summon_trigger(obj, effect_fn)]


def _otherworldly_journey_setup(obj, state):
    """When destroyed by battle: banish self; during your next Standby Phase, return to field."""
    def effect_fn(o, state):
        # Simplified: just return to your hand
        return _move_to_hand(state, o.controller, o.id)
    return [make_ygo_destroy_trigger(obj, effect_fn)]


def _konda_setup(obj, state):
    """Cannot be destroyed by battle while you control another Samurai. When Tribute Summoned: SS 1 Samurai from your hand."""
    interceptors = []
    # Battle-immortality: while another Samurai exists, redirect destruction-by-battle
    def battle_immortality_modifier(event, state):
        from src.engine.types import (InterceptorAction, InterceptorResult)
        # If something is trying to destroy Konda by battle and we have another Samurai, prevent
        if event.payload.get('card_id') != obj.id:
            return InterceptorResult(action=InterceptorAction.PASS)
        if event.payload.get('reason') != 'battle':
            return InterceptorResult(action=InterceptorAction.PASS)
        if count_on_field(state, obj.controller, "Samurai", exclude_id=obj.id) <= 0:
            return InterceptorResult(action=InterceptorAction.PASS)
        return InterceptorResult(action=InterceptorAction.PREVENT)
    from src.engine.types import (Interceptor, InterceptorAction,
                                  InterceptorPriority, InterceptorResult, new_id)
    def _battle_filter(event, state):
        return event.type == EventType.YGO_DESTROY
    interceptors.append(Interceptor(
        id=new_id(), source=obj.id, controller=obj.controller,
        priority=InterceptorPriority.PREVENT, filter=_battle_filter,
        handler=battle_immortality_modifier, duration='until_leaves',
    ))
    # Tribute Summon trigger: SS 1 Samurai from hand
    def ss_from_hand_fn(o, state):
        hand = state.zones.get(f"hand_{o.controller}")
        zone = state.zones.get(f"monster_zone_{o.controller}")
        if not hand or not zone:
            return []
        for cid in list(hand.objects):
            cobj = state.objects.get(cid)
            if not cobj or not _is_samurai(cobj):
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
            hand.objects.remove(cid)
            zone.objects[slot] = cid
            cobj.zone = ZoneType.MONSTER_ZONE
            cobj.state.ygo_position = 'face_up_atk'
            return [Event(type=EventType.YGO_SPECIAL_SUMMON,
                          payload={'player': o.controller, 'card_id': cid,
                                   'card_name': cobj.name, 'summon_type': 'konda'})]
        return []
    def _ts_filter(event, state):
        return (event.type == EventType.YGO_TRIBUTE_SUMMON and
                event.payload.get('card_id') == obj.id)
    def _ts_handler(event, state):
        return InterceptorResult(action=InterceptorAction.REACT,
                                 new_events=ss_from_hand_fn(obj, state) or [])
    interceptors.append(Interceptor(
        id=new_id(), source=obj.id, controller=obj.controller,
        priority=InterceptorPriority.REACT, filter=_ts_filter,
        handler=_ts_handler, duration='until_leaves',
    ))
    return interceptors


def _hatamoto_setup(obj, state):
    """While you control 'Konda, Lord of Eiganjo': cannot be destroyed by battle or card effects."""
    def modifier_fn(event, state):
        from src.engine.types import (InterceptorAction, InterceptorResult)
        if event.payload.get('card_id') != obj.id:
            return InterceptorResult(action=InterceptorAction.PASS)
        # Check controller has Konda
        zone = state.zones.get(f"monster_zone_{obj.controller}")
        if not zone:
            return InterceptorResult(action=InterceptorAction.PASS)
        has_konda = False
        for oid in zone.objects:
            if not oid or oid == obj.id:
                continue
            other = state.objects.get(oid)
            if other and other.name == "Konda, Lord of Eiganjo":
                has_konda = True
                break
        if not has_konda:
            return InterceptorResult(action=InterceptorAction.PASS)
        return InterceptorResult(action=InterceptorAction.PREVENT)
    from src.engine.types import (Interceptor, InterceptorAction,
                                  InterceptorPriority, InterceptorResult, new_id)
    def _filter(event, state):
        return event.type == EventType.YGO_DESTROY
    return [Interceptor(id=new_id(), source=obj.id, controller=obj.controller,
                        priority=InterceptorPriority.PREVENT, filter=_filter,
                        handler=modifier_fn, duration='until_leaves')]


def _inari_foxguard_setup(obj, state):
    """If a 'Samurai' you control would be destroyed: destroy this card instead. Once per turn."""
    def modifier_fn(event, state):
        from src.engine.types import (InterceptorAction, InterceptorResult)
        # If another Samurai you control is being destroyed, redirect to self
        target_id = event.payload.get('card_id')
        if not target_id or target_id == obj.id:
            return InterceptorResult(action=InterceptorAction.PASS)
        target = state.objects.get(target_id)
        if not target or target.controller != obj.controller:
            return InterceptorResult(action=InterceptorAction.PASS)
        if not _is_samurai(target):
            return InterceptorResult(action=InterceptorAction.PASS)
        # Redirect: destroy self instead
        event.payload['card_id'] = obj.id
        event.payload['card_name'] = obj.name
        event.payload['redirected_from'] = target_id
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=event)
    from src.engine.types import (Interceptor, InterceptorAction,
                                  InterceptorPriority, InterceptorResult, new_id)
    def _filter(event, state):
        return event.type == EventType.YGO_DESTROY
    return [Interceptor(id=new_id(), source=obj.id, controller=obj.controller,
                        priority=InterceptorPriority.PREVENT, filter=_filter,
                        handler=modifier_fn, duration='until_leaves',
                        uses_remaining=1)]


def _sai_of_the_shinobi_setup(obj, state):
    """Once per turn: target 1 'Samurai' you control; that monster gains 800 ATK until EP."""
    def effect_fn(o, state):
        zone = state.zones.get(f"monster_zone_{o.controller}")
        if not zone:
            return []
        for mid in zone.objects:
            if not mid or mid == o.id:
                continue
            target = state.objects.get(mid)
            if target and _is_samurai(target):
                target.state.atk_bonus_eot = getattr(target.state, 'atk_bonus_eot', 0) + 800
                return []
        return []
    return [make_ygo_ignition_effect(obj, effect_fn)]


def _brothers_yamazaki_setup(obj, state):
    """While you control another 'Brothers Yamazaki': this card cannot be destroyed by battle."""
    def modifier_fn(event, state):
        from src.engine.types import (InterceptorAction, InterceptorResult)
        if event.payload.get('card_id') != obj.id:
            return InterceptorResult(action=InterceptorAction.PASS)
        if event.payload.get('reason') != 'battle':
            return InterceptorResult(action=InterceptorAction.PASS)
        zone = state.zones.get(f"monster_zone_{obj.controller}")
        if not zone:
            return InterceptorResult(action=InterceptorAction.PASS)
        has_other = any(
            (other := state.objects.get(oid)) and other.id != obj.id and
            other.name == "Brothers Yamazaki"
            for oid in zone.objects if oid
        )
        if not has_other:
            return InterceptorResult(action=InterceptorAction.PASS)
        return InterceptorResult(action=InterceptorAction.PREVENT)
    from src.engine.types import (Interceptor, InterceptorAction,
                                  InterceptorPriority, InterceptorResult, new_id)
    def _filter(event, state):
        return event.type == EventType.YGO_DESTROY
    return [Interceptor(id=new_id(), source=obj.id, controller=obj.controller,
                        priority=InterceptorPriority.PREVENT, filter=_filter,
                        handler=modifier_fn, duration='until_leaves')]


def _mothrider_samurai_setup(obj, state):
    """If this card battles a Lv 5+ monster: it gains 1500 ATK during damage step only."""
    def modifier_fn(event, state):
        from src.engine.types import (InterceptorAction, InterceptorResult)
        if event.type != EventType.QUERY_POWER:
            return InterceptorResult(action=InterceptorAction.PASS)
        if event.payload.get('object_id') != obj.id:
            return InterceptorResult(action=InterceptorAction.PASS)
        # Check current battle target via state.combat or state.battle
        opp_id = event.payload.get('battle_opponent_id')
        if not opp_id:
            return InterceptorResult(action=InterceptorAction.PASS)
        opp = state.objects.get(opp_id)
        if not opp or not opp.card_def:
            return InterceptorResult(action=InterceptorAction.PASS)
        if (getattr(opp.card_def, 'level', 0) or 0) >= 5:
            event.payload['value'] = event.payload.get('value', 0) + 1500
            return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=event)
        return InterceptorResult(action=InterceptorAction.PASS)
    return [make_ygo_continuous_effect(obj, modifier_fn)]


def _make_flat_other_samurai_boost(obj, atk_bonus: int):
    """Flat self boost while at least one other Samurai is face-up."""
    def modifier_fn(event, state):
        if event.type != EventType.QUERY_POWER:
            return InterceptorResult(action=InterceptorAction.PASS)
        if event.payload.get('object_id') != obj.id:
            return InterceptorResult(action=InterceptorAction.PASS)
        if count_on_field(state, obj.controller, "Samurai", exclude_id=obj.id) <= 0:
            return InterceptorResult(action=InterceptorAction.PASS)
        event.payload['value'] = event.payload.get('value', 0) + atk_bonus
        return InterceptorResult(action=InterceptorAction.TRANSFORM,
                                 transformed_event=event)
    return make_ygo_continuous_effect(obj, modifier_fn)


def _isamaru_setup(obj, state):
    """Small Samurai glue: bushido body plus one battle save each turn."""
    interceptors = [_make_flat_other_samurai_boost(obj, 400)]

    from src.engine.types import (Interceptor, InterceptorAction,
                                  InterceptorPriority, InterceptorResult, new_id)

    def _filter(event, state):
        if event.type != EventType.YGO_DESTROY:
            return False
        if event.payload.get('card_id') != obj.id:
            return False
        if event.payload.get('reason') != 'battle':
            return False
        if count_on_field(state, obj.controller, "Samurai", exclude_id=obj.id) <= 0:
            return False
        return getattr(obj.state, 'isamaru_saved_turn', None) != state.turn_number

    def _handler(event, state):
        obj.state.isamaru_saved_turn = state.turn_number
        return InterceptorResult(action=InterceptorAction.PREVENT)

    interceptors.append(Interceptor(
        id=new_id(), source=obj.id, controller=obj.controller,
        priority=InterceptorPriority.PREVENT, filter=_filter,
        handler=_handler, duration='until_leaves',
    ))
    return interceptors


def _ronin_houndmaster_setup(obj, state):
    """Normal Summon: find a small Samurai; also gets a light bushido pump."""
    def effect_fn(o, state):
        return _search_library(
            state, o.controller,
            lambda c: _is_samurai(c) and c.id != o.id
                      and (getattr(c.card_def, 'level', 99) or 99) <= 2
        )
    return [
        make_ygo_summon_trigger(obj, effect_fn),
        _make_flat_other_samurai_boost(obj, 300),
    ]


def _sokenzan_renegade_setup(obj, state):
    """Normal Summon: recover an Equip if alone; scales once Samurai arrive."""
    def effect_fn(o, state):
        if count_on_field(state, o.controller, "Samurai", exclude_id=o.id) > 0:
            return []
        return _search_library(state, o.controller, _is_equip_spell)
    return [
        make_ygo_summon_trigger(obj, effect_fn),
        _make_flat_other_samurai_boost(obj, 200),
    ]


def _kitsune_tsuki_setup(obj, state):
    """Continuous Trap: opponent's Level 5+ monsters have effects negated."""
    from src.engine.types import (Interceptor, InterceptorAction,
                                  InterceptorPriority, InterceptorResult, new_id)

    def _filter(event, state):
        if obj.zone != ZoneType.SPELL_TRAP_ZONE or obj.state.face_down:
            return False
        if event.type != EventType.QUERY_ABILITIES:
            return False
        target = state.objects.get(event.payload.get('object_id'))
        if target is None or target.controller == obj.controller or not target.card_def:
            return False
        return (getattr(target.card_def, 'level', 0) or 0) >= 5

    def _handler(event, state):
        target = state.objects.get(event.payload.get('object_id'))
        if target is not None:
            target.state.effects_negated = True
        granted = event.payload.setdefault('granted', [])
        if isinstance(granted, list):
            granted.append('effects_negated')
        abilities = event.payload.setdefault('abilities', set())
        if isinstance(abilities, set):
            abilities.add('effects_negated')
        return InterceptorResult(action=InterceptorAction.TRANSFORM,
                                 transformed_event=event)

    return [Interceptor(id=new_id(), source=obj.id, controller=obj.controller,
                        priority=InterceptorPriority.QUERY, filter=_filter,
                        handler=_handler, duration='until_leaves')]


# =============================================================================
# Card definitions — Monsters
# =============================================================================

ISAMARU_HOUND_OF_KONDA = make_ygo_monster(
    "Isamaru, Hound of Konda", atk=800, def_val=600, level=1,
    attribute="EARTH", ygo_monster_type="Effect",
    subtypes={"Beast-Warrior", "Samurai"},
    text="While you control another 'Samurai', this card gains 400 ATK. "
         "Once each turn, if this card would be destroyed by battle, prevent that destruction.",
    setup_interceptors=_isamaru_setup,
)

DEVOTED_RETAINER = make_ygo_monster(
    "Devoted Retainer", atk=800, def_val=600, level=2,
    attribute="LIGHT", ygo_monster_type="Effect",
    subtypes={"Warrior", "Samurai"},
    text="When Normal Summoned: add 1 'Samurai' with 1500 ATK or less from your Deck to your hand.",
    setup_interceptors=_devoted_retainer_setup,
)

KITSUNE_DIVINER = make_ygo_monster(
    "Kitsune Diviner", atk=700, def_val=1500, level=2,
    attribute="LIGHT", ygo_monster_type="Effect",
    subtypes={"Spellcaster", "Samurai"},
    text="FLIP: add 1 Equip Spell from your Deck or GY to your hand. "
         "If the Deck has no Equip Spell, recover one from your GY instead.",
    flip_effect=_kitsune_diviner_flip,
    setup_interceptors=_kitsune_diviner_setup,
)

EIGANJO_FREE_RIDER = make_ygo_monster(
    "Eiganjo Free-Rider", atk=1300, def_val=1000, level=3,
    attribute="LIGHT", ygo_monster_type="Effect",
    subtypes={"Warrior", "Samurai"},
    text="Once per turn (Ignition): change this card's Battle Position. If from face-up DEF to face-up ATK: draw 1 card.",
    setup_interceptors=_eiganjo_free_rider_setup,
)

EIGHT_AND_A_HALF_TAILS = make_ygo_monster(
    "Eight-and-a-Half-Tails", atk=1000, def_val=1000, level=4,
    attribute="LIGHT", ygo_monster_type="Effect", is_tuner=True,
    subtypes={"Spellcaster", "Samurai"},
    text="Once per turn: target 1 face-up monster you control; until EP its Attribute becomes LIGHT and it gains 200 ATK.",
    setup_interceptors=_eight_and_a_half_tails_setup,
)

GENERAL_FUMIKO = make_ygo_monster(
    "General Fumiko", atk=1700, def_val=1500, level=4,
    attribute="EARTH", ygo_monster_type="Effect",
    subtypes={"Warrior", "Samurai"},
    text="When Normal Summoned: SS 1 Lv 4 or lower 'Samurai' from your hand.",
    setup_interceptors=_general_fumiko_setup,
)

KONDAS_BANNER_BEARER = make_ygo_monster(
    "Konda's Banner-Bearer", atk=1500, def_val=1000, level=4,
    attribute="LIGHT", ygo_monster_type="Effect",
    subtypes={"Warrior", "Samurai"},
    text="All other 'Samurai' monsters you control gain 200 ATK. "
         "This banner does not pump itself, so it rewards a wider board.",
    setup_interceptors=lambda obj, state: [
        make_archetype_team_lord(obj, atk_bonus=200, archetype="Samurai")
    ],
)

HAND_OF_HONOR = make_ygo_monster(
    "Hand of Honor", atk=1700, def_val=1500, level=4,
    attribute="LIGHT", ygo_monster_type="Effect",
    subtypes={"Warrior", "Samurai"},
    text="Bushido — While you control another 'Samurai': gains 200 ATK.",
    setup_interceptors=lambda obj, state: [make_bushido(obj, atk_bonus=200, archetype="Samurai")],
)

HAND_OF_CRUELTY = make_ygo_monster(
    "Hand of Cruelty", atk=1700, def_val=1500, level=4,
    attribute="DARK", ygo_monster_type="Effect",
    subtypes={"Warrior", "Samurai"},
    text="Bushido — While you control another 'Samurai': gains 200 ATK.",
    setup_interceptors=lambda obj, state: [make_bushido(obj, atk_bonus=200, archetype="Samurai")],
)

MOTHRIDER_SAMURAI = make_ygo_monster(
    "Mothrider Samurai", atk=1500, def_val=1000, level=4,
    attribute="LIGHT", ygo_monster_type="Effect",
    subtypes={"Wing Beast", "Samurai"},
    text="If this card battles a Lv 5+ monster: gains 1500 ATK during damage step only.",
    setup_interceptors=_mothrider_samurai_setup,
)

BROTHERS_YAMAZAKI = make_ygo_monster(
    "Brothers Yamazaki", atk=1800, def_val=1000, level=4,
    attribute="EARTH", ygo_monster_type="Effect",
    subtypes={"Warrior", "Samurai"},
    text="While you control another 'Brothers Yamazaki': this card cannot be destroyed by battle.",
    setup_interceptors=_brothers_yamazaki_setup,
)

RONIN_HOUNDMASTER = make_ygo_monster(
    "Ronin Houndmaster", atk=1900, def_val=1500, level=4,
    attribute="EARTH", ygo_monster_type="Effect",
    subtypes={"Warrior", "Samurai"},
    text="When Normal Summoned: add 1 Level 2 or lower 'Samurai' from your Deck "
         "to your hand. While you control another 'Samurai', this card gains 300 ATK.",
    setup_interceptors=_ronin_houndmaster_setup,
)

KONDAS_HATAMOTO = make_ygo_monster(
    "Konda's Hatamoto", atk=1700, def_val=1500, level=4,
    attribute="LIGHT", ygo_monster_type="Effect",
    subtypes={"Warrior", "Samurai"},
    text="While you control 'Konda, Lord of Eiganjo': cannot be destroyed.",
    setup_interceptors=_hatamoto_setup,
)

IMPERIAL_RECOVERY_UNIT = make_ygo_monster(
    "Imperial Recovery Unit", atk=1500, def_val=1500, level=4,
    attribute="EARTH", ygo_monster_type="Effect",
    subtypes={"Machine", "Samurai"},
    text="When sent from field to GY: add 1 'Samurai' from your GY to your hand.",
    setup_interceptors=_imperial_recovery_unit_setup,
)

MUKOTAI_AMBUSHER = make_ygo_monster(
    "Mukotai Ambusher", atk=1700, def_val=1700, level=4,
    attribute="DARK", ygo_monster_type="Effect",
    subtypes={"Warrior", "Samurai"},
    text="Once per turn: tribute 1 'Samurai' you control; destroy 1 face-up monster opponent controls.",
    setup_interceptors=_mukotai_ambusher_setup,
)

ASARI_CAPTAIN = make_ygo_monster(
    "Asari Captain", atk=1700, def_val=1700, level=4,
    attribute="EARTH", ygo_monster_type="Effect",
    subtypes={"Warrior", "Samurai"},
    text="When this card declares an attack: gain 500 LP for each 'Samurai' in your GY (max 2500).",
    setup_interceptors=_asari_captain_setup,
)

KIRA_GREAT_GLASS_SPINNER = make_ygo_monster(
    "Kira, Great Glass-Spinner", atk=800, def_val=1500, level=3,
    attribute="LIGHT", ygo_monster_type="Effect",
    subtypes={"Spellcaster", "Samurai"},
    text="Quick Effect (once per turn): negate 1 effect that targets a face-up monster you control.",
    setup_interceptors=_kira_setup,
)

SAI_OF_THE_SHINOBI = make_ygo_monster(
    "Sai of the Shinobi", atk=1500, def_val=1500, level=4,
    attribute="EARTH", ygo_monster_type="Effect",
    subtypes={"Warrior", "Samurai"},
    text="Once per turn: target 1 'Samurai' you control; that monster gains 800 ATK until End Phase.",
    setup_interceptors=_sai_of_the_shinobi_setup,
)

INARI_ASCENDANT_FOXGUARD = make_ygo_monster(
    "Inari Ascendant Foxguard", atk=1900, def_val=1000, level=4,
    attribute="LIGHT", ygo_monster_type="Effect",
    subtypes={"Beast", "Samurai"},
    text="If a 'Samurai' you control would be destroyed: destroy this card instead. Once per turn.",
    setup_interceptors=_inari_foxguard_setup,
)

HEIKO_YAMAZAKI = make_ygo_monster(
    "Heiko Yamazaki, the General", atk=2400, def_val=2000, level=6,
    attribute="EARTH", ygo_monster_type="Effect",
    subtypes={"Warrior", "Samurai"},
    text="When Tribute Summoned: SS up to 2 Lv 4 or lower 'Samurai' from your GY in face-up DEF.",
    setup_interceptors=_heiko_yamazaki_setup,
)

LIGHT_PAWS_EMPERORS_VOICE = make_ygo_monster(
    "Light-Paws, Emperor's Voice", atk=2000, def_val=2000, level=5,
    attribute="LIGHT", ygo_monster_type="Effect",
    subtypes={"Beast", "Samurai"},
    text="When Special Summoned: search 1 Equip Spell from your Deck.",
    setup_interceptors=_light_paws_setup,
)

THE_WANDERING_HEIR = make_ygo_monster(
    "The Wandering Heir", atk=2200, def_val=2000, level=5,
    attribute="LIGHT", ygo_monster_type="Effect", is_tuner=True,
    subtypes={"Warrior", "Samurai"},
    text="When Normal Summoned: SS 1 'Samurai' from your GY in face-up DEF.",
    setup_interceptors=_wandering_heir_setup,
)

OTHERWORLDLY_JOURNEY = make_ygo_monster(
    "Otherworldly Journey", atk=1300, def_val=1500, level=4,
    attribute="LIGHT", ygo_monster_type="Effect",
    subtypes={"Spellcaster", "Samurai"},
    text="When destroyed: return this card to your hand.",
    setup_interceptors=_otherworldly_journey_setup,
)

KONDA_LORD_OF_EIGANJO = make_ygo_monster(
    "Konda, Lord of Eiganjo", atk=3000, def_val=2500, level=8,
    attribute="LIGHT", ygo_monster_type="Effect",
    subtypes={"Warrior", "Samurai"},
    text="Cannot be destroyed by battle while you control another 'Samurai'. When Tribute Summoned: SS 1 'Samurai' from your hand.",
    setup_interceptors=_konda_setup,
)

SOKENZAN_RENEGADE = make_ygo_monster(
    "Sokenzan Renegade", atk=1900, def_val=0, level=4,
    attribute="FIRE", ygo_monster_type="Effect",
    subtypes={"Warrior", "Samurai"},
    text="When Normal Summoned, if you control no other 'Samurai': add 1 Equip "
         "Spell from your Deck to your hand. While you control another 'Samurai', this gains 200 ATK.",
    setup_interceptors=_sokenzan_renegade_setup,
)


# =============================================================================
# Card definitions — Spells
# =============================================================================

def _path_of_bravery_resolve(event, state):
    """Continuous: each Samurai you Normal Summon gains +200 ATK (handled as ATK boost)."""
    return []  # Simplified: continuous-spell stat boost would need an interceptor; placeholder


def _path_of_bravery_setup(obj, state):
    """Track Samurai Normal Summons and grant a query-time ATK bonus."""
    from src.engine.types import (Interceptor, InterceptorAction,
                                  InterceptorPriority, InterceptorResult, new_id)

    def _active() -> bool:
        return obj.zone == ZoneType.SPELL_TRAP_ZONE

    def summon_filter(event, state):
        if not _active() or event.type != EventType.YGO_NORMAL_SUMMON:
            return False
        if event.payload.get('player') != obj.controller:
            return False
        target = state.objects.get(event.payload.get('card_id'))
        return target is not None and _is_samurai(target)

    def summon_handler(event, state):
        target = state.objects.get(event.payload.get('card_id'))
        if not target:
            return InterceptorResult(action=InterceptorAction.PASS)
        target.state.path_bravery_bonus = getattr(
            target.state, 'path_bravery_bonus', 0
        ) + 200
        return InterceptorResult(action=InterceptorAction.REACT, new_events=[
            Event(type=EventType.YGO_CHAIN_LINK,
                  payload={'effect': 'path_bravery_bonus',
                           'card_id': target.id, 'amount': 200})
        ])

    def boost_filter(event, state):
        if not _active() or event.type != EventType.QUERY_POWER:
            return False
        target = state.objects.get(event.payload.get('object_id'))
        return target is not None and target.controller == obj.controller

    def boost_handler(event, state):
        target = state.objects.get(event.payload.get('object_id'))
        bonus = getattr(target.state, 'path_bravery_bonus', 0) if target else 0
        if bonus <= 0:
            return InterceptorResult(action=InterceptorAction.PASS)
        event.payload['value'] = event.payload.get('value', 0) + bonus
        return InterceptorResult(action=InterceptorAction.TRANSFORM,
                                 transformed_event=event)

    return [
        Interceptor(id=new_id(), source=obj.id, controller=obj.controller,
                    priority=InterceptorPriority.REACT, filter=summon_filter,
                    handler=summon_handler, duration='until_leaves'),
        Interceptor(id=new_id(), source=obj.id, controller=obj.controller,
                    priority=InterceptorPriority.QUERY, filter=boost_filter,
                    handler=boost_handler, duration='until_leaves'),
    ]


PATH_OF_BRAVERY = make_ygo_spell(
    "Path of Bravery", ygo_spell_type="Continuous",
    text="While face-up: when you Normal Summon a 'Samurai', that monster "
         "gains 200 ATK while this card remains on the field. Layer "
         "simplification: store a query-time bonus on that monster.",
    resolve=_path_of_bravery_resolve,
    setup_interceptors=_path_of_bravery_setup,
)


def _splice_bushido_resolve(event, state):
    """Quick-Play: target Samurai gains 1000 ATK until End Phase."""
    targets = event.payload.get('targets') or []
    if not targets:
        # Auto-target: first Samurai you control
        controller = event.payload.get('player')
        if controller:
            zone = state.zones.get(f"monster_zone_{controller}")
            if zone:
                for oid in zone.objects:
                    if oid:
                        cobj = state.objects.get(oid)
                        if cobj and _is_samurai(cobj):
                            targets = [oid]
                            break
    if not targets:
        return []
    target = state.objects.get(targets[0])
    if target and _is_samurai(target):
        target.state.atk_bonus_eot = getattr(target.state, 'atk_bonus_eot', 0) + 1000
    return []


SPLICE_BUSHIDO = make_ygo_spell(
    "Splice Bushido", ygo_spell_type="Quick-Play",
    text="Target 1 'Samurai' you control: it gains 1000 ATK until End Phase.",
    resolve=_splice_bushido_resolve,
)


def _imperial_edict_resolve(event, state):
    """Phase 4 demo: search your Deck for 2 cards (was blind top-2 grab).

    The Emperor's edict reaches into the deck and pulls 2 named cards — a
    real search, not a draw. For humans this emits a ``PendingChoice`` over
    every card in their library; for AI the heuristic_pick preserves the
    prior "top 2 library cards" behavior so existing AI play doesn't shift.

    After both cards are added to hand, the controller still discards 1
    (simplified to "last added to hand", matching the old behavior).
    """
    from src.engine.pending_choice_helpers import create_choice_and_resolve

    controller = event.payload.get('player')
    if not controller:
        return []
    library = state.zones.get(f"library_{controller}")
    hand = state.zones.get(f"hand_{controller}")
    if not library or not hand:
        return []

    # Empty short-circuit: no library cards → nothing to search, no choice.
    if not library.objects:
        return []

    source_id = event.payload.get('card_id') or ''

    # How many to search for: up to 2, but no more than library size.
    want = min(2, len(library.objects))

    # Build options over the full library visible to the searcher.
    options = []
    for cid in library.objects:
        cobj = state.objects.get(cid)
        if cobj is None or cobj.card_def is None:
            continue
        cdef = cobj.card_def
        # Description hints at type/atk/def for monsters, spell/trap for non-monsters.
        atk = getattr(cdef, 'atk', None)
        df = getattr(cdef, 'def_', None) if hasattr(cdef, 'def_') else getattr(cdef, 'defense', None)
        spell_type = getattr(cdef, 'ygo_spell_type', None)
        trap_type = getattr(cdef, 'ygo_trap_type', None)
        if atk is not None and df is not None:
            desc = f"Monster · {atk}/{df}"
        elif spell_type:
            desc = f"Spell · {spell_type}"
        elif trap_type:
            desc = f"Trap · {trap_type}"
        else:
            desc = ""
        options.append({"id": cid, "label": cobj.name, "description": desc})

    if not options:
        return []

    # Heuristic_pick = top N library cards (preserves old "blind grab top 2"
    # behavior for AI). Take from the raw library order.
    top_ids = [cid for cid in library.objects[:want]]

    def _resolve_handler(choice, selected, st):
        # Tolerate raw id list or list of {id: ...} dicts.
        picked: list[str] = []
        for entry in selected or []:
            if isinstance(entry, dict):
                eid = entry.get("id")
                if eid is not None:
                    picked.append(eid)
            else:
                picked.append(entry)
        # Cap at the requested count.
        picked = picked[:want]

        # Pull picked cards from library to hand (preserves the old draw-event
        # emission so downstream effects that listen for YGO_DRAW still fire).
        lib = st.zones.get(f"library_{controller}")
        hd = st.zones.get(f"hand_{controller}")
        if lib is None or hd is None:
            return []
        out: list[Event] = []
        for cid in picked:
            if cid not in lib.objects:
                continue
            lib.objects.remove(cid)
            hd.objects.append(cid)
            cobj = st.objects.get(cid)
            if cobj is not None:
                cobj.zone = ZoneType.HAND
            out.append(Event(type=EventType.YGO_DRAW,
                             payload={'player': controller, 'count': 1,
                                      'card_id': cid, 'source': 'imperial_edict'}))
        # Auto-discard one card (simplified: last added to hand), as before.
        if hd.objects:
            discard_id = hd.objects.pop()
            gy = st.zones.get(f"graveyard_{controller}")
            if gy is not None:
                gy.objects.append(discard_id)
            dobj = st.objects.get(discard_id)
            if dobj is not None:
                dobj.zone = ZoneType.GRAVEYARD
            out.append(Event(type=EventType.YGO_SEND_TO_GY,
                             payload={'card_id': discard_id,
                                      'reason': 'imperial_edict_discard'}))
        return out

    return create_choice_and_resolve(
        state,
        choice_type="target",
        player_id=controller,
        prompt=f"Search your Deck for {want} card(s) to add to your hand.",
        options=options,
        source_id=source_id,
        min_choices=want,
        max_choices=want,
        handler=_resolve_handler,
        heuristic_pick=top_ids,
    )


IMPERIAL_EDICT = make_ygo_spell(
    "Imperial Edict", ygo_spell_type="Normal",
    text="Search your Deck for 2 cards and add them to your hand, then discard 1.",
    resolve=_imperial_edict_resolve,
)


def _eiganjo_castle_setup(obj, state):
    """Field Spell: Samurai boost and once-per-turn battle protection."""
    from src.engine.types import (Interceptor, InterceptorAction,
                                  InterceptorPriority, InterceptorResult, new_id)

    def _active() -> bool:
        return obj.zone == ZoneType.FIELD_SPELL_ZONE

    def boost_filter(event, state):
        if not _active() or event.type != EventType.QUERY_POWER:
            return False
        target = state.objects.get(event.payload.get('object_id'))
        return target is not None and target.controller == obj.controller and _is_samurai(target)

    def boost_handler(event, state):
        event.payload['value'] = event.payload.get('value', 0) + 200
        return InterceptorResult(action=InterceptorAction.TRANSFORM,
                                 transformed_event=event)

    def prevent_filter(event, state):
        if not _active() or event.type != EventType.YGO_DESTROY:
            return False
        if event.payload.get('reason') != 'battle':
            return False
        target = state.objects.get(event.payload.get('card_id'))
        if target is None or target.controller != obj.controller or not _is_samurai(target):
            return False
        saved_turn = getattr(obj.state, 'eiganjo_saved_turn', None)
        return saved_turn != state.turn_number

    def prevent_handler(event, state):
        obj.state.eiganjo_saved_turn = state.turn_number
        return InterceptorResult(action=InterceptorAction.PREVENT)

    return [
        Interceptor(id=new_id(), source=obj.id, controller=obj.controller,
                    priority=InterceptorPriority.QUERY, filter=boost_filter,
                    handler=boost_handler, duration='until_leaves'),
        Interceptor(id=new_id(), source=obj.id, controller=obj.controller,
                    priority=InterceptorPriority.PREVENT, filter=prevent_filter,
                    handler=prevent_handler, duration='until_leaves'),
    ]


EIGANJO_CASTLE = make_ygo_spell(
    "Eiganjo Castle", ygo_spell_type="Field",
    text="All 'Samurai' you control gain 200 ATK. The first 'Samurai' you control destroyed by battle each turn is not destroyed.",
    setup_interceptors=_eiganjo_castle_setup,
)


def _sword_of_light_and_shadow_setup(obj, state):
    """Equip: Samurai gains 200 ATK and DEF. When sent to GY: add 1 'Samurai' from GY."""
    from src.engine.yugioh_helpers import make_ygo_equip_boost
    interceptors = [make_ygo_equip_boost(obj, atk_boost=200, def_boost=200)]
    def effect_fn(o, state):
        target = find_in_graveyard(state, o.controller, "Samurai")
        if not target or target == o.id:
            return []
        return _move_to_hand(state, o.controller, target)
    interceptors.append(make_ygo_destroy_trigger(obj, effect_fn))
    return interceptors


SWORD_OF_LIGHT_AND_SHADOW = make_ygo_spell(
    "Sword of Light and Shadow", ygo_spell_type="Equip",
    text="Equipped 'Samurai' gains 200 ATK and DEF. When this card is sent to the GY: add 1 'Samurai' from your GY to your hand.",
    setup_interceptors=_sword_of_light_and_shadow_setup,
)


def _reciprocate_resolve(event, state):
    """Target Samurai gains 1000 ATK and is indestructible by battle this turn."""
    targets = event.payload.get('targets') or []
    if not targets:
        return []
    target = state.objects.get(targets[0])
    if target and _is_samurai(target):
        target.state.atk_bonus_eot = getattr(target.state, 'atk_bonus_eot', 0) + 1000
        target.state.battle_indestructible_eot = True
    return []


RECIPROCATE = make_ygo_spell(
    "Reciprocate", ygo_spell_type="Quick-Play",
    text="Target 1 'Samurai' you control: gain 1000 ATK; cannot be destroyed by battle this turn.",
    resolve=_reciprocate_resolve,
)


def _honor_worn_shaku_setup(obj, state):
    """Equip: equipped Samurai is treated as a Tuner and gains 300 ATK."""
    from src.engine.types import (Interceptor, InterceptorAction,
                                  InterceptorPriority, InterceptorResult, new_id)
    from src.engine.yugioh_helpers import make_ygo_equip_boost
    interceptors = [make_ygo_equip_boost(obj, atk_boost=300, def_boost=0)]
    def make_tuner(event, state):
        target_id = getattr(obj.state, 'equipped_to', None)
        if not target_id:
            return InterceptorResult(action=InterceptorAction.PASS)
        target = state.objects.get(target_id)
        if target and target.card_def and not target.card_def.is_tuner:
            target.card_def.is_tuner = True
        return InterceptorResult(action=InterceptorAction.PASS)
    interceptors.append(Interceptor(
        id=new_id(), source=obj.id, controller=obj.controller,
        priority=InterceptorPriority.QUERY,
        filter=lambda e, s: e.type == EventType.QUERY_ABILITIES,
        handler=make_tuner, duration='until_leaves',
    ))
    return interceptors


HONOR_WORN_SHAKU = make_ygo_spell(
    "Honor-Worn Shaku", ygo_spell_type="Equip",
    text="Equipped 'Samurai' is treated as a Tuner and gains 300 ATK.",
    setup_interceptors=_honor_worn_shaku_setup,
)


def _cleaving_reach_resolve(event, state):
    """Send 1 Equip Spell you control to GY; destroy 1 face-up opponent monster."""
    controller = event.payload.get('player')
    if not controller:
        return []
    # Send first equip spell controlled to GY
    sent = False
    for obj in list(state.objects.values()):
        if obj.controller == controller and _is_equip_spell(obj):
            for z in state.zones.values():
                while obj.id in z.objects:
                    z.objects.remove(obj.id)
            gy = state.zones.get(f"graveyard_{controller}")
            if gy is not None:
                gy.objects.append(obj.id)
            obj.zone = ZoneType.GRAVEYARD
            sent = True
            break
    if not sent:
        return []
    return _destroy_one_face_up_opponent(state, controller)


CLEAVING_REACH = make_ygo_spell(
    "Cleaving Reach", ygo_spell_type="Normal",
    text="Send 1 Equip Spell you control to the GY; destroy 1 face-up monster opponent controls.",
    resolve=_cleaving_reach_resolve,
)


def _glistening_katana_setup(obj, state):
    from src.engine.yugioh_helpers import make_ygo_equip_boost
    return [make_ygo_equip_boost(obj, atk_boost=800, def_boost=0)]


GLISTENING_KATANA = make_ygo_spell(
    "Glistening Katana", ygo_spell_type="Equip",
    text="Equipped monster gains 800 ATK. When equipped monster destroys an opponent's monster: draw 1.",
    setup_interceptors=_glistening_katana_setup,
)


def _imperial_mobilization_resolve(event, state):
    """SS up to 2 Lv 3 or lower Samurai from your GY in face-up DEF."""
    controller = event.payload.get('player')
    if not controller:
        return []
    events = []
    for _ in range(2):
        target = find_in_graveyard(state, controller, "Samurai", max_level=3)
        if not target:
            break
        ev = revive_from_graveyard(state, controller, target)
        tobj = state.objects.get(target)
        if tobj:
            tobj.state.ygo_position = 'face_up_def'
        events.extend(ev)
    return events


IMPERIAL_MOBILIZATION = make_ygo_spell(
    "Imperial Mobilization", ygo_spell_type="Normal",
    text="SS up to 2 Lv 3 or lower 'Samurai' from your GY in face-up Defense Position.",
    resolve=_imperial_mobilization_resolve,
)


def _bushido_drill_resolve(event, state):
    return []  # Continuous spell — wired via setup_interceptors below


def _bushido_drill_setup(obj, state):
    """Once per turn (Ignition): tribute 1 'Samurai'; SS 1 'Samurai' from your GY whose Level >= tributed."""
    def effect_fn(o, state):
        # Find a Samurai on the field to tribute (excluding this spell's "object")
        zone = state.zones.get(f"monster_zone_{o.controller}")
        if not zone:
            return []
        tributed_level = 0
        tributed_id = None
        for i, oid in enumerate(zone.objects):
            if not oid:
                continue
            cobj = state.objects.get(oid)
            if cobj and _is_samurai(cobj):
                tributed_id = oid
                tributed_level = getattr(cobj.card_def, 'level', 0) or 0
                zone.objects[i] = None
                gy = state.zones.get(f"graveyard_{cobj.owner}")
                if gy:
                    gy.objects.append(oid)
                cobj.zone = ZoneType.GRAVEYARD
                cobj.state.ygo_position = None
                break
        if not tributed_id:
            return []
        # Find a same-or-higher level Samurai in GY
        gy = state.zones.get(f"graveyard_{o.controller}")
        if not gy:
            return []
        for cid in list(gy.objects):
            if cid == tributed_id:
                continue
            cobj = state.objects.get(cid)
            if cobj and _is_samurai(cobj):
                lvl = getattr(cobj.card_def, 'level', 0) or 0
                if lvl >= tributed_level:
                    return revive_from_graveyard(state, o.controller, cid)
        return []
    return [make_ygo_ignition_effect(obj, effect_fn)]


BUSHIDO_DRILL = make_ygo_spell(
    "Bushido Drill", ygo_spell_type="Continuous",
    text="Once per turn: tribute 1 'Samurai'; SS 1 'Samurai' from your GY whose Level >= tributed.",
    setup_interceptors=_bushido_drill_setup,
)


def _wandering_decree_resolve(event, state):
    """Send 1 Samurai from field to GY; SS 1 Lv 5+ 'Samurai' from your hand or GY."""
    controller = event.payload.get('player')
    if not controller:
        return []
    # Sacrifice a Samurai
    sacrificed = _tribute_one(state, controller, _is_samurai)
    if not sacrificed:
        return []
    # SS Lv 5+ Samurai from GY
    gy = state.zones.get(f"graveyard_{controller}")
    if gy:
        for cid in list(gy.objects):
            if cid == sacrificed:
                continue
            cobj = state.objects.get(cid)
            if cobj and _is_samurai(cobj):
                lvl = getattr(cobj.card_def, 'level', 0) or 0
                if lvl >= 5:
                    return revive_from_graveyard(state, controller, cid)
    return []


THE_WANDERING_DECREE = make_ygo_spell(
    "The Wandering Decree", ygo_spell_type="Quick-Play",
    text="Send 1 'Samurai' you control to the GY; SS 1 Lv 5+ 'Samurai' from your hand or GY.",
    resolve=_wandering_decree_resolve,
)


# =============================================================================
# Card definitions — Traps
# =============================================================================

def _bushido_honor_resolve(event, state):
    """Trigger when a Samurai you control declares an attack — give +1000 ATK/DEF EOT."""
    targets = event.payload.get('targets') or []
    target_id = targets[0] if targets else event.payload.get('attacker_id')
    if not target_id:
        return []
    target = state.objects.get(target_id)
    if target and _is_samurai(target):
        target.state.atk_bonus_eot = getattr(target.state, 'atk_bonus_eot', 0) + 1000
        target.state.def_bonus_eot = getattr(target.state, 'def_bonus_eot', 0) + 1000
    return []


BUSHIDO_HONOR = make_ygo_trap(
    "Bushido Honor", ygo_trap_type="Normal",
    text="When a 'Samurai' you control declares an attack: it gains 1000 ATK and DEF until End Phase.",
    resolve=_bushido_honor_resolve,
)


def _final_flourish_resolve(event, state):
    """Counter Trap — negate the destroying effect on a Samurai."""
    return [Event(type=EventType.YGO_CHAIN_LINK,
                  payload={'effect': 'negate_destroy', 'controller': event.payload.get('player')})]


FINAL_FLOURISH = make_ygo_trap(
    "Final Flourish", ygo_trap_type="Counter",
    text="When a 'Samurai' you control would be destroyed by an opponent's effect: negate it.",
    resolve=_final_flourish_resolve,
)


def _stand_together_resolve(event, state):
    """Tribute 1 face-up monster you control; SS 1 'Samurai' from your GY in face-up ATK."""
    controller = event.payload.get('player')
    if not controller:
        return []
    sacrificed = _tribute_one(state, controller)
    if not sacrificed:
        return []
    target = find_in_graveyard(state, controller, "Samurai")
    if not target:
        return []
    return revive_from_graveyard(state, controller, target)


STAND_TOGETHER = make_ygo_trap(
    "Stand Together", ygo_trap_type="Normal",
    text="Tribute 1 face-up monster you control; SS 1 'Samurai' from your GY.",
    resolve=_stand_together_resolve,
)


def _heroic_sacrifice_resolve(event, state):
    """Tribute 1 'Samurai'; destroy 1 face-up card opponent controls."""
    controller = event.payload.get('player')
    if not controller:
        return []
    sacrificed = _tribute_one(state, controller, _is_samurai)
    if not sacrificed:
        return []
    return _destroy_one_face_up_opponent(state, controller)


HEROIC_SACRIFICE = make_ygo_trap(
    "Heroic Sacrifice", ygo_trap_type="Normal",
    text="Tribute 1 'Samurai'; destroy 1 face-up card opponent controls.",
    resolve=_heroic_sacrifice_resolve,
)


def _shroud_setup(obj, state):
    """When a Samurai you control is destroyed: SS 1 Samurai with the same Level from your GY."""
    def effect_fn(o, state):
        # On the destroy event, look at the most recent destroyed Samurai
        target = find_in_graveyard(state, o.controller, "Samurai")
        if not target:
            return []
        return revive_from_graveyard(state, o.controller, target)
    from src.engine.types import (Interceptor, InterceptorAction,
                                  InterceptorPriority, InterceptorResult, new_id)
    def _filter(event, state):
        if event.type != EventType.YGO_DESTROY:
            return False
        cid = event.payload.get('card_id')
        if not cid:
            return False
        cobj = state.objects.get(cid)
        return cobj is not None and cobj.controller == obj.controller and _is_samurai(cobj)
    def _handler(event, state):
        return InterceptorResult(action=InterceptorAction.REACT,
                                 new_events=effect_fn(obj, state) or [])
    return [Interceptor(id=new_id(), source=obj.id, controller=obj.controller,
                        priority=InterceptorPriority.REACT, filter=_filter,
                        handler=_handler, duration='until_leaves')]


SHROUD_OF_THE_ETERNAL = make_ygo_trap(
    "Shroud of the Eternal", ygo_trap_type="Continuous",
    text="Once per turn: when a 'Samurai' you control is destroyed: SS 1 'Samurai' from your GY.",
    setup_interceptors=_shroud_setup,
)


KITSUNE_TSUKI = make_ygo_trap(
    "Kitsune-Tsuki", ygo_trap_type="Continuous",
    text="While this card is face-up, negate the effects of opponent's Level 5+ "
         "monsters on the field. Layer simplification: affected monsters gain an effects_negated marker.",
    setup_interceptors=_kitsune_tsuki_setup,
)


# =============================================================================
# Card definitions — Extra Deck
# =============================================================================

def _wandering_emperor_setup(obj, state):
    """Detach 1 material; SS 1 Lv 4 or lower 'Samurai' from your Deck."""
    def effect_fn(o, state):
        if not o.state.overlay_units:
            return []
        # Detach
        detached = o.state.overlay_units.pop(0)
        gy = state.zones.get(f"graveyard_{o.controller}")
        if gy is not None:
            gy.objects.append(detached)
        # SS Samurai from Deck
        zone = state.zones.get(f"monster_zone_{o.controller}")
        library = state.zones.get(f"library_{o.controller}")
        if not zone or not library:
            return []
        for cid in list(library.objects):
            cobj = state.objects.get(cid)
            if not cobj or not _is_samurai(cobj):
                continue
            lvl = getattr(cobj.card_def, 'level', 99) or 99
            if lvl > 4:
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
            cobj.state.ygo_position = 'face_up_atk'
            return [Event(type=EventType.YGO_SPECIAL_SUMMON,
                          payload={'player': o.controller, 'card_id': cid,
                                   'card_name': cobj.name, 'summon_type': 'wandering_emperor'})]
        return []
    interceptors = [make_ygo_ignition_effect(obj, effect_fn)]
    # Lord effect: while this has Xyz Materials, Samurai you control gain 500 ATK
    def lord_modifier(event, state):
        from src.engine.types import (InterceptorAction, InterceptorResult)
        if event.type != EventType.QUERY_POWER:
            return InterceptorResult(action=InterceptorAction.PASS)
        target_id = event.payload.get('object_id')
        target = state.objects.get(target_id) if target_id else None
        if not target or target.controller != obj.controller or not _is_samurai(target):
            return InterceptorResult(action=InterceptorAction.PASS)
        if not obj.state.overlay_units:
            return InterceptorResult(action=InterceptorAction.PASS)
        event.payload['value'] = event.payload.get('value', 0) + 500
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=event)
    interceptors.append(make_ygo_continuous_effect(obj, lord_modifier))
    return interceptors


THE_WANDERING_EMPEROR = make_ygo_monster(
    "The Wandering Emperor", atk=2500, def_val=2500, level=4,
    attribute="LIGHT", ygo_monster_type="Xyz", rank=4,
    subtypes={"Warrior", "Samurai"},
    text="2 Lv 4 monsters. Once per turn: detach 1 material; SS 1 Lv 4 or lower 'Samurai' from your Deck. While this has Xyz Material: 'Samurai' you control gain 500 ATK.",
    materials="2 Lv 4 monsters",
    setup_interceptors=_wandering_emperor_setup,
)


def _konda_apex_dragon_setup(obj, state):
    """When Synchro Summoned: destroy all face-up monsters opponent controls."""
    def effect_fn(o, state):
        events = []
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
    return [make_ygo_summon_trigger(obj, effect_fn)]


KONDAS_APEX_DRAGON = make_ygo_monster(
    "Konda's Apex Dragon", atk=3000, def_val=2500, level=8,
    attribute="LIGHT", ygo_monster_type="Synchro",
    subtypes={"Dragon", "Samurai"},
    text="1 Tuner + 1+ non-Tuner 'Samurai'. When Synchro Summoned: destroy all face-up monsters opponent controls.",
    materials="1 Tuner + 1+ non-Tuner 'Samurai'",
    setup_interceptors=_konda_apex_dragon_setup,
)


def _saheeli_lattice_setup(obj, state):
    """When Synchro Summoned: SS 1 'Lattice Samurai' (a Samurai) from your GY."""
    def effect_fn(o, state):
        target = find_in_graveyard(state, o.controller, "Samurai")
        if not target:
            return []
        return revive_from_graveyard(state, o.controller, target)
    return [make_ygo_summon_trigger(obj, effect_fn)]


SAHEELIS_IMPERIAL_LATTICE = make_ygo_monster(
    "Saheeli's Imperial Lattice", atk=2300, def_val=2000, level=6,
    attribute="EARTH", ygo_monster_type="Synchro",
    subtypes={"Machine", "Samurai"},
    text="1 Tuner + 1+ non-Tuner 'Samurai'. When Synchro Summoned: SS 1 'Samurai' from your GY.",
    materials="1 Tuner + 1+ non-Tuner 'Samurai'",
    setup_interceptors=_saheeli_lattice_setup,
)


OTAWARA_IMPERIAL_STRONGHOLD = make_ygo_monster(
    "Otawara, Imperial Stronghold", atk=1900, def_val=0, level=2,
    attribute="LIGHT", ygo_monster_type="Link", link_rating=2,
    link_arrows=["bottom_left", "bottom_right"],
    subtypes={"Warrior", "Samurai"},
    text="2 'Samurai' monsters. While this card points to a 'Samurai': that 'Samurai' gains 500 ATK and DEF.",
    materials="2 'Samurai' monsters",
    setup_interceptors=lambda obj, state: [make_archetype_lord(obj, atk_bonus=500, def_bonus=500, archetype="Samurai")],
)


def _storm_of_saito_setup(obj, state):
    """When Synchro Summoned: deal 400 damage to opponent for each 'Samurai' you control."""
    def effect_fn(o, state):
        n = count_on_field(state, o.controller, "Samurai")
        damage = 400 * n
        if damage <= 0:
            return []
        events = []
        for pid in state.players:
            if pid == o.controller:
                continue
            player = state.players.get(pid)
            if player:
                player.lp = max(0, player.lp - damage)
                events.append(Event(type=EventType.YGO_LP_CHANGE,
                                    payload={'player': pid, 'amount': -damage,
                                             'source': 'Storm of Saito'}))
        return events
    return [make_ygo_summon_trigger(obj, effect_fn)]


STORM_OF_SAITO = make_ygo_monster(
    "Storm of Saito", atk=2400, def_val=2000, level=7,
    attribute="WIND", ygo_monster_type="Synchro",
    subtypes={"Wing Beast", "Samurai"},
    text="1 Tuner + 1+ non-Tuner 'Samurai'. When Synchro Summoned: deal 400 damage to opponent per 'Samurai' you control.",
    materials="1 Tuner + 1+ non-Tuner 'Samurai'",
    setup_interceptors=_storm_of_saito_setup,
)


_PASS3_TEXT_APPENDIX = {
    "Hand of Cruelty": "Battle rule: the Bushido bonus is checked through the stat layer whenever another Samurai is face-up, so removal can turn it off mid-combat.",
    "Hand of Honor": "Battle rule: the Bushido bonus is checked through the stat layer whenever another Samurai is face-up, so removal can turn it off mid-combat.",
    "Konda's Hatamoto": "Protection rule: while Konda is face-up on your field, destruction effects and battle destruction that target this retainer are prevented by its interceptor.",
    "Imperial Edict": "Resolution simplification: emit a target PendingChoice over your Deck (min/max = 2); AI keeps the historical top-2 heuristic. After the chosen cards enter your hand, the last card is auto-discarded to GY.",
    "Imperial Mobilization": "Resolution simplification: choose the first legal Level 3 or lower Samurai in your GY, Special Summon it in Defense Position, then repeat once if a slot remains.",
    "The Wandering Decree": "Cost and resolution: send the first Samurai you control to the GY, then Special Summon the first Level 5 or higher Samurai available from your GY.",
    "Stand Together": "Cost and resolution: tribute the first face-up monster you control, then return the first Samurai in your GY to the field in Attack Position.",
    "Heroic Sacrifice": "Cost and resolution: tribute a Samurai you control, then destroy the first face-up opponent monster found by the simplified targeting pass.",
    "Final Flourish": "Chain timing simplification: when a destroy effect would remove your Samurai, emit a negate_destroy marker for the YGO chain layer.",
    "Splice Bushido": "Resolution simplification: target the first Samurai you control if none is supplied; it gains 1000 ATK until End Phase through temporary state.",
    "Honor-Worn Shaku": "Equip layer: the equipped Samurai gains 300 ATK and is treated as a Tuner while this card remains attached and face-up.",
    "Brothers Yamazaki": "Protection rule: if another Brothers Yamazaki is face-up on your field, battle destruction against this copy is prevented.",
    "Cleaving Reach": "Cost and resolution: send your first Equip Spell to the GY, then destroy the first face-up opponent monster found by the targeting pass.",
    "Reciprocate": "Resolution simplification: target a Samurai you control, give it 1000 ATK, and mark it battle_indestructible_eot for the rest of the turn.",
    "Otherworldly Journey": "Recursion rule: when this card is destroyed, it returns itself to your hand instead of staying in the GY.",
    "The Wandering Heir": "Summon trigger: when Normal Summoned, Special Summon the first Samurai in your GY in face-up Defense Position if you have an open monster zone.",
    "Bushido Honor": "Battle trick: when a Samurai declares an attack, target that attacker and give it 1000 ATK and DEF until End Phase.",
    "General Fumiko": "Summon trigger: when Normal Summoned, Special Summon the first Level 4 or lower Samurai from your hand into an open monster zone.",
}

for _pass3_card in list(globals().values()):
    _pass3_note = _PASS3_TEXT_APPENDIX.get(getattr(_pass3_card, "name", None))
    if _pass3_note and _pass3_note not in (_pass3_card.text or ""):
        _pass3_card.text = f"{_pass3_card.text} {_pass3_note}"


# =============================================================================
# Set registry
# =============================================================================

BEYOND_KAMIGAWA_SAMURAI = {card.name: card for card in [
    # Monsters
    ISAMARU_HOUND_OF_KONDA, DEVOTED_RETAINER, KITSUNE_DIVINER, EIGANJO_FREE_RIDER,
    EIGHT_AND_A_HALF_TAILS, GENERAL_FUMIKO, KONDAS_BANNER_BEARER,
    HAND_OF_HONOR, HAND_OF_CRUELTY, MOTHRIDER_SAMURAI, BROTHERS_YAMAZAKI,
    RONIN_HOUNDMASTER, KONDAS_HATAMOTO, IMPERIAL_RECOVERY_UNIT, MUKOTAI_AMBUSHER,
    ASARI_CAPTAIN, KIRA_GREAT_GLASS_SPINNER, SAI_OF_THE_SHINOBI,
    INARI_ASCENDANT_FOXGUARD, HEIKO_YAMAZAKI, LIGHT_PAWS_EMPERORS_VOICE,
    THE_WANDERING_HEIR, OTHERWORLDLY_JOURNEY, KONDA_LORD_OF_EIGANJO,
    SOKENZAN_RENEGADE,
    # Spells
    PATH_OF_BRAVERY, SPLICE_BUSHIDO, IMPERIAL_EDICT, EIGANJO_CASTLE,
    SWORD_OF_LIGHT_AND_SHADOW, RECIPROCATE, HONOR_WORN_SHAKU, CLEAVING_REACH,
    GLISTENING_KATANA, IMPERIAL_MOBILIZATION, BUSHIDO_DRILL, THE_WANDERING_DECREE,
    # Traps
    BUSHIDO_HONOR, FINAL_FLOURISH, STAND_TOGETHER, HEROIC_SACRIFICE,
    SHROUD_OF_THE_ETERNAL, KITSUNE_TSUKI,
    # Extra Deck
    THE_WANDERING_EMPEROR, KONDAS_APEX_DRAGON, SAHEELIS_IMPERIAL_LATTICE,
    OTAWARA_IMPERIAL_STRONGHOLD, STORM_OF_SAITO,
]}


# =============================================================================
# Pre-built deck
# =============================================================================

def make_samurai_deck() -> tuple[list, list]:
    """Eiganjo Samurai — 40 main + 5 extra.

    Tuned 2026-05-02: Bushido-lord stack reduced from 7 → 5 (Hand of Honor
    3→2, Konda's Banner-Bearer 2→1) so Bushido pumps don't compound past
    +600 ATK on a typical board. Two Sokenzan Renegade vanillas added in
    their place — keeps the deck at 40 with similar early-game tempo but
    less burst-attacking power.
    """
    main = (
        # Monsters (23) — Bushido density reduced
        [ISAMARU_HOUND_OF_KONDA] * 3 +
        [DEVOTED_RETAINER] * 3 +
        [EIGHT_AND_A_HALF_TAILS] * 2 +
        [HAND_OF_HONOR] * 2 +              # was 3
        [HAND_OF_CRUELTY] * 2 +
        [GENERAL_FUMIKO] * 2 +
        [KONDAS_BANNER_BEARER] * 1 +       # was 2
        [SOKENZAN_RENEGADE] * 2 +          # +2 — vanilla 1900 ATK replaces 2 Bushido lords
        [IMPERIAL_RECOVERY_UNIT] * 2 +
        [KONDA_LORD_OF_EIGANJO] * 1 +
        [HEIKO_YAMAZAKI] * 1 +
        [KIRA_GREAT_GLASS_SPINNER] * 1 +
        [THE_WANDERING_HEIR] * 1 +
        # Spells (12)
        [PATH_OF_BRAVERY] * 2 +
        [SPLICE_BUSHIDO] * 2 +
        [EIGANJO_CASTLE] * 2 +
        [SWORD_OF_LIGHT_AND_SHADOW] * 2 +
        [RECIPROCATE] * 1 +
        [IMPERIAL_MOBILIZATION] * 1 +
        [CLEAVING_REACH] * 2 +
        # Traps (5)
        [BUSHIDO_HONOR] * 2 +
        [FINAL_FLOURISH] * 2 +
        [HEROIC_SACRIFICE] * 1
    )
    extra = [
        THE_WANDERING_EMPEROR,
        KONDAS_APEX_DRAGON,
        SAHEELIS_IMPERIAL_LATTICE,
        OTAWARA_IMPERIAL_STRONGHOLD,
        STORM_OF_SAITO,
    ]
    return (main, extra)


__all__ = ["BEYOND_KAMIGAWA_SAMURAI", "make_samurai_deck"]
