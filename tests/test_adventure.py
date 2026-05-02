"""Adventure mechanic — v1 (cast Adventure half from hand, exile self).

The card-from-exile recast path (cast as the main half after Adventure
resolves) is an engine gap and not tested here. v1 covers:
- The Adventure side registers as a hand-zone activated ability.
- Activating it pays the cost, exiles the source, and resolves the effect.
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
    make_creature,
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


def test_adventure_registers_in_hand():
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")

    def adventure_effect(obj, state, targets):
        return [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': obj.controller, 'amount': 2},
            source=obj.id, controller=obj.controller,
        )]

    creature_def = make_creature(
        name="Test Virtue", power=3, toughness=3, mana_cost="{2}{W}",
        colors={Color.WHITE}, subtypes={"Enchantment"},
        text="At the beginning of your end step, gain 1.\n// Adventure — Test Adv {1}{W} (Instant)\nYou gain 2 life.",
    )
    creature_def.setup_in_hand = make_adventure_setup(
        adventure_cost="{1}{W}",
        effect_fn=adventure_effect,
    )

    obj = _put_in_hand(game, p1, creature_def)
    abilities = getattr(obj.state, "activated_abilities", [])
    assert len(abilities) == 1
    assert abilities[0].cost_text == "{1}{W}, Exile this card"
    assert abilities[0].exile_self
    print("PASS: adventure registers in hand")


def test_adventure_dispatch_exiles_and_resolves():
    async def _run():
        game = Game()
        p1 = game.add_player("Alice")
        p2 = game.add_player("Bob")
        game.turn_manager.turn_state.active_player_id = p1.id
        game.turn_manager.turn_state.phase = Phase.PRECOMBAT_MAIN

        def adventure_effect(obj, state, targets):
            return [Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': obj.controller, 'amount': 2},
                source=obj.id, controller=obj.controller,
            )]

        creature_def = make_creature(
            name="Test Virtue", power=3, toughness=3, mana_cost="{2}{W}",
            colors={Color.WHITE}, subtypes={"Enchantment"},
            text="// Adventure — Test Adv {1}{W} (Instant)\nYou gain 2 life.",
        )
        creature_def.setup_in_hand = make_adventure_setup(
            adventure_cost="{1}{W}",
            effect_fn=adventure_effect,
        )

        obj = _put_in_hand(game, p1, creature_def)

        # Provide {1}{W}.
        game.mana_system.produce_mana(p1.id, ManaType.COLORLESS, 1)
        game.mana_system.produce_mana(p1.id, ManaType.WHITE, 1)

        # Activate the adventure ability.
        action = PlayerAction(
            type=ActionType.ACTIVATE_ABILITY,
            player_id=p1.id, source_id=obj.id, ability_id="activated:0",
        )
        events = await game.priority_system._handle_activate_ability(action)
        types = [e.type for e in events]
        # Cost should include EXILE for self.
        assert EventType.EXILE in types, f"expected EXILE in cost events, got {types}"
        assert EventType.ACTIVATE in types

        # Resolve stack item — should emit LIFE_CHANGE.
        item = game.stack.items[-1]
        resolved = item.resolve_fn(item.chosen_targets, game.state) if item.resolve_fn else []
        life_events = [e for e in resolved if e.type == EventType.LIFE_CHANGE]
        assert life_events, f"expected LIFE_CHANGE from resolve, got {[e.type for e in resolved]}"
        assert life_events[0].payload['amount'] == 2
        print("PASS: adventure dispatch exiles + resolves")

    asyncio.get_event_loop().run_until_complete(_run())


if __name__ == "__main__":
    test_adventure_registers_in_hand()
    test_adventure_dispatch_exiles_and_resolves()
    print("\nAll adventure tests passed!")
