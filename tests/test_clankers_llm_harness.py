"""Regression tests for Wave-5 follow-up findings.

Covers:
1. Harness ``_translate`` returns errors for malformed slot-index payloads
   (used to silently drop into {} / [] / pass, which masked agent bugs).
2. Solo unattached parts CAN block — combat applies damage to the solo
   blocker, not unblocked-to-Core. The Wave-5 BULWARK agent thought solos
   couldn't block; really, the harness was dropping their block decls due
   to slot-string protocol confusion.
3. Repair Subroutine readies exhausted add-ons (does NOT heal damage).

All tests use the in-process engine — no subprocess, no LLM, no FastAPI.
"""

from __future__ import annotations

import pytest

from src.cards.clankers.CLAN.clan_bulwark import REPAIR_SUBROUTINE
from src.engine.clankers import (
    CLANKERS_SOLO_PART_INTEGRITY,
    CLANKERS_SOLO_PART_POWER,
    compute_effective_power,
    compute_effective_integrity,
)
from src.engine.types import Event, EventType


def test_translate_choose_blockers_rejects_garbage_strings():
    """The Wave-5 BULWARK agent submitted obj_ids as attacker_slot. With
    the new fix: valid obj_ids coerce to slots (silent success — agent
    was just sloppy), but BAD strings (non-matching) raise 422 instead
    of silently dropping into {}."""
    from scripts.play.clankers_local_match import _translate

    pending = {
        "attacker_ids": ["obj_atk_1", "obj_atk_2"],
        "defenders": [{"id": "obj_def_1"}, {"id": "obj_def_2"}],
    }
    # Bad: completely bogus strings.
    value = {"blocks": [{"attacker_slot": "nope", "blocker_slot": "garbage"}]}
    translated, errors = _translate("choose_blockers", pending, value)
    assert errors, "should reject unrecognized strings"
    assert translated == {}


def test_translate_choose_blockers_obj_id_fallback():
    """Convenience: if an agent submits an obj_id (string matching a
    candidate), the harness still coerces it to the right slot."""
    from scripts.play.clankers_local_match import _translate

    pending = {
        "attacker_ids": ["obj_atk_1", "obj_atk_2"],
        "defenders": [{"id": "obj_def_1"}, {"id": "obj_def_2"}],
    }
    # All obj_ids — should coerce silently.
    value = {"blocks": [{"attacker_slot": "obj_atk_1", "blocker_slot": "obj_def_2"}]}
    translated, errors = _translate("choose_blockers", pending, value)
    assert not errors, f"valid obj_ids should coerce: {errors}"
    assert translated == {"obj_atk_1": "obj_def_2"}


def test_translate_choose_blockers_accepts_int_slots():
    from scripts.play.clankers_local_match import _translate

    pending = {
        "attacker_ids": ["obj_atk_1", "obj_atk_2"],
        "defenders": [{"id": "obj_def_1"}, {"id": "obj_def_2"}],
    }
    value = {"blocks": [{"attacker_slot": 1, "blocker_slot": 2}]}
    translated, errors = _translate("choose_blockers", pending, value)
    assert not errors, f"integer slots should validate: {errors}"
    assert translated == {"obj_atk_1": "obj_def_2"}


def test_translate_choose_blockers_out_of_range():
    from scripts.play.clankers_local_match import _translate

    pending = {
        "attacker_ids": ["obj_atk_1"],
        "defenders": [{"id": "obj_def_1"}],
    }
    value = {"blocks": [{"attacker_slot": 99, "blocker_slot": 1}]}
    translated, errors = _translate("choose_blockers", pending, value)
    assert errors, "out-of-range slot should error"


def test_translate_choose_attackers_accepts_obj_id_fallback():
    """A nice agent UX: submitting `obj_id` instead of slot still works."""
    from scripts.play.clankers_local_match import _translate

    pending = {
        "candidates": [{"id": "obj_a"}, {"id": "obj_b"}, {"id": "obj_c"}],
    }
    value = {"slots": ["obj_a", "obj_c"]}
    translated, errors = _translate("choose_attackers", pending, value)
    assert not errors, f"obj_id strings should coerce: {errors}"
    assert translated == ["obj_a", "obj_c"]


def test_translate_choose_assemble_action_returns_errors():
    """Bad input now surfaces — Wave-5 silent drop converted to pass with
    an error, not bare pass."""
    from scripts.play.clankers_local_match import _translate

    pending = {"raw_legal": [
        {"action": "play_chassis", "card_obj_id": "obj1", "compute_cost": 2},
        {"action": "pass"},
    ]}
    # Slot out of range.
    translated, errors = _translate("choose_assemble_action", pending, {"slot": 99})
    assert errors
    assert translated == {"action": "pass"}


def test_solo_part_can_block_baseline():
    """A solo weapon/add-on has CLANKERS_SOLO_PART_INTEGRITY and is a legal
    blocker. The Wave-5 BULWARK agent thought solos couldn't block, but
    the engine validates them — the issue was harness translation."""
    from src.cards.clankers.CLAN.clan_forge import HEAVY_ASSEMBLY as TEST_CHASSIS
    from src.cards.clankers.CLAN.clan_mirth import SCOUT_DRONE  # Self-Mobile weapon
    from src.engine.clankers_combat import ClankersCombatManager

    cm = ClankersCombatManager.__new__(ClankersCombatManager)
    cm.game = None
    cm.state = None

    # Mock a minimal state with one chassis and one solo weapon on the
    # Assembly Floor, both controlled by the same player.
    from src.engine.types import GameState, GameObject, ObjectState, Characteristics, ZoneType
    state = GameState()
    chassis_id = "test_chassis"
    solo_id = "test_solo"
    state.objects[chassis_id] = GameObject(
        id=chassis_id, name="ChassisDef", owner="p2", controller="p2",
        zone=ZoneType.CLANKERS_ASSEMBLY_FLOOR,
        characteristics=Characteristics(types=TEST_CHASSIS.characteristics.types),
        card_def=TEST_CHASSIS,
        state=ObjectState(tapped=False, damage_marked=0, attached_to=None),
    )
    state.objects[solo_id] = GameObject(
        id=solo_id, name="ScoutDef", owner="p2", controller="p2",
        zone=ZoneType.CLANKERS_ASSEMBLY_FLOOR,
        characteristics=Characteristics(types=SCOUT_DRONE.characteristics.types),
        card_def=SCOUT_DRONE,
        state=ObjectState(tapped=False, damage_marked=0, attached_to=None),
    )
    cm.state = state

    # The chassis is on the floor → tracked in clankers_assemblies.
    state.clankers_assemblies = {"p2": [chassis_id]}  # type: ignore[attr-defined]

    # Both should validate as blockers for "p2".
    assert cm._validate_blocker(state, chassis_id, "p2")
    assert cm._validate_blocker(state, solo_id, "p2"), \
        "Solo unattached weapon should validate as a legal blocker"


def test_solo_part_integrity_baseline():
    """A solo part takes at most CLANKERS_SOLO_PART_INTEGRITY damage before
    dying. Verifies the engine's solo-part baseline is what production
    expects."""
    assert CLANKERS_SOLO_PART_POWER == 1
    assert CLANKERS_SOLO_PART_INTEGRITY == 1


def test_repair_subroutine_text_says_ready_not_heal():
    """Documentation/regression: Repair Subroutine readies exhausted add-ons.
    It does NOT heal chassis damage. (Wave-5 BULWARK agent expected heal.)"""
    assert "Ready up to 2 exhausted add-ons" in REPAIR_SUBROUTINE.text
    assert "heal" not in REPAIR_SUBROUTINE.text.lower()
    assert "damage" not in REPAIR_SUBROUTINE.text.lower()


def test_repair_subroutine_readies_exhausted_addons():
    """Functional verification: passing tapped add-ons through Repair
    Subroutine sets state.tapped=False on up to 2 of them."""
    from src.cards.clankers.CLAN.clan_bulwark import _repair_subroutine_resolve
    from src.cards.clankers.CLAN.clan_bulwark import REACTIVE_SHIELDING
    from src.engine.types import GameState, GameObject, ObjectState, Characteristics, ZoneType

    state = GameState()
    # Build 3 exhausted add-ons (we should ready only 2).
    addon_ids = []
    for i in range(3):
        oid = f"addon_{i}"
        state.objects[oid] = GameObject(
            id=oid, name=f"A{i}", owner="p1", controller="p1",
            zone=ZoneType.CLANKERS_ASSEMBLY_FLOOR,
            characteristics=Characteristics(types=REACTIVE_SHIELDING.characteristics.types),
            card_def=REACTIVE_SHIELDING,
            state=ObjectState(tapped=True, damage_marked=0, attached_to=None),
        )
        addon_ids.append(oid)

    event = Event(
        type=EventType.CLANKERS_CORE_PASSIVE,  # placeholder
        payload={"controller": "p1"},
        controller="p1",
    )
    events = _repair_subroutine_resolve(event, state)
    # Should have readied exactly 2 of the 3 add-ons.
    readied = [oid for oid in addon_ids if not state.objects[oid].state.tapped]
    assert len(readied) == 2, f"expected 2 readied, got {len(readied)}"
    # The unreadied one should still be tapped.
    still_tapped = [oid for oid in addon_ids if state.objects[oid].state.tapped]
    assert len(still_tapped) == 1


def test_repair_subroutine_does_not_heal_damage():
    """Verify Repair Subroutine doesn't touch damage_marked."""
    from src.cards.clankers.CLAN.clan_bulwark import _repair_subroutine_resolve
    from src.cards.clankers.CLAN.clan_bulwark import REACTIVE_SHIELDING
    from src.cards.clankers.CLAN.clan_forge import HEAVY_ASSEMBLY as TEST_CHASSIS
    from src.engine.types import GameState, GameObject, ObjectState, Characteristics, ZoneType

    state = GameState()
    # A damaged chassis.
    chassis_id = "chassis_dmg"
    state.objects[chassis_id] = GameObject(
        id=chassis_id, name="Hurt", owner="p1", controller="p1",
        zone=ZoneType.CLANKERS_ASSEMBLY_FLOOR,
        characteristics=Characteristics(types=TEST_CHASSIS.characteristics.types),
        card_def=TEST_CHASSIS,
        state=ObjectState(tapped=False, damage_marked=5, attached_to=None),
    )
    # An exhausted add-on (to give Repair Subroutine something to do).
    addon_id = "addon_exh"
    state.objects[addon_id] = GameObject(
        id=addon_id, name="Plate", owner="p1", controller="p1",
        zone=ZoneType.CLANKERS_ASSEMBLY_FLOOR,
        characteristics=Characteristics(types=REACTIVE_SHIELDING.characteristics.types),
        card_def=REACTIVE_SHIELDING,
        state=ObjectState(tapped=True, damage_marked=0, attached_to=chassis_id),
    )

    event = Event(type=EventType.CLANKERS_CORE_PASSIVE,
                  payload={"controller": "p1"}, controller="p1")
    _repair_subroutine_resolve(event, state)

    # Add-on readied, chassis damage UNCHANGED.
    assert state.objects[addon_id].state.tapped is False
    assert state.objects[chassis_id].state.damage_marked == 5, \
        "Repair Subroutine should not heal chassis damage"
