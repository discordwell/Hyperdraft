import asyncio
import sys

sys.path.insert(0, '/Users/discordwell/Projects/Hyperdraft')

from src.engine import (
    Game, ZoneType, CardType, Color,
    make_instant, make_land,
    PlayerAction, ActionType,
)


def _make_test_flashback_instant():
    # Printed mana cost is intentionally cheaper than flashback to verify we
    # validate/persist the alternate cost.
    def noop_resolve(targets, state):
        return []

    return make_instant(
        name="Test Flashback Instant",
        mana_cost="{1}{U}",
        colors={Color.BLUE},
        text="Flashback {3}{U} (You may cast this card from your graveyard for its flashback cost. Then exile it.)",
        resolve=noop_resolve,
    )


def test_flashback_legal_actions_use_flashback_cost_for_mana_check():
    game = Game()
    p1 = game.add_player("P1")
    game.add_player("P2")

    flashback = _make_test_flashback_instant()

    # Put the spell into P1's graveyard.
    gy_card = game.create_object(
        name=flashback.name,
        owner_id=p1.id,
        zone=ZoneType.GRAVEYARD,
        characteristics=flashback.characteristics,
        card_def=flashback,
    )

    # Only two Islands: can pay {1}{U} but NOT {3}{U}.
    island_def = make_land("Island", subtypes={"Island"})
    for _ in range(2):
        game.create_object(
            name="Island",
            owner_id=p1.id,
            zone=ZoneType.BATTLEFIELD,
            characteristics=island_def.characteristics,
            card_def=island_def,
        )

    legal = game.priority_system.get_legal_actions(p1.id)
    assert not any(a.type == ActionType.CAST_SPELL and a.card_id == gy_card.id for a in legal)

    # With four Islands, {3}{U} becomes payable.
    for _ in range(2):
        game.create_object(
            name="Island",
            owner_id=p1.id,
            zone=ZoneType.BATTLEFIELD,
            characteristics=island_def.characteristics,
            card_def=island_def,
        )

    legal = game.priority_system.get_legal_actions(p1.id)
    assert any(
        a.type == ActionType.CAST_SPELL and a.card_id == gy_card.id and "flashback" in a.description.lower()
        for a in legal
    )


def test_flashback_cast_from_graveyard_exiles_on_resolution():
    game = Game()
    p1 = game.add_player("P1")
    game.add_player("P2")

    flashback = _make_test_flashback_instant()
    gy_card = game.create_object(
        name=flashback.name,
        owner_id=p1.id,
        zone=ZoneType.GRAVEYARD,
        characteristics=flashback.characteristics,
        card_def=flashback,
    )

    # Make {3}{U} payable.
    island_def = make_land("Island", subtypes={"Island"})
    for _ in range(4):
        game.create_object(
            name="Island",
            owner_id=p1.id,
            zone=ZoneType.BATTLEFIELD,
            characteristics=island_def.characteristics,
            card_def=island_def,
        )

    action = PlayerAction(type=ActionType.CAST_SPELL, player_id=p1.id, card_id=gy_card.id)
    asyncio.run(game.priority_system._handle_cast_spell(action))
    assert gy_card.zone == ZoneType.STACK

    # Resolve and apply post-resolution zone changes.
    for e in game.resolve_stack():
        game.emit(e)

    assert gy_card.zone == ZoneType.EXILE
    assert gy_card.id in game.state.zones["exile"].objects
    assert gy_card.id not in game.state.zones[f"graveyard_{p1.id}"].objects


def test_flashback_exiles_if_countered():
    game = Game()
    p1 = game.add_player("P1")
    game.add_player("P2")

    flashback = _make_test_flashback_instant()
    gy_card = game.create_object(
        name=flashback.name,
        owner_id=p1.id,
        zone=ZoneType.GRAVEYARD,
        characteristics=flashback.characteristics,
        card_def=flashback,
    )

    island_def = make_land("Island", subtypes={"Island"})
    for _ in range(4):
        game.create_object(
            name="Island",
            owner_id=p1.id,
            zone=ZoneType.BATTLEFIELD,
            characteristics=island_def.characteristics,
            card_def=island_def,
        )

    action = PlayerAction(type=ActionType.CAST_SPELL, player_id=p1.id, card_id=gy_card.id)
    asyncio.run(game.priority_system._handle_cast_spell(action))
    item = game.stack.top()
    assert item is not None

    for e in game.stack.counter(item.id, reason="countered"):
        game.emit(e)

    assert gy_card.zone == ZoneType.EXILE
    assert gy_card.id in game.state.zones["exile"].objects
