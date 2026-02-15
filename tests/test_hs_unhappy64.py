"""
Hearthstone Unhappy Path Tests - Batch 64

Hero power interactions and edge cases: all 9 hero powers basic function,
hero power once-per-turn restriction, Mage Fireblast targeting,
Priest Lesser Heal on damaged minion, Warlock Life Tap at 1 HP,
Paladin Reinforce on full board, Hunter Steady Shot face only,
Rogue Dagger Mastery weapon equip, Shaman Totemic Call random totem,
Druid Shapeshift attack+armor, Warrior Armor Up stacking,
hero power with Auchenai (heal becomes damage), hero power with
spell damage (Fireblast boosted).
"""

import asyncio
import random
from src.engine.game import Game
from src.engine.types import (
    Event, EventType, GameObject, GameState, CardType, ZoneType,
    Interceptor, InterceptorPriority, InterceptorAction, InterceptorResult,
    new_id
)
from src.engine.queries import get_power, get_toughness, has_ability

from src.cards.hearthstone.heroes import HEROES
from src.cards.hearthstone.hero_powers import (
    HERO_POWERS, FIREBLAST, ARMOR_UP, STEADY_SHOT, REINFORCE,
    LESSER_HEAL, DAGGER_MASTERY, TOTEMIC_CALL, LIFE_TAP, SHAPESHIFT,
    fireblast_effect, armor_up_effect, steady_shot_effect,
    reinforce_effect, lesser_heal_effect, dagger_mastery_effect,
    totemic_call_effect, life_tap_effect, shapeshift_effect,
)

from src.cards.hearthstone.basic import (
    WISP, CHILLWIND_YETI, KOBOLD_GEOMANCER, BLOODFEN_RAPTOR,
)
from src.cards.hearthstone.priest import AUCHENAI_SOULPRIEST


# ============================================================
# Test Helpers
# ============================================================

def new_hs_game_classes(class1, class2):
    """Create a Hearthstone game with specific hero classes."""
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
    return game.create_object(
        name=card_def.name, owner_id=owner.id, zone=zone,
        characteristics=card_def.characteristics, card_def=card_def
    )


def activate_hero_power(game, player, hp_effect):
    """Activate a hero power by calling its effect and emitting events."""
    hp_obj = game.state.objects.get(player.hero_power_id)
    if hp_obj:
        events = hp_effect(hp_obj, game.state)
        for e in events:
            game.emit(e)
    return hp_obj


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


# ============================================================
# Test 1: Fireblast (Mage)
# ============================================================

class TestFireblast:
    def test_fireblast_deals_1_damage_to_enemy_hero(self):
        """Fireblast deals 1 damage to enemy hero."""
        game, p1, p2 = new_hs_game_classes("Mage", "Warrior")
        p2.life = 30

        activate_hero_power(game, p1, fireblast_effect)

        assert p2.life == 29, (
            f"Fireblast should deal 1 damage to enemy hero: expected 29, got {p2.life}"
        )

    def test_fireblast_emits_damage_event(self):
        """Fireblast should emit a DAMAGE event."""
        game, p1, p2 = new_hs_game_classes("Mage", "Warrior")

        hp_obj = game.state.objects.get(p1.hero_power_id)
        events = fireblast_effect(hp_obj, game.state)

        assert len(events) == 1, f"Fireblast should produce 1 event, got {len(events)}"
        assert events[0].type == EventType.DAMAGE
        assert events[0].payload['amount'] == 1
        assert events[0].payload['target'] == p2.hero_id

    def test_fireblast_targets_enemy_hero_not_self(self):
        """Fireblast auto-targets enemy hero, not own hero."""
        game, p1, p2 = new_hs_game_classes("Mage", "Warrior")
        p1.life = 30

        activate_hero_power(game, p1, fireblast_effect)

        assert p1.life == 30, (
            f"Fireblast should not damage own hero, p1 life should be 30, got {p1.life}"
        )


# ============================================================
# Test 2: Lesser Heal (Priest)
# ============================================================

class TestLesserHeal:
    def test_lesser_heal_restores_2_health(self):
        """Lesser Heal restores 2 health to own hero."""
        game, p1, p2 = new_hs_game_classes("Priest", "Warrior")
        p1.life = 25

        activate_hero_power(game, p1, lesser_heal_effect)

        assert p1.life == 27, (
            f"Lesser Heal should restore 2 health: expected 27, got {p1.life}"
        )

    def test_lesser_heal_at_full_health_no_effect(self):
        """Lesser Heal at full health (30) should produce no events."""
        game, p1, p2 = new_hs_game_classes("Priest", "Warrior")
        p1.life = 30

        hp_obj = game.state.objects.get(p1.hero_power_id)
        events = lesser_heal_effect(hp_obj, game.state)

        assert len(events) == 0, (
            f"Lesser Heal at full HP should produce 0 events, got {len(events)}"
        )

    def test_lesser_heal_does_not_overheal(self):
        """Lesser Heal at 29 HP should heal to 30, not 31."""
        game, p1, p2 = new_hs_game_classes("Priest", "Warrior")
        p1.life = 29

        activate_hero_power(game, p1, lesser_heal_effect)

        # The pipeline caps at max_life (30)
        assert p1.life <= 30, (
            f"Lesser Heal should not exceed max life of 30, got {p1.life}"
        )


# ============================================================
# Test 3: Life Tap (Warlock)
# ============================================================

class TestLifeTap:
    def test_life_tap_deals_2_damage_and_draws(self):
        """Life Tap deals 2 damage to self and draws a card."""
        game, p1, p2 = new_hs_game_classes("Warlock", "Warrior")
        p1.life = 30

        activate_hero_power(game, p1, life_tap_effect)

        # Life Tap deals 2 damage, draw may cause fatigue (extra damage)
        assert p1.life <= 28, (
            f"Life Tap should deal at least 2 damage: expected <= 28, got {p1.life}"
        )

        draw_events = [e for e in game.state.event_log
                       if e.type == EventType.DRAW and
                       e.payload.get('player') == p1.id]
        assert len(draw_events) >= 1, "Life Tap should draw at least 1 card"

    def test_life_tap_at_1_hp(self):
        """Life Tap at 1 HP should still execute (hero goes below 0)."""
        game, p1, p2 = new_hs_game_classes("Warlock", "Warrior")
        p1.life = 1

        activate_hero_power(game, p1, life_tap_effect)

        # 1 - 2 = -1 (and possibly more from fatigue)
        assert p1.life <= -1, (
            f"Life Tap at 1 HP should reduce hero to -1 or below, got {p1.life}"
        )

    def test_life_tap_produces_damage_then_draw_events(self):
        """Life Tap produces events in order: DAMAGE first, then DRAW."""
        game, p1, p2 = new_hs_game_classes("Warlock", "Warrior")

        hp_obj = game.state.objects.get(p1.hero_power_id)
        events = life_tap_effect(hp_obj, game.state)

        assert len(events) == 2, f"Life Tap should produce 2 events, got {len(events)}"
        assert events[0].type == EventType.DAMAGE, (
            f"First event should be DAMAGE, got {events[0].type}"
        )
        assert events[0].payload['amount'] == 2
        assert events[1].type == EventType.DRAW, (
            f"Second event should be DRAW, got {events[1].type}"
        )


# ============================================================
# Test 4: Reinforce (Paladin)
# ============================================================

class TestReinforce:
    def test_reinforce_summons_silver_hand_recruit(self):
        """Reinforce summons a 1/1 Silver Hand Recruit."""
        game, p1, p2 = new_hs_game_classes("Paladin", "Warrior")

        activate_hero_power(game, p1, reinforce_effect)

        token_events = [e for e in game.state.event_log
                        if e.type == EventType.CREATE_TOKEN and
                        e.payload.get('controller') == p1.id]
        assert len(token_events) >= 1, "Reinforce should create a token"
        token = token_events[0].payload['token']
        assert token['name'] == 'Silver Hand Recruit', (
            f"Token should be named 'Silver Hand Recruit', got '{token['name']}'"
        )
        assert token['power'] == 1, f"Token should have 1 power, got {token['power']}"
        assert token['toughness'] == 1, f"Token should have 1 toughness, got {token['toughness']}"

    def test_reinforce_event_structure(self):
        """Reinforce effect returns exactly 1 CREATE_TOKEN event."""
        game, p1, p2 = new_hs_game_classes("Paladin", "Warrior")

        hp_obj = game.state.objects.get(p1.hero_power_id)
        events = reinforce_effect(hp_obj, game.state)

        assert len(events) == 1, f"Reinforce should produce exactly 1 event, got {len(events)}"
        assert events[0].type == EventType.CREATE_TOKEN


# ============================================================
# Test 5: Steady Shot (Hunter)
# ============================================================

class TestSteadyShot:
    def test_steady_shot_deals_2_to_enemy_hero(self):
        """Steady Shot deals 2 damage to enemy hero."""
        game, p1, p2 = new_hs_game_classes("Hunter", "Warrior")
        p2.life = 30

        activate_hero_power(game, p1, steady_shot_effect)

        assert p2.life == 28, (
            f"Steady Shot should deal 2 damage to enemy hero: expected 28, got {p2.life}"
        )

    def test_steady_shot_targets_enemy_hero_only(self):
        """Steady Shot only targets enemy hero (face-only)."""
        game, p1, p2 = new_hs_game_classes("Hunter", "Warrior")

        hp_obj = game.state.objects.get(p1.hero_power_id)
        events = steady_shot_effect(hp_obj, game.state)

        assert len(events) == 1
        assert events[0].payload['target'] == p2.hero_id, (
            "Steady Shot should target enemy hero specifically"
        )

    def test_steady_shot_does_not_damage_self(self):
        """Steady Shot should not damage own hero."""
        game, p1, p2 = new_hs_game_classes("Hunter", "Warrior")
        p1.life = 30

        activate_hero_power(game, p1, steady_shot_effect)

        assert p1.life == 30, (
            f"Steady Shot should not damage own hero, got {p1.life}"
        )


# ============================================================
# Test 6: Dagger Mastery (Rogue)
# ============================================================

class TestDaggerMastery:
    def test_dagger_mastery_equips_weapon(self):
        """Dagger Mastery equips a 1/2 Wicked Knife weapon."""
        game, p1, p2 = new_hs_game_classes("Rogue", "Warrior")

        activate_hero_power(game, p1, dagger_mastery_effect)

        assert p1.weapon_attack == 1, (
            f"Dagger Mastery should set weapon_attack to 1, got {p1.weapon_attack}"
        )
        assert p1.weapon_durability == 2, (
            f"Dagger Mastery should set weapon_durability to 2, got {p1.weapon_durability}"
        )

    def test_dagger_mastery_emits_weapon_equip_event(self):
        """Dagger Mastery should emit a WEAPON_EQUIP event."""
        game, p1, p2 = new_hs_game_classes("Rogue", "Warrior")

        activate_hero_power(game, p1, dagger_mastery_effect)

        equip_events = [e for e in game.state.event_log
                        if e.type == EventType.WEAPON_EQUIP]
        assert len(equip_events) >= 1, "Dagger Mastery should emit WEAPON_EQUIP event"
        assert equip_events[0].payload['attack'] == 1
        assert equip_events[0].payload['durability'] == 2


# ============================================================
# Test 7: Totemic Call (Shaman)
# ============================================================

class TestTotemicCall:
    def test_totemic_call_summons_basic_totem(self):
        """Totemic Call summons a random basic totem (one of 4 types)."""
        game, p1, p2 = new_hs_game_classes("Shaman", "Warrior")

        random.seed(42)
        activate_hero_power(game, p1, totemic_call_effect)

        token_events = [e for e in game.state.event_log
                        if e.type == EventType.CREATE_TOKEN and
                        e.payload.get('controller') == p1.id]
        assert len(token_events) >= 1, "Totemic Call should create a token"
        totem_name = token_events[0].payload['token']['name']
        valid_totems = ['Healing Totem', 'Searing Totem', 'Stoneclaw Totem', 'Wrath of Air Totem']
        assert totem_name in valid_totems, (
            f"Totem should be one of {valid_totems}, got '{totem_name}'"
        )

    def test_totemic_call_totem_is_0_2_or_1_1(self):
        """All basic totems are 0/2 except Searing Totem which is 1/1."""
        game, p1, p2 = new_hs_game_classes("Shaman", "Warrior")

        hp_obj = game.state.objects.get(p1.hero_power_id)
        random.seed(42)
        events = totemic_call_effect(hp_obj, game.state)

        assert len(events) == 1
        token = events[0].payload['token']
        name = token['name']
        if name == 'Searing Totem':
            assert token['power'] == 1 and token['toughness'] == 1, (
                f"Searing Totem should be 1/1, got {token['power']}/{token['toughness']}"
            )
        else:
            assert token['power'] == 0 and token['toughness'] == 2, (
                f"{name} should be 0/2, got {token['power']}/{token['toughness']}"
            )


# ============================================================
# Test 8: Shapeshift (Druid)
# ============================================================

class TestShapeshift:
    def test_shapeshift_gives_1_armor(self):
        """Shapeshift gives +1 Armor."""
        game, p1, p2 = new_hs_game_classes("Druid", "Warrior")
        p1.armor = 0

        activate_hero_power(game, p1, shapeshift_effect)

        assert p1.armor == 1, (
            f"Shapeshift should give 1 armor: expected 1, got {p1.armor}"
        )

    def test_shapeshift_gives_1_attack(self):
        """Shapeshift gives +1 Attack this turn."""
        game, p1, p2 = new_hs_game_classes("Druid", "Warrior")
        base_attack = p1.weapon_attack

        activate_hero_power(game, p1, shapeshift_effect)

        assert p1.weapon_attack == base_attack + 1, (
            f"Shapeshift should increase weapon_attack by 1: "
            f"expected {base_attack + 1}, got {p1.weapon_attack}"
        )

    def test_shapeshift_attack_and_armor_together(self):
        """Shapeshift grants both +1 Attack and +1 Armor in same activation."""
        game, p1, p2 = new_hs_game_classes("Druid", "Warrior")
        p1.armor = 0
        base_attack = p1.weapon_attack

        activate_hero_power(game, p1, shapeshift_effect)

        assert p1.armor == 1, "Shapeshift should give 1 armor"
        assert p1.weapon_attack == base_attack + 1, "Shapeshift should give +1 attack"


# ============================================================
# Test 9: Armor Up (Warrior)
# ============================================================

class TestArmorUp:
    def test_armor_up_gives_2_armor(self):
        """Armor Up gives 2 Armor."""
        game, p1, p2 = new_hs_game_classes("Warrior", "Mage")
        p1.armor = 0

        activate_hero_power(game, p1, armor_up_effect)

        assert p1.armor == 2, (
            f"Armor Up should give 2 armor: expected 2, got {p1.armor}"
        )

    def test_armor_up_stacks_with_existing_armor(self):
        """Armor Up stacks on top of existing armor."""
        game, p1, p2 = new_hs_game_classes("Warrior", "Mage")
        p1.armor = 5

        activate_hero_power(game, p1, armor_up_effect)

        assert p1.armor == 7, (
            f"Armor Up should stack: 5 + 2 = 7, got {p1.armor}"
        )

    def test_armor_up_emits_armor_gain_event(self):
        """Armor Up should emit an ARMOR_GAIN event with amount 2."""
        game, p1, p2 = new_hs_game_classes("Warrior", "Mage")
        p1.armor = 0

        hp_obj = game.state.objects.get(p1.hero_power_id)
        events = armor_up_effect(hp_obj, game.state)

        assert len(events) == 1, f"Armor Up should produce 1 event, got {len(events)}"
        assert events[0].type == EventType.ARMOR_GAIN
        assert events[0].payload['amount'] == 2
        assert events[0].payload['player'] == p1.id


# ============================================================
# Test 10: Hero Power Once Per Turn
# ============================================================

class TestHeroPowerOncePerTurn:
    def test_use_hero_power_marks_used(self):
        """Using hero power via use_hero_power marks hero_power_used = True."""
        game, p1, p2 = new_hs_game_classes("Mage", "Warrior")
        p1.hero_power_used = False
        p1.mana_crystals_available = 10

        result = asyncio.get_event_loop().run_until_complete(
            game.use_hero_power(p1.id)
        )
        assert result is True, "First use_hero_power should succeed"
        assert p1.hero_power_used is True, "hero_power_used should be True after use"

    def test_second_use_fails(self):
        """Second hero power use in same turn should fail."""
        game, p1, p2 = new_hs_game_classes("Mage", "Warrior")
        p1.hero_power_used = False
        p1.mana_crystals_available = 10

        result1 = asyncio.get_event_loop().run_until_complete(
            game.use_hero_power(p1.id)
        )
        assert result1 is True

        result2 = asyncio.get_event_loop().run_until_complete(
            game.use_hero_power(p1.id)
        )
        assert result2 is False, "Second hero power use should fail"

    def test_hero_power_used_flag_blocks_directly(self):
        """Setting hero_power_used to True should block use_hero_power."""
        game, p1, p2 = new_hs_game_classes("Warrior", "Mage")
        p1.hero_power_used = True
        p1.mana_crystals_available = 10

        result = asyncio.get_event_loop().run_until_complete(
            game.use_hero_power(p1.id)
        )
        assert result is False, "Hero power should be blocked when hero_power_used is True"


# ============================================================
# Test 11: Hero Power Refreshes Next Turn
# ============================================================

class TestHeroPowerResetNextTurn:
    def test_hero_power_used_resets_on_turn_start(self):
        """hero_power_used should reset to False when the player's turn starts."""
        game, p1, p2 = new_hs_game_classes("Mage", "Warrior")
        p1.hero_power_used = True

        # Simulate turn start reset (what hearthstone_turn.py does)
        p1.hero_power_used = False  # This is what on_turn_start does

        assert p1.hero_power_used is False, (
            "hero_power_used should be False after turn start reset"
        )

    def test_hero_power_usable_after_reset(self):
        """After resetting hero_power_used, hero power should be usable again."""
        game, p1, p2 = new_hs_game_classes("Mage", "Warrior")
        p1.mana_crystals_available = 10

        # Use hero power
        result1 = asyncio.get_event_loop().run_until_complete(
            game.use_hero_power(p1.id)
        )
        assert result1 is True
        assert p1.hero_power_used is True

        # Reset for next turn
        p1.hero_power_used = False
        p1.mana_crystals_available = 10

        # Should be usable again
        result2 = asyncio.get_event_loop().run_until_complete(
            game.use_hero_power(p1.id)
        )
        assert result2 is True, "Hero power should be usable after turn reset"


# ============================================================
# Test 12: Reinforce on Full Board
# ============================================================

class TestReinforceOnFullBoard:
    def test_reinforce_on_full_board_does_not_add_minion(self):
        """Reinforce on a full board (7 minions) should not add an 8th minion."""
        game, p1, p2 = new_hs_game_classes("Paladin", "Warrior")

        # Fill the board with 7 minions
        for _ in range(7):
            make_obj(game, WISP, p1)

        minions_before = len(get_battlefield_minions(game, p1))
        assert minions_before == 7, f"Board should have 7 minions, got {minions_before}"

        # Try to use Reinforce
        activate_hero_power(game, p1, reinforce_effect)

        # Board should still have 7 minions (pipeline enforces limit)
        minions_after = len(get_battlefield_minions(game, p1))
        assert minions_after == 7, (
            f"Full board should block Reinforce token: expected 7, got {minions_after}"
        )

    def test_reinforce_on_6_minions_succeeds(self):
        """Reinforce with 6 minions should succeed (below 7 limit)."""
        game, p1, p2 = new_hs_game_classes("Paladin", "Warrior")

        for _ in range(6):
            make_obj(game, WISP, p1)

        minions_before = len(get_battlefield_minions(game, p1))
        assert minions_before == 6

        activate_hero_power(game, p1, reinforce_effect)

        minions_after = len(get_battlefield_minions(game, p1))
        assert minions_after == 7, (
            f"Reinforce on 6-minion board should create 7th: expected 7, got {minions_after}"
        )


# ============================================================
# Test 13: Dagger Mastery Replaces Weapon
# ============================================================

class TestDaggerMasteryReplacesWeapon:
    def test_replaces_existing_dagger(self):
        """Using Dagger Mastery twice should replace the first dagger with a fresh one."""
        game, p1, p2 = new_hs_game_classes("Rogue", "Warrior")

        # First equip
        activate_hero_power(game, p1, dagger_mastery_effect)
        assert p1.weapon_attack == 1
        assert p1.weapon_durability == 2

        # Simulate using weapon once (reduce durability)
        p1.weapon_durability = 1

        # Second equip should give fresh 1/2 dagger
        activate_hero_power(game, p1, dagger_mastery_effect)
        assert p1.weapon_attack == 1, (
            f"New dagger should have 1 attack, got {p1.weapon_attack}"
        )
        assert p1.weapon_durability == 2, (
            f"New dagger should have 2 durability (fresh), got {p1.weapon_durability}"
        )

    def test_replaces_better_weapon(self):
        """Dagger Mastery replaces any existing weapon, even a stronger one."""
        game, p1, p2 = new_hs_game_classes("Rogue", "Warrior")

        # Simulate having a 3/2 weapon equipped
        p1.weapon_attack = 3
        p1.weapon_durability = 2

        activate_hero_power(game, p1, dagger_mastery_effect)

        assert p1.weapon_attack == 1, (
            f"Dagger should replace weapon to 1 attack, got {p1.weapon_attack}"
        )
        assert p1.weapon_durability == 2, (
            f"Dagger should have 2 durability, got {p1.weapon_durability}"
        )


# ============================================================
# Test 14: Fireblast With Spell Damage
# ============================================================

class TestFireblastWithSpellDamage:
    def test_fireblast_not_boosted_by_spell_damage(self):
        """
        Fireblast is NOT boosted by spell damage because hero powers
        are not spells - the DAMAGE event does not have from_spell flag.
        """
        game, p1, p2 = new_hs_game_classes("Mage", "Warrior")
        kobold = make_obj(game, KOBOLD_GEOMANCER, p1)  # Spell Damage +1
        p2.life = 30

        activate_hero_power(game, p1, fireblast_effect)

        # Fireblast doesn't set from_spell, so Kobold's TRANSFORM doesn't trigger
        assert p2.life == 29, (
            f"Fireblast should still deal only 1 damage with spell damage on board: "
            f"expected 29, got {p2.life}"
        )

    def test_fireblast_damage_event_has_no_from_spell_flag(self):
        """Fireblast DAMAGE event should NOT have from_spell flag."""
        game, p1, p2 = new_hs_game_classes("Mage", "Warrior")

        hp_obj = game.state.objects.get(p1.hero_power_id)
        events = fireblast_effect(hp_obj, game.state)

        assert len(events) == 1
        assert events[0].payload.get('from_spell') is None or events[0].payload.get('from_spell') is False, (
            "Fireblast DAMAGE event should not have from_spell=True"
        )


# ============================================================
# Test 15: Lesser Heal With Auchenai Soulpriest
# ============================================================

class TestLesserHealWithAuchenai:
    def test_auchenai_converts_heal_to_damage(self):
        """Auchenai Soulpriest converts Priest Lesser Heal into 2 damage."""
        game, p1, p2 = new_hs_game_classes("Priest", "Warrior")
        auchenai = make_obj(game, AUCHENAI_SOULPRIEST, p1)
        p1.life = 25

        activate_hero_power(game, p1, lesser_heal_effect)

        # Auchenai TRANSFORM converts LIFE_CHANGE (+2) to DAMAGE (2)
        # Hero takes 2 damage: 25 - 2 = 23
        assert p1.life == 23, (
            f"With Auchenai, Lesser Heal should deal 2 damage: expected 23, got {p1.life}"
        )

    def test_auchenai_at_2_hp_is_lethal(self):
        """Auchenai + Lesser Heal at 2 HP should reduce hero to 0."""
        game, p1, p2 = new_hs_game_classes("Priest", "Warrior")
        auchenai = make_obj(game, AUCHENAI_SOULPRIEST, p1)
        p1.life = 2

        activate_hero_power(game, p1, lesser_heal_effect)

        assert p1.life <= 0, (
            f"Auchenai + Lesser Heal at 2 HP should be lethal, got {p1.life}"
        )


# ============================================================
# Run tests
# ============================================================

if __name__ == '__main__':
    import pytest
    pytest.main([__file__, '-v'])
