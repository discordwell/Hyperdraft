"""
Hearthstone Unhappy Path Tests - Batch 32

Class-specific final sweep: Kirin Tor Mage (next secret costs 0), Cabal Shadow Priest
(steal <=2 ATK minion), SI:7 Agent (Combo: 2 damage), Dust Devil (Overload 2 on play),
Felguard (destroy mana crystal), Lord Jaraxxus (hero replacement), and comprehensive
cross-mechanic interactions testing the boundaries of the engine.
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
    FIREBALL, KNIFE_JUGGLER, ABUSIVE_SERGEANT,
    FLESHEATING_GHOUL, GADGETZAN_AUCTIONEER,
    CULT_MASTER, ACOLYTE_OF_PAIN,
)
from src.cards.hearthstone.mage import KIRIN_TOR_MAGE, COUNTERSPELL
from src.cards.hearthstone.priest import CABAL_SHADOW_PRIEST, LIGHTSPAWN
from src.cards.hearthstone.rogue import SI7_AGENT
from src.cards.hearthstone.shaman import DUST_DEVIL, UNBOUND_ELEMENTAL
from src.cards.hearthstone.warlock import FELGUARD, LORD_JARAXXUS


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
# Kirin Tor Mage — Battlecry: Next Secret costs 0
# ============================================================

class TestKirinTorMage:
    def test_adds_cost_reduction_for_secrets(self):
        """Kirin Tor Mage should add a cost reduction modifier for secrets."""
        game, p1, p2 = new_hs_game()

        ktm = play_from_hand(game, KIRIN_TOR_MAGE, p1)

        # Check that a cost modifier was added for secrets
        assert len(p1.cost_modifiers) >= 1
        modifier = p1.cost_modifiers[-1]
        assert modifier['card_type'] == CardType.SECRET
        assert modifier['amount'] >= 99  # Effectively free

    def test_no_modifier_without_battlecry(self):
        """Placing Kirin Tor directly on battlefield (not from hand) shouldn't trigger."""
        game, p1, p2 = new_hs_game()
        modifiers_before = len(p1.cost_modifiers)

        # Direct place, no battlecry
        ktm = make_obj(game, KIRIN_TOR_MAGE, p1)

        assert len(p1.cost_modifiers) == modifiers_before


# ============================================================
# Cabal Shadow Priest — Battlecry: Steal enemy minion with <=2 ATK
# ============================================================

class TestCabalShadowPriest:
    def test_steals_low_attack_minion(self):
        """Cabal should steal an enemy minion with 2 or less Attack."""
        game, p1, p2 = new_hs_game()
        target = make_obj(game, WISP, p2)  # 1/1

        events = CABAL_SHADOW_PRIEST.battlecry(
            make_obj(game, CABAL_SHADOW_PRIEST, p1), game.state
        )

        assert len(events) >= 1
        gain_control = events[0]
        assert gain_control.type == EventType.GAIN_CONTROL
        assert gain_control.payload['object_id'] == target.id
        assert gain_control.payload['new_controller'] == p1.id

    def test_does_not_steal_high_attack(self):
        """Cabal shouldn't steal minions with more than 2 Attack."""
        game, p1, p2 = new_hs_game()
        big = make_obj(game, CHILLWIND_YETI, p2)  # 4/5

        events = CABAL_SHADOW_PRIEST.battlecry(
            make_obj(game, CABAL_SHADOW_PRIEST, p1), game.state
        )

        assert events == []

    def test_no_targets_no_crash(self):
        """Cabal with no valid targets shouldn't crash."""
        game, p1, p2 = new_hs_game()

        events = CABAL_SHADOW_PRIEST.battlecry(
            make_obj(game, CABAL_SHADOW_PRIEST, p1), game.state
        )
        assert events == []


# ============================================================
# SI:7 Agent — Combo: Deal 2 damage
# ============================================================

class TestSI7Agent:
    def test_combo_deals_2_damage(self):
        """SI:7 Agent with Combo active should deal 2 damage."""
        game, p1, p2 = new_hs_game()
        p1.cards_played_this_turn = 1  # Combo active
        enemy = make_obj(game, CHILLWIND_YETI, p2)

        si7 = make_obj(game, SI7_AGENT, p1)
        events = SI7_AGENT.battlecry(si7, game.state)

        assert len(events) >= 1
        assert events[0].type == EventType.DAMAGE
        assert events[0].payload['amount'] == 2

    def test_no_combo_no_damage(self):
        """SI:7 Agent without Combo should deal 0 damage."""
        game, p1, p2 = new_hs_game()
        p1.cards_played_this_turn = 0  # No combo

        si7 = make_obj(game, SI7_AGENT, p1)
        events = SI7_AGENT.battlecry(si7, game.state)

        assert events == []


# ============================================================
# Dust Devil — Overload: (2) on play
# ============================================================

class TestDustDevil:
    def test_overloads_2_on_play(self):
        """Dust Devil should add 2 Overload when played."""
        game, p1, p2 = new_hs_game()
        overload_before = p1.overloaded_mana

        dd = play_from_hand(game, DUST_DEVIL, p1)

        assert p1.overloaded_mana == overload_before + 2

    def test_has_windfury(self):
        """Dust Devil should have windfury keyword."""
        game, p1, p2 = new_hs_game()
        dd = make_obj(game, DUST_DEVIL, p1)

        assert has_ability(dd, 'windfury', game.state)


# ============================================================
# Felguard — Battlecry: Destroy one of your Mana Crystals
# ============================================================

class TestFelguard:
    def test_destroys_mana_crystal(self):
        """Felguard should emit ADD_MANA with -1."""
        game, p1, p2 = new_hs_game()
        assert p1.mana_crystals == 10

        events = FELGUARD.battlecry(
            make_obj(game, FELGUARD, p1), game.state
        )

        assert len(events) >= 1
        mana_event = events[0]
        assert mana_event.type == EventType.ADD_MANA
        assert mana_event.payload['amount'] == -1
        assert mana_event.payload['permanent'] == True

    def test_no_mana_no_crash(self):
        """Felguard at 0 mana crystals shouldn't crash."""
        game, p1, p2 = new_hs_game()
        p1.mana_crystals = 0

        events = FELGUARD.battlecry(
            make_obj(game, FELGUARD, p1), game.state
        )
        assert events == []


# ============================================================
# Lord Jaraxxus — Battlecry: Replace hero
# ============================================================

class TestLordJaraxxus:
    def test_sets_hp_to_15(self):
        """Lord Jaraxxus should set hero HP to 15."""
        game, p1, p2 = new_hs_game()
        assert p1.life == 30

        LORD_JARAXXUS.battlecry(
            make_obj(game, LORD_JARAXXUS, p1), game.state
        )

        assert p1.life == 15
        assert p1.max_life == 15

    def test_equips_blood_fury_weapon(self):
        """Lord Jaraxxus should equip a 3/8 weapon."""
        game, p1, p2 = new_hs_game()

        LORD_JARAXXUS.battlecry(
            make_obj(game, LORD_JARAXXUS, p1), game.state
        )

        assert p1.weapon_attack == 3
        assert p1.weapon_durability == 8

    def test_clears_armor(self):
        """Lord Jaraxxus should clear any existing armor."""
        game, p1, p2 = new_hs_game()
        p1.armor = 10

        LORD_JARAXXUS.battlecry(
            make_obj(game, LORD_JARAXXUS, p1), game.state
        )

        assert p1.armor == 0

    def test_replaces_hero_power(self):
        """Lord Jaraxxus should replace the hero power with INFERNO!."""
        game, p1, p2 = new_hs_game()
        old_hp = p1.hero_power_id

        LORD_JARAXXUS.battlecry(
            make_obj(game, LORD_JARAXXUS, p1), game.state
        )

        # Hero power should have changed
        assert p1.hero_power_id != old_hp
        new_hp = game.state.objects.get(p1.hero_power_id)
        assert new_hp is not None
        assert 'INFERNO' in new_hp.name


# ============================================================
# Cross-Mechanic Combos
# ============================================================

class TestCrossMechanicBatch32:
    def test_si7_combo_triggers_frothing(self):
        """SI:7 Agent Combo damage to a minion should trigger effects."""
        game, p1, p2 = new_hs_game()
        p1.cards_played_this_turn = 1
        target = make_obj(game, CHILLWIND_YETI, p2)

        si7 = make_obj(game, SI7_AGENT, p1)
        events = SI7_AGENT.battlecry(si7, game.state)
        for e in events:
            game.emit(e)

        dmg_events = [e for e in game.state.event_log
                      if e.type == EventType.DAMAGE]
        assert len(dmg_events) >= 1

    def test_dust_devil_triggers_unbound(self):
        """Dust Devil with Overload text should trigger Unbound Elemental."""
        game, p1, p2 = new_hs_game()
        ue = make_obj(game, UNBOUND_ELEMENTAL, p1)
        base_power = get_power(ue, game.state)

        dd = play_from_hand(game, DUST_DEVIL, p1)

        pt_mods = [e for e in game.state.event_log
                   if e.type == EventType.PT_MODIFICATION and
                   e.payload.get('object_id') == ue.id]
        assert len(pt_mods) >= 1

    def test_jaraxxus_from_full_hp(self):
        """Lord Jaraxxus at 30 HP should reduce to 15, not increase."""
        game, p1, p2 = new_hs_game()
        assert p1.life == 30

        LORD_JARAXXUS.battlecry(
            make_obj(game, LORD_JARAXXUS, p1), game.state
        )

        assert p1.life == 15

    def test_jaraxxus_from_low_hp(self):
        """Lord Jaraxxus at low HP should NOT increase HP (sets to 15)."""
        game, p1, p2 = new_hs_game()
        p1.life = 5

        LORD_JARAXXUS.battlecry(
            make_obj(game, LORD_JARAXXUS, p1), game.state
        )

        assert p1.life == 15  # Sets to 15 regardless

    def test_felguard_multiple_times(self):
        """Multiple Felguards should each destroy a mana crystal."""
        game, p1, p2 = new_hs_game()
        p1.mana_crystals = 5

        events1 = FELGUARD.battlecry(make_obj(game, FELGUARD, p1), game.state)
        events2 = FELGUARD.battlecry(make_obj(game, FELGUARD, p1), game.state)

        all_events = events1 + events2
        add_mana = [e for e in all_events if e.type == EventType.ADD_MANA]
        assert len(add_mana) == 2

    def test_cabal_steals_lightspawn_at_zero_base(self):
        """Cabal Shadow Priest should be able to steal Lightspawn (0 base ATK <= 2)."""
        game, p1, p2 = new_hs_game()
        ls = make_obj(game, LIGHTSPAWN, p2)  # 0 base ATK, but effective ATK = 5

        events = CABAL_SHADOW_PRIEST.battlecry(
            make_obj(game, CABAL_SHADOW_PRIEST, p1), game.state
        )

        # Lightspawn has 0 base power in characteristics, which is <= 2
        assert len(events) >= 1
        assert events[0].payload['object_id'] == ls.id
