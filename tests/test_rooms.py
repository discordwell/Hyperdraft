"""Phase 5D: Rooms / Doors framework tests."""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_HERE)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import asyncio

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color, CardDefinition,
    Characteristics,
)
from src.cards.interceptor_helpers import make_room_setup, is_door_unlocked
from src.engine.priority import ActionType, PlayerAction
from src.engine.turn import Phase


def _spawn_room(game, player, card_def):
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


def _make_test_room(door1_effect=None, door2_effect=None, door2_cost="{2}{W}"):
    def _door1_effect(obj, state):
        return door1_effect or []
    def _door2_effect(obj, state):
        return door2_effect or []
    setup = make_room_setup(
        door1_name="Door A",
        door1_unlock_effect=_door1_effect,
        door2_name="Door B",
        door2_cost=door2_cost,
        door2_unlock_effect=_door2_effect,
    )
    return CardDefinition(
        name="Test Room",
        mana_cost="{1}{W}",
        characteristics=Characteristics(
            types={CardType.ENCHANTMENT},
            subtypes={"Room"},
            colors={Color.WHITE},
            mana_cost="{1}{W}",
        ),
        text="Door A {1}{W}: When you unlock this door, do A.\n//\nDoor B {2}{W}: When you unlock this door, do B.",
        setup_interceptors=setup,
    )


def test_etb_unlocks_door1():
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")

    room_def = _make_test_room()
    room = _spawn_room(game, p1, room_def)

    assert is_door_unlocked(room, "Door A"), f"Door A should be unlocked, got {room.state.unlocked_doors}"
    assert not is_door_unlocked(room, "Door B"), "Door B should not yet be unlocked"
    print("PASS: ETB unlocks door 1")


def test_unlock_door1_fires_effect():
    """When Door A unlocks, its effect callback fires."""
    captured = []
    def door1_effect_fn(obj, state):
        captured.append(("door1", obj.id))
        return [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': obj.controller, 'amount': 3},
            source=obj.id, controller=obj.controller,
        )]

    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")

    setup = make_room_setup(
        door1_name="Door A",
        door1_unlock_effect=door1_effect_fn,
        door2_name="Door B",
        door2_cost="{2}{W}",
    )
    chars = Characteristics(
        types={CardType.ENCHANTMENT}, subtypes={"Room"},
        colors={Color.WHITE}, mana_cost="{1}{W}",
    )
    card_def = CardDefinition(
        name="Effect Room", mana_cost="{1}{W}",
        characteristics=chars, text="Door A test", setup_interceptors=setup,
    )
    room = _spawn_room(game, p1, card_def)

    # The callback should have been invoked with the room id, and life should
    # have gained.
    assert captured, "door1 effect callback should have been invoked"
    assert captured[0] == ("door1", room.id), f"unexpected capture: {captured}"
    assert is_door_unlocked(room, "Door A")
    print("PASS: unlock door 1 fires effect")


def test_door2_activated_ability_unlocks_and_fires_effect():
    """Activating the door-2 ability emits UNLOCK_DOOR for door 2 and fires its effect."""
    async def _run():
        captured = []
        def door2_effect_fn(obj, state):
            captured.append(("door2", obj.id))
            return [Event(
                type=EventType.DRAW,
                payload={'player': obj.controller, 'count': 1},
                source=obj.id, controller=obj.controller,
            )]

        game = Game()
        p1 = game.add_player("Alice")
        p2 = game.add_player("Bob")
        game.turn_manager.turn_state.active_player_id = p1.id
        game.turn_manager.turn_state.phase = Phase.PRECOMBAT_MAIN

        setup = make_room_setup(
            door1_name="Door A",
            door1_unlock_effect=lambda o, s: [],
            door2_name="Door B",
            door2_cost="{2}{W}",
            door2_unlock_effect=door2_effect_fn,
        )
        chars = Characteristics(
            types={CardType.ENCHANTMENT}, subtypes={"Room"},
            colors={Color.WHITE}, mana_cost="{1}{W}",
        )
        card_def = CardDefinition(
            name="Door2 Room", mana_cost="{1}{W}",
            characteristics=chars, text="...", setup_interceptors=setup,
        )
        room = _spawn_room(game, p1, card_def)
        room.state.summoning_sickness = False

        # Provide {2}{W}.
        from src.engine.mana import ManaType
        game.mana_system.produce_mana(p1.id, ManaType.COLORLESS, 2)
        game.mana_system.produce_mana(p1.id, ManaType.WHITE, 1)

        # Activate the door-2 ability.
        action = PlayerAction(
            type=ActionType.ACTIVATE_ABILITY,
            player_id=p1.id, source_id=room.id, ability_id="activated:0",
        )
        events = await game.priority_system._handle_activate_ability(action)
        # Resolve the stack item to fire UNLOCK_DOOR.
        item = game.stack.items[-1]
        resolved = item.resolve_fn(item.chosen_targets, game.state) if item.resolve_fn else []
        for ev in resolved:
            game.emit(ev)
        # Emit any follow-ups produced by the unlock handler.
        # captured should include door2.
        assert is_door_unlocked(room, "Door B"), f"Door B should be unlocked, got {room.state.unlocked_doors}"
        assert captured, f"door2 effect should have fired, captured={captured}"
        assert captured[0] == ("door2", room.id)
        print("PASS: door 2 activated ability unlocks + fires effect")

    asyncio.get_event_loop().run_until_complete(_run())


if __name__ == "__main__":
    test_etb_unlocks_door1()
    test_unlock_door1_fires_effect()
    test_door2_activated_ability_unlocks_and_fires_effect()
    print("\nAll Rooms tests passed!")
