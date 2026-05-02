"""Round-9 T2: vehicle animation Exhaust framework.

The animate-via-exhaust pattern: a non-creature artifact gains the CREATURE
type plus a base P/T plus optional +1/+1 counters until end of turn. This
test suite covers:

- The generic helper installs interceptors that flip an artifact into a
  creature with the requested base P/T.
- The +1/+1 counter rider is emitted when ``plus_one_counters > 0``.
- Cleanup at end of turn restores the original printed types AND removes
  any subtypes that were dual-written by becomes_creature.
- Each of the four wired vehicles registers exactly one Exhaust ability
  with the expected cost, and animation works end-to-end.
"""
import os
import sys
import asyncio

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_HERE)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color,
    get_power, get_toughness, get_types,
)
from src.engine.priority import ActionType, PlayerAction
from src.engine.turn import Phase
from src.cards.interceptor_helpers import make_animate_via_exhaust
from src.cards.card_factories import make_artifact


def _setup_game_for_player(p_id, game):
    game.turn_manager.turn_state.active_player_id = p_id
    game.turn_manager.turn_state.phase = Phase.PRECOMBAT_MAIN


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


def _give_player_mana(player, mana_system, *, generic=0, white=0, blue=0,
                       black=0, red=0, green=0):
    from src.engine.mana import ManaType
    for _ in range(generic):
        mana_system.produce_mana(player.id, ManaType.COLORLESS, 1)
    for _ in range(white):
        mana_system.produce_mana(player.id, ManaType.WHITE, 1)
    for _ in range(blue):
        mana_system.produce_mana(player.id, ManaType.BLUE, 1)
    for _ in range(black):
        mana_system.produce_mana(player.id, ManaType.BLACK, 1)
    for _ in range(red):
        mana_system.produce_mana(player.id, ManaType.RED, 1)
    for _ in range(green):
        mana_system.produce_mana(player.id, ManaType.GREEN, 1)


def _make_test_vehicle(name, cost, power, toughness, *, counters=0):
    def setup(obj, state):
        make_animate_via_exhaust(
            obj, cost=cost, power=power, toughness=toughness,
            plus_one_counters=counters,
        )
        return []
    return make_artifact(
        name=name, mana_cost="{2}",
        text=f"Exhaust — {cost}: This Vehicle becomes an artifact creature with base P/T {power}/{toughness} until end of turn.",
        subtypes={"Vehicle"},
        setup_interceptors=setup,
    )


# =============================================================================
# Generic helper
# =============================================================================

def test_helper_registers_one_exhaust_ability():
    game = Game()
    p1 = game.add_player("Alice")
    game.add_player("Bob")
    _setup_game_for_player(p1.id, game)

    obj = _spawn_on_battlefield(
        game, p1, _make_test_vehicle("TestRig", "{4}", 3, 3, counters=1),
    )
    abilities = obj.state.activated_abilities
    assert len(abilities) == 1
    assert abilities[0].is_exhaust
    assert abilities[0].mana_cost is not None
    assert abilities[0].mana_cost.generic == 4
    print("PASS: helper registers exactly one Exhaust ability with the right cost")


def test_animation_flips_types_and_pt():
    """Activating the exhaust turns the artifact into a creature with base P/T,
    keeps the Vehicle subtype, and emits a +1/+1 counter event when the stack
    resolves."""
    async def _run():
        game = Game()
        p1 = game.add_player("Alice")
        game.add_player("Bob")
        _setup_game_for_player(p1.id, game)

        obj = _spawn_on_battlefield(
            game, p1, _make_test_vehicle("TestRig", "{4}", 3, 3, counters=1),
        )
        # Pre-animation: NOT a creature.
        types_before = get_types(obj, game.state)
        assert CardType.CREATURE not in types_before

        _give_player_mana(p1, game.mana_system, generic=4)

        action = PlayerAction(
            type=ActionType.ACTIVATE_ABILITY,
            player_id=p1.id, source_id=obj.id, ability_id="activated:0",
        )
        events = await game.priority_system._handle_activate_ability(action)
        assert any(e.type == EventType.ACTIVATE for e in events)

        # Resolve the stack item to actually run the animate closure.
        item = game.stack.items[-1]
        resolved = item.resolve_fn(item.chosen_targets, game.state) if item.resolve_fn else []
        # +1/+1 counter rider should fire on resolution.
        ctr_events = [e for e in resolved if e.type == EventType.COUNTER_ADDED]
        assert ctr_events, f"expected COUNTER_ADDED rider, got {[e.type for e in resolved]}"
        assert ctr_events[0].payload['amount'] == 1

        # After resolution, target is a creature with base 3/3.
        types_after = get_types(obj, game.state)
        assert CardType.CREATURE in types_after, (
            f"Vehicle should now be a creature, got {types_after}"
        )
        assert get_power(obj, game.state) == 3
        assert get_toughness(obj, game.state) == 3
        # Vehicle subtype is preserved.
        assert "Vehicle" in obj.characteristics.subtypes
        print("PASS: animation flips to creature with the expected base P/T")

    asyncio.get_event_loop().run_until_complete(_run())


def test_animation_cleanup_reverts_at_eot():
    """End-of-turn cleanup removes the CREATURE type AND restores subtypes
    that were dual-written (proves the becomes_creature subtype-cleanup gap
    is fixed in Round 9)."""
    async def _run():
        game = Game()
        p1 = game.add_player("Alice")
        game.add_player("Bob")
        _setup_game_for_player(p1.id, game)

        # Vehicle that adds a creature subtype on animation.
        def setup(obj, state):
            make_animate_via_exhaust(
                obj, cost="{2}", power=2, toughness=2,
                subtypes_to_add={"Soldier"}, plus_one_counters=0,
            )
            return []

        card = make_artifact(
            name="SubtypeRig", mana_cost="{2}",
            text="Exhaust — {2}: This Vehicle becomes a 2/2 Soldier artifact creature.",
            subtypes={"Vehicle"},
            setup_interceptors=setup,
        )
        obj = _spawn_on_battlefield(game, p1, card)

        _give_player_mana(p1, game.mana_system, generic=2)

        action = PlayerAction(
            type=ActionType.ACTIVATE_ABILITY,
            player_id=p1.id, source_id=obj.id, ability_id="activated:0",
        )
        await game.priority_system._handle_activate_ability(action)
        # Resolve the stack item so the animate closure actually runs.
        item = game.stack.items[-1]
        if item.resolve_fn:
            item.resolve_fn(item.chosen_targets, game.state)

        # Mid-turn: creature, with Soldier added.
        assert CardType.CREATURE in get_types(obj, game.state)
        assert "Soldier" in obj.characteristics.subtypes
        # Vehicle still printed.
        assert "Vehicle" in obj.characteristics.subtypes

        # Run cleanup step.
        tm = game.turn_manager
        tm.turn_state.active_player_id = p1.id
        await tm._do_cleanup_step()

        types_after = get_types(obj, game.state)
        assert CardType.CREATURE not in types_after, (
            f"CREATURE type should be removed after cleanup, got {types_after}"
        )
        assert "Soldier" not in obj.characteristics.subtypes, (
            f"Soldier subtype dual-write should be reverted, got {obj.characteristics.subtypes}"
        )
        # Vehicle should still be there (it was printed).
        assert "Vehicle" in obj.characteristics.subtypes
        print("PASS: cleanup reverts CREATURE type AND added subtypes at EOT")

    asyncio.get_event_loop().run_until_complete(_run())


# =============================================================================
# Wired cards
# =============================================================================

def test_rangers_refueler_registers_animate_exhaust():
    """Rangers' Refueler: the existing draw-on-exhaust trigger plus a new
    {4} animate exhaust that brings it to 3/3 with a +1/+1 counter."""
    from src.cards.aetherdrift import RANGERS_REFUELER

    game = Game()
    p1 = game.add_player("Alice")
    game.add_player("Bob")
    _setup_game_for_player(p1.id, game)

    obj = _spawn_on_battlefield(game, p1, RANGERS_REFUELER)
    abilities = obj.state.activated_abilities
    assert len(abilities) == 1, (
        f"Rangers' Refueler should have exactly 1 exhaust ability, got {len(abilities)}"
    )
    assert abilities[0].mana_cost.generic == 4
    print("PASS: Rangers' Refueler registers its animate-exhaust ({4})")


def test_rocketeer_boostbuggy_registers_animate_exhaust():
    from src.cards.aetherdrift import ROCKETEER_BOOSTBUGGY

    game = Game()
    p1 = game.add_player("Alice")
    game.add_player("Bob")
    _setup_game_for_player(p1.id, game)

    obj = _spawn_on_battlefield(game, p1, ROCKETEER_BOOSTBUGGY)
    abilities = obj.state.activated_abilities
    assert len(abilities) == 1
    assert abilities[0].mana_cost.generic == 3
    print("PASS: Rocketeer Boostbuggy registers its animate-exhaust ({3})")


def test_marshals_pathcruiser_registers_animate_exhaust():
    from src.cards.aetherdrift import MARSHALS_PATHCRUISER

    game = Game()
    p1 = game.add_player("Alice")
    game.add_player("Bob")
    _setup_game_for_player(p1.id, game)

    obj = _spawn_on_battlefield(game, p1, MARSHALS_PATHCRUISER)
    abilities = obj.state.activated_abilities
    assert len(abilities) == 1
    cost = abilities[0].mana_cost
    # 5-color cost: one of each.
    assert cost.white == 1 and cost.blue == 1 and cost.black == 1
    assert cost.red == 1 and cost.green == 1
    print("PASS: Marshals' Pathcruiser registers its animate-exhaust (WUBRG)")


def test_invasion_submersible_registers_animate_exhaust():
    from src.cards.avatar_tla import INVASION_SUBMERSIBLE

    game = Game()
    p1 = game.add_player("Alice")
    game.add_player("Bob")
    _setup_game_for_player(p1.id, game)

    obj = _spawn_on_battlefield(game, p1, INVASION_SUBMERSIBLE)
    abilities = obj.state.activated_abilities
    assert len(abilities) == 1
    assert abilities[0].mana_cost.generic == 3
    print("PASS: Invasion Submersible registers its animate-exhaust ({3})")


def test_rangers_refueler_animate_end_to_end():
    """Activate Rangers' Refueler's exhaust: should flip to 3/3 creature."""
    from src.cards.aetherdrift import RANGERS_REFUELER

    async def _run():
        game = Game()
        p1 = game.add_player("Alice")
        game.add_player("Bob")
        _setup_game_for_player(p1.id, game)

        obj = _spawn_on_battlefield(game, p1, RANGERS_REFUELER)
        _give_player_mana(p1, game.mana_system, generic=4)

        action = PlayerAction(
            type=ActionType.ACTIVATE_ABILITY,
            player_id=p1.id, source_id=obj.id, ability_id="activated:0",
        )
        events = await game.priority_system._handle_activate_ability(action)
        assert any(e.type == EventType.ACTIVATE for e in events)
        # Resolve the activated-ability closure off the stack.
        item = game.stack.items[-1]
        if item.resolve_fn:
            item.resolve_fn(item.chosen_targets, game.state)

        # Now a creature with base 3/3.
        assert CardType.CREATURE in get_types(obj, game.state)
        assert get_power(obj, game.state) == 3
        assert get_toughness(obj, game.state) == 3
        # Exhaust is now spent.
        assert obj.state.activated_abilities[0].once_per_game_used
        print("PASS: Rangers' Refueler animates to 3/3 and locks the exhaust")

    asyncio.get_event_loop().run_until_complete(_run())


if __name__ == "__main__":
    test_helper_registers_one_exhaust_ability()
    test_animation_flips_types_and_pt()
    test_animation_cleanup_reverts_at_eot()
    test_rangers_refueler_registers_animate_exhaust()
    test_rocketeer_boostbuggy_registers_animate_exhaust()
    test_marshals_pathcruiser_registers_animate_exhaust()
    test_invasion_submersible_registers_animate_exhaust()
    test_rangers_refueler_animate_end_to_end()
    print("\nAll vehicle-animate tests passed.")
