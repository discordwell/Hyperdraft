"""
Beyond Kamigawa — Spirit Dragons of the Five Nights archetype.

YGO mechanic: Soulshift recursion (when destroyed, Special Summon 1 lower-Level
Spirit from your GY) plus a 5-attribute Spirit Dragon cycle (Yosei / Kokusho /
Jugan / Keiga / Ryusei) culminating in O-Kagachi (DIVINE Fusion).

Design pillar: Champions/Saviors of Kamigawa's iconic Spirit Dragon cycle —
each preserves its MTG-original death trigger.

All cards in this archetype carry "Spirit" in their ``subtypes`` set so the
archetype-membership helpers in ``_archetype_helpers.py`` can find them.
The five Spirit Dragons additionally carry "Dragon" as their Type subtype.
"""

from src.engine.game import make_ygo_monster, make_ygo_spell, make_ygo_trap
from src.engine.types import (
    Event, EventType, ZoneType, CardType,
    Interceptor, InterceptorAction, InterceptorPriority, InterceptorResult,
    new_id,
)
from src.engine.yugioh_helpers import (
    make_ygo_summon_trigger, make_ygo_destroy_trigger,
    make_ygo_continuous_effect, make_ygo_ignition_effect,
    revive_from_graveyard, destroy_spell_trap, destroy_all_monsters,
)
from ._archetype_helpers import (
    has_subtype, count_on_field, find_in_graveyard,
    make_archetype_lord, make_soulshift,
)


# =============================================================================
# Internal helpers — Spirit-specific predicates and ops
# =============================================================================

def _is_spirit(obj) -> bool:
    return obj is not None and obj.card_def is not None and \
        "Spirit" in (obj.card_def.characteristics.subtypes or set())


def _is_spirit_dragon(obj) -> bool:
    if not _is_spirit(obj):
        return False
    return "Dragon" in (obj.card_def.characteristics.subtypes or set())


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


def _banish_from_gy(state, controller: str, card_id: str) -> bool:
    """Remove ``card_id`` from controller's GY into the banished pile if present."""
    gy = state.zones.get(f"graveyard_{controller}")
    if not gy or card_id not in gy.objects:
        return False
    gy.objects.remove(card_id)
    banish = state.zones.get(f"banished_{controller}")
    if banish is not None:
        banish.objects.append(card_id)
    obj = state.objects.get(card_id)
    if obj:
        obj.zone = ZoneType.EXILE if hasattr(ZoneType, 'EXILE') else ZoneType.GRAVEYARD
    return True


def _send_to_gy_from_hand(state, controller: str, card_id: str) -> list[Event]:
    """Discard ``card_id`` from controller's hand."""
    obj = state.objects.get(card_id)
    if not obj:
        return []
    hand = state.zones.get(f"hand_{controller}")
    if hand and card_id in hand.objects:
        hand.objects.remove(card_id)
    gy = state.zones.get(f"graveyard_{controller}")
    if gy is not None:
        gy.objects.append(card_id)
    obj.zone = ZoneType.GRAVEYARD
    obj.state.face_down = False
    return [Event(type=EventType.YGO_SEND_TO_GY,
                  payload={'card_id': card_id, 'reason': 'discard'})]


def _destroy_face_up_opponent_monsters(state, controller: str,
                                       *, except_subtype: str = None) -> list[Event]:
    """Destroy every face-up monster opponent controls.

    If ``except_subtype`` is set, monsters with that subtype are skipped
    (used for Ryusei "skip Wing Beast fliers" flavor).
    """
    events: list[Event] = []
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
            if not obj or obj.state.face_down:
                continue
            if except_subtype is not None and \
               obj.card_def is not None and \
               except_subtype in (obj.card_def.characteristics.subtypes or set()):
                continue
            zone.objects[i] = None
            gy = state.zones.get(f"graveyard_{obj.owner}")
            if gy is not None:
                gy.objects.append(oid)
            obj.zone = ZoneType.GRAVEYARD
            obj.state.ygo_position = None
            obj.state.face_down = False
            events.append(Event(type=EventType.YGO_DESTROY,
                                payload={'card_id': oid, 'card_name': obj.name}))
    return events


def _opponent_id(state, controller: str) -> str | None:
    for pid in state.players:
        if pid != controller:
            return pid
    return None


def _draw_n(state, controller: str, n: int) -> list[Event]:
    library = state.zones.get(f"library_{controller}")
    hand = state.zones.get(f"hand_{controller}")
    if not library or not hand:
        return []
    events: list[Event] = []
    for _ in range(min(n, len(library.objects))):
        cid = library.objects.pop(0)
        hand.objects.append(cid)
        obj = state.objects.get(cid)
        if obj:
            obj.zone = ZoneType.HAND
        events.append(Event(type=EventType.YGO_DRAW,
                            payload={'player': controller, 'count': 1}))
    return events


def _ss_from_hand(state, controller: str, card_id: str,
                  *, summon_type: str = 'effect',
                  position: str = 'face_up_atk') -> list[Event]:
    """Special Summon ``card_id`` from controller's hand."""
    obj = state.objects.get(card_id)
    if not obj:
        return []
    hand = state.zones.get(f"hand_{controller}")
    zone = state.zones.get(f"monster_zone_{controller}")
    if not hand or not zone or card_id not in hand.objects:
        return []
    slot = None
    for i in range(5):
        if i >= len(zone.objects) or zone.objects[i] is None:
            slot = i
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
    obj.state.face_down = (position == 'face_down_def')
    return [Event(type=EventType.YGO_SPECIAL_SUMMON,
                  payload={'player': controller, 'card_id': card_id,
                           'card_name': obj.name, 'summon_type': summon_type})]


def _ss_from_extra(state, controller: str, card_id: str,
                   *, summon_type: str = 'fusion',
                   position: str = 'face_up_atk') -> list[Event]:
    """Special Summon ``card_id`` from controller's extra deck."""
    obj = state.objects.get(card_id)
    if not obj:
        return []
    extra = state.zones.get(f"extra_deck_{controller}")
    zone = state.zones.get(f"monster_zone_{controller}")
    if not zone:
        return []
    if extra and card_id in extra.objects:
        extra.objects.remove(card_id)
    slot = None
    for i in range(5):
        if i >= len(zone.objects) or zone.objects[i] is None:
            slot = i
            break
    if slot is None:
        return []
    while len(zone.objects) <= slot:
        zone.objects.append(None)
    zone.objects[slot] = card_id
    obj.zone = ZoneType.MONSTER_ZONE
    obj.controller = controller
    obj.state.ygo_position = position
    obj.state.face_down = False
    return [Event(type=EventType.YGO_SPECIAL_SUMMON,
                  payload={'player': controller, 'card_id': card_id,
                           'card_name': obj.name, 'summon_type': summon_type})]


def _take_control(state, target_id: str, new_controller: str,
                  *, duration: str = 'end_of_turn') -> list[Event]:
    """Move ``target_id`` to ``new_controller``'s monster zone (Keiga's effect)."""
    obj = state.objects.get(target_id)
    if not obj:
        return []
    # Remove from current zone
    old_zone = state.zones.get(f"monster_zone_{obj.controller}")
    if old_zone:
        for i, oid in enumerate(old_zone.objects):
            if oid == target_id:
                old_zone.objects[i] = None
                break
    # Place in new controller's zone
    new_zone = state.zones.get(f"monster_zone_{new_controller}")
    if not new_zone:
        return []
    slot = None
    for i in range(5):
        if i >= len(new_zone.objects) or new_zone.objects[i] is None:
            slot = i
            break
    if slot is None:
        # No room — fall back to leaving it where it is
        if old_zone:
            for i in range(5):
                if i >= len(old_zone.objects) or old_zone.objects[i] is None:
                    while len(old_zone.objects) <= i:
                        old_zone.objects.append(None)
                    old_zone.objects[i] = target_id
                    break
        return []
    while len(new_zone.objects) <= slot:
        new_zone.objects.append(None)
    new_zone.objects[slot] = target_id
    obj.controller = new_controller
    obj.state.ygo_position = 'face_up_atk'
    obj.state.face_down = False
    # Track expiry for cleanup at end-of-turn (engine reads obj.state.control_revert_at)
    obj.state.control_revert_at = duration
    return [Event(type=EventType.YGO_SPECIAL_SUMMON,
                  payload={'player': new_controller, 'card_id': target_id,
                           'card_name': obj.name, 'summon_type': 'control_grab'})]


# =============================================================================
# The 5-attribute Spirit Dragon cycle — death triggers
# =============================================================================

def _yosei_setup(obj, state):
    """LIGHT. On destruction: target a face-up opponent monster — it cannot attack
    and skip opponent's next Standby Phase. Also Soulshift 9."""
    def effect_fn(o, state):
        events: list[Event] = []
        opp = _opponent_id(state, o.controller)
        if opp is not None:
            zone = state.zones.get(f"monster_zone_{opp}")
            if zone:
                for oid in zone.objects:
                    if not oid:
                        continue
                    target = state.objects.get(oid)
                    if target and not target.state.face_down:
                        target.state.cannot_attack_eot = True
                        break
            # Skip the opponent's next Standby Phase via state flag
            opp_player = state.players.get(opp)
            if opp_player is not None:
                cur = getattr(opp_player, 'skip_standby_phases', 0) or 0
                opp_player.skip_standby_phases = cur + 1
        # Soulshift: revive a lower-level Spirit
        target_id = find_in_graveyard(state, o.controller, "Spirit", max_level=8)
        if target_id and target_id != o.id:
            events.extend(revive_from_graveyard(state, o.controller, target_id))
        return events
    return [make_ygo_destroy_trigger(obj, effect_fn)]


def _kokusho_setup(obj, state):
    """DARK. On destruction: opponent loses 1500 LP, you gain 1500 LP. Soulshift 9."""
    def effect_fn(o, state):
        events: list[Event] = []
        opp = _opponent_id(state, o.controller)
        if opp is not None:
            opp_player = state.players.get(opp)
            if opp_player is not None:
                opp_player.lp = max(0, opp_player.lp - 1500)
                events.append(Event(type=EventType.YGO_LP_CHANGE,
                                    payload={'player': opp, 'amount': -1500,
                                             'source': 'Kokusho, the Evening Star'}))
        you = state.players.get(o.controller)
        if you is not None:
            you.lp += 1500
            events.append(Event(type=EventType.YGO_LP_CHANGE,
                                payload={'player': o.controller, 'amount': 1500,
                                         'source': 'Kokusho, the Evening Star'}))
        target_id = find_in_graveyard(state, o.controller, "Spirit", max_level=8)
        if target_id and target_id != o.id:
            events.extend(revive_from_graveyard(state, o.controller, target_id))
        return events
    return [make_ygo_destroy_trigger(obj, effect_fn)]


def _jugan_setup(obj, state):
    """EARTH. On destruction: draw 3 cards. Soulshift 9."""
    def effect_fn(o, state):
        events = _draw_n(state, o.controller, 3)
        target_id = find_in_graveyard(state, o.controller, "Spirit", max_level=8)
        if target_id and target_id != o.id:
            events.extend(revive_from_graveyard(state, o.controller, target_id))
        return events
    return [make_ygo_destroy_trigger(obj, effect_fn)]


def _keiga_setup(obj, state):
    """WATER. On destruction: take control of 1 opponent monster until End Phase. Soulshift 9."""
    def effect_fn(o, state):
        events: list[Event] = []
        opp = _opponent_id(state, o.controller)
        if opp is not None:
            zone = state.zones.get(f"monster_zone_{opp}")
            if zone:
                for oid in zone.objects:
                    if not oid:
                        continue
                    target = state.objects.get(oid)
                    if target and not target.state.face_down:
                        events.extend(_take_control(state, oid, o.controller))
                        break
        target_id = find_in_graveyard(state, o.controller, "Spirit", max_level=8)
        if target_id and target_id != o.id:
            events.extend(revive_from_graveyard(state, o.controller, target_id))
        return events
    return [make_ygo_destroy_trigger(obj, effect_fn)]


def _ryusei_setup(obj, state):
    """FIRE. On destruction: deal 700 damage to all face-up opponent monsters
    (skip Wing Beasts as flavor "fliers"). Soulshift 9."""
    def effect_fn(o, state):
        events: list[Event] = []
        opp = _opponent_id(state, o.controller)
        if opp is not None:
            zone = state.zones.get(f"monster_zone_{opp}")
            if zone:
                for oid in list(zone.objects):
                    if not oid:
                        continue
                    target = state.objects.get(oid)
                    if not target or target.state.face_down or not target.card_def:
                        continue
                    subs = target.card_def.characteristics.subtypes or set()
                    if "Wing Beast" in subs:
                        continue  # fliers dodge the rain of stars
                    # 700 damage is applied to the monster — drop its effective DEF/ATK
                    # by reducing it; if it falls to 0 ATK/DEF, destroy it.
                    cur_atk = getattr(target.card_def, 'atk', 0) or 0
                    if cur_atk <= 700:
                        # destroy outright
                        for i, mid in enumerate(zone.objects):
                            if mid == oid:
                                zone.objects[i] = None
                                break
                        gy = state.zones.get(f"graveyard_{target.owner}")
                        if gy is not None:
                            gy.objects.append(oid)
                        target.zone = ZoneType.GRAVEYARD
                        target.state.ygo_position = None
                        events.append(Event(type=EventType.YGO_DESTROY,
                                            payload={'card_id': oid,
                                                     'card_name': target.name,
                                                     'reason': 'ryusei_damage'}))
                    else:
                        target.state.atk_bonus_eot = \
                            getattr(target.state, 'atk_bonus_eot', 0) - 700
        target_id = find_in_graveyard(state, o.controller, "Spirit", max_level=8)
        if target_id and target_id != o.id:
            events.extend(revive_from_graveyard(state, o.controller, target_id))
        return events
    return [make_ygo_destroy_trigger(obj, effect_fn)]


# =============================================================================
# Effect monsters — supporting Spirits
# =============================================================================

def _atsushi_setup(obj, state):
    """When destroyed: banish 1 card the opponent controls (FIRE Lv 7 toolbox).
    On destruction: opponent banishes the top card of their deck."""
    def effect_fn(o, state):
        events: list[Event] = []
        opp = _opponent_id(state, o.controller)
        if opp is None:
            return events
        # Banish opponent's top deck card as a flavor "exile"
        lib = state.zones.get(f"library_{opp}")
        if lib and lib.objects:
            cid = lib.objects.pop(0)
            banish = state.zones.get(f"banished_{opp}")
            if banish is not None:
                banish.objects.append(cid)
            cobj = state.objects.get(cid)
            if cobj:
                cobj.zone = ZoneType.EXILE if hasattr(ZoneType, 'EXILE') else ZoneType.GRAVEYARD
        target_id = find_in_graveyard(state, o.controller, "Spirit", max_level=6)
        if target_id and target_id != o.id:
            events.extend(revive_from_graveyard(state, o.controller, target_id))
        return events
    return [make_ygo_destroy_trigger(obj, effect_fn)]


def _hidetsugu_setup(obj, state):
    """When Synchro Summoned: destroy all face-up monsters opponent controls
    AND inflict 800 damage per monster destroyed."""
    def effect_fn(o, state):
        destroyed = _destroy_face_up_opponent_monsters(state, o.controller)
        events: list[Event] = list(destroyed)
        damage = 800 * len(destroyed)
        if damage > 0:
            opp = _opponent_id(state, o.controller)
            if opp is not None:
                opp_player = state.players.get(opp)
                if opp_player is not None:
                    opp_player.lp = max(0, opp_player.lp - damage)
                    events.append(Event(type=EventType.YGO_LP_CHANGE,
                                        payload={'player': opp, 'amount': -damage,
                                                 'source': 'Hidetsugu, Devouring Chaos'}))
        return events
    return [make_ygo_summon_trigger(obj, effect_fn)]


def _iname_death_setup(obj, state):
    """When destroyed: search 1 'Spirit' from your Deck and send it to GY."""
    def effect_fn(o, state):
        library = state.zones.get(f"library_{o.controller}")
        gy = state.zones.get(f"graveyard_{o.controller}")
        if not library or not gy:
            return []
        for cid in list(library.objects):
            cobj = state.objects.get(cid)
            if cobj and _is_spirit(cobj) and cid != o.id:
                library.objects.remove(cid)
                gy.objects.append(cid)
                cobj.zone = ZoneType.GRAVEYARD
                return [Event(type=EventType.YGO_SEND_TO_GY,
                              payload={'card_id': cid, 'card_name': cobj.name,
                                       'reason': 'iname_death'})]
        return []
    return [make_ygo_destroy_trigger(obj, effect_fn)]


def _iname_life_setup(obj, state):
    """When Normal Summoned: SS 1 'Spirit' from your GY in face-up DEF."""
    def effect_fn(o, state):
        target = find_in_graveyard(state, o.controller, "Spirit")
        if not target:
            return []
        ev = revive_from_graveyard(state, o.controller, target)
        tobj = state.objects.get(target)
        if tobj:
            tobj.state.ygo_position = 'face_up_def'
        return ev
    return [make_ygo_summon_trigger(obj, effect_fn)]


def _hana_kami_setup(obj, state):
    """When destroyed: add 1 'Spirit' Spell from your GY to your hand."""
    def effect_fn(o, state):
        gy = state.zones.get(f"graveyard_{o.controller}")
        if not gy:
            return []
        for cid in list(gy.objects):
            cobj = state.objects.get(cid)
            if not cobj or not cobj.card_def:
                continue
            if CardType.YGO_SPELL not in cobj.card_def.characteristics.types:
                continue
            # Recover any Spirit-themed Spell (we tag them via subtypes too)
            return _move_to_hand(state, o.controller, cid)
        return []
    return [make_ygo_destroy_trigger(obj, effect_fn)]


def _kami_of_ancient_law_setup(obj, state):
    """When Normal Summoned: target 1 Spell/Trap opponent controls and destroy it."""
    def effect_fn(o, state):
        opp = _opponent_id(state, o.controller)
        if opp is None:
            return []
        st_zone = state.zones.get(f"spell_trap_zone_{opp}")
        if not st_zone:
            return []
        for oid in st_zone.objects:
            if not oid:
                continue
            return destroy_spell_trap(state, oid)
        return []
    return [make_ygo_summon_trigger(obj, effect_fn)]


def _kami_of_false_hope_setup(obj, state):
    """During the damage step in which this card is destroyed by battle:
    your LP cannot go below 1 until the end of your next Standby Phase."""
    interceptors = []
    def effect_fn(o, state):
        you = state.players.get(o.controller)
        if you is not None:
            you.lp_floor_until = 'next_standby'
        return []
    interceptors.append(make_ygo_destroy_trigger(obj, effect_fn))
    return interceptors


def _kami_of_hopeful_strength_setup(obj, state):
    """When this card is Normal Summoned: SS 1 Lv 3 or lower 'Spirit' from your hand."""
    def effect_fn(o, state):
        hand = state.zones.get(f"hand_{o.controller}")
        if not hand:
            return []
        for cid in list(hand.objects):
            cobj = state.objects.get(cid)
            if not cobj or not _is_spirit(cobj):
                continue
            lvl = getattr(cobj.card_def, 'level', 99) or 99
            if lvl > 3:
                continue
            return _ss_from_hand(state, o.controller, cid, summon_type='hopeful_strength')
        return []
    return [make_ygo_summon_trigger(obj, effect_fn)]


def _petalmane_baku_setup(obj, state):
    """When Normal Summoned: search 1 'Spirit' Lv 4 or lower from your Deck."""
    def effect_fn(o, state):
        return _search_library(
            state, o.controller,
            lambda c: _is_spirit(c) and c.id != o.id and
                      (getattr(c.card_def, 'level', 99) or 99) <= 4,
        )
    return [make_ygo_summon_trigger(obj, effect_fn)]


def _hikari_twilight_setup(obj, state):
    """While you control another 'Spirit', this card cannot be destroyed by card effects.

    The original card text said 'cannot be targeted by opponent's effects' but
    the engine has no targeting event yet, so we approximate with a non-battle
    destroy-prevention. Effective protection is similar in practice.
    """
    def modifier_fn(event, state):
        if event.type != EventType.YGO_DESTROY:
            return InterceptorResult(action=InterceptorAction.PASS)
        if event.payload.get('card_id') != obj.id:
            return InterceptorResult(action=InterceptorAction.PASS)
        if event.payload.get('reason') == 'battle':
            return InterceptorResult(action=InterceptorAction.PASS)
        if count_on_field(state, obj.controller, "Spirit", exclude_id=obj.id) <= 0:
            return InterceptorResult(action=InterceptorAction.PASS)
        return InterceptorResult(action=InterceptorAction.PREVENT)
    def _filter(event, state):
        return event.type == EventType.YGO_DESTROY
    return [Interceptor(id=new_id(), source=obj.id, controller=obj.controller,
                        priority=InterceptorPriority.PREVENT, filter=_filter,
                        handler=modifier_fn, duration='until_leaves')]


def _yukora_setup(obj, state):
    """When Normal Summoned: opponent discards 1 random card from their hand."""
    def effect_fn(o, state):
        opp = _opponent_id(state, o.controller)
        if opp is None:
            return []
        hand = state.zones.get(f"hand_{opp}")
        if not hand or not hand.objects:
            return []
        cid = hand.objects[0]  # first card stands in for "random"
        return _send_to_gy_from_hand(state, opp, cid)
    return [make_ygo_summon_trigger(obj, effect_fn)]


def _daimyos_steed_setup(obj, state):
    """During the End Phase, if you control no other 'Spirit': lose 500 LP.
    But while you control another 'Spirit': all 'Spirit' you control gain 200 ATK."""
    def modifier_fn(event, state):
        if event.payload.get('object_id') != obj.id:
            return InterceptorResult(action=InterceptorAction.PASS)
        n = count_on_field(state, obj.controller, "Spirit", exclude_id=obj.id)
        if n <= 0:
            return InterceptorResult(action=InterceptorAction.PASS)
        if event.type == EventType.QUERY_POWER:
            event.payload['value'] = event.payload.get('value', 0) + 200 * n
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=event)
    return [make_ygo_continuous_effect(obj, modifier_fn)]


# =============================================================================
# Card definitions — Monsters
# =============================================================================

# --- The 5 Spirit Dragons (each Lv 9, ~3500/3000 unless noted) ---

YOSEI_THE_MORNING_STAR = make_ygo_monster(
    "Yosei, the Morning Star", atk=3500, def_val=3000, level=9,
    attribute="LIGHT", ygo_monster_type="Effect",
    subtypes={"Dragon", "Spirit"},
    text="When destroyed: target 1 face-up monster opponent controls — it cannot attack, "
         "and your opponent skips their next Standby Phase. Soulshift 9: SS 1 'Spirit' "
         "of lower Level from your GY.",
    setup_interceptors=_yosei_setup,
)

KOKUSHO_THE_EVENING_STAR = make_ygo_monster(
    "Kokusho, the Evening Star", atk=3500, def_val=3000, level=9,
    attribute="DARK", ygo_monster_type="Effect",
    subtypes={"Dragon", "Spirit"},
    text="When destroyed: opponent loses 1500 LP, you gain 1500 LP. "
         "Soulshift 9: SS 1 'Spirit' of lower Level from your GY.",
    setup_interceptors=_kokusho_setup,
)

JUGAN_THE_RISING_STAR = make_ygo_monster(
    "Jugan, the Rising Star", atk=3300, def_val=3300, level=9,
    attribute="EARTH", ygo_monster_type="Effect",
    subtypes={"Dragon", "Spirit"},
    text="When destroyed: draw 3 cards. "
         "Soulshift 9: SS 1 'Spirit' of lower Level from your GY.",
    setup_interceptors=_jugan_setup,
)

KEIGA_THE_TIDE_STAR = make_ygo_monster(
    "Keiga, the Tide Star", atk=3500, def_val=3000, level=9,
    attribute="WATER", ygo_monster_type="Effect",
    subtypes={"Dragon", "Spirit"},
    text="When destroyed: take control of 1 face-up monster opponent controls until "
         "the End Phase. Soulshift 9: SS 1 'Spirit' of lower Level from your GY.",
    setup_interceptors=_keiga_setup,
)

RYUSEI_THE_FALLING_STAR = make_ygo_monster(
    "Ryusei, the Falling Star", atk=3000, def_val=3500, level=9,
    attribute="FIRE", ygo_monster_type="Effect",
    subtypes={"Dragon", "Spirit"},
    text="When destroyed: deal 700 damage to all face-up monsters opponent controls "
         "(except Wing Beasts). Soulshift 9: SS 1 'Spirit' of lower Level from your GY.",
    setup_interceptors=_ryusei_setup,
)


# --- Other Spirits (low/mid level supporting cast) ---

ATSUSHI_THE_BLAZING_SKY = make_ygo_monster(
    "Atsushi, the Blazing Sky", atk=2500, def_val=2200, level=7,
    attribute="FIRE", ygo_monster_type="Effect",
    subtypes={"Dragon", "Spirit"},
    text="When destroyed: opponent banishes the top card of their Deck. "
         "Soulshift 7: SS 1 'Spirit' of lower Level from your GY.",
    setup_interceptors=_atsushi_setup,
)

INAME_DEATH_ASPECT = make_ygo_monster(
    "Iname, Death Aspect", atk=400, def_val=400, level=1,
    attribute="DARK", ygo_monster_type="Effect",
    subtypes={"Spellcaster", "Spirit"},
    text="When destroyed: send 1 'Spirit' from your Deck to your GY.",
    setup_interceptors=_iname_death_setup,
)

INAME_LIFE_ASPECT = make_ygo_monster(
    "Iname, Life Aspect", atk=400, def_val=400, level=1,
    attribute="LIGHT", ygo_monster_type="Effect",
    subtypes={"Spellcaster", "Spirit"},
    text="When Normal Summoned: SS 1 'Spirit' from your GY in face-up Defense Position.",
    setup_interceptors=_iname_life_setup,
)

HANA_KAMI = make_ygo_monster(
    "Hana Kami", atk=600, def_val=600, level=2,
    attribute="EARTH", ygo_monster_type="Effect",
    subtypes={"Plant", "Spirit"},
    text="When destroyed: add 1 Spell from your GY to your hand.",
    setup_interceptors=_hana_kami_setup,
)

KAMI_OF_ANCIENT_LAW = make_ygo_monster(
    "Kami of Ancient Law", atk=1500, def_val=1300, level=4,
    attribute="LIGHT", ygo_monster_type="Effect",
    subtypes={"Spellcaster", "Spirit"},
    text="When Normal Summoned: target 1 Spell/Trap your opponent controls and destroy it.",
    setup_interceptors=_kami_of_ancient_law_setup,
)

KAMI_OF_FALSE_HOPE = make_ygo_monster(
    "Kami of False Hope", atk=200, def_val=200, level=1,
    attribute="LIGHT", ygo_monster_type="Effect",
    subtypes={"Spirit"},
    text="When this card is destroyed: your LP cannot drop below 1 until the end of "
         "your next Standby Phase.",
    setup_interceptors=_kami_of_false_hope_setup,
)

KAMI_OF_HOPEFUL_STRENGTH = make_ygo_monster(
    "Kami of Hopeful Strength", atk=1500, def_val=1500, level=4,
    attribute="EARTH", ygo_monster_type="Effect",
    subtypes={"Beast", "Spirit"},
    text="When Normal Summoned: SS 1 Lv 3 or lower 'Spirit' from your hand.",
    setup_interceptors=_kami_of_hopeful_strength_setup,
)

PETALMANE_BAKU = make_ygo_monster(
    "Petalmane Baku", atk=1100, def_val=900, level=3,
    attribute="EARTH", ygo_monster_type="Effect",
    subtypes={"Beast", "Spirit"},
    text="When Normal Summoned: search 1 Lv 4 or lower 'Spirit' from your Deck.",
    setup_interceptors=_petalmane_baku_setup,
)

HIKARI_TWILIGHT_GUARDIAN = make_ygo_monster(
    "Hikari, Twilight Guardian", atk=1700, def_val=1700, level=4,
    attribute="LIGHT", ygo_monster_type="Effect",
    subtypes={"Warrior", "Spirit"},
    text="While you control another 'Spirit': this card cannot be targeted by your "
         "opponent's card effects.",
    setup_interceptors=_hikari_twilight_setup,
)

YUKORA_THE_PRISONER = make_ygo_monster(
    "Yukora, the Prisoner", atk=2000, def_val=900, level=4,
    attribute="DARK", ygo_monster_type="Effect",
    subtypes={"Demon", "Spirit"},
    text="When Normal Summoned: opponent discards 1 card.",
    setup_interceptors=_yukora_setup,
)

DAIMYOS_SPIRIT_STEED = make_ygo_monster(
    "Daimyo's Spirit Steed", atk=2300, def_val=1500, level=5,
    attribute="WIND", ygo_monster_type="Effect",
    subtypes={"Beast", "Spirit"},
    text="While you control another 'Spirit': all 'Spirit' you control gain 200 ATK "
         "per other 'Spirit'.",
    setup_interceptors=_daimyos_steed_setup,
)

# A pure-vanilla low-cost Spirit to round out the summoning pool.
VILLAGE_GUIDE_SPIRIT = make_ygo_monster(
    "Village Guide Spirit", atk=900, def_val=600, level=2,
    attribute="LIGHT", ygo_monster_type="Normal",
    subtypes={"Beast", "Spirit"},
    text="A small Akki spirit that lights the way for travellers in the foothills.",
)

# A WATER tuner so the deck can reach Synchro 8 / 10 plays without leaning on
# the boss dragons themselves.
TIDESHEPHERD_KOI_SPIRIT = make_ygo_monster(
    "Tideshepherd Koi Spirit", atk=1000, def_val=800, level=2,
    attribute="WATER", ygo_monster_type="Effect", is_tuner=True,
    subtypes={"Fish", "Spirit"},
    text="A small WATER tuner. While you control another 'Spirit', this card "
         "can be Special Summoned from your hand by tributing 1 'Spirit'.",
)

# A cheap WIND beater that doubles as a Soulshift target.
KIRIN_OF_THE_FIRST_WIND = make_ygo_monster(
    "Kirin of the First Wind", atk=1600, def_val=1200, level=3,
    attribute="WIND", ygo_monster_type="Effect",
    subtypes={"Beast", "Spirit"},
    text="Soulshift 3: when destroyed, SS 1 'Spirit' of Lv 2 or lower from your GY.",
    setup_interceptors=lambda obj, state: [make_soulshift(obj, max_level=2, archetype="Spirit")],
)


# =============================================================================
# Card definitions — Spells
# =============================================================================

def _reach_through_mists_resolve(event, state):
    """Normal: search 1 'Spirit' from your Deck."""
    controller = event.payload.get('player')
    if not controller:
        return []
    return _search_library(state, controller, _is_spirit)


REACH_THROUGH_MISTS = make_ygo_spell(
    "Reach Through Mists", ygo_spell_type="Normal",
    text="Add 1 'Spirit' monster from your Deck to your hand.",
    resolve=_reach_through_mists_resolve,
)


def _soulshift_brand_setup(obj, state):
    """Continuous: when a 'Spirit' you control is destroyed, search 1 lower-Level 'Spirit'."""
    def effect_fn_for_spirit(destroyed_obj, controller):
        max_level = 99
        if destroyed_obj and destroyed_obj.card_def is not None:
            max_level = (getattr(destroyed_obj.card_def, 'level', None) or 99) - 1
        return _search_library(
            state, controller,
            lambda c: _is_spirit(c) and (getattr(c.card_def, 'level', 99) or 99) <= max_level,
        )
    def _filter(event, state):
        if event.type != EventType.YGO_DESTROY:
            return False
        cid = event.payload.get('card_id')
        if not cid:
            return False
        cobj = state.objects.get(cid)
        return cobj is not None and cobj.controller == obj.controller and _is_spirit(cobj)
    def _handler(event, state):
        cid = event.payload.get('card_id')
        cobj = state.objects.get(cid)
        return InterceptorResult(action=InterceptorAction.REACT,
                                 new_events=effect_fn_for_spirit(cobj, obj.controller))
    return [Interceptor(id=new_id(), source=obj.id, controller=obj.controller,
                        priority=InterceptorPriority.REACT, filter=_filter,
                        handler=_handler, duration='until_leaves')]


SOULSHIFT_BRAND = make_ygo_spell(
    "Soulshift Brand", ygo_spell_type="Continuous",
    text="When a 'Spirit' you control is destroyed: add 1 'Spirit' of lower Level "
         "from your Deck to your hand.",
    setup_interceptors=_soulshift_brand_setup,
)


def _petals_of_insight_resolve(event, state):
    """Normal: look at the top 3 cards of your Deck; add 1 'Spirit' among them to
    your hand, send the rest to GY."""
    controller = event.payload.get('player')
    if not controller:
        return []
    library = state.zones.get(f"library_{controller}")
    hand = state.zones.get(f"hand_{controller}")
    gy = state.zones.get(f"graveyard_{controller}")
    if not library or not hand or not gy:
        return []
    look = []
    for _ in range(min(3, len(library.objects))):
        look.append(library.objects.pop(0))
    if not look:
        return []
    chosen = None
    for cid in look:
        cobj = state.objects.get(cid)
        if cobj and _is_spirit(cobj):
            chosen = cid
            break
    events: list[Event] = []
    if chosen is not None:
        hand.objects.append(chosen)
        cobj = state.objects.get(chosen)
        if cobj:
            cobj.zone = ZoneType.HAND
            events.append(Event(type=EventType.YGO_DRAW,
                                payload={'player': controller, 'card_id': chosen,
                                         'card_name': cobj.name, 'source': 'petals'}))
    for cid in look:
        if cid == chosen:
            continue
        gy.objects.append(cid)
        cobj = state.objects.get(cid)
        if cobj:
            cobj.zone = ZoneType.GRAVEYARD
        events.append(Event(type=EventType.YGO_SEND_TO_GY,
                            payload={'card_id': cid, 'reason': 'petals_mill'}))
    return events


PETALS_OF_INSIGHT = make_ygo_spell(
    "Petals of Insight", ygo_spell_type="Normal",
    text="Look at the top 3 cards of your Deck; add 1 'Spirit' among them to your "
         "hand, send the rest to the GY.",
    resolve=_petals_of_insight_resolve,
)


def _spirit_bond_resolve(event, state):
    """Normal (Polymerization analog): banish materials from field+hand,
    SS 1 Fusion 'Spirit' from the Extra Deck."""
    controller = event.payload.get('player')
    if not controller:
        return []
    extra = state.zones.get(f"extra_deck_{controller}")
    if not extra:
        return []
    # Find a Fusion Spirit in the extra deck
    target_id = None
    for cid in extra.objects:
        cobj = state.objects.get(cid)
        if cobj and cobj.card_def and \
           getattr(cobj.card_def, 'ygo_monster_type', None) == "Fusion" and \
           _is_spirit(cobj):
            target_id = cid
            break
    if not target_id:
        return []
    # Materials: send up to 5 different-Attribute Spirit Dragons from field/hand to GY
    seen_attrs: set[str] = set()
    sent: list[str] = []
    for source_zone_key in (f"monster_zone_{controller}", f"hand_{controller}"):
        zone = state.zones.get(source_zone_key)
        if not zone:
            continue
        for cid in list(zone.objects):
            if not cid:
                continue
            cobj = state.objects.get(cid)
            if not cobj or not _is_spirit_dragon(cobj):
                continue
            attr = getattr(cobj.card_def, 'attribute', None)
            if attr in seen_attrs:
                continue
            seen_attrs.add(attr)
            sent.append(cid)
            # Remove from source
            if isinstance(zone.objects, list) and cid in zone.objects:
                if source_zone_key.startswith('monster_zone'):
                    for i, mid in enumerate(zone.objects):
                        if mid == cid:
                            zone.objects[i] = None
                            break
                else:
                    zone.objects.remove(cid)
            gy = state.zones.get(f"graveyard_{controller}")
            if gy is not None:
                gy.objects.append(cid)
            cobj.zone = ZoneType.GRAVEYARD
            cobj.state.ygo_position = None
            if len(sent) >= 5:
                break
        if len(sent) >= 5:
            break
    if not sent:
        return []
    events: list[Event] = [Event(type=EventType.YGO_SEND_TO_GY,
                                 payload={'card_id': cid, 'reason': 'fusion_material'})
                            for cid in sent]
    events.extend(_ss_from_extra(state, controller, target_id, summon_type='fusion'))
    return events


SPIRIT_BOND = make_ygo_spell(
    "Spirit Bond", ygo_spell_type="Normal",
    text="Send up to 5 'Spirit' monsters with different Attributes from your hand "
         "and/or field to the GY; SS 1 Fusion 'Spirit' from your Extra Deck.",
    resolve=_spirit_bond_resolve,
)


def _charge_of_five_stars_resolve(event, state):
    """Normal: banish 5 different-Attribute 'Spirit' monsters from your GY;
    SS O-Kagachi from your Extra Deck."""
    controller = event.payload.get('player')
    if not controller:
        return []
    gy = state.zones.get(f"graveyard_{controller}")
    extra = state.zones.get(f"extra_deck_{controller}")
    if not gy or not extra:
        return []
    seen_attrs: set[str] = set()
    chosen: list[str] = []
    for cid in list(gy.objects):
        cobj = state.objects.get(cid)
        if not cobj or not _is_spirit(cobj):
            continue
        attr = getattr(cobj.card_def, 'attribute', None)
        if attr in seen_attrs or attr is None:
            continue
        seen_attrs.add(attr)
        chosen.append(cid)
        if len(chosen) >= 5:
            break
    if len(chosen) < 5:
        return []
    # Find O-Kagachi in extra
    okagachi_id = None
    for cid in extra.objects:
        cobj = state.objects.get(cid)
        if cobj and cobj.name == "O-Kagachi, Vengeful Kami":
            okagachi_id = cid
            break
    if not okagachi_id:
        return []
    events: list[Event] = []
    for cid in chosen:
        _banish_from_gy(state, controller, cid)
    events.extend(_ss_from_extra(state, controller, okagachi_id, summon_type='charge'))
    return events


CHARGE_OF_THE_FIVE_STARS = make_ygo_spell(
    "Charge of the Five Stars", ygo_spell_type="Normal",
    text="Banish 5 'Spirit' monsters with different Attributes from your GY; "
         "SS 'O-Kagachi, Vengeful Kami' from your Extra Deck.",
    resolve=_charge_of_five_stars_resolve,
)


def _awakening_hour_resolve(event, state):
    """Quick-Play: 'Spirit' monsters you control cannot be destroyed by battle this turn."""
    controller = event.payload.get('player')
    if not controller:
        return []
    zone = state.zones.get(f"monster_zone_{controller}")
    if not zone:
        return []
    for oid in zone.objects:
        if not oid:
            continue
        obj = state.objects.get(oid)
        if obj and _is_spirit(obj):
            obj.state.battle_indestructible_eot = True
    return []


AWAKENING_HOUR = make_ygo_spell(
    "Awakening Hour", ygo_spell_type="Quick-Play",
    text="'Spirit' monsters you control cannot be destroyed by battle this turn.",
    resolve=_awakening_hour_resolve,
)


def _heart_of_light_setup(obj, state):
    """Field: when a 'Spirit' you control is sent to GY, gain 300 LP."""
    def _filter(event, state):
        if event.type not in (EventType.YGO_SEND_TO_GY, EventType.YGO_DESTROY):
            return False
        cid = event.payload.get('card_id')
        cobj = state.objects.get(cid) if cid else None
        return cobj is not None and cobj.controller == obj.controller and _is_spirit(cobj)
    def _handler(event, state):
        player = state.players.get(obj.controller)
        if player is not None:
            player.lp += 300
            return InterceptorResult(action=InterceptorAction.REACT, new_events=[
                Event(type=EventType.YGO_LP_CHANGE,
                      payload={'player': obj.controller, 'amount': 300,
                               'source': 'Heart of Light'}),
            ])
        return InterceptorResult(action=InterceptorAction.PASS)
    return [Interceptor(id=new_id(), source=obj.id, controller=obj.controller,
                        priority=InterceptorPriority.REACT, filter=_filter,
                        handler=_handler, duration='until_leaves')]


HEART_OF_LIGHT = make_ygo_spell(
    "Heart of Light", ygo_spell_type="Field",
    text="When a 'Spirit' monster you control is sent to the GY: gain 300 LP.",
    setup_interceptors=_heart_of_light_setup,
)


def _hana_sash_setup(obj, state):
    """Equip: equipped 'Spirit' gains 800 ATK; when this card is sent to GY,
    return the equipped monster to its owner's hand."""
    from src.engine.yugioh_helpers import make_ygo_equip_boost
    interceptors = [make_ygo_equip_boost(obj, atk_boost=800, def_boost=0)]
    def effect_fn(o, state):
        target_id = getattr(o.state, 'equipped_to', None)
        if not target_id:
            return []
        target = state.objects.get(target_id)
        if not target:
            return []
        return _move_to_hand(state, target.controller, target_id)
    interceptors.append(make_ygo_destroy_trigger(obj, effect_fn))
    return interceptors


HANA_SASH = make_ygo_spell(
    "Hana Sash", ygo_spell_type="Equip",
    text="Equipped 'Spirit' gains 800 ATK. When this card is sent to the GY: "
         "return the equipped monster to its owner's hand.",
    setup_interceptors=_hana_sash_setup,
)


def _mirror_stone_of_five_suns_setup(obj, state):
    """Continuous: 'Spirit' you control gain +100 ATK for each different
    Attribute among 'Spirit' monsters in your GY."""
    def modifier_fn(event, state):
        target_id = event.payload.get('object_id')
        target = state.objects.get(target_id) if target_id else None
        if not target or target.controller != obj.controller or not _is_spirit(target):
            return InterceptorResult(action=InterceptorAction.PASS)
        gy = state.zones.get(f"graveyard_{obj.controller}")
        if not gy:
            return InterceptorResult(action=InterceptorAction.PASS)
        attrs = set()
        for cid in gy.objects:
            cobj = state.objects.get(cid)
            if cobj and _is_spirit(cobj):
                a = getattr(cobj.card_def, 'attribute', None)
                if a:
                    attrs.add(a)
        if not attrs:
            return InterceptorResult(action=InterceptorAction.PASS)
        if event.type == EventType.QUERY_POWER:
            event.payload['value'] = event.payload.get('value', 0) + 100 * len(attrs)
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=event)
    return [make_ygo_continuous_effect(obj, modifier_fn)]


MIRROR_STONE_OF_FIVE_SUNS = make_ygo_spell(
    "Mirror Stone of Five Suns", ygo_spell_type="Continuous",
    text="'Spirit' monsters you control gain 100 ATK for each different Attribute "
         "among 'Spirit' monsters in your GY.",
    setup_interceptors=_mirror_stone_of_five_suns_setup,
)


# =============================================================================
# Card definitions — Traps
# =============================================================================

def _soulless_ringing_resolve(event, state):
    """Counter: negate destruction by Spell."""
    return [Event(type=EventType.YGO_CHAIN_LINK,
                  payload={'effect': 'negate_destroy', 'reason': 'soulless_ringing',
                           'controller': event.payload.get('player')})]


SOULLESS_RINGING = make_ygo_trap(
    "Soulless Ringing", ygo_trap_type="Counter",
    text="When a Spell would destroy a 'Spirit' you control: negate that effect.",
    resolve=_soulless_ringing_resolve,
)


def _devouring_greed_resolve(event, state):
    """Normal: banish 1 'Spirit' from your GY; SS 1 'Spirit' of lower Level from your GY."""
    controller = event.payload.get('player')
    if not controller:
        return []
    gy = state.zones.get(f"graveyard_{controller}")
    if not gy:
        return []
    pivot_id = None
    pivot_level = 0
    for cid in list(gy.objects):
        cobj = state.objects.get(cid)
        if cobj and _is_spirit(cobj):
            pivot_id = cid
            pivot_level = getattr(cobj.card_def, 'level', 99) or 99
            break
    if not pivot_id:
        return []
    _banish_from_gy(state, controller, pivot_id)
    target_id = find_in_graveyard(state, controller, "Spirit", max_level=max(0, pivot_level - 1))
    if not target_id:
        return []
    return revive_from_graveyard(state, controller, target_id)


DEVOURING_GREED = make_ygo_trap(
    "Devouring Greed", ygo_trap_type="Normal",
    text="Banish 1 'Spirit' from your GY; SS 1 'Spirit' of lower Level from your GY.",
    resolve=_devouring_greed_resolve,
)


def _vow_of_reverence_setup(obj, state):
    """When a 'Spirit' you control is destroyed: SS 1 'Spirit' from your GY."""
    def _filter(event, state):
        if event.type != EventType.YGO_DESTROY:
            return False
        cid = event.payload.get('card_id')
        if not cid:
            return False
        cobj = state.objects.get(cid)
        return cobj is not None and cobj.controller == obj.controller and _is_spirit(cobj)
    def _handler(event, state):
        target = find_in_graveyard(state, obj.controller, "Spirit")
        if not target:
            return InterceptorResult(action=InterceptorAction.PASS)
        return InterceptorResult(action=InterceptorAction.REACT,
                                 new_events=revive_from_graveyard(state, obj.controller, target))
    return [Interceptor(id=new_id(), source=obj.id, controller=obj.controller,
                        priority=InterceptorPriority.REACT, filter=_filter,
                        handler=_handler, duration='until_leaves', uses_remaining=1)]


VOW_OF_REVERENCE = make_ygo_trap(
    "Vow of Reverence", ygo_trap_type="Normal",
    text="When a 'Spirit' you control is destroyed: SS 1 'Spirit' from your GY.",
    setup_interceptors=_vow_of_reverence_setup,
)


def _glistening_path_setup(obj, state):
    """Continuous: when a 'Spirit' you control is destroyed by battle, draw 1."""
    def _filter(event, state):
        if event.type != EventType.YGO_DESTROY:
            return False
        if event.payload.get('reason') != 'battle':
            return False
        cid = event.payload.get('card_id')
        if not cid:
            return False
        cobj = state.objects.get(cid)
        return cobj is not None and cobj.controller == obj.controller and _is_spirit(cobj)
    def _handler(event, state):
        ev = _draw_n(state, obj.controller, 1)
        return InterceptorResult(action=InterceptorAction.REACT, new_events=ev)
    return [Interceptor(id=new_id(), source=obj.id, controller=obj.controller,
                        priority=InterceptorPriority.REACT, filter=_filter,
                        handler=_handler, duration='until_leaves')]


GLISTENING_PATH = make_ygo_trap(
    "Glistening Path", ygo_trap_type="Continuous",
    text="When a 'Spirit' you control is destroyed by battle: draw 1 card.",
    setup_interceptors=_glistening_path_setup,
)


def _trial_of_the_moonless_night_resolve(event, state):
    """Normal: if you control 5 'Spirit' monsters with different Attributes, end opponent's turn."""
    controller = event.payload.get('player')
    if not controller:
        return []
    zone = state.zones.get(f"monster_zone_{controller}")
    if not zone:
        return []
    attrs = set()
    for oid in zone.objects:
        if not oid:
            continue
        cobj = state.objects.get(oid)
        if cobj and _is_spirit(cobj) and cobj.card_def is not None:
            a = getattr(cobj.card_def, 'attribute', None)
            if a:
                attrs.add(a)
    if len(attrs) < 5:
        return []
    # Signal end-of-turn — the engine watches for this flag during phase transitions.
    state.end_turn_requested = True
    return []


TRIAL_OF_THE_MOONLESS_NIGHT = make_ygo_trap(
    "Trial of the Moonless Night", ygo_trap_type="Normal",
    text="If you control 5 'Spirit' monsters with different Attributes: end the current turn.",
    resolve=_trial_of_the_moonless_night_resolve,
)


def _final_word_resolve(event, state):
    """Counter: negate an effect that targets 'O-Kagachi, Vengeful Kami'."""
    return [Event(type=EventType.YGO_CHAIN_LINK,
                  payload={'effect': 'negate_target', 'target_name': 'O-Kagachi, Vengeful Kami',
                           'controller': event.payload.get('player')})]


FINAL_WORD = make_ygo_trap(
    "Final Word", ygo_trap_type="Counter",
    text="Negate 1 effect that targets 'O-Kagachi, Vengeful Kami' you control.",
    resolve=_final_word_resolve,
)


# =============================================================================
# Card definitions — Extra Deck
# =============================================================================

def _okagachi_setup(obj, state):
    """When Fusion Summoned: destroy all face-up monsters. Cannot be destroyed by battle."""
    interceptors: list[Interceptor] = []

    # 1) Destroy all face-up monsters when Fusion Summoned.
    def fusion_summon_fn(o, state):
        return destroy_all_monsters(state)
    def _ss_filter(event, state):
        return (event.type == EventType.YGO_SPECIAL_SUMMON and
                event.payload.get('card_id') == obj.id and
                event.payload.get('summon_type') in ('fusion', 'charge'))
    def _ss_handler(event, state):
        return InterceptorResult(action=InterceptorAction.REACT,
                                 new_events=fusion_summon_fn(obj, state))
    interceptors.append(Interceptor(
        id=new_id(), source=obj.id, controller=obj.controller,
        priority=InterceptorPriority.REACT, filter=_ss_filter,
        handler=_ss_handler, duration='until_leaves',
    ))

    # 2) Cannot be destroyed by battle.
    def battle_proof_fn(event, state):
        if event.payload.get('card_id') != obj.id:
            return InterceptorResult(action=InterceptorAction.PASS)
        if event.payload.get('reason') != 'battle':
            return InterceptorResult(action=InterceptorAction.PASS)
        return InterceptorResult(action=InterceptorAction.PREVENT)
    def _bp_filter(event, state):
        return event.type == EventType.YGO_DESTROY
    interceptors.append(Interceptor(
        id=new_id(), source=obj.id, controller=obj.controller,
        priority=InterceptorPriority.PREVENT, filter=_bp_filter,
        handler=battle_proof_fn, duration='until_leaves',
    ))
    return interceptors


O_KAGACHI_VENGEFUL_KAMI = make_ygo_monster(
    "O-Kagachi, Vengeful Kami", atk=4500, def_val=4500, level=12,
    attribute="DIVINE", ygo_monster_type="Fusion",
    subtypes={"Dragon", "Spirit"},
    text="5 'Spirit Dragon' monsters with different Attributes. When this card is "
         "Fusion Summoned: destroy all face-up monsters. This card cannot be destroyed "
         "by battle.",
    materials="5 'Spirit Dragon' monsters with different Attributes",
    setup_interceptors=_okagachi_setup,
)


HIDETSUGU_DEVOURING_CHAOS = make_ygo_monster(
    "Hidetsugu, Devouring Chaos", atk=3500, def_val=3000, level=10,
    attribute="DARK", ygo_monster_type="Synchro",
    subtypes={"Demon", "Spirit"},
    text="1 Tuner + 1+ non-Tuner 'Spirit' monsters. When Synchro Summoned: destroy "
         "all face-up monsters opponent controls and inflict 800 damage per monster destroyed.",
    materials="1 Tuner + 1+ non-Tuner 'Spirit' monsters",
    setup_interceptors=_hidetsugu_setup,
)


def _pearl_dragon_concord_setup(obj, state):
    """Synchro Lv 8 LIGHT — Soulshift 8, and a static lord (+300 ATK to Spirits)."""
    interceptors = [
        make_archetype_lord(obj, atk_bonus=300, def_bonus=0, archetype="Spirit"),
        make_soulshift(obj, max_level=7, archetype="Spirit"),
    ]
    return interceptors


PEARL_DRAGON_CONCORD = make_ygo_monster(
    "Pearl-Dragon Concord", atk=3000, def_val=2500, level=8,
    attribute="LIGHT", ygo_monster_type="Synchro",
    subtypes={"Dragon", "Spirit"},
    text="1 Tuner + 1+ non-Tuner 'Spirit' monsters. All 'Spirit' you control gain "
         "300 ATK. Soulshift 8: when destroyed, SS 1 'Spirit' of Lv 7 or lower from your GY.",
    materials="1 Tuner + 1+ non-Tuner 'Spirit' monsters",
    setup_interceptors=_pearl_dragon_concord_setup,
)


def _greater_kami_wakening_setup(obj, state):
    """Xyz Rank 4: detach 1 material; SS 1 Lv 4 or lower 'Spirit' from your GY."""
    def effect_fn(o, state):
        if not o.state.overlay_units:
            return []
        detached = o.state.overlay_units.pop(0)
        gy = state.zones.get(f"graveyard_{o.controller}")
        if gy is not None:
            gy.objects.append(detached)
        target = find_in_graveyard(state, o.controller, "Spirit", max_level=4)
        if not target:
            return []
        return revive_from_graveyard(state, o.controller, target)
    return [make_ygo_ignition_effect(obj, effect_fn)]


GREATER_KAMI_WAKENING = make_ygo_monster(
    "Greater Kami Wakening", atk=2400, def_val=2000, level=4,
    attribute="LIGHT", ygo_monster_type="Xyz", rank=4,
    subtypes={"Spellcaster", "Spirit"},
    text="2 Lv 4 monsters. Once per turn: detach 1 material; SS 1 Lv 4 or lower "
         "'Spirit' from your GY.",
    materials="2 Lv 4 monsters",
    setup_interceptors=_greater_kami_wakening_setup,
)


def _spirit_hatch_trill_setup(obj, state):
    """Link 2: while this points to a 'Spirit', that 'Spirit' gains 500 ATK and DEF."""
    return [make_archetype_lord(obj, atk_bonus=500, def_bonus=500, archetype="Spirit")]


SPIRIT_HATCH_TRILL = make_ygo_monster(
    "Spirit-Hatch Trill", atk=1800, def_val=0, level=2,
    attribute="WIND", ygo_monster_type="Link", link_rating=2,
    link_arrows=["bottom_left", "bottom_right"],
    subtypes={"Wing Beast", "Spirit"},
    text="2 'Spirit' monsters. While this card points to a 'Spirit': that 'Spirit' "
         "gains 500 ATK and DEF.",
    materials="2 'Spirit' monsters",
    setup_interceptors=_spirit_hatch_trill_setup,
)


# =============================================================================
# Set registry
# =============================================================================

BEYOND_KAMIGAWA_SPIRIT_DRAGONS = {card.name: card for card in [
    # The 5 Spirit Dragons
    YOSEI_THE_MORNING_STAR, KOKUSHO_THE_EVENING_STAR, JUGAN_THE_RISING_STAR,
    KEIGA_THE_TIDE_STAR, RYUSEI_THE_FALLING_STAR,
    # Other monsters
    ATSUSHI_THE_BLAZING_SKY, INAME_DEATH_ASPECT, INAME_LIFE_ASPECT, HANA_KAMI,
    KAMI_OF_ANCIENT_LAW, KAMI_OF_FALSE_HOPE, KAMI_OF_HOPEFUL_STRENGTH,
    PETALMANE_BAKU, HIKARI_TWILIGHT_GUARDIAN, YUKORA_THE_PRISONER,
    DAIMYOS_SPIRIT_STEED, VILLAGE_GUIDE_SPIRIT, TIDESHEPHERD_KOI_SPIRIT,
    KIRIN_OF_THE_FIRST_WIND,
    # Spells
    REACH_THROUGH_MISTS, SOULSHIFT_BRAND, PETALS_OF_INSIGHT, SPIRIT_BOND,
    CHARGE_OF_THE_FIVE_STARS, AWAKENING_HOUR, HEART_OF_LIGHT, HANA_SASH,
    MIRROR_STONE_OF_FIVE_SUNS,
    # Traps
    SOULLESS_RINGING, DEVOURING_GREED, VOW_OF_REVERENCE, GLISTENING_PATH,
    TRIAL_OF_THE_MOONLESS_NIGHT, FINAL_WORD,
    # Extra Deck
    O_KAGACHI_VENGEFUL_KAMI, HIDETSUGU_DEVOURING_CHAOS, PEARL_DRAGON_CONCORD,
    GREATER_KAMI_WAKENING, SPIRIT_HATCH_TRILL,
]}


# =============================================================================
# Pre-built deck
# =============================================================================

def make_spirit_dragon_deck() -> tuple[list, list]:
    """Spirit Dragons of the Five Nights — 40 main + 5 extra.

    The 5 Spirit Dragons each appear ×1 (sacred bosses); the rest of the deck
    fuels Soulshift recursion with cheap Spirits and search/recovery support.
    """
    main = (
        # The 5 Spirit Dragons (×1 each, 5 cards)
        [YOSEI_THE_MORNING_STAR] * 1 +
        [KOKUSHO_THE_EVENING_STAR] * 1 +
        [JUGAN_THE_RISING_STAR] * 1 +
        [KEIGA_THE_TIDE_STAR] * 1 +
        [RYUSEI_THE_FALLING_STAR] * 1 +
        # Mid/large Spirits (3 cards)
        [ATSUSHI_THE_BLAZING_SKY] * 1 +
        [DAIMYOS_SPIRIT_STEED] * 2 +
        # Lv 4 enablers (9 cards)
        [KAMI_OF_HOPEFUL_STRENGTH] * 3 +
        [KAMI_OF_ANCIENT_LAW] * 2 +
        [HIKARI_TWILIGHT_GUARDIAN] * 2 +
        [YUKORA_THE_PRISONER] * 2 +
        # Low-level recursion (11 cards — incl. WATER tuner + WIND Soulshift body)
        [PETALMANE_BAKU] * 3 +
        [HANA_KAMI] * 2 +
        [INAME_DEATH_ASPECT] * 2 +
        [INAME_LIFE_ASPECT] * 1 +
        [KAMI_OF_FALSE_HOPE] * 1 +
        [TIDESHEPHERD_KOI_SPIRIT] * 1 +
        [KIRIN_OF_THE_FIRST_WIND] * 1 +
        # Spells (8 cards)
        [REACH_THROUGH_MISTS] * 3 +
        [PETALS_OF_INSIGHT] * 1 +
        [SPIRIT_BOND] * 1 +
        [CHARGE_OF_THE_FIVE_STARS] * 1 +
        [AWAKENING_HOUR] * 1 +
        [SOULSHIFT_BRAND] * 1 +
        # Traps (4 cards)
        [VOW_OF_REVERENCE] * 2 +
        [DEVOURING_GREED] * 1 +
        [GLISTENING_PATH] * 1
    )
    extra = [
        O_KAGACHI_VENGEFUL_KAMI,
        HIDETSUGU_DEVOURING_CHAOS,
        PEARL_DRAGON_CONCORD,
        GREATER_KAMI_WAKENING,
        SPIRIT_HATCH_TRILL,
    ]
    return (main, extra)


__all__ = ["BEYOND_KAMIGAWA_SPIRIT_DRAGONS", "make_spirit_dragon_deck"]
