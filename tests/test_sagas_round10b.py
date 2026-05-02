"""Tests for Round 10B saga chapter wirings.

Each test spawns a saga on the battlefield, runs setup_interceptors, then
emits a SAGA_CHAPTER event for the target chapter and asserts the expected
follow-up events fire (or pending_choice is set, for target-requiring
chapters).

Sagas wired in this round:
  - FF: SUMMON_BAHAMUT I/II (destroy nonland), SUMMON_PRIMAL_GARUDA I
        (damage 4), II/III (pump +1/+0 EOT), SUMMON_PRIMAL_ODIN I
        (destroy opp creature)
  - SPM: THE_DEATH_OF_GWEN_STACY I (destroy creature), II (each opp
         loses 3 life), KRAVENS_LAST_HUNT II (pump +2/+2 EOT)
  - TLA: THE_CAVE_OF_TWO_LOVERS II (library search), LEAVES_FROM_THE_VINE
         II (counter_add up to 2)
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_HERE)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.engine import (
    Game, Event, EventType, ZoneType, CardType,
    GameObject, ObjectState, new_id,
)


# =============================================================================
# Helpers
# =============================================================================


def _new_game():
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    game.start_game()
    return game, p1, p2


def _spawn_on_battlefield(game, player_id, card_def):
    obj = GameObject(
        id=new_id(), name=card_def.name, owner=player_id, controller=player_id,
        zone=ZoneType.BATTLEFIELD, characteristics=card_def.characteristics,
        state=ObjectState(), card_def=card_def,
        created_at=game.state.next_timestamp(),
        entered_zone_at=game.state.timestamp,
        _state_ref=game.state,
    )
    game.state.objects[obj.id] = obj
    game.state.zones['battlefield'].objects.append(obj.id)
    if card_def.setup_interceptors is not None:
        for interceptor in card_def.setup_interceptors(obj, game.state) or []:
            interceptor.timestamp = game.state.next_timestamp()
            game.state.interceptors[interceptor.id] = interceptor
            obj.interceptor_ids.append(interceptor.id)
    return obj


def _fire_chapter(game, saga_obj, chapter):
    ev = Event(
        type=EventType.SAGA_CHAPTER,
        payload={'object_id': saga_obj.id, 'chapter': chapter},
        source=saga_obj.id, controller=saga_obj.controller,
    )
    return game.pipeline.emit(ev)


# =============================================================================
# FF — Summon: Bahamut
# =============================================================================


def test_summon_bahamut_chapter_1_emits_target_required_destroy():
    print("\n=== Test: SUMMON_BAHAMUT chapter I emits TARGET_REQUIRED destroy ===")
    from src.cards.final_fantasy import SUMMON_BAHAMUT
    from src.engine import make_creature, Color
    game, p1, p2 = _new_game()
    # Spawn an opponent creature so a non-land permanent is a legal target.
    bear_def = make_creature(
        name="Target Bear", power=2, toughness=2,
        mana_cost="{1}{G}", colors={Color.GREEN}, subtypes={"Bear"}, text="",
    )
    _spawn_on_battlefield(game, p2.id, bear_def)
    saga = _spawn_on_battlefield(game, p1.id, SUMMON_BAHAMUT)
    _fire_chapter(game, saga, 1)
    pc = game.state.pending_choice
    assert pc is not None and pc.choice_type in ('target', 'target_with_callback'), \
        f"expected pending target choice; got {pc}"
    assert pc.callback_data.get('effect') == 'destroy', pc.callback_data
    assert pc.source_id == saga.id
    print("  PASS: chapter I opened destroy-target choice")


def test_summon_bahamut_chapter_3_draws_two():
    print("\n=== Test: SUMMON_BAHAMUT chapter III draws 2 ===")
    from src.cards.final_fantasy import SUMMON_BAHAMUT
    game, p1, _ = _new_game()
    saga = _spawn_on_battlefield(game, p1.id, SUMMON_BAHAMUT)
    pre_log = len(game.state.event_log)
    _fire_chapter(game, saga, 3)
    draws = [
        e for e in game.state.event_log[pre_log:]
        if e.type == EventType.DRAW and e.payload.get('amount') == 2
    ]
    assert draws, "expected DRAW(2) event"
    print("  PASS: chapter III emits DRAW(amount=2)")


# =============================================================================
# FF — Summon: Primal Garuda
# =============================================================================


def test_summon_primal_garuda_chapter_1_damages_opp_creature():
    print("\n=== Test: SUMMON_PRIMAL_GARUDA chapter I damages opp creature ===")
    from src.cards.final_fantasy import SUMMON_PRIMAL_GARUDA
    from src.engine import make_creature, Color
    game, p1, p2 = _new_game()
    # Spawn an opponent creature so a target exists
    target_def = make_creature(
        name="Test Bear", power=2, toughness=2,
        mana_cost="{1}{G}", colors={Color.GREEN}, subtypes={"Bear"}, text="",
    )
    _spawn_on_battlefield(game, p2.id, target_def)
    saga = _spawn_on_battlefield(game, p1.id, SUMMON_PRIMAL_GARUDA)
    _fire_chapter(game, saga, 1)
    pc = game.state.pending_choice
    assert pc is not None, "expected pending target choice"
    assert pc.callback_data.get('effect') == 'damage'
    assert pc.callback_data.get('effect_params', {}).get('amount') == 4
    print("  PASS: chapter I opened damage-4 target choice with opponent creature legal")


def test_summon_primal_garuda_chapter_2_pumps_your_creature():
    print("\n=== Test: SUMMON_PRIMAL_GARUDA chapter II pumps your creature ===")
    from src.cards.final_fantasy import SUMMON_PRIMAL_GARUDA
    from src.engine import make_creature, Color
    game, p1, _ = _new_game()
    yours_def = make_creature(
        name="Your Bear", power=2, toughness=2,
        mana_cost="{1}{G}", colors={Color.GREEN}, subtypes={"Bear"}, text="",
    )
    _spawn_on_battlefield(game, p1.id, yours_def)
    saga = _spawn_on_battlefield(game, p1.id, SUMMON_PRIMAL_GARUDA)
    _fire_chapter(game, saga, 2)
    pc = game.state.pending_choice
    assert pc is not None
    assert pc.callback_data.get('effect') == 'pump'
    print("  PASS: chapter II opened pump target choice on your creature")


# =============================================================================
# FF — Summon: Primal Odin
# =============================================================================


def test_summon_primal_odin_chapter_1_destroys_opp_creature():
    print("\n=== Test: SUMMON_PRIMAL_ODIN chapter I destroys opp creature ===")
    from src.cards.final_fantasy import SUMMON_PRIMAL_ODIN
    from src.engine import make_creature, Color
    game, p1, p2 = _new_game()
    target_def = make_creature(
        name="Opp Bear", power=2, toughness=2,
        mana_cost="{1}{B}", colors={Color.BLACK}, subtypes={"Bear"}, text="",
    )
    _spawn_on_battlefield(game, p2.id, target_def)
    saga = _spawn_on_battlefield(game, p1.id, SUMMON_PRIMAL_ODIN)
    _fire_chapter(game, saga, 1)
    pc = game.state.pending_choice
    assert pc is not None
    assert pc.callback_data.get('effect') == 'destroy'
    print("  PASS: chapter I opened destroy target choice on opponent creature")


# =============================================================================
# SPM — The Death of Gwen Stacy
# =============================================================================


def test_gwen_stacy_chapter_1_destroys_creature():
    print("\n=== Test: GWEN_STACY chapter I destroys target creature ===")
    from src.cards.spider_man import THE_DEATH_OF_GWEN_STACY
    from src.engine import make_creature, Color
    game, p1, _ = _new_game()
    target_def = make_creature(
        name="Sacrifice Bear", power=2, toughness=2,
        mana_cost="{2}", colors=set(), subtypes={"Bear"}, text="",
    )
    _spawn_on_battlefield(game, p1.id, target_def)
    saga = _spawn_on_battlefield(game, p1.id, THE_DEATH_OF_GWEN_STACY)
    _fire_chapter(game, saga, 1)
    pc = game.state.pending_choice
    assert pc is not None
    assert pc.callback_data.get('effect') == 'destroy'
    print("  PASS: chapter I opened destroy target choice")


def test_gwen_stacy_chapter_2_each_opp_loses_3_life():
    print("\n=== Test: GWEN_STACY chapter II opps lose 3 life ===")
    from src.cards.spider_man import THE_DEATH_OF_GWEN_STACY
    game, p1, p2 = _new_game()
    saga = _spawn_on_battlefield(game, p1.id, THE_DEATH_OF_GWEN_STACY)
    p2_starting_life = p2.life
    pre_log = len(game.state.event_log)
    _fire_chapter(game, saga, 2)
    life_events = [
        e for e in game.state.event_log[pre_log:]
        if e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p2.id
    ]
    assert life_events, "expected LIFE_CHANGE for opponent"
    # Opponent should have lost 3 life
    assert p2.life == p2_starting_life - 3, f"expected {p2_starting_life - 3}, got {p2.life}"
    print("  PASS: chapter II reduced opponent life by 3")


# =============================================================================
# SPM — Kraven's Last Hunt
# =============================================================================


def test_kravens_last_hunt_chapter_2_pumps_your_creature():
    print("\n=== Test: KRAVENS_LAST_HUNT chapter II pumps your creature ===")
    from src.cards.spider_man import KRAVENS_LAST_HUNT
    from src.engine import make_creature, Color
    game, p1, _ = _new_game()
    yours_def = make_creature(
        name="Hunter Bear", power=3, toughness=3,
        mana_cost="{2}{G}", colors={Color.GREEN}, subtypes={"Bear"}, text="",
    )
    _spawn_on_battlefield(game, p1.id, yours_def)
    saga = _spawn_on_battlefield(game, p1.id, KRAVENS_LAST_HUNT)
    _fire_chapter(game, saga, 2)
    pc = game.state.pending_choice
    assert pc is not None
    assert pc.callback_data.get('effect') == 'pump'
    params = pc.callback_data.get('effect_params', {})
    assert params.get('power_mod') == 2 and params.get('toughness_mod') == 2
    print("  PASS: chapter II opened pump +2/+2 target choice")


# =============================================================================
# TLA — Cave of Two Lovers / Leaves from the Vine
# =============================================================================


def test_cave_of_two_lovers_chapter_2_opens_library_search():
    print("\n=== Test: CAVE_OF_TWO_LOVERS chapter II opens library search ===")
    from src.cards.avatar_tla import THE_CAVE_OF_TWO_LOVERS
    from src.engine import make_land
    game, p1, _ = _new_game()
    # Plant a Mountain in the library so the search has a legal target
    mountain = make_land(name="Test Mountain", text="{T}: Add {R}.", subtypes={"Mountain"})
    m_obj = GameObject(
        id=new_id(), name=mountain.name, owner=p1.id, controller=p1.id,
        zone=ZoneType.LIBRARY, characteristics=mountain.characteristics,
        state=ObjectState(), card_def=mountain,
        created_at=game.state.next_timestamp(),
        entered_zone_at=game.state.timestamp,
        _state_ref=game.state,
    )
    game.state.objects[m_obj.id] = m_obj
    game.state.zones[f'library_{p1.id}'].objects.insert(0, m_obj.id)
    saga = _spawn_on_battlefield(game, p1.id, THE_CAVE_OF_TWO_LOVERS)
    _fire_chapter(game, saga, 2)
    pc = game.state.pending_choice
    assert pc is not None, "expected library-search choice"
    # library_search has its own choice_type
    assert pc.choice_type in ('library_search', 'target', 'library_search_callback', 'target_with_callback'), \
        pc.choice_type
    print(f"  PASS: chapter II opened {pc.choice_type} choice for Mountain/Cave search")


def test_leaves_from_the_vine_chapter_2_counter_add_up_to_two():
    print("\n=== Test: LEAVES_FROM_THE_VINE chapter II counter_add up to 2 ===")
    from src.cards.avatar_tla import LEAVES_FROM_THE_VINE
    from src.engine import make_creature, Color
    game, p1, _ = _new_game()
    # Spawn 3 creatures so max_choices clamps to 2 (not to legal-target count)
    for n in range(3):
        cdef = make_creature(
            name=f"Tea Bear {n}", power=1, toughness=1,
            mana_cost="{G}", colors={Color.GREEN}, subtypes={"Bear"}, text="",
        )
        _spawn_on_battlefield(game, p1.id, cdef)
    saga = _spawn_on_battlefield(game, p1.id, LEAVES_FROM_THE_VINE)
    _fire_chapter(game, saga, 2)
    pc = game.state.pending_choice
    assert pc is not None
    assert pc.callback_data.get('effect') == 'counter_add'
    # max_choices is clamped to min(max_targets, legal_targets); we spawned 3
    # creatures + saga (saga isn't a creature) => max_choices == 2.
    assert pc.max_choices == 2, f"expected max_choices=2, got {pc.max_choices}"
    print("  PASS: chapter II opened counter_add (max 2) target choice")


# =============================================================================
# Run all
# =============================================================================


if __name__ == '__main__':
    print("=" * 60)
    print("ROUND 10B SAGA TESTS")
    print("=" * 60)

    tests = [
        test_summon_bahamut_chapter_1_emits_target_required_destroy,
        test_summon_bahamut_chapter_3_draws_two,
        test_summon_primal_garuda_chapter_1_damages_opp_creature,
        test_summon_primal_garuda_chapter_2_pumps_your_creature,
        test_summon_primal_odin_chapter_1_destroys_opp_creature,
        test_gwen_stacy_chapter_1_destroys_creature,
        test_gwen_stacy_chapter_2_each_opp_loses_3_life,
        test_kravens_last_hunt_chapter_2_pumps_your_creature,
        test_cave_of_two_lovers_chapter_2_opens_library_search,
        test_leaves_from_the_vine_chapter_2_counter_add_up_to_two,
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
    print(f"ALL {len(tests)} SAGA TESTS PASSED")
    print("=" * 60)
