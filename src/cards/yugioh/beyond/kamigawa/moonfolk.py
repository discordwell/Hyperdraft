"""
Beyond Kamigawa — Soratami Moonfolk archetype.

YGO mechanic: bounce/draw control with Counter Trap suite. Effects often pay
"return 1 monster you control to your hand" as a cost (the YGO analog to
Moonfolk's signature "return 2 lands" cost). WATER Spellcaster + Wing Beast.

Design pillar: Meloku the Clouded Mirror, Soratami Mirror-Mage, Patron of the
Moon (classic Kamigawa) and Tamiyo, Compleated Sage / The Wandering Emperor
(Neon Dynasty).

All cards in this archetype carry "Moonfolk" in their ``subtypes`` set so
the archetype-membership helpers in ``_archetype_helpers.py`` can find them.
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
    make_ygo_quick_effect,
    revive_from_graveyard,
)
from ._archetype_helpers import (
    has_subtype, count_on_field, find_in_graveyard,
    make_archetype_lord, make_archetype_team_lord,
)


# =============================================================================
# Internal helpers — bounce, search, draw
# =============================================================================

def _is_moonfolk(obj) -> bool:
    return (obj is not None and obj.card_def is not None and
            "Moonfolk" in (obj.card_def.characteristics.subtypes or set()))


def _bounce_monster_to_hand(state, target_id: str) -> list[Event]:
    """Send a monster from the field to its owner's hand. Emits a chain-link
    event so observers (counter traps, lord effects) can react.

    Mirrors ``_bounce_to_hand`` in ``_archetype_helpers.py`` but emits an
    event so test harnesses can detect the bounce.
    """
    target = state.objects.get(target_id)
    if not target:
        return []
    moved = False
    for z in state.zones.values():
        while target_id in z.objects:
            for i, oid in enumerate(z.objects):
                if oid == target_id:
                    z.objects[i] = None
                    moved = True
                    break
            while target_id in z.objects:
                z.objects.remove(target_id)
    hand = state.zones.get(f"hand_{target.owner}")
    if hand is not None:
        hand.objects.append(target_id)
    target.zone = ZoneType.HAND
    target.state.face_down = False
    target.state.ygo_position = None
    target.controller = target.owner
    if not moved:
        return []
    return [Event(type=EventType.YGO_CHAIN_LINK,
                  payload={'effect': 'bounce_to_hand', 'card_id': target_id,
                           'card_name': target.name})]


def _bounce_spell_trap_to_hand(state, target_id: str) -> list[Event]:
    """Return a Spell/Trap from the field to its owner's hand."""
    target = state.objects.get(target_id)
    if not target:
        return []
    moved = False
    for z in state.zones.values():
        if target_id in z.objects:
            for i, oid in enumerate(z.objects):
                if oid == target_id:
                    z.objects[i] = None
                    moved = True
            while target_id in z.objects:
                z.objects.remove(target_id)
    hand = state.zones.get(f"hand_{target.owner}")
    if hand is not None:
        hand.objects.append(target_id)
    target.zone = ZoneType.HAND
    target.state.face_down = False
    target.controller = target.owner
    if not moved:
        return []
    return [Event(type=EventType.YGO_CHAIN_LINK,
                  payload={'effect': 'bounce_spell_trap', 'card_id': target_id,
                           'card_name': target.name})]


def _first_own_monster(state, controller: str, predicate=None,
                       exclude_id: str = None) -> str | None:
    zone = state.zones.get(f"monster_zone_{controller}")
    if not zone:
        return None
    for oid in zone.objects:
        if not oid or oid == exclude_id:
            continue
        obj = state.objects.get(oid)
        if obj is None:
            continue
        if predicate is not None and not predicate(obj):
            continue
        return oid
    return None


def _first_opp_face_up_monster(state, controller: str) -> str | None:
    for pid in state.players:
        if pid == controller:
            continue
        zone = state.zones.get(f"monster_zone_{pid}")
        if not zone:
            continue
        for oid in zone.objects:
            if not oid:
                continue
            obj = state.objects.get(oid)
            if obj and not obj.state.face_down:
                return oid
    return None


def _all_opp_face_up_monsters(state, controller: str) -> list[str]:
    out = []
    for pid in state.players:
        if pid == controller:
            continue
        zone = state.zones.get(f"monster_zone_{pid}")
        if not zone:
            continue
        for oid in zone.objects:
            if not oid:
                continue
            obj = state.objects.get(oid)
            if obj and not obj.state.face_down:
                out.append(oid)
    return out


def _first_face_up_spell_trap(state, controller: str, own: bool = True) -> str | None:
    """Return the first face-up spell/trap on ``controller``'s side (own=True)
    or any opponent's side (own=False)."""
    targets = [controller] if own else [pid for pid in state.players if pid != controller]
    for pid in targets:
        zone = state.zones.get(f"spell_trap_zone_{pid}")
        if not zone:
            continue
        for oid in zone.objects:
            if not oid:
                continue
            obj = state.objects.get(oid)
            if obj and not obj.state.face_down:
                return oid
    return None


def _first_face_down_spell_trap_anywhere(state) -> str | None:
    for pid in state.players:
        zone = state.zones.get(f"spell_trap_zone_{pid}")
        if not zone:
            continue
        for oid in zone.objects:
            if not oid:
                continue
            obj = state.objects.get(oid)
            if obj and obj.state.face_down:
                return oid
    return None


def _draw(state, controller: str, n: int = 1) -> list[Event]:
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
                            payload={'player': controller, 'card_id': cid,
                                     'count': 1}))
    return events


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


def _move_to_hand(state, controller: str, card_id: str) -> list[Event]:
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


def _opp_id(state, controller: str) -> str | None:
    for pid in state.players:
        if pid != controller:
            return pid
    return None


# =============================================================================
# Effect monsters — setup functions
# =============================================================================

def _meloku_setup(obj, state):
    """Once per turn (Ignition): bounce 1 monster you control; draw 1 card.

    Token-creation simplified to a draw, per the design plan.
    """
    def effect_fn(o, state):
        target = _first_own_monster(state, o.controller, exclude_id=o.id)
        if not target:
            return []
        events = _bounce_monster_to_hand(state, target)
        events.extend(_draw(state, o.controller, 1))
        return events
    return [make_ygo_ignition_effect(obj, effect_fn)]


def _mirror_mage_setup(obj, state):
    """Once per turn: bounce 1 monster you control; bounce 1 monster opponent controls."""
    def effect_fn(o, state):
        own = _first_own_monster(state, o.controller, exclude_id=o.id)
        if not own:
            return []
        opp = _first_opp_face_up_monster(state, o.controller)
        if not opp:
            return []
        events = _bounce_monster_to_hand(state, own)
        events.extend(_bounce_monster_to_hand(state, opp))
        return events
    return [make_ygo_ignition_effect(obj, effect_fn)]


def _cloudskater_setup(obj, state):
    """Once per turn: bounce 1 monster you control; draw 1 card."""
    def effect_fn(o, state):
        target = _first_own_monster(state, o.controller, exclude_id=o.id)
        if not target:
            return []
        events = _bounce_monster_to_hand(state, target)
        events.extend(_draw(state, o.controller, 1))
        return events
    return [make_ygo_ignition_effect(obj, effect_fn)]


def _patron_of_the_moon_setup(obj, state):
    """When Tribute Summoned: bounce all face-up monsters opponent controls."""
    def effect_fn(o, state):
        events = []
        for tid in _all_opp_face_up_monsters(state, o.controller):
            events.extend(_bounce_monster_to_hand(state, tid))
        return events
    def _filter(event, state):
        return (event.type == EventType.YGO_TRIBUTE_SUMMON and
                event.payload.get('card_id') == obj.id)
    def _handler(event, state):
        return InterceptorResult(action=InterceptorAction.REACT,
                                 new_events=effect_fn(obj, state) or [])
    return [Interceptor(id=new_id(), source=obj.id, controller=obj.controller,
                        priority=InterceptorPriority.REACT, filter=_filter,
                        handler=_handler, duration='until_leaves')]


def _tamiyo_compleated_setup(obj, state):
    """Effect (Ignition): target 1 Spell in your GY; add it to your hand.

    Pendulum scale handling is left to the engine's Pendulum Zone code; the
    pendulum_scale field on the CardDefinition is set by the constructor.
    """
    def effect_fn(o, state):
        gy = state.zones.get(f"graveyard_{o.controller}")
        if not gy:
            return []
        for cid in list(gy.objects):
            cobj = state.objects.get(cid)
            if cobj and cobj.card_def and CardType.YGO_SPELL in (cobj.card_def.characteristics.types or set()):
                return _move_to_hand(state, o.controller, cid)
        return []
    return [make_ygo_ignition_effect(obj, effect_fn)]


def _tamiyo_field_researcher_setup(obj, state):
    """Once per turn: opponent reveals 1 random card from their hand; you may
    discard 1 card. If you do: shuffle the revealed card into the Deck.

    Simplified: on activation, banish-equivalent (shuffle) the top card of
    opponent's hand if you have a card to discard. Discards your last hand
    card. Skips when either hand is empty.
    """
    def effect_fn(o, state):
        opp = _opp_id(state, o.controller)
        if not opp:
            return []
        opp_hand = state.zones.get(f"hand_{opp}")
        own_hand = state.zones.get(f"hand_{o.controller}")
        if not opp_hand or not own_hand:
            return []
        if not opp_hand.objects or not own_hand.objects:
            return []
        # Discard your last drawn card
        discard_id = own_hand.objects.pop()
        gy = state.zones.get(f"graveyard_{o.controller}")
        if gy is not None:
            gy.objects.append(discard_id)
        dobj = state.objects.get(discard_id)
        if dobj:
            dobj.zone = ZoneType.GRAVEYARD
        # Shuffle the first card of opp's hand back into their Deck
        revealed = opp_hand.objects.pop(0)
        lib = state.zones.get(f"library_{opp}")
        if lib is not None:
            lib.objects.append(revealed)
        robj = state.objects.get(revealed)
        if robj:
            robj.zone = ZoneType.LIBRARY
        return [Event(type=EventType.YGO_CHAIN_LINK,
                      payload={'effect': 'shuffle_into_deck',
                               'card_id': revealed, 'controller': opp})]
    return [make_ygo_ignition_effect(obj, effect_fn)]


def _wandering_emperor_moonfolk_setup(obj, state):
    """Quick Effect: negate the effects of 1 face-up Spell/Trap until End Phase."""
    def effect_fn(o, state):
        target = _first_face_up_spell_trap(state, o.controller, own=False)
        if not target:
            return []
        tobj = state.objects.get(target)
        if tobj:
            tobj.state.effects_negated_eot = True
        return [Event(type=EventType.YGO_CHAIN_LINK,
                      payload={'effect': 'negate_spell_trap_effects',
                               'card_id': target, 'controller': o.controller})]
    return [make_ygo_quick_effect(obj, effect_fn)]


def _mirror_guard_setup(obj, state):
    """Once per turn: bounce 1 face-up Spell/Trap you control to your hand;
    SS this card from your hand to the field."""
    def effect_fn(o, state):
        if o.zone != ZoneType.HAND:
            return []
        target = _first_face_up_spell_trap(state, o.controller, own=True)
        if not target:
            return []
        events = _bounce_spell_trap_to_hand(state, target)
        # SS self
        zone = state.zones.get(f"monster_zone_{o.controller}")
        hand = state.zones.get(f"hand_{o.controller}")
        if not zone or not hand:
            return events
        slot = None
        for j in range(5):
            if j >= len(zone.objects) or zone.objects[j] is None:
                slot = j
                break
        if slot is None:
            return events
        while len(zone.objects) <= slot:
            zone.objects.append(None)
        if o.id in hand.objects:
            hand.objects.remove(o.id)
        zone.objects[slot] = o.id
        o.zone = ZoneType.MONSTER_ZONE
        o.state.ygo_position = 'face_up_atk'
        o.state.face_down = False
        events.append(Event(type=EventType.YGO_SPECIAL_SUMMON,
                            payload={'player': o.controller, 'card_id': o.id,
                                     'card_name': o.name, 'summon_type': 'mirror_guard'}))
        return events
    return [make_ygo_ignition_effect(obj, effect_fn)]


def _eye_of_nowhere_diviner_setup(obj, state):
    """When Normal Summoned: bounce 1 face-down Spell/Trap on the field to its
    owner's hand."""
    def effect_fn(o, state):
        target = _first_face_down_spell_trap_anywhere(state)
        if not target:
            return []
        return _bounce_spell_trap_to_hand(state, target)
    def _filter(event, state):
        return (event.type == EventType.YGO_NORMAL_SUMMON and
                event.payload.get('card_id') == obj.id)
    def _handler(event, state):
        return InterceptorResult(action=InterceptorAction.REACT,
                                 new_events=effect_fn(obj, state) or [])
    return [Interceptor(id=new_id(), source=obj.id, controller=obj.controller,
                        priority=InterceptorPriority.REACT, filter=_filter,
                        handler=_handler, duration='until_leaves')]


def _soratami_savant_setup(obj, state):
    """When Normal Summoned: search 1 'Moonfolk' from Deck (excluding self)."""
    def effect_fn(o, state):
        return _search_library(state, o.controller,
                               lambda c: _is_moonfolk(c) and c.id != o.id)
    return [make_ygo_summon_trigger(obj, effect_fn)]


def _cloud_cuckoo_land_setup(obj, state):
    """When Normal Summoned: search 1 Lv 4 or lower 'Moonfolk' from Deck."""
    def effect_fn(o, state):
        return _search_library(
            state, o.controller,
            lambda c: _is_moonfolk(c) and c.id != o.id and
                      (getattr(c.card_def, 'level', 99) or 99) <= 4
        )
    return [make_ygo_summon_trigger(obj, effect_fn)]


def _misdirection_master_setup(obj, state):
    """Once per turn: bounce 1 monster opponent controls to its owner's hand."""
    def effect_fn(o, state):
        target = _first_opp_face_up_monster(state, o.controller)
        if not target:
            return []
        return _bounce_monster_to_hand(state, target)
    return [make_ygo_ignition_effect(obj, effect_fn)]


def _reality_chip_bearer_setup(obj, state):
    """When Normal Summoned: draw 1. Bridges Moonfolk to the Modified archetype.

    This card carries both 'Moonfolk' and 'Modified' in subtypes for the
    cross-archetype Reality Chip support.
    """
    def effect_fn(o, state):
        return _draw(state, o.controller, 1)
    return [make_ygo_summon_trigger(obj, effect_fn)]


def _tide_star_acolyte_setup(obj, state):
    """When sent from field to GY: draw 1."""
    def effect_fn(o, state):
        return _draw(state, o.controller, 1)
    return [make_ygo_destroy_trigger(obj, effect_fn)]


# =============================================================================
# Card definitions — Monsters
# =============================================================================

TIDE_STAR_ACOLYTE = make_ygo_monster(
    "Tide-Star Acolyte", atk=400, def_val=400, level=2,
    attribute="WATER", ygo_monster_type="Effect",
    subtypes={"Spellcaster", "Moonfolk"},
    text="When sent from the field to the GY: draw 1 card.",
    setup_interceptors=_tide_star_acolyte_setup,
)

CLOUD_CUCKOO_LAND = make_ygo_monster(
    "Cloud Cuckoo Land", atk=300, def_val=600, level=1,
    attribute="WATER", ygo_monster_type="Effect",
    subtypes={"Spellcaster", "Moonfolk"},
    text="When Normal Summoned: search 1 Lv 4 or lower 'Moonfolk' from your Deck.",
    setup_interceptors=_cloud_cuckoo_land_setup,
)

SORATAMI_SAVANT = make_ygo_monster(
    "Soratami Savant", atk=900, def_val=1100, level=3,
    attribute="WATER", ygo_monster_type="Effect",
    subtypes={"Wing Beast", "Moonfolk"},
    text="When Normal Summoned: search 1 'Moonfolk' from your Deck.",
    setup_interceptors=_soratami_savant_setup,
)

SORATAMI_MIRROR_GUARD = make_ygo_monster(
    "Soratami Mirror-Guard", atk=1500, def_val=1000, level=3,
    attribute="WATER", ygo_monster_type="Effect",
    subtypes={"Wing Beast", "Moonfolk"},
    text="Once per turn: return 1 face-up Spell/Trap you control to your hand; "
         "SS this card from your hand.",
    setup_interceptors=_mirror_guard_setup,
)

EYE_OF_NOWHERE_DIVINER = make_ygo_monster(
    "Eye of Nowhere Diviner", atk=1400, def_val=1400, level=4,
    attribute="WATER", ygo_monster_type="Effect",
    subtypes={"Spellcaster", "Moonfolk"},
    text="When Normal Summoned: return 1 face-down Spell/Trap on the field to its "
         "owner's hand.",
    setup_interceptors=_eye_of_nowhere_diviner_setup,
)

SORATAMI_CLOUDSKATER = make_ygo_monster(
    "Soratami Cloudskater", atk=1500, def_val=1000, level=4,
    attribute="WATER", ygo_monster_type="Effect",
    subtypes={"Wing Beast", "Moonfolk"},
    text="Once per turn: return 1 monster you control to your hand; draw 1 card.",
    setup_interceptors=_cloudskater_setup,
)

SORATAMI_MIRROR_MAGE = make_ygo_monster(
    "Soratami Mirror-Mage", atk=1500, def_val=1500, level=4,
    attribute="WATER", ygo_monster_type="Effect",
    subtypes={"Wing Beast", "Moonfolk"},
    text="Once per turn: return 1 monster you control to your hand; "
         "return 1 monster opponent controls to its owner's hand.",
    setup_interceptors=_mirror_mage_setup,
)

MISDIRECTION_MASTER = make_ygo_monster(
    "Misdirection Master", atk=1600, def_val=1200, level=4,
    attribute="WATER", ygo_monster_type="Effect",
    subtypes={"Spellcaster", "Moonfolk"},
    text="Once per turn: return 1 monster opponent controls to its owner's hand.",
    setup_interceptors=_misdirection_master_setup,
)

REALITY_CHIP_BEARER = make_ygo_monster(
    "Reality Chip Bearer", atk=1400, def_val=1400, level=4,
    attribute="WATER", ygo_monster_type="Effect",
    subtypes={"Spellcaster", "Moonfolk", "Modified"},
    text="When Normal Summoned: draw 1 card.",
    setup_interceptors=_reality_chip_bearer_setup,
)

REFLECT_LORD = make_ygo_monster(
    "Reflect Lord of the Soratami", atk=1700, def_val=1500, level=4,
    attribute="WATER", ygo_monster_type="Effect",
    subtypes={"Spellcaster", "Moonfolk"},
    text="All other 'Moonfolk' monsters you control gain 200 ATK. "
         "The boost applies through the stat layer while this card stays face-up.",
    setup_interceptors=lambda obj, state: [
        make_archetype_team_lord(obj, atk_bonus=200, archetype="Moonfolk")
    ],
)

THE_WANDERING_EMPEROR_MOONFOLK = make_ygo_monster(
    "The Wandering Emperor, Cloud Sovereign", atk=1700, def_val=1700, level=4,
    attribute="WATER", ygo_monster_type="Effect",
    subtypes={"Spellcaster", "Moonfolk"},
    text="Once per turn (Quick Effect): negate the effects of 1 face-up Spell/Trap "
         "your opponent controls until the End Phase.",
    setup_interceptors=_wandering_emperor_moonfolk_setup,
)

TAMIYO_FIELD_RESEARCHER = make_ygo_monster(
    "Tamiyo, Field Researcher", atk=2000, def_val=2000, level=5,
    attribute="WATER", ygo_monster_type="Effect", is_tuner=True,
    subtypes={"Spellcaster", "Moonfolk"},
    text="Once per turn: opponent reveals 1 random card from their hand; you may "
         "discard 1 card. If you do: shuffle the revealed card into the Deck.",
    setup_interceptors=_tamiyo_field_researcher_setup,
)

MELOKU_THE_CLOUDED_MIRROR = make_ygo_monster(
    "Meloku the Clouded Mirror", atk=2500, def_val=2000, level=7,
    attribute="WATER", ygo_monster_type="Effect",
    subtypes={"Spellcaster", "Moonfolk"},
    text="Once per turn (Ignition): return 1 monster you control to your hand; "
         "draw 1 card.",
    setup_interceptors=_meloku_setup,
)


# =============================================================================
# Card definitions — Spells
# =============================================================================

def _hinder_resolve(event, state):
    """Quick-Play: bounce 1 monster opponent controls."""
    controller = event.payload.get('player')
    if not controller:
        return []
    target = _first_opp_face_up_monster(state, controller)
    if not target:
        return []
    return _bounce_monster_to_hand(state, target)


HINDER = make_ygo_spell(
    "Hinder", ygo_spell_type="Quick-Play",
    text="When activated: return 1 monster opponent controls to its owner's "
         "hand. Targeting simplification: auto-pick the first face-up opposing "
         "monster.",
    resolve=_hinder_resolve,
)


def _eye_of_nowhere_resolve(event, state):
    """Normal: bounce 1 face-up Spell/Trap on the field."""
    controller = event.payload.get('player')
    if not controller:
        return []
    target = _first_face_up_spell_trap(state, controller, own=False)
    if not target:
        target = _first_face_up_spell_trap(state, controller, own=True)
    if not target:
        return []
    return _bounce_spell_trap_to_hand(state, target)


EYE_OF_NOWHERE = make_ygo_spell(
    "Eye of Nowhere", ygo_spell_type="Normal",
    text="Return 1 face-up Spell/Trap on the field to its owner's hand.",
    resolve=_eye_of_nowhere_resolve,
)


def _boomerang_setup(obj, state):
    """Equip: once per turn, bounce equipped to hand and draw 1."""
    from src.engine.yugioh_helpers import make_ygo_equip_boost
    interceptors = [make_ygo_equip_boost(obj, atk_boost=0, def_boost=0)]
    def effect_fn(o, state):
        equipped_id = getattr(o.state, 'equipped_to', None)
        if not equipped_id:
            return []
        events = _bounce_monster_to_hand(state, equipped_id)
        events.extend(_draw(state, o.controller, 1))
        return events
    interceptors.append(make_ygo_ignition_effect(obj, effect_fn))
    return interceptors


BOOMERANG = make_ygo_spell(
    "Boomerang", ygo_spell_type="Equip",
    text="Once per turn: return the equipped monster to its owner's hand; draw 1.",
    setup_interceptors=_boomerang_setup,
)


def _vapor_snag_resolve(event, state):
    """Quick-Play: bounce 1 monster opponent controls; deal 200 damage."""
    controller = event.payload.get('player')
    if not controller:
        return []
    target = _first_opp_face_up_monster(state, controller)
    if not target:
        return []
    events = _bounce_monster_to_hand(state, target)
    opp = _opp_id(state, controller)
    if opp:
        player = state.players.get(opp)
        if player:
            player.lp = max(0, player.lp - 200)
            events.append(Event(type=EventType.YGO_LP_CHANGE,
                                payload={'player': opp, 'amount': -200,
                                         'source': 'Vapor Snag'}))
    return events


VAPOR_SNAG = make_ygo_spell(
    "Vapor Snag", ygo_spell_type="Quick-Play",
    text="Return 1 monster opponent controls to its owner's hand; deal 200 damage.",
    resolve=_vapor_snag_resolve,
)


def _path_of_shadows_setup(obj, state):
    """Continuous: once per turn at Standby, bounce 1 of your monsters; search
    1 'Moonfolk' from your Deck.

    We register an ignition-style activation hook (engine schedules an upkeep
    call) and rely on the deck-level once-per-turn limiter built into
    ``make_ygo_ignition_effect``.
    """
    def effect_fn(o, state):
        target = _first_own_monster(state, o.controller)
        if not target:
            return []
        events = _bounce_monster_to_hand(state, target)
        events.extend(_search_library(state, o.controller, _is_moonfolk))
        return events
    return [make_ygo_ignition_effect(obj, effect_fn)]


PATH_OF_SHADOWS = make_ygo_spell(
    "Path of Shadows", ygo_spell_type="Continuous",
    text="Once per turn during your Standby Phase: return 1 monster you control "
         "to your hand; add 1 'Moonfolk' from your Deck to your hand.",
    setup_interceptors=_path_of_shadows_setup,
)


def _reality_stutter_resolve(event, state):
    """Normal: opponent shuffles 2 cards from their hand into Deck.

    Phase 4: the choice of which 2 hand cards to shuffle belongs to the
    *opponent* (they pay the cost). For humans, emit a PendingChoice over
    their hand. For AI, ``heuristic_pick`` preserves the prior "first 2 in
    hand order" behavior so existing AI play doesn't shift.
    """
    from src.engine.pending_choice_helpers import create_choice_and_resolve

    controller = event.payload.get('player')
    if not controller:
        return []
    opp = _opp_id(state, controller)
    if not opp:
        return []
    opp_hand = state.zones.get(f"hand_{opp}")
    lib = state.zones.get(f"library_{opp}")
    if not opp_hand or not lib:
        return []

    # Empty short-circuit: opponent has nothing to shuffle.
    if not opp_hand.objects:
        return []

    source_id = event.payload.get('card_id') or ''
    want = min(2, len(opp_hand.objects))

    options = []
    for cid in opp_hand.objects:
        cobj = state.objects.get(cid)
        if cobj is None or cobj.card_def is None:
            continue
        cdef = cobj.card_def
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

    # Preserve old "first 2 in hand order" pick.
    top_ids = list(opp_hand.objects[:want])

    def _resolve_handler(choice, selected, st):
        picked: list[str] = []
        for entry in selected or []:
            if isinstance(entry, dict):
                eid = entry.get("id")
                if eid is not None:
                    picked.append(eid)
            else:
                picked.append(entry)
        picked = picked[:want]

        hd = st.zones.get(f"hand_{opp}")
        lb = st.zones.get(f"library_{opp}")
        if hd is None or lb is None:
            return []
        out: list[Event] = []
        for cid in picked:
            if cid not in hd.objects:
                continue
            hd.objects.remove(cid)
            lb.objects.append(cid)
            cobj = st.objects.get(cid)
            if cobj is not None:
                cobj.zone = ZoneType.LIBRARY
            out.append(Event(type=EventType.YGO_CHAIN_LINK,
                             payload={'effect': 'shuffle_into_deck',
                                      'card_id': cid, 'controller': opp}))
        return out

    return create_choice_and_resolve(
        state,
        choice_type="target",
        player_id=opp,  # The OPPONENT picks which cards to shuffle.
        prompt=f"Shuffle {want} card(s) from your hand into your Deck.",
        options=options,
        source_id=source_id,
        min_choices=want,
        max_choices=want,
        handler=_resolve_handler,
        heuristic_pick=top_ids,
    )


REALITY_STUTTER = make_ygo_spell(
    "Reality Stutter", ygo_spell_type="Normal",
    text="When activated: opponent shuffles 2 cards from their hand into "
         "their Deck. The opponent chooses which cards to shuffle.",
    resolve=_reality_stutter_resolve,
)


def _mirror_realm_setup(obj, state):
    """Field Spell: Moonfolk boost plus once-per-turn bounce cantrip."""
    def _active() -> bool:
        return obj.zone == ZoneType.FIELD_SPELL_ZONE

    def boost_filter(event, state):
        if not _active() or event.type != EventType.QUERY_POWER:
            return False
        target = state.objects.get(event.payload.get('object_id'))
        return target is not None and target.controller == obj.controller and _is_moonfolk(target)

    def boost_handler(event, state):
        event.payload['value'] = event.payload.get('value', 0) + 200
        return InterceptorResult(action=InterceptorAction.TRANSFORM,
                                 transformed_event=event)

    def bounce_filter(event, state):
        if not _active() or event.type != EventType.YGO_CHAIN_LINK:
            return False
        if event.payload.get('effect') not in {'bounce_to_hand', 'bounce_spell_trap'}:
            return False
        return getattr(obj.state, 'mirror_realm_draw_turn', None) != state.turn_number

    def bounce_handler(event, state):
        obj.state.mirror_realm_draw_turn = state.turn_number
        return InterceptorResult(action=InterceptorAction.REACT,
                                 new_events=_draw(state, obj.controller, 1))

    return [
        Interceptor(id=new_id(), source=obj.id, controller=obj.controller,
                    priority=InterceptorPriority.QUERY, filter=boost_filter,
                    handler=boost_handler, duration='until_leaves'),
        Interceptor(id=new_id(), source=obj.id, controller=obj.controller,
                    priority=InterceptorPriority.REACT, filter=bounce_filter,
                    handler=bounce_handler, duration='until_leaves'),
    ]


MIRROR_REALM = make_ygo_spell(
    "Mirror Realm", ygo_spell_type="Field",
    text="All 'Moonfolk' you control gain 200 ATK. While this card is on the "
         "field, the first time each turn a card is returned to hand by an "
         "effect: draw 1 card.",
    setup_interceptors=_mirror_realm_setup,
)


def _brainstorm_resolve(event, state):
    """Normal: draw 3, then put 2 cards from your hand on top of your Deck.

    Phase 4: after the draw 3, controller picks WHICH 2 cards to put back on
    top of the deck. Humans get a PendingChoice; AI heuristic_pick preserves
    the old "last 2 cards in hand" behavior (i.e. the 2 last drawn).
    """
    from src.engine.pending_choice_helpers import create_choice_and_resolve

    controller = event.payload.get('player')
    if not controller:
        return []
    events = _draw(state, controller, 3)
    hand = state.zones.get(f"hand_{controller}")
    lib = state.zones.get(f"library_{controller}")
    if not hand or not lib:
        return events

    # Empty short-circuit: hand has nothing to push back.
    if not hand.objects:
        return events

    source_id = event.payload.get('card_id') or ''
    want = min(2, len(hand.objects))

    options = []
    for cid in hand.objects:
        cobj = state.objects.get(cid)
        if cobj is None or cobj.card_def is None:
            continue
        cdef = cobj.card_def
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
        return events

    # Old behavior: pop the last `want` cards (i.e. the 2 last drawn). These
    # are the tail of hand.objects post-draw, so the heuristic is the LAST N.
    top_ids = list(hand.objects[-want:])

    def _resolve_handler(choice, selected, st):
        picked: list[str] = []
        for entry in selected or []:
            if isinstance(entry, dict):
                eid = entry.get("id")
                if eid is not None:
                    picked.append(eid)
            else:
                picked.append(entry)
        picked = picked[:want]

        hd = st.zones.get(f"hand_{controller}")
        lb = st.zones.get(f"library_{controller}")
        if hd is None or lb is None:
            return []
        for cid in picked:
            if cid not in hd.objects:
                continue
            hd.objects.remove(cid)
            lb.objects.insert(0, cid)
            cobj = st.objects.get(cid)
            if cobj is not None:
                cobj.zone = ZoneType.LIBRARY
        return []  # Top-of-deck moves are silent (no DRAW event).

    events.extend(create_choice_and_resolve(
        state,
        choice_type="target",
        player_id=controller,
        prompt=f"Put {want} card(s) from your hand on top of your Deck.",
        options=options,
        source_id=source_id,
        min_choices=want,
        max_choices=want,
        handler=_resolve_handler,
        heuristic_pick=top_ids,
    ))
    return events


BRAINSTORM = make_ygo_spell(
    "Brainstorm", ygo_spell_type="Normal",
    text="Draw 3 cards, then put 2 cards from your hand on top of your Deck "
         "in any order.",
    resolve=_brainstorm_resolve,
)


def _counterspell_lite_resolve(event, state):
    """Normal: negate the activation of 1 Normal Spell."""
    return [Event(type=EventType.YGO_CHAIN_LINK,
                  payload={'effect': 'negate_spell',
                           'restriction': 'normal_spell',
                           'controller': event.payload.get('player')})]


COUNTERSPELL_LITE = make_ygo_spell(
    "Counterspell, Lite Edition", ygo_spell_type="Normal",
    text="When activated in a chain: negate the activation of 1 Normal Spell. "
         "Chain timing simplification: emit a restricted negate_spell marker.",
    resolve=_counterspell_lite_resolve,
)


def _resounding_roar_setup(obj, state):
    """Continuous: once per turn during Standby Phase: opponent reveals top of
    Deck; bounce a face-up monster you control. (Simplified: bounce a face-up
    monster opponent controls instead.)"""
    def effect_fn(o, state):
        target = _first_opp_face_up_monster(state, o.controller)
        if not target:
            return []
        return _bounce_monster_to_hand(state, target)
    return [make_ygo_ignition_effect(obj, effect_fn)]


RESOUNDING_ROAR = make_ygo_spell(
    "Resounding Roar", ygo_spell_type="Continuous",
    text="Once per turn during your Standby Phase: opponent reveals the top "
         "card of their Deck. Then return 1 face-up monster opponent controls "
         "to its owner's hand.",
    setup_interceptors=_resounding_roar_setup,
)


# =============================================================================
# Card definitions — Traps (mostly Counter)
# =============================================================================

def _wandering_negation_resolve(event, state):
    """Counter Trap: negate 1 Spell/Trap and destroy it."""
    return [Event(type=EventType.YGO_CHAIN_LINK,
                  payload={'effect': 'negate_spell_trap_and_destroy',
                           'controller': event.payload.get('player')})]


WANDERING_NEGATION = make_ygo_trap(
    "Wandering Negation", ygo_trap_type="Counter",
    text="When activated in a chain: negate the activation of 1 Spell/Trap "
         "and destroy it. Chain timing simplification: emit a "
         "negate_spell_trap_and_destroy marker.",
    resolve=_wandering_negation_resolve,
)


def _reverberate_resolve(event, state):
    """Counter Trap: copy the effect of 1 just-resolved Spell/Trap.

    Simplification: emit a chain-link 'copy_effect' marker for the engine to
    pick up where the chain machinery exists, otherwise a no-op.
    """
    return [Event(type=EventType.YGO_CHAIN_LINK,
                  payload={'effect': 'copy_effect',
                           'controller': event.payload.get('player')})]


REVERBERATE = make_ygo_trap(
    "Reverberate", ygo_trap_type="Counter",
    text="Copy the effect of 1 Spell/Trap that just resolved on the field.",
    resolve=_reverberate_resolve,
)


def _mana_leak_resolve(event, state):
    """Counter Trap: negate 1 Spell unless opponent banishes 2 cards from GY.

    Simplification: opponent's GY auto-pays if it has 2+ cards (banish first
    two). Otherwise the negation goes through.
    """
    controller = event.payload.get('player')
    opp = _opp_id(state, controller) if controller else None
    if not opp:
        return [Event(type=EventType.YGO_CHAIN_LINK,
                      payload={'effect': 'negate_spell',
                               'controller': controller})]
    gy = state.zones.get(f"graveyard_{opp}")
    if gy and len(gy.objects) >= 2:
        # Pay the cost: banish two cards
        events = []
        for _ in range(2):
            cid = gy.objects.pop(0)
            cobj = state.objects.get(cid)
            if cobj:
                cobj.zone = ZoneType.EXILE
            events.append(Event(type=EventType.YGO_CHAIN_LINK,
                                payload={'effect': 'banish',
                                         'card_id': cid, 'controller': opp}))
        return events
    return [Event(type=EventType.YGO_CHAIN_LINK,
                  payload={'effect': 'negate_spell',
                           'controller': controller})]


MANA_LEAK = make_ygo_trap(
    "Mana Leak", ygo_trap_type="Counter",
    text="Negate the activation of 1 Spell unless your opponent banishes 2 "
         "cards from their GY.",
    resolve=_mana_leak_resolve,
)


def _cancel_resolve(event, state):
    """Counter Trap: negate 1 Spell or Trap activation."""
    return [Event(type=EventType.YGO_CHAIN_LINK,
                  payload={'effect': 'negate_spell_trap',
                           'controller': event.payload.get('player')})]


CANCEL = make_ygo_trap(
    "Cancel", ygo_trap_type="Counter",
    text="When activated in a chain: negate the activation of 1 Spell or Trap. "
         "Chain timing simplification: emit a negate_spell_trap marker.",
    resolve=_cancel_resolve,
)


def _tide_of_knowledge_resolve(event, state):
    """Normal Trap: bounce 2 face-up monsters opponent controls; opponent draws 1.

    Phase 4: the controller (trap activator) picks WHICH 2 monsters to bounce
    from the opponent's board. Humans get a PendingChoice; AI heuristic
    preserves the old "first 2 face-up in zone order" behavior.

    Opponent's draw still fires unconditionally so the trap stays a net
    +1 information-trade.
    """
    from src.engine.pending_choice_helpers import create_choice_and_resolve

    controller = event.payload.get('player')
    if not controller:
        return []
    opp = _opp_id(state, controller)
    if not opp:
        return []

    # Collect all face-up opponent monsters as targetable options.
    targets: list[str] = _all_opp_face_up_monsters(state, controller)

    # Empty short-circuit: nothing to bounce. Opponent still draws 1.
    if not targets:
        if opp:
            return _draw(state, opp, 1)
        return []

    source_id = event.payload.get('card_id') or ''
    want = min(2, len(targets))

    options = []
    for tid in targets:
        cobj = state.objects.get(tid)
        if cobj is None or cobj.card_def is None:
            continue
        cdef = cobj.card_def
        atk = getattr(cdef, 'atk', None) or 0
        df = getattr(cdef, 'def_', None) if hasattr(cdef, 'def_') else getattr(cdef, 'defense', None)
        if df is None:
            df = 0
        options.append({"id": tid, "label": cobj.name,
                        "description": f"Monster · ATK/DEF {atk}/{df}"})

    if not options:
        if opp:
            return _draw(state, opp, 1)
        return []

    # Heuristic_pick: first N face-up opp monsters in zone order (old behavior).
    top_ids = [t for t in targets[:want]]

    def _resolve_handler(choice, selected, st):
        picked: list[str] = []
        for entry in selected or []:
            if isinstance(entry, dict):
                eid = entry.get("id")
                if eid is not None:
                    picked.append(eid)
            else:
                picked.append(entry)
        picked = picked[:want]

        out: list[Event] = []
        for tid in picked:
            out.extend(_bounce_monster_to_hand(st, tid))
        # Opponent draws 1 after the bounce.
        out.extend(_draw(st, opp, 1))
        return out

    return create_choice_and_resolve(
        state,
        choice_type="target",
        player_id=controller,
        prompt=f"Return {want} face-up monster(s) opponent controls to their hand.",
        options=options,
        source_id=source_id,
        min_choices=want,
        max_choices=want,
        handler=_resolve_handler,
        heuristic_pick=top_ids,
    )


TIDE_OF_KNOWLEDGE = make_ygo_trap(
    "Tide of Knowledge", ygo_trap_type="Normal",
    text="Return 2 face-up monsters opponent controls to their hands; "
         "your opponent draws 1 card.",
    resolve=_tide_of_knowledge_resolve,
)


def _foresight_sphinx_setup(obj, state):
    """Continuous Trap: once per turn, when opponent activates a Spell/Trap,
    pay 500 LP; negate it.

    Implemented as an interceptor on YGO_ACTIVATE events whose source is the
    opponent. Pays from controller's LP.
    """
    def _filter(event, state):
        if event.type not in (EventType.YGO_ACTIVATE_SPELL, EventType.YGO_ACTIVATE_TRAP):
            return False
        cid = event.payload.get('card_id')
        if not cid:
            return False
        cobj = state.objects.get(cid)
        if not cobj or cobj.controller == obj.controller:
            return False
        return True

    def _handler(event, state):
        player = state.players.get(obj.controller)
        if not player or player.lp < 500:
            return InterceptorResult(action=InterceptorAction.PASS)
        player.lp -= 500
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.YGO_CHAIN_LINK,
                payload={'effect': 'negate_spell_trap',
                         'card_id': event.payload.get('card_id'),
                         'controller': obj.controller,
                         'cost': 'pay_500_lp'},
            )],
        )

    return [Interceptor(id=new_id(), source=obj.id, controller=obj.controller,
                        priority=InterceptorPriority.REACT, filter=_filter,
                        handler=_handler, duration='until_leaves')]


FORESIGHT_SPHINX = make_ygo_trap(
    "Foresight Sphinx", ygo_trap_type="Continuous",
    text="Once per turn, when your opponent activates a Spell/Trap: pay 500 LP; "
         "negate that activation.",
    setup_interceptors=_foresight_sphinx_setup,
)


# =============================================================================
# Card definitions — Extra Deck
# =============================================================================

# Pendulum monster doubles as Extra Deck and Main Deck — we register only once
# and place it in the Extra Deck list.
TAMIYO_COMPLEATED_SAGE = make_ygo_monster(
    "Tamiyo, Compleated Sage", atk=2500, def_val=2500, level=7,
    attribute="WATER", ygo_monster_type="Pendulum",
    subtypes={"Spellcaster", "Moonfolk"},
    pendulum_scale=9,
    text="Pendulum: Once per turn, when a Continuous Spell is activated: draw "
         "1 card. Effect: target 1 Spell in your GY; add it to your hand.",
    setup_interceptors=_tamiyo_compleated_setup,
)


def _patron_synchro_setup(obj, state):
    """When SS: bounce all face-up monsters opponent controls."""
    def effect_fn(o, state):
        events = []
        for tid in _all_opp_face_up_monsters(state, o.controller):
            events.extend(_bounce_monster_to_hand(state, tid))
        return events
    return [make_ygo_summon_trigger(obj, effect_fn)]


PATRON_OF_THE_MOON = make_ygo_monster(
    "Patron of the Moon", atk=2700, def_val=2400, level=8,
    attribute="WATER", ygo_monster_type="Synchro",
    subtypes={"Spellcaster", "Moonfolk"},
    materials="1 Tuner + 1+ non-Tuner 'Moonfolk' monsters",
    text="1 Tuner + 1+ non-Tuner 'Moonfolk'. When Synchro Summoned: return all "
         "face-up monsters opponent controls to their hands.",
    setup_interceptors=_patron_synchro_setup,
)


def _saheeli_gifted_setup(obj, state):
    """Link 3: monsters this card points to gain 500 ATK."""
    def modifier_fn(event, state):
        if event.type != EventType.QUERY_POWER:
            return InterceptorResult(action=InterceptorAction.PASS)
        target_id = event.payload.get('object_id')
        if not target_id:
            return InterceptorResult(action=InterceptorAction.PASS)
        # Simplified: any Spellcaster or Moonfolk you control gets +500 while
        # this Link monster is on the field.
        target = state.objects.get(target_id)
        if not target or target.controller != obj.controller:
            return InterceptorResult(action=InterceptorAction.PASS)
        if target.id == obj.id:
            return InterceptorResult(action=InterceptorAction.PASS)
        if not _is_moonfolk(target):
            return InterceptorResult(action=InterceptorAction.PASS)
        event.payload['value'] = event.payload.get('value', 0) + 500
        return InterceptorResult(action=InterceptorAction.TRANSFORM,
                                 transformed_event=event)
    return [make_ygo_continuous_effect(obj, modifier_fn)]


SAHEELI_THE_GIFTED = make_ygo_monster(
    "Saheeli, the Gifted", atk=2400, def_val=0, level=3,
    attribute="WIND", ygo_monster_type="Link", link_rating=3,
    link_arrows=["left", "bottom_left", "right"],
    subtypes={"Spellcaster", "Moonfolk"},
    materials="3 Spellcaster monsters",
    text="3 Spellcaster monsters. Monsters this card points to gain 500 ATK.",
    setup_interceptors=_saheeli_gifted_setup,
)


def _otawara_setup(obj, state):
    """Synchro Lv 6: when SS, bounce 1 face-up card on the field."""
    def effect_fn(o, state):
        # Try opponent's monsters first, then opponent's spells/traps.
        target = _first_opp_face_up_monster(state, o.controller)
        if target:
            return _bounce_monster_to_hand(state, target)
        target = _first_face_up_spell_trap(state, o.controller, own=False)
        if target:
            return _bounce_spell_trap_to_hand(state, target)
        return []
    return [make_ygo_summon_trigger(obj, effect_fn)]


OTAWARA_SOARING_CITY = make_ygo_monster(
    "Otawara, Soaring City", atk=2300, def_val=2300, level=6,
    attribute="WATER", ygo_monster_type="Synchro",
    subtypes={"Wing Beast", "Moonfolk"},
    materials="1 Tuner + 1+ non-Tuner 'Moonfolk' monsters",
    text="1 Tuner + 1+ non-Tuner 'Moonfolk'. When Synchro Summoned: return 1 "
         "face-up card on the field to its owner's hand.",
    setup_interceptors=_otawara_setup,
)


def _higure_setup(obj, state):
    """Xyz Rank 4: detach 1 material; opponent reveals their hand; pick 1 to
    bounce to the top of their Deck.

    Simplified: detach 1 material; bounce the first card in opponent's hand
    to the top of their Deck.
    """
    def effect_fn(o, state):
        if not o.state.overlay_units:
            return []
        detached = o.state.overlay_units.pop(0)
        gy = state.zones.get(f"graveyard_{o.controller}")
        if gy is not None:
            gy.objects.append(detached)
        opp = _opp_id(state, o.controller)
        if not opp:
            return []
        opp_hand = state.zones.get(f"hand_{opp}")
        lib = state.zones.get(f"library_{opp}")
        if not opp_hand or not lib or not opp_hand.objects:
            return []
        cid = opp_hand.objects.pop(0)
        lib.objects.insert(0, cid)
        cobj = state.objects.get(cid)
        if cobj:
            cobj.zone = ZoneType.LIBRARY
        return [Event(type=EventType.YGO_CHAIN_LINK,
                      payload={'effect': 'top_of_deck',
                               'card_id': cid, 'controller': opp})]
    return [make_ygo_ignition_effect(obj, effect_fn)]


HIGURE_MIRROR_REFLECTION = make_ygo_monster(
    "Higure, Mirror Reflection", atk=2400, def_val=2200, level=4,
    attribute="WATER", ygo_monster_type="Xyz", rank=4,
    subtypes={"Spellcaster", "Moonfolk"},
    materials="2 Lv 4 'Moonfolk' monsters",
    text="2 Lv 4 'Moonfolk'. Detach 1 material: opponent reveals their hand; "
         "pick 1 card to return to the top of their Deck.",
    setup_interceptors=_higure_setup,
)


_PASS3_TEXT_APPENDIX = {
    "Reverberate": "Chain timing simplification: when activated after a Spell or Trap resolves, emit a copy_effect chain marker using this card as the controller.",
    "Eye of Nowhere": "Resolution simplification: target the first face-up opponent Spell or Trap if possible; otherwise return your first face-up Spell or Trap to its owner's hand.",
    "Mana Leak": "Counter rule: the opponent automatically banishes two cards from their GY if able; if they cannot pay, emit a negate_spell marker.",
    "Vapor Snag": "Resolution simplification: return the first face-up opponent monster to its owner's hand, then that opponent loses 200 LP.",
    "Tide of Knowledge": "Resolution simplification: return up to two face-up opponent monsters to their owners' hands, then your opponent draws one card.",
    "Saheeli, the Gifted": "Link layer: while this card is face-up, the monster it points to gains 500 ATK through the stat query layer.",
    "Brainstorm": "Resolution simplification: draw three cards from the top of your Deck, then place the last two cards from your hand back on top.",
    "Reality Chip Bearer": "Summon trigger: when Normal Summoned, draw one card and keep this card tagged as both Moonfolk and Modified for cross-archetype support.",
    "Soratami Savant": "Summon trigger: when Normal Summoned, search your Deck for the first Moonfolk card other than itself and add it to your hand.",
}

for _pass3_card in list(globals().values()):
    _pass3_note = _PASS3_TEXT_APPENDIX.get(getattr(_pass3_card, "name", None))
    if _pass3_note and _pass3_note not in (_pass3_card.text or ""):
        _pass3_card.text = f"{_pass3_card.text} {_pass3_note}"


# =============================================================================
# Set registry
# =============================================================================

BEYOND_KAMIGAWA_MOONFOLK = {card.name: card for card in [
    # Monsters (13 main-deck unique cards)
    TIDE_STAR_ACOLYTE, CLOUD_CUCKOO_LAND, SORATAMI_SAVANT,
    SORATAMI_MIRROR_GUARD, EYE_OF_NOWHERE_DIVINER, SORATAMI_CLOUDSKATER,
    SORATAMI_MIRROR_MAGE, MISDIRECTION_MASTER, REALITY_CHIP_BEARER,
    REFLECT_LORD, THE_WANDERING_EMPEROR_MOONFOLK, TAMIYO_FIELD_RESEARCHER,
    MELOKU_THE_CLOUDED_MIRROR,
    # Spells (10)
    HINDER, EYE_OF_NOWHERE, BOOMERANG, VAPOR_SNAG, PATH_OF_SHADOWS,
    REALITY_STUTTER, MIRROR_REALM, BRAINSTORM, COUNTERSPELL_LITE,
    RESOUNDING_ROAR,
    # Traps (6)
    WANDERING_NEGATION, REVERBERATE, MANA_LEAK, CANCEL,
    TIDE_OF_KNOWLEDGE, FORESIGHT_SPHINX,
    # Extra Deck (5)
    TAMIYO_COMPLEATED_SAGE, PATRON_OF_THE_MOON, SAHEELI_THE_GIFTED,
    OTAWARA_SOARING_CITY, HIGURE_MIRROR_REFLECTION,
]}


# =============================================================================
# Pre-built deck — 40 main + 5 extra
# =============================================================================

def make_moonfolk_deck() -> tuple[list, list]:
    """Soratami Moonfolk — 40 main + 5 extra. Bounce + Counter Trap control.

    Tuned 2026-05-02 (round 2): the deck's identity is Counter Traps but
    their negate effects emit chain-link markers the engine doesn't yet
    consume. Round 1 added Wrath/Bolt; round 2 goes further — replaces
    most of the broken-Counter-Trap suite with real removal/draw staples
    plus a second board wipe and Demonic Tutor for the Patron of the Moon
    finisher. Keeps two Counter Traps for archetype flavor.

    Tuned 2026-05-10: after strategy-aware YGO wet tests, trimmed the
    remaining mostly-unmodeled Counter Trap package and moved that space into
    Ponder plus Doom Blade. The deck still plays as control, but more of its
    slots now convert into engine-visible draw/removal.
    """
    from src.cards.yugioh.beyond.kamigawa.staples import (
        WRATH_OF_GOD, DAY_OF_JUDGMENT, LIGHTNING_BOLT,
        EMPYRIAL_PLATE, DEMONIC_TUTOR, FACT_OR_FICTION,
        PONDER, DOOM_BLADE,
    )
    main = (
        # Monsters (15) — trimmed weakest, kept ace + finisher
        [SORATAMI_SAVANT] * 2 +
        [SORATAMI_MIRROR_GUARD] * 2 +
        [EYE_OF_NOWHERE_DIVINER] * 1 +
        [SORATAMI_CLOUDSKATER] * 2 +
        [SORATAMI_MIRROR_MAGE] * 2 +
        [REFLECT_LORD] * 2 +
        [TAMIYO_FIELD_RESEARCHER] * 1 +     # Tuner
        [MELOKU_THE_CLOUDED_MIRROR] * 1 +
        [SORATAMI_SAVANT] * 0 +              # placeholder for sum-readability
        [MISDIRECTION_MASTER] * 2 +
        # Spells (20) — heavy real-interaction package
        [WRATH_OF_GOD] * 2 +
        [DAY_OF_JUDGMENT] * 1 +              # +1 — second board wipe
        [LIGHTNING_BOLT] * 3 +               # max copies
        [EMPYRIAL_PLATE] * 1 +
        [DEMONIC_TUTOR] * 1 +                # +1 — find Patron / Meloku
        [FACT_OR_FICTION] * 1 +              # +1 — drawback engine
        [PONDER] * 2 +                       # +2 — early smoothing
        [DOOM_BLADE] * 1 +                   # +1 — reliable spot removal
        [HINDER] * 2 +
        [EYE_OF_NOWHERE] * 2 +
        [VAPOR_SNAG] * 2 +
        [PATH_OF_SHADOWS] * 2 +
        [BRAINSTORM] * 2 +
        [COUNTERSPELL_LITE] * 1 +            # was 2 — half flavor, half function
        # Traps (2) — only the engine-visible bounce trap remains
        [TIDE_OF_KNOWLEDGE] * 2
    )
    extra = [
        TAMIYO_COMPLEATED_SAGE,
        PATRON_OF_THE_MOON,
        SAHEELI_THE_GIFTED,
        OTAWARA_SOARING_CITY,
        HIGURE_MIRROR_REFLECTION,
    ]
    return (main, extra)


__all__ = ["BEYOND_KAMIGAWA_MOONFOLK", "make_moonfolk_deck"]
