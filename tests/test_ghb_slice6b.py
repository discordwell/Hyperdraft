"""
Studio Ghibli Slice 6B median-lift tests (2026-05-19)

Validates 21 vanilla Blue + Red cards lifted to depth>=2 via inline
state.zones + all_opponents pattern. Each test fires the buffed ETB / attack
trigger and asserts the expected information + asymmetric events emit.

Mirrors test_zelda_spice.py slice-8B pattern (gotcha #18: worktree-portable
sys.path).
"""

import os
import sys

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
sys.path.insert(0, _REPO_ROOT)

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color, Characteristics,
)
from src.cards.custom.studio_ghibli import STUDIO_GHIBLI_CARDS


def _put_on_battlefield(game, player, card_name):
    """Standard pattern: create in hand without card_def, then ZONE_CHANGE."""
    card_def = STUDIO_GHIBLI_CARDS[card_name]
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
            'to_zone_type': ZoneType.BATTLEFIELD,
        },
    ))
    return obj


def _emitted_types(game):
    return [e.type.name for e in game.state.event_log]


def _events_after(game, source_id, event_type, since):
    return [
        e for e in game.state.event_log[since:]
        if e.type == event_type and e.source == source_id
    ]


def _assert_etb_scry(game, p, card_name, expected_amount):
    before = len(game.state.event_log)
    obj = _put_on_battlefield(game, p, card_name)
    scrys = _events_after(game, obj.id, EventType.SCRY, before)
    assert scrys, (
        f"{card_name}: SCRY missing — got {_emitted_types(game)[-10:]}"
    )
    assert scrys[-1].payload.get('amount') == expected_amount, (
        f"{card_name}: expected SCRY {expected_amount}, "
        f"got {scrys[-1].payload}"
    )
    return obj, before


def _fire_attack(game, attacker, attacker_controller):
    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={'attacker_id': attacker.id, 'attacker': attacker.id,
                 'controller': attacker_controller.id},
        source=attacker.id,
    ))
    return before


def _assert_each_opp_drain(game, source_id, opp_id, since,
                           expected_min_loss=1):
    drains = [
        e for e in game.state.event_log[since:]
        if e.type == EventType.LIFE_CHANGE
        and e.payload.get('player') == opp_id
        and e.payload.get('amount', 0) < 0
        and abs(e.payload.get('amount', 0)) >= expected_min_loss
        and e.source == source_id
    ]
    assert drains, (
        f"Expected drain >= {expected_min_loss}; "
        f"got {_emitted_types(game)[-10:]}"
    )


def _assert_each_opp_damage(game, source_id, opp_id, since,
                            expected_min=1):
    damages = [
        e for e in game.state.event_log[since:]
        if e.type == EventType.DAMAGE
        and e.payload.get('target') == opp_id
        and e.payload.get('amount', 0) >= expected_min
        and e.source == source_id
    ]
    assert damages, (
        f"Expected damage >= {expected_min}; "
        f"got {_emitted_types(game)[-10:]}"
    )


# ============================================================================
# Blue cards (11)
# ============================================================================


def test_river_spirit_etb_scry_and_drain():
    print("\n=== River Spirit: ETB scry + drain ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    obj, before = _assert_etb_scry(game, p1, "River Spirit", 1)
    _assert_each_opp_drain(game, obj.id, p2.id, before)


def test_laputa_robot_gardener_etb_scry2_and_drain():
    print("\n=== Laputa Robot Gardener: ETB scry 2 + drain ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    obj, before = _assert_etb_scry(game, p1, "Laputa Robot Gardener", 2)
    _assert_each_opp_drain(game, obj.id, p2.id, before)


def test_granmamare_etb_scry2_and_drain():
    print("\n=== Granmamare, Sea Goddess: ETB scry 2 + drain 2+ ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    obj, before = _assert_etb_scry(game, p1, "Granmamare, Sea Goddess", 2)
    _assert_each_opp_drain(game, obj.id, p2.id, before, expected_min_loss=2)


def test_flying_fish_spirit_etb_scry_and_drain():
    print("\n=== Flying Fish Spirit: ETB scry + drain ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    obj, before = _assert_etb_scry(game, p1, "Flying Fish Spirit", 1)
    _assert_each_opp_drain(game, obj.id, p2.id, before)


def test_cloud_elemental_etb_scry_surveil_drain():
    print("\n=== Cloud Elemental: ETB scry + surveil-if-threat + drain ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    # Put an opponent creature to trigger surveil branch.
    threat_cd = STUDIO_GHIBLI_CARDS["Wild Boar"]
    game.create_object(
        name="Wild Boar",
        owner_id=p2.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=threat_cd.characteristics,
        card_def=threat_cd,
    )
    obj, before = _assert_etb_scry(game, p1, "Cloud Elemental", 1)
    surveils = _events_after(game, obj.id, EventType.SURVEIL, before)
    assert surveils, (
        f"Expected SURVEIL when opp has creature; "
        f"got {_emitted_types(game)[-10:]}"
    )
    _assert_each_opp_drain(game, obj.id, p2.id, before)


def test_bathhouse_frog_etb_scry_and_drain():
    print("\n=== Bathhouse Frog: ETB scry + drain ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    obj, before = _assert_etb_scry(game, p1, "Bathhouse Frog", 1)
    _assert_each_opp_drain(game, obj.id, p2.id, before)


def test_minor_water_spirit_etb_scry_and_drain():
    print("\n=== Minor Water Spirit: ETB scry + drain ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    obj, before = _assert_etb_scry(game, p1, "Minor Water Spirit", 1)
    _assert_each_opp_drain(game, obj.id, p2.id, before)


def test_tiger_moth_crew_attack_scry_and_drain():
    print("\n=== Tiger Moth Crew: attack scry + drain ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    obj = _put_on_battlefield(game, p1, "Tiger Moth Crew")
    before = _fire_attack(game, obj, p1)
    scrys = _events_after(game, obj.id, EventType.SCRY, before)
    assert scrys, f"Expected SCRY; got {_emitted_types(game)[-10:]}"
    _assert_each_opp_drain(game, obj.id, p2.id, before)


def test_mystical_guardian_etb_scry_surveil_drain():
    print("\n=== Mystical Guardian: ETB scry 2 + surveil if threat + drain ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    # Add a threat for surveil branch.
    threat_cd = STUDIO_GHIBLI_CARDS["Wild Boar"]
    game.create_object(
        name="Wild Boar",
        owner_id=p2.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=threat_cd.characteristics,
        card_def=threat_cd,
    )
    obj, before = _assert_etb_scry(game, p1, "Mystical Guardian", 2)
    surveils = _events_after(game, obj.id, EventType.SURVEIL, before)
    assert surveils, f"Expected SURVEIL with threat; got {_emitted_types(game)[-10:]}"
    _assert_each_opp_drain(game, obj.id, p2.id, before)


def test_rivers_blessing_etb_scry2_and_drain():
    print("\n=== River's Blessing: ETB scry 2 + drain ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    obj, before = _assert_etb_scry(game, p1, "River's Blessing", 2)
    _assert_each_opp_drain(game, obj.id, p2.id, before)


def test_sky_domain_etb_scry_reveal_drain():
    print("\n=== Sky Domain: ETB scry + reveal hand + drain ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    obj, before = _assert_etb_scry(game, p1, "Sky Domain", 1)
    reveals = [
        e for e in game.state.event_log[before:]
        if e.type == EventType.REVEAL_HAND
        and e.payload.get('player') == p2.id
        and e.source == obj.id
    ]
    assert reveals, (
        f"Expected REVEAL_HAND; got {_emitted_types(game)[-10:]}"
    )
    _assert_each_opp_drain(game, obj.id, p2.id, before)


# ============================================================================
# Red cards (10)
# ============================================================================


def test_torumekian_soldier_attack_scry_and_damage():
    print("\n=== Torumekian Soldier: attack scry + damage ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    obj = _put_on_battlefield(game, p1, "Torumekian Soldier")
    before = _fire_attack(game, obj, p1)
    scrys = _events_after(game, obj.id, EventType.SCRY, before)
    assert scrys, f"Expected SCRY; got {_emitted_types(game)[-10:]}"
    _assert_each_opp_damage(game, obj.id, p2.id, before)


def test_flame_elemental_etb_scry_and_damage():
    print("\n=== Flame Elemental: ETB scry + damage ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    obj, before = _assert_etb_scry(game, p1, "Flame Elemental", 1)
    _assert_each_opp_damage(game, obj.id, p2.id, before)


def test_volcanic_spirit_etb_surveil_and_damage():
    print("\n=== Volcanic Spirit: ETB surveil + 2+ damage ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    before = len(game.state.event_log)
    obj = _put_on_battlefield(game, p1, "Volcanic Spirit")
    surveils = _events_after(game, obj.id, EventType.SURVEIL, before)
    assert surveils, f"Expected SURVEIL; got {_emitted_types(game)[-10:]}"
    _assert_each_opp_damage(game, obj.id, p2.id, before, expected_min=2)


def test_destruction_spirit_etb_scry_reveal_damage():
    print("\n=== Destruction Spirit: ETB scry + reveal hand + damage ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    obj, before = _assert_etb_scry(game, p1, "Destruction Spirit", 1)
    reveals = [
        e for e in game.state.event_log[before:]
        if e.type == EventType.REVEAL_HAND
        and e.payload.get('player') == p2.id
        and e.source == obj.id
    ]
    assert reveals, f"Expected REVEAL_HAND; got {_emitted_types(game)[-10:]}"
    _assert_each_opp_damage(game, obj.id, p2.id, before)


def test_pejite_warrior_etb_scry_and_damage():
    print("\n=== Pejite Warrior: ETB scry + damage ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    obj, before = _assert_etb_scry(game, p1, "Pejite Warrior", 1)
    _assert_each_opp_damage(game, obj.id, p2.id, before)


def test_forest_arsonist_etb_damage_and_drain():
    print("\n=== Forest Arsonist: ETB damage each opp + drain ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    before = len(game.state.event_log)
    obj = _put_on_battlefield(game, p1, "Forest Arsonist")
    _assert_each_opp_damage(game, obj.id, p2.id, before)
    _assert_each_opp_drain(game, obj.id, p2.id, before)


def test_wild_boar_attack_scry_and_damage():
    print("\n=== Wild Boar: attack scry + damage ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    obj = _put_on_battlefield(game, p1, "Wild Boar")
    before = _fire_attack(game, obj, p1)
    scrys = _events_after(game, obj.id, EventType.SCRY, before)
    assert scrys, f"Expected SCRY; got {_emitted_types(game)[-10:]}"
    _assert_each_opp_damage(game, obj.id, p2.id, before)


def test_ironworks_furnace_etb_scry_and_damage():
    print("\n=== Ironworks Furnace: ETB scry + damage ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    obj, before = _assert_etb_scry(game, p1, "Ironworks Furnace", 1)
    _assert_each_opp_damage(game, obj.id, p2.id, before)


def test_bombardment_crew_etb_scry_and_damage():
    print("\n=== Bombardment Crew: ETB scry + damage ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    obj, before = _assert_etb_scry(game, p1, "Bombardment Crew", 1)
    _assert_each_opp_damage(game, obj.id, p2.id, before)


def test_war_drums_etb_scry_and_damage():
    print("\n=== War Drums: ETB scry + damage ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    obj, before = _assert_etb_scry(game, p1, "War Drums", 1)
    _assert_each_opp_damage(game, obj.id, p2.id, before)


if __name__ == "__main__":
    # Blue
    test_river_spirit_etb_scry_and_drain()
    test_laputa_robot_gardener_etb_scry2_and_drain()
    test_granmamare_etb_scry2_and_drain()
    test_flying_fish_spirit_etb_scry_and_drain()
    test_cloud_elemental_etb_scry_surveil_drain()
    test_bathhouse_frog_etb_scry_and_drain()
    test_minor_water_spirit_etb_scry_and_drain()
    test_tiger_moth_crew_attack_scry_and_drain()
    test_mystical_guardian_etb_scry_surveil_drain()
    test_rivers_blessing_etb_scry2_and_drain()
    test_sky_domain_etb_scry_reveal_drain()
    # Red
    test_torumekian_soldier_attack_scry_and_damage()
    test_flame_elemental_etb_scry_and_damage()
    test_volcanic_spirit_etb_surveil_and_damage()
    test_destruction_spirit_etb_scry_reveal_damage()
    test_pejite_warrior_etb_scry_and_damage()
    test_forest_arsonist_etb_damage_and_drain()
    test_wild_boar_attack_scry_and_damage()
    test_ironworks_furnace_etb_scry_and_damage()
    test_bombardment_crew_etb_scry_and_damage()
    test_war_drums_etb_scry_and_damage()
    print("\n" + "=" * 60)
    print("ALL GHB SLICE-6B TESTS PASSED!")
    print("=" * 60)
