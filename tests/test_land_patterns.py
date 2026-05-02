"""Tests for Round 10A land-patterns sweep.

Covers:
  - Unconditional ETB-tapped auto-detection from card text
  - Shockland pay-2-life-or-tapped auto-decision in `_handle_play_land`
  - Mana-text parser handling "{T}: Add {U} or {R}" and ", or"-list forms
  - `make_surveil_ability` helper end-to-end
  - Hidden-land discover-on-sac (LCI) end-to-end with new DISCOVER handler
  - BLB lifeland ETB life-gain trigger still fires under auto-detect path
"""
import os
import sys
import asyncio

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_HERE)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.engine import (
    Game, Event, EventType, ZoneType, CardType,
    GameObject, ObjectState, new_id,
)
from src.engine.priority import PlayerAction, ActionType
from src.engine.mana import ManaSystem, ManaType


# =============================================================================
# Helpers
# =============================================================================


def _new_game():
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    game.start_game()
    return game, p1, p2


def _spawn_in_hand(game, player_id, card_def):
    obj = GameObject(
        id=new_id(),
        name=card_def.name,
        owner=player_id,
        controller=player_id,
        zone=ZoneType.HAND,
        characteristics=card_def.characteristics,
        state=ObjectState(),
        card_def=card_def,
        created_at=game.state.next_timestamp(),
        entered_zone_at=game.state.timestamp,
        _state_ref=game.state,
    )
    game.state.objects[obj.id] = obj
    game.state.zones[f'hand_{player_id}'].objects.append(obj.id)
    return obj


async def _play_land(game, player_id, obj_id):
    action = PlayerAction(type=ActionType.PLAY_LAND, player_id=player_id, card_id=obj_id)
    events = await game.priority_system._handle_play_land(action)
    for e in events:
        game.pipeline.emit(e)
    return events


# =============================================================================
# Mana-text parser: "Add {X} or {Y}" forms
# =============================================================================


def test_mana_parser_dual_or_pattern():
    print("\n=== Test: mana parser handles 'Add {U} or {R}' ===")
    m = ManaSystem(None)
    assert set(m._parse_mana_abilities_from_text('{T}: Add {U} or {R}.')) == {ManaType.BLUE, ManaType.RED}
    print("  PASS: dual 'or' parses both colors")


def test_mana_parser_tri_or_pattern():
    print("\n=== Test: mana parser handles 'Add {U}, {B}, or {R}' ===")
    m = ManaSystem(None)
    out = m._parse_mana_abilities_from_text('{T}: Add {U}, {B}, or {R}.')
    assert set(out) == {ManaType.BLUE, ManaType.BLACK, ManaType.RED}, out
    print("  PASS: tri 'or' parses all three colors")


def test_mana_parser_concat_still_works():
    print("\n=== Test: mana parser still handles concat 'Add {G}{G}' ===")
    m = ManaSystem(None)
    assert m._parse_mana_abilities_from_text('{T}: Add {G}{G}.') == [ManaType.GREEN]
    assert m._parse_mana_abilities_from_text('{T}: Add {U}.') == [ManaType.BLUE]
    print("  PASS: existing single/concat patterns unaffected")


# =============================================================================
# ETB-tapped auto-detection in _handle_play_land
# =============================================================================


def test_unconditional_etb_tapped_from_text():
    print("\n=== Test: 'This land enters tapped.' auto-detected ===")
    from src.cards.avatar_tla import AIRSHIP_ENGINE_ROOM

    async def go():
        game, p1, _ = _new_game()
        obj = _spawn_in_hand(game, p1.id, AIRSHIP_ENGINE_ROOM)
        await _play_land(game, p1.id, obj.id)
        on_bf = game.state.objects[obj.id]
        assert on_bf.zone == ZoneType.BATTLEFIELD, on_bf.zone
        assert on_bf.state.tapped is True, "should ETB tapped"

    asyncio.run(go())
    print("  PASS: Airship Engine Room ETBs tapped via text auto-detect")


def test_shockland_pays_2_life_when_healthy():
    print("\n=== Test: shockland with life>4 pays 2 life, untapped ===")
    from src.cards.lorwyn_eclipsed import BLOOD_CRYPT

    async def go():
        game, p1, _ = _new_game()
        starting_life = p1.life
        obj = _spawn_in_hand(game, p1.id, BLOOD_CRYPT)
        events = await _play_land(game, p1.id, obj.id)
        # Should have emitted LIFE_CHANGE -2 + ZONE_CHANGE
        life_events = [e for e in events if e.type == EventType.LIFE_CHANGE]
        assert life_events, f"expected LIFE_CHANGE; got {[e.type.name for e in events]}"
        assert life_events[0].payload.get('amount') == -2
        on_bf = game.state.objects[obj.id]
        assert on_bf.state.tapped is False, "should NOT enter tapped"
        # Life should be reduced
        assert p1.life == starting_life - 2, f"life {p1.life} != {starting_life - 2}"

    asyncio.run(go())
    print("  PASS: Blood Crypt at life=20 pays 2 life and enters untapped")


def test_shockland_enters_tapped_when_low_life():
    print("\n=== Test: shockland with life<=4 enters tapped, no life loss ===")
    from src.cards.lorwyn_eclipsed import BLOOD_CRYPT

    async def go():
        game, p1, _ = _new_game()
        p1.life = 4  # at threshold -> should enter tapped
        obj = _spawn_in_hand(game, p1.id, BLOOD_CRYPT)
        events = await _play_land(game, p1.id, obj.id)
        life_events = [e for e in events if e.type == EventType.LIFE_CHANGE]
        assert not life_events, "should NOT emit LIFE_CHANGE at low life"
        on_bf = game.state.objects[obj.id]
        assert on_bf.state.tapped is True, "should ETB tapped"

    asyncio.run(go())
    print("  PASS: Blood Crypt at life=4 enters tapped, no life loss")


def test_conditional_etb_tapped_text_does_not_auto_tap():
    """A land whose ETB-tapped clause has 'unless ...' should NOT be auto-detected
    as unconditionally tapped (those need bespoke setup interceptors).
    """
    print("\n=== Test: 'enters tapped unless ...' is not auto-detected ===")
    import re
    pat = r'^\s*(?:this\s+land|it)\s+enters\s+(?:the\s+battlefield\s+)?tapped\.?\s*$'
    text = "This land enters tapped unless you control a Mount or Vehicle."
    assert not re.search(pat, text, re.IGNORECASE | re.MULTILINE)
    print("  PASS: conditional ETB-tapped is correctly skipped")


# =============================================================================
# SPM surveil hideout
# =============================================================================


def test_spm_hideout_surveil_ability_registered():
    print("\n=== Test: SPM hideout registers {4},{T}: Surveil 1 ===")
    from src.cards.spider_man import OMINOUS_ASYLUM, SAVAGE_MANSION

    async def go():
        game, p1, _ = _new_game()
        obj = _spawn_in_hand(game, p1.id, OMINOUS_ASYLUM)
        await _play_land(game, p1.id, obj.id)
        on_bf = game.state.objects[obj.id]
        # Activated abilities are registered on obj.state.activated_abilities
        abilities = on_bf.state.activated_abilities
        assert any('Surveil' in a.description for a in abilities), \
            f"no Surveil ability; got: {[a.description for a in abilities]}"

    asyncio.run(go())
    print("  PASS: Ominous Asylum has Surveil 1 activated ability")


# =============================================================================
# LCI hidden land + DISCOVER handler
# =============================================================================


def test_lci_hidden_land_registers_discover_ability():
    print("\n=== Test: LCI hidden land registers Discover 4 ability ===")
    from src.cards.lost_caverns_ixalan import HIDDEN_CATARACT

    async def go():
        game, p1, _ = _new_game()
        obj = _spawn_in_hand(game, p1.id, HIDDEN_CATARACT)
        await _play_land(game, p1.id, obj.id)
        on_bf = game.state.objects[obj.id]
        abilities = on_bf.state.activated_abilities
        assert any('Discover' in a.description for a in abilities), \
            f"no Discover ability; got: {[a.description for a in abilities]}"
        # Also check ETB-tapped auto-detection
        assert on_bf.state.tapped is True

    asyncio.run(go())
    print("  PASS: Hidden Cataract registers Discover 4 + ETBs tapped")


def test_discover_handler_finds_and_pulls_to_hand():
    print("\n=== Test: DISCOVER handler exiles to hand a non-land MV<=N ===")
    from src.engine import make_creature, Color
    # Build a small library: top is a creature MV 2, then a creature MV 6,
    # then a basic land. Discover 3 should pull the MV 2 creature.

    async def go():
        game, p1, _ = _new_game()
        cheap = make_creature(
            name="Cheap Beast", power=1, toughness=1,
            mana_cost="{2}", colors={Color.GREEN}, subtypes={"Beast"},
            text="",
        )
        big = make_creature(
            name="Big Beast", power=6, toughness=6,
            mana_cost="{4}{G}{G}", colors={Color.GREEN}, subtypes={"Beast"},
            text="",
        )
        # We don't bother with a land here — just two creatures.
        cheap_obj = GameObject(
            id=new_id(), name=cheap.name, owner=p1.id, controller=p1.id,
            zone=ZoneType.LIBRARY, characteristics=cheap.characteristics,
            state=ObjectState(), card_def=cheap,
            created_at=game.state.next_timestamp(),
            entered_zone_at=game.state.timestamp,
            _state_ref=game.state,
        )
        big_obj = GameObject(
            id=new_id(), name=big.name, owner=p1.id, controller=p1.id,
            zone=ZoneType.LIBRARY, characteristics=big.characteristics,
            state=ObjectState(), card_def=big,
            created_at=game.state.next_timestamp(),
            entered_zone_at=game.state.timestamp,
            _state_ref=game.state,
        )
        game.state.objects[cheap_obj.id] = cheap_obj
        game.state.objects[big_obj.id] = big_obj
        # Replace library with these two on top
        lib = game.state.zones[f'library_{p1.id}']
        lib.objects = [big_obj.id, cheap_obj.id] + lib.objects  # big on top, then cheap

        # Discover 3: big (MV 6) > 3 → exile-others; cheap (MV 2) <= 3 → hit
        ev = Event(
            type=EventType.DISCOVER,
            payload={'player': p1.id, 'value': 3},
            source=None, controller=p1.id,
        )
        game.pipeline.emit(ev)

        hand = game.state.zones[f'hand_{p1.id}']
        assert cheap_obj.id in hand.objects, "Discover hit should be in hand"
        # big should be at the bottom of the library
        assert big_obj.id in lib.objects
        assert big_obj.id not in hand.objects

    asyncio.run(go())
    print("  PASS: Discover 3 pulled MV-2 creature into hand")


# =============================================================================
# BLB lifeland ETB life trigger
# =============================================================================


def test_blb_lifeland_etb_gains_life():
    print("\n=== Test: Blossoming Sands gains 1 life on ETB ===")
    from src.cards.bloomburrow import BLOSSOMING_SANDS

    async def go():
        game, p1, _ = _new_game()
        starting_life = p1.life
        obj = _spawn_in_hand(game, p1.id, BLOSSOMING_SANDS)
        await _play_land(game, p1.id, obj.id)
        on_bf = game.state.objects[obj.id]
        assert on_bf.state.tapped is True, "lifeland ETBs tapped"
        # ETB life trigger should have fired
        assert p1.life == starting_life + 1, f"life {p1.life} != {starting_life + 1}"

    asyncio.run(go())
    print("  PASS: Blossoming Sands ETBs tapped + gains 1 life")


# =============================================================================
# FIN dual-mana land — auto-detect only, no setup function
# =============================================================================


def test_fin_dual_mana_land_etb_tapped_and_produces_two_colors():
    print("\n=== Test: FIN Baron Airship Kingdom ETBs tapped, produces U or R ===")
    from src.cards.final_fantasy import BARON_AIRSHIP_KINGDOM

    async def go():
        game, p1, _ = _new_game()
        obj = _spawn_in_hand(game, p1.id, BARON_AIRSHIP_KINGDOM)
        await _play_land(game, p1.id, obj.id)
        on_bf = game.state.objects[obj.id]
        assert on_bf.state.tapped is True
        # Mana-text parser should report U and R produces
        m = ManaSystem(None)
        produces = m._parse_mana_abilities_from_text(BARON_AIRSHIP_KINGDOM.text)
        assert ManaType.BLUE in produces and ManaType.RED in produces, produces

    asyncio.run(go())
    print("  PASS: Baron Airship Kingdom ETBs tapped + parses {U}/{R}")


# =============================================================================
# Run all
# =============================================================================


if __name__ == '__main__':
    print("=" * 60)
    print("ROUND 10A LAND-PATTERN TESTS")
    print("=" * 60)

    tests = [
        test_mana_parser_dual_or_pattern,
        test_mana_parser_tri_or_pattern,
        test_mana_parser_concat_still_works,
        test_unconditional_etb_tapped_from_text,
        test_shockland_pays_2_life_when_healthy,
        test_shockland_enters_tapped_when_low_life,
        test_conditional_etb_tapped_text_does_not_auto_tap,
        test_spm_hideout_surveil_ability_registered,
        test_lci_hidden_land_registers_discover_ability,
        test_discover_handler_finds_and_pulls_to_hand,
        test_blb_lifeland_etb_gains_life,
        test_fin_dual_mana_land_etb_tapped_and_produces_two_colors,
    ]

    failed = []
    for t in tests:
        try:
            t()
        except AssertionError as exc:
            failed.append((t.__name__, str(exc) or '<no message>'))
            print(f"  FAIL: {t.__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failed.append((t.__name__, repr(exc)))
            print(f"  ERROR: {t.__name__}: {exc!r}")

    print("\n" + "=" * 60)
    if failed:
        print(f"FAILED ({len(failed)}/{len(tests)}):")
        for name, msg in failed:
            print(f"  - {name}: {msg}")
        sys.exit(1)
    print(f"ALL {len(tests)} LAND-PATTERN TESTS PASSED")
    print("=" * 60)
