"""
Interceptor verification for Penultimate Avatar (TLAC, src/cards/custom/penultimate_avatar.py).

Created during the Option-A slice-20 wrapper deletion (2026-05-28). Asserts that:

 1. Every signature ATLA character (Aang, Korra, Roku, Katara, Sokka, Suki,
    Zuko x3, Ozai, Azula x2, Iroh, Bumi, Combustion Man, Toph x2) registers
    its claimed interceptor trigger on entry to the battlefield.
 2. Cards with text-faithful real effects (Sokka, Iroh-Dragon, Aang-and-La,
    Fire Lord Ozai end-step ping) actually emit the documented event when
    the trigger fires.
 3. Fated Firepower's static damage-boost interceptor wires under
    InterceptorPriority.TRANSFORM (the previous InterceptorPriority.MODIFY
    raised AttributeError because the enum value did not exist).
 4. The 2 inlined ex-slice-20 setups (Firebending Student attack trigger and
    Water Tribe Healer ETB life-gain) still emit non-zero amounts now that
    their `_tlac_s20_count_*` helper dependencies were removed.

Run directly: ``python tests/test_penultimate_avatar_interceptors.py``.
"""

import os
import sys

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color,
    InterceptorPriority, InterceptorAction,
    get_power, get_toughness,
)
from src.cards.custom.penultimate_avatar import AVATAR_TLA_CUSTOM_CARDS


# Harness

def _put_on_battlefield(game, player, card_name):
    card_def = AVATAR_TLA_CUSTOM_CARDS[card_name]
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


# Tests

def test_aang_last_airbender_loads():
    print("\n=== Aang, the Last Airbender: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    aang = _put_on_battlefield(game, p1, "Aang, the Last Airbender")
    assert aang.zone == ZoneType.BATTLEFIELD
    assert aang.interceptor_ids, "Aang must register interceptors"


def test_aang_last_airbender_lesson_grants_lifelink():
    print("\n=== Aang, the Last Airbender: lesson -> lifelink ===")
    game = Game()
    p1 = game.add_player("Alice")
    aang = _put_on_battlefield(game, p1, "Aang, the Last Airbender")

    lesson_def = AVATAR_TLA_CUSTOM_CARDS["Airbending Lesson"]
    lesson_obj = game.create_object(
        name=lesson_def.name,
        owner_id=p1.id,
        zone=ZoneType.HAND,
        characteristics=lesson_def.characteristics,
        card_def=lesson_def,
    )
    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.CAST,
        payload={
            'caster': p1.id,
            'spell_id': lesson_obj.id,
            'types': list(lesson_obj.characteristics.types),
            'subtypes': ['Lesson'],  # set's Lesson is in card text not subtypes
        },
    ))
    grants = [
        e for e in game.state.event_log[before:]
        if e.type == EventType.GRANT_KEYWORD
        and e.payload.get('object_id') == aang.id
        and e.payload.get('keyword') == 'lifelink'
    ]
    assert grants, (
        f"Expected GRANT_KEYWORD(lifelink) on Aang from Lesson cast; "
        f"recent={[e.type.name for e in game.state.event_log[-10:]]}"
    )


def test_aang_swift_savior_etb_trigger_registers():
    print("\n=== Aang, Swift Savior: ETB trigger registered ===")
    game = Game()
    p1 = game.add_player("Alice")
    aang = _put_on_battlefield(game, p1, "Aang, Swift Savior")
    assert aang.interceptor_ids


def test_aang_and_la_bounces_opp_creatures():
    print("\n=== Aang and La: bounce opp creatures ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")

    sokka_def = AVATAR_TLA_CUSTOM_CARDS["Sokka, Swordsman"]
    enemy = game.create_object(
        name=sokka_def.name,
        owner_id=p2.id,
        zone=ZoneType.HAND,
        characteristics=sokka_def.characteristics,
        card_def=sokka_def,
    )
    enemy.controller = p2.id
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': enemy.id,
            'from_zone': f'hand_{p2.id}',
            'to_zone': 'battlefield',
            'to_zone_type': ZoneType.BATTLEFIELD,
        },
    ))
    assert enemy.zone == ZoneType.BATTLEFIELD

    before = len(game.state.event_log)
    aang_la = _put_on_battlefield(game, p1, "Aang and La, Ocean's Fury")

    bounces = [
        e for e in game.state.event_log[before:]
        if e.type == EventType.ZONE_CHANGE
        and e.payload.get('object_id') == enemy.id
        and (
            e.payload.get('to_zone') == f'hand_{p2.id}'
            or e.payload.get('to_zone_type') == ZoneType.HAND
        )
    ]
    assert bounces, f"Aang and La must bounce opp creature; recent={[(e.type.name, e.payload) for e in game.state.event_log[-12:]]}"


def test_avatar_korra_attack_trigger():
    print("\n=== Avatar Korra: attack trigger registered ===")
    game = Game()
    p1 = game.add_player("Alice")
    korra = _put_on_battlefield(game, p1, "Avatar Korra, Spirit Bridge")
    assert korra.interceptor_ids


def test_avatar_roku_registers_firebend_and_etb():
    print("\n=== Avatar Roku: firebend + ETB ===")
    game = Game()
    p1 = game.add_player("Alice")
    roku = _put_on_battlefield(game, p1, "Avatar Roku")
    assert len(roku.interceptor_ids) >= 2


def test_katara_waterbending_master_trigger():
    print("\n=== Katara: spell cast trigger registered ===")
    game = Game()
    p1 = game.add_player("Alice")
    katara = _put_on_battlefield(game, p1, "Katara, Waterbending Master")
    assert katara.interceptor_ids


def test_sokka_swordsman_draws_on_combat_damage():
    print("\n=== Sokka: combat damage -> draw ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    sokka = _put_on_battlefield(game, p1, "Sokka, Swordsman")

    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.DAMAGE,
        payload={
            'target': p2.id,
            'amount': 3,
            'source': sokka.id,
            'is_combat': True,
        },
        source=sokka.id,
    ))
    draws = [
        e for e in game.state.event_log[before:]
        if e.type == EventType.DRAW
        and e.payload.get('player') == p1.id
        and e.payload.get('amount') == 1
    ]
    assert draws, f"Expected DRAW for Alice on combat damage; recent={[e.type.name for e in game.state.event_log[-10:]]}"


def test_sokka_non_combat_damage_no_draw():
    print("\n=== Sokka: non-combat damage -> no draw ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    sokka = _put_on_battlefield(game, p1, "Sokka, Swordsman")

    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.DAMAGE,
        payload={
            'target': p2.id,
            'amount': 3,
            'source': sokka.id,
            'is_combat': False,
        },
        source=sokka.id,
    ))
    draws = [
        e for e in game.state.event_log[before:]
        if e.type == EventType.DRAW
        and e.payload.get('player') == p1.id
    ]
    assert not draws, "Sokka must not draw from non-combat damage"


def test_suki_anthems_other_warriors():
    print("\n=== Suki: anthem +1/+0 to other Warriors ===")
    game = Game()
    p1 = game.add_player("Alice")
    suki = _put_on_battlefield(game, p1, "Suki, Kyoshi Warrior")
    sokka = _put_on_battlefield(game, p1, "Sokka, Swordsman")
    base_p = sokka.characteristics.power or 0
    new_p = get_power(sokka, game.state)
    assert new_p == base_p + 1, f"base={base_p} new={new_p}"


def test_suki_does_not_buff_self():
    print("\n=== Suki: anthem excludes self ===")
    game = Game()
    p1 = game.add_player("Alice")
    suki = _put_on_battlefield(game, p1, "Suki, Kyoshi Warrior")
    base_p = suki.characteristics.power or 0
    new_p = get_power(suki, game.state)
    assert new_p == base_p, f"base={base_p} new={new_p}"


def test_prince_zuko_firebend_etb_registers():
    print("\n=== Prince Zuko: firebend ETB + attack trigger ===")
    game = Game()
    p1 = game.add_player("Alice")
    zuko = _put_on_battlefield(game, p1, "Prince Zuko")
    assert len(zuko.interceptor_ids) >= 2


def test_zuko_redeemed_registers_damage_trigger():
    print("\n=== Zuko, Redeemed: combat damage trigger ===")
    game = Game()
    p1 = game.add_player("Alice")
    zuko = _put_on_battlefield(game, p1, "Zuko, Redeemed")
    assert len(zuko.interceptor_ids) >= 2


def test_fire_lord_zuko_cast_from_exile_adds_counter():
    print("\n=== Fire Lord Zuko: cast from exile -> counter ===")
    game = Game()
    p1 = game.add_player("Alice")
    zuko = _put_on_battlefield(game, p1, "Fire Lord Zuko")

    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.CAST,
        payload={
            'caster': p1.id,
            'spell_id': 'fake_spell',
            'from_zone': ZoneType.EXILE,
        },
    ))
    counters = [
        e for e in game.state.event_log[before:]
        if e.type == EventType.COUNTER_ADDED
        and e.payload.get('object_id') == zuko.id
        and e.payload.get('counter_type') == '+1/+1'
    ]
    assert counters, f"recent={[e.type.name for e in game.state.event_log[-8:]]}"


def test_fire_lord_zuko_cast_from_hand_no_counter():
    print("\n=== Fire Lord Zuko: cast from hand -> no counter ===")
    game = Game()
    p1 = game.add_player("Alice")
    zuko = _put_on_battlefield(game, p1, "Fire Lord Zuko")

    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.CAST,
        payload={
            'caster': p1.id,
            'spell_id': 'fake_spell',
            'from_zone': f'hand_{p1.id}',
        },
    ))
    counters = [
        e for e in game.state.event_log[before:]
        if e.type == EventType.COUNTER_ADDED
        and e.payload.get('object_id') == zuko.id
    ]
    assert not counters


def test_fire_lord_ozai_end_step_damage():
    print("\n=== Fire Lord Ozai: end step damage ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    ozai = _put_on_battlefield(game, p1, "Fire Lord Ozai")

    before = len(game.state.event_log)
    game.state.active_player = p1.id
    game.emit(Event(
        type=EventType.PHASE_START,
        payload={'phase': 'end_step', 'active_player': p1.id},
    ))
    damages = [
        e for e in game.state.event_log[before:]
        if e.type == EventType.DAMAGE
        and e.payload.get('target') == p2.id
        and e.payload.get('source') == ozai.id
        and e.payload.get('amount', 0) > 0
    ]
    assert damages, f"recent={[e.type.name for e in game.state.event_log[-12:]]}"


def test_fire_lord_azula_copy_trigger_registers():
    print("\n=== Fire Lord Azula: copy trigger registered ===")
    game = Game()
    p1 = game.add_player("Alice")
    azula = _put_on_battlefield(game, p1, "Fire Lord Azula")
    assert azula.interceptor_ids


def test_azula_cunning_usurper_firebend_attack():
    print("\n=== Azula, Cunning Usurper: firebend attack ===")
    game = Game()
    p1 = game.add_player("Alice")
    azula = _put_on_battlefield(game, p1, "Azula, Cunning Usurper")
    assert azula.interceptor_ids


def test_iroh_dragon_upkeep_damages_opp():
    print("\n=== Iroh, Dragon of the West: upkeep ping ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    iroh = _put_on_battlefield(game, p1, "Iroh, Dragon of the West")

    before = len(game.state.event_log)
    game.state.active_player = p1.id
    game.emit(Event(
        type=EventType.PHASE_START,
        payload={'phase': 'upkeep', 'active_player': p1.id},
    ))
    damages = [
        e for e in game.state.event_log[before:]
        if e.type == EventType.DAMAGE
        and e.payload.get('target') == p2.id
        and e.payload.get('source') == iroh.id
        and e.payload.get('amount') == 1
    ]
    assert damages, f"recent={[e.type.name for e in game.state.event_log[-10:]]}"


def test_bumi_king_etb_trigger_registers():
    print("\n=== Bumi, King of Three Trials: ETB trigger ===")
    game = Game()
    p1 = game.add_player("Alice")
    bumi = _put_on_battlefield(game, p1, "Bumi, King of Three Trials")
    assert bumi.interceptor_ids


def test_combustion_man_attack_trigger_registers():
    print("\n=== Combustion Man: attack trigger ===")
    game = Game()
    p1 = game.add_player("Alice")
    comb = _put_on_battlefield(game, p1, "Combustion Man")
    assert comb.interceptor_ids


def test_toph_beifong_earthbend_etb():
    print("\n=== Toph Beifong: earthbend + grant ===")
    game = Game()
    p1 = game.add_player("Alice")
    toph = _put_on_battlefield(game, p1, "Toph Beifong")
    assert len(toph.interceptor_ids) >= 1


def test_toph_metalbender_interceptors():
    print("\n=== Toph, Metalbender: interceptors register ===")
    game = Game()
    p1 = game.add_player("Alice")
    toph = _put_on_battlefield(game, p1, "Toph, Metalbender")
    assert len(toph.interceptor_ids) >= 2


def test_fated_firepower_setup_registers_transform_interceptor():
    print("\n=== Fated Firepower: TRANSFORM (not MODIFY) ===")
    game = Game()
    p1 = game.add_player("Alice")
    ffp = _put_on_battlefield(game, p1, "Fated Firepower")

    assert ffp.interceptor_ids, "Fated Firepower must register an interceptor"

    found_transform = False
    for iid in ffp.interceptor_ids:
        intr = game.state.interceptors.get(iid)
        if intr is None:
            continue
        if intr.priority == InterceptorPriority.TRANSFORM:
            found_transform = True
            break
    assert found_transform, "Fated Firepower must register a TRANSFORM-priority interceptor"


def test_fated_firepower_boosts_damage_with_counters():
    print("\n=== Fated Firepower: +N damage with N fire counters ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    ffp = _put_on_battlefield(game, p1, "Fated Firepower")
    ffp.state.counters['fire'] = 3

    sokka = _put_on_battlefield(game, p1, "Sokka, Swordsman")

    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.DAMAGE,
        payload={
            'target': p2.id,
            'amount': 2,
            'source': sokka.id,
            'is_combat': False,
        },
        source=sokka.id,
    ))
    new_dmg = [
        e for e in game.state.event_log[before:]
        if e.type == EventType.DAMAGE
        and e.payload.get('source') == sokka.id
        and e.payload.get('target') == p2.id
    ]
    assert new_dmg, "Sokka damage event missing from log"
    assert any(e.payload.get('amount') == 5 for e in new_dmg), (
        f"FF must transform damage 2 + 3 fire counters -> 5; "
        f"got amounts={[e.payload.get('amount') for e in new_dmg]}"
    )


def test_firebending_student_attack_emits_damage():
    print("\n=== Firebending Student: attack -> damage to opp ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    student = _put_on_battlefield(game, p1, "Firebending Student")

    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={
            'attacker_id': student.id,
            'defender': p2.id,
            'controller': p1.id,
        },
        source=student.id,
    ))
    damages = [
        e for e in game.state.event_log[before:]
        if e.type == EventType.DAMAGE
        and e.payload.get('target') == p2.id
        and e.payload.get('source') == student.id
        and (e.payload.get('amount') or 0) > 0
    ]
    assert damages, f"recent={[(e.type.name, e.payload) for e in game.state.event_log[-12:]]}"


def test_water_tribe_healer_etb_emits_life_gain():
    print("\n=== Water Tribe Healer: ETB life gain ===")
    game = Game()
    p1 = game.add_player("Alice")
    before = len(game.state.event_log)
    healer = _put_on_battlefield(game, p1, "Water Tribe Healer")
    gains = [
        e for e in game.state.event_log[before:]
        if e.type == EventType.LIFE_CHANGE
        and e.payload.get('player') == p1.id
        and (e.payload.get('amount') or 0) > 0
        and e.source == healer.id
    ]
    assert gains, f"recent={[(e.type.name, e.payload) for e in game.state.event_log[-12:]]}"


def main():
    import inspect
    module = sys.modules[__name__]
    tests = [
        (name, fn)
        for name, fn in inspect.getmembers(module, inspect.isfunction)
        if name.startswith("test_")
    ]
    print("=" * 60)
    print(f"penultimate_avatar interceptor tests: {len(tests)} cases")
    print("=" * 60)
    passed = 0
    failed = 0
    failures = []
    for name, fn in tests:
        try:
            fn()
            passed += 1
        except AssertionError as e:
            failed += 1
            failures.append((name, str(e)))
            print(f"FAIL: {name}")
            print(f"  {e}")
        except Exception as e:
            failed += 1
            failures.append((name, f"{type(e).__name__}: {e}"))
            print(f"ERROR: {name}")
            print(f"  {type(e).__name__}: {e}")
    print("=" * 60)
    print(f"Total: {passed}/{len(tests)} passed")
    print("=" * 60)
    if failures:
        for name, msg in failures:
            print(f" - {name}: {msg}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
