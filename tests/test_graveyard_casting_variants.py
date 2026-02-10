import asyncio
import sys

sys.path.insert(0, '/Users/discordwell/Projects/Hyperdraft')

from src.engine import (
    Game, Event, EventType, ZoneType, Color,
    make_instant, make_land,
    PlayerAction, ActionType,
)


def _make_test_harmonize_instant():
    def noop_resolve(targets, state):
        return []

    return make_instant(
        name="Test Harmonize Instant",
        mana_cost="{1}{U}",
        colors={Color.BLUE},
        text="Harmonize {3}{U} (You may cast this card from your graveyard for its harmonize cost. Then exile this spell.)",
        resolve=noop_resolve,
    )


def _make_test_mayhem_instant():
    def noop_resolve(targets, state):
        return []

    return make_instant(
        name="Test Mayhem Instant",
        mana_cost="{2}{R}",
        colors={Color.RED},
        text="Mayhem {R} (You may cast this card from your graveyard for {R} if you discarded it this turn. Timing rules still apply.)",
        resolve=noop_resolve,
    )


def test_harmonize_legal_actions_use_harmonize_cost_for_mana_check():
    game = Game()
    p1 = game.add_player("P1")
    game.add_player("P2")

    harmonize = _make_test_harmonize_instant()

    gy_card = game.create_object(
        name=harmonize.name,
        owner_id=p1.id,
        zone=ZoneType.GRAVEYARD,
        characteristics=harmonize.characteristics,
        card_def=harmonize,
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
        a.type == ActionType.CAST_SPELL and a.card_id == gy_card.id and "harmonize" in a.description.lower()
        for a in legal
    )


def test_harmonize_cast_from_graveyard_exiles_on_resolution():
    game = Game()
    p1 = game.add_player("P1")
    game.add_player("P2")

    harmonize = _make_test_harmonize_instant()
    gy_card = game.create_object(
        name=harmonize.name,
        owner_id=p1.id,
        zone=ZoneType.GRAVEYARD,
        characteristics=harmonize.characteristics,
        card_def=harmonize,
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
    assert gy_card.zone == ZoneType.STACK

    for e in game.resolve_stack():
        game.emit(e)

    assert gy_card.zone == ZoneType.EXILE
    assert gy_card.id in game.state.zones["exile"].objects


def test_mayhem_requires_discard_this_turn():
    game = Game()
    p1 = game.add_player("P1")
    game.add_player("P2")

    mayhem = _make_test_mayhem_instant()

    # Put directly in graveyard without discarding: should NOT be castable.
    gy_card = game.create_object(
        name=mayhem.name,
        owner_id=p1.id,
        zone=ZoneType.GRAVEYARD,
        characteristics=mayhem.characteristics,
        card_def=mayhem,
    )

    mountain_def = make_land("Mountain", subtypes={"Mountain"})
    game.create_object(
        name="Mountain",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=mountain_def.characteristics,
        card_def=mountain_def,
    )

    legal = game.priority_system.get_legal_actions(p1.id)
    assert not any(a.type == ActionType.CAST_SPELL and a.card_id == gy_card.id for a in legal)


def test_mayhem_cast_from_graveyard_uses_mayhem_cost_and_does_not_exile():
    game = Game()
    p1 = game.add_player("P1")
    game.add_player("P2")
    game.state.turn_number = 1

    mayhem = _make_test_mayhem_instant()

    # Put in hand, then discard (to satisfy "discarded it this turn").
    hand_card = game.create_object(
        name=mayhem.name,
        owner_id=p1.id,
        zone=ZoneType.HAND,
        characteristics=mayhem.characteristics,
        card_def=mayhem,
    )

    game.emit(Event(
        type=EventType.DISCARD,
        payload={"object_id": hand_card.id},
        controller=p1.id,
    ))

    assert hand_card.zone == ZoneType.GRAVEYARD
    assert hand_card.state.last_discarded_turn == 1
    assert hand_card.state.last_discarded_by == p1.id

    # Pay {R} mayhem cost.
    mountain_def = make_land("Mountain", subtypes={"Mountain"})
    game.create_object(
        name="Mountain",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=mountain_def.characteristics,
        card_def=mountain_def,
    )

    legal = game.priority_system.get_legal_actions(p1.id)
    assert any(
        a.type == ActionType.CAST_SPELL and a.card_id == hand_card.id and "mayhem" in a.description.lower()
        for a in legal
    )

    action = PlayerAction(type=ActionType.CAST_SPELL, player_id=p1.id, card_id=hand_card.id)
    asyncio.run(game.priority_system._handle_cast_spell(action))

    # Resolve and apply post-resolution zone changes.
    for e in game.resolve_stack():
        game.emit(e)

    assert hand_card.zone == ZoneType.GRAVEYARD
    assert hand_card.id in game.state.zones[f"graveyard_{p1.id}"].objects
    assert hand_card.id not in game.state.zones["exile"].objects


def test_graveyard_cast_action_ability_id_selects_correct_option():
    """
    If a card has multiple supported graveyard-cast options, the client must be
    able to choose which one. We use LegalAction.ability_id to disambiguate.
    """
    game = Game()
    p1 = game.add_player("P1")
    game.add_player("P2")

    def noop_resolve(targets, state):
        return []

    dual = make_instant(
        name="Test Dual Graveyard Instant",
        mana_cost="{1}{U}",
        colors={Color.BLUE},
        text=(
            "Flashback {3}{U} (You may cast this card from your graveyard for its flashback cost. Then exile it.)\n"
            "Harmonize {2}{U} (You may cast this card from your graveyard for its harmonize cost. Then exile this spell.)"
        ),
        resolve=noop_resolve,
    )

    gy_card = game.create_object(
        name=dual.name,
        owner_id=p1.id,
        zone=ZoneType.GRAVEYARD,
        characteristics=dual.characteristics,
        card_def=dual,
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

    legal = game.priority_system.get_legal_actions(p1.id)
    options = [
        a for a in legal
        if a.type == ActionType.CAST_SPELL and a.card_id == gy_card.id
    ]
    assert len(options) >= 2, "Expected multiple graveyard cast options"
    assert all(a.ability_id for a in options), "Expected cast options to include ability_id"

    harmonize_action = next(
        a for a in options if "harmonize" in a.description.lower()
    )

    action = PlayerAction(
        type=ActionType.CAST_SPELL,
        player_id=p1.id,
        card_id=gy_card.id,
        ability_id=harmonize_action.ability_id,
    )
    asyncio.run(game.priority_system._handle_cast_spell(action))
    assert gy_card.zone == ZoneType.STACK

    battlefield = game.state.zones["battlefield"].objects
    tapped = sum(1 for oid in battlefield if game.state.objects[oid].state.tapped)
    assert tapped == 3, f"Expected 3 tapped lands for harmonize cost, got {tapped}"
