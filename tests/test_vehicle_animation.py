"""Tests for the GRANT_CREATURE_TYPE event + make_vehicle_animation_ability
helper.

GRANT_CREATURE_TYPE is the dedicated pipeline event that adds the CREATURE
card type to a non-creature artifact (e.g. a Vehicle) for some duration.
The handler installs a TRANSFORM-action QUERY-priority interceptor on
EventType.QUERY_TYPES so ``get_types(obj, state)`` reports CREATURE.

make_vehicle_animation_ability is the activated-ability helper that
composes the type grant with a P/T override and optional granted keywords.

Covers:
  - Pipeline handler: emitting GRANT_CREATURE_TYPE installs the QUERY
    interceptor; ``get_types`` reflects the new type.
  - Helper API: activation flips types and P/T, registers exactly one
    activated ability, and respects ``once_per_game``.
  - End-of-turn cleanup removes the interceptor and the P/T mod.
  - Mana cost is paid (mana pool is reduced by the activation cost).
  - All four wired vehicle cards (Rangers' Refueler, Rocketeer Boostbuggy,
    Marshals' Pathcruiser, Invasion Submersible) flip to creatures with
    the right P/T after activating their Exhaust ability.
  - Once-per-game (Exhaust): a second activation is rejected.
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
    get_power, get_toughness,
)
from src.engine.queries import get_types, has_ability
from src.engine.priority import ActionType, PlayerAction
from src.engine.turn import Phase
from src.cards.interceptor_helpers import make_vehicle_animation_ability
from src.cards.card_factories import make_artifact


# =============================================================================
# Helpers
# =============================================================================

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


def _mana_pool_total(player, mana_system):
    pool = mana_system.get_pool(player.id)
    if pool is None:
        return 0
    if hasattr(pool, 'total'):
        return pool.total()
    if hasattr(pool, 'values'):
        return sum(pool.values())
    return 0


# =============================================================================
# GRANT_CREATURE_TYPE pipeline handler
# =============================================================================

def test_grant_creature_type_handler_installs_interceptor():
    """Emitting GRANT_CREATURE_TYPE through the pipeline installs a QUERY
    interceptor that adds CREATURE to the type-set.

    CR 311.7 — the existing ARTIFACT type and the Vehicle subtype must
    BOTH remain alongside the new CREATURE type.
    """
    game = Game()
    p1 = game.add_player("Alice")
    game.add_player("Bob")
    _setup_game_for_player(p1.id, game)

    card = make_artifact(
        name="TestPlate",
        mana_cost="{2}",
        text="A plain artifact (no setup_interceptors).",
        subtypes={"Vehicle"},
    )
    obj = _spawn_on_battlefield(game, p1, card)

    types_before = get_types(obj, game.state)
    assert CardType.CREATURE not in types_before
    assert CardType.ARTIFACT in types_before

    # Emit the new event through the pipeline.
    game.emit(Event(
        type=EventType.GRANT_CREATURE_TYPE,
        payload={'object_id': obj.id, 'duration': 'end_of_turn'},
        source=obj.id, controller=p1.id,
    ))

    types_after = get_types(obj, game.state)
    assert CardType.CREATURE in types_after, (
        f"GRANT_CREATURE_TYPE should add CREATURE to {types_after}"
    )
    assert CardType.ARTIFACT in types_after, "ARTIFACT should remain"
    # CR 311.7: Vehicle subtype is preserved (the handler does not touch
    # subtypes; the QUERY interceptor only modifies the type-set).
    assert "Vehicle" in obj.characteristics.subtypes, (
        f"Vehicle subtype must remain (CR 311.7), got {obj.characteristics.subtypes}"
    )
    print("PASS: GRANT_CREATURE_TYPE handler installs the type-grant interceptor "
          "(CR 311.7: Vehicle subtype kept)")


def test_grant_creature_type_cleanup_at_eot():
    """End-of-turn cleanup sweeps the QUERY interceptor; types revert."""
    async def _run():
        game = Game()
        p1 = game.add_player("Alice")
        game.add_player("Bob")
        _setup_game_for_player(p1.id, game)

        card = make_artifact(
            name="TestPlate", mana_cost="{2}", text="...",
            subtypes={"Vehicle"},
        )
        obj = _spawn_on_battlefield(game, p1, card)

        game.emit(Event(
            type=EventType.GRANT_CREATURE_TYPE,
            payload={'object_id': obj.id, 'duration': 'end_of_turn'},
            source=obj.id, controller=p1.id,
        ))
        assert CardType.CREATURE in get_types(obj, game.state)

        # Run the cleanup step.
        tm = game.turn_manager
        tm.turn_state.active_player_id = p1.id
        await tm._do_cleanup_step()

        types_after = get_types(obj, game.state)
        assert CardType.CREATURE not in types_after, (
            f"CREATURE should be swept at EOT, got {types_after}"
        )
        assert CardType.ARTIFACT in types_after
        # CR 311.7: even after EOT cleanup the Vehicle subtype is intact.
        assert "Vehicle" in obj.characteristics.subtypes, (
            f"Vehicle subtype must persist post-EOT, got "
            f"{obj.characteristics.subtypes}"
        )
        print("PASS: GRANT_CREATURE_TYPE cleans up at end of turn (Vehicle kept)")

    asyncio.get_event_loop().run_until_complete(_run())


# =============================================================================
# make_vehicle_animation_ability helper
# =============================================================================

def _make_test_vehicle(name, cost, power, toughness, *, keywords=None,
                       once_per_game=True):
    keyword_list = list(keywords or [])

    def setup(obj, state):
        make_vehicle_animation_ability(
            obj, cost=cost, power=power, toughness=toughness,
            keywords=keyword_list, once_per_game=once_per_game,
        )
        return []

    return make_artifact(
        name=name, mana_cost="{2}",
        text=f"{cost}: This Vehicle becomes a {power}/{toughness} artifact "
             f"creature until end of turn.",
        subtypes={"Vehicle"},
        setup_interceptors=setup,
    )


def test_helper_registers_one_ability():
    game = Game()
    p1 = game.add_player("Alice")
    game.add_player("Bob")
    _setup_game_for_player(p1.id, game)

    obj = _spawn_on_battlefield(
        game, p1,
        _make_test_vehicle("VRig", "{4}", 4, 4),
    )
    abilities = obj.state.activated_abilities
    assert len(abilities) == 1
    assert abilities[0].mana_cost is not None
    assert abilities[0].mana_cost.generic == 4
    assert abilities[0].once_per_game is True
    assert abilities[0].is_exhaust is True
    print("PASS: helper registers exactly one ability with the right cost")


def test_helper_animation_flips_types_and_pt():
    """Activation flips the artifact to a 4/4 creature with vigilance."""
    async def _run():
        game = Game()
        p1 = game.add_player("Alice")
        game.add_player("Bob")
        _setup_game_for_player(p1.id, game)

        obj = _spawn_on_battlefield(
            game, p1,
            _make_test_vehicle("VRig", "{4}", 4, 4, keywords=["vigilance"]),
        )
        # Pre-state: artifact-only.
        types_before = get_types(obj, game.state)
        assert CardType.CREATURE not in types_before
        assert not has_ability(obj, "vigilance", game.state)

        _give_player_mana(p1, game.mana_system, generic=4)
        pool_before = _mana_pool_total(p1, game.mana_system)
        assert pool_before == 4

        action = PlayerAction(
            type=ActionType.ACTIVATE_ABILITY,
            player_id=p1.id, source_id=obj.id, ability_id="activated:0",
        )
        events = await game.priority_system._handle_activate_ability(action)
        assert any(e.type == EventType.ACTIVATE for e in events)

        # Mana cost was paid.
        pool_after = _mana_pool_total(p1, game.mana_system)
        assert pool_after == 0, f"Mana should be paid, pool={pool_after}"

        # Resolve the stack item.
        item = game.stack.items[-1]
        if item.resolve_fn:
            item.resolve_fn(item.chosen_targets, game.state)

        # Post-state: creature with 4/4 and vigilance.
        types_after = get_types(obj, game.state)
        assert CardType.CREATURE in types_after, (
            f"Should have CREATURE type, got {types_after}"
        )
        assert get_power(obj, game.state) == 4
        assert get_toughness(obj, game.state) == 4
        assert has_ability(obj, "vigilance", game.state)
        print("PASS: helper flips artifact to creature with target P/T and keyword")

    asyncio.get_event_loop().run_until_complete(_run())


def test_helper_eot_cleanup_reverts():
    """End-of-turn cleanup reverts the type and P/T."""
    async def _run():
        game = Game()
        p1 = game.add_player("Alice")
        game.add_player("Bob")
        _setup_game_for_player(p1.id, game)

        obj = _spawn_on_battlefield(
            game, p1,
            _make_test_vehicle("VRig", "{2}", 3, 3),
        )
        _give_player_mana(p1, game.mana_system, generic=2)

        action = PlayerAction(
            type=ActionType.ACTIVATE_ABILITY,
            player_id=p1.id, source_id=obj.id, ability_id="activated:0",
        )
        await game.priority_system._handle_activate_ability(action)
        item = game.stack.items[-1]
        if item.resolve_fn:
            item.resolve_fn(item.chosen_targets, game.state)

        assert CardType.CREATURE in get_types(obj, game.state)
        assert get_power(obj, game.state) == 3

        tm = game.turn_manager
        tm.turn_state.active_player_id = p1.id
        await tm._do_cleanup_step()

        types_after = get_types(obj, game.state)
        assert CardType.CREATURE not in types_after, (
            f"CREATURE should revert at EOT, got {types_after}"
        )
        # P/T mod should be cleared too.
        # (Vehicle's printed P/T is None for non-creature artifact.)
        assert get_power(obj, game.state) == 0
        print("PASS: animation reverts at end of turn (types + P/T)")

    asyncio.get_event_loop().run_until_complete(_run())


def test_helper_once_per_game_blocks_second_activation():
    """Two activations of the same ability are blocked by Exhaust contract."""
    async def _run():
        game = Game()
        p1 = game.add_player("Alice")
        game.add_player("Bob")
        _setup_game_for_player(p1.id, game)

        obj = _spawn_on_battlefield(
            game, p1,
            _make_test_vehicle("VRig", "{2}", 3, 3, once_per_game=True),
        )
        _give_player_mana(p1, game.mana_system, generic=4)

        action = PlayerAction(
            type=ActionType.ACTIVATE_ABILITY,
            player_id=p1.id, source_id=obj.id, ability_id="activated:0",
        )
        events = await game.priority_system._handle_activate_ability(action)
        assert any(e.type == EventType.ACTIVATE for e in events), \
            "First activation should succeed"
        # Resolve so once_per_game_used flips.
        item = game.stack.items[-1]
        if item.resolve_fn:
            item.resolve_fn(item.chosen_targets, game.state)

        assert obj.state.activated_abilities[0].once_per_game_used is True

        # Second activation: should be blocked.
        action2 = PlayerAction(
            type=ActionType.ACTIVATE_ABILITY,
            player_id=p1.id, source_id=obj.id, ability_id="activated:0",
        )
        events2 = await game.priority_system._handle_activate_ability(action2)
        # No ACTIVATE event means the second activation was rejected.
        activate_events = [e for e in events2 if e.type == EventType.ACTIVATE]
        assert not activate_events, (
            f"Second activation should be blocked by Exhaust, got {activate_events}"
        )
        print("PASS: once_per_game blocks the second activation")

    asyncio.get_event_loop().run_until_complete(_run())


# =============================================================================
# Wired Aetherdrift cards
# =============================================================================

def _activate_and_resolve(game, p1, obj):
    action = PlayerAction(
        type=ActionType.ACTIVATE_ABILITY,
        player_id=p1.id, source_id=obj.id, ability_id="activated:0",
    )
    return game.priority_system._handle_activate_ability(action)


def test_rangers_refueler_card_animates():
    """Rangers' Refueler ({4} Exhaust) should flip to 3/3 creature."""
    from src.cards.aetherdrift import RANGERS_REFUELER

    async def _run():
        game = Game()
        p1 = game.add_player("Alice")
        game.add_player("Bob")
        _setup_game_for_player(p1.id, game)

        obj = _spawn_on_battlefield(game, p1, RANGERS_REFUELER)
        assert CardType.CREATURE not in get_types(obj, game.state)
        _give_player_mana(p1, game.mana_system, generic=4)

        await _activate_and_resolve(game, p1, obj)
        item = game.stack.items[-1]
        if item.resolve_fn:
            item.resolve_fn(item.chosen_targets, game.state)

        assert CardType.CREATURE in get_types(obj, game.state)
        assert get_power(obj, game.state) == 3
        assert get_toughness(obj, game.state) == 3
        print("PASS: Rangers' Refueler animates to 3/3 creature")

    asyncio.get_event_loop().run_until_complete(_run())


def test_rocketeer_boostbuggy_card_animates():
    """Rocketeer Boostbuggy ({3} Exhaust) flips to 3/2 creature."""
    from src.cards.aetherdrift import ROCKETEER_BOOSTBUGGY

    async def _run():
        game = Game()
        p1 = game.add_player("Alice")
        game.add_player("Bob")
        _setup_game_for_player(p1.id, game)

        obj = _spawn_on_battlefield(game, p1, ROCKETEER_BOOSTBUGGY)
        assert CardType.CREATURE not in get_types(obj, game.state)
        _give_player_mana(p1, game.mana_system, generic=3)

        await _activate_and_resolve(game, p1, obj)
        item = game.stack.items[-1]
        if item.resolve_fn:
            item.resolve_fn(item.chosen_targets, game.state)

        assert CardType.CREATURE in get_types(obj, game.state)
        assert get_power(obj, game.state) == 3
        assert get_toughness(obj, game.state) == 2
        print("PASS: Rocketeer Boostbuggy animates to 3/2 creature")

    asyncio.get_event_loop().run_until_complete(_run())


def test_marshals_pathcruiser_card_animates():
    """Marshals' Pathcruiser ({W}{U}{B}{R}{G} Exhaust) flips to 4/4 creature."""
    from src.cards.aetherdrift import MARSHALS_PATHCRUISER

    async def _run():
        game = Game()
        p1 = game.add_player("Alice")
        game.add_player("Bob")
        _setup_game_for_player(p1.id, game)

        obj = _spawn_on_battlefield(game, p1, MARSHALS_PATHCRUISER)
        assert CardType.CREATURE not in get_types(obj, game.state)
        _give_player_mana(p1, game.mana_system,
                           white=1, blue=1, black=1, red=1, green=1)

        await _activate_and_resolve(game, p1, obj)
        item = game.stack.items[-1]
        if item.resolve_fn:
            item.resolve_fn(item.chosen_targets, game.state)

        assert CardType.CREATURE in get_types(obj, game.state)
        assert get_power(obj, game.state) == 4
        assert get_toughness(obj, game.state) == 4
        print("PASS: Marshals' Pathcruiser animates to 4/4 creature")

    asyncio.get_event_loop().run_until_complete(_run())


def test_invasion_submersible_card_animates():
    """Invasion Submersible ({3} Exhaust) flips to 3/3 creature."""
    from src.cards.avatar_tla import INVASION_SUBMERSIBLE

    async def _run():
        game = Game()
        p1 = game.add_player("Alice")
        game.add_player("Bob")
        _setup_game_for_player(p1.id, game)

        obj = _spawn_on_battlefield(game, p1, INVASION_SUBMERSIBLE)
        assert CardType.CREATURE not in get_types(obj, game.state)
        _give_player_mana(p1, game.mana_system, generic=3)

        await _activate_and_resolve(game, p1, obj)
        item = game.stack.items[-1]
        if item.resolve_fn:
            item.resolve_fn(item.chosen_targets, game.state)

        assert CardType.CREATURE in get_types(obj, game.state)
        assert get_power(obj, game.state) == 3
        assert get_toughness(obj, game.state) == 3
        print("PASS: Invasion Submersible animates to 3/3 creature")

    asyncio.get_event_loop().run_until_complete(_run())


# =============================================================================
# Run all
# =============================================================================

if __name__ == "__main__":
    test_grant_creature_type_handler_installs_interceptor()
    test_grant_creature_type_cleanup_at_eot()
    test_helper_registers_one_ability()
    test_helper_animation_flips_types_and_pt()
    test_helper_eot_cleanup_reverts()
    test_helper_once_per_game_blocks_second_activation()
    test_rangers_refueler_card_animates()
    test_rocketeer_boostbuggy_card_animates()
    test_marshals_pathcruiser_card_animates()
    test_invasion_submersible_card_animates()
    print("\nAll vehicle-animation tests passed.")
