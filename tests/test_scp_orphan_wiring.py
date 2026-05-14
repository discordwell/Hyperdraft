"""
Per-slot fire-proof tests for the previously-orphan ``scp_on_*`` hooks.

Each test constructs a card whose only mechanic is the slot under test
(bound to a counter-recording closure), drives the engine path that
should fire the slot, and asserts the counter incremented. If the
counter is still zero, the slot is still orphaned — the engine path
didn't reach the new wiring.

Run::

    python -m pytest tests/test_scp_orphan_wiring.py -q
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import pytest

from src.engine.game import Game
from src.engine.types import CardType, Characteristics, Event, EventType, ZoneType
from src.engine import scp


# ---------------------------------------------------------------------------
# Harness — build a minimal SCP game with a hand-crafted card on each
# player's side, fire the relevant engine path, assert the hook fired.
# ---------------------------------------------------------------------------


@dataclass
class _Counter:
    n: int = 0

    def hook(self, obj, state, game=None):
        """Hook that increments self.n and emits no events."""
        self.n += 1
        return []


def _make_game():
    game = Game(mode="scp")
    p1 = game.add_player("Site-A")
    p2 = game.add_player("Site-B")
    game.setup_scp_player(p1, [])
    game.setup_scp_player(p2, [])
    return game, p1, p2


def _bare_card(name: str, card_type: CardType, **slots) -> object:
    """Build a CardDefinition-style stand-in with only the SCP slots we need.

    Uses src.engine.scp.make_scp_card's underlying CardDefinition + sets
    the requested slot. Returns an object usable as ``card_def`` on a
    GameObject.
    """
    from src.engine.types import CardDefinition
    card = CardDefinition(
        name=name,
        mana_cost=None,
        characteristics=Characteristics(types=frozenset({card_type})),
    )
    # SCP cards default these to 0 — set so the engine's threat/clearance
    # logic doesn't reject them at gates.
    for slot in (
        "scp_containment", "scp_curiosity", "scp_hazard",
        "scp_red_tape", "scp_clearance",
    ):
        if slot not in slots and not hasattr(card, slot):
            setattr(card, slot, 0)
    for slot, value in slots.items():
        setattr(card, slot, value)
    return card


def _put_on_battlefield(game, player, card_type: CardType, **slots):
    """Create a GameObject from a bare card and drop it on the battlefield
    in the right SCP zone bucket. Returns the GameObject."""
    card_def = _bare_card(f"_T_{card_type.name}", card_type, **slots)
    obj = game.create_object(
        name=card_def.name,
        owner_id=player.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=card_def.characteristics,
        card_def=card_def,
    )
    obj.controller = player.id
    obj.state.scp_status = "active"
    if card_type == CardType.SCP_ANOMALY:
        game.state.scp_anomalies.setdefault(player.id, []).append(obj.id)
    elif card_type == CardType.SCP_PERSONNEL:
        game.state.scp_personnel.setdefault(player.id, []).append(obj.id)
    elif card_type == CardType.SCP_FACILITY:
        game.state.scp_facilities.setdefault(player.id, []).append(obj.id)
    elif card_type == CardType.SCP_MANDATE:
        game.state.scp_mandates.setdefault(player.id, []).append(obj.id)
    return obj


# ---------------------------------------------------------------------------
# 1. scp_on_play — fires for procedures, anomalies, and other types via
#    _activate_dossier.
# ---------------------------------------------------------------------------


def test_scp_on_play_fires_for_procedure():
    game, p1, _ = _make_game()
    counter = _Counter()
    card_def = _bare_card("Test Proc", CardType.SCP_PROCEDURE, scp_on_play=counter.hook)
    obj = game.create_object(
        name=card_def.name, owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
        characteristics=card_def.characteristics, card_def=card_def,
    )
    obj.controller = p1.id
    obj.state.scp_status = "pending"
    scp._activate_dossier(game, obj)
    assert counter.n == 1


def test_scp_on_play_fires_for_anomaly_after_reveal():
    game, p1, _ = _make_game()
    counter = _Counter()
    card_def = _bare_card("Test Anom", CardType.SCP_ANOMALY, scp_on_play=counter.hook)
    obj = game.create_object(
        name=card_def.name, owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
        characteristics=card_def.characteristics, card_def=card_def,
    )
    obj.controller = p1.id
    obj.state.scp_status = "pending"
    scp._activate_dossier(game, obj)
    assert counter.n == 1


# ---------------------------------------------------------------------------
# 2. scp_on_anomaly_enter — static trigger on OTHER cards when an anomaly
#    enters.
# ---------------------------------------------------------------------------


def test_scp_on_anomaly_enter_fires_on_other_card_when_anomaly_enters():
    game, p1, _ = _make_game()
    counter = _Counter()
    # Watcher card already on battlefield with the static trigger.
    _put_on_battlefield(
        game, p1, CardType.SCP_FACILITY, scp_on_anomaly_enter=counter.hook,
    )
    # New anomaly enters play.
    new_card = _bare_card("Newly Entered", CardType.SCP_ANOMALY)
    new_obj = game.create_object(
        name=new_card.name, owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
        characteristics=new_card.characteristics, card_def=new_card,
    )
    new_obj.controller = p1.id
    new_obj.state.scp_status = "pending"
    scp._activate_dossier(game, new_obj)
    assert counter.n == 1, (
        "Watcher card did not see new Anomaly enter — static trigger orphaned"
    )


def test_anomaly_enter_does_not_self_trigger():
    """An anomaly's own scp_on_anomaly_enter must NOT fire when *it* enters —
    that's what scp_on_reveal / scp_on_play are for."""
    game, p1, _ = _make_game()
    counter = _Counter()
    card_def = _bare_card(
        "Self-Watcher Anom", CardType.SCP_ANOMALY,
        scp_on_anomaly_enter=counter.hook,
    )
    obj = game.create_object(
        name=card_def.name, owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
        characteristics=card_def.characteristics, card_def=card_def,
    )
    obj.controller = p1.id
    obj.state.scp_status = "pending"
    scp._activate_dossier(game, obj)
    assert counter.n == 0


# ---------------------------------------------------------------------------
# 3. scp_on_open_dossier — fires when a dossier is opened.
# ---------------------------------------------------------------------------


def test_scp_on_open_dossier_fires_during_open():
    game, p1, _ = _make_game()
    counter = _Counter()
    card_def = _bare_card(
        "Openable", CardType.SCP_PERSONNEL,
        scp_on_open_dossier=counter.hook,
        scp_red_tape=2,  # pending after open
    )
    obj = game.create_object(
        name=card_def.name, owner_id=p1.id, zone=ZoneType.HAND,
        characteristics=card_def.characteristics, card_def=card_def,
    )
    ok, _msg, _events = scp.open_dossier(game, p1.id, obj.id)
    assert ok
    assert counter.n == 1


# ---------------------------------------------------------------------------
# 4. scp_on_activate — fires when a pending dossier is activated mid-turn
#    via activate_dossier_now.
# ---------------------------------------------------------------------------


def test_scp_on_activate_fires_via_activate_dossier_now():
    game, p1, _ = _make_game()
    counter = _Counter()
    card_def = _bare_card(
        "Mid-Turn Activator", CardType.SCP_ANOMALY,
        scp_on_activate=counter.hook,
    )
    obj = game.create_object(
        name=card_def.name, owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
        characteristics=card_def.characteristics, card_def=card_def,
    )
    obj.controller = p1.id
    obj.state.scp_status = "pending"
    obj.state.scp_paperwork = 2
    scp.activate_dossier_now(game, obj)
    assert counter.n == 1


# ---------------------------------------------------------------------------
# 5. scp_on_breach — fires on each active anomaly during breach_tick.
# ---------------------------------------------------------------------------


def test_scp_on_breach_fires_per_active_anomaly():
    game, p1, _ = _make_game()
    counter = _Counter()
    _put_on_battlefield(
        game, p1, CardType.SCP_ANOMALY,
        scp_on_breach=counter.hook, scp_hazard=2,
    )
    scp.breach_tick(game, p1.id)
    assert counter.n == 1


# ---------------------------------------------------------------------------
# 6. scp_on_dragon_contain — fires on facilities when a Dragon-subtype
#    anomaly is contained.
# ---------------------------------------------------------------------------


def test_scp_on_dragon_contain_fires_only_for_dragon_subtype():
    game, p1, _ = _make_game()
    counter = _Counter()
    _put_on_battlefield(
        game, p1, CardType.SCP_FACILITY,
        scp_on_dragon_contain=counter.hook,
    )
    # Non-dragon anomaly: trigger must NOT fire.
    non_dragon = _put_on_battlefield(
        game, p1, CardType.SCP_ANOMALY, scp_hazard=1,
    )
    non_dragon.card_def.subtypes = set()
    # Stage a personnel and run the contain path.
    personnel = _put_on_battlefield(
        game, p1, CardType.SCP_PERSONNEL,
        scp_skills={"contain": 99},  # auto-pass containment
    )
    ok, _msg, _events = scp.contain_anomaly(
        game, p1.id, non_dragon.id, [personnel.id],
    )
    assert ok
    assert counter.n == 0, "Trigger fired on non-Dragon anomaly"

    # Dragon anomaly: trigger MUST fire.
    dragon = _put_on_battlefield(
        game, p1, CardType.SCP_ANOMALY, scp_hazard=1,
    )
    dragon.card_def.subtypes = {"Dragon"}
    ok, _msg, _events = scp.contain_anomaly(
        game, p1.id, dragon.id, [personnel.id],
    )
    assert ok
    assert counter.n == 1


# ---------------------------------------------------------------------------
# 7. scp_on_memory_hole — fires when a dossier is memory-holed.
# ---------------------------------------------------------------------------


def test_scp_on_memory_hole_fires():
    game, p1, _ = _make_game()
    counter = _Counter()
    card_def = _bare_card(
        "Antimeme Decoy", CardType.SCP_ANOMALY,
        scp_on_memory_hole=counter.hook,
    )
    obj = game.create_object(
        name=card_def.name, owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
        characteristics=card_def.characteristics, card_def=card_def,
    )
    obj.controller = p1.id
    obj.state.scp_status = "sealed"  # memory_hole rejects "active"
    scp.site(game.state, p1.id)["archives"] = 1
    ok, _msg, _events = scp.memory_hole(game, p1.id, obj.id)
    assert ok
    assert counter.n == 1


# ---------------------------------------------------------------------------
# 8. scp_on_archive / scp_on_archive_stub — fire on source card whose
#    containment / activation produced the archive gain.
# ---------------------------------------------------------------------------


def test_scp_on_archive_fires_on_source_card():
    game, p1, _ = _make_game()
    counter = _Counter()
    stub_counter = _Counter()
    src = _put_on_battlefield(
        game, p1, CardType.SCP_FACILITY,
        scp_on_archive=counter.hook,
        scp_on_archive_stub=stub_counter.hook,
    )
    scp.gain_archives(game, p1.id, 1, source=src.id)
    assert counter.n == 1
    assert stub_counter.n == 1


def test_scp_on_archive_does_not_fire_without_source():
    game, p1, _ = _make_game()
    counter = _Counter()
    _put_on_battlefield(
        game, p1, CardType.SCP_FACILITY,
        scp_on_archive=counter.hook,
    )
    scp.gain_archives(game, p1.id, 1)  # no source
    assert counter.n == 0


# ---------------------------------------------------------------------------
# 9. scp_on_audit_return — fires ONLY on the accept branch of phylactery
#    audit (card actually returns to hand).
# ---------------------------------------------------------------------------


def test_scp_on_audit_return_fires_on_accept_branch():
    game, p1, _ = _make_game()
    counter = _Counter()
    card_def = _bare_card(
        "Auditable", CardType.SCP_PERSONNEL,
        scp_phylactery_audit=2, scp_on_audit_return=counter.hook,
    )
    obj = game.create_object(
        name=card_def.name, owner_id=p1.id, zone=ZoneType.EXILE,
        characteristics=card_def.characteristics, card_def=card_def,
    )
    obj.controller = p1.id
    scp.site(game.state, p1.id)["ethics_debt"] = 1  # 1 + 2 <= 8 → accept
    scp.apply_phylactery_audit(game.state, game, obj)
    assert counter.n == 1


def test_scp_on_audit_return_does_not_fire_on_reject():
    game, p1, _ = _make_game()
    counter = _Counter()
    card_def = _bare_card(
        "Auditable Heavy", CardType.SCP_PERSONNEL,
        scp_phylactery_audit=7, scp_on_audit_return=counter.hook,
    )
    obj = game.create_object(
        name=card_def.name, owner_id=p1.id, zone=ZoneType.EXILE,
        characteristics=card_def.characteristics, card_def=card_def,
    )
    obj.controller = p1.id
    scp.site(game.state, p1.id)["ethics_debt"] = 5  # 5 + 7 > 8 → reject
    scp.apply_phylactery_audit(game.state, game, obj)
    assert counter.n == 0


# ---------------------------------------------------------------------------
# 10. scp_on_annihilation_wave_fire — fires on the anomaly when its wave
#     triggers during breach_tick.
# ---------------------------------------------------------------------------


def test_scp_on_annihilation_wave_fire_fires():
    game, p1, _ = _make_game()
    counter = _Counter()
    _put_on_battlefield(
        game, p1, CardType.SCP_ANOMALY,
        scp_annihilation_wave=1,
        scp_on_annihilation_wave_fire=counter.hook,
        scp_hazard=1,
    )
    scp.breach_tick(game, p1.id)
    assert counter.n == 1


# ---------------------------------------------------------------------------
# 11. scp_on_rift_play — fires when a card is played from the rift window.
# ---------------------------------------------------------------------------


def test_scp_on_rift_play_fires():
    game, p1, _ = _make_game()
    counter = _Counter()
    card_def = _bare_card(
        "Rift Sprite", CardType.SCP_ANOMALY,
        scp_on_rift_play=counter.hook,
    )
    obj = game.create_object(
        name=card_def.name, owner_id=p1.id, zone=ZoneType.EXILE,
        characteristics=card_def.characteristics, card_def=card_def,
    )
    obj.controller = p1.id
    obj.state.scp_status = "pending"
    # Drop into the rift_window manually (apply_planar_rift normally does
    # this from a Multiverse Rift anomaly's containment; bypass that path).
    s = scp.site(game.state, p1.id)
    s["rift_window"] = [obj.id]
    exile = game.state.zones.get("exile")
    if exile is not None and obj.id not in exile.objects:
        exile.objects.append(obj.id)
    ok, _msg, _events = scp.play_from_rift_window(game, p1.id, obj.id)
    assert ok
    assert counter.n == 1


# ---------------------------------------------------------------------------
# 12. scp_on_sacrifice — fires when sacrifice_dossier is called on the
#     card.
# ---------------------------------------------------------------------------


def test_scp_on_sacrifice_fires_via_sacrifice_dossier():
    game, p1, _ = _make_game()
    counter = _Counter()
    obj = _put_on_battlefield(
        game, p1, CardType.SCP_PERSONNEL,
        scp_on_sacrifice=counter.hook,
    )
    ok, _msg, _events = scp.sacrifice_dossier(game, p1.id, obj.id)
    assert ok
    assert counter.n == 1
    # And the card should have moved to graveyard.
    assert obj.zone == ZoneType.GRAVEYARD


def test_sacrifice_dossier_rejects_off_battlefield():
    game, p1, _ = _make_game()
    counter = _Counter()
    card_def = _bare_card(
        "In Hand", CardType.SCP_PERSONNEL,
        scp_on_sacrifice=counter.hook,
    )
    obj = game.create_object(
        name=card_def.name, owner_id=p1.id, zone=ZoneType.HAND,
        characteristics=card_def.characteristics, card_def=card_def,
    )
    obj.controller = p1.id
    ok, _msg, _events = scp.sacrifice_dossier(game, p1.id, obj.id)
    assert not ok
    assert counter.n == 0


# ---------------------------------------------------------------------------
# 13. Compleation triggers — any_compleated, opponent_compleated,
#     you_compleated all fire when a personnel control-swaps via
#     apply_compleation_vector.
# ---------------------------------------------------------------------------


def test_compleation_triggers_fan_out_correctly():
    game, p1, p2 = _make_game()
    any_counter_p1, any_counter_p2 = _Counter(), _Counter()
    opp_counter = _Counter()  # fires for the loser-of-personnel
    you_counter = _Counter()  # fires for the new-controller
    # Observer cards on each side.
    _put_on_battlefield(
        game, p1, CardType.SCP_FACILITY,
        scp_on_any_compleated=any_counter_p1.hook,
        scp_on_opponent_compleated=opp_counter.hook,
    )
    _put_on_battlefield(
        game, p2, CardType.SCP_FACILITY,
        scp_on_any_compleated=any_counter_p2.hook,
        scp_on_you_compleated=you_counter.hook,
    )
    # p2 controls an opposing Phyrexian-strain anomaly with vector=3.
    anomaly = _put_on_battlefield(
        game, p2, CardType.SCP_ANOMALY,
        scp_compleation_vector=3,
    )
    # p1 controls a single non-Mnestic personnel.
    target = _put_on_battlefield(
        game, p1, CardType.SCP_PERSONNEL,
        scp_skills={"contain": 1},
    )
    # Run the vector — p1's personnel hits compleation>=3 and control-swaps.
    scp.apply_compleation_vector(game, p1.id)
    # The personnel's new controller is p2 (compleation_swap flips to opp).
    assert target.controller == p2.id
    # any_compleated fires for both observers.
    assert any_counter_p1.n == 1
    assert any_counter_p2.n == 1
    # opponent_compleated fires on p1's side (p1 was the loser).
    assert opp_counter.n == 1
    # you_compleated fires on p2's side (p2 is the new controller).
    assert you_counter.n == 1


# ---------------------------------------------------------------------------
# 14. scp_on_turn_end — fires on every battlefield card at end of turn.
# ---------------------------------------------------------------------------


def test_scp_on_turn_end_fires_via_static_trigger_helper():
    """The end-of-turn path is wired in scp_turn.run_turn — exercise it via
    the underlying helper to keep this test light-weight (the full
    SCPTurnManager async harness would add 100+ LOC of fixture)."""
    game, p1, _ = _make_game()
    counter = _Counter()
    _put_on_battlefield(
        game, p1, CardType.SCP_FACILITY,
        scp_on_turn_end=counter.hook,
    )
    scp._fire_static_trigger(game, "scp_on_turn_end", p1.id)
    assert counter.n == 1


# ---------------------------------------------------------------------------
# Sanity: the static-trigger helper iterates all five zone buckets.
# ---------------------------------------------------------------------------


def test_static_trigger_walks_anomaly_personnel_facility_contained_mandate():
    """A trigger declared on cards in different SCP zone buckets must all
    fire when the static helper is invoked."""
    game, p1, _ = _make_game()
    counter = _Counter()
    for ctype in (
        CardType.SCP_ANOMALY,
        CardType.SCP_PERSONNEL,
        CardType.SCP_FACILITY,
        CardType.SCP_MANDATE,
    ):
        _put_on_battlefield(
            game, p1, ctype, scp_on_turn_end=counter.hook,
        )
    scp._fire_static_trigger(game, "scp_on_turn_end", p1.id)
    # Four cards, four fires.
    assert counter.n == 4
