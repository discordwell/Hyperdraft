"""Pokemon strategy integration tests."""

from src.ai.pokemon_adapter import PokemonAIAdapter
from src.cards.pokemon.sv_starter import SWITCH
from src.engine.game import Game, make_pokemon
from src.engine.types import EventType, PokemonType, ZoneType


def _pokemon_card(
    name: str,
    hp: int,
    pokemon_type: str = PokemonType.COLORLESS.value,
    *,
    damage: int = 40,
    retreat_cost: int = 0,
    is_ex: bool = False,
):
    return make_pokemon(
        name=name,
        hp=hp,
        pokemon_type=pokemon_type,
        attacks=[{
            "name": "Pressure",
            "cost": [],
            "damage": damage,
            "text": "",
        }],
        retreat_cost=retreat_cost,
        is_ex=is_ex,
    )


def _place_pokemon(game: Game, player_id: str, card, zone: ZoneType):
    return game.create_object(
        name=card.name,
        owner_id=player_id,
        zone=zone,
        characteristics=card.characteristics,
        card_def=card,
    )


def _ai_game(difficulty: str = "hard"):
    game = Game(mode="pokemon")
    p1 = game.add_player("AI")
    p2 = game.add_player("Opponent")
    ai = PokemonAIAdapter(difficulty=difficulty)
    game.turn_manager.set_ai_handler(ai)
    game.turn_manager.set_ai_player(p1.id)
    return game, p1, p2, ai


def test_ultra_setup_active_selection_uses_strategy_flag():
    game, p1, _p2, ai = _ai_game("ultra")
    frail = _place_pokemon(
        game,
        p1.id,
        _pokemon_card("Frail Starter", 50, damage=10, retreat_cost=1),
        ZoneType.HAND,
    )
    striker = _place_pokemon(
        game,
        p1.id,
        _pokemon_card("Quick Striker", 90, damage=40, retreat_cost=0),
        ZoneType.HAND,
    )

    assert ai._get_settings(p1.id)["use_opening_active_selection"] is True
    assert ai.choose_setup_active(p1.id, game.state, [frail.id, striker.id]) == striker.id


def test_knockout_promotion_uses_ai_prize_aware_choice():
    game, p1, p2, _ai = _ai_game("hard")
    active = _place_pokemon(
        game,
        p1.id,
        _pokemon_card("Spent Active", 50, damage=10),
        ZoneType.ACTIVE_SPOT,
    )
    _place_pokemon(
        game,
        p2.id,
        _pokemon_card("Large Opponent", 200, PokemonType.WATER.value, damage=40),
        ZoneType.ACTIVE_SPOT,
    )
    risky_ex = _place_pokemon(
        game,
        p1.id,
        _pokemon_card("Risky ex", 160, PokemonType.PSYCHIC.value, damage=40, is_ex=True),
        ZoneType.BENCH,
    )
    safe_attacker = _place_pokemon(
        game,
        p1.id,
        _pokemon_card("Safe Attacker", 140, PokemonType.LIGHTNING.value, damage=40),
        ZoneType.BENCH,
    )
    p1.prizes_remaining = 5
    p2.prizes_remaining = 2

    events = game.combat_manager.handle_knockout(active.id)

    assert game.state.zones[f"active_spot_{p1.id}"].objects == [safe_attacker.id]
    assert risky_ex.id in game.state.zones[f"bench_{p1.id}"].objects
    promote_events = [event for event in events if event.type == EventType.PKM_PROMOTE_ACTIVE]
    assert promote_events[-1].payload["pokemon_id"] == safe_attacker.id


def test_switch_trainer_uses_ai_prize_aware_choice():
    game, p1, p2, _ai = _ai_game("hard")
    _place_pokemon(
        game,
        p1.id,
        _pokemon_card("Active", 80, damage=10),
        ZoneType.ACTIVE_SPOT,
    )
    _place_pokemon(
        game,
        p2.id,
        _pokemon_card("Large Opponent", 200, PokemonType.WATER.value, damage=40),
        ZoneType.ACTIVE_SPOT,
    )
    risky_ex = _place_pokemon(
        game,
        p1.id,
        _pokemon_card("Risky ex", 160, PokemonType.PSYCHIC.value, damage=40, is_ex=True),
        ZoneType.BENCH,
    )
    safe_attacker = _place_pokemon(
        game,
        p1.id,
        _pokemon_card("Safe Attacker", 140, PokemonType.LIGHTNING.value, damage=40),
        ZoneType.BENCH,
    )
    switch = game.create_object(
        name=SWITCH.name,
        owner_id=p1.id,
        zone=ZoneType.HAND,
        characteristics=SWITCH.characteristics,
        card_def=SWITCH,
    )
    p1.prizes_remaining = 5
    p2.prizes_remaining = 2

    events = game.turn_manager._play_trainer(p1.id, switch.id, "item")

    assert game.state.zones[f"active_spot_{p1.id}"].objects == [safe_attacker.id]
    assert risky_ex.id in game.state.zones[f"bench_{p1.id}"].objects
    switch_events = [event for event in events if event.type == EventType.PKM_SWITCH]
    assert switch_events[-1].payload["new_active"] == safe_attacker.id
