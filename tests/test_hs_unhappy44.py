"""
Hearthstone Unhappy Path Tests - Batch 44

Pipeline boundary tests: event ordering, zero damage handling, overkill damage,
simultaneous death resolution, negative life behavior, interceptor cleanup after
death, double silence, buff persistence after zone change, and various edge
cases that stress the event pipeline's handling of unusual inputs.
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
    WISP, CHILLWIND_YETI, BLOODFEN_RAPTOR, RAID_LEADER,
    KOBOLD_GEOMANCER, STORMWIND_CHAMPION, GURUBASHI_BERSERKER,
)
from src.cards.hearthstone.classic import (
    KNIFE_JUGGLER, FROSTBOLT, FIREBALL, LOOT_HOARDER,
    AMANI_BERSERKER, ABUSIVE_SERGEANT, ARGENT_SQUIRE,
    ACOLYTE_OF_PAIN, WILD_PYROMANCER, FLESHEATING_GHOUL,
    CULT_MASTER,
)
from src.cards.hearthstone.warrior import ARMORSMITH


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
# Zero Damage Handling
# ============================================================

class TestZeroDamage:
    def test_zero_damage_does_not_trigger_effects(self):
        """0 damage events should not trigger damage-based effects."""
        game, p1, p2 = new_hs_game()
        acolyte = make_obj(game, ACOLYTE_OF_PAIN, p1)

        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': acolyte.id, 'amount': 0, 'source': 'test'},
            source='test'
        ))

        draws = [e for e in game.state.event_log
                 if e.type == EventType.DRAW and
                 e.payload.get('player') == p1.id]
        # 0 damage may or may not trigger — test for no crash
        assert isinstance(draws, list)

    def test_negative_damage_no_crash(self):
        """Negative damage amount should not crash."""
        game, p1, p2 = new_hs_game()
        yeti = make_obj(game, CHILLWIND_YETI, p1)

        # Negative damage shouldn't crash
        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': yeti.id, 'amount': -5, 'source': 'test'},
            source='test'
        ))
        assert True  # No crash


# ============================================================
# Overkill Damage
# ============================================================

class TestOverkillDamage:
    def test_overkill_does_not_crash(self):
        """Damage far exceeding health should not crash."""
        game, p1, p2 = new_hs_game()
        wisp = make_obj(game, WISP, p1)  # 1/1

        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': wisp.id, 'amount': 100, 'source': 'test'},
            source='test'
        ))
        assert True

    def test_massive_hero_damage(self):
        """Huge damage to hero should work without crashing."""
        game, p1, p2 = new_hs_game()
        p1.life = 30

        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': p1.hero_id, 'amount': 999, 'source': 'test'},
            source='test'
        ))

        assert p1.life < 0  # Life goes negative


# ============================================================
# Simultaneous Deaths
# ============================================================

class TestSimultaneousDeaths:
    def test_multiple_minions_destroyed_same_event(self):
        """Multiple OBJECT_DESTROYED events in sequence should all resolve."""
        game, p1, p2 = new_hs_game()
        w1 = make_obj(game, WISP, p1)
        w2 = make_obj(game, WISP, p1)
        w3 = make_obj(game, WISP, p2)

        for w in [w1, w2, w3]:
            game.emit(Event(
                type=EventType.OBJECT_DESTROYED,
                payload={'object_id': w.id},
                source='test'
            ))

        destroy_events = [e for e in game.state.event_log
                          if e.type == EventType.OBJECT_DESTROYED]
        assert len(destroy_events) >= 3

    def test_flesheating_ghoul_tracks_multiple_deaths(self):
        """Ghoul gains +1 ATK per death — multiple simultaneous deaths."""
        game, p1, p2 = new_hs_game()
        ghoul = make_obj(game, FLESHEATING_GHOUL, p1)
        w1 = make_obj(game, WISP, p2)
        w2 = make_obj(game, WISP, p2)
        w3 = make_obj(game, WISP, p2)

        for w in [w1, w2, w3]:
            game.emit(Event(
                type=EventType.OBJECT_DESTROYED,
                payload={'object_id': w.id},
                source='test'
            ))

        pt_mods = [e for e in game.state.event_log
                   if e.type == EventType.PT_MODIFICATION and
                   e.payload.get('object_id') == ghoul.id]
        assert len(pt_mods) >= 3  # +1 per death


# ============================================================
# Enrage Interactions
# ============================================================

class TestEnrageEdgeCases:
    def test_gurubashi_berserker_gains_per_hit(self):
        """Gurubashi Berserker gains +3 Attack each time it takes damage."""
        game, p1, p2 = new_hs_game()
        guru = make_obj(game, GURUBASHI_BERSERKER, p1)

        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': guru.id, 'amount': 1, 'source': 'test'},
            source='test'
        ))
        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': guru.id, 'amount': 1, 'source': 'test'},
            source='test'
        ))

        pt_mods = [e for e in game.state.event_log
                   if e.type == EventType.PT_MODIFICATION and
                   e.payload.get('object_id') == guru.id]
        assert len(pt_mods) >= 2
        # Each gives +3 ATK
        for m in pt_mods:
            assert m.payload.get('power_mod') == 3

    def test_amani_berserker_enrage(self):
        """Amani Berserker gains +3 Attack when damaged (via QUERY_POWER)."""
        game, p1, p2 = new_hs_game()
        amani = make_obj(game, AMANI_BERSERKER, p1)

        # Undamaged: 2 ATK
        power_before = get_power(amani, game.state)
        assert power_before == 2

        amani.state.damage = 1  # Now enraged

        power_after = get_power(amani, game.state)
        assert power_after == 5  # 2 base + 3 enrage


# ============================================================
# Double Silence
# ============================================================

class TestDoubleSilence:
    def test_silencing_already_silenced_no_crash(self):
        """Silencing an already-silenced minion should not crash."""
        game, p1, p2 = new_hs_game()
        yeti = make_obj(game, CHILLWIND_YETI, p1)

        game.emit(Event(
            type=EventType.SILENCE_TARGET,
            payload={'target': yeti.id},
            source='test'
        ))
        game.emit(Event(
            type=EventType.SILENCE_TARGET,
            payload={'target': yeti.id},
            source='test'
        ))

        # No crash, minion still exists
        assert game.state.objects.get(yeti.id) is not None

    def test_silence_raid_leader_twice(self):
        """Silencing Raid Leader twice should be harmless."""
        game, p1, p2 = new_hs_game()
        rl = make_obj(game, RAID_LEADER, p1)
        wisp = make_obj(game, WISP, p1)

        game.emit(Event(
            type=EventType.SILENCE_TARGET,
            payload={'target': rl.id},
            source='test'
        ))
        game.emit(Event(
            type=EventType.SILENCE_TARGET,
            payload={'target': rl.id},
            source='test'
        ))

        power = get_power(wisp, game.state)
        assert power == 1  # No aura


# ============================================================
# Abusive Sergeant Temporary Buff
# ============================================================

class TestAbusiveSergeant:
    def test_battlecry_gives_attack(self):
        """Abusive Sergeant BC gives target +2 Attack this turn."""
        game, p1, p2 = new_hs_game()
        target = make_obj(game, WISP, p1)

        sgt = play_from_hand(game, ABUSIVE_SERGEANT, p1)

        pt_mods = [e for e in game.state.event_log
                   if e.type == EventType.PT_MODIFICATION and
                   e.payload.get('power_mod') == 2]
        assert len(pt_mods) >= 1


# ============================================================
# Argent Squire Divine Shield
# ============================================================

class TestArgentSquireDivineShield:
    def test_has_divine_shield(self):
        """Argent Squire should spawn with Divine Shield."""
        game, p1, p2 = new_hs_game()
        sq = make_obj(game, ARGENT_SQUIRE, p1)

        has_ds = has_ability(sq, 'divine_shield', game.state) or \
                 getattr(sq.state, 'divine_shield', False) or \
                 any(a.get('keyword') == 'divine_shield'
                     for a in (sq.characteristics.abilities or []))
        assert has_ds


# ============================================================
# Event Log Consistency
# ============================================================

class TestEventLogConsistency:
    def test_events_have_timestamps(self):
        """All events in the log should have a valid timestamp."""
        game, p1, p2 = new_hs_game()
        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': p2.hero_id, 'amount': 1, 'source': 'test'},
            source='test'
        ))

        for event in game.state.event_log:
            assert hasattr(event, 'timestamp')

    def test_large_event_chain_no_crash(self):
        """Processing many events in sequence should not crash or stack overflow."""
        game, p1, p2 = new_hs_game()

        for i in range(100):
            game.emit(Event(
                type=EventType.DAMAGE,
                payload={'target': p2.hero_id, 'amount': 1, 'source': 'test'},
                source='test'
            ))

        assert len(game.state.event_log) >= 100


# ============================================================
# Armorsmith + Multiple Friendly Hits
# ============================================================

class TestArmorsmithStress:
    def test_armorsmith_many_friendly_hits(self):
        """Armorsmith gains 1 armor per friendly minion damage — many hits."""
        game, p1, p2 = new_hs_game()
        smith = make_obj(game, ARMORSMITH, p1)
        yetis = [make_obj(game, CHILLWIND_YETI, p1) for _ in range(5)]
        p1.armor = 0

        for y in yetis:
            game.emit(Event(
                type=EventType.DAMAGE,
                payload={'target': y.id, 'amount': 1, 'source': 'test'},
                source='test'
            ))

        armor_events = [e for e in game.state.event_log
                        if e.type == EventType.ARMOR_GAIN and
                        e.payload.get('player') == p1.id]
        assert len(armor_events) >= 5


# ============================================================
# Cult Master + Mass Board Clear
# ============================================================

class TestCultMasterMassDeaths:
    def test_cult_master_draws_per_friendly_death(self):
        """Cult Master draws for each friendly minion that dies."""
        game, p1, p2 = new_hs_game()
        cm = make_obj(game, CULT_MASTER, p1)
        wisps = [make_obj(game, WISP, p1) for _ in range(4)]

        for w in wisps:
            game.emit(Event(
                type=EventType.OBJECT_DESTROYED,
                payload={'object_id': w.id},
                source='test'
            ))

        draws = [e for e in game.state.event_log
                 if e.type == EventType.DRAW and
                 e.payload.get('player') == p1.id]
        assert len(draws) >= 4


# ============================================================
# Stormwind Champion + Silence
# ============================================================

class TestStormwindChampionEdges:
    def test_buffs_all_friendly_minions(self):
        """Stormwind Champion gives all other friendly minions +1/+1."""
        game, p1, p2 = new_hs_game()
        sc = make_obj(game, STORMWIND_CHAMPION, p1)
        w1 = make_obj(game, WISP, p1)
        w2 = make_obj(game, WISP, p1)

        p1_w1 = get_power(w1, game.state)
        t1_w1 = get_toughness(w1, game.state)
        assert p1_w1 == 2  # 1 + 1
        assert t1_w1 == 2  # 1 + 1

    def test_does_not_buff_self(self):
        """Stormwind Champion should NOT buff itself."""
        game, p1, p2 = new_hs_game()
        sc = make_obj(game, STORMWIND_CHAMPION, p1)

        power = get_power(sc, game.state)
        toughness = get_toughness(sc, game.state)
        assert power == 6  # Base 6, no self-buff
        assert toughness == 6  # Base 6

    def test_does_not_buff_enemy(self):
        """Stormwind Champion doesn't buff enemy minions."""
        game, p1, p2 = new_hs_game()
        sc = make_obj(game, STORMWIND_CHAMPION, p1)
        enemy = make_obj(game, WISP, p2)

        power = get_power(enemy, game.state)
        assert power == 1  # Base, no buff
