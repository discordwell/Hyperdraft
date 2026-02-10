import asyncio
import sys

sys.path.insert(0, "/Users/discordwell/Projects/Hyperdraft")

from src.engine import (
    Game, Event, EventType, ZoneType, Phase, Step,
    Color, make_instant, make_creature, make_land,
    PlayerAction, ActionType,
)
from src.ai import AIEngine


def _set_active_main(game: Game, player_id: str) -> None:
    # Sorcery-speed casting + land plays require an active player and a main phase.
    game.turn_manager.turn_state.active_player_id = player_id
    game.turn_manager.turn_state.phase = Phase.PRECOMBAT_MAIN
    game.turn_manager.turn_state.step = Step.MAIN
    game.state.active_player = player_id


def _make_noop_instant(name: str, mana_cost: str, text: str = ""):
    def noop_resolve(targets, state):
        return []

    return make_instant(
        name=name,
        mana_cost=mana_cost,
        colors={Color.BLUE},
        text=text,
        resolve=noop_resolve,
    )


def test_jump_start_cast_from_graveyard_discards_and_exiles_on_resolution():
    game = Game()
    p1 = game.add_player("P1")
    game.add_player("P2")

    jump_def = _make_noop_instant(
        name="Test Jump-Start",
        mana_cost="{1}{U}",
        text="Jump-start (You may cast this spell from your graveyard by discarding a card in addition to paying its other costs. Then exile this spell.)",
    )
    jump_obj = game.create_object(
        name=jump_def.name,
        owner_id=p1.id,
        zone=ZoneType.GRAVEYARD,
        characteristics=jump_def.characteristics,
        card_def=jump_def,
    )

    filler_def = _make_noop_instant("Filler", "{0}", "")
    filler = game.create_object(
        name=filler_def.name,
        owner_id=p1.id,
        zone=ZoneType.HAND,
        characteristics=filler_def.characteristics,
        card_def=filler_def,
    )

    island_def = make_land("Island", subtypes={"Island"})
    for _ in range(2):
        game.create_object(
            name="Island",
            owner_id=p1.id,
            zone=ZoneType.BATTLEFIELD,
            characteristics=island_def.characteristics,
            card_def=island_def,
        )

    action = PlayerAction(type=ActionType.CAST_SPELL, player_id=p1.id, card_id=jump_obj.id)
    asyncio.run(game.priority_system._handle_cast_spell(action))

    choice = game.state.pending_choice
    assert choice is not None
    assert choice.choice_type == "discard"

    ok, msg, _events = game.submit_choice(choice.id, p1.id, [filler.id])
    assert ok, msg
    assert filler.zone == ZoneType.GRAVEYARD
    assert jump_obj.zone == ZoneType.STACK

    for e in game.resolve_stack():
        game.emit(e)

    assert jump_obj.zone == ZoneType.EXILE
    assert jump_obj.id in game.state.zones["exile"].objects


def test_retrace_cast_from_graveyard_discards_land_and_does_not_exile():
    game = Game()
    p1 = game.add_player("P1")
    game.add_player("P2")

    retrace_def = _make_noop_instant(
        name="Test Retrace",
        mana_cost="{1}{U}",
        text="Retrace (You may cast this card from your graveyard by discarding a land card in addition to paying its other costs.)",
    )
    retrace_obj = game.create_object(
        name=retrace_def.name,
        owner_id=p1.id,
        zone=ZoneType.GRAVEYARD,
        characteristics=retrace_def.characteristics,
        card_def=retrace_def,
    )

    forest_def = make_land("Forest", subtypes={"Forest"})
    forest = game.create_object(
        name="Forest",
        owner_id=p1.id,
        zone=ZoneType.HAND,
        characteristics=forest_def.characteristics,
        card_def=forest_def,
    )

    island_def = make_land("Island", subtypes={"Island"})
    for _ in range(2):
        game.create_object(
            name="Island",
            owner_id=p1.id,
            zone=ZoneType.BATTLEFIELD,
            characteristics=island_def.characteristics,
            card_def=island_def,
        )

    action = PlayerAction(type=ActionType.CAST_SPELL, player_id=p1.id, card_id=retrace_obj.id)
    asyncio.run(game.priority_system._handle_cast_spell(action))

    choice = game.state.pending_choice
    assert choice is not None
    assert choice.choice_type == "discard"
    assert forest.id in choice.options

    ok, msg, _events = game.submit_choice(choice.id, p1.id, [forest.id])
    assert ok, msg
    assert forest.zone == ZoneType.GRAVEYARD
    assert retrace_obj.zone == ZoneType.STACK

    for e in game.resolve_stack():
        game.emit(e)

    assert retrace_obj.zone == ZoneType.GRAVEYARD
    assert retrace_obj.id in game.state.zones[f"graveyard_{p1.id}"].objects
    assert retrace_obj.id not in game.state.zones["exile"].objects


def test_escape_cast_from_graveyard_exiles_other_cards_and_returns_to_battlefield():
    game = Game()
    p1 = game.add_player("P1")
    game.add_player("P2")

    _set_active_main(game, p1.id)

    escape_def = make_creature(
        name="Test Escape Creature",
        power=2,
        toughness=2,
        mana_cost="{4}{R}",
        colors={Color.RED},
        text="Escape - {1}{R}, Exile three other cards from your graveyard.",
    )
    escape_obj = game.create_object(
        name=escape_def.name,
        owner_id=p1.id,
        zone=ZoneType.GRAVEYARD,
        characteristics=escape_def.characteristics,
        card_def=escape_def,
    )

    filler_def = _make_noop_instant("GY Filler", "{0}", "")
    fillers = [
        game.create_object(
            name=f"GY Filler {i}",
            owner_id=p1.id,
            zone=ZoneType.GRAVEYARD,
            characteristics=filler_def.characteristics,
            card_def=filler_def,
        )
        for i in range(3)
    ]

    mountain_def = make_land("Mountain", subtypes={"Mountain"})
    for _ in range(2):
        game.create_object(
            name="Mountain",
            owner_id=p1.id,
            zone=ZoneType.BATTLEFIELD,
            characteristics=mountain_def.characteristics,
            card_def=mountain_def,
        )

    action = PlayerAction(type=ActionType.CAST_SPELL, player_id=p1.id, card_id=escape_obj.id)
    asyncio.run(game.priority_system._handle_cast_spell(action))

    choice = game.state.pending_choice
    assert choice is not None
    assert choice.choice_type == "exile_from_graveyard"

    ok, msg, _events = game.submit_choice(choice.id, p1.id, [c.id for c in fillers])
    assert ok, msg

    assert all(c.zone == ZoneType.EXILE for c in fillers)
    assert escape_obj.zone == ZoneType.STACK

    for e in game.resolve_stack():
        game.emit(e)

    assert escape_obj.zone == ZoneType.BATTLEFIELD
    assert escape_obj.id in game.state.zones["battlefield"].objects


def test_delve_reduces_generic_cost_by_exiling_from_graveyard():
    game = Game()
    p1 = game.add_player("P1")
    game.add_player("P2")

    delve_def = _make_noop_instant(
        name="Test Delve Spell",
        mana_cost="{6}{U}",
        text="Delve (Each card you exile from your graveyard while casting this spell pays for {1}.)",
    )
    delve_obj = game.create_object(
        name=delve_def.name,
        owner_id=p1.id,
        zone=ZoneType.HAND,
        characteristics=delve_def.characteristics,
        card_def=delve_def,
    )

    filler_def = _make_noop_instant("GY Filler", "{0}", "")
    fillers = [
        game.create_object(
            name=f"GY Filler {i}",
            owner_id=p1.id,
            zone=ZoneType.GRAVEYARD,
            characteristics=filler_def.characteristics,
            card_def=filler_def,
        )
        for i in range(5)
    ]

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
    assert any(a.type == ActionType.CAST_SPELL and a.card_id == delve_obj.id for a in legal)

    action = PlayerAction(type=ActionType.CAST_SPELL, player_id=p1.id, card_id=delve_obj.id)
    asyncio.run(game.priority_system._handle_cast_spell(action))

    assert all(c.zone == ZoneType.EXILE for c in fillers)

    battlefield = game.state.zones["battlefield"].objects
    tapped = sum(1 for oid in battlefield if game.state.objects[oid].state.tapped)
    assert tapped == 2

    assert delve_obj.zone == ZoneType.STACK
    for e in game.resolve_stack():
        game.emit(e)
    assert delve_obj.zone == ZoneType.GRAVEYARD


def test_grant_cast_from_graveyard_allows_casting_normal_cards_and_expires():
    game = Game()
    p1 = game.add_player("P1")
    game.add_player("P2")

    game.state.turn_number = 5

    spell_def = _make_noop_instant("Plain GY Spell", "{0}", "")
    gy_spell = game.create_object(
        name=spell_def.name,
        owner_id=p1.id,
        zone=ZoneType.GRAVEYARD,
        characteristics=spell_def.characteristics,
        card_def=spell_def,
    )

    legal = game.priority_system.get_legal_actions(p1.id)
    assert not any(a.type == ActionType.CAST_SPELL and a.card_id == gy_spell.id for a in legal)

    game.emit(Event(
        type=EventType.GRANT_CAST_FROM_GRAVEYARD,
        payload={"player": p1.id, "duration": "this_turn"},
        controller=p1.id,
    ))

    legal = game.priority_system.get_legal_actions(p1.id)
    assert any(a.type == ActionType.CAST_SPELL and a.card_id == gy_spell.id for a in legal)

    action = PlayerAction(type=ActionType.CAST_SPELL, player_id=p1.id, card_id=gy_spell.id)
    asyncio.run(game.priority_system._handle_cast_spell(action))
    assert gy_spell.zone == ZoneType.STACK

    # Permission expires after this turn (inclusive).
    game.state.turn_number = 6
    legal = game.priority_system.get_legal_actions(p1.id)
    assert not any(a.type == ActionType.CAST_SPELL and a.card_id == gy_spell.id for a in legal)


def test_grant_play_lands_from_graveyard_allows_playing_land_from_graveyard():
    game = Game()
    p1 = game.add_player("P1")
    game.add_player("P2")

    _set_active_main(game, p1.id)
    game.state.turn_number = 1

    forest_def = make_land("Forest", subtypes={"Forest"})
    gy_forest = game.create_object(
        name="Forest",
        owner_id=p1.id,
        zone=ZoneType.GRAVEYARD,
        characteristics=forest_def.characteristics,
        card_def=forest_def,
    )

    legal = game.priority_system.get_legal_actions(p1.id)
    assert not any(a.type == ActionType.PLAY_LAND and a.card_id == gy_forest.id for a in legal)

    game.emit(Event(
        type=EventType.GRANT_PLAY_LANDS_FROM_GRAVEYARD,
        payload={"player": p1.id, "duration": "this_turn"},
        controller=p1.id,
    ))

    legal = game.priority_system.get_legal_actions(p1.id)
    assert any(a.type == ActionType.PLAY_LAND and a.card_id == gy_forest.id for a in legal)

    action = PlayerAction(type=ActionType.PLAY_LAND, player_id=p1.id, card_id=gy_forest.id)
    asyncio.run(game.priority_system._execute_action(action))

    assert gy_forest.zone == ZoneType.BATTLEFIELD
    assert gy_forest.id in game.state.zones["battlefield"].objects
    assert game.state.lands_played_this_turn == 1


def test_exile_instead_of_graveyard_replaces_spell_leaving_stack():
    game = Game()
    p1 = game.add_player("P1")
    game.add_player("P2")

    game.state.turn_number = 1

    game.emit(Event(
        type=EventType.GRANT_EXILE_INSTEAD_OF_GRAVEYARD,
        payload={"player": p1.id, "duration": "this_turn"},
        controller=p1.id,
    ))

    spell_def = _make_noop_instant("Exile Me", "{0}", "")
    spell = game.create_object(
        name=spell_def.name,
        owner_id=p1.id,
        zone=ZoneType.HAND,
        characteristics=spell_def.characteristics,
        card_def=spell_def,
    )

    action = PlayerAction(type=ActionType.CAST_SPELL, player_id=p1.id, card_id=spell.id)
    asyncio.run(game.priority_system._handle_cast_spell(action))
    assert spell.zone == ZoneType.STACK

    for e in game.resolve_stack():
        game.emit(e)

    assert spell.zone == ZoneType.EXILE
    assert spell.id in game.state.zones["exile"].objects
    assert spell.id not in game.state.zones[f"graveyard_{p1.id}"].objects


def test_exile_instead_of_graveyard_replaces_discard_to_exile():
    game = Game()
    p1 = game.add_player("P1")
    game.add_player("P2")

    game.state.turn_number = 1
    game.emit(Event(
        type=EventType.GRANT_EXILE_INSTEAD_OF_GRAVEYARD,
        payload={"player": p1.id, "duration": "this_turn"},
        controller=p1.id,
    ))

    card_def = _make_noop_instant("Discard Target", "{0}", "")
    card = game.create_object(
        name=card_def.name,
        owner_id=p1.id,
        zone=ZoneType.HAND,
        characteristics=card_def.characteristics,
        card_def=card_def,
    )

    game.emit(Event(type=EventType.DISCARD, payload={"object_id": card.id}, controller=p1.id))

    assert card.zone == ZoneType.EXILE
    assert card.id in game.state.zones["exile"].objects
    assert card.id not in game.state.zones[f"graveyard_{p1.id}"].objects


def test_return_to_hand_from_graveyard_direct_object_id_executes_immediately():
    game = Game()
    p1 = game.add_player("P1")
    game.add_player("P2")

    creature_def = make_creature(name="GY Creature", power=2, toughness=2, mana_cost="{0}", text="")
    creature = game.create_object(
        name=creature_def.name,
        owner_id=p1.id,
        zone=ZoneType.GRAVEYARD,
        characteristics=creature_def.characteristics,
        card_def=creature_def,
    )

    game.emit(Event(
        type=EventType.RETURN_TO_HAND_FROM_GRAVEYARD,
        payload={"player": p1.id, "object_id": creature.id},
        controller=p1.id,
    ))

    assert game.state.pending_choice is None
    assert creature.zone == ZoneType.HAND
    assert creature.id in game.state.zones[f"hand_{p1.id}"].objects


def test_return_from_graveyard_direct_object_id_executes_immediately():
    game = Game()
    p1 = game.add_player("P1")
    game.add_player("P2")

    creature_def = make_creature(name="GY Creature", power=2, toughness=2, mana_cost="{0}", text="")
    creature = game.create_object(
        name=creature_def.name,
        owner_id=p1.id,
        zone=ZoneType.GRAVEYARD,
        characteristics=creature_def.characteristics,
        card_def=creature_def,
    )

    game.emit(Event(
        type=EventType.RETURN_FROM_GRAVEYARD,
        payload={"player": p1.id, "object_id": creature.id},
        controller=p1.id,
    ))

    assert game.state.pending_choice is None
    assert creature.zone == ZoneType.BATTLEFIELD
    assert creature.id in game.state.zones["battlefield"].objects


def test_return_from_graveyard_prompts_when_multiple_eligible_and_returns_selected():
    game = Game()
    p1 = game.add_player("P1")
    game.add_player("P2")

    creature_def = make_creature(name="GY Creature", power=2, toughness=2, mana_cost="{0}", text="")
    a = game.create_object(
        name="A",
        owner_id=p1.id,
        zone=ZoneType.GRAVEYARD,
        characteristics=creature_def.characteristics,
        card_def=creature_def,
    )
    b = game.create_object(
        name="B",
        owner_id=p1.id,
        zone=ZoneType.GRAVEYARD,
        characteristics=creature_def.characteristics,
        card_def=creature_def,
    )

    game.emit(Event(
        type=EventType.RETURN_FROM_GRAVEYARD,
        payload={"player": p1.id, "card_type": "creature", "amount": 1},
        controller=p1.id,
    ))

    choice = game.state.pending_choice
    assert choice is not None
    assert choice.choice_type == "target_with_callback"

    ok, msg, _events = game.submit_choice(choice.id, p1.id, [a.id])
    assert ok, msg

    assert a.zone == ZoneType.BATTLEFIELD
    assert b.zone == ZoneType.GRAVEYARD


def test_ai_can_jump_start_from_graveyard_and_pay_discard_cost():
    game = Game()
    p1 = game.add_player("P1")
    game.add_player("P2")

    jump_def = _make_noop_instant(
        name="AI Jump-Start",
        mana_cost="{1}{U}",
        text="Jump-start (You may cast this spell from your graveyard by discarding a card in addition to paying its other costs. Then exile this spell.)\nDraw a card.",
    )
    jump_obj = game.create_object(
        name=jump_def.name,
        owner_id=p1.id,
        zone=ZoneType.GRAVEYARD,
        characteristics=jump_def.characteristics,
        card_def=jump_def,
    )

    # Land in hand is a safe discard option and can't be played outside main.
    forest_def = make_land("Forest", subtypes={"Forest"})
    forest = game.create_object(
        name="Forest",
        owner_id=p1.id,
        zone=ZoneType.HAND,
        characteristics=forest_def.characteristics,
        card_def=forest_def,
    )

    island_def = make_land("Island", subtypes={"Island"})
    for _ in range(2):
        game.create_object(
            name="Island",
            owner_id=p1.id,
            zone=ZoneType.BATTLEFIELD,
            characteristics=island_def.characteristics,
            card_def=island_def,
        )

    ai = AIEngine(difficulty="medium")
    legal = game.priority_system.get_legal_actions(p1.id)
    action = ai.get_action(p1.id, game.state, legal)
    assert action.type == ActionType.CAST_SPELL
    assert action.card_id == jump_obj.id
    assert action.ability_id is not None

    asyncio.run(game.priority_system._handle_cast_spell(action))
    choice = game.state.pending_choice
    assert choice is not None
    assert choice.choice_type == "discard"

    selected = ai.make_choice(p1.id, choice, game.state)
    assert selected, "Expected AI to select a discard option"

    ok, msg, _events = game.submit_choice(choice.id, p1.id, selected)
    assert ok, msg
    assert forest.zone == ZoneType.GRAVEYARD
    assert jump_obj.zone == ZoneType.STACK

    for e in game.resolve_stack():
        game.emit(e)

    assert jump_obj.zone == ZoneType.EXILE
