"""Tests for the general replacement-effect framework.

Covers ``make_replacement_effect`` (the card-side helper introduced as a
generalisation of the bespoke ``make_*_replacer`` helpers in
``src/engine/replacements.py``) plus its two proof cards:

  * Twinflame Tyrant — damage from your sources to opponents/their permanents
    is doubled.
  * Gratuitous Violence — damage from your creatures to any permanent or
    player is doubled.

Tests:
  1. Helper basic — fake event, double its amount, verify TRANSFORM applied.
  2. duration='one_shot' fires exactly once; 'permanent' keeps firing.
  3. Twinflame Tyrant: damage to opponent's creature gets doubled (3 -> 6).
  4. Twinflame Tyrant: damage to own creature does NOT get doubled.
  5. Gratuitous Violence: damage to player gets doubled.
  6. No infinite loop: Twinflame's doubled output is not re-doubled by same
     Twinflame (apply_once_per_event marker pin).
  7. End-of-turn cleanup removes EOT-duration replacements.
"""
import asyncio
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_HERE)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color,
    make_creature,
)
from src.engine.types import Characteristics, CardDefinition
from src.cards.interceptor_helpers import make_replacement_effect


# =============================================================================
# Helpers
# =============================================================================

def _new_game():
    game = Game()
    p1 = game.add_player("Alice", life=20)
    p2 = game.add_player("Bob", life=20)
    return game, p1, p2


def _put_creature(game, owner, name="Test", power=2, toughness=2, *,
                  setup_fn=None):
    """Create a creature directly on the battlefield."""
    chars = Characteristics(
        types={CardType.CREATURE},
        subtypes={"Beast"},
        power=power, toughness=toughness,
    )
    cdef = CardDefinition(
        name=name, mana_cost="{2}",
        characteristics=chars,
        setup_interceptors=setup_fn,
    )
    obj = game.create_object(
        name=name, owner_id=owner.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=chars, card_def=cdef,
    )
    return obj


def _put_enchantment(game, owner, name="Test Enchant", *, setup_fn=None):
    """Create an enchantment directly on the battlefield (for global replacements)."""
    chars = Characteristics(types={CardType.ENCHANTMENT})
    cdef = CardDefinition(
        name=name, mana_cost="{2}{R}{R}",
        characteristics=chars,
        setup_interceptors=setup_fn,
    )
    obj = game.create_object(
        name=name, owner_id=owner.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=chars, card_def=cdef,
    )
    return obj


# =============================================================================
# Tests — helper basics
# =============================================================================

def test_helper_basic_doubles_damage():
    """make_replacement_effect rewrites a single DAMAGE event."""
    print("\n=== Test: helper basic (DAMAGE doubling) ===")
    game, p1, p2 = _new_game()

    def setup_fn(obj, state):
        def filter_dmg(event, state):
            return (event.type == EventType.DAMAGE
                    and event.payload.get('amount', 0) > 0)

        def double(event, state):
            new = event.copy()
            new.payload['amount'] = event.payload['amount'] * 2
            return new

        return make_replacement_effect(
            obj,
            event_filter=filter_dmg,
            replace_fn=double,
            duration='permanent',
        )

    src = _put_enchantment(game, p1, name="Doubler", setup_fn=setup_fn)
    target = _put_creature(game, p1, name="Target", power=1, toughness=10)

    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': target.id, 'amount': 3},
        source=src.id,
    ))

    # The event_log records the resolved (post-transform) event. Verify the
    # rewrite actually happened by checking both the log AND the side effect.
    log_dmg = [e for e in game.state.event_log if e.type == EventType.DAMAGE]
    assert log_dmg, "expected DAMAGE in event_log"
    final = log_dmg[-1]
    assert final.payload['amount'] == 6, (
        f"expected log amount=6 after doubling, got {final.payload['amount']}"
    )
    assert target.state.damage == 6, (
        f"expected creature to take 6 damage, got {target.state.damage}"
    )
    print(f"PASS: damage 3 -> {final.payload['amount']}, target damage={target.state.damage}")


def test_helper_one_shot_fires_once():
    """duration='one_shot' replacements consume one use, then stop firing."""
    print("\n=== Test: one_shot duration ===")
    game, p1, p2 = _new_game()

    fired = {'count': 0}

    def setup_fn(obj, state):
        def filter_dmg(event, state):
            return event.type == EventType.DAMAGE

        def double(event, state):
            fired['count'] += 1
            new = event.copy()
            new.payload['amount'] = event.payload.get('amount', 0) * 2
            return new

        return make_replacement_effect(
            obj,
            event_filter=filter_dmg,
            replace_fn=double,
            duration='one_shot',
        )

    src = _put_enchantment(game, p1, name="OneShot", setup_fn=setup_fn)
    t1 = _put_creature(game, p1, name="T1", power=1, toughness=20)
    t2 = _put_creature(game, p1, name="T2", power=1, toughness=20)

    # First damage fires the replacement.
    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': t1.id, 'amount': 4},
        source=src.id,
    ))
    assert fired['count'] == 1, f"expected 1 fire, got {fired['count']}"
    assert t1.state.damage == 8, f"expected 8 (4*2), got {t1.state.damage}"

    # Second damage should NOT fire (one-shot is exhausted).
    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': t2.id, 'amount': 4},
        source=src.id,
    ))
    assert fired['count'] == 1, f"one_shot fired again, count={fired['count']}"
    assert t2.state.damage == 4, (
        f"expected 4 (no double), got {t2.state.damage}"
    )
    print(f"PASS: one_shot fired exactly {fired['count']} time(s)")


def test_helper_permanent_keeps_firing():
    """duration='permanent' keeps doubling event after event."""
    print("\n=== Test: permanent duration ===")
    game, p1, p2 = _new_game()

    fired = {'count': 0}

    def setup_fn(obj, state):
        def filter_dmg(event, state):
            return event.type == EventType.DAMAGE

        def double(event, state):
            fired['count'] += 1
            new = event.copy()
            new.payload['amount'] = event.payload.get('amount', 0) * 2
            return new

        return make_replacement_effect(
            obj,
            event_filter=filter_dmg,
            replace_fn=double,
            duration='permanent',
        )

    src = _put_enchantment(game, p1, name="Permanent", setup_fn=setup_fn)
    t1 = _put_creature(game, p1, name="T1", power=1, toughness=20)
    t2 = _put_creature(game, p1, name="T2", power=1, toughness=20)

    for tgt in (t1, t2):
        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': tgt.id, 'amount': 3},
            source=src.id,
        ))

    assert fired['count'] == 2, f"expected 2 fires, got {fired['count']}"
    assert t1.state.damage == 6
    assert t2.state.damage == 6
    print(f"PASS: permanent fired {fired['count']} time(s)")


# =============================================================================
# Tests — Twinflame Tyrant
# =============================================================================

def test_twinflame_doubles_damage_to_opponents_creature():
    """Twinflame Tyrant doubles damage your sources deal to opponent's creatures."""
    print("\n=== Test: Twinflame doubles damage to opponent's creature ===")
    from src.cards.foundations import TWINFLAME_TYRANT

    game, p1, p2 = _new_game()

    # Twinflame on p1's battlefield.
    twinflame = game.create_object(
        name=TWINFLAME_TYRANT.name,
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=TWINFLAME_TYRANT.characteristics,
        card_def=TWINFLAME_TYRANT,
    )

    # Source on p1's battlefield, target on p2's.
    p1_attacker = _put_creature(game, p1, name="Slugger", power=3, toughness=3)
    p2_blocker = _put_creature(game, p2, name="Mug", power=1, toughness=10)

    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': p2_blocker.id, 'amount': 3},
        source=p1_attacker.id,
    ))

    assert p2_blocker.state.damage == 6, (
        f"expected 6 damage (doubled), got {p2_blocker.state.damage}"
    )
    print(f"PASS: opponent creature took {p2_blocker.state.damage} damage (3 doubled)")


def test_twinflame_does_not_double_damage_to_own_creature():
    """Twinflame Tyrant does NOT double damage to your own creature."""
    print("\n=== Test: Twinflame does NOT double damage to own creature ===")
    from src.cards.foundations import TWINFLAME_TYRANT

    game, p1, p2 = _new_game()

    twinflame = game.create_object(
        name=TWINFLAME_TYRANT.name,
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=TWINFLAME_TYRANT.characteristics,
        card_def=TWINFLAME_TYRANT,
    )

    # Both source and target on p1's battlefield (e.g. fight effect on own
    # creature, or hostile shock targeting own creature).
    p1_source = _put_creature(game, p1, name="Source", power=2, toughness=2)
    p1_target = _put_creature(game, p1, name="OwnGuy", power=1, toughness=10)

    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': p1_target.id, 'amount': 3},
        source=p1_source.id,
    ))

    assert p1_target.state.damage == 3, (
        f"expected 3 damage (not doubled), got {p1_target.state.damage}"
    )
    print(f"PASS: own creature took {p1_target.state.damage} damage (no double)")


def test_twinflame_doubles_damage_to_opponent_player():
    """Twinflame doubles damage your sources deal directly to an opponent."""
    print("\n=== Test: Twinflame doubles damage to opponent player ===")
    from src.cards.foundations import TWINFLAME_TYRANT

    game, p1, p2 = _new_game()

    twinflame = game.create_object(
        name=TWINFLAME_TYRANT.name,
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=TWINFLAME_TYRANT.characteristics,
        card_def=TWINFLAME_TYRANT,
    )

    p1_source = _put_creature(game, p1, name="Bolt-y", power=3, toughness=3)

    starting_life = p2.life
    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': p2.id, 'amount': 4},
        source=p1_source.id,
    ))

    delta = starting_life - p2.life
    assert delta == 8, (
        f"expected 8 damage to opponent (4 doubled), got {delta}"
    )
    print(f"PASS: opponent took {delta} life-loss (4 doubled)")


def test_twinflame_does_not_double_to_own_player():
    """Twinflame does NOT double damage your sources deal to YOU."""
    print("\n=== Test: Twinflame does NOT double damage to own player ===")
    from src.cards.foundations import TWINFLAME_TYRANT

    game, p1, p2 = _new_game()

    twinflame = game.create_object(
        name=TWINFLAME_TYRANT.name,
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=TWINFLAME_TYRANT.characteristics,
        card_def=TWINFLAME_TYRANT,
    )

    p1_source = _put_creature(game, p1, name="Pyromancer", power=2, toughness=2)

    starting_life = p1.life
    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': p1.id, 'amount': 2},
        source=p1_source.id,
    ))

    delta = starting_life - p1.life
    assert delta == 2, f"expected 2 damage (no double), got {delta}"
    print(f"PASS: own player took {delta} life-loss (no double)")


def test_twinflame_no_infinite_loop():
    """Twinflame's doubled output is not re-doubled by the same Twinflame."""
    print("\n=== Test: Twinflame no infinite loop (marker pin) ===")
    from src.cards.foundations import TWINFLAME_TYRANT

    game, p1, p2 = _new_game()

    twinflame = game.create_object(
        name=TWINFLAME_TYRANT.name,
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=TWINFLAME_TYRANT.characteristics,
        card_def=TWINFLAME_TYRANT,
    )

    p1_source = _put_creature(game, p1, name="Source", power=2, toughness=2)
    p2_target = _put_creature(game, p2, name="Mug", power=1, toughness=20)

    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': p2_target.id, 'amount': 4},
        source=p1_source.id,
    ))

    # 4 -> 8, NOT 4 -> 8 -> 16. The marker pin must stop re-firing.
    assert p2_target.state.damage == 8, (
        f"expected 8 damage (single double), got {p2_target.state.damage}"
    )
    print(f"PASS: target took {p2_target.state.damage} (4 doubled exactly once)")


# =============================================================================
# Tests — Gratuitous Violence
# =============================================================================

def test_gratuitous_doubles_damage_to_player():
    """Gratuitous Violence doubles creature damage to a player."""
    print("\n=== Test: Gratuitous Violence doubles damage to player ===")
    from src.cards.foundations import GRATUITOUS_VIOLENCE

    game, p1, p2 = _new_game()

    # Gratuitous Violence on p1's battlefield.
    grat = game.create_object(
        name=GRATUITOUS_VIOLENCE.name,
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=GRATUITOUS_VIOLENCE.characteristics,
        card_def=GRATUITOUS_VIOLENCE,
    )

    p1_creature = _put_creature(game, p1, name="Hellrider", power=3, toughness=3)

    starting_life = p2.life
    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': p2.id, 'amount': 3},
        source=p1_creature.id,
    ))

    delta = starting_life - p2.life
    assert delta == 6, f"expected 6 (3 doubled), got {delta}"
    print(f"PASS: opponent took {delta} life-loss (3 doubled)")


def test_gratuitous_does_not_double_noncreature_source():
    """Gratuitous Violence does NOT double damage from non-creature sources."""
    print("\n=== Test: Gratuitous Violence ignores non-creature sources ===")
    from src.cards.foundations import GRATUITOUS_VIOLENCE

    game, p1, p2 = _new_game()

    grat = game.create_object(
        name=GRATUITOUS_VIOLENCE.name,
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=GRATUITOUS_VIOLENCE.characteristics,
        card_def=GRATUITOUS_VIOLENCE,
    )

    # An enchantment dealing damage (e.g. a "deal damage" trigger). Not a creature.
    chars = Characteristics(types={CardType.ENCHANTMENT})
    cdef = CardDefinition(
        name="Pyromancer's Goggles", mana_cost="{4}",
        characteristics=chars,
    )
    enchant = game.create_object(
        name="Pyromancer's Goggles",
        owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
        characteristics=chars, card_def=cdef,
    )

    starting_life = p2.life
    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': p2.id, 'amount': 3},
        source=enchant.id,
    ))

    delta = starting_life - p2.life
    assert delta == 3, f"expected 3 (no double), got {delta}"
    print(f"PASS: enchantment-source took {delta} (no double, source not a creature)")


# =============================================================================
# Tests — End of turn cleanup
# =============================================================================

def test_end_of_turn_duration_swept_at_cleanup():
    """duration='end_of_turn' replacements get evicted by TurnManager cleanup."""
    print("\n=== Test: end_of_turn cleanup removes EOT replacements ===")
    game, p1, p2 = _new_game()

    fired = {'count': 0}

    def setup_fn(obj, state):
        def filter_dmg(event, state):
            return event.type == EventType.DAMAGE

        def double(event, state):
            fired['count'] += 1
            new = event.copy()
            new.payload['amount'] = event.payload.get('amount', 0) * 2
            return new

        return make_replacement_effect(
            obj,
            event_filter=filter_dmg,
            replace_fn=double,
            duration='end_of_turn',
        )

    src = _put_enchantment(game, p1, name="EotDouble", setup_fn=setup_fn)
    target = _put_creature(game, p1, name="Tank", power=1, toughness=20)

    # Confirm the interceptor is registered.
    pre_count = sum(1 for ic in game.state.interceptors.values()
                    if ic.source == src.id)
    assert pre_count >= 1, "EOT replacement interceptor should be registered"

    # Damage fires the doubler.
    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': target.id, 'amount': 4},
        source=src.id,
    ))
    assert fired['count'] == 1
    assert target.state.damage == 8

    # Run the cleanup step (sweep EOT interceptors).
    tm = game.turn_manager
    tm.turn_state.active_player_id = p1.id
    asyncio.run(tm._do_cleanup_step())

    # Now the EOT interceptor should be gone.
    post_count = sum(1 for ic in game.state.interceptors.values()
                     if ic.source == src.id)
    assert post_count == 0, (
        f"EOT replacement should be swept, but {post_count} remain"
    )

    # Damage no longer doubles.
    target2 = _put_creature(game, p1, name="Tank2", power=1, toughness=20)
    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': target2.id, 'amount': 4},
        source=src.id,
    ))
    assert fired['count'] == 1, (
        f"replacement fired after EOT cleanup (count={fired['count']})"
    )
    assert target2.state.damage == 4, (
        f"expected 4 (no double after EOT), got {target2.state.damage}"
    )
    print(f"PASS: EOT swept (target2 took {target2.state.damage}, no double)")


def test_source_leaves_battlefield_evicts_replacement():
    """Permanent replacement is evicted when the source leaves the battlefield."""
    print("\n=== Test: source leaving battlefield evicts permanent replacement ===")
    from src.cards.foundations import TWINFLAME_TYRANT

    game, p1, p2 = _new_game()

    twinflame = game.create_object(
        name=TWINFLAME_TYRANT.name,
        owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
        characteristics=TWINFLAME_TYRANT.characteristics,
        card_def=TWINFLAME_TYRANT,
    )
    pre_count = sum(1 for ic in game.state.interceptors.values()
                    if ic.source == twinflame.id)
    assert pre_count >= 1, "Twinflame should have registered its replacement"

    # Move Twinflame off the battlefield.
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': twinflame.id,
            'from_zone_type': ZoneType.BATTLEFIELD,
            'to_zone_type': ZoneType.GRAVEYARD,
        },
    ))

    # Damage from p1's source to p2's creature should NOT be doubled now.
    p1_attacker = _put_creature(game, p1, name="Attacker", power=2, toughness=2)
    p2_target = _put_creature(game, p2, name="Target", power=1, toughness=20)
    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': p2_target.id, 'amount': 3},
        source=p1_attacker.id,
    ))

    assert p2_target.state.damage == 3, (
        f"expected 3 (Twinflame gone), got {p2_target.state.damage}"
    )
    print(f"PASS: target took {p2_target.state.damage} after Twinflame left battlefield")


# =============================================================================
# Driver
# =============================================================================

def run_all_tests():
    print("=" * 60)
    print("REPLACEMENT-EFFECT FRAMEWORK TESTS")
    print("=" * 60)

    # Helper-level
    test_helper_basic_doubles_damage()
    test_helper_one_shot_fires_once()
    test_helper_permanent_keeps_firing()

    # Twinflame Tyrant
    test_twinflame_doubles_damage_to_opponents_creature()
    test_twinflame_does_not_double_damage_to_own_creature()
    test_twinflame_doubles_damage_to_opponent_player()
    test_twinflame_does_not_double_to_own_player()
    test_twinflame_no_infinite_loop()

    # Gratuitous Violence
    test_gratuitous_doubles_damage_to_player()
    test_gratuitous_does_not_double_noncreature_source()

    # Cleanup paths
    test_end_of_turn_duration_swept_at_cleanup()
    test_source_leaves_battlefield_evicts_replacement()

    print("\n" + "=" * 60)
    print("ALL REPLACEMENT-EFFECT TESTS PASSED")
    print("=" * 60)


if __name__ == "__main__":
    run_all_tests()
