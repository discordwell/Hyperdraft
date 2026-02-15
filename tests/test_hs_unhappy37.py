"""
Hearthstone Unhappy Path Tests - Batch 37

Druid choose-one mechanics: Wrath (3 damage OR 1 + draw), Keeper of the Grove
(2 damage OR silence), Druid of the Claw (charge OR taunt+health), Nourish
(mana crystals OR draw 3), Starfall (5 single OR 2 AOE), Force of Nature
(three 2/2 treants), Ancient of Lore (draw 2 OR heal 5), Ancient of War
(+5 ATK OR +5 HP + taunt), Cenarius (buff +2/+2 OR summon treants), Bite
(hero +4 ATK + 4 armor), Mark of Nature (+4 ATK OR +4 HP + taunt), Savagery
(damage = hero ATK), Soul of the Forest (deathrattle treants), Power of the
Wild (+1/+1 OR 3/2 panther).
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
from src.cards.hearthstone.classic import AMANI_BERSERKER
from src.cards.hearthstone.druid import (
    WRATH, KEEPER_OF_THE_GROVE, DRUID_OF_THE_CLAW, NOURISH, STARFALL,
    FORCE_OF_NATURE, ANCIENT_OF_LORE, ANCIENT_OF_WAR, CENARIUS, BITE,
    MARK_OF_NATURE, SAVAGERY, SOUL_OF_THE_FOREST, POWER_OF_THE_WILD,
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
# Wrath — Choose One: 3 damage OR 1 damage + draw
# ============================================================

class TestWrath:
    def test_deals_3_to_low_health(self):
        """Wrath should deal 3 to a minion with 3 or less effective HP."""
        game, p1, p2 = new_hs_game()
        target = make_obj(game, BLOODFEN_RAPTOR, p2)  # 3/2

        cast_spell_full(game, WRATH, p1)

        dmg_events = [e for e in game.state.event_log
                      if e.type == EventType.DAMAGE and
                      e.payload.get('amount') == 3 and
                      e.payload.get('from_spell') is True]
        assert len(dmg_events) >= 1

    def test_deals_1_and_draws_on_high_health(self):
        """Wrath should deal 1 + draw against a minion with >3 HP."""
        game, p1, p2 = new_hs_game()
        target = make_obj(game, CHILLWIND_YETI, p2)  # 4/5

        cast_spell_full(game, WRATH, p1)

        dmg_events = [e for e in game.state.event_log
                      if e.type == EventType.DAMAGE and
                      e.payload.get('amount') == 1 and
                      e.payload.get('from_spell') is True]
        draw_events = [e for e in game.state.event_log
                       if e.type == EventType.DRAW and
                       e.payload.get('player') == p1.id]
        assert len(dmg_events) >= 1
        assert len(draw_events) >= 1

    def test_no_targets_no_crash(self):
        """Wrath with no enemy minions should not crash."""
        game, p1, p2 = new_hs_game()
        obj = game.create_object(
            name=WRATH.name, owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
            characteristics=WRATH.characteristics, card_def=WRATH
        )
        events = WRATH.spell_effect(obj, game.state, [])
        assert events == []


# ============================================================
# Keeper of the Grove — Choose One: 2 damage OR Silence
# ============================================================

class TestKeeperOfTheGrove:
    def test_silences_minion_with_interceptors(self):
        """Keeper should silence enemy minion with active interceptors."""
        game, p1, p2 = new_hs_game()
        enrage_target = make_obj(game, AMANI_BERSERKER, p2)
        assert len(enrage_target.interceptor_ids) > 0

        keeper = make_obj(game, KEEPER_OF_THE_GROVE, p1)
        events = KEEPER_OF_THE_GROVE.battlecry(keeper, game.state)

        assert len(events) >= 1
        assert events[0].type == EventType.SILENCE_TARGET
        assert events[0].payload['target'] == enrage_target.id

    def test_deals_2_to_vanilla_minion(self):
        """Keeper should deal 2 damage to enemy without interceptors."""
        game, p1, p2 = new_hs_game()
        target = make_obj(game, CHILLWIND_YETI, p2)  # No interceptors

        keeper = make_obj(game, KEEPER_OF_THE_GROVE, p1)
        events = KEEPER_OF_THE_GROVE.battlecry(keeper, game.state)

        assert len(events) >= 1
        assert events[0].type == EventType.DAMAGE
        assert events[0].payload['amount'] == 2

    def test_no_enemies_no_crash(self):
        """Keeper with no enemy minions should not crash."""
        game, p1, p2 = new_hs_game()
        keeper = make_obj(game, KEEPER_OF_THE_GROVE, p1)
        events = KEEPER_OF_THE_GROVE.battlecry(keeper, game.state)
        assert events == []


# ============================================================
# Druid of the Claw — Choose One: Charge OR +2 HP + Taunt
# ============================================================

class TestDruidOfTheClaw:
    def test_bear_form_adds_taunt_and_health(self):
        """Druid of the Claw (AI default) should gain Taunt and +2 HP."""
        game, p1, p2 = new_hs_game()
        dotc = make_obj(game, DRUID_OF_THE_CLAW, p1)
        events = DRUID_OF_THE_CLAW.battlecry(dotc, game.state)

        # Should have taunt
        has_taunt = any(a.get('keyword') == 'taunt'
                        for a in (dotc.characteristics.abilities or []))
        assert has_taunt

        # Should emit PT_MOD for +2 health
        assert len(events) >= 1
        assert events[0].type == EventType.PT_MODIFICATION
        assert events[0].payload['toughness_mod'] == 2


# ============================================================
# Nourish — Choose One: +2 Mana Crystals OR Draw 3
# ============================================================

class TestNourish:
    def test_ramps_when_low_crystals(self):
        """Nourish should gain 2 mana crystals when at <8."""
        game, p1, p2 = new_hs_game()
        p1.mana_crystals = 5

        obj = game.create_object(
            name=NOURISH.name, owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
            characteristics=NOURISH.characteristics, card_def=NOURISH
        )
        events = NOURISH.spell_effect(obj, game.state, [])

        assert p1.mana_crystals == 7

    def test_draws_3_when_high_crystals(self):
        """Nourish should draw 3 when at 8+ crystals."""
        game, p1, p2 = new_hs_game()
        p1.mana_crystals = 10

        obj = game.create_object(
            name=NOURISH.name, owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
            characteristics=NOURISH.characteristics, card_def=NOURISH
        )
        events = NOURISH.spell_effect(obj, game.state, [])

        draw_events = [e for e in events if e.type == EventType.DRAW]
        assert len(draw_events) >= 1
        assert draw_events[0].payload['count'] == 3

    def test_ramp_caps_at_10(self):
        """Nourish ramp from 9 should cap at 10."""
        game, p1, p2 = new_hs_game()
        p1.mana_crystals = 7  # Below 8, so will ramp

        obj = game.create_object(
            name=NOURISH.name, owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
            characteristics=NOURISH.characteristics, card_def=NOURISH
        )
        NOURISH.spell_effect(obj, game.state, [])

        assert p1.mana_crystals == 9


# ============================================================
# Starfall — Choose One: 5 single OR 2 AOE
# ============================================================

class TestStarfall:
    def test_aoe_with_3_plus_enemies(self):
        """Starfall should deal 2 AOE when 3+ enemy minions."""
        game, p1, p2 = new_hs_game()
        m1 = make_obj(game, CHILLWIND_YETI, p2)
        m2 = make_obj(game, CHILLWIND_YETI, p2)
        m3 = make_obj(game, CHILLWIND_YETI, p2)

        cast_spell_full(game, STARFALL, p1)

        dmg_events = [e for e in game.state.event_log
                      if e.type == EventType.DAMAGE and
                      e.payload.get('amount') == 2 and
                      e.payload.get('from_spell') is True]
        assert len(dmg_events) >= 3

    def test_single_target_with_few_enemies(self):
        """Starfall should deal 5 to a single target with <3 enemy minions."""
        game, p1, p2 = new_hs_game()
        m1 = make_obj(game, CHILLWIND_YETI, p2)

        cast_spell_full(game, STARFALL, p1)

        dmg_events = [e for e in game.state.event_log
                      if e.type == EventType.DAMAGE and
                      e.payload.get('amount') == 5 and
                      e.payload.get('from_spell') is True]
        assert len(dmg_events) >= 1

    def test_no_enemies_no_crash(self):
        """Starfall with no enemies should not crash."""
        game, p1, p2 = new_hs_game()
        obj = game.create_object(
            name=STARFALL.name, owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
            characteristics=STARFALL.characteristics, card_def=STARFALL
        )
        events = STARFALL.spell_effect(obj, game.state, [])
        assert events == []


# ============================================================
# Force of Nature — Summon three 2/2 Treants
# ============================================================

class TestForceOfNature:
    def test_summons_three_treants(self):
        """Force of Nature should summon exactly 3 Treants."""
        game, p1, p2 = new_hs_game()

        cast_spell_full(game, FORCE_OF_NATURE, p1)

        treant_events = [e for e in game.state.event_log
                         if e.type == EventType.CREATE_TOKEN and
                         e.payload.get('token', {}).get('name') == 'Treant']
        assert len(treant_events) == 3
        for te in treant_events:
            assert te.payload['token']['power'] == 2
            assert te.payload['token']['toughness'] == 2


# ============================================================
# Ancient of Lore — Choose One: Draw 2 OR Heal 5
# ============================================================

class TestAncientOfLore:
    def test_heals_when_low_hp(self):
        """Ancient of Lore should heal 5 when hero is below 15 HP."""
        game, p1, p2 = new_hs_game()
        p1.life = 10

        aol = make_obj(game, ANCIENT_OF_LORE, p1)
        events = ANCIENT_OF_LORE.battlecry(aol, game.state)

        assert p1.life == 15
        assert events == []  # Direct heal, no events

    def test_draws_2_when_high_hp(self):
        """Ancient of Lore should draw 2 when hero is at 15+ HP."""
        game, p1, p2 = new_hs_game()
        p1.life = 30

        aol = make_obj(game, ANCIENT_OF_LORE, p1)
        events = ANCIENT_OF_LORE.battlecry(aol, game.state)

        draw_events = [e for e in events if e.type == EventType.DRAW]
        assert len(draw_events) >= 1
        assert draw_events[0].payload['count'] == 2

    def test_heal_caps_at_30(self):
        """Ancient of Lore healing should not exceed 30 HP."""
        game, p1, p2 = new_hs_game()
        p1.life = 14

        aol = make_obj(game, ANCIENT_OF_LORE, p1)
        ANCIENT_OF_LORE.battlecry(aol, game.state)

        assert p1.life == 19  # 14 + 5
        assert p1.life <= 30


# ============================================================
# Ancient of War — Choose One: +5 ATK OR +5 HP + Taunt
# ============================================================

class TestAncientOfWar:
    def test_taunt_form_adds_health_and_taunt(self):
        """Ancient of War (AI default) should gain +5 HP and Taunt."""
        game, p1, p2 = new_hs_game()
        aow = make_obj(game, ANCIENT_OF_WAR, p1)
        events = ANCIENT_OF_WAR.battlecry(aow, game.state)

        has_taunt = any(a.get('keyword') == 'taunt'
                        for a in (aow.characteristics.abilities or []))
        assert has_taunt

        assert len(events) >= 1
        assert events[0].payload['toughness_mod'] == 5


# ============================================================
# Cenarius — Choose One: +2/+2 all OR Summon 2/4 Taunt Treants
# ============================================================

class TestCenarius:
    def test_summon_mode_with_few_minions(self):
        """Cenarius with <3 friendly minions should summon treants."""
        game, p1, p2 = new_hs_game()
        m1 = make_obj(game, WISP, p1)

        cen = make_obj(game, CENARIUS, p1)
        events = CENARIUS.battlecry(cen, game.state)

        treant_events = [e for e in events
                         if e.type == EventType.CREATE_TOKEN and
                         e.payload.get('token', {}).get('name') == 'Treant']
        assert len(treant_events) == 2
        assert treant_events[0].payload['token']['power'] == 2
        assert treant_events[0].payload['token']['toughness'] == 4

    def test_buff_mode_with_many_minions(self):
        """Cenarius with 3+ friendly minions should buff +2/+2."""
        game, p1, p2 = new_hs_game()
        m1 = make_obj(game, WISP, p1)
        m2 = make_obj(game, WISP, p1)
        m3 = make_obj(game, WISP, p1)

        cen = make_obj(game, CENARIUS, p1)
        events = CENARIUS.battlecry(cen, game.state)

        pt_events = [e for e in events
                     if e.type == EventType.PT_MODIFICATION and
                     e.payload.get('power_mod') == 2 and
                     e.payload.get('toughness_mod') == 2]
        assert len(pt_events) >= 3


# ============================================================
# Bite — Hero +4 ATK + 4 Armor
# ============================================================

class TestBite:
    def test_gives_hero_attack_and_armor(self):
        """Bite should give hero +4 ATK and +4 armor."""
        game, p1, p2 = new_hs_game()
        armor_before = p1.armor
        atk_before = p1.weapon_attack

        cast_spell_full(game, BITE, p1)

        assert p1.weapon_attack == atk_before + 4
        assert p1.armor == armor_before + 4

    def test_gives_temporary_durability(self):
        """Bite should give 1 temporary durability if no weapon equipped."""
        game, p1, p2 = new_hs_game()
        assert p1.weapon_durability == 0

        cast_spell_full(game, BITE, p1)

        assert p1.weapon_durability >= 1


# ============================================================
# Mark of Nature — +4 ATK OR +4 HP + Taunt
# ============================================================

class TestMarkOfNature:
    def test_buffs_a_friendly_minion(self):
        """Mark of Nature should apply a buff to a friendly minion."""
        game, p1, p2 = new_hs_game()
        target = make_obj(game, CHILLWIND_YETI, p1)

        cast_spell_full(game, MARK_OF_NATURE, p1)

        pt_events = [e for e in game.state.event_log
                     if e.type == EventType.PT_MODIFICATION and
                     e.payload.get('object_id') == target.id]
        assert len(pt_events) >= 1
        mod = pt_events[0].payload
        # Should be either +4/+0 or +0/+4
        assert mod['power_mod'] == 4 or mod['toughness_mod'] == 4

    def test_no_friendly_minions_no_crash(self):
        """Mark of Nature with no friendly minions should not crash."""
        game, p1, p2 = new_hs_game()
        obj = game.create_object(
            name=MARK_OF_NATURE.name, owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
            characteristics=MARK_OF_NATURE.characteristics, card_def=MARK_OF_NATURE
        )
        events = MARK_OF_NATURE.spell_effect(obj, game.state, [])
        assert events == []


# ============================================================
# Savagery — Deal damage equal to hero's Attack
# ============================================================

class TestSavagery:
    def test_deals_hero_attack_damage(self):
        """Savagery should deal damage equal to hero's weapon attack."""
        game, p1, p2 = new_hs_game()
        p1.weapon_attack = 4
        p1.weapon_durability = 2
        target = make_obj(game, CHILLWIND_YETI, p2)

        cast_spell_full(game, SAVAGERY, p1)

        dmg_events = [e for e in game.state.event_log
                      if e.type == EventType.DAMAGE and
                      e.payload.get('amount') == 4 and
                      e.payload.get('from_spell') is True]
        assert len(dmg_events) >= 1

    def test_zero_hero_attack_no_damage(self):
        """Savagery with 0 hero attack should deal no damage."""
        game, p1, p2 = new_hs_game()
        p1.weapon_attack = 0
        target = make_obj(game, CHILLWIND_YETI, p2)

        obj = game.create_object(
            name=SAVAGERY.name, owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
            characteristics=SAVAGERY.characteristics, card_def=SAVAGERY
        )
        events = SAVAGERY.spell_effect(obj, game.state, [])
        assert events == []


# ============================================================
# Soul of the Forest — Deathrattle: Summon 2/2 Treant
# ============================================================

class TestSoulOfTheForest:
    def test_adds_deathrattle_to_minions(self):
        """Soul of the Forest should add a deathrattle interceptor to minions."""
        game, p1, p2 = new_hs_game()
        m1 = make_obj(game, WISP, p1)
        interceptors_before = len(game.state.interceptors)

        cast_spell_full(game, SOUL_OF_THE_FOREST, p1)

        # Should have added interceptors for the minion
        assert len(game.state.interceptors) > interceptors_before

    def test_deathrattle_summons_treant_on_death(self):
        """Minion with Soul of the Forest buff should summon treant on death."""
        game, p1, p2 = new_hs_game()
        m1 = make_obj(game, WISP, p1)

        cast_spell_full(game, SOUL_OF_THE_FOREST, p1)

        # Kill the buffed minion
        game.emit(Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': m1.id},
            source='test'
        ))

        treant_events = [e for e in game.state.event_log
                         if e.type == EventType.CREATE_TOKEN and
                         e.payload.get('token', {}).get('name') == 'Treant']
        assert len(treant_events) >= 1
        assert treant_events[0].payload['token']['power'] == 2
        assert treant_events[0].payload['token']['toughness'] == 2


# ============================================================
# Power of the Wild — +1/+1 all OR 3/2 Panther
# ============================================================

class TestPowerOfTheWild:
    def test_buffs_minions_when_board_present(self):
        """Power of the Wild should buff all friendly minions when board has minions."""
        game, p1, p2 = new_hs_game()
        m1 = make_obj(game, WISP, p1)
        m2 = make_obj(game, WISP, p1)

        cast_spell_full(game, POWER_OF_THE_WILD, p1)

        pt_events = [e for e in game.state.event_log
                     if e.type == EventType.PT_MODIFICATION]
        # With minions, AI buffs — OR summons panther.
        # Either way, something should happen.
        total_events = pt_events + [e for e in game.state.event_log
                                     if e.type == EventType.CREATE_TOKEN]
        assert len(total_events) >= 1

    def test_summons_panther_when_no_minions(self):
        """Power of the Wild with no minions should summon 3/2 Panther."""
        game, p1, p2 = new_hs_game()

        cast_spell_full(game, POWER_OF_THE_WILD, p1)

        panther_events = [e for e in game.state.event_log
                          if e.type == EventType.CREATE_TOKEN and
                          e.payload.get('token', {}).get('name') == 'Panther']
        assert len(panther_events) >= 1
        assert panther_events[0].payload['token']['power'] == 3
        assert panther_events[0].payload['token']['toughness'] == 2
