"""Phase 5A: Suspect mechanic tests.

A suspected creature gains menace and can't block. We test:
- The suspect_creature helper emits the right events.
- After emission, the creature has menace and the cant_block keyword.
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_HERE)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color,
    make_creature, has_ability,
)
from src.cards.interceptor_helpers import suspect_creature


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


def test_suspect_grants_menace_and_cant_block():
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")

    # A vanilla 2/2 creature.
    bear_def = make_creature(
        name="Bear", power=2, toughness=2, mana_cost="{1}{G}",
        colors={Color.GREEN}, subtypes={"Bear"}, text="",
    )
    bear = _spawn(game, p1, bear_def)

    # Sanity: not menacing, not can't-block before suspect.
    assert not has_ability(bear, "menace", game.state)
    assert not has_ability(bear, "cant_block", game.state)

    # Emit suspect events.
    for ev in suspect_creature(bear.id, source_id="spell", controller=p1.id):
        game.emit(ev)

    assert has_ability(bear, "menace", game.state), "suspected creature should have menace"
    assert has_ability(bear, "cant_block", game.state), "suspected creature should have cant_block"
    print("PASS: suspect grants menace and cant_block")


def test_suspect_sets_state_flag():
    """suspect_creature(state=...) should also set obj.state.suspected = True."""
    game = Game()
    p1 = game.add_player("Alice")
    bear_def = make_creature(
        name="Bear", power=2, toughness=2, mana_cost="{1}{G}",
        colors={Color.GREEN}, subtypes={"Bear"}, text="",
    )
    bear = _spawn(game, p1, bear_def)
    assert not bear.state.suspected

    for ev in suspect_creature(bear.id, "spell", p1.id, state=game.state):
        game.emit(ev)

    assert bear.state.suspected, "obj.state.suspected should be True after suspect_creature"
    print("PASS: suspect sets state flag")


def test_repeat_offender_branches_on_suspect():
    """Repeat Offender: first activation suspects self; second adds +1/+1 counter."""
    import asyncio
    from src.engine.priority import ActionType, PlayerAction
    from src.engine.turn import Phase
    from src.cards.murders_karlov_manor import REPEAT_OFFENDER

    async def _run():
        game = Game()
        p1 = game.add_player("Alice")
        p2 = game.add_player("Bob")
        game.turn_manager.turn_state.active_player_id = p1.id
        game.turn_manager.turn_state.phase = Phase.PRECOMBAT_MAIN

        ro = _spawn(game, p1, REPEAT_OFFENDER)
        ro.state.summoning_sickness = False

        # Provide {2}{B}.
        from src.engine.mana import ManaType
        game.mana_system.produce_mana(p1.id, ManaType.COLORLESS, 2)
        game.mana_system.produce_mana(p1.id, ManaType.BLACK, 1)

        # First activation: not yet suspected → should suspect self.
        action = PlayerAction(
            type=ActionType.ACTIVATE_ABILITY,
            player_id=p1.id, source_id=ro.id, ability_id="activated:0",
        )
        await game.priority_system._handle_activate_ability(action)
        item = game.stack.items[-1]
        events = item.resolve_fn(item.chosen_targets, game.state) if item.resolve_fn else []
        types = [e.type for e in events]
        # Suspect emits GRANT_KEYWORD + CANT_BLOCK.
        assert EventType.GRANT_KEYWORD in types and EventType.CANT_BLOCK in types, f"first activation should suspect, got {types}"
        for e in events:
            game.emit(e)
        assert ro.state.suspected, "Repeat Offender should be suspected after first activation"
        print("PASS: repeat offender branches on suspect (first activation)")

    asyncio.get_event_loop().run_until_complete(_run())


if __name__ == "__main__":
    test_suspect_grants_menace_and_cant_block()
    test_suspect_sets_state_flag()
    test_repeat_offender_branches_on_suspect()
    print("\nAll Suspect tests passed!")
