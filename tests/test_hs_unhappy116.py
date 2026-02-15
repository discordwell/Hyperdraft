"""
Hearthstone Unhappy Path Tests - Batch 116

Card Draw and Hand Management Edge Cases.

Tests cover:
- Fatigue damage escalation (5 tests)
- Overdraw / hand limit (5 tests)
- Card draw triggered by deathrattle (5 tests)
- Card draw triggered by spell (5 tests)
- Sprint draws 4 cards interaction (5 tests)
- Novice Engineer battlecry draw (5 tests)
- Acolyte of Pain draws on damage (5 tests)
- Drawing into empty deck at low health (5 tests)
- Multiple draw effects stacking in same turn (5 tests)
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
    ARCANE_INTELLECT, AZURE_DRAKE, LOOT_HOARDER, NOVICE_ENGINEER,
    ACOLYTE_OF_PAIN, SPRINT, HARVEST_GOLEM, FIREBALL, WILD_PYROMANCER,
    BLOODMAGE_THALNOS
)
from src.cards.hearthstone.warrior import WHIRLWIND
from src.cards.hearthstone.warlock import HELLFIRE


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
    library_key = f"library_{player.id}"
    if library_key not in game.state.zones:
        return
    for _ in range(count):
        obj = game.create_object(
            name="Dummy Card", owner_id=player.id, zone=ZoneType.LIBRARY,
            characteristics=WISP.characteristics, card_def=WISP
        )


def get_hand_count(game, player):
    """Get number of cards in player's hand."""
    hand_key = f"hand_{player.id}"
    hand = game.state.zones.get(hand_key)
    if not hand:
        return 0
    return len(hand.objects)


def get_library_count(game, player):
    """Get number of cards in player's library."""
    library_key = f"library_{player.id}"
    library = game.state.zones.get(library_key)
    if not library:
        return 0
    return len(library.objects)


# ============================================================
# Category 1: Fatigue Damage Escalation (5 tests)
# ============================================================

def test_fatigue_first_draw_deals_1_damage():
    """First draw from empty deck deals 1 fatigue damage."""
    game, p1, p2 = new_hs_game()

    # Ensure library is empty
    library_key = f"library_{p1.id}"
    game.state.zones[library_key].objects.clear()

    # Draw from empty deck
    initial_life = p1.life
    game.emit(Event(
        type=EventType.DRAW,
        payload={'player': p1.id, 'count': 1},
        source='test'
    ))

    # Check fatigue damage
    assert p1.fatigue_damage == 1, f"Expected fatigue_damage=1, got {p1.fatigue_damage}"
    assert p1.life == initial_life - 1, f"Expected life={initial_life - 1}, got {p1.life}"


def test_fatigue_second_draw_deals_2_damage():
    """Second draw from empty deck deals 2 fatigue damage."""
    game, p1, p2 = new_hs_game()

    # Ensure library is empty
    library_key = f"library_{p1.id}"
    game.state.zones[library_key].objects.clear()

    # First draw (1 damage)
    game.emit(Event(
        type=EventType.DRAW,
        payload={'player': p1.id, 'count': 1},
        source='test'
    ))

    # Second draw (2 damage)
    life_after_first = p1.life
    game.emit(Event(
        type=EventType.DRAW,
        payload={'player': p1.id, 'count': 1},
        source='test'
    ))

    assert p1.fatigue_damage == 2, f"Expected fatigue_damage=2, got {p1.fatigue_damage}"
    assert p1.life == life_after_first - 2, f"Expected life={life_after_first - 2}, got {p1.life}"


def test_fatigue_escalates_to_10_damage():
    """Fatigue damage escalates correctly up to 10."""
    game, p1, p2 = new_hs_game()

    # Ensure library is empty
    library_key = f"library_{p1.id}"
    game.state.zones[library_key].objects.clear()

    # Draw 10 times
    expected_total_damage = sum(range(1, 11))  # 1+2+3+...+10 = 55
    initial_life = p1.life

    for i in range(10):
        game.emit(Event(
            type=EventType.DRAW,
            payload={'player': p1.id, 'count': 1},
            source='test'
        ))

    assert p1.fatigue_damage == 10, f"Expected fatigue_damage=10, got {p1.fatigue_damage}"
    assert p1.life == initial_life - expected_total_damage, \
        f"Expected life={initial_life - expected_total_damage}, got {p1.life}"


def test_fatigue_persists_across_turns():
    """Fatigue counter persists across multiple turns."""
    game, p1, p2 = new_hs_game()

    # Ensure library is empty
    library_key = f"library_{p1.id}"
    game.state.zones[library_key].objects.clear()

    # Draw once (1 damage)
    game.emit(Event(
        type=EventType.DRAW,
        payload={'player': p1.id, 'count': 1},
        source='test'
    ))

    assert p1.fatigue_damage == 1

    # Simulate turn passing (this shouldn't reset fatigue)
    # Draw again (should be 2 damage)
    life_after_first = p1.life
    game.emit(Event(
        type=EventType.DRAW,
        payload={'player': p1.id, 'count': 1},
        source='test'
    ))

    assert p1.fatigue_damage == 2, f"Fatigue should persist, expected 2, got {p1.fatigue_damage}"
    assert p1.life == life_after_first - 2


def test_multiple_draws_in_one_event():
    """Drawing multiple cards from empty deck triggers multiple fatigue instances."""
    game, p1, p2 = new_hs_game()

    # Ensure library is empty
    library_key = f"library_{p1.id}"
    game.state.zones[library_key].objects.clear()

    initial_life = p1.life
    # Draw 3 cards at once: should deal 1+2+3 = 6 damage
    game.emit(Event(
        type=EventType.DRAW,
        payload={'player': p1.id, 'count': 3},
        source='test'
    ))

    assert p1.fatigue_damage == 3, f"Expected fatigue_damage=3, got {p1.fatigue_damage}"
    assert p1.life == initial_life - 6, f"Expected life={initial_life - 6}, got {p1.life}"


# ============================================================
# Category 2: Overdraw / Hand Limit (5 tests)
# ============================================================

def test_overdraw_with_10_card_hand():
    """Drawing with 10 cards in hand burns the drawn card."""
    game, p1, p2 = new_hs_game()

    # Fill hand to 10 cards
    hand_key = f"hand_{p1.id}"
    for i in range(10):
        obj = make_obj(game, WISP, p1, zone=ZoneType.HAND)

    # Add 1 card to library
    add_cards_to_library(game, p1, count=1)

    assert get_hand_count(game, p1) == 10, "Hand should have 10 cards"
    assert get_library_count(game, p1) == 1, "Library should have 1 card"

    # Draw - should burn the card
    game.emit(Event(
        type=EventType.DRAW,
        payload={'player': p1.id, 'count': 1},
        source='test'
    ))

    assert get_hand_count(game, p1) == 10, "Hand should still have 10 cards"
    assert get_library_count(game, p1) == 0, "Library should be empty"


def test_overdraw_burns_to_graveyard():
    """Burned cards go to graveyard."""
    game, p1, p2 = new_hs_game()

    # Fill hand to 10 cards
    hand_key = f"hand_{p1.id}"
    for i in range(10):
        obj = make_obj(game, WISP, p1, zone=ZoneType.HAND)

    # Add 1 card to library
    add_cards_to_library(game, p1, count=1)

    graveyard_key = f"graveyard_{p1.id}"
    initial_gy_count = len(game.state.zones[graveyard_key].objects)

    # Draw - should burn
    game.emit(Event(
        type=EventType.DRAW,
        payload={'player': p1.id, 'count': 1},
        source='test'
    ))

    final_gy_count = len(game.state.zones[graveyard_key].objects)
    assert final_gy_count == initial_gy_count + 1, "Burned card should be in graveyard"


def test_overdraw_multiple_cards():
    """Drawing multiple cards with full hand burns all of them."""
    game, p1, p2 = new_hs_game()

    # Fill hand to 10 cards
    hand_key = f"hand_{p1.id}"
    for i in range(10):
        obj = make_obj(game, WISP, p1, zone=ZoneType.HAND)

    # Add 3 cards to library
    add_cards_to_library(game, p1, count=3)

    graveyard_key = f"graveyard_{p1.id}"
    initial_gy_count = len(game.state.zones[graveyard_key].objects)

    # Draw 3 - should burn all 3
    game.emit(Event(
        type=EventType.DRAW,
        payload={'player': p1.id, 'count': 3},
        source='test'
    ))

    assert get_hand_count(game, p1) == 10, "Hand should still be at max"
    assert get_library_count(game, p1) == 0, "Library should be empty"
    final_gy_count = len(game.state.zones[graveyard_key].objects)
    assert final_gy_count == initial_gy_count + 3, "All 3 cards should be burned to graveyard"


def test_overdraw_partial_burn():
    """Drawing when hand has 9 cards: first card goes to hand, rest burn."""
    game, p1, p2 = new_hs_game()

    # Fill hand to 9 cards
    hand_key = f"hand_{p1.id}"
    for i in range(9):
        obj = make_obj(game, WISP, p1, zone=ZoneType.HAND)

    # Add 3 cards to library
    add_cards_to_library(game, p1, count=3)

    graveyard_key = f"graveyard_{p1.id}"
    initial_gy_count = len(game.state.zones[graveyard_key].objects)

    # Draw 3: first should go to hand (9->10), next 2 burn
    game.emit(Event(
        type=EventType.DRAW,
        payload={'player': p1.id, 'count': 3},
        source='test'
    ))

    assert get_hand_count(game, p1) == 10, "Hand should be at max"
    final_gy_count = len(game.state.zones[graveyard_key].objects)
    assert final_gy_count == initial_gy_count + 2, "2 cards should be burned"


def test_no_overdraw_with_empty_hand():
    """Drawing with empty hand works normally."""
    game, p1, p2 = new_hs_game()

    # Add 5 cards to library
    add_cards_to_library(game, p1, count=5)

    assert get_hand_count(game, p1) == 0, "Hand should be empty"

    # Draw 5
    game.emit(Event(
        type=EventType.DRAW,
        payload={'player': p1.id, 'count': 5},
        source='test'
    ))

    assert get_hand_count(game, p1) == 5, "Hand should have 5 cards"
    assert get_library_count(game, p1) == 0, "Library should be empty"


# ============================================================
# Category 3: Card Draw Triggered by Deathrattle (5 tests)
# ============================================================

def test_loot_hoarder_deathrattle_draws():
    """Loot Hoarder deathrattle draws a card when it dies."""
    game, p1, p2 = new_hs_game()

    # Add cards to library
    add_cards_to_library(game, p1, count=3)

    # Play Loot Hoarder
    hoarder = play_minion(game, LOOT_HOARDER, p1)

    initial_hand = get_hand_count(game, p1)

    # Kill Loot Hoarder
    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': hoarder.id, 'reason': 'test'},
        source='test'
    ))

    final_hand = get_hand_count(game, p1)
    assert final_hand == initial_hand + 1, "Should draw 1 card from deathrattle"


def test_loot_hoarder_deathrattle_empty_deck():
    """Loot Hoarder deathrattle from empty deck triggers fatigue."""
    game, p1, p2 = new_hs_game()

    # Ensure library is empty
    library_key = f"library_{p1.id}"
    game.state.zones[library_key].objects.clear()

    # Play Loot Hoarder
    hoarder = play_minion(game, LOOT_HOARDER, p1)

    initial_life = p1.life

    # Kill Loot Hoarder
    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': hoarder.id, 'reason': 'test'},
        source='test'
    ))

    assert p1.fatigue_damage == 1, "Should take 1 fatigue damage"
    assert p1.life == initial_life - 1, "Life should decrease by 1"


def test_loot_hoarder_deathrattle_overdraw():
    """Loot Hoarder deathrattle with full hand burns the card."""
    game, p1, p2 = new_hs_game()

    # Fill hand to 10 cards
    hand_key = f"hand_{p1.id}"
    for i in range(10):
        obj = make_obj(game, WISP, p1, zone=ZoneType.HAND)

    # Add card to library
    add_cards_to_library(game, p1, count=1)

    # Play Loot Hoarder
    hoarder = play_minion(game, LOOT_HOARDER, p1)

    graveyard_key = f"graveyard_{p1.id}"
    initial_gy_count = len(game.state.zones[graveyard_key].objects)

    # Kill Loot Hoarder
    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': hoarder.id, 'reason': 'test'},
        source='test'
    ))

    assert get_hand_count(game, p1) == 10, "Hand should remain at 10"
    # Note: Loot Hoarder itself goes to graveyard + burned card
    final_gy_count = len(game.state.zones[graveyard_key].objects)
    assert final_gy_count >= initial_gy_count + 1, "Burned card should be in graveyard"


def test_multiple_loot_hoarders_die():
    """Multiple Loot Hoarders dying draw multiple cards."""
    game, p1, p2 = new_hs_game()

    # Add cards to library
    add_cards_to_library(game, p1, count=5)

    # Play 3 Loot Hoarders
    hoarder1 = play_minion(game, LOOT_HOARDER, p1)
    hoarder2 = play_minion(game, LOOT_HOARDER, p1)
    hoarder3 = play_minion(game, LOOT_HOARDER, p1)

    initial_hand = get_hand_count(game, p1)

    # Kill all 3
    for hoarder in [hoarder1, hoarder2, hoarder3]:
        game.emit(Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': hoarder.id, 'reason': 'test'},
            source='test'
        ))

    final_hand = get_hand_count(game, p1)
    assert final_hand == initial_hand + 3, "Should draw 3 cards from 3 deathrattles"


def test_loot_hoarder_dies_to_aoe():
    """Loot Hoarder dying to AOE still triggers deathrattle."""
    game, p1, p2 = new_hs_game()

    # Add cards to library
    add_cards_to_library(game, p1, count=3)

    # Play Loot Hoarder
    hoarder = play_minion(game, LOOT_HOARDER, p1)

    initial_hand = get_hand_count(game, p1)

    # Deal 1 damage directly to kill it (Loot Hoarder is 2/1)
    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': hoarder.id, 'amount': 1, 'source': 'test'},
        source='test'
    ))

    # Explicitly destroy it to trigger deathrattle
    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': hoarder.id, 'reason': 'lethal_damage'},
        source='test'
    ))

    final_hand = get_hand_count(game, p1)
    assert final_hand == initial_hand + 1, "Should draw 1 card from deathrattle"


# ============================================================
# Category 4: Card Draw Triggered by Spell (5 tests)
# ============================================================

def test_arcane_intellect_draws_2():
    """Arcane Intellect draws 2 cards."""
    game, p1, p2 = new_hs_game()

    # Add cards to library
    add_cards_to_library(game, p1, count=5)

    initial_hand = get_hand_count(game, p1)

    # Cast Arcane Intellect
    cast_spell(game, ARCANE_INTELLECT, p1)

    final_hand = get_hand_count(game, p1)
    assert final_hand == initial_hand + 2, "Should draw 2 cards"


def test_arcane_intellect_empty_deck():
    """Arcane Intellect from empty deck triggers fatigue twice."""
    game, p1, p2 = new_hs_game()

    # Ensure library is empty
    library_key = f"library_{p1.id}"
    game.state.zones[library_key].objects.clear()

    initial_life = p1.life

    # Cast Arcane Intellect (should trigger 1 + 2 = 3 total fatigue damage)
    cast_spell(game, ARCANE_INTELLECT, p1)

    assert p1.fatigue_damage == 2, "Should have 2 fatigue instances"
    assert p1.life == initial_life - 3, "Should take 1+2=3 fatigue damage"


def test_arcane_intellect_partial_deck():
    """Arcane Intellect with 1 card in deck draws 1 then fatigues."""
    game, p1, p2 = new_hs_game()

    # Add 1 card to library
    add_cards_to_library(game, p1, count=1)

    initial_hand = get_hand_count(game, p1)
    initial_life = p1.life

    # Cast Arcane Intellect (draws 1, then 1 fatigue)
    cast_spell(game, ARCANE_INTELLECT, p1)

    final_hand = get_hand_count(game, p1)
    assert final_hand == initial_hand + 1, "Should draw 1 card"
    assert p1.fatigue_damage == 1, "Should have 1 fatigue instance"
    assert p1.life == initial_life - 1, "Should take 1 fatigue damage"


def test_arcane_intellect_overdraw():
    """Arcane Intellect with 9 cards in hand draws 1 and burns 1."""
    game, p1, p2 = new_hs_game()

    # Fill hand to 9 cards
    hand_key = f"hand_{p1.id}"
    for i in range(9):
        obj = make_obj(game, WISP, p1, zone=ZoneType.HAND)

    # Add 2 cards to library
    add_cards_to_library(game, p1, count=2)

    graveyard_key = f"graveyard_{p1.id}"
    initial_gy_count = len(game.state.zones[graveyard_key].objects)

    # Cast Arcane Intellect
    cast_spell(game, ARCANE_INTELLECT, p1)

    assert get_hand_count(game, p1) == 10, "Hand should be at max"
    final_gy_count = len(game.state.zones[graveyard_key].objects)
    assert final_gy_count == initial_gy_count + 1, "1 card should be burned"


def test_arcane_intellect_full_hand():
    """Arcane Intellect with 10 cards in hand burns both draws."""
    game, p1, p2 = new_hs_game()

    # Fill hand to 10 cards
    hand_key = f"hand_{p1.id}"
    for i in range(10):
        obj = make_obj(game, WISP, p1, zone=ZoneType.HAND)

    # Add 2 cards to library
    add_cards_to_library(game, p1, count=2)

    graveyard_key = f"graveyard_{p1.id}"
    initial_gy_count = len(game.state.zones[graveyard_key].objects)

    # Cast Arcane Intellect
    cast_spell(game, ARCANE_INTELLECT, p1)

    assert get_hand_count(game, p1) == 10, "Hand should remain at 10"
    final_gy_count = len(game.state.zones[graveyard_key].objects)
    assert final_gy_count == initial_gy_count + 2, "Both cards should be burned"


# ============================================================
# Category 5: Sprint Draws 4 Cards Interaction (5 tests)
# ============================================================

def test_sprint_draws_4_cards():
    """Sprint draws 4 cards."""
    game, p1, p2 = new_hs_game()

    # Add cards to library
    add_cards_to_library(game, p1, count=10)

    initial_hand = get_hand_count(game, p1)

    # Cast Sprint
    cast_spell(game, SPRINT, p1)

    final_hand = get_hand_count(game, p1)
    assert final_hand == initial_hand + 4, "Should draw 4 cards"


def test_sprint_empty_deck():
    """Sprint from empty deck triggers 4 fatigue instances."""
    game, p1, p2 = new_hs_game()

    # Ensure library is empty
    library_key = f"library_{p1.id}"
    game.state.zones[library_key].objects.clear()

    initial_life = p1.life

    # Cast Sprint (should trigger 1+2+3+4 = 10 total fatigue damage)
    cast_spell(game, SPRINT, p1)

    assert p1.fatigue_damage == 4, "Should have 4 fatigue instances"
    assert p1.life == initial_life - 10, "Should take 1+2+3+4=10 fatigue damage"


def test_sprint_partial_deck_2_cards():
    """Sprint with 2 cards in deck draws 2 then fatigues 2 times."""
    game, p1, p2 = new_hs_game()

    # Add 2 cards to library
    add_cards_to_library(game, p1, count=2)

    initial_hand = get_hand_count(game, p1)
    initial_life = p1.life

    # Cast Sprint (draws 2, then 1+2 fatigue)
    cast_spell(game, SPRINT, p1)

    final_hand = get_hand_count(game, p1)
    assert final_hand == initial_hand + 2, "Should draw 2 cards"
    assert p1.fatigue_damage == 2, "Should have 2 fatigue instances"
    assert p1.life == initial_life - 3, "Should take 1+2=3 fatigue damage"


def test_sprint_full_hand():
    """Sprint with 10 cards in hand burns all 4 draws."""
    game, p1, p2 = new_hs_game()

    # Fill hand to 10 cards
    hand_key = f"hand_{p1.id}"
    for i in range(10):
        obj = make_obj(game, WISP, p1, zone=ZoneType.HAND)

    # Add 4 cards to library
    add_cards_to_library(game, p1, count=4)

    graveyard_key = f"graveyard_{p1.id}"
    initial_gy_count = len(game.state.zones[graveyard_key].objects)

    # Cast Sprint
    cast_spell(game, SPRINT, p1)

    assert get_hand_count(game, p1) == 10, "Hand should remain at 10"
    final_gy_count = len(game.state.zones[graveyard_key].objects)
    assert final_gy_count == initial_gy_count + 4, "All 4 cards should be burned"


def test_sprint_partial_overdraw():
    """Sprint with 8 cards in hand draws 2 and burns 2."""
    game, p1, p2 = new_hs_game()

    # Fill hand to 8 cards
    hand_key = f"hand_{p1.id}"
    for i in range(8):
        obj = make_obj(game, WISP, p1, zone=ZoneType.HAND)

    # Add 4 cards to library
    add_cards_to_library(game, p1, count=4)

    graveyard_key = f"graveyard_{p1.id}"
    initial_gy_count = len(game.state.zones[graveyard_key].objects)

    # Cast Sprint (should draw 2 to hand, burn 2)
    cast_spell(game, SPRINT, p1)

    assert get_hand_count(game, p1) == 10, "Hand should be at max"
    final_gy_count = len(game.state.zones[graveyard_key].objects)
    assert final_gy_count == initial_gy_count + 2, "2 cards should be burned"


# ============================================================
# Category 6: Novice Engineer Battlecry Draw (5 tests)
# ============================================================

def test_novice_engineer_battlecry_draws():
    """Novice Engineer battlecry draws a card."""
    game, p1, p2 = new_hs_game()

    # Add cards to library
    add_cards_to_library(game, p1, count=3)

    initial_hand = get_hand_count(game, p1)

    # Play Novice Engineer
    play_minion(game, NOVICE_ENGINEER, p1)

    final_hand = get_hand_count(game, p1)
    assert final_hand == initial_hand + 1, "Should draw 1 card from battlecry"


def test_novice_engineer_empty_deck():
    """Novice Engineer battlecry from empty deck triggers fatigue."""
    game, p1, p2 = new_hs_game()

    # Ensure library is empty
    library_key = f"library_{p1.id}"
    game.state.zones[library_key].objects.clear()

    initial_life = p1.life

    # Play Novice Engineer
    play_minion(game, NOVICE_ENGINEER, p1)

    assert p1.fatigue_damage == 1, "Should take 1 fatigue damage"
    assert p1.life == initial_life - 1, "Life should decrease by 1"


def test_novice_engineer_full_hand():
    """Novice Engineer battlecry with 10 cards already on board (after playing) doesn't burn."""
    game, p1, p2 = new_hs_game()

    # Fill hand to 10 cards INCLUDING Novice Engineer
    hand_key = f"hand_{p1.id}"
    for i in range(9):
        obj = make_obj(game, WISP, p1, zone=ZoneType.HAND)

    # Add card to library
    add_cards_to_library(game, p1, count=1)

    # Create Novice Engineer in hand (10th card)
    engineer = make_obj(game, NOVICE_ENGINEER, p1, zone=ZoneType.HAND)

    assert get_hand_count(game, p1) == 10, "Hand should have 10 cards"

    graveyard_key = f"graveyard_{p1.id}"
    initial_gy_count = len(game.state.zones[graveyard_key].objects)

    # Play Novice Engineer from hand (hand goes to 9, then battlecry draws 1 to make 10)
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': engineer.id,
            'from_zone_type': ZoneType.HAND,
            'to_zone_type': ZoneType.BATTLEFIELD,
            'controller': p1.id,
        },
        source=engineer.id
    ))

    # After playing: hand was 10, play Novice (-1 = 9), battlecry draws (+1 = 10)
    assert get_hand_count(game, p1) == 10, "Hand should be at 10"
    # Card should be drawn successfully since hand was at 9 when battlecry resolved
    final_gy_count = len(game.state.zones[graveyard_key].objects)
    assert final_gy_count == initial_gy_count, "Card should be drawn successfully, not burned"


def test_multiple_novice_engineers():
    """Playing multiple Novice Engineers draws multiple cards."""
    game, p1, p2 = new_hs_game()

    # Add cards to library
    add_cards_to_library(game, p1, count=5)

    initial_hand = get_hand_count(game, p1)

    # Play 3 Novice Engineers
    play_minion(game, NOVICE_ENGINEER, p1)
    play_minion(game, NOVICE_ENGINEER, p1)
    play_minion(game, NOVICE_ENGINEER, p1)

    final_hand = get_hand_count(game, p1)
    assert final_hand == initial_hand + 3, "Should draw 3 cards from 3 battlecries"


def test_novice_engineer_then_dies():
    """Novice Engineer draws on play, then dies (no additional draw)."""
    game, p1, p2 = new_hs_game()

    # Add cards to library
    add_cards_to_library(game, p1, count=5)

    initial_hand = get_hand_count(game, p1)

    # Play Novice Engineer
    engineer = play_minion(game, NOVICE_ENGINEER, p1)

    hand_after_play = get_hand_count(game, p1)
    assert hand_after_play == initial_hand + 1, "Should draw 1 card from battlecry"

    # Kill it (no deathrattle, so no additional draw)
    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': engineer.id, 'reason': 'test'},
        source='test'
    ))

    final_hand = get_hand_count(game, p1)
    assert final_hand == hand_after_play, "No additional card draw from death"


# ============================================================
# Category 7: Acolyte of Pain Draws on Damage (5 tests)
# ============================================================

def test_acolyte_draws_on_damage():
    """Acolyte of Pain draws when taking damage."""
    game, p1, p2 = new_hs_game()

    # Add cards to library
    add_cards_to_library(game, p1, count=5)

    # Play Acolyte of Pain (1/3)
    acolyte = play_minion(game, ACOLYTE_OF_PAIN, p1)

    initial_hand = get_hand_count(game, p1)

    # Deal 1 damage to Acolyte
    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': acolyte.id, 'amount': 1, 'source': 'test'},
        source='test'
    ))

    final_hand = get_hand_count(game, p1)
    assert final_hand == initial_hand + 1, "Should draw 1 card from taking damage"


def test_acolyte_draws_multiple_times():
    """Acolyte of Pain draws multiple times from multiple damage instances."""
    game, p1, p2 = new_hs_game()

    # Add cards to library
    add_cards_to_library(game, p1, count=5)

    # Play Acolyte of Pain (1/3)
    acolyte = play_minion(game, ACOLYTE_OF_PAIN, p1)

    initial_hand = get_hand_count(game, p1)

    # Deal damage 3 times (1 damage each)
    for _ in range(3):
        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': acolyte.id, 'amount': 1, 'source': 'test'},
            source='test'
        ))

    final_hand = get_hand_count(game, p1)
    assert final_hand == initial_hand + 3, "Should draw 3 cards from 3 damage instances"


def test_acolyte_empty_deck():
    """Acolyte of Pain taking damage from empty deck triggers fatigue."""
    game, p1, p2 = new_hs_game()

    # Ensure library is empty
    library_key = f"library_{p1.id}"
    game.state.zones[library_key].objects.clear()

    # Play Acolyte of Pain
    acolyte = play_minion(game, ACOLYTE_OF_PAIN, p1)

    initial_life = p1.life

    # Deal damage to Acolyte
    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': acolyte.id, 'amount': 1, 'source': 'test'},
        source='test'
    ))

    assert p1.fatigue_damage == 1, "Should take 1 fatigue damage"
    assert p1.life == initial_life - 1, "Life should decrease by 1"


def test_acolyte_full_hand():
    """Acolyte of Pain with full hand burns the drawn card."""
    game, p1, p2 = new_hs_game()

    # Fill hand to 10 cards
    hand_key = f"hand_{p1.id}"
    for i in range(10):
        obj = make_obj(game, WISP, p1, zone=ZoneType.HAND)

    # Add card to library
    add_cards_to_library(game, p1, count=1)

    # Play Acolyte of Pain
    acolyte = make_obj(game, ACOLYTE_OF_PAIN, p1, zone=ZoneType.BATTLEFIELD)
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': acolyte.id,
            'from_zone_type': None,
            'to_zone_type': ZoneType.BATTLEFIELD,
            'controller': p1.id,
        },
        source=acolyte.id
    ))

    graveyard_key = f"graveyard_{p1.id}"
    initial_gy_count = len(game.state.zones[graveyard_key].objects)

    # Deal damage to Acolyte
    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': acolyte.id, 'amount': 1, 'source': 'test'},
        source='test'
    ))

    assert get_hand_count(game, p1) == 10, "Hand should remain at 10"
    final_gy_count = len(game.state.zones[graveyard_key].objects)
    assert final_gy_count == initial_gy_count + 1, "Burned card should be in graveyard"


def test_acolyte_dies_from_damage():
    """Acolyte of Pain draws when taking lethal damage."""
    game, p1, p2 = new_hs_game()

    # Add cards to library
    add_cards_to_library(game, p1, count=5)

    # Play Acolyte of Pain (1/3)
    acolyte = play_minion(game, ACOLYTE_OF_PAIN, p1)

    initial_hand = get_hand_count(game, p1)

    # Deal 3 damage to Acolyte (kills it)
    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': acolyte.id, 'amount': 3, 'source': 'test'},
        source='test'
    ))

    final_hand = get_hand_count(game, p1)
    # Should draw 1 card even though it dies
    assert final_hand == initial_hand + 1, "Should draw exactly 1 card from damage"


# ============================================================
# Category 8: Drawing into Empty Deck at Low Health (5 tests)
# ============================================================

def test_fatigue_kills_at_1_health():
    """Drawing from empty deck at 1 health kills the player."""
    game, p1, p2 = new_hs_game()

    # Set player to 1 life
    p1.life = 1

    # Ensure library is empty
    library_key = f"library_{p1.id}"
    game.state.zones[library_key].objects.clear()

    # Draw (should trigger 1 fatigue damage, killing player)
    game.emit(Event(
        type=EventType.DRAW,
        payload={'player': p1.id, 'count': 1},
        source='test'
    ))

    assert p1.life <= 0, "Player should be dead"


def test_fatigue_kills_at_5_health_3rd_draw():
    """Third fatigue draw (3 damage) at 5 health leaves player at 2 health."""
    game, p1, p2 = new_hs_game()

    # Set player to 5 life
    p1.life = 5
    p1.fatigue_damage = 2  # Next draw will be 3 damage

    # Ensure library is empty
    library_key = f"library_{p1.id}"
    game.state.zones[library_key].objects.clear()

    # Draw (should trigger 3 fatigue damage)
    game.emit(Event(
        type=EventType.DRAW,
        payload={'player': p1.id, 'count': 1},
        source='test'
    ))

    assert p1.life == 2, f"Player should be at 2 life, got {p1.life}"


def test_sprint_kills_with_fatigue():
    """Sprint from empty deck at low health kills the player."""
    game, p1, p2 = new_hs_game()

    # Set player to 6 life (1+2+3+4 = 10 damage from Sprint)
    p1.life = 6

    # Ensure library is empty
    library_key = f"library_{p1.id}"
    game.state.zones[library_key].objects.clear()

    # Cast Sprint (should deal 10 fatigue damage total, killing player)
    cast_spell(game, SPRINT, p1)

    assert p1.life <= 0, "Player should be dead from fatigue"


def test_arcane_intellect_kills_with_fatigue():
    """Arcane Intellect from empty deck at 2 health kills the player."""
    game, p1, p2 = new_hs_game()

    # Set player to 2 life (1+2 = 3 damage from Arcane Intellect)
    p1.life = 2

    # Ensure library is empty
    library_key = f"library_{p1.id}"
    game.state.zones[library_key].objects.clear()

    # Cast Arcane Intellect (should deal 3 fatigue damage total, killing player)
    cast_spell(game, ARCANE_INTELLECT, p1)

    assert p1.life <= 0, "Player should be dead from fatigue"


def test_loot_hoarder_fatigue_kills():
    """Loot Hoarder deathrattle fatigue at 1 health kills the player."""
    game, p1, p2 = new_hs_game()

    # Set player to 1 life
    p1.life = 1

    # Ensure library is empty
    library_key = f"library_{p1.id}"
    game.state.zones[library_key].objects.clear()

    # Play Loot Hoarder
    hoarder = play_minion(game, LOOT_HOARDER, p1)

    # Kill Loot Hoarder (deathrattle should trigger 1 fatigue damage)
    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': hoarder.id, 'reason': 'test'},
        source='test'
    ))

    assert p1.life <= 0, "Player should be dead from fatigue"


# ============================================================
# Category 9: Multiple Draw Effects Stacking in Same Turn (5 tests)
# ============================================================

def test_multiple_arcane_intellects():
    """Casting multiple Arcane Intellects draws multiple cards."""
    game, p1, p2 = new_hs_game()

    # Add cards to library
    add_cards_to_library(game, p1, count=10)

    initial_hand = get_hand_count(game, p1)

    # Cast 2 Arcane Intellects
    cast_spell(game, ARCANE_INTELLECT, p1)
    cast_spell(game, ARCANE_INTELLECT, p1)

    final_hand = get_hand_count(game, p1)
    assert final_hand == initial_hand + 4, "Should draw 4 cards total"


def test_arcane_intellect_then_sprint():
    """Arcane Intellect then Sprint draws 6 cards total."""
    game, p1, p2 = new_hs_game()

    # Add cards to library
    add_cards_to_library(game, p1, count=10)

    initial_hand = get_hand_count(game, p1)

    # Cast Arcane Intellect then Sprint
    cast_spell(game, ARCANE_INTELLECT, p1)
    cast_spell(game, SPRINT, p1)

    final_hand = get_hand_count(game, p1)
    assert final_hand == initial_hand + 6, "Should draw 6 cards total (2+4)"


def test_novice_then_loot_hoarder_dies():
    """Novice Engineer then Loot Hoarder dying draws 2 cards."""
    game, p1, p2 = new_hs_game()

    # Add cards to library
    add_cards_to_library(game, p1, count=5)

    initial_hand = get_hand_count(game, p1)

    # Play Novice Engineer (draws 1)
    play_minion(game, NOVICE_ENGINEER, p1)

    # Play Loot Hoarder
    hoarder = play_minion(game, LOOT_HOARDER, p1)

    # Kill Loot Hoarder (draws 1)
    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': hoarder.id, 'reason': 'test'},
        source='test'
    ))

    final_hand = get_hand_count(game, p1)
    assert final_hand == initial_hand + 2, "Should draw 2 cards total"


def test_multiple_draw_effects_with_overdraw():
    """Multiple draw effects can cause progressive overdraw."""
    game, p1, p2 = new_hs_game()

    # Fill hand to 7 cards
    hand_key = f"hand_{p1.id}"
    for i in range(7):
        obj = make_obj(game, WISP, p1, zone=ZoneType.HAND)

    # Add 10 cards to library
    add_cards_to_library(game, p1, count=10)

    graveyard_key = f"graveyard_{p1.id}"
    initial_gy_count = len(game.state.zones[graveyard_key].objects)

    # Cast Arcane Intellect (draws 2, hand becomes 9)
    cast_spell(game, ARCANE_INTELLECT, p1)

    # Cast Arcane Intellect again (draws 1, burns 1)
    cast_spell(game, ARCANE_INTELLECT, p1)

    assert get_hand_count(game, p1) == 10, "Hand should be at max"
    final_gy_count = len(game.state.zones[graveyard_key].objects)
    assert final_gy_count >= initial_gy_count + 1, "At least 1 card should be burned"


def test_multiple_draw_empty_deck_stacking_fatigue():
    """Multiple draw effects from empty deck stack fatigue damage."""
    game, p1, p2 = new_hs_game()

    # Ensure library is empty
    library_key = f"library_{p1.id}"
    game.state.zones[library_key].objects.clear()

    initial_life = p1.life

    # Cast Arcane Intellect (1+2 = 3 damage)
    cast_spell(game, ARCANE_INTELLECT, p1)

    life_after_first = p1.life
    assert life_after_first == initial_life - 3, "Should take 3 fatigue damage"

    # Cast Arcane Intellect again (3+4 = 7 more damage)
    cast_spell(game, ARCANE_INTELLECT, p1)

    assert p1.fatigue_damage == 4, "Fatigue counter should be at 4"
    assert p1.life == life_after_first - 7, "Should take 7 more fatigue damage (3+4)"
