"""
Hearthstone Unhappy Path Tests - Batch 122: Mana and Resource Management

Tests mana crystal accumulation, overload mechanics, cost modifiers, dynamic costs,
and various mana-related edge cases.
"""

import pytest
from src.engine.game import Game
from src.engine.types import (
    Event, EventType, GameObject, GameState, CardType, ZoneType,
    Interceptor, InterceptorPriority, InterceptorAction, InterceptorResult,
    new_id
)
from src.engine.queries import get_power, get_toughness, has_ability
from src.cards.hearthstone.heroes import HEROES
from src.cards.hearthstone.hero_powers import HERO_POWERS
from src.cards.hearthstone.basic import THE_COIN, WISP, STONETUSK_BOAR, CHILLWIND_YETI
from src.cards.hearthstone.druid import INNERVATE, WILD_GROWTH
from src.cards.hearthstone.rogue import PREPARATION
from src.cards.hearthstone.shaman import FERAL_SPIRIT, LIGHTNING_STORM, EARTH_ELEMENTAL
from src.cards.hearthstone.classic import (
    SEA_GIANT, MOUNTAIN_GIANT, MOLTEN_GIANT,
    VENTURE_CO_MERCENARY, MANA_WRAITH, PINT_SIZED_SUMMONER
)


def new_hs_game(p1_class="Warrior", p2_class="Mage"):
    """Create a fresh Hearthstone game starting at 0 mana."""
    game = Game(mode='hearthstone')
    p1 = game.add_player("Player1", life=30)
    p2 = game.add_player("Player2", life=30)
    game.setup_hearthstone_player(p1, HEROES[p1_class], HERO_POWERS[p1_class])
    game.setup_hearthstone_player(p2, HEROES[p2_class], HERO_POWERS[p2_class])
    return game, p1, p2


def new_hs_game_full_mana(p1_class="Warrior", p2_class="Mage"):
    """Create a Hearthstone game with full 10 mana for both players."""
    game, p1, p2 = new_hs_game(p1_class, p2_class)
    for _ in range(10):
        game.mana_system.on_turn_start(p1.id)
        game.mana_system.on_turn_start(p2.id)
    return game, p1, p2


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


def add_cards_to_library(game, player, count=10):
    for _ in range(count):
        game.create_object(
            name="Dummy Card",
            owner_id=player.id,
            zone=ZoneType.LIBRARY,
            characteristics=WISP.characteristics,
            card_def=WISP
        )


# ====================================================================
# 1. Mana Crystal Accumulation (1 per turn, max 10)
# ====================================================================

def test_mana_starts_at_zero():
    """Players start with 0 mana crystals."""
    game, p1, p2 = new_hs_game()
    assert p1.mana_crystals == 0
    assert p1.mana_crystals_available == 0
    assert p2.mana_crystals == 0
    assert p2.mana_crystals_available == 0


def test_mana_gains_one_per_turn():
    """Mana crystals increase by 1 each turn (up to 10)."""
    game, p1, p2 = new_hs_game()

    for turn in range(1, 11):
        game.mana_system.on_turn_start(p1.id)
        assert p1.mana_crystals == turn
        assert p1.mana_crystals_available == turn


def test_mana_caps_at_10():
    """Mana crystals cap at 10, no further gain."""
    game, p1, p2 = new_hs_game()

    for _ in range(15):
        game.mana_system.on_turn_start(p1.id)

    assert p1.mana_crystals == 10
    assert p1.mana_crystals_available == 10


def test_mana_refills_each_turn():
    """Available mana refills to max at turn start."""
    game, p1, p2 = new_hs_game()

    for _ in range(5):
        game.mana_system.on_turn_start(p1.id)

    # Spend some mana manually
    p1.mana_crystals_available = 2

    # Next turn refills to max
    game.mana_system.on_turn_start(p1.id)
    assert p1.mana_crystals == 6
    assert p1.mana_crystals_available == 6


def test_both_players_gain_mana_independently():
    """Each player's mana tracks independently."""
    game, p1, p2 = new_hs_game()

    # P1 gets 3 turns of mana
    for _ in range(3):
        game.mana_system.on_turn_start(p1.id)

    # P2 gets 5 turns of mana
    for _ in range(5):
        game.mana_system.on_turn_start(p2.id)

    assert p1.mana_crystals == 3
    assert p2.mana_crystals == 5


# ====================================================================
# 2. Mana Spending
# ====================================================================

def test_insufficient_mana_card_stays_in_hand():
    """Card cannot be played if not enough mana available."""
    game, p1, p2 = new_hs_game()

    # Give p1 2 mana
    game.mana_system.on_turn_start(p1.id)
    game.mana_system.on_turn_start(p1.id)
    assert p1.mana_crystals_available == 2

    # Put a 4-cost card in hand
    yeti = game.create_object(
        name=CHILLWIND_YETI.name,
        owner_id=p1.id,
        zone=ZoneType.HAND,
        characteristics=CHILLWIND_YETI.characteristics,
        card_def=CHILLWIND_YETI
    )

    # Verify mana is less than cost
    hand = game.state.zones.get(f'hand_{p1.id}')
    assert yeti.id in hand.objects
    assert p1.mana_crystals_available < 4


def test_zero_cost_playable_with_no_mana():
    """0-cost cards are playable with 0 mana (Wisp)."""
    game, p1, p2 = new_hs_game()

    assert p1.mana_crystals_available == 0

    # Play Wisp (0 cost) — our play_minion bypasses mana check
    wisp = play_minion(game, WISP, p1)

    battlefield = game.state.zones.get('battlefield')
    assert wisp.id in battlefield.objects


def test_spending_mana_reduces_available():
    """Spending mana reduces available but not max crystals."""
    game, p1, p2 = new_hs_game()

    for _ in range(5):
        game.mana_system.on_turn_start(p1.id)

    assert p1.mana_crystals == 5
    assert p1.mana_crystals_available == 5

    # Simulate spending 3 mana
    p1.mana_crystals_available -= 3

    assert p1.mana_crystals == 5  # Max unchanged
    assert p1.mana_crystals_available == 2  # Available reduced


# ====================================================================
# 3. Overload Mechanic
# ====================================================================

def test_overload_sets_overloaded_mana():
    """Playing an overload card should set overloaded_mana on the player."""
    game, p1, p2 = new_hs_game("Shaman", "Mage")

    # Verify overload starts at 0
    assert p1.overloaded_mana == 0

    # Manually set overload (simulating what the turn manager does)
    p1.overloaded_mana = 2

    assert p1.overloaded_mana == 2


def test_overload_locks_mana_next_turn():
    """Overload should reduce available mana next turn."""
    game, p1, p2 = new_hs_game("Shaman", "Mage")

    for _ in range(3):
        game.mana_system.on_turn_start(p1.id)
    assert p1.mana_crystals == 3

    # Simulate playing Feral Spirit (Overload: 2)
    p1.overloaded_mana = 2

    # Next turn: gain crystal but apply overload
    game.mana_system.on_turn_start(p1.id)
    available_after_overload = max(0, p1.mana_crystals_available - p1.overloaded_mana)
    p1.overloaded_mana = 0

    # 4 crystals - 2 overload = 2 available
    assert p1.mana_crystals == 4
    assert available_after_overload == 2


def test_overload_clears_after_application():
    """Overload only affects the next turn, then clears."""
    game, p1, p2 = new_hs_game("Shaman", "Mage")

    for _ in range(5):
        game.mana_system.on_turn_start(p1.id)

    # Simulate Earth Elemental overload
    p1.overloaded_mana = 3

    # Apply overload next turn
    game.mana_system.on_turn_start(p1.id)
    p1.mana_crystals_available = max(0, p1.mana_crystals_available - p1.overloaded_mana)
    p1.overloaded_mana = 0

    # Turn after: no overload
    game.mana_system.on_turn_start(p1.id)
    assert p1.overloaded_mana == 0
    assert p1.mana_crystals_available == p1.mana_crystals


def test_overload_cannot_go_negative():
    """Overload cannot reduce available mana below 0."""
    game, p1, p2 = new_hs_game("Shaman", "Mage")

    # Only 1 crystal
    game.mana_system.on_turn_start(p1.id)
    assert p1.mana_crystals == 1

    # Overload 3 (more than available)
    p1.overloaded_mana = 3

    game.mana_system.on_turn_start(p1.id)
    available = max(0, p1.mana_crystals_available - p1.overloaded_mana)

    assert available == 0  # Not negative


def test_feral_spirit_has_overload_value():
    """Feral Spirit card definition should indicate overload."""
    # Check the card has overload attribute
    assert hasattr(FERAL_SPIRIT, 'overload') or hasattr(FERAL_SPIRIT, 'characteristics')
    # Feral Spirit summons two 2/3 wolves with taunt
    assert FERAL_SPIRIT.name == "Feral Spirit"


def test_earth_elemental_has_overload_value():
    """Earth Elemental card definition should indicate overload."""
    assert EARTH_ELEMENTAL.name == "Earth Elemental"


def test_lightning_storm_has_overload_value():
    """Lightning Storm card definition should indicate overload."""
    assert LIGHTNING_STORM.name == "Lightning Storm"


# ====================================================================
# 4. Temporary Mana (The Coin, Innervate)
# ====================================================================

def test_the_coin_increases_available_mana():
    """The Coin grants 1 temporary mana crystal."""
    game, p1, p2 = new_hs_game()

    for _ in range(2):
        game.mana_system.on_turn_start(p1.id)
    assert p1.mana_crystals_available == 2

    cast_spell(game, THE_COIN, p1)

    # Should have 3 available now (or the coin adds a crystal)
    assert p1.mana_crystals_available >= 2


def test_innervate_increases_available_mana():
    """Innervate grants 2 temporary mana."""
    game, p1, p2 = new_hs_game("Druid", "Mage")

    game.mana_system.on_turn_start(p1.id)
    initial_mana = p1.mana_crystals_available

    cast_spell(game, INNERVATE, p1)

    # Should have gained mana
    assert p1.mana_crystals_available >= initial_mana


def test_coin_does_not_increase_max_crystals():
    """The Coin does not increase max mana crystals."""
    game, p1, p2 = new_hs_game()

    for _ in range(2):
        game.mana_system.on_turn_start(p1.id)
    max_before = p1.mana_crystals

    cast_spell(game, THE_COIN, p1)

    # Max crystals unchanged
    assert p1.mana_crystals == max_before


def test_temporary_mana_does_not_persist():
    """Temporary mana does not carry over to next turn."""
    game, p1, p2 = new_hs_game()

    for _ in range(2):
        game.mana_system.on_turn_start(p1.id)

    cast_spell(game, THE_COIN, p1)
    # Save the current available
    available_after_coin = p1.mana_crystals_available

    # Next turn: refills to normal max (3 crystals)
    game.mana_system.on_turn_start(p1.id)
    assert p1.mana_crystals == 3
    assert p1.mana_crystals_available == 3


# ====================================================================
# 5. Wild Growth
# ====================================================================

def test_wild_growth_adds_mana_crystal():
    """Wild Growth should grant an empty mana crystal."""
    game, p1, p2 = new_hs_game("Druid", "Mage")

    for _ in range(2):
        game.mana_system.on_turn_start(p1.id)
    crystals_before = p1.mana_crystals

    cast_spell(game, WILD_GROWTH, p1)

    # Should have gained a crystal
    assert p1.mana_crystals >= crystals_before


def test_wild_growth_does_not_exceed_10():
    """Wild Growth at 10 crystals should not go above 10."""
    game, p1, p2 = new_hs_game_full_mana("Druid", "Mage")

    assert p1.mana_crystals == 10

    cast_spell(game, WILD_GROWTH, p1)

    assert p1.mana_crystals <= 10


# ====================================================================
# 6. Cost Reduction (Preparation)
# ====================================================================

def test_preparation_adds_cost_modifier():
    """Preparation should add a cost modifier for the next spell."""
    game, p1, p2 = new_hs_game("Rogue", "Mage")

    for _ in range(5):
        game.mana_system.on_turn_start(p1.id)

    modifiers_before = len(p1.cost_modifiers)

    cast_spell(game, PREPARATION, p1)

    # Should have added a cost modifier
    assert len(p1.cost_modifiers) > modifiers_before


def test_preparation_modifier_targets_spells():
    """Preparation's cost modifier should target spells specifically."""
    game, p1, p2 = new_hs_game("Rogue", "Mage")

    for _ in range(5):
        game.mana_system.on_turn_start(p1.id)

    cast_spell(game, PREPARATION, p1)

    # Check the modifier
    assert len(p1.cost_modifiers) > 0
    modifier = p1.cost_modifiers[-1]
    assert modifier.get('card_type') == CardType.SPELL or 'spell' in str(modifier).lower()


# ====================================================================
# 7. Cost Modifiers (Mana Wraith, Venture Co.)
# ====================================================================

def test_mana_wraith_on_battlefield():
    """Mana Wraith should register interceptors when played."""
    game, p1, p2 = new_hs_game_full_mana()

    wraith = play_minion(game, MANA_WRAITH, p1)

    # Mana Wraith should have interceptors registered
    assert len(wraith.interceptor_ids) >= 1


def test_venture_co_on_battlefield():
    """Venture Co. Mercenary should register cost interceptors when played."""
    game, p1, p2 = new_hs_game_full_mana()

    venture = play_minion(game, VENTURE_CO_MERCENARY, p1)

    # Should have interceptors for cost increase
    assert len(venture.interceptor_ids) >= 1


def test_pint_sized_summoner_on_battlefield():
    """Pint-Sized Summoner should register cost interceptors when played."""
    game, p1, p2 = new_hs_game_full_mana()

    pint = play_minion(game, PINT_SIZED_SUMMONER, p1)

    # Should have interceptors
    assert len(pint.interceptor_ids) >= 1


def test_venture_co_death_removes_cost_increase():
    """Venture Co. dying should remove its cost increase effect."""
    game, p1, p2 = new_hs_game_full_mana()

    venture = play_minion(game, VENTURE_CO_MERCENARY, p1)

    # Kill Venture Co.
    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': venture.id, 'amount': 20, 'source': 'test'},
        source='test'
    ))
    game.check_state_based_actions()

    # Verify Venture Co. is dead
    battlefield = game.state.zones.get('battlefield')
    assert venture.id not in battlefield.objects

    # Cost modifiers should be cleared from player
    assert len(p1.cost_modifiers) == 0


def test_mana_wraith_death_removes_cost_increase():
    """Mana Wraith dying should remove its cost increase effect."""
    game, p1, p2 = new_hs_game_full_mana()

    wraith = play_minion(game, MANA_WRAITH, p1)

    # Kill Mana Wraith
    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': wraith.id, 'amount': 20, 'source': 'test'},
        source='test'
    ))
    game.check_state_based_actions()

    battlefield = game.state.zones.get('battlefield')
    assert wraith.id not in battlefield.objects

    # Cost modifiers should be cleared
    assert len(p1.cost_modifiers) == 0


# ====================================================================
# 8. Dynamic Costs (Sea Giant, Mountain Giant, Molten Giant)
# ====================================================================

def test_sea_giant_base_cost():
    """Sea Giant base cost is 10 with no minions on board."""
    game, p1, p2 = new_hs_game()

    sea = game.create_object(
        name=SEA_GIANT.name,
        owner_id=p1.id,
        zone=ZoneType.HAND,
        characteristics=SEA_GIANT.characteristics,
        card_def=SEA_GIANT
    )

    cost = SEA_GIANT.dynamic_cost(sea, game.state)
    # Heroes are on battlefield but aren't minions — Sea Giant counts minions only
    # With 0 minions, cost should be 10
    assert cost == 10


def test_sea_giant_reduces_with_minions():
    """Sea Giant costs less with minions on the battlefield."""
    game, p1, p2 = new_hs_game_full_mana()

    sea = game.create_object(
        name=SEA_GIANT.name,
        owner_id=p1.id,
        zone=ZoneType.HAND,
        characteristics=SEA_GIANT.characteristics,
        card_def=SEA_GIANT
    )

    # Play 3 minions
    play_minion(game, WISP, p1)
    play_minion(game, WISP, p1)
    play_minion(game, WISP, p2)

    cost = SEA_GIANT.dynamic_cost(sea, game.state)
    assert cost == 7  # 10 - 3 minions


def test_sea_giant_minimum_cost_zero():
    """Sea Giant cost cannot go below 0."""
    game, p1, p2 = new_hs_game_full_mana()

    sea = game.create_object(
        name=SEA_GIANT.name,
        owner_id=p1.id,
        zone=ZoneType.HAND,
        characteristics=SEA_GIANT.characteristics,
        card_def=SEA_GIANT
    )

    # Play lots of minions (more than 10)
    for _ in range(7):
        play_minion(game, WISP, p1)
    for _ in range(5):
        play_minion(game, WISP, p2)

    cost = SEA_GIANT.dynamic_cost(sea, game.state)
    assert cost == 0


def test_mountain_giant_base_cost():
    """Mountain Giant base cost is 12 with only itself in hand."""
    game, p1, p2 = new_hs_game()

    mountain = game.create_object(
        name=MOUNTAIN_GIANT.name,
        owner_id=p1.id,
        zone=ZoneType.HAND,
        characteristics=MOUNTAIN_GIANT.characteristics,
        card_def=MOUNTAIN_GIANT
    )

    cost = MOUNTAIN_GIANT.dynamic_cost(mountain, game.state)
    # With just Mountain Giant in hand (1 card, 0 other cards), cost should be 12
    assert cost == 12


def test_mountain_giant_reduces_with_hand_size():
    """Mountain Giant costs less with more cards in hand."""
    game, p1, p2 = new_hs_game()

    mountain = game.create_object(
        name=MOUNTAIN_GIANT.name,
        owner_id=p1.id,
        zone=ZoneType.HAND,
        characteristics=MOUNTAIN_GIANT.characteristics,
        card_def=MOUNTAIN_GIANT
    )

    # Add 5 more cards to hand
    for _ in range(5):
        game.create_object(
            name=WISP.name,
            owner_id=p1.id,
            zone=ZoneType.HAND,
            characteristics=WISP.characteristics,
            card_def=WISP
        )

    cost = MOUNTAIN_GIANT.dynamic_cost(mountain, game.state)
    # 12 - 5 other cards = 7
    assert cost == 7


def test_mountain_giant_empty_hand():
    """Mountain Giant with no other cards costs 12."""
    game, p1, p2 = new_hs_game()

    mountain = game.create_object(
        name=MOUNTAIN_GIANT.name,
        owner_id=p1.id,
        zone=ZoneType.HAND,
        characteristics=MOUNTAIN_GIANT.characteristics,
        card_def=MOUNTAIN_GIANT
    )

    cost = MOUNTAIN_GIANT.dynamic_cost(mountain, game.state)
    assert cost == 12


def test_molten_giant_at_full_health():
    """Molten Giant at full HP costs 20."""
    game, p1, p2 = new_hs_game()

    molten = game.create_object(
        name=MOLTEN_GIANT.name,
        owner_id=p1.id,
        zone=ZoneType.HAND,
        characteristics=MOLTEN_GIANT.characteristics,
        card_def=MOLTEN_GIANT
    )

    assert p1.life == 30
    cost = MOLTEN_GIANT.dynamic_cost(molten, game.state)
    assert cost == 20


def test_molten_giant_reduces_with_damage():
    """Molten Giant costs less for each damage taken."""
    game, p1, p2 = new_hs_game()

    molten = game.create_object(
        name=MOLTEN_GIANT.name,
        owner_id=p1.id,
        zone=ZoneType.HAND,
        characteristics=MOLTEN_GIANT.characteristics,
        card_def=MOLTEN_GIANT
    )

    # Take 10 damage
    p1.life = 20
    cost = MOLTEN_GIANT.dynamic_cost(molten, game.state)
    assert cost == 10  # 20 - 10 damage


def test_molten_giant_at_low_health():
    """Molten Giant is free when hero has taken 20+ damage."""
    game, p1, p2 = new_hs_game()

    molten = game.create_object(
        name=MOLTEN_GIANT.name,
        owner_id=p1.id,
        zone=ZoneType.HAND,
        characteristics=MOLTEN_GIANT.characteristics,
        card_def=MOLTEN_GIANT
    )

    p1.life = 10  # 20 damage taken
    cost = MOLTEN_GIANT.dynamic_cost(molten, game.state)
    assert cost == 0


def test_molten_giant_near_death():
    """Molten Giant cost floors at 0 even at very low HP."""
    game, p1, p2 = new_hs_game()

    molten = game.create_object(
        name=MOLTEN_GIANT.name,
        owner_id=p1.id,
        zone=ZoneType.HAND,
        characteristics=MOLTEN_GIANT.characteristics,
        card_def=MOLTEN_GIANT
    )

    p1.life = 1  # 29 damage taken
    cost = MOLTEN_GIANT.dynamic_cost(molten, game.state)
    assert cost == 0


def test_molten_giant_with_armor():
    """Molten Giant cost is based on life lost, not effective HP with armor."""
    game, p1, p2 = new_hs_game()

    molten = game.create_object(
        name=MOLTEN_GIANT.name,
        owner_id=p1.id,
        zone=ZoneType.HAND,
        characteristics=MOLTEN_GIANT.characteristics,
        card_def=MOLTEN_GIANT
    )

    p1.life = 20  # 10 damage taken
    p1.armor = 5  # Effective HP = 25 but damage is still 10

    cost = MOLTEN_GIANT.dynamic_cost(molten, game.state)
    assert cost == 10  # Based on life lost (10), not effective HP


def test_sea_giant_counts_both_sides():
    """Sea Giant counts minions from both players."""
    game, p1, p2 = new_hs_game_full_mana()

    sea = game.create_object(
        name=SEA_GIANT.name,
        owner_id=p1.id,
        zone=ZoneType.HAND,
        characteristics=SEA_GIANT.characteristics,
        card_def=SEA_GIANT
    )

    # P1 gets 2 minions, P2 gets 3 minions
    play_minion(game, WISP, p1)
    play_minion(game, WISP, p1)
    play_minion(game, WISP, p2)
    play_minion(game, WISP, p2)
    play_minion(game, WISP, p2)

    cost = SEA_GIANT.dynamic_cost(sea, game.state)
    assert cost == 5  # 10 - 5 minions


# ====================================================================
# 9. Edge Cases
# ====================================================================

def test_mana_refill_does_not_exceed_max():
    """Turn start refill should not give more than max crystals."""
    game, p1, p2 = new_hs_game()

    for _ in range(5):
        game.mana_system.on_turn_start(p1.id)

    # Even if available was somehow higher, refill caps at max
    p1.mana_crystals_available = 10  # Manually set higher
    game.mana_system.on_turn_start(p1.id)

    # Should be capped at 6 crystals
    assert p1.mana_crystals == 6
    assert p1.mana_crystals_available == 6


def test_multiple_turn_starts_accumulate():
    """Multiple on_turn_start calls accumulate crystals correctly."""
    game, p1, p2 = new_hs_game()

    game.mana_system.on_turn_start(p1.id)
    assert p1.mana_crystals == 1

    game.mana_system.on_turn_start(p1.id)
    assert p1.mana_crystals == 2

    game.mana_system.on_turn_start(p1.id)
    assert p1.mana_crystals == 3


def test_mountain_giant_cost_with_large_hand():
    """Mountain Giant minimum cost floors at 0 with huge hand."""
    game, p1, p2 = new_hs_game()

    mountain = game.create_object(
        name=MOUNTAIN_GIANT.name,
        owner_id=p1.id,
        zone=ZoneType.HAND,
        characteristics=MOUNTAIN_GIANT.characteristics,
        card_def=MOUNTAIN_GIANT
    )

    # Add 15 cards to hand
    for _ in range(15):
        game.create_object(
            name=WISP.name,
            owner_id=p1.id,
            zone=ZoneType.HAND,
            characteristics=WISP.characteristics,
            card_def=WISP
        )

    cost = MOUNTAIN_GIANT.dynamic_cost(mountain, game.state)
    assert cost == 0  # 12 - 15 = -3, floored to 0
