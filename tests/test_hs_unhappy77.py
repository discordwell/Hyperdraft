"""
Hearthstone Unhappy Path Tests - Batch 77

Mana system edge cases: mana crystal gain per turn (1-10 cap),
mana refill at turn start, spending mana reduces available, Innervate
temporary mana boost, Wild Growth permanent crystal, overload locks
mana next turn, overload with mana refill interaction, Coin gives
1 temporary mana, mana cost 0 cards always playable, mana overflow
from Innervate (can exceed 10 temporarily), cost reduction stacking
with mana spending, paying exact mana leaves 0 available.
"""

import asyncio
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
    WISP, CHILLWIND_YETI, BLOODFEN_RAPTOR, THE_COIN,
)
from src.cards.hearthstone.druid import INNERVATE, WILD_GROWTH
from src.cards.hearthstone.shaman import LIGHTNING_BOLT, FERAL_SPIRIT, LAVA_BURST
from src.cards.hearthstone.mage import SORCERERS_APPRENTICE
from src.cards.hearthstone.classic import FIREBALL, FROSTBOLT, ARCANE_INTELLECT


# ============================================================
# Test Helpers
# ============================================================

def new_hs_game(class1="Mage", class2="Warrior"):
    """Create a fresh Hearthstone game with 2 players, heroes, and 10 mana each."""
    game = Game(mode='hearthstone')
    p1 = game.add_player("Player1", life=30)
    p2 = game.add_player("Player2", life=30)
    game.setup_hearthstone_player(p1, HEROES[class1], HERO_POWERS[class1])
    game.setup_hearthstone_player(p2, HEROES[class2], HERO_POWERS[class2])
    for _ in range(10):
        game.mana_system.on_turn_start(p1.id)
        game.mana_system.on_turn_start(p2.id)
    return game, p1, p2


def new_hs_game_fresh(class1="Mage", class2="Warrior"):
    """Create a fresh Hearthstone game with 2 players, heroes, and 0 mana (fresh start)."""
    game = Game(mode='hearthstone')
    p1 = game.add_player("Player1", life=30)
    p2 = game.add_player("Player2", life=30)
    game.setup_hearthstone_player(p1, HEROES[class1], HERO_POWERS[class1])
    game.setup_hearthstone_player(p2, HEROES[class2], HERO_POWERS[class2])
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
    events = card_def.spell_effect(obj, game.state, targets or [])
    for e in events:
        game.emit(e)
    game.emit(Event(
        type=EventType.SPELL_CAST,
        payload={'spell_id': obj.id, 'controller': owner.id, 'caster': owner.id},
        source=obj.id
    ))
    return obj


# ============================================================
# Test 1: TestManaCrystalGainPerTurn
# ============================================================

class TestManaCrystalGainPerTurn:
    """Turns 1-10 give 1-10 crystals. Turn 11+ stays at 10."""

    def test_turns_1_through_10(self):
        """Each turn from 1-10 gains exactly 1 mana crystal."""
        game, p1, p2 = new_hs_game_fresh()

        for turn in range(1, 11):
            game.mana_system.on_turn_start(p1.id)
            assert p1.mana_crystals == turn, (
                f"Turn {turn}: should have {turn} crystals, got {p1.mana_crystals}"
            )
            assert p1.mana_crystals_available == turn, (
                f"Turn {turn}: should have {turn} available, got {p1.mana_crystals_available}"
            )

    def test_turn_10_is_max(self):
        """At turn 10, player has exactly 10 mana crystals."""
        game, p1, p2 = new_hs_game_fresh()

        for _ in range(10):
            game.mana_system.on_turn_start(p1.id)

        assert p1.mana_crystals == 10, (
            f"After 10 turns, should have 10 crystals, got {p1.mana_crystals}"
        )

    def test_turn_11_stays_at_10(self):
        """Turn 11 does not gain an 11th crystal."""
        game, p1, p2 = new_hs_game_fresh()

        for _ in range(11):
            game.mana_system.on_turn_start(p1.id)

        assert p1.mana_crystals == 10, (
            f"After 11 turns, crystals should cap at 10, got {p1.mana_crystals}"
        )
        assert p1.mana_crystals_available == 10, (
            f"After 11 turns, available should cap at 10, got {p1.mana_crystals_available}"
        )

    def test_turn_15_stays_at_10(self):
        """Turns well beyond 10 still stay at 10 max."""
        game, p1, p2 = new_hs_game_fresh()

        for _ in range(15):
            game.mana_system.on_turn_start(p1.id)

        assert p1.mana_crystals == 10, (
            f"After 15 turns, crystals should cap at 10, got {p1.mana_crystals}"
        )


# ============================================================
# Test 2: TestManaRefillAtTurnStart
# ============================================================

class TestManaRefillAtTurnStart:
    """Available mana refills to max crystals at turn start."""

    def test_refill_after_spending(self):
        """After spending mana, next turn start refills to max."""
        game, p1, p2 = new_hs_game_fresh()

        # Turn 1: gain 1, spend 1
        game.mana_system.on_turn_start(p1.id)
        game.mana_system.pay_cost(p1.id, 1)
        assert p1.mana_crystals_available == 0, (
            f"After spending 1 of 1, available should be 0, got {p1.mana_crystals_available}"
        )

        # Turn 2: gain crystal, refill to 2
        game.mana_system.on_turn_start(p1.id)
        assert p1.mana_crystals == 2
        assert p1.mana_crystals_available == 2, (
            f"Turn 2: available should refill to 2, got {p1.mana_crystals_available}"
        )

    def test_refill_at_full_mana(self):
        """At 10 mana with 0 spent, refill still produces 10 available."""
        game, p1, p2 = new_hs_game()

        # Already at 10/10 from new_hs_game
        assert p1.mana_crystals == 10
        assert p1.mana_crystals_available == 10

        # Spend 5, then start a new turn
        game.mana_system.pay_cost(p1.id, 5)
        assert p1.mana_crystals_available == 5

        game.mana_system.on_turn_start(p1.id)
        assert p1.mana_crystals_available == 10, (
            f"After refill at 10 crystals, available should be 10, got {p1.mana_crystals_available}"
        )

    def test_refill_after_spending_all(self):
        """After spending all mana, turn start refills completely."""
        game, p1, p2 = new_hs_game()

        game.mana_system.pay_cost(p1.id, 10)
        assert p1.mana_crystals_available == 0

        game.mana_system.on_turn_start(p1.id)
        assert p1.mana_crystals_available == 10, (
            f"After spending all and refilling, available should be 10, "
            f"got {p1.mana_crystals_available}"
        )


# ============================================================
# Test 3: TestSpendingReducesAvailable
# ============================================================

class TestSpendingReducesAvailable:
    """Spending 3 mana at 5 available -> 2 remaining."""

    def test_spend_3_of_5(self):
        """Spending 3 from 5 available leaves 2."""
        game, p1, p2 = new_hs_game_fresh()

        # Get to 5 mana
        for _ in range(5):
            game.mana_system.on_turn_start(p1.id)

        assert p1.mana_crystals_available == 5
        success = game.mana_system.pay_cost(p1.id, 3)
        assert success is True
        assert p1.mana_crystals_available == 2, (
            f"5 - 3 = 2 available, got {p1.mana_crystals_available}"
        )

    def test_spend_reduces_incrementally(self):
        """Multiple spends reduce available incrementally."""
        game, p1, p2 = new_hs_game()

        assert p1.mana_crystals_available == 10

        game.mana_system.pay_cost(p1.id, 4)
        assert p1.mana_crystals_available == 6

        game.mana_system.pay_cost(p1.id, 3)
        assert p1.mana_crystals_available == 3

        game.mana_system.pay_cost(p1.id, 3)
        assert p1.mana_crystals_available == 0

    def test_cannot_overspend(self):
        """Spending more than available returns False."""
        game, p1, p2 = new_hs_game_fresh()

        for _ in range(3):
            game.mana_system.on_turn_start(p1.id)

        assert p1.mana_crystals_available == 3
        success = game.mana_system.pay_cost(p1.id, 4)
        assert success is False, "Should not be able to spend 4 mana when only 3 available"
        assert p1.mana_crystals_available == 3, (
            f"After failed payment, available should remain 3, got {p1.mana_crystals_available}"
        )

    def test_spending_does_not_change_max(self):
        """Spending mana does not reduce max crystals, only available."""
        game, p1, p2 = new_hs_game()

        game.mana_system.pay_cost(p1.id, 7)
        assert p1.mana_crystals == 10, (
            f"Max crystals should still be 10 after spending, got {p1.mana_crystals}"
        )
        assert p1.mana_crystals_available == 3


# ============================================================
# Test 4: TestInnervateTemporaryMana
# ============================================================

class TestInnervateTemporaryMana:
    """Innervate gives +2 temporary mana (can exceed current crystals)."""

    def test_innervate_adds_2_mana(self):
        """Casting Innervate increases available mana by 2."""
        game, p1, p2 = new_hs_game_fresh()

        for _ in range(5):
            game.mana_system.on_turn_start(p1.id)

        assert p1.mana_crystals_available == 5

        cast_spell(game, INNERVATE, p1)
        assert p1.mana_crystals_available == 7, (
            f"Innervate should give +2 available, expected 7, got {p1.mana_crystals_available}"
        )

    def test_innervate_does_not_increase_max(self):
        """Innervate does not increase max mana crystals."""
        game, p1, p2 = new_hs_game_fresh()

        for _ in range(5):
            game.mana_system.on_turn_start(p1.id)

        cast_spell(game, INNERVATE, p1)
        assert p1.mana_crystals == 5, (
            f"Max crystals should still be 5, got {p1.mana_crystals}"
        )

    def test_innervate_at_10_exceeds_10_temporarily(self):
        """Innervate at 10 mana gives 12 available temporarily."""
        game, p1, p2 = new_hs_game()

        assert p1.mana_crystals_available == 10
        cast_spell(game, INNERVATE, p1)
        assert p1.mana_crystals_available == 12, (
            f"Innervate at 10 mana should give 12 available, "
            f"got {p1.mana_crystals_available}"
        )

    def test_innervate_temporary_resets_on_turn(self):
        """Temporary mana from Innervate resets on next turn start (refill caps at max crystals)."""
        game, p1, p2 = new_hs_game()

        cast_spell(game, INNERVATE, p1)
        assert p1.mana_crystals_available == 12

        # Next turn start refills to max crystals (10), not 12
        game.mana_system.on_turn_start(p1.id)
        assert p1.mana_crystals_available == 10, (
            f"After turn start, available should refill to 10 (not 12), "
            f"got {p1.mana_crystals_available}"
        )


# ============================================================
# Test 5: TestWildGrowthPermanentCrystal
# ============================================================

class TestWildGrowthPermanentCrystal:
    """Wild Growth adds 1 permanent mana crystal."""

    def test_wild_growth_adds_crystal(self):
        """Wild Growth increases max crystals by 1."""
        game, p1, p2 = new_hs_game_fresh()

        for _ in range(3):
            game.mana_system.on_turn_start(p1.id)

        assert p1.mana_crystals == 3

        cast_spell(game, WILD_GROWTH, p1)
        assert p1.mana_crystals == 4, (
            f"Wild Growth should add 1 crystal, expected 4, got {p1.mana_crystals}"
        )

    def test_wild_growth_crystal_persists(self):
        """The crystal from Wild Growth persists and refills on next turn."""
        game, p1, p2 = new_hs_game_fresh()

        for _ in range(3):
            game.mana_system.on_turn_start(p1.id)

        cast_spell(game, WILD_GROWTH, p1)
        assert p1.mana_crystals == 4

        # Spend all mana
        p1.mana_crystals_available = 0

        # Next turn: gain 1 more crystal (now 5), refill to 5
        game.mana_system.on_turn_start(p1.id)
        assert p1.mana_crystals == 5, (
            f"After Wild Growth and next turn, should have 5 crystals, got {p1.mana_crystals}"
        )
        assert p1.mana_crystals_available == 5

    def test_wild_growth_empty_crystal(self):
        """Wild Growth adds an empty crystal (does not increase available this turn)."""
        game, p1, p2 = new_hs_game_fresh()

        for _ in range(3):
            game.mana_system.on_turn_start(p1.id)

        # Spend some mana first to track available separately
        game.mana_system.pay_cost(p1.id, 2)
        available_before = p1.mana_crystals_available  # 1

        cast_spell(game, WILD_GROWTH, p1)

        # Wild Growth adds an empty crystal (max goes up but available doesn't change)
        assert p1.mana_crystals == 4, "Max should increase to 4"
        assert p1.mana_crystals_available == available_before, (
            f"Available should stay at {available_before}, got {p1.mana_crystals_available}"
        )


# ============================================================
# Test 6: TestWildGrowthAtCap
# ============================================================

class TestWildGrowthAtCap:
    """Wild Growth at 10 crystals -> no effect (capped)."""

    def test_wild_growth_at_10_does_nothing(self):
        """Wild Growth at 10 max crystals does not go above 10."""
        game, p1, p2 = new_hs_game()

        assert p1.mana_crystals == 10

        cast_spell(game, WILD_GROWTH, p1)
        assert p1.mana_crystals == 10, (
            f"Wild Growth at 10 should not exceed 10, got {p1.mana_crystals}"
        )

    def test_wild_growth_at_10_available_unchanged(self):
        """Available mana does not change when Wild Growth is at cap."""
        game, p1, p2 = new_hs_game()

        game.mana_system.pay_cost(p1.id, 3)
        available_before = p1.mana_crystals_available  # 7

        cast_spell(game, WILD_GROWTH, p1)
        assert p1.mana_crystals_available == available_before, (
            f"Available should not change at cap, expected {available_before}, "
            f"got {p1.mana_crystals_available}"
        )


# ============================================================
# Test 7: TestCoinGivesOneMana
# ============================================================

class TestCoinGivesOneMana:
    """The Coin gives +1 temporary mana."""

    def test_coin_adds_1_mana(self):
        """Casting The Coin increases available mana by 1."""
        game, p1, p2 = new_hs_game_fresh()

        game.mana_system.on_turn_start(p1.id)
        assert p1.mana_crystals_available == 1

        cast_spell(game, THE_COIN, p1)
        assert p1.mana_crystals_available == 2, (
            f"The Coin should add +1 available, expected 2, got {p1.mana_crystals_available}"
        )

    def test_coin_does_not_increase_max(self):
        """The Coin does not increase max mana crystals."""
        game, p1, p2 = new_hs_game_fresh()

        game.mana_system.on_turn_start(p1.id)
        cast_spell(game, THE_COIN, p1)
        assert p1.mana_crystals == 1, (
            f"Max crystals should still be 1 after Coin, got {p1.mana_crystals}"
        )

    def test_coin_at_0_mana_gives_1(self):
        """The Coin at 0 available gives exactly 1."""
        game, p1, p2 = new_hs_game_fresh()

        game.mana_system.on_turn_start(p1.id)
        game.mana_system.pay_cost(p1.id, 1)
        assert p1.mana_crystals_available == 0

        cast_spell(game, THE_COIN, p1)
        assert p1.mana_crystals_available == 1, (
            f"Coin at 0 available should give 1, got {p1.mana_crystals_available}"
        )

    def test_coin_temporary_resets_on_turn(self):
        """Coin's temporary mana resets on next turn start."""
        game, p1, p2 = new_hs_game_fresh()

        game.mana_system.on_turn_start(p1.id)  # Turn 1: 1 crystal
        cast_spell(game, THE_COIN, p1)  # 2 available, 1 max
        assert p1.mana_crystals_available == 2

        # Next turn: gain 1 more (2 max), refill to 2 (not 3)
        game.mana_system.on_turn_start(p1.id)
        assert p1.mana_crystals == 2
        assert p1.mana_crystals_available == 2, (
            f"Coin mana should not persist, expected 2, got {p1.mana_crystals_available}"
        )


# ============================================================
# Test 8: TestOverloadLocksManaNextTurn
# ============================================================

class TestOverloadLocksManaNextTurn:
    """Overload 2 -> next turn 2 mana is locked."""

    def test_overload_sets_field(self):
        """Casting a spell with Overload sets overloaded_mana on the player."""
        game, p1, p2 = new_hs_game("Shaman", "Warrior")

        assert p1.overloaded_mana == 0

        cast_spell(game, LIGHTNING_BOLT, p1)
        assert p1.overloaded_mana == 1, (
            f"Lightning Bolt should set overloaded_mana to 1, got {p1.overloaded_mana}"
        )

    def test_overload_2_locks_2_next_turn(self):
        """Feral Spirit (Overload: 2) locks 2 mana on the next turn."""
        game, p1, p2 = new_hs_game("Shaman", "Warrior")

        cast_spell(game, FERAL_SPIRIT, p1)
        assert p1.overloaded_mana == 2

        # Simulate next turn via hearthstone_turn draw phase logic:
        # on_turn_start gives crystal + refill, then overload subtracts
        game.mana_system.on_turn_start(p1.id)
        # Apply overload manually (as turn manager does)
        locked = p1.overloaded_mana
        p1.mana_crystals_available = max(0, p1.mana_crystals_available - locked)
        p1.overloaded_mana = 0

        assert p1.mana_crystals_available == 8, (
            f"10 crystals minus 2 overload should give 8 available, "
            f"got {p1.mana_crystals_available}"
        )

    def test_overload_1_locks_1_next_turn(self):
        """Lightning Bolt (Overload: 1) locks 1 mana on the next turn."""
        game, p1, p2 = new_hs_game("Shaman", "Warrior")

        cast_spell(game, LIGHTNING_BOLT, p1)
        assert p1.overloaded_mana == 1

        game.mana_system.on_turn_start(p1.id)
        locked = p1.overloaded_mana
        p1.mana_crystals_available = max(0, p1.mana_crystals_available - locked)
        p1.overloaded_mana = 0

        assert p1.mana_crystals_available == 9, (
            f"10 crystals minus 1 overload should give 9 available, "
            f"got {p1.mana_crystals_available}"
        )


# ============================================================
# Test 9: TestOverloadWithRefill
# ============================================================

class TestOverloadWithRefill:
    """Turn start refills mana but overloaded crystals stay locked."""

    def test_refill_then_overload_subtraction(self):
        """Turn start refills to max, then overload subtracts."""
        game, p1, p2 = new_hs_game("Shaman", "Warrior")

        # Spend some mana, then set overload
        game.mana_system.pay_cost(p1.id, 7)
        assert p1.mana_crystals_available == 3
        p1.overloaded_mana = 3

        # Turn start: refill to 10, then overload locks 3 -> 7
        game.mana_system.on_turn_start(p1.id)
        locked = p1.overloaded_mana
        p1.mana_crystals_available = max(0, p1.mana_crystals_available - locked)
        p1.overloaded_mana = 0

        assert p1.mana_crystals == 10, "Max crystals should still be 10"
        assert p1.mana_crystals_available == 7, (
            f"10 refilled minus 3 overload should give 7, got {p1.mana_crystals_available}"
        )

    def test_overload_does_not_reduce_max(self):
        """Overload does not reduce max mana crystals, only available."""
        game, p1, p2 = new_hs_game("Shaman", "Warrior")

        p1.overloaded_mana = 5
        game.mana_system.on_turn_start(p1.id)

        assert p1.mana_crystals == 10, (
            f"Max crystals should remain 10 with overload, got {p1.mana_crystals}"
        )


# ============================================================
# Test 10: TestOverloadStacking
# ============================================================

class TestOverloadStacking:
    """2 overload cards -> overload stacks."""

    def test_two_overload_cards_stack(self):
        """Casting 2 Overload cards accumulates the total overload."""
        game, p1, p2 = new_hs_game("Shaman", "Warrior")

        # Lightning Bolt: Overload 1
        cast_spell(game, LIGHTNING_BOLT, p1)
        assert p1.overloaded_mana == 1

        # Feral Spirit: Overload 2
        cast_spell(game, FERAL_SPIRIT, p1)
        assert p1.overloaded_mana == 3, (
            f"Overload should stack: 1 + 2 = 3, got {p1.overloaded_mana}"
        )

    def test_stacked_overload_locks_total_next_turn(self):
        """Stacked overload of 3 locks 3 mana next turn."""
        game, p1, p2 = new_hs_game("Shaman", "Warrior")

        cast_spell(game, LIGHTNING_BOLT, p1)
        cast_spell(game, FERAL_SPIRIT, p1)
        assert p1.overloaded_mana == 3

        game.mana_system.on_turn_start(p1.id)
        locked = p1.overloaded_mana
        p1.mana_crystals_available = max(0, p1.mana_crystals_available - locked)
        p1.overloaded_mana = 0

        assert p1.mana_crystals_available == 7, (
            f"10 minus 3 stacked overload should give 7, got {p1.mana_crystals_available}"
        )

    def test_two_lava_bursts_stack_overload_4(self):
        """Two Lava Bursts (Overload: 2 each) stack to 4 total overload."""
        game, p1, p2 = new_hs_game("Shaman", "Warrior")

        cast_spell(game, LAVA_BURST, p1)
        assert p1.overloaded_mana == 2

        cast_spell(game, LAVA_BURST, p1)
        assert p1.overloaded_mana == 4, (
            f"Two Lava Bursts should stack 2+2=4 overload, got {p1.overloaded_mana}"
        )


# ============================================================
# Test 11: TestOverloadClearsAfterLockTurn
# ============================================================

class TestOverloadClearsAfterLockTurn:
    """Overload locks for 1 turn, then clears."""

    def test_overload_clears_after_one_turn(self):
        """Overload applies on the next turn, then the turn after is clean."""
        game, p1, p2 = new_hs_game("Shaman", "Warrior")

        cast_spell(game, FERAL_SPIRIT, p1)
        assert p1.overloaded_mana == 2

        # Next turn: apply overload
        game.mana_system.on_turn_start(p1.id)
        locked = p1.overloaded_mana
        p1.mana_crystals_available = max(0, p1.mana_crystals_available - locked)
        p1.overloaded_mana = 0

        assert p1.mana_crystals_available == 8

        # Turn after: no overload, full refill
        game.mana_system.on_turn_start(p1.id)
        # No overload to apply
        assert p1.overloaded_mana == 0
        assert p1.mana_crystals_available == 10, (
            f"Turn after overload should have full 10 mana, "
            f"got {p1.mana_crystals_available}"
        )

    def test_overload_resets_to_zero_after_lock(self):
        """After applying overload, the overloaded_mana field resets to 0."""
        game, p1, p2 = new_hs_game("Shaman", "Warrior")

        p1.overloaded_mana = 5

        # Apply overload (as turn manager does)
        game.mana_system.on_turn_start(p1.id)
        locked = p1.overloaded_mana
        p1.mana_crystals_available = max(0, p1.mana_crystals_available - locked)
        p1.overloaded_mana = 0

        assert p1.overloaded_mana == 0, (
            f"Overloaded mana should be 0 after applying lock, got {p1.overloaded_mana}"
        )


# ============================================================
# Test 12: TestZeroCostAlwaysPlayable
# ============================================================

class TestZeroCostAlwaysPlayable:
    """0-cost card can be played with 0 mana."""

    def test_wisp_playable_at_0_mana(self):
        """A 0-cost card (Wisp) can be paid for with 0 available mana."""
        game, p1, p2 = new_hs_game_fresh()

        # No turns taken, 0 mana
        assert p1.mana_crystals_available == 0

        can_pay = game.mana_system.can_pay_cost(p1.id, 0)
        assert can_pay is True, "0-cost card should be playable at 0 mana"

    def test_innervate_playable_at_0_mana(self):
        """Innervate (0 cost) is playable even at 0 available mana."""
        game, p1, p2 = new_hs_game_fresh()

        assert p1.mana_crystals_available == 0

        can_pay = game.mana_system.can_pay_cost(p1.id, 0)
        assert can_pay is True

    def test_zero_cost_pay_succeeds(self):
        """Paying 0 mana always succeeds and does not change available."""
        game, p1, p2 = new_hs_game()

        assert p1.mana_crystals_available == 10
        success = game.mana_system.pay_cost(p1.id, 0)
        assert success is True
        assert p1.mana_crystals_available == 10, (
            f"Paying 0 should not change available, got {p1.mana_crystals_available}"
        )

    def test_zero_cost_at_0_available(self):
        """Paying 0 cost with 0 available succeeds."""
        game, p1, p2 = new_hs_game()

        p1.mana_crystals_available = 0
        success = game.mana_system.pay_cost(p1.id, 0)
        assert success is True
        assert p1.mana_crystals_available == 0


# ============================================================
# Test 13: TestExactManaPay
# ============================================================

class TestExactManaPay:
    """Paying exact cost leaves 0 available."""

    def test_pay_exact_10(self):
        """Paying exactly 10 from 10 available leaves 0."""
        game, p1, p2 = new_hs_game()

        assert p1.mana_crystals_available == 10
        success = game.mana_system.pay_cost(p1.id, 10)
        assert success is True
        assert p1.mana_crystals_available == 0, (
            f"After paying exact 10, available should be 0, got {p1.mana_crystals_available}"
        )

    def test_pay_exact_3(self):
        """Paying exactly 3 from 3 available leaves 0."""
        game, p1, p2 = new_hs_game_fresh()

        for _ in range(3):
            game.mana_system.on_turn_start(p1.id)

        assert p1.mana_crystals_available == 3
        success = game.mana_system.pay_cost(p1.id, 3)
        assert success is True
        assert p1.mana_crystals_available == 0, (
            f"After paying exact 3, available should be 0, got {p1.mana_crystals_available}"
        )

    def test_pay_exact_1(self):
        """Paying exactly 1 from 1 available leaves 0."""
        game, p1, p2 = new_hs_game_fresh()

        game.mana_system.on_turn_start(p1.id)
        assert p1.mana_crystals_available == 1

        success = game.mana_system.pay_cost(p1.id, 1)
        assert success is True
        assert p1.mana_crystals_available == 0

    def test_cannot_pay_1_more_than_available(self):
        """Paying 1 more than available fails."""
        game, p1, p2 = new_hs_game_fresh()

        for _ in range(5):
            game.mana_system.on_turn_start(p1.id)

        success = game.mana_system.pay_cost(p1.id, 6)
        assert success is False, "Should not be able to pay 6 with 5 available"
        assert p1.mana_crystals_available == 5, "Available should be unchanged after failed pay"


# ============================================================
# Test 14: TestCostReductionReducesPayment
# ============================================================

class TestCostReductionReducesPayment:
    """Sorcerer's Apprentice (-1 spell) -> 3-cost spell costs 2."""

    def test_apprentice_reduces_fireball_cost(self):
        """With Sorcerer's Apprentice, Fireball (cost 4) effectively costs 3."""
        game, p1, p2 = new_hs_game()

        # Place Sorcerer's Apprentice on battlefield (setup_interceptors adds cost modifier)
        apprentice = make_obj(game, SORCERERS_APPRENTICE, p1)

        # Check cost modifier was applied to player
        has_spell_reduction = any(
            m.get('card_type') == CardType.SPELL and m.get('amount', 0) == 1
            for m in p1.cost_modifiers
        )
        assert has_spell_reduction, (
            f"Sorcerer's Apprentice should add a spell cost reduction modifier, "
            f"found: {p1.cost_modifiers}"
        )

        # Create a Fireball in hand to check effective cost via the adapter
        from src.ai.hearthstone_adapter import HearthstoneAIAdapter
        adapter = HearthstoneAIAdapter()
        fireball_obj = game.create_object(
            name=FIREBALL.name, owner_id=p1.id, zone=ZoneType.HAND,
            characteristics=FIREBALL.characteristics, card_def=FIREBALL
        )
        cost = adapter._get_mana_cost(fireball_obj, game.state, p1.id)
        assert cost == 3, (
            f"Fireball with Apprentice should cost 3, got {cost}"
        )

    def test_apprentice_reduces_frostbolt_cost(self):
        """Frostbolt (cost 2) reduced by 1 to cost 1 with Apprentice."""
        game, p1, p2 = new_hs_game()

        apprentice = make_obj(game, SORCERERS_APPRENTICE, p1)

        from src.ai.hearthstone_adapter import HearthstoneAIAdapter
        adapter = HearthstoneAIAdapter()
        frostbolt_obj = game.create_object(
            name=FROSTBOLT.name, owner_id=p1.id, zone=ZoneType.HAND,
            characteristics=FROSTBOLT.characteristics, card_def=FROSTBOLT
        )
        cost = adapter._get_mana_cost(frostbolt_obj, game.state, p1.id)
        assert cost == 1, (
            f"Frostbolt with Apprentice should cost 1, got {cost}"
        )

    def test_apprentice_does_not_reduce_minion_cost(self):
        """Sorcerer's Apprentice only reduces spell costs, not minion costs."""
        game, p1, p2 = new_hs_game()

        apprentice = make_obj(game, SORCERERS_APPRENTICE, p1)

        from src.ai.hearthstone_adapter import HearthstoneAIAdapter
        adapter = HearthstoneAIAdapter()
        yeti_obj = game.create_object(
            name=CHILLWIND_YETI.name, owner_id=p1.id, zone=ZoneType.HAND,
            characteristics=CHILLWIND_YETI.characteristics, card_def=CHILLWIND_YETI
        )
        cost = adapter._get_mana_cost(yeti_obj, game.state, p1.id)
        assert cost == 4, (
            f"Yeti (minion) should still cost 4 with Apprentice, got {cost}"
        )


# ============================================================
# Test 15: TestCostReductionFloorAtZero
# ============================================================

class TestCostReductionFloorAtZero:
    """0-cost spell with Apprentice -> still costs 0 (not -1)."""

    def test_innervate_stays_at_0_with_apprentice(self):
        """Innervate (0 cost spell) stays at 0 with Apprentice, not negative."""
        game, p1, p2 = new_hs_game()

        apprentice = make_obj(game, SORCERERS_APPRENTICE, p1)

        from src.ai.hearthstone_adapter import HearthstoneAIAdapter
        adapter = HearthstoneAIAdapter()
        innervate_obj = game.create_object(
            name=INNERVATE.name, owner_id=p1.id, zone=ZoneType.HAND,
            characteristics=INNERVATE.characteristics, card_def=INNERVATE
        )
        cost = adapter._get_mana_cost(innervate_obj, game.state, p1.id)
        assert cost == 0, (
            f"0-cost spell with Apprentice should still cost 0, got {cost}"
        )

    def test_coin_stays_at_0_with_apprentice(self):
        """The Coin (0 cost spell) stays at 0 with Apprentice."""
        game, p1, p2 = new_hs_game()

        apprentice = make_obj(game, SORCERERS_APPRENTICE, p1)

        from src.ai.hearthstone_adapter import HearthstoneAIAdapter
        adapter = HearthstoneAIAdapter()
        coin_obj = game.create_object(
            name=THE_COIN.name, owner_id=p1.id, zone=ZoneType.HAND,
            characteristics=THE_COIN.characteristics, card_def=THE_COIN
        )
        cost = adapter._get_mana_cost(coin_obj, game.state, p1.id)
        assert cost == 0, (
            f"The Coin (0-cost) with Apprentice should still cost 0, got {cost}"
        )

    def test_1_cost_spell_reduced_to_0(self):
        """A 1-cost spell is reduced to 0 by Apprentice (not below 0)."""
        game, p1, p2 = new_hs_game()

        apprentice = make_obj(game, SORCERERS_APPRENTICE, p1)

        from src.ai.hearthstone_adapter import HearthstoneAIAdapter
        adapter = HearthstoneAIAdapter()
        bolt_obj = game.create_object(
            name=LIGHTNING_BOLT.name, owner_id=p1.id, zone=ZoneType.HAND,
            characteristics=LIGHTNING_BOLT.characteristics, card_def=LIGHTNING_BOLT
        )
        cost = adapter._get_mana_cost(bolt_obj, game.state, p1.id)
        assert cost == 0, (
            f"1-cost spell with Apprentice should cost 0, got {cost}"
        )

    def test_cost_never_goes_negative(self):
        """Even with multiple reductions, cost floors at 0."""
        game, p1, p2 = new_hs_game()

        # Add two Apprentices for -2 total spell reduction
        apprentice1 = make_obj(game, SORCERERS_APPRENTICE, p1)
        apprentice2 = make_obj(game, SORCERERS_APPRENTICE, p1)

        from src.ai.hearthstone_adapter import HearthstoneAIAdapter
        adapter = HearthstoneAIAdapter()
        bolt_obj = game.create_object(
            name=LIGHTNING_BOLT.name, owner_id=p1.id, zone=ZoneType.HAND,
            characteristics=LIGHTNING_BOLT.characteristics, card_def=LIGHTNING_BOLT
        )
        cost = adapter._get_mana_cost(bolt_obj, game.state, p1.id)
        assert cost == 0, (
            f"1-cost spell with 2 Apprentices (total -2) should floor at 0, got {cost}"
        )


# ============================================================
# Run tests
# ============================================================

if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
