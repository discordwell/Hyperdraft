"""
MTG Saga Mechanic Tests

Validates the lore-counter / chapter-trigger / final-chapter-sacrifice
behavior implemented in ``src/engine/saga.py`` + the ``make_saga_setup``
helper in ``src/cards/interceptor_helpers.py``.
"""

import asyncio
import sys

sys.path.insert(0, '/Users/discordwell/Projects/HYPERDRAFT/.claude/worktrees/agent-a3f5b4657c792cc38')

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color,
    Characteristics, CardDefinition,
)
from src.cards.interceptor_helpers import make_saga_setup


def _build_saga(text: str, chapter_handlers, name="Test Saga"):
    """Make a basic Saga CardDefinition for testing."""
    chars = Characteristics(
        types={CardType.ENCHANTMENT},
        subtypes={"Saga"},
        colors={Color.WHITE},
    )

    def _setup(obj, state):
        return make_saga_setup(obj, chapter_handlers)

    return CardDefinition(
        name=name,
        mana_cost="{2}{W}",
        characteristics=chars,
        text=text,
        setup_interceptors=_setup,
    )


def _put_saga_on_battlefield(game, player, saga_def):
    """
    Mirror the test_lorwyn helper: create the object in HAND without
    setup, then move it onto the battlefield via ZONE_CHANGE so
    interceptors get installed exactly once.
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


def test_saga_etb_chapter_one_fires():
    """As Saga ETBs, a lore counter is added and chapter I triggers."""
    print("\n=== Test: Saga ETB chapter I ===")
    game = Game()
    p1 = game.add_player("Alice")

    fired = {'I': 0, 'II': 0, 'III': 0}

    def ch_i(obj, state):
        fired['I'] += 1
        return []

    def ch_ii(obj, state):
        fired['II'] += 1
        return []

    def ch_iii(obj, state):
        fired['III'] += 1
        return []

    saga_def = _build_saga(
        "(As this Saga enters and after your draw step, add a lore counter. "
        "Sacrifice after III.)\nI — Test\nII — Test\nIII — Test",
        {1: ch_i, 2: ch_ii, 3: ch_iii},
    )

    saga = _put_saga_on_battlefield(game, p1, saga_def)
    assert fired['I'] == 1, f"Chapter I should fire once on ETB; fired {fired}"
    assert fired['II'] == 0
    assert fired['III'] == 0
    assert saga.state.counters.get('lore', 0) == 1
    assert saga.zone == ZoneType.BATTLEFIELD
    print("  Chapter I fired:", fired['I'])
    print("  Lore counters:", saga.state.counters.get('lore', 0))
    print("  Zone:", saga.zone.name)


def test_saga_advances_on_draw_step():
    """After the controller's draw step a new lore counter is added and the
    next chapter triggers."""
    print("\n=== Test: Saga advances on draw step ===")
    game = Game()
    p1 = game.add_player("Alice")

    fired = []

    def make(ch):
        def fn(obj, state):
            fired.append(ch)
            return []
        return fn

    saga_def = _build_saga(
        "(...)\nI — a\nII — b\nIII — c",
        {1: make(1), 2: make(2), 3: make(3)},
    )

    saga = _put_saga_on_battlefield(game, p1, saga_def)
    assert fired == [1]
    assert saga.zone == ZoneType.BATTLEFIELD

    # Simulate controller's draw step: PHASE_START with phase='draw' and
    # active_player == saga's controller.
    game.state.active_player = p1.id
    game.emit(Event(
        type=EventType.PHASE_START,
        payload={'phase': 'draw', 'step': 'draw',
                 'active_player': p1.id, 'turn_number': 1},
    ))
    assert fired == [1, 2], f"Expected [1,2], got {fired}"
    assert saga.state.counters.get('lore', 0) == 2
    assert saga.zone == ZoneType.BATTLEFIELD

    # Another draw step -> chapter III.
    game.emit(Event(
        type=EventType.PHASE_START,
        payload={'phase': 'draw', 'step': 'draw',
                 'active_player': p1.id, 'turn_number': 2},
    ))
    assert fired == [1, 2, 3]
    # After chapter III the Saga should have been sacrificed (final chapter).
    assert saga.zone == ZoneType.GRAVEYARD, f"Saga zone after final chapter: {saga.zone}"
    print("  Chapters fired:", fired)
    print("  Final zone:", saga.zone.name)


def test_saga_does_not_advance_on_opponent_draw():
    """Opponent's draw step must not add a lore counter."""
    print("\n=== Test: Saga ignores opponent's draw step ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")

    fired = []

    def make(ch):
        def fn(obj, state):
            fired.append(ch)
            return []
        return fn

    saga_def = _build_saga(
        "(...)\nI — a\nII — b\nIII — c",
        {1: make(1), 2: make(2), 3: make(3)},
    )
    saga = _put_saga_on_battlefield(game, p1, saga_def)
    assert fired == [1]

    # Opponent's draw step. Saga should not advance.
    game.state.active_player = p2.id
    game.emit(Event(
        type=EventType.PHASE_START,
        payload={'phase': 'draw', 'step': 'draw',
                 'active_player': p2.id, 'turn_number': 1},
    ))
    assert fired == [1], f"Saga must not advance on opponent's draw; fired {fired}"
    assert saga.state.counters.get('lore', 0) == 1


def test_saga_chapter_effect_emits_events():
    """A chapter handler that returns events sees them go through the pipeline."""
    print("\n=== Test: chapter effect emits events ===")
    game = Game()
    p1 = game.add_player("Alice")

    # Chapter I gains the controller 3 life.
    def chapter_one(obj, state):
        return [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': obj.controller, 'amount': 3},
            source=obj.id,
        )]

    saga_def = _build_saga(
        "(...)\nI — gain 3\nII — nothing\nIII — nothing",
        {1: chapter_one, 2: lambda o, s: [], 3: lambda o, s: []},
    )

    initial = p1.life
    _put_saga_on_battlefield(game, p1, saga_def)
    assert p1.life == initial + 3, f"Expected life {initial+3}, got {p1.life}"
    print(f"  Life gain: {initial} -> {p1.life}")


def test_real_saga_card_choco_mog():
    """End-to-end test using a real wired Saga card (Summon: Choco/Mog).

    Verifies that ``setup_interceptors=summon_chocomog_ff_setup`` wires up
    correctly when going through the same code path as gameplay."""
    print("\n=== Test: real Saga card Summon: Choco/Mog ===")
    from src.cards.final_fantasy import SUMMON_CHOCOMOG

    game = Game()
    p1 = game.add_player("Alice")

    # Other creature on the battlefield to verify the +1/+0 stampede fires.
    ally = game.create_object(
        name="Ally",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE},
            power=2, toughness=2,
            colors={Color.WHITE},
        ),
    )
    base_power = ally.characteristics.power

    saga = game.create_object(
        name=SUMMON_CHOCOMOG.name,
        owner_id=p1.id,
        zone=ZoneType.HAND,
        characteristics=SUMMON_CHOCOMOG.characteristics,
        card_def=None,
    )
    saga.card_def = SUMMON_CHOCOMOG
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': saga.id,
            'from_zone': f'hand_{p1.id}',
            'to_zone': 'battlefield',
            'to_zone_type': ZoneType.BATTLEFIELD,
        },
    ))

    # ETB chapter I: stampede. Other creature should be +1/+0 EOT.
    from src.engine import get_power
    boosted = get_power(ally, game.state)
    print(f"  Ally base power {base_power} -> after chapter I {boosted}")
    assert boosted == base_power + 1, f"Expected +1 power; got {boosted}"
    assert saga.state.counters.get('lore', 0) == 1
    assert saga.zone == ZoneType.BATTLEFIELD


def test_saga_four_chapters_sacrifices_after_iv():
    """Saga with `Sacrifice after IV.` only sacrifices on chapter IV."""
    print("\n=== Test: Saga IV ===")
    game = Game()
    p1 = game.add_player("Alice")

    fired = []

    def make(ch):
        def fn(obj, state):
            fired.append(ch)
            return []
        return fn

    saga_def = _build_saga(
        "(As this Saga enters and after your draw step, add a lore counter. "
        "Sacrifice after IV.)\nI — a\nII — b\nIII — c\nIV — d",
        {1: make(1), 2: make(2), 3: make(3), 4: make(4)},
    )

    saga = _put_saga_on_battlefield(game, p1, saga_def)
    assert fired == [1]
    assert saga.zone == ZoneType.BATTLEFIELD

    game.state.active_player = p1.id
    for _ in range(3):
        game.emit(Event(
            type=EventType.PHASE_START,
            payload={'phase': 'draw', 'step': 'draw',
                     'active_player': p1.id, 'turn_number': 99},
        ))
    assert fired == [1, 2, 3, 4]
    assert saga.zone == ZoneType.GRAVEYARD


if __name__ == "__main__":
    test_saga_etb_chapter_one_fires()
    test_saga_advances_on_draw_step()
    test_saga_does_not_advance_on_opponent_draw()
    test_saga_chapter_effect_emits_events()
    test_saga_four_chapters_sacrifices_after_iv()
    test_real_saga_card_choco_mog()
    print("\n" + "=" * 60)
    print("ALL SAGA TESTS PASSED!")
    print("=" * 60)
