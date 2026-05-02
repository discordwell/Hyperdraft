"""Adventure recursion — cast-from-exile after the Adventure half resolves.

Covers the engine path that lets a card whose Adventure activation paid
"Exile this card" be re-cast from exile as its main creature/enchantment
half. v1 (test_adventure.py) covered the Adventure dispatch; this suite
verifies that:

1. After the Adventure resolves, the source is in EXILE and has
   ``state.adventure_exile = True``.
2. ``priority.get_legal_actions`` surfaces a CAST_SPELL action for the
   exiled card to the owner.
3. Casting it pays the printed mana cost, the card moves to the
   battlefield as the main half, and ``adventure_exile`` is cleared.
4. After the main-side cast, no further cast-from-exile is offered for
   the same card.
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
    make_enchantment,
)
from src.cards.interceptor_helpers import make_adventure_setup
from src.engine.priority import ActionType, PlayerAction
from src.engine.turn import Phase
from src.engine.mana import ManaType


def _put_in_hand(game, player, card_def):
    return game.create_object(
        name=card_def.name,
        owner_id=player.id,
        zone=ZoneType.HAND,
        characteristics=card_def.characteristics,
        card_def=card_def,
    )


def _build_virtue_like_card():
    """Build a Virtue-of-Loyalty-like Adventure enchantment.

    Adventure side ({1}{W}, exile this): you gain 2 life.
    Main side ({3}{W}{W}): plain enchantment ETB (no triggers in this stub).
    """
    def adventure_effect(obj, state, targets):
        return [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': obj.controller, 'amount': 2},
            source=obj.id, controller=obj.controller,
        )]

    enchantment = make_enchantment(
        name="Test Virtue of Loyalty",
        mana_cost="{3}{W}{W}",
        colors={Color.WHITE},
        text="// Adventure — Test Adv {1}{W} (Instant)\nYou gain 2 life.",
    )
    enchantment.setup_in_hand = make_adventure_setup(
        adventure_cost="{1}{W}",
        effect_fn=adventure_effect,
        description="Adventure: gain 2 life",
    )
    return enchantment


def _setup_game_with_card():
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    game.turn_manager.turn_state.active_player_id = p1.id
    game.turn_manager.turn_state.phase = Phase.PRECOMBAT_MAIN

    card_def = _build_virtue_like_card()
    obj = _put_in_hand(game, p1, card_def)
    return game, p1, p2, obj


def _resolve_top_of_stack(game):
    """Resolve the top stack item via the StackManager and emit events."""
    events = game.stack.resolve_top()
    if game.priority_system and game.priority_system.pipeline:
        for ev in events or []:
            game.priority_system.pipeline.emit(ev)
    return events


async def _activate_adventure(game, p1, obj):
    # Provide {1}{W}.
    game.mana_system.produce_mana(p1.id, ManaType.COLORLESS, 1)
    game.mana_system.produce_mana(p1.id, ManaType.WHITE, 1)

    action = PlayerAction(
        type=ActionType.ACTIVATE_ABILITY,
        player_id=p1.id, source_id=obj.id, ability_id="activated:0",
    )
    events = await game.priority_system._handle_activate_ability(action)
    # Emit cost events through the pipeline so EXILE moves the card.
    if game.priority_system.pipeline:
        for ev in events:
            game.priority_system.pipeline.emit(ev)
    # Resolve the Adventure stack item now (the activated ability).
    _resolve_top_of_stack(game)


def test_adventure_resolution_marks_exile_flag():
    async def _run():
        game, p1, _, obj = _setup_game_with_card()
        await _activate_adventure(game, p1, obj)

        # Card should now be in EXILE with adventure_exile set.
        assert obj.zone == ZoneType.EXILE, f"expected EXILE, got {obj.zone}"
        assert obj.state.adventure_exile is True, "expected adventure_exile=True"
        # And actually present in the exile zone.
        exile_zone = game.state.zones.get('exile')
        assert exile_zone is not None and obj.id in exile_zone.objects
        print("PASS: adventure resolves -> card in exile w/ adventure_exile=True")

    asyncio.get_event_loop().run_until_complete(_run())


def test_legal_actions_surfaces_cast_from_exile():
    async def _run():
        game, p1, p2, obj = _setup_game_with_card()
        await _activate_adventure(game, p1, obj)

        # Now provide the printed cost ({3}{W}{W}).
        game.mana_system.produce_mana(p1.id, ManaType.COLORLESS, 3)
        game.mana_system.produce_mana(p1.id, ManaType.WHITE, 2)

        actions = game.priority_system.get_legal_actions(p1.id)
        cast_actions = [
            a for a in actions
            if a.type == ActionType.CAST_SPELL and a.card_id == obj.id
        ]
        assert cast_actions, (
            "expected a CAST_SPELL action for the exiled card; "
            f"got {[(a.type.name, a.description) for a in actions]}"
        )
        # The action must have the exile:adventure ability_id.
        assert any(a.ability_id == "exile:adventure" for a in cast_actions), (
            f"expected exile:adventure ability_id; got {[a.ability_id for a in cast_actions]}"
        )

        # Opponent should NOT see this action — it's the owner's.
        opp_actions = game.priority_system.get_legal_actions(p2.id)
        assert not any(
            a.type == ActionType.CAST_SPELL and a.card_id == obj.id
            for a in opp_actions
        ), "opponent should not be offered cast-from-exile of someone else's card"

        print("PASS: get_legal_actions surfaces CAST_SPELL from exile to owner")

    asyncio.get_event_loop().run_until_complete(_run())


def test_cast_from_exile_resolves_to_battlefield_and_clears_flag():
    async def _run():
        game, p1, _, obj = _setup_game_with_card()
        await _activate_adventure(game, p1, obj)

        # Provide printed cost.
        game.mana_system.produce_mana(p1.id, ManaType.COLORLESS, 3)
        game.mana_system.produce_mana(p1.id, ManaType.WHITE, 2)

        # Cast from exile.
        action = PlayerAction(
            type=ActionType.CAST_SPELL,
            player_id=p1.id, card_id=obj.id, ability_id="exile:adventure",
        )
        events = await game.priority_system._handle_cast_spell(action)
        # Emit any events (pay costs etc.) so that pipeline runs.
        if game.priority_system.pipeline:
            for ev in events:
                game.priority_system.pipeline.emit(ev)

        # adventure_exile flag must already be cleared (we clear at cast time).
        assert obj.state.adventure_exile is False, (
            "adventure_exile flag should be cleared when cast from exile"
        )

        # Card should be on the stack now.
        assert obj.zone == ZoneType.STACK, f"expected STACK, got {obj.zone}"

        # Resolve the top of the stack — the spell should ETB onto the battlefield.
        _resolve_top_of_stack(game)

        assert obj.zone == ZoneType.BATTLEFIELD, (
            f"expected BATTLEFIELD after resolve, got {obj.zone}"
        )
        battlefield = game.state.zones.get('battlefield')
        assert battlefield is not None and obj.id in battlefield.objects

        # Flag still clear.
        assert obj.state.adventure_exile is False
        print("PASS: cast from exile -> battlefield, flag cleared")

    asyncio.get_event_loop().run_until_complete(_run())


def test_cannot_cast_from_exile_twice():
    async def _run():
        game, p1, _, obj = _setup_game_with_card()
        await _activate_adventure(game, p1, obj)

        # Provide printed cost.
        game.mana_system.produce_mana(p1.id, ManaType.COLORLESS, 3)
        game.mana_system.produce_mana(p1.id, ManaType.WHITE, 2)

        # Cast from exile (first time).
        action = PlayerAction(
            type=ActionType.CAST_SPELL,
            player_id=p1.id, card_id=obj.id, ability_id="exile:adventure",
        )
        await game.priority_system._handle_cast_spell(action)
        _resolve_top_of_stack(game)

        # Now ask again: the card is on the battlefield, not in exile, and
        # certainly not flagged. Provide the cost again so a printed-cost cast
        # would otherwise be possible.
        game.mana_system.produce_mana(p1.id, ManaType.COLORLESS, 3)
        game.mana_system.produce_mana(p1.id, ManaType.WHITE, 2)

        actions = game.priority_system.get_legal_actions(p1.id)
        cast_from_exile = [
            a for a in actions
            if a.type == ActionType.CAST_SPELL
            and a.card_id == obj.id
            and a.ability_id == "exile:adventure"
        ]
        assert not cast_from_exile, (
            f"expected no further cast-from-exile actions; got {cast_from_exile}"
        )
        print("PASS: cast-from-exile not offered after main-side cast")

    asyncio.get_event_loop().run_until_complete(_run())


if __name__ == "__main__":
    test_adventure_resolution_marks_exile_flag()
    test_legal_actions_surfaces_cast_from_exile()
    test_cast_from_exile_resolves_to_battlefield_and_clears_flag()
    test_cannot_cast_from_exile_twice()
    print("\nAll adventure-recursion tests passed!")
