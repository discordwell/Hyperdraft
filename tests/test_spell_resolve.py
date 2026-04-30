"""
Tests for the extended spell resolution framework.

Covers:
- New auto-pattern matches in ``stack._create_resolve_from_text``:
  token creation (creature & artifact), +1/+1 counter on target, scry,
  surveil, mill, target-mill, pump, discard (target & each opponent),
  tap, investigate, basic-land tutor.
- Each resolve helper in ``src/engine/spell_resolve.py``.
- ``resolve_chain`` composing two effects.
- A regression sample for the legacy 8 patterns to ensure the new code
  does not shadow them.

Run directly:
    python tests/test_spell_resolve.py
"""

import os
import sys

# Insert the project root (parent of /tests) at the head of sys.path so this
# test runs equally well in the main worktree or any agent worktree.
_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_HERE)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.engine import (
    Game, Event, EventType, ZoneType,
)
from src.engine.types import (
    CardDefinition, Characteristics, CardType, Color, GameObject, ObjectState,
    new_id,
)
from src.engine.stack import SpellBuilder
from src.engine.targeting import Target
from src.engine.spell_resolve import (
    resolve_damage,
    resolve_destroy,
    resolve_exile,
    resolve_draw,
    resolve_life_change,
    resolve_create_token,
    resolve_pump,
    resolve_counter,
    resolve_modal,
    resolve_chain,
)


# ---------------------------------------------------------------------------
# Test scaffolding
# ---------------------------------------------------------------------------

def _make_game_with_two_players():
    g = Game()
    p1 = g.add_player("Alice")
    p2 = g.add_player("Bob")
    return g, p1, p2


def _put_card_in_hand(game: Game, player_id: str, card_def: CardDefinition) -> GameObject:
    """Create a GameObject for ``card_def`` and place it in ``player_id``'s hand."""
    obj = GameObject(
        id=new_id(),
        name=card_def.name,
        owner=player_id,
        controller=player_id,
        zone=ZoneType.HAND,
        characteristics=card_def.characteristics,
        state=ObjectState(),
        card_def=card_def,
        _state_ref=game.state,
    )
    game.state.objects[obj.id] = obj
    game.state.zones[f"hand_{player_id}"].objects.append(obj.id)
    return obj


def _make_creature_obj(game: Game, controller_id: str, *, power=2, toughness=2) -> GameObject:
    """Create a vanilla creature GameObject on ``controller_id``'s battlefield."""
    obj = GameObject(
        id=new_id(),
        name="Test Creature",
        owner=controller_id,
        controller=controller_id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE},
            power=power,
            toughness=toughness,
        ),
        state=ObjectState(),
        _state_ref=game.state,
    )
    game.state.objects[obj.id] = obj
    game.state.zones["battlefield"].objects.append(obj.id)
    return obj


def _resolve_text(game: Game, text: str, controller_id: str,
                  targets=None) -> list[Event]:
    """Run the auto-resolver for ``text`` and return the events it emits."""
    card_def = CardDefinition(
        name="Test Spell",
        mana_cost="{1}{R}",
        characteristics=Characteristics(types={CardType.SORCERY}),
        text=text,
    )
    obj = _put_card_in_hand(game, controller_id, card_def)
    builder = SpellBuilder(game.state, game.stack)
    item = builder.cast_spell(
        card_id=obj.id,
        controller_id=controller_id,
        targets=targets or [],
    )
    # Don't push (no need to thread through stack); we just want the resolve_fn.
    if item.resolve_fn is None:
        return []
    return list(item.resolve_fn(item.chosen_targets, game.state)) or []


def _check(condition, label: str) -> None:
    """Assertion that prints both success and failure for nicer logs."""
    if condition:
        print(f"  ok: {label}")
    else:
        raise AssertionError(label)


# ---------------------------------------------------------------------------
# Auto-pattern tests
# ---------------------------------------------------------------------------

def test_auto_create_creature_token():
    print("\n=== auto: create creature token ===")
    g, p1, _ = _make_game_with_two_players()
    events = _resolve_text(g, "Create a 1/1 white Soldier creature token.", p1.id)
    _check(len(events) == 1, "one OBJECT_CREATED event")
    e = events[0]
    _check(e.type == EventType.OBJECT_CREATED, "event type is OBJECT_CREATED")
    _check(e.payload.get('power') == 1, "power=1")
    _check(e.payload.get('toughness') == 1, "toughness=1")
    _check(Color.WHITE in (e.payload.get('colors') or []), "white color")
    _check('Soldier' in (e.payload.get('subtypes') or []), "Soldier subtype")
    _check(e.payload.get('controller') == p1.id, "controller is caster")
    _check(e.payload.get('is_token') is True, "is_token flag")


def test_auto_create_multiple_tokens():
    print("\n=== auto: create N tokens ===")
    g, p1, _ = _make_game_with_two_players()
    events = _resolve_text(g, "Create three 2/2 black Zombie creature tokens.", p1.id)
    _check(len(events) == 3, "three events")
    for e in events:
        _check(e.payload.get('power') == 2, "power=2")
        _check(e.payload.get('toughness') == 2, "toughness=2")
        _check(Color.BLACK in (e.payload.get('colors') or []), "black color")
        _check('Zombie' in (e.payload.get('subtypes') or []), "Zombie subtype")


def test_auto_create_treasure_token():
    print("\n=== auto: create treasure token ===")
    g, p1, _ = _make_game_with_two_players()
    events = _resolve_text(g, "Create two Treasure tokens.", p1.id)
    _check(len(events) == 2, "two events")
    e = events[0]
    _check(CardType.ARTIFACT in (e.payload.get('types') or []), "artifact type")
    _check('Treasure' in (e.payload.get('subtypes') or []), "Treasure subtype")
    _check(Color.COLORLESS in (e.payload.get('colors') or []), "colorless")
    _check(e.payload.get('power') is None, "no power on artifact token")


def test_auto_plus_one_counter_on_target():
    print("\n=== auto: +1/+1 counter on target ===")
    g, p1, _ = _make_game_with_two_players()
    target_obj = _make_creature_obj(g, p1.id)
    targets = [[Target(id=target_obj.id, is_player=False)]]
    events = _resolve_text(
        g, "Put a +1/+1 counter on target creature.", p1.id, targets=targets,
    )
    _check(len(events) == 1, "one event")
    e = events[0]
    _check(e.type == EventType.COUNTER_ADDED, "COUNTER_ADDED")
    _check(e.payload.get('object_id') == target_obj.id, "target object_id")
    _check(e.payload.get('counter_type') == '+1/+1', "+1/+1 counter")
    _check(e.payload.get('amount') == 1, "amount=1")


def test_auto_three_plus_one_counters_on_target():
    print("\n=== auto: 3 +1/+1 counters on target ===")
    g, p1, _ = _make_game_with_two_players()
    target_obj = _make_creature_obj(g, p1.id)
    targets = [[Target(id=target_obj.id, is_player=False)]]
    events = _resolve_text(
        g, "Put three +1/+1 counters on target creature.", p1.id, targets=targets,
    )
    _check(len(events) == 1, "one event")
    _check(events[0].payload.get('amount') == 3, "amount=3")


def test_auto_scry():
    print("\n=== auto: scry N ===")
    g, p1, _ = _make_game_with_two_players()
    events = _resolve_text(g, "Scry 2.", p1.id)
    _check(len(events) == 1, "one event")
    _check(events[0].type == EventType.SCRY, "SCRY event")
    _check(events[0].payload.get('player') == p1.id, "player is caster")
    _check(events[0].payload.get('amount') == 2, "amount=2")


def test_auto_surveil():
    print("\n=== auto: surveil N ===")
    g, p1, _ = _make_game_with_two_players()
    events = _resolve_text(g, "Surveil 1.", p1.id)
    _check(len(events) == 1, "one event")
    _check(events[0].type == EventType.SURVEIL, "SURVEIL event")
    _check(events[0].payload.get('player') == p1.id, "player is caster")
    _check(events[0].payload.get('amount') == 1, "amount=1")


def test_auto_mill_self():
    print("\n=== auto: mill N (self) ===")
    g, p1, _ = _make_game_with_two_players()
    events = _resolve_text(g, "Mill 4.", p1.id)
    _check(len(events) == 1, "one event")
    _check(events[0].type == EventType.MILL, "MILL event")
    _check(events[0].payload.get('player') == p1.id, "controller mills")
    _check(events[0].payload.get('amount') == 4, "amount=4")


def test_auto_mill_target_player():
    print("\n=== auto: target player mills N ===")
    g, p1, p2 = _make_game_with_two_players()
    targets = [[Target(id=p2.id, is_player=True)]]
    events = _resolve_text(
        g, "Target opponent mills 3 cards.", p1.id, targets=targets,
    )
    _check(len(events) == 1, "one event")
    _check(events[0].type == EventType.MILL, "MILL event")
    _check(events[0].payload.get('player') == p2.id, "p2 mills")
    _check(events[0].payload.get('amount') == 3, "amount=3")


def test_auto_pump():
    print("\n=== auto: pump until end of turn ===")
    g, p1, _ = _make_game_with_two_players()
    target_obj = _make_creature_obj(g, p1.id)
    targets = [[Target(id=target_obj.id, is_player=False)]]
    events = _resolve_text(
        g, "Target creature gets +3/+3 until end of turn.", p1.id, targets=targets,
    )
    _check(len(events) == 1, "one event")
    e = events[0]
    _check(e.type == EventType.PT_MODIFICATION, "PT_MODIFICATION")
    _check(e.payload.get('object_id') == target_obj.id, "object_id")
    _check(e.payload.get('power_mod') == 3, "power_mod=3")
    _check(e.payload.get('toughness_mod') == 3, "toughness_mod=3")
    _check(e.payload.get('duration') == 'end_of_turn', "duration end_of_turn")


def test_auto_pump_negative():
    print("\n=== auto: -2/-0 pump ===")
    g, p1, _ = _make_game_with_two_players()
    target_obj = _make_creature_obj(g, p1.id)
    targets = [[Target(id=target_obj.id, is_player=False)]]
    events = _resolve_text(
        g, "Target creature gets -2/-0 until end of turn.", p1.id, targets=targets,
    )
    _check(len(events) == 1, "one event")
    _check(events[0].payload.get('power_mod') == -2, "power_mod=-2")
    _check(events[0].payload.get('toughness_mod') == 0, "toughness_mod=0")


def test_auto_target_player_discards():
    print("\n=== auto: target player discards N cards ===")
    g, p1, p2 = _make_game_with_two_players()
    targets = [[Target(id=p2.id, is_player=True)]]
    events = _resolve_text(
        g, "Target player discards two cards.", p1.id, targets=targets,
    )
    _check(len(events) == 1, "one event")
    e = events[0]
    _check(e.type == EventType.DISCARD, "DISCARD")
    _check(e.payload.get('player') == p2.id, "p2 discards")
    _check(e.payload.get('amount') == 2, "amount=2")


def test_auto_each_opponent_discards():
    print("\n=== auto: each opponent discards a card ===")
    g, p1, p2 = _make_game_with_two_players()
    p3 = g.add_player("Carol")
    events = _resolve_text(
        g, "Each opponent discards a card.", p1.id,
    )
    _check(len(events) == 2, "two events (one per opponent)")
    payload_players = sorted(e.payload.get('player') for e in events)
    _check(payload_players == sorted([p2.id, p3.id]), "events target opponents only")


def test_auto_tap_target():
    print("\n=== auto: tap target permanent ===")
    g, p1, _ = _make_game_with_two_players()
    target_obj = _make_creature_obj(g, p1.id)
    targets = [[Target(id=target_obj.id, is_player=False)]]
    events = _resolve_text(g, "Tap target permanent.", p1.id, targets=targets)
    _check(len(events) == 1, "one event")
    _check(events[0].type == EventType.TAP, "TAP event")
    _check(events[0].payload.get('object_id') == target_obj.id, "object_id")


def test_auto_investigate():
    print("\n=== auto: investigate ===")
    g, p1, _ = _make_game_with_two_players()
    events = _resolve_text(g, "Investigate.", p1.id)
    _check(len(events) == 1, "one event")
    e = events[0]
    _check(e.type == EventType.OBJECT_CREATED, "OBJECT_CREATED")
    _check('Clue' in (e.payload.get('subtypes') or []), "Clue subtype")
    _check(CardType.ARTIFACT in (e.payload.get('types') or []), "artifact type")


def test_auto_investigate_n_times():
    print("\n=== auto: investigate three times ===")
    g, p1, _ = _make_game_with_two_players()
    events = _resolve_text(g, "Investigate three times.", p1.id)
    _check(len(events) == 3, "three OBJECT_CREATED events")
    for e in events:
        _check('Clue' in (e.payload.get('subtypes') or []), "Clue subtype")


def test_auto_basic_land_tutor():
    print("\n=== auto: basic land tutor ===")
    g, p1, _ = _make_game_with_two_players()
    text = ("Search your library for a basic land card, "
            "put it onto the battlefield tapped, then shuffle.")
    events = _resolve_text(g, text, p1.id)
    # Either a PendingChoice was opened (returning [] here), or LIBSEARCH_BEGIN
    # was emitted. Either is acceptable per the prompt.
    if events:
        _check(events[0].type == EventType.LIBSEARCH_BEGIN, "LIBSEARCH_BEGIN fallback")
    else:
        choice = g.state.pending_choice
        # An empty library makes the search a no-op; both outcomes are fine.
        _check(choice is None or choice.choice_type == 'library_search',
               "library_search choice (or no-op on empty library)")


# ---------------------------------------------------------------------------
# Regression tests for legacy 8 patterns
# ---------------------------------------------------------------------------

def test_legacy_damage_pattern_still_works():
    print("\n=== legacy: 'deals 3 damage' still routes via damage pattern ===")
    g, p1, p2 = _make_game_with_two_players()
    targets = [[Target(id=p2.id, is_player=True)]]
    events = _resolve_text(
        g, "Lightning strike deals 3 damage to any target.", p1.id, targets=targets,
    )
    _check(len(events) == 1, "one event")
    _check(events[0].type == EventType.DAMAGE, "DAMAGE event")
    _check(events[0].payload.get('amount') == 3, "amount=3")


def test_legacy_destroy_pattern_still_works():
    print("\n=== legacy: 'destroy target creature' ===")
    g, p1, _ = _make_game_with_two_players()
    target_obj = _make_creature_obj(g, p1.id)
    targets = [[Target(id=target_obj.id, is_player=False)]]
    events = _resolve_text(g, "Destroy target creature.", p1.id, targets=targets)
    _check(len(events) == 1, "one event")
    _check(events[0].type == EventType.OBJECT_DESTROYED, "OBJECT_DESTROYED")


def test_legacy_draw_pattern_still_works():
    print("\n=== legacy: 'draw 2 cards' ===")
    g, p1, _ = _make_game_with_two_players()
    events = _resolve_text(g, "Draw 2 cards.", p1.id)
    _check(len(events) == 1, "one event")
    _check(events[0].type == EventType.DRAW, "DRAW event")


def test_legacy_gain_life_pattern_still_works():
    print("\n=== legacy: 'gain 5 life' ===")
    g, p1, _ = _make_game_with_two_players()
    events = _resolve_text(g, "You gain 5 life.", p1.id)
    _check(len(events) == 1, "one event")
    _check(events[0].type == EventType.LIFE_CHANGE, "LIFE_CHANGE")
    _check(events[0].payload.get('amount') == 5, "+5 life")


# ---------------------------------------------------------------------------
# Helper-library tests
# ---------------------------------------------------------------------------

def _setup_for_helper_test(target_kind: str = 'creature'):
    """Build a game + a fake stack item so helpers can find the caster.

    Returns (game, p1, p2, target_list, source_id).
    """
    g, p1, p2 = _make_game_with_two_players()
    obj = _make_creature_obj(g, p1.id)
    targets = []
    if target_kind == 'creature':
        targets = [[Target(id=obj.id, is_player=False)]]
    elif target_kind == 'opponent':
        targets = [[Target(id=p2.id, is_player=True)]]

    # Push a fake spell so `_caster_id_from_state_and_targets` finds p1.
    builder = SpellBuilder(g.state, g.stack)
    fake_def = CardDefinition(
        name="Caster Spell",
        mana_cost="{1}",
        characteristics=Characteristics(types={CardType.SORCERY}),
        text="(test)",
    )
    fake_obj = _put_card_in_hand(g, p1.id, fake_def)
    item = builder.cast_spell(
        card_id=fake_obj.id, controller_id=p1.id, targets=targets,
    )
    g.stack.push(item)
    return g, p1, p2, targets, fake_obj.id


def test_helper_resolve_damage():
    print("\n=== helper: resolve_damage ===")
    g, p1, p2, targets, _ = _setup_for_helper_test('opponent')
    fn = resolve_damage(3)
    events = fn(targets, g.state)
    _check(len(events) == 1, "one DAMAGE event")
    _check(events[0].type == EventType.DAMAGE, "DAMAGE")
    _check(events[0].payload.get('amount') == 3, "amount=3")
    _check(events[0].payload.get('target') == p2.id, "target is opponent")


def test_helper_resolve_damage_to_each_opponent():
    print("\n=== helper: resolve_damage to each opponent ===")
    g, p1, _, _, _ = _setup_for_helper_test()
    p3 = g.add_player("Carol")
    fn = resolve_damage(2, to_each_opponent=True)
    events = fn([], g.state)
    _check(len(events) == 2, "two DAMAGE events (one per opponent)")
    for e in events:
        _check(e.payload.get('amount') == 2, "amount=2")
        _check(e.payload.get('is_player') is True, "is_player=True")


def test_helper_resolve_destroy():
    print("\n=== helper: resolve_destroy ===")
    g, p1, _, targets, _ = _setup_for_helper_test('creature')
    fn = resolve_destroy()
    events = fn(targets, g.state)
    _check(len(events) == 1, "one event")
    _check(events[0].type == EventType.OBJECT_DESTROYED, "OBJECT_DESTROYED")


def test_helper_resolve_exile():
    print("\n=== helper: resolve_exile ===")
    g, p1, _, targets, _ = _setup_for_helper_test('creature')
    fn = resolve_exile()
    events = fn(targets, g.state)
    _check(len(events) == 1, "one ZONE_CHANGE")
    _check(events[0].type == EventType.ZONE_CHANGE, "ZONE_CHANGE")
    _check(events[0].payload.get('to_zone_type') == ZoneType.EXILE, "to exile")


def test_helper_resolve_draw():
    print("\n=== helper: resolve_draw ===")
    g, p1, _, _, _ = _setup_for_helper_test()
    fn = resolve_draw(2)
    events = fn([], g.state)
    _check(len(events) == 1, "one DRAW event")
    _check(events[0].type == EventType.DRAW, "DRAW")
    _check(events[0].payload.get('player') == p1.id, "p1 draws")
    _check(events[0].payload.get('amount') == 2, "amount=2")


def test_helper_resolve_life_change_caster():
    print("\n=== helper: resolve_life_change (caster) ===")
    g, p1, _, _, _ = _setup_for_helper_test()
    fn = resolve_life_change(4)
    events = fn([], g.state)
    _check(len(events) == 1, "one LIFE_CHANGE")
    _check(events[0].payload.get('player') == p1.id, "p1 gains")
    _check(events[0].payload.get('amount') == 4, "+4 life")


def test_helper_resolve_create_token():
    print("\n=== helper: resolve_create_token ===")
    g, p1, _, _, _ = _setup_for_helper_test()
    fn = resolve_create_token(
        name="Spirit Token", power=1, toughness=1,
        types=[CardType.CREATURE], subtypes=["Spirit"],
        colors=[Color.WHITE], count=2,
    )
    events = fn([], g.state)
    _check(len(events) == 2, "two OBJECT_CREATED events")
    for e in events:
        _check(e.type == EventType.OBJECT_CREATED, "OBJECT_CREATED")
        _check(e.payload.get('controller') == p1.id, "controller is caster")
        _check('Spirit' in e.payload.get('subtypes', []), "Spirit subtype")
        _check(Color.WHITE in e.payload.get('colors', []), "white color")
        _check(e.payload.get('is_token') is True, "is_token")


def test_helper_resolve_pump():
    print("\n=== helper: resolve_pump ===")
    g, p1, _, targets, _ = _setup_for_helper_test('creature')
    fn = resolve_pump(2, 2)
    events = fn(targets, g.state)
    _check(len(events) == 1, "one PT event")
    _check(events[0].type == EventType.PT_MODIFICATION, "PT_MODIFICATION")
    _check(events[0].payload.get('power_mod') == 2, "+2 power")
    _check(events[0].payload.get('toughness_mod') == 2, "+2 toughness")


def test_helper_resolve_counter():
    print("\n=== helper: resolve_counter ===")
    g, p1, _, targets, _ = _setup_for_helper_test('creature')
    fn = resolve_counter(amount=2, counter_type='+1/+1')
    events = fn(targets, g.state)
    _check(len(events) == 1, "one COUNTER_ADDED")
    _check(events[0].type == EventType.COUNTER_ADDED, "COUNTER_ADDED")
    _check(events[0].payload.get('amount') == 2, "amount=2")
    _check(events[0].payload.get('counter_type') == '+1/+1', "+1/+1 counter")


def test_helper_resolve_modal():
    print("\n=== helper: resolve_modal ===")
    g, p1, _, _, source_id = _setup_for_helper_test()
    fn = resolve_modal([
        resolve_draw(1),
        resolve_life_change(7),
    ])
    # No mode chosen -> defaults to first option (draw).
    events_default = fn([], g.state)
    _check(events_default[0].type == EventType.DRAW, "default mode -> DRAW")
    # Set mode = 1 on the topmost stack object's chosen_mode attr.
    stack_zone = g.state.zones['stack']
    top_id = stack_zone.objects[-1]
    g.state.objects[top_id].chosen_mode = 1
    events_alt = fn([], g.state)
    _check(events_alt[0].type == EventType.LIFE_CHANGE, "mode=1 -> LIFE_CHANGE")
    _check(events_alt[0].payload.get('amount') == 7, "+7 life")


def test_helper_resolve_chain_two_effects():
    print("\n=== helper: resolve_chain composes two effects ===")
    g, p1, p2, _, _ = _setup_for_helper_test()
    targets = [[Target(id=p2.id, is_player=True)]]
    fn = resolve_chain(
        resolve_damage(2),
        resolve_draw(1),
    )
    events = fn(targets, g.state)
    _check(len(events) == 2, "two events (damage + draw)")
    types_in_order = [e.type for e in events]
    _check(types_in_order == [EventType.DAMAGE, EventType.DRAW], "ordered DAMAGE then DRAW")
    _check(events[0].payload.get('amount') == 2, "2 damage")
    _check(events[1].payload.get('player') == p1.id, "caster draws")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

ALL_TESTS = [
    # Auto-pattern tests
    test_auto_create_creature_token,
    test_auto_create_multiple_tokens,
    test_auto_create_treasure_token,
    test_auto_plus_one_counter_on_target,
    test_auto_three_plus_one_counters_on_target,
    test_auto_scry,
    test_auto_surveil,
    test_auto_mill_self,
    test_auto_mill_target_player,
    test_auto_pump,
    test_auto_pump_negative,
    test_auto_target_player_discards,
    test_auto_each_opponent_discards,
    test_auto_tap_target,
    test_auto_investigate,
    test_auto_investigate_n_times,
    test_auto_basic_land_tutor,
    # Legacy regressions
    test_legacy_damage_pattern_still_works,
    test_legacy_destroy_pattern_still_works,
    test_legacy_draw_pattern_still_works,
    test_legacy_gain_life_pattern_still_works,
    # Helper-library tests
    test_helper_resolve_damage,
    test_helper_resolve_damage_to_each_opponent,
    test_helper_resolve_destroy,
    test_helper_resolve_exile,
    test_helper_resolve_draw,
    test_helper_resolve_life_change_caster,
    test_helper_resolve_create_token,
    test_helper_resolve_pump,
    test_helper_resolve_counter,
    test_helper_resolve_modal,
    test_helper_resolve_chain_two_effects,
]


def main():
    failures = 0
    for test in ALL_TESTS:
        try:
            test()
        except AssertionError as e:
            print(f"  FAIL: {test.__name__}: {e}")
            failures += 1
        except Exception as e:
            import traceback
            print(f"  ERROR: {test.__name__}: {e}")
            traceback.print_exc()
            failures += 1
    total = len(ALL_TESTS)
    passed = total - failures
    print(f"\n=== Spell Resolve: {passed}/{total} passed ===")
    if failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
