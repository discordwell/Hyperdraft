"""Focused Pokemon strategy iteration tests."""

from src.ai.pokemon_adapter import PokemonAIAdapter
from src.cards.pokemon.sv_starter import (
    CHARIZARD_EX,
    CHARMANDER,
    PROFESSOR_RESEARCH,
    RARE_CANDY,
)
from src.engine.game import Game, make_pokemon
from src.engine.types import PokemonType, ZoneType


def _new_pokemon_game(difficulty: str = "hard"):
    game = Game(mode="pokemon")
    p1 = game.add_player("AI")
    p2 = game.add_player("Opponent")
    ai = PokemonAIAdapter(difficulty=difficulty)
    game.turn_manager.set_ai_handler(ai)
    game.turn_manager.set_ai_player(p1.id)
    return game, p1, p2, ai


def _card(game: Game, card_def, owner, zone: ZoneType):
    return game.create_object(
        name=card_def.name,
        owner_id=owner.id,
        zone=zone,
        characteristics=card_def.characteristics,
        card_def=card_def,
    )


def _basic(
    name: str,
    hp: int = 80,
    pokemon_type: str = PokemonType.COLORLESS.value,
    damage: int = 30,
    retreat_cost: int = 0,
):
    return make_pokemon(
        name=name,
        hp=hp,
        pokemon_type=pokemon_type,
        evolution_stage="Basic",
        attacks=[{
            "name": "Pressure",
            "cost": [],
            "damage": damage,
            "text": "",
        }],
        retreat_cost=retreat_cost,
    )


def test_hard_ai_preserves_rare_candy_stage2_combo_over_research():
    game, p1, _p2, ai = _new_pokemon_game("hard")
    active = _card(game, CHARMANDER, p1, ZoneType.ACTIVE_SPOT)
    active.state.turns_in_play = 1
    research = _card(game, PROFESSOR_RESEARCH, p1, ZoneType.HAND)
    _card(game, RARE_CANDY, p1, ZoneType.HAND)
    _card(game, CHARIZARD_EX, p1, ZoneType.HAND)

    ai._current_context = ai._build_turn_context(p1.id, game.state)
    events = ai._do_play_supporter(p1.id, game.state, game.turn_manager)

    assert events == []
    assert research.id in game.state.zones[f"hand_{p1.id}"].objects
