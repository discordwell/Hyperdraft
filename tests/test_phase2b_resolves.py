"""
Phase 2B vanilla-spell resolve sweep tests.

Validates the new `resolve=` callbacks added to MKM and ECL spells whose
effects don't fit the auto-pattern matcher in `src/engine/stack.py`.

These tests verify that calling each resolve function with a representative
state either:
- emits the right events directly (untargeted effects), or
- opens a PendingChoice that, when resolved, produces the expected events.

We avoid spinning up a full stack/casting flow — we call `resolve` directly
since each resolve is independent of cast-time costs.
"""

import os
import sys

_THIS = os.path.abspath(__file__)
_ROOT = os.path.dirname(os.path.dirname(_THIS))
sys.path.insert(0, _ROOT)

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color, Characteristics,
)
from src.cards.murders_karlov_manor import (
    CEREBRAL_CONFISCATION,
    EXTRACT_A_CONFESSION,
    MACABRE_RECONSTRUCTION,
    FELONIOUS_RAGE,
    AUDIENCE_WITH_TROSTANI,
    HARDHITTING_QUESTION,
    URGENT_NECROPSY,
)
from src.cards.lorwyn_eclipsed import (
    RIVERGUARDS_REFLEXES,
    RUN_AWAY_TOGETHER,
    THIRST_FOR_IDENTITY,
    WANDERWINE_FAREWELL,
    BLIGHT_ROT,
    DARKNESS_DESCENDS,
    NAMELESS_INVERSION,
    PERFECT_INTIMIDATION,
    BLOSSOMING_DEFENSE,
)


def _make_game(num_players: int = 2):
    game = Game()
    players = [game.add_player(f"P{i}") for i in range(num_players)]
    if not game.state.active_player and players:
        game.state.active_player = players[0].id
    return game, players


def _put_creature(game, player, name, power=2, toughness=2):
    obj = game.create_object(
        name=name,
        owner_id=player.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE}, power=power, toughness=toughness,
        ),
    )
    obj.controller = player.id
    return obj


# =============================================================================
# All resolves are present
# =============================================================================

def test_phase2b_resolves_present():
    """Smoke check: every Phase 2B card has a resolve callback."""
    cards = [
        CEREBRAL_CONFISCATION, EXTRACT_A_CONFESSION, MACABRE_RECONSTRUCTION,
        FELONIOUS_RAGE, AUDIENCE_WITH_TROSTANI, HARDHITTING_QUESTION,
        URGENT_NECROPSY,
        RIVERGUARDS_REFLEXES, RUN_AWAY_TOGETHER, THIRST_FOR_IDENTITY,
        WANDERWINE_FAREWELL, BLIGHT_ROT, DARKNESS_DESCENDS,
        NAMELESS_INVERSION, PERFECT_INTIMIDATION, BLOSSOMING_DEFENSE,
    ]
    for c in cards:
        assert callable(c.resolve), f"{c.name} resolve missing"
    print("PASS: all Phase 2B resolves are wired")


# =============================================================================
# MKM
# =============================================================================

def test_macabre_reconstruction_opens_choice():
    """Macabre Reconstruction posts a target_with_callback over the caster's GY."""
    game, (p, opp) = _make_game(2)

    # Put a creature card in caster's graveyard.
    grave = game.state.zones.get(f"graveyard_{p.id}")
    assert grave is not None
    creature = game.create_object(
        name="Goblin",
        owner_id=p.id,
        zone=ZoneType.GRAVEYARD,
        characteristics=Characteristics(
            types={CardType.CREATURE}, power=1, toughness=1,
        ),
    )
    grave.objects.append(creature.id)

    MACABRE_RECONSTRUCTION.resolve([], game.state)
    pc = game.state.pending_choice
    assert pc is not None, "Expected pending choice"
    assert pc.choice_type == "target_with_callback"
    assert creature.id in pc.options
    print("PASS: Macabre Reconstruction opens GY target choice")


def test_extract_a_confession_opens_per_opponent_sacrifice_choices():
    """Extract a Confession opens a sacrifice choice for each opponent with a creature."""
    game, (p, opp) = _make_game(2)

    _put_creature(game, opp, "Opp Goblin", 1, 1)
    EXTRACT_A_CONFESSION.resolve([], game.state)
    pc = game.state.pending_choice
    assert pc is not None
    assert pc.choice_type == "sacrifice"
    assert pc.player == opp.id
    print("PASS: Extract a Confession queues opponent sacrifice choice")


def test_audience_with_trostani_creates_token_and_draws():
    """Audience with Trostani emits OBJECT_CREATED (Plant) + DRAW (>=1)."""
    game, (p, opp) = _make_game(2)
    events = AUDIENCE_WITH_TROSTANI.resolve([], game.state)
    assert any(e.type == EventType.OBJECT_CREATED for e in events)
    assert any(e.type == EventType.DRAW for e in events)
    # The Plant we just made counts toward the draw count -> at least 1.
    draw_evt = next(e for e in events if e.type == EventType.DRAW)
    assert draw_evt.payload['count'] >= 1
    print("PASS: Audience with Trostani makes Plant + draws")


def test_urgent_necropsy_opens_destroy_choice():
    """Urgent Necropsy queues a chained destroy-up-to-one choice."""
    game, (p, opp) = _make_game(2)
    _put_creature(game, opp, "Opp Creature", 2, 2)
    URGENT_NECROPSY.resolve([], game.state)
    pc = game.state.pending_choice
    assert pc is not None
    assert pc.choice_type == "target_with_callback"
    assert pc.min_choices == 0 and pc.max_choices == 1
    print("PASS: Urgent Necropsy opens chained destroy choice")


def test_felonious_rage_pumps_caster_creature():
    """Felonious Rage opens a target choice scoped to caster's creatures."""
    game, (p, opp) = _make_game(2)
    own = _put_creature(game, p, "Mine", 2, 2)
    _put_creature(game, opp, "Theirs", 2, 2)
    FELONIOUS_RAGE.resolve([], game.state)
    pc = game.state.pending_choice
    assert pc is not None
    assert own.id in pc.options
    print("PASS: Felonious Rage scopes target to caster's creatures")


def test_hardhitting_question_opens_two_target_chain():
    """Hard-Hitting Question opens a target choice for caster's creatures first."""
    game, (p, opp) = _make_game(2)
    _put_creature(game, p, "Mine", 4, 4)
    _put_creature(game, opp, "Theirs", 2, 2)
    HARDHITTING_QUESTION.resolve([], game.state)
    pc = game.state.pending_choice
    assert pc is not None
    # First choice is over caster's creatures.
    for tid in pc.options:
        obj = game.state.objects[tid]
        assert obj.controller == p.id
    print("PASS: Hard-Hitting Question opens own-creature choice first")


def test_cerebral_confiscation_modal():
    """Cerebral Confiscation opens a 1-of-2 modal choice."""
    game, (p, opp) = _make_game(2)
    CEREBRAL_CONFISCATION.resolve([], game.state)
    pc = game.state.pending_choice
    assert pc is not None
    assert pc.choice_type == "modal_with_callback"
    assert pc.min_choices == 1 and pc.max_choices == 1
    assert len(pc.options) == 2
    print("PASS: Cerebral Confiscation opens modal choice")


# =============================================================================
# ECL
# =============================================================================

def test_blight_rot_emits_minus_counters():
    """Blight Rot resolves to a target choice that adds 4 -1/-1 counters."""
    game, (p, opp) = _make_game(2)
    target = _put_creature(game, opp, "Victim", 4, 4)

    BLIGHT_ROT.resolve([], game.state)
    pc = game.state.pending_choice
    assert pc is not None
    assert target.id in pc.options
    # Simulate selection.
    handler = pc.callback_data['handler']
    events = handler(pc, [target.id], game.state)
    counter_evts = [e for e in events if e.type == EventType.COUNTER_ADDED]
    assert counter_evts and counter_evts[0].payload['amount'] == 4
    assert counter_evts[0].payload['counter_type'] == '-1/-1'
    print("PASS: Blight Rot adds 4 -1/-1 counters")


def test_darkness_descends_blankets_battlefield():
    """Darkness Descends puts 2 -1/-1 counters on every creature on the battlefield."""
    game, (p, opp) = _make_game(2)
    a = _put_creature(game, p, "A", 3, 3)
    b = _put_creature(game, opp, "B", 4, 4)

    events = DARKNESS_DESCENDS.resolve([], game.state)
    targets = {e.payload['object_id'] for e in events if e.type == EventType.COUNTER_ADDED}
    assert a.id in targets and b.id in targets
    for e in events:
        assert e.payload['amount'] == 2
        assert e.payload['counter_type'] == '-1/-1'
    print("PASS: Darkness Descends hits all creatures")


def test_blossoming_defense_opens_self_target_choice_and_emits_pump_keyword():
    """Blossoming Defense pumps and grants hexproof to a caster creature."""
    game, (p, opp) = _make_game(2)
    own = _put_creature(game, p, "Mine", 2, 2)
    _put_creature(game, opp, "Theirs", 2, 2)

    BLOSSOMING_DEFENSE.resolve([], game.state)
    pc = game.state.pending_choice
    assert pc is not None
    # Only own creatures should be valid targets.
    for tid in pc.options:
        assert game.state.objects[tid].controller == p.id
    handler = pc.callback_data['handler']
    events = handler(pc, [own.id], game.state)
    assert any(e.type == EventType.PT_MODIFICATION for e in events)
    assert any(e.type == EventType.KEYWORD_GRANT
               and 'hexproof' in e.payload['keywords'] for e in events)
    print("PASS: Blossoming Defense pumps + grants hexproof")


def test_riverguards_reflexes_emits_pump_keyword_untap():
    """Riverguard's Reflexes: +2/+2 + first strike + UNTAP on selected creature."""
    game, (p, _opp) = _make_game(2)
    target = _put_creature(game, p, "Mine", 2, 2)

    RIVERGUARDS_REFLEXES.resolve([], game.state)
    pc = game.state.pending_choice
    assert pc is not None
    handler = pc.callback_data['handler']
    events = handler(pc, [target.id], game.state)
    types = {e.type for e in events}
    assert EventType.PT_MODIFICATION in types
    assert EventType.KEYWORD_GRANT in types
    assert EventType.UNTAP in types
    print("PASS: Riverguard's Reflexes emits all 3 events")


def test_run_away_together_requires_two_distinct_controllers():
    """Run Away Together opens a 2-target choice, validating distinct controllers."""
    game, (p, opp) = _make_game(2)
    a = _put_creature(game, p, "A", 1, 1)
    b = _put_creature(game, opp, "B", 1, 1)

    RUN_AWAY_TOGETHER.resolve([], game.state)
    pc = game.state.pending_choice
    assert pc is not None
    assert pc.min_choices == 2 and pc.max_choices == 2
    handler = pc.callback_data['handler']
    events = handler(pc, [a.id, b.id], game.state)
    bounce_evts = [e for e in events if e.type == EventType.ZONE_CHANGE]
    assert len(bounce_evts) == 2
    print("PASS: Run Away Together bounces 2 distinct-controller creatures")


def test_run_away_together_rejects_same_controller():
    """When all candidate creatures share one controller, no choice is opened."""
    game, (p, _opp) = _make_game(2)
    _put_creature(game, p, "A", 1, 1)
    _put_creature(game, p, "B", 1, 1)

    events = RUN_AWAY_TOGETHER.resolve([], game.state)
    assert events == [], "No events expected when no legal pair exists"
    assert game.state.pending_choice is None, (
        "No choice should be opened when no two creatures with different "
        "controllers exist"
    )
    print("PASS: Run Away Together fizzles on same-controller pool")


def test_thirst_for_identity_draws_three_and_opens_discard():
    """Thirst for Identity emits DRAW(3) and opens a discard-2 prompt."""
    game, (p, _opp) = _make_game(2)
    # Seed the hand with 3 cards so the discard choice has options.
    hand = game.state.zones[f"hand_{p.id}"]
    for i in range(3):
        c = game.create_object(
            name=f"Land{i}",
            owner_id=p.id,
            zone=ZoneType.HAND,
            characteristics=Characteristics(types={CardType.LAND}),
        )
        hand.objects.append(c.id)

    events = THIRST_FOR_IDENTITY.resolve([], game.state)
    draws = [e for e in events if e.type == EventType.DRAW]
    assert draws and draws[0].payload['count'] == 3
    pc = game.state.pending_choice
    assert pc is not None
    assert pc.choice_type == "discard"
    print("PASS: Thirst for Identity draws 3 + opens discard choice")


def test_nameless_inversion_pump():
    """Nameless Inversion: +3/-3 PT_MODIFICATION on a chosen creature."""
    game, (p, opp) = _make_game(2)
    target = _put_creature(game, opp, "Victim", 2, 4)

    NAMELESS_INVERSION.resolve([], game.state)
    pc = game.state.pending_choice
    handler = pc.callback_data['handler']
    events = handler(pc, [target.id], game.state)
    assert events and events[0].type == EventType.PT_MODIFICATION
    assert events[0].payload['power_mod'] == 3
    assert events[0].payload['toughness_mod'] == -3
    print("PASS: Nameless Inversion +3/-3")


def test_perfect_intimidation_modal_choice_one_or_both():
    """Perfect Intimidation opens a modal choice with min_modes=1, max_modes=2."""
    game, (p, _opp) = _make_game(2)
    PERFECT_INTIMIDATION.resolve([], game.state)
    pc = game.state.pending_choice
    assert pc is not None
    assert pc.choice_type == "modal_with_callback"
    assert pc.min_choices == 1 and pc.max_choices == 2
    print("PASS: Perfect Intimidation modal choice 1-or-both")


def test_wanderwine_farewell_returns_and_makes_token_when_merfolk():
    """Wanderwine Farewell bounces nonland and creates Merfolk token if controller has Merfolk."""
    game, (p, opp) = _make_game(2)
    # Caster controls a Merfolk to trigger the rider.
    merfolk = game.create_object(
        name="My Merfolk",
        owner_id=p.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE}, subtypes={"Merfolk"}, power=1, toughness=1,
        ),
    )
    merfolk.controller = p.id
    target = _put_creature(game, opp, "Target", 2, 2)

    WANDERWINE_FAREWELL.resolve([], game.state)
    pc = game.state.pending_choice
    assert pc is not None
    handler = pc.callback_data['handler']
    events = handler(pc, [target.id], game.state)
    assert any(e.type == EventType.ZONE_CHANGE for e in events)
    assert any(e.type == EventType.OBJECT_CREATED
               and e.payload.get('subtypes') == ['Merfolk'] for e in events)
    print("PASS: Wanderwine Farewell bounces + makes Merfolk token")


# =============================================================================
# Runner
# =============================================================================

ALL_TESTS = [
    test_phase2b_resolves_present,
    test_macabre_reconstruction_opens_choice,
    test_extract_a_confession_opens_per_opponent_sacrifice_choices,
    test_audience_with_trostani_creates_token_and_draws,
    test_urgent_necropsy_opens_destroy_choice,
    test_felonious_rage_pumps_caster_creature,
    test_hardhitting_question_opens_two_target_chain,
    test_cerebral_confiscation_modal,
    test_blight_rot_emits_minus_counters,
    test_darkness_descends_blankets_battlefield,
    test_blossoming_defense_opens_self_target_choice_and_emits_pump_keyword,
    test_riverguards_reflexes_emits_pump_keyword_untap,
    test_run_away_together_requires_two_distinct_controllers,
    test_run_away_together_rejects_same_controller,
    test_thirst_for_identity_draws_three_and_opens_discard,
    test_nameless_inversion_pump,
    test_perfect_intimidation_modal_choice_one_or_both,
    test_wanderwine_farewell_returns_and_makes_token_when_merfolk,
]


if __name__ == "__main__":
    failed = 0
    for fn in ALL_TESTS:
        try:
            fn()
        except Exception as e:
            failed += 1
            print(f"FAIL: {fn.__name__}: {e}")
            import traceback
            traceback.print_exc()
    print()
    print("=" * 60)
    if failed:
        print(f"{failed} test(s) failed")
        sys.exit(1)
    else:
        print(f"All {len(ALL_TESTS)} Phase 2B resolve tests passed!")
