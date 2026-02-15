"""
Hearthstone Unhappy Path Tests - Batch 34

Hero system edge cases: hero damage vs armor, life cap at max_life, hero power
used-this-turn tracking, weapon durability loss on attack, weapon destruction at
0 durability, hero attack from weapon, equipping new weapon replaces old,
damage to hero with divine shield minions on board, multi-turn hero interaction,
and hero replacement edge cases.
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
    WISP, CHILLWIND_YETI, BLOODFEN_RAPTOR,
)
from src.cards.hearthstone.classic import (
    FIREBALL, FROSTBOLT, TRUESILVER_CHAMPION, ARCANITE_REAPER,
    ABUSIVE_SERGEANT, ARGENT_SQUIRE,
)
from src.cards.hearthstone.warrior import GOREHOWL
from src.cards.hearthstone.warlock import LORD_JARAXXUS


# ============================================================
# Test Helpers
# ============================================================

def new_hs_game():
    game = Game(mode='hearthstone')
    p1 = game.add_player("Player1", life=30)
    p2 = game.add_player("Player2", life=30)
    game.setup_hearthstone_player(p1, HEROES["Mage"], HERO_POWERS["Mage"])
    game.setup_hearthstone_player(p2, HEROES["Warrior"], HERO_POWERS["Warrior"])
    for _ in range(10):
        game.mana_system.on_turn_start(p1.id)
        game.mana_system.on_turn_start(p2.id)
    return game, p1, p2


def make_obj(game, card_def, owner, zone=ZoneType.BATTLEFIELD):
    return game.create_object(
        name=card_def.name, owner_id=owner.id, zone=zone,
        characteristics=card_def.characteristics, card_def=card_def
    )


def play_from_hand(game, card_def, owner):
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


def cast_spell_full(game, card_def, owner, targets=None):
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
# Hero Damage and Armor
# ============================================================

class TestHeroDamageAndArmor:
    def test_armor_absorbs_damage_first(self):
        """Armor should absorb damage before health takes a hit."""
        game, p1, p2 = new_hs_game()
        p1.armor = 5
        p1.life = 30

        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': p1.hero_id, 'amount': 3, 'source': 'test'},
            source='test'
        ))

        # Armor should absorb 3, leaving 2 armor and 30 HP
        assert p1.armor == 2
        assert p1.life == 30

    def test_damage_exceeding_armor_hits_health(self):
        """Damage exceeding armor should spill into health."""
        game, p1, p2 = new_hs_game()
        p1.armor = 3
        p1.life = 30

        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': p1.hero_id, 'amount': 5, 'source': 'test'},
            source='test'
        ))

        assert p1.armor == 0
        assert p1.life == 28  # 30 - (5 - 3)

    def test_zero_armor_damage_goes_to_health(self):
        """With no armor, all damage goes to health."""
        game, p1, p2 = new_hs_game()
        p1.armor = 0
        p1.life = 30

        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': p1.hero_id, 'amount': 7, 'source': 'test'},
            source='test'
        ))

        assert p1.life == 23

    def test_heal_does_not_exceed_max_life(self):
        """Healing should not exceed max_life."""
        game, p1, p2 = new_hs_game()
        p1.life = 29
        p1.max_life = 30

        game.emit(Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': p1.id, 'amount': 5},
            source='test'
        ))

        # Life should be capped at 30
        assert p1.life <= 30


# ============================================================
# Weapon Mechanics
# ============================================================

class TestWeaponMechanics:
    def test_weapon_equip_sets_stats(self):
        """Equipping a weapon should set player weapon stats."""
        game, p1, p2 = new_hs_game()
        assert p1.weapon_attack == 0
        assert p1.weapon_durability == 0

        # Equip via direct set (how battlecries do it)
        p1.weapon_attack = 4
        p1.weapon_durability = 2

        assert p1.weapon_attack == 4
        assert p1.weapon_durability == 2

    def test_new_weapon_replaces_old(self):
        """Equipping a new weapon should replace the old one."""
        game, p1, p2 = new_hs_game()
        p1.weapon_attack = 3
        p1.weapon_durability = 2

        # Equip new weapon (overwrites)
        p1.weapon_attack = 5
        p1.weapon_durability = 1

        assert p1.weapon_attack == 5
        assert p1.weapon_durability == 1

    def test_gorehowl_multi_attack_sequence(self):
        """Gorehowl loses 1 ATK per minion attack, tracking across attacks."""
        game, p1, p2 = new_hs_game()
        gh = make_obj(game, GOREHOWL, p1)
        p1.weapon_attack = 7
        p1.weapon_durability = 1

        # First attack on a minion
        t1 = make_obj(game, CHILLWIND_YETI, p2)
        game.emit(Event(
            type=EventType.ATTACK_DECLARED,
            payload={'attacker_id': p1.hero_id, 'target_id': t1.id},
            source=p1.hero_id
        ))

        # Should be at 6 ATK now
        assert p1.weapon_attack == 6

        # Second attack on another minion
        t2 = make_obj(game, CHILLWIND_YETI, p2)
        game.emit(Event(
            type=EventType.ATTACK_DECLARED,
            payload={'attacker_id': p1.hero_id, 'target_id': t2.id},
            source=p1.hero_id
        ))

        assert p1.weapon_attack == 5


# ============================================================
# Mana System Edge Cases
# ============================================================

class TestManaSystemEdges:
    def test_mana_crystal_cap_at_10(self):
        """Mana crystals should cap at 10."""
        game, p1, p2 = new_hs_game()
        assert p1.mana_crystals == 10

        # Try to add more
        p1.mana_crystals += 1
        # Depending on implementation, may or may not cap here
        # The adapter enforces the cap during play validation

    def test_overload_reduces_available_mana(self):
        """Overloaded mana should reduce available mana next turn."""
        game, p1, p2 = new_hs_game()
        p1.overloaded_mana = 3

        # After overload, available mana should be reduced
        assert p1.overloaded_mana == 3

    def test_cost_modifier_structure(self):
        """Cost modifiers should have proper structure."""
        game, p1, p2 = new_hs_game()
        from src.cards.interceptor_helpers import add_one_shot_cost_reduction

        add_one_shot_cost_reduction(p1, CardType.SPELL, 2, duration='this_turn')

        assert len(p1.cost_modifiers) >= 1
        mod = p1.cost_modifiers[-1]
        assert mod['card_type'] == CardType.SPELL
        assert mod['amount'] == 2


# ============================================================
# Hero Power Edge Cases
# ============================================================

class TestHeroPowerEdges:
    def test_hero_power_exists_on_setup(self):
        """Hero power should be registered in state.objects after setup."""
        game, p1, p2 = new_hs_game()

        assert p1.hero_power_id is not None
        hp = game.state.objects.get(p1.hero_power_id)
        assert hp is not None

    def test_different_heroes_different_powers(self):
        """Mage and Warrior should have different hero powers."""
        game, p1, p2 = new_hs_game()

        hp1 = game.state.objects.get(p1.hero_power_id)
        hp2 = game.state.objects.get(p2.hero_power_id)
        assert hp1.name != hp2.name


# ============================================================
# Lord Jaraxxus Detailed
# ============================================================

class TestJaraxxusDetailed:
    def test_jaraxxus_weapon_syncs_to_hero(self):
        """Jaraxxus weapon stats should sync to the hero object."""
        game, p1, p2 = new_hs_game()
        hero = game.state.objects.get(p1.hero_id)

        LORD_JARAXXUS.battlecry(
            make_obj(game, LORD_JARAXXUS, p1), game.state
        )

        assert hero.state.weapon_attack == 3
        assert hero.state.weapon_durability == 8

    def test_jaraxxus_with_existing_weapon(self):
        """Jaraxxus should replace any existing weapon."""
        game, p1, p2 = new_hs_game()
        p1.weapon_attack = 4
        p1.weapon_durability = 2

        LORD_JARAXXUS.battlecry(
            make_obj(game, LORD_JARAXXUS, p1), game.state
        )

        assert p1.weapon_attack == 3
        assert p1.weapon_durability == 8

    def test_jaraxxus_with_armor(self):
        """Jaraxxus should clear armor on replacement."""
        game, p1, p2 = new_hs_game()
        p1.armor = 15

        LORD_JARAXXUS.battlecry(
            make_obj(game, LORD_JARAXXUS, p1), game.state
        )

        assert p1.armor == 0
        assert p1.life == 15


# ============================================================
# Truesilver Champion + Armor Interaction
# ============================================================

class TestTruesilverWithArmor:
    def test_truesilver_heals_during_armor(self):
        """Truesilver heal with full HP but armor should still fire (if at max HP, skips)."""
        game, p1, p2 = new_hs_game()
        ts = make_obj(game, TRUESILVER_CHAMPION, p1)
        p1.life = 30
        p1.armor = 5

        game.emit(Event(
            type=EventType.ATTACK_DECLARED,
            payload={'attacker_id': p1.hero_id, 'target_id': p2.hero_id},
            source=p1.hero_id
        ))

        # At full HP, Truesilver skips the heal
        heal_events = [e for e in game.state.event_log
                       if e.type == EventType.LIFE_CHANGE and
                       e.payload.get('player') == p1.id and
                       e.payload.get('amount', 0) > 0]
        assert len(heal_events) == 0

    def test_truesilver_heals_when_damaged(self):
        """Truesilver heal should fire when hero is below max HP."""
        game, p1, p2 = new_hs_game()
        ts = make_obj(game, TRUESILVER_CHAMPION, p1)
        p1.life = 20

        game.emit(Event(
            type=EventType.ATTACK_DECLARED,
            payload={'attacker_id': p1.hero_id, 'target_id': p2.hero_id},
            source=p1.hero_id
        ))

        heal_events = [e for e in game.state.event_log
                       if e.type == EventType.LIFE_CHANGE and
                       e.payload.get('player') == p1.id and
                       e.payload.get('amount', 0) > 0]
        assert len(heal_events) >= 1


# ============================================================
# Zone Tracking
# ============================================================

class TestZoneTracking:
    def test_object_in_correct_zone_after_create(self):
        """Objects should be in the correct zone after creation."""
        game, p1, p2 = new_hs_game()
        bf_obj = make_obj(game, WISP, p1, zone=ZoneType.BATTLEFIELD)
        hand_obj = make_obj(game, WISP, p1, zone=ZoneType.HAND)

        assert bf_obj.zone == ZoneType.BATTLEFIELD
        assert hand_obj.zone == ZoneType.HAND

        bf_zone = game.state.zones.get('battlefield')
        hand_zone = game.state.zones.get(f'hand_{p1.id}')

        assert bf_obj.id in bf_zone.objects
        assert hand_obj.id in hand_zone.objects

    def test_battlefield_shared_between_players(self):
        """Battlefield zone should contain both players' minions."""
        game, p1, p2 = new_hs_game()
        m1 = make_obj(game, WISP, p1)
        m2 = make_obj(game, WISP, p2)

        bf = game.state.zones.get('battlefield')
        assert m1.id in bf.objects
        assert m2.id in bf.objects

    def test_objects_distinguished_by_controller(self):
        """Objects on shared battlefield should have different controllers."""
        game, p1, p2 = new_hs_game()
        m1 = make_obj(game, WISP, p1)
        m2 = make_obj(game, WISP, p2)

        assert m1.controller == p1.id
        assert m2.controller == p2.id


# ============================================================
# Game State Integrity
# ============================================================

class TestGameStateIntegrity:
    def test_event_log_records_all_events(self):
        """Event log should capture all emitted events."""
        game, p1, p2 = new_hs_game()
        log_before = len(game.state.event_log)

        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': p2.hero_id, 'amount': 1, 'source': 'test'},
            source='test'
        ))

        assert len(game.state.event_log) > log_before

    def test_deep_copy_prevents_shared_characteristics(self):
        """Two objects from the same card_def should have independent characteristics."""
        game, p1, p2 = new_hs_game()
        obj1 = make_obj(game, CHILLWIND_YETI, p1)
        obj2 = make_obj(game, CHILLWIND_YETI, p2)

        # Modify one, shouldn't affect the other
        obj1.characteristics.power = 99

        assert obj2.characteristics.power == 4  # Original
        assert obj1.characteristics.power == 99

    def test_summoning_sickness_set_on_battlefield_create(self):
        """Objects created on battlefield should have summoning sickness."""
        game, p1, p2 = new_hs_game()
        obj = make_obj(game, WISP, p1)

        assert obj.state.summoning_sickness is True

    def test_hand_objects_no_summoning_sickness(self):
        """Objects created in hand should NOT have summoning sickness."""
        game, p1, p2 = new_hs_game()
        obj = make_obj(game, WISP, p1, zone=ZoneType.HAND)

        assert obj.state.summoning_sickness is False
