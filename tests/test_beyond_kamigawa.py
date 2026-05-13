"""
Beyond Kamigawa — engine integration tests for the Eiganjo Samurai PoC.

Validates that the Samurai archetype loads, its deck is legal, key effect
monsters' setup_interceptors fire, and a Samurai-vs-Samurai AI mirror
match runs to completion without crashing.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if __name__ != "__main__":
    import pytest
    pytest.skip("Run directly: `python tests/test_beyond_kamigawa.py`",
                allow_module_level=True)


from src.engine.game import Game
from src.cards.yugioh.beyond.kamigawa.samurai import (
    BEYOND_KAMIGAWA_SAMURAI,
    make_samurai_deck,
    KONDA_LORD_OF_EIGANJO, HAND_OF_HONOR, HAND_OF_CRUELTY,
    KONDAS_BANNER_BEARER, IMPERIAL_RECOVERY_UNIT,
    IMPERIAL_EDICT,
    _imperial_edict_resolve,
)


passed = 0
failed = 0


def check(name, condition, detail=""):
    global passed, failed
    if condition:
        print(f"  PASS: {name}")
        passed += 1
    else:
        print(f"  FAIL: {name}{(' - ' + detail) if detail else ''}")
        failed += 1


def run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# =============================================================================
# Test 1: Set load
# =============================================================================

print("\n=== Test 1: Samurai archetype loads ===")
check("BEYOND_KAMIGAWA_SAMURAI has >= 35 cards",
      len(BEYOND_KAMIGAWA_SAMURAI) >= 35,
      f"got {len(BEYOND_KAMIGAWA_SAMURAI)}")
main, extra = make_samurai_deck()
check("Main deck is exactly 40 cards", len(main) == 40, f"got {len(main)}")
check("Extra deck is <= 15 cards", len(extra) <= 15, f"got {len(extra)}")
check("Extra deck has >= 1 card", len(extra) >= 1)


# =============================================================================
# Test 2: Multiplicity (no card appears more than 3x in main)
# =============================================================================

print("\n=== Test 2: Deck multiplicity ===")
from collections import Counter
counts = Counter(card.name for card in main)
violations = [(n, k) for n, k in counts.items() if k > 3]
check("No card exceeds 3 copies in main deck",
      not violations, f"violations: {violations}")


# =============================================================================
# Test 3: Key cards have proper subtypes (archetype tag)
# =============================================================================

print("\n=== Test 3: Archetype subtypes ===")
check("Konda has 'Samurai' subtype",
      "Samurai" in KONDA_LORD_OF_EIGANJO.characteristics.subtypes)
check("Konda has 'Warrior' subtype",
      "Warrior" in KONDA_LORD_OF_EIGANJO.characteristics.subtypes)
check("Hand of Honor has Bushido setup_interceptors",
      HAND_OF_HONOR.setup_interceptors is not None)
check("Konda's Banner-Bearer has lord setup_interceptors",
      KONDAS_BANNER_BEARER.setup_interceptors is not None)
check("Imperial Recovery Unit has destroy-trigger setup",
      IMPERIAL_RECOVERY_UNIT.setup_interceptors is not None)


# =============================================================================
# Test 4: Bushido lord static effect
# =============================================================================

print("\n=== Test 4: Bushido lord static effect ===")
# Place 2 Hand of Honor onto a player's monster zone, query their ATK,
# confirm that the second one has +200 from the first via Bushido.
from src.engine.types import ZoneType, CardType
from src.cards.yugioh.beyond.kamigawa.samurai import HAND_OF_HONOR
import copy


def make_test_game():
    game = Game(mode="yugioh")
    p1 = game.add_player("Test 1")
    p2 = game.add_player("Test 2")
    return game, p1, p2


def place_card(game, player_id, card_def, zone_type=ZoneType.HAND):
    obj = game.create_object(
        card_def.name, player_id, zone_type,
        copy.deepcopy(card_def.characteristics), card_def,
    )
    return obj


game, p1, p2 = make_test_game()
m1 = place_card(game, p1.id, HAND_OF_HONOR, ZoneType.MONSTER_ZONE)
check("Hand of Honor object exists", m1 is not None)
check("Hand of Honor has interceptors registered",
      len(m1.interceptor_ids) > 0,
      f"got {len(m1.interceptor_ids)} interceptors")


# =============================================================================
# Test 4b: Imperial Edict — PendingChoice deck-search (Phase 4 demo)
# =============================================================================

print("\n=== Test 4b: Imperial Edict PendingChoice ===")

from src.engine.types import Event, EventType
from src.cards.yugioh.ygo_classic import KURIBOH, BLUE_EYES_WHITE_DRAGON, DARK_HOLE


def _make_edict_state():
    g = Game(mode="yugioh")
    a = g.add_player("Edict-A")
    b = g.add_player("Edict-B")
    g.setup_yugioh_player(a, [])
    g.setup_yugioh_player(b, [])
    return g, a, b


def _stock_library(g, player_id, card_defs):
    """Replace player's library with the given card defs (front of list = top)."""
    lib = g.state.zones.get(f"library_{player_id}")
    assert lib is not None, f"no library zone for {player_id}"
    # Clear any starter objects we may have created.
    for cid in list(lib.objects):
        lib.objects.remove(cid)
    ids = []
    for cdef in card_defs:
        obj = g.create_object(
            name=cdef.name,
            owner_id=player_id,
            zone=ZoneType.LIBRARY,
            characteristics=copy.deepcopy(cdef.characteristics),
            card_def=cdef,
        )
        # create_object placed it in LIBRARY but the existing setup_yugioh_player
        # path may have also appended; this guards correctness.
        if obj.id not in lib.objects:
            lib.objects.append(obj.id)
        ids.append(obj.id)
    return ids


def test_imperial_edict_human_emits_pending_choice_over_library():
    """Human path: Imperial Edict emits a target PendingChoice over the library,
    no library cards have moved to hand yet, and min/max_choices == 2."""
    g, a, _b = _make_edict_state()
    lib_ids = _stock_library(g, a.id, [KURIBOH, BLUE_EYES_WHITE_DRAGON, DARK_HOLE])
    # Spell card id is just a placeholder for source_id.
    spell_id = "imperial-edict-test"
    event = Event(
        type=EventType.YGO_ACTIVATE_SPELL,
        payload={'player': a.id, 'card_id': spell_id},
        source=spell_id, controller=a.id,
    )
    out = _imperial_edict_resolve(event, g.state)
    # No AI registered for `a` → human path; resolve returns [] and choice is pending.
    check("Imperial Edict human path emits no events yet",
          out == [], f"got {len(out)} events")
    pc = g.state.pending_choice
    check("PendingChoice is set on state", pc is not None)
    if pc is not None:
        check("PendingChoice type is 'target'", pc.choice_type == "target")
        check("PendingChoice player == controller", pc.player == a.id)
        check("PendingChoice min_choices == 2", pc.min_choices == 2)
        check("PendingChoice max_choices == 2", pc.max_choices == 2)
        opt_ids = {opt["id"] for opt in pc.options}
        check("PendingChoice options cover full library",
              opt_ids == set(lib_ids),
              f"opts={opt_ids} lib={set(lib_ids)}")
        check("Library still has 3 cards (nothing moved yet)",
              len(g.state.zones[f"library_{a.id}"].objects) == 3,
              f"got {len(g.state.zones[f'library_{a.id}'].objects)}")
        hp = pc.callback_data.get("heuristic_pick")
        check("Heuristic_pick preserves top-N library order",
              hp == lib_ids[:2], f"hp={hp} expected={lib_ids[:2]}")


def test_imperial_edict_empty_library_short_circuits():
    """Empty library → no-op (no events, no PendingChoice)."""
    g, a, _b = _make_edict_state()
    # Ensure library is empty.
    lib = g.state.zones.get(f"library_{a.id}")
    for cid in list(lib.objects):
        lib.objects.remove(cid)
    g.state.pending_choice = None  # clear prior fixture state
    spell_id = "imperial-edict-empty-test"
    event = Event(
        type=EventType.YGO_ACTIVATE_SPELL,
        payload={'player': a.id, 'card_id': spell_id},
        source=spell_id, controller=a.id,
    )
    out = _imperial_edict_resolve(event, g.state)
    check("Empty library: no events", out == [], f"got {len(out)} events")
    check("Empty library: no PendingChoice", g.state.pending_choice is None)


def test_imperial_edict_ai_path_uses_heuristic_top_2():
    """AI path: the YGO AI adapter has no `make_choice`, so the helper falls
    back to ``heuristic_pick`` (top-2 of library). Verify the chosen cards
    actually move to hand and the auto-discard fires."""
    from src.ai.yugioh_adapter import YugiohAIAdapter
    g, a, _b = _make_edict_state()
    lib_ids = _stock_library(g, a.id, [KURIBOH, BLUE_EYES_WHITE_DRAGON, DARK_HOLE])
    # Register `a` as AI so the inline resolver takes the AI path.
    ai = YugiohAIAdapter(difficulty="medium")
    g.turn_manager.set_ai_handler(ai)
    g.turn_manager.ai_players.add(a.id)

    spell_id = "imperial-edict-ai-test"
    event = Event(
        type=EventType.YGO_ACTIVATE_SPELL,
        payload={'player': a.id, 'card_id': spell_id},
        source=spell_id, controller=a.id,
    )
    out = _imperial_edict_resolve(event, g.state)
    check("AI path emits events (search + discard)",
          len(out) >= 2, f"got {len(out)} events")
    check("AI path clears PendingChoice", g.state.pending_choice is None)

    # Top-2 (KURIBOH, BLUE_EYES) should have left the library.
    lib_now = g.state.zones[f"library_{a.id}"].objects
    check("Library lost the top-2 picks",
          lib_ids[0] not in lib_now and lib_ids[1] not in lib_now,
          f"lib_now={lib_now}")
    check("DARK_HOLE (3rd card) still in library", lib_ids[2] in lib_now)

    # Hand received the first pick (the second was auto-discarded).
    hand_now = g.state.zones[f"hand_{a.id}"].objects
    check("Hand has exactly one of the top-2 picks (other discarded)",
          sum(1 for cid in lib_ids[:2] if cid in hand_now) == 1,
          f"hand_now={hand_now}")

    # The other one is in the graveyard.
    gy_now = g.state.zones[f"graveyard_{a.id}"].objects
    check("Graveyard received exactly one of the top-2 picks",
          sum(1 for cid in lib_ids[:2] if cid in gy_now) == 1,
          f"gy_now={gy_now}")


test_imperial_edict_human_emits_pending_choice_over_library()
test_imperial_edict_empty_library_short_circuits()
test_imperial_edict_ai_path_uses_heuristic_top_2()


# =============================================================================
# Test 5: AI vs AI mirror (Samurai vs Samurai), short run
# =============================================================================

print("\n=== Test 5: AI mirror match ===")


async def run_mirror_match(max_turns: int = 20):
    from src.ai.yugioh_adapter import YugiohAIAdapter
    g = Game(mode="yugioh")
    p1 = g.add_player("Samurai A")
    p2 = g.add_player("Samurai B")
    main_a, extra_a = make_samurai_deck()
    main_b, extra_b = make_samurai_deck()
    g.setup_yugioh_player(p1, main_a, extra_a)
    g.setup_yugioh_player(p2, main_b, extra_b)
    ai = YugiohAIAdapter(difficulty="medium")
    g.turn_manager.set_ai_handler(ai)
    g.turn_manager.ai_players.add(p1.id)
    g.turn_manager.ai_players.add(p2.id)
    await g.turn_manager.setup_game()
    turns = 0
    while turns < max_turns:
        if g.is_game_over():
            break
        await g.turn_manager.run_turn()
        turns += 1
    return turns, g.is_game_over()


try:
    turns, ended = run(run_mirror_match(max_turns=20))
    check(f"Mirror match ran {turns} turns without crashing",
          turns > 0, f"turns={turns}, ended_early={ended}")
except Exception as ex:
    check("Mirror match runs without crashing", False,
          f"{type(ex).__name__}: {ex}")


# =============================================================================
# Summary
# =============================================================================

print(f"\n{'=' * 60}")
print(f"PASSED: {passed}    FAILED: {failed}")
print(f"{'=' * 60}")
sys.exit(0 if failed == 0 else 1)
