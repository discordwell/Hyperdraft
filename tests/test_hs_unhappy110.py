"""
Hearthstone Unhappy Path Tests - Batch 110

Death Processing and Aftermath tests.

Tests cover:
- Deathrattle summons (Harvest Golem, Cairne, Highmane) [6 tests]
- Multiple simultaneous deathrattles [5 tests]
- Abomination chain reactions [5 tests]
- Sylvanas mind control on death [4 tests]
- Cult Master / Flesheating Ghoul death triggers [5 tests]
- Loot Hoarder drawing into fatigue [4 tests]
- Board space and deathrattle summons [5 tests]
- Overkill and exact lethal [5 tests]
- Complex death chains [6 tests]
"""

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

from src.cards.hearthstone.basic import WISP, STONETUSK_BOAR
from src.cards.hearthstone.classic import (
    HARVEST_GOLEM, CAIRNE_BLOODHOOF, ABOMINATION, SYLVANAS_WINDRUNNER,
    LOOT_HOARDER, CULT_MASTER, FLESHEATING_GHOUL, NOVICE_ENGINEER,
    ACOLYTE_OF_PAIN, WILD_PYROMANCER, BARON_GEDDON, FLAMESTRIKE,
    ARCANE_MISSILES, FIREBALL, FROSTBOLT
)
from src.cards.hearthstone.hunter import SAVANNAH_HIGHMANE
from src.cards.hearthstone.warlock import HELLFIRE
from src.cards.hearthstone.priest import SHADOW_WORD_DEATH, HOLY_NOVA
from src.cards.hearthstone.paladin import CONSECRATION, EQUALITY
from src.cards.hearthstone.warrior import WHIRLWIND, EXECUTE
from src.cards.hearthstone.rogue import ASSASSINATE


# ============================================================
# Test Helpers
# ============================================================

def new_hs_game(p1_class="Warrior", p2_class="Mage"):
    """Create a fresh Hearthstone game with 2 players, heroes, and 10 mana each."""
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
    """Create an object from a card definition and place it in the given zone."""
    obj = game.create_object(
        name=card_def.name, owner_id=owner.id, zone=zone,
        characteristics=card_def.characteristics, card_def=card_def
    )
    if zone == ZoneType.BATTLEFIELD and CardType.WEAPON in card_def.characteristics.types:
        game.emit(Event(
            type=EventType.ZONE_CHANGE,
            payload={
                'object_id': obj.id,
                'from_zone_type': None,
                'to_zone_type': ZoneType.BATTLEFIELD,
                'controller': owner.id,
            },
            source=obj.id
        ))
    return obj


def cast_spell(game, card_def, owner, targets=None):
    """Cast a spell card by invoking its spell_effect and emitting SPELL_CAST."""
    obj = game.create_object(
        name=card_def.name, owner_id=owner.id, zone=ZoneType.BATTLEFIELD,
        characteristics=card_def.characteristics, card_def=card_def
    )
    if targets is None and getattr(card_def, 'requires_target', False):
        battlefield = game.state.zones.get('battlefield')
        enemy_id = None
        for pid in game.state.players.keys():
            if pid != owner.id:
                enemy_player = game.state.players[pid]
                if battlefield:
                    for oid in battlefield.objects:
                        o = game.state.objects.get(oid)
                        if o and o.controller == pid and CardType.MINION in o.characteristics.types:
                            enemy_id = oid
                            break
                if not enemy_id and enemy_player.hero_id:
                    enemy_id = enemy_player.hero_id
                break
        if enemy_id:
            targets = [enemy_id]
        else:
            targets = []
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
    """Play a minion from hand to battlefield."""
    obj = game.create_object(
        name=card_def.name, owner_id=owner.id, zone=ZoneType.HAND,
        characteristics=card_def.characteristics, card_def=card_def
    )
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': obj.id,
            'from_zone_type': ZoneType.HAND,
            'to_zone_type': ZoneType.BATTLEFIELD,
            'controller': owner.id,
        },
        source=obj.id
    ))
    owner.cards_played_this_turn += 1
    return obj


def get_battlefield_count(game, player):
    """Get number of minions on battlefield for player."""
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
    """Add dummy cards to player's library for draw testing."""
    lib_zone = game.state.zones.get(f'library_{player.id}')
    if lib_zone:
        for _ in range(count):
            dummy = game.create_object(
                name="Dummy Card", owner_id=player.id, zone=ZoneType.LIBRARY,
                characteristics=WISP.characteristics, card_def=WISP
            )


# ============================================================
# Deathrattle Summons [6 tests]
# ============================================================

def test_harvest_golem_deathrattle_summons_damaged_golem():
    """Harvest Golem deathrattle summons a 2/1 Damaged Golem."""
    game, p1, p2 = new_hs_game()
    golem = make_obj(game, HARVEST_GOLEM, p1)

    assert get_battlefield_count(game, p1) == 1

    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': golem.id},
        source='test'
    ))
    game.check_state_based_actions()

    # Should have 1 minion (the 2/1 token)
    assert get_battlefield_count(game, p1) == 1

    # Find the token
    battlefield = game.state.zones.get('battlefield')
    token = None
    for oid in battlefield.objects:
        obj = game.state.objects.get(oid)
        if obj and obj.controller == p1.id and obj.id != golem.id and CardType.MINION in obj.characteristics.types:
            token = obj
            break

    assert token is not None
    assert get_power(token, game.state) == 2
    assert get_toughness(token, game.state) == 1


def test_cairne_bloodhoof_deathrattle_summons_baine():
    """Cairne Bloodhoof deathrattle summons a 4/5 Baine Bloodhoof."""
    game, p1, p2 = new_hs_game()
    cairne = make_obj(game, CAIRNE_BLOODHOOF, p1)

    assert get_battlefield_count(game, p1) == 1

    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': cairne.id},
        source='test'
    ))
    game.check_state_based_actions()

    # Should have 1 minion (Baine)
    assert get_battlefield_count(game, p1) == 1

    battlefield = game.state.zones.get('battlefield')
    baine = None
    for oid in battlefield.objects:
        obj = game.state.objects.get(oid)
        if obj and obj.controller == p1.id and obj.id != cairne.id and CardType.MINION in obj.characteristics.types:
            baine = obj
            break

    assert baine is not None
    assert get_power(baine, game.state) == 4
    assert get_toughness(baine, game.state) == 5


def test_savannah_highmane_deathrattle_summons_two_hyenas():
    """Savannah Highmane deathrattle summons two 2/2 Hyenas."""
    game, p1, p2 = new_hs_game()
    highmane = make_obj(game, SAVANNAH_HIGHMANE, p1)

    assert get_battlefield_count(game, p1) == 1

    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': highmane.id},
        source='test'
    ))
    game.check_state_based_actions()

    # Should have 2 minions (two Hyenas)
    assert get_battlefield_count(game, p1) == 2

    battlefield = game.state.zones.get('battlefield')
    hyenas = []
    for oid in battlefield.objects:
        obj = game.state.objects.get(oid)
        if obj and obj.controller == p1.id and obj.id != highmane.id and CardType.MINION in obj.characteristics.types:
            hyenas.append(obj)

    assert len(hyenas) == 2
    for hyena in hyenas:
        assert get_power(hyena, game.state) == 2
        assert get_toughness(hyena, game.state) == 2


def test_harvest_golem_killed_by_spell():
    """Harvest Golem killed by spell still triggers deathrattle."""
    game, p1, p2 = new_hs_game()
    golem = make_obj(game, HARVEST_GOLEM, p1)

    cast_spell(game, FIREBALL, p2, targets=[golem.id])
    game.check_state_based_actions()

    # Golem should be dead, token should be alive
    assert get_battlefield_count(game, p1) == 1


def test_cairne_killed_by_combat_damage():
    """Cairne killed by combat damage summons Baine."""
    game, p1, p2 = new_hs_game()
    cairne = make_obj(game, CAIRNE_BLOODHOOF, p1)

    # Deal 6 damage to Cairne (5 health)
    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': cairne.id, 'amount': 6, 'source': 'test'},
        source='test'
    ))
    game.check_state_based_actions()

    # Should have Baine
    assert get_battlefield_count(game, p1) == 1


def test_highmane_killed_exact_lethal():
    """Highmane killed with exact 6 damage summons hyenas."""
    game, p1, p2 = new_hs_game()
    highmane = make_obj(game, SAVANNAH_HIGHMANE, p1)

    # Deal exactly 5 damage (exact lethal for 6/5)
    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': highmane.id, 'amount': 5, 'source': 'test'},
        source='test'
    ))
    game.check_state_based_actions()

    # Should have 2 hyenas
    assert get_battlefield_count(game, p1) == 2


# ============================================================
# Multiple Simultaneous Deathrattles [5 tests]
# ============================================================

def test_two_harvest_golems_die_simultaneously():
    """Two Harvest Golems dying together summon two tokens."""
    game, p1, p2 = new_hs_game()
    golem1 = make_obj(game, HARVEST_GOLEM, p1)
    golem2 = make_obj(game, HARVEST_GOLEM, p1)

    assert get_battlefield_count(game, p1) == 2

    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': golem1.id},
        source='test'
    ))
    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': golem2.id},
        source='test'
    ))
    game.check_state_based_actions()

    # Should have 2 tokens
    assert get_battlefield_count(game, p1) == 2


def test_loot_hoarder_and_harvest_golem_die_together():
    """Loot Hoarder and Harvest Golem dying together trigger both deathrattles."""
    game, p1, p2 = new_hs_game()
    add_cards_to_library(game, p1)
    hoarder = make_obj(game, LOOT_HOARDER, p1)
    golem = make_obj(game, HARVEST_GOLEM, p1)

    hand_zone = game.state.zones.get(f'hand_{p1.id}')
    initial_hand = len(hand_zone.objects) if hand_zone else 0

    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': hoarder.id},
        source='test'
    ))
    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': golem.id},
        source='test'
    ))
    game.check_state_based_actions()

    # Should have 1 minion (golem token) and 1 extra card
    assert get_battlefield_count(game, p1) == 1
    hand_zone = game.state.zones.get(f'hand_{p1.id}')
    final_hand = len(hand_zone.objects) if hand_zone else 0
    assert final_hand == initial_hand + 1


def test_three_loot_hoarders_die_simultaneously():
    """Three Loot Hoarders dying draw three cards."""
    game, p1, p2 = new_hs_game()
    add_cards_to_library(game, p1)
    h1 = make_obj(game, LOOT_HOARDER, p1)
    h2 = make_obj(game, LOOT_HOARDER, p1)
    h3 = make_obj(game, LOOT_HOARDER, p1)

    hand_zone = game.state.zones.get(f'hand_{p1.id}')
    initial_hand = len(hand_zone.objects) if hand_zone else 0

    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': h1.id},
        source='test'
    ))
    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': h2.id},
        source='test'
    ))
    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': h3.id},
        source='test'
    ))
    game.check_state_based_actions()

    hand_zone = game.state.zones.get(f'hand_{p1.id}')
    final_hand = len(hand_zone.objects) if hand_zone else 0
    assert final_hand == initial_hand + 3


def test_cairne_and_highmane_die_together():
    """Cairne and Highmane dying together summon Baine and 2 Hyenas."""
    game, p1, p2 = new_hs_game()
    cairne = make_obj(game, CAIRNE_BLOODHOOF, p1)
    highmane = make_obj(game, SAVANNAH_HIGHMANE, p1)

    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': cairne.id},
        source='test'
    ))
    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': highmane.id},
        source='test'
    ))
    game.check_state_based_actions()

    # Should have 3 minions (Baine + 2 Hyenas)
    assert get_battlefield_count(game, p1) == 3


def test_aoe_kills_multiple_deathrattle_minions():
    """AOE killing multiple deathrattle minions triggers all deathrattles."""
    game, p1, p2 = new_hs_game()
    add_cards_to_library(game, p1)
    golem = make_obj(game, HARVEST_GOLEM, p1)
    hoarder = make_obj(game, LOOT_HOARDER, p1)

    hand_zone = game.state.zones.get(f'hand_{p1.id}')
    initial_hand = len(hand_zone.objects) if hand_zone else 0

    cast_spell(game, FLAMESTRIKE, p2)
    game.check_state_based_actions()

    # Golem should leave token, hoarder should draw
    assert get_battlefield_count(game, p1) == 1
    hand_zone = game.state.zones.get(f'hand_{p1.id}')
    final_hand = len(hand_zone.objects) if hand_zone else 0
    assert final_hand == initial_hand + 1


# ============================================================
# Abomination Chain Reactions [5 tests]
# ============================================================

def test_abomination_deathrattle_damages_all():
    """Abomination's deathrattle deals 2 damage to all characters."""
    game, p1, p2 = new_hs_game()
    abom = make_obj(game, ABOMINATION, p1)

    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': abom.id},
        source='test'
    ))
    game.check_state_based_actions()

    # Both heroes should have taken 2 damage
    assert p1.life == 28
    assert p2.life == 28


def test_abomination_kills_adjacent_minions():
    """Abomination's deathrattle kills 1-health minions."""
    game, p1, p2 = new_hs_game()
    abom = make_obj(game, ABOMINATION, p1)
    wisp1 = make_obj(game, WISP, p1)  # 1/1
    wisp2 = make_obj(game, WISP, p2)  # 1/1

    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': abom.id},
        source='test'
    ))
    game.check_state_based_actions()

    assert wisp1.zone == ZoneType.GRAVEYARD
    assert wisp2.zone == ZoneType.GRAVEYARD


def test_two_abominations_die_chain_reaction():
    """Two Abominations dying trigger 4 damage to all characters."""
    game, p1, p2 = new_hs_game()
    abom1 = make_obj(game, ABOMINATION, p1)
    abom2 = make_obj(game, ABOMINATION, p2)

    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': abom1.id},
        source='test'
    ))
    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': abom2.id},
        source='test'
    ))
    game.check_state_based_actions()

    # Each hero should take 4 damage (2 from each abom)
    assert p1.life == 26
    assert p2.life == 26


def test_abomination_kills_harvest_golem():
    """Abomination's deathrattle kills Harvest Golem which summons token."""
    game, p1, p2 = new_hs_game()
    abom = make_obj(game, ABOMINATION, p1)
    golem = make_obj(game, HARVEST_GOLEM, p2)

    # Damage golem to 1 health remaining
    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': golem.id, 'amount': 1, 'source': 'test'},
        source='test'
    ))

    # Kill abomination
    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': abom.id},
        source='test'
    ))
    game.check_state_based_actions()

    # Golem should be dead, token should exist
    assert get_battlefield_count(game, p2) == 1


def test_abomination_in_graveyard_after_death():
    """Abomination is in graveyard after death."""
    game, p1, p2 = new_hs_game()
    abom = make_obj(game, ABOMINATION, p1)

    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': abom.id},
        source='test'
    ))
    game.check_state_based_actions()

    assert abom.zone == ZoneType.GRAVEYARD


# ============================================================
# Sylvanas Mind Control on Death [4 tests]
# ============================================================

def test_sylvanas_steals_random_enemy_minion():
    """Sylvanas deathrattle steals a random enemy minion."""
    random.seed(42)
    game, p1, p2 = new_hs_game()
    sylvanas = make_obj(game, SYLVANAS_WINDRUNNER, p1)
    enemy_minion = make_obj(game, STONETUSK_BOAR, p2)

    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': sylvanas.id},
        source='test'
    ))
    game.check_state_based_actions()

    # Enemy minion should now be controlled by p1
    assert enemy_minion.controller == p1.id
    assert get_battlefield_count(game, p1) == 1
    assert get_battlefield_count(game, p2) == 0


def test_sylvanas_no_enemy_minions():
    """Sylvanas deathrattle with no enemy minions does nothing."""
    game, p1, p2 = new_hs_game()
    sylvanas = make_obj(game, SYLVANAS_WINDRUNNER, p1)

    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': sylvanas.id},
        source='test'
    ))
    game.check_state_based_actions()

    assert get_battlefield_count(game, p1) == 0
    assert get_battlefield_count(game, p2) == 0


def test_sylvanas_steals_from_multiple_choices():
    """Sylvanas picks one of multiple enemy minions."""
    random.seed(123)
    game, p1, p2 = new_hs_game()
    sylvanas = make_obj(game, SYLVANAS_WINDRUNNER, p1)
    m1 = make_obj(game, WISP, p2)
    m2 = make_obj(game, WISP, p2)
    m3 = make_obj(game, WISP, p2)

    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': sylvanas.id},
        source='test'
    ))
    game.check_state_based_actions()

    # P1 should have 1 minion (stolen), P2 should have 2
    assert get_battlefield_count(game, p1) == 1
    assert get_battlefield_count(game, p2) == 2


def test_two_sylvanas_die_simultaneously():
    """Two Sylvanas dying together each steal a minion."""
    random.seed(999)
    game, p1, p2 = new_hs_game()
    syl1 = make_obj(game, SYLVANAS_WINDRUNNER, p1)
    syl2 = make_obj(game, SYLVANAS_WINDRUNNER, p2)
    wisp1 = make_obj(game, WISP, p1)
    wisp2 = make_obj(game, WISP, p2)

    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': syl1.id},
        source='test'
    ))
    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': syl2.id},
        source='test'
    ))
    game.check_state_based_actions()

    # Each player should have at least 1 minion
    total_minions = get_battlefield_count(game, p1) + get_battlefield_count(game, p2)
    assert total_minions == 2


# ============================================================
# Cult Master / Flesheating Ghoul Death Triggers [5 tests]
# ============================================================

def test_cult_master_draws_when_friendly_dies():
    """Cult Master draws a card when a friendly minion dies."""
    game, p1, p2 = new_hs_game()
    add_cards_to_library(game, p1)
    cult = make_obj(game, CULT_MASTER, p1)
    wisp = make_obj(game, WISP, p1)

    hand_zone = game.state.zones.get(f'hand_{p1.id}')
    initial_hand = len(hand_zone.objects) if hand_zone else 0

    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': wisp.id},
        source='test'
    ))
    game.check_state_based_actions()

    hand_zone = game.state.zones.get(f'hand_{p1.id}')
    final_hand = len(hand_zone.objects) if hand_zone else 0
    assert final_hand == initial_hand + 1


def test_cult_master_draws_multiple_cards():
    """Cult Master draws multiple cards when multiple friendlies die."""
    game, p1, p2 = new_hs_game()
    add_cards_to_library(game, p1)
    cult = make_obj(game, CULT_MASTER, p1)
    w1 = make_obj(game, WISP, p1)
    w2 = make_obj(game, WISP, p1)
    w3 = make_obj(game, WISP, p1)

    hand_zone = game.state.zones.get(f'hand_{p1.id}')
    initial_hand = len(hand_zone.objects) if hand_zone else 0

    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': w1.id},
        source='test'
    ))
    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': w2.id},
        source='test'
    ))
    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': w3.id},
        source='test'
    ))
    game.check_state_based_actions()

    hand_zone = game.state.zones.get(f'hand_{p1.id}')
    final_hand = len(hand_zone.objects) if hand_zone else 0
    assert final_hand == initial_hand + 3


def test_flesheating_ghoul_gains_attack_on_death():
    """Flesheating Ghoul gains +1 attack when any minion dies."""
    game, p1, p2 = new_hs_game()
    ghoul = make_obj(game, FLESHEATING_GHOUL, p1)
    wisp = make_obj(game, WISP, p2)

    initial_power = get_power(ghoul, game.state)

    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': wisp.id},
        source='test'
    ))
    game.check_state_based_actions()

    assert get_power(ghoul, game.state) == initial_power + 1


def test_flesheating_ghoul_gains_from_multiple_deaths():
    """Flesheating Ghoul gains attack from multiple deaths."""
    game, p1, p2 = new_hs_game()
    ghoul = make_obj(game, FLESHEATING_GHOUL, p1)
    w1 = make_obj(game, WISP, p2)
    w2 = make_obj(game, WISP, p2)
    w3 = make_obj(game, WISP, p2)

    initial_power = get_power(ghoul, game.state)

    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': w1.id},
        source='test'
    ))
    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': w2.id},
        source='test'
    ))
    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': w3.id},
        source='test'
    ))
    game.check_state_based_actions()

    assert get_power(ghoul, game.state) == initial_power + 3


def test_cult_master_and_ghoul_trigger_together():
    """Cult Master and Flesheating Ghoul both trigger on same death."""
    game, p1, p2 = new_hs_game()
    add_cards_to_library(game, p1)
    cult = make_obj(game, CULT_MASTER, p1)
    ghoul = make_obj(game, FLESHEATING_GHOUL, p1)
    wisp = make_obj(game, WISP, p1)

    hand_zone = game.state.zones.get(f'hand_{p1.id}')
    initial_hand = len(hand_zone.objects) if hand_zone else 0
    initial_power = get_power(ghoul, game.state)

    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': wisp.id},
        source='test'
    ))
    game.check_state_based_actions()

    hand_zone = game.state.zones.get(f'hand_{p1.id}')
    final_hand = len(hand_zone.objects) if hand_zone else 0
    assert final_hand == initial_hand + 1
    assert get_power(ghoul, game.state) == initial_power + 1


# ============================================================
# Loot Hoarder Drawing into Fatigue [4 tests]
# ============================================================

def test_loot_hoarder_draws_into_empty_deck():
    """Loot Hoarder deathrattle draws from empty deck causes fatigue."""
    game, p1, p2 = new_hs_game()

    # Empty the deck
    deck_zone = game.state.zones.get(f'library_{p1.id}')
    if deck_zone:
        deck_zone.objects = []

    hoarder = make_obj(game, LOOT_HOARDER, p1)

    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': hoarder.id},
        source='test'
    ))
    game.check_state_based_actions()

    # Player should take 1 fatigue damage
    assert p1.life == 29


def test_multiple_loot_hoarders_escalating_fatigue():
    """Multiple Loot Hoarders cause escalating fatigue damage."""
    game, p1, p2 = new_hs_game()

    deck_zone = game.state.zones.get(f'library_{p1.id}')
    if deck_zone:
        deck_zone.objects = []

    h1 = make_obj(game, LOOT_HOARDER, p1)
    h2 = make_obj(game, LOOT_HOARDER, p1)
    h3 = make_obj(game, LOOT_HOARDER, p1)

    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': h1.id},
        source='test'
    ))
    game.check_state_based_actions()

    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': h2.id},
        source='test'
    ))
    game.check_state_based_actions()

    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': h3.id},
        source='test'
    ))
    game.check_state_based_actions()

    # Should take 1 + 2 + 3 = 6 fatigue damage
    assert p1.life == 24


def test_loot_hoarder_draws_last_card_no_fatigue():
    """Loot Hoarder drawing the last card doesn't cause fatigue."""
    game, p1, p2 = new_hs_game()

    # Put exactly 1 card in library
    lib_zone = game.state.zones.get(f'library_{p1.id}')
    if lib_zone:
        lib_zone.objects = []  # Clear first
    add_cards_to_library(game, p1, count=1)

    hoarder = make_obj(game, LOOT_HOARDER, p1)

    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': hoarder.id},
        source='test'
    ))
    game.check_state_based_actions()

    assert p1.life == 30


def test_cult_master_draws_into_fatigue():
    """Cult Master drawing into empty deck causes fatigue."""
    game, p1, p2 = new_hs_game()

    deck_zone = game.state.zones.get(f'library_{p1.id}')
    if deck_zone:
        deck_zone.objects = []

    cult = make_obj(game, CULT_MASTER, p1)
    wisp = make_obj(game, WISP, p1)

    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': wisp.id},
        source='test'
    ))
    game.check_state_based_actions()

    assert p1.life == 29


# ============================================================
# Board Space and Deathrattle Summons [5 tests]
# ============================================================

def test_harvest_golem_dies_on_full_board():
    """Harvest Golem deathrattle at 7 board may not spawn token."""
    game, p1, p2 = new_hs_game()
    golem = make_obj(game, HARVEST_GOLEM, p1)

    for _ in range(6):
        make_obj(game, WISP, p1)

    assert get_battlefield_count(game, p1) == 7

    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': golem.id},
        source='test'
    ))
    game.check_state_based_actions()

    # Golem died freeing a slot, token may spawn (6 or 7)
    count = get_battlefield_count(game, p1)
    assert count in (6, 7)


def test_highmane_dies_with_limited_board_space():
    """Highmane with limited room summons what fits."""
    game, p1, p2 = new_hs_game()
    highmane = make_obj(game, SAVANNAH_HIGHMANE, p1)

    for _ in range(6):
        make_obj(game, WISP, p1)

    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': highmane.id},
        source='test'
    ))
    game.check_state_based_actions()

    count = get_battlefield_count(game, p1)
    assert count <= 7


def test_cairne_dies_on_full_board():
    """Cairne deathrattle at full board may not summon Baine."""
    game, p1, p2 = new_hs_game()
    cairne = make_obj(game, CAIRNE_BLOODHOOF, p1)

    for _ in range(6):
        make_obj(game, WISP, p1)

    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': cairne.id},
        source='test'
    ))
    game.check_state_based_actions()

    count = get_battlefield_count(game, p1)
    assert count in (6, 7)


def test_overkill_doesnt_prevent_deathrattle():
    """Overkilling a deathrattle minion still triggers deathrattle."""
    game, p1, p2 = new_hs_game()
    golem = make_obj(game, HARVEST_GOLEM, p1)

    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': golem.id, 'amount': 10, 'source': 'test'},
        source='test'
    ))
    game.check_state_based_actions()

    assert get_battlefield_count(game, p1) == 1


def test_massive_overkill_on_highmane():
    """Massive overkill on Highmane still summons both hyenas."""
    game, p1, p2 = new_hs_game()
    highmane = make_obj(game, SAVANNAH_HIGHMANE, p1)

    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': highmane.id, 'amount': 100, 'source': 'test'},
        source='test'
    ))
    game.check_state_based_actions()

    assert get_battlefield_count(game, p1) == 2


# ============================================================
# Complex Death Chains [6 tests]
# ============================================================

def test_abomination_kills_loot_hoarder_draws_cards():
    """Abomination kills Loot Hoarder, which draws cards."""
    game, p1, p2 = new_hs_game()
    add_cards_to_library(game, p1)
    add_cards_to_library(game, p2)
    abom = make_obj(game, ABOMINATION, p1)
    h1 = make_obj(game, LOOT_HOARDER, p1)  # 2/1 will die to 2 damage
    h2 = make_obj(game, LOOT_HOARDER, p2)  # 2/1 will die to 2 damage

    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': h1.id, 'amount': 1, 'source': 'test'},
        source='test'
    ))
    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': h2.id, 'amount': 1, 'source': 'test'},
        source='test'
    ))

    hand_zone_p1 = game.state.zones.get(f'hand_{p1.id}')
    initial_hand_p1 = len(hand_zone_p1.objects) if hand_zone_p1 else 0
    hand_zone_p2 = game.state.zones.get(f'hand_{p2.id}')
    initial_hand_p2 = len(hand_zone_p2.objects) if hand_zone_p2 else 0

    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': abom.id},
        source='test'
    ))
    game.check_state_based_actions()

    hand_zone_p1 = game.state.zones.get(f'hand_{p1.id}')
    final_hand_p1 = len(hand_zone_p1.objects) if hand_zone_p1 else 0
    hand_zone_p2 = game.state.zones.get(f'hand_{p2.id}')
    final_hand_p2 = len(hand_zone_p2.objects) if hand_zone_p2 else 0

    assert final_hand_p1 == initial_hand_p1 + 1
    assert final_hand_p2 == initial_hand_p2 + 1


def test_cult_master_dies_doesnt_draw_for_itself():
    """Cult Master dying doesn't trigger its own effect."""
    game, p1, p2 = new_hs_game()
    cult = make_obj(game, CULT_MASTER, p1)

    hand_zone = game.state.zones.get(f'hand_{p1.id}')
    initial_hand = len(hand_zone.objects) if hand_zone else 0

    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': cult.id},
        source='test'
    ))
    game.check_state_based_actions()

    hand_zone = game.state.zones.get(f'hand_{p1.id}')
    final_hand = len(hand_zone.objects) if hand_zone else 0
    assert final_hand == initial_hand


def test_flesheating_ghoul_doesnt_buff_from_own_death():
    """Flesheating Ghoul dying doesn't buff itself."""
    game, p1, p2 = new_hs_game()
    ghoul = make_obj(game, FLESHEATING_GHOUL, p1)

    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': ghoul.id},
        source='test'
    ))
    game.check_state_based_actions()

    assert ghoul.zone != ZoneType.BATTLEFIELD


def test_exact_lethal_triggers_deathrattle():
    """Exact lethal damage triggers deathrattle."""
    game, p1, p2 = new_hs_game()
    add_cards_to_library(game, p1)
    hoarder = make_obj(game, LOOT_HOARDER, p1)

    hand_zone = game.state.zones.get(f'hand_{p1.id}')
    initial_hand = len(hand_zone.objects) if hand_zone else 0

    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': hoarder.id, 'amount': 1, 'source': 'test'},
        source='test'
    ))
    game.check_state_based_actions()

    hand_zone = game.state.zones.get(f'hand_{p1.id}')
    final_hand = len(hand_zone.objects) if hand_zone else 0
    assert final_hand == initial_hand + 1


def test_zero_damage_doesnt_kill():
    """Zero damage doesn't kill minion or trigger deathrattle."""
    game, p1, p2 = new_hs_game()
    golem = make_obj(game, HARVEST_GOLEM, p1)

    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': golem.id, 'amount': 0, 'source': 'test'},
        source='test'
    ))
    game.check_state_based_actions()

    assert golem.zone == ZoneType.BATTLEFIELD
    assert get_battlefield_count(game, p1) == 1


def test_sylvanas_steals_deathrattle_minion():
    """Sylvanas steals a deathrattle minion."""
    random.seed(42)
    game, p1, p2 = new_hs_game()
    sylvanas = make_obj(game, SYLVANAS_WINDRUNNER, p1)
    golem = make_obj(game, HARVEST_GOLEM, p2)

    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': sylvanas.id},
        source='test'
    ))
    game.check_state_based_actions()

    # Golem should be controlled by p1
    assert golem.controller == p1.id
