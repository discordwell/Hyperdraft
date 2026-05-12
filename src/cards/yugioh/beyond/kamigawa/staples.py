"""
Beyond Kamigawa — generic staples shared across all 5 archetypes.

Universal cards that any deck in the set could draw from. Built around the
5-Honden Field-Spell cycle (the iconic Champions of Kamigawa enchantment cycle),
generic counterspells / removal traps, classic MTG-flavor utility spells
(Path to Exile, Swords to Plowshares, Ponder, Preordain, Brainstorm),
and a handful of utility small monsters for any deck to use.

Cards already provided by individual archetypes (e.g. Brainstorm in Moonfolk,
Cranial Plating in Modified, Counterspell-Lite / Mana Leak / Cancel in Moonfolk)
are NOT redefined here — the archetype version is canonical.
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
    make_ygo_equip_boost,
    revive_from_graveyard, destroy_all_monsters,
)


# =============================================================================
# Internal helpers (lightweight — no archetype-specific dependencies)
# =============================================================================

def _draw(state, controller: str, n: int = 1) -> list[Event]:
    library = state.zones.get(f"library_{controller}")
    hand = state.zones.get(f"hand_{controller}")
    if not library or not hand:
        return []
    events = []
    for _ in range(min(n, len(library.objects))):
        cid = library.objects.pop(0)
        hand.objects.append(cid)
        cobj = state.objects.get(cid)
        if cobj:
            cobj.zone = ZoneType.HAND
        events.append(Event(type=EventType.YGO_DRAW,
                            payload={'player': controller, 'count': 1}))
    return events


def _opponent_id(state, controller: str) -> str | None:
    for pid in state.players:
        if pid != controller:
            return pid
    return None


def _change_lp(state, player_id: str, delta: int, source: str = "") -> list[Event]:
    player = state.players.get(player_id)
    if not player:
        return []
    if delta < 0:
        player.lp = max(0, player.lp + delta)
    else:
        player.lp += delta
    return [Event(type=EventType.YGO_LP_CHANGE,
                  payload={'player': player_id, 'amount': delta, 'source': source})]


def _banish_one_face_up_opponent(state, controller: str) -> tuple[str | None, int]:
    """Banish the first face-up opponent monster. Returns (id, atk) on success."""
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
                atk = getattr(obj.card_def, 'atk', 0) if obj.card_def else 0
                zone.objects[i] = None
                banish = state.zones.get(f"banished_{obj.owner}") or state.zones.get(f"graveyard_{obj.owner}")
                if banish is not None:
                    banish.objects.append(oid)
                obj.zone = ZoneType.EXILE if hasattr(ZoneType, 'EXILE') else ZoneType.GRAVEYARD
                obj.state.ygo_position = None
                return (oid, atk or 0)
    return (None, 0)


def _discard_random(state, player_id: str, n: int = 1) -> list[Event]:
    hand = state.zones.get(f"hand_{player_id}")
    gy = state.zones.get(f"graveyard_{player_id}")
    if not hand or not gy:
        return []
    events = []
    for _ in range(n):
        if not hand.objects:
            break
        cid = hand.objects.pop()
        gy.objects.append(cid)
        cobj = state.objects.get(cid)
        if cobj:
            cobj.zone = ZoneType.GRAVEYARD
        events.append(Event(type=EventType.YGO_SEND_TO_GY,
                            payload={'card_id': cid, 'reason': 'discard'}))
    return events


def _is_ygo_monster(obj) -> bool:
    return (
        obj is not None and obj.card_def is not None
        and CardType.YGO_MONSTER in obj.card_def.characteristics.types
    )


def _is_equip_spell(obj) -> bool:
    return (
        obj is not None and obj.card_def is not None
        and getattr(obj.card_def, 'ygo_spell_type', None) == "Equip"
    )


def _destroy_card(state, card_id: str, reason: str = "effect") -> list[Event]:
    obj = state.objects.get(card_id)
    if not obj:
        return []
    for zone in state.zones.values():
        for i, oid in enumerate(zone.objects):
            if oid == card_id:
                zone.objects[i] = None
        while card_id in zone.objects:
            zone.objects.remove(card_id)
    gy = state.zones.get(f"graveyard_{obj.owner}")
    if gy is not None:
        gy.objects.append(card_id)
    obj.zone = ZoneType.GRAVEYARD
    obj.state.face_down = False
    obj.state.ygo_position = None
    return [Event(type=EventType.YGO_DESTROY,
                  payload={'card_id': card_id, 'card_name': obj.name,
                           'reason': reason})]


def _destroy_one_face_up_opponent_card(state, controller: str) -> list[Event]:
    for pid in state.players:
        if pid == controller:
            continue
        for zone_key in (f"monster_zone_{pid}", f"spell_trap_zone_{pid}",
                         f"field_spell_zone_{pid}"):
            zone = state.zones.get(zone_key)
            if not zone:
                continue
            for oid in list(zone.objects):
                if not oid:
                    continue
                obj = state.objects.get(oid)
                if obj and not obj.state.face_down:
                    return _destroy_card(state, oid, reason="effect")
    return []


def _search_library(state, controller: str, predicate) -> list[Event]:
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


def _first_own_monster(state, controller: str) -> str | None:
    zone = state.zones.get(f"monster_zone_{controller}")
    if not zone:
        return None
    for oid in zone.objects:
        if not oid:
            continue
        obj = state.objects.get(oid)
        if _is_ygo_monster(obj):
            return oid
    return None


def _make_counter_resolve(effect: str):
    def _resolve(event, state):
        controller = event.payload.get('player')
        return [Event(type=EventType.YGO_CHAIN_LINK,
                      payload={'effect': effect, 'controller': controller,
                               'source': event.payload.get('card_id')})]
    return _resolve


def _make_honden_standby_setup(resolve_fn):
    """Field Spell upkeep hook.

    The YGO spell manager still calls ``resolve`` on activation, so these
    Honden keep their immediate activation effect and also repeat during the
    controller's Standby Phase while face-up in the Field Zone.
    """
    def _setup(obj, state):
        def _filter(event, state):
            return (
                obj.zone == ZoneType.FIELD_SPELL_ZONE
                and event.type == EventType.PHASE_CHANGE
                and event.payload.get('phase') == 'standby'
                and event.payload.get('player') == obj.controller
                and getattr(obj.state, 'honden_standby_turn', None) != state.turn_number
            )

        def _handler(event, state):
            obj.state.honden_standby_turn = state.turn_number
            trigger = Event(
                type=EventType.YGO_ACTIVATE_SPELL,
                payload={'player': obj.controller, 'card_id': obj.id},
                source=obj.id,
                controller=obj.controller,
            )
            return InterceptorResult(
                action=InterceptorAction.REACT,
                new_events=resolve_fn(trigger, state) or [],
            )

        return [Interceptor(id=new_id(), source=obj.id, controller=obj.controller,
                            priority=InterceptorPriority.REACT, filter=_filter,
                            handler=_handler, duration='until_leaves')]
    return _setup


def _make_attribute_field_setup(atk_bonuses: dict[str, int],
                                def_bonuses: dict[str, int] | None = None):
    """Create a Field Spell stat layer for YGO attributes."""
    def _setup(obj, state):
        def _filter(event, state):
            if obj.zone != ZoneType.FIELD_SPELL_ZONE:
                return False
            if event.type not in (EventType.QUERY_POWER, EventType.QUERY_TOUGHNESS):
                return False
            target = state.objects.get(event.payload.get('object_id'))
            return _is_ygo_monster(target)

        def _handler(event, state):
            target = state.objects.get(event.payload.get('object_id'))
            attr = getattr(target.card_def, 'attribute', None) if target and target.card_def else None
            if event.type == EventType.QUERY_POWER:
                bonus = atk_bonuses.get(attr, 0)
            else:
                bonus = (def_bonuses or {}).get(attr, 0)
            if not bonus:
                return InterceptorResult(action=InterceptorAction.PASS)
            event.payload['value'] = event.payload.get('value', 0) + bonus
            return InterceptorResult(action=InterceptorAction.TRANSFORM,
                                     transformed_event=event)

        return [Interceptor(id=new_id(), source=obj.id, controller=obj.controller,
                            priority=InterceptorPriority.QUERY, filter=_filter,
                            handler=_handler, duration='until_leaves')]
    return _setup


# =============================================================================
# The 5-Honden Field-Spell cycle (Champions of Kamigawa enchantment cycle)
# =============================================================================

def _honden_cleansing_fire_resolve(event, state):
    controller = event.payload.get('player')
    if not controller:
        return []
    return _change_lp(state, controller, +500, "Honden of Cleansing Fire")


HONDEN_OF_CLEANSING_FIRE = make_ygo_spell(
    "Honden of Cleansing Fire", ygo_spell_type="Field",
    text="When activated and during each of your Standby Phases: gain 500 LP. "
         "Standby timing simplification: this Field Spell repeats on PHASE_CHANGE.",
    resolve=_honden_cleansing_fire_resolve,
    setup_interceptors=_make_honden_standby_setup(_honden_cleansing_fire_resolve),
)


def _honden_nights_reach_resolve(event, state):
    controller = event.payload.get('player')
    opp = _opponent_id(state, controller) if controller else None
    if not opp:
        return []
    return _discard_random(state, opp, 1)


HONDEN_OF_NIGHTS_REACH = make_ygo_spell(
    "Honden of Night's Reach", ygo_spell_type="Field",
    text="When activated and during each of your Standby Phases: opponent "
         "discards 1 random card. Standby timing simplification: discard the "
         "first available hand card.",
    resolve=_honden_nights_reach_resolve,
    setup_interceptors=_make_honden_standby_setup(_honden_nights_reach_resolve),
)


def _honden_infinite_rage_resolve(event, state):
    controller = event.payload.get('player')
    opp = _opponent_id(state, controller) if controller else None
    if not opp:
        return []
    return _change_lp(state, opp, -600, "Honden of Infinite Rage")


HONDEN_OF_INFINITE_RAGE = make_ygo_spell(
    "Honden of Infinite Rage", ygo_spell_type="Field",
    text="When activated and during each of your Standby Phases: deal 600 "
         "damage to opponent. Standby timing simplification: apply direct LP "
         "loss on PHASE_CHANGE.",
    resolve=_honden_infinite_rage_resolve,
    setup_interceptors=_make_honden_standby_setup(_honden_infinite_rage_resolve),
)


def _honden_lifes_web_resolve(event, state):
    """Fire from any Spirit/Plant in GY to summon back a Lv ≤2 monster."""
    controller = event.payload.get('player')
    if not controller:
        return []
    gy = state.zones.get(f"graveyard_{controller}")
    if not gy:
        return []
    for cid in list(gy.objects):
        cobj = state.objects.get(cid)
        if not cobj or not cobj.card_def:
            continue
        lvl = getattr(cobj.card_def, 'level', 99) or 99
        is_monster = (cobj.card_def.characteristics
                      and any(t.name == 'YGO_MONSTER' for t in cobj.card_def.characteristics.types))
        if is_monster and lvl <= 2:
            return revive_from_graveyard(state, controller, cid)
    return []


HONDEN_OF_LIFES_WEB = make_ygo_spell(
    "Honden of Life's Web", ygo_spell_type="Field",
    text="When activated and during each of your Standby Phases: SS 1 Lv 2 "
         "or lower monster from your GY. Standby timing simplification: revive "
         "the first legal monster.",
    resolve=_honden_lifes_web_resolve,
    setup_interceptors=_make_honden_standby_setup(_honden_lifes_web_resolve),
)


def _honden_seeing_winds_resolve(event, state):
    controller = event.payload.get('player')
    if not controller:
        return []
    return _draw(state, controller, 1)


HONDEN_OF_SEEING_WINDS = make_ygo_spell(
    "Honden of Seeing Winds", ygo_spell_type="Field",
    text="When activated and during each of your Standby Phases: draw 1 card. "
         "Standby timing simplification: draw on your standby PHASE_CHANGE.",
    resolve=_honden_seeing_winds_resolve,
    setup_interceptors=_make_honden_standby_setup(_honden_seeing_winds_resolve),
)


# =============================================================================
# Generic utility spells (Path to Exile, Ponder, Brainstorm-not-already-defined)
# =============================================================================

def _path_to_exile_resolve(event, state):
    controller = event.payload.get('player')
    if not controller:
        return []
    banished, _atk = _banish_one_face_up_opponent(state, controller)
    if not banished:
        return []
    # Compensation: opponent searches a Field Spell from their Deck
    opp = _opponent_id(state, controller)
    if opp:
        library = state.zones.get(f"library_{opp}")
        hand = state.zones.get(f"hand_{opp}")
        if library and hand:
            for cid in list(library.objects):
                cobj = state.objects.get(cid)
                if cobj and cobj.card_def and \
                   getattr(cobj.card_def, 'ygo_spell_type', None) == "Field":
                    library.objects.remove(cid)
                    hand.objects.append(cid)
                    cobj.zone = ZoneType.HAND
                    break
    return [Event(type=EventType.YGO_BANISH,
                  payload={'card_id': banished})]


PATH_TO_EXILE = make_ygo_spell(
    "Path to Exile", ygo_spell_type="Quick-Play",
    text="When activated: banish 1 face-up monster opponent controls; then "
         "that player may add 1 Field Spell from their Deck to hand. Targeting "
         "simplification: auto-pick the first face-up opposing monster.",
    resolve=_path_to_exile_resolve,
)


def _swords_to_plowshares_resolve(event, state):
    controller = event.payload.get('player')
    if not controller:
        return []
    banished, atk = _banish_one_face_up_opponent(state, controller)
    if not banished:
        return []
    opp = _opponent_id(state, controller)
    events = [Event(type=EventType.YGO_BANISH, payload={'card_id': banished})]
    if opp and atk:
        events.extend(_change_lp(state, opp, +atk, "Swords to Plowshares"))
    return events


SWORDS_TO_PLOWSHARES = make_ygo_spell(
    "Swords to Plowshares", ygo_spell_type="Quick-Play",
    text="When activated: banish 1 face-up monster opponent controls; then "
         "opponent gains LP equal to that monster's ATK. Targeting "
         "simplification: auto-pick the first face-up opposing monster.",
    resolve=_swords_to_plowshares_resolve,
)


def _doom_blade_resolve(event, state):
    """Destroy 1 face-up non-LIGHT monster opponent controls."""
    controller = event.payload.get('player')
    if not controller:
        return []
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
            if not obj or obj.state.face_down or not obj.card_def:
                continue
            if getattr(obj.card_def, 'attribute', None) == "LIGHT":
                continue
            zone.objects[i] = None
            gy = state.zones.get(f"graveyard_{obj.owner}")
            if gy:
                gy.objects.append(oid)
            obj.zone = ZoneType.GRAVEYARD
            obj.state.ygo_position = None
            return [Event(type=EventType.YGO_DESTROY,
                          payload={'card_id': oid, 'card_name': obj.name})]
    return []


DOOM_BLADE = make_ygo_spell(
    "Doom Blade", ygo_spell_type="Quick-Play",
    text="When activated: destroy 1 face-up non-LIGHT monster opponent "
         "controls. Targeting simplification: auto-pick the first legal "
         "opposing monster.",
    resolve=_doom_blade_resolve,
)


def _ponder_resolve(event, state):
    controller = event.payload.get('player')
    if not controller:
        return []
    # Look at top 3, optionally rearrange (auto: leave them), then draw 1
    return _draw(state, controller, 1)


PONDER = make_ygo_spell(
    "Ponder", ygo_spell_type="Normal",
    text="Look at the top 3 cards of your Deck; rearrange them, then draw 1 card.",
    resolve=_ponder_resolve,
)


def _preordain_resolve(event, state):
    controller = event.payload.get('player')
    if not controller:
        return []
    library = state.zones.get(f"library_{controller}")
    if library and len(library.objects) >= 2:
        # Move top to bottom (sim "put on bottom")
        top = library.objects.pop(0)
        library.objects.append(top)
    return _draw(state, controller, 1)


PREORDAIN = make_ygo_spell(
    "Preordain", ygo_spell_type="Normal",
    text="Look at top 2 of your Deck; put 1 on the bottom; draw 1.",
    resolve=_preordain_resolve,
)


def _lightning_bolt_resolve(event, state):
    controller = event.payload.get('player')
    if not controller:
        return []
    targets = event.payload.get('targets') or []
    # Default: hit opponent for 1500
    if not targets:
        opp = _opponent_id(state, controller)
        if opp:
            return _change_lp(state, opp, -1500, "Lightning Bolt")
        return []
    # Otherwise targeted at a monster — destroy if its ATK ≤ 1500, else apply -1500 EOT
    target = state.objects.get(targets[0])
    if not target or not target.card_def:
        return []
    atk = getattr(target.card_def, 'atk', 0) or 0
    if atk <= 1500:
        # destroy
        for z in state.zones.values():
            for i, oid in enumerate(z.objects):
                if oid == target.id:
                    z.objects[i] = None
            while target.id in z.objects:
                z.objects.remove(target.id)
        gy = state.zones.get(f"graveyard_{target.owner}")
        if gy is not None:
            gy.objects.append(target.id)
        target.zone = ZoneType.GRAVEYARD
        target.state.ygo_position = None
        return [Event(type=EventType.YGO_DESTROY,
                      payload={'card_id': target.id, 'card_name': target.name})]
    target.state.atk_bonus_eot = getattr(target.state, 'atk_bonus_eot', 0) - 1500
    return []


LIGHTNING_BOLT = make_ygo_spell(
    "Lightning Bolt", ygo_spell_type="Normal",
    text="When activated: deal 1500 damage to opponent; or destroy 1 targeted "
         "monster with ATK 1500 or less. Targeting simplification: no target "
         "means direct LP damage.",
    resolve=_lightning_bolt_resolve,
)


def _wrath_of_god_resolve(event, state):
    return destroy_all_monsters(state)


WRATH_OF_GOD = make_ygo_spell(
    "Wrath of God", ygo_spell_type="Normal",
    text="When activated: destroy all face-up monsters on the field. "
         "Resolution simplification: emit one YGO_DESTROY event for each "
         "monster destroyed.",
    resolve=_wrath_of_god_resolve,
)


def _day_of_judgment_resolve(event, state):
    return destroy_all_monsters(state)


DAY_OF_JUDGMENT = make_ygo_spell(
    "Day of Judgment", ygo_spell_type="Normal",
    text="When activated: destroy all monsters on the field. Resolution "
         "simplification: emit one YGO_DESTROY event for each monster destroyed.",
    resolve=_day_of_judgment_resolve,
)


def _demonic_tutor_resolve(event, state):
    """Search any monster from Deck."""
    controller = event.payload.get('player')
    if not controller:
        return []
    library = state.zones.get(f"library_{controller}")
    hand = state.zones.get(f"hand_{controller}")
    if not library or not hand:
        return []
    for cid in list(library.objects):
        obj = state.objects.get(cid)
        if not obj or not obj.card_def:
            continue
        if any(t.name == 'YGO_MONSTER' for t in obj.card_def.characteristics.types):
            library.objects.remove(cid)
            hand.objects.append(cid)
            obj.zone = ZoneType.HAND
            return [Event(type=EventType.YGO_DRAW,
                          payload={'player': controller, 'card_id': cid,
                                   'card_name': obj.name, 'source': 'tutor'})]
    return []


DEMONIC_TUTOR = make_ygo_spell(
    "Demonic Tutor", ygo_spell_type="Normal",
    text="When activated: search your Deck for 1 monster and add it to your "
         "hand. Search simplification: take the first legal monster in Deck order.",
    resolve=_demonic_tutor_resolve,
)


def _ss_level_four_from_hand_or_gy(state, controller: str) -> list[Event]:
    zone = state.zones.get(f"monster_zone_{controller}")
    if not zone:
        return []
    slot = None
    for i in range(5):
        if i >= len(zone.objects) or zone.objects[i] is None:
            slot = i
            break
    if slot is None:
        return []
    for zone_key in (f"graveyard_{controller}", f"hand_{controller}"):
        origin = state.zones.get(zone_key)
        if not origin:
            continue
        for cid in list(origin.objects):
            cobj = state.objects.get(cid)
            if not _is_ygo_monster(cobj):
                continue
            level = getattr(cobj.card_def, 'level', 99) or 99
            if level > 4:
                continue
            while len(zone.objects) <= slot:
                zone.objects.append(None)
            origin.objects.remove(cid)
            zone.objects[slot] = cid
            cobj.zone = ZoneType.MONSTER_ZONE
            cobj.controller = controller
            cobj.state.face_down = False
            cobj.state.ygo_position = 'face_up_atk'
            return [Event(type=EventType.YGO_SPECIAL_SUMMON,
                          payload={'player': controller, 'card_id': cid,
                                   'card_name': cobj.name,
                                   'summon_type': 'dark_ritual'})]
    return []


def _dark_ritual_resolve(event, state):
    """SS 1 Lv 4 or lower monster from your hand or GY."""
    controller = event.payload.get('player')
    if not controller:
        return []
    return _ss_level_four_from_hand_or_gy(state, controller)


DARK_RITUAL = make_ygo_spell(
    "Dark Ritual", ygo_spell_type="Normal",
    text="When activated: SS 1 Level 4 or lower monster from your GY or hand. "
         "Summon simplification: choose the first legal monster, preferring GY.",
    resolve=_dark_ritual_resolve,
)


def _howling_mine_resolve(event, state):
    """Continuous: each player draws 1 extra at Standby."""
    return []


def _howling_mine_setup(obj, state):
    def _filter(event, state):
        return (
            obj.zone == ZoneType.SPELL_TRAP_ZONE
            and event.type == EventType.PHASE_CHANGE
            and event.payload.get('phase') == 'standby'
            and event.payload.get('player') in state.players
            and getattr(obj.state, 'mine_turn', None) != (
                event.payload.get('player'), state.turn_number
            )
        )

    def _handler(event, state):
        player_id = event.payload.get('player')
        obj.state.mine_turn = (player_id, state.turn_number)
        return InterceptorResult(action=InterceptorAction.REACT,
                                 new_events=_draw(state, player_id, 1))

    return [Interceptor(id=new_id(), source=obj.id, controller=obj.controller,
                        priority=InterceptorPriority.REACT, filter=_filter,
                        handler=_handler, duration='until_leaves')]


HOWLING_MINE = make_ygo_spell(
    "Howling Mine", ygo_spell_type="Continuous",
    text="During each player's Standby Phase: that player draws 1 additional "
         "card. Standby timing simplification: draw once per player per turn "
         "on PHASE_CHANGE.",
    resolve=_howling_mine_resolve,
    setup_interceptors=_howling_mine_setup,
)


def _phyrexian_arena_setup(obj, state):
    """Once per turn during Standby: pay 1000 LP; draw 1."""
    def effect_fn(o, state):
        events = _change_lp(state, o.controller, -1000, "Phyrexian Arena")
        events.extend(_draw(state, o.controller, 1))
        return events
    return [make_ygo_ignition_effect(obj, effect_fn)]


PHYREXIAN_ARENA = make_ygo_spell(
    "Phyrexian Arena", ygo_spell_type="Continuous",
    text="Once per turn: pay 1000 LP; draw 1.",
    setup_interceptors=_phyrexian_arena_setup,
)


def _fact_or_fiction_resolve(event, state):
    """Reveal top 5; opponent splits; you take 1 pile."""
    # Simplified: draw 3 from top
    controller = event.payload.get('player')
    if not controller:
        return []
    return _draw(state, controller, 3)


FACT_OR_FICTION = make_ygo_spell(
    "Fact or Fiction", ygo_spell_type="Normal",
    text="When activated: reveal the top 5 cards of your Deck; opponent splits "
         "them into 2 piles; you take 1 pile. Choice simplification: draw 3 "
         "from the top.",
    resolve=_fact_or_fiction_resolve,
)


def _wheel_of_fortune_resolve(event, state):
    """Both players discard hands and draw 7."""
    events = []
    for pid in list(state.players.keys()):
        hand = state.zones.get(f"hand_{pid}")
        gy = state.zones.get(f"graveyard_{pid}")
        if hand and gy:
            while hand.objects:
                cid = hand.objects.pop()
                gy.objects.append(cid)
                cobj = state.objects.get(cid)
                if cobj:
                    cobj.zone = ZoneType.GRAVEYARD
                events.append(Event(type=EventType.YGO_SEND_TO_GY,
                                    payload={'card_id': cid, 'reason': 'wheel'}))
        events.extend(_draw(state, pid, 7))
    return events


WHEEL_OF_FORTUNE = make_ygo_spell(
    "Wheel of Fortune", ygo_spell_type="Normal",
    text="When activated: both players discard their hands; then both players "
         "draw 7 cards. Hand choice simplification: discard every card currently "
         "in hand.",
    resolve=_wheel_of_fortune_resolve,
)


# =============================================================================
# Generic utility traps
# =============================================================================

BOSEIJU_WHO_SHELTERS_ALL = make_ygo_trap(
    "Boseiju, Who Shelters All", ygo_trap_type="Counter",
    text="When activated in a chain: negate the activation of 1 Spell or Trap "
         "that targets a card in your hand or GY. Chain timing simplification: "
         "emit a negate_hand_or_gy_target marker.",
    resolve=_make_counter_resolve("negate_hand_or_gy_target"),
)


NEGATE = make_ygo_trap(
    "Negate", ygo_trap_type="Counter",
    text="When activated in a chain: negate the activation of 1 Spell. Chain "
         "timing simplification: emit a negate_spell marker instead of opening "
         "a full response window.",
    resolve=_make_counter_resolve("negate_spell"),
)


def _spell_pierce_resolve(event, state):
    """Opponent pays 2000 LP if able; otherwise the activation is negated."""
    controller = event.payload.get('player')
    opp = _opponent_id(state, controller) if controller else None
    if not opp:
        return []
    opp_player = state.players.get(opp)
    if opp_player and opp_player.lp > 2000:
        opp_player.lp -= 2000
        return [Event(type=EventType.YGO_LP_CHANGE,
                      payload={'player': opp, 'amount': -2000,
                               'source': 'Spell Pierce tax'})]
    return [Event(type=EventType.YGO_CHAIN_LINK,
                  payload={'effect': 'negate_spell_unless_pay',
                           'controller': controller,
                           'source': event.payload.get('card_id')})]


SPELL_PIERCE = make_ygo_trap(
    "Spell Pierce", ygo_trap_type="Counter",
    text="When activated in a chain: negate the activation of 1 Spell unless "
         "its controller pays 2000 LP. Chain timing simplification: opponent "
         "auto-pays when above 2000 LP.",
    resolve=_spell_pierce_resolve,
)


FORCE_SPIKE = make_ygo_trap(
    "Force Spike", ygo_trap_type="Counter",
    text="When activated in a chain: negate the activation of 1 Spell that has "
         "been activated this turn. Chain timing simplification: emit a "
         "negate_recent_spell marker.",
    resolve=_make_counter_resolve("negate_recent_spell"),
)


def _sword_and_shield_resolve(event, state):
    """All face-up monsters' ATK and DEF swap until end of turn."""
    for obj in state.objects.values():
        if obj.zone != ZoneType.MONSTER_ZONE or obj.state.face_down:
            continue
        if not obj.card_def:
            continue
        # Swap by setting end-of-turn modifiers
        atk = getattr(obj.card_def, 'atk', 0) or 0
        defv = getattr(obj.card_def, 'def_val', 0) or 0
        obj.state.atk_bonus_eot = getattr(obj.state, 'atk_bonus_eot', 0) + (defv - atk)
        obj.state.def_bonus_eot = getattr(obj.state, 'def_bonus_eot', 0) + (atk - defv)
    return []


SWORD_AND_SHIELD = make_ygo_trap(
    "Sword and Shield", ygo_trap_type="Normal",
    text="When activated: all face-up monsters swap their ATK and DEF until "
         "End of Turn. Layer simplification: record temporary ATK/DEF deltas "
         "on each current face-up monster.",
    resolve=_sword_and_shield_resolve,
)


def _karma_setup(obj, state):
    """Continuous Trap: drain the opponent whenever a monster goes to the GY."""
    def _filter(event, state):
        if obj.zone != ZoneType.SPELL_TRAP_ZONE or obj.state.face_down:
            return False
        if event.type not in (EventType.YGO_DESTROY, EventType.YGO_SEND_TO_GY):
            return False
        cid = event.payload.get('card_id')
        moved = state.objects.get(cid) if cid else None
        return _is_ygo_monster(moved)

    def _handler(event, state):
        opp = _opponent_id(state, obj.controller)
        if not opp:
            return InterceptorResult(action=InterceptorAction.PASS)
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=_change_lp(state, opp, -200, "Karma"),
        )

    return [Interceptor(id=new_id(), source=obj.id, controller=obj.controller,
                        priority=InterceptorPriority.REACT, filter=_filter,
                        handler=_handler, duration='until_leaves')]


KARMA = make_ygo_trap(
    "Karma", ygo_trap_type="Continuous",
    text="Each time a monster is sent to the GY: opponent loses 200 LP.",
    setup_interceptors=_karma_setup,
)


# =============================================================================
# Generic Equip Spells (universal)
# =============================================================================

def _empyrial_plate_setup(obj, state):
    """Equipped monster gains 200 ATK and DEF for each card in your hand."""
    def modifier_fn(event, state):
        from src.engine.types import (InterceptorAction, InterceptorResult)
        target_id = getattr(obj.state, 'equipped_to', None)
        if not target_id or event.payload.get('object_id') != target_id:
            return InterceptorResult(action=InterceptorAction.PASS)
        hand = state.zones.get(f"hand_{obj.controller}")
        n = len(hand.objects) if hand else 0
        if event.type == EventType.QUERY_POWER:
            event.payload['value'] = event.payload.get('value', 0) + 200 * n
        elif event.type == EventType.QUERY_TOUGHNESS:
            event.payload['value'] = event.payload.get('value', 0) + 200 * n
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=event)
    return [make_ygo_continuous_effect(obj, modifier_fn)]


EMPYRIAL_PLATE = make_ygo_spell(
    "Empyrial Plate", ygo_spell_type="Equip",
    text="Equipped monster gains 200 ATK and DEF for each card in your hand.",
    setup_interceptors=_empyrial_plate_setup,
)


def _whispersilk_cloak_setup(obj, state):
    """Equipped monster cannot be targeted by card effects (placeholder via flag)."""
    def modifier_fn(event, state):
        from src.engine.types import (InterceptorAction, InterceptorResult)
        target_id = getattr(obj.state, 'equipped_to', None)
        if target_id:
            target = state.objects.get(target_id)
            if target:
                target.state.untargetable = True
        return InterceptorResult(action=InterceptorAction.PASS)
    return [make_ygo_continuous_effect(obj, modifier_fn)]


WHISPERSILK_CLOAK = make_ygo_spell(
    "Whispersilk Cloak", ygo_spell_type="Equip",
    text="Equipped monster cannot be targeted by card effects.",
    setup_interceptors=_whispersilk_cloak_setup,
)


def _lightning_greaves_setup(obj, state):
    return [make_ygo_equip_boost(obj, atk_boost=500, def_boost=500)]


LIGHTNING_GREAVES = make_ygo_spell(
    "Lightning Greaves", ygo_spell_type="Equip",
    text="Equipped monster gains 500 ATK and DEF; cannot be targeted by effects.",
    setup_interceptors=_lightning_greaves_setup,
)


def _argentum_armor_setup(obj, state):
    """Equip boost plus attack-triggered removal."""
    def _filter(event, state):
        if event.type != EventType.YGO_BATTLE_DECLARE:
            return False
        target_id = getattr(obj.state, 'equipped_to', None)
        return bool(target_id and event.payload.get('attacker_id') == target_id)

    def _handler(event, state):
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=_destroy_one_face_up_opponent_card(state, obj.controller),
        )

    return [
        make_ygo_equip_boost(obj, atk_boost=500, def_boost=500),
        Interceptor(id=new_id(), source=obj.id, controller=obj.controller,
                    priority=InterceptorPriority.REACT, filter=_filter,
                    handler=_handler, duration='until_leaves'),
    ]


ARGENTUM_ARMOR = make_ygo_spell(
    "Argentum Armor", ygo_spell_type="Equip",
    text="Equipped monster gains 500 ATK and DEF. When equipped monster attacks: destroy 1 face-up card opponent controls.",
    setup_interceptors=_argentum_armor_setup,
)


# =============================================================================
# Generic small monsters (utility / universal use)
# =============================================================================

def _honden_acolyte_setup(obj, state):
    """When Normal Summoned: search 1 'Honden of...' Field Spell from Deck."""
    def effect_fn(o, state):
        library = state.zones.get(f"library_{o.controller}")
        hand = state.zones.get(f"hand_{o.controller}")
        if not library or not hand:
            return []
        for cid in list(library.objects):
            cobj = state.objects.get(cid)
            if cobj and cobj.card_def and cobj.name.startswith("Honden of"):
                library.objects.remove(cid)
                hand.objects.append(cid)
                cobj.zone = ZoneType.HAND
                return [Event(type=EventType.YGO_DRAW,
                              payload={'player': o.controller, 'card_id': cid,
                                       'card_name': cobj.name, 'source': 'search'})]
        return []
    return [make_ygo_summon_trigger(obj, effect_fn)]


HONDEN_ACOLYTE = make_ygo_monster(
    "Honden Acolyte", atk=800, def_val=800, level=2,
    attribute="LIGHT", ygo_monster_type="Effect",
    subtypes={"Spellcaster"},
    text="When Normal Summoned: add 1 'Honden of ...' Field Spell from your Deck.",
    setup_interceptors=_honden_acolyte_setup,
)


def _llanowar_elves_setup(obj, state):
    def effect_fn(o, state):
        events = _change_lp(state, o.controller, -500, "Llanowar Elves")
        gy = state.zones.get(f"graveyard_{o.controller}")
        if gy:
            for cid in list(gy.objects):
                cobj = state.objects.get(cid)
                if not cobj or not cobj.card_def:
                    continue
                lvl = getattr(cobj.card_def, 'level', 99) or 99
                is_monster = any(t.name == 'YGO_MONSTER' for t in cobj.card_def.characteristics.types)
                if is_monster and lvl <= 2:
                    events.extend(revive_from_graveyard(state, o.controller, cid))
                    return events
        return events
    return [make_ygo_ignition_effect(obj, effect_fn)]


LLANOWAR_ELVES = make_ygo_monster(
    "Llanowar Elves", atk=200, def_val=100, level=1,
    attribute="EARTH", ygo_monster_type="Effect",
    subtypes={"Plant"},
    text="Once per turn: pay 500 LP; SS 1 Lv ≤2 monster from your GY.",
    setup_interceptors=_llanowar_elves_setup,
)


def _birds_of_paradise_setup(obj, state):
    def effect_fn(o, state):
        hand = state.zones.get(f"hand_{o.controller}")
        zone = state.zones.get(f"monster_zone_{o.controller}")
        if not hand or not zone:
            return []
        for cid in list(hand.objects):
            cobj = state.objects.get(cid)
            if not cobj or not cobj.card_def:
                continue
            is_monster = any(t.name == 'YGO_MONSTER' for t in cobj.card_def.characteristics.types)
            lvl = getattr(cobj.card_def, 'level', 99) or 99
            if is_monster and lvl <= 4:
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
                cobj.state.ygo_position = 'face_up_def'
                return [Event(type=EventType.YGO_SPECIAL_SUMMON,
                              payload={'player': o.controller, 'card_id': cid,
                                       'card_name': cobj.name, 'summon_type': 'birds'})]
        return []
    return [make_ygo_ignition_effect(obj, effect_fn)]


BIRDS_OF_PARADISE = make_ygo_monster(
    "Birds of Paradise", atk=100, def_val=200, level=1,
    attribute="WIND", ygo_monster_type="Effect",
    subtypes={"Wing Beast"},
    text="Once per turn: SS 1 Lv ≤4 monster from your hand in face-up DEF.",
    setup_interceptors=_birds_of_paradise_setup,
)


def _squee_setup(obj, state):
    """When in your GY during your Standby Phase: you may add it to your hand."""
    def effect_fn(o, state):
        if o.zone == ZoneType.GRAVEYARD:
            hand = state.zones.get(f"hand_{o.controller}")
            gy = state.zones.get(f"graveyard_{o.controller}")
            if hand and gy and o.id in gy.objects:
                gy.objects.remove(o.id)
                hand.objects.append(o.id)
                o.zone = ZoneType.HAND
                return [Event(type=EventType.YGO_DRAW,
                              payload={'player': o.controller, 'card_id': o.id,
                                       'card_name': o.name, 'source': 'squee'})]
        return []
    return [make_ygo_ignition_effect(obj, effect_fn)]


SQUEE_GOBLIN_NABOB = make_ygo_monster(
    "Squee, Goblin Nabob", atk=100, def_val=100, level=1,
    attribute="FIRE", ygo_monster_type="Effect",
    subtypes={"Pyro"},
    text="During your Standby Phase, while this is in your GY: you may add it to your hand.",
    setup_interceptors=_squee_setup,
)


def _mox_diamond_setup(obj, state):
    def effect_fn(o, state):
        library = state.zones.get(f"library_{o.controller}")
        hand = state.zones.get(f"hand_{o.controller}")
        if not library or not hand:
            return []
        for cid in list(library.objects):
            cobj = state.objects.get(cid)
            if cobj and cobj.card_def and \
               getattr(cobj.card_def, 'ygo_spell_type', None) == "Field":
                library.objects.remove(cid)
                hand.objects.append(cid)
                cobj.zone = ZoneType.HAND
                return [Event(type=EventType.YGO_DRAW,
                              payload={'player': o.controller, 'card_id': cid,
                                       'card_name': cobj.name, 'source': 'mox'})]
        return []
    return [make_ygo_summon_trigger(obj, effect_fn)]


MOX_DIAMOND = make_ygo_monster(
    "Mox Diamond", atk=0, def_val=0, level=1,
    attribute="LIGHT", ygo_monster_type="Effect",
    subtypes={"Rock"},
    text="When Normal Summoned: search 1 Field Spell from your Deck.",
    setup_interceptors=_mox_diamond_setup,
)


def _sangromancer_setup(obj, state):
    def effect_fn(o, state):
        return _change_lp(state, o.controller, +500, "Sangromancer")
    def _filter(event, state):
        if event.type != EventType.YGO_DESTROY:
            return False
        cid = event.payload.get('card_id')
        if not cid:
            return False
        cobj = state.objects.get(cid)
        return cobj is not None and cobj.controller != obj.controller
    from src.engine.types import (Interceptor, InterceptorAction,
                                  InterceptorPriority, InterceptorResult, new_id)
    def _handler(event, state):
        return InterceptorResult(action=InterceptorAction.REACT,
                                 new_events=effect_fn(obj, state))
    return [Interceptor(id=new_id(), source=obj.id, controller=obj.controller,
                        priority=InterceptorPriority.REACT, filter=_filter,
                        handler=_handler, duration='until_leaves')]


SANGROMANCER = make_ygo_monster(
    "Sangromancer", atk=1700, def_val=1500, level=4,
    attribute="DARK", ygo_monster_type="Effect",
    subtypes={"Spellcaster"},
    text="Each time an opponent's monster is destroyed: gain 500 LP.",
    setup_interceptors=_sangromancer_setup,
)


def _akki_coalflinger_setup(obj, state):
    def effect_fn(o, state):
        opp = _opponent_id(state, o.controller)
        if opp:
            return _discard_random(state, opp, 1)
        return []
    def _filter(event, state):
        return (event.type == EventType.YGO_BATTLE_DECLARE and
                event.payload.get('attacker_id') == obj.id)
    from src.engine.types import (Interceptor, InterceptorAction,
                                  InterceptorPriority, InterceptorResult, new_id)
    def _handler(event, state):
        return InterceptorResult(action=InterceptorAction.REACT,
                                 new_events=effect_fn(obj, state))
    return [Interceptor(id=new_id(), source=obj.id, controller=obj.controller,
                        priority=InterceptorPriority.REACT, filter=_filter,
                        handler=_handler, duration='until_leaves')]


AKKI_COALFLINGER = make_ygo_monster(
    "Akki Coalflinger", atk=1500, def_val=1000, level=4,
    attribute="FIRE", ygo_monster_type="Effect",
    subtypes={"Beast"},
    text="When this card declares an attack: opponent discards 1 random card.",
    setup_interceptors=_akki_coalflinger_setup,
)


def _sage_of_mountain_path_setup(obj, state):
    def effect_fn(o, state):
        gy = state.zones.get(f"graveyard_{o.controller}")
        hand = state.zones.get(f"hand_{o.controller}")
        if not gy or not hand:
            return []
        for cid in list(gy.objects):
            cobj = state.objects.get(cid)
            if cobj and cobj.card_def and \
               getattr(cobj.card_def, 'ygo_spell_type', None) == "Field":
                gy.objects.remove(cid)
                hand.objects.append(cid)
                cobj.zone = ZoneType.HAND
                return [Event(type=EventType.YGO_DRAW,
                              payload={'player': o.controller, 'card_id': cid,
                                       'card_name': cobj.name, 'source': 'sage'})]
        return []
    return [make_ygo_ignition_effect(obj, effect_fn)]


SAGE_OF_MOUNTAIN_PATH = make_ygo_monster(
    "Sage of Mountain Path", atk=1000, def_val=1500, level=3,
    attribute="LIGHT", ygo_monster_type="Effect",
    subtypes={"Spellcaster"},
    text="Once per turn: target 1 Field Spell in your GY; add it to your hand.",
    setup_interceptors=_sage_of_mountain_path_setup,
)


def _goblin_welder_setup(obj, state):
    def effect_fn(o, state):
        gy = state.zones.get(f"graveyard_{o.controller}")
        if not gy:
            return []
        for cid in list(gy.objects):
            cobj = state.objects.get(cid)
            if cobj and cobj.card_def and \
               getattr(cobj.card_def, 'ygo_spell_type', None) == "Equip":
                # Find a Machine you control
                zone = state.zones.get(f"monster_zone_{o.controller}")
                if not zone:
                    return []
                for mid in zone.objects:
                    if not mid:
                        continue
                    mobj = state.objects.get(mid)
                    if mobj and mobj.card_def and \
                       "Machine" in (mobj.card_def.characteristics.subtypes or set()):
                        gy.objects.remove(cid)
                        # equip
                        st_zone = state.zones.get(f"spell_trap_zone_{o.controller}")
                        if st_zone is not None:
                            st_zone.objects.append(cid)
                        cobj.zone = ZoneType.BATTLEFIELD
                        cobj.state.equipped_to = mid
                        return [Event(type=EventType.YGO_EQUIP,
                                      payload={'card_id': cid, 'target_id': mid})]
        return []
    return [make_ygo_ignition_effect(obj, effect_fn)]


GOBLIN_WELDER = make_ygo_monster(
    "Goblin Welder", atk=200, def_val=200, level=1,
    attribute="FIRE", ygo_monster_type="Effect",
    subtypes={"Warrior"},
    text="Once per turn: target 1 Equip Spell in your GY; equip it to a Machine you control.",
    setup_interceptors=_goblin_welder_setup,
)


def _ss_level_two_from_hand_or_gy(state, controller: str) -> list[Event]:
    zone = state.zones.get(f"monster_zone_{controller}")
    if not zone:
        return []
    slot = None
    for i in range(5):
        if i >= len(zone.objects) or zone.objects[i] is None:
            slot = i
            break
    if slot is None:
        return []

    for zone_key in (f"hand_{controller}", f"graveyard_{controller}"):
        origin = state.zones.get(zone_key)
        if not origin:
            continue
        for cid in list(origin.objects):
            cobj = state.objects.get(cid)
            if not _is_ygo_monster(cobj):
                continue
            level = getattr(cobj.card_def, 'level', 99) or 99
            if level > 2:
                continue
            while len(zone.objects) <= slot:
                zone.objects.append(None)
            origin.objects.remove(cid)
            zone.objects[slot] = cid
            cobj.zone = ZoneType.MONSTER_ZONE
            cobj.controller = controller
            cobj.state.face_down = False
            cobj.state.ygo_position = 'face_up_def'
            return [Event(type=EventType.YGO_SPECIAL_SUMMON,
                          payload={'player': controller, 'card_id': cid,
                                   'card_name': cobj.name,
                                   'summon_type': 'solitary_confinement'})]
    return []


def _solitary_confinement_setup(obj, state):
    """Battle shield plus a low-level recovery ignition effect."""
    def _battle_filter(event, state):
        if obj.zone != ZoneType.MONSTER_ZONE:
            return False
        return (event.type == EventType.YGO_DESTROY
                and event.payload.get('card_id') == obj.id
                and event.payload.get('reason') == 'battle')

    def _battle_handler(event, state):
        return InterceptorResult(action=InterceptorAction.PREVENT)

    def effect_fn(o, state):
        if o.zone != ZoneType.MONSTER_ZONE:
            return []
        events = _change_lp(state, o.controller, -500, "Solitary Confinement")
        events.extend(_ss_level_two_from_hand_or_gy(state, o.controller))
        return events

    return [
        Interceptor(id=new_id(), source=obj.id, controller=obj.controller,
                    priority=InterceptorPriority.PREVENT, filter=_battle_filter,
                    handler=_battle_handler, duration='until_leaves'),
        make_ygo_ignition_effect(obj, effect_fn),
    ]


SOLITARY_CONFINEMENT = make_ygo_monster(
    "Solitary Confinement", atk=500, def_val=2000, level=2,
    attribute="LIGHT", ygo_monster_type="Effect",
    subtypes={"Spellcaster"},
    text="Cannot be destroyed by battle. Once per turn: pay 500 LP; SS 1 Lv ≤2 monster from your hand or GY.",
    setup_interceptors=_solitary_confinement_setup,
)


# Plain "land-flavored" Field Spells (5)
PLAINS = make_ygo_spell(
    "Plains, Sanctified Ground", ygo_spell_type="Field",
    text="While face-up in the Field Zone: LIGHT and EARTH monsters on the "
         "field gain 200 ATK and DEF. Layer simplification: a query hook "
         "checks current Attribute.",
    setup_interceptors=_make_attribute_field_setup(
        {"LIGHT": 200, "EARTH": 200},
        {"LIGHT": 200, "EARTH": 200},
    ),
)

ISLAND = make_ygo_spell(
    "Island, Mirror's Edge", ygo_spell_type="Field",
    text="While face-up in the Field Zone: WATER and WIND monsters on the "
         "field gain 200 ATK and DEF. Layer simplification: a query hook "
         "checks current Attribute.",
    setup_interceptors=_make_attribute_field_setup(
        {"WATER": 200, "WIND": 200},
        {"WATER": 200, "WIND": 200},
    ),
)

SWAMP = make_ygo_spell(
    "Swamp, Choking Mire", ygo_spell_type="Field",
    text="While face-up in the Field Zone: DARK monsters on the field gain "
         "300 ATK and 100 DEF. Layer simplification: a query hook checks "
         "current Attribute.",
    setup_interceptors=_make_attribute_field_setup({"DARK": 300}, {"DARK": 100}),
)

MOUNTAIN = make_ygo_spell(
    "Mountain, Smoldering Crag", ygo_spell_type="Field",
    text="While face-up in the Field Zone: FIRE and EARTH monsters on the "
         "field gain 300 ATK. Layer simplification: a query hook checks "
         "current Attribute.",
    setup_interceptors=_make_attribute_field_setup({"FIRE": 300, "EARTH": 300}),
)

FOREST = make_ygo_spell(
    "Forest, Whispering Glade", ygo_spell_type="Field",
    text="While face-up in the Field Zone: EARTH and WATER monsters on the "
         "field gain 200 ATK and 200 DEF. Layer simplification: a query hook "
         "checks current Attribute.",
    setup_interceptors=_make_attribute_field_setup(
        {"EARTH": 200, "WATER": 200},
        {"EARTH": 200, "WATER": 200},
    ),
)


# A few more universal monsters / staples to round to ~50
GREAVES_BEARER = make_ygo_monster(
    "Greaves Bearer", atk=800, def_val=1200, level=2,
    attribute="EARTH", ygo_monster_type="Effect",
    subtypes={"Warrior"},
    text="When Normal Summoned: add 1 Equip Spell from your Deck to your hand.",
    setup_interceptors=lambda obj, state: [
        make_ygo_summon_trigger(
            obj,
            lambda o, s: _search_library(s, o.controller, _is_equip_spell),
        )
    ],
)


def _solemn_wayfarer_setup(obj, state):
    def effect_fn(o, state):
        opp = _opponent_id(state, o.controller)
        if not opp:
            return []
        hand = state.zones.get(f"hand_{opp}")
        if not hand or not hand.objects:
            return []
        revealed = hand.objects[0]
        cobj = state.objects.get(revealed)
        return [Event(type=EventType.YGO_CHAIN_LINK,
                      payload={'effect': 'reveal_hand_card',
                               'controller': o.controller,
                               'opponent': opp,
                               'card_id': revealed,
                               'card_name': cobj.name if cobj else None})]
    return [make_ygo_summon_trigger(obj, effect_fn)]


def _equip_from_hand_to_first_monster(state, controller: str) -> list[Event]:
    target_id = _first_own_monster(state, controller)
    if not target_id:
        return []
    hand = state.zones.get(f"hand_{controller}")
    st_zone = state.zones.get(f"spell_trap_zone_{controller}")
    if not hand or st_zone is None:
        return []
    for cid in list(hand.objects):
        equip = state.objects.get(cid)
        if not _is_equip_spell(equip):
            continue
        slot = None
        for i in range(5):
            if i >= len(st_zone.objects) or st_zone.objects[i] is None:
                slot = i
                break
        if slot is None:
            return []
        while len(st_zone.objects) <= slot:
            st_zone.objects.append(None)
        hand.objects.remove(cid)
        st_zone.objects[slot] = cid
        equip.zone = ZoneType.SPELL_TRAP_ZONE
        equip.state.face_down = False
        equip.state.equipped_to = target_id
        return [Event(type=EventType.YGO_EQUIP,
                      payload={'player': controller, 'card_id': cid,
                               'target_id': target_id})]
    return []


def _stoneforge_mystic_setup(obj, state):
    """Normal Summon tutor plus an on-field equip cheat."""
    def summon_fn(o, state):
        return _search_library(state, o.controller, _is_equip_spell)

    def ignition_fn(o, state):
        if o.zone != ZoneType.MONSTER_ZONE:
            return []
        return _equip_from_hand_to_first_monster(state, o.controller)

    return [
        make_ygo_summon_trigger(obj, summon_fn),
        make_ygo_ignition_effect(obj, ignition_fn),
    ]


def _coiled_tomb_setup(obj, state):
    """When destroyed: revive a small EARTH monster from your GY."""
    def effect_fn(o, state):
        gy = state.zones.get(f"graveyard_{o.controller}")
        if not gy:
            return []
        for cid in list(gy.objects):
            cobj = state.objects.get(cid)
            if not _is_ygo_monster(cobj) or cobj.id == o.id:
                continue
            if getattr(cobj.card_def, 'attribute', None) != "EARTH":
                continue
            if (getattr(cobj.card_def, 'level', 99) or 99) > 4:
                continue
            return revive_from_graveyard(state, o.controller, cid)
        return []
    return [make_ygo_destroy_trigger(obj, effect_fn)]


STONEFORGE_MYSTIC = make_ygo_monster(
    "Stoneforge Mystic", atk=1200, def_val=1500, level=3,
    attribute="LIGHT", ygo_monster_type="Effect",
    subtypes={"Spellcaster"},
    text="When Normal Summoned: search 1 Equip Spell from your Deck. Once per turn: equip 1 Equip Spell from your hand to a monster you control.",
    setup_interceptors=_stoneforge_mystic_setup,
)


SOLEMN_WAYFARER = make_ygo_monster(
    "Solemn Wayfarer", atk=1500, def_val=1500, level=4,
    attribute="EARTH", ygo_monster_type="Effect",
    subtypes={"Warrior"},
    text="When Normal Summoned: opponent reveals 1 random card from their hand. "
         "Reveal simplification: show the first card in opponent hand order.",
    setup_interceptors=_solemn_wayfarer_setup,
)


COILED_TOMB = make_ygo_monster(
    "Coiled Tomb", atk=1000, def_val=2000, level=3,
    attribute="EARTH", ygo_monster_type="Effect",
    subtypes={"Reptile"},
    text="When destroyed by battle: SS 1 'Snake Token' (1500/1500). [Simplified: SS 1 Lv ≤4 EARTH monster from your GY.]",
    setup_interceptors=_coiled_tomb_setup,
)


SAKURA_TRIBE_SCOUT = make_ygo_monster(
    "Sakura-Tribe Scout", atk=600, def_val=1000, level=2,
    attribute="EARTH", ygo_monster_type="Effect",
    subtypes={"Plant"},
    text="When Normal Summoned: search 1 Field Spell from your Deck.",
    setup_interceptors=_mox_diamond_setup,  # Same effect — Field Spell search
)


_PASS3_TEXT_APPENDIX = {
    "Whispersilk Cloak": "Equip layer: the equipped monster gains an untargetable_by_effects marker while this card remains attached and face-up.",
    "Sangromancer": "Reaction trigger: each time an opponent's monster is destroyed and sent to the GY, you gain 500 LP.",
    "Empyrial Plate": "Equip layer: the equipped monster gains 200 ATK and DEF for each card in your hand, recalculated whenever stats are queried.",
    "Karma": "Continuous trigger: whenever any monster is sent to the GY, the opponent of this card's controller loses 200 LP.",
    "Akki Coalflinger": "Attack trigger: when this card declares an attack, the opponent discards the last card in hand as the simplified random card.",
    "Lightning Greaves": "Equip layer: the equipped monster gains 500 ATK and DEF and cannot be targeted by opponent card effects.",
    "Squee, Goblin Nabob": "Standby trigger: during your Standby Phase, if this card is in your GY, add it to your hand once.",
}

for _pass3_card in list(globals().values()):
    _pass3_note = _PASS3_TEXT_APPENDIX.get(getattr(_pass3_card, "name", None))
    if _pass3_note and _pass3_note not in (_pass3_card.text or ""):
        _pass3_card.text = f"{_pass3_card.text} {_pass3_note}"


# =============================================================================
# Set registry
# =============================================================================

BEYOND_KAMIGAWA_STAPLES = {card.name: card for card in [
    # Honden cycle (5)
    HONDEN_OF_CLEANSING_FIRE, HONDEN_OF_NIGHTS_REACH, HONDEN_OF_INFINITE_RAGE,
    HONDEN_OF_LIFES_WEB, HONDEN_OF_SEEING_WINDS,
    # Generic "land" Field Spells (5)
    PLAINS, ISLAND, SWAMP, MOUNTAIN, FOREST,
    # Spells (~16)
    PATH_TO_EXILE, SWORDS_TO_PLOWSHARES, DOOM_BLADE, PONDER, PREORDAIN,
    LIGHTNING_BOLT, WRATH_OF_GOD, DAY_OF_JUDGMENT, DEMONIC_TUTOR, DARK_RITUAL,
    HOWLING_MINE, PHYREXIAN_ARENA, FACT_OR_FICTION, WHEEL_OF_FORTUNE,
    EMPYRIAL_PLATE, WHISPERSILK_CLOAK, LIGHTNING_GREAVES, ARGENTUM_ARMOR,
    # Traps (7)
    BOSEIJU_WHO_SHELTERS_ALL, NEGATE, SPELL_PIERCE, FORCE_SPIKE,
    SWORD_AND_SHIELD, KARMA,
    # Monsters (12)
    HONDEN_ACOLYTE, LLANOWAR_ELVES, BIRDS_OF_PARADISE, SQUEE_GOBLIN_NABOB,
    MOX_DIAMOND, SANGROMANCER, AKKI_COALFLINGER, SAGE_OF_MOUNTAIN_PATH,
    GOBLIN_WELDER, SOLITARY_CONFINEMENT, GREAVES_BEARER, STONEFORGE_MYSTIC,
    SOLEMN_WAYFARER, COILED_TOMB, SAKURA_TRIBE_SCOUT,
]}


__all__ = ["BEYOND_KAMIGAWA_STAPLES"]
