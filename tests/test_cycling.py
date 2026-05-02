"""Cycling: ``{cost}, Discard this card: Draw a card.``

Tests:
- A card in HAND with `setup_in_hand=make_cycling_setup(cost)` registers a
  cycling activated ability.
- Priority's get_legal_actions surfaces it for the card's owner.
- Activating it: pays mana, discards the source, draws a card.
"""
import os
import sys
import asyncio

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_HERE)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color, CardDefinition,
    Characteristics, make_creature,
)
from src.cards.interceptor_helpers import make_cycling_ability, make_cycling_setup
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


def test_cycling_registers_activated_ability_in_hand():
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")

    cycler_def = make_creature(
        name="Cycler", power=3, toughness=3, mana_cost="{4}",
        colors=set(), subtypes={"Beast"},
        text="Cycling {2} ({2}, Discard this card: Draw a card.)",
    )
    cycler_def.setup_in_hand = make_cycling_setup("{2}")

    obj = _put_in_hand(game, p1, cycler_def)
    abilities = getattr(obj.state, "activated_abilities", [])
    assert len(abilities) == 1, f"expected 1 cycling ability, got {len(abilities)}"
    assert abilities[0].cost_text == "{2}, Discard this card"
    assert abilities[0].discard_self
    print("PASS: cycling ability registers via setup_in_hand")


def test_cycling_surfaces_in_legal_actions():
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    game.turn_manager.turn_state.active_player_id = p1.id
    game.turn_manager.turn_state.phase = Phase.PRECOMBAT_MAIN

    cycler_def = make_creature(
        name="Cycler", power=3, toughness=3, mana_cost="{4}",
        colors=set(), subtypes={"Beast"},
        text="Cycling {2} ({2}, Discard this card: Draw a card.)",
    )
    cycler_def.setup_in_hand = make_cycling_setup("{2}")
    obj = _put_in_hand(game, p1, cycler_def)

    # Provide enough mana to pay {2}.
    for _ in range(2):
        game.mana_system.produce_mana(p1.id, ManaType.COLORLESS, 1)

    actions = game.priority_system.get_legal_actions(p1.id)
    cycling_actions = [
        a for a in actions
        if a.source_id == obj.id and a.ability_id and a.ability_id.startswith("activated:")
    ]
    assert cycling_actions, f"expected cycling action, got {[a.description for a in actions[:5]]}"
    print("PASS: cycling surfaces in legal actions")


def test_cycling_dispatch_pays_cost_and_draws():
    async def _run():
        game = Game()
        p1 = game.add_player("Alice")
        p2 = game.add_player("Bob")
        game.turn_manager.turn_state.active_player_id = p1.id
        game.turn_manager.turn_state.phase = Phase.PRECOMBAT_MAIN

        cycler_def = make_creature(
            name="Cycler", power=3, toughness=3, mana_cost="{4}",
            colors=set(), subtypes={"Beast"},
            text="Cycling {2} ({2}, Discard this card: Draw a card.)",
        )
        cycler_def.setup_in_hand = make_cycling_setup("{2}")
        obj = _put_in_hand(game, p1, cycler_def)

        for _ in range(2):
            game.mana_system.produce_mana(p1.id, ManaType.COLORLESS, 1)

        action = PlayerAction(
            type=ActionType.ACTIVATE_ABILITY,
            player_id=p1.id, source_id=obj.id, ability_id="activated:0",
        )
        events = await game.priority_system._handle_activate_ability(action)
        types = [e.type for e in events]
        # Discard cost emitted, ACTIVATE marker emitted.
        assert EventType.DISCARD in types, f"expected DISCARD as cost, got {types}"
        assert EventType.ACTIVATE in types

        # Stack item should have a resolve_fn that emits DRAW.
        item = game.stack.items[-1]
        resolved = item.resolve_fn(item.chosen_targets, game.state) if item.resolve_fn else []
        draw_events = [e for e in resolved if e.type == EventType.DRAW]
        assert draw_events, f"expected DRAW from resolve, got {[e.type for e in resolved]}"
        assert draw_events[0].payload['player'] == p1.id
        print("PASS: cycling dispatch pays cost + emits DRAW")

    asyncio.get_event_loop().run_until_complete(_run())


if __name__ == "__main__":
    test_cycling_registers_activated_ability_in_hand()
    test_cycling_surfaces_in_legal_actions()
    test_cycling_dispatch_pays_cost_and_draws()
    print("\nAll cycling tests passed!")
