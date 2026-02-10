import asyncio
import sys

sys.path.insert(0, '/Users/discordwell/Projects/Hyperdraft')

from src.engine import (
    Game, ZoneType, Color,
    make_instant, make_creature,
    PlayerAction, ActionType,
)


def _make_noop_instant(name: str, mana_cost: str, text: str):
    def noop_resolve(targets, state):
        return []

    return make_instant(
        name=name,
        mana_cost=mana_cost,
        colors={Color.BLUE},
        text=text,
        resolve=noop_resolve,
    )


def test_additional_cost_discard_blocks_cast_if_no_other_hand_cards():
    game = Game()
    p1 = game.add_player("P1")
    game.add_player("P2")

    spell_def = _make_noop_instant(
        name="Test Discard Additional Cost",
        mana_cost="{0}",
        text="As an additional cost to cast this spell, discard a card.",
    )

    spell_obj = game.create_object(
        name=spell_def.name,
        owner_id=p1.id,
        zone=ZoneType.HAND,
        characteristics=spell_def.characteristics,
        card_def=spell_def,
    )

    legal = game.priority_system.get_legal_actions(p1.id)
    assert not any(a.type == ActionType.CAST_SPELL and a.card_id == spell_obj.id for a in legal)


def test_additional_cost_discard_choice_pays_and_casts():
    game = Game()
    p1 = game.add_player("P1")
    game.add_player("P2")

    spell_def = _make_noop_instant(
        name="Test Discard Additional Cost",
        mana_cost="{0}",
        text="As an additional cost to cast this spell, discard a card.",
    )
    filler_def = _make_noop_instant(
        name="Filler Card",
        mana_cost="{0}",
        text="",
    )

    spell_obj = game.create_object(
        name=spell_def.name,
        owner_id=p1.id,
        zone=ZoneType.HAND,
        characteristics=spell_def.characteristics,
        card_def=spell_def,
    )
    filler_obj = game.create_object(
        name=filler_def.name,
        owner_id=p1.id,
        zone=ZoneType.HAND,
        characteristics=filler_def.characteristics,
        card_def=filler_def,
    )

    legal = game.priority_system.get_legal_actions(p1.id)
    assert any(a.type == ActionType.CAST_SPELL and a.card_id == spell_obj.id for a in legal)

    action = PlayerAction(type=ActionType.CAST_SPELL, player_id=p1.id, card_id=spell_obj.id)
    asyncio.run(game.priority_system._handle_cast_spell(action))

    choice = game.state.pending_choice
    assert choice is not None
    assert choice.choice_type == "discard"

    ok, msg, _events = game.submit_choice(choice.id, p1.id, [filler_obj.id])
    assert ok, msg

    assert filler_obj.zone == ZoneType.GRAVEYARD
    assert spell_obj.zone == ZoneType.STACK


def test_additional_cost_or_auto_selects_only_payable_option():
    game = Game()
    p1 = game.add_player("P1")
    game.add_player("P2")

    spell_def = _make_noop_instant(
        name="Test OR Additional Cost",
        mana_cost="{0}",
        text="As an additional cost to cast this spell, discard a card or pay 3 life.",
    )

    spell_obj = game.create_object(
        name=spell_def.name,
        owner_id=p1.id,
        zone=ZoneType.HAND,
        characteristics=spell_def.characteristics,
        card_def=spell_def,
    )

    assert game.state.players[p1.id].life == 20

    action = PlayerAction(type=ActionType.CAST_SPELL, player_id=p1.id, card_id=spell_obj.id)
    asyncio.run(game.priority_system._handle_cast_spell(action))

    # With no other cards in hand, only "pay 3 life" is payable.
    assert game.state.pending_choice is None
    assert game.state.players[p1.id].life == 17
    assert spell_obj.zone == ZoneType.STACK


def test_additional_cost_or_prompts_when_multiple_options_payable():
    game = Game()
    p1 = game.add_player("P1")
    game.add_player("P2")

    spell_def = _make_noop_instant(
        name="Test OR Additional Cost",
        mana_cost="{0}",
        text="As an additional cost to cast this spell, discard a card or pay 3 life.",
    )
    filler_def = _make_noop_instant(
        name="Filler Card",
        mana_cost="{0}",
        text="",
    )

    spell_obj = game.create_object(
        name=spell_def.name,
        owner_id=p1.id,
        zone=ZoneType.HAND,
        characteristics=spell_def.characteristics,
        card_def=spell_def,
    )
    filler_obj = game.create_object(
        name=filler_def.name,
        owner_id=p1.id,
        zone=ZoneType.HAND,
        characteristics=filler_def.characteristics,
        card_def=filler_def,
    )

    action = PlayerAction(type=ActionType.CAST_SPELL, player_id=p1.id, card_id=spell_obj.id)
    asyncio.run(game.priority_system._handle_cast_spell(action))

    choice = game.state.pending_choice
    assert choice is not None
    assert choice.choice_type == "additional_cost_or"

    # Pick the "pay 3 life" option.
    pay_life_id = None
    for opt in choice.options:
        if isinstance(opt, dict) and "pay 3 life" in (opt.get("label") or ""):
            pay_life_id = opt.get("id")
            break
    assert pay_life_id is not None

    assert game.state.players[p1.id].life == 20
    ok, msg, _events = game.submit_choice(choice.id, p1.id, [pay_life_id])
    assert ok, msg

    assert game.state.players[p1.id].life == 17
    assert filler_obj.zone == ZoneType.HAND  # We chose life, not discard.
    assert spell_obj.zone == ZoneType.STACK


def test_graveyard_permission_additional_cost_plan_pays_and_casts():
    game = Game()
    p1 = game.add_player("P1")
    game.add_player("P2")

    spell_def = _make_noop_instant(
        name="Test Graveyard Permission",
        mana_cost="{0}",
        text="You may cast this card from your graveyard by pay 2 life and sacrifice a creature in addition to paying its other costs.",
    )

    gy_obj = game.create_object(
        name=spell_def.name,
        owner_id=p1.id,
        zone=ZoneType.GRAVEYARD,
        characteristics=spell_def.characteristics,
        card_def=spell_def,
    )

    creature_def = make_creature(
        name="Test Creature",
        power=1,
        toughness=1,
        mana_cost="{0}",
        text="",
    )
    creature_obj = game.create_object(
        name=creature_def.name,
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=creature_def.characteristics,
        card_def=creature_def,
    )

    assert game.state.players[p1.id].life == 20

    action = PlayerAction(type=ActionType.CAST_SPELL, player_id=p1.id, card_id=gy_obj.id)
    asyncio.run(game.priority_system._handle_cast_spell(action))

    # The plan starts with a deterministic pay-life step.
    assert game.state.players[p1.id].life == 18

    choice = game.state.pending_choice
    assert choice is not None
    assert choice.choice_type == "sacrifice"

    ok, msg, _events = game.submit_choice(choice.id, p1.id, [creature_obj.id])
    assert ok, msg

    assert creature_obj.zone == ZoneType.GRAVEYARD
    assert gy_obj.zone == ZoneType.STACK

