"""Sweep 8: 'Add one mana of any color' fallback.

Activated mana abilities whose text uses "any color" or "in any combination
of colors" don't have literal {W/U/B/R/G/C} symbols. Without explicit color
selection (engine gap), we produce colorless as a pragmatic fallback so the
ability isn't a pure no-op.
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
    Characteristics,
)
from src.engine.priority import ActionType, PlayerAction
from src.engine.turn import Phase
from src.engine.mana import ManaType


def _spawn(game, player, card_def):
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


def test_add_one_mana_of_any_color_produces_colorless():
    async def _run():
        game = Game()
        p1 = game.add_player("Alice")
        p2 = game.add_player("Bob")
        game.turn_manager.turn_state.active_player_id = p1.id
        game.turn_manager.turn_state.phase = Phase.PRECOMBAT_MAIN

        # A mock land with "{T}: Add one mana of any color."
        land_def = CardDefinition(
            name="Mox of Many Colors", mana_cost="",
            characteristics=Characteristics(
                types={CardType.LAND}, subtypes={"Land"},
                colors=set(), mana_cost="",
            ),
            text="{T}: Add one mana of any color.",
        )

        land = _spawn(game, p1, land_def)
        land.state.summoning_sickness = False

        actions = game.priority_system.get_legal_actions(p1.id)
        mana_actions = [a for a in actions if a.ability_id and a.ability_id.startswith("mana:") and a.source_id == land.id]
        assert mana_actions, f"expected a mana action, got {[a.description for a in actions]}"

        action = PlayerAction(
            type=ActionType.ACTIVATE_ABILITY,
            player_id=p1.id, source_id=land.id,
            ability_id=mana_actions[0].ability_id,
        )
        events = await game.priority_system._handle_activate_ability(action)
        types = [e.type for e in events]
        assert EventType.TAP in types
        # Mana produced event with colorless fallback.
        mana_events = [e for e in events if e.type == EventType.MANA_PRODUCED]
        assert mana_events, f"expected MANA_PRODUCED, got {types}"
        assert mana_events[0].payload['color'] == ManaType.COLORLESS.value
        assert mana_events[0].payload['amount'] == 1

        # Check the pool actually has a colorless mana now.
        pool = game.mana_system.get_pool(p1.id)
        assert pool.get_count(ManaType.COLORLESS) >= 1, "pool should contain at least 1 colorless"
        print("PASS: add-one-mana-of-any-color produces colorless")

    asyncio.get_event_loop().run_until_complete(_run())


def test_add_two_in_any_combination_produces_two_colorless():
    async def _run():
        game = Game()
        p1 = game.add_player("Alice")
        p2 = game.add_player("Bob")
        game.turn_manager.turn_state.active_player_id = p1.id
        game.turn_manager.turn_state.phase = Phase.PRECOMBAT_MAIN

        land_def = CardDefinition(
            name="Big Mana", mana_cost="",
            characteristics=Characteristics(
                types={CardType.LAND}, subtypes={"Land"},
                colors=set(), mana_cost="",
            ),
            text="{T}: Add two mana in any combination of colors.",
        )
        land = _spawn(game, p1, land_def)
        land.state.summoning_sickness = False

        actions = game.priority_system.get_legal_actions(p1.id)
        mana_actions = [a for a in actions if a.ability_id and a.ability_id.startswith("mana:") and a.source_id == land.id]
        assert mana_actions
        action = PlayerAction(
            type=ActionType.ACTIVATE_ABILITY,
            player_id=p1.id, source_id=land.id,
            ability_id=mana_actions[0].ability_id,
        )
        events = await game.priority_system._handle_activate_ability(action)
        mana_events = [e for e in events if e.type == EventType.MANA_PRODUCED]
        assert mana_events, "expected MANA_PRODUCED"
        assert mana_events[0].payload['amount'] == 2, f"expected amount=2, got {mana_events[0].payload['amount']}"
        print("PASS: add-two-in-any-combination produces 2 colorless")

    asyncio.get_event_loop().run_until_complete(_run())


def test_explicit_colors_still_work():
    """Sanity: existing "{T}: Add {R}" path is unchanged."""
    async def _run():
        game = Game()
        p1 = game.add_player("Alice")
        p2 = game.add_player("Bob")
        game.turn_manager.turn_state.active_player_id = p1.id
        game.turn_manager.turn_state.phase = Phase.PRECOMBAT_MAIN

        land_def = CardDefinition(
            name="Mountain", mana_cost="",
            characteristics=Characteristics(
                types={CardType.LAND}, subtypes={"Mountain"},
                colors=set(), mana_cost="",
            ),
            text="{T}: Add {R}.",
        )
        land = _spawn(game, p1, land_def)
        land.state.summoning_sickness = False

        actions = game.priority_system.get_legal_actions(p1.id)
        mana_actions = [a for a in actions if a.ability_id and a.ability_id.startswith("mana:") and a.source_id == land.id]
        assert mana_actions
        action = PlayerAction(
            type=ActionType.ACTIVATE_ABILITY,
            player_id=p1.id, source_id=land.id,
            ability_id=mana_actions[0].ability_id,
        )
        events = await game.priority_system._handle_activate_ability(action)
        mana_events = [e for e in events if e.type == EventType.MANA_PRODUCED]
        assert mana_events
        assert mana_events[0].payload['color'] == ManaType.RED.value, f"expected RED, got {mana_events[0].payload['color']}"
        print("PASS: explicit color mana ability still works")

    asyncio.get_event_loop().run_until_complete(_run())


if __name__ == "__main__":
    test_add_one_mana_of_any_color_produces_colorless()
    test_add_two_in_any_combination_produces_two_colorless()
    test_explicit_colors_still_work()
    print("\nAll any-color mana tests passed!")
