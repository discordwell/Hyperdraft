"""
Hearthstone Unhappy Path Tests - Batch 119

Combo, Choose One, and Conditional Effects tests.
"""
import pytest
import random
from src.engine.game import Game
from src.engine.types import (
    Event, EventType, GameObject, GameState, CardType, ZoneType,
    Interceptor, InterceptorPriority, InterceptorAction, InterceptorResult,
    new_id
)
from src.engine.queries import get_power, get_toughness, has_ability

from src.cards.hearthstone.heroes import HEROES
from src.cards.hearthstone.hero_powers import HERO_POWERS

from src.cards.hearthstone.basic import (
    WISP, STONETUSK_BOAR, CHILLWIND_YETI, BOULDERFIST_OGRE,
    RIVER_CROCOLISK, BLOODFEN_RAPTOR, RAZORFEN_HUNTER
)
from src.cards.hearthstone.classic import (
    STRANGLETHORN_TIGER, RAGING_WORGEN
)
from src.cards.hearthstone.rogue import (
    EVISCERATE, BACKSTAB, PREPARATION, HEADCRACK,
    SI7_AGENT, DEFIAS_RINGLEADER, EDWIN_VANCLEEF, KIDNAPPER
)
from src.cards.hearthstone.druid import (
    WRATH, STARFALL, DRUID_OF_THE_CLAW, ANCIENT_OF_LORE, ANCIENT_OF_WAR,
    POWER_OF_THE_WILD, NOURISH, MARK_OF_NATURE
)
from src.cards.hearthstone.warrior import EXECUTE, WHIRLWIND, MORTAL_STRIKE
from src.cards.hearthstone.priest import SHADOW_WORD_DEATH, SHADOW_WORD_PAIN
from src.cards.hearthstone.hunter import KILL_COMMAND, TIMBER_WOLF

def new_hs_game(p1_class="Warrior", p2_class="Mage"):
    game = Game(mode='hearthstone')
    p1 = game.add_player("Player1", life=30)
    p2 = game.add_player("Player2", life=30)
    game.setup_hearthstone_player(p1, HEROES[p1_class], HERO_POWERS[p1_class])
    game.setup_hearthstone_player(p2, HEROES[p2_class], HERO_POWERS[p2_class])
    for _ in range(10):
        game.mana_system.on_turn_start(p1.id)
        game.mana_system.on_turn_start(p2.id)
    return game, p1, p2

def make_obj(game, card_def, owner, zone=ZoneType.BATTLEFIELD):
    obj = game.create_object(
        name=card_def.name,
        owner_id=owner.id,
        zone=zone,
        characteristics=card_def.characteristics,
        card_def=card_def
    )
    if zone == ZoneType.BATTLEFIELD and CardType.WEAPON in card_def.characteristics.types:
        game.emit(Event(
            type=EventType.ZONE_CHANGE,
            payload={'object_id': obj.id, 'from_zone_type': None,
                     'to_zone_type': ZoneType.BATTLEFIELD, 'controller': owner.id},
            source=obj.id
        ))
    return obj

def cast_spell(game, card_def, owner, targets=None):
    obj = game.create_object(
        name=card_def.name,
        owner_id=owner.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=card_def.characteristics,
        card_def=card_def
    )
    if targets is None and getattr(card_def, 'requires_target', False):
        battlefield = game.state.zones.get('battlefield')
        if battlefield:
            for oid in battlefield.objects:
                o = game.state.objects.get(oid)
                if o and o.controller != owner.id and CardType.MINION in o.characteristics.types:
                    targets = [oid]
                    break
    events = card_def.spell_effect(obj, game.state, targets or [])
    for e in events:
        game.emit(e)
    game.emit(Event(
        type=EventType.SPELL_CAST,
        payload={'spell_id': obj.id, 'controller': owner.id, 'caster': owner.id},
        source=obj.id
    ))
    owner.cards_played_this_turn += 1
    return obj

def play_minion(game, card_def, owner):
    obj = game.create_object(
        name=card_def.name,
        owner_id=owner.id,
        zone=ZoneType.HAND,
        characteristics=card_def.characteristics,
        card_def=card_def
    )
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={'object_id': obj.id, 'from_zone_type': ZoneType.HAND,
                 'to_zone_type': ZoneType.BATTLEFIELD, 'controller': owner.id},
        source=obj.id
    ))
    owner.cards_played_this_turn += 1
    return obj

def get_battlefield_count(game, player):
    battlefield = game.state.zones.get('battlefield')
    if not battlefield:
        return 0
    count = 0
    for oid in battlefield.objects:
        obj = game.state.objects.get(oid)
        if obj and obj.controller == player.id and CardType.MINION in obj.characteristics.types:
            count += 1
    return count

def add_cards_to_library(game, player, count=10):
    for _ in range(count):
        game.create_object(
            name="Dummy Card",
            owner_id=player.id,
            zone=ZoneType.LIBRARY,
            characteristics=WISP.characteristics,
            card_def=WISP
        )


# ==================== COMBO MECHANICS ====================

def test_eviscerate_without_combo():
    """Eviscerate deals 2 damage without combo"""
    game, p1, p2 = new_hs_game("Rogue", "Mage")
    target = play_minion(game, CHILLWIND_YETI, p2)

    p1.cards_played_this_turn = 0
    cast_spell(game, EVISCERATE, p1, targets=[target.id])

    assert target.state.damage == 2


def test_eviscerate_with_combo():
    """Eviscerate deals 4 damage with combo"""
    game, p1, p2 = new_hs_game("Rogue", "Mage")
    target = play_minion(game, CHILLWIND_YETI, p2)

    p1.cards_played_this_turn = 1
    cast_spell(game, EVISCERATE, p1, targets=[target.id])

    assert target.state.damage == 4


def test_si7_agent_without_combo():
    """SI:7 Agent without combo has no battlecry effect"""
    game, p1, p2 = new_hs_game("Rogue", "Mage")
    target = play_minion(game, CHILLWIND_YETI, p2)

    p1.cards_played_this_turn = 0
    agent = play_minion(game, SI7_AGENT, p1)

    assert target.state.damage == 0


def test_si7_agent_with_combo():
    """SI:7 Agent with combo deals 2 damage"""
    game, p1, p2 = new_hs_game("Rogue", "Mage")
    target = play_minion(game, CHILLWIND_YETI, p2)

    p1.cards_played_this_turn = 1
    agent = play_minion(game, SI7_AGENT, p1)

    assert target.state.damage == 2


def test_defias_ringleader_without_combo():
    """Defias Ringleader without combo summons no token"""
    game, p1, p2 = new_hs_game("Rogue", "Mage")

    p1.cards_played_this_turn = 0
    initial_count = get_battlefield_count(game, p1)
    play_minion(game, DEFIAS_RINGLEADER, p1)

    assert get_battlefield_count(game, p1) == initial_count + 1


def test_defias_ringleader_with_combo():
    """Defias Ringleader with combo summons a 2/1 Defias Bandit"""
    game, p1, p2 = new_hs_game("Rogue", "Mage")

    p1.cards_played_this_turn = 1
    initial_count = get_battlefield_count(game, p1)
    play_minion(game, DEFIAS_RINGLEADER, p1)

    assert get_battlefield_count(game, p1) == initial_count + 2


def test_edwin_vancleef_zero_cards():
    """Edwin VanCleef with 0 cards played is 2/2"""
    game, p1, p2 = new_hs_game("Rogue", "Mage")

    p1.cards_played_this_turn = 0
    edwin = play_minion(game, EDWIN_VANCLEEF, p1)

    assert get_power(edwin, game.state) == 2
    assert get_toughness(edwin, game.state) == 2


def test_edwin_vancleef_one_card():
    """Edwin VanCleef with 1 card played is 4/4"""
    game, p1, p2 = new_hs_game("Rogue", "Mage")

    p1.cards_played_this_turn = 1
    edwin = play_minion(game, EDWIN_VANCLEEF, p1)

    assert get_power(edwin, game.state) == 4
    assert get_toughness(edwin, game.state) == 4


def test_edwin_vancleef_three_cards():
    """Edwin VanCleef with 3 cards played is 8/8"""
    game, p1, p2 = new_hs_game("Rogue", "Mage")

    p1.cards_played_this_turn = 3
    edwin = play_minion(game, EDWIN_VANCLEEF, p1)

    assert get_power(edwin, game.state) == 8
    assert get_toughness(edwin, game.state) == 8


def test_edwin_vancleef_five_cards():
    """Edwin VanCleef with 5 cards played is 12/12"""
    game, p1, p2 = new_hs_game("Rogue", "Mage")

    p1.cards_played_this_turn = 5
    edwin = play_minion(game, EDWIN_VANCLEEF, p1)

    assert get_power(edwin, game.state) == 12
    assert get_toughness(edwin, game.state) == 12


def test_edwin_vancleef_ten_cards():
    """Edwin VanCleef with 10 cards played is massive"""
    game, p1, p2 = new_hs_game("Rogue", "Mage")

    p1.cards_played_this_turn = 10
    edwin = play_minion(game, EDWIN_VANCLEEF, p1)

    # 2/2 base + 2/2 per card = 22/22
    assert get_power(edwin, game.state) == 22
    assert get_toughness(edwin, game.state) == 22


def test_kidnapper_without_combo():
    """Kidnapper without combo returns no minion"""
    game, p1, p2 = new_hs_game("Rogue", "Mage")
    target = play_minion(game, WISP, p2)

    p1.cards_played_this_turn = 0
    initial_count = get_battlefield_count(game, p2)
    play_minion(game, KIDNAPPER, p1)

    assert get_battlefield_count(game, p2) == initial_count


def test_kidnapper_with_combo():
    """Kidnapper with combo returns a minion to hand"""
    game, p1, p2 = new_hs_game("Rogue", "Mage")
    target = play_minion(game, WISP, p2)

    p1.cards_played_this_turn = 1
    initial_count = get_battlefield_count(game, p2)
    play_minion(game, KIDNAPPER, p1)

    assert get_battlefield_count(game, p2) == initial_count - 1


def test_headcrack_without_combo_deals_damage():
    """Headcrack without combo still deals 2 damage to hero"""
    game, p1, p2 = new_hs_game("Rogue", "Mage")

    p1.cards_played_this_turn = 0
    cast_spell(game, HEADCRACK, p1)

    assert p2.life == 28


def test_headcrack_with_combo_deals_damage():
    """Headcrack with combo deals 2 damage to hero"""
    game, p1, p2 = new_hs_game("Rogue", "Mage")

    p1.cards_played_this_turn = 1
    cast_spell(game, HEADCRACK, p1)

    assert p2.life == 28


def test_combo_counter_increments():
    """Cards played this turn increments properly"""
    game, p1, p2 = new_hs_game("Rogue", "Mage")

    assert p1.cards_played_this_turn == 0
    cast_spell(game, BACKSTAB, p1)
    assert p1.cards_played_this_turn == 1
    play_minion(game, WISP, p1)
    assert p1.cards_played_this_turn == 2


def test_combo_with_preparation():
    """Preparation counts as a card for combo"""
    game, p1, p2 = new_hs_game("Rogue", "Mage")

    p1.cards_played_this_turn = 0
    cast_spell(game, PREPARATION, p1)
    assert p1.cards_played_this_turn == 1

    target = play_minion(game, CHILLWIND_YETI, p2)
    cast_spell(game, EVISCERATE, p1, targets=[target.id])
    assert target.state.damage == 4  # Combo active


# ==================== CHOOSE ONE MECHANICS ====================

def test_wrath_choice_damage():
    """Wrath AI chooses 3 damage on low-health target"""
    game, p1, p2 = new_hs_game("Druid", "Mage")
    # Play a 1/1 minion so AI will choose 3 damage to kill it
    target = play_minion(game, WISP, p2)

    obj = game.create_object(
        name=WRATH.name,
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=WRATH.characteristics,
        card_def=WRATH
    )
    events = WRATH.spell_effect(obj, game.state, [target.id])
    for e in events:
        game.emit(e)

    assert target.state.damage == 3


def test_wrath_choice_draw():
    """Wrath AI chooses 1 damage + draw on high-health target"""
    game, p1, p2 = new_hs_game("Druid", "Mage")
    # Play a high-health minion (6/7) so AI will choose 1 damage + draw
    target = play_minion(game, BOULDERFIST_OGRE, p2)
    add_cards_to_library(game, p1, 5)

    hand_zone = game.state.zones.get(f'hand_{p1.id}')
    initial_hand = len(hand_zone.objects) if hand_zone else 0

    obj = game.create_object(
        name=WRATH.name,
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=WRATH.characteristics,
        card_def=WRATH
    )
    events = WRATH.spell_effect(obj, game.state, [target.id])
    for e in events:
        game.emit(e)

    assert target.state.damage == 1
    final_hand = len(hand_zone.objects) if hand_zone else 0
    assert final_hand == initial_hand + 1


def test_starfall_choice_single_target():
    """Starfall AI chooses 5 damage on single/few targets"""
    game, p1, p2 = new_hs_game("Druid", "Mage")
    # Only 2 minions, so AI will choose single-target 5 damage
    target = play_minion(game, CHILLWIND_YETI, p2)
    other = play_minion(game, WISP, p2)

    obj = game.create_object(
        name=STARFALL.name,
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=STARFALL.characteristics,
        card_def=STARFALL
    )
    events = STARFALL.spell_effect(obj, game.state, [target.id])
    for e in events:
        game.emit(e)

    # AI picks one target for 5 damage when there are <3 minions
    assert target.state.damage == 5 or other.state.damage == 5


def test_starfall_choice_aoe():
    """Starfall AI chooses AOE on 3+ minions"""
    game, p1, p2 = new_hs_game("Druid", "Mage")
    # 3+ minions triggers AOE mode in AI
    minion1 = play_minion(game, CHILLWIND_YETI, p2)
    minion2 = play_minion(game, BOULDERFIST_OGRE, p2)
    minion3 = play_minion(game, WISP, p2)

    obj = game.create_object(
        name=STARFALL.name,
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=STARFALL.characteristics,
        card_def=STARFALL
    )
    events = STARFALL.spell_effect(obj, game.state, [])
    for e in events:
        game.emit(e)

    assert minion1.state.damage == 2
    assert minion2.state.damage == 2
    assert minion3.state.damage == 2


def test_power_of_the_wild_choice_buff():
    """Power of the Wild AI chooses buff with 2+ minions"""
    game, p1, p2 = new_hs_game("Druid", "Mage")
    # AI picks buff mode when there are 2+ friendly minions
    minion1 = play_minion(game, WISP, p1)
    minion2 = play_minion(game, WISP, p1)

    obj = game.create_object(
        name=POWER_OF_THE_WILD.name,
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=POWER_OF_THE_WILD.characteristics,
        card_def=POWER_OF_THE_WILD
    )
    events = POWER_OF_THE_WILD.spell_effect(obj, game.state, [])
    for e in events:
        game.emit(e)

    assert get_power(minion1, game.state) == 2
    assert get_toughness(minion1, game.state) == 2


def test_power_of_the_wild_choice_token():
    """Power of the Wild AI chooses token with <2 minions"""
    game, p1, p2 = new_hs_game("Druid", "Mage")
    # AI picks token mode when there are <2 friendly minions
    initial_count = get_battlefield_count(game, p1)

    obj = game.create_object(
        name=POWER_OF_THE_WILD.name,
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=POWER_OF_THE_WILD.characteristics,
        card_def=POWER_OF_THE_WILD
    )
    events = POWER_OF_THE_WILD.spell_effect(obj, game.state, [])
    for e in events:
        game.emit(e)

    assert get_battlefield_count(game, p1) == initial_count + 1


def test_nourish_choice_mana():
    """Nourish AI chooses mana with <8 crystals"""
    game, p1, p2 = new_hs_game("Druid", "Mage")

    # Reset mana to <8 so AI picks ramp
    p1.mana_crystals = 5
    initial_max = p1.mana_crystals

    obj = game.create_object(
        name=NOURISH.name,
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=NOURISH.characteristics,
        card_def=NOURISH
    )
    events = NOURISH.spell_effect(obj, game.state, [])
    for e in events:
        game.emit(e)

    # AI should pick ramp when <8 mana
    assert p1.mana_crystals == initial_max + 2


def test_nourish_choice_draw():
    """Nourish AI chooses draw with 8+ crystals"""
    game, p1, p2 = new_hs_game("Druid", "Mage")
    add_cards_to_library(game, p1, 5)

    # Set mana to 8+ so AI picks draw
    p1.mana_crystals = 8

    hand_zone = game.state.zones.get(f'hand_{p1.id}')
    initial_hand = len(hand_zone.objects) if hand_zone else 0

    obj = game.create_object(
        name=NOURISH.name,
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=NOURISH.characteristics,
        card_def=NOURISH
    )
    events = NOURISH.spell_effect(obj, game.state, [])
    for e in events:
        game.emit(e)

    final_hand = len(hand_zone.objects) if hand_zone else 0
    assert final_hand == initial_hand + 3


def test_mark_of_nature_choice_attack():
    """Mark of Nature AI chooses attack on high-health target"""
    game, p1, p2 = new_hs_game("Druid", "Mage")
    # AI picks attack mode when toughness > 3
    target = play_minion(game, CHILLWIND_YETI, p1)

    obj = game.create_object(
        name=MARK_OF_NATURE.name,
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=MARK_OF_NATURE.characteristics,
        card_def=MARK_OF_NATURE
    )
    events = MARK_OF_NATURE.spell_effect(obj, game.state, [target.id])
    for e in events:
        game.emit(e)

    assert get_power(target, game.state) == 8  # 4 base + 4 buff


def test_mark_of_nature_choice_health():
    """Mark of Nature AI chooses health+taunt on low-health target"""
    game, p1, p2 = new_hs_game("Druid", "Mage")
    # AI picks health mode when toughness <= 3
    target = play_minion(game, WISP, p1)

    obj = game.create_object(
        name=MARK_OF_NATURE.name,
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=MARK_OF_NATURE.characteristics,
        card_def=MARK_OF_NATURE
    )
    events = MARK_OF_NATURE.spell_effect(obj, game.state, [target.id])
    for e in events:
        game.emit(e)

    assert get_toughness(target, game.state) == 5  # 1 base + 4 buff


# ==================== CONDITIONAL EFFECTS ====================

def test_execute_on_damaged_minion():
    """Execute destroys a damaged minion"""
    game, p1, p2 = new_hs_game("Warrior", "Mage")
    target = play_minion(game, BOULDERFIST_OGRE, p2)

    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': target.id, 'amount': 1, 'source': 'test'},
        source='test'
    ))

    cast_spell(game, EXECUTE, p1, targets=[target.id])
    game.check_state_based_actions()

    assert get_battlefield_count(game, p2) == 0


def test_execute_on_undamaged_minion_fails():
    """Execute does nothing to an undamaged minion"""
    game, p1, p2 = new_hs_game("Warrior", "Mage")
    target = play_minion(game, BOULDERFIST_OGRE, p2)

    initial_count = get_battlefield_count(game, p2)
    cast_spell(game, EXECUTE, p1, targets=[target.id])
    game.check_state_based_actions()

    assert get_battlefield_count(game, p2) == initial_count


def test_shadow_word_death_on_high_attack():
    """Shadow Word: Death destroys a minion with 5+ attack"""
    game, p1, p2 = new_hs_game("Priest", "Mage")
    target = play_minion(game, BOULDERFIST_OGRE, p2)

    assert get_power(target, game.state) == 6

    cast_spell(game, SHADOW_WORD_DEATH, p1, targets=[target.id])
    game.check_state_based_actions()

    assert get_battlefield_count(game, p2) == 0


def test_shadow_word_death_on_low_attack_fails():
    """Shadow Word: Death fails on a minion with <5 attack"""
    game, p1, p2 = new_hs_game("Priest", "Mage")
    target = play_minion(game, CHILLWIND_YETI, p2)

    assert get_power(target, game.state) == 4

    initial_count = get_battlefield_count(game, p2)
    cast_spell(game, SHADOW_WORD_DEATH, p1, targets=[target.id])
    game.check_state_based_actions()

    assert get_battlefield_count(game, p2) == initial_count


def test_shadow_word_death_on_exactly_five_attack():
    """Shadow Word: Death works on exactly 5 attack"""
    game, p1, p2 = new_hs_game("Priest", "Mage")
    target = play_minion(game, STRANGLETHORN_TIGER, p2)

    assert get_power(target, game.state) == 5

    cast_spell(game, SHADOW_WORD_DEATH, p1, targets=[target.id])
    game.check_state_based_actions()

    assert get_battlefield_count(game, p2) == 0


def test_shadow_word_pain_on_low_attack():
    """Shadow Word: Pain destroys a minion with 3 or less attack"""
    game, p1, p2 = new_hs_game("Priest", "Mage")
    target = play_minion(game, RIVER_CROCOLISK, p2)

    assert get_power(target, game.state) == 2

    cast_spell(game, SHADOW_WORD_PAIN, p1, targets=[target.id])
    game.check_state_based_actions()

    assert get_battlefield_count(game, p2) == 0


def test_shadow_word_pain_on_high_attack_fails():
    """Shadow Word: Pain fails on a minion with 4+ attack"""
    game, p1, p2 = new_hs_game("Priest", "Mage")
    target = play_minion(game, CHILLWIND_YETI, p2)

    assert get_power(target, game.state) == 4

    initial_count = get_battlefield_count(game, p2)
    cast_spell(game, SHADOW_WORD_PAIN, p1, targets=[target.id])
    game.check_state_based_actions()

    assert get_battlefield_count(game, p2) == initial_count


def test_shadow_word_pain_on_exactly_three_attack():
    """Shadow Word: Pain works on exactly 3 attack"""
    game, p1, p2 = new_hs_game("Priest", "Mage")
    target = play_minion(game, RAGING_WORGEN, p2)

    assert get_power(target, game.state) == 3

    cast_spell(game, SHADOW_WORD_PAIN, p1, targets=[target.id])
    game.check_state_based_actions()

    assert get_battlefield_count(game, p2) == 0


def test_kill_command_with_beast():
    """Kill Command deals 5 damage with a beast"""
    game, p1, p2 = new_hs_game("Hunter", "Mage")
    play_minion(game, TIMBER_WOLF, p1)
    target = play_minion(game, CHILLWIND_YETI, p2)

    cast_spell(game, KILL_COMMAND, p1, targets=[target.id])

    assert target.state.damage == 5


def test_kill_command_without_beast():
    """Kill Command deals 3 damage without a beast"""
    game, p1, p2 = new_hs_game("Hunter", "Mage")
    target = play_minion(game, CHILLWIND_YETI, p2)

    cast_spell(game, KILL_COMMAND, p1, targets=[target.id])

    assert target.state.damage == 3


def test_mortal_strike_at_high_health():
    """Mortal Strike deals 4 damage when hero has 13+ health"""
    game, p1, p2 = new_hs_game("Warrior", "Mage")

    assert p1.life == 30

    cast_spell(game, MORTAL_STRIKE, p1, targets=[p2.id])

    assert p2.life == 26


def test_mortal_strike_at_low_health():
    """Mortal Strike deals 6 damage when hero has 12 or less health"""
    game, p1, p2 = new_hs_game("Warrior", "Mage")

    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': p1.id, 'amount': 18, 'source': 'test'},
        source='test'
    ))

    assert p1.life == 12

    cast_spell(game, MORTAL_STRIKE, p1, targets=[p2.id])

    assert p2.life == 24


def test_execute_whirlwind_combo():
    """Whirlwind + Execute combo: Whirlwind damages target, then Execute kills it"""
    game, p1, p2 = new_hs_game("Warrior", "Mage")
    target = play_minion(game, BOULDERFIST_OGRE, p2)

    cast_spell(game, WHIRLWIND, p1)
    assert target.state.damage == 1

    cast_spell(game, EXECUTE, p1, targets=[target.id])
    game.check_state_based_actions()

    assert get_battlefield_count(game, p2) == 0


def test_backstab_enables_execute():
    """Backstab deals 2 damage, enabling Execute"""
    game, p1, p2 = new_hs_game("Warrior", "Mage")
    target = play_minion(game, CHILLWIND_YETI, p2)

    cast_spell(game, BACKSTAB, p1, targets=[target.id])
    assert target.state.damage == 2

    cast_spell(game, EXECUTE, p1, targets=[target.id])
    game.check_state_based_actions()

    assert get_battlefield_count(game, p2) == 0


def test_combo_not_triggered_by_zero_cards():
    """Combo check: 0 cards played means Eviscerate deals 2 (non-combo)"""
    game, p1, p2 = new_hs_game("Rogue", "Mage")

    p1.cards_played_this_turn = 0
    target = play_minion(game, CHILLWIND_YETI, p2)

    cast_spell(game, EVISCERATE, p1, targets=[target.id])

    # Without combo, Eviscerate deals 2 damage
    assert target.state.damage == 2
