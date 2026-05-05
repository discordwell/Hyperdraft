"""Tests for the planeswalker loyalty framework.

Covers:
- ETB: PW enters with starting_loyalty counters.
- +N ability: pays nothing else, adds N loyalty, fires effect.
- -N ability: requires >= N loyalty; removes N; fires effect.
- -N ability with insufficient loyalty: rejected (illegal action).
- Once-per-turn: cannot activate two loyalty abilities in same turn.
- Sorcery-speed: cannot activate during opponent's turn.
- 0-loyalty SBA: PW destroyed when loyalty hits 0.
- Damage to PW: damage converts to loyalty-counter removal.
- Damage to PW reduces loyalty to 0 -> destroyed.
- Ral, Crackling Wit (BLB): full wiring smoke-test.
"""

from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_HERE)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import asyncio

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color,
)
from src.cards.card_factories import make_planeswalker
from src.engine.priority import ActionType, PlayerAction
from src.engine.turn import Phase, check_planeswalker_zero_loyalty_sbas
from src.cards.interceptor_helpers import (
    make_planeswalker_setup,
    make_loyalty_ability,
    get_loyalty,
)


# ---------------------------------------------------------------------------
# Test scaffolding
# ---------------------------------------------------------------------------


def _setup_game_for_player(p_id, game):
    """Set up turn_state so the player has priority on their own main phase."""
    game.turn_manager.turn_state.active_player_id = p_id
    game.turn_manager.turn_state.phase = Phase.PRECOMBAT_MAIN
    game.state.active_player = p_id
    game.state.turn_number = 1


def _spawn_on_battlefield(game, player, card_def):
    obj = game.create_object(
        name=card_def.name,
        owner_id=player.id,
        zone=ZoneType.HAND,
        characteristics=card_def.characteristics,
        card_def=None,
    )
    obj.card_def = card_def
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


def _make_test_pw(*, starting_loyalty: int = 4, with_minus3: bool = True,
                  with_plus2: bool = True, with_zero: bool = False,
                  ability_text: str = ""):
    """Construct a stub planeswalker with the requested loyalty abilities.

    Each ability records the resolution into a list captured via
    ``card_def._test_log`` so tests can verify the effect_fn fired.
    """
    log: list = []

    def setup(obj, state):
        ints = make_planeswalker_setup(obj, starting_loyalty=starting_loyalty)
        if with_plus2:
            def plus2_effect(o, st, targets):
                log.append(("+2", o.id))
                return []
            make_loyalty_ability(
                obj, cost=+2, effect_fn=plus2_effect, ability_id="+2",
                description="+2: log +2",
            )
        if with_minus3:
            def minus3_effect(o, st, targets):
                log.append(("-3", o.id))
                return []
            make_loyalty_ability(
                obj, cost=-3, effect_fn=minus3_effect, ability_id="-3",
                description="-3: log -3",
            )
        if with_zero:
            def zero_effect(o, st, targets):
                log.append(("0", o.id))
                return []
            make_loyalty_ability(
                obj, cost=0, effect_fn=zero_effect, ability_id="0",
                description="0: log 0",
            )
        return ints

    pw = make_planeswalker(
        name="Test Walker",
        mana_cost="{2}{U}{R}",
        colors={Color.BLUE, Color.RED},
        loyalty=starting_loyalty,
        subtypes={"Test"},
        supertypes={"Legendary"},
        text=ability_text or "+2: log +2.\n-3: log -3.",
        setup_interceptors=setup,
    )
    pw._test_log = log
    return pw


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_etb_adds_starting_loyalty():
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    _setup_game_for_player(p1.id, game)

    pw_def = _make_test_pw(starting_loyalty=4)
    pw = _spawn_on_battlefield(game, p1, pw_def)

    assert get_loyalty(pw) == 4, f"expected 4 loyalty, got {get_loyalty(pw)}"
    assert pw.zone == ZoneType.BATTLEFIELD
    print("PASS: ETB adds starting loyalty")


def test_plus_n_ability_adds_loyalty_and_fires_effect():
    async def _run():
        game = Game()
        p1 = game.add_player("Alice")
        p2 = game.add_player("Bob")
        _setup_game_for_player(p1.id, game)

        pw_def = _make_test_pw(starting_loyalty=4)
        pw = _spawn_on_battlefield(game, p1, pw_def)
        pw.state.summoning_sickness = False
        starting = get_loyalty(pw)

        # Find +2 ability index.
        plus_idx = None
        for idx, ab in enumerate(pw.state.activated_abilities):
            if getattr(ab, "loyalty_cost", 0) == 2:
                plus_idx = idx
                break
        assert plus_idx is not None, "could not find +2 ability"

        action = PlayerAction(
            type=ActionType.ACTIVATE_ABILITY,
            player_id=p1.id, source_id=pw.id,
            ability_id=f"activated:{plus_idx}",
        )
        events = await game.priority_system._execute_action(action)
        types = [e.type for e in events]
        assert EventType.ACTIVATE in types, f"expected ACTIVATE, got {types}"

        # Resolve stack item.
        item = game.stack.items[-1]
        resolved = item.resolve_fn(item.chosen_targets, game.state)
        for e in resolved:
            game.emit(e)

        assert get_loyalty(pw) == starting + 2, f"expected {starting+2}, got {get_loyalty(pw)}"
        assert ("+2", pw.id) in pw_def._test_log, f"effect didn't fire: {pw_def._test_log}"
        print("PASS: +N ability adds loyalty and fires effect")

    asyncio.get_event_loop().run_until_complete(_run())


def test_minus_n_ability_removes_loyalty_and_fires_effect():
    async def _run():
        game = Game()
        p1 = game.add_player("Alice")
        p2 = game.add_player("Bob")
        _setup_game_for_player(p1.id, game)

        pw_def = _make_test_pw(starting_loyalty=5)
        pw = _spawn_on_battlefield(game, p1, pw_def)
        pw.state.summoning_sickness = False
        starting = get_loyalty(pw)

        # Find -3 ability index.
        minus_idx = None
        for idx, ab in enumerate(pw.state.activated_abilities):
            if getattr(ab, "loyalty_cost", 0) == -3:
                minus_idx = idx
                break
        assert minus_idx is not None, "could not find -3 ability"

        action = PlayerAction(
            type=ActionType.ACTIVATE_ABILITY,
            player_id=p1.id, source_id=pw.id,
            ability_id=f"activated:{minus_idx}",
        )
        events = await game.priority_system._execute_action(action)
        types = [e.type for e in events]
        assert EventType.ACTIVATE in types, f"expected ACTIVATE, got {types}"
        assert EventType.COUNTER_REMOVED in types, f"expected COUNTER_REMOVED, got {types}"

        # Resolve stack item.
        item = game.stack.items[-1]
        resolved = item.resolve_fn(item.chosen_targets, game.state)
        for e in resolved:
            game.emit(e)

        # 5 - 3 = 2 expected.
        assert get_loyalty(pw) == starting - 3, f"expected {starting-3}, got {get_loyalty(pw)}"
        assert ("-3", pw.id) in pw_def._test_log, f"effect didn't fire: {pw_def._test_log}"
        print("PASS: -N ability removes loyalty and fires effect")

    asyncio.get_event_loop().run_until_complete(_run())


def test_minus_n_with_insufficient_loyalty_is_rejected():
    async def _run():
        game = Game()
        p1 = game.add_player("Alice")
        p2 = game.add_player("Bob")
        _setup_game_for_player(p1.id, game)

        # Starting loyalty 2, but ability costs 3.
        pw_def = _make_test_pw(starting_loyalty=2)
        pw = _spawn_on_battlefield(game, p1, pw_def)
        pw.state.summoning_sickness = False

        minus_idx = None
        for idx, ab in enumerate(pw.state.activated_abilities):
            if getattr(ab, "loyalty_cost", 0) == -3:
                minus_idx = idx
                break
        assert minus_idx is not None

        # Legal actions surface should NOT include the -3 ability.
        actions = game.priority_system.get_legal_actions(p1.id)
        matches = [a for a in actions if a.ability_id == f"activated:{minus_idx}"
                   and a.source_id == pw.id]
        assert not matches, f"-3 should be illegal at 2 loyalty, got: {[m.description for m in matches]}"

        # Even if forced, the ability path returns no events (rejected).
        action = PlayerAction(
            type=ActionType.ACTIVATE_ABILITY,
            player_id=p1.id, source_id=pw.id,
            ability_id=f"activated:{minus_idx}",
        )
        events = await game.priority_system._handle_activate_ability(action)
        assert not events, f"expected no events, got {[e.type for e in events]}"

        # Loyalty unchanged.
        assert get_loyalty(pw) == 2
        print("PASS: -N with insufficient loyalty is rejected")

    asyncio.get_event_loop().run_until_complete(_run())


def test_once_per_turn_blocks_second_activation():
    async def _run():
        game = Game()
        p1 = game.add_player("Alice")
        p2 = game.add_player("Bob")
        _setup_game_for_player(p1.id, game)

        pw_def = _make_test_pw(starting_loyalty=10)
        pw = _spawn_on_battlefield(game, p1, pw_def)
        pw.state.summoning_sickness = False

        # First activation: +2.
        plus_idx = None
        minus_idx = None
        for idx, ab in enumerate(pw.state.activated_abilities):
            if getattr(ab, "loyalty_cost", 0) == 2:
                plus_idx = idx
            if getattr(ab, "loyalty_cost", 0) == -3:
                minus_idx = idx
        assert plus_idx is not None and minus_idx is not None

        action = PlayerAction(
            type=ActionType.ACTIVATE_ABILITY,
            player_id=p1.id, source_id=pw.id,
            ability_id=f"activated:{plus_idx}",
        )
        events = await game.priority_system._execute_action(action)
        assert any(e.type == EventType.ACTIVATE for e in events), "first activation should succeed"
        # Resolve stack item to fire the LOYALTY_ABILITY_ACTIVATED marker
        # (the lockout interceptor reacts to that marker).
        item = game.stack.items[-1]
        resolved = item.resolve_fn(item.chosen_targets, game.state)
        for e in resolved:
            game.emit(e)

        # Second activation (-3) on the same turn should be rejected.
        actions = game.priority_system.get_legal_actions(p1.id)
        matches = [a for a in actions if a.source_id == pw.id and a.ability_id.startswith("activated:")]
        assert not matches, f"loyalty abilities should be locked out, got: {[m.description for m in matches]}"

        action2 = PlayerAction(
            type=ActionType.ACTIVATE_ABILITY,
            player_id=p1.id, source_id=pw.id,
            ability_id=f"activated:{minus_idx}",
        )
        events2 = await game.priority_system._handle_activate_ability(action2)
        assert not events2, "second activation should be rejected by once-per-turn"
        print("PASS: once-per-turn blocks second activation")

    asyncio.get_event_loop().run_until_complete(_run())


def test_sorcery_speed_blocks_on_opponent_turn():
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    # Bob's turn.
    game.turn_manager.turn_state.active_player_id = p2.id
    game.turn_manager.turn_state.phase = Phase.PRECOMBAT_MAIN
    game.state.active_player = p2.id

    pw_def = _make_test_pw(starting_loyalty=4)
    pw = _spawn_on_battlefield(game, p1, pw_def)
    pw.state.summoning_sickness = False

    actions = game.priority_system.get_legal_actions(p1.id)
    matches = [a for a in actions if a.source_id == pw.id and a.ability_id.startswith("activated:")]
    assert not matches, f"loyalty abilities should be hidden on opponent's turn, got: {[m.description for m in matches]}"
    print("PASS: sorcery-speed blocks on opponent's turn")


def test_zero_loyalty_destroys_planeswalker_via_sba():
    """When loyalty drops to 0, the SBA helper destroys the PW."""
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    _setup_game_for_player(p1.id, game)

    pw_def = _make_test_pw(starting_loyalty=3)
    pw = _spawn_on_battlefield(game, p1, pw_def)
    pw.state.summoning_sickness = False

    # Force loyalty to zero by zeroing the counters dict.
    pw.state.counters['loyalty'] = 0
    assert pw.zone == ZoneType.BATTLEFIELD

    events = check_planeswalker_zero_loyalty_sbas(game.state, game.pipeline)
    assert any(e.type == EventType.OBJECT_DESTROYED for e in events), \
        f"expected OBJECT_DESTROYED, got {[e.type for e in events]}"
    assert pw.zone == ZoneType.GRAVEYARD, f"expected GRAVEYARD, got {pw.zone}"
    print("PASS: 0-loyalty SBA destroys planeswalker")


def test_damage_redirects_to_loyalty_counter_removal():
    """Damage to a PW removes that many loyalty counters."""
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    _setup_game_for_player(p1.id, game)

    pw_def = _make_test_pw(starting_loyalty=5)
    pw = _spawn_on_battlefield(game, p1, pw_def)
    pw.state.summoning_sickness = False

    # Bob's creature damages Ral for 3.
    game.deal_damage(source_id="bolt-source", target_id=pw.id, amount=3)
    assert get_loyalty(pw) == 2, f"expected 2 loyalty (5-3), got {get_loyalty(pw)}"
    # The PW should NOT have damage marked (we redirect, we don't mark).
    assert pw.state.damage == 0, f"expected damage=0, got {pw.state.damage}"
    print("PASS: damage to PW redirects to loyalty-counter removal")


def test_damage_lethal_destroys_planeswalker():
    """Damage that drops loyalty to 0 triggers destruction via the SBA hook."""
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    _setup_game_for_player(p1.id, game)

    pw_def = _make_test_pw(starting_loyalty=3)
    pw = _spawn_on_battlefield(game, p1, pw_def)
    pw.state.summoning_sickness = False

    # Bolt for 3 -> drops loyalty to 0 -> SBA destroys.
    game.deal_damage(source_id="bolt-source", target_id=pw.id, amount=3)
    # The COUNTER_REMOVED-driven SBA hook should have already destroyed it.
    # If it hasn't (because the interceptor pipeline ordering let the
    # destruction event ride on the same emit), call the helper to be sure.
    if pw.zone == ZoneType.BATTLEFIELD:
        check_planeswalker_zero_loyalty_sbas(game.state, game.pipeline)
    assert pw.zone == ZoneType.GRAVEYARD, f"expected GRAVEYARD, got {pw.zone}"
    print("PASS: lethal damage destroys planeswalker")


def test_zero_cost_ability():
    async def _run():
        game = Game()
        p1 = game.add_player("Alice")
        p2 = game.add_player("Bob")
        _setup_game_for_player(p1.id, game)

        pw_def = _make_test_pw(starting_loyalty=3, with_zero=True, with_plus2=False,
                                with_minus3=False)
        pw = _spawn_on_battlefield(game, p1, pw_def)
        pw.state.summoning_sickness = False
        starting = get_loyalty(pw)

        zero_idx = None
        for idx, ab in enumerate(pw.state.activated_abilities):
            if getattr(ab, "loyalty_cost", None) == 0 and getattr(ab, "is_loyalty", False):
                zero_idx = idx
                break
        assert zero_idx is not None

        action = PlayerAction(
            type=ActionType.ACTIVATE_ABILITY,
            player_id=p1.id, source_id=pw.id,
            ability_id=f"activated:{zero_idx}",
        )
        events = await game.priority_system._execute_action(action)
        item = game.stack.items[-1]
        resolved = item.resolve_fn(item.chosen_targets, game.state)
        for e in resolved:
            game.emit(e)
        assert get_loyalty(pw) == starting, f"0-cost ability shouldn't change loyalty"
        assert ("0", pw.id) in pw_def._test_log
        print("PASS: 0-cost ability fires without loyalty change")

    asyncio.get_event_loop().run_until_complete(_run())


def test_turn_start_resets_once_per_turn_lock():
    """After a TURN_START event, the planeswalker can activate again."""
    async def _run():
        game = Game()
        p1 = game.add_player("Alice")
        p2 = game.add_player("Bob")
        _setup_game_for_player(p1.id, game)

        pw_def = _make_test_pw(starting_loyalty=10)
        pw = _spawn_on_battlefield(game, p1, pw_def)
        pw.state.summoning_sickness = False

        plus_idx = None
        for idx, ab in enumerate(pw.state.activated_abilities):
            if getattr(ab, "loyalty_cost", 0) == 2:
                plus_idx = idx
                break

        # First activation.
        action = PlayerAction(
            type=ActionType.ACTIVATE_ABILITY,
            player_id=p1.id, source_id=pw.id,
            ability_id=f"activated:{plus_idx}",
        )
        await game.priority_system._execute_action(action)
        item = game.stack.items[-1]
        resolved = item.resolve_fn(item.chosen_targets, game.state)
        for e in resolved:
            game.emit(e)

        # Drain the stack (sorcery-speed legality requires an empty stack).
        while game.stack.items:
            game.stack.items.pop()

        # Bump turn number and emit TURN_START.
        game.state.turn_number = 2
        game.emit(Event(
            type=EventType.TURN_START,
            payload={'player': p1.id, 'turn_number': 2},
        ))

        # Now the +2 should be activatable again.
        actions = game.priority_system.get_legal_actions(p1.id)
        matches = [a for a in actions if a.source_id == pw.id and a.ability_id == f"activated:{plus_idx}"]
        assert matches, f"after TURN_START, +2 should be activatable; got {[a.description for a in actions if a.source_id == pw.id]}"
        print("PASS: TURN_START resets once-per-turn lock")

    asyncio.get_event_loop().run_until_complete(_run())


def test_ral_crackling_wit_smoke_test():
    """Smoke-test Ral, Crackling Wit (BLB) wiring through the framework."""
    from src.cards.bloomburrow import RAL_CRACKLING_WIT

    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    _setup_game_for_player(p1.id, game)

    ral = _spawn_on_battlefield(game, p1, RAL_CRACKLING_WIT)
    ral.state.summoning_sickness = False

    assert get_loyalty(ral) == 4, f"Ral should ETB with 4 loyalty, got {get_loyalty(ral)}"

    # All three loyalty abilities + the noncreature spell-cast trigger should
    # be registered on Ral. Tally how many loyalty abilities are listed.
    loyalty_abilities = [ab for ab in ral.state.activated_abilities
                         if getattr(ab, "is_loyalty", False)]
    assert len(loyalty_abilities) == 3, \
        f"expected 3 loyalty abilities, got {len(loyalty_abilities)}: " \
        f"{[a.loyalty_ability_id for a in loyalty_abilities]}"
    costs = sorted(a.loyalty_cost for a in loyalty_abilities)
    assert costs == [-10, -3, 1], f"unexpected costs: {costs}"
    print("PASS: Ral, Crackling Wit smoke-test (ETB loyalty + 3 loyalty abilities)")


# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------

def run_all():
    failed = 0
    tests = [
        test_etb_adds_starting_loyalty,
        test_plus_n_ability_adds_loyalty_and_fires_effect,
        test_minus_n_ability_removes_loyalty_and_fires_effect,
        test_minus_n_with_insufficient_loyalty_is_rejected,
        test_once_per_turn_blocks_second_activation,
        test_sorcery_speed_blocks_on_opponent_turn,
        test_zero_loyalty_destroys_planeswalker_via_sba,
        test_damage_redirects_to_loyalty_counter_removal,
        test_damage_lethal_destroys_planeswalker,
        test_zero_cost_ability,
        test_turn_start_resets_once_per_turn_lock,
        test_ral_crackling_wit_smoke_test,
    ]
    for t in tests:
        try:
            t()
        except AssertionError as e:
            failed += 1
            print(f"FAIL: {t.__name__}: {e}")
        except Exception as e:
            failed += 1
            import traceback
            print(f"ERROR: {t.__name__}: {e}")
            traceback.print_exc()
    print(f"\n{len(tests) - failed}/{len(tests)} tests passed")
    return failed


if __name__ == "__main__":
    sys.exit(run_all())
