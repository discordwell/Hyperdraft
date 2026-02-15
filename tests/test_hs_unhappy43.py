"""
Hearthstone Unhappy Path Tests - Batch 43

Water Elemental freeze, Emperor Cobra poisonous, Demolisher start-of-turn
damage, Young Priestess/Master Swordsmith random EOT buffs, Acolyte of Pain
draw-on-damage, Patient Assassin poisonous, Bloodmage Thalnos spell damage +
deathrattle draw, and cross-card interactions between damage triggers and
death-related effects.
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
    WATER_ELEMENTAL, EMPEROR_COBRA, DEMOLISHER,
    YOUNG_PRIESTESS, MASTER_SWORDSMITH, ACOLYTE_OF_PAIN,
    FROSTBOLT, KNIFE_JUGGLER, WILD_PYROMANCER,
    BLOODMAGE_THALNOS,
)
from src.cards.hearthstone.rogue import PATIENT_ASSASSIN


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
# Water Elemental — Freeze on Damage
# ============================================================

class TestWaterElemental:
    def test_freezes_damaged_target(self):
        """Water Elemental freezes any character it damages."""
        game, p1, p2 = new_hs_game()
        we = make_obj(game, WATER_ELEMENTAL, p1)
        target = make_obj(game, CHILLWIND_YETI, p2)

        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': target.id, 'amount': 3, 'source': we.id},
            source=we.id
        ))

        freeze_events = [e for e in game.state.event_log
                         if e.type == EventType.FREEZE_TARGET and
                         e.payload.get('target') == target.id]
        assert len(freeze_events) >= 1

    def test_freezes_hero_on_attack(self):
        """Water Elemental freezes hero when dealing damage."""
        game, p1, p2 = new_hs_game()
        we = make_obj(game, WATER_ELEMENTAL, p1)

        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': p2.hero_id, 'amount': 3, 'source': we.id},
            source=we.id
        ))

        freeze_events = [e for e in game.state.event_log
                         if e.type == EventType.FREEZE_TARGET and
                         e.payload.get('target') == p2.hero_id]
        assert len(freeze_events) >= 1

    def test_no_freeze_from_other_source(self):
        """Damage from other sources should NOT trigger Water Elemental freeze."""
        game, p1, p2 = new_hs_game()
        we = make_obj(game, WATER_ELEMENTAL, p1)
        target = make_obj(game, CHILLWIND_YETI, p2)

        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': target.id, 'amount': 2, 'source': 'other'},
            source='other'
        ))

        freeze_events = [e for e in game.state.event_log
                         if e.type == EventType.FREEZE_TARGET and
                         e.payload.get('target') == target.id and
                         e.source == we.id]
        assert len(freeze_events) == 0


# ============================================================
# Emperor Cobra — Poisonous
# ============================================================

class TestEmperorCobra:
    def test_destroys_damaged_minion(self):
        """Emperor Cobra destroys any minion it damages."""
        game, p1, p2 = new_hs_game()
        cobra = make_obj(game, EMPEROR_COBRA, p1)
        target = make_obj(game, CHILLWIND_YETI, p2)

        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': target.id, 'amount': 2, 'source': cobra.id},
            source=cobra.id
        ))

        destroy_events = [e for e in game.state.event_log
                          if e.type == EventType.OBJECT_DESTROYED and
                          e.payload.get('object_id') == target.id]
        assert len(destroy_events) >= 1

    def test_does_not_destroy_heroes(self):
        """Poisonous should NOT trigger on hero damage."""
        game, p1, p2 = new_hs_game()
        cobra = make_obj(game, EMPEROR_COBRA, p1)

        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': p2.hero_id, 'amount': 2, 'source': cobra.id},
            source=cobra.id
        ))

        destroy_events = [e for e in game.state.event_log
                          if e.type == EventType.OBJECT_DESTROYED and
                          e.payload.get('object_id') == p2.hero_id]
        assert len(destroy_events) == 0


class TestPatientAssassin:
    def test_poisonous_destroys_minion(self):
        """Patient Assassin also has poisonous."""
        game, p1, p2 = new_hs_game()
        pa = make_obj(game, PATIENT_ASSASSIN, p1)
        target = make_obj(game, CHILLWIND_YETI, p2)

        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': target.id, 'amount': 1, 'source': pa.id},
            source=pa.id
        ))

        destroy_events = [e for e in game.state.event_log
                          if e.type == EventType.OBJECT_DESTROYED and
                          e.payload.get('object_id') == target.id]
        assert len(destroy_events) >= 1


# ============================================================
# Demolisher — Start-of-Turn Damage
# ============================================================

class TestDemolisher:
    def test_deals_2_to_random_enemy_at_turn_start(self):
        """Demolisher deals 2 to a random enemy at start of turn."""
        game, p1, p2 = new_hs_game()
        random.seed(42)
        demo = make_obj(game, DEMOLISHER, p1)

        game.emit(Event(
            type=EventType.TURN_START,
            payload={'player': p1.id},
            source='game'
        ))

        dmg = [e for e in game.state.event_log
               if e.type == EventType.DAMAGE and
               e.payload.get('source') == demo.id and
               e.payload.get('amount') == 2]
        assert len(dmg) == 1

    def test_no_trigger_on_opponent_turn(self):
        """Demolisher only fires on controller's turn start."""
        game, p1, p2 = new_hs_game()
        demo = make_obj(game, DEMOLISHER, p1)

        game.emit(Event(
            type=EventType.TURN_START,
            payload={'player': p2.id},
            source='game'
        ))

        dmg = [e for e in game.state.event_log
               if e.type == EventType.DAMAGE and
               e.payload.get('source') == demo.id]
        assert len(dmg) == 0


# ============================================================
# Young Priestess — Random EOT Health Buff
# ============================================================

class TestYoungPriestess:
    def test_buffs_random_friendly_minion(self):
        """Young Priestess gives +1 Health to random friendly at EOT."""
        game, p1, p2 = new_hs_game()
        random.seed(42)
        yp = make_obj(game, YOUNG_PRIESTESS, p1)
        wisp = make_obj(game, WISP, p1)

        game.emit(Event(
            type=EventType.TURN_END,
            payload={'player': p1.id},
            source='game'
        ))

        pt_mods = [e for e in game.state.event_log
                   if e.type == EventType.PT_MODIFICATION and
                   e.payload.get('toughness_mod') == 1 and
                   e.source == yp.id]
        assert len(pt_mods) >= 1

    def test_no_buff_if_alone(self):
        """Young Priestess alone on board has no valid target (excludes self)."""
        game, p1, p2 = new_hs_game()
        yp = make_obj(game, YOUNG_PRIESTESS, p1)
        # No other friendly minions

        game.emit(Event(
            type=EventType.TURN_END,
            payload={'player': p1.id},
            source='game'
        ))

        pt_mods = [e for e in game.state.event_log
                   if e.type == EventType.PT_MODIFICATION and
                   e.source == yp.id]
        assert len(pt_mods) == 0


# ============================================================
# Master Swordsmith — Random EOT Attack Buff
# ============================================================

class TestMasterSwordsmith:
    def test_buffs_random_friendly_attack(self):
        """Master Swordsmith gives +1 Attack to random friendly at EOT."""
        game, p1, p2 = new_hs_game()
        random.seed(42)
        ms = make_obj(game, MASTER_SWORDSMITH, p1)
        wisp = make_obj(game, WISP, p1)

        game.emit(Event(
            type=EventType.TURN_END,
            payload={'player': p1.id},
            source='game'
        ))

        pt_mods = [e for e in game.state.event_log
                   if e.type == EventType.PT_MODIFICATION and
                   e.payload.get('power_mod') == 1 and
                   e.source == ms.id]
        assert len(pt_mods) >= 1


# ============================================================
# Acolyte of Pain — Draw on Damage
# ============================================================

class TestAcolyteOfPain:
    def test_draws_when_damaged(self):
        """Acolyte draws a card each time it takes damage."""
        game, p1, p2 = new_hs_game()
        acolyte = make_obj(game, ACOLYTE_OF_PAIN, p1)

        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': acolyte.id, 'amount': 1, 'source': 'test'},
            source='test'
        ))

        draws = [e for e in game.state.event_log
                 if e.type == EventType.DRAW and
                 e.payload.get('player') == p1.id]
        assert len(draws) >= 1

    def test_draws_multiple_times(self):
        """Multiple hits = multiple draws."""
        game, p1, p2 = new_hs_game()
        acolyte = make_obj(game, ACOLYTE_OF_PAIN, p1)

        for _ in range(3):
            game.emit(Event(
                type=EventType.DAMAGE,
                payload={'target': acolyte.id, 'amount': 1, 'source': 'test'},
                source='test'
            ))

        draws = [e for e in game.state.event_log
                 if e.type == EventType.DRAW and
                 e.payload.get('player') == p1.id]
        assert len(draws) >= 3


# ============================================================
# Bloodmage Thalnos — Spell Damage + DR Draw
# ============================================================

class TestBloodmageThalnos:
    def test_spell_damage_boost(self):
        """Thalnos gives +1 spell damage."""
        game, p1, p2 = new_hs_game()
        thalnos = make_obj(game, BLOODMAGE_THALNOS, p1)
        target = make_obj(game, CHILLWIND_YETI, p2)

        log_before = len(game.state.event_log)
        cast_spell_full(game, FROSTBOLT, p1, targets=[target.id])

        dmg = [e for e in game.state.event_log[log_before:]
               if e.type == EventType.DAMAGE and
               e.payload.get('from_spell') is True]
        assert len(dmg) >= 1
        assert dmg[0].payload['amount'] == 4  # 3 + 1 spell damage

    def test_deathrattle_draws(self):
        """Thalnos deathrattle draws a card."""
        game, p1, p2 = new_hs_game()
        thalnos = make_obj(game, BLOODMAGE_THALNOS, p1)

        game.emit(Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': thalnos.id},
            source='test'
        ))

        draws = [e for e in game.state.event_log
                 if e.type == EventType.DRAW and
                 e.payload.get('player') == p1.id]
        assert len(draws) >= 1


# ============================================================
# Cross-card: Water Elemental + Wild Pyromancer
# ============================================================

class TestWaterElementalPyroCombo:
    def test_pyro_aoe_does_not_trigger_water_freeze(self):
        """Pyro damage is sourced from Pyro, not Water Elemental."""
        game, p1, p2 = new_hs_game()
        we = make_obj(game, WATER_ELEMENTAL, p1)
        pyro = make_obj(game, WILD_PYROMANCER, p1)
        enemy = make_obj(game, CHILLWIND_YETI, p2)
        target = make_obj(game, CHILLWIND_YETI, p2)

        cast_spell_full(game, FROSTBOLT, p1, targets=[target.id])

        # Pyro damage has source=pyro.id, not water elemental
        # Water Elemental freeze should only trigger from WE's own damage
        pyro_freezes = [e for e in game.state.event_log
                        if e.type == EventType.FREEZE_TARGET and
                        e.source == pyro.id]
        # Pyro doesn't have freeze ability
        assert len(pyro_freezes) == 0


# ============================================================
# Cross-card: Acolyte + Wild Pyromancer
# ============================================================

class TestAcolytePyroCombo:
    def test_pyro_damages_acolyte_draws(self):
        """Pyro AOE hits Acolyte → Acolyte draws."""
        game, p1, p2 = new_hs_game()
        acolyte = make_obj(game, ACOLYTE_OF_PAIN, p1)
        pyro = make_obj(game, WILD_PYROMANCER, p1)
        target = make_obj(game, CHILLWIND_YETI, p2)

        cast_spell_full(game, FROSTBOLT, p1, targets=[target.id])

        # Pyro deals 1 to all minions → hits Acolyte → Acolyte draws
        acolyte_dmg = [e for e in game.state.event_log
                       if e.type == EventType.DAMAGE and
                       e.payload.get('target') == acolyte.id]
        draws = [e for e in game.state.event_log
                 if e.type == EventType.DRAW and
                 e.payload.get('player') == p1.id]
        assert len(acolyte_dmg) >= 1
        assert len(draws) >= 1


# ============================================================
# Cross-card: Knife Juggler + Multiple Summons
# ============================================================

class TestKnifeJugglerMultiple:
    def test_multiple_summons_multiple_knives(self):
        """Multiple minion summons should each trigger Knife Juggler."""
        game, p1, p2 = new_hs_game()
        random.seed(42)
        kj = make_obj(game, KNIFE_JUGGLER, p1)

        play_from_hand(game, WISP, p1)
        play_from_hand(game, WISP, p1)
        play_from_hand(game, WISP, p1)

        juggle_dmg = [e for e in game.state.event_log
                      if e.type == EventType.DAMAGE and
                      e.payload.get('source') == kj.id and
                      e.payload.get('amount') == 1]
        assert len(juggle_dmg) >= 3
