"""Phase 5b — Replacement-effect framework tests.

These tests cover the cards/uses requested by Agent Q's brief:

  * ``test_replacement_effect_doubles_damage`` — Twinflame Tyrant + a creature
    deals 3 damage to an opponent -> opponent takes 6.
  * ``test_replacement_does_not_apply_to_opposing_sources`` — opponent's
    creature deals 3 -> damage stays at 3.
  * ``test_two_replacements_apply_at_most_once_each`` — Twinflame Tyrant +
    Gratuitous Violence both in play, single 1-damage event -> final damage
    is 4 (1*2*2), not 8 or 1.
  * ``test_replacement_unregistered_when_source_leaves`` — Twinflame dies,
    subsequent damage events are NOT doubled.
  * ``test_replacement_does_not_replace_zero_damage`` — 0-damage events don't
    get replaced (no spurious doubling).
  * ``test_neriv_doubles_damage_for_creatures_that_entered_this_turn`` —
    new wiring proof: Neriv (Tarkir: Dragonstorm) doubles damage from
    creatures with summoning sickness, leaves older creatures alone.
  * ``test_replacement_lifegain_doubles_only_for_controller`` — Wind Crystal
    (life-gain x2) only doubles its controller's life gain, not the
    opponent's.
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_HERE)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color,
)
from src.engine.types import Characteristics, CardDefinition


# =============================================================================
# Helpers
# =============================================================================

def _new_game():
    game = Game()
    p1 = game.add_player("Alice", life=20)
    p2 = game.add_player("Bob", life=20)
    return game, p1, p2


def _put_creature(game, owner, name="T", power=2, toughness=2,
                  sickness=False):
    """Create a creature directly on the battlefield."""
    chars = Characteristics(
        types={CardType.CREATURE},
        subtypes={"Beast"},
        power=power, toughness=toughness,
    )
    cdef = CardDefinition(
        name=name, mana_cost="{2}",
        characteristics=chars,
    )
    obj = game.create_object(
        name=name, owner_id=owner.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=chars, card_def=cdef,
    )
    # Default: cleared sickness so test creatures can attack/etc.
    obj.state.summoning_sickness = bool(sickness)
    return obj


def _put_card(game, owner, card_def):
    """Drop a CardDefinition onto the battlefield (runs setup_interceptors)."""
    return game.create_object(
        name=card_def.name,
        owner_id=owner.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=card_def.characteristics,
        card_def=card_def,
    )


# =============================================================================
# Brief-specified tests
# =============================================================================

def test_replacement_effect_doubles_damage():
    """Twinflame Tyrant + 3 damage to opponent -> opponent takes 6 (CR 614)."""
    print("\n=== Test: replacement_effect_doubles_damage ===")
    from src.cards.foundations import TWINFLAME_TYRANT

    game, p1, p2 = _new_game()
    twinflame = _put_card(game, p1, TWINFLAME_TYRANT)
    src_creature = _put_creature(game, p1, name="Bolt-Hurler", power=2)

    starting_life = p2.life
    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': p2.id, 'amount': 3},
        source=src_creature.id,
    ))

    delta = starting_life - p2.life
    assert delta == 6, f"expected 6 (3 doubled), got {delta}"
    print(f"PASS: opponent lost {delta} life (3 doubled)")


def test_replacement_does_not_apply_to_opposing_sources():
    """Twinflame Tyrant on p1's side; p2's creature deals 3 -> stays 3."""
    print("\n=== Test: replacement_does_not_apply_to_opposing_sources ===")
    from src.cards.foundations import TWINFLAME_TYRANT

    game, p1, p2 = _new_game()
    _put_card(game, p1, TWINFLAME_TYRANT)
    # Source belongs to opponent.
    opp_source = _put_creature(game, p2, name="Enemy-Bolt", power=2)

    starting_life = p1.life
    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': p1.id, 'amount': 3},
        source=opp_source.id,
    ))

    delta = starting_life - p1.life
    assert delta == 3, f"expected 3 (no double, opposing source), got {delta}"
    print(f"PASS: p1 lost {delta} life (no double)")


def test_two_replacements_apply_at_most_once_each():
    """Twinflame + Gratuitous both in play, 1 damage event -> 4, not 8 or 1.

    MTG rule: each replacement effect can apply at most once per event. With
    two doublers stacked, 1 -> 2 -> 4.
    """
    print("\n=== Test: two_replacements_apply_at_most_once_each ===")
    from src.cards.foundations import TWINFLAME_TYRANT, GRATUITOUS_VIOLENCE

    game, p1, p2 = _new_game()
    _put_card(game, p1, TWINFLAME_TYRANT)
    _put_card(game, p1, GRATUITOUS_VIOLENCE)

    # Source is a creature so Gratuitous Violence applies.
    p1_creature = _put_creature(game, p1, name="Bonk", power=1)
    target = _put_creature(game, p2, name="Mug", power=1, toughness=20)

    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': target.id, 'amount': 1},
        source=p1_creature.id,
    ))

    final = target.state.damage
    assert final == 4, (
        f"expected 4 (1 doubled twice = 4), got {final}. "
        f"If 8: a replacement is firing twice on its own output. "
        f"If 1: replacements never fired."
    )
    print(f"PASS: target took {final} damage (1 -> 2 -> 4)")


def test_replacement_unregistered_when_source_leaves():
    """Twinflame dies; subsequent damage is NOT doubled (cleanup on zone change)."""
    print("\n=== Test: replacement_unregistered_when_source_leaves ===")
    from src.cards.foundations import TWINFLAME_TYRANT

    game, p1, p2 = _new_game()
    twinflame = _put_card(game, p1, TWINFLAME_TYRANT)

    # Sanity: Twinflame's replacement is registered.
    pre_count = sum(
        1 for ic in game.state.interceptors.values() if ic.source == twinflame.id
    )
    assert pre_count >= 1, "Twinflame should have registered a replacement"

    # Move Twinflame to the graveyard.
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': twinflame.id,
            'from_zone_type': ZoneType.BATTLEFIELD,
            'to_zone_type': ZoneType.GRAVEYARD,
        },
    ))

    # Replacement should no longer fire.
    p1_src = _put_creature(game, p1, name="Source", power=2)
    p2_tgt = _put_creature(game, p2, name="Mug", toughness=20)
    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': p2_tgt.id, 'amount': 4},
        source=p1_src.id,
    ))

    assert p2_tgt.state.damage == 4, (
        f"expected 4 (no double after Twinflame left), got {p2_tgt.state.damage}"
    )
    print(f"PASS: target took {p2_tgt.state.damage} after Twinflame left")


def test_replacement_does_not_replace_zero_damage():
    """0-damage events don't get replaced (no spurious doubling -> 0)."""
    print("\n=== Test: replacement_does_not_replace_zero_damage ===")
    from src.cards.foundations import TWINFLAME_TYRANT

    game, p1, p2 = _new_game()
    _put_card(game, p1, TWINFLAME_TYRANT)
    p1_src = _put_creature(game, p1, name="Zero-Bolt", power=0)
    p2_tgt = _put_creature(game, p2, name="Beefy", toughness=10)

    pre_damage = p2_tgt.state.damage
    pre_log_len = len(game.state.event_log)

    # 0-damage event: the framework filters amount<=0 out, so the event
    # should pass through unmodified.
    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': p2_tgt.id, 'amount': 0},
        source=p1_src.id,
    ))

    # No damage marked, no replacement marker pinned.
    assert p2_tgt.state.damage == pre_damage, (
        f"0-damage event applied damage anyway: {p2_tgt.state.damage}"
    )

    # And the event_log records a DAMAGE with amount 0 (unmodified).
    new_log = game.state.event_log[pre_log_len:]
    dmg_events = [e for e in new_log if e.type == EventType.DAMAGE]
    assert dmg_events, "expected the 0-damage event in the log"
    final = dmg_events[-1]
    assert final.payload.get('amount', 0) == 0, (
        f"expected 0 in log, got {final.payload.get('amount')}"
    )
    # No replacement marker should have been pinned to the event payload.
    marker_keys = [
        k for k in final.payload.keys()
        if isinstance(k, str) and k.startswith('_replaced_by')
    ]
    assert not marker_keys, (
        f"0-damage event was touched by a replacement: markers={marker_keys}"
    )
    print("PASS: 0-damage event passed through with no replacement")


# =============================================================================
# Additional coverage — Neriv wiring (new in this commit)
# =============================================================================

def test_neriv_doubles_damage_for_creatures_that_entered_this_turn():
    """Neriv doubles damage for sickness-flagged creatures only.

    Proxy for "entered this turn": summoning sickness flag still set.
    """
    print("\n=== Test: neriv_doubles_damage_for_creatures_that_entered_this_turn ===")
    from src.cards.tarkir_dragonstorm import NERIV_HEART_OF_THE_STORM

    game, p1, p2 = _new_game()
    neriv = _put_card(game, p1, NERIV_HEART_OF_THE_STORM)

    # Creature that "entered this turn" -> sickness=True, doubled.
    new_creature = _put_creature(game, p1, name="Fresh-Dragon", power=3,
                                 sickness=True)
    # Creature that was already in play -> sickness=False, NOT doubled.
    old_creature = _put_creature(game, p1, name="Old-Bear", power=3,
                                 sickness=False)

    p2_target_a = _put_creature(game, p2, name="MugA", toughness=20)
    p2_target_b = _put_creature(game, p2, name="MugB", toughness=20)

    # Fresh creature: 3 -> 6.
    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': p2_target_a.id, 'amount': 3},
        source=new_creature.id,
    ))
    assert p2_target_a.state.damage == 6, (
        f"expected 6 (Neriv doubled), got {p2_target_a.state.damage}"
    )

    # Old creature: 3 stays 3.
    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': p2_target_b.id, 'amount': 3},
        source=old_creature.id,
    ))
    assert p2_target_b.state.damage == 3, (
        f"expected 3 (no double, no sickness), got {p2_target_b.state.damage}"
    )
    print(
        f"PASS: fresh creature damage doubled ({p2_target_a.state.damage}), "
        f"old creature not ({p2_target_b.state.damage})"
    )


# =============================================================================
# Negative test — life-doubling controlled scope
# =============================================================================

def test_replacement_lifegain_doubles_only_for_controller():
    """The Wind Crystal: only the controller's life gains get doubled."""
    print("\n=== Test: replacement_lifegain_doubles_only_for_controller ===")
    from src.cards.final_fantasy import THE_WIND_CRYSTAL

    game, p1, p2 = _new_game()
    _put_card(game, p1, THE_WIND_CRYSTAL)

    # Controller gains 4 life -> doubled to 8.
    p1_pre = p1.life
    game.emit(Event(
        type=EventType.LIFE_CHANGE,
        payload={'player': p1.id, 'amount': 4},
    ))
    p1_delta = p1.life - p1_pre
    assert p1_delta == 8, (
        f"expected p1 +8 (4 doubled), got +{p1_delta}"
    )

    # Opponent gains 4 life -> stays 4 (the Wind Crystal only affects its
    # controller).
    p2_pre = p2.life
    game.emit(Event(
        type=EventType.LIFE_CHANGE,
        payload={'player': p2.id, 'amount': 4},
    ))
    p2_delta = p2.life - p2_pre
    assert p2_delta == 4, (
        f"expected p2 +4 (no double, not controller), got +{p2_delta}"
    )
    print(f"PASS: p1 +{p1_delta} (doubled), p2 +{p2_delta} (untouched)")


# =============================================================================
# Driver
# =============================================================================

def run_all_tests():
    print("=" * 60)
    print("PHASE 5b REPLACEMENT-EFFECT TESTS")
    print("=" * 60)

    test_replacement_effect_doubles_damage()
    test_replacement_does_not_apply_to_opposing_sources()
    test_two_replacements_apply_at_most_once_each()
    test_replacement_unregistered_when_source_leaves()
    test_replacement_does_not_replace_zero_damage()
    test_neriv_doubles_damage_for_creatures_that_entered_this_turn()
    test_replacement_lifegain_doubles_only_for_controller()

    print("\n" + "=" * 60)
    print("ALL PHASE 5b REPLACEMENT TESTS PASSED")
    print("=" * 60)


if __name__ == "__main__":
    run_all_tests()
