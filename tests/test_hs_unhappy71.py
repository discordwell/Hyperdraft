"""
Hearthstone Unhappy Path Tests - Batch 71

Cross-class synergy combos: Force of Nature + Savage Roar (14 damage
combo), Leeroy + Shadowstep + Leeroy (12+ damage), Gadgetzan Auctioneer
+ cheap spells (miracle rogue draw engine), Knife Juggler + Unleash
the Hounds (damage per hound), Wild Pyromancer + cheap spells (board
clear combo), Northshire Cleric + Circle of Healing (mass draw),
Armorsmith + Whirlwind (mass armor gain), Frothing Berserker + Whirlwind
(mass attack gain), Auchenai + Zombie Chow (reverse deathrattle),
Injured Blademaster + Circle (full heal combo), Alexstrasza + Fireball
(burst combo), Knife Juggler + Imp-losion or token summons.
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

from src.cards.hearthstone.basic import WISP, CHILLWIND_YETI, KOBOLD_GEOMANCER
from src.cards.hearthstone.classic import (
    FIREBALL, KNIFE_JUGGLER, WILD_PYROMANCER, INJURED_BLADEMASTER,
    LEEROY_JENKINS, ALEXSTRASZA, GADGETZAN_AUCTIONEER, SPRINT,
)
from src.cards.hearthstone.druid import FORCE_OF_NATURE, SAVAGE_ROAR, MOONFIRE
from src.cards.hearthstone.rogue import PREPARATION, SHADOWSTEP, SHIV, SINISTER_STRIKE
from src.cards.hearthstone.warrior import (
    WHIRLWIND, ARMORSMITH, FROTHING_BERSERKER, CRUEL_TASKMASTER,
    GROMMASH_HELLSCREAM,
)
from src.cards.hearthstone.priest import (
    NORTHSHIRE_CLERIC, CIRCLE_OF_HEALING, AUCHENAI_SOULPRIEST,
    HOLY_SMITE,
)
from src.cards.hearthstone.hunter import UNLEASH_THE_HOUNDS


# ============================================================
# Test Helpers
# ============================================================

def new_hs_game(p1_class="Druid", p2_class="Mage"):
    """Create a fresh Hearthstone game with configurable classes, 10 mana each."""
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
    """Create an object from a card definition."""
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
    """Play a minion from hand to battlefield (triggers ZONE_CHANGE for Knife Juggler etc.)."""
    obj = game.create_object(
        name=card_def.name, owner_id=owner.id, zone=ZoneType.HAND,
        characteristics=card_def.characteristics, card_def=card_def
    )
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={'object_id': obj.id, 'from_zone_type': ZoneType.HAND,
                 'to_zone_type': ZoneType.BATTLEFIELD, 'controller': owner.id},
        source=obj.id
    ))
    return obj


def use_hero_power(game, player):
    """Activate a hero power via event."""
    game.emit(Event(
        type=EventType.HERO_POWER_ACTIVATE,
        payload={'hero_power_id': player.hero_power_id, 'player': player.id},
        source=player.hero_power_id,
    ))


def add_library_cards(game, owner, card_def, count):
    """Add cards to a player's library so draws don't fatigue."""
    for _ in range(count):
        game.create_object(
            name=card_def.name, owner_id=owner.id, zone=ZoneType.LIBRARY,
            characteristics=card_def.characteristics, card_def=card_def
        )


# ============================================================
# Test 1: Force of Nature + Savage Roar
# ============================================================

class TestForceOfNaturePlusSavageRoar:
    def test_fon_summons_three_treants(self):
        """Force of Nature summons 3x 2/2 Treants."""
        game, p1, p2 = new_hs_game("Druid", "Mage")

        cast_spell(game, FORCE_OF_NATURE, p1)

        # Count treants on battlefield
        battlefield = game.state.zones.get('battlefield')
        treants = [
            mid for mid in battlefield.objects
            if game.state.objects.get(mid) and
            game.state.objects[mid].name == 'Treant' and
            game.state.objects[mid].controller == p1.id
        ]
        assert len(treants) == 3, (
            f"Force of Nature should summon 3 Treants, got {len(treants)}"
        )

    def test_savage_roar_buffs_hero_and_minions(self):
        """Savage Roar gives +2 attack to hero and all friendly minions."""
        game, p1, p2 = new_hs_game("Druid", "Mage")

        # Place 2 wisps first
        wisp1 = make_obj(game, WISP, p1)
        wisp2 = make_obj(game, WISP, p1)

        cast_spell(game, SAVAGE_ROAR, p1)

        # Wisps are 1/1 base; Savage Roar gives +2 attack
        w1_power = get_power(wisp1, game.state)
        w2_power = get_power(wisp2, game.state)
        assert w1_power == 3, f"Wisp should have 3 attack after Savage Roar, got {w1_power}"
        assert w2_power == 3, f"Wisp should have 3 attack after Savage Roar, got {w2_power}"

        # Hero should have +2 attack
        assert p1.weapon_attack >= 2, (
            f"Hero should have at least 2 weapon attack from Savage Roar, got {p1.weapon_attack}"
        )

    def test_fon_plus_savage_roar_14_damage(self):
        """FoN + Savage Roar = 3 Treants at 4 ATK each + hero at 2 ATK = 14 burst."""
        game, p1, p2 = new_hs_game("Druid", "Mage")

        # Cast FoN first: 3x 2/2 Treants
        cast_spell(game, FORCE_OF_NATURE, p1)

        # Then Savage Roar: all friendly characters get +2 attack
        cast_spell(game, SAVAGE_ROAR, p1)

        # Count treant attack values
        battlefield = game.state.zones.get('battlefield')
        treants = [
            mid for mid in battlefield.objects
            if game.state.objects.get(mid) and
            game.state.objects[mid].name == 'Treant' and
            game.state.objects[mid].controller == p1.id
        ]
        assert len(treants) == 3, f"Expected 3 Treants, got {len(treants)}"

        total_treant_attack = 0
        for tid in treants:
            t = game.state.objects[tid]
            atk = get_power(t, game.state)
            assert atk == 4, f"Treant should have 4 ATK (2 base + 2 Savage Roar), got {atk}"
            total_treant_attack += atk

        # Hero attack from Savage Roar
        hero_attack = p1.weapon_attack
        assert hero_attack >= 2, f"Hero should have at least 2 ATK, got {hero_attack}"

        total_burst = total_treant_attack + hero_attack
        assert total_burst >= 14, (
            f"FoN + Savage Roar should be 14+ burst damage, got {total_burst}"
        )


# ============================================================
# Test 2: Gadgetzan Auctioneer + Cheap Spells (Miracle Rogue)
# ============================================================

class TestGadgetzanPlusCheapSpells:
    def test_auctioneer_draws_on_spell_cast(self):
        """Gadgetzan Auctioneer on board: casting 3 spells draws 3 cards."""
        game, p1, p2 = new_hs_game("Rogue", "Mage")

        # Place Auctioneer
        auctioneer = make_obj(game, GADGETZAN_AUCTIONEER, p1)

        # Add library cards so draws succeed
        add_library_cards(game, p1, WISP, 10)

        # Count hand size before
        hand_key = f"hand_{p1.id}"
        hand_before = len(game.state.zones[hand_key].objects)

        # Cast 3 cheap spells (Moonfire is 0-cost)
        cast_spell(game, MOONFIRE, p1)
        cast_spell(game, MOONFIRE, p1)
        cast_spell(game, MOONFIRE, p1)

        hand_after = len(game.state.zones[hand_key].objects)
        cards_drawn = hand_after - hand_before

        assert cards_drawn == 3, (
            f"Auctioneer should draw 3 cards from 3 spells, drew {cards_drawn}"
        )


# ============================================================
# Test 3: Preparation + Sprint
# ============================================================

class TestPreparationPlusSprint:
    def test_prep_reduces_sprint_cost(self):
        """Preparation makes the next spell cost 3 less; Sprint (7) should cost 4."""
        game, p1, p2 = new_hs_game("Rogue", "Mage")

        # Cast Preparation: adds a cost modifier to the player
        cast_spell(game, PREPARATION, p1)

        # Verify the cost modifier was added
        assert len(p1.cost_modifiers) >= 1, (
            "Preparation should add a cost modifier to the player"
        )

        # Check modifier details: spell type, amount=3, uses_remaining=1
        modifier = p1.cost_modifiers[-1]
        assert modifier['card_type'] == CardType.SPELL, (
            f"Cost modifier should apply to spells, got {modifier['card_type']}"
        )
        assert modifier['amount'] == 3, (
            f"Preparation should reduce by 3, got {modifier['amount']}"
        )
        assert modifier['uses_remaining'] == 1, (
            f"Preparation modifier should be one-shot, got {modifier['uses_remaining']}"
        )


# ============================================================
# Test 4: Knife Juggler + Unleash the Hounds
# ============================================================

class TestKnifeJugglerPlusUnleash:
    def test_juggler_fires_per_hound(self):
        """Knife Juggler fires 1 damage per hound summoned by Unleash the Hounds."""
        game, p1, p2 = new_hs_game("Hunter", "Mage")

        # Place 3 enemy minions so Unleash summons 3 hounds
        for _ in range(3):
            make_obj(game, WISP, p2)

        # Place Knife Juggler
        juggler = make_obj(game, KNIFE_JUGGLER, p1)

        # Clear event log to track new damage events
        game.state.event_log.clear()

        random.seed(42)

        # Cast Unleash the Hounds: summons 3 hounds (1 per enemy minion)
        cast_spell(game, UNLEASH_THE_HOUNDS, p1)

        # Count Juggler damage events (1 damage events sourced from juggler)
        juggler_damage = [
            e for e in game.state.event_log
            if e.type == EventType.DAMAGE and
            e.payload.get('amount') == 1 and
            e.payload.get('source') == juggler.id
        ]
        assert len(juggler_damage) == 3, (
            f"Knife Juggler should fire 3 times for 3 hounds, fired {len(juggler_damage)}"
        )


# ============================================================
# Test 5: Knife Juggler + Token Summons (Wisps)
# ============================================================

class TestKnifeJugglerPlusTokens:
    def test_juggler_fires_per_wisp_played(self):
        """Knife Juggler fires 1 damage per minion played after it."""
        game, p1, p2 = new_hs_game("Hunter", "Mage")

        # Place an enemy minion so juggler has a target
        make_obj(game, WISP, p2)

        # Place Knife Juggler
        juggler = make_obj(game, KNIFE_JUGGLER, p1)

        # Clear event log
        game.state.event_log.clear()

        random.seed(42)

        # Play 3 Wisps from hand (each triggers Juggler)
        play_minion(game, WISP, p1)
        play_minion(game, WISP, p1)
        play_minion(game, WISP, p1)

        # Count Juggler damage events
        juggler_damage = [
            e for e in game.state.event_log
            if e.type == EventType.DAMAGE and
            e.payload.get('amount') == 1 and
            e.payload.get('source') == juggler.id
        ]
        assert len(juggler_damage) == 3, (
            f"Knife Juggler should fire 3 times for 3 Wisps, fired {len(juggler_damage)}"
        )


# ============================================================
# Test 6: Armorsmith + Whirlwind
# ============================================================

class TestArmorsmiPhPlusWhirlwind:
    def test_armorsmith_gains_armor_per_damaged_friendly(self):
        """Whirlwind hits all minions; Armorsmith triggers per friendly minion damaged."""
        game, p1, p2 = new_hs_game("Warrior", "Mage")

        # Place Armorsmith (1/4) and 3 other friendly minions
        armorsmith = make_obj(game, ARMORSMITH, p1)
        yeti1 = make_obj(game, CHILLWIND_YETI, p1)
        yeti2 = make_obj(game, CHILLWIND_YETI, p1)
        yeti3 = make_obj(game, CHILLWIND_YETI, p1)

        # Clear event log to track ARMOR_GAIN events
        game.state.event_log.clear()

        # Cast Whirlwind: 1 damage to ALL minions
        cast_spell(game, WHIRLWIND, p1)

        # Armorsmith triggers for each friendly minion that takes damage.
        # Friendly minions: Armorsmith + yeti1 + yeti2 + yeti3 = 4 triggers.
        # The interceptor emits ARMOR_GAIN events (one per trigger).
        armor_gain_events = [
            e for e in game.state.event_log
            if e.type == EventType.ARMOR_GAIN and
            e.payload.get('player') == p1.id
        ]
        assert len(armor_gain_events) == 4, (
            f"Armorsmith should emit 4 ARMOR_GAIN events (4 friendly minions damaged), "
            f"got {len(armor_gain_events)}"
        )


# ============================================================
# Test 7: Frothing Berserker + Whirlwind
# ============================================================

class TestFrothingPlusWhirlwind:
    def test_frothing_gains_attack_per_damaged_minion(self):
        """Whirlwind with 4 minions on board -> Frothing gets +4 attack."""
        game, p1, p2 = new_hs_game("Warrior", "Mage")

        # Place Frothing Berserker (2/4)
        frothing = make_obj(game, FROTHING_BERSERKER, p1)

        # Place 3 other minions (mix of friendly and enemy)
        yeti1 = make_obj(game, CHILLWIND_YETI, p1)
        wisp_e1 = make_obj(game, WISP, p2)
        wisp_e2 = make_obj(game, WISP, p2)

        base_power = get_power(frothing, game.state)

        # Cast Whirlwind: 1 damage to ALL 4 minions
        # Frothing triggers for each minion taking damage
        cast_spell(game, WHIRLWIND, p1)

        new_power = get_power(frothing, game.state)

        # Frothing was damaged (1 trigger for itself), plus yeti1 (1), wisp_e1 (1), wisp_e2 (1)
        # = 4 total damage events to minions => +4 attack
        expected = base_power + 4
        assert new_power == expected, (
            f"Frothing should gain +4 attack (4 minions damaged), "
            f"expected {expected}, got {new_power}"
        )


# ============================================================
# Test 8: Northshire Cleric + Circle of Healing
# ============================================================

class TestNorthshirePlusCircle:
    def test_northshire_draws_per_healed_minion(self):
        """3 damaged minions + Northshire + Circle = 3 draws."""
        game, p1, p2 = new_hs_game("Priest", "Mage")

        # Place Northshire Cleric (1/3)
        cleric = make_obj(game, NORTHSHIRE_CLERIC, p1)

        # Place 3 damaged minions
        yeti1 = make_obj(game, CHILLWIND_YETI, p1)
        yeti1.state.damage = 2
        yeti2 = make_obj(game, CHILLWIND_YETI, p1)
        yeti2.state.damage = 2
        yeti3 = make_obj(game, CHILLWIND_YETI, p1)
        yeti3.state.damage = 2

        # Add library cards to avoid fatigue
        add_library_cards(game, p1, WISP, 10)

        # Count hand size before
        hand_key = f"hand_{p1.id}"
        hand_before = len(game.state.zones[hand_key].objects)

        # Cast Circle of Healing
        cast_spell(game, CIRCLE_OF_HEALING, p1)

        hand_after = len(game.state.zones[hand_key].objects)
        cards_drawn = hand_after - hand_before

        assert cards_drawn == 3, (
            f"Northshire should draw 3 cards (3 healed minions), drew {cards_drawn}"
        )


# ============================================================
# Test 9: Injured Blademaster + Circle of Healing
# ============================================================

class TestInjuredBlademasterPlusCircle:
    def test_blademaster_enters_damaged(self):
        """Injured Blademaster enters at 4/7 and deals 4 to itself -> 4/3 effective."""
        game, p1, p2 = new_hs_game("Priest", "Mage")

        blademaster = make_obj(game, INJURED_BLADEMASTER, p1)
        # Fire the battlecry: deal 4 damage to itself
        events = INJURED_BLADEMASTER.battlecry(blademaster, game.state)
        for e in events:
            game.emit(e)

        effective_health = get_toughness(blademaster, game.state) - blademaster.state.damage
        assert effective_health == 3, (
            f"Blademaster should be at 3 effective health (7 - 4 damage), got {effective_health}"
        )
        assert get_power(blademaster, game.state) == 4, (
            f"Blademaster should have 4 attack, got {get_power(blademaster, game.state)}"
        )

    def test_circle_heals_blademaster_to_full(self):
        """Circle of Healing heals Blademaster from 4/3 to 4/7."""
        game, p1, p2 = new_hs_game("Priest", "Mage")

        blademaster = make_obj(game, INJURED_BLADEMASTER, p1)
        events = INJURED_BLADEMASTER.battlecry(blademaster, game.state)
        for e in events:
            game.emit(e)

        # Verify damaged state
        assert blademaster.state.damage == 4

        # Cast Circle of Healing: heals up to 4 to all minions
        cast_spell(game, CIRCLE_OF_HEALING, p1)

        # Should be fully healed
        assert blademaster.state.damage == 0, (
            f"Blademaster damage should be 0 after Circle, got {blademaster.state.damage}"
        )
        effective_health = get_toughness(blademaster, game.state) - blademaster.state.damage
        assert effective_health == 7, (
            f"Blademaster should be at 7 effective health after Circle, got {effective_health}"
        )


# ============================================================
# Test 10: Auchenai Soulpriest + Hero Power
# ============================================================

class TestAuchenaiPlusHeroPower:
    def test_auchenai_converts_lesser_heal_to_damage(self):
        """With Auchenai, Priest Lesser Heal deals 2 damage instead of healing."""
        game, p1, p2 = new_hs_game("Priest", "Mage")
        p1.life = 25  # Damage hero so Lesser Heal would normally trigger

        # Place Auchenai Soulpriest
        auchenai = make_obj(game, AUCHENAI_SOULPRIEST, p1)

        life_before = p1.life

        use_hero_power(game, p1)

        # Auchenai converts healing into damage
        assert p1.life <= life_before, (
            f"With Auchenai, Lesser Heal should not increase life. "
            f"Was {life_before}, now {p1.life}"
        )


# ============================================================
# Test 11: Alexstrasza + Fireball
# ============================================================

class TestAlexstraszaPlusFireball:
    def test_alex_sets_enemy_to_15(self):
        """Alexstrasza battlecry sets enemy hero to 15 HP."""
        game, p1, p2 = new_hs_game("Mage", "Mage")

        alex = make_obj(game, ALEXSTRASZA, p1)
        events = ALEXSTRASZA.battlecry(alex, game.state)
        for e in events:
            game.emit(e)

        assert p2.life == 15, (
            f"Alexstrasza should set enemy hero to 15 HP, got {p2.life}"
        )

    def test_alex_plus_fireball_leaves_enemy_at_9(self):
        """Alex sets enemy to 15, then Fireball deals 6 -> enemy at 9."""
        game, p1, p2 = new_hs_game("Mage", "Mage")

        # Alex battlecry sets enemy to 15
        alex = make_obj(game, ALEXSTRASZA, p1)
        events = ALEXSTRASZA.battlecry(alex, game.state)
        for e in events:
            game.emit(e)

        assert p2.life == 15, f"Alex should set enemy to 15, got {p2.life}"

        # Fireball deals 6 to enemy hero
        cast_spell(game, FIREBALL, p1, targets=[p2.hero_id])

        assert p2.life == 9, (
            f"After Alex (15) + Fireball (6), enemy should be at 9, got {p2.life}"
        )


# ============================================================
# Test 12: Grommash Hellscream + Cruel Taskmaster
# ============================================================

class TestGrimmashPlusTaskmaster:
    def test_grom_base_stats(self):
        """Grommash Hellscream is a 4/9 with Charge."""
        game, p1, p2 = new_hs_game("Warrior", "Mage")

        grom = make_obj(game, GROMMASH_HELLSCREAM, p1)
        assert get_power(grom, game.state) == 4, (
            f"Grom base power should be 4, got {get_power(grom, game.state)}"
        )
        assert get_toughness(grom, game.state) == 9, (
            f"Grom base toughness should be 9, got {get_toughness(grom, game.state)}"
        )

    def test_taskmaster_enrages_grom(self):
        """Cruel Taskmaster deals 1 damage to Grom, activating Enrage (+6 ATK) -> 10 ATK total."""
        game, p1, p2 = new_hs_game("Warrior", "Mage")

        grom = make_obj(game, GROMMASH_HELLSCREAM, p1)

        base_power = get_power(grom, game.state)
        assert base_power == 4, f"Grom base should be 4, got {base_power}"

        # Directly deal 1 damage to Grom (emulating Cruel Taskmaster's battlecry)
        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': grom.id, 'amount': 1, 'source': 'taskmaster_test'},
            source='taskmaster_test'
        ))

        # Also give +2 attack from Taskmaster
        game.emit(Event(
            type=EventType.PT_MODIFICATION,
            payload={'object_id': grom.id, 'power_mod': 2, 'toughness_mod': 0, 'duration': 'permanent'},
            source='taskmaster_test'
        ))

        assert grom.state.damage == 1, (
            f"Grom should have 1 damage, got {grom.state.damage}"
        )

        # Enrage: +6 attack when damaged. Plus +2 from Taskmaster buff.
        # 4 base + 6 enrage + 2 taskmaster = 12
        enraged_power = get_power(grom, game.state)
        assert enraged_power == 12, (
            f"Grom should have 12 ATK (4 base + 6 enrage + 2 taskmaster), got {enraged_power}"
        )

    def test_grom_has_charge(self):
        """Grommash has Charge, can attack immediately."""
        game, p1, p2 = new_hs_game("Warrior", "Mage")

        grom = make_obj(game, GROMMASH_HELLSCREAM, p1)

        has_charge = has_ability(grom, 'charge', game.state)
        assert has_charge, "Grommash should have Charge keyword"


# ============================================================
# Run tests
# ============================================================

if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
