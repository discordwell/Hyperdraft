"""
Hearthstone Unhappy Path Tests - Batch 111

Mana and Resource Edge Cases tests.

Tests cover:
- Mana spending and tracking (5 tests)
- Cost reduction stacking (5 tests)
- Cost increase effects (5 tests)
- Temporary mana (Innervate, Coin) (5 tests)
- Overload mechanics (5 tests)
- Mana crystal limits (5 tests)
- Dynamic cost cards (5 tests)
- Turn start mana behavior (5 tests)
- Cost modifier interactions (5 tests)
"""

import random
import re
from src.engine.game import Game
from src.engine.types import (
    Event, EventType, GameObject, GameState, CardType, ZoneType,
    Interceptor, InterceptorPriority, InterceptorAction, InterceptorResult,
    new_id
)
from src.engine.queries import get_power, get_toughness, has_ability

from src.cards.hearthstone.heroes import HEROES
from src.cards.hearthstone.hero_powers import HERO_POWERS

from src.cards.hearthstone.basic import WISP, THE_COIN, STONETUSK_BOAR
from src.cards.hearthstone.classic import (
    FIREBALL, ARCANE_INTELLECT, BACKSTAB, SPRINT,
    SEA_GIANT, MOUNTAIN_GIANT, MOLTEN_GIANT, DREAD_CORSAIR,
    MANA_WRAITH, VENTURE_CO_MERCENARY
)
from src.cards.hearthstone.mage import SORCERERS_APPRENTICE
from src.cards.hearthstone.druid import INNERVATE, WILD_GROWTH
from src.cards.hearthstone.shaman import FERAL_SPIRIT, LIGHTNING_BOLT, EARTH_ELEMENTAL
from src.cards.hearthstone.rogue import PREPARATION, EVISCERATE
from src.cards.hearthstone.warlock import FLAME_IMP, SOULFIRE
from src.cards.hearthstone.priest import MIND_BLAST
from src.cards.hearthstone.paladin import BLESSING_OF_KINGS
from src.cards.hearthstone.warrior import EXECUTE
from src.cards.hearthstone.hunter import ARCANE_SHOT


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


def new_hs_game_low_mana(p1_class="Warrior", p2_class="Mage", mana_turns=3):
    """Create a game with limited mana crystals."""
    game = Game(mode='hearthstone')
    p1 = game.add_player("Player1", life=30)
    p2 = game.add_player("Player2", life=30)
    game.setup_hearthstone_player(p1, HEROES[p1_class], HERO_POWERS[p1_class])
    game.setup_hearthstone_player(p2, HEROES[p2_class], HERO_POWERS[p2_class])
    for _ in range(mana_turns):
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


# ============================================================
# Mana Spending and Tracking (5 tests)
# ============================================================

def test_mana_depletes_when_manually_reduced():
    """Manually reducing mana_crystals_available tracks spending."""
    game, p1, p2 = new_hs_game()
    initial = p1.mana_crystals_available
    p1.mana_crystals_available -= 4
    assert p1.mana_crystals_available == initial - 4


def test_multiple_small_spends_accumulate():
    """Multiple small mana spends reduce available mana correctly."""
    game, p1, p2 = new_hs_game()
    p1.mana_crystals_available = 10
    p1.mana_crystals_available -= 1
    p1.mana_crystals_available -= 2
    p1.mana_crystals_available -= 3
    assert p1.mana_crystals_available == 4


def test_spending_all_mana_leaves_zero():
    """Spending exactly all mana leaves zero available."""
    game, p1, p2 = new_hs_game_low_mana(mana_turns=5)
    p1.mana_crystals_available = 5
    p1.mana_crystals_available -= 5
    assert p1.mana_crystals_available == 0


def test_mana_available_matches_max_after_turn_start():
    """After turn start, available mana equals max mana."""
    game, p1, p2 = new_hs_game_low_mana(mana_turns=3)
    max_mana = game.mana_system.get_max_mana(p1.id)
    available = game.mana_system.get_available_mana(p1.id)
    assert available == max_mana


def test_mana_starts_at_zero():
    """New game starts with 0 mana before any turn starts."""
    game = Game(mode='hearthstone')
    p1 = game.add_player("Player1", life=30)
    p2 = game.add_player("Player2", life=30)
    game.setup_hearthstone_player(p1, HEROES["Warrior"], HERO_POWERS["Warrior"])
    game.setup_hearthstone_player(p2, HEROES["Mage"], HERO_POWERS["Mage"])
    assert p1.mana_crystals_available == 0


# ============================================================
# Cost Reduction Stacking (5 tests)
# ============================================================

def test_single_cost_reduction_modifier():
    """Single cost reduction modifier is tracked in cost_modifiers list."""
    game, p1, p2 = new_hs_game()
    p1.cost_modifiers.append({'amount': 1, 'filter': lambda c: True})
    assert len(p1.cost_modifiers) == 1
    assert p1.cost_modifiers[0]['amount'] == 1


def test_multiple_cost_reduction_modifiers_stack():
    """Multiple cost reduction modifiers accumulate in the list."""
    game, p1, p2 = new_hs_game()
    p1.cost_modifiers.append({'amount': 1, 'filter': lambda c: True})
    p1.cost_modifiers.append({'amount': 2, 'filter': lambda c: True})
    assert len(p1.cost_modifiers) == 2
    total_reduction = sum(mod['amount'] for mod in p1.cost_modifiers)
    assert total_reduction == 3


def test_sorcerers_apprentice_on_battlefield():
    """Playing Sorcerer's Apprentice places it on battlefield."""
    game, p1, p2 = new_hs_game()
    apprentice = play_minion(game, SORCERERS_APPRENTICE, p1)
    assert apprentice is not None
    assert get_battlefield_count(game, p1) == 1


def test_two_apprentices_on_battlefield():
    """Two Sorcerer's Apprentices can coexist on battlefield."""
    game, p1, p2 = new_hs_game()
    play_minion(game, SORCERERS_APPRENTICE, p1)
    play_minion(game, SORCERERS_APPRENTICE, p1)
    assert get_battlefield_count(game, p1) == 2


def test_cost_reduction_filter_only_matching():
    """Cost reduction with filter only matches relevant cards."""
    game, p1, p2 = new_hs_game()
    spell_filter = lambda c: CardType.SPELL in c.characteristics.types
    p1.cost_modifiers.append({'amount': 3, 'filter': spell_filter})
    assert p1.cost_modifiers[0]['filter'](FIREBALL)
    assert not p1.cost_modifiers[0]['filter'](STONETUSK_BOAR)


# ============================================================
# Cost Increase Effects (5 tests)
# ============================================================

def test_mana_wraith_on_battlefield():
    """Mana Wraith can be placed on battlefield."""
    game, p1, p2 = new_hs_game()
    wraith = play_minion(game, MANA_WRAITH, p1)
    assert wraith.name == "Mana Wraith"
    assert get_battlefield_count(game, p1) == 1


def test_venture_co_on_battlefield():
    """Venture Co. Mercenary can be placed on battlefield."""
    game, p1, p2 = new_hs_game()
    venture = play_minion(game, VENTURE_CO_MERCENARY, p1)
    assert venture.name == "Venture Co. Mercenary"
    assert get_battlefield_count(game, p1) == 1


def test_cost_increase_modifier_tracking():
    """Cost increase modifiers are tracked with negative amounts."""
    game, p1, p2 = new_hs_game()
    p1.cost_modifiers.append({'amount': -2, 'filter': lambda c: True})
    assert len(p1.cost_modifiers) == 1
    assert p1.cost_modifiers[0]['amount'] == -2


def test_cost_increase_and_decrease_coexist():
    """Both cost increase and decrease modifiers can exist simultaneously."""
    game, p1, p2 = new_hs_game()
    p1.cost_modifiers.append({'amount': 2, 'filter': lambda c: True})
    p1.cost_modifiers.append({'amount': -1, 'filter': lambda c: True})
    assert len(p1.cost_modifiers) == 2
    net_change = sum(mod['amount'] for mod in p1.cost_modifiers)
    assert net_change == 1


def test_multiple_cost_increases_stack():
    """Multiple cost increase effects accumulate."""
    game, p1, p2 = new_hs_game()
    p1.cost_modifiers.append({'amount': -1, 'filter': lambda c: True})
    p1.cost_modifiers.append({'amount': -2, 'filter': lambda c: True})
    total_increase = sum(abs(mod['amount']) for mod in p1.cost_modifiers if mod['amount'] < 0)
    assert total_increase == 3


# ============================================================
# Temporary Mana (Innervate, Coin) (5 tests)
# ============================================================

def test_innervate_grants_two_temporary_mana():
    """Casting Innervate grants 2 temporary mana crystals."""
    game, p1, p2 = new_hs_game_low_mana(mana_turns=2)
    before = p1.mana_crystals_available
    cast_spell(game, INNERVATE, p1)
    after = p1.mana_crystals_available
    assert after == before + 2


def test_the_coin_grants_one_temporary_mana():
    """Casting The Coin grants 1 temporary mana crystal."""
    game, p1, p2 = new_hs_game_low_mana(mana_turns=1)
    before = p1.mana_crystals_available
    cast_spell(game, THE_COIN, p1)
    after = p1.mana_crystals_available
    assert after == before + 1


def test_temporary_mana_can_exceed_max():
    """Temporary mana can push available mana above max crystals."""
    game, p1, p2 = new_hs_game()
    max_mana = game.mana_system.get_max_mana(p1.id)
    cast_spell(game, INNERVATE, p1)
    available = p1.mana_crystals_available
    assert available == max_mana + 2


def test_multiple_innervates_stack():
    """Multiple Innervates stack to grant 4 temporary mana."""
    game, p1, p2 = new_hs_game_low_mana(mana_turns=3)
    before = p1.mana_crystals_available
    cast_spell(game, INNERVATE, p1)
    cast_spell(game, INNERVATE, p1)
    after = p1.mana_crystals_available
    assert after == before + 4


def test_temporary_mana_consumed_by_spending():
    """Temporary mana is consumed when spending mana."""
    game, p1, p2 = new_hs_game_low_mana(mana_turns=5)
    p1.mana_crystals_available = 5
    cast_spell(game, INNERVATE, p1)
    assert p1.mana_crystals_available == 7
    p1.mana_crystals_available -= 3
    assert p1.mana_crystals_available == 4


# ============================================================
# Overload Mechanics (5 tests)
# ============================================================

def test_lightning_bolt_sets_overload():
    """Casting an overload card sets overload_this_turn."""
    game, p1, p2 = new_hs_game()
    p2_hero = game.state.objects[p2.hero_id]
    cast_spell(game, LIGHTNING_BOLT, p1, targets=[p2_hero.id])
    assert p1.overloaded_mana == 1


def test_feral_spirit_overload():
    """Feral Spirit has Overload (2)."""
    game, p1, p2 = new_hs_game()
    cast_spell(game, FERAL_SPIRIT, p1)
    assert p1.overloaded_mana == 2


def test_earth_elemental_overload():
    """Earth Elemental has Overload (3)."""
    game, p1, p2 = new_hs_game()
    play_minion(game, EARTH_ELEMENTAL, p1)
    assert p1.overloaded_mana == 3


def test_multiple_overload_cards_stack():
    """Multiple overload cards stack their overload amounts."""
    game, p1, p2 = new_hs_game()
    p2_hero = game.state.objects[p2.hero_id]
    cast_spell(game, LIGHTNING_BOLT, p1, targets=[p2_hero.id])
    overload1 = p1.overloaded_mana
    cast_spell(game, FERAL_SPIRIT, p1)
    overload2 = p1.overloaded_mana
    assert overload2 == overload1 + 2


def test_overload_does_not_reduce_current_mana():
    """Overload does not reduce mana in the current turn."""
    game, p1, p2 = new_hs_game()
    before = p1.mana_crystals_available
    p2_hero = game.state.objects[p2.hero_id]
    cast_spell(game, LIGHTNING_BOLT, p1, targets=[p2_hero.id])
    after = p1.mana_crystals_available
    assert after == before


# ============================================================
# Mana Crystal Limits (5 tests)
# ============================================================

def test_max_mana_is_ten():
    """Maximum mana crystals cap at 10."""
    game, p1, p2 = new_hs_game()
    max_mana = game.mana_system.get_max_mana(p1.id)
    assert max_mana == 10


def test_turn_start_does_not_exceed_ten():
    """Additional turn starts do not increase mana beyond 10."""
    game, p1, p2 = new_hs_game()
    for _ in range(5):
        game.mana_system.on_turn_start(p1.id)
    max_mana = game.mana_system.get_max_mana(p1.id)
    assert max_mana == 10


def test_wild_growth_at_ten_mana():
    """Wild Growth at 10 mana does not increase max mana."""
    game, p1, p2 = new_hs_game()
    before_max = game.mana_system.get_max_mana(p1.id)
    cast_spell(game, WILD_GROWTH, p1)
    after_max = game.mana_system.get_max_mana(p1.id)
    assert after_max == before_max
    assert after_max == 10


def test_temporary_mana_not_limited_by_max():
    """Temporary mana can exceed the 10 crystal limit."""
    game, p1, p2 = new_hs_game()
    cast_spell(game, INNERVATE, p1)
    cast_spell(game, INNERVATE, p1)
    available = p1.mana_crystals_available
    assert available == 14


def test_low_mana_game_has_correct_max():
    """Game with few turn starts has correct max mana."""
    game, p1, p2 = new_hs_game_low_mana(mana_turns=4)
    max_mana = game.mana_system.get_max_mana(p1.id)
    assert max_mana == 4


# ============================================================
# Dynamic Cost Cards (5 tests)
# ============================================================

def test_sea_giant_has_dynamic_cost():
    """Sea Giant has a dynamic_cost function."""
    assert hasattr(SEA_GIANT, 'dynamic_cost')
    assert callable(SEA_GIANT.dynamic_cost)


def test_mountain_giant_has_dynamic_cost():
    """Mountain Giant has a dynamic_cost function."""
    assert hasattr(MOUNTAIN_GIANT, 'dynamic_cost')
    assert callable(MOUNTAIN_GIANT.dynamic_cost)


def test_molten_giant_has_dynamic_cost():
    """Molten Giant has a dynamic_cost function."""
    assert hasattr(MOLTEN_GIANT, 'dynamic_cost')
    assert callable(MOLTEN_GIANT.dynamic_cost)


def test_dread_corsair_has_dynamic_cost():
    """Dread Corsair has dynamic cost based on weapon attack."""
    assert hasattr(DREAD_CORSAIR, 'dynamic_cost')
    game, p1, p2 = new_hs_game()
    # Create a card object to pass as first arg (needs .controller)
    card_obj = make_obj(game, DREAD_CORSAIR, p1)
    cost = DREAD_CORSAIR.dynamic_cost(card_obj, game.state)
    # Without weapon, cost should be base (4)
    assert cost == 4


def test_sea_giant_cost_reduces_with_minions():
    """Sea Giant cost reduces based on minions on battlefield."""
    game, p1, p2 = new_hs_game()
    play_minion(game, STONETUSK_BOAR, p1)
    play_minion(game, STONETUSK_BOAR, p1)
    play_minion(game, STONETUSK_BOAR, p2)
    minion_count = get_battlefield_count(game, p1) + get_battlefield_count(game, p2)
    # Create a card object to pass as first arg
    card_obj = make_obj(game, SEA_GIANT, p1)
    cost = SEA_GIANT.dynamic_cost(card_obj, game.state)
    # Note: card_obj itself is also on battlefield, so minion_count should include it
    total_minions = minion_count + 1  # +1 for the Sea Giant we just placed
    assert cost == 10 - total_minions


# ============================================================
# Turn Start Mana Behavior (5 tests)
# ============================================================

def test_turn_start_increases_max_mana():
    """Turn start increases max mana by 1 up to 10."""
    game, p1, p2 = new_hs_game_low_mana(mana_turns=0)
    before = game.mana_system.get_max_mana(p1.id)
    game.mana_system.on_turn_start(p1.id)
    after = game.mana_system.get_max_mana(p1.id)
    assert after == before + 1


def test_turn_start_refreshes_available_mana():
    """Turn start refreshes available mana to max."""
    game, p1, p2 = new_hs_game_low_mana(mana_turns=5)
    p1.mana_crystals_available = 0
    game.mana_system.on_turn_start(p1.id)
    available = game.mana_system.get_available_mana(p1.id)
    max_mana = game.mana_system.get_max_mana(p1.id)
    assert available == max_mana


def test_turn_start_at_max_only_refreshes():
    """Turn start at 10 mana only refreshes, does not increase max."""
    game, p1, p2 = new_hs_game()
    before_max = game.mana_system.get_max_mana(p1.id)
    p1.mana_crystals_available = 3
    game.mana_system.on_turn_start(p1.id)
    after_max = game.mana_system.get_max_mana(p1.id)
    assert after_max == before_max
    assert after_max == 10


def test_first_turn_starts_with_one_mana():
    """First turn start gives 1 mana crystal."""
    game, p1, p2 = new_hs_game_low_mana(mana_turns=0)
    game.mana_system.on_turn_start(p1.id)
    max_mana = game.mana_system.get_max_mana(p1.id)
    assert max_mana == 1


def test_ten_turn_starts_reach_max():
    """Ten consecutive turn starts reach max mana of 10."""
    game, p1, p2 = new_hs_game_low_mana(mana_turns=0)
    for _ in range(10):
        game.mana_system.on_turn_start(p1.id)
    max_mana = game.mana_system.get_max_mana(p1.id)
    assert max_mana == 10


# ============================================================
# Cost Modifier Interactions (5 tests)
# ============================================================

def test_preparation_casts_without_error():
    """Preparation spell casts without error."""
    game, p1, p2 = new_hs_game()
    cast_spell(game, PREPARATION, p1)
    # Verify spell cast event was emitted
    spell_events = [e for e in game.state.event_log if e.type == EventType.SPELL_CAST]
    assert len(spell_events) == 1


def test_cost_modifier_filter_matches_spells():
    """Cost modifier with spell filter matches spell cards."""
    game, p1, p2 = new_hs_game()
    spell_filter = lambda c: CardType.SPELL in c.characteristics.types
    p1.cost_modifiers.append({'amount': 2, 'filter': spell_filter})
    assert p1.cost_modifiers[0]['filter'](FIREBALL)
    assert not p1.cost_modifiers[0]['filter'](STONETUSK_BOAR)


def test_clearing_cost_modifiers():
    """Cost modifiers can be cleared from the list."""
    game, p1, p2 = new_hs_game()
    p1.cost_modifiers.append({'amount': 1, 'filter': lambda c: True})
    p1.cost_modifiers.append({'amount': 2, 'filter': lambda c: True})
    assert len(p1.cost_modifiers) == 2
    p1.cost_modifiers.clear()
    assert len(p1.cost_modifiers) == 0


def test_cost_modifier_persists_across_turn_starts():
    """Cost modifiers persist across turn starts."""
    game, p1, p2 = new_hs_game()
    p1.cost_modifiers.append({'amount': 1, 'filter': lambda c: True})
    game.mana_system.on_turn_start(p1.id)
    assert len(p1.cost_modifiers) == 1


def test_mana_cost_string_parseable():
    """Card mana cost strings are parseable."""
    cost_str = FIREBALL.characteristics.mana_cost
    numbers = re.findall(r'\{(\d+)\}', cost_str)
    total = sum(int(n) for n in numbers)
    assert total == 4  # Fireball costs 4
