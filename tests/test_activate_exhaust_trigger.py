"""Tests for activate-exhaust triggers (W2 engine extension).

Covers:
  - The ACTIVATE event payload now carries `is_exhaust` (True for Exhaust,
    False otherwise) and `x_value`.
  - make_activate_exhaust_trigger fires only on exhaust ability activations
    by the matching controller.
  - Non-exhaust activations do NOT fire the trigger.
  - The trigger respects ``while_in_zone`` (Afterburner Expert only fires
    while it's in the graveyard).
  - Wired cards Rangers' Refueler (battlefield half) and Afterburner Expert
    (graveyard half) actually behave as advertised.
"""

import os
import sys
import asyncio

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_HERE)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.engine import (
    Game, Event, EventType, ZoneType, Color, CardType,
    make_creature,
)
from src.engine.mana import ManaType
from src.engine.priority import ActionType, PlayerAction
from src.engine.turn import Phase
from src.cards.interceptor_helpers import (
    make_exhaust_ability,
    make_draw_ability,
    make_activate_exhaust_trigger,
)


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


def _spawn_in_graveyard(game, player, card_def):
    """Move a card directly into the graveyard so setup_in_graveyard fires."""
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
            'from_zone_type': ZoneType.HAND,
            'to_zone': f'graveyard_{player.id}',
            'to_zone_type': ZoneType.GRAVEYARD,
        },
    ))
    return obj


def _give_player_mana(player, mana_system, *, generic=0, red=0, green=0):
    for _ in range(generic):
        mana_system.produce_mana(player.id, ManaType.COLORLESS, 1)
    for _ in range(red):
        mana_system.produce_mana(player.id, ManaType.RED, 1)
    for _ in range(green):
        mana_system.produce_mana(player.id, ManaType.GREEN, 1)


def _make_exhaust_dummy(name, cost):
    """A creature with an Exhaust ability of cost ``cost``."""

    def setup(obj, state):
        def _effect(o, st, t):
            return [Event(
                type=EventType.COUNTER_ADDED,
                payload={'object_id': o.id, 'counter_type': '+1/+1', 'amount': 1},
                source=o.id, controller=o.controller,
            )]
        make_exhaust_ability(
            obj, cost=cost, effect_fn=_effect,
            description=f"{cost}: Test counter.",
        )
        return []

    return make_creature(
        name=name, power=1, toughness=1, mana_cost="{1}",
        colors=set(), subtypes={"Construct"},
        text=f"Exhaust — {cost}: counter test.",
        setup_interceptors=setup,
    )


def _make_non_exhaust_dummy(name, cost):
    """A creature with a regular (non-Exhaust) activated ability."""

    def setup(obj, state):
        make_draw_ability(obj, cost, count=1, description=f"{cost}: Draw a card.")
        return []

    return make_creature(
        name=name, power=1, toughness=1, mana_cost="{1}",
        colors=set(), subtypes={"Construct"},
        text=f"{cost}: Draw a card.",
        setup_interceptors=setup,
    )


# ---------------------------------------------------------------------------
# Direct ACTIVATE-event payload checks
# ---------------------------------------------------------------------------


def test_activate_event_carries_is_exhaust_for_exhaust_ability():
    """Activating an Exhaust ability emits ACTIVATE with is_exhaust=True."""
    async def _run():
        game = Game()
        p1 = game.add_player("Alice")
        game.add_player("Bob")
        _setup_game_for_player(p1.id, game)

        target = _spawn_on_battlefield(game, p1, _make_exhaust_dummy("E", "{1}"))
        target.state.summoning_sickness = False
        _give_player_mana(p1, game.mana_system, generic=1)

        action = PlayerAction(
            type=ActionType.ACTIVATE_ABILITY,
            player_id=p1.id, source_id=target.id,
            ability_id="activated:0",
        )
        events = await game.priority_system._handle_activate_ability(action)
        activate = [e for e in events if e.type == EventType.ACTIVATE]
        assert activate, f"expected ACTIVATE event; got {[e.type for e in events]}"
        assert activate[0].payload.get('is_exhaust') is True, \
            f"is_exhaust should be True for Exhaust ability: {activate[0].payload}"
        print("PASS: ACTIVATE payload carries is_exhaust=True for Exhaust")

    asyncio.get_event_loop().run_until_complete(_run())


def test_activate_event_is_exhaust_false_for_non_exhaust():
    """Activating a regular activated ability emits is_exhaust=False."""
    async def _run():
        game = Game()
        p1 = game.add_player("Alice")
        game.add_player("Bob")
        _setup_game_for_player(p1.id, game)

        target = _spawn_on_battlefield(game, p1, _make_non_exhaust_dummy("D", "{T}"))
        target.state.summoning_sickness = False

        action = PlayerAction(
            type=ActionType.ACTIVATE_ABILITY,
            player_id=p1.id, source_id=target.id,
            ability_id="activated:0",
        )
        events = await game.priority_system._handle_activate_ability(action)
        activate = [e for e in events if e.type == EventType.ACTIVATE]
        assert activate
        assert activate[0].payload.get('is_exhaust') is False, \
            f"is_exhaust should be False for non-Exhaust: {activate[0].payload}"
        print("PASS: ACTIVATE payload reports is_exhaust=False for non-Exhaust")

    asyncio.get_event_loop().run_until_complete(_run())


# ---------------------------------------------------------------------------
# Rangers' Refueler-style: battlefield trigger reacting to exhaust activations
# ---------------------------------------------------------------------------


def test_refueler_proxy_draws_card_on_exhaust_activation():
    """A 'whenever you activate an exhaust ability, draw a card' permanent
    fires when an exhaust ability is activated."""
    async def _run():
        game = Game()
        p1 = game.add_player("Alice")
        game.add_player("Bob")
        _setup_game_for_player(p1.id, game)

        # Refueler proxy.
        def setup(obj, state):
            def _draw(event, st):
                return [Event(
                    type=EventType.DRAW,
                    payload={'player': obj.controller, 'count': 1},
                    source=obj.id, controller=obj.controller,
                )]
            return [make_activate_exhaust_trigger(obj, _draw, controller_only=True)]

        refueler = make_creature(
            name="Refueler Proxy",
            power=0, toughness=2, mana_cost="{1}",
            colors=set(), subtypes={"Construct"},
            text="Whenever you activate an exhaust ability, draw a card.",
            setup_interceptors=setup,
        )
        _spawn_on_battlefield(game, p1, refueler)

        # Pre-load the library so DRAW has something to deliver.
        for i in range(5):
            game.create_object(
                name=f"Card{i}", owner_id=p1.id, zone=ZoneType.LIBRARY,
                characteristics=None, card_def=None,
            )

        before_hand = len(game.state.zones[f'hand_{p1.id}'].objects)

        # Activate an Exhaust ability on a different permanent.
        exh_obj = _spawn_on_battlefield(game, p1, _make_exhaust_dummy("Exh", "{1}"))
        exh_obj.state.summoning_sickness = False
        _give_player_mana(p1, game.mana_system, generic=1)

        action = PlayerAction(
            type=ActionType.ACTIVATE_ABILITY,
            player_id=p1.id, source_id=exh_obj.id,
            ability_id="activated:0",
        )
        events = await game.priority_system._handle_activate_ability(action)
        # Emit events through the pipeline so the REACT trigger fires.
        for ev in events:
            game.pipeline.emit(ev)

        after_hand = len(game.state.zones[f'hand_{p1.id}'].objects)
        assert after_hand > before_hand, \
            f"refueler should draw a card (hand: {before_hand} -> {after_hand})"
        print("PASS: refueler-proxy draws on exhaust activation")

    asyncio.get_event_loop().run_until_complete(_run())


def test_refueler_proxy_does_not_fire_on_non_exhaust_activation():
    """The trigger doesn't fire when a *non*-exhaust activated ability is used."""
    async def _run():
        game = Game()
        p1 = game.add_player("Alice")
        game.add_player("Bob")
        _setup_game_for_player(p1.id, game)

        def setup(obj, state):
            def _draw(event, st):
                return [Event(
                    type=EventType.DRAW,
                    payload={'player': obj.controller, 'count': 1},
                    source=obj.id, controller=obj.controller,
                )]
            return [make_activate_exhaust_trigger(obj, _draw)]

        refueler = make_creature(
            name="Refueler Proxy",
            power=0, toughness=2, mana_cost="{1}",
            colors=set(), subtypes={"Construct"},
            text="...",
            setup_interceptors=setup,
        )
        _spawn_on_battlefield(game, p1, refueler)
        for i in range(5):
            game.create_object(
                name=f"Card{i}", owner_id=p1.id, zone=ZoneType.LIBRARY,
                characteristics=None, card_def=None,
            )
        before_hand = len(game.state.zones[f'hand_{p1.id}'].objects)

        non_exh = _spawn_on_battlefield(game, p1, _make_non_exhaust_dummy("D", "{T}"))
        non_exh.state.summoning_sickness = False
        action = PlayerAction(
            type=ActionType.ACTIVATE_ABILITY,
            player_id=p1.id, source_id=non_exh.id,
            ability_id="activated:0",
        )
        events = await game.priority_system._handle_activate_ability(action)
        for ev in events:
            game.pipeline.emit(ev)

        # The non-exhaust ability draws a card on resolve, but the refueler's
        # trigger should NOT fire (no extra draw on activation itself).
        # We check by looking only at the immediate hand size: the activation
        # above pushed a stack item; resolving it would draw 1, but since we
        # didn't resolve, the refueler is the only path that *could* have
        # drawn. So hand size must be unchanged.
        after_hand = len(game.state.zones[f'hand_{p1.id}'].objects)
        assert after_hand == before_hand, \
            f"refueler should NOT fire on non-exhaust activation; hand: {before_hand} -> {after_hand}"
        print("PASS: refueler does not fire on non-exhaust activation")

    asyncio.get_event_loop().run_until_complete(_run())


def test_wired_rangers_refueler_draws_on_exhaust():
    """Wired Rangers' Refueler draws a card when its controller activates an
    exhaust ability on another permanent."""
    async def _run():
        from src.cards.aetherdrift import RANGERS_REFUELER

        game = Game()
        p1 = game.add_player("Alice")
        game.add_player("Bob")
        _setup_game_for_player(p1.id, game)

        _spawn_on_battlefield(game, p1, RANGERS_REFUELER)
        # Library content for DRAW.
        for i in range(5):
            game.create_object(
                name=f"Card{i}", owner_id=p1.id, zone=ZoneType.LIBRARY,
                characteristics=None, card_def=None,
            )

        before_hand = len(game.state.zones[f'hand_{p1.id}'].objects)

        target = _spawn_on_battlefield(game, p1, _make_exhaust_dummy("E", "{1}"))
        target.state.summoning_sickness = False
        _give_player_mana(p1, game.mana_system, generic=1)

        action = PlayerAction(
            type=ActionType.ACTIVATE_ABILITY,
            player_id=p1.id, source_id=target.id,
            ability_id="activated:0",
        )
        events = await game.priority_system._handle_activate_ability(action)
        for ev in events:
            game.pipeline.emit(ev)

        after_hand = len(game.state.zones[f'hand_{p1.id}'].objects)
        assert after_hand > before_hand, \
            f"Rangers' Refueler should draw on exhaust activation; hand {before_hand} -> {after_hand}"
        print("PASS: wired Rangers' Refueler draws on exhaust activation")

    asyncio.get_event_loop().run_until_complete(_run())


# ---------------------------------------------------------------------------
# Afterburner Expert (graveyard half) — reanimate on exhaust activation
# ---------------------------------------------------------------------------


def test_wired_afterburner_returns_from_graveyard_on_exhaust():
    """Wired Afterburner Expert in graveyard returns to battlefield when its
    controller activates an exhaust ability."""
    async def _run():
        from src.cards.aetherdrift import AFTERBURNER_EXPERT

        game = Game()
        p1 = game.add_player("Alice")
        game.add_player("Bob")
        _setup_game_for_player(p1.id, game)

        # Spawn Afterburner directly into the graveyard.
        afterburner = _spawn_in_graveyard(game, p1, AFTERBURNER_EXPERT)
        assert afterburner.zone == ZoneType.GRAVEYARD, \
            "Afterburner should start in graveyard"

        # Spawn a separate permanent with an exhaust ability.
        exh = _spawn_on_battlefield(game, p1, _make_exhaust_dummy("Exh", "{1}"))
        exh.state.summoning_sickness = False
        _give_player_mana(p1, game.mana_system, generic=1)

        # Activate the exhaust ability — Afterburner's graveyard trigger
        # should fire and return the card to battlefield.
        action = PlayerAction(
            type=ActionType.ACTIVATE_ABILITY,
            player_id=p1.id, source_id=exh.id,
            ability_id="activated:0",
        )
        events = await game.priority_system._handle_activate_ability(action)
        for ev in events:
            game.pipeline.emit(ev)

        # Check Afterburner's zone after the trigger has been processed.
        # The pipeline's REACT phase queues new events synchronously.
        current = game.state.objects.get(afterburner.id)
        assert current is not None, "Afterburner object should still exist"
        assert current.zone == ZoneType.BATTLEFIELD, \
            f"Afterburner should have returned to battlefield; got zone={current.zone}"
        print("PASS: wired Afterburner Expert returns from graveyard on exhaust")

    asyncio.get_event_loop().run_until_complete(_run())


def test_afterburner_does_not_fire_when_on_battlefield():
    """If Afterburner is on the battlefield, the GY-only trigger doesn't fire."""
    async def _run():
        from src.cards.aetherdrift import AFTERBURNER_EXPERT

        game = Game()
        p1 = game.add_player("Alice")
        game.add_player("Bob")
        _setup_game_for_player(p1.id, game)

        # Put Afterburner directly on the battlefield.
        afterburner = _spawn_on_battlefield(game, p1, AFTERBURNER_EXPERT)
        afterburner.state.summoning_sickness = False
        starting_zone = afterburner.zone

        # Different permanent with an exhaust ability.
        exh = _spawn_on_battlefield(game, p1, _make_exhaust_dummy("Exh", "{1}"))
        exh.state.summoning_sickness = False
        _give_player_mana(p1, game.mana_system, generic=1)

        action = PlayerAction(
            type=ActionType.ACTIVATE_ABILITY,
            player_id=p1.id, source_id=exh.id,
            ability_id="activated:0",
        )
        events = await game.priority_system._handle_activate_ability(action)
        for ev in events:
            game.pipeline.emit(ev)

        # No state change for Afterburner; the GY trigger is gated by zone.
        assert game.state.objects[afterburner.id].zone == starting_zone, \
            "Afterburner already on battlefield should not move"
        print("PASS: Afterburner GY trigger silent when not in graveyard")

    asyncio.get_event_loop().run_until_complete(_run())


if __name__ == "__main__":
    test_activate_event_carries_is_exhaust_for_exhaust_ability()
    test_activate_event_is_exhaust_false_for_non_exhaust()
    test_refueler_proxy_draws_card_on_exhaust_activation()
    test_refueler_proxy_does_not_fire_on_non_exhaust_activation()
    test_wired_rangers_refueler_draws_on_exhaust()
    test_wired_afterburner_returns_from_graveyard_on_exhaust()
    test_afterburner_does_not_fire_when_on_battlefield()
    print("\nAll activate-exhaust trigger tests passed.")
