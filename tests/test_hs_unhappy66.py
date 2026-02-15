"""
Hearthstone Unhappy Path Tests - Batch 66

Multi-turn game scenarios: end-of-turn temporary buff cleanup, start-of-turn
draw, turn-based mana progression, Ragnaros end-of-turn across turns,
Mana Tide Totem draw every turn, end-of-turn hero attack cleanup,
Ysera dream card every turn, Nat Pagle coin-flip draw, temp buffs
lasting until end of turn (Savage Roar, Bloodlust, Heroic Strike),
multiple end-of-turn triggers ordering, start-of-turn summoning
sickness clear, weapon durability persisting across turns.
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
    FIERY_WAR_AXE,
)
from src.cards.hearthstone.classic import (
    RAGNAROS_THE_FIRELORD, YSERA, NAT_PAGLE,
)
from src.cards.hearthstone.shaman import (
    MANA_TIDE_TOTEM, BLOODLUST,
)
from src.cards.hearthstone.warrior import HEROIC_STRIKE
from src.cards.hearthstone.druid import SAVAGE_ROAR
from src.cards.hearthstone.paladin import BLESSING_OF_KINGS


# ============================================================
# Test Helpers
# ============================================================

def new_hs_game():
    """Create a fresh Hearthstone game with 2 players, heroes, and 10 mana each."""
    game = Game(mode='hearthstone')
    p1 = game.add_player("Player1", life=30)
    p2 = game.add_player("Player2", life=30)
    game.setup_hearthstone_player(p1, HEROES["Warrior"], HERO_POWERS["Warrior"])
    game.setup_hearthstone_player(p2, HEROES["Mage"], HERO_POWERS["Mage"])
    for _ in range(10):
        game.mana_system.on_turn_start(p1.id)
        game.mana_system.on_turn_start(p2.id)
    return game, p1, p2


def new_hs_game_fresh_mana():
    """Create a fresh Hearthstone game with 0 mana crystals (for mana progression tests)."""
    game = Game(mode='hearthstone')
    p1 = game.add_player("Player1", life=30)
    p2 = game.add_player("Player2", life=30)
    game.setup_hearthstone_player(p1, HEROES["Warrior"], HERO_POWERS["Warrior"])
    game.setup_hearthstone_player(p2, HEROES["Mage"], HERO_POWERS["Mage"])
    return game, p1, p2


def make_obj(game, card_def, owner, zone=ZoneType.BATTLEFIELD):
    """Create an object from a card definition."""
    obj = game.create_object(
        name=card_def.name, owner_id=owner.id, zone=zone,
        characteristics=card_def.characteristics, card_def=card_def
    )
    # Weapons need a ZONE_CHANGE event to trigger the equip interceptor
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


def get_battlefield_minions(game, player):
    """Get all minion objects on battlefield controlled by player."""
    bf = game.state.zones.get('battlefield')
    if not bf:
        return []
    result = []
    for oid in bf.objects:
        obj = game.state.objects.get(oid)
        if obj and obj.controller == player.id and CardType.MINION in obj.characteristics.types:
            result.append(obj)
    return result


def get_hand_objects(game, player):
    """Get all objects in a player's hand."""
    hand_key = f"hand_{player.id}"
    hand = game.state.zones.get(hand_key)
    if not hand:
        return []
    return [game.state.objects[oid] for oid in hand.objects if oid in game.state.objects]


def add_cards_to_library(game, player, card_def, count):
    """Add card objects to a player's library for draw testing."""
    lib_key = f"library_{player.id}"
    for _ in range(count):
        obj = game.create_object(
            name=card_def.name, owner_id=player.id, zone=ZoneType.LIBRARY,
            characteristics=card_def.characteristics, card_def=card_def
        )


def end_turn(game, player):
    """
    Simulate end-of-turn for a player.
    Emits PHASE_END (triggers Mana Tide, cleans pt_modifiers) then TURN_END (triggers Ragnaros, Ysera).
    Also performs the cleanup that HearthstoneTurnManager._run_end_phase does.
    """
    # 1. PHASE_END with phase='end' (used by make_end_of_turn_trigger)
    game.emit(Event(
        type=EventType.PHASE_END,
        payload={'phase': 'end', 'player': player.id},
        source='game'
    ))

    # 2. Clear end-of-turn PT modifiers on all battlefield objects
    battlefield = game.state.zones.get('battlefield')
    if battlefield:
        for obj_id in list(battlefield.objects):
            obj = game.state.objects.get(obj_id)
            if obj and hasattr(obj.state, 'pt_modifiers'):
                obj.state.pt_modifiers = [
                    mod for mod in obj.state.pt_modifiers
                    if mod.get('duration') != 'end_of_turn'
                ]

    # 3. Reset combat state for the active player
    if battlefield:
        for obj_id in list(battlefield.objects):
            obj = game.state.objects.get(obj_id)
            if obj and obj.controller == player.id:
                obj.state.attacks_this_turn = 0

    # 4. TURN_END (used by Ragnaros, Ysera, Savage Roar/Heroic Strike cleanup interceptors)
    game.emit(Event(
        type=EventType.TURN_END,
        payload={'player': player.id},
        source='game'
    ))


def start_turn(game, player):
    """
    Simulate start-of-turn for a player.
    Gains mana crystal, clears summoning sickness, draws a card.
    """
    # 1. TURN_START event
    game.emit(Event(
        type=EventType.TURN_START,
        payload={'player': player.id},
        source='game'
    ))

    # 2. Mana crystal gain + refill
    game.mana_system.on_turn_start(player.id)

    # 3. Clear summoning sickness for the active player's minions
    battlefield = game.state.zones.get('battlefield')
    if battlefield:
        for obj_id in list(battlefield.objects):
            obj = game.state.objects.get(obj_id)
            if obj and obj.controller == player.id and CardType.MINION in obj.characteristics.types:
                obj.state.summoning_sickness = False

    # 4. Draw a card
    lib_key = f"library_{player.id}"
    library = game.state.zones.get(lib_key)
    if library and library.objects:
        game.emit(Event(
            type=EventType.DRAW,
            payload={'player': player.id, 'count': 1},
            source='game'
        ))


# ============================================================
# Test 1: TestTurnStartDraw
# ============================================================

class TestTurnStartDraw:
    def test_turn_start_draws_a_card(self):
        """At start of turn, active player draws a card."""
        game, p1, p2 = new_hs_game()

        # Put some cards in p1's library
        add_cards_to_library(game, p1, WISP, 5)

        hand_before = len(get_hand_objects(game, p1))
        start_turn(game, p1)
        hand_after = len(get_hand_objects(game, p1))

        assert hand_after == hand_before + 1, (
            f"Player should draw 1 card at turn start, "
            f"hand went from {hand_before} to {hand_after}"
        )

    def test_turn_start_draw_does_not_affect_opponent(self):
        """Opponent's hand should not change on active player's turn start."""
        game, p1, p2 = new_hs_game()

        add_cards_to_library(game, p1, WISP, 5)
        add_cards_to_library(game, p2, WISP, 5)

        hand_p2_before = len(get_hand_objects(game, p2))
        start_turn(game, p1)
        hand_p2_after = len(get_hand_objects(game, p2))

        assert hand_p2_after == hand_p2_before, (
            f"Opponent hand should not change on active player's turn start, "
            f"p2 hand went from {hand_p2_before} to {hand_p2_after}"
        )


# ============================================================
# Test 2: TestTurnStartManaGain
# ============================================================

class TestTurnStartManaGain:
    def test_gains_one_mana_crystal_per_turn(self):
        """Each turn start grants +1 mana crystal."""
        game, p1, p2 = new_hs_game_fresh_mana()

        assert p1.mana_crystals == 0, "Should start with 0 mana crystals"

        game.mana_system.on_turn_start(p1.id)
        assert p1.mana_crystals == 1, f"After turn 1 should have 1 crystal, got {p1.mana_crystals}"
        assert p1.mana_crystals_available == 1, f"Available mana should be 1, got {p1.mana_crystals_available}"

        game.mana_system.on_turn_start(p1.id)
        assert p1.mana_crystals == 2, f"After turn 2 should have 2 crystals, got {p1.mana_crystals}"
        assert p1.mana_crystals_available == 2, f"Available mana should be 2, got {p1.mana_crystals_available}"

    def test_mana_crystals_cap_at_10(self):
        """Mana crystals should not exceed 10."""
        game, p1, p2 = new_hs_game_fresh_mana()

        for i in range(12):
            game.mana_system.on_turn_start(p1.id)

        assert p1.mana_crystals == 10, f"Mana should cap at 10, got {p1.mana_crystals}"
        assert p1.mana_crystals_available == 10, f"Available mana should be 10, got {p1.mana_crystals_available}"

    def test_mana_refills_each_turn(self):
        """Available mana should refill to max each turn start."""
        game, p1, p2 = new_hs_game()

        # Spend some mana
        p1.mana_crystals_available = 3  # 7 mana spent

        game.mana_system.on_turn_start(p1.id)
        assert p1.mana_crystals_available == p1.mana_crystals, (
            f"Available mana should refill to {p1.mana_crystals}, "
            f"got {p1.mana_crystals_available}"
        )


# ============================================================
# Test 3: TestTurnStartSummoningSicknessClear
# ============================================================

class TestTurnStartSummoningSicknessClear:
    def test_summoning_sickness_cleared_at_turn_start(self):
        """Minions lose summoning sickness at their controller's turn start."""
        game, p1, p2 = new_hs_game()

        minion = make_obj(game, CHILLWIND_YETI, p1)
        assert minion.state.summoning_sickness is True, (
            "Newly placed minion should have summoning sickness"
        )

        start_turn(game, p1)
        assert minion.state.summoning_sickness is False, (
            "Minion should lose summoning sickness at controller's turn start"
        )

    def test_summoning_sickness_not_cleared_on_opponent_turn(self):
        """Minions should NOT lose summoning sickness on opponent's turn start."""
        game, p1, p2 = new_hs_game()

        add_cards_to_library(game, p2, WISP, 5)

        minion = make_obj(game, CHILLWIND_YETI, p1)
        assert minion.state.summoning_sickness is True

        # Start opponent's turn (not the minion's controller)
        start_turn(game, p2)

        assert minion.state.summoning_sickness is True, (
            "Minion should still have summoning sickness after opponent's turn start"
        )


# ============================================================
# Test 4: TestEndOfTurnTempBuffExpires
# ============================================================

class TestEndOfTurnTempBuffExpires:
    def test_savage_roar_hero_attack_expires_end_of_turn(self):
        """Savage Roar gives +2 hero attack this turn; at end of turn it expires."""
        game, p1, p2 = new_hs_game()

        # Verify hero has no weapon attack before casting
        assert p1.weapon_attack == 0, f"Hero should start with 0 weapon_attack, got {p1.weapon_attack}"

        # Cast Savage Roar
        cast_spell(game, SAVAGE_ROAR, p1)

        assert p1.weapon_attack >= 2, (
            f"Hero should have at least +2 weapon_attack from Savage Roar, got {p1.weapon_attack}"
        )

        # End the turn
        end_turn(game, p1)

        assert p1.weapon_attack == 0, (
            f"Hero weapon_attack should return to 0 after end of turn, got {p1.weapon_attack}"
        )

    def test_savage_roar_minion_buff_expires_end_of_turn(self):
        """Savage Roar gives +2 attack to minions this turn; at end of turn buff expires."""
        game, p1, p2 = new_hs_game()

        minion = make_obj(game, CHILLWIND_YETI, p1)  # 4/5
        base_power = get_power(minion, game.state)
        assert base_power == 4, f"Yeti base power should be 4, got {base_power}"

        # Cast Savage Roar (+2 attack this turn)
        cast_spell(game, SAVAGE_ROAR, p1)

        buffed_power = get_power(minion, game.state)
        assert buffed_power == 6, (
            f"Yeti should have 6 power after Savage Roar, got {buffed_power}"
        )

        # End turn -> buff expires
        end_turn(game, p1)

        final_power = get_power(minion, game.state)
        assert final_power == 4, (
            f"Yeti should return to 4 power after end of turn, got {final_power}"
        )


# ============================================================
# Test 5: TestBloodlustExpiresEndOfTurn
# ============================================================

class TestBloodlustExpiresEndOfTurn:
    def test_bloodlust_minion_buff_expires(self):
        """Bloodlust gives +3 attack to all friendly minions this turn; expires at end of turn."""
        game, p1, p2 = new_hs_game()

        m1 = make_obj(game, WISP, p1)         # 1/1
        m2 = make_obj(game, CHILLWIND_YETI, p1)  # 4/5

        cast_spell(game, BLOODLUST, p1)

        m1_power = get_power(m1, game.state)
        m2_power = get_power(m2, game.state)
        assert m1_power == 4, f"Wisp should have 4 power after Bloodlust, got {m1_power}"
        assert m2_power == 7, f"Yeti should have 7 power after Bloodlust, got {m2_power}"

        # End turn -> buff expires
        end_turn(game, p1)

        m1_power_after = get_power(m1, game.state)
        m2_power_after = get_power(m2, game.state)
        assert m1_power_after == 1, (
            f"Wisp should return to 1 power after end of turn, got {m1_power_after}"
        )
        assert m2_power_after == 4, (
            f"Yeti should return to 4 power after end of turn, got {m2_power_after}"
        )

    def test_bloodlust_does_not_affect_enemy_minions(self):
        """Bloodlust should only buff friendly minions, not enemy ones."""
        game, p1, p2 = new_hs_game()

        enemy_minion = make_obj(game, CHILLWIND_YETI, p2)  # 4/5, enemy
        friendly_minion = make_obj(game, WISP, p1)          # 1/1, friendly

        cast_spell(game, BLOODLUST, p1)

        enemy_power = get_power(enemy_minion, game.state)
        assert enemy_power == 4, (
            f"Enemy Yeti should still have 4 power (no Bloodlust buff), got {enemy_power}"
        )


# ============================================================
# Test 6: TestHeroicStrikeExpiresEndOfTurn
# ============================================================

class TestHeroicStrikeExpiresEndOfTurn:
    def test_heroic_strike_gives_4_attack(self):
        """Heroic Strike gives hero +4 attack this turn."""
        game, p1, p2 = new_hs_game()

        assert p1.weapon_attack == 0, f"Hero should start with 0 attack, got {p1.weapon_attack}"

        cast_spell(game, HEROIC_STRIKE, p1)
        assert p1.weapon_attack == 4, (
            f"Hero should have 4 weapon_attack after Heroic Strike, got {p1.weapon_attack}"
        )

    def test_heroic_strike_expires_end_of_turn(self):
        """Heroic Strike +4 attack expires at end of turn."""
        game, p1, p2 = new_hs_game()

        cast_spell(game, HEROIC_STRIKE, p1)
        assert p1.weapon_attack == 4

        end_turn(game, p1)
        assert p1.weapon_attack == 0, (
            f"Hero weapon_attack should return to 0 after end of turn, got {p1.weapon_attack}"
        )

    def test_heroic_strike_stacks_with_weapon(self):
        """Heroic Strike should stack with an equipped weapon's attack."""
        game, p1, p2 = new_hs_game()

        # Equip weapon first (3 attack)
        make_obj(game, FIERY_WAR_AXE, p1)
        assert p1.weapon_attack == 3, f"Expected weapon_attack=3, got {p1.weapon_attack}"

        # Cast Heroic Strike (+4)
        cast_spell(game, HEROIC_STRIKE, p1)
        assert p1.weapon_attack == 7, (
            f"Weapon + Heroic Strike should give 7 attack, got {p1.weapon_attack}"
        )

        # End turn -> Heroic Strike expires, weapon remains
        end_turn(game, p1)
        assert p1.weapon_attack == 3, (
            f"After end of turn, weapon_attack should revert to weapon's base 3, got {p1.weapon_attack}"
        )


# ============================================================
# Test 7: TestRagnarosFiresEveryTurn
# ============================================================

class TestRagnarosFiresEveryTurn:
    def test_ragnaros_fires_two_turns(self):
        """Ragnaros fires 8 damage at end of each controller's turn. 2 turns = 2 fires."""
        game, p1, p2 = new_hs_game()
        rag = make_obj(game, RAGNAROS_THE_FIRELORD, p1)

        initial_life = p2.life
        random.seed(42)

        # Turn 1 end
        end_turn(game, p1)
        life_after_turn1 = p2.life
        assert life_after_turn1 == initial_life - 8, (
            f"After turn 1 end, p2 should lose 8 life (no enemy minions), "
            f"expected {initial_life - 8}, got {life_after_turn1}"
        )

        # Simulate turn 2 (opponent turn, then back to p1)
        # Ragnaros should NOT fire on opponent's turn
        end_turn(game, p2)
        life_after_opp_turn = p2.life
        assert life_after_opp_turn == life_after_turn1, (
            f"Ragnaros should not fire on opponent's turn end, "
            f"p2 life should stay {life_after_turn1}, got {life_after_opp_turn}"
        )

        # Turn 2 end (p1's turn again)
        end_turn(game, p1)
        life_after_turn2 = p2.life
        assert life_after_turn2 == initial_life - 16, (
            f"After 2 of p1's turns, p2 should lose 16 total life, "
            f"expected {initial_life - 16}, got {life_after_turn2}"
        )


# ============================================================
# Test 8: TestManaTideDrawsEveryTurn
# ============================================================

class TestManaTideDrawsEveryTurn:
    def test_mana_tide_draws_two_turns(self):
        """Mana Tide Totem draws at end of each controller's turn. 2 turns = 2 draws."""
        game, p1, p2 = new_hs_game()
        totem = make_obj(game, MANA_TIDE_TOTEM, p1)

        # Add cards to library so draws don't cause fatigue
        add_cards_to_library(game, p1, WISP, 10)

        hand_before = len(get_hand_objects(game, p1))

        # End turn 1
        end_turn(game, p1)
        hand_after_t1 = len(get_hand_objects(game, p1))
        assert hand_after_t1 == hand_before + 1, (
            f"Mana Tide should draw 1 card at end of turn 1, "
            f"hand went from {hand_before} to {hand_after_t1}"
        )

        # End turn 2 (p1's turn again)
        end_turn(game, p1)
        hand_after_t2 = len(get_hand_objects(game, p1))
        assert hand_after_t2 == hand_before + 2, (
            f"Mana Tide should draw 1 card each turn, "
            f"expected {hand_before + 2} cards, got {hand_after_t2}"
        )

    def test_mana_tide_does_not_draw_on_opponent_turn(self):
        """Mana Tide Totem should NOT draw on opponent's turn end."""
        game, p1, p2 = new_hs_game()
        totem = make_obj(game, MANA_TIDE_TOTEM, p1)

        add_cards_to_library(game, p1, WISP, 10)

        hand_before = len(get_hand_objects(game, p1))

        # End opponent's turn
        end_turn(game, p2)
        hand_after = len(get_hand_objects(game, p1))

        assert hand_after == hand_before, (
            f"Mana Tide should not draw on opponent's turn end, "
            f"hand should stay at {hand_before}, got {hand_after}"
        )


# ============================================================
# Test 9: TestYseraDreamCardEveryTurn
# ============================================================

class TestYseraDreamCardEveryTurn:
    def test_ysera_generates_dream_card_each_turn(self):
        """Ysera adds a Dream Card at end of each controller's turn."""
        game, p1, p2 = new_hs_game()
        ysera = make_obj(game, YSERA, p1)

        hand_before = len(get_hand_objects(game, p1))
        random.seed(42)

        # End turn 1
        end_turn(game, p1)
        hand_after_t1 = len(get_hand_objects(game, p1))
        assert hand_after_t1 == hand_before + 1, (
            f"Ysera should add 1 Dream Card at end of turn 1, "
            f"hand went from {hand_before} to {hand_after_t1}"
        )

        # End turn 2
        end_turn(game, p1)
        hand_after_t2 = len(get_hand_objects(game, p1))
        assert hand_after_t2 == hand_before + 2, (
            f"Ysera should add 1 Dream Card each turn, "
            f"expected {hand_before + 2}, got {hand_after_t2}"
        )

    def test_ysera_does_not_trigger_on_opponent_turn(self):
        """Ysera should NOT generate a Dream Card on opponent's turn end."""
        game, p1, p2 = new_hs_game()
        ysera = make_obj(game, YSERA, p1)

        hand_before = len(get_hand_objects(game, p1))
        random.seed(42)

        # End opponent's turn
        end_turn(game, p2)
        hand_after = len(get_hand_objects(game, p1))

        assert hand_after == hand_before, (
            f"Ysera should not trigger on opponent's turn end, "
            f"hand should stay at {hand_before}, got {hand_after}"
        )


# ============================================================
# Test 10: TestMultipleEndOfTurnTriggers
# ============================================================

class TestMultipleEndOfTurnTriggers:
    def test_ragnaros_and_mana_tide_both_fire(self):
        """Ragnaros + Mana Tide on same board should both fire at end of turn."""
        game, p1, p2 = new_hs_game()
        rag = make_obj(game, RAGNAROS_THE_FIRELORD, p1)
        totem = make_obj(game, MANA_TIDE_TOTEM, p1)

        add_cards_to_library(game, p1, WISP, 10)

        initial_life = p2.life
        hand_before = len(get_hand_objects(game, p1))

        random.seed(42)
        end_turn(game, p1)

        # Mana Tide should have drawn (PHASE_END trigger)
        hand_after = len(get_hand_objects(game, p1))
        assert hand_after >= hand_before + 1, (
            f"Mana Tide should draw 1 card, hand went from {hand_before} to {hand_after}"
        )

        # Ragnaros should have dealt 8 (TURN_END trigger)
        # With no enemy minions, hits hero
        if not get_battlefield_minions(game, p2):
            assert p2.life == initial_life - 8, (
                f"Ragnaros should deal 8 to enemy hero, "
                f"expected {initial_life - 8}, got {p2.life}"
            )

    def test_ysera_and_mana_tide_both_fire(self):
        """Ysera + Mana Tide on same board should both fire at end of turn."""
        game, p1, p2 = new_hs_game()
        ysera = make_obj(game, YSERA, p1)
        totem = make_obj(game, MANA_TIDE_TOTEM, p1)

        add_cards_to_library(game, p1, WISP, 10)

        hand_before = len(get_hand_objects(game, p1))
        random.seed(42)

        end_turn(game, p1)

        hand_after = len(get_hand_objects(game, p1))
        # Mana Tide draws 1 (PHASE_END) + Ysera adds 1 dream card (TURN_END) = 2
        assert hand_after >= hand_before + 2, (
            f"Mana Tide + Ysera should add 2 cards total, "
            f"hand went from {hand_before} to {hand_after}"
        )


# ============================================================
# Test 11: TestWeaponDurabilityPersistsAcrossTurns
# ============================================================

class TestWeaponDurabilityPersistsAcrossTurns:
    def test_weapon_persists_without_attacking(self):
        """Weapon equipped on turn 1 should still be there on turn 2 if not used."""
        game, p1, p2 = new_hs_game()

        axe = make_obj(game, FIERY_WAR_AXE, p1)
        assert p1.weapon_attack == 3
        assert p1.weapon_durability == 2

        # End turn 1 (no attack)
        end_turn(game, p1)

        # Check weapon is still equipped
        assert p1.weapon_attack == 3, (
            f"Weapon attack should persist across turns, got {p1.weapon_attack}"
        )
        assert p1.weapon_durability == 2, (
            f"Weapon durability should persist across turns (no attack used), got {p1.weapon_durability}"
        )

        # Start turn 2
        add_cards_to_library(game, p1, WISP, 5)
        start_turn(game, p1)

        # Weapon should still be there
        assert p1.weapon_attack == 3, (
            f"Weapon should still be equipped on turn 2, got {p1.weapon_attack}"
        )
        assert p1.weapon_durability == 2, (
            f"Weapon durability should be unchanged on turn 2, got {p1.weapon_durability}"
        )

    def test_weapon_on_battlefield_persists(self):
        """The weapon object should remain on the battlefield across turns."""
        game, p1, p2 = new_hs_game()

        axe = make_obj(game, FIERY_WAR_AXE, p1)
        assert axe.zone == ZoneType.BATTLEFIELD

        end_turn(game, p1)

        assert axe.zone == ZoneType.BATTLEFIELD, (
            f"Weapon object should remain on battlefield, zone is {axe.zone}"
        )


# ============================================================
# Test 12: TestBuffsFromPreviousTurnsStay
# ============================================================

class TestBuffsFromPreviousTurnsStay:
    def test_blessing_of_kings_persists_across_turns(self):
        """Blessing of Kings (+4/+4 permanent) should persist across turns."""
        game, p1, p2 = new_hs_game()

        minion = make_obj(game, CHILLWIND_YETI, p1)  # 4/5
        base_power = get_power(minion, game.state)
        base_toughness = get_toughness(minion, game.state)
        assert base_power == 4
        assert base_toughness == 5

        # Cast Blessing of Kings on the minion
        random.seed(42)
        cast_spell(game, BLESSING_OF_KINGS, p1)

        # Check buff applied
        buffed_power = get_power(minion, game.state)
        buffed_toughness = get_toughness(minion, game.state)
        assert buffed_power == 8, f"Power should be 8 after BoK, got {buffed_power}"
        assert buffed_toughness == 9, f"Toughness should be 9 after BoK, got {buffed_toughness}"

        # End turn
        end_turn(game, p1)

        # Permanent buff should persist
        post_turn_power = get_power(minion, game.state)
        post_turn_toughness = get_toughness(minion, game.state)
        assert post_turn_power == 8, (
            f"Permanent buff power should persist, expected 8, got {post_turn_power}"
        )
        assert post_turn_toughness == 9, (
            f"Permanent buff toughness should persist, expected 9, got {post_turn_toughness}"
        )

    def test_plus_one_counters_persist_across_turns(self):
        """Counters (+1/+1) should persist across turns."""
        game, p1, p2 = new_hs_game()

        minion = make_obj(game, WISP, p1)  # 1/1
        minion.state.counters['+1/+1'] = 2  # Add 2 counters -> 3/3

        power = get_power(minion, game.state)
        assert power == 3, f"Power with counters should be 3, got {power}"

        end_turn(game, p1)

        power_after = get_power(minion, game.state)
        assert power_after == 3, (
            f"Counters should persist across turns, expected 3, got {power_after}"
        )


# ============================================================
# Test 13: TestDamageRemainsAcrossTurns
# ============================================================

class TestDamageRemainsAcrossTurns:
    def test_damage_persists_across_turns(self):
        """A minion damaged on turn 1 should still be damaged on turn 2 (no auto-heal)."""
        game, p1, p2 = new_hs_game()

        minion = make_obj(game, CHILLWIND_YETI, p1)  # 4/5

        # Deal 3 damage
        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': minion.id, 'amount': 3, 'source': 'test'},
            source='test'
        ))
        assert minion.state.damage == 3, f"Minion should have 3 damage, got {minion.state.damage}"

        effective_health = get_toughness(minion, game.state) - minion.state.damage
        assert effective_health == 2, f"Effective health should be 2, got {effective_health}"

        # End turn
        end_turn(game, p1)

        # Damage should persist
        assert minion.state.damage == 3, (
            f"Damage should persist across turns, got {minion.state.damage}"
        )

        # Start next turn
        add_cards_to_library(game, p1, WISP, 5)
        start_turn(game, p1)

        # Still damaged
        assert minion.state.damage == 3, (
            f"Damage should still persist after new turn starts, got {minion.state.damage}"
        )

    def test_no_auto_heal_between_turns(self):
        """Minions should NOT auto-heal between turns in Hearthstone."""
        game, p1, p2 = new_hs_game()

        m1 = make_obj(game, BOULDERFIST_OGRE, p1)  # 6/7

        # Deal 5 damage
        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': m1.id, 'amount': 5, 'source': 'test'},
            source='test'
        ))
        assert m1.state.damage == 5

        # Full turn cycle
        end_turn(game, p1)
        add_cards_to_library(game, p1, WISP, 5)
        start_turn(game, p1)

        assert m1.state.damage == 5, (
            f"Ogre should still have 5 damage after turn cycle, got {m1.state.damage}"
        )
        effective_health = get_toughness(m1, game.state) - m1.state.damage
        assert effective_health == 2, (
            f"Ogre effective health should be 2, got {effective_health}"
        )


# ============================================================
# Run tests
# ============================================================

if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
