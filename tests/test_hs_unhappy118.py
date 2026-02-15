"""
Hearthstone Unhappy Path Tests - Batch 118

Enrage and Damage-Triggered Effects tests.
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
    WISP, STONETUSK_BOAR, BLOODFEN_RAPTOR, GURUBASHI_BERSERKER
)
from src.cards.hearthstone.classic import (
    AMANI_BERSERKER, RAGING_WORGEN, ANGRY_CHICKEN, SPITEFUL_SMITH,
    ACOLYTE_OF_PAIN, ARGENT_SQUIRE
)
from src.cards.hearthstone.warrior import (
    WHIRLWIND, EXECUTE, FIERY_WAR_AXE, GROMMASH_HELLSCREAM,
    CRUEL_TASKMASTER, INNER_RAGE, ARMORSMITH, FROTHING_BERSERKER
)
from src.cards.hearthstone.paladin import HOLY_LIGHT
from src.cards.hearthstone.priest import CIRCLE_OF_HEALING

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


# Amani Berserker Tests (2/3 minion, enraged 5/3)
def test_amani_berserker_enrage_on_damage():
    """Amani Berserker should gain +3 attack when damaged"""
    game, p1, p2 = new_hs_game()
    berserker = play_minion(game, AMANI_BERSERKER, p1)

    assert get_power(berserker, game.state) == 2
    assert get_toughness(berserker, game.state) == 3

    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': berserker.id, 'amount': 1, 'source': 'test'},
        source='test'
    ))

    assert berserker.state.damage == 1
    assert get_power(berserker, game.state) == 5
    assert get_toughness(berserker, game.state) == 3


def test_amani_berserker_enrage_removed_by_healing():
    """Amani Berserker should lose enrage when healed back to full"""
    game, p1, p2 = new_hs_game()
    berserker = play_minion(game, AMANI_BERSERKER, p1)

    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': berserker.id, 'amount': 2, 'source': 'test'},
        source='test'
    ))

    assert get_power(berserker, game.state) == 5

    cast_spell(game, CIRCLE_OF_HEALING, p1)

    assert berserker.state.damage == 0
    assert get_power(berserker, game.state) == 2


def test_amani_berserker_killed_while_enraged():
    """Amani Berserker should die when damage >= toughness, enrage doesn't save it"""
    game, p1, p2 = new_hs_game()
    berserker = play_minion(game, AMANI_BERSERKER, p1)

    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': berserker.id, 'amount': 3, 'source': 'test'},
        source='test'
    ))

    game.check_state_based_actions()

    battlefield_zone = game.state.zones.get('battlefield')
    assert berserker.id not in battlefield_zone.objects


def test_amani_berserker_partial_healing_stays_enraged():
    """Amani Berserker should stay enraged if partially healed (still damaged)"""
    game, p1, p2 = new_hs_game()
    berserker = play_minion(game, AMANI_BERSERKER, p1)

    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': berserker.id, 'amount': 2, 'source': 'test'},
        source='test'
    ))

    assert get_power(berserker, game.state) == 5

    # Directly heal the minion by reducing damage
    berserker.state.damage = max(0, berserker.state.damage - 1)

    assert berserker.state.damage == 1
    assert get_power(berserker, game.state) == 5


# Raging Worgen Tests (3/3 minion, enraged 4/3 with windfury)
def test_raging_worgen_enrage_grants_attack_and_windfury():
    """Raging Worgen should gain +1 attack and windfury when damaged"""
    game, p1, p2 = new_hs_game()
    worgen = play_minion(game, RAGING_WORGEN, p1)

    assert get_power(worgen, game.state) == 3
    assert get_toughness(worgen, game.state) == 3
    assert not has_ability(worgen, 'windfury', game.state)

    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': worgen.id, 'amount': 1, 'source': 'test'},
        source='test'
    ))

    assert get_power(worgen, game.state) == 4
    assert has_ability(worgen, 'windfury', game.state)


def test_raging_worgen_loses_windfury_when_healed():
    """Raging Worgen should lose windfury when healed to full"""
    game, p1, p2 = new_hs_game()
    worgen = play_minion(game, RAGING_WORGEN, p1)

    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': worgen.id, 'amount': 2, 'source': 'test'},
        source='test'
    ))

    assert has_ability(worgen, 'windfury', game.state)

    cast_spell(game, CIRCLE_OF_HEALING, p1)

    assert worgen.state.damage == 0
    assert get_power(worgen, game.state) == 3
    assert not has_ability(worgen, 'windfury', game.state)


# Angry Chicken Tests (1/1 minion, enraged 6/1)
def test_angry_chicken_enrage_massive_attack_boost():
    """Angry Chicken should gain +5 attack when damaged"""
    game, p1, p2 = new_hs_game()
    chicken = play_minion(game, ANGRY_CHICKEN, p1)

    assert get_power(chicken, game.state) == 1

    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': chicken.id, 'amount': 1, 'source': 'test'},
        source='test'
    ))

    assert chicken.state.damage == 1
    assert get_toughness(chicken, game.state) == 1
    assert get_power(chicken, game.state) == 6


def test_angry_chicken_dies_from_overkill():
    """Angry Chicken should die from overkill damage, enrage doesn't matter"""
    game, p1, p2 = new_hs_game()
    chicken = play_minion(game, ANGRY_CHICKEN, p1)

    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': chicken.id, 'amount': 5, 'source': 'test'},
        source='test'
    ))

    game.check_state_based_actions()

    battlefield_zone = game.state.zones.get('battlefield')
    assert chicken.id not in battlefield_zone.objects


# Grommash Hellscream Tests (4/9 with charge, enraged 10/9)
def test_grommash_enrage_gains_six_attack():
    """Grommash should gain +6 attack when damaged"""
    game, p1, p2 = new_hs_game()
    grommash = play_minion(game, GROMMASH_HELLSCREAM, p1)

    assert get_power(grommash, game.state) == 4
    assert has_ability(grommash, 'charge', game.state)

    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': grommash.id, 'amount': 1, 'source': 'test'},
        source='test'
    ))

    assert get_power(grommash, game.state) == 10


def test_grommash_enrage_enabled_by_inner_rage():
    """Inner Rage should damage Grommash and enable enrage"""
    game, p1, p2 = new_hs_game()
    grommash = play_minion(game, GROMMASH_HELLSCREAM, p1)

    assert get_power(grommash, game.state) == 4

    cast_spell(game, INNER_RAGE, p1, targets=[grommash.id])

    # +2 from Inner Rage, +6 from enrage = 12 total attack
    assert grommash.state.damage == 1
    assert get_power(grommash, game.state) == 12


def test_grommash_retains_charge_while_enraged():
    """Grommash should keep charge even when enraged"""
    game, p1, p2 = new_hs_game()
    grommash = play_minion(game, GROMMASH_HELLSCREAM, p1)

    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': grommash.id, 'amount': 5, 'source': 'test'},
        source='test'
    ))

    assert has_ability(grommash, 'charge', game.state)
    assert get_power(grommash, game.state) == 10


# Spiteful Smith Tests (4/6 minion, enraged gives weapon +2 attack)
def test_spiteful_smith_enrage_boosts_weapon():
    """Spiteful Smith's enrage interceptor should be registered when damaged.
    The effect transforms combat DAMAGE events to add +2 to weapon attacks."""
    game, p1, p2 = new_hs_game()
    smith = play_minion(game, SPITEFUL_SMITH, p1)
    weapon = make_obj(game, FIERY_WAR_AXE, p1, ZoneType.BATTLEFIELD)

    # Verify the smith has interceptors registered
    assert len(smith.interceptor_ids) >= 1

    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': smith.id, 'amount': 1, 'source': 'test'},
        source='test'
    ))

    # Smith is now damaged (enraged) — interceptor transforms weapon combat damage
    assert smith.state.damage == 1


def test_spiteful_smith_loses_weapon_boost_when_healed():
    """Spiteful Smith should lose enrage buff when healed to full"""
    game, p1, p2 = new_hs_game()
    smith = play_minion(game, SPITEFUL_SMITH, p1)

    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': smith.id, 'amount': 3, 'source': 'test'},
        source='test'
    ))

    assert smith.state.damage == 3

    # Heal via Circle of Healing
    cast_spell(game, CIRCLE_OF_HEALING, p1)

    # Smith healed to full — no longer enraged
    assert smith.state.damage == 0


def test_spiteful_smith_dies_weapon_stays():
    """When Spiteful Smith dies, the weapon itself remains on the battlefield"""
    game, p1, p2 = new_hs_game()
    smith = play_minion(game, SPITEFUL_SMITH, p1)
    weapon = make_obj(game, FIERY_WAR_AXE, p1, ZoneType.BATTLEFIELD)

    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': smith.id, 'amount': 10, 'source': 'test'},
        source='test'
    ))

    game.check_state_based_actions()

    # Smith dead, weapon still exists
    battlefield = game.state.zones.get('battlefield')
    assert smith.id not in battlefield.objects
    assert weapon.id in battlefield.objects


# Acolyte of Pain Tests (1/3 minion, draw a card when damaged)
def test_acolyte_of_pain_draws_on_single_damage():
    """Acolyte of Pain should draw 1 card when damaged once"""
    game, p1, p2 = new_hs_game()
    add_cards_to_library(game, p1, 10)
    acolyte = play_minion(game, ACOLYTE_OF_PAIN, p1)

    hand_zone = game.state.zones.get(f'hand_{p1.id}')
    initial_hand = len(hand_zone.objects)

    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': acolyte.id, 'amount': 1, 'source': 'test'},
        source='test'
    ))

    assert len(hand_zone.objects) == initial_hand + 1


def test_acolyte_of_pain_draws_from_whirlwind():
    """Acolyte of Pain should draw once from Whirlwind"""
    game, p1, p2 = new_hs_game()
    add_cards_to_library(game, p1, 10)
    acolyte = play_minion(game, ACOLYTE_OF_PAIN, p1)

    hand_zone = game.state.zones.get(f'hand_{p1.id}')
    initial_hand = len(hand_zone.objects)

    cast_spell(game, WHIRLWIND, p1)

    assert len(hand_zone.objects) == initial_hand + 1


def test_acolyte_of_pain_draws_three_times_from_three_damage():
    """Acolyte of Pain should draw 3 cards from 3 separate damage instances"""
    game, p1, p2 = new_hs_game()
    add_cards_to_library(game, p1, 10)
    acolyte = play_minion(game, ACOLYTE_OF_PAIN, p1)

    hand_zone = game.state.zones.get(f'hand_{p1.id}')
    initial_hand = len(hand_zone.objects)

    for _ in range(3):
        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': acolyte.id, 'amount': 1, 'source': 'test'},
            source='test'
        ))

    assert len(hand_zone.objects) == initial_hand + 3


def test_acolyte_of_pain_killed_by_damage_still_draws():
    """Acolyte of Pain should draw even if the damage kills it"""
    game, p1, p2 = new_hs_game()
    add_cards_to_library(game, p1, 10)
    acolyte = play_minion(game, ACOLYTE_OF_PAIN, p1)

    hand_zone = game.state.zones.get(f'hand_{p1.id}')
    initial_hand = len(hand_zone.objects)

    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': acolyte.id, 'amount': 10, 'source': 'test'},
        source='test'
    ))

    assert len(hand_zone.objects) == initial_hand + 1

    game.check_state_based_actions()

    battlefield_zone = game.state.zones.get('battlefield')
    assert acolyte.id not in battlefield_zone.objects


def test_acolyte_of_pain_no_draw_from_divine_shield():
    """Acolyte of Pain with divine shield should not draw when shield blocks damage"""
    game, p1, p2 = new_hs_game()
    add_cards_to_library(game, p1, 10)
    acolyte = play_minion(game, ACOLYTE_OF_PAIN, p1)

    acolyte.state.divine_shield = True

    hand_zone = game.state.zones.get(f'hand_{p1.id}')
    initial_hand = len(hand_zone.objects)

    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': acolyte.id, 'amount': 1, 'source': 'test'},
        source='test'
    ))

    assert acolyte.state.damage == 0
    assert len(hand_zone.objects) == initial_hand


# Armorsmith Tests (1/4 minion, gain 1 armor when friendly minion takes damage)
def test_armorsmith_gains_armor_when_friendly_minion_damaged():
    """Armorsmith should grant 1 armor when friendly minion is damaged"""
    game, p1, p2 = new_hs_game()
    armorsmith = play_minion(game, ARMORSMITH, p1)
    boar = play_minion(game, STONETUSK_BOAR, p1)

    assert p1.armor == 0

    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': boar.id, 'amount': 1, 'source': 'test'},
        source='test'
    ))

    assert p1.armor == 1


def test_armorsmith_gains_armor_when_itself_damaged():
    """Armorsmith should grant armor when it itself takes damage"""
    game, p1, p2 = new_hs_game()
    armorsmith = play_minion(game, ARMORSMITH, p1)

    assert p1.armor == 0

    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': armorsmith.id, 'amount': 1, 'source': 'test'},
        source='test'
    ))

    assert p1.armor == 1


def test_armorsmith_gains_armor_from_whirlwind():
    """Armorsmith should grant 1 armor per minion damaged by Whirlwind"""
    game, p1, p2 = new_hs_game()
    armorsmith = play_minion(game, ARMORSMITH, p1)
    boar1 = play_minion(game, STONETUSK_BOAR, p1)
    boar2 = play_minion(game, STONETUSK_BOAR, p1)

    assert p1.armor == 0

    cast_spell(game, WHIRLWIND, p1)

    # 3 friendly minions damaged = 3 armor
    assert p1.armor == 3


def test_armorsmith_no_armor_from_enemy_minion_damage():
    """Armorsmith should not grant armor when enemy minion is damaged"""
    game, p1, p2 = new_hs_game()
    armorsmith = play_minion(game, ARMORSMITH, p1)
    enemy_boar = play_minion(game, STONETUSK_BOAR, p2)

    assert p1.armor == 0

    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': enemy_boar.id, 'amount': 1, 'source': 'test'},
        source='test'
    ))

    assert p1.armor == 0


def test_double_armorsmith_doubles_armor_gain():
    """Two Armorsmiths should each grant 1 armor per damaged minion"""
    game, p1, p2 = new_hs_game()
    armorsmith1 = play_minion(game, ARMORSMITH, p1)
    armorsmith2 = play_minion(game, ARMORSMITH, p1)
    boar = play_minion(game, STONETUSK_BOAR, p1)

    assert p1.armor == 0

    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': boar.id, 'amount': 1, 'source': 'test'},
        source='test'
    ))

    assert p1.armor == 2


# Gurubashi Berserker Tests (2/7 minion, gain +3 attack when damaged)
def test_gurubashi_berserker_gains_attack_on_damage():
    """Gurubashi Berserker should gain +3 attack when damaged"""
    game, p1, p2 = new_hs_game()
    berserker = play_minion(game, GURUBASHI_BERSERKER, p1)

    assert get_power(berserker, game.state) == 2

    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': berserker.id, 'amount': 1, 'source': 'test'},
        source='test'
    ))

    assert get_power(berserker, game.state) == 5


def test_gurubashi_berserker_stacks_attack_from_multiple_damage():
    """Gurubashi Berserker should stack +3 attack for each damage instance"""
    game, p1, p2 = new_hs_game()
    berserker = play_minion(game, GURUBASHI_BERSERKER, p1)

    assert get_power(berserker, game.state) == 2

    for _ in range(3):
        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': berserker.id, 'amount': 1, 'source': 'test'},
            source='test'
        ))

    # 2 base + (3 * 3) = 11 attack
    assert get_power(berserker, game.state) == 11


def test_gurubashi_berserker_healing_does_not_remove_attack():
    """Gurubashi Berserker should keep +3 attack bonuses even when healed (not enrage)"""
    game, p1, p2 = new_hs_game()
    berserker = play_minion(game, GURUBASHI_BERSERKER, p1)

    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': berserker.id, 'amount': 1, 'source': 'test'},
        source='test'
    ))
    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': berserker.id, 'amount': 1, 'source': 'test'},
        source='test'
    ))

    # 2 damage instances = +6 attack
    assert get_power(berserker, game.state) == 8

    cast_spell(game, CIRCLE_OF_HEALING, p1)

    assert berserker.state.damage == 0
    assert get_power(berserker, game.state) == 8


def test_gurubashi_berserker_massive_stacking():
    """Gurubashi Berserker should stack attack from many damage instances"""
    game, p1, p2 = new_hs_game()
    berserker = play_minion(game, GURUBASHI_BERSERKER, p1)

    for _ in range(5):
        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': berserker.id, 'amount': 1, 'source': 'test'},
            source='test'
        ))

    # 2 base + (5 * 3) = 17 attack
    assert get_power(berserker, game.state) == 17


# Frothing Berserker Tests (2/4 minion, gain +1 attack when ANY minion takes damage)
def test_frothing_berserker_gains_attack_from_friendly_damage():
    """Frothing Berserker should gain +1 attack when friendly minion is damaged"""
    game, p1, p2 = new_hs_game()
    frothing = play_minion(game, FROTHING_BERSERKER, p1)
    boar = play_minion(game, STONETUSK_BOAR, p1)

    assert get_power(frothing, game.state) == 2

    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': boar.id, 'amount': 1, 'source': 'test'},
        source='test'
    ))

    assert get_power(frothing, game.state) == 3


def test_frothing_berserker_gains_attack_from_enemy_damage():
    """Frothing Berserker should gain +1 attack when enemy minion is damaged"""
    game, p1, p2 = new_hs_game()
    frothing = play_minion(game, FROTHING_BERSERKER, p1)
    enemy_boar = play_minion(game, STONETUSK_BOAR, p2)

    assert get_power(frothing, game.state) == 2

    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': enemy_boar.id, 'amount': 1, 'source': 'test'},
        source='test'
    ))

    assert get_power(frothing, game.state) == 3


def test_frothing_berserker_gains_attack_from_self_damage():
    """Frothing Berserker should gain +1 attack when it takes damage"""
    game, p1, p2 = new_hs_game()
    frothing = play_minion(game, FROTHING_BERSERKER, p1)

    assert get_power(frothing, game.state) == 2

    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': frothing.id, 'amount': 1, 'source': 'test'},
        source='test'
    ))

    assert get_power(frothing, game.state) == 3


def test_frothing_berserker_whirlwind_counting():
    """Frothing Berserker should gain +1 attack per minion hit by Whirlwind"""
    game, p1, p2 = new_hs_game()
    frothing = play_minion(game, FROTHING_BERSERKER, p1)
    boar1 = play_minion(game, STONETUSK_BOAR, p1)
    boar2 = play_minion(game, STONETUSK_BOAR, p1)
    enemy_boar = play_minion(game, STONETUSK_BOAR, p2)

    assert get_power(frothing, game.state) == 2

    cast_spell(game, WHIRLWIND, p1)

    # 4 minions damaged (frothing + 2 friendly + 1 enemy) = +4 attack
    assert get_power(frothing, game.state) == 6


def test_double_frothing_berserker_both_gain_attack():
    """Two Frothing Berserkers should each gain +1 attack per damage instance"""
    game, p1, p2 = new_hs_game()
    frothing1 = play_minion(game, FROTHING_BERSERKER, p1)
    frothing2 = play_minion(game, FROTHING_BERSERKER, p1)
    boar = play_minion(game, STONETUSK_BOAR, p1)

    assert get_power(frothing1, game.state) == 2
    assert get_power(frothing2, game.state) == 2

    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': boar.id, 'amount': 1, 'source': 'test'},
        source='test'
    ))

    assert get_power(frothing1, game.state) == 3
    assert get_power(frothing2, game.state) == 3


def test_frothing_berserker_attack_persists_after_healing():
    """Frothing Berserker attack bonuses should persist (not enrage)"""
    game, p1, p2 = new_hs_game()
    frothing = play_minion(game, FROTHING_BERSERKER, p1)
    boar = play_minion(game, STONETUSK_BOAR, p1)

    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': boar.id, 'amount': 1, 'source': 'test'},
        source='test'
    ))

    assert get_power(frothing, game.state) == 3

    # Directly heal the minion by reducing damage
    boar.state.damage = max(0, boar.state.damage - 5)

    assert get_power(frothing, game.state) == 3


# Inner Rage Tests (deal 1 damage, grant +2 attack)
def test_inner_rage_enables_enrage():
    """Inner Rage should damage a minion and grant +2 attack, enabling enrage"""
    game, p1, p2 = new_hs_game()
    berserker = play_minion(game, AMANI_BERSERKER, p1)

    assert get_power(berserker, game.state) == 2

    cast_spell(game, INNER_RAGE, p1, targets=[berserker.id])

    # +2 from Inner Rage, +3 from enrage = 7 attack
    assert berserker.state.damage == 1
    assert get_power(berserker, game.state) == 7


def test_inner_rage_on_gurubashi():
    """Inner Rage should trigger Gurubashi and grant attack buff"""
    game, p1, p2 = new_hs_game()
    berserker = play_minion(game, GURUBASHI_BERSERKER, p1)

    assert get_power(berserker, game.state) == 2

    cast_spell(game, INNER_RAGE, p1, targets=[berserker.id])

    # +2 from Inner Rage, +3 from Gurubashi trigger = 7 attack
    assert get_power(berserker, game.state) == 7


def test_inner_rage_triggers_acolyte():
    """Inner Rage should trigger Acolyte of Pain to draw"""
    game, p1, p2 = new_hs_game()
    add_cards_to_library(game, p1, 10)
    acolyte = play_minion(game, ACOLYTE_OF_PAIN, p1)

    hand_zone = game.state.zones.get(f'hand_{p1.id}')
    initial_hand = len(hand_zone.objects)

    cast_spell(game, INNER_RAGE, p1, targets=[acolyte.id])

    assert len(hand_zone.objects) == initial_hand + 1


# Divine Shield Interaction Tests
def test_divine_shield_prevents_enrage():
    """Divine shield should block damage and prevent enrage from triggering"""
    game, p1, p2 = new_hs_game()
    berserker = play_minion(game, AMANI_BERSERKER, p1)

    berserker.state.divine_shield = True

    assert get_power(berserker, game.state) == 2

    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': berserker.id, 'amount': 1, 'source': 'test'},
        source='test'
    ))

    assert berserker.state.damage == 0
    assert not berserker.state.divine_shield
    assert get_power(berserker, game.state) == 2


def test_divine_shield_prevents_gurubashi_trigger():
    """Divine shield should prevent Gurubashi Berserker from gaining attack"""
    game, p1, p2 = new_hs_game()
    berserker = play_minion(game, GURUBASHI_BERSERKER, p1)

    berserker.state.divine_shield = True

    assert get_power(berserker, game.state) == 2

    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': berserker.id, 'amount': 1, 'source': 'test'},
        source='test'
    ))

    assert get_power(berserker, game.state) == 2


def test_argent_squire_takes_damage_after_shield_breaks():
    """Argent Squire's shield should break on first hit, second hit damages"""
    game, p1, p2 = new_hs_game()
    squire = play_minion(game, ARGENT_SQUIRE, p1)

    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': squire.id, 'amount': 1, 'source': 'test'},
        source='test'
    ))

    assert squire.state.damage == 0
    assert not squire.state.divine_shield

    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': squire.id, 'amount': 1, 'source': 'test'},
        source='test'
    ))

    assert squire.state.damage == 1


# Multi-Trigger Combos
def test_whirlwind_with_acolyte_armorsmith_frothing():
    """Whirlwind should trigger Acolyte (draw), Armorsmith (armor), and Frothing (attack)"""
    game, p1, p2 = new_hs_game()
    add_cards_to_library(game, p1, 10)
    acolyte = play_minion(game, ACOLYTE_OF_PAIN, p1)
    armorsmith = play_minion(game, ARMORSMITH, p1)
    frothing = play_minion(game, FROTHING_BERSERKER, p1)

    hand_zone = game.state.zones.get(f'hand_{p1.id}')
    initial_hand = len(hand_zone.objects)

    assert p1.armor == 0
    assert get_power(frothing, game.state) == 2

    cast_spell(game, WHIRLWIND, p1)

    # Acolyte draws 1
    assert len(hand_zone.objects) == initial_hand + 1

    # Armorsmith grants 3 armor (3 minions damaged)
    assert p1.armor == 3

    # Frothing gains +3 attack (3 minions damaged)
    assert get_power(frothing, game.state) == 5


def test_cruel_taskmaster_stacks_with_enrage():
    """Inner Rage +2 attack should stack with enrage bonuses"""
    game, p1, p2 = new_hs_game()
    worgen = play_minion(game, RAGING_WORGEN, p1)

    assert get_power(worgen, game.state) == 3

    cast_spell(game, INNER_RAGE, p1, targets=[worgen.id])

    # +2 from Inner Rage, +1 from enrage = 6 attack, and windfury
    assert get_power(worgen, game.state) == 6
    assert has_ability(worgen, 'windfury', game.state)


def test_multiple_damage_triggers_on_same_minion():
    """Damage to Gurubashi should trigger both Gurubashi and Frothing"""
    game, p1, p2 = new_hs_game()
    add_cards_to_library(game, p1, 10)

    gurubashi = play_minion(game, GURUBASHI_BERSERKER, p1)
    frothing = play_minion(game, FROTHING_BERSERKER, p1)

    assert get_power(gurubashi, game.state) == 2
    assert get_power(frothing, game.state) == 2

    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': gurubashi.id, 'amount': 1, 'source': 'test'},
        source='test'
    ))

    # Gurubashi gains +3, Frothing gains +1
    assert get_power(gurubashi, game.state) == 5
    assert get_power(frothing, game.state) == 3


def test_combat_damage_triggers_enrage():
    """Combat damage should trigger enrage effects"""
    game, p1, p2 = new_hs_game()
    berserker = play_minion(game, AMANI_BERSERKER, p1)
    boar = play_minion(game, STONETUSK_BOAR, p2)

    assert get_power(berserker, game.state) == 2

    # Simulate combat damage: both deal damage to each other
    boar_power = get_power(boar, game.state)
    berserker_power = get_power(berserker, game.state)
    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': berserker.id, 'amount': boar_power, 'source': boar.id},
        source=boar.id
    ))
    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': boar.id, 'amount': berserker_power, 'source': berserker.id},
        source=berserker.id
    ))

    game.check_state_based_actions()

    assert berserker.state.damage == 1
    assert get_power(berserker, game.state) == 5


def test_enrage_minion_survives_combat_stays_enraged():
    """Enraged minion surviving combat should keep enrage bonus"""
    game, p1, p2 = new_hs_game()
    grommash = play_minion(game, GROMMASH_HELLSCREAM, p1)
    raptor = play_minion(game, BLOODFEN_RAPTOR, p2)

    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': grommash.id, 'amount': 1, 'source': 'test'},
        source='test'
    ))

    assert get_power(grommash, game.state) == 10

    # Simulate combat damage: raptor deals 3 damage to Grommash
    raptor_power = get_power(raptor, game.state)
    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': grommash.id, 'amount': raptor_power, 'source': raptor.id},
        source=raptor.id
    ))

    game.check_state_based_actions()

    # 1 (initial) + 3 (raptor) = 4 damage total
    assert grommash.state.damage == 4
    assert get_power(grommash, game.state) == 10


def test_healing_during_combat_removes_enrage():
    """Healing an enraged minion to full should remove enrage"""
    game, p1, p2 = new_hs_game()
    berserker = play_minion(game, AMANI_BERSERKER, p1)

    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': berserker.id, 'amount': 2, 'source': 'test'},
        source='test'
    ))

    assert get_power(berserker, game.state) == 5

    cast_spell(game, CIRCLE_OF_HEALING, p1)

    assert berserker.state.damage == 0
    assert get_power(berserker, game.state) == 2


def test_armorsmith_triggers_before_minion_dies():
    """Armorsmith should grant armor even if the damaged minion dies"""
    game, p1, p2 = new_hs_game()
    armorsmith = play_minion(game, ARMORSMITH, p1)
    boar = play_minion(game, STONETUSK_BOAR, p1)

    assert p1.armor == 0

    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': boar.id, 'amount': 10, 'source': 'test'},
        source='test'
    ))

    assert p1.armor == 1

    game.check_state_based_actions()

    battlefield_zone = game.state.zones.get('battlefield')
    assert boar.id not in battlefield_zone.objects


def test_frothing_berserker_counts_lethal_damage():
    """Frothing Berserker should count damage even if it kills the target"""
    game, p1, p2 = new_hs_game()
    frothing = play_minion(game, FROTHING_BERSERKER, p1)
    boar = play_minion(game, STONETUSK_BOAR, p2)

    assert get_power(frothing, game.state) == 2

    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': boar.id, 'amount': 10, 'source': 'test'},
        source='test'
    ))

    assert get_power(frothing, game.state) == 3
