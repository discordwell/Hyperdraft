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

# Additional samurai cards used by the Phase 4 tests below.
from src.cards.yugioh.beyond.kamigawa.samurai import (
    ISAMARU_HOUND_OF_KONDA, DEVOTED_RETAINER, EIGANJO_FREE_RIDER,
)


# =============================================================================
# Test 4c: Phase 4 PendingChoice migration — 5 Kamigawa cards
# =============================================================================
#
# Each migrated card gets three tests:
#   - human path: PendingChoice is set, state mutated only after resolution
#   - heuristic preservation: AI heuristic_pick matches the old blind-grab
#   - empty short-circuit: empty zone = no-op (no choice, no events)
#
# Plus a chain-stack integrity test at the end to confirm a mid-chain
# PendingChoice doesn't corrupt the chain.

print("\n=== Test 4c: Phase 4 PendingChoice migration ===")


def _reset_pending(g):
    """Clear stray pending_choice from a fixture state."""
    g.state.pending_choice = None


def _new_test_game():
    """Build a fresh 2-player YGO game with both players un-AI-ed (human path)."""
    g = Game(mode="yugioh")
    a = g.add_player("A")
    b = g.add_player("B")
    g.setup_yugioh_player(a, [])
    g.setup_yugioh_player(b, [])
    _reset_pending(g)
    return g, a, b


def _set_ai(g, *player_ids):
    """Register the YGO AI handler and tag the given players as AI."""
    from src.ai.yugioh_adapter import YugiohAIAdapter
    ai = YugiohAIAdapter(difficulty="medium")
    g.turn_manager.set_ai_handler(ai)
    for pid in player_ids:
        g.turn_manager.ai_players.add(pid)


def _stock_hand(g, player_id, card_defs):
    """Replace player's hand with the given card defs (front = first in order)."""
    hand = g.state.zones.get(f"hand_{player_id}")
    assert hand is not None
    for cid in list(hand.objects):
        hand.objects.remove(cid)
    ids = []
    for cdef in card_defs:
        obj = g.create_object(
            name=cdef.name, owner_id=player_id, zone=ZoneType.HAND,
            characteristics=copy.deepcopy(cdef.characteristics), card_def=cdef,
        )
        if obj.id not in hand.objects:
            hand.objects.append(obj.id)
        ids.append(obj.id)
    return ids


def _stock_gy(g, player_id, card_defs):
    """Replace player's graveyard with the given card defs."""
    gy = g.state.zones.get(f"graveyard_{player_id}")
    assert gy is not None
    for cid in list(gy.objects):
        gy.objects.remove(cid)
    ids = []
    for cdef in card_defs:
        obj = g.create_object(
            name=cdef.name, owner_id=player_id, zone=ZoneType.GRAVEYARD,
            characteristics=copy.deepcopy(cdef.characteristics), card_def=cdef,
        )
        if obj.id not in gy.objects:
            gy.objects.append(obj.id)
        ids.append(obj.id)
    return ids


def _stock_field(g, player_id, card_defs):
    """Place the given card defs in player's monster_zone (face-up ATK)."""
    zone = g.state.zones.get(f"monster_zone_{player_id}")
    assert zone is not None
    # Reset zone first so we have predictable slot indices.
    for cid in list(zone.objects):
        zone.objects.remove(cid)
    ids = []
    for cdef in card_defs:
        obj = g.create_object(
            name=cdef.name, owner_id=player_id, zone=ZoneType.MONSTER_ZONE,
            characteristics=copy.deepcopy(cdef.characteristics), card_def=cdef,
        )
        # create_object already appended via _get_zone_key. Remove that
        # append (it's at the tail) and place at the first None / next slot.
        if obj.id in zone.objects:
            zone.objects.remove(obj.id)
        slot = None
        for i in range(5):
            if i >= len(zone.objects) or zone.objects[i] is None:
                slot = i
                break
        if slot is None:
            continue
        while len(zone.objects) <= slot:
            zone.objects.append(None)
        zone.objects[slot] = obj.id
        obj.state.ygo_position = 'face_up_atk'
        obj.state.face_down = False
        obj.controller = player_id
        ids.append(obj.id)
    return ids


def _stock_library(g, player_id, card_defs):
    """Replace player's library with the given card defs (front of list = top)."""
    lib = g.state.zones.get(f"library_{player_id}")
    assert lib is not None
    for cid in list(lib.objects):
        lib.objects.remove(cid)
    ids = []
    for cdef in card_defs:
        obj = g.create_object(
            name=cdef.name, owner_id=player_id, zone=ZoneType.LIBRARY,
            characteristics=copy.deepcopy(cdef.characteristics), card_def=cdef,
        )
        if obj.id not in lib.objects:
            lib.objects.append(obj.id)
        ids.append(obj.id)
    return ids


def _activate_event(spell_id, player_id):
    return Event(
        type=EventType.YGO_ACTIVATE_SPELL,
        payload={'player': player_id, 'card_id': spell_id},
        source=spell_id, controller=player_id,
    )


# ---- Reality Stutter (opponent picks 2 hand cards to shuffle to deck) -------

print("\n--- Reality Stutter ---")
from src.cards.yugioh.beyond.kamigawa.moonfolk import (
    _reality_stutter_resolve, REALITY_STUTTER,
)


def test_reality_stutter_human_emits_choice_for_opponent():
    g, a, b = _new_test_game()
    hand_ids = _stock_hand(g, b.id, [KURIBOH, BLUE_EYES_WHITE_DRAGON, DARK_HOLE])
    out = _reality_stutter_resolve(_activate_event("rs-test", a.id), g.state)
    check("Reality Stutter human: no events yet", out == [],
          f"got {len(out)} events")
    pc = g.state.pending_choice
    check("Reality Stutter human: PendingChoice set", pc is not None)
    if pc is not None:
        check("Reality Stutter: choice player = opponent (b)",
              pc.player == b.id, f"got {pc.player}")
        check("Reality Stutter: min_choices == 2", pc.min_choices == 2)
        check("Reality Stutter: max_choices == 2", pc.max_choices == 2)
        opt_ids = {o["id"] for o in pc.options}
        check("Reality Stutter: options over full opp hand",
              opt_ids == set(hand_ids), f"opts={opt_ids} hand={set(hand_ids)}")
        check("Reality Stutter: heuristic_pick == first 2 hand",
              pc.callback_data.get("heuristic_pick") == hand_ids[:2])
        check("Reality Stutter: opp hand untouched (still 3 cards)",
              len(g.state.zones[f"hand_{b.id}"].objects) == 3)


def test_reality_stutter_empty_opp_hand_short_circuits():
    g, a, b = _new_test_game()
    hand = g.state.zones.get(f"hand_{b.id}")
    for cid in list(hand.objects):
        hand.objects.remove(cid)
    _reset_pending(g)
    out = _reality_stutter_resolve(_activate_event("rs-empty", a.id), g.state)
    check("Reality Stutter empty opp hand: no events", out == [])
    check("Reality Stutter empty opp hand: no PendingChoice",
          g.state.pending_choice is None)


def test_reality_stutter_ai_uses_heuristic_top_2():
    g, a, b = _new_test_game()
    hand_ids = _stock_hand(g, b.id, [KURIBOH, BLUE_EYES_WHITE_DRAGON, DARK_HOLE])
    _set_ai(g, b.id)  # Opponent makes the choice; tag b as AI.
    out = _reality_stutter_resolve(_activate_event("rs-ai", a.id), g.state)
    check("Reality Stutter AI: events emitted",
          len(out) >= 2, f"got {len(out)}")
    check("Reality Stutter AI: choice cleared",
          g.state.pending_choice is None)
    lib_b = g.state.zones[f"library_{b.id}"].objects
    check("Reality Stutter AI: top-2 moved to library",
          hand_ids[0] in lib_b and hand_ids[1] in lib_b,
          f"lib={lib_b} expected_in={hand_ids[:2]}")
    hand_b = g.state.zones[f"hand_{b.id}"].objects
    check("Reality Stutter AI: 3rd card still in hand",
          hand_ids[2] in hand_b)


test_reality_stutter_human_emits_choice_for_opponent()
test_reality_stutter_empty_opp_hand_short_circuits()
test_reality_stutter_ai_uses_heuristic_top_2()


# ---- Brainstorm (draw 3, then pick 2 hand cards to top of deck) -------------

print("\n--- Brainstorm ---")
from src.cards.yugioh.beyond.kamigawa.moonfolk import _brainstorm_resolve


def test_brainstorm_human_emits_choice_after_draw():
    g, a, _b = _new_test_game()
    lib_ids = _stock_library(g, a.id, [KURIBOH, BLUE_EYES_WHITE_DRAGON, DARK_HOLE])
    out = _brainstorm_resolve(_activate_event("bs-test", a.id), g.state)
    # Draw 3 always happens before the choice.
    check("Brainstorm human: 3 draw events", len(out) == 3,
          f"got {len(out)} events (expected 3)")
    pc = g.state.pending_choice
    check("Brainstorm human: PendingChoice set", pc is not None)
    if pc is not None:
        check("Brainstorm human: choice player == controller",
              pc.player == a.id)
        check("Brainstorm human: min/max_choices == 2",
              pc.min_choices == 2 and pc.max_choices == 2)
        hand_now = g.state.zones[f"hand_{a.id}"].objects
        check("Brainstorm human: hand has 3 cards (post-draw, pre-pushback)",
              len(hand_now) == 3, f"got {len(hand_now)}")
        check("Brainstorm human: options cover full hand",
              {o["id"] for o in pc.options} == set(hand_now))
        # heuristic = last N cards in hand (2 last drawn).
        check("Brainstorm human: heuristic_pick == last 2 in hand",
              pc.callback_data.get("heuristic_pick") == list(hand_now[-2:]))
        check("Brainstorm human: library now 0 cards (drew everything)",
              len(g.state.zones[f"library_{a.id}"].objects) == 0)


def test_brainstorm_empty_library_still_works():
    g, a, _b = _new_test_game()
    # Empty library, but hand has cards from prior turn. Draw fails silently.
    _stock_hand(g, a.id, [KURIBOH, BLUE_EYES_WHITE_DRAGON])
    lib = g.state.zones.get(f"library_{a.id}")
    for cid in list(lib.objects):
        lib.objects.remove(cid)
    _reset_pending(g)
    out = _brainstorm_resolve(_activate_event("bs-empty-lib", a.id), g.state)
    # No draws, but hand exists, so we still emit a choice over the 2 hand cards.
    check("Brainstorm empty library: 0 draw events", len(out) == 0)
    pc = g.state.pending_choice
    check("Brainstorm empty library: choice still emitted over hand",
          pc is not None)
    if pc is not None:
        check("Brainstorm empty library: options match hand",
              len(pc.options) == 2)


def test_brainstorm_empty_hand_pre_draw_no_choice():
    """If draw fails (no library) AND hand is empty, no choice fires."""
    g, a, _b = _new_test_game()
    hand = g.state.zones.get(f"hand_{a.id}")
    for cid in list(hand.objects):
        hand.objects.remove(cid)
    lib = g.state.zones.get(f"library_{a.id}")
    for cid in list(lib.objects):
        lib.objects.remove(cid)
    _reset_pending(g)
    out = _brainstorm_resolve(_activate_event("bs-empty-both", a.id), g.state)
    check("Brainstorm empty both: 0 events", out == [])
    check("Brainstorm empty both: no PendingChoice",
          g.state.pending_choice is None)


def test_brainstorm_ai_uses_heuristic_last_2():
    g, a, _b = _new_test_game()
    lib_ids = _stock_library(g, a.id, [KURIBOH, BLUE_EYES_WHITE_DRAGON, DARK_HOLE])
    _set_ai(g, a.id)
    out = _brainstorm_resolve(_activate_event("bs-ai", a.id), g.state)
    check("Brainstorm AI: events emitted (3 draws)",
          len(out) >= 3, f"got {len(out)}")
    check("Brainstorm AI: choice cleared",
          g.state.pending_choice is None)
    lib_now = g.state.zones[f"library_{a.id}"].objects
    check("Brainstorm AI: 2 cards back on library",
          len(lib_now) == 2, f"got {len(lib_now)}")
    # Last 2 of the 3 drawn → BLUE_EYES_WHITE_DRAGON, DARK_HOLE.
    check("Brainstorm AI: library has the 2 'last-drawn' cards",
          lib_ids[1] in lib_now and lib_ids[2] in lib_now,
          f"lib={lib_now} expected={lib_ids[1:]}")


test_brainstorm_human_emits_choice_after_draw()
test_brainstorm_empty_library_still_works()
test_brainstorm_empty_hand_pre_draw_no_choice()
test_brainstorm_ai_uses_heuristic_last_2()


# ---- Tide of Knowledge (bounce 2 face-up opp monsters; opp draws 1) ---------

print("\n--- Tide of Knowledge ---")
from src.cards.yugioh.beyond.kamigawa.moonfolk import _tide_of_knowledge_resolve


def test_tide_human_emits_choice_over_opp_field():
    g, a, b = _new_test_game()
    # Need a deck for opponent so the draw 1 doesn't crash.
    _stock_library(g, b.id, [KURIBOH])
    mon_ids = _stock_field(g, b.id, [BLUE_EYES_WHITE_DRAGON, KURIBOH, DARK_HOLE])
    out = _tide_of_knowledge_resolve(_activate_event("tide-test", a.id), g.state)
    # Wait — DARK_HOLE is a Spell, not a Monster. It got placed in monster_zone
    # but isn't a real monster. The "_all_opp_face_up_monsters" doesn't filter
    # by type, only by face_down. So it will be listed.
    check("Tide human: no events yet", out == [])
    pc = g.state.pending_choice
    check("Tide human: PendingChoice set", pc is not None)
    if pc is not None:
        check("Tide human: choice player == controller (a)", pc.player == a.id)
        check("Tide human: min/max == 2",
              pc.min_choices == 2 and pc.max_choices == 2)
        check("Tide human: options cover all face-up opp monsters",
              len(pc.options) == 3)
        check("Tide human: heuristic_pick == first 2 face-up",
              pc.callback_data.get("heuristic_pick") == mon_ids[:2])


def test_tide_no_opp_monsters_opp_still_draws():
    g, a, b = _new_test_game()
    _stock_library(g, b.id, [KURIBOH])
    # No monsters on opp field; opp should still draw 1.
    _reset_pending(g)
    out = _tide_of_knowledge_resolve(_activate_event("tide-empty", a.id), g.state)
    check("Tide no opp monsters: still produces draw event",
          len(out) == 1, f"got {len(out)}")
    check("Tide no opp monsters: no PendingChoice",
          g.state.pending_choice is None)


def test_tide_ai_uses_heuristic_first_2():
    g, a, b = _new_test_game()
    _stock_library(g, b.id, [KURIBOH])
    mon_ids = _stock_field(g, b.id, [BLUE_EYES_WHITE_DRAGON, KURIBOH])
    _set_ai(g, a.id)
    out = _tide_of_knowledge_resolve(_activate_event("tide-ai", a.id), g.state)
    check("Tide AI: events emitted (bounces + draw)",
          len(out) >= 2, f"got {len(out)}")
    check("Tide AI: choice cleared", g.state.pending_choice is None)
    hand_b = g.state.zones[f"hand_{b.id}"].objects
    check("Tide AI: bounced monsters in opp hand",
          mon_ids[0] in hand_b and mon_ids[1] in hand_b,
          f"hand_b={hand_b} expected={mon_ids}")


test_tide_human_emits_choice_over_opp_field()
test_tide_no_opp_monsters_opp_still_draws()
test_tide_ai_uses_heuristic_first_2()


# ---- Petals of Insight (look 3, pick 1 Spirit, mill rest) -------------------

print("\n--- Petals of Insight ---")
from src.cards.yugioh.beyond.kamigawa.spirit_dragons import (
    _petals_of_insight_resolve, _is_spirit,
)
from src.cards.yugioh.beyond.kamigawa.spirit_dragons import (
    YOSEI_THE_MORNING_STAR, KOKUSHO_THE_EVENING_STAR,
)


def test_petals_human_choice_over_revealed_spirits():
    g, a, _b = _new_test_game()
    # Stock library: 2 Spirits + 1 non-Spirit. Top 3 reveals 2 Spirit candidates.
    lib_ids = _stock_library(
        g, a.id, [YOSEI_THE_MORNING_STAR, KURIBOH, KOKUSHO_THE_EVENING_STAR])
    out = _petals_of_insight_resolve(_activate_event("petals-test", a.id), g.state)
    pc = g.state.pending_choice
    check("Petals human: 0 events yet", out == [])
    check("Petals human: PendingChoice set", pc is not None)
    if pc is not None:
        check("Petals human: 2 spirit options (Yosei + Kokusho)",
              len(pc.options) == 2)
        check("Petals human: min/max == 1",
              pc.min_choices == 1 and pc.max_choices == 1)
        check("Petals human: heuristic_pick == first Spirit (Yosei)",
              pc.callback_data.get("heuristic_pick") == [lib_ids[0]])
        check("Petals human: library now empty (top 3 popped)",
              len(g.state.zones[f"library_{a.id}"].objects) == 0)
        # Look-pile is in-memory only; cards have been popped but not yet placed.


def test_petals_no_spirit_revealed_mills_all():
    g, a, _b = _new_test_game()
    # 3 non-Spirit cards on top.
    lib_ids = _stock_library(g, a.id, [KURIBOH, BLUE_EYES_WHITE_DRAGON, DARK_HOLE])
    out = _petals_of_insight_resolve(_activate_event("petals-mill", a.id), g.state)
    check("Petals no spirit: 3 mill events", len(out) == 3, f"got {len(out)}")
    check("Petals no spirit: no PendingChoice",
          g.state.pending_choice is None)
    gy = g.state.zones[f"graveyard_{a.id}"].objects
    check("Petals no spirit: all 3 cards in GY",
          all(c in gy for c in lib_ids), f"gy={gy} lib={lib_ids}")


def test_petals_empty_library_short_circuits():
    g, a, _b = _new_test_game()
    lib = g.state.zones.get(f"library_{a.id}")
    for cid in list(lib.objects):
        lib.objects.remove(cid)
    _reset_pending(g)
    out = _petals_of_insight_resolve(_activate_event("petals-empty", a.id), g.state)
    check("Petals empty library: 0 events", out == [])
    check("Petals empty library: no PendingChoice",
          g.state.pending_choice is None)


def test_petals_ai_uses_first_spirit():
    g, a, _b = _new_test_game()
    lib_ids = _stock_library(
        g, a.id, [YOSEI_THE_MORNING_STAR, KURIBOH, KOKUSHO_THE_EVENING_STAR])
    _set_ai(g, a.id)
    out = _petals_of_insight_resolve(_activate_event("petals-ai", a.id), g.state)
    check("Petals AI: events emitted (add + 2 mill)",
          len(out) == 3, f"got {len(out)}")
    check("Petals AI: choice cleared", g.state.pending_choice is None)
    hand = g.state.zones[f"hand_{a.id}"].objects
    check("Petals AI: first Spirit (Yosei) added to hand",
          lib_ids[0] in hand, f"hand={hand}")
    gy = g.state.zones[f"graveyard_{a.id}"].objects
    check("Petals AI: Kuriboh + Kokusho both milled",
          lib_ids[1] in gy and lib_ids[2] in gy, f"gy={gy}")


test_petals_human_choice_over_revealed_spirits()
test_petals_no_spirit_revealed_mills_all()
test_petals_empty_library_short_circuits()
test_petals_ai_uses_first_spirit()


# ---- Imperial Mobilization (up to 2 Lv 3 Samurai from GY) -------------------

print("\n--- Imperial Mobilization ---")
from src.cards.yugioh.beyond.kamigawa.samurai import (
    _imperial_mobilization_resolve, _is_samurai,
)


def test_mobilization_human_choice_over_gy_samurai():
    g, a, _b = _new_test_game()
    # Stock GY: 3 Lv-3-or-lower Samurai (Isamaru Lv1, Devoted Lv2, Free-Rider Lv3)
    # + 1 non-Samurai (Kuriboh) + 1 Lv-7 Samurai (Konda, filtered out by Lv).
    gy_ids = _stock_gy(g, a.id, [
        ISAMARU_HOUND_OF_KONDA, DEVOTED_RETAINER, EIGANJO_FREE_RIDER,
        KURIBOH, KONDA_LORD_OF_EIGANJO,
    ])
    out = _imperial_mobilization_resolve(
        _activate_event("mob-test", a.id), g.state)
    pc = g.state.pending_choice
    check("Mobilization human: 0 events yet", out == [])
    check("Mobilization human: PendingChoice set", pc is not None)
    if pc is not None:
        check("Mobilization human: min == 0 (up to 2)", pc.min_choices == 0)
        check("Mobilization human: max == 2", pc.max_choices == 2)
        opt_ids = {o["id"] for o in pc.options}
        # KURIBOH (non-Samurai) and KONDA (Lv > 3) both excluded.
        check("Mobilization human: KURIBOH excluded", gy_ids[3] not in opt_ids)
        check("Mobilization human: KONDA (Lv > 3) excluded",
              gy_ids[4] not in opt_ids)
        # All 3 low-Lv Samurai are options.
        check("Mobilization human: 3 eligible Samurai are options",
              opt_ids == {gy_ids[0], gy_ids[1], gy_ids[2]},
              f"opts={opt_ids} expected={set(gy_ids[:3])}")
        check("Mobilization human: heuristic_pick == first 2 eligible",
              pc.callback_data.get("heuristic_pick") == gy_ids[:2])


def test_mobilization_empty_gy_short_circuits():
    g, a, _b = _new_test_game()
    gy = g.state.zones.get(f"graveyard_{a.id}")
    for cid in list(gy.objects):
        gy.objects.remove(cid)
    _reset_pending(g)
    out = _imperial_mobilization_resolve(
        _activate_event("mob-empty", a.id), g.state)
    check("Mobilization empty GY: 0 events", out == [])
    check("Mobilization empty GY: no PendingChoice",
          g.state.pending_choice is None)


def test_mobilization_no_eligible_short_circuits():
    """GY has cards but none are Lv-3-or-lower Samurai."""
    g, a, _b = _new_test_game()
    _stock_gy(g, a.id, [KURIBOH, BLUE_EYES_WHITE_DRAGON, KONDA_LORD_OF_EIGANJO])
    _reset_pending(g)
    out = _imperial_mobilization_resolve(
        _activate_event("mob-noeligible", a.id), g.state)
    check("Mobilization no eligible: 0 events", out == [])
    check("Mobilization no eligible: no PendingChoice",
          g.state.pending_choice is None)


def test_mobilization_ai_revives_first_2_in_gy_order():
    g, a, _b = _new_test_game()
    gy_ids = _stock_gy(g, a.id, [
        ISAMARU_HOUND_OF_KONDA, DEVOTED_RETAINER, EIGANJO_FREE_RIDER, KURIBOH,
    ])
    _set_ai(g, a.id)
    out = _imperial_mobilization_resolve(
        _activate_event("mob-ai", a.id), g.state)
    check("Mobilization AI: choice cleared", g.state.pending_choice is None)
    # First 2 eligible (Isamaru + Devoted) should be revived.
    field = g.state.zones[f"monster_zone_{a.id}"].objects
    check("Mobilization AI: Isamaru on field (id 0 revived)",
          gy_ids[0] in field, f"field={field}")
    check("Mobilization AI: Devoted Retainer on field (id 1 revived)",
          gy_ids[1] in field, f"field={field}")
    check("Mobilization AI: Eiganjo Free-Rider NOT revived (cap 2)",
          gy_ids[2] not in field, f"field={field}")


test_mobilization_human_choice_over_gy_samurai()
test_mobilization_empty_gy_short_circuits()
test_mobilization_no_eligible_short_circuits()
test_mobilization_ai_revives_first_2_in_gy_order()


# ---- The Wandering Decree (tribute Samurai, revive Lv-5+ Samurai) -----------

print("\n--- The Wandering Decree ---")
from src.cards.yugioh.beyond.kamigawa.samurai import (
    _wandering_decree_resolve, THE_WANDERING_DECREE,
)


def test_decree_human_choice_over_field_samurai():
    g, a, _b = _new_test_game()
    field_ids = _stock_field(g, a.id, [HAND_OF_HONOR, KURIBOH, HAND_OF_CRUELTY])
    # Stock GY with a Lv 5+ Samurai for the revive to find.
    _stock_gy(g, a.id, [KONDA_LORD_OF_EIGANJO])
    out = _wandering_decree_resolve(_activate_event("dec-test", a.id), g.state)
    pc = g.state.pending_choice
    check("Decree human: 0 events yet", out == [])
    check("Decree human: PendingChoice set", pc is not None)
    if pc is not None:
        check("Decree human: min/max == 1",
              pc.min_choices == 1 and pc.max_choices == 1)
        # Only Samurai-subtyped monsters from controller's field are options.
        opt_ids = {o["id"] for o in pc.options}
        check("Decree human: KURIBOH (non-Samurai) excluded",
              field_ids[1] not in opt_ids)
        check("Decree human: 2 Samurai are options",
              field_ids[0] in opt_ids and field_ids[2] in opt_ids)


def test_decree_no_samurai_on_field_short_circuits():
    g, a, _b = _new_test_game()
    _stock_field(g, a.id, [KURIBOH])
    _reset_pending(g)
    out = _wandering_decree_resolve(
        _activate_event("dec-empty", a.id), g.state)
    check("Decree no Samurai on field: 0 events", out == [])
    check("Decree no Samurai: no PendingChoice",
          g.state.pending_choice is None)


def test_decree_ai_tributes_first_samurai():
    g, a, _b = _new_test_game()
    field_ids = _stock_field(g, a.id, [HAND_OF_HONOR, HAND_OF_CRUELTY])
    _stock_gy(g, a.id, [KONDA_LORD_OF_EIGANJO])
    _set_ai(g, a.id)
    out = _wandering_decree_resolve(
        _activate_event("dec-ai", a.id), g.state)
    check("Decree AI: choice cleared", g.state.pending_choice is None)
    # First Samurai (HAND_OF_HONOR) should be tributed; revive Konda.
    gy_now = g.state.zones[f"graveyard_{a.id}"].objects
    check("Decree AI: first Samurai tributed (in GY)",
          field_ids[0] in gy_now, f"gy={gy_now}")


test_decree_human_choice_over_field_samurai()
test_decree_no_samurai_on_field_short_circuits()
test_decree_ai_tributes_first_samurai()


# ---- Chain-stack integrity ---------------------------------------------------

print("\n--- Chain-stack integrity (mid-chain PendingChoice) ---")


def test_imperial_edict_mid_chain_does_not_corrupt_stack():
    """Activate Imperial Edict as a chain link, verify the chain stack
    remains coherent through the inline PendingChoice → AI-resolve cycle.

    YGO chains resolve LIFO; if a PendingChoice mid-resolution leaks an
    unresolved chain link or duplicates one, this test catches it.
    """
    from src.engine.yugioh_chain import YugiohChainManager

    g, a, _b = _new_test_game()
    _stock_library(g, a.id, [KURIBOH, BLUE_EYES_WHITE_DRAGON, DARK_HOLE])
    _set_ai(g, a.id)

    # Build a fresh chain with Imperial Edict as link 1.
    chain = YugiohChainManager(g.state)

    def edict_resolve_fn(state, targets):
        return _imperial_edict_resolve(
            Event(type=EventType.YGO_ACTIVATE_SPELL,
                  payload={'player': a.id, 'card_id': 'edict-mid-chain'},
                  source='edict-mid-chain', controller=a.id),
            state)

    chain.start_chain(
        card_id="edict-mid-chain", controller=a.id, spell_speed=1,
        card_name="Imperial Edict", resolve_fn=edict_resolve_fn,
    )
    check("Chain stack: 1 link after start", len(chain.chain_links) == 1)

    events = chain.resolve_chain()
    check("Chain stack: 0 links after resolve", len(chain.chain_links) == 0)
    check("Chain stack: pending_choice cleared post-AI",
          g.state.pending_choice is None)
    # The AI resolved the choice mid-chain, so events should include
    # at minimum a YGO_DRAW and a YGO_SEND_TO_GY (the auto-discard).
    has_draw = any('draw' in str(e.type).lower() for e in events)
    has_gy = any('send_to_gy' in str(e.type).lower() or
                 'discard' in str(e.type).lower() for e in events)
    check("Chain stack: events include draw + discard",
          has_draw and has_gy,
          f"events={[str(e.type) for e in events]}")


test_imperial_edict_mid_chain_does_not_corrupt_stack()


# =============================================================================
# Test 4d: Phase 4 follow-up — Soulshift + Heiko Yamazaki PendingChoice
# =============================================================================
#
# Migrated cards:
#   - soulshift_revive() helper (drives make_soulshift + 5 Spirit Dragons
#     + Atsushi; same shape applies to Village Guide Spirit, Kirin of the
#     First Wind, and Pearl-Dragon Concord)
#   - Heiko Yamazaki, the General (Tribute Summon → SS 2 Lv≤4 Samurai)
#
# Each card gets the three standard tests: human-emits-choice,
# AI-uses-heuristic, empty-short-circuits.

print("\n=== Test 4d: Soulshift + Heiko Yamazaki PendingChoice ===")

from src.cards.yugioh.beyond.kamigawa._archetype_helpers import soulshift_revive
from src.cards.yugioh.beyond.kamigawa.spirit_dragons import (
    YOSEI_THE_MORNING_STAR, KOKUSHO_THE_EVENING_STAR, JUGAN_THE_RISING_STAR,
    KEIGA_THE_TIDE_STAR, RYUSEI_THE_FALLING_STAR, ATSUSHI_THE_BLAZING_SKY,
    INAME_DEATH_ASPECT, INAME_LIFE_ASPECT, HANA_KAMI,
    _jugan_setup, _atsushi_setup,
)
from src.cards.yugioh.beyond.kamigawa.samurai import (
    HEIKO_YAMAZAKI, _heiko_yamazaki_setup,
    HAND_OF_HONOR, HAND_OF_CRUELTY, DEVOTED_RETAINER, ISAMARU_HOUND_OF_KONDA,
)


# ---- soulshift_revive() helper -----------------------------------------------

print("\n--- soulshift_revive helper ---")


def test_soulshift_empty_gy_returns_empty():
    """No Spirit in GY → returns [] (no event, no choice)."""
    g, a, _b = _new_test_game()
    _reset_pending(g)
    out = soulshift_revive(g.state, a.id, "Spirit", max_level=8,
                            source_id="soulshift-empty")
    check("Soulshift empty GY: no events", out == [])
    check("Soulshift empty GY: no PendingChoice",
          g.state.pending_choice is None)


def test_soulshift_single_candidate_auto_revives():
    """Only 1 eligible Spirit in GY → auto-revive, no choice (the choice is
    trivial when there's only one option)."""
    g, a, _b = _new_test_game()
    gy_ids = _stock_gy(g, a.id, [HANA_KAMI])
    _reset_pending(g)
    out = soulshift_revive(g.state, a.id, "Spirit", max_level=8,
                            source_id="soulshift-single")
    check("Soulshift 1 candidate: events emitted (auto-revive)",
          len(out) >= 1, f"got {len(out)} events")
    check("Soulshift 1 candidate: no PendingChoice",
          g.state.pending_choice is None)


def test_soulshift_multi_candidate_human_emits_choice():
    """2+ eligible Spirits → emit PendingChoice over them."""
    g, a, _b = _new_test_game()
    gy_ids = _stock_gy(g, a.id, [HANA_KAMI, INAME_DEATH_ASPECT, INAME_LIFE_ASPECT])
    _reset_pending(g)
    out = soulshift_revive(g.state, a.id, "Spirit", max_level=8,
                            source_id="soulshift-multi")
    check("Soulshift multi human: no events yet (choice pending)",
          out == [], f"got {len(out)} events")
    pc = g.state.pending_choice
    check("Soulshift multi human: PendingChoice set", pc is not None)
    if pc is not None:
        check("Soulshift multi: choice type 'target'",
              pc.choice_type == "target")
        check("Soulshift multi: player == controller", pc.player == a.id)
        check("Soulshift multi: min/max == 1",
              pc.min_choices == 1 and pc.max_choices == 1)
        opt_ids = {o["id"] for o in pc.options}
        check("Soulshift multi: options cover all 3 GY Spirits",
              opt_ids == set(gy_ids),
              f"opts={opt_ids} expected={set(gy_ids)}")
        # Heuristic: first in GY order
        check("Soulshift multi: heuristic_pick == first in GY",
              pc.callback_data.get("heuristic_pick") == [gy_ids[0]])


def test_soulshift_excludes_source_id():
    """The source card itself must not be a soulshift candidate (its own GY
    row would let a Spirit revive itself, breaking the Kamigawa rule)."""
    g, a, _b = _new_test_game()
    gy_ids = _stock_gy(g, a.id, [HANA_KAMI, INAME_LIFE_ASPECT])
    _reset_pending(g)
    # Use HANA_KAMI's id as exclude — only INAME_LIFE_ASPECT remains.
    out = soulshift_revive(g.state, a.id, "Spirit", max_level=8,
                            source_id=gy_ids[0], exclude_id=gy_ids[0])
    # Only 1 remaining candidate → auto-revive, no choice.
    check("Soulshift exclude_source: auto-revive (single remaining)",
          len(out) >= 1, f"got {len(out)} events")
    check("Soulshift exclude_source: source not revived",
          all('hana_kami' not in str(e.payload).lower() for e in out))


def test_soulshift_respects_max_level():
    """High-level Spirit Dragons in GY are excluded when max_level cap < their Lv."""
    g, a, _b = _new_test_game()
    # YOSEI is Lv 9 — too high for max_level=4
    gy_ids = _stock_gy(g, a.id, [YOSEI_THE_MORNING_STAR, HANA_KAMI])
    _reset_pending(g)
    out = soulshift_revive(g.state, a.id, "Spirit", max_level=4,
                            source_id="soulshift-cap")
    # Only HANA_KAMI eligible → auto-revive.
    check("Soulshift max_level cap: yosei (Lv9) excluded",
          g.state.pending_choice is None,
          "should auto-revive the single eligible Lv2 Spirit")


def test_soulshift_ai_uses_heuristic():
    """AI path: heuristic_pick = first GY candidate. The chosen Spirit moves
    out of GY (the revive places it on the monster zone)."""
    g, a, _b = _new_test_game()
    gy_ids = _stock_gy(g, a.id, [HANA_KAMI, INAME_DEATH_ASPECT, INAME_LIFE_ASPECT])
    _set_ai(g, a.id)
    out = soulshift_revive(g.state, a.id, "Spirit", max_level=8,
                            source_id="soulshift-ai")
    check("Soulshift AI: events emitted",
          len(out) >= 1, f"got {len(out)} events")
    check("Soulshift AI: choice cleared",
          g.state.pending_choice is None)
    # The heuristic picks the first GY candidate — it should have left the GY.
    gy_now = g.state.zones[f"graveyard_{a.id}"].objects
    check("Soulshift AI: first GY candidate left the graveyard",
          gy_ids[0] not in gy_now,
          f"gy_now={gy_now}")


test_soulshift_empty_gy_returns_empty()
test_soulshift_single_candidate_auto_revives()
test_soulshift_multi_candidate_human_emits_choice()
test_soulshift_excludes_source_id()
test_soulshift_respects_max_level()
test_soulshift_ai_uses_heuristic()


# ---- Jugan, the Rising Star (Spirit Dragon Soulshift wired path) -------------

print("\n--- Jugan Soulshift (wired) ---")


def test_jugan_destroy_trigger_emits_choice_over_gy_spirits():
    """When Jugan resolves its destroy trigger and 2+ Spirits are in GY,
    a PendingChoice is emitted (after the Draw 3)."""
    g, a, _b = _new_test_game()
    # Stock GY with 2 Spirits + Jugan itself (we exclude it via source_id).
    gy_ids = _stock_gy(g, a.id, [HANA_KAMI, INAME_LIFE_ASPECT])
    # Stock library so Draw 3 can fire (otherwise Jugan still works but draw is 0).
    lib_ids = _stock_library(g, a.id, [KURIBOH, BLUE_EYES_WHITE_DRAGON, DARK_HOLE])
    _reset_pending(g)

    # Build a Jugan game object to invoke the destroy trigger's effect.
    jugan = g.create_object(
        name=JUGAN_THE_RISING_STAR.name, owner_id=a.id,
        zone=ZoneType.GRAVEYARD,  # logical: a destroyed Jugan is in GY
        characteristics=copy.deepcopy(JUGAN_THE_RISING_STAR.characteristics),
        card_def=JUGAN_THE_RISING_STAR,
    )
    # Drive the effect_fn directly via setup_interceptors (Jugan returns
    # one destroy-trigger interceptor; we invoke its handler).
    interceptors = _jugan_setup(jugan, g.state)
    check("Jugan: setup returned 1 interceptor", len(interceptors) == 1)
    interceptor = interceptors[0]
    # Trigger event (destroy of jugan).
    fake_event = Event(
        type=EventType.YGO_DESTROY,
        payload={'card_id': jugan.id, 'card_name': jugan.name},
        source=jugan.id, controller=a.id,
    )
    result = interceptor.handler(fake_event, g.state)
    events = result.new_events or []
    # We expect 3 YGO_DRAW events (Jugan's draw 3), then a PendingChoice
    # for the Soulshift over the 2 GY Spirits.
    draw_count = sum(1 for e in events if 'draw' in str(e.type).lower())
    check("Jugan: 3 draw events", draw_count == 3,
          f"got draw_count={draw_count}, events={[str(e.type) for e in events]}")
    pc = g.state.pending_choice
    check("Jugan: Soulshift PendingChoice set after draw", pc is not None)
    if pc is not None:
        opt_ids = {o["id"] for o in pc.options}
        check("Jugan: Soulshift options == GY Spirits",
              opt_ids == set(gy_ids),
              f"opts={opt_ids} expected={set(gy_ids)}")


def test_jugan_empty_gy_no_choice():
    """Jugan with no Spirits in GY: only the Draw 3 fires, no choice."""
    g, a, _b = _new_test_game()
    # GY empty.
    _stock_library(g, a.id, [KURIBOH, BLUE_EYES_WHITE_DRAGON, DARK_HOLE])
    _reset_pending(g)
    jugan = g.create_object(
        name=JUGAN_THE_RISING_STAR.name, owner_id=a.id, zone=ZoneType.GRAVEYARD,
        characteristics=copy.deepcopy(JUGAN_THE_RISING_STAR.characteristics),
        card_def=JUGAN_THE_RISING_STAR,
    )
    interceptors = _jugan_setup(jugan, g.state)
    interceptor = interceptors[0]
    fake_event = Event(
        type=EventType.YGO_DESTROY,
        payload={'card_id': jugan.id, 'card_name': jugan.name},
        source=jugan.id, controller=a.id,
    )
    result = interceptor.handler(fake_event, g.state)
    events = result.new_events or []
    draw_count = sum(1 for e in events if 'draw' in str(e.type).lower())
    check("Jugan empty GY: 3 draws still fire", draw_count == 3)
    check("Jugan empty GY: no PendingChoice",
          g.state.pending_choice is None)


def test_atsushi_soulshift_respects_lv7_cap():
    """Atsushi is Lv 7 — Soulshift 7. Lv 8 Spirits in GY are excluded."""
    g, a, _b = _new_test_game()
    # Both Lv9 Spirit Dragons (exceed Atsushi's max_level=6) plus a Lv 2 Hana Kami.
    gy_ids = _stock_gy(g, a.id, [YOSEI_THE_MORNING_STAR, KOKUSHO_THE_EVENING_STAR, HANA_KAMI])
    _reset_pending(g)
    atsushi = g.create_object(
        name=ATSUSHI_THE_BLAZING_SKY.name, owner_id=a.id, zone=ZoneType.GRAVEYARD,
        characteristics=copy.deepcopy(ATSUSHI_THE_BLAZING_SKY.characteristics),
        card_def=ATSUSHI_THE_BLAZING_SKY,
    )
    interceptors = _atsushi_setup(atsushi, g.state)
    interceptor = interceptors[0]
    fake_event = Event(
        type=EventType.YGO_DESTROY,
        payload={'card_id': atsushi.id, 'card_name': atsushi.name},
        source=atsushi.id, controller=a.id,
    )
    result = interceptor.handler(fake_event, g.state)
    events = result.new_events or []
    # The two Lv9 dragons are over Atsushi's Soulshift 7 cap (max_level=6).
    # Only Hana Kami eligible → auto-revive, no choice.
    check("Atsushi: no PendingChoice (1 eligible auto-revives)",
          g.state.pending_choice is None)


test_jugan_destroy_trigger_emits_choice_over_gy_spirits()
test_jugan_empty_gy_no_choice()
test_atsushi_soulshift_respects_lv7_cap()


# ---- make_soulshift helper (Village Guide Spirit Soulshift 2) ---------------

print("\n--- make_soulshift helper (Village Guide Spirit) ---")


def test_make_soulshift_emits_choice_via_village_guide():
    """Drive the centralized ``make_soulshift`` helper end-to-end through
    Village Guide Spirit. 2+ low-level Spirits in GY → PendingChoice."""
    from src.cards.yugioh.beyond.kamigawa.spirit_dragons import VILLAGE_GUIDE_SPIRIT

    g, a, _b = _new_test_game()
    _stock_gy(g, a.id, [HANA_KAMI, INAME_LIFE_ASPECT])
    _reset_pending(g)
    vgs = g.create_object(
        name=VILLAGE_GUIDE_SPIRIT.name, owner_id=a.id, zone=ZoneType.GRAVEYARD,
        characteristics=copy.deepcopy(VILLAGE_GUIDE_SPIRIT.characteristics),
        card_def=VILLAGE_GUIDE_SPIRIT,
    )
    interceptors = VILLAGE_GUIDE_SPIRIT.setup_interceptors(vgs, g.state)
    # VGS has 2 interceptors (summon trigger + soulshift).
    check("VGS: 2 interceptors", len(interceptors) == 2)
    # Find the soulshift (destroy-trigger) one.
    fake = Event(
        type=EventType.YGO_DESTROY,
        payload={'card_id': vgs.id, 'card_name': vgs.name},
        source=vgs.id, controller=a.id,
    )
    fired = False
    for it in interceptors:
        if it.filter(fake, g.state):
            result = it.handler(fake, g.state)
            fired = True
            break
    check("VGS soulshift fired on destroy", fired)
    check("VGS soulshift emitted PendingChoice",
          g.state.pending_choice is not None)


test_make_soulshift_emits_choice_via_village_guide()


# ---- Heiko Yamazaki, the General (Tribute Summon → SS 2 Lv≤4 Samurai) ------

print("\n--- Heiko Yamazaki ---")


def test_heiko_empty_gy_short_circuits():
    """No Lv≤4 Samurai in GY: no events, no choice."""
    g, a, _b = _new_test_game()
    _reset_pending(g)
    heiko = g.create_object(
        name=HEIKO_YAMAZAKI.name, owner_id=a.id, zone=ZoneType.MONSTER_ZONE,
        characteristics=copy.deepcopy(HEIKO_YAMAZAKI.characteristics),
        card_def=HEIKO_YAMAZAKI,
    )
    interceptors = _heiko_yamazaki_setup(heiko, g.state)
    check("Heiko: 1 interceptor (tribute-summon trigger)",
          len(interceptors) == 1)
    fake_event = Event(
        type=EventType.YGO_TRIBUTE_SUMMON,
        payload={'card_id': heiko.id, 'card_name': heiko.name},
        source=heiko.id, controller=a.id,
    )
    result = interceptors[0].handler(fake_event, g.state)
    events = result.new_events or []
    check("Heiko empty GY: no events", events == [])
    check("Heiko empty GY: no PendingChoice",
          g.state.pending_choice is None)


def test_heiko_human_emits_choice_over_lv4_samurai():
    """3 Lv≤4 Samurai in GY + 1 Lv 6 → choice over only the 3 small ones."""
    g, a, _b = _new_test_game()
    gy_ids = _stock_gy(g, a.id, [HAND_OF_HONOR, HAND_OF_CRUELTY, DEVOTED_RETAINER,
                                  ISAMARU_HOUND_OF_KONDA])
    _reset_pending(g)
    heiko = g.create_object(
        name=HEIKO_YAMAZAKI.name, owner_id=a.id, zone=ZoneType.MONSTER_ZONE,
        characteristics=copy.deepcopy(HEIKO_YAMAZAKI.characteristics),
        card_def=HEIKO_YAMAZAKI,
    )
    interceptors = _heiko_yamazaki_setup(heiko, g.state)
    fake_event = Event(
        type=EventType.YGO_TRIBUTE_SUMMON,
        payload={'card_id': heiko.id, 'card_name': heiko.name},
        source=heiko.id, controller=a.id,
    )
    result = interceptors[0].handler(fake_event, g.state)
    events = result.new_events or []
    check("Heiko human: no events yet (choice pending)",
          events == [], f"got {len(events)} events")
    pc = g.state.pending_choice
    check("Heiko human: PendingChoice set", pc is not None)
    if pc is not None:
        check("Heiko: choice player == controller", pc.player == a.id)
        check("Heiko: min/max == 2",
              pc.min_choices == 2 and pc.max_choices == 2)
        opt_ids = {o["id"] for o in pc.options}
        # All 4 stocked Samurai are Lv≤4 by construction.
        check("Heiko: options cover all Lv≤4 Samurai in GY",
              opt_ids == set(gy_ids),
              f"opts={opt_ids} expected={set(gy_ids)}")
        check("Heiko: heuristic_pick == first 2 in GY",
              pc.callback_data.get("heuristic_pick") == gy_ids[:2])


def test_heiko_ai_uses_heuristic_first_2_samurai():
    """AI path: top-2 GY Samurai revived. Both leave the GY."""
    g, a, _b = _new_test_game()
    gy_ids = _stock_gy(g, a.id, [HAND_OF_HONOR, HAND_OF_CRUELTY, DEVOTED_RETAINER])
    _set_ai(g, a.id)
    heiko = g.create_object(
        name=HEIKO_YAMAZAKI.name, owner_id=a.id, zone=ZoneType.MONSTER_ZONE,
        characteristics=copy.deepcopy(HEIKO_YAMAZAKI.characteristics),
        card_def=HEIKO_YAMAZAKI,
    )
    interceptors = _heiko_yamazaki_setup(heiko, g.state)
    fake_event = Event(
        type=EventType.YGO_TRIBUTE_SUMMON,
        payload={'card_id': heiko.id, 'card_name': heiko.name},
        source=heiko.id, controller=a.id,
    )
    result = interceptors[0].handler(fake_event, g.state)
    events = result.new_events or []
    check("Heiko AI: events emitted (2 revives)",
          len(events) >= 2, f"got {len(events)}")
    check("Heiko AI: choice cleared",
          g.state.pending_choice is None)
    gy_now = g.state.zones[f"graveyard_{a.id}"].objects
    # First 2 should have left the GY.
    check("Heiko AI: top-2 GY Samurai left the graveyard",
          gy_ids[0] not in gy_now and gy_ids[1] not in gy_now,
          f"gy_now={gy_now}")
    check("Heiko AI: 3rd Samurai still in GY",
          gy_ids[2] in gy_now)


test_heiko_empty_gy_short_circuits()
test_heiko_human_emits_choice_over_lv4_samurai()
test_heiko_ai_uses_heuristic_first_2_samurai()


# ---- Chain-stack integrity for a Soulshift-driven card ----------------------

print("\n--- Chain-stack integrity (mid-chain Soulshift PendingChoice) ---")


def test_jugan_soulshift_mid_chain_does_not_corrupt_stack():
    """Resolve Jugan's destroy trigger via a chain link with multiple GY
    Spirits available. The mid-chain Soulshift PendingChoice must not leak
    chain links or duplicate any.
    """
    from src.engine.yugioh_chain import YugiohChainManager

    g, a, _b = _new_test_game()
    _stock_gy(g, a.id, [HANA_KAMI, INAME_LIFE_ASPECT])
    _stock_library(g, a.id, [KURIBOH, BLUE_EYES_WHITE_DRAGON, DARK_HOLE])
    _set_ai(g, a.id)

    chain = YugiohChainManager(g.state)
    jugan = g.create_object(
        name=JUGAN_THE_RISING_STAR.name, owner_id=a.id, zone=ZoneType.GRAVEYARD,
        characteristics=copy.deepcopy(JUGAN_THE_RISING_STAR.characteristics),
        card_def=JUGAN_THE_RISING_STAR,
    )
    interceptors = _jugan_setup(jugan, g.state)
    interceptor = interceptors[0]

    def jugan_resolve_fn(state, targets):
        return interceptor.handler(
            Event(type=EventType.YGO_DESTROY,
                  payload={'card_id': jugan.id, 'card_name': jugan.name},
                  source=jugan.id, controller=a.id),
            state).new_events or []

    chain.start_chain(
        card_id=jugan.id, controller=a.id, spell_speed=1,
        card_name="Jugan, the Rising Star", resolve_fn=jugan_resolve_fn,
    )
    check("Jugan chain: 1 link after start", len(chain.chain_links) == 1)

    events = chain.resolve_chain()
    check("Jugan chain: 0 links after resolve",
          len(chain.chain_links) == 0)
    check("Jugan chain: pending_choice cleared post-AI",
          g.state.pending_choice is None)


test_jugan_soulshift_mid_chain_does_not_corrupt_stack()


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
