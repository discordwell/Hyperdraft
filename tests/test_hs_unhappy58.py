"""
Hearthstone Unhappy Path Tests - Batch 58

Weapon interactions and hero attack mechanics: Truesilver Champion heal
on attack, weapon durability consumption per attack, weapon destruction
at 0 durability, Fiery War Axe two attacks, Assassin's Blade multi-attack,
hero attack + weapon combo, Upgrade! on existing weapon, weapon equip
replaces old weapon, Gorehowl special durability, Arcanite Reaper,
Eaglehorn Bow durability gain from secrets.
"""

import asyncio
from src.engine.game import Game
from src.engine.types import (
    Event, EventType, GameObject, GameState, CardType, ZoneType,
    Interceptor, InterceptorPriority, InterceptorAction, InterceptorResult,
    new_id
)
from src.engine.queries import get_power, get_toughness

from src.cards.hearthstone.heroes import HEROES
from src.cards.hearthstone.hero_powers import HERO_POWERS

from src.cards.hearthstone.basic import (
    WISP, CHILLWIND_YETI, BLOODFEN_RAPTOR,
    FIERY_WAR_AXE, ARCANITE_REAPER,
)
from src.cards.hearthstone.classic import (
    TRUESILVER_CHAMPION,
)
from src.cards.hearthstone.rogue import (
    ASSASSINS_BLADE, DEADLY_POISON,
)
from src.cards.hearthstone.warrior import (
    GOREHOWL, UPGRADE, ARATHI_WEAPONSMITH,
)
from src.cards.hearthstone.paladin import (
    SWORD_OF_JUSTICE,
)
from src.cards.hearthstone.hunter import (
    EAGLEHORN_BOW,
)


# ============================================================
# Test Helpers
# ============================================================

def new_hs_game(class1="Warrior", class2="Mage"):
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


def play_from_hand(game, card_def, owner):
    """Play a card from hand to battlefield, triggering ZONE_CHANGE interceptors."""
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


def cast_spell(game, card_def, owner, targets=None):
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


def hero_attack(game, player, target_id):
    """
    Simulate a full hero attack using the HearthstoneCombatManager.

    This calls declare_attack which handles:
    - ATTACK_DECLARED event (interceptors fire)
    - Damage resolution (simultaneous)
    - Weapon durability loss
    - Weapon destruction at 0 durability
    """
    loop = asyncio.new_event_loop()
    try:
        events = loop.run_until_complete(
            game.combat_manager.declare_attack(player.hero_id, target_id)
        )
    finally:
        loop.close()
    return events


def sync_hero_weapon(player, hero_obj):
    """Sync weapon stats from player to hero object."""
    hero_obj.state.weapon_attack = player.weapon_attack
    hero_obj.state.weapon_durability = player.weapon_durability


# ============================================================
# Weapon Durability
# ============================================================

class TestWeaponDurabilityConsumption:
    """Equip a 3/2 weapon (Fiery War Axe). Attack twice.
    After first attack, durability = 1. After second attack, weapon destroyed."""

    def test_first_attack_reduces_durability_by_one(self):
        game, p1, p2 = new_hs_game("Warrior", "Mage")
        game.state.active_player = p1.id

        # Play Fiery War Axe from hand (triggers equip interceptor)
        axe = play_from_hand(game, FIERY_WAR_AXE, p1)

        assert p1.weapon_attack == 3
        assert p1.weapon_durability == 2

        hero = game.state.objects[p1.hero_id]
        hero.state.attacks_this_turn = 0

        # Attack enemy hero
        events = hero_attack(game, p1, p2.hero_id)

        assert p1.weapon_durability == 1
        assert p1.weapon_attack == 3  # Attack stays the same

    def test_second_attack_destroys_weapon(self):
        game, p1, p2 = new_hs_game("Warrior", "Mage")
        game.state.active_player = p1.id

        axe = play_from_hand(game, FIERY_WAR_AXE, p1)

        hero = game.state.objects[p1.hero_id]
        hero.state.attacks_this_turn = 0

        # First attack
        hero_attack(game, p1, p2.hero_id)
        assert p1.weapon_durability == 1

        # Reset attack counter for second attack
        hero.state.attacks_this_turn = 0

        # Second attack
        hero_attack(game, p1, p2.hero_id)
        assert p1.weapon_durability == 0
        assert p1.weapon_attack == 0  # Weapon destroyed


class TestWeaponDurabilityAtZeroDestroyed:
    """Equip a 1-durability weapon. Attack once. Weapon should be destroyed."""

    def test_one_durability_weapon_destroyed_after_attack(self):
        game, p1, p2 = new_hs_game("Warrior", "Mage")
        game.state.active_player = p1.id

        # Manually set up a 1-durability weapon
        p1.weapon_attack = 5
        p1.weapon_durability = 1
        hero = game.state.objects[p1.hero_id]
        sync_hero_weapon(p1, hero)
        hero.state.attacks_this_turn = 0

        events = hero_attack(game, p1, p2.hero_id)

        assert p1.weapon_durability == 0
        assert p1.weapon_attack == 0

        # Verify damage was dealt
        damage_events = [e for e in events if e.type == EventType.DAMAGE
                         and e.payload.get('target') == p2.hero_id]
        assert len(damage_events) == 1
        assert damage_events[0].payload['amount'] == 5


class TestArcaniteReaper:
    """Equip 5/2 Arcanite Reaper. Attack. Verify 5 damage dealt and durability goes to 1."""

    def test_arcanite_reaper_attack_deals_five_and_reduces_durability(self):
        game, p1, p2 = new_hs_game("Warrior", "Mage")
        game.state.active_player = p1.id

        reaper = play_from_hand(game, ARCANITE_REAPER, p1)

        assert p1.weapon_attack == 5
        assert p1.weapon_durability == 2

        hero = game.state.objects[p1.hero_id]
        hero.state.attacks_this_turn = 0

        events = hero_attack(game, p1, p2.hero_id)

        # Durability went from 2 to 1
        assert p1.weapon_durability == 1
        # Attack is still 5
        assert p1.weapon_attack == 5

        # Verify 5 damage was dealt to enemy hero
        damage_events = [e for e in events if e.type == EventType.DAMAGE
                         and e.payload.get('target') == p2.hero_id]
        assert len(damage_events) == 1
        assert damage_events[0].payload['amount'] == 5

        # Enemy hero lost 5 life
        assert p2.life == 25


# ============================================================
# Weapon + Hero Attack
# ============================================================

class TestHeroAttackWithWeapon:
    """Equip weapon, then hero attacks an enemy minion.
    Verify damage equal to weapon attack, and hero takes minion's attack as damage."""

    def test_hero_attacks_minion_mutual_damage(self):
        game, p1, p2 = new_hs_game("Warrior", "Mage")
        game.state.active_player = p1.id

        axe = play_from_hand(game, FIERY_WAR_AXE, p1)

        # Enemy minion: 4/5 Chillwind Yeti
        yeti = make_obj(game, CHILLWIND_YETI, p2)

        hero = game.state.objects[p1.hero_id]
        hero.state.attacks_this_turn = 0

        p1_life_before = p1.life
        events = hero_attack(game, p1, yeti.id)

        # Yeti should have taken 3 damage (weapon attack)
        assert yeti.state.damage == 3

        # Hero should have taken 4 damage (yeti's attack)
        assert p1.life == p1_life_before - 4


class TestHeroAttackDealsDamage:
    """Hero attacks enemy hero face. Verify damage event with correct amount."""

    def test_hero_face_attack_deals_weapon_damage(self):
        game, p1, p2 = new_hs_game("Warrior", "Mage")
        game.state.active_player = p1.id

        p1.weapon_attack = 4
        p1.weapon_durability = 2
        hero = game.state.objects[p1.hero_id]
        sync_hero_weapon(p1, hero)
        hero.state.attacks_this_turn = 0

        events = hero_attack(game, p1, p2.hero_id)

        # Verify a DAMAGE event was emitted with amount == 4
        damage_events = [e for e in events if e.type == EventType.DAMAGE
                         and e.payload.get('target') == p2.hero_id]
        assert len(damage_events) == 1
        assert damage_events[0].payload['amount'] == 4

        # P2 lost 4 life
        assert p2.life == 26


# ============================================================
# Special Weapons
# ============================================================

class TestTruesilverChampionHeal:
    """Truesilver Champion (4/2) heals hero for 2 on each attack.
    Verify LIFE_CHANGE event with amount=2 for the attacking hero."""

    def test_truesilver_heals_on_attack(self):
        game, p1, p2 = new_hs_game("Paladin", "Mage")
        game.state.active_player = p1.id

        truesilver = play_from_hand(game, TRUESILVER_CHAMPION, p1)

        assert p1.weapon_attack == 4
        assert p1.weapon_durability == 2

        # Damage hero first so heal is observable
        p1.life = 25

        hero = game.state.objects[p1.hero_id]
        hero.state.attacks_this_turn = 0

        events = hero_attack(game, p1, p2.hero_id)

        # Check that a LIFE_CHANGE event was generated
        heal_events = [e for e in game.state.event_log
                       if e.type == EventType.LIFE_CHANGE
                       and e.payload.get('player') == p1.id
                       and e.payload.get('amount') == 2]
        assert len(heal_events) >= 1

        # Hero should have been healed by 2 (25 -> 27)
        assert p1.life == 27


class TestSwordOfJusticeAutoBuffs:
    """Sword of Justice (1/5) gives summoned minions +1/+1 and loses 1 durability."""

    def test_sword_of_justice_buffs_minion_on_summon(self):
        game, p1, p2 = new_hs_game("Paladin", "Mage")

        sword = play_from_hand(game, SWORD_OF_JUSTICE, p1)

        assert p1.weapon_attack == 1
        assert p1.weapon_durability == 5

        # Summon a minion (Wisp: 1/1)
        wisp = play_from_hand(game, WISP, p1)

        # Check for PT_MODIFICATION event (+1/+1)
        buff_events = [e for e in game.state.event_log
                       if e.type == EventType.PT_MODIFICATION
                       and e.payload.get('object_id') == wisp.id
                       and e.payload.get('power_mod') == 1
                       and e.payload.get('toughness_mod') == 1]
        assert len(buff_events) >= 1

        # Durability should have decreased by 1
        assert p1.weapon_durability == 4


# ============================================================
# Weapon Replacement
# ============================================================

class TestWeaponEquipReplacesOld:
    """Equip one weapon, then equip another. The old weapon should be destroyed and replaced."""

    def test_second_weapon_replaces_first(self):
        game, p1, p2 = new_hs_game("Warrior", "Mage")

        # Play Fiery War Axe (3/2)
        axe = play_from_hand(game, FIERY_WAR_AXE, p1)
        assert p1.weapon_attack == 3
        assert p1.weapon_durability == 2

        # Play Arcanite Reaper (5/2) - should replace the axe
        reaper = play_from_hand(game, ARCANITE_REAPER, p1)

        # Check that old weapon was destroyed
        destroy_events = [e for e in game.state.event_log
                          if e.type == EventType.OBJECT_DESTROYED
                          and e.payload.get('object_id') == axe.id
                          and e.payload.get('reason') == 'weapon_replaced']
        assert len(destroy_events) >= 1

        # New weapon stats are set
        assert p1.weapon_attack == 5
        assert p1.weapon_durability == 2


class TestWeaponEquipEvent:
    """Equipping a weapon fires relevant events during ZONE_CHANGE."""

    def test_weapon_equip_produces_zone_change_event(self):
        game, p1, p2 = new_hs_game("Warrior", "Mage")

        axe = play_from_hand(game, FIERY_WAR_AXE, p1)

        # Verify ZONE_CHANGE event was emitted for the weapon entering battlefield
        zone_events = [e for e in game.state.event_log
                       if e.type == EventType.ZONE_CHANGE
                       and e.payload.get('object_id') == axe.id
                       and e.payload.get('to_zone_type') == ZoneType.BATTLEFIELD]
        assert len(zone_events) >= 1

        # And weapon stats are now set on the player
        assert p1.weapon_attack == 3
        assert p1.weapon_durability == 2


# ============================================================
# Weapon Buffs
# ============================================================

class TestDeadlyPoisonBuffsWeapon:
    """Equip a 1/2 dagger, cast Deadly Poison (+2 attack). Weapon attack should be 3."""

    def test_deadly_poison_adds_two_attack(self):
        game, p1, p2 = new_hs_game("Rogue", "Mage")

        # Set up a 1/2 dagger (rogue hero power weapon)
        p1.weapon_attack = 1
        p1.weapon_durability = 2

        cast_spell(game, DEADLY_POISON, p1)

        # Weapon attack should now be 3 (+2 from Deadly Poison)
        assert p1.weapon_attack == 3


class TestUpgradeExistingWeapon:
    """Equip Fiery War Axe (3/2), cast Upgrade! -> should become 4/3 (+1/+1)."""

    def test_upgrade_buffs_existing_weapon(self):
        game, p1, p2 = new_hs_game("Warrior", "Mage")

        axe = play_from_hand(game, FIERY_WAR_AXE, p1)
        assert p1.weapon_attack == 3
        assert p1.weapon_durability == 2

        cast_spell(game, UPGRADE, p1)

        assert p1.weapon_attack == 4
        assert p1.weapon_durability == 3


class TestUpgradeNoWeapon:
    """Cast Upgrade! with no weapon -> should equip a 1/3 weapon."""

    def test_upgrade_equips_new_weapon_when_none(self):
        game, p1, p2 = new_hs_game("Warrior", "Mage")

        # Ensure no weapon equipped
        assert p1.weapon_attack == 0
        assert p1.weapon_durability == 0

        cast_spell(game, UPGRADE, p1)

        # Should have emitted WEAPON_EQUIP event with attack=1, durability=3
        equip_events = [e for e in game.state.event_log
                        if e.type == EventType.WEAPON_EQUIP]
        assert len(equip_events) >= 1
        assert equip_events[0].payload.get('attack') == 1
        assert equip_events[0].payload.get('durability') == 3
