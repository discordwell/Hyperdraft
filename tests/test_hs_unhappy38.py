"""
Hearthstone Unhappy Path Tests - Batch 38

Warlock spell mechanics: Soulfire (4 damage + discard), Mortal Coil (1 damage,
draw if kills), Power Overwhelming (+4/+4 then dies), Demonfire (2 damage OR
+2/+2 demon buff), Shadowflame (sacrifice + AOE damage).
Legendary battlecries: Alexstrasza (set hero HP to 15), Leeroy Jenkins (charge
+ 2 whelps for opponent), Deathwing (destroy all + discard hand), Onyxia (fill
board with whelps), Stampeding Kodo (destroy <=2 ATK minion), Coldlight Oracle
(both draw 2), Mind Control Tech (steal if 4+ enemy minions).
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

from src.cards.hearthstone.basic import WISP, CHILLWIND_YETI, BLOODFEN_RAPTOR
from src.cards.hearthstone.classic import (
    ALEXSTRASZA, LEEROY_JENKINS, DEATHWING, ONYXIA,
    STAMPEDING_KODO, COLDLIGHT_ORACLE, MIND_CONTROL_TECH,
)
from src.cards.hearthstone.warlock import (
    SOULFIRE, MORTAL_COIL, POWER_OVERWHELMING, DEMONFIRE, SHADOWFLAME,
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
# Soulfire — 4 damage + discard
# ============================================================

class TestSoulfire:
    def test_deals_4_damage(self):
        """Soulfire should deal 4 damage to a random enemy."""
        game, p1, p2 = new_hs_game()
        target = make_obj(game, CHILLWIND_YETI, p2)

        cast_spell_full(game, SOULFIRE, p1)

        dmg_events = [e for e in game.state.event_log
                      if e.type == EventType.DAMAGE and
                      e.payload.get('amount') == 4 and
                      e.payload.get('from_spell') is True]
        assert len(dmg_events) >= 1

    def test_discards_when_hand_has_cards(self):
        """Soulfire should discard a card if hand is not empty."""
        game, p1, p2 = new_hs_game()
        hand_card = make_obj(game, WISP, p1, zone=ZoneType.HAND)

        cast_spell_full(game, SOULFIRE, p1)

        discard_events = [e for e in game.state.event_log
                          if e.type == EventType.DISCARD and
                          e.payload.get('player') == p1.id]
        assert len(discard_events) >= 1

    def test_no_discard_with_empty_hand(self):
        """Soulfire with empty hand should not discard."""
        game, p1, p2 = new_hs_game()
        # No cards in hand

        obj = game.create_object(
            name=SOULFIRE.name, owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
            characteristics=SOULFIRE.characteristics, card_def=SOULFIRE
        )
        events = SOULFIRE.spell_effect(obj, game.state, [])

        discard_events = [e for e in events if e.type == EventType.DISCARD]
        assert len(discard_events) == 0


# ============================================================
# Mortal Coil — 1 damage, draw if kills
# ============================================================

class TestMortalCoil:
    def test_deals_1_damage(self):
        """Mortal Coil should deal 1 damage to a random enemy minion."""
        game, p1, p2 = new_hs_game()
        target = make_obj(game, CHILLWIND_YETI, p2)

        cast_spell_full(game, MORTAL_COIL, p1)

        dmg_events = [e for e in game.state.event_log
                      if e.type == EventType.DAMAGE and
                      e.payload.get('amount') == 1 and
                      e.payload.get('from_spell') is True]
        assert len(dmg_events) >= 1

    def test_draws_when_kills(self):
        """Mortal Coil should draw a card when it kills a minion."""
        game, p1, p2 = new_hs_game()
        target = make_obj(game, WISP, p2)  # 1/1 — will die to 1 damage

        cast_spell_full(game, MORTAL_COIL, p1)

        draw_events = [e for e in game.state.event_log
                       if e.type == EventType.DRAW and
                       e.payload.get('player') == p1.id]
        assert len(draw_events) >= 1

    def test_no_draw_when_doesnt_kill(self):
        """Mortal Coil should NOT draw when target survives."""
        game, p1, p2 = new_hs_game()
        target = make_obj(game, CHILLWIND_YETI, p2)  # 4/5 — survives

        obj = game.create_object(
            name=MORTAL_COIL.name, owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
            characteristics=MORTAL_COIL.characteristics, card_def=MORTAL_COIL
        )
        events = MORTAL_COIL.spell_effect(obj, game.state, [])

        draw_events = [e for e in events if e.type == EventType.DRAW]
        assert len(draw_events) == 0


# ============================================================
# Power Overwhelming — +4/+4 then dies at end of turn
# ============================================================

class TestPowerOverwhelming:
    def test_buffs_friendly_minion(self):
        """Power Overwhelming should give +4/+4 to a friendly minion."""
        game, p1, p2 = new_hs_game()
        target = make_obj(game, WISP, p1)

        cast_spell_full(game, POWER_OVERWHELMING, p1)

        pt_events = [e for e in game.state.event_log
                     if e.type == EventType.PT_MODIFICATION and
                     e.payload.get('power_mod') == 4 and
                     e.payload.get('toughness_mod') == 4]
        assert len(pt_events) >= 1

    def test_registers_death_interceptor(self):
        """Power Overwhelming should register end-of-turn death interceptor."""
        game, p1, p2 = new_hs_game()
        target = make_obj(game, WISP, p1)
        interceptors_before = len(game.state.interceptors)

        cast_spell_full(game, POWER_OVERWHELMING, p1)

        assert len(game.state.interceptors) > interceptors_before

    def test_no_friendly_minions_no_crash(self):
        """Power Overwhelming with no friendly minions should not crash."""
        game, p1, p2 = new_hs_game()
        obj = game.create_object(
            name=POWER_OVERWHELMING.name, owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
            characteristics=POWER_OVERWHELMING.characteristics, card_def=POWER_OVERWHELMING
        )
        events = POWER_OVERWHELMING.spell_effect(obj, game.state, [])
        assert events == []


# ============================================================
# Demonfire — 2 damage OR buff friendly Demon +2/+2
# ============================================================

class TestDemonfire:
    def test_damages_enemy_when_no_demons(self):
        """Demonfire should deal 2 damage to enemy when no friendly Demons."""
        game, p1, p2 = new_hs_game()
        target = make_obj(game, CHILLWIND_YETI, p2)

        cast_spell_full(game, DEMONFIRE, p1)

        dmg_events = [e for e in game.state.event_log
                      if e.type == EventType.DAMAGE and
                      e.payload.get('amount') == 2 and
                      e.payload.get('from_spell') is True]
        assert len(dmg_events) >= 1

    def test_buffs_friendly_demon(self):
        """Demonfire should give +2/+2 to a friendly Demon."""
        game, p1, p2 = new_hs_game()
        # Create a demon
        demon = game.create_object(
            name="Test Demon", owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
            characteristics=CHILLWIND_YETI.characteristics, card_def=CHILLWIND_YETI
        )
        demon.characteristics.subtypes = {'Demon'}
        demon.characteristics.types = {CardType.MINION}

        cast_spell_full(game, DEMONFIRE, p1)

        pt_events = [e for e in game.state.event_log
                     if e.type == EventType.PT_MODIFICATION and
                     e.payload.get('power_mod') == 2 and
                     e.payload.get('toughness_mod') == 2]
        assert len(pt_events) >= 1


# ============================================================
# Shadowflame — Sacrifice + AOE
# ============================================================

class TestShadowflame:
    def test_destroys_friendly_and_damages_enemies(self):
        """Shadowflame should destroy a friendly minion and AOE enemies."""
        game, p1, p2 = new_hs_game()
        sacrifice = make_obj(game, CHILLWIND_YETI, p1)  # 4 ATK
        enemy = make_obj(game, BLOODFEN_RAPTOR, p2)

        cast_spell_full(game, SHADOWFLAME, p1)

        # Should destroy the friendly minion
        destroy_events = [e for e in game.state.event_log
                          if e.type == EventType.OBJECT_DESTROYED and
                          e.payload.get('object_id') == sacrifice.id]
        assert len(destroy_events) >= 1

        # Should deal the sacrifice's ATK as damage to enemies
        dmg_events = [e for e in game.state.event_log
                      if e.type == EventType.DAMAGE and
                      e.payload.get('amount') == 4]
        assert len(dmg_events) >= 1

    def test_no_friendly_minions_no_crash(self):
        """Shadowflame with no friendly minions should not crash."""
        game, p1, p2 = new_hs_game()
        obj = game.create_object(
            name=SHADOWFLAME.name, owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
            characteristics=SHADOWFLAME.characteristics, card_def=SHADOWFLAME
        )
        events = SHADOWFLAME.spell_effect(obj, game.state, [])
        assert events == []


# ============================================================
# Alexstrasza — Set hero HP to 15
# ============================================================

class TestAlexstrasza:
    def test_damages_enemy_above_15(self):
        """Alexstrasza should damage enemy hero from 30 to 15."""
        game, p1, p2 = new_hs_game()
        assert p2.life == 30

        alex = make_obj(game, ALEXSTRASZA, p1)
        events = ALEXSTRASZA.battlecry(alex, game.state)

        assert len(events) >= 1
        assert events[0].type == EventType.DAMAGE
        assert events[0].payload['amount'] == 15  # 30 - 15

    def test_heals_self_below_15(self):
        """Alexstrasza should heal own hero if below 15 and enemy is already at 15."""
        game, p1, p2 = new_hs_game()
        p2.life = 15  # Enemy already at 15
        p1.life = 10  # Self below 15

        alex = make_obj(game, ALEXSTRASZA, p1)
        events = ALEXSTRASZA.battlecry(alex, game.state)

        heal_events = [e for e in events if e.type == EventType.LIFE_CHANGE]
        assert len(heal_events) >= 1
        assert heal_events[0].payload['amount'] == 5  # 15 - 10

    def test_no_action_all_at_15(self):
        """Alexstrasza does nothing when all heroes are at or below 15."""
        game, p1, p2 = new_hs_game()
        p1.life = 15
        p2.life = 15

        alex = make_obj(game, ALEXSTRASZA, p1)
        events = ALEXSTRASZA.battlecry(alex, game.state)

        assert events == []


# ============================================================
# Leeroy Jenkins — Charge + 2 Whelps for Opponent
# ============================================================

class TestLeeroyJenkins:
    def test_has_charge(self):
        """Leeroy should have charge."""
        game, p1, p2 = new_hs_game()
        leeroy = make_obj(game, LEEROY_JENKINS, p1)
        assert has_ability(leeroy, 'charge', game.state)

    def test_summons_two_whelps_for_opponent(self):
        """Leeroy battlecry should summon 2 Whelps for the opponent."""
        game, p1, p2 = new_hs_game()
        leeroy = make_obj(game, LEEROY_JENKINS, p1)
        events = LEEROY_JENKINS.battlecry(leeroy, game.state)

        whelp_events = [e for e in events
                        if e.type == EventType.CREATE_TOKEN and
                        e.payload.get('controller') == p2.id and
                        e.payload.get('token', {}).get('name') == 'Whelp']
        assert len(whelp_events) == 2
        assert whelp_events[0].payload['token']['power'] == 1
        assert whelp_events[0].payload['token']['toughness'] == 1


# ============================================================
# Deathwing — Destroy all + discard hand
# ============================================================

class TestDeathwing:
    def test_destroys_all_other_minions(self):
        """Deathwing should destroy all other minions."""
        game, p1, p2 = new_hs_game()
        m1 = make_obj(game, CHILLWIND_YETI, p1)
        m2 = make_obj(game, CHILLWIND_YETI, p2)

        dw = make_obj(game, DEATHWING, p1)
        events = DEATHWING.battlecry(dw, game.state)

        destroy_events = [e for e in events if e.type == EventType.OBJECT_DESTROYED]
        destroyed_ids = {e.payload['object_id'] for e in destroy_events}
        assert m1.id in destroyed_ids
        assert m2.id in destroyed_ids
        assert dw.id not in destroyed_ids  # Deathwing survives

    def test_discards_hand(self):
        """Deathwing should discard all cards in hand."""
        game, p1, p2 = new_hs_game()
        h1 = make_obj(game, WISP, p1, zone=ZoneType.HAND)
        h2 = make_obj(game, WISP, p1, zone=ZoneType.HAND)

        dw = make_obj(game, DEATHWING, p1)
        events = DEATHWING.battlecry(dw, game.state)

        discard_events = [e for e in events if e.type == EventType.DISCARD]
        assert len(discard_events) >= 2

    def test_empty_board_and_hand_no_crash(self):
        """Deathwing on empty board with empty hand should not crash."""
        game, p1, p2 = new_hs_game()
        dw = make_obj(game, DEATHWING, p1)
        events = DEATHWING.battlecry(dw, game.state)
        # Only heroes should be on board, no minions to destroy
        destroy_events = [e for e in events if e.type == EventType.OBJECT_DESTROYED]
        assert len(destroy_events) == 0


# ============================================================
# Onyxia — Fill board with Whelps
# ============================================================

class TestOnyxia:
    def test_fills_board_with_whelps(self):
        """Onyxia should summon Whelps up to 7 total minions."""
        game, p1, p2 = new_hs_game()
        onyxia = make_obj(game, ONYXIA, p1)
        events = ONYXIA.battlecry(onyxia, game.state)

        whelp_events = [e for e in events
                        if e.type == EventType.CREATE_TOKEN and
                        e.payload.get('token', {}).get('name') == 'Whelp']
        # Onyxia counts as 1, so 6 whelps
        assert len(whelp_events) == 6

    def test_respects_board_space(self):
        """Onyxia with existing minions should summon fewer Whelps."""
        game, p1, p2 = new_hs_game()
        m1 = make_obj(game, WISP, p1)
        m2 = make_obj(game, WISP, p1)
        m3 = make_obj(game, WISP, p1)
        onyxia = make_obj(game, ONYXIA, p1)  # 4 minions now
        events = ONYXIA.battlecry(onyxia, game.state)

        whelp_events = [e for e in events
                        if e.type == EventType.CREATE_TOKEN]
        # 4 existing (3 wisps + onyxia), so 3 whelps max
        assert len(whelp_events) <= 3


# ============================================================
# Stampeding Kodo — Destroy <=2 ATK enemy minion
# ============================================================

class TestStampedingKodo:
    def test_destroys_low_attack_minion(self):
        """Kodo should destroy an enemy minion with 2 or less ATK."""
        game, p1, p2 = new_hs_game()
        low_atk = make_obj(game, WISP, p2)  # 1/1

        kodo = make_obj(game, STAMPEDING_KODO, p1)
        events = STAMPEDING_KODO.battlecry(kodo, game.state)

        assert len(events) >= 1
        assert events[0].type == EventType.OBJECT_DESTROYED
        assert events[0].payload['object_id'] == low_atk.id

    def test_ignores_high_attack(self):
        """Kodo should not destroy enemy minions with >2 ATK."""
        game, p1, p2 = new_hs_game()
        high_atk = make_obj(game, CHILLWIND_YETI, p2)  # 4/5

        kodo = make_obj(game, STAMPEDING_KODO, p1)
        events = STAMPEDING_KODO.battlecry(kodo, game.state)

        assert events == []

    def test_no_enemies_no_crash(self):
        """Kodo with no valid targets should not crash."""
        game, p1, p2 = new_hs_game()
        kodo = make_obj(game, STAMPEDING_KODO, p1)
        events = STAMPEDING_KODO.battlecry(kodo, game.state)
        assert events == []


# ============================================================
# Coldlight Oracle — Both players draw 2
# ============================================================

class TestColdlightOracle:
    def test_both_players_draw_2(self):
        """Coldlight Oracle should make both players draw 2 cards."""
        game, p1, p2 = new_hs_game()
        cl = make_obj(game, COLDLIGHT_ORACLE, p1)
        events = COLDLIGHT_ORACLE.battlecry(cl, game.state)

        p1_draws = [e for e in events
                    if e.type == EventType.DRAW and
                    e.payload.get('player') == p1.id]
        p2_draws = [e for e in events
                    if e.type == EventType.DRAW and
                    e.payload.get('player') == p2.id]
        assert len(p1_draws) >= 1
        assert len(p2_draws) >= 1
        assert p1_draws[0].payload['count'] == 2
        assert p2_draws[0].payload['count'] == 2


# ============================================================
# Mind Control Tech — Steal if 4+ enemy minions
# ============================================================

class TestMindControlTech:
    def test_steals_with_4_plus_enemies(self):
        """MCT should steal an enemy minion when opponent has 4+ minions."""
        game, p1, p2 = new_hs_game()
        e1 = make_obj(game, WISP, p2)
        e2 = make_obj(game, WISP, p2)
        e3 = make_obj(game, WISP, p2)
        e4 = make_obj(game, WISP, p2)

        mct = make_obj(game, MIND_CONTROL_TECH, p1)
        events = MIND_CONTROL_TECH.battlecry(mct, game.state)

        steal_events = [e for e in events
                        if e.type == EventType.CONTROL_CHANGE and
                        e.payload.get('new_controller') == p1.id]
        assert len(steal_events) >= 1

    def test_no_steal_with_3_enemies(self):
        """MCT should NOT steal when opponent has fewer than 4 minions."""
        game, p1, p2 = new_hs_game()
        e1 = make_obj(game, WISP, p2)
        e2 = make_obj(game, WISP, p2)
        e3 = make_obj(game, WISP, p2)

        mct = make_obj(game, MIND_CONTROL_TECH, p1)
        events = MIND_CONTROL_TECH.battlecry(mct, game.state)

        assert events == []

    def test_no_enemies_no_crash(self):
        """MCT with no enemy minions should not crash."""
        game, p1, p2 = new_hs_game()
        mct = make_obj(game, MIND_CONTROL_TECH, p1)
        events = MIND_CONTROL_TECH.battlecry(mct, game.state)
        assert events == []
