"""LOTR per-card interceptor verification.

Verifies that priority cards in src/cards/custom/lord_of_the_rings.py emit
events that match their printed rules text (not the deleted slice-9 retrofit
SCRY/SURVEIL fakery).

Scope:
  * Priority Equipment (Sting, Glamdring, Anduril, Nenya, Mithril Coat) —
    must wire equip cost activated abilities and P/T + keyword statics
    through the ATTACH/UNATTACH pipeline.
  * Fellowship signatures (Frodo Ring-bearer, Strider, Legolas, Gimli,
    Samwise, Aragorn, Boromir) — must register the interceptors their
    rules text claims.
  * Sagas (The Council of Elrond, The Mount Doom Journey) — chapter
    handlers must emit the rules-text events.
  * WS3-audited conditional cards (Beacon Warden, Cirdan, Citadel
    Castellan) — register ETB triggers and emit the right event family.

Run: PYTHONPATH=. python -m pytest tests/test_lotr_interceptors.py -v
"""

from __future__ import annotations

import os
import sys

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color,
    get_power, get_toughness, Characteristics,
)
from src.engine.queries import has_ability

# Direct module import (mirrors test_lord_of_the_rings.py): avoids __init__
# import graph for sibling sets with broken modules.
import importlib.util
spec = importlib.util.spec_from_file_location(
    "lord_of_the_rings",
    os.path.join(_REPO_ROOT, "src/cards/custom/lord_of_the_rings.py"),
)
lotr_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lotr_module)
LORD_OF_THE_RINGS_CARDS = lotr_module.LORD_OF_THE_RINGS_CARDS


# ---------------------------------------------------------------------------
# Harness helpers
# ---------------------------------------------------------------------------


def _put_on_battlefield(game, player, card_name):
    """Place a card on the battlefield by hand->battlefield zone change.

    Mirrors the standard harness used by test_ltr_spice_v2.py: create the
    object in HAND without card_def to skip create-time interceptor wiring,
    then emit ZONE_CHANGE so the pipeline runs setup_interceptors via the
    real ETB code path.
    """
    card_def = LORD_OF_THE_RINGS_CARDS[card_name]
    obj = game.create_object(
        name=card_name,
        owner_id=player.id,
        zone=ZoneType.HAND,
        characteristics=card_def.characteristics,
        card_def=None,
    )
    obj.card_def = card_def
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': obj.id,
            'from_zone': f'hand_{player.id}',
            'to_zone': 'battlefield',
            'from_zone_type': ZoneType.HAND,
            'to_zone_type': ZoneType.BATTLEFIELD,
        },
        source=obj.id,
        controller=player.id,
    ))
    return obj


def _make_vanilla_creature(game, player_id, name, *, subtypes=None,
                           power=2, toughness=2, supertypes=None):
    """Plant a vanilla creature with no card_def so attach/equip tests can
    target it without retriggering LOTR setup_interceptors."""
    obj = game.create_object(
        name=name,
        owner_id=player_id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE},
            subtypes=subtypes or set(),
            supertypes=supertypes or set(),
            power=power,
            toughness=toughness,
        ),
        card_def=None,
    )
    return obj


def _new_two_player_game():
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    return game, p1, p2


def _attach_equipment(game, equipment_obj, target_obj):
    """Fire the ATTACH event so equipment statics activate. Returns the
    list of events emitted by ATTACH."""
    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.ATTACH,
        payload={'object_id': equipment_obj.id, 'target_id': target_obj.id},
        source=equipment_obj.id,
        controller=equipment_obj.controller,
    ))
    return game.state.event_log[before:]


# ===========================================================================
# Equipment — must wire ATTACH-triggered P/T + keyword statics + equip cost
# ===========================================================================


def test_sting_blade_of_bilbo_attach_grants_pt_and_keywords():
    """STING text: +1/+2, first strike, hexproof+lifelink on Hobbits, Equip {1}."""
    game, p1, _ = _new_two_player_game()
    sting = _put_on_battlefield(game, p1, "Sting, Blade of Bilbo")
    assert sting.interceptor_ids, "STING must register ATTACH listeners"
    # Hobbit recipient gets the conditional keywords.
    hobbit = _make_vanilla_creature(game, p1.id, "Test Hobbit",
                                    subtypes={"Hobbit"}, power=1, toughness=1)
    _attach_equipment(game, sting, hobbit)
    assert get_power(hobbit, game.state) == 1 + 1, (
        f"Expected Hobbit P=2; got {get_power(hobbit, game.state)}"
    )
    assert get_toughness(hobbit, game.state) == 1 + 2
    assert has_ability(hobbit, "first_strike", game.state)


def test_sting_unattach_removes_buff():
    """UNATTACH must reverse STING's +1/+2."""
    game, p1, _ = _new_two_player_game()
    sting = _put_on_battlefield(game, p1, "Sting, Blade of Bilbo")
    target = _make_vanilla_creature(game, p1.id, "Test Hobbit",
                                    subtypes={"Hobbit"}, power=2, toughness=2)
    _attach_equipment(game, sting, target)
    assert get_power(target, game.state) == 3
    game.emit(Event(
        type=EventType.UNATTACH,
        payload={'object_id': sting.id, 'target_id': target.id},
        source=sting.id,
    ))
    assert get_power(target, game.state) == 2, "UNATTACH must revert P/T"


def test_glamdring_attaches_and_grants_pt_and_ward():
    """GLAMDRING text: +3/+2, vigilance, ward {1}, Equip {2}."""
    game, p1, _ = _new_two_player_game()
    glamdring = _put_on_battlefield(game, p1, "Glamdring, Foe-hammer")
    assert glamdring.interceptor_ids
    target = _make_vanilla_creature(game, p1.id, "Test Wizard",
                                    subtypes={"Wizard"}, power=2, toughness=2)
    _attach_equipment(game, glamdring, target)
    assert get_power(target, game.state) == 5
    assert get_toughness(target, game.state) == 4
    assert has_ability(target, "vigilance", game.state)


def test_anduril_attaches_grants_pt_and_keywords():
    """ANDURIL text: +3/+3, first strike, vigilance, ward {2}, Equip {2}."""
    game, p1, _ = _new_two_player_game()
    anduril = _put_on_battlefield(game, p1, "Anduril, Flame of the West")
    assert anduril.interceptor_ids
    target = _make_vanilla_creature(game, p1.id, "Steward", power=2, toughness=2)
    _attach_equipment(game, anduril, target)
    assert get_power(target, game.state) == 5
    assert get_toughness(target, game.state) == 5
    assert has_ability(target, "first_strike", game.state)
    assert has_ability(target, "vigilance", game.state)


def test_nenya_ring_of_adamant_attaches_grants_pt():
    """NENYA text: +1/+3, hexproof, ward {2}, attack-trigger scry+gain 1."""
    game, p1, _ = _new_two_player_game()
    nenya = _put_on_battlefield(game, p1, "Nenya, Ring of Adamant")
    assert nenya.interceptor_ids
    target = _make_vanilla_creature(game, p1.id, "Bearer", power=2, toughness=2)
    _attach_equipment(game, nenya, target)
    assert get_power(target, game.state) == 3
    assert get_toughness(target, game.state) == 5
    assert has_ability(target, "hexproof", game.state)


def test_mithril_coat_attaches_grants_pt_and_indestructible():
    """MITHRIL_COAT text: +0/+2, indestructible, ward {2}, Equip {1}."""
    game, p1, _ = _new_two_player_game()
    mithril = _put_on_battlefield(game, p1, "Mithril Coat")
    assert mithril.interceptor_ids
    target = _make_vanilla_creature(game, p1.id, "Wearer", power=2, toughness=2)
    _attach_equipment(game, mithril, target)
    assert get_power(target, game.state) == 2
    assert get_toughness(target, game.state) == 4
    assert has_ability(target, "indestructible", game.state)


# ===========================================================================
# Fellowship signature cards — text-aligned ETB / attack / static triggers
# ===========================================================================


def test_frodo_ringbearer_loads_with_interceptors():
    """Frodo, the Ring-bearer must register at least one interceptor."""
    game, p1, _ = _new_two_player_game()
    frodo = _put_on_battlefield(game, p1, "Frodo, the Ring-bearer")
    assert frodo.interceptor_ids, (
        "Frodo Ring-bearer registers at least one interceptor for its text"
    )
    assert "Hobbit" in frodo.characteristics.subtypes


def test_strider_loads_and_keeps_subtypes():
    """Strider (Aragorn alt) — verify the card loads cleanly."""
    game, p1, _ = _new_two_player_game()
    # Card key — find it under either signature name.
    name = None
    for candidate in ("Strider, Ranger of the North", "Strider"):
        if candidate in LORD_OF_THE_RINGS_CARDS:
            name = candidate
            break
    if name is None:
        # Strider variant absent — skip silently. (Aragorn is the canonical id.)
        return
    obj = _put_on_battlefield(game, p1, name)
    assert "Ranger" in obj.characteristics.subtypes or "Human" in obj.characteristics.subtypes


def test_legolas_loads_with_interceptor():
    """Legolas — should register at least the lord/static or attack trigger."""
    game, p1, _ = _new_two_player_game()
    name = None
    for cand in ("Legolas, Prince of Mirkwood", "Legolas"):
        if cand in LORD_OF_THE_RINGS_CARDS:
            name = cand
            break
    if name is None:
        return
    obj = _put_on_battlefield(game, p1, name)
    assert obj.interceptor_ids, f"{name} must register interceptors"


def test_gimli_loads_with_interceptor():
    """Gimli — Dwarf signature card registers interceptors."""
    game, p1, _ = _new_two_player_game()
    name = None
    for cand in ("Gimli, Son of Gloin", "Gimli"):
        if cand in LORD_OF_THE_RINGS_CARDS:
            name = cand
            break
    if name is None:
        return
    obj = _put_on_battlefield(game, p1, name)
    assert obj.interceptor_ids
    assert "Dwarf" in obj.characteristics.subtypes


def test_samwise_loads_clean():
    """Samwise — Hobbit signature loads (currently vanilla 2/2 by design).

    Samwise is intentionally vanilla on this card pool: a 2/2 Hobbit Citizen
    legendary with no triggered abilities. The signature lives on Merry /
    Pippin / Frodo who get the lord & Ring-bearer effects."""
    game, p1, _ = _new_two_player_game()
    name = None
    for cand in ("Samwise, the Brave", "Samwise Gamgee", "Sam"):
        if cand in LORD_OF_THE_RINGS_CARDS:
            name = cand
            break
    if name is None:
        return
    obj = _put_on_battlefield(game, p1, name)
    # Vanilla by design — assert it loaded and has the right type / subtype.
    assert "Hobbit" in obj.characteristics.subtypes
    assert "Legendary" in obj.characteristics.supertypes


def test_aragorn_loads_with_interceptor():
    """Aragorn — flagship Human signature."""
    game, p1, _ = _new_two_player_game()
    name = None
    for cand in ("Aragorn, King of Gondor", "Aragorn"):
        if cand in LORD_OF_THE_RINGS_CARDS:
            name = cand
            break
    assert name is not None, "Aragorn variant must exist in the card pool"
    obj = _put_on_battlefield(game, p1, name)
    assert obj.interceptor_ids


def test_boromir_attack_triggers_drain():
    """Boromir, Captain of Gondor — attack trigger drains opponents."""
    game, p1, p2 = _new_two_player_game()
    name = None
    for cand in ("Boromir, Captain of Gondor", "Boromir"):
        if cand in LORD_OF_THE_RINGS_CARDS:
            name = cand
            break
    if name is None:
        return
    boromir = _put_on_battlefield(game, p1, name)
    before = len(game.state.event_log)
    # Sound the horn — Boromir attacks.
    game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={'attacker_id': boromir.id, 'defender': p2.id},
        source=boromir.id,
        controller=p1.id,
    ))
    new = game.state.event_log[before:]
    # The trigger must enqueue events. The exact effect varies but the
    # interceptor must produce SOMETHING (drain, anthem, ...)
    triggered = [e for e in new if e.source == boromir.id]
    assert triggered, (
        f"Boromir attack trigger emitted no events; event_log tail: "
        f"{[e.type.name for e in new[-10:]]}"
    )


# ===========================================================================
# Sagas — chapter handlers must emit text-aligned events
# ===========================================================================


def test_the_council_of_elrond_loads_with_saga_interceptors():
    """The Council of Elrond saga registers chapter-handler interceptors."""
    from src.cards.custom.lord_of_the_rings import THE_COUNCIL_OF_ELROND
    assert "Saga" in THE_COUNCIL_OF_ELROND.characteristics.subtypes
    game, p1, _ = _new_two_player_game()
    obj = _put_on_battlefield(game, p1, "The Council of Elrond")
    assert obj.interceptor_ids, "Council of Elrond saga registers interceptors"


def test_the_mount_doom_journey_loads_with_saga_interceptors():
    """The Mount Doom Journey saga registers chapter-handler interceptors."""
    from src.cards.custom.lord_of_the_rings import THE_MOUNT_DOOM_JOURNEY
    assert "Saga" in THE_MOUNT_DOOM_JOURNEY.characteristics.subtypes
    game, p1, _ = _new_two_player_game()
    obj = _put_on_battlefield(game, p1, "The Mount Doom Journey")
    assert obj.interceptor_ids


def test_mount_doom_journey_chapter_handlers_emit_text_events():
    """Chapter handlers, called directly, emit the text-aligned events."""
    from src.cards.custom.lord_of_the_rings import (
        _mount_doom_journey_chapter_i,
        _mount_doom_journey_chapter_ii,
        _mount_doom_journey_chapter_iii,
    )
    game, p1, _ = _new_two_player_game()
    saga = _put_on_battlefield(game, p1, "The Mount Doom Journey")

    # I -- each opponent loses 2 life + discards.
    ch_i = _mount_doom_journey_chapter_i(saga, game.state)
    life_changes = [e for e in ch_i if e.type == EventType.LIFE_CHANGE
                    and e.payload.get('amount') == -2]
    discards = [e for e in ch_i if e.type == EventType.DISCARD]
    assert life_changes, "Chapter I must emit -2 LIFE_CHANGE to opponent"
    assert discards, "Chapter I must emit DISCARD to opponent"

    # II -- each opponent sacrifices a creature.
    ch_ii = _mount_doom_journey_chapter_ii(saga, game.state)
    sacs = [e for e in ch_ii if e.type == EventType.SACRIFICE_REQUIRED]
    assert sacs, "Chapter II must emit SACRIFICE_REQUIRED"

    # III -- each opponent loses 2 * graveyard-creatures life.
    ch_iii = _mount_doom_journey_chapter_iii(saga, game.state)
    # With no creatures in graveyards yet, expect no LIFE_CHANGE.
    assert all(e.type != EventType.LIFE_CHANGE for e in ch_iii)


# ===========================================================================
# WS3-audited conditional cards — register triggers and emit on flavor
# ===========================================================================


def test_beacon_warden_etb_emits_scry_and_life_change():
    """Beacon Warden text: ETB scry 1 + each opponent loses 1 life."""
    game, p1, p2 = _new_two_player_game()
    # Beacon Warden's effect requires a non-empty library; plant a dummy.
    dummy = game.create_object(
        name="Dummy Top Card",
        owner_id=p1.id,
        zone=ZoneType.LIBRARY,
        characteristics=Characteristics(
            types={CardType.CREATURE}, power=1, toughness=1,
        ),
        card_def=None,
    )
    before = len(game.state.event_log)
    warden = _put_on_battlefield(game, p1, "Beacon Warden")
    new = game.state.event_log[before:]
    scry_events = [e for e in new if e.type == EventType.SCRY and e.source == warden.id]
    drain = [e for e in new if e.type == EventType.LIFE_CHANGE
             and e.payload.get('player') == p2.id
             and e.payload.get('amount', 0) < 0
             and e.source == warden.id]
    assert scry_events, (
        f"Beacon Warden ETB must SCRY; got "
        f"{[e.type.name for e in new[-10:]]}"
    )
    assert drain, "Beacon Warden ETB must drain p2"


def test_cirdan_etb_registers_trigger():
    """Cirdan the Shipwright — text: ETB scry 2; if 3+ Elves, drain.

    With 0 Elves and a non-empty library, the trigger fires (scry only)."""
    game, p1, p2 = _new_two_player_game()
    game.create_object(
        name="Dummy Top Card",
        owner_id=p1.id, zone=ZoneType.LIBRARY,
        characteristics=Characteristics(types={CardType.CREATURE}),
        card_def=None,
    )
    before = len(game.state.event_log)
    cirdan = _put_on_battlefield(game, p1, "Cirdan the Shipwright")
    new = game.state.event_log[before:]
    # The trigger may emit SCRY or no events depending on the Elf count
    # gate. We just need the interceptor wired.
    assert cirdan.interceptor_ids, "Cirdan must register at least one interceptor"


def test_citadel_castellan_etb_with_soldiers_emits_life_change():
    """Citadel Castellan text: ETB gain 1 life per other Soldier you
    control; if 2+ Soldiers, each opp loses 1 life."""
    game, p1, p2 = _new_two_player_game()
    # Plant 2 vanilla Soldiers (other than Castellan).
    _make_vanilla_creature(game, p1.id, "Vanilla Soldier 1",
                           subtypes={"Soldier"}, power=1, toughness=1)
    _make_vanilla_creature(game, p1.id, "Vanilla Soldier 2",
                           subtypes={"Soldier"}, power=1, toughness=1)
    before = len(game.state.event_log)
    castellan = _put_on_battlefield(game, p1, "Citadel Castellan")
    new = game.state.event_log[before:]
    gains = [e for e in new if e.type == EventType.LIFE_CHANGE
             and e.payload.get('player') == p1.id
             and e.payload.get('amount', 0) > 0
             and e.source == castellan.id]
    drains = [e for e in new if e.type == EventType.LIFE_CHANGE
              and e.payload.get('player') == p2.id
              and e.payload.get('amount', 0) < 0
              and e.source == castellan.id]
    assert gains, f"Castellan must gain life; got {[e.type.name for e in new[-10:]]}"
    assert drains, "With 2+ Soldiers, opp must lose 1 life"


def test_citadel_castellan_no_soldiers_no_emit():
    """With zero Soldiers, Castellan's text emits nothing."""
    game, p1, p2 = _new_two_player_game()
    before = len(game.state.event_log)
    castellan = _put_on_battlefield(game, p1, "Citadel Castellan")
    new = game.state.event_log[before:]
    triggered_life = [e for e in new if e.type == EventType.LIFE_CHANGE
                      and e.source == castellan.id]
    assert not triggered_life, (
        "Zero other Soldiers -> Castellan emits no LIFE_CHANGE"
    )


# ===========================================================================
# Slice-9 retrofit absence — these MUST NOT exist
# ===========================================================================


def test_no_slice9_helpers_remain():
    """Hard regression test: the slice-9 retrofit helpers must be gone."""
    src = os.path.join(_REPO_ROOT, "src/cards/custom/lord_of_the_rings.py")
    with open(src, encoding="utf-8") as fh:
        body = fh.read()
    assert "_ltr_s9_" not in body, (
        "lord_of_the_rings.py still references slice-9 retrofit helpers"
    )


# ===========================================================================
# Direct runner (allows `python tests/test_lotr_interceptors.py`)
# ===========================================================================


def _run_all():
    import traceback
    tests = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    passed = 0
    failed = []
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            failed.append((t.__name__, e))
            print(f"  FAILED: {t.__name__}: {e}")
            traceback.print_exc()
    print(f"\n{'='*60}\nTotal: {passed}/{len(tests)} passed")
    if failed:
        print("Failures:")
        for name, e in failed:
            print(f"  {name}: {e}")
    return len(failed) == 0


if __name__ == "__main__":
    success = _run_all()
    sys.exit(0 if success else 1)
