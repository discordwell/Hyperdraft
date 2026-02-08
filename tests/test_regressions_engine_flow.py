#!/usr/bin/env python3
"""
Targeted regressions for gameplay flow and AI/session integration.
"""

import asyncio
import sys

sys.path.insert(0, '/Users/discordwell/Projects/Hyperdraft')

from pydantic import TypeAdapter

from src.ai import AIEngine
from src.cards import ALL_CARDS
from src.engine import CardType, EventType, Game, ZoneType
from src.engine.priority import ActionType, PlayerAction
from src.engine.types import PendingChoice
from src.server.models import ChoiceResultResponse
from src.server.session import GameSession


def test_choice_result_response_forward_ref_is_resolved():
    """ChoiceResultResponse should build a pydantic adapter without errors."""
    adapter = TypeAdapter(ChoiceResultResponse)
    assert adapter is not None


def test_scry_choice_handles_land_without_mana_cost():
    """AI scry choice should not crash when options include lands with no mana cost."""
    ai = AIEngine(difficulty='ultra')

    class DummyObj:
        def __init__(self, name, mana_cost, types):
            self.id = name
            self.name = name
            self.owner = 'p1'
            self.controller = 'p1'
            self.card_def = type('CardDef', (), {'text': ''})()
            self.characteristics = type('Characteristics', (), {
                'mana_cost': mana_cost,
                'types': types,
            })()

    state = type('State', (), {})()
    state.players = {
        'p1': type('Player', (), {'life': 20})(),
        'p2': type('Player', (), {'life': 20})(),
    }
    state.objects = {
        'land': DummyObj('land', None, {CardType.LAND}),
        'spell': DummyObj('spell', '{3}{G}', {CardType.SORCERY}),
    }
    state.zones = {'battlefield': type('Zone', (), {'objects': []})()}

    choice = PendingChoice(
        choice_type='scry',
        player='p1',
        prompt='Scry 2',
        options=['land', 'spell'],
        source_id='source',
        min_choices=0,
        max_choices=2,
    )

    selected = ai.make_choice('p1', choice, state)
    assert isinstance(selected, list)


def test_modal_with_callback_accepts_index_selection():
    """Modal-with-callback selections by index should validate for indexed options."""
    choice = PendingChoice(
        choice_type='modal_with_callback',
        player='p1',
        prompt='Choose one',
        options=[
            {'index': 0, 'text': 'Mode A'},
            {'index': 1, 'text': 'Mode B'},
        ],
        source_id='source',
        min_choices=1,
        max_choices=1,
    )

    ok, message = choice.validate_selection([0])
    assert ok, message


def test_session_ultra_difficulty_uses_ultra_strategy():
    """Session AI should instantiate UltraStrategy for ultra difficulty."""
    session = GameSession(id='test', game=Game(), mode='human_vs_bot', ai_difficulty='ultra')
    ai = session._get_or_create_ai_engine()
    assert ai.strategy.__class__.__name__ == 'UltraStrategy'


def test_planeswalker_has_activatable_loyalty_actions():
    """Planeswalkers with loyalty text should surface activate-ability actions."""
    game = Game()
    player = game.add_player("P1")
    game.add_player("P2")

    kaito = ALL_CARDS["Kaito, Bane of Nightmares"]
    obj = game.create_object(
        name=kaito.name,
        owner_id=player.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=kaito.characteristics,
        card_def=kaito,
    )

    actions = game.priority_system._get_activatable_abilities(obj, player.id)
    assert any(a.type.name == "ACTIVATE_ABILITY" for a in actions)


def test_submit_scry_choice_does_not_crash_pipeline():
    """Submitting a scry choice should not raise when SCRY event payload uses summary counts."""
    game = Game()
    player = game.add_player("P1")
    game.add_player("P2")

    card_a = game.create_object(
        name="Card A",
        owner_id=player.id,
        zone=ZoneType.LIBRARY,
    )
    card_b = game.create_object(
        name="Card B",
        owner_id=player.id,
        zone=ZoneType.LIBRARY,
    )

    choice = game.create_choice(
        choice_type="scry",
        player_id=player.id,
        prompt="Scry 2",
        options=[card_a.id, card_b.id],
        source_id="source",
        min_choices=0,
        max_choices=2,
        callback_data={"scry_count": 2},
    )

    success, message, events = game.submit_choice(choice.id, player.id, [card_a.id])
    assert success, message
    assert game.get_pending_choice() is None
    assert any(e.type == EventType.SCRY for e in events)

    library = game.state.zones[f"library_{player.id}"].objects
    assert library == [card_b.id, card_a.id]


def test_planeswalker_loyalty_activation_only_once_per_turn():
    """Loyalty ability should be activatable at most once per planeswalker each turn."""
    game = Game()
    player = game.add_player("P1")
    game.add_player("P2")

    kaito = ALL_CARDS["Kaito, Bane of Nightmares"]
    obj = game.create_object(
        name=kaito.name,
        owner_id=player.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=kaito.characteristics,
        card_def=kaito,
    )

    loyalty_actions = [
        a for a in game.priority_system._get_activatable_abilities(obj, player.id)
        if (a.ability_id or "").startswith("loyalty:")
    ]
    assert loyalty_actions

    first = loyalty_actions[0]
    action = PlayerAction(
        type=ActionType.ACTIVATE_ABILITY,
        player_id=player.id,
        ability_id=first.ability_id,
        source_id=obj.id,
    )

    first_events = asyncio.run(game.priority_system._handle_activate_ability(action))
    assert first_events

    second_events = asyncio.run(game.priority_system._handle_activate_ability(action))
    assert second_events == []

    remaining = [
        a for a in game.priority_system._get_activatable_abilities(obj, player.id)
        if (a.ability_id or "").startswith("loyalty:")
    ]
    assert not remaining
