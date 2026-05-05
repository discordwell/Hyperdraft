"""Focused Hearthstone strategy iteration tests."""

from src.ai.hearthstone_adapter import HearthstoneAIAdapter
from src.cards.hearthstone.basic import BLOODFEN_RAPTOR, CHILLWIND_YETI, THE_COIN
from src.cards.hearthstone.hero_powers import HERO_POWERS
from src.cards.hearthstone.heroes import HEROES
from src.engine.game import Game
from src.engine.types import CardDefinition, CardType, Characteristics, Event, EventType, ZoneType


def _new_hs_game(hero1: str = "Mage", hero2: str = "Warrior"):
    game = Game(mode="hearthstone")
    p1 = game.add_player("P1")
    p2 = game.add_player("P2")
    game.setup_hearthstone_player(p1, HEROES[hero1], HERO_POWERS[hero1])
    game.setup_hearthstone_player(p2, HEROES[hero2], HERO_POWERS[hero2])
    return game, p1, p2


def _hand_card(game: Game, card_def, owner):
    return game.create_object(
        name=card_def.name,
        owner_id=owner.id,
        zone=ZoneType.HAND,
        characteristics=card_def.characteristics,
        card_def=card_def,
    )


def _summon_minion(game: Game, owner, name: str, attack: int, health: int, keywords=None):
    minion = game.create_object(name=name, owner_id=owner.id, zone=ZoneType.BATTLEFIELD)
    minion.characteristics.types = {CardType.MINION}
    minion.characteristics.power = attack
    minion.characteristics.toughness = health
    minion.characteristics.abilities = [
        {"keyword": keyword}
        for keyword in (keywords or set())
    ]
    return minion


def test_hard_ai_uses_coin_to_unlock_much_better_curve_play():
    game, p1, _p2 = _new_hs_game()
    ai = HearthstoneAIAdapter(difficulty="hard")
    p1.mana_crystals_available = 3

    coin = _hand_card(game, THE_COIN, p1)
    _hand_card(game, BLOODFEN_RAPTOR, p1)
    _hand_card(game, CHILLWIND_YETI, p1)

    choice = ai._choose_card_to_play(game.state, p1.id, game)

    assert choice is not None
    assert choice["card_id"] == coin.id


def test_fireblast_kills_one_health_threat_before_defaulting_face():
    game, p1, p2 = _new_hs_game("Mage", "Warrior")
    p1.mana_crystals_available = 2
    p2.life = 30
    _summon_minion(game, p2, "Low Threat", 1, 1)
    threat = _summon_minion(game, p2, "Knife Juggler", 3, 1)

    events = game.pipeline.emit(Event(
        type=EventType.HERO_POWER_ACTIVATE,
        payload={"hero_power_id": p1.hero_power_id, "player": p1.id},
        source=p1.hero_power_id,
    ))

    damage_events = [event for event in events if event.type == EventType.DAMAGE]
    assert damage_events
    assert damage_events[-1].payload["target"] == threat.id


def test_lesser_heal_restores_damaged_friendly_minion_when_hero_full():
    game, p1, _p2 = _new_hs_game("Priest", "Warrior")
    p1.mana_crystals_available = 2
    p1.life = p1.max_life
    minion = _summon_minion(game, p1, "Injured Blademaster", 4, 7)
    minion.state.damage = 3

    events = game.pipeline.emit(Event(
        type=EventType.HERO_POWER_ACTIVATE,
        payload={"hero_power_id": p1.hero_power_id, "player": p1.id},
        source=p1.hero_power_id,
    ))

    assert any(event.type == EventType.LIFE_CHANGE for event in events)
    assert minion.state.damage == 1


def test_hard_ai_damages_best_forced_taunt_target_instead_of_board_order():
    game, p1, p2 = _new_hs_game("Druid", "Warrior")
    ai = HearthstoneAIAdapter(difficulty="hard")
    attacker = _summon_minion(game, p1, "River Crocolisk", 2, 2)
    attacker.state.summoning_sickness = False
    _summon_minion(game, p2, "Ancient Wall", 8, 8, keywords={"taunt"})
    smaller_taunt = _summon_minion(game, p2, "Stubborn Guard", 1, 4, keywords={"taunt"})

    target_id = ai._choose_attack_target(attacker.id, game.state, p1.id)

    assert target_id == smaller_taunt.id


def test_rogue_ai_does_not_replace_existing_dagger_before_attacking():
    game, p1, _p2 = _new_hs_game("Rogue", "Warrior")
    ai = HearthstoneAIAdapter(difficulty="hard")
    p1.mana_crystals_available = 2
    p1.weapon_attack = 1
    p1.weapon_durability = 2

    assert ai._should_use_hero_power(game.state, p1.id) is False

    p1.weapon_durability = 0

    assert ai._should_use_hero_power(game.state, p1.id) is True


def test_minion_only_damage_spell_does_not_create_fake_face_lethal():
    game, p1, p2 = _new_hs_game("Druid", "Warrior")
    ai = HearthstoneAIAdapter(difficulty="hard")
    p1.mana_crystals_available = 2
    p2.life = 3
    target = _summon_minion(game, p2, "Damaged Threat", 3, 3)
    wrath_def = CardDefinition(
        name="Test Wrath",
        mana_cost="{2}",
        characteristics=Characteristics(types={CardType.SPELL}, mana_cost="{2}"),
        text="Deal 3 damage to a minion.",
        requires_target=True,
    )
    wrath = game.create_object(
        name=wrath_def.name,
        owner_id=p1.id,
        zone=ZoneType.HAND,
        characteristics=wrath_def.characteristics,
        card_def=wrath_def,
    )

    lethal = ai._calculate_lethal(p1.id, game.state)
    targets = ai._choose_spell_targets(wrath, game.state, p1.id)

    assert lethal["is_lethal"] is False
    assert lethal["burn_damage"] == 0
    assert targets == [[target.id]]


def test_damage_hero_power_fires_before_card_play_when_lethal():
    game, p1, p2 = _new_hs_game("Hunter", "Warrior")
    ai = HearthstoneAIAdapter(difficulty="hard")
    p1.mana_crystals_available = 2
    p2.life = 2
    _hand_card(game, BLOODFEN_RAPTOR, p1)

    assert ai._should_use_hero_power_early(game.state, p1.id) is True

    p2.armor = 1

    assert ai._should_use_hero_power_early(game.state, p1.id) is False


def test_ultra_does_not_score_minion_only_removal_as_lethal_burn():
    game, p1, p2 = _new_hs_game("Druid", "Warrior")
    ai = HearthstoneAIAdapter(difficulty="ultra")
    attacker = _summon_minion(game, p1, "Board Damage", 3, 3)
    attacker.state.summoning_sickness = False
    p1.mana_crystals_available = 2
    p2.life = 3
    removal_def = CardDefinition(
        name="Minion Bolt",
        mana_cost="{2}",
        characteristics=Characteristics(types={CardType.SPELL}, mana_cost="{2}"),
        text="Deal 3 damage to a minion.",
        requires_target=True,
    )
    removal = game.create_object(
        name=removal_def.name,
        owner_id=p1.id,
        zone=ZoneType.HAND,
        characteristics=removal_def.characteristics,
        card_def=removal_def,
    )

    score = ai._score_card_play(removal, game.state, p1.id)

    assert ai._calculate_lethal(p1.id, game.state)["is_lethal"] is True
    assert score < 100


def test_random_enemy_burn_is_not_guaranteed_lethal_through_minions():
    game, p1, p2 = _new_hs_game("Druid", "Warrior")
    ai = HearthstoneAIAdapter(difficulty="hard")
    p1.mana_crystals_available = 2
    p2.life = 2
    random_burn_def = CardDefinition(
        name="Random Spark",
        mana_cost="{2}",
        characteristics=Characteristics(types={CardType.SPELL}, mana_cost="{2}"),
        text="Deal 2 damage to a random enemy.",
    )
    game.create_object(
        name=random_burn_def.name,
        owner_id=p1.id,
        zone=ZoneType.HAND,
        characteristics=random_burn_def.characteristics,
        card_def=random_burn_def,
    )

    assert ai._calculate_lethal(p1.id, game.state)["is_lethal"] is True

    _summon_minion(game, p2, "Lightning Rod", 1, 1)
    lethal = ai._calculate_lethal(p1.id, game.state)

    assert lethal["is_lethal"] is False
    assert lethal["burn_damage"] == 0
