"""
Yu-Gi-Oh! Interceptor Tests — YGO_DESTROY / YGO_SEND_TO_GY effect families.

Verifies the pipeline handlers correctly move cards to GY and emit follow-up
notification events (YGO_DESTROYED, YGO_SENT_TO_GY), and that the 18 wired
cards actually fire their destroy/send-to-GY effects end-to-end.

Run directly:
    python tests/test_yugioh_interceptors.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.engine.game import Game
from src.engine.types import ZoneType, CardType, EventType, Event, Characteristics
from src.engine.yugioh_spells import YugiohSpellTrapManager

from src.cards.yugioh.ygo_starter import (
    BREAKER_THE_MAGICAL_WARRIOR, WITCH_OF_THE_BLACK_FOREST,
    BATTLE_OX, ALEXANDRITE_DRAGON, MOUNTAIN_FIELD,
)
from src.cards.yugioh.ygo_classic import (
    CRUSH_CARD_VIRUS, BLUE_EYES_WHITE_DRAGON, DARK_MAGICIAN, CELTIC_GUARDIAN,
)
from src.cards.yugioh.ygo_optimized import (
    RAIGEKI, MOBIUS_THE_FROST_MONARCH, ZABORG_THE_THUNDER_MONARCH,
    TRIBE_INFECTING_VIRUS, SANGAN, MYSTIC_TOMATO, MASKED_DRAGON,
    GIANT_GERM, ARMED_DRAGON_LV5, ARMED_DRAGON_LV7,
)


def make_test_game():
    game = Game(mode="yugioh")
    p1 = game.add_player("Player 1")
    p2 = game.add_player("Player 2")
    return game, p1, p2


def create_in_zone(game, owner, card_def, zone, position='face_up_atk'):
    """Create a card directly in a zone (bypasses summon for testing)."""
    obj = game.create_object(
        name=card_def.name, owner_id=owner.id, zone=ZoneType.HAND,
        characteristics=Characteristics(types=set(card_def.characteristics.types),
                                        subtypes=set(card_def.characteristics.subtypes or set())),
        card_def=card_def,
    )
    # Move to target zone
    hand_zone = game.state.zones[f"hand_{owner.id}"]
    if obj.id in hand_zone.objects:
        hand_zone.objects.remove(obj.id)
    target_key = _zone_key_for(zone, owner.id)
    if target_key and target_key in game.state.zones:
        z = game.state.zones[target_key]
        if "monster_zone_" in target_key or "spell_trap_zone_" in target_key:
            placed = False
            for i in range(5):
                if i >= len(z.objects) or z.objects[i] is None:
                    while len(z.objects) <= i:
                        z.objects.append(None)
                    z.objects[i] = obj.id
                    placed = True
                    break
            if not placed:
                z.objects.append(obj.id)
        else:
            z.objects.append(obj.id)
    obj.zone = zone
    obj.controller = owner.id
    if zone == ZoneType.MONSTER_ZONE:
        obj.state.ygo_position = position
        obj.state.face_down = False
    return obj


def _zone_key_for(zone, owner_id):
    if zone == ZoneType.MONSTER_ZONE:
        return f"monster_zone_{owner_id}"
    if zone == ZoneType.SPELL_TRAP_ZONE:
        return f"spell_trap_zone_{owner_id}"
    if zone == ZoneType.LIBRARY:
        return f"library_{owner_id}"
    if zone == ZoneType.HAND:
        return f"hand_{owner_id}"
    if zone == ZoneType.GRAVEYARD:
        return f"graveyard_{owner_id}"
    return None


def count_monsters(game, player_id):
    zone = game.state.zones.get(f"monster_zone_{player_id}")
    if not zone:
        return 0
    return sum(1 for oid in zone.objects if oid is not None)


# =============================================================================
# Tests
# =============================================================================

def test_ygo_destroy_handler_moves_to_gy():
    """YGO_DESTROY with target_ids moves cards to GY and emits YGO_DESTROYED."""
    game, p1, p2 = make_test_game()
    pipeline = game.pipeline

    m1 = create_in_zone(game, p2, CELTIC_GUARDIAN, ZoneType.MONSTER_ZONE)
    m2 = create_in_zone(game, p2, BLUE_EYES_WHITE_DRAGON, ZoneType.MONSTER_ZONE)

    assert count_monsters(game, p2.id) == 2

    processed = pipeline.emit(Event(
        type=EventType.YGO_DESTROY,
        payload={'target_ids': [m1.id, m2.id], 'source_id': 'test', 'reason': 'effect'},
    ))

    # Both monsters now in p2's graveyard
    assert count_monsters(game, p2.id) == 0
    gy = game.state.zones[f"graveyard_{p2.id}"].objects
    assert m1.id in gy
    assert m2.id in gy

    # Both notification events emitted
    destroyed_evts = [e for e in processed if e.type == EventType.YGO_DESTROYED]
    sent_evts = [e for e in processed if e.type == EventType.YGO_SENT_TO_GY]
    assert len(destroyed_evts) == 2, f"expected 2 YGO_DESTROYED, got {len(destroyed_evts)}"
    assert len(sent_evts) == 2, f"expected 2 YGO_SENT_TO_GY, got {len(sent_evts)}"
    # from_zone is captured
    assert all(e.payload.get('from_zone', '').startswith('monster_zone_')
               for e in destroyed_evts), "from_zone not captured"
    print("  PASS: test_ygo_destroy_handler_moves_to_gy")


def test_ygo_send_to_gy_handler_moves_and_emits_only_sent():
    """YGO_SEND_TO_GY moves card to GY and emits YGO_SENT_TO_GY (NOT YGO_DESTROYED)."""
    game, p1, p2 = make_test_game()
    pipeline = game.pipeline

    m = create_in_zone(game, p1, DARK_MAGICIAN, ZoneType.MONSTER_ZONE)

    processed = pipeline.emit(Event(
        type=EventType.YGO_SEND_TO_GY,
        payload={'card_id': m.id, 'reason': 'tribute'},
    ))

    assert count_monsters(game, p1.id) == 0
    assert m.id in game.state.zones[f"graveyard_{p1.id}"].objects

    destroyed_evts = [e for e in processed if e.type == EventType.YGO_DESTROYED]
    sent_evts = [e for e in processed if e.type == EventType.YGO_SENT_TO_GY]
    assert len(destroyed_evts) == 0, "YGO_SEND_TO_GY must NOT emit YGO_DESTROYED"
    assert len(sent_evts) == 1
    assert sent_evts[0].payload.get('reason') == 'tribute'
    print("  PASS: test_ygo_send_to_gy_handler_moves_and_emits_only_sent")


def test_raigeki_destroys_opponent_monsters_via_event():
    """Raigeki resolver still works after the event-handler refactor."""
    game, p1, p2 = make_test_game()
    spell_mgr = YugiohSpellTrapManager(game.state)

    # 3 opponent monsters
    for cd in (CELTIC_GUARDIAN, BLUE_EYES_WHITE_DRAGON, DARK_MAGICIAN):
        create_in_zone(game, p2, cd, ZoneType.MONSTER_ZONE)
    # 1 of our own
    own = create_in_zone(game, p1, BATTLE_OX, ZoneType.MONSTER_ZONE)

    assert count_monsters(game, p2.id) == 3
    assert count_monsters(game, p1.id) == 1

    # Activate Raigeki
    raigeki = game.create_object(
        name=RAIGEKI.name, owner_id=p1.id, zone=ZoneType.HAND,
        characteristics=Characteristics(types=set(RAIGEKI.characteristics.types)),
        card_def=RAIGEKI,
    )
    spell_mgr.activate_spell(raigeki.id, p1.id)

    # All opp monsters destroyed; our own untouched
    assert count_monsters(game, p2.id) == 0, "Raigeki must destroy all opponent monsters"
    assert count_monsters(game, p1.id) == 1, "Raigeki must NOT destroy own monsters"
    print("  PASS: test_raigeki_destroys_opponent_monsters_via_event")


def test_mobius_destroys_opp_spell_trap_on_tribute():
    """Mobius destroys up to 2 opp S/T on Tribute Summon."""
    game, p1, p2 = make_test_game()
    pipeline = game.pipeline

    # Set up 2 opp S/T
    st1 = create_in_zone(game, p2, MOUNTAIN_FIELD, ZoneType.SPELL_TRAP_ZONE)
    st2 = create_in_zone(game, p2, MOUNTAIN_FIELD, ZoneType.SPELL_TRAP_ZONE)
    # Place Mobius on field & emit YGO_TRIBUTE_SUMMON
    mobius = create_in_zone(game, p1, MOBIUS_THE_FROST_MONARCH, ZoneType.MONSTER_ZONE)

    # Sanity
    assert sum(1 for o in game.state.zones[f"spell_trap_zone_{p2.id}"].objects if o) == 2

    pipeline.emit(Event(
        type=EventType.YGO_TRIBUTE_SUMMON,
        payload={'card_id': mobius.id, 'player': p1.id, 'card_name': mobius.name},
        source=mobius.id, controller=p1.id,
    ))

    # Both opp S/T destroyed
    remaining = sum(1 for o in game.state.zones[f"spell_trap_zone_{p2.id}"].objects if o)
    assert remaining == 0, f"Mobius should clear 2 opp S/T, {remaining} remain"
    print("  PASS: test_mobius_destroys_opp_spell_trap_on_tribute")


def test_zaborg_destroys_one_monster_on_tribute():
    """Zaborg destroys 1 monster on Tribute Summon (prefers highest ATK opp)."""
    game, p1, p2 = make_test_game()
    pipeline = game.pipeline

    create_in_zone(game, p2, CELTIC_GUARDIAN, ZoneType.MONSTER_ZONE)  # 1400 ATK
    create_in_zone(game, p2, BLUE_EYES_WHITE_DRAGON, ZoneType.MONSTER_ZONE)  # 3000 ATK
    zaborg = create_in_zone(game, p1, ZABORG_THE_THUNDER_MONARCH, ZoneType.MONSTER_ZONE)

    assert count_monsters(game, p2.id) == 2

    pipeline.emit(Event(
        type=EventType.YGO_TRIBUTE_SUMMON,
        payload={'card_id': zaborg.id, 'player': p1.id, 'card_name': zaborg.name},
        source=zaborg.id, controller=p1.id,
    ))

    # 1 of 2 opp monsters destroyed; Blue-Eyes (higher ATK) should be the target
    remaining_names = []
    zone = game.state.zones[f"monster_zone_{p2.id}"]
    for oid in zone.objects:
        if oid is None:
            continue
        o = game.state.objects.get(oid)
        if o:
            remaining_names.append(o.name)
    assert len(remaining_names) == 1, f"Zaborg should destroy 1, remaining: {remaining_names}"
    assert remaining_names[0] == "Celtic Guardian", (
        f"Zaborg should kill highest-ATK (Blue-Eyes), kept: {remaining_names[0]}")
    print("  PASS: test_zaborg_destroys_one_monster_on_tribute")


def test_sangan_searches_on_send_to_gy():
    """Sangan searches a low-ATK monster when sent from the field to the GY."""
    game, p1, p2 = make_test_game()
    pipeline = game.pipeline

    # Populate p1's library with a low-ATK monster that Sangan can search
    target = game.create_object(
        name=CELTIC_GUARDIAN.name, owner_id=p1.id, zone=ZoneType.LIBRARY,
        characteristics=Characteristics(types=set(CELTIC_GUARDIAN.characteristics.types)),
        card_def=CELTIC_GUARDIAN,
    )

    sangan = create_in_zone(game, p1, SANGAN, ZoneType.MONSTER_ZONE)
    assert count_monsters(game, p1.id) == 1
    hand_before = len(game.state.zones[f"hand_{p1.id}"].objects)

    # Send Sangan to GY via the new event family.
    pipeline.emit(Event(
        type=EventType.YGO_SEND_TO_GY,
        payload={'card_id': sangan.id, 'reason': 'tribute'},
    ))

    # Hand grew by 1 (the searched monster)
    hand_after = len(game.state.zones[f"hand_{p1.id}"].objects)
    assert hand_after == hand_before + 1, (
        f"Sangan should add a card to hand: before={hand_before}, after={hand_after}")
    assert target.id in game.state.zones[f"hand_{p1.id}"].objects
    print("  PASS: test_sangan_searches_on_send_to_gy")


def test_witch_searches_on_send_to_gy():
    """Witch searches a low-DEF monster when sent from the field to the GY."""
    game, p1, p2 = make_test_game()
    pipeline = game.pipeline

    # ALEXANDRITE_DRAGON has DEF 100 (under 1500)
    target = game.create_object(
        name=ALEXANDRITE_DRAGON.name, owner_id=p1.id, zone=ZoneType.LIBRARY,
        characteristics=Characteristics(types=set(ALEXANDRITE_DRAGON.characteristics.types)),
        card_def=ALEXANDRITE_DRAGON,
    )
    witch = create_in_zone(game, p1, WITCH_OF_THE_BLACK_FOREST, ZoneType.MONSTER_ZONE)
    hand_before = len(game.state.zones[f"hand_{p1.id}"].objects)

    pipeline.emit(Event(
        type=EventType.YGO_SEND_TO_GY,
        payload={'card_id': witch.id, 'reason': 'effect'},
    ))

    hand_after = len(game.state.zones[f"hand_{p1.id}"].objects)
    assert hand_after == hand_before + 1
    assert target.id in game.state.zones[f"hand_{p1.id}"].objects
    print("  PASS: test_witch_searches_on_send_to_gy")


def test_armed_dragon_lv5_destroys_via_event():
    """Armed Dragon LV5: discard 1 monster from hand; destroy 1 opp monster with ATK <= discarded."""
    game, p1, p2 = make_test_game()
    pipeline = game.pipeline

    # AD LV5 on the field
    ad = create_in_zone(game, p1, ARMED_DRAGON_LV5, ZoneType.MONSTER_ZONE)
    # Discard candidate in hand: Battle Ox (1700 ATK)
    discard_pick = game.create_object(
        name=BATTLE_OX.name, owner_id=p1.id, zone=ZoneType.HAND,
        characteristics=Characteristics(types=set(BATTLE_OX.characteristics.types)),
        card_def=BATTLE_OX,
    )
    # Opp monster: Celtic Guardian (1400 ATK, <= 1700)
    cg = create_in_zone(game, p2, CELTIC_GUARDIAN, ZoneType.MONSTER_ZONE)

    pipeline.emit(Event(
        type=EventType.YGO_ACTIVATE_MONSTER_EFFECT,
        payload={'monster_id': ad.id, 'player': p1.id, 'card_id': ad.id},
        source=ad.id, controller=p1.id,
    ))

    # CG destroyed, discard sent to GY
    assert count_monsters(game, p2.id) == 0, "Armed Dragon should destroy CG"
    assert discard_pick.id in game.state.zones[f"graveyard_{p1.id}"].objects, \
        "Discard cost not paid"
    print("  PASS: test_armed_dragon_lv5_destroys_via_event")


def test_armed_dragon_lv7_destroys_all_via_event():
    """Armed Dragon LV7: discard 1 monster; destroy ALL opp monsters with ATK <= discarded."""
    game, p1, p2 = make_test_game()
    pipeline = game.pipeline

    ad = create_in_zone(game, p1, ARMED_DRAGON_LV7, ZoneType.MONSTER_ZONE)
    game.create_object(
        name=BATTLE_OX.name, owner_id=p1.id, zone=ZoneType.HAND,
        characteristics=Characteristics(types=set(BATTLE_OX.characteristics.types)),
        card_def=BATTLE_OX,
    )
    # 3 opp monsters: 2 below 1700, 1 above
    create_in_zone(game, p2, CELTIC_GUARDIAN, ZoneType.MONSTER_ZONE)  # 1400
    create_in_zone(game, p2, DARK_MAGICIAN, ZoneType.MONSTER_ZONE)    # 2500 — survives
    create_in_zone(game, p2, BATTLE_OX, ZoneType.MONSTER_ZONE)        # 1700 — destroyed

    pipeline.emit(Event(
        type=EventType.YGO_ACTIVATE_MONSTER_EFFECT,
        payload={'monster_id': ad.id, 'player': p1.id, 'card_id': ad.id},
        source=ad.id, controller=p1.id,
    ))

    assert count_monsters(game, p2.id) == 1, "AD7 should clear all ATK<=1700"
    # Dark Magician (2500) should be the survivor
    survivors = []
    for oid in game.state.zones[f"monster_zone_{p2.id}"].objects:
        if oid is None:
            continue
        o = game.state.objects.get(oid)
        if o:
            survivors.append(o.name)
    assert survivors == ["Dark Magician"], f"Survivors: {survivors}"
    print("  PASS: test_armed_dragon_lv7_destroys_all_via_event")


def test_breaker_destroys_spell_trap():
    """Breaker: spell counter on summon, ignition removes counter + destroys 1 S/T."""
    game, p1, p2 = make_test_game()
    pipeline = game.pipeline

    breaker = create_in_zone(game, p1, BREAKER_THE_MAGICAL_WARRIOR, ZoneType.MONSTER_ZONE)
    # Manually emit Normal Summon to trigger the spell-counter on-summon hook
    pipeline.emit(Event(
        type=EventType.YGO_NORMAL_SUMMON,
        payload={'card_id': breaker.id, 'player': p1.id, 'card_name': breaker.name},
        source=breaker.id, controller=p1.id,
    ))
    assert getattr(breaker.state, 'spell_counters', 0) == 1, "Spell Counter not placed"
    # 1 opp S/T to destroy
    st = create_in_zone(game, p2, MOUNTAIN_FIELD, ZoneType.SPELL_TRAP_ZONE)
    pipeline.emit(Event(
        type=EventType.YGO_ACTIVATE_MONSTER_EFFECT,
        payload={'monster_id': breaker.id, 'player': p1.id, 'card_id': breaker.id},
        source=breaker.id, controller=p1.id,
    ))
    # S/T destroyed and counter consumed
    assert getattr(breaker.state, 'spell_counters', 0) == 0
    remaining = sum(1 for o in game.state.zones[f"spell_trap_zone_{p2.id}"].objects if o)
    assert remaining == 0, f"Breaker should destroy 1 S/T, {remaining} left"
    print("  PASS: test_breaker_destroys_spell_trap")


def test_tribe_infecting_virus_clears_subtype():
    """Tribe-Infecting Virus: discard cost paid, declared type clears matching monsters."""
    game, p1, p2 = make_test_game()
    pipeline = game.pipeline

    tiv = create_in_zone(game, p1, TRIBE_INFECTING_VIRUS, ZoneType.MONSTER_ZONE)
    game.create_object(  # discard candidate
        name=CELTIC_GUARDIAN.name, owner_id=p1.id, zone=ZoneType.HAND,
        characteristics=Characteristics(types=set(CELTIC_GUARDIAN.characteristics.types)),
        card_def=CELTIC_GUARDIAN,
    )
    # 2 opp Beast-Warrior (e.g. Battle Ox) + 1 different (Dark Magician = Spellcaster)
    create_in_zone(game, p2, BATTLE_OX, ZoneType.MONSTER_ZONE)
    create_in_zone(game, p2, BATTLE_OX, ZoneType.MONSTER_ZONE)
    create_in_zone(game, p2, DARK_MAGICIAN, ZoneType.MONSTER_ZONE)

    pipeline.emit(Event(
        type=EventType.YGO_ACTIVATE_MONSTER_EFFECT,
        payload={'monster_id': tiv.id, 'player': p1.id, 'card_id': tiv.id},
        source=tiv.id, controller=p1.id,
    ))

    # Beast-Warriors gone; Dark Magician survives
    survivors = []
    for oid in game.state.zones[f"monster_zone_{p2.id}"].objects:
        if oid is None:
            continue
        o = game.state.objects.get(oid)
        if o:
            survivors.append(o.name)
    assert survivors == ["Dark Magician"], f"Survivors after TIV: {survivors}"
    print("  PASS: test_tribe_infecting_virus_clears_subtype")


def run_all():
    tests = [
        test_ygo_destroy_handler_moves_to_gy,
        test_ygo_send_to_gy_handler_moves_and_emits_only_sent,
        test_raigeki_destroys_opponent_monsters_via_event,
        test_mobius_destroys_opp_spell_trap_on_tribute,
        test_zaborg_destroys_one_monster_on_tribute,
        test_sangan_searches_on_send_to_gy,
        test_witch_searches_on_send_to_gy,
        test_armed_dragon_lv5_destroys_via_event,
        test_armed_dragon_lv7_destroys_all_via_event,
        test_breaker_destroys_spell_trap,
        test_tribe_infecting_virus_clears_subtype,
    ]
    failed = []
    for t in tests:
        try:
            t()
        except AssertionError as e:
            print(f"  FAIL: {t.__name__}: {e}")
            failed.append(t.__name__)
        except Exception as e:
            import traceback
            print(f"  ERROR: {t.__name__}: {type(e).__name__}: {e}")
            traceback.print_exc()
            failed.append(t.__name__)
    print()
    print(f"  Passed: {len(tests) - len(failed)}/{len(tests)}")
    if failed:
        print(f"  Failed: {failed}")
        sys.exit(1)


if __name__ == "__main__":
    run_all()
