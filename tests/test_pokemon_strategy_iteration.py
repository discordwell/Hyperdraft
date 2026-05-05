"""Focused Pokemon strategy iteration tests."""

from src.ai.pokemon_adapter import PokemonAIAdapter
from src.cards.pokemon.sv_starter import (
    BOSS_ORDERS,
    CHARIZARD_EX,
    FIRE_ENERGY,
    WATER_ENERGY,
    CHARMELEON,
    CHARMANDER,
    NEST_BALL,
    POTION,
    PROFESSOR_RESEARCH,
    RARE_CANDY,
    ULTRA_BALL,
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
    cost: list[dict] | None = None,
    retreat_cost: int = 0,
    is_ex: bool = False,
):
    return make_pokemon(
        name=name,
        hp=hp,
        pokemon_type=pokemon_type,
        evolution_stage="Basic",
        attacks=[{
            "name": "Pressure",
            "cost": cost or [],
            "damage": damage,
            "text": "",
        }],
        retreat_cost=retreat_cost,
        is_ex=is_ex,
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


def test_hard_ai_boss_orders_targets_game_winning_ex_over_weak_bench():
    game, p1, p2, ai = _new_pokemon_game("hard")
    game.turn_manager.pkm_turn_state.game_turn_count = 2
    p1.prizes_remaining = 2

    attacker = _card(game, _basic("Ready Attacker", hp=110, damage=120), p1, ZoneType.ACTIVE_SPOT)
    _card(game, BOSS_ORDERS, p1, ZoneType.HAND)
    _card(game, _basic("Opponent Active", hp=180, damage=30), p2, ZoneType.ACTIVE_SPOT)
    weak_bench = _card(game, _basic("Damaged One-Prizer", hp=70, damage=20), p2, ZoneType.BENCH)
    weak_bench.state.damage_counters = 4
    ex_bench = _card(
        game,
        _basic("Prize-Rich ex", hp=120, damage=80, is_ex=True),
        p2,
        ZoneType.BENCH,
    )

    assert ai.choose_boss_target(p1.id, game.state, [weak_bench.id, ex_bench.id]) == ex_bench.id

    ai._current_context = ai._build_turn_context(p1.id, game.state)
    events = ai._do_play_supporter(p1.id, game.state, game.turn_manager)

    assert events
    assert attacker.id in game.state.zones[f"active_spot_{p1.id}"].objects
    assert ex_bench.id in game.state.zones[f"active_spot_{p2.id}"].objects
    assert weak_bench.id in game.state.zones[f"bench_{p2.id}"].objects


def test_hard_ai_routes_energy_to_next_attacker_when_active_is_doomed():
    game, p1, p2, ai = _new_pokemon_game("hard")
    active = _card(
        game,
        _basic("Overexposed Attacker", hp=80, damage=120, cost=[{"type": "C", "count": 1}]),
        p1,
        ZoneType.ACTIVE_SPOT,
    )
    active.state.damage_counters = 2
    attached_energy = _card(game, FIRE_ENERGY, p1, ZoneType.BATTLEFIELD)
    active.state.attached_energy.append(attached_energy.id)
    bench = _card(
        game,
        _basic("Backup Attacker", hp=110, damage=90, cost=[{"type": "C", "count": 1}]),
        p1,
        ZoneType.BENCH,
    )
    hand_energy = _card(game, FIRE_ENERGY, p1, ZoneType.HAND)
    _card(game, _basic("Opponent", hp=160, damage=70), p2, ZoneType.ACTIVE_SPOT)

    ctx = ai._build_turn_context(p1.id, game.state)

    assert ctx.opp_can_ko_me is True
    assert ai._select_energy_target(ctx, game.state, p1.id, [hand_energy.id]) == bench.id


def test_hard_ai_avoids_draw_attack_when_library_is_low():
    game, p1, p2, ai = _new_pokemon_game("hard")
    attacker = _card(
        game,
        make_pokemon(
            name="Careful Attacker",
            hp=110,
            pokemon_type=PokemonType.COLORLESS.value,
            evolution_stage="Basic",
            attacks=[
                {"name": "Reckless Draw", "cost": [], "damage": 60, "text": "Draw 3 cards."},
                {"name": "Safe Hit", "cost": [], "damage": 50, "text": ""},
            ],
        ),
        p1,
        ZoneType.ACTIVE_SPOT,
    )
    _card(game, _basic("Opponent", hp=160, damage=30), p2, ZoneType.ACTIVE_SPOT)
    _card(game, _basic("Deck Card 1"), p1, ZoneType.LIBRARY)
    _card(game, _basic("Deck Card 2"), p1, ZoneType.LIBRARY)

    draw_score = ai._score_attack(attacker, attacker.card_def.attacks[0], game.state, p1.id)
    safe_score = ai._score_attack(attacker, attacker.card_def.attacks[1], game.state, p1.id)

    assert safe_score > draw_score


def test_hard_ai_potion_heals_survival_target_over_most_damaged_bench():
    game, p1, p2, ai = _new_pokemon_game("hard")
    active = _card(game, _basic("Fragile Active", hp=70, damage=60), p1, ZoneType.ACTIVE_SPOT)
    active.state.damage_counters = 4
    bench = _card(game, _basic("Damaged Bench", hp=160, damage=80), p1, ZoneType.BENCH)
    bench.state.damage_counters = 5
    _card(game, _basic("Opponent", hp=160, damage=50), p2, ZoneType.ACTIVE_SPOT)
    _card(game, POTION, p1, ZoneType.HAND)

    ai._current_context = ai._build_turn_context(p1.id, game.state)
    events = ai._do_play_items(p1.id, game.state, game.turn_manager)

    assert events
    assert active.state.damage_counters == 1
    assert bench.state.damage_counters == 5


def test_hard_ai_picks_energy_that_unlocks_attack_now():
    game, p1, _p2, ai = _new_pokemon_game("hard")
    target = _card(
        game,
        make_pokemon(
            name="Mixed Attacker",
            hp=120,
            pokemon_type=PokemonType.FIRE.value,
            evolution_stage="Basic",
            attacks=[
                {
                    "name": "Fire Jab",
                    "cost": [{"type": PokemonType.FIRE.value, "count": 1}],
                    "damage": 60,
                    "text": "",
                },
                {
                    "name": "Water Charge",
                    "cost": [
                        {"type": PokemonType.WATER.value, "count": 1},
                        {"type": "C", "count": 2},
                    ],
                    "damage": 120,
                    "text": "",
                },
            ],
        ),
        p1,
        ZoneType.ACTIVE_SPOT,
    )
    water = _card(game, WATER_ENERGY, p1, ZoneType.HAND)
    fire = _card(game, FIRE_ENERGY, p1, ZoneType.HAND)

    assert ai._pick_best_energy_for_target(target.id, [water.id, fire.id], game.state) == fire.id


def test_hard_ai_promotion_denies_game_winning_ex_prizes():
    game, p1, p2, ai = _new_pokemon_game("hard")
    p1.prizes_remaining = 5
    p2.prizes_remaining = 2
    ex_pokemon = _card(
        game,
        _basic("Huge ex", hp=300, damage=120, is_ex=True),
        p1,
        ZoneType.BENCH,
    )
    single_prizer = _card(game, _basic("One Prize Wall", hp=100, damage=0), p1, ZoneType.BENCH)
    _card(game, _basic("Opponent", hp=160, damage=80), p2, ZoneType.ACTIVE_SPOT)

    assert ai.choose_promote(p1.id, game.state) == single_prizer.id
    assert ai.choose_promote(p1.id, game.state) != ex_pokemon.id


def test_ultra_ball_preserves_rare_candy_stage2_combo():
    game, p1, _p2, _ai = _new_pokemon_game("hard")
    ultra_ball = _card(game, ULTRA_BALL, p1, ZoneType.HAND)
    rare_candy = _card(game, RARE_CANDY, p1, ZoneType.HAND)
    stage2 = _card(game, CHARIZARD_EX, p1, ZoneType.HAND)
    research = _card(game, PROFESSOR_RESEARCH, p1, ZoneType.HAND)
    boss = _card(game, BOSS_ORDERS, p1, ZoneType.HAND)
    _card(game, _basic("Search Target", hp=90, damage=40), p1, ZoneType.LIBRARY)

    events = game.turn_manager._play_trainer(p1.id, ultra_ball.id, "item")

    hand = game.state.zones[f"hand_{p1.id}"].objects
    graveyard = game.state.zones[f"graveyard_{p1.id}"].objects
    assert events
    assert rare_candy.id in hand
    assert stage2.id in hand
    assert research.id in graveyard
    assert boss.id in graveyard


def test_nest_ball_fetches_basic_matching_evolution_in_hand():
    game, p1, _p2, ai = _new_pokemon_game("hard")
    _card(game, NEST_BALL, p1, ZoneType.HAND)
    _card(game, CHARMELEON, p1, ZoneType.HAND)
    target = _card(game, CHARMANDER, p1, ZoneType.LIBRARY)
    bulky = _card(game, _basic("Bulky Basic", hp=140, damage=20), p1, ZoneType.LIBRARY)

    assert ai.choose_nest_ball_target(p1.id, game.state, [bulky.id, target.id]) == target.id

    game.turn_manager._play_trainer(p1.id, game.state.zones[f"hand_{p1.id}"].objects[0], "item")

    assert target.id in game.state.zones[f"bench_{p1.id}"].objects
    assert bulky.id in game.state.zones[f"library_{p1.id}"].objects


def test_hard_ai_does_not_bench_game_losing_ex_liability():
    game, p1, p2, ai = _new_pokemon_game("hard")
    p1.prizes_remaining = 5
    p2.prizes_remaining = 2
    _card(game, _basic("Active", hp=100, damage=40), p1, ZoneType.ACTIVE_SPOT)
    for index in range(3):
        _card(game, _basic(f"Bench {index}", hp=90, damage=30), p1, ZoneType.BENCH)
    ex_basic = _card(game, _basic("Bench Liability ex", hp=220, damage=120, is_ex=True), p1, ZoneType.HAND)
    _card(game, _basic("Opponent", hp=160, damage=80), p2, ZoneType.ACTIVE_SPOT)

    assert ai._score_basic_play(ex_basic, game.state, p1.id) <= 0
    assert ai._do_play_basics(p1.id, game.state, game.turn_manager) == []
    assert ex_basic.id in game.state.zones[f"hand_{p1.id}"].objects
