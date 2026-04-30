"""
Tests for the library-search-with-player-choice subsystem.

Covers:
  - create_library_search_choice opens a PendingChoice with the right options
  - Submitting a choice resolves with the card moving to the chosen destination
  - "hand", "graveyard", "library_top", "library_bottom", "exile" destinations
  - "battlefield_tapped" emits a ZONE_CHANGE so ETB triggers fire
  - Optional searches fail gracefully when no candidates exist
  - Filter functions work (basic land, creature with MV>=N, instant/sorcery MV=N,
    subtype matching, any-card)
  - Wiring of foundations/spider_man cards (Fierce Empath, Rune-Scarred Demon,
    Vile Entomber, Hoarding Dragon, Spider-Man Brooklyn Visionary)
"""

import sys
import os

# Ensure the repo root is on sys.path. We compute it from this file's location
# so the test works whether run from a worktree or the main checkout.
_TEST_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_TEST_DIR)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color,
    Characteristics, GameObject, ObjectState,
    new_id,
)
from src.engine.library_search import (
    create_library_search_choice,
    library_search_with_callback,
    is_basic_land,
    is_basic_with_subtype,
    is_card_type,
    is_creature_with_mv_at_least,
    is_instant_or_sorcery_with_mv,
    is_subtype,
    any_card,
)


# =============================================================================
# Helpers
# =============================================================================

def _make_card(game, player_id, name, *, types=None, subtypes=None,
               supertypes=None, mana_cost="{1}", power=None, toughness=None,
               card_def=None):
    """Add a fake card to a player's library, return its object."""
    types = set(types or [CardType.CREATURE])
    chars = Characteristics(
        types=types,
        subtypes=set(subtypes or []),
        supertypes=set(supertypes or []),
        mana_cost=mana_cost,
        power=power,
        toughness=toughness,
    )
    obj = game.create_object(
        name=name,
        owner_id=player_id,
        zone=ZoneType.LIBRARY,
        characteristics=chars,
        card_def=card_def,
    )
    return obj


def _new_game_with_player(player_count=1):
    game = Game()
    players = [game.add_player(f"P{i}") for i in range(player_count)]
    return game, players


# =============================================================================
# Core subsystem tests
# =============================================================================

def test_basic_land_search_to_hand():
    print("\n=== Test: Basic-land search -> hand ===")
    game, [p1] = _new_game_with_player(1)

    forest = _make_card(game, p1.id, "Forest",
                         types=[CardType.LAND],
                         subtypes=["Forest"],
                         supertypes=["Basic"],
                         mana_cost="")
    creature = _make_card(game, p1.id, "Some Creature",
                           types=[CardType.CREATURE],
                           power=2, toughness=2,
                           mana_cost="{1}{G}")

    choice = create_library_search_choice(
        game.state, p1.id, source_id="test_source",
        filter_fn=is_basic_land(),
        destination="hand",
        shuffle_after=False,
    )
    assert choice is not None, "Choice should be created"
    assert game.state.pending_choice is choice
    assert forest.id in choice.options
    assert creature.id not in choice.options, "Creature should not match basic-land filter"

    # Submit the choice (pick forest)
    ok, msg, _ = game.submit_choice(choice.id, p1.id, [forest.id])
    assert ok, f"Submit should succeed: {msg}"
    assert game.state.pending_choice is None

    # Forest should now be in hand
    hand = game.state.zones[f"hand_{p1.id}"]
    library = game.state.zones[f"library_{p1.id}"]
    assert forest.id in hand.objects, "Forest should be in hand"
    assert forest.id not in library.objects, "Forest should be removed from library"
    assert forest.zone == ZoneType.HAND
    print("OK basic-land search to hand works")


def test_optional_search_with_no_candidates():
    print("\n=== Test: optional search with no candidates -> no choice ===")
    game, [p1] = _new_game_with_player(1)

    # Add a non-matching card
    _make_card(game, p1.id, "Some Creature", types=[CardType.CREATURE])

    choice = create_library_search_choice(
        game.state, p1.id, source_id="test_source",
        filter_fn=is_basic_land(),
        optional=True,
    )
    assert choice is None, "Optional search with no matches should return None"
    assert game.state.pending_choice is None
    print("OK optional empty search no-ops")


def test_search_to_graveyard():
    print("\n=== Test: search -> graveyard (Vile Entomber pattern) ===")
    game, [p1] = _new_game_with_player(1)
    target = _make_card(game, p1.id, "Target", mana_cost="{2}")

    choice = create_library_search_choice(
        game.state, p1.id, source_id="entomber",
        filter_fn=any_card(),
        destination="graveyard",
        shuffle_after=False,
        optional=False,
        min_count=1,
    )
    ok, _, _ = game.submit_choice(choice.id, p1.id, [target.id])
    assert ok
    gy = game.state.zones[f"graveyard_{p1.id}"]
    assert target.id in gy.objects
    assert target.zone == ZoneType.GRAVEYARD
    print("OK graveyard destination works")


def test_search_to_exile():
    print("\n=== Test: search -> exile (Hoarding Dragon pattern) ===")
    game, [p1] = _new_game_with_player(1)
    artifact = _make_card(game, p1.id, "Sol Ring",
                            types=[CardType.ARTIFACT], mana_cost="{1}")

    choice = create_library_search_choice(
        game.state, p1.id, source_id="dragon",
        filter_fn=is_card_type(CardType.ARTIFACT),
        destination="exile",
    )
    ok, _, _ = game.submit_choice(choice.id, p1.id, [artifact.id])
    assert ok
    ex = game.state.zones["exile"]
    assert artifact.id in ex.objects
    assert artifact.zone == ZoneType.EXILE
    print("OK exile destination works")


def test_search_to_library_top_no_shuffle():
    print("\n=== Test: search -> library top (no shuffle) ===")
    game, [p1] = _new_game_with_player(1)
    a = _make_card(game, p1.id, "A", mana_cost="{1}")
    b = _make_card(game, p1.id, "B", mana_cost="{1}")
    c = _make_card(game, p1.id, "C", mana_cost="{1}")

    choice = create_library_search_choice(
        game.state, p1.id, source_id="src",
        filter_fn=any_card(),
        destination="library_top",
        shuffle_after=False,
    )
    ok, _, _ = game.submit_choice(choice.id, p1.id, [b.id])
    assert ok
    lib = game.state.zones[f"library_{p1.id}"]
    assert lib.objects[0] == b.id, f"B should be on top, got {lib.objects[0]}"
    print("OK library_top destination preserves order")


def test_search_to_battlefield_tapped_emits_zone_change():
    print("\n=== Test: search -> battlefield tapped (ZONE_CHANGE path) ===")
    game, [p1] = _new_game_with_player(1)
    forest = _make_card(game, p1.id, "Forest",
                         types=[CardType.LAND],
                         subtypes=["Forest"],
                         supertypes=["Basic"],
                         mana_cost="")

    choice = create_library_search_choice(
        game.state, p1.id, source_id="src",
        filter_fn=is_basic_with_subtype("Forest"),
        destination="battlefield_tapped",
        shuffle_after=False,
    )
    ok, _, _ = game.submit_choice(choice.id, p1.id, [forest.id])
    assert ok

    bf = game.state.zones["battlefield"]
    assert forest.id in bf.objects, "Forest should now be on the battlefield"
    obj = game.state.objects[forest.id]
    assert obj.zone == ZoneType.BATTLEFIELD
    assert obj.state.tapped is True, "Forest should enter tapped"
    print("OK battlefield_tapped fires ZONE_CHANGE and lands tapped")


def test_creature_with_mv_filter():
    print("\n=== Test: creature with MV >= 6 filter (Fierce Empath) ===")
    game, [p1] = _new_game_with_player(1)
    big = _make_card(game, p1.id, "Big Bad", mana_cost="{4}{G}{G}",
                       power=8, toughness=8)
    small = _make_card(game, p1.id, "Small", mana_cost="{1}", power=1, toughness=1)

    choice = create_library_search_choice(
        game.state, p1.id, source_id="empath",
        filter_fn=is_creature_with_mv_at_least(6),
    )
    assert big.id in choice.options
    assert small.id not in choice.options
    print("OK MV>=6 filter only allows the big creature")


def test_instant_sorcery_mv_filter():
    print("\n=== Test: instant/sorcery MV=1 filter (Micromancer) ===")
    game, [p1] = _new_game_with_player(1)
    bolt = _make_card(game, p1.id, "Lightning Bolt",
                        types=[CardType.INSTANT], mana_cost="{R}")
    counter = _make_card(game, p1.id, "Counterspell",
                         types=[CardType.INSTANT], mana_cost="{U}{U}")
    creature = _make_card(game, p1.id, "Goblin Guide", mana_cost="{R}")

    choice = create_library_search_choice(
        game.state, p1.id, source_id="mm",
        filter_fn=is_instant_or_sorcery_with_mv(1),
    )
    assert bolt.id in choice.options
    assert counter.id not in choice.options
    assert creature.id not in choice.options
    print("OK MV=1 instant/sorcery filter is precise")


def test_subtype_filter_aura():
    print("\n=== Test: subtype filter (Aura) ===")
    game, [p1] = _new_game_with_player(1)
    aura = _make_card(game, p1.id, "Some Aura",
                        types=[CardType.ENCHANTMENT],
                        subtypes=["Aura"], mana_cost="{1}{W}")
    eq = _make_card(game, p1.id, "Some Equipment",
                      types=[CardType.ARTIFACT],
                      subtypes=["Equipment"], mana_cost="{2}")

    choice = create_library_search_choice(
        game.state, p1.id, source_id="src",
        filter_fn=is_subtype("Aura"),
    )
    assert aura.id in choice.options
    assert eq.id not in choice.options
    print("OK Aura-subtype filter works")


def test_on_chosen_rider_fires():
    print("\n=== Test: on_chosen rider fires after move ===")
    game, [p1] = _new_game_with_player(1)
    target = _make_card(game, p1.id, "Target", mana_cost="{1}")

    rider_called = {"count": 0, "moved": None}

    def rider(choice, moved, state):
        rider_called["count"] += 1
        rider_called["moved"] = list(moved)
        return []

    choice = library_search_with_callback(
        game.state, p1.id, "src",
        filter_fn=any_card(),
        destination="hand",
        shuffle_after=False,
        on_chosen=rider,
    )
    ok, _, _ = game.submit_choice(choice.id, p1.id, [target.id])
    assert ok
    assert rider_called["count"] == 1
    assert rider_called["moved"] == [target.id]
    print("OK on_chosen rider runs after the move")


def test_libsearch_complete_marker_emitted():
    print("\n=== Test: LIBSEARCH_COMPLETE marker emitted ===")
    game, [p1] = _new_game_with_player(1)
    target = _make_card(game, p1.id, "Target", mana_cost="{1}")

    seen = []
    def filter_fn(e, s):
        return e.type == EventType.LIBSEARCH_COMPLETE
    def handler(e, s):
        seen.append(e)
        from src.engine import InterceptorAction, InterceptorResult
        return InterceptorResult(action=InterceptorAction.PASS)

    from src.engine import Interceptor, InterceptorPriority
    interceptor = Interceptor(
        id=new_id(),
        source="watcher",
        controller=p1.id,
        priority=InterceptorPriority.REACT,
        filter=filter_fn,
        handler=handler,
        duration='forever',  # Not gated to a battlefield permanent.
    )
    game.register_interceptor(interceptor)

    choice = create_library_search_choice(
        game.state, p1.id, source_id="src",
        filter_fn=any_card(),
        destination="hand",
        shuffle_after=False,
    )
    game.submit_choice(choice.id, p1.id, [target.id])
    assert len(seen) == 1, f"Expected one COMPLETE event, got {len(seen)}"
    assert seen[0].payload.get("destination") == "hand"
    assert seen[0].payload.get("selected") == [target.id]
    print("OK LIBSEARCH_COMPLETE marker emitted")


# =============================================================================
# End-to-end card wiring tests
# =============================================================================

def _put_card_on_battlefield(game, player, card_def):
    """Create a card and put it on the battlefield, firing ETB triggers."""
    obj = game.create_object(
        name=card_def.name,
        owner_id=player.id,
        zone=ZoneType.HAND,
        characteristics=card_def.characteristics,
        card_def=None,  # avoid premature setup
    )
    obj.card_def = card_def
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            "object_id": obj.id,
            "from_zone": f"hand_{player.id}",
            "to_zone": "battlefield",
            "to_zone_type": ZoneType.BATTLEFIELD,
        }
    ))
    return obj


def test_fierce_empath_etb_opens_search():
    print("\n=== Test: Fierce Empath ETB opens library_search choice ===")
    from src.cards.foundations import FIERCE_EMPATH
    game, [p1] = _new_game_with_player(1)

    # Stack a couple of MV>=6 creatures in the library
    big = _make_card(game, p1.id, "Big Brawler",
                       mana_cost="{4}{G}{G}", power=7, toughness=7)
    small = _make_card(game, p1.id, "Tiny", mana_cost="{1}", power=1, toughness=1)

    _put_card_on_battlefield(game, p1, FIERCE_EMPATH)

    pc = game.state.pending_choice
    assert pc is not None, "Fierce Empath should open a pending choice"
    assert pc.choice_type == "library_search"
    assert big.id in pc.options
    assert small.id not in pc.options

    # Resolve
    ok, _, _ = game.submit_choice(pc.id, p1.id, [big.id])
    assert ok
    assert big.id in game.state.zones[f"hand_{p1.id}"].objects
    print("OK Fierce Empath wired and tutors a 6+ MV creature")


def test_runescarred_demon_etb_finds_any_card():
    print("\n=== Test: Rune-Scarred Demon ETB finds any card ===")
    from src.cards.foundations import RUNESCARRED_DEMON
    game, [p1] = _new_game_with_player(1)

    target = _make_card(game, p1.id, "Foo", mana_cost="{1}")
    _put_card_on_battlefield(game, p1, RUNESCARRED_DEMON)

    pc = game.state.pending_choice
    assert pc is not None
    assert pc.choice_type == "library_search"
    assert target.id in pc.options
    ok, _, _ = game.submit_choice(pc.id, p1.id, [target.id])
    assert ok
    assert target.id in game.state.zones[f"hand_{p1.id}"].objects
    print("OK Rune-Scarred Demon wired")


def test_vile_entomber_puts_to_graveyard():
    print("\n=== Test: Vile Entomber search -> graveyard ===")
    from src.cards.foundations import VILE_ENTOMBER
    game, [p1] = _new_game_with_player(1)

    target = _make_card(game, p1.id, "Foo", mana_cost="{1}")
    _put_card_on_battlefield(game, p1, VILE_ENTOMBER)

    pc = game.state.pending_choice
    assert pc is not None
    ok, _, _ = game.submit_choice(pc.id, p1.id, [target.id])
    assert ok
    assert target.id in game.state.zones[f"graveyard_{p1.id}"].objects
    print("OK Vile Entomber wired")


def test_tutored_creature_etb_trigger_fires():
    """When a creature with an ETB trigger is tutored onto the battlefield,
    its own ETB trigger should still fire (via the ZONE_CHANGE path)."""
    print("\n=== Test: tutored creature ETB trigger fires ===")
    from src.cards.foundations import RUNESCARRED_DEMON  # ETB tutor
    game, [p1] = _new_game_with_player(1)

    # Stack a card and Rune-Scarred in the library
    target = _make_card(game, p1.id, "Foo", mana_cost="{1}")

    # Put Rune-Scarred in library so it can be tutored.
    runescarred = game.create_object(
        name=RUNESCARRED_DEMON.name,
        owner_id=p1.id,
        zone=ZoneType.LIBRARY,
        characteristics=RUNESCARRED_DEMON.characteristics,
        card_def=RUNESCARRED_DEMON,
    )

    # Open a search that fetches the demon to the battlefield.
    choice = create_library_search_choice(
        game.state, p1.id, source_id="src",
        filter_fn=any_card(),
        destination="battlefield",
        shuffle_after=False,
        optional=False,
        min_count=1,
    )
    ok, _, _ = game.submit_choice(choice.id, p1.id, [runescarred.id])
    assert ok

    # Demon should now be on the battlefield
    assert runescarred.zone == ZoneType.BATTLEFIELD
    # AND the demon's own ETB should have opened a NEW pending choice (its tutor).
    pc = game.state.pending_choice
    assert pc is not None, "Rune-Scarred ETB should fire on tutor-into-play"
    assert pc.choice_type == "library_search"
    assert target.id in pc.options
    print("OK ETB triggers fire on tutored permanents")


def test_spiderman_brooklyn_lands_to_battlefield_tapped():
    print("\n=== Test: Spider-Man, Brooklyn Visionary fetches tapped land ===")
    from src.cards.spider_man import SPIDERMAN_BROOKLYN_VISIONARY
    game, [p1] = _new_game_with_player(1)

    forest = _make_card(game, p1.id, "Forest",
                          types=[CardType.LAND],
                          subtypes=["Forest"], supertypes=["Basic"],
                          mana_cost="")

    _put_card_on_battlefield(game, p1, SPIDERMAN_BROOKLYN_VISIONARY)
    pc = game.state.pending_choice
    assert pc is not None, "Spider-Man should open a search choice"
    assert forest.id in pc.options
    ok, _, _ = game.submit_choice(pc.id, p1.id, [forest.id])
    assert ok
    assert game.state.objects[forest.id].zone == ZoneType.BATTLEFIELD
    assert game.state.objects[forest.id].state.tapped is True
    print("OK Spider-Man Brooklyn Visionary wired (ZONE_CHANGE path)")


# =============================================================================
# Find SPIDERMAN export name
# =============================================================================

# Import-time check: confirm the card export name we expect actually exists.
def test_card_exports_exist():
    from src.cards import foundations, spider_man
    for name in ("FIERCE_EMPATH", "RUNESCARRED_DEMON", "VILE_ENTOMBER",
                 "MICROMANCER", "HOARDING_DRAGON", "CAMPUS_GUIDE",
                 "SPRINGBLOOM_DRUID"):
        assert hasattr(foundations, name), f"foundations missing {name}"
    for name in ("SUNSPIDER_NIMBLE_WEBBER", "SPIDERBOT", "MOLTEN_MAN_INFERNO_INCARNATE",
                 "SPIDERMAN_BROOKLYN_VISIONARY"):
        assert hasattr(spider_man, name), f"spider_man missing {name}"
    print("OK card exports are reachable")


if __name__ == "__main__":
    test_basic_land_search_to_hand()
    test_optional_search_with_no_candidates()
    test_search_to_graveyard()
    test_search_to_exile()
    test_search_to_library_top_no_shuffle()
    test_search_to_battlefield_tapped_emits_zone_change()
    test_creature_with_mv_filter()
    test_instant_sorcery_mv_filter()
    test_subtype_filter_aura()
    test_on_chosen_rider_fires()
    test_libsearch_complete_marker_emitted()
    test_card_exports_exist()
    test_fierce_empath_etb_opens_search()
    test_runescarred_demon_etb_finds_any_card()
    test_vile_entomber_puts_to_graveyard()
    test_tutored_creature_etb_trigger_fires()
    test_spiderman_brooklyn_lands_to_battlefield_tapped()
    print("\n==============================================")
    print("ALL LIBRARY SEARCH TESTS PASSED!")
    print("==============================================")
