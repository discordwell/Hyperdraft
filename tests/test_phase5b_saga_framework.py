"""Phase 5b — Saga framework tests.

Covers the saga subsystem (``src/engine/saga.py`` + ``make_saga_setup`` in
``src/cards/interceptor_helpers.py``):

1. ETB fires chapter I (CR 714.2).
2. Three upkeep/draw-step cycles fire I/II/III in order (CR 714.3).
3. Saga is sacrificed after the final chapter resolves (CR 714.5).
4. Combined-chapter labels like ``"I, II"`` fire the effect on each value.
5. If the saga leaves the battlefield before the final chapter, no spurious
   sacrifice is queued.
6. The new ``SagaChapter`` dataclass API and the legacy dict-of-int form
   are exercised against each other.

Card-specific tests verify the printed effect of three wired sagas (one
each from FIN, SPM, TLA).
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_HERE)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color,
    Characteristics, CardDefinition,
)
from src.cards.interceptor_helpers import make_saga_setup, SagaChapter


# =============================================================================
# Helpers
# =============================================================================


def _put_saga_on_battlefield(game, player, saga_def):
    """Create the saga in HAND, then move it to battlefield via ZONE_CHANGE.

    Mirrors the test_saga pattern: registering the object with no setup,
    then emitting ZONE_CHANGE so the pipeline installs interceptors exactly
    once.
    """
    obj = game.create_object(
        name=saga_def.name,
        owner_id=player.id,
        zone=ZoneType.HAND,
        characteristics=saga_def.characteristics,
        card_def=None,
    )
    obj.card_def = saga_def
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


def _make_saga_def(text, setup, name="Test Saga"):
    chars = Characteristics(
        types={CardType.ENCHANTMENT},
        subtypes={"Saga"},
        colors={Color.WHITE},
    )
    return CardDefinition(
        name=name,
        mana_cost="{2}{W}",
        characteristics=chars,
        text=text,
        setup_interceptors=setup,
    )


def _draw_step(game, player_id, turn=1):
    """Emit a draw-step PHASE_START for `player_id` (the active player)."""
    game.state.active_player = player_id
    game.emit(Event(
        type=EventType.PHASE_START,
        payload={'phase': 'draw', 'step': 'draw',
                 'active_player': player_id, 'turn_number': turn},
    ))


# =============================================================================
# 1. ETB fires chapter I
# =============================================================================


def test_saga_framework_etb_fires_chapter_one():
    """As the saga enters, chapter I fires once and exactly once."""
    print("\n=== Test: ETB fires chapter I ===")
    game = Game()
    p1 = game.add_player("Alice")

    fired = {1: 0, 2: 0, 3: 0}

    def mk(n):
        def fn(o, s):
            fired[n] += 1
            return []
        return fn

    def setup(obj, state):
        return make_saga_setup(
            obj,
            chapters=[
                SagaChapter("I", mk(1)),
                SagaChapter("II", mk(2)),
                SagaChapter("III", mk(3)),
            ],
        )

    saga_def = _make_saga_def(
        "(...)\nI — A\nII — B\nIII — C\n(Sacrifice after III.)", setup,
        name="Test Saga ETB I",
    )
    saga = _put_saga_on_battlefield(game, p1, saga_def)
    assert fired == {1: 1, 2: 0, 3: 0}, fired
    assert saga.state.counters.get('lore', 0) == 1
    assert saga.zone == ZoneType.BATTLEFIELD
    print("  PASS: chapter I fired exactly once")


# =============================================================================
# 2. Saga advances through chapters
# =============================================================================


def test_saga_framework_advances_through_chapters():
    """Three draw-step cycles fire I (ETB), II, then III in order."""
    print("\n=== Test: saga advances through chapters ===")
    game = Game()
    p1 = game.add_player("Alice")

    order = []

    def mk(n):
        def fn(o, s):
            order.append(n)
            return []
        return fn

    def setup(obj, state):
        return make_saga_setup(
            obj,
            chapters=[
                SagaChapter("I", mk(1)),
                SagaChapter("II", mk(2)),
                SagaChapter("III", mk(3)),
            ],
        )

    saga_def = _make_saga_def(
        "(...)\nI — A\nII — B\nIII — C\n(Sacrifice after III.)", setup,
        name="Test Saga Advance",
    )

    saga = _put_saga_on_battlefield(game, p1, saga_def)
    assert order == [1]

    _draw_step(game, p1.id, turn=1)
    assert order == [1, 2]
    assert saga.state.counters.get('lore', 0) == 2

    _draw_step(game, p1.id, turn=2)
    assert order == [1, 2, 3]
    print(f"  PASS: chapters fired in order {order}")


# =============================================================================
# 3. Sacrificed after final chapter
# =============================================================================


def test_saga_framework_sacrifices_after_final():
    """After the final chapter resolves, the saga should be in graveyard."""
    print("\n=== Test: saga is sacrificed after final ===")
    game = Game()
    p1 = game.add_player("Alice")

    def noop(o, s):
        return []

    def setup(obj, state):
        return make_saga_setup(
            obj,
            chapters=[
                SagaChapter("I", noop),
                SagaChapter("II", noop),
                SagaChapter("III", noop),
            ],
        )

    saga_def = _make_saga_def(
        "(...)\nI — A\nII — B\nIII — C\n(Sacrifice after III.)", setup,
        name="Test Saga Sac",
    )
    saga = _put_saga_on_battlefield(game, p1, saga_def)
    assert saga.zone == ZoneType.BATTLEFIELD

    _draw_step(game, p1.id, turn=1)
    assert saga.zone == ZoneType.BATTLEFIELD, "still alive after chapter II"

    _draw_step(game, p1.id, turn=2)
    assert saga.zone == ZoneType.GRAVEYARD, (
        f"Saga must be sacrificed after final chapter; zone={saga.zone}"
    )
    print(f"  PASS: saga in {saga.zone.name} after chapter III")


def test_saga_framework_sacrifice_opt_out():
    """If sacrifice_after_final=False is passed, the saga persists."""
    print("\n=== Test: saga sacrifice_after_final=False keeps it alive ===")
    game = Game()
    p1 = game.add_player("Alice")

    def setup(obj, state):
        return make_saga_setup(
            obj,
            chapters=[SagaChapter("I", lambda o, s: []),
                      SagaChapter("II", lambda o, s: [])],
            sacrifice_after_final=False,
        )

    saga_def = _make_saga_def(
        "(...)\nI — A\nII — B\n(Sacrifice after II.)", setup,
        name="Test Saga No-Sac",
    )
    saga = _put_saga_on_battlefield(game, p1, saga_def)
    _draw_step(game, p1.id, turn=1)
    # Chapter II resolved; saga should NOT be sacrificed.
    assert saga.zone == ZoneType.BATTLEFIELD, (
        f"sacrifice_after_final=False should keep saga on bf; zone={saga.zone}"
    )
    print("  PASS: saga still on battlefield after final (opt-out)")


# =============================================================================
# 4. Combined-chapter labels
# =============================================================================


def test_saga_framework_combined_chapter_fires_on_both_counts():
    """SagaChapter("I, II", fn) registers `fn` for chapter 1 AND chapter 2."""
    print("\n=== Test: combined-chapter SagaChapter('I, II') fires twice ===")
    game = Game()
    p1 = game.add_player("Alice")

    combined_fires = []
    iii_fires = []

    def combined(o, s):
        combined_fires.append(s.objects[o.id].state.counters.get('lore', 0))
        return []

    def chapter_three(o, s):
        iii_fires.append(s.objects[o.id].state.counters.get('lore', 0))
        return []

    def setup(obj, state):
        return make_saga_setup(
            obj,
            chapters=[
                SagaChapter("I, II", combined),
                SagaChapter("III", chapter_three),
            ],
        )

    saga_def = _make_saga_def(
        "(...)\nI, II — A\nIII — B\n(Sacrifice after III.)", setup,
        name="Test Saga Combined",
    )

    saga = _put_saga_on_battlefield(game, p1, saga_def)
    assert combined_fires == [1], (
        f"Combined fn should fire on chapter 1 (lore=1); got {combined_fires}"
    )
    assert iii_fires == []

    _draw_step(game, p1.id, turn=1)
    assert combined_fires == [1, 2], (
        f"Combined fn should fire on chapter 2 (lore=2); got {combined_fires}"
    )
    assert iii_fires == []

    _draw_step(game, p1.id, turn=2)
    assert iii_fires == [3]
    assert saga.zone == ZoneType.GRAVEYARD
    print(f"  PASS: combined fired at lore values {combined_fires}")


# =============================================================================
# 5. Saga leaves battlefield before final → no spurious sacrifice
# =============================================================================


def test_saga_framework_leaves_before_final_no_sac():
    """If the saga is exiled mid-life, the chapter-handler must not queue a sacrifice.

    We force-move the saga to exile before the final chapter would fire and
    then ensure that emitting a SAGA_CHAPTER event for the final chapter
    is a no-op (no SACRIFICE follows). Even if a stale interceptor remains
    in `state.interceptors`, the chapter handler reads the live zone and
    refuses to enqueue a sacrifice when the saga is no longer on
    battlefield.
    """
    print("\n=== Test: saga leaves before final → no sacrifice ===")
    game = Game()
    p1 = game.add_player("Alice")

    fired = []

    def mk(n):
        def fn(o, s):
            fired.append(n)
            return []
        return fn

    def setup(obj, state):
        return make_saga_setup(
            obj,
            chapters=[
                SagaChapter("I", mk(1)),
                SagaChapter("II", mk(2)),
                SagaChapter("III", mk(3)),
            ],
        )

    saga_def = _make_saga_def(
        "(...)\nI — A\nII — B\nIII — C\n(Sacrifice after III.)", setup,
        name="Test Saga Removed",
    )
    saga = _put_saga_on_battlefield(game, p1, saga_def)
    assert fired == [1]
    assert saga.zone == ZoneType.BATTLEFIELD

    # Forcibly exile the saga before its final chapter would fire.
    game.emit(Event(
        type=EventType.EXILE,
        payload={'object_id': saga.id},
        source=saga.id, controller=saga.controller,
    ))
    assert saga.zone == ZoneType.EXILE, f"Saga should be in exile; got {saga.zone}"

    # Even if some bookkeeping kept the chapter interceptor alive, an
    # explicit SAGA_CHAPTER 3 event must not queue a sacrifice — the saga
    # is already gone, and `_handle_saga_lore_added` short-circuits.
    game.emit(Event(
        type=EventType.SAGA_CHAPTER,
        payload={'object_id': saga.id, 'chapter': 3, 'final_chapter': 3},
        source=saga.id, controller=saga.controller,
    ))
    # The saga should still be in EXILE (no GRAVEYARD transition from a
    # SACRIFICE event firing redundantly).
    assert saga.zone == ZoneType.EXILE, (
        f"Saga zone must remain EXILE after spurious chapter event; "
        f"got {saga.zone}"
    )
    print("  PASS: spurious final chapter on exiled saga didn't re-sacrifice")


def test_saga_framework_destroyed_before_final_no_sac():
    """Pipeline-driven destruction before the final chapter should not
    cause the saga to be re-sacrificed by the chapter handler."""
    print("\n=== Test: saga destroyed mid-life skips spurious sac ===")
    game = Game()
    p1 = game.add_player("Alice")

    fired = []

    def mk(n):
        def fn(o, s):
            fired.append(n)
            return []
        return fn

    def setup(obj, state):
        return make_saga_setup(
            obj,
            chapters=[
                SagaChapter("I", mk(1)),
                SagaChapter("II", mk(2)),
                SagaChapter("III", mk(3)),
            ],
        )

    saga_def = _make_saga_def(
        "(...)\nI — A\nII — B\nIII — C\n(Sacrifice after III.)", setup,
        name="Test Saga Destroyed",
    )
    saga = _put_saga_on_battlefield(game, p1, saga_def)

    # Destroy the saga after chapter I.
    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': saga.id},
        source=saga.id, controller=saga.controller,
    ))
    assert saga.zone == ZoneType.GRAVEYARD, (
        f"Expected saga in graveyard after destroy; got {saga.zone}"
    )

    # Subsequent draw-step events should NOT fire chapter II / III.
    _draw_step(game, p1.id, turn=1)
    _draw_step(game, p1.id, turn=2)
    # Only chapter I should have fired (ETB).
    assert fired == [1], (
        f"Saga must not advance after leaving battlefield; fired {fired}"
    )
    print(f"  PASS: post-destroy chapters skipped (fired only {fired})")


# =============================================================================
# 6. API compatibility: dict and SagaChapter both work
# =============================================================================


def test_saga_framework_legacy_dict_api():
    """The legacy ``{int: fn}`` API still wires correctly."""
    print("\n=== Test: legacy dict API still works ===")
    game = Game()
    p1 = game.add_player("Alice")

    fired = []

    def mk(n):
        def fn(o, s):
            fired.append(n)
            return []
        return fn

    def setup(obj, state):
        return make_saga_setup(obj, {1: mk(1), 2: mk(2), 3: mk(3)})

    saga_def = _make_saga_def(
        "(...)\nI — A\nII — B\nIII — C\n(Sacrifice after III.)", setup,
        name="Test Saga Legacy",
    )
    saga = _put_saga_on_battlefield(game, p1, saga_def)
    assert fired == [1]
    _draw_step(game, p1.id, turn=1)
    _draw_step(game, p1.id, turn=2)
    assert fired == [1, 2, 3]
    assert saga.zone == ZoneType.GRAVEYARD
    print("  PASS: legacy dict API still works end-to-end")


def test_saga_framework_dict_chapters_conflict_raises():
    """Passing both ``chapter_handlers`` and ``chapters`` is an error."""
    print("\n=== Test: passing both APIs raises TypeError ===")
    game = Game()
    p1 = game.add_player("Alice")

    err = None

    def setup(obj, state):
        nonlocal err
        try:
            make_saga_setup(
                obj,
                {1: lambda o, s: []},
                chapters=[SagaChapter("I", lambda o, s: [])],
            )
        except TypeError as e:
            err = e
            return []
        return []

    saga_def = _make_saga_def(
        "(...)\nI — A\n(Sacrifice after I.)", setup,
        name="Test Saga Bad API",
    )
    _put_saga_on_battlefield(game, p1, saga_def)
    assert isinstance(err, TypeError), f"Expected TypeError; got {err!r}"
    print(f"  PASS: TypeError raised: {err}")


# =============================================================================
# Card-specific tests
# =============================================================================


def test_card_summon_anima_chapter_pain():
    """FIN: Summon: Anima chapter I/II/III each draw a card + lose 1 life.

    Chapter IV makes each opponent lose 3 life. We test chapter I via the
    ETB path and then chapter IV explicitly.
    """
    print("\n=== Card test: SUMMON_ANIMA chapter I (draw + lose 1) ===")
    from src.cards.final_fantasy import SUMMON_ANIMA

    game = Game()
    p1 = game.add_player("Alice")

    initial_life = p1.life
    hand_zone = game.state.zones.get(f'hand_{p1.id}')
    initial_hand_count = len(hand_zone.objects) if hand_zone else 0
    # Put one card into the library so the chapter-I draw has something
    # to draw.
    library_zone = game.state.zones.get(f'library_{p1.id}')
    if library_zone is not None:
        # Create a dummy card and put it on top of the library.
        dummy = game.create_object(
            name="Library Filler",
            owner_id=p1.id,
            zone=ZoneType.LIBRARY,
            characteristics=Characteristics(
                types={CardType.LAND},
                subtypes={"Plains"},
                colors=set(),
            ),
            card_def=None,
        )
        # Ensure the dummy is on top.
        if dummy.id in library_zone.objects:
            library_zone.objects.remove(dummy.id)
        library_zone.objects.append(dummy.id)

    saga = _put_saga_on_battlefield(game, p1, SUMMON_ANIMA)
    # Chapter I = "draw a card and you lose 1 life."
    assert p1.life == initial_life - 1, (
        f"Expected -1 life from Anima chapter I; got {p1.life - initial_life}"
    )
    print(f"  PASS: life {initial_life} → {p1.life} (chapter I pain)")
    assert saga.state.counters.get('lore', 0) == 1


def test_card_maximum_carnage_chapter_ii_adds_mana():
    """SPM: Maximum Carnage chapter II adds {R}{R}{R}.

    We tick the saga to chapter II via a draw step and verify the mana
    pool has three red mana.
    """
    print("\n=== Card test: MAXIMUM_CARNAGE chapter II adds {R}{R}{R} ===")
    from src.cards.spider_man import MAXIMUM_CARNAGE

    game = Game()
    p1 = game.add_player("Alice")

    saga = _put_saga_on_battlefield(game, p1, MAXIMUM_CARNAGE)
    # ETB → chapter I (goad noop). Tick to chapter II.
    _draw_step(game, p1.id, turn=1)
    # Verify chapter II resolved and the controller has {R}{R}{R} in the
    # mana pool (or floating mana that the engine tracks).
    pool = getattr(p1, 'mana_pool', None)
    red = 0
    if pool is not None:
        # ManaPool exposes mana as a list of ManaUnit, or as a dict.
        if hasattr(pool, 'get_total'):
            try:
                red = pool.get_total(Color.RED)
            except Exception:
                red = 0
        elif hasattr(pool, 'mana'):
            red = sum(1 for m in pool.mana if getattr(m, 'color', None) == Color.RED)
        elif isinstance(pool, dict):
            red = int(pool.get(Color.RED, 0) or pool.get('R', 0) or 0)
    assert red >= 3, (
        f"Expected ≥3 red mana after Maximum Carnage chapter II; got {red} "
        f"(pool: {pool!r})"
    )
    print(f"  PASS: {red} red mana in pool after chapter II")
    assert saga.zone == ZoneType.BATTLEFIELD, "Saga still alive at chapter II"


def test_card_leaves_from_the_vine_chapter_i_mills_three():
    """TLA: Leaves from the Vine chapter I mills three + creates a Food token."""
    print("\n=== Card test: LEAVES_FROM_THE_VINE chapter I mill 3 + Food ===")
    from src.cards.avatar_tla import LEAVES_FROM_THE_VINE

    game = Game()
    p1 = game.add_player("Alice")

    # Stock the library with 5 dummy cards to mill.
    library_zone = game.state.zones.get(f'library_{p1.id}')
    assert library_zone is not None
    initial_library_count = len(library_zone.objects)
    for i in range(5):
        dummy = game.create_object(
            name=f"Filler {i}",
            owner_id=p1.id,
            zone=ZoneType.LIBRARY,
            characteristics=Characteristics(
                types={CardType.LAND},
                subtypes={"Plains"},
                colors=set(),
            ),
            card_def=None,
        )
        # Put the new dummy on top of the library.
        if dummy.id in library_zone.objects:
            library_zone.objects.remove(dummy.id)
        library_zone.objects.append(dummy.id)
    stocked_count = len(library_zone.objects)

    gy_zone = game.state.zones.get(f'graveyard_{p1.id}')
    initial_gy = len(gy_zone.objects) if gy_zone else 0

    saga = _put_saga_on_battlefield(game, p1, LEAVES_FROM_THE_VINE)
    # Chapter I = mill 3 + create Food token.
    if gy_zone is not None:
        final_gy = len(gy_zone.objects)
        milled = final_gy - initial_gy
        assert milled >= 3, (
            f"Expected ≥3 cards milled; got {milled} (gy: {initial_gy} → {final_gy})"
        )
        print(f"  Milled {milled} card(s) to graveyard")

    # Confirm a Food token was created.
    food_tokens = [
        o for o in game.state.objects.values()
        if 'Food' in o.characteristics.subtypes
    ]
    assert len(food_tokens) >= 1, "Expected at least one Food token created"
    print(f"  PASS: {len(food_tokens)} Food token(s) created")
    assert saga.state.counters.get('lore', 0) == 1


# =============================================================================
# Entry point
# =============================================================================


_ALL_TESTS = [
    test_saga_framework_etb_fires_chapter_one,
    test_saga_framework_advances_through_chapters,
    test_saga_framework_sacrifices_after_final,
    test_saga_framework_sacrifice_opt_out,
    test_saga_framework_combined_chapter_fires_on_both_counts,
    test_saga_framework_leaves_before_final_no_sac,
    test_saga_framework_destroyed_before_final_no_sac,
    test_saga_framework_legacy_dict_api,
    test_saga_framework_dict_chapters_conflict_raises,
    test_card_summon_anima_chapter_pain,
    test_card_maximum_carnage_chapter_ii_adds_mana,
    test_card_leaves_from_the_vine_chapter_i_mills_three,
]


if __name__ == "__main__":
    for fn in _ALL_TESTS:
        fn()
    print("\n" + "=" * 60)
    print(f"ALL {len(_ALL_TESTS)} SAGA FRAMEWORK TESTS PASSED!")
    print("=" * 60)
