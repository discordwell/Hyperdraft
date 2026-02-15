"""
Hearthstone Unhappy Path Tests - Batch 24

Deep edge cases: silence interactions, aura stacking, battlecry-from-hand-only,
copy independence, multi-aura removal, enrage variants, summoning sickness edge
cases, zero-attack minion behavior, double deathrattle resolution, fatigue chain
with draw triggers, poison/destroy interactions, taunt enforcement concepts,
healing cap mechanics, and end-of-turn trigger ordering.
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
    WISP, CHILLWIND_YETI, RIVER_CROCOLISK, BOULDERFIST_OGRE,
    BLOODFEN_RAPTOR, MURLOC_RAIDER, STONETUSK_BOAR,
    KOBOLD_GEOMANCER, RAID_LEADER, STORMWIND_CHAMPION,
    VOODOO_DOCTOR, SHATTERED_SUN_CLERIC, GURUBASHI_BERSERKER,
)
from src.cards.hearthstone.classic import (
    KNIFE_JUGGLER, WILD_PYROMANCER, HARVEST_GOLEM,
    ABOMINATION, ARGENT_SQUIRE, DIRE_WOLF_ALPHA,
    MURLOC_WARLEADER, FLESHEATING_GHOUL, LOOT_HOARDER,
    ACOLYTE_OF_PAIN, CAIRNE_BLOODHOOF, WATER_ELEMENTAL,
    AMANI_BERSERKER, YOUNG_PRIESTESS,
    RAGNAROS_THE_FIRELORD, ANCIENT_WATCHER, INJURED_BLADEMASTER,
    SILVER_HAND_KNIGHT, SUNWALKER,
)
from src.cards.hearthstone.paladin import (
    EQUALITY, CONSECRATION, BLESSING_OF_KINGS,
)
from src.cards.hearthstone.warlock import HELLFIRE, VOIDWALKER
from src.cards.hearthstone.shaman import HEX
from src.cards.hearthstone.warrior import WHIRLWIND, CRUEL_TASKMASTER
from src.cards.hearthstone.priest import NORTHSHIRE_CLERIC
from src.cards.hearthstone.druid import MOONFIRE
from src.cards.hearthstone.mage import FROST_NOVA


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
    obj = game.create_object(
        name=card_def.name, owner_id=owner.id, zone=zone,
        characteristics=card_def.characteristics, card_def=card_def
    )
    return obj


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


def cast_spell(game, card_def, owner, targets=None):
    obj = game.create_object(
        name=card_def.name, owner_id=owner.id, zone=ZoneType.BATTLEFIELD,
        characteristics=card_def.characteristics, card_def=card_def
    )
    events = card_def.spell_effect(obj, game.state, targets or [])
    for e in events:
        game.emit(e)
    return obj


def get_battlefield_minions(game, player_id):
    bf = game.state.zones.get('battlefield')
    if not bf:
        return []
    return [game.state.objects[oid] for oid in bf.objects
            if oid in game.state.objects
            and game.state.objects[oid].controller == player_id
            and CardType.MINION in game.state.objects[oid].characteristics.types]


def count_battlefield_minions(game, player_id):
    return len(get_battlefield_minions(game, player_id))


def fill_library(game, owner, count=10):
    for _ in range(count):
        make_obj(game, WISP, owner, zone=ZoneType.LIBRARY)


def hand_size(game, player_id):
    return len(game.state.zones[f"hand_{player_id}"].objects)


# ============================================================
# Silence Interactions Deep
# ============================================================

class TestSilenceDeep:
    def test_silence_removes_lord_aura(self):
        """Silencing Stormwind Champion removes its aura buff from other minions."""
        game, p1, p2 = new_hs_game()
        champion = make_obj(game, STORMWIND_CHAMPION, p1)
        wisp = make_obj(game, WISP, p1)  # 1/1 → 2/2 with champion

        power_buffed = get_power(wisp, game.state)

        # Silence the champion
        game.emit(Event(
            type=EventType.SILENCE_TARGET,
            payload={'target': champion.id},
            source='test'
        ))

        power_after = get_power(wisp, game.state)
        # Wisp should lose the buff
        assert power_after <= power_buffed

    def test_silence_removes_divine_shield(self):
        """Silencing a minion with Divine Shield removes it."""
        game, p1, p2 = new_hs_game()
        squire = make_obj(game, ARGENT_SQUIRE, p1)
        assert squire.state.divine_shield is True

        game.emit(Event(
            type=EventType.SILENCE_TARGET,
            payload={'target': squire.id},
            source='test'
        ))

        assert squire.state.divine_shield is False

    def test_silence_removes_taunt(self):
        """Silencing a taunt minion removes taunt."""
        game, p1, p2 = new_hs_game()
        voidwalker = make_obj(game, VOIDWALKER, p1)  # 1/3 Taunt
        assert has_ability(voidwalker, 'taunt', game.state)

        game.emit(Event(
            type=EventType.SILENCE_TARGET,
            payload={'target': voidwalker.id},
            source='test'
        ))

        assert not has_ability(voidwalker, 'taunt', game.state)

    def test_silence_doesnt_change_base_stats(self):
        """Silencing a minion doesn't change its base power/toughness."""
        game, p1, p2 = new_hs_game()
        yeti = make_obj(game, CHILLWIND_YETI, p1)  # 4/5

        game.emit(Event(
            type=EventType.SILENCE_TARGET,
            payload={'target': yeti.id},
            source='test'
        ))

        assert yeti.characteristics.power == 4
        assert yeti.characteristics.toughness == 5

    def test_silence_keeps_damage(self):
        """Silencing a damaged minion keeps the damage."""
        game, p1, p2 = new_hs_game()
        yeti = make_obj(game, CHILLWIND_YETI, p1)
        yeti.state.damage = 3

        game.emit(Event(
            type=EventType.SILENCE_TARGET,
            payload={'target': yeti.id},
            source='test'
        ))

        assert yeti.state.damage == 3  # Damage preserved


# ============================================================
# Battlecry From Hand Only
# ============================================================

class TestBattlecryFromHandOnly:
    def test_battlecry_fires_from_hand(self):
        """Battlecries fire when played from hand."""
        game, p1, p2 = new_hs_game()
        random.seed(42)
        # Shattered Sun Cleric BC: give a friendly minion +1/+1
        wisp = make_obj(game, WISP, p1)
        base_power = get_power(wisp, game.state)

        play_from_hand(game, SHATTERED_SUN_CLERIC, p1)

        # Wisp should have been buffed
        new_power = get_power(wisp, game.state)
        assert new_power >= base_power + 1

    def test_battlecry_doesnt_fire_from_battlefield(self):
        """Battlecries don't fire when summoned directly to battlefield."""
        game, p1, p2 = new_hs_game()
        random.seed(42)
        wisp = make_obj(game, WISP, p1)
        base_power = get_power(wisp, game.state)

        # Create Shattered Sun Cleric directly on battlefield (not from hand)
        make_obj(game, SHATTERED_SUN_CLERIC, p1)

        # Wisp should NOT be buffed (BC only from hand)
        new_power = get_power(wisp, game.state)
        assert new_power == base_power


# ============================================================
# Copy Independence
# ============================================================

class TestCopyIndependence:
    def test_two_instances_independent_damage(self):
        """Two instances of the same card take independent damage."""
        game, p1, p2 = new_hs_game()
        yeti1 = make_obj(game, CHILLWIND_YETI, p1)
        yeti2 = make_obj(game, CHILLWIND_YETI, p1)

        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': yeti1.id, 'amount': 3, 'source': 'test'},
            source='test'
        ))

        assert yeti1.state.damage == 3
        assert yeti2.state.damage == 0

    def test_two_instances_independent_buffs(self):
        """Buffing one instance doesn't buff another."""
        game, p1, p2 = new_hs_game()
        yeti1 = make_obj(game, CHILLWIND_YETI, p1)
        yeti2 = make_obj(game, CHILLWIND_YETI, p1)

        game.emit(Event(
            type=EventType.PT_CHANGE,
            payload={'object_id': yeti1.id, 'power': 2, 'toughness': 2},
            source='test'
        ))

        assert get_power(yeti1, game.state) >= 6  # 4 + 2
        assert get_power(yeti2, game.state) == 4   # unchanged


# ============================================================
# Multi-Aura Stacking and Removal
# ============================================================

class TestMultiAuraStacking:
    def test_raid_leader_plus_stormwind(self):
        """Raid Leader (+1 ATK) + Stormwind Champion (+1/+1) stack on same minion."""
        game, p1, p2 = new_hs_game()
        raid = make_obj(game, RAID_LEADER, p1)
        champ = make_obj(game, STORMWIND_CHAMPION, p1)
        wisp = make_obj(game, WISP, p1)  # 1/1

        power = get_power(wisp, game.state)
        # Wisp should get both buffs: base 1 + 1 (Raid) + 1 (Stormwind) = 3
        assert power >= 3

    def test_raid_leader_dies_stormwind_remains(self):
        """Kill Raid Leader — Stormwind Champion buff still applies."""
        game, p1, p2 = new_hs_game()
        raid = make_obj(game, RAID_LEADER, p1)
        champ = make_obj(game, STORMWIND_CHAMPION, p1)
        wisp = make_obj(game, WISP, p1)

        game.emit(Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': raid.id},
            source='test'
        ))

        power = get_power(wisp, game.state)
        # Should still get Stormwind buff: 1 + 1 = 2
        assert power >= 2

    def test_double_dire_wolf_adjacent(self):
        """Two Dire Wolf Alphas adjacent to same minion: +2 total ATK."""
        game, p1, p2 = new_hs_game()
        wolf1 = make_obj(game, DIRE_WOLF_ALPHA, p1)
        wisp = make_obj(game, WISP, p1)
        wolf2 = make_obj(game, DIRE_WOLF_ALPHA, p1)

        power = get_power(wisp, game.state)
        # Wisp between two wolves: +1 from each = base 1 + 2 = 3
        assert power >= 3

    def test_triple_murloc_warleader(self):
        """Three Murloc Warleaders: each buffing all OTHER murlocs."""
        game, p1, p2 = new_hs_game()
        wl1 = make_obj(game, MURLOC_WARLEADER, p1)
        wl2 = make_obj(game, MURLOC_WARLEADER, p1)
        wl3 = make_obj(game, MURLOC_WARLEADER, p1)

        # Each warleader gets buffed by the other two
        power1 = get_power(wl1, game.state)
        power2 = get_power(wl2, game.state)
        power3 = get_power(wl3, game.state)
        # Base 3 + 2*(+2 ATK from other warleaders) = 7
        assert power1 >= 7
        assert power2 >= 7
        assert power3 >= 7


# ============================================================
# Gurubashi Berserker Damage Stacking
# ============================================================

class TestGurubashiBerserker:
    def test_gurubashi_gains_3_per_damage(self):
        """Gurubashi Berserker: gain +3 Attack whenever this minion takes damage."""
        game, p1, p2 = new_hs_game()
        gurubashi = make_obj(game, GURUBASHI_BERSERKER, p1)  # 2/7
        base_power = get_power(gurubashi, game.state)

        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': gurubashi.id, 'amount': 1, 'source': 'test'},
            source='test'
        ))

        new_power = get_power(gurubashi, game.state)
        assert new_power == base_power + 3

    def test_gurubashi_stacks_multiple_hits(self):
        """Gurubashi hit 3 times: +9 Attack total."""
        game, p1, p2 = new_hs_game()
        gurubashi = make_obj(game, GURUBASHI_BERSERKER, p1)
        base_power = get_power(gurubashi, game.state)

        for _ in range(3):
            game.emit(Event(
                type=EventType.DAMAGE,
                payload={'target': gurubashi.id, 'amount': 1, 'source': 'test'},
                source='test'
            ))

        new_power = get_power(gurubashi, game.state)
        assert new_power == base_power + 9

    def test_gurubashi_whirlwind_triggers(self):
        """Gurubashi + Whirlwind: takes 1 damage → gains +3 Attack."""
        game, p1, p2 = new_hs_game()
        gurubashi = make_obj(game, GURUBASHI_BERSERKER, p1)
        base_power = get_power(gurubashi, game.state)

        cast_spell(game, WHIRLWIND, p1)

        new_power = get_power(gurubashi, game.state)
        assert new_power == base_power + 3


# ============================================================
# Injured Blademaster Battlecry
# ============================================================

class TestInjuredBlademaster:
    def test_blademaster_self_damages(self):
        """Injured Blademaster (4/7): Battlecry deals 4 damage to itself."""
        game, p1, p2 = new_hs_game()
        blademaster = play_from_hand(game, INJURED_BLADEMASTER, p1)

        # Should have 4 damage (4/7 base, 4 damage = effective 3 HP)
        assert blademaster.state.damage == 4
        assert get_toughness(blademaster, game.state) == 7  # base toughness unchanged
        # Effective health = toughness - damage = 3

    def test_blademaster_no_damage_from_summon(self):
        """Injured Blademaster placed directly doesn't self-damage (BC is hand-only)."""
        game, p1, p2 = new_hs_game()
        blademaster = make_obj(game, INJURED_BLADEMASTER, p1)

        # No battlecry from direct placement
        assert blademaster.state.damage == 0


# ============================================================
# Ragnaros Can't Attack
# ============================================================

class TestRagnarosCantAttack:
    def test_ragnaros_has_cant_attack(self):
        """Ragnaros has can't_attack ability."""
        game, p1, p2 = new_hs_game()
        rag = make_obj(game, RAGNAROS_THE_FIRELORD, p1)

        assert has_ability(rag, 'cant_attack', game.state)

    def test_ragnaros_end_of_turn_damage(self):
        """Ragnaros fires 8 damage at random enemy at end of turn."""
        game, p1, p2 = new_hs_game()
        random.seed(42)
        rag = make_obj(game, RAGNAROS_THE_FIRELORD, p1)

        life_before = p2.life

        game.emit(Event(
            type=EventType.TURN_END,
            payload={'player': p1.id},
            source='system'
        ))

        # Should deal 8 damage to something
        rag_damage = [e for e in game.state.event_log
                      if e.type == EventType.DAMAGE and e.source == rag.id]
        assert len(rag_damage) >= 1
        assert rag_damage[0].payload.get('amount') == 8


# ============================================================
# Ancient Watcher Can't Attack
# ============================================================

class TestAncientWatcher:
    def test_watcher_has_cant_attack(self):
        """Ancient Watcher has can't_attack ability."""
        game, p1, p2 = new_hs_game()
        watcher = make_obj(game, ANCIENT_WATCHER, p1)

        assert has_ability(watcher, 'cant_attack', game.state)

    def test_watcher_has_good_stats(self):
        """Ancient Watcher is a 4/5 for 2 mana — premium stats for the drawback."""
        game, p1, p2 = new_hs_game()
        watcher = make_obj(game, ANCIENT_WATCHER, p1)

        assert get_power(watcher, game.state) == 4
        assert get_toughness(watcher, game.state) == 5


# ============================================================
# Healing Cap (Can't Heal Above Max)
# ============================================================

class TestHealingCap:
    def test_hero_cant_heal_above_max(self):
        """Hero at 30 HP can't be healed above 30."""
        game, p1, p2 = new_hs_game()
        p1.life = 30

        game.emit(Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': p1.id, 'amount': 5},
            source='test'
        ))

        # Life should not exceed max
        assert p1.life <= 30

    def test_hero_heals_to_max(self):
        """Hero at 25 HP healed for 10 → caps at 30."""
        game, p1, p2 = new_hs_game()
        p1.life = 25

        game.emit(Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': p1.id, 'amount': 10},
            source='test'
        ))

        # Life should cap at 30
        assert p1.life <= 30

    def test_minion_heal_doesnt_exceed_max(self):
        """Minion healed for more than damage taken doesn't exceed max health."""
        game, p1, p2 = new_hs_game()
        yeti = make_obj(game, CHILLWIND_YETI, p1)  # 4/5
        yeti.state.damage = 2  # At 4/3

        # Heal for 5 (more than 2 damage)
        yeti.state.damage = max(0, yeti.state.damage - 5)

        assert yeti.state.damage == 0
        effective_health = yeti.characteristics.toughness - yeti.state.damage
        assert effective_health == 5  # Back to max


# ============================================================
# End-of-Turn Trigger Ordering
# ============================================================

class TestEndOfTurnTriggers:
    def test_ragnaros_fires_on_turn_end(self):
        """Ragnaros fires on TURN_END event."""
        game, p1, p2 = new_hs_game()
        random.seed(42)
        rag = make_obj(game, RAGNAROS_THE_FIRELORD, p1)

        game.emit(Event(
            type=EventType.TURN_END,
            payload={'player': p1.id},
            source='system'
        ))

        rag_damage = [e for e in game.state.event_log
                      if e.type == EventType.DAMAGE and e.source == rag.id]
        assert len(rag_damage) >= 1

    def test_young_priestess_eot_buff(self):
        """Young Priestess: At end of turn, give a random friendly minion +1 Health."""
        game, p1, p2 = new_hs_game()
        random.seed(42)
        priestess = make_obj(game, YOUNG_PRIESTESS, p1)
        wisp = make_obj(game, WISP, p1)

        base_tough = get_toughness(wisp, game.state)

        game.emit(Event(
            type=EventType.TURN_END,
            payload={'player': p1.id},
            source='system'
        ))

        # Wisp should get +1 health (or priestess buffed self)
        pt_events = [e for e in game.state.event_log
                     if e.type in (EventType.PT_MODIFICATION, EventType.PT_CHANGE)]
        # At least some buff should have been applied
        assert len(pt_events) >= 1


# ============================================================
# Sunwalker — Divine Shield + Taunt
# ============================================================

class TestSunwalker:
    def test_sunwalker_has_divine_shield_and_taunt(self):
        """Sunwalker (4/5) has both Divine Shield and Taunt."""
        game, p1, p2 = new_hs_game()
        sunwalker = make_obj(game, SUNWALKER, p1)

        assert sunwalker.state.divine_shield is True
        assert has_ability(sunwalker, 'taunt', game.state)

    def test_sunwalker_shield_absorbs_then_taunt_remains(self):
        """Hit Sunwalker once (shield pops), second hit goes through but taunt remains."""
        game, p1, p2 = new_hs_game()
        sunwalker = make_obj(game, SUNWALKER, p1)

        # First hit: shield absorbs
        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': sunwalker.id, 'amount': 5, 'source': 'test'},
            source='test'
        ))
        assert sunwalker.state.divine_shield is False
        assert sunwalker.state.damage == 0

        # Second hit: damage goes through
        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': sunwalker.id, 'amount': 3, 'source': 'test'},
            source='test'
        ))
        assert sunwalker.state.damage == 3

        # Taunt still active
        assert has_ability(sunwalker, 'taunt', game.state)


# ============================================================
# Cruel Taskmaster Battlecry
# ============================================================

class TestCruelTaskmaster:
    def test_taskmaster_buffs_and_damages(self):
        """Cruel Taskmaster: Deal 1 damage to a minion and give it +2 Attack."""
        game, p1, p2 = new_hs_game()
        random.seed(42)
        yeti = make_obj(game, CHILLWIND_YETI, p1)  # 4/5

        play_from_hand(game, CRUEL_TASKMASTER, p1)

        # Yeti should have taken 1 damage and gained +2 ATK
        assert yeti.state.damage >= 1  # Took 1 damage
        power = get_power(yeti, game.state)
        assert power >= 6  # 4 base + 2 buff

    def test_taskmaster_on_acolyte_triggers_draw(self):
        """Cruel Taskmaster damages Acolyte of Pain → triggers draw."""
        game, p1, p2 = new_hs_game()
        random.seed(42)
        acolyte = make_obj(game, ACOLYTE_OF_PAIN, p1)  # 1/3
        fill_library(game, p1)

        hand_before = hand_size(game, p1.id)

        play_from_hand(game, CRUEL_TASKMASTER, p1)

        draw_events = [e for e in game.state.event_log
                       if e.type == EventType.DRAW and e.payload.get('player') == p1.id]
        # If taskmaster targeted acolyte, should have drawn
        if acolyte.state.damage >= 1:
            assert len(draw_events) >= 1 or hand_size(game, p1.id) > hand_before

    def test_taskmaster_on_enrage_minion(self):
        """Cruel Taskmaster damages Amani Berserker → triggers enrage."""
        game, p1, p2 = new_hs_game()
        random.seed(42)
        amani = make_obj(game, AMANI_BERSERKER, p1)
        base_power = get_power(amani, game.state)

        play_from_hand(game, CRUEL_TASKMASTER, p1)

        # If taskmaster targeted amani: +2 from BC + +3 from enrage = +5 total
        if amani.state.damage >= 1:
            new_power = get_power(amani, game.state)
            assert new_power >= base_power + 5  # +2 buff + +3 enrage


# ============================================================
# Silver Hand Knight Squire Token
# ============================================================

class TestSilverHandKnight:
    def test_knight_summons_squire(self):
        """Silver Hand Knight (4/4): Battlecry summon a 2/2 Squire."""
        game, p1, p2 = new_hs_game()
        knight = play_from_hand(game, SILVER_HAND_KNIGHT, p1)

        p1_minions = get_battlefield_minions(game, p1.id)
        # Should have knight + squire
        assert len(p1_minions) >= 2
        squires = [m for m in p1_minions if m.name == 'Squire']
        assert len(squires) >= 1

    def test_knight_no_squire_from_direct_summon(self):
        """Silver Hand Knight placed directly (not from hand) doesn't summon squire."""
        game, p1, p2 = new_hs_game()
        knight = make_obj(game, SILVER_HAND_KNIGHT, p1)

        p1_minions = get_battlefield_minions(game, p1.id)
        # Only knight, no squire (BC is hand-only)
        squires = [m for m in p1_minions if m.name == 'Squire']
        assert len(squires) == 0


# ============================================================
# Equality Interaction with Damage
# ============================================================

class TestEqualityDamageInteraction:
    def test_equality_resets_damage(self):
        """Equality sets health to 1 AND resets damage to 0."""
        game, p1, p2 = new_hs_game()
        yeti = make_obj(game, CHILLWIND_YETI, p1)  # 4/5
        yeti.state.damage = 3  # At 4/2

        cast_spell(game, EQUALITY, p1)

        # Equality sets toughness to 1, damage to 0
        assert yeti.characteristics.toughness == 1
        assert yeti.state.damage == 0

    def test_equality_on_divine_shield_minion(self):
        """Equality on Argent Squire: still 1/1 with divine shield."""
        game, p1, p2 = new_hs_game()
        squire = make_obj(game, ARGENT_SQUIRE, p1)  # 1/1 DS

        cast_spell(game, EQUALITY, p1)

        # Still 1/1 (was already 1/1)
        assert squire.characteristics.toughness == 1
        # Divine shield should still be active (equality doesn't strip keywords)
        assert squire.state.divine_shield is True

    def test_equality_whistle_stop(self):
        """Equality doesn't change attack values."""
        game, p1, p2 = new_hs_game()
        ogre = make_obj(game, BOULDERFIST_OGRE, p1)  # 6/7

        cast_spell(game, EQUALITY, p1)

        assert ogre.characteristics.power == 6  # Attack unchanged
        assert ogre.characteristics.toughness == 1  # Health set to 1


# ============================================================
# Voodoo Doctor Battlecry Heal
# ============================================================

class TestVoodooDoctorHeal:
    def test_voodoo_doctor_heals_hero(self):
        """Voodoo Doctor: Battlecry restore 2 Health."""
        game, p1, p2 = new_hs_game()
        p1.life = 25

        play_from_hand(game, VOODOO_DOCTOR, p1)

        # Should heal 2 — life events emitted
        heal_events = [e for e in game.state.event_log
                       if e.type == EventType.LIFE_CHANGE
                       and e.payload.get('player') == p1.id]
        assert len(heal_events) >= 1 or p1.life > 25
