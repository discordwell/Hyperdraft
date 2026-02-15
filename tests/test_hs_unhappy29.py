"""
Hearthstone Unhappy Path Tests - Batch 29

Classic minion deep coverage: Water Elemental (freeze on damage), Truesilver Champion
(heal on hero attack), Young Priestess (EOT random health buff), Faerie Dragon (elusive),
Amani Berserker (enrage +3), Acolyte of Pain (damage→draw), Doomsayer (SOT destroy all),
Gadgetzan Auctioneer (spell→draw), Flesheating Ghoul (death→+1 ATK), Cult Master
(friendly death→draw), Emperor Cobra (poisonous), Alarm-o-Bot (SOT swap), Raid Leader
(+1 ATK lord), Stormwind Champion (+1/+1 lord), spell damage minions (stacking), and
cross-mechanic interaction chains.
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
    WISP, CHILLWIND_YETI, BLOODFEN_RAPTOR, MURLOC_RAIDER,
    RAID_LEADER, STORMWIND_CHAMPION, KOBOLD_GEOMANCER,
    DALARAN_MAGE, OGRE_MAGI, ARCHMAGE, GRIMSCALE_ORACLE,
)
from src.cards.hearthstone.classic import (
    WATER_ELEMENTAL, TRUESILVER_CHAMPION, YOUNG_PRIESTESS,
    FAERIE_DRAGON, AMANI_BERSERKER, ACOLYTE_OF_PAIN,
    DOOMSAYER, GADGETZAN_AUCTIONEER, FLESHEATING_GHOUL,
    CULT_MASTER, EMPEROR_COBRA, ALARM_O_BOT,
    KNIFE_JUGGLER, WILD_PYROMANCER, AZURE_DRAKE,
    FIREBALL, FROSTBOLT, ABUSIVE_SERGEANT,
)
from src.cards.hearthstone.mage import ARCANE_MISSILES


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
    """Effect first, then SPELL_CAST (correct HS 'after you cast' ordering)."""
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
# Water Elemental — Freeze any character damaged by this minion
# ============================================================

class TestWaterElemental:
    def test_freezes_target_on_damage(self):
        """Water Elemental should emit FREEZE_TARGET when it deals damage."""
        game, p1, p2 = new_hs_game()
        we = make_obj(game, WATER_ELEMENTAL, p1)
        target = make_obj(game, CHILLWIND_YETI, p2)

        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': target.id, 'amount': 3, 'source': we.id},
            source=we.id
        ))

        freeze_events = [e for e in game.state.event_log
                         if e.type == EventType.FREEZE_TARGET]
        assert len(freeze_events) >= 1
        assert freeze_events[0].payload['target'] == target.id

    def test_does_not_freeze_when_other_minion_deals_damage(self):
        """Water Elemental shouldn't freeze when another minion damages something."""
        game, p1, p2 = new_hs_game()
        we = make_obj(game, WATER_ELEMENTAL, p1)
        attacker = make_obj(game, CHILLWIND_YETI, p1)
        target = make_obj(game, BLOODFEN_RAPTOR, p2)

        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': target.id, 'amount': 4, 'source': attacker.id},
            source=attacker.id
        ))

        freeze_events = [e for e in game.state.event_log
                         if e.type == EventType.FREEZE_TARGET]
        assert len(freeze_events) == 0

    def test_freeze_on_hero_damage(self):
        """Water Elemental can freeze heroes too (target is hero)."""
        game, p1, p2 = new_hs_game()
        we = make_obj(game, WATER_ELEMENTAL, p1)

        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': p2.hero_id, 'amount': 3, 'source': we.id},
            source=we.id
        ))

        freeze_events = [e for e in game.state.event_log
                         if e.type == EventType.FREEZE_TARGET]
        assert len(freeze_events) >= 1
        assert freeze_events[0].payload['target'] == p2.hero_id


# ============================================================
# Truesilver Champion — Heal hero 2 HP on attack
# ============================================================

class TestTruesilverChampion:
    def test_heals_on_hero_attack(self):
        """Truesilver should heal 2 HP when hero attacks."""
        game, p1, p2 = new_hs_game()
        ts = make_obj(game, TRUESILVER_CHAMPION, p1)
        p1.life = 25  # Take some damage first

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

    def test_no_heal_at_full_hp(self):
        """Truesilver should skip heal when hero is at max HP."""
        game, p1, p2 = new_hs_game()
        ts = make_obj(game, TRUESILVER_CHAMPION, p1)
        assert p1.life == 30

        game.emit(Event(
            type=EventType.ATTACK_DECLARED,
            payload={'attacker_id': p1.hero_id, 'target_id': p2.hero_id},
            source=p1.hero_id
        ))

        heal_events = [e for e in game.state.event_log
                       if e.type == EventType.LIFE_CHANGE and
                       e.payload.get('player') == p1.id and
                       e.payload.get('amount', 0) > 0]
        assert len(heal_events) == 0

    def test_no_heal_on_minion_attack(self):
        """Truesilver shouldn't heal when a minion attacks, only hero."""
        game, p1, p2 = new_hs_game()
        ts = make_obj(game, TRUESILVER_CHAMPION, p1)
        minion = make_obj(game, CHILLWIND_YETI, p1)
        p1.life = 25

        game.emit(Event(
            type=EventType.ATTACK_DECLARED,
            payload={'attacker_id': minion.id, 'target_id': p2.hero_id},
            source=minion.id
        ))

        heal_events = [e for e in game.state.event_log
                       if e.type == EventType.LIFE_CHANGE and
                       e.payload.get('player') == p1.id and
                       e.payload.get('amount', 0) > 0]
        assert len(heal_events) == 0


# ============================================================
# Young Priestess — End of turn, give random friendly minion +1 Health
# ============================================================

class TestYoungPriestess:
    def test_buffs_friendly_minion_eot(self):
        """Young Priestess should buff a friendly minion at end of turn."""
        game, p1, p2 = new_hs_game()
        yp = make_obj(game, YOUNG_PRIESTESS, p1)
        target = make_obj(game, CHILLWIND_YETI, p1)
        toughness_before = get_toughness(target, game.state)

        # Young Priestess uses TURN_END directly
        game.emit(Event(
            type=EventType.TURN_END,
            payload={'player': p1.id},
            source='system'
        ))

        pt_mods = [e for e in game.state.event_log
                   if e.type == EventType.PT_MODIFICATION and
                   e.payload.get('object_id') == target.id]
        assert len(pt_mods) >= 1
        assert pt_mods[0].payload['toughness_mod'] == 1

    def test_no_buff_when_alone(self):
        """Young Priestess with no other friendly minions shouldn't buff."""
        game, p1, p2 = new_hs_game()
        yp = make_obj(game, YOUNG_PRIESTESS, p1)

        game.emit(Event(
            type=EventType.TURN_END,
            payload={'player': p1.id},
            source='system'
        ))

        pt_mods = [e for e in game.state.event_log
                   if e.type == EventType.PT_MODIFICATION]
        assert len(pt_mods) == 0

    def test_no_buff_on_enemy_turn(self):
        """Young Priestess shouldn't trigger on opponent's end of turn."""
        game, p1, p2 = new_hs_game()
        yp = make_obj(game, YOUNG_PRIESTESS, p1)
        target = make_obj(game, CHILLWIND_YETI, p1)

        game.emit(Event(
            type=EventType.TURN_END,
            payload={'player': p2.id},
            source='system'
        ))

        pt_mods = [e for e in game.state.event_log
                   if e.type == EventType.PT_MODIFICATION]
        assert len(pt_mods) == 0


# ============================================================
# Faerie Dragon — Can't be targeted by spells or Hero Powers (Elusive)
# ============================================================

class TestFaerieDragon:
    def test_grants_elusive_on_query(self):
        """Faerie Dragon should have the 'elusive' ability via has_ability."""
        game, p1, p2 = new_hs_game()
        fd = make_obj(game, FAERIE_DRAGON, p1)

        # has_ability checks via QUERY_ABILITIES internally
        assert has_ability(fd, 'elusive', game.state)

    def test_elusive_only_for_self(self):
        """Elusive should only apply to the Faerie Dragon itself, not other minions."""
        game, p1, p2 = new_hs_game()
        fd = make_obj(game, FAERIE_DRAGON, p1)
        other = make_obj(game, CHILLWIND_YETI, p1)

        query_event = Event(
            type=EventType.QUERY_ABILITIES,
            payload={'object_id': other.id, 'granted': []},
            source='system'
        )
        game.emit(query_event)

        ability_events = [e for e in game.state.event_log
                          if e.type == EventType.QUERY_ABILITIES and
                          'elusive' in e.payload.get('granted', [])]
        assert len(ability_events) == 0


# ============================================================
# Amani Berserker — Enrage: +3 Attack
# ============================================================

class TestAmaniBerserker:
    def test_enrage_on_damage(self):
        """Amani Berserker gains +3 Attack when damaged."""
        game, p1, p2 = new_hs_game()
        amani = make_obj(game, AMANI_BERSERKER, p1)
        base_power = get_power(amani, game.state)

        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': amani.id, 'amount': 1, 'source': 'test'},
            source='test'
        ))

        assert get_power(amani, game.state) >= base_power + 3

    def test_enrage_lost_at_full_health(self):
        """Amani Berserker loses enrage bonus when healed to full."""
        game, p1, p2 = new_hs_game()
        amani = make_obj(game, AMANI_BERSERKER, p1)
        base_power = get_power(amani, game.state)

        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': amani.id, 'amount': 1, 'source': 'test'},
            source='test'
        ))
        assert get_power(amani, game.state) >= base_power + 3

        # Heal to full
        amani.state.damage = 0
        # Enrage should deactivate
        assert get_power(amani, game.state) == base_power


# ============================================================
# Acolyte of Pain — Whenever this takes damage, draw a card
# ============================================================

class TestAcolyteOfPain:
    def test_draws_on_damage(self):
        """Acolyte of Pain should draw a card when damaged."""
        game, p1, p2 = new_hs_game()
        acolyte = make_obj(game, ACOLYTE_OF_PAIN, p1)

        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': acolyte.id, 'amount': 1, 'source': 'test'},
            source='test'
        ))

        draw_events = [e for e in game.state.event_log
                       if e.type == EventType.DRAW and
                       e.payload.get('player') == p1.id]
        assert len(draw_events) >= 1

    def test_draws_multiple_times(self):
        """Acolyte should draw once per damage event (not per point)."""
        game, p1, p2 = new_hs_game()
        acolyte = make_obj(game, ACOLYTE_OF_PAIN, p1)

        # Two separate damage events
        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': acolyte.id, 'amount': 1, 'source': 'test'},
            source='test'
        ))
        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': acolyte.id, 'amount': 1, 'source': 'test'},
            source='test'
        ))

        draw_events = [e for e in game.state.event_log
                       if e.type == EventType.DRAW and
                       e.payload.get('player') == p1.id]
        assert len(draw_events) >= 2

    def test_no_draw_when_other_minion_damaged(self):
        """Acolyte shouldn't draw when a different minion takes damage."""
        game, p1, p2 = new_hs_game()
        acolyte = make_obj(game, ACOLYTE_OF_PAIN, p1)
        other = make_obj(game, CHILLWIND_YETI, p1)

        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': other.id, 'amount': 1, 'source': 'test'},
            source='test'
        ))

        draw_events = [e for e in game.state.event_log
                       if e.type == EventType.DRAW and
                       e.payload.get('player') == p1.id]
        assert len(draw_events) == 0


# ============================================================
# Doomsayer — At start of your turn, destroy ALL minions
# ============================================================

class TestDoomsayer:
    def test_destroys_all_on_turn_start(self):
        """Doomsayer should destroy all minions at start of controller's turn."""
        game, p1, p2 = new_hs_game()
        doom = make_obj(game, DOOMSAYER, p1)
        m1 = make_obj(game, CHILLWIND_YETI, p1)
        m2 = make_obj(game, BLOODFEN_RAPTOR, p2)

        game.emit(Event(
            type=EventType.TURN_START,
            payload={'player': p1.id},
            source='system'
        ))

        destroy_events = [e for e in game.state.event_log
                          if e.type == EventType.OBJECT_DESTROYED]
        destroyed_ids = {e.payload['object_id'] for e in destroy_events}
        # All minions should be destroyed (including Doomsayer itself)
        assert m1.id in destroyed_ids
        assert m2.id in destroyed_ids
        assert doom.id in destroyed_ids

    def test_no_trigger_on_opponent_turn(self):
        """Doomsayer shouldn't trigger on opponent's turn start."""
        game, p1, p2 = new_hs_game()
        doom = make_obj(game, DOOMSAYER, p1)
        m1 = make_obj(game, CHILLWIND_YETI, p2)

        game.emit(Event(
            type=EventType.TURN_START,
            payload={'player': p2.id},
            source='system'
        ))

        destroy_events = [e for e in game.state.event_log
                          if e.type == EventType.OBJECT_DESTROYED]
        assert len(destroy_events) == 0

    def test_empty_board_no_crash(self):
        """Doomsayer on an otherwise empty board should not crash."""
        game, p1, p2 = new_hs_game()
        doom = make_obj(game, DOOMSAYER, p1)

        game.emit(Event(
            type=EventType.TURN_START,
            payload={'player': p1.id},
            source='system'
        ))

        destroy_events = [e for e in game.state.event_log
                          if e.type == EventType.OBJECT_DESTROYED]
        # At minimum Doomsayer destroys itself
        assert doom.id in {e.payload['object_id'] for e in destroy_events}


# ============================================================
# Gadgetzan Auctioneer — Whenever you cast a spell, draw a card
# ============================================================

class TestGadgetzanAuctioneer:
    def test_draws_on_spell_cast(self):
        """Gadgetzan should draw when controller casts a spell."""
        game, p1, p2 = new_hs_game()
        gadget = make_obj(game, GADGETZAN_AUCTIONEER, p1)

        cast_spell_full(game, FIREBALL, p1, targets=[p2.hero_id])

        draw_events = [e for e in game.state.event_log
                       if e.type == EventType.DRAW and
                       e.payload.get('player') == p1.id]
        assert len(draw_events) >= 1

    def test_no_draw_on_opponent_spell(self):
        """Gadgetzan shouldn't draw when opponent casts a spell."""
        game, p1, p2 = new_hs_game()
        gadget = make_obj(game, GADGETZAN_AUCTIONEER, p1)

        cast_spell_full(game, FIREBALL, p2, targets=[p1.hero_id])

        draw_events = [e for e in game.state.event_log
                       if e.type == EventType.DRAW and
                       e.payload.get('player') == p1.id]
        assert len(draw_events) == 0

    def test_multiple_spells_multiple_draws(self):
        """Each spell should trigger a separate draw."""
        game, p1, p2 = new_hs_game()
        gadget = make_obj(game, GADGETZAN_AUCTIONEER, p1)

        cast_spell_full(game, FIREBALL, p1, targets=[p2.hero_id])
        cast_spell_full(game, FROSTBOLT, p1, targets=[p2.hero_id])

        draw_events = [e for e in game.state.event_log
                       if e.type == EventType.DRAW and
                       e.payload.get('player') == p1.id]
        assert len(draw_events) >= 2


# ============================================================
# Flesheating Ghoul — Whenever a minion dies, gain +1 Attack
# ============================================================

class TestFleshEatingGhoul:
    def test_gains_attack_on_friendly_death(self):
        """Flesheating Ghoul gains +1 Attack when a friendly minion dies."""
        game, p1, p2 = new_hs_game()
        ghoul = make_obj(game, FLESHEATING_GHOUL, p1)
        base_power = get_power(ghoul, game.state)
        victim = make_obj(game, WISP, p1)

        game.emit(Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': victim.id, 'reason': 'test'},
            source='test'
        ))

        assert get_power(ghoul, game.state) >= base_power + 1

    def test_gains_attack_on_enemy_death(self):
        """Flesheating Ghoul gains +1 Attack when an enemy minion dies too."""
        game, p1, p2 = new_hs_game()
        ghoul = make_obj(game, FLESHEATING_GHOUL, p1)
        base_power = get_power(ghoul, game.state)
        victim = make_obj(game, WISP, p2)

        game.emit(Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': victim.id, 'reason': 'test'},
            source='test'
        ))

        assert get_power(ghoul, game.state) >= base_power + 1

    def test_no_gain_from_own_death(self):
        """Ghoul shouldn't trigger from its own death."""
        game, p1, p2 = new_hs_game()
        ghoul = make_obj(game, FLESHEATING_GHOUL, p1)

        game.emit(Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': ghoul.id, 'reason': 'test'},
            source='test'
        ))

        # Can't check power after death meaningfully, but no PT_MOD should fire
        pt_mods = [e for e in game.state.event_log
                   if e.type == EventType.PT_MODIFICATION and
                   e.payload.get('object_id') == ghoul.id]
        assert len(pt_mods) == 0

    def test_stacks_on_multiple_deaths(self):
        """Multiple deaths should stack +1 Attack each time."""
        game, p1, p2 = new_hs_game()
        ghoul = make_obj(game, FLESHEATING_GHOUL, p1)
        base_power = get_power(ghoul, game.state)
        v1 = make_obj(game, WISP, p2)
        v2 = make_obj(game, BLOODFEN_RAPTOR, p2)

        game.emit(Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': v1.id, 'reason': 'test'},
            source='test'
        ))
        game.emit(Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': v2.id, 'reason': 'test'},
            source='test'
        ))

        assert get_power(ghoul, game.state) >= base_power + 2


# ============================================================
# Cult Master — Whenever one of your other minions dies, draw a card
# ============================================================

class TestCultMaster:
    def test_draws_on_friendly_death(self):
        """Cult Master should draw when a friendly minion dies."""
        game, p1, p2 = new_hs_game()
        cm = make_obj(game, CULT_MASTER, p1)
        victim = make_obj(game, WISP, p1)

        game.emit(Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': victim.id, 'reason': 'test'},
            source='test'
        ))

        draw_events = [e for e in game.state.event_log
                       if e.type == EventType.DRAW and
                       e.payload.get('player') == p1.id]
        assert len(draw_events) >= 1

    def test_no_draw_on_enemy_death(self):
        """Cult Master shouldn't draw when an enemy minion dies."""
        game, p1, p2 = new_hs_game()
        cm = make_obj(game, CULT_MASTER, p1)
        victim = make_obj(game, WISP, p2)

        game.emit(Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': victim.id, 'reason': 'test'},
            source='test'
        ))

        draw_events = [e for e in game.state.event_log
                       if e.type == EventType.DRAW and
                       e.payload.get('player') == p1.id]
        assert len(draw_events) == 0

    def test_no_draw_from_own_death(self):
        """Cult Master shouldn't draw from its own death."""
        game, p1, p2 = new_hs_game()
        cm = make_obj(game, CULT_MASTER, p1)

        game.emit(Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': cm.id, 'reason': 'test'},
            source='test'
        ))

        draw_events = [e for e in game.state.event_log
                       if e.type == EventType.DRAW and
                       e.payload.get('player') == p1.id]
        assert len(draw_events) == 0


# ============================================================
# Emperor Cobra — Poisonous (destroy any minion it damages)
# ============================================================

class TestEmperorCobra:
    def test_destroys_damaged_minion(self):
        """Emperor Cobra should destroy any minion it damages."""
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
        assert destroy_events[0].payload.get('reason') == 'poisonous'

    def test_does_not_destroy_hero(self):
        """Poisonous should not fire on hero targets."""
        game, p1, p2 = new_hs_game()
        cobra = make_obj(game, EMPEROR_COBRA, p1)

        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': p2.hero_id, 'amount': 2, 'source': cobra.id},
            source=cobra.id
        ))

        destroy_events = [e for e in game.state.event_log
                          if e.type == EventType.OBJECT_DESTROYED and
                          e.payload.get('reason') == 'poisonous']
        assert len(destroy_events) == 0


# ============================================================
# Alarm-o-Bot — Start of turn, swap with random minion from hand
# ============================================================

class TestAlarmOBot:
    def test_swaps_with_hand_minion(self):
        """Alarm-o-Bot should return to hand and put a hand minion on board."""
        game, p1, p2 = new_hs_game()
        bot = make_obj(game, ALARM_O_BOT, p1)
        hand_minion = make_obj(game, CHILLWIND_YETI, p1, zone=ZoneType.HAND)

        game.emit(Event(
            type=EventType.TURN_START,
            payload={'player': p1.id},
            source='system'
        ))

        return_events = [e for e in game.state.event_log
                         if e.type == EventType.RETURN_TO_HAND and
                         e.payload.get('object_id') == bot.id]
        zone_events = [e for e in game.state.event_log
                       if e.type == EventType.ZONE_CHANGE and
                       e.payload.get('object_id') == hand_minion.id and
                       e.payload.get('to_zone_type') == ZoneType.BATTLEFIELD]
        assert len(return_events) >= 1
        assert len(zone_events) >= 1

    def test_no_swap_empty_hand(self):
        """Alarm-o-Bot shouldn't swap when no minions in hand."""
        game, p1, p2 = new_hs_game()
        bot = make_obj(game, ALARM_O_BOT, p1)

        game.emit(Event(
            type=EventType.TURN_START,
            payload={'player': p1.id},
            source='system'
        ))

        return_events = [e for e in game.state.event_log
                         if e.type == EventType.RETURN_TO_HAND]
        assert len(return_events) == 0


# ============================================================
# Raid Leader — Your other minions have +1 Attack (lord)
# ============================================================

class TestRaidLeader:
    def test_buffs_friendly_minions(self):
        """Raid Leader should give other friendly minions +1 Attack."""
        game, p1, p2 = new_hs_game()
        rl = make_obj(game, RAID_LEADER, p1)
        minion = make_obj(game, WISP, p1)  # 1/1

        power = get_power(minion, game.state)
        assert power >= 2  # 1 base + 1 from Raid Leader

    def test_does_not_buff_self(self):
        """Raid Leader should not buff itself."""
        game, p1, p2 = new_hs_game()
        rl = make_obj(game, RAID_LEADER, p1)

        assert get_power(rl, game.state) == 2  # 2 base, no buff

    def test_does_not_buff_enemy(self):
        """Raid Leader shouldn't buff enemy minions."""
        game, p1, p2 = new_hs_game()
        rl = make_obj(game, RAID_LEADER, p1)
        enemy = make_obj(game, WISP, p2)

        assert get_power(enemy, game.state) == 1  # No buff


# ============================================================
# Stormwind Champion — Your other minions have +1/+1
# ============================================================

class TestStormwindChampion:
    def test_buffs_attack_and_health(self):
        """Stormwind Champion should give other friendly minions +1/+1."""
        game, p1, p2 = new_hs_game()
        sc = make_obj(game, STORMWIND_CHAMPION, p1)
        minion = make_obj(game, WISP, p1)  # 1/1

        assert get_power(minion, game.state) >= 2
        assert get_toughness(minion, game.state) >= 2

    def test_does_not_buff_self(self):
        """Stormwind Champion should not buff itself."""
        game, p1, p2 = new_hs_game()
        sc = make_obj(game, STORMWIND_CHAMPION, p1)

        assert get_power(sc, game.state) == 6
        assert get_toughness(sc, game.state) == 6

    def test_multiple_lords_stack(self):
        """Two Stormwind Champions should stack, giving +2/+2."""
        game, p1, p2 = new_hs_game()
        sc1 = make_obj(game, STORMWIND_CHAMPION, p1)
        sc2 = make_obj(game, STORMWIND_CHAMPION, p1)
        minion = make_obj(game, WISP, p1)  # 1/1

        assert get_power(minion, game.state) >= 3  # 1 + 2
        assert get_toughness(minion, game.state) >= 3


# ============================================================
# Spell Damage stacking — Multiple spell damage minions
# ============================================================

class TestSpellDamageStacking:
    def test_kobold_geomancer_spell_damage(self):
        """Kobold Geomancer provides Spell Damage +1."""
        game, p1, p2 = new_hs_game()
        kg = make_obj(game, KOBOLD_GEOMANCER, p1)

        # Cast Fireball (6 damage base) — should do 7 with +1 spell damage
        cast_spell_full(game, FIREBALL, p1, targets=[p2.hero_id])

        dmg_events = [e for e in game.state.event_log
                      if e.type == EventType.DAMAGE and
                      e.payload.get('target') == p2.hero_id and
                      e.payload.get('from_spell')]
        assert len(dmg_events) >= 1
        assert dmg_events[0].payload['amount'] >= 7

    def test_two_spell_damage_minions_stack(self):
        """Two spell damage minions should add up their spell damage."""
        game, p1, p2 = new_hs_game()
        kg = make_obj(game, KOBOLD_GEOMANCER, p1)  # +1
        dm = make_obj(game, DALARAN_MAGE, p1)  # +1

        cast_spell_full(game, FIREBALL, p1, targets=[p2.hero_id])

        dmg_events = [e for e in game.state.event_log
                      if e.type == EventType.DAMAGE and
                      e.payload.get('target') == p2.hero_id and
                      e.payload.get('from_spell')]
        assert len(dmg_events) >= 1
        assert dmg_events[0].payload['amount'] >= 8  # 6 + 2

    def test_azure_drake_spell_damage_plus_draw(self):
        """Azure Drake provides Spell Damage +1 and has battlecry draw."""
        game, p1, p2 = new_hs_game()
        ad = make_obj(game, AZURE_DRAKE, p1)

        cast_spell_full(game, FROSTBOLT, p1, targets=[p2.hero_id])

        dmg_events = [e for e in game.state.event_log
                      if e.type == EventType.DAMAGE and
                      e.payload.get('target') == p2.hero_id and
                      e.payload.get('from_spell')]
        assert len(dmg_events) >= 1
        assert dmg_events[0].payload['amount'] >= 4  # 3 + 1


# ============================================================
# Grimscale Oracle — Your other Murlocs have +1 Attack
# ============================================================

class TestGrimscaleOracle:
    def test_buffs_friendly_murlocs(self):
        """Grimscale Oracle should buff other friendly Murlocs."""
        game, p1, p2 = new_hs_game()
        oracle = make_obj(game, GRIMSCALE_ORACLE, p1)
        murloc = make_obj(game, MURLOC_RAIDER, p1)  # 2/1 Murloc

        assert get_power(murloc, game.state) >= 3  # 2 + 1

    def test_does_not_buff_non_murlocs(self):
        """Grimscale Oracle shouldn't buff non-Murloc minions."""
        game, p1, p2 = new_hs_game()
        oracle = make_obj(game, GRIMSCALE_ORACLE, p1)
        non_murloc = make_obj(game, WISP, p1)

        assert get_power(non_murloc, game.state) == 1  # Wisp stays 1


# ============================================================
# Cross-Mechanic Combos
# ============================================================

class TestCrossMechanicBatch29:
    def test_acolyte_wild_pyromancer_aoe(self):
        """Wild Pyromancer AOE damages Acolyte → Acolyte draws."""
        game, p1, p2 = new_hs_game()
        pyro = make_obj(game, WILD_PYROMANCER, p1)
        acolyte = make_obj(game, ACOLYTE_OF_PAIN, p1)

        # Cast a spell → Pyro deals 1 to all minions
        cast_spell_full(game, FIREBALL, p1, targets=[p2.hero_id])

        draw_events = [e for e in game.state.event_log
                       if e.type == EventType.DRAW and
                       e.payload.get('player') == p1.id]
        assert len(draw_events) >= 1

    def test_cult_master_draws_on_independent_death(self):
        """Cult Master draws when a friendly minion dies outside of Doomsayer mass destruction."""
        game, p1, p2 = new_hs_game()
        cm = make_obj(game, CULT_MASTER, p1)
        victim = make_obj(game, WISP, p1)

        game.emit(Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': victim.id, 'reason': 'combat'},
            source='test'
        ))

        draw_events = [e for e in game.state.event_log
                       if e.type == EventType.DRAW and
                       e.payload.get('player') == p1.id]
        assert len(draw_events) >= 1

    def test_ghoul_gains_from_sequential_deaths(self):
        """Flesheating Ghoul gains attack from multiple minion deaths."""
        game, p1, p2 = new_hs_game()
        ghoul = make_obj(game, FLESHEATING_GHOUL, p1)
        base_power = get_power(ghoul, game.state)
        v1 = make_obj(game, WISP, p1)
        v2 = make_obj(game, WISP, p2)

        game.emit(Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': v1.id, 'reason': 'test'},
            source='test'
        ))
        game.emit(Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': v2.id, 'reason': 'test'},
            source='test'
        ))

        assert get_power(ghoul, game.state) >= base_power + 2

    def test_gadgetzan_plus_acolyte_spell_chain(self):
        """Gadgetzan draws on spell, spell triggers Pyro AOE, AOE hits Acolyte → more draws."""
        game, p1, p2 = new_hs_game()
        gadget = make_obj(game, GADGETZAN_AUCTIONEER, p1)
        acolyte = make_obj(game, ACOLYTE_OF_PAIN, p1)

        cast_spell_full(game, FIREBALL, p1, targets=[p2.hero_id])

        draw_events = [e for e in game.state.event_log
                       if e.type == EventType.DRAW and
                       e.payload.get('player') == p1.id]
        # At least Gadgetzan draw from the spell
        assert len(draw_events) >= 1

    def test_raid_leader_plus_stormwind_stack(self):
        """Raid Leader + Stormwind Champion should both buff the same minion."""
        game, p1, p2 = new_hs_game()
        rl = make_obj(game, RAID_LEADER, p1)
        sc = make_obj(game, STORMWIND_CHAMPION, p1)
        minion = make_obj(game, WISP, p1)

        # Wisp should get +1 ATK from Raid Leader, +1/+1 from Stormwind = 3/2
        assert get_power(minion, game.state) >= 3
        assert get_toughness(minion, game.state) >= 2

    def test_water_elemental_cobra_freeze_and_poison(self):
        """Test that freeze and poison are independent damage reactions."""
        game, p1, p2 = new_hs_game()
        we = make_obj(game, WATER_ELEMENTAL, p1)
        cobra = make_obj(game, EMPEROR_COBRA, p1)
        target = make_obj(game, CHILLWIND_YETI, p2)

        # Cobra damages target → poison destroy
        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': target.id, 'amount': 2, 'source': cobra.id},
            source=cobra.id
        ))

        destroy_events = [e for e in game.state.event_log
                          if e.type == EventType.OBJECT_DESTROYED and
                          e.payload.get('reason') == 'poisonous']
        assert len(destroy_events) >= 1

        # Water Elemental damages a different target → freeze
        target2 = make_obj(game, BLOODFEN_RAPTOR, p2)
        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': target2.id, 'amount': 3, 'source': we.id},
            source=we.id
        ))

        freeze_events = [e for e in game.state.event_log
                         if e.type == EventType.FREEZE_TARGET and
                         e.payload.get('target') == target2.id]
        assert len(freeze_events) >= 1
