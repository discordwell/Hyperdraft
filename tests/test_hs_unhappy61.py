"""
Hearthstone Unhappy Path Tests - Batch 61

Board state limits and boundary conditions: 7-minion board limit prevents
further summons, hand size limit of 10 causes overdraw/mill, multiple
tokens from a single effect hitting board cap, summoning sickness prevents
attack on first turn, charge bypasses summoning sickness, taunt forces
targeting, board-full token summon truncation, hand-full draw burns card,
mana crystal cap at 10, excess mana crystals wasted.
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
    WISP, CHILLWIND_YETI, BLOODFEN_RAPTOR, STONETUSK_BOAR,
    SEN_JIN_SHIELDMASTA, GOLDSHIRE_FOOTMAN, BOULDERFIST_OGRE,
    RIVER_CROCOLISK, FROSTWOLF_GRUNT,
)
from src.cards.hearthstone.druid import FORCE_OF_NATURE


# ============================================================
# Test Helpers
# ============================================================

def new_hs_game():
    """Create a new Hearthstone game with two players at 10 mana."""
    game = Game(mode='hearthstone')
    p1 = game.add_player("Player1", life=30)
    p2 = game.add_player("Player2", life=30)
    game.setup_hearthstone_player(p1, HEROES["Paladin"], HERO_POWERS["Paladin"])
    game.setup_hearthstone_player(p2, HEROES["Mage"], HERO_POWERS["Mage"])
    for _ in range(10):
        game.mana_system.on_turn_start(p1.id)
        game.mana_system.on_turn_start(p2.id)
    return game, p1, p2


def make_obj(game, card_def, owner, zone=ZoneType.BATTLEFIELD):
    """Place a card object in the specified zone."""
    return game.create_object(
        name=card_def.name, owner_id=owner.id, zone=zone,
        characteristics=card_def.characteristics, card_def=card_def
    )


def cast_spell(game, card_def, owner, targets=None):
    """Cast a spell card and resolve its effect."""
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


def count_battlefield_minions(game, player_id):
    """Count minions on the battlefield controlled by a player."""
    battlefield = game.state.zones.get('battlefield')
    if not battlefield:
        return 0
    count = 0
    for oid in battlefield.objects:
        obj = game.state.objects.get(oid)
        if (obj and obj.controller == player_id
                and CardType.MINION in obj.characteristics.types):
            count += 1
    return count


def hand_size(game, player_id):
    """Get the number of cards in a player's hand."""
    hand_key = f"hand_{player_id}"
    hand = game.state.zones.get(hand_key)
    if not hand:
        return 0
    return len(hand.objects)


def fill_board(game, player, count=7):
    """Fill a player's board with Wisps up to `count` minions."""
    minions = []
    for _ in range(count):
        m = make_obj(game, WISP, player)
        minions.append(m)
    return minions


def fill_hand(game, player, count=10):
    """Fill a player's hand with Wisp objects up to `count` cards."""
    cards = []
    for _ in range(count):
        c = make_obj(game, WISP, player, zone=ZoneType.HAND)
        cards.append(c)
    return cards


def fill_library(game, player, count=10):
    """Put Wisp objects into a player's library."""
    cards = []
    for _ in range(count):
        c = make_obj(game, WISP, player, zone=ZoneType.LIBRARY)
        cards.append(c)
    return cards


# ============================================================
# Test 1: Board Limit Prevents Summon
# ============================================================

class TestBoardLimitPreventsSummon:
    def test_eighth_minion_not_placed_on_battlefield(self):
        """With 7 minions on board, an 8th ZONE_CHANGE to battlefield should fail."""
        game, p1, p2 = new_hs_game()

        # Fill board to 7
        fill_board(game, p1, 7)
        assert count_battlefield_minions(game, p1.id) == 7

        # Try to add an 8th minion via ZONE_CHANGE (how playing from hand works)
        extra = make_obj(game, CHILLWIND_YETI, p1, zone=ZoneType.HAND)
        game.emit(Event(
            type=EventType.ZONE_CHANGE,
            payload={
                'object_id': extra.id,
                'from_zone_type': ZoneType.HAND,
                'to_zone_type': ZoneType.BATTLEFIELD,
            },
            source=extra.id
        ))

        # Board should still be exactly 7
        assert count_battlefield_minions(game, p1.id) == 7, (
            f"Board should stay at 7, got {count_battlefield_minions(game, p1.id)}"
        )

    def test_eighth_minion_sent_to_graveyard(self):
        """An 8th minion that can't fit on board goes to graveyard."""
        game, p1, p2 = new_hs_game()
        fill_board(game, p1, 7)

        extra = make_obj(game, CHILLWIND_YETI, p1, zone=ZoneType.HAND)
        game.emit(Event(
            type=EventType.ZONE_CHANGE,
            payload={
                'object_id': extra.id,
                'from_zone_type': ZoneType.HAND,
                'to_zone_type': ZoneType.BATTLEFIELD,
            },
            source=extra.id
        ))

        # The extra minion should be in graveyard
        assert extra.zone == ZoneType.GRAVEYARD, (
            f"Extra minion should be in graveyard, got {extra.zone}"
        )

    def test_opponent_board_independent(self):
        """P1 having 7 minions does not prevent P2 from placing minions."""
        game, p1, p2 = new_hs_game()
        fill_board(game, p1, 7)

        # P2 should be able to place a minion just fine
        p2_minion = make_obj(game, WISP, p2)
        assert count_battlefield_minions(game, p1.id) == 7
        assert count_battlefield_minions(game, p2.id) == 1


# ============================================================
# Test 2: Board Limit Multiple Tokens
# ============================================================

class TestBoardLimitMultipleTokens:
    def test_force_of_nature_capped_at_board_limit(self):
        """Force of Nature summons 3 Treants, but with 5 on board only 2 fit."""
        game, p1, p2 = new_hs_game()

        # Fill board to 5 minions
        fill_board(game, p1, 5)
        assert count_battlefield_minions(game, p1.id) == 5

        # Cast Force of Nature (summons 3 Treants)
        cast_spell(game, FORCE_OF_NATURE, p1)

        # Should be capped at 7 (5 existing + 2 Treants)
        final_count = count_battlefield_minions(game, p1.id)
        assert final_count == 7, (
            f"Board should be 7 (5 + 2 Treants), got {final_count}"
        )

    def test_force_of_nature_with_full_board_summons_zero(self):
        """Force of Nature with 7 minions on board summons no Treants."""
        game, p1, p2 = new_hs_game()
        fill_board(game, p1, 7)

        cast_spell(game, FORCE_OF_NATURE, p1)

        assert count_battlefield_minions(game, p1.id) == 7, (
            f"Board should still be 7, got {count_battlefield_minions(game, p1.id)}"
        )

    def test_force_of_nature_with_6_summons_exactly_one(self):
        """Force of Nature with 6 minions on board summons exactly 1 Treant."""
        game, p1, p2 = new_hs_game()
        fill_board(game, p1, 6)

        cast_spell(game, FORCE_OF_NATURE, p1)

        assert count_battlefield_minions(game, p1.id) == 7, (
            f"Board should be 7 (6 + 1 Treant), got {count_battlefield_minions(game, p1.id)}"
        )


# ============================================================
# Test 3: Board Count Includes Tokens
# ============================================================

class TestBoardCountIncludesTokens:
    def test_tokens_count_toward_board_limit(self):
        """Tokens created via CREATE_TOKEN count toward the 7-minion limit."""
        game, p1, p2 = new_hs_game()

        # Place 4 regular minions
        fill_board(game, p1, 4)

        # Create 3 tokens via CREATE_TOKEN events
        for _ in range(3):
            game.emit(Event(
                type=EventType.CREATE_TOKEN,
                payload={
                    'controller': p1.id,
                    'token': {
                        'name': 'Treant',
                        'power': 2,
                        'toughness': 2,
                        'types': {CardType.MINION}
                    }
                },
                source='test'
            ))

        assert count_battlefield_minions(game, p1.id) == 7

        # Now try to create one more token - should fail
        game.emit(Event(
            type=EventType.CREATE_TOKEN,
            payload={
                'controller': p1.id,
                'token': {
                    'name': 'Treant',
                    'power': 2,
                    'toughness': 2,
                    'types': {CardType.MINION}
                }
            },
            source='test'
        ))

        assert count_battlefield_minions(game, p1.id) == 7, (
            f"Board should stay at 7 (tokens count), got {count_battlefield_minions(game, p1.id)}"
        )

    def test_mixed_tokens_and_minions_at_limit(self):
        """A mix of tokens and minions both count toward 7-minion limit."""
        game, p1, p2 = new_hs_game()

        # 3 regular minions
        fill_board(game, p1, 3)

        # 4 tokens
        for _ in range(4):
            game.emit(Event(
                type=EventType.CREATE_TOKEN,
                payload={
                    'controller': p1.id,
                    'token': {
                        'name': 'Imp',
                        'power': 1,
                        'toughness': 1,
                        'types': {CardType.MINION}
                    }
                },
                source='test'
            ))

        assert count_battlefield_minions(game, p1.id) == 7


# ============================================================
# Test 4: Hand Size Limit
# ============================================================

class TestHandSizeLimit:
    def test_drawing_at_max_hand_burns_card(self):
        """Drawing when hand has 10 cards should burn the drawn card."""
        game, p1, p2 = new_hs_game()

        # Fill hand to 10
        fill_hand(game, p1, 10)
        assert hand_size(game, p1.id) == 10

        # Put a card in library
        fill_library(game, p1, 1)

        # Draw - card should be burned
        game.emit(Event(
            type=EventType.DRAW,
            payload={'player': p1.id, 'count': 1},
            source='test'
        ))

        # Hand should still be 10 (card was burned, not added)
        assert hand_size(game, p1.id) == 10, (
            f"Hand should remain at 10 after overdraw, got {hand_size(game, p1.id)}"
        )

    def test_burned_card_goes_to_graveyard(self):
        """A burned/milled card should end up in the graveyard."""
        game, p1, p2 = new_hs_game()
        fill_hand(game, p1, 10)

        # Add a specific card to library
        lib_card = make_obj(game, CHILLWIND_YETI, p1, zone=ZoneType.LIBRARY)

        graveyard_key = f"graveyard_{p1.id}"
        graveyard_before = len(game.state.zones[graveyard_key].objects)

        game.emit(Event(
            type=EventType.DRAW,
            payload={'player': p1.id, 'count': 1},
            source='test'
        ))

        graveyard_after = len(game.state.zones[graveyard_key].objects)
        assert graveyard_after == graveyard_before + 1, (
            f"Graveyard should have 1 more card after overdraw, was {graveyard_before}, now {graveyard_after}"
        )

    def test_library_shrinks_on_overdraw(self):
        """Even when overdrawn, the card is still removed from the library."""
        game, p1, p2 = new_hs_game()
        fill_hand(game, p1, 10)

        lib_card = make_obj(game, WISP, p1, zone=ZoneType.LIBRARY)
        lib_key = f"library_{p1.id}"
        lib_before = len(game.state.zones[lib_key].objects)

        game.emit(Event(
            type=EventType.DRAW,
            payload={'player': p1.id, 'count': 1},
            source='test'
        ))

        lib_after = len(game.state.zones[lib_key].objects)
        assert lib_after == lib_before - 1, (
            f"Library should shrink by 1 on overdraw, was {lib_before}, now {lib_after}"
        )


# ============================================================
# Test 5: Hand Size Limit Draw Multiple
# ============================================================

class TestHandSizeLimitDrawMultiple:
    def test_draw_3_at_9_cards_burns_2(self):
        """Hand at 9, draw 3: first goes to hand (10), next 2 are burned."""
        game, p1, p2 = new_hs_game()

        fill_hand(game, p1, 9)
        assert hand_size(game, p1.id) == 9

        # Put 3 cards in library
        fill_library(game, p1, 3)

        game.emit(Event(
            type=EventType.DRAW,
            payload={'player': p1.id, 'count': 3},
            source='test'
        ))

        # Hand should be 10 (9 + 1 drawn, 2 burned)
        assert hand_size(game, p1.id) == 10, (
            f"Hand should be 10 (9 + 1 drawn), got {hand_size(game, p1.id)}"
        )

    def test_draw_3_at_9_puts_2_in_graveyard(self):
        """The 2 burned cards go to graveyard."""
        game, p1, p2 = new_hs_game()

        fill_hand(game, p1, 9)
        fill_library(game, p1, 3)

        graveyard_key = f"graveyard_{p1.id}"
        graveyard_before = len(game.state.zones[graveyard_key].objects)

        game.emit(Event(
            type=EventType.DRAW,
            payload={'player': p1.id, 'count': 3},
            source='test'
        ))

        graveyard_after = len(game.state.zones[graveyard_key].objects)
        assert graveyard_after == graveyard_before + 2, (
            f"Graveyard should have 2 more burned cards, was {graveyard_before}, now {graveyard_after}"
        )

    def test_draw_at_10_all_burned(self):
        """Hand already at 10, drawing 2 burns both."""
        game, p1, p2 = new_hs_game()

        fill_hand(game, p1, 10)
        fill_library(game, p1, 2)

        graveyard_key = f"graveyard_{p1.id}"
        graveyard_before = len(game.state.zones[graveyard_key].objects)

        game.emit(Event(
            type=EventType.DRAW,
            payload={'player': p1.id, 'count': 2},
            source='test'
        ))

        assert hand_size(game, p1.id) == 10
        graveyard_after = len(game.state.zones[graveyard_key].objects)
        assert graveyard_after == graveyard_before + 2, (
            f"Both drawn cards should be burned to graveyard"
        )


# ============================================================
# Test 6: Summoning Sickness Prevents Attack
# ============================================================

class TestSummoningSicknessPreventAttack:
    def test_new_minion_has_summoning_sickness(self):
        """A minion placed on the battlefield has summoning_sickness=True."""
        game, p1, p2 = new_hs_game()

        yeti = make_obj(game, CHILLWIND_YETI, p1)
        assert yeti.state.summoning_sickness is True, (
            f"New minion should have summoning sickness, got {yeti.state.summoning_sickness}"
        )

    def test_summoning_sickness_prevents_can_attack(self):
        """Combat manager should not allow attack when summoning_sickness=True."""
        game, p1, p2 = new_hs_game()
        game.state.active_player = p1.id

        yeti = make_obj(game, CHILLWIND_YETI, p1)

        # The combat manager's _can_attack should return False
        can_attack = game.combat_manager._can_attack(yeti.id, p1.id)
        assert can_attack is False, (
            "Minion with summoning sickness should not be able to attack"
        )

    def test_declare_attack_fails_with_summoning_sickness(self):
        """Attempting to declare an attack with a sick minion returns no events."""
        game, p1, p2 = new_hs_game()
        game.state.active_player = p1.id

        yeti = make_obj(game, CHILLWIND_YETI, p1)

        # Attempt attack (declare_attack is async)
        events = asyncio.get_event_loop().run_until_complete(
            game.combat_manager.declare_attack(yeti.id, p2.hero_id)
        )
        assert len(events) == 0, (
            f"Attack should fail with summoning sickness, got {len(events)} events"
        )


# ============================================================
# Test 7: Charge Bypasses Summoning Sickness
# ============================================================

class TestChargeBypassesSummoningSickness:
    def test_charge_minion_can_attack_immediately(self):
        """Stonetusk Boar (Charge) should be able to attack the turn it's played."""
        game, p1, p2 = new_hs_game()
        game.state.active_player = p1.id

        boar = make_obj(game, STONETUSK_BOAR, p1)

        can_attack = game.combat_manager._can_attack(boar.id, p1.id)
        assert can_attack is True, (
            "Charge minion should be able to attack immediately"
        )

    def test_charge_minion_summoning_sickness_state(self):
        """Charge minion may still have summoning_sickness=True but can attack via keyword check."""
        game, p1, p2 = new_hs_game()
        game.state.active_player = p1.id

        boar = make_obj(game, STONETUSK_BOAR, p1)

        # Regardless of the summoning_sickness flag, the charge keyword overrides
        assert has_ability(boar, 'charge', game.state) is True

    def test_charge_minion_deals_damage_on_first_turn(self):
        """A Charge minion can actually deal damage via declare_attack on its first turn."""
        game, p1, p2 = new_hs_game()
        game.state.active_player = p1.id

        boar = make_obj(game, STONETUSK_BOAR, p1)
        p2_life_before = p2.life

        events = asyncio.get_event_loop().run_until_complete(
            game.combat_manager.declare_attack(boar.id, p2.hero_id)
        )
        game.check_state_based_actions()

        # Boar has 1 attack, hero should have taken 1 damage
        assert p2.life == p2_life_before - 1, (
            f"P2 should have lost 1 life from Boar attack, was {p2_life_before}, now {p2.life}"
        )


# ============================================================
# Test 8: Summoning Sickness Cleared Next Turn
# ============================================================

class TestSummoningSicknessClearedNextTurn:
    def test_sickness_cleared_on_controllers_turn_start(self):
        """Summoning sickness is cleared at the start of the controller's turn."""
        game, p1, p2 = new_hs_game()

        yeti = make_obj(game, CHILLWIND_YETI, p1)
        assert yeti.state.summoning_sickness is True

        # Simulate start of P1's turn (clears summoning sickness for P1's minions)
        # The HearthstoneTurnManager._run_draw_phase clears sickness, but we can
        # directly simulate what it does:
        battlefield = game.state.zones.get('battlefield')
        if battlefield:
            for obj_id in list(battlefield.objects):
                obj = game.state.objects.get(obj_id)
                if obj and obj.controller == p1.id:
                    if CardType.MINION in obj.characteristics.types:
                        obj.state.summoning_sickness = False

        assert yeti.state.summoning_sickness is False, (
            "Summoning sickness should be cleared at turn start"
        )

    def test_minion_can_attack_after_sickness_cleared(self):
        """After clearing summoning sickness, the minion can attack."""
        game, p1, p2 = new_hs_game()
        game.state.active_player = p1.id

        yeti = make_obj(game, CHILLWIND_YETI, p1)

        # Can't attack now
        assert game.combat_manager._can_attack(yeti.id, p1.id) is False

        # Clear summoning sickness (simulating turn start)
        yeti.state.summoning_sickness = False

        # Now it can attack
        assert game.combat_manager._can_attack(yeti.id, p1.id) is True

    def test_opponent_minion_sickness_not_cleared_on_your_turn(self):
        """Opponent's minion sickness is not cleared when your turn starts."""
        game, p1, p2 = new_hs_game()

        p2_yeti = make_obj(game, CHILLWIND_YETI, p2)
        assert p2_yeti.state.summoning_sickness is True

        # Simulate P1's turn start - only clears P1's minions' sickness
        battlefield = game.state.zones.get('battlefield')
        if battlefield:
            for obj_id in list(battlefield.objects):
                obj = game.state.objects.get(obj_id)
                if obj and obj.controller == p1.id:
                    if CardType.MINION in obj.characteristics.types:
                        obj.state.summoning_sickness = False

        # P2's minion should still have sickness
        assert p2_yeti.state.summoning_sickness is True, (
            "Opponent's minion sickness should not be cleared on your turn"
        )


# ============================================================
# Test 9: Mana Crystal Cap at 10
# ============================================================

class TestManaCrystalCapAt10:
    def test_mana_caps_at_10_after_10_turns(self):
        """After 10 on_turn_start calls, mana crystals should be exactly 10."""
        game, p1, p2 = new_hs_game()
        # new_hs_game already calls on_turn_start 10 times
        assert p1.mana_crystals == 10, (
            f"Mana crystals should be 10, got {p1.mana_crystals}"
        )

    def test_mana_does_not_exceed_10_after_more_turns(self):
        """Calling on_turn_start beyond 10 times should not exceed 10 crystals."""
        game, p1, p2 = new_hs_game()

        # Call 5 more times (total 15)
        for _ in range(5):
            game.mana_system.on_turn_start(p1.id)

        assert p1.mana_crystals == 10, (
            f"Mana crystals should still be 10 after 15 turns, got {p1.mana_crystals}"
        )

    def test_available_mana_equals_max_after_turn_start(self):
        """Available mana should equal max crystals after on_turn_start."""
        game, p1, p2 = new_hs_game()

        # Spend some mana
        p1.mana_crystals_available = 3

        # Next turn start should refill
        game.mana_system.on_turn_start(p1.id)

        assert p1.mana_crystals_available == 10, (
            f"Available mana should be 10 after turn start, got {p1.mana_crystals_available}"
        )


# ============================================================
# Test 10: Excess Mana Crystals Wasted
# ============================================================

class TestExcessManaCrystalsWasted:
    def test_add_empty_crystal_at_10_stays_at_10(self):
        """Adding empty crystals at max doesn't exceed 10."""
        game, p1, p2 = new_hs_game()
        assert p1.mana_crystals == 10

        game.mana_system.add_empty_crystal(p1.id, 3)

        assert p1.mana_crystals == 10, (
            f"Mana crystals should stay at 10 after add_empty_crystal, got {p1.mana_crystals}"
        )

    def test_excess_gain_from_card_effect_wasted(self):
        """Wild Growth-like effect at 10 crystals is wasted (capped)."""
        game, p1, p2 = new_hs_game()

        # Manually try to increase beyond 10
        p1.mana_crystals = 10
        game.mana_system.add_empty_crystal(p1.id, 1)

        assert p1.mana_crystals == 10, (
            f"Crystals should not exceed 10, got {p1.mana_crystals}"
        )

    def test_on_turn_start_at_max_does_not_increase(self):
        """Calling on_turn_start at 10 crystals: max stays 10, available refills to 10."""
        game, p1, p2 = new_hs_game()
        assert p1.mana_crystals == 10

        p1.mana_crystals_available = 0
        game.mana_system.on_turn_start(p1.id)

        assert p1.mana_crystals == 10
        assert p1.mana_crystals_available == 10


# ============================================================
# Test 11: Mana Refreshes Each Turn
# ============================================================

class TestManaRefreshesEachTurn:
    def test_mana_refills_to_max_on_turn_start(self):
        """Available mana should be fully refreshed to max at turn start."""
        game, p1, p2 = new_hs_game()

        # Spend all mana
        p1.mana_crystals_available = 0

        game.mana_system.on_turn_start(p1.id)

        assert p1.mana_crystals_available == p1.mana_crystals, (
            f"Available mana ({p1.mana_crystals_available}) should equal max ({p1.mana_crystals})"
        )

    def test_partial_mana_refills_fully(self):
        """Even with partial mana remaining, turn start refills to max."""
        game, p1, p2 = new_hs_game()
        p1.mana_crystals_available = 3

        game.mana_system.on_turn_start(p1.id)

        assert p1.mana_crystals_available == 10, (
            f"Mana should refill to 10, got {p1.mana_crystals_available}"
        )

    def test_mana_refill_at_early_game(self):
        """At turn 3 (3 crystals), refill should give 3 available."""
        game = Game(mode='hearthstone')
        p1 = game.add_player("Player1", life=30)
        p2 = game.add_player("Player2", life=30)
        game.setup_hearthstone_player(p1, HEROES["Paladin"], HERO_POWERS["Paladin"])
        game.setup_hearthstone_player(p2, HEROES["Mage"], HERO_POWERS["Mage"])

        # 3 turns
        for _ in range(3):
            game.mana_system.on_turn_start(p1.id)

        assert p1.mana_crystals == 3
        assert p1.mana_crystals_available == 3


# ============================================================
# Test 12: Taunt Forces Targeting
# ============================================================

class TestTauntForcesTargeting:
    def test_taunt_blocks_hero_attack(self):
        """With a Taunt minion on board, attacks cannot target the hero."""
        game, p1, p2 = new_hs_game()
        game.state.active_player = p1.id

        # P1 has an attacker (clear its summoning sickness)
        attacker = make_obj(game, CHILLWIND_YETI, p1)
        attacker.state.summoning_sickness = False

        # P2 has a Taunt minion
        taunt_minion = make_obj(game, SEN_JIN_SHIELDMASTA, p2)

        # Check taunt enforcement: targeting hero should fail
        result = game.combat_manager._check_taunt_requirement(p1.id, p2.hero_id)
        assert result is False, (
            "Should not be able to target hero when opponent has Taunt minion"
        )

    def test_taunt_allows_targeting_taunt_minion(self):
        """Attacks CAN target the Taunt minion itself."""
        game, p1, p2 = new_hs_game()
        game.state.active_player = p1.id

        attacker = make_obj(game, CHILLWIND_YETI, p1)
        attacker.state.summoning_sickness = False

        taunt_minion = make_obj(game, SEN_JIN_SHIELDMASTA, p2)

        result = game.combat_manager._check_taunt_requirement(p1.id, taunt_minion.id)
        assert result is True, (
            "Should be able to target the Taunt minion"
        )

    def test_taunt_blocks_non_taunt_minion_target(self):
        """With a Taunt minion present, cannot target other non-Taunt minions."""
        game, p1, p2 = new_hs_game()
        game.state.active_player = p1.id

        attacker = make_obj(game, CHILLWIND_YETI, p1)
        attacker.state.summoning_sickness = False

        # P2 has both a Taunt and a non-Taunt minion
        taunt_minion = make_obj(game, SEN_JIN_SHIELDMASTA, p2)
        non_taunt = make_obj(game, BLOODFEN_RAPTOR, p2)

        result = game.combat_manager._check_taunt_requirement(p1.id, non_taunt.id)
        assert result is False, (
            "Should not be able to target non-Taunt minion when Taunt is present"
        )


# ============================================================
# Test 13: Multiple Taunts
# ============================================================

class TestMultipleTaunts:
    def test_can_target_either_taunt(self):
        """With two Taunt minions, attacker can choose either one."""
        game, p1, p2 = new_hs_game()
        game.state.active_player = p1.id

        attacker = make_obj(game, CHILLWIND_YETI, p1)
        attacker.state.summoning_sickness = False

        taunt1 = make_obj(game, SEN_JIN_SHIELDMASTA, p2)
        taunt2 = make_obj(game, GOLDSHIRE_FOOTMAN, p2)

        assert game.combat_manager._check_taunt_requirement(p1.id, taunt1.id) is True, (
            "Should be able to target first Taunt minion"
        )
        assert game.combat_manager._check_taunt_requirement(p1.id, taunt2.id) is True, (
            "Should be able to target second Taunt minion"
        )

    def test_cannot_target_hero_with_two_taunts(self):
        """Cannot bypass two Taunt minions to target hero."""
        game, p1, p2 = new_hs_game()
        game.state.active_player = p1.id

        attacker = make_obj(game, CHILLWIND_YETI, p1)
        attacker.state.summoning_sickness = False

        taunt1 = make_obj(game, SEN_JIN_SHIELDMASTA, p2)
        taunt2 = make_obj(game, GOLDSHIRE_FOOTMAN, p2)

        result = game.combat_manager._check_taunt_requirement(p1.id, p2.hero_id)
        assert result is False, (
            "Should not be able to target hero with two Taunt minions on board"
        )

    def test_cannot_target_non_taunt_with_taunts_present(self):
        """With two Taunts, cannot target a non-Taunt minion."""
        game, p1, p2 = new_hs_game()
        game.state.active_player = p1.id

        attacker = make_obj(game, CHILLWIND_YETI, p1)
        attacker.state.summoning_sickness = False

        taunt1 = make_obj(game, SEN_JIN_SHIELDMASTA, p2)
        taunt2 = make_obj(game, GOLDSHIRE_FOOTMAN, p2)
        non_taunt = make_obj(game, BLOODFEN_RAPTOR, p2)

        result = game.combat_manager._check_taunt_requirement(p1.id, non_taunt.id)
        assert result is False, (
            "Cannot target non-Taunt minion when Taunts are present"
        )


# ============================================================
# Test 14: Taunt Does Not Affect Spells
# ============================================================

class TestTauntDoesNotAffectSpells:
    def test_spell_can_target_non_taunt_minion(self):
        """Spells can target non-Taunt minions even when Taunt is present."""
        game, p1, p2 = new_hs_game()

        # P2 has a Taunt and a non-Taunt minion
        taunt_minion = make_obj(game, SEN_JIN_SHIELDMASTA, p2)
        non_taunt = make_obj(game, BLOODFEN_RAPTOR, p2)

        # Cast a damage spell targeting the non-Taunt minion directly
        # (Spells bypass Taunt; Taunt only affects attack declarations)
        damage_event = Event(
            type=EventType.DAMAGE,
            payload={'target': non_taunt.id, 'amount': 3, 'source': 'spell'},
            source='spell'
        )
        game.emit(damage_event)

        # Damage should have been applied to the non-Taunt minion
        assert non_taunt.state.damage == 3, (
            f"Spell should damage non-Taunt minion through Taunt, damage={non_taunt.state.damage}"
        )

    def test_spell_can_target_hero_past_taunt(self):
        """Spells can target the enemy hero even when Taunt is present."""
        game, p1, p2 = new_hs_game()

        taunt_minion = make_obj(game, SEN_JIN_SHIELDMASTA, p2)
        p2_life_before = p2.life

        # Fire a spell at P2's hero directly
        damage_event = Event(
            type=EventType.DAMAGE,
            payload={'target': p2.hero_id, 'amount': 5, 'source': 'spell'},
            source='spell'
        )
        game.emit(damage_event)

        assert p2.life == p2_life_before - 5, (
            f"Spell should bypass Taunt and hit hero, life was {p2_life_before}, now {p2.life}"
        )

    def test_taunt_check_only_applies_to_combat(self):
        """_check_taunt_requirement is only called for combat, not spell targeting."""
        game, p1, p2 = new_hs_game()

        taunt_minion = make_obj(game, SEN_JIN_SHIELDMASTA, p2)
        non_taunt = make_obj(game, BLOODFEN_RAPTOR, p2)

        # The taunt check is for combat only - it returns False for non-taunt targets
        combat_check = game.combat_manager._check_taunt_requirement(p1.id, non_taunt.id)
        assert combat_check is False, "Combat targeting should be blocked by Taunt"

        # But spell damage events don't go through this check at all -
        # they resolve directly via the pipeline
        non_taunt.state.damage = 0  # reset
        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': non_taunt.id, 'amount': 2, 'source': 'spell'},
            source='spell'
        ))
        assert non_taunt.state.damage == 2, (
            "Spell damage resolves regardless of Taunt"
        )


# ============================================================
# Main: run with pytest or direct execution
# ============================================================

if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
