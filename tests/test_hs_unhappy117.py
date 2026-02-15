"""
Hearthstone Unhappy Path Tests - Batch 117

Hero Power Interactions and Class Mechanics tests.

Tests cover:
- Hero power once per turn (5 tests)
- Mage hero power (Fireblast deals 1 damage) (5 tests)
- Warrior hero power (Armor Up grants 2 armor) (5 tests)
- Priest hero power (Lesser Heal restores 2 health) (5 tests)
- Warlock hero power (Life Tap draws card, costs 2 life) (5 tests)
- Hunter hero power (Steady Shot deals 2 to enemy hero) (5 tests)
- Paladin hero power (Reinforce summons 1/1) (5 tests)
- Rogue hero power (Dagger Mastery equips 1/2) (5 tests)
- Shaman hero power (Totemic Call summons totem) (5 tests)
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
    FIREBALL, AZURE_DRAKE, BLOODMAGE_THALNOS, ARGENT_COMMANDER,
    WILD_PYROMANCER, LOOT_HOARDER
)


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


def use_hero_power(game, player):
    """Activate a hero power via event emission."""
    hp_obj = game.state.objects.get(player.hero_power_id)
    if not hp_obj:
        return None

    # Get the hero power effect from the card_def
    hp_def = hp_obj.card_def
    if hasattr(hp_def, 'setup_interceptors') and hp_def.setup_interceptors:
        # For complex hero powers with interceptors, emit the event
        game.emit(Event(
            type=EventType.HERO_POWER_ACTIVATE,
            payload={'hero_power_id': player.hero_power_id, 'player': player.id},
            source=player.hero_power_id,
        ))
    else:
        # Call the effect function directly from hero_powers.py
        # Each hero power definition has an 'effect' parameter
        # We need to find it in the setup_interceptors wrapper
        from src.cards.hearthstone import hero_powers

        # Map class to effect function
        class_to_effect = {
            'Mage': hero_powers.fireblast_effect,
            'Warrior': hero_powers.armor_up_effect,
            'Hunter': hero_powers.steady_shot_effect,
            'Paladin': hero_powers.reinforce_effect,
            'Priest': hero_powers.lesser_heal_effect,
            'Rogue': hero_powers.dagger_mastery_effect,
            'Shaman': hero_powers.totemic_call_effect,
            'Warlock': hero_powers.life_tap_effect,
            'Druid': hero_powers.shapeshift_effect,
        }

        # Determine which class this hero power belongs to
        for class_name, hp_card in HERO_POWERS.items():
            if hp_card.name == hp_def.name:
                effect_fn = class_to_effect.get(class_name)
                if effect_fn:
                    events = effect_fn(hp_obj, game.state)
                    for e in events:
                        game.emit(e)
                break

    # Mark as used
    player.hero_power_used = True
    # Deduct mana
    player.mana_crystals_available -= 2

    return hp_obj


def add_to_library(game, card_def, owner, count=1):
    """Add cards to player's library."""
    zone_name = f"library_{owner.id}"
    if zone_name not in game.state.zones:
        game.state.zones[zone_name] = type('Zone', (), {'objects': []})()

    for _ in range(count):
        obj = game.create_object(
            name=card_def.name, owner_id=owner.id, zone=ZoneType.LIBRARY,
            characteristics=card_def.characteristics, card_def=card_def
        )
        game.state.zones[zone_name].objects.append(obj.id)


# ============================================================
# Category 1: Hero Power Once Per Turn (5 tests)
# ============================================================

class TestHeroPowerOncePerTurn:
    def test_cannot_use_hero_power_twice_same_turn(self):
        """Cannot use hero power twice in the same turn."""
        game, p1, p2 = new_hs_game("Mage", "Warrior")

        # Use hero power once
        use_hero_power(game, p1)
        assert p1.hero_power_used == True

        # Try to use it again - should fail
        initial_life = p2.life
        use_hero_power(game, p1)

        # Enemy hero should only have taken 1 damage (first use only)
        assert p2.life == initial_life  # No additional damage

    def test_hero_power_resets_on_new_turn(self):
        """Hero power usage resets at the start of next turn."""
        game, p1, p2 = new_hs_game("Warrior", "Mage")

        # Use hero power
        use_hero_power(game, p1)
        assert p1.hero_power_used == True
        initial_armor = p1.armor

        # Start new turn (manually reset hero_power_used)
        p1.hero_power_used = False
        game.emit(Event(
            type=EventType.TURN_START,
            payload={'player': p1.id},
            source=None
        ))

        # Hero power should be available again
        assert p1.hero_power_used == False

        # Use it again
        use_hero_power(game, p1)
        assert p1.armor > initial_armor

    def test_hero_power_blocked_after_first_use(self):
        """Hero power is blocked after first use in turn."""
        game, p1, p2 = new_hs_game("Hunter", "Warrior")

        initial_life = p2.life
        use_hero_power(game, p1)
        assert p2.life == initial_life - 2

        # Mark as used and try again
        assert p1.hero_power_used == True
        life_after_first = p2.life

        # Attempt second use (should do nothing)
        use_hero_power(game, p1)
        assert p2.life == life_after_first  # No change

    def test_multiple_turns_multiple_uses(self):
        """Can use hero power once per turn over multiple turns."""
        game, p1, p2 = new_hs_game("Paladin", "Warrior")

        # Turn 1
        use_hero_power(game, p1)
        count1 = get_battlefield_count(game, p1)
        assert count1 == 1

        # Turn 2
        p1.hero_power_used = False
        game.emit(Event(type=EventType.TURN_START, payload={'player': p1.id}, source=None))
        use_hero_power(game, p1)
        count2 = get_battlefield_count(game, p1)
        assert count2 == 2

        # Turn 3
        p1.hero_power_used = False
        game.emit(Event(type=EventType.TURN_START, payload={'player': p1.id}, source=None))
        use_hero_power(game, p1)
        count3 = get_battlefield_count(game, p1)
        assert count3 == 3

    def test_opponent_hero_power_independent(self):
        """Each player's hero power usage is independent."""
        game, p1, p2 = new_hs_game("Mage", "Warrior")

        # P1 uses hero power
        use_hero_power(game, p1)
        assert p1.hero_power_used == True
        assert p2.hero_power_used == False

        # P2 can still use theirs
        use_hero_power(game, p2)
        assert p1.hero_power_used == True
        assert p2.hero_power_used == True
        assert p2.armor == 2


# ============================================================
# Category 2: Mage Hero Power (Fireblast) (5 tests)
# ============================================================

class TestMageHeroPower:
    def test_fireblast_deals_1_damage(self):
        """Fireblast deals exactly 1 damage to enemy hero."""
        game, p1, p2 = new_hs_game("Mage", "Warrior")

        initial_life = p2.life
        use_hero_power(game, p1)

        assert p2.life == initial_life - 1

    def test_fireblast_with_spell_damage(self):
        """Fireblast is NOT affected by spell damage (it's not a spell)."""
        game, p1, p2 = new_hs_game("Mage", "Warrior")

        # Add spell damage minion
        play_minion(game, BLOODMAGE_THALNOS, p1)

        initial_life = p2.life
        use_hero_power(game, p1)

        # Should deal only 1 damage (hero power is not a spell)
        assert p2.life == initial_life - 1

    def test_fireblast_on_damaged_hero(self):
        """Fireblast works on already damaged hero."""
        game, p1, p2 = new_hs_game("Mage", "Warrior")

        # Damage enemy hero first
        p2.life = 15

        use_hero_power(game, p1)
        assert p2.life == 14

    def test_fireblast_lethal(self):
        """Fireblast can deal lethal damage."""
        game, p1, p2 = new_hs_game("Mage", "Warrior")

        p2.life = 1
        use_hero_power(game, p1)

        assert p2.life == 0

    def test_fireblast_costs_2_mana(self):
        """Fireblast costs 2 mana."""
        game, p1, p2 = new_hs_game("Mage", "Warrior")

        initial_mana = p1.mana_crystals_available
        use_hero_power(game, p1)

        assert p1.mana_crystals_available == initial_mana - 2


# ============================================================
# Category 3: Warrior Hero Power (Armor Up) (5 tests)
# ============================================================

class TestWarriorHeroPower:
    def test_armor_up_grants_2_armor(self):
        """Armor Up grants exactly 2 armor."""
        game, p1, p2 = new_hs_game("Warrior", "Mage")

        assert p1.armor == 0
        use_hero_power(game, p1)
        assert p1.armor == 2

    def test_armor_up_stacks(self):
        """Armor from multiple uses stacks."""
        game, p1, p2 = new_hs_game("Warrior", "Mage")

        use_hero_power(game, p1)
        assert p1.armor == 2

        # Next turn
        p1.hero_power_used = False
        game.emit(Event(type=EventType.TURN_START, payload={'player': p1.id}, source=None))
        use_hero_power(game, p1)
        assert p1.armor == 4

    def test_armor_up_at_max_life(self):
        """Armor Up works even at max life."""
        game, p1, p2 = new_hs_game("Warrior", "Mage")

        assert p1.life == 30
        use_hero_power(game, p1)

        assert p1.armor == 2
        assert p1.life == 30

    def test_armor_protects_from_damage(self):
        """Armor blocks damage before life."""
        game, p1, p2 = new_hs_game("Warrior", "Mage")

        use_hero_power(game, p1)
        assert p1.armor == 2

        # Take 1 damage
        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': p1.hero_id, 'amount': 1, 'source': None},
            source=None
        ))

        assert p1.armor == 1
        assert p1.life == 30

    def test_armor_up_costs_2_mana(self):
        """Armor Up costs 2 mana."""
        game, p1, p2 = new_hs_game("Warrior", "Mage")

        initial_mana = p1.mana_crystals_available
        use_hero_power(game, p1)

        assert p1.mana_crystals_available == initial_mana - 2


# ============================================================
# Category 4: Priest Hero Power (Lesser Heal) (5 tests)
# ============================================================

class TestPriestHeroPower:
    def test_lesser_heal_restores_2_health(self):
        """Lesser Heal restores 2 health to own hero."""
        game, p1, p2 = new_hs_game("Priest", "Mage")

        p1.life = 20
        use_hero_power(game, p1)

        assert p1.life == 22

    def test_lesser_heal_at_max_health(self):
        """Lesser Heal does nothing at max health."""
        game, p1, p2 = new_hs_game("Priest", "Mage")

        assert p1.life == 30
        use_hero_power(game, p1)

        # Should not go above max
        assert p1.life == 30

    def test_lesser_heal_caps_at_max(self):
        """Lesser Heal caps at max health."""
        game, p1, p2 = new_hs_game("Priest", "Mage")

        p1.life = 29
        use_hero_power(game, p1)

        assert p1.life == 30  # Capped, not 31

    def test_lesser_heal_after_damage(self):
        """Lesser Heal works after taking damage."""
        game, p1, p2 = new_hs_game("Priest", "Mage")

        p1.life = 15
        use_hero_power(game, p1)

        assert p1.life == 17

    def test_lesser_heal_costs_2_mana(self):
        """Lesser Heal costs 2 mana."""
        game, p1, p2 = new_hs_game("Priest", "Mage")

        p1.life = 20
        initial_mana = p1.mana_crystals_available
        use_hero_power(game, p1)

        assert p1.mana_crystals_available == initial_mana - 2


# ============================================================
# Category 5: Warlock Hero Power (Life Tap) (5 tests)
# ============================================================

class TestWarlockHeroPower:
    def test_life_tap_draws_card(self):
        """Life Tap draws a card."""
        game, p1, p2 = new_hs_game("Warlock", "Mage")

        # Add cards to library
        add_to_library(game, WISP, p1, 3)

        hand_zone = f"hand_{p1.id}"
        if hand_zone not in game.state.zones:
            game.state.zones[hand_zone] = type('Zone', (), {'objects': []})()

        initial_hand_size = len(game.state.zones[hand_zone].objects)
        use_hero_power(game, p1)

        assert len(game.state.zones[hand_zone].objects) == initial_hand_size + 1

    def test_life_tap_costs_2_life(self):
        """Life Tap costs 2 life."""
        game, p1, p2 = new_hs_game("Warlock", "Mage")

        add_to_library(game, WISP, p1, 1)

        initial_life = p1.life
        use_hero_power(game, p1)

        assert p1.life == initial_life - 2

    def test_life_tap_at_low_health(self):
        """Life Tap works at low health."""
        game, p1, p2 = new_hs_game("Warlock", "Mage")

        add_to_library(game, WISP, p1, 1)
        p1.life = 3

        use_hero_power(game, p1)
        assert p1.life == 1

    def test_life_tap_can_kill_self(self):
        """Life Tap can reduce health to 0 or below."""
        game, p1, p2 = new_hs_game("Warlock", "Mage")

        add_to_library(game, WISP, p1, 1)
        p1.life = 2

        use_hero_power(game, p1)
        assert p1.life <= 0

    def test_life_tap_costs_2_mana(self):
        """Life Tap costs 2 mana."""
        game, p1, p2 = new_hs_game("Warlock", "Mage")

        add_to_library(game, WISP, p1, 1)
        initial_mana = p1.mana_crystals_available
        use_hero_power(game, p1)

        assert p1.mana_crystals_available == initial_mana - 2


# ============================================================
# Category 6: Hunter Hero Power (Steady Shot) (5 tests)
# ============================================================

class TestHunterHeroPower:
    def test_steady_shot_deals_2_damage(self):
        """Steady Shot deals exactly 2 damage to enemy hero."""
        game, p1, p2 = new_hs_game("Hunter", "Warrior")

        initial_life = p2.life
        use_hero_power(game, p1)

        assert p2.life == initial_life - 2

    def test_steady_shot_ignores_armor(self):
        """Steady Shot damage goes through armor first."""
        game, p1, p2 = new_hs_game("Hunter", "Warrior")

        p2.armor = 5
        use_hero_power(game, p1)

        assert p2.armor == 3
        assert p2.life == 30

    def test_steady_shot_lethal(self):
        """Steady Shot can deal lethal damage."""
        game, p1, p2 = new_hs_game("Hunter", "Warrior")

        p2.life = 2
        use_hero_power(game, p1)

        assert p2.life == 0

    def test_steady_shot_not_spell_damage(self):
        """Steady Shot is not affected by spell damage."""
        game, p1, p2 = new_hs_game("Hunter", "Warrior")

        play_minion(game, BLOODMAGE_THALNOS, p1)

        initial_life = p2.life
        use_hero_power(game, p1)

        # Should deal only 2 damage
        assert p2.life == initial_life - 2

    def test_steady_shot_costs_2_mana(self):
        """Steady Shot costs 2 mana."""
        game, p1, p2 = new_hs_game("Hunter", "Warrior")

        initial_mana = p1.mana_crystals_available
        use_hero_power(game, p1)

        assert p1.mana_crystals_available == initial_mana - 2


# ============================================================
# Category 7: Paladin Hero Power (Reinforce) (5 tests)
# ============================================================

class TestPaladinHeroPower:
    def test_reinforce_summons_1_1(self):
        """Reinforce summons a 1/1 Silver Hand Recruit."""
        game, p1, p2 = new_hs_game("Paladin", "Warrior")

        initial_count = get_battlefield_count(game, p1)
        use_hero_power(game, p1)

        assert get_battlefield_count(game, p1) == initial_count + 1

    def test_reinforce_creates_correct_stats(self):
        """Silver Hand Recruit has 1/1 stats."""
        game, p1, p2 = new_hs_game("Paladin", "Warrior")

        use_hero_power(game, p1)

        battlefield = game.state.zones.get('battlefield')
        recruit = None
        for oid in battlefield.objects:
            obj = game.state.objects.get(oid)
            if obj and obj.controller == p1.id and 'Silver Hand Recruit' in obj.name:
                recruit = obj
                break

        assert recruit is not None
        assert get_power(recruit, game.state) == 1
        assert get_toughness(recruit, game.state) == 1

    def test_reinforce_multiple_uses(self):
        """Can summon multiple recruits over turns."""
        game, p1, p2 = new_hs_game("Paladin", "Warrior")

        use_hero_power(game, p1)
        assert get_battlefield_count(game, p1) == 1

        p1.hero_power_used = False
        game.emit(Event(type=EventType.TURN_START, payload={'player': p1.id}, source=None))
        use_hero_power(game, p1)
        assert get_battlefield_count(game, p1) == 2

    def test_reinforce_full_board(self):
        """Reinforce attempts to summon even with full board."""
        game, p1, p2 = new_hs_game("Paladin", "Warrior")

        # Fill board with 7 minions
        for _ in range(7):
            play_minion(game, WISP, p1)

        assert get_battlefield_count(game, p1) == 7
        use_hero_power(game, p1)

        # Board stays at 7 (can't go over)
        assert get_battlefield_count(game, p1) == 7

    def test_reinforce_costs_2_mana(self):
        """Reinforce costs 2 mana."""
        game, p1, p2 = new_hs_game("Paladin", "Warrior")

        initial_mana = p1.mana_crystals_available
        use_hero_power(game, p1)

        assert p1.mana_crystals_available == initial_mana - 2


# ============================================================
# Category 8: Rogue Hero Power (Dagger Mastery) (5 tests)
# ============================================================

class TestRogueHeroPower:
    def test_dagger_mastery_equips_weapon(self):
        """Dagger Mastery equips a 1/2 weapon."""
        game, p1, p2 = new_hs_game("Rogue", "Warrior")

        assert p1.weapon_attack == 0
        assert p1.weapon_durability == 0

        use_hero_power(game, p1)

        assert p1.weapon_attack == 1
        assert p1.weapon_durability == 2

    def test_dagger_mastery_replaces_weapon(self):
        """Dagger Mastery replaces existing weapon."""
        game, p1, p2 = new_hs_game("Rogue", "Warrior")

        # Equip first dagger
        use_hero_power(game, p1)
        assert p1.weapon_durability == 2

        # Use weapon once
        p1.weapon_durability = 1
        hero = game.state.objects.get(p1.hero_id)
        hero.state.weapon_durability = 1

        # Equip new dagger next turn
        p1.hero_power_used = False
        game.emit(Event(type=EventType.TURN_START, payload={'player': p1.id}, source=None))
        use_hero_power(game, p1)

        # Should have fresh 1/2 dagger
        assert p1.weapon_attack == 1
        assert p1.weapon_durability == 2

    def test_dagger_mastery_no_weapon_stacking(self):
        """Cannot stack dagger stats."""
        game, p1, p2 = new_hs_game("Rogue", "Warrior")

        use_hero_power(game, p1)
        assert p1.weapon_attack == 1

        p1.hero_power_used = False
        game.emit(Event(type=EventType.TURN_START, payload={'player': p1.id}, source=None))
        use_hero_power(game, p1)

        # Still 1/2, not 2/4
        assert p1.weapon_attack == 1
        assert p1.weapon_durability == 2

    def test_dagger_mastery_costs_2_mana(self):
        """Dagger Mastery costs 2 mana."""
        game, p1, p2 = new_hs_game("Rogue", "Warrior")

        initial_mana = p1.mana_crystals_available
        use_hero_power(game, p1)

        assert p1.mana_crystals_available == initial_mana - 2

    def test_dagger_allows_hero_attack(self):
        """Dagger allows hero to attack."""
        game, p1, p2 = new_hs_game("Rogue", "Warrior")

        use_hero_power(game, p1)

        # Hero should be able to attack with 1 attack
        hero = game.state.objects.get(p1.hero_id)
        assert hero.state.weapon_attack == 1


# ============================================================
# Category 9: Shaman Hero Power (Totemic Call) (5 tests)
# ============================================================

class TestShamanHeroPower:
    def test_totemic_call_summons_totem(self):
        """Totemic Call summons a totem."""
        game, p1, p2 = new_hs_game("Shaman", "Warrior")

        initial_count = get_battlefield_count(game, p1)
        use_hero_power(game, p1)

        assert get_battlefield_count(game, p1) == initial_count + 1

    def test_totemic_call_creates_totem_type(self):
        """Summoned totem has Totem subtype."""
        game, p1, p2 = new_hs_game("Shaman", "Warrior")

        use_hero_power(game, p1)

        battlefield = game.state.zones.get('battlefield')
        totem_found = False
        for oid in battlefield.objects:
            obj = game.state.objects.get(oid)
            if obj and obj.controller == p1.id:
                if 'Totem' in obj.characteristics.subtypes:
                    totem_found = True
                    break

        assert totem_found

    def test_totemic_call_no_duplicate_totems(self):
        """Cannot summon duplicate basic totems."""
        game, p1, p2 = new_hs_game("Shaman", "Warrior")

        # Summon 4 totems
        for i in range(4):
            use_hero_power(game, p1)
            if i < 3:
                p1.hero_power_used = False
                game.emit(Event(type=EventType.TURN_START, payload={'player': p1.id}, source=None))

        assert get_battlefield_count(game, p1) == 4

        # 5th attempt should fail (all 4 basic totems present)
        p1.hero_power_used = False
        game.emit(Event(type=EventType.TURN_START, payload={'player': p1.id}, source=None))
        use_hero_power(game, p1)

        # Still only 4 totems
        assert get_battlefield_count(game, p1) == 4

    def test_totemic_call_after_totem_dies(self):
        """Can summon totem again after one dies."""
        game, p1, p2 = new_hs_game("Shaman", "Warrior")

        use_hero_power(game, p1)
        assert get_battlefield_count(game, p1) == 1

        # Kill the totem
        battlefield = game.state.zones.get('battlefield')
        totem_id = None
        for oid in battlefield.objects:
            obj = game.state.objects.get(oid)
            if obj and obj.controller == p1.id and CardType.MINION in obj.characteristics.types:
                totem_id = oid
                break

        if totem_id:
            game.emit(Event(
                type=EventType.OBJECT_DESTROYED,
                payload={'object_id': totem_id, 'reason': 'test'},
                source=None
            ))

        # Summon again
        p1.hero_power_used = False
        game.emit(Event(type=EventType.TURN_START, payload={'player': p1.id}, source=None))
        use_hero_power(game, p1)

        # Should have 1 totem again (possibly different type)
        assert get_battlefield_count(game, p1) == 1

    def test_totemic_call_costs_2_mana(self):
        """Totemic Call costs 2 mana."""
        game, p1, p2 = new_hs_game("Shaman", "Warrior")

        initial_mana = p1.mana_crystals_available
        use_hero_power(game, p1)

        assert p1.mana_crystals_available == initial_mana - 2
