"""
Hearthstone Unhappy Path Tests - Batch 48

Warrior weapons (Gorehowl, Upgrade!, Shield Slam), Frothing Berserker,
Mortal Strike conditional damage, Brawl mass destruction, warlock
self-damage/discard mechanics (Soulfire, Doomguard, Succubus, Flame Imp,
Power Overwhelming), and cross-card weapon interaction chains.
"""

import random
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
)
from src.cards.hearthstone.classic import (
    KNIFE_JUGGLER, FROSTBOLT, WILD_PYROMANCER,
    LOOT_HOARDER, FLESHEATING_GHOUL,
)
from src.cards.hearthstone.warrior import (
    GOREHOWL, UPGRADE, SHIELD_SLAM, MORTAL_STRIKE, BRAWL,
    FROTHING_BERSERKER, CRUEL_TASKMASTER, ARMORSMITH,
    ARATHI_WEAPONSMITH,
)
from src.cards.hearthstone.warlock import (
    SOULFIRE, SUCCUBUS, DOOMGUARD, FLAME_IMP, PIT_LORD,
)


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


def new_hs_game_classes(class1, class2):
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
# Gorehowl
# ============================================================

class TestGorehowl:
    def test_gorehowl_loses_attack_on_minion_hit(self):
        """Gorehowl: attacking a minion loses 1 Attack instead of durability."""
        game, p1, p2 = new_hs_game_classes("Warrior", "Mage")
        gorehowl = make_obj(game, GOREHOWL, p1)
        p1.weapon_attack = 7
        p1.weapon_durability = 1

        target = make_obj(game, CHILLWIND_YETI, p2)

        game.emit(Event(
            type=EventType.ATTACK_DECLARED,
            payload={'attacker_id': p1.hero_id, 'target_id': target.id},
            source=p1.hero_id
        ))

        # Attack should be reduced by 1 and durability compensated
        assert p1.weapon_attack == 6  # 7 - 1
        assert p1.weapon_durability >= 1  # Still usable

    def test_gorehowl_destroyed_at_zero_attack(self):
        """Gorehowl should be destroyed when attack reaches 0."""
        game, p1, p2 = new_hs_game_classes("Warrior", "Mage")
        gorehowl = make_obj(game, GOREHOWL, p1)
        p1.weapon_attack = 1
        p1.weapon_durability = 1

        target = make_obj(game, CHILLWIND_YETI, p2)

        game.emit(Event(
            type=EventType.ATTACK_DECLARED,
            payload={'attacker_id': p1.hero_id, 'target_id': target.id},
            source=p1.hero_id
        ))

        assert p1.weapon_attack == 0
        assert p1.weapon_durability == 0


# ============================================================
# Upgrade!
# ============================================================

class TestUpgrade:
    def test_upgrade_with_weapon_buffs(self):
        """Upgrade! with a weapon gives +1/+1 to weapon."""
        game, p1, p2 = new_hs_game_classes("Warrior", "Mage")
        p1.weapon_attack = 3
        p1.weapon_durability = 2

        cast_spell_full(game, UPGRADE, p1)

        # Should have buffed weapon or equipped new one
        # Upgrade checks for existing weapon
        weapon_events = [e for e in game.state.event_log
                         if e.type in (EventType.WEAPON_EQUIP, EventType.PT_MODIFICATION)]
        assert len(weapon_events) >= 1

    def test_upgrade_without_weapon_equips(self):
        """Upgrade! without a weapon equips a 1/3 weapon."""
        game, p1, p2 = new_hs_game_classes("Warrior", "Mage")
        p1.weapon_attack = 0
        p1.weapon_durability = 0

        cast_spell_full(game, UPGRADE, p1)

        equip_events = [e for e in game.state.event_log
                        if e.type == EventType.WEAPON_EQUIP]
        assert len(equip_events) >= 1
        assert equip_events[0].payload.get('attack') == 1
        assert equip_events[0].payload.get('durability') == 3


# ============================================================
# Shield Slam
# ============================================================

class TestShieldSlam:
    def test_damage_equals_armor(self):
        """Shield Slam deals damage equal to armor amount."""
        game, p1, p2 = new_hs_game_classes("Warrior", "Mage")
        p1.armor = 10
        target = make_obj(game, CHILLWIND_YETI, p2)

        cast_spell_full(game, SHIELD_SLAM, p1)

        damage_events = [e for e in game.state.event_log
                         if e.type == EventType.DAMAGE and
                         e.payload.get('amount') == 10]
        assert len(damage_events) >= 1

    def test_no_armor_no_damage(self):
        """Shield Slam with 0 armor does nothing."""
        game, p1, p2 = new_hs_game_classes("Warrior", "Mage")
        p1.armor = 0
        target = make_obj(game, CHILLWIND_YETI, p2)

        cast_spell_full(game, SHIELD_SLAM, p1)

        damage_events = [e for e in game.state.event_log
                         if e.type == EventType.DAMAGE and
                         e.payload.get('from_spell')]
        assert len(damage_events) == 0


# ============================================================
# Mortal Strike
# ============================================================

class TestMortalStrike:
    def test_deals_4_damage_above_12_hp(self):
        """Mortal Strike deals 4 damage when controller has > 12 HP."""
        game, p1, p2 = new_hs_game_classes("Warrior", "Mage")
        p1.life = 20
        target = make_obj(game, CHILLWIND_YETI, p2)

        cast_spell_full(game, MORTAL_STRIKE, p1)

        damage_events = [e for e in game.state.event_log
                         if e.type == EventType.DAMAGE and
                         e.payload.get('amount') == 4]
        assert len(damage_events) >= 1

    def test_deals_6_damage_at_or_below_12_hp(self):
        """Mortal Strike deals 6 damage when controller has <= 12 HP."""
        game, p1, p2 = new_hs_game_classes("Warrior", "Mage")
        p1.life = 12
        target = make_obj(game, CHILLWIND_YETI, p2)

        cast_spell_full(game, MORTAL_STRIKE, p1)

        damage_events = [e for e in game.state.event_log
                         if e.type == EventType.DAMAGE and
                         e.payload.get('amount') == 6]
        assert len(damage_events) >= 1


# ============================================================
# Brawl
# ============================================================

class TestBrawl:
    def test_destroys_all_but_one(self):
        """Brawl destroys all minions except one random survivor."""
        game, p1, p2 = new_hs_game()
        random.seed(42)
        minions = [make_obj(game, WISP, p1) for _ in range(3)]
        minions += [make_obj(game, WISP, p2) for _ in range(3)]

        cast_spell_full(game, BRAWL, p1)

        destroy_events = [e for e in game.state.event_log
                          if e.type == EventType.OBJECT_DESTROYED and
                          e.payload.get('reason') == 'brawl']
        assert len(destroy_events) == 5  # 6 minions - 1 survivor

    def test_brawl_with_one_minion_does_nothing(self):
        """Brawl with only 1 minion should not destroy it."""
        game, p1, p2 = new_hs_game()
        sole = make_obj(game, WISP, p1)

        cast_spell_full(game, BRAWL, p1)

        destroy_events = [e for e in game.state.event_log
                          if e.type == EventType.OBJECT_DESTROYED and
                          e.payload.get('reason') == 'brawl']
        assert len(destroy_events) == 0

    def test_brawl_with_no_minions(self):
        """Brawl with empty board should do nothing."""
        game, p1, p2 = new_hs_game()

        cast_spell_full(game, BRAWL, p1)

        destroy_events = [e for e in game.state.event_log
                          if e.type == EventType.OBJECT_DESTROYED]
        assert len(destroy_events) == 0


# ============================================================
# Frothing Berserker
# ============================================================

class TestFrothingBerserker:
    def test_gains_attack_on_any_minion_damage(self):
        """Frothing gains +1 ATK whenever ANY minion takes damage."""
        game, p1, p2 = new_hs_game()
        froth = make_obj(game, FROTHING_BERSERKER, p1)

        # Damage an enemy minion
        enemy = make_obj(game, CHILLWIND_YETI, p2)
        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': enemy.id, 'amount': 1, 'source': 'test'},
            source='test'
        ))

        pt_mods = [e for e in game.state.event_log
                   if e.type == EventType.PT_MODIFICATION and
                   e.payload.get('object_id') == froth.id]
        assert len(pt_mods) >= 1

    def test_gains_from_friendly_damage_too(self):
        """Frothing gains from friendly minion damage as well."""
        game, p1, p2 = new_hs_game()
        froth = make_obj(game, FROTHING_BERSERKER, p1)
        friendly = make_obj(game, WISP, p1)

        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': friendly.id, 'amount': 1, 'source': 'test'},
            source='test'
        ))

        pt_mods = [e for e in game.state.event_log
                   if e.type == EventType.PT_MODIFICATION and
                   e.payload.get('object_id') == froth.id]
        assert len(pt_mods) >= 1

    def test_does_not_trigger_on_hero_damage(self):
        """Frothing should NOT trigger on hero damage (only minions)."""
        game, p1, p2 = new_hs_game()
        froth = make_obj(game, FROTHING_BERSERKER, p1)

        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': p2.hero_id, 'amount': 5, 'source': 'test'},
            source='test'
        ))

        pt_mods = [e for e in game.state.event_log
                   if e.type == EventType.PT_MODIFICATION and
                   e.payload.get('object_id') == froth.id]
        assert len(pt_mods) == 0

    def test_frothing_with_whirlwind_mass_damage(self):
        """Frothing + many minions taking damage = many +1 ATK procs."""
        game, p1, p2 = new_hs_game()
        froth = make_obj(game, FROTHING_BERSERKER, p1)
        minions = [make_obj(game, CHILLWIND_YETI, p2) for _ in range(4)]

        for m in minions:
            game.emit(Event(
                type=EventType.DAMAGE,
                payload={'target': m.id, 'amount': 1, 'source': 'test'},
                source='test'
            ))

        pt_mods = [e for e in game.state.event_log
                   if e.type == EventType.PT_MODIFICATION and
                   e.payload.get('object_id') == froth.id]
        assert len(pt_mods) >= 4


# ============================================================
# Cruel Taskmaster
# ============================================================

class TestCruelTaskmaster:
    def test_deals_1_damage_and_buffs(self):
        """Cruel Taskmaster BC: 1 damage + 2 ATK to a minion."""
        game, p1, p2 = new_hs_game()
        target = make_obj(game, CHILLWIND_YETI, p2)

        random.seed(42)
        ct = play_from_hand(game, CRUEL_TASKMASTER, p1)

        # Should have damage and buff events
        damage_events = [e for e in game.state.event_log
                         if e.type == EventType.DAMAGE and
                         e.payload.get('source') == ct.id]
        pt_mods = [e for e in game.state.event_log
                   if e.type == EventType.PT_MODIFICATION and
                   e.payload.get('power_mod') == 2]
        assert len(damage_events) >= 1
        assert len(pt_mods) >= 1


# ============================================================
# Warlock Discard Mechanics
# ============================================================

class TestSoulfire:
    def test_deals_4_damage_and_discards(self):
        """Soulfire: deal 4 damage and discard a random card."""
        game, p1, p2 = new_hs_game()
        # Put a card in hand to discard
        hand_card = game.create_object(
            name="Dummy", owner_id=p1.id, zone=ZoneType.HAND,
            characteristics=WISP.characteristics, card_def=WISP
        )

        cast_spell_full(game, SOULFIRE, p1)

        damage_events = [e for e in game.state.event_log
                         if e.type == EventType.DAMAGE and
                         e.payload.get('amount') == 4]
        discard_events = [e for e in game.state.event_log
                          if e.type == EventType.DISCARD and
                          e.payload.get('player') == p1.id]
        assert len(damage_events) >= 1
        assert len(discard_events) >= 1

    def test_soulfire_empty_hand_no_discard(self):
        """Soulfire with empty hand: still deals damage, no discard event."""
        game, p1, p2 = new_hs_game()
        # Ensure hand is empty
        hand = game.state.zones.get(f"hand_{p1.id}")
        if hand:
            hand.objects.clear()

        cast_spell_full(game, SOULFIRE, p1)

        damage_events = [e for e in game.state.event_log
                         if e.type == EventType.DAMAGE and
                         e.payload.get('amount') == 4]
        discard_events = [e for e in game.state.event_log
                          if e.type == EventType.DISCARD]
        assert len(damage_events) >= 1
        assert len(discard_events) == 0


class TestDoomguard:
    def test_discards_2_cards(self):
        """Doomguard BC: discard 2 random cards."""
        game, p1, p2 = new_hs_game()
        # Put 3 cards in hand
        for _ in range(3):
            game.create_object(
                name="Dummy", owner_id=p1.id, zone=ZoneType.HAND,
                characteristics=WISP.characteristics, card_def=WISP
            )

        play_from_hand(game, DOOMGUARD, p1)

        discard_events = [e for e in game.state.event_log
                          if e.type == EventType.DISCARD and
                          e.payload.get('player') == p1.id]
        assert len(discard_events) >= 2

    def test_doomguard_empty_hand(self):
        """Doomguard with empty hand: no discard, no crash."""
        game, p1, p2 = new_hs_game()
        hand = game.state.zones.get(f"hand_{p1.id}")
        if hand:
            hand.objects.clear()

        play_from_hand(game, DOOMGUARD, p1)

        discard_events = [e for e in game.state.event_log
                          if e.type == EventType.DISCARD]
        assert len(discard_events) == 0

    def test_doomguard_one_card_in_hand(self):
        """Doomguard with 1 card: only discards 1 (can't discard 2)."""
        game, p1, p2 = new_hs_game()
        hand = game.state.zones.get(f"hand_{p1.id}")
        if hand:
            hand.objects.clear()
        game.create_object(
            name="Dummy", owner_id=p1.id, zone=ZoneType.HAND,
            characteristics=WISP.characteristics, card_def=WISP
        )

        play_from_hand(game, DOOMGUARD, p1)

        discard_events = [e for e in game.state.event_log
                          if e.type == EventType.DISCARD]
        assert len(discard_events) == 1


class TestSuccubus:
    def test_discards_one_card(self):
        """Succubus BC: discard 1 random card."""
        game, p1, p2 = new_hs_game()
        game.create_object(
            name="Dummy", owner_id=p1.id, zone=ZoneType.HAND,
            characteristics=WISP.characteristics, card_def=WISP
        )

        play_from_hand(game, SUCCUBUS, p1)

        discard_events = [e for e in game.state.event_log
                          if e.type == EventType.DISCARD and
                          e.payload.get('player') == p1.id]
        assert len(discard_events) >= 1

    def test_succubus_empty_hand(self):
        """Succubus with empty hand: no discard, no crash."""
        game, p1, p2 = new_hs_game()
        hand = game.state.zones.get(f"hand_{p1.id}")
        if hand:
            hand.objects.clear()

        play_from_hand(game, SUCCUBUS, p1)

        discard_events = [e for e in game.state.event_log
                          if e.type == EventType.DISCARD]
        assert len(discard_events) == 0


# ============================================================
# Warlock Self-Damage Battlecries
# ============================================================

class TestFlameImp:
    def test_deals_3_damage_to_own_hero(self):
        """Flame Imp BC: 3 damage to own hero."""
        game, p1, p2 = new_hs_game()
        p1.life = 30

        play_from_hand(game, FLAME_IMP, p1)

        damage_events = [e for e in game.state.event_log
                         if e.type == EventType.DAMAGE and
                         e.payload.get('target') == p1.hero_id and
                         e.payload.get('amount') == 3]
        assert len(damage_events) >= 1


class TestPitLord:
    def test_deals_5_damage_to_own_hero(self):
        """Pit Lord BC: 5 damage to own hero."""
        game, p1, p2 = new_hs_game()
        p1.life = 30

        play_from_hand(game, PIT_LORD, p1)

        damage_events = [e for e in game.state.event_log
                         if e.type == EventType.DAMAGE and
                         e.payload.get('target') == p1.hero_id and
                         e.payload.get('amount') == 5]
        assert len(damage_events) >= 1


# ============================================================
# Arathi Weaponsmith
# ============================================================

class TestArathiWeaponsmith:
    def test_battlecry_equips_weapon(self):
        """Arathi Weaponsmith BC: equip a 2/2 weapon."""
        game, p1, p2 = new_hs_game_classes("Warrior", "Mage")

        play_from_hand(game, ARATHI_WEAPONSMITH, p1)

        equip_events = [e for e in game.state.event_log
                        if e.type == EventType.WEAPON_EQUIP and
                        e.payload.get('attack') == 2 and
                        e.payload.get('durability') == 2]
        assert len(equip_events) >= 1


# ============================================================
# Frothing + Armorsmith Chain
# ============================================================

class TestFrothingArmorsmithChain:
    def test_both_trigger_on_same_damage(self):
        """Both Frothing and Armorsmith should trigger on friendly minion damage."""
        game, p1, p2 = new_hs_game()
        froth = make_obj(game, FROTHING_BERSERKER, p1)
        smith = make_obj(game, ARMORSMITH, p1)
        target = make_obj(game, CHILLWIND_YETI, p1)
        p1.armor = 0

        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': target.id, 'amount': 1, 'source': 'test'},
            source='test'
        ))

        # Frothing should get +1 ATK
        froth_mods = [e for e in game.state.event_log
                      if e.type == EventType.PT_MODIFICATION and
                      e.payload.get('object_id') == froth.id]
        assert len(froth_mods) >= 1

        # Armorsmith should gain 1 armor
        armor_events = [e for e in game.state.event_log
                        if e.type == EventType.ARMOR_GAIN and
                        e.payload.get('player') == p1.id]
        assert len(armor_events) >= 1
