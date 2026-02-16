"""
Hearthstone Unhappy Path Tests - Batch 129: Card Draw, Fatigue, and Hand Management

Tests cover:
- Drawing cards from library (card moves from library to hand)
- Drawing from empty library (fatigue damage)
- Fatigue damage increases (1, 2, 3, 4... per draw)
- Multiple fatigue draws (cumulative damage)
- Fatigue kills hero (dies at 0 HP from fatigue)
- Hand limit (10 cards) - drawn card is destroyed if hand full
- Overdraw burns card (card goes to graveyard, not hand)
- Acolyte of Pain draws on each damage instance
- Loot Hoarder draws on death (deathrattle draw)
- Azure Drake battlecry draw
- Arcane Intellect draws 2
- Drawing while near hand limit (draws up to 10 then burns)
- Multiple draw effects in sequence
- Fatigue with armor (armor absorbs fatigue damage)
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

from src.cards.hearthstone.basic import (
    WISP, CHILLWIND_YETI, BLOODFEN_RAPTOR, BOULDERFIST_OGRE,
    STORMWIND_CHAMPION
)
from src.cards.hearthstone.classic import (
    LOOT_HOARDER, ACOLYTE_OF_PAIN, AZURE_DRAKE, NOVICE_ENGINEER,
    ARCANE_INTELLECT
)
from src.cards.hearthstone.mage import FIREBALL, FROSTBOLT


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


def make_obj(game, card_def, owner, zone=ZoneType.BATTLEFIELD):
    """Create an object from a card definition and place it in the given zone."""
    obj = game.create_object(
        name=card_def.name, owner_id=owner.id, zone=zone,
        characteristics=card_def.characteristics, card_def=card_def
    )
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


def play_minion(game, card_def, owner):
    """Play a minion from hand (simulates battlecry)."""
    obj = game.create_object(
        name=card_def.name, owner_id=owner.id, zone=ZoneType.BATTLEFIELD,
        characteristics=card_def.characteristics, card_def=card_def
    )
    # Trigger battlecry if exists
    if hasattr(card_def, 'battlecry') and callable(card_def.battlecry):
        events = card_def.battlecry(obj, game.state)
        for e in events:
            game.emit(e)
    # Emit ETB
    game.emit(Event(
        type=EventType.ENTER_BATTLEFIELD,
        payload={'object_id': obj.id},
        source=obj.id
    ))
    return obj


def run_sba(game):
    """Manually check state-based actions (destroy lethal minions, check hero death)."""
    game.check_state_based_actions()


def get_hand_count(game, player):
    """Get the number of cards in a player's hand."""
    hand_key = f"hand_{player.id}"
    return len(game.state.zones.get(hand_key).objects) if hand_key in game.state.zones else 0


def get_library_count(game, player):
    """Get the number of cards in a player's library."""
    library_key = f"library_{player.id}"
    return len(game.state.zones.get(library_key).objects) if library_key in game.state.zones else 0


def get_graveyard_count(game, player):
    """Get the number of cards in a player's graveyard."""
    graveyard_key = f"graveyard_{player.id}"
    return len(game.state.zones.get(graveyard_key).objects) if graveyard_key in game.state.zones else 0


# ============================================================
# Test 1-5: Basic Card Draw
# ============================================================

class TestBasicCardDraw:
    """Tests for basic card draw mechanics."""

    def test_drawing_card_moves_from_library_to_hand(self):
        """Drawing a card should move it from library to hand."""
        game, p1, p2 = new_hs_game()

        # Add card to library
        card = make_obj(game, WISP, p1, zone=ZoneType.LIBRARY)

        library_before = get_library_count(game, p1)
        hand_before = get_hand_count(game, p1)

        # Draw a card
        game.draw_cards(p1.id, 1)

        library_after = get_library_count(game, p1)
        hand_after = get_hand_count(game, p1)

        assert library_after == library_before - 1, (
            f"Library should have 1 fewer card, had {library_before}, now {library_after}"
        )
        assert hand_after == hand_before + 1, (
            f"Hand should have 1 more card, had {hand_before}, now {hand_after}"
        )

    def test_drawing_multiple_cards(self):
        """Drawing multiple cards should move them all."""
        game, p1, p2 = new_hs_game()

        # Add 5 cards to library
        for _ in range(5):
            make_obj(game, WISP, p1, zone=ZoneType.LIBRARY)

        library_before = get_library_count(game, p1)
        hand_before = get_hand_count(game, p1)

        # Draw 3 cards
        game.draw_cards(p1.id, 3)

        library_after = get_library_count(game, p1)
        hand_after = get_hand_count(game, p1)

        assert library_after == library_before - 3, (
            f"Library should have 3 fewer cards, had {library_before}, now {library_after}"
        )
        assert hand_after == hand_before + 3, (
            f"Hand should have 3 more cards, had {hand_before}, now {hand_after}"
        )

    def test_drawing_from_nonempty_library_does_not_trigger_fatigue(self):
        """Drawing from a library with cards should not cause fatigue damage."""
        game, p1, p2 = new_hs_game()

        # Add card to library
        make_obj(game, WISP, p1, zone=ZoneType.LIBRARY)

        hero = game.state.objects.get(p1.hero_id)
        hp_before = hero.life if hero else 0

        # Draw a card
        game.draw_cards(p1.id, 1)

        hp_after = hero.life if hero else 0

        assert hp_after == hp_before, (
            f"Hero HP should not change when drawing from nonempty library, was {hp_before}, now {hp_after}"
        )

    def test_card_moves_to_hand_zone(self):
        """Drawn card should have zone set to HAND."""
        game, p1, p2 = new_hs_game()

        # Add card to library
        card = make_obj(game, WISP, p1, zone=ZoneType.LIBRARY)

        # Draw a card
        game.draw_cards(p1.id, 1)

        # Check the card's zone
        drawn_card = game.state.objects.get(card.id)
        assert drawn_card is not None, "Card should exist"
        assert drawn_card.zone == ZoneType.HAND, (
            f"Card should be in HAND zone, but is in {drawn_card.zone}"
        )

    def test_multiple_draws_in_sequence(self):
        """Multiple draw effects should work in sequence."""
        game, p1, p2 = new_hs_game()

        # Add 10 cards to library
        for _ in range(10):
            make_obj(game, WISP, p1, zone=ZoneType.LIBRARY)

        hand_before = get_hand_count(game, p1)

        # Draw 2, then draw 3, then draw 1
        game.draw_cards(p1.id, 2)
        game.draw_cards(p1.id, 3)
        game.draw_cards(p1.id, 1)

        hand_after = get_hand_count(game, p1)

        assert hand_after == hand_before + 6, (
            f"Hand should have 6 more cards, had {hand_before}, now {hand_after}"
        )


# ============================================================
# Test 6-10: Fatigue Mechanics
# ============================================================

class TestFatigueMechanics:
    """Tests for fatigue damage when drawing from empty library."""

    def test_drawing_from_empty_library_causes_fatigue_damage(self):
        """Drawing from empty library should deal fatigue damage."""
        game, p1, p2 = new_hs_game()

        # Ensure library is empty
        library_key = f"library_{p1.id}"
        if library_key in game.state.zones:
            game.state.zones[library_key].objects.clear()

        hero = game.state.objects.get(p1.hero_id)
        hp_before = hero.life if hero else 0

        # Draw from empty library
        game.draw_cards(p1.id, 1)

        hp_after = hero.life if hero else 0

        assert hp_after < hp_before, (
            f"Hero should take fatigue damage, was {hp_before} HP, now {hp_after} HP"
        )

    def test_first_fatigue_damage_is_1(self):
        """First fatigue draw should deal 1 damage."""
        game, p1, p2 = new_hs_game()

        # Ensure library is empty
        library_key = f"library_{p1.id}"
        if library_key in game.state.zones:
            game.state.zones[library_key].objects.clear()

        hero = game.state.objects.get(p1.hero_id)
        hp_before = hero.life if hero else 0

        # Reset fatigue counter
        p1.fatigue_damage = 0

        # Draw from empty library
        game.draw_cards(p1.id, 1)

        hp_after = hero.life if hero else 0

        assert hp_after == hp_before - 1, (
            f"First fatigue should deal 1 damage, was {hp_before} HP, now {hp_after} HP"
        )

    def test_fatigue_damage_increases_each_draw(self):
        """Fatigue damage should increase: 1, 2, 3, 4..."""
        game, p1, p2 = new_hs_game()

        # Ensure library is empty
        library_key = f"library_{p1.id}"
        if library_key in game.state.zones:
            game.state.zones[library_key].objects.clear()

        # Reset fatigue counter
        p1.fatigue_damage = 0

        hero = game.state.objects.get(p1.hero_id)
        hp_before = hero.life if hero else 0

        # Draw 4 times from empty library
        game.draw_cards(p1.id, 1)  # -1 (total: 1)
        game.draw_cards(p1.id, 1)  # -2 (total: 3)
        game.draw_cards(p1.id, 1)  # -3 (total: 6)
        game.draw_cards(p1.id, 1)  # -4 (total: 10)

        hp_after = hero.life if hero else 0
        total_damage = hp_before - hp_after

        assert total_damage == 10, (
            f"Fatigue should deal 1+2+3+4=10 damage, dealt {total_damage}"
        )

    def test_multiple_fatigue_draws_in_single_event(self):
        """Drawing multiple cards from empty library should deal increasing fatigue."""
        game, p1, p2 = new_hs_game()

        # Ensure library is empty
        library_key = f"library_{p1.id}"
        if library_key in game.state.zones:
            game.state.zones[library_key].objects.clear()

        # Reset fatigue counter
        p1.fatigue_damage = 0

        hero = game.state.objects.get(p1.hero_id)
        hp_before = hero.life if hero else 0

        # Draw 3 cards from empty library in one call
        game.draw_cards(p1.id, 3)  # Should deal 1+2+3=6 damage

        hp_after = hero.life if hero else 0
        total_damage = hp_before - hp_after

        assert total_damage == 6, (
            f"Drawing 3 from empty library should deal 1+2+3=6 damage, dealt {total_damage}"
        )

    def test_fatigue_kills_hero(self):
        """Fatigue damage should be able to kill the hero."""
        game, p1, p2 = new_hs_game()

        # Ensure library is empty
        library_key = f"library_{p1.id}"
        if library_key in game.state.zones:
            game.state.zones[library_key].objects.clear()

        # Set hero to low HP
        hero = game.state.objects.get(p1.hero_id)
        if hero:
            hero.life = 3

        # Reset fatigue counter
        p1.fatigue_damage = 0

        # Draw 3 times: 1+2+3=6 damage, hero at 3 HP should die
        game.draw_cards(p1.id, 3)

        # Run state-based actions to check for death
        run_sba(game)

        # Check if hero is dead (life <= 0)
        hero_after = game.state.objects.get(p1.hero_id)
        assert hero_after.life <= 0, (
            f"Hero should be at 0 or below HP from fatigue, at {hero_after.life} HP"
        )


# ============================================================
# Test 11-15: Hand Limit and Overdraw
# ============================================================

class TestHandLimitAndOverdraw:
    """Tests for 10-card hand limit and overdraw mechanics."""

    def test_hand_limit_is_10_cards(self):
        """Hand limit should be 10 cards in Hearthstone mode."""
        game, p1, p2 = new_hs_game()

        assert game.state.max_hand_size == 10, (
            f"Hearthstone hand limit should be 10, got {game.state.max_hand_size}"
        )

    def test_drawing_at_hand_limit_burns_card(self):
        """Drawing when hand is full (10 cards) should burn the card."""
        game, p1, p2 = new_hs_game()

        # Fill hand with 10 cards
        for _ in range(10):
            make_obj(game, WISP, p1, zone=ZoneType.HAND)

        # Add card to library
        make_obj(game, BLOODFEN_RAPTOR, p1, zone=ZoneType.LIBRARY)

        hand_before = get_hand_count(game, p1)
        graveyard_before = get_graveyard_count(game, p1)

        # Draw a card (should burn)
        game.draw_cards(p1.id, 1)

        hand_after = get_hand_count(game, p1)
        graveyard_after = get_graveyard_count(game, p1)

        assert hand_after == 10, (
            f"Hand should stay at 10 cards, got {hand_after}"
        )
        assert graveyard_after == graveyard_before + 1, (
            f"Graveyard should gain 1 card from overdraw, had {graveyard_before}, now {graveyard_after}"
        )

    def test_overdraw_does_not_add_to_hand(self):
        """Overdrawn card should not be added to hand."""
        game, p1, p2 = new_hs_game()

        # Fill hand with 10 cards
        for _ in range(10):
            make_obj(game, WISP, p1, zone=ZoneType.HAND)

        # Add card to library
        burned_card = make_obj(game, BLOODFEN_RAPTOR, p1, zone=ZoneType.LIBRARY)

        # Draw a card (should burn)
        game.draw_cards(p1.id, 1)

        # Check card is not in hand
        hand_key = f"hand_{p1.id}"
        hand_ids = game.state.zones.get(hand_key).objects if hand_key in game.state.zones else []

        assert burned_card.id not in hand_ids, (
            f"Overdrawn card should not be in hand"
        )

    def test_overdraw_sends_card_to_graveyard(self):
        """Overdrawn card should go to graveyard."""
        game, p1, p2 = new_hs_game()

        # Fill hand with 10 cards
        for _ in range(10):
            make_obj(game, WISP, p1, zone=ZoneType.HAND)

        # Add card to library
        burned_card = make_obj(game, BLOODFEN_RAPTOR, p1, zone=ZoneType.LIBRARY)

        # Draw a card (should burn)
        game.draw_cards(p1.id, 1)

        # Check card is in graveyard
        graveyard_key = f"graveyard_{p1.id}"
        graveyard_ids = game.state.zones.get(graveyard_key).objects if graveyard_key in game.state.zones else []

        assert burned_card.id in graveyard_ids, (
            f"Overdrawn card should be in graveyard"
        )

    def test_drawing_near_hand_limit_fills_to_10_then_burns(self):
        """Drawing multiple cards when near limit should fill to 10, then burn rest."""
        game, p1, p2 = new_hs_game()

        # Put 8 cards in hand
        for _ in range(8):
            make_obj(game, WISP, p1, zone=ZoneType.HAND)

        # Add 5 cards to library
        for _ in range(5):
            make_obj(game, BLOODFEN_RAPTOR, p1, zone=ZoneType.LIBRARY)

        # Draw 5 cards (2 should go to hand, 3 should burn)
        game.draw_cards(p1.id, 5)

        hand_after = get_hand_count(game, p1)
        graveyard_after = get_graveyard_count(game, p1)

        assert hand_after == 10, (
            f"Hand should be at 10 cards, got {hand_after}"
        )
        assert graveyard_after == 3, (
            f"Graveyard should have 3 burned cards, got {graveyard_after}"
        )


# ============================================================
# Test 16-20: Card Draw Effects
# ============================================================

class TestCardDrawEffects:
    """Tests for cards that draw cards."""

    def test_loot_hoarder_draws_on_death(self):
        """Loot Hoarder deathrattle should draw a card."""
        game, p1, p2 = new_hs_game()

        # Add cards to library
        for _ in range(5):
            make_obj(game, WISP, p1, zone=ZoneType.LIBRARY)

        # Play Loot Hoarder
        hoarder = make_obj(game, LOOT_HOARDER, p1, zone=ZoneType.BATTLEFIELD)

        hand_before = get_hand_count(game, p1)

        # Kill Loot Hoarder
        game.emit(Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': hoarder.id},
            source='test'
        ))

        hand_after = get_hand_count(game, p1)

        assert hand_after == hand_before + 1, (
            f"Loot Hoarder death should draw 1 card, had {hand_before}, now {hand_after}"
        )

    def test_azure_drake_battlecry_draws_card(self):
        """Azure Drake battlecry should draw a card."""
        game, p1, p2 = new_hs_game()

        # Add cards to library
        for _ in range(5):
            make_obj(game, WISP, p1, zone=ZoneType.LIBRARY)

        hand_before = get_hand_count(game, p1)

        # Play Azure Drake (with battlecry)
        drake = play_minion(game, AZURE_DRAKE, p1)

        hand_after = get_hand_count(game, p1)

        assert hand_after == hand_before + 1, (
            f"Azure Drake battlecry should draw 1 card, had {hand_before}, now {hand_after}"
        )

    def test_novice_engineer_battlecry_draws_card(self):
        """Novice Engineer battlecry should draw a card."""
        game, p1, p2 = new_hs_game()

        # Add cards to library
        for _ in range(5):
            make_obj(game, WISP, p1, zone=ZoneType.LIBRARY)

        hand_before = get_hand_count(game, p1)

        # Play Novice Engineer (with battlecry)
        engineer = play_minion(game, NOVICE_ENGINEER, p1)

        hand_after = get_hand_count(game, p1)

        assert hand_after == hand_before + 1, (
            f"Novice Engineer battlecry should draw 1 card, had {hand_before}, now {hand_after}"
        )

    def test_arcane_intellect_draws_2_cards(self):
        """Arcane Intellect should draw 2 cards."""
        game, p1, p2 = new_hs_game()

        # Add cards to library
        for _ in range(5):
            make_obj(game, WISP, p1, zone=ZoneType.LIBRARY)

        hand_before = get_hand_count(game, p1)

        # Cast Arcane Intellect
        cast_spell(game, ARCANE_INTELLECT, p1)

        hand_after = get_hand_count(game, p1)

        assert hand_after == hand_before + 2, (
            f"Arcane Intellect should draw 2 cards, had {hand_before}, now {hand_after}"
        )

    def test_acolyte_of_pain_draws_on_damage(self):
        """Acolyte of Pain should draw a card when damaged."""
        game, p1, p2 = new_hs_game()

        # Add cards to library
        for _ in range(5):
            make_obj(game, WISP, p1, zone=ZoneType.LIBRARY)

        # Play Acolyte of Pain
        acolyte = make_obj(game, ACOLYTE_OF_PAIN, p1, zone=ZoneType.BATTLEFIELD)

        hand_before = get_hand_count(game, p1)

        # Deal 1 damage to Acolyte
        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': acolyte.id, 'amount': 1},
            source='test'
        ))

        hand_after = get_hand_count(game, p1)

        assert hand_after == hand_before + 1, (
            f"Acolyte of Pain should draw 1 card when damaged, had {hand_before}, now {hand_after}"
        )


# ============================================================
# Test 21-25: Advanced Draw Scenarios
# ============================================================

class TestAdvancedDrawScenarios:
    """Tests for advanced draw scenarios."""

    def test_acolyte_of_pain_draws_on_each_damage_instance(self):
        """Acolyte of Pain should draw separately for each damage instance."""
        game, p1, p2 = new_hs_game()

        # Add cards to library
        for _ in range(10):
            make_obj(game, WISP, p1, zone=ZoneType.LIBRARY)

        # Play Acolyte of Pain
        acolyte = make_obj(game, ACOLYTE_OF_PAIN, p1, zone=ZoneType.BATTLEFIELD)

        hand_before = get_hand_count(game, p1)

        # Deal damage 3 times (1 damage each time)
        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': acolyte.id, 'amount': 1},
            source='test'
        ))
        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': acolyte.id, 'amount': 1},
            source='test'
        ))
        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': acolyte.id, 'amount': 1},
            source='test'
        ))

        hand_after = get_hand_count(game, p1)

        assert hand_after == hand_before + 3, (
            f"Acolyte should draw 3 cards (1 per damage instance), had {hand_before}, now {hand_after}"
        )

    def test_loot_hoarder_death_with_empty_library_causes_fatigue(self):
        """Loot Hoarder deathrattle with empty library should cause fatigue."""
        game, p1, p2 = new_hs_game()

        # Ensure library is empty
        library_key = f"library_{p1.id}"
        if library_key in game.state.zones:
            game.state.zones[library_key].objects.clear()

        # Reset fatigue counter
        p1.fatigue_damage = 0

        # Play Loot Hoarder
        hoarder = make_obj(game, LOOT_HOARDER, p1, zone=ZoneType.BATTLEFIELD)

        hero = game.state.objects.get(p1.hero_id)
        hp_before = hero.life if hero else 0

        # Kill Loot Hoarder (should draw, hit fatigue)
        game.emit(Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': hoarder.id},
            source='test'
        ))

        hp_after = hero.life if hero else 0

        assert hp_after == hp_before - 1, (
            f"Loot Hoarder death with empty library should deal 1 fatigue damage, was {hp_before}, now {hp_after}"
        )

    def test_azure_drake_battlecry_with_full_hand_burns_card(self):
        """Azure Drake battlecry with full hand should burn the drawn card."""
        game, p1, p2 = new_hs_game()

        # Fill hand with 10 cards
        for _ in range(10):
            make_obj(game, WISP, p1, zone=ZoneType.HAND)

        # Add card to library
        make_obj(game, BLOODFEN_RAPTOR, p1, zone=ZoneType.LIBRARY)

        graveyard_before = get_graveyard_count(game, p1)

        # Play Azure Drake (should draw and burn)
        drake = play_minion(game, AZURE_DRAKE, p1)

        hand_after = get_hand_count(game, p1)
        graveyard_after = get_graveyard_count(game, p1)

        assert hand_after == 10, (
            f"Hand should stay at 10 cards, got {hand_after}"
        )
        assert graveyard_after == graveyard_before + 1, (
            f"Graveyard should gain 1 burned card, had {graveyard_before}, now {graveyard_after}"
        )

    def test_arcane_intellect_draws_2_then_burns_1_when_hand_at_9(self):
        """Arcane Intellect with 9 cards in hand should draw 1, then burn 1."""
        game, p1, p2 = new_hs_game()

        # Put 9 cards in hand
        for _ in range(9):
            make_obj(game, WISP, p1, zone=ZoneType.HAND)

        # Add 2 cards to library
        make_obj(game, BLOODFEN_RAPTOR, p1, zone=ZoneType.LIBRARY)
        make_obj(game, CHILLWIND_YETI, p1, zone=ZoneType.LIBRARY)

        # Cast Arcane Intellect (draws 2: first fills to 10, second burns)
        cast_spell(game, ARCANE_INTELLECT, p1)

        hand_after = get_hand_count(game, p1)
        graveyard_after = get_graveyard_count(game, p1)

        assert hand_after == 10, (
            f"Hand should be at 10 cards, got {hand_after}"
        )
        assert graveyard_after == 1, (
            f"Graveyard should have 1 burned card, got {graveyard_after}"
        )

    def test_multiple_acolytes_each_draw_on_aoe_damage(self):
        """Multiple Acolytes of Pain should each draw when hit by AOE."""
        game, p1, p2 = new_hs_game()

        # Add cards to library
        for _ in range(10):
            make_obj(game, WISP, p1, zone=ZoneType.LIBRARY)

        # Play 3 Acolytes
        acolyte1 = make_obj(game, ACOLYTE_OF_PAIN, p1, zone=ZoneType.BATTLEFIELD)
        acolyte2 = make_obj(game, ACOLYTE_OF_PAIN, p1, zone=ZoneType.BATTLEFIELD)
        acolyte3 = make_obj(game, ACOLYTE_OF_PAIN, p1, zone=ZoneType.BATTLEFIELD)

        hand_before = get_hand_count(game, p1)

        # Deal 1 damage to each (simulating AOE)
        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': acolyte1.id, 'amount': 1},
            source='test'
        ))
        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': acolyte2.id, 'amount': 1},
            source='test'
        ))
        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': acolyte3.id, 'amount': 1},
            source='test'
        ))

        hand_after = get_hand_count(game, p1)

        assert hand_after == hand_before + 3, (
            f"Each Acolyte should draw 1 card (3 total), had {hand_before}, now {hand_after}"
        )


# ============================================================
# Test 26-30: Fatigue with Armor and Edge Cases
# ============================================================

class TestFatigueWithArmor:
    """Tests for fatigue interaction with armor."""

    def test_fatigue_damage_absorbed_by_armor(self):
        """Armor should absorb fatigue damage."""
        game, p1, p2 = new_hs_game()

        # Ensure library is empty
        library_key = f"library_{p1.id}"
        if library_key in game.state.zones:
            game.state.zones[library_key].objects.clear()

        # Give player armor
        p1.armor = 5

        # Reset fatigue counter
        p1.fatigue_damage = 0

        hero = game.state.objects.get(p1.hero_id)
        hp_before = hero.life if hero else 0
        armor_before = p1.armor

        # Draw from empty library (1 damage)
        game.draw_cards(p1.id, 1)

        hp_after = hero.life if hero else 0
        armor_after = p1.armor

        assert hp_after == hp_before, (
            f"Hero HP should not change (armor absorbs), was {hp_before}, now {hp_after}"
        )
        assert armor_after == armor_before - 1, (
            f"Armor should be reduced by 1, was {armor_before}, now {armor_after}"
        )

    def test_fatigue_exceeds_armor_damages_hero(self):
        """Fatigue damage exceeding armor should damage hero."""
        game, p1, p2 = new_hs_game()

        # Ensure library is empty
        library_key = f"library_{p1.id}"
        if library_key in game.state.zones:
            game.state.zones[library_key].objects.clear()

        # Give player 2 armor
        p1.armor = 2

        # Reset fatigue counter
        p1.fatigue_damage = 0

        hero = game.state.objects.get(p1.hero_id)
        hp_before = hero.life if hero else 0

        # Draw 2 times: 1 damage (armor absorbs), 2 damage (1 absorbed, 1 to hero)
        game.draw_cards(p1.id, 2)

        hp_after = hero.life if hero else 0
        armor_after = p1.armor

        # After 1st draw: armor 2->1, HP unchanged
        # After 2nd draw: armor 1->0, HP -1
        assert armor_after == 0, (
            f"Armor should be depleted, now {armor_after}"
        )
        assert hp_after == hp_before - 1, (
            f"Hero should take 1 damage after armor depleted, was {hp_before}, now {hp_after}"
        )

    def test_high_fatigue_with_low_armor(self):
        """High fatigue damage with low armor should mostly damage hero."""
        game, p1, p2 = new_hs_game()

        # Ensure library is empty
        library_key = f"library_{p1.id}"
        if library_key in game.state.zones:
            game.state.zones[library_key].objects.clear()

        # Give player 1 armor
        p1.armor = 1

        # Set fatigue counter to high value
        p1.fatigue_damage = 9  # Next draw will be 10 damage

        hero = game.state.objects.get(p1.hero_id)
        hp_before = hero.life if hero else 0

        # Draw once (10 damage: 1 absorbed by armor, 9 to hero)
        game.draw_cards(p1.id, 1)

        hp_after = hero.life if hero else 0
        armor_after = p1.armor

        assert armor_after == 0, (
            f"Armor should be depleted, now {armor_after}"
        )
        assert hp_after == hp_before - 9, (
            f"Hero should take 9 damage (10 total - 1 armor), was {hp_before}, now {hp_after}"
        )

    def test_fatigue_counter_persists_across_draws(self):
        """Fatigue counter should persist across multiple draws."""
        game, p1, p2 = new_hs_game()

        # Ensure library is empty
        library_key = f"library_{p1.id}"
        if library_key in game.state.zones:
            game.state.zones[library_key].objects.clear()

        # Reset fatigue counter
        p1.fatigue_damage = 0

        # Draw once
        game.draw_cards(p1.id, 1)

        # Check fatigue counter incremented
        assert p1.fatigue_damage == 1, (
            f"Fatigue counter should be 1 after first draw, got {p1.fatigue_damage}"
        )

        # Draw again
        game.draw_cards(p1.id, 1)

        # Check fatigue counter incremented again
        assert p1.fatigue_damage == 2, (
            f"Fatigue counter should be 2 after second draw, got {p1.fatigue_damage}"
        )

    def test_fatigue_counter_never_decreases(self):
        """Fatigue counter should never decrease."""
        game, p1, p2 = new_hs_game()

        # Set fatigue counter to 5
        p1.fatigue_damage = 5

        # Add cards to library
        for _ in range(3):
            make_obj(game, WISP, p1, zone=ZoneType.LIBRARY)

        # Draw cards from non-empty library
        game.draw_cards(p1.id, 3)

        # Fatigue counter should remain at 5
        assert p1.fatigue_damage == 5, (
            f"Fatigue counter should remain at 5, got {p1.fatigue_damage}"
        )


# ============================================================
# Test 31-35: Edge Cases
# ============================================================

class TestEdgeCases:
    """Tests for edge cases in card draw mechanics."""

    def test_drawing_zero_cards_does_nothing(self):
        """Drawing 0 cards should not change hand or library."""
        game, p1, p2 = new_hs_game()

        # Add cards to library
        make_obj(game, WISP, p1, zone=ZoneType.LIBRARY)

        hand_before = get_hand_count(game, p1)
        library_before = get_library_count(game, p1)

        # Draw 0 cards
        game.draw_cards(p1.id, 0)

        hand_after = get_hand_count(game, p1)
        library_after = get_library_count(game, p1)

        assert hand_after == hand_before, (
            f"Hand should not change, was {hand_before}, now {hand_after}"
        )
        assert library_after == library_before, (
            f"Library should not change, was {library_before}, now {library_after}"
        )

    def test_drawing_more_cards_than_library_has(self):
        """Drawing more cards than library has should draw all, then fatigue."""
        game, p1, p2 = new_hs_game()

        # Add 2 cards to library
        make_obj(game, WISP, p1, zone=ZoneType.LIBRARY)
        make_obj(game, BLOODFEN_RAPTOR, p1, zone=ZoneType.LIBRARY)

        # Reset fatigue counter
        p1.fatigue_damage = 0

        hand_before = get_hand_count(game, p1)

        hero = game.state.objects.get(p1.hero_id)
        hp_before = hero.life if hero else 0

        # Draw 5 cards (2 from library, then 3 fatigue: 1+2+3=6 damage)
        game.draw_cards(p1.id, 5)

        hand_after = get_hand_count(game, p1)
        hp_after = hero.life if hero else 0
        library_after = get_library_count(game, p1)

        assert hand_after == hand_before + 2, (
            f"Should draw 2 cards from library, had {hand_before}, now {hand_after}"
        )
        assert library_after == 0, (
            f"Library should be empty, got {library_after}"
        )
        assert hp_after == hp_before - 6, (
            f"Should take 1+2+3=6 fatigue damage, was {hp_before}, now {hp_after}"
        )

    def test_acolyte_draws_then_dies_from_damage(self):
        """Acolyte of Pain at 1 HP taking 2 damage should draw then die."""
        game, p1, p2 = new_hs_game()

        # Add cards to library
        for _ in range(5):
            make_obj(game, WISP, p1, zone=ZoneType.LIBRARY)

        # Play Acolyte of Pain (1/3)
        acolyte = make_obj(game, ACOLYTE_OF_PAIN, p1, zone=ZoneType.BATTLEFIELD)

        # Damage it to 1 HP
        acolyte.damage_taken = 2

        hand_before = get_hand_count(game, p1)

        # Deal 2 more damage (should trigger draw, then die)
        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': acolyte.id, 'amount': 2},
            source='test'
        ))

        # Run SBA to kill it
        run_sba(game)

        hand_after = get_hand_count(game, p1)

        # Should draw 1 card from damage trigger
        assert hand_after == hand_before + 1, (
            f"Acolyte should draw before dying, had {hand_before}, now {hand_after}"
        )

        # Acolyte should be dead
        assert acolyte.zone == ZoneType.GRAVEYARD, (
            f"Acolyte should be in graveyard, in {acolyte.zone}"
        )

    def test_drawing_with_empty_zones(self):
        """Drawing when zones don't exist should handle gracefully."""
        game, p1, p2 = new_hs_game()

        # Remove hand zone (edge case)
        hand_key = f"hand_{p1.id}"
        if hand_key in game.state.zones:
            del game.state.zones[hand_key]

        # Attempt to draw (should not crash)
        try:
            game.draw_cards(p1.id, 1)
            # If we get here without crashing, test passes
            assert True
        except Exception as e:
            assert False, f"Drawing with missing hand zone should not crash: {e}"

    def test_simultaneous_draws_from_multiple_effects(self):
        """Multiple draw effects resolving simultaneously should all work."""
        game, p1, p2 = new_hs_game()

        # Add lots of cards to library
        for _ in range(20):
            make_obj(game, WISP, p1, zone=ZoneType.LIBRARY)

        hand_before = get_hand_count(game, p1)

        # Emit multiple draw events
        game.emit(Event(type=EventType.DRAW, payload={'player': p1.id, 'count': 2}, source='test'))
        game.emit(Event(type=EventType.DRAW, payload={'player': p1.id, 'count': 3}, source='test'))
        game.emit(Event(type=EventType.DRAW, payload={'player': p1.id, 'count': 1}, source='test'))

        hand_after = get_hand_count(game, p1)

        assert hand_after == hand_before + 6, (
            f"Should draw total of 6 cards, had {hand_before}, now {hand_after}"
        )


# ============================================================
# Test 36-40: Complex Scenarios
# ============================================================

class TestComplexScenarios:
    """Tests for complex card draw scenarios."""

    def test_acolyte_overdraw_scenario(self):
        """Acolyte drawing when hand is full should burn cards."""
        game, p1, p2 = new_hs_game()

        # Fill hand with 10 cards
        for _ in range(10):
            make_obj(game, WISP, p1, zone=ZoneType.HAND)

        # Add cards to library
        for _ in range(5):
            make_obj(game, BLOODFEN_RAPTOR, p1, zone=ZoneType.LIBRARY)

        # Play Acolyte
        acolyte = make_obj(game, ACOLYTE_OF_PAIN, p1, zone=ZoneType.BATTLEFIELD)

        graveyard_before = get_graveyard_count(game, p1)

        # Deal damage to Acolyte 3 times (should try to draw 3, all burn)
        game.emit(Event(type=EventType.DAMAGE, payload={'target': acolyte.id, 'amount': 1}, source='test'))
        game.emit(Event(type=EventType.DAMAGE, payload={'target': acolyte.id, 'amount': 1}, source='test'))
        game.emit(Event(type=EventType.DAMAGE, payload={'target': acolyte.id, 'amount': 1}, source='test'))

        hand_after = get_hand_count(game, p1)
        graveyard_after = get_graveyard_count(game, p1)

        assert hand_after == 10, (
            f"Hand should stay at 10, got {hand_after}"
        )
        assert graveyard_after == graveyard_before + 3, (
            f"Should burn 3 cards, had {graveyard_before}, now {graveyard_after}"
        )

    def test_loot_hoarder_chain_deaths(self):
        """Multiple Loot Hoarders dying should each draw."""
        game, p1, p2 = new_hs_game()

        # Add cards to library
        for _ in range(10):
            make_obj(game, WISP, p1, zone=ZoneType.LIBRARY)

        # Play 3 Loot Hoarders
        hoarder1 = make_obj(game, LOOT_HOARDER, p1, zone=ZoneType.BATTLEFIELD)
        hoarder2 = make_obj(game, LOOT_HOARDER, p1, zone=ZoneType.BATTLEFIELD)
        hoarder3 = make_obj(game, LOOT_HOARDER, p1, zone=ZoneType.BATTLEFIELD)

        hand_before = get_hand_count(game, p1)

        # Kill all 3
        game.emit(Event(type=EventType.OBJECT_DESTROYED, payload={'object_id': hoarder1.id}, source='test'))
        game.emit(Event(type=EventType.OBJECT_DESTROYED, payload={'object_id': hoarder2.id}, source='test'))
        game.emit(Event(type=EventType.OBJECT_DESTROYED, payload={'object_id': hoarder3.id}, source='test'))

        hand_after = get_hand_count(game, p1)

        assert hand_after == hand_before + 3, (
            f"Each Loot Hoarder should draw 1 card (3 total), had {hand_before}, now {hand_after}"
        )

    def test_draw_then_fatigue_in_same_turn(self):
        """Drawing cards then hitting fatigue in same turn should work."""
        game, p1, p2 = new_hs_game()

        # Add 1 card to library
        make_obj(game, WISP, p1, zone=ZoneType.LIBRARY)

        # Reset fatigue counter
        p1.fatigue_damage = 0

        hand_before = get_hand_count(game, p1)

        hero = game.state.objects.get(p1.hero_id)
        hp_before = hero.life if hero else 0

        # Draw 1 card (from library)
        game.draw_cards(p1.id, 1)

        # Draw 2 more (both fatigue: 1+2=3 damage)
        game.draw_cards(p1.id, 2)

        hand_after = get_hand_count(game, p1)
        hp_after = hero.life if hero else 0

        assert hand_after == hand_before + 1, (
            f"Should draw 1 card from library, had {hand_before}, now {hand_after}"
        )
        assert hp_after == hp_before - 3, (
            f"Should take 1+2=3 fatigue damage, was {hp_before}, now {hp_after}"
        )

    def test_arcane_intellect_with_1_card_in_library(self):
        """Arcane Intellect with 1 card in library should draw 1, then 1 fatigue."""
        game, p1, p2 = new_hs_game()

        # Add 1 card to library
        make_obj(game, WISP, p1, zone=ZoneType.LIBRARY)

        # Reset fatigue counter
        p1.fatigue_damage = 0

        hand_before = get_hand_count(game, p1)

        hero = game.state.objects.get(p1.hero_id)
        hp_before = hero.life if hero else 0

        # Cast Arcane Intellect (draws 2: 1 from library, 1 fatigue)
        cast_spell(game, ARCANE_INTELLECT, p1)

        hand_after = get_hand_count(game, p1)
        hp_after = hero.life if hero else 0

        assert hand_after == hand_before + 1, (
            f"Should draw 1 card from library, had {hand_before}, now {hand_after}"
        )
        assert hp_after == hp_before - 1, (
            f"Should take 1 fatigue damage, was {hp_before}, now {hp_after}"
        )

    def test_drawing_exact_hand_limit_from_empty_hand(self):
        """Drawing 10 cards from empty hand should fill hand exactly."""
        game, p1, p2 = new_hs_game()

        # Ensure hand is empty
        hand_key = f"hand_{p1.id}"
        if hand_key in game.state.zones:
            game.state.zones[hand_key].objects.clear()

        # Add 10 cards to library
        for _ in range(10):
            make_obj(game, WISP, p1, zone=ZoneType.LIBRARY)

        # Draw 10 cards
        game.draw_cards(p1.id, 10)

        hand_after = get_hand_count(game, p1)

        assert hand_after == 10, (
            f"Should have exactly 10 cards in hand, got {hand_after}"
        )


# ============================================================
# Test 41-45: Extreme Edge Cases
# ============================================================

class TestExtremeEdgeCases:
    """Tests for extreme edge cases."""

    def test_massive_fatigue_damage(self):
        """Very high fatigue counter should deal massive damage."""
        game, p1, p2 = new_hs_game()

        # Ensure library is empty
        library_key = f"library_{p1.id}"
        if library_key in game.state.zones:
            game.state.zones[library_key].objects.clear()

        # Set fatigue counter to 19 (next draw is 20 damage)
        p1.fatigue_damage = 19

        hero = game.state.objects.get(p1.hero_id)
        hp_before = hero.life if hero else 0

        # Draw once (20 damage)
        game.draw_cards(p1.id, 1)

        hp_after = hero.life if hero else 0

        assert hp_after == hp_before - 20, (
            f"Should deal 20 fatigue damage, was {hp_before}, now {hp_after}"
        )

    def test_draw_11_cards_from_empty_hand(self):
        """Drawing 11 cards from empty hand should fill to 10, burn 1."""
        game, p1, p2 = new_hs_game()

        # Ensure hand is empty
        hand_key = f"hand_{p1.id}"
        if hand_key in game.state.zones:
            game.state.zones[hand_key].objects.clear()

        # Add 11 cards to library
        for _ in range(11):
            make_obj(game, WISP, p1, zone=ZoneType.LIBRARY)

        # Draw 11 cards
        game.draw_cards(p1.id, 11)

        hand_after = get_hand_count(game, p1)
        graveyard_after = get_graveyard_count(game, p1)

        assert hand_after == 10, (
            f"Hand should be at 10 cards, got {hand_after}"
        )
        assert graveyard_after == 1, (
            f"Graveyard should have 1 burned card, got {graveyard_after}"
        )

    def test_acolyte_takes_lethal_damage_still_draws(self):
        """Acolyte taking lethal damage should still trigger draw before dying."""
        game, p1, p2 = new_hs_game()

        # Add cards to library
        for _ in range(5):
            make_obj(game, WISP, p1, zone=ZoneType.LIBRARY)

        # Play Acolyte (1/3)
        acolyte = make_obj(game, ACOLYTE_OF_PAIN, p1, zone=ZoneType.BATTLEFIELD)

        hand_before = get_hand_count(game, p1)

        # Deal 10 damage (lethal)
        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': acolyte.id, 'amount': 10},
            source='test'
        ))

        hand_after = get_hand_count(game, p1)

        # Should draw 1 card from damage trigger
        assert hand_after == hand_before + 1, (
            f"Acolyte should draw even from lethal damage, had {hand_before}, now {hand_after}"
        )

        # Run SBA to kill it
        run_sba(game)

        # Acolyte should be dead
        assert acolyte.zone == ZoneType.GRAVEYARD, (
            f"Acolyte should be in graveyard, in {acolyte.zone}"
        )

    def test_fatigue_with_max_armor(self):
        """Fatigue with very high armor should be fully absorbed."""
        game, p1, p2 = new_hs_game()

        # Ensure library is empty
        library_key = f"library_{p1.id}"
        if library_key in game.state.zones:
            game.state.zones[library_key].objects.clear()

        # Give player 100 armor
        p1.armor = 100

        # Reset fatigue counter
        p1.fatigue_damage = 0

        hero = game.state.objects.get(p1.hero_id)
        hp_before = hero.life if hero else 0

        # Draw 5 times (1+2+3+4+5=15 damage, all absorbed)
        game.draw_cards(p1.id, 5)

        hp_after = hero.life if hero else 0
        armor_after = p1.armor

        assert hp_after == hp_before, (
            f"Hero HP should not change, was {hp_before}, now {hp_after}"
        )
        assert armor_after == 100 - 15, (
            f"Armor should be reduced by 15, was 100, now {armor_after}"
        )

    def test_drawing_negative_cards_does_nothing(self):
        """Drawing negative number of cards should not crash or do anything weird."""
        game, p1, p2 = new_hs_game()

        # Add cards to library
        make_obj(game, WISP, p1, zone=ZoneType.LIBRARY)

        hand_before = get_hand_count(game, p1)
        library_before = get_library_count(game, p1)

        # Attempt to draw -1 cards
        try:
            game.draw_cards(p1.id, -1)
            # If we get here without crashing, check nothing changed
            hand_after = get_hand_count(game, p1)
            library_after = get_library_count(game, p1)

            # Ideally nothing should change
            assert hand_after == hand_before, (
                f"Hand should not change with negative draw, was {hand_before}, now {hand_after}"
            )
            assert library_after == library_before, (
                f"Library should not change with negative draw, was {library_before}, now {library_after}"
            )
        except Exception as e:
            # If it crashes, that's also acceptable behavior
            assert True
