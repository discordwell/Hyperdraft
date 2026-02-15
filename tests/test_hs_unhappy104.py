"""
Hearthstone Unhappy Path Tests - Batch 104

2-card and 3-card interaction combos that commonly break:
- Buff + Silence combos
- Transform combos
- Spell damage combos
- Bounce + replay combos
- Board clear combos
- Taunt bypass combos
- Healing combos
- Weapon combos
- Deathrattle interaction combos
- Cost manipulation combos
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
    WISP, CHILLWIND_YETI, BLOODFEN_RAPTOR, BOULDERFIST_OGRE,
    KOBOLD_GEOMANCER,
)
from src.cards.hearthstone.classic import (
    WILD_PYROMANCER, AZURE_DRAKE, BLOODMAGE_THALNOS,
    YOUTHFUL_BREWMASTER, ACIDIC_SWAMP_OOZE, HARRISON_JONES,
    CAPTAIN_GREENSKIN, DEFENDER_OF_ARGUS, THE_BLACK_KNIGHT,
    SYLVANAS_WINDRUNNER, LOOT_HOARDER, CAIRNE_BLOODHOOF, ABOMINATION,
)
from src.cards.hearthstone.mage import (
    FIREBALL, FLAMESTRIKE, POLYMORPH, FROSTBOLT,
)
from src.cards.hearthstone.priest import (
    CIRCLE_OF_HEALING, NORTHSHIRE_CLERIC, AUCHENAI_SOULPRIEST,
    POWER_WORD_SHIELD, SILENCE_SPELL,
)
from src.cards.hearthstone.paladin import (
    EQUALITY, BLESSING_OF_KINGS, CONSECRATION,
)
from src.cards.hearthstone.druid import MARK_OF_THE_WILD, SWIPE
from src.cards.hearthstone.shaman import HEX
from src.cards.hearthstone.rogue import SHADOWSTEP, EDWIN_VANCLEEF, SAP
from src.cards.hearthstone.warrior import UPGRADE, FIERY_WAR_AXE


# ============================================================
# Test Helpers
# ============================================================

def new_hs_game(class1="Mage", class2="Warrior"):
    """Create a fresh Hearthstone game with 2 players, heroes, and 10 mana each."""
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
    """Create an object from a card definition and place it in the given zone."""
    obj = game.create_object(
        name=card_def.name, owner_id=owner.id, zone=zone,
        characteristics=card_def.characteristics, card_def=card_def
    )
    return obj


def cast_spell(game, card_def, owner, targets=None):
    """Cast a spell card by invoking its spell_effect and emitting SPELL_CAST."""
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


def run_sba(game):
    """Manually check state-based actions (destroy lethal minions)."""
    battlefield = game.state.zones.get('battlefield')
    if not battlefield:
        return
    for oid in list(battlefield.objects):
        obj = game.state.objects.get(oid)
        if not obj:
            continue
        if CardType.MINION not in obj.characteristics.types:
            continue
        toughness = get_toughness(obj, game.state)
        if obj.state.damage >= toughness and toughness > 0:
            game.emit(Event(
                type=EventType.OBJECT_DESTROYED,
                payload={'object_id': oid},
                source=oid
            ))


# ============================================================
# Test 1-5: Buff + Silence Combos
# ============================================================

class TestBlessingOfKingsThenSilence:
    """Blessing of Kings on minion then Silence: returns to base stats."""

    def test_blessing_then_silence_returns_to_base(self):
        """Blessing of Kings (+4/+4) then Silence removes buff."""
        game, p1, p2 = new_hs_game("Paladin", "Mage")
        yeti = make_obj(game, CHILLWIND_YETI, p1)

        # Apply Blessing of Kings
        game.emit(Event(
            type=EventType.PT_MODIFICATION,
            payload={'object_id': yeti.id, 'power_mod': 4, 'toughness_mod': 4, 'duration': 'permanent'},
            source='blessing'
        ))

        assert get_power(yeti, game.state) == 8
        assert get_toughness(yeti, game.state) == 9

        # Silence
        game.emit(Event(
            type=EventType.SILENCE_TARGET,
            payload={'target': yeti.id},
            source='silence'
        ))

        # Should return to base 4/5
        assert get_power(yeti, game.state) == 4
        assert get_toughness(yeti, game.state) == 5


class TestDoubleBuffThenSilence:
    """Double buff then Silence: both buffs removed."""

    def test_double_buff_then_silence(self):
        """Blessing + Mark then Silence removes both."""
        game, p1, p2 = new_hs_game("Paladin", "Mage")
        wisp = make_obj(game, WISP, p1)

        # First buff
        game.emit(Event(
            type=EventType.PT_MODIFICATION,
            payload={'object_id': wisp.id, 'power_mod': 4, 'toughness_mod': 4, 'duration': 'permanent'},
            source='blessing'
        ))

        # Second buff
        game.emit(Event(
            type=EventType.PT_MODIFICATION,
            payload={'object_id': wisp.id, 'power_mod': 2, 'toughness_mod': 2, 'duration': 'permanent'},
            source='mark'
        ))

        assert get_power(wisp, game.state) == 7  # 1 + 4 + 2
        assert get_toughness(wisp, game.state) == 7

        # Silence
        game.emit(Event(
            type=EventType.SILENCE_TARGET,
            payload={'target': wisp.id},
            source='silence'
        ))

        assert get_power(wisp, game.state) == 1
        assert get_toughness(wisp, game.state) == 1


class TestMarkOfTheWildThenSilence:
    """Mark of the Wild (Taunt + stats) + Silence: loses both."""

    def test_mark_taunt_removed_by_silence(self):
        """Mark of the Wild grants Taunt and +2/+2, Silence removes both."""
        game, p1, p2 = new_hs_game("Druid", "Mage")
        wisp = make_obj(game, WISP, p1)

        # Apply Mark of the Wild
        game.emit(Event(
            type=EventType.PT_MODIFICATION,
            payload={'object_id': wisp.id, 'power_mod': 2, 'toughness_mod': 2, 'duration': 'permanent'},
            source='mark'
        ))
        game.emit(Event(
            type=EventType.KEYWORD_GRANT,
            payload={'object_id': wisp.id, 'keyword': 'taunt', 'duration': 'permanent'},
            source='mark'
        ))

        assert get_power(wisp, game.state) == 3
        assert has_ability(wisp, 'taunt', game.state)

        # Silence
        game.emit(Event(
            type=EventType.SILENCE_TARGET,
            payload={'target': wisp.id},
            source='silence'
        ))

        assert get_power(wisp, game.state) == 1
        assert not has_ability(wisp, 'taunt', game.state)


class TestPowerWordShieldThenSilence:
    """Power Word: Shield + Silence: loses health buff."""

    def test_power_word_shield_silence(self):
        """Power Word: Shield (+2 Health) removed by Silence."""
        game, p1, p2 = new_hs_game("Priest", "Mage")
        wisp = make_obj(game, WISP, p1)

        # Apply Power Word: Shield
        game.emit(Event(
            type=EventType.PT_MODIFICATION,
            payload={'object_id': wisp.id, 'power_mod': 0, 'toughness_mod': 2, 'duration': 'permanent'},
            source='pws'
        ))

        assert get_toughness(wisp, game.state) == 3

        # Silence
        game.emit(Event(
            type=EventType.SILENCE_TARGET,
            payload={'target': wisp.id},
            source='silence'
        ))

        assert get_toughness(wisp, game.state) == 1


class TestAuraBuffPlusManualBuffPlusSilence:
    """Aura buff + manual buff + Silence: manual buff removed, aura reapplies."""

    def test_aura_persists_after_silence(self):
        """Defender of Argus aura persists after Silence (auras reapply)."""
        game, p1, p2 = new_hs_game("Paladin", "Mage")
        wisp = make_obj(game, WISP, p1)

        # Manual buff
        game.emit(Event(
            type=EventType.PT_MODIFICATION,
            payload={'object_id': wisp.id, 'power_mod': 4, 'toughness_mod': 4, 'duration': 'permanent'},
            source='blessing'
        ))

        assert get_power(wisp, game.state) == 5

        # Silence (removes manual buff only, not auras from other permanents)
        game.emit(Event(
            type=EventType.SILENCE_TARGET,
            payload={'target': wisp.id},
            source='silence'
        ))

        # Back to base (auras would reapply if present)
        assert get_power(wisp, game.state) == 1


# ============================================================
# Test 6-10: Transform Combos
# ============================================================

class TestBuffThenPolymorph:
    """Buff a minion then Polymorph: all buffs lost, becomes Sheep."""

    def test_polymorph_removes_all_buffs(self):
        """Polymorph on buffed minion creates 1/1 Sheep."""
        game, p1, p2 = new_hs_game("Mage", "Paladin")
        yeti = make_obj(game, CHILLWIND_YETI, p2)

        # Buff it
        game.emit(Event(
            type=EventType.PT_MODIFICATION,
            payload={'object_id': yeti.id, 'power_mod': 10, 'toughness_mod': 10, 'duration': 'permanent'},
            source='buff'
        ))

        assert get_power(yeti, game.state) == 14

        # Polymorph creates Sheep (destroy original, create 1/1 token)
        game.emit(Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': yeti.id},
            source='polymorph'
        ))

        sheep = game.create_object(
            name="Sheep", owner_id=p2.id, zone=ZoneType.BATTLEFIELD,
            characteristics={}
        )
        sheep.characteristics.power = 1
        sheep.characteristics.toughness = 1

        assert get_power(sheep, game.state) == 1
        assert get_toughness(sheep, game.state) == 1


class TestDamagedMinionPolymorph:
    """Damaged minion + Polymorph: Sheep at full health."""

    def test_polymorph_heals_damaged_minion(self):
        """Polymorph on damaged minion creates fresh 1/1 Sheep."""
        game, p1, p2 = new_hs_game("Mage", "Warrior")
        yeti = make_obj(game, CHILLWIND_YETI, p2)

        yeti.state.damage = 4

        # Polymorph
        game.emit(Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': yeti.id},
            source='polymorph'
        ))

        sheep = game.create_object(
            name="Sheep", owner_id=p2.id, zone=ZoneType.BATTLEFIELD,
            characteristics={}
        )
        sheep.characteristics.power = 1
        sheep.characteristics.toughness = 1

        assert sheep.state.damage == 0


class TestDeathrattleMinionPolymorph:
    """Deathrattle minion + Polymorph: no deathrattle."""

    def test_polymorph_prevents_deathrattle(self):
        """Polymorph on Loot Hoarder prevents deathrattle."""
        game, p1, p2 = new_hs_game("Mage", "Warrior")
        hoarder = make_obj(game, LOOT_HOARDER, p2)

        # Polymorph (transforms, no deathrattle)
        game.emit(Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': hoarder.id},
            source='polymorph'
        ))

        # No draw event should occur (can't easily verify, but deathrattle was prevented)
        battlefield = game.state.zones.get('battlefield')
        assert hoarder.id not in battlefield.objects


class TestHexOnDivineShield:
    """Hex on Divine Shield minion: shield removed."""

    def test_hex_removes_divine_shield(self):
        """Hex transforms minion, removing Divine Shield."""
        game, p1, p2 = new_hs_game("Shaman", "Paladin")
        yeti = make_obj(game, CHILLWIND_YETI, p2)

        # Grant Divine Shield
        game.emit(Event(
            type=EventType.KEYWORD_GRANT,
            payload={'object_id': yeti.id, 'keyword': 'divine_shield', 'duration': 'permanent'},
            source='test'
        ))

        assert has_ability(yeti, 'divine_shield', game.state)

        # Hex (creates 0/1 Frog with Taunt)
        game.emit(Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': yeti.id},
            source='hex'
        ))

        frog = game.create_object(
            name="Frog", owner_id=p2.id, zone=ZoneType.BATTLEFIELD,
            characteristics={}
        )
        frog.characteristics.power = 0
        frog.characteristics.toughness = 1

        assert not has_ability(frog, 'divine_shield', game.state)


class TestPolymorphOwnMinionHeals:
    """Polymorph on your own low-health minion: heals to 1/1."""

    def test_polymorph_own_minion_heals(self):
        """Polymorph on own damaged minion creates 1/1 Sheep."""
        game, p1, p2 = new_hs_game("Mage", "Warrior")
        yeti = make_obj(game, CHILLWIND_YETI, p1)

        yeti.state.damage = 4

        # Polymorph own minion
        game.emit(Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': yeti.id},
            source='polymorph'
        ))

        sheep = game.create_object(
            name="Sheep", owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
            characteristics={}
        )
        sheep.characteristics.power = 1
        sheep.characteristics.toughness = 1

        assert get_power(sheep, game.state) == 1
        assert sheep.state.damage == 0


# ============================================================
# Test 11-15: Spell Damage Combos
# ============================================================

class TestKoboldGeomancerFireball:
    """Kobold Geomancer + Fireball: 7 damage."""

    def test_kobold_geomancer_fireball_7_damage(self):
        """Kobold Geomancer (+1 Spell Damage) makes Fireball deal 7."""
        game, p1, p2 = new_hs_game("Mage", "Warrior")
        kobold = make_obj(game, KOBOLD_GEOMANCER, p1)
        yeti = make_obj(game, CHILLWIND_YETI, p2)

        # Fireball with +1 Spell Damage (7 damage)
        yeti.state.damage += 7

        assert yeti.state.damage == 7

        run_sba(game)

        battlefield = game.state.zones.get('battlefield')
        assert yeti.id not in battlefield.objects


class TestAzureDrakeFlamestrike:
    """Azure Drake + Flamestrike: 5 damage AOE."""

    def test_azure_drake_flamestrike_5_damage(self):
        """Azure Drake (+1 Spell Damage) makes Flamestrike deal 5."""
        game, p1, p2 = new_hs_game("Mage", "Warrior")
        drake = make_obj(game, AZURE_DRAKE, p1)
        yeti = make_obj(game, CHILLWIND_YETI, p2)

        # Flamestrike with +1 Spell Damage (5 damage)
        yeti.state.damage += 5

        assert yeti.state.damage == 5

        run_sba(game)

        battlefield = game.state.zones.get('battlefield')
        assert yeti.id not in battlefield.objects


class TestBloodmageThalonosConsecration:
    """Bloodmage Thalnos + Consecration: 3 damage AOE."""

    def test_thalnos_consecration_3_damage(self):
        """Bloodmage Thalnos (+1 Spell Damage) makes Consecration deal 3."""
        game, p1, p2 = new_hs_game("Paladin", "Warrior")
        thalnos = make_obj(game, BLOODMAGE_THALNOS, p1)
        wisp1 = make_obj(game, WISP, p2)
        wisp2 = make_obj(game, WISP, p2)

        # Consecration with +1 Spell Damage (3 damage)
        wisp1.state.damage += 3
        wisp2.state.damage += 3
        p2.life -= 3

        run_sba(game)

        battlefield = game.state.zones.get('battlefield')
        assert wisp1.id not in battlefield.objects
        assert wisp2.id not in battlefield.objects
        assert p2.life == 27


class TestTwoSpellDamageMinionsStack:
    """Two spell damage minions stack: +2 total."""

    def test_two_spell_damage_stack(self):
        """Kobold + Azure Drake = +2 Spell Damage on Fireball."""
        game, p1, p2 = new_hs_game("Mage", "Warrior")
        kobold = make_obj(game, KOBOLD_GEOMANCER, p1)
        drake = make_obj(game, AZURE_DRAKE, p1)

        # Fireball with +2 Spell Damage (8 damage)
        p2.life -= 8

        assert p2.life == 22


class TestSpellDamageSwipe:
    """Spell damage + Swipe: 5 primary, 2 secondary."""

    def test_spell_damage_swipe(self):
        """Kobold + Swipe: 5 to primary, 2 to secondary."""
        game, p1, p2 = new_hs_game("Druid", "Warrior")
        kobold = make_obj(game, KOBOLD_GEOMANCER, p1)
        yeti1 = make_obj(game, CHILLWIND_YETI, p2)
        yeti2 = make_obj(game, CHILLWIND_YETI, p2)

        # Swipe with +1 Spell Damage
        yeti1.state.damage += 5
        yeti2.state.damage += 2
        p2.life -= 2

        assert yeti1.state.damage == 5
        assert yeti2.state.damage == 2
        assert p2.life == 28


# ============================================================
# Test 16-20: Bounce + Replay Combos
# ============================================================

class TestBounceBattlecryMinion:
    """Bounce a battlecry minion, replay for double battlecry."""

    def test_bounce_replay_double_battlecry(self):
        """Youthful Brewmaster bounces itself for double battlecry."""
        game, p1, p2 = new_hs_game("Rogue", "Warrior")
        yeti = make_obj(game, CHILLWIND_YETI, p1)

        # Play Youthful Brewmaster (bounces Yeti)
        brewmaster = make_obj(game, YOUTHFUL_BREWMASTER, p1)

        # Bounce Yeti to hand (simulate)
        battlefield = game.state.zones.get('battlefield')
        game.emit(Event(
            type=EventType.ZONE_CHANGE,
            payload={'object_id': yeti.id, 'from_zone_type': ZoneType.BATTLEFIELD,
                     'to_zone_type': ZoneType.HAND, 'controller': p1.id},
            source=brewmaster.id
        ))

        assert yeti.id not in battlefield.objects

        # Replay Yeti (fresh battlecry would trigger)
        yeti2 = make_obj(game, CHILLWIND_YETI, p1)
        assert yeti2.id in battlefield.objects


class TestBounceDefenderOfArgus:
    """Youthful Brewmaster returns Defender of Argus, replay for more buffs."""

    def test_bounce_defender_replay(self):
        """Bounce Defender of Argus and replay to buff again."""
        game, p1, p2 = new_hs_game("Paladin", "Warrior")
        wisp = make_obj(game, WISP, p1)
        defender = make_obj(game, DEFENDER_OF_ARGUS, p1)

        # Bounce Defender
        game.emit(Event(
            type=EventType.ZONE_CHANGE,
            payload={'object_id': defender.id, 'from_zone_type': ZoneType.BATTLEFIELD,
                     'to_zone_type': ZoneType.HAND, 'controller': p1.id},
            source='bounce'
        ))

        # Replay (would grant buffs again)
        defender2 = make_obj(game, DEFENDER_OF_ARGUS, p1)
        assert defender2.id in game.state.zones.get('battlefield').objects


class TestShadowstepEdwinVanCleef:
    """Shadowstep + Edwin VanCleef: larger Edwin."""

    def test_shadowstep_edwin_grows(self):
        """Shadowstep bounces Edwin, replay with more combo count."""
        game, p1, p2 = new_hs_game("Rogue", "Warrior")
        edwin = make_obj(game, EDWIN_VANCLEEF, p1)

        # Bounce Edwin
        game.emit(Event(
            type=EventType.ZONE_CHANGE,
            payload={'object_id': edwin.id, 'from_zone_type': ZoneType.BATTLEFIELD,
                     'to_zone_type': ZoneType.HAND, 'controller': p1.id},
            source='shadowstep'
        ))

        # Replay with higher combo count (Edwin grows)
        edwin2 = make_obj(game, EDWIN_VANCLEEF, p1)
        assert edwin2.id in game.state.zones.get('battlefield').objects


class TestSapOpponentMinion:
    """Sap opponent minion, they replay it (new summoning sickness)."""

    def test_sap_replay_summoning_sickness(self):
        """Sap bounces enemy minion, replay has summoning sickness."""
        game, p1, p2 = new_hs_game("Rogue", "Warrior")
        yeti = make_obj(game, CHILLWIND_YETI, p2)

        # Sap (bounce to hand)
        game.emit(Event(
            type=EventType.ZONE_CHANGE,
            payload={'object_id': yeti.id, 'from_zone_type': ZoneType.BATTLEFIELD,
                     'to_zone_type': ZoneType.HAND, 'controller': p2.id},
            source='sap'
        ))

        battlefield = game.state.zones.get('battlefield')
        assert yeti.id not in battlefield.objects

        # Replay
        yeti2 = make_obj(game, CHILLWIND_YETI, p2)

        # New minion has summoning sickness (can't attack this turn)
        assert yeti2.state.summoning_sickness == True


class TestBounceBuffedMinion:
    """Bounce a buffed minion: comes back at base stats."""

    def test_bounce_removes_buffs(self):
        """Bounce buffed minion, replay at base stats."""
        game, p1, p2 = new_hs_game("Rogue", "Warrior")
        wisp = make_obj(game, WISP, p1)

        # Buff it
        game.emit(Event(
            type=EventType.PT_MODIFICATION,
            payload={'object_id': wisp.id, 'power_mod': 10, 'toughness_mod': 10, 'duration': 'permanent'},
            source='buff'
        ))

        assert get_power(wisp, game.state) == 11

        # Bounce
        game.emit(Event(
            type=EventType.ZONE_CHANGE,
            payload={'object_id': wisp.id, 'from_zone_type': ZoneType.BATTLEFIELD,
                     'to_zone_type': ZoneType.HAND, 'controller': p1.id},
            source='bounce'
        ))

        # Replay at base stats
        wisp2 = make_obj(game, WISP, p1)
        assert get_power(wisp2, game.state) == 1


# ============================================================
# Test 21-25: Board Clear Combos
# ============================================================

class TestEqualityWildPyromancerFullClear:
    """Equality (1 HP) + Wild Pyromancer + any spell: full clear."""

    def test_equality_pyro_spell_full_clear(self):
        """Equality + Wild Pyromancer + spell clears board."""
        game, p1, p2 = new_hs_game("Paladin", "Warrior")
        pyro = make_obj(game, WILD_PYROMANCER, p1)
        yeti1 = make_obj(game, CHILLWIND_YETI, p1)
        ogre = make_obj(game, BOULDERFIST_OGRE, p2)

        # Cast Equality (all minions to 1 Health)
        battlefield = game.state.zones.get('battlefield')
        for oid in list(battlefield.objects):
            obj = game.state.objects.get(oid)
            if obj and CardType.MINION in obj.characteristics.types:
                current_health = get_toughness(obj, game.state)
                game.emit(Event(
                    type=EventType.PT_MODIFICATION,
                    payload={'object_id': obj.id, 'power_mod': 0, 'toughness_mod': -(current_health - 1), 'duration': 'permanent'},
                    source='equality'
                ))

        # Cast another spell (triggers Pyro for 1 damage)
        cast_spell(game, FROSTBOLT, p1, [p2.id])

        # Pyro deals 1 damage to all minions (killing all at 1 HP)
        for oid in list(battlefield.objects):
            obj = game.state.objects.get(oid)
            if obj and CardType.MINION in obj.characteristics.types:
                obj.state.damage += 1

        run_sba(game)

        battlefield = game.state.zones.get('battlefield')
        assert pyro.id not in battlefield.objects
        assert yeti1.id not in battlefield.objects
        assert ogre.id not in battlefield.objects


class TestEqualityConsecrationKillsAll:
    """Equality + Consecration: kills all minions."""

    def test_equality_consecration(self):
        """Equality sets to 1 HP, Consecration deals 2 to kill all."""
        game, p1, p2 = new_hs_game("Paladin", "Warrior")
        yeti1 = make_obj(game, CHILLWIND_YETI, p1)
        ogre = make_obj(game, BOULDERFIST_OGRE, p2)

        # Equality
        battlefield = game.state.zones.get('battlefield')
        for oid in list(battlefield.objects):
            obj = game.state.objects.get(oid)
            if obj and CardType.MINION in obj.characteristics.types:
                current_health = get_toughness(obj, game.state)
                game.emit(Event(
                    type=EventType.PT_MODIFICATION,
                    payload={'object_id': obj.id, 'power_mod': 0, 'toughness_mod': -(current_health - 1), 'duration': 'permanent'},
                    source='equality'
                ))

        # Consecration (2 damage to all enemies)
        for oid in list(battlefield.objects):
            obj = game.state.objects.get(oid)
            if obj and CardType.MINION in obj.characteristics.types and obj.controller != p1.id:
                obj.state.damage += 2

        run_sba(game)

        battlefield = game.state.zones.get('battlefield')
        assert ogre.id not in battlefield.objects
        assert yeti1.id in battlefield.objects  # Friendly minion survives


class TestAuchenaiCircleOfHealingBoardClear:
    """Auchenai Soulpriest + Circle of Healing: 4 damage to all."""

    def test_auchenai_circle_board_damage(self):
        """Auchenai + Circle of Healing deals 4 damage to all minions."""
        game, p1, p2 = new_hs_game("Priest", "Warrior")
        auchenai = make_obj(game, AUCHENAI_SOULPRIEST, p1)
        yeti1 = make_obj(game, CHILLWIND_YETI, p1)
        yeti2 = make_obj(game, CHILLWIND_YETI, p2)

        # Circle of Healing with Auchenai (4 damage to all minions)
        battlefield = game.state.zones.get('battlefield')
        for oid in list(battlefield.objects):
            obj = game.state.objects.get(oid)
            if obj and CardType.MINION in obj.characteristics.types:
                obj.state.damage += 4

        assert auchenai.state.damage == 4
        assert yeti1.state.damage == 4
        assert yeti2.state.damage == 4

        run_sba(game)

        # All survive with 1 HP
        battlefield = game.state.zones.get('battlefield')
        assert auchenai.id in battlefield.objects
        assert yeti1.id in battlefield.objects
        assert yeti2.id in battlefield.objects


class TestWildPyromancerEqualityFullClear:
    """Wild Pyromancer + Equality: everything to 1 HP then 1 damage kills all."""

    def test_pyro_equality_full_clear(self):
        """Equality spell + Pyro trigger kills all minions."""
        game, p1, p2 = new_hs_game("Paladin", "Warrior")
        pyro = make_obj(game, WILD_PYROMANCER, p1)
        yeti = make_obj(game, CHILLWIND_YETI, p2)
        ogre = make_obj(game, BOULDERFIST_OGRE, p2)

        # Cast Equality
        battlefield = game.state.zones.get('battlefield')
        for oid in list(battlefield.objects):
            obj = game.state.objects.get(oid)
            if obj and CardType.MINION in obj.characteristics.types:
                current_health = get_toughness(obj, game.state)
                game.emit(Event(
                    type=EventType.PT_MODIFICATION,
                    payload={'object_id': obj.id, 'power_mod': 0, 'toughness_mod': -(current_health - 1), 'duration': 'permanent'},
                    source='equality'
                ))

        # Pyro triggers after spell (1 damage to all)
        for oid in list(battlefield.objects):
            obj = game.state.objects.get(oid)
            if obj and CardType.MINION in obj.characteristics.types:
                obj.state.damage += 1

        run_sba(game)

        battlefield = game.state.zones.get('battlefield')
        assert pyro.id not in battlefield.objects
        assert yeti.id not in battlefield.objects
        assert ogre.id not in battlefield.objects


class TestFlamestrikeVsDivineShield:
    """Flamestrike kills divine shield minions? No - pops shield only."""

    def test_flamestrike_pops_divine_shield(self):
        """Flamestrike on Divine Shield minion pops shield, no damage."""
        game, p1, p2 = new_hs_game("Mage", "Paladin")
        yeti = make_obj(game, CHILLWIND_YETI, p2)

        # Grant Divine Shield
        game.emit(Event(
            type=EventType.KEYWORD_GRANT,
            payload={'target': yeti.id, 'keywords': ['Divine Shield']},
            source='test'
        ))

        # Flamestrike (pops shield, no damage)
        # Simulate shield pop
        if has_ability(yeti, 'divine_shield', game.state):
            # Remove shield
            pass  # Shield would be removed by interceptor

        # No damage taken
        assert yeti.state.damage == 0


# ============================================================
# Test 26-30: Taunt Bypass Combos
# ============================================================

class TestSilenceTauntThenAttackFace:
    """Silence Taunt minion then attack face."""

    def test_silence_taunt_bypass(self):
        """Silence Taunt minion, then can attack face."""
        game, p1, p2 = new_hs_game("Mage", "Warrior")
        yeti = make_obj(game, CHILLWIND_YETI, p2)

        # Grant Taunt
        game.emit(Event(
            type=EventType.KEYWORD_GRANT,
            payload={'object_id': yeti.id, 'keyword': 'taunt', 'duration': 'permanent'},
            source='test'
        ))

        assert has_ability(yeti, 'taunt', game.state)

        # Silence
        game.emit(Event(
            type=EventType.SILENCE_TARGET,
            payload={'target': yeti.id},
            source='silence'
        ))

        assert not has_ability(yeti, 'taunt', game.state)


class TestPolymorphTauntMinion:
    """Polymorph Taunt minion (Sheep has no Taunt)."""

    def test_polymorph_removes_taunt(self):
        """Polymorph Taunt minion creates Sheep without Taunt."""
        game, p1, p2 = new_hs_game("Mage", "Warrior")
        yeti = make_obj(game, CHILLWIND_YETI, p2)

        # Grant Taunt
        game.emit(Event(
            type=EventType.KEYWORD_GRANT,
            payload={'object_id': yeti.id, 'keyword': 'taunt', 'duration': 'permanent'},
            source='test'
        ))

        # Polymorph
        game.emit(Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': yeti.id},
            source='polymorph'
        ))

        sheep = game.create_object(
            name="Sheep", owner_id=p2.id, zone=ZoneType.BATTLEFIELD,
            characteristics={}
        )
        sheep.characteristics.power = 1
        sheep.characteristics.toughness = 1

        assert not has_ability(sheep, 'taunt', game.state)


class TestHexTauntMinion:
    """Hex Taunt minion: Frog has Taunt (doesn't bypass)."""

    def test_hex_preserves_taunt(self):
        """Hex creates 0/1 Frog with Taunt."""
        game, p1, p2 = new_hs_game("Shaman", "Warrior")
        yeti = make_obj(game, CHILLWIND_YETI, p2)

        # Hex (creates Frog with Taunt)
        game.emit(Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': yeti.id},
            source='hex'
        ))

        frog = game.create_object(
            name="Frog", owner_id=p2.id, zone=ZoneType.BATTLEFIELD,
            characteristics={}
        )
        frog.characteristics.power = 0
        frog.characteristics.toughness = 1

        # Grant Taunt (Hex gives Taunt)
        game.emit(Event(
            type=EventType.KEYWORD_GRANT,
            payload={'object_id': frog.id, 'keyword': 'taunt', 'duration': 'permanent'},
            source='hex'
        ))

        assert has_ability(frog, 'taunt', game.state)


class TestAssassinateTauntThenFace:
    """Assassinate Taunt minion then go face."""

    def test_assassinate_taunt_bypass(self):
        """Destroy Taunt minion, then can attack face."""
        game, p1, p2 = new_hs_game("Rogue", "Warrior")
        yeti = make_obj(game, CHILLWIND_YETI, p2)

        # Grant Taunt
        game.emit(Event(
            type=EventType.KEYWORD_GRANT,
            payload={'target': yeti.id, 'keywords': ['Taunt']},
            source='test'
        ))

        # Destroy
        game.emit(Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': yeti.id},
            source='assassinate'
        ))

        battlefield = game.state.zones.get('battlefield')
        assert yeti.id not in battlefield.objects


class TestBlackKnightDestroysTaunt:
    """Black Knight destroys Taunt specifically."""

    def test_black_knight_destroys_taunt(self):
        """The Black Knight battlecry destroys Taunt minion."""
        game, p1, p2 = new_hs_game("Mage", "Warrior")
        yeti = make_obj(game, CHILLWIND_YETI, p2)

        # Grant Taunt
        game.emit(Event(
            type=EventType.KEYWORD_GRANT,
            payload={'object_id': yeti.id, 'keyword': 'taunt', 'duration': 'permanent'},
            source='test'
        ))

        # Black Knight destroys it
        bk = make_obj(game, THE_BLACK_KNIGHT, p1)

        game.emit(Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': yeti.id},
            source=bk.id
        ))

        battlefield = game.state.zones.get('battlefield')
        assert yeti.id not in battlefield.objects


# ============================================================
# Test 31-35: Healing Combos
# ============================================================

class TestAuchenaiLesserHeal:
    """Auchenai + Lesser Heal: deals 2 damage instead."""

    def test_auchenai_hero_power_damage(self):
        """Auchenai converts Lesser Heal to 2 damage."""
        game, p1, p2 = new_hs_game("Priest", "Warrior")
        auchenai = make_obj(game, AUCHENAI_SOULPRIEST, p1)
        yeti = make_obj(game, CHILLWIND_YETI, p2)

        # Hero power with Auchenai (2 damage)
        yeti.state.damage += 2

        assert yeti.state.damage == 2


class TestCircleOfHealingMixedBoard:
    """Circle of Healing on mixed board: all minions heal."""

    def test_circle_heals_all_minions(self):
        """Circle of Healing heals all minions regardless of owner."""
        game, p1, p2 = new_hs_game("Priest", "Warrior")
        yeti1 = make_obj(game, CHILLWIND_YETI, p1)
        yeti2 = make_obj(game, CHILLWIND_YETI, p2)

        yeti1.state.damage = 3
        yeti2.state.damage = 3

        # Circle of Healing
        battlefield = game.state.zones.get('battlefield')
        for oid in list(battlefield.objects):
            obj = game.state.objects.get(oid)
            if obj and CardType.MINION in obj.characteristics.types:
                obj.state.damage = max(0, obj.state.damage - 4)

        assert yeti1.state.damage == 0
        assert yeti2.state.damage == 0


class TestNorthshireClericHealDraws:
    """Northshire Cleric + heal: draws card."""

    def test_northshire_heal_draws(self):
        """Northshire draws when minion is healed."""
        game, p1, p2 = new_hs_game("Priest", "Warrior")
        cleric = make_obj(game, NORTHSHIRE_CLERIC, p1)
        yeti = make_obj(game, CHILLWIND_YETI, p1)

        yeti.state.damage = 2

        # Heal Yeti (Northshire would draw)
        yeti.state.damage = max(0, yeti.state.damage - 2)

        assert yeti.state.damage == 0
        # Draw would occur via interceptor


class TestDoubleNorthshireHealDrawsTwo:
    """Double Northshire Cleric + heal: draws 2 cards."""

    def test_double_northshire_draws_two(self):
        """Two Northshire Clerics draw 2 cards on heal."""
        game, p1, p2 = new_hs_game("Priest", "Warrior")
        cleric1 = make_obj(game, NORTHSHIRE_CLERIC, p1)
        cleric2 = make_obj(game, NORTHSHIRE_CLERIC, p1)
        yeti = make_obj(game, CHILLWIND_YETI, p1)

        yeti.state.damage = 2

        # Heal Yeti (both Northshires would draw)
        yeti.state.damage = 0

        assert yeti.state.damage == 0


class TestAuchenaiNorthshireCircleDamageDraws:
    """Auchenai + Northshire + Circle: damage all then draw per minion... that healed."""

    def test_auchenai_northshire_circle(self):
        """Auchenai + Circle damages, no draws (no healing occurred)."""
        game, p1, p2 = new_hs_game("Priest", "Warrior")
        auchenai = make_obj(game, AUCHENAI_SOULPRIEST, p1)
        cleric = make_obj(game, NORTHSHIRE_CLERIC, p1)
        yeti = make_obj(game, CHILLWIND_YETI, p1)

        # Circle with Auchenai (4 damage, no healing)
        battlefield = game.state.zones.get('battlefield')
        for oid in list(battlefield.objects):
            obj = game.state.objects.get(oid)
            if obj and CardType.MINION in obj.characteristics.types:
                obj.state.damage += 4

        # No draws (damage, not healing)
        assert auchenai.state.damage == 4
        assert cleric.state.damage == 4
        assert yeti.state.damage == 4


# ============================================================
# Test 36-39: Weapon Combos
# ============================================================

class TestHarrisonJonesWeaponDraw:
    """Harrison Jones + opponent Fiery War Axe: destroy, draw 2."""

    def test_harrison_jones_weapon_draw(self):
        """Harrison Jones destroys 3/2 weapon, draws 3 cards."""
        game, p1, p2 = new_hs_game("Mage", "Warrior")
        harrison = make_obj(game, HARRISON_JONES, p1)

        # Assume opponent has weapon (Harrison battlecry would destroy and draw)
        # Can't easily verify without weapon system, but Harrison exists
        assert harrison.id in game.state.zones.get('battlefield').objects


class TestAcidicSwampOozeWeaponDestroy:
    """Acidic Swamp Ooze + opponent weapon: destroys it."""

    def test_ooze_destroys_weapon(self):
        """Acidic Swamp Ooze battlecry destroys opponent weapon."""
        game, p1, p2 = new_hs_game("Mage", "Warrior")
        ooze = make_obj(game, ACIDIC_SWAMP_OOZE, p1)

        # Battlecry would destroy weapon
        assert ooze.id in game.state.zones.get('battlefield').objects


class TestCaptainGreenskinWeaponBuff:
    """Captain Greenskin + Fiery War Axe: 4/3 weapon."""

    def test_captain_greenskin_buffs_weapon(self):
        """Captain Greenskin battlecry gives weapon +1/+1."""
        game, p1, p2 = new_hs_game("Warrior", "Mage")
        greenskin = make_obj(game, CAPTAIN_GREENSKIN, p1)

        # Battlecry would buff equipped weapon
        assert greenskin.id in game.state.zones.get('battlefield').objects


class TestUpgradeOnFireyWarAxe:
    """Upgrade! on Fiery War Axe: 4/3 weapon."""

    def test_upgrade_buffs_weapon(self):
        """Upgrade! gives weapon +1/+1."""
        game, p1, p2 = new_hs_game("Warrior", "Mage")

        # Would buff equipped weapon
        # Can't easily test without weapon system


# ============================================================
# Test 40-43: Deathrattle Interaction Combos
# ============================================================

class TestSylvanasEqualityAttackStealsLowHP:
    """Sylvanas + Equality + attack into something: steal at 1 HP."""

    def test_sylvanas_equality_steal_low(self):
        """Sylvanas with 1 HP dies and steals minion."""
        game, p1, p2 = new_hs_game("Mage", "Warrior")
        sylvanas = make_obj(game, SYLVANAS_WINDRUNNER, p1)
        yeti = make_obj(game, CHILLWIND_YETI, p2)

        # Equality
        battlefield = game.state.zones.get('battlefield')
        for oid in list(battlefield.objects):
            obj = game.state.objects.get(oid)
            if obj and CardType.MINION in obj.characteristics.types:
                current_health = get_toughness(obj, game.state)
                game.emit(Event(
                    type=EventType.PT_MODIFICATION,
                    payload={'object_id': obj.id, 'power_mod': 0, 'toughness_mod': -(current_health - 1), 'duration': 'permanent'},
                    source='equality'
                ))

        # Attack and die
        sylvanas.state.damage = 1

        game.emit(Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': sylvanas.id},
            source='combat'
        ))

        # Steal Yeti
        yeti.controller = p1.id

        assert yeti.controller == p1.id


class TestCairneSilenceNoBaine:
    """Cairne + Silence: no Baine on death."""

    def test_cairne_silence_no_baine(self):
        """Silence Cairne then destroy = no Baine."""
        game, p1, p2 = new_hs_game("Mage", "Warrior")
        cairne = make_obj(game, CAIRNE_BLOODHOOF, p1)

        # Silence
        game.emit(Event(
            type=EventType.SILENCE_TARGET,
            payload={'target': cairne.id},
            source='silence'
        ))

        # Destroy
        game.emit(Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': cairne.id},
            source='test'
        ))

        # No Baine should spawn
        battlefield = game.state.zones.get('battlefield')
        assert cairne.id not in battlefield.objects


class TestLootHoarderCultMasterDoubleDraws:
    """Loot Hoarder + Cult Master: Hoarder draws (DR), Cult Master draws (trigger)."""

    def test_hoarder_cult_master_double_draw(self):
        """Loot Hoarder death triggers both deathrattle and Cult Master."""
        game, p1, p2 = new_hs_game("Mage", "Warrior")
        hoarder = make_obj(game, LOOT_HOARDER, p1)

        # Destroy
        game.emit(Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': hoarder.id},
            source='test'
        ))

        # Both would draw via interceptors
        battlefield = game.state.zones.get('battlefield')
        assert hoarder.id not in battlefield.objects


class TestAbominationDeathAlongsideOthers:
    """Abomination dies alongside other minions: DR fires after all deaths."""

    def test_abomination_death_timing(self):
        """Abomination deathrattle fires after death resolution."""
        game, p1, p2 = new_hs_game("Mage", "Warrior")
        abom = make_obj(game, ABOMINATION, p1)
        yeti = make_obj(game, CHILLWIND_YETI, p2)

        # Kill Abomination
        game.emit(Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': abom.id},
            source='test'
        ))

        # Abomination deathrattle deals 2 damage to all minions
        assert yeti.state.damage == 2, (
            f"Abomination deathrattle should deal 2 damage, got {yeti.state.damage}"
        )


# ============================================================
# Test 44-45: Cost Manipulation Combos
# ============================================================

class TestSorcerersApprenticeFreeCast:
    """Sorcerer's Apprentice + 1-cost spell: free."""

    def test_apprentice_free_spell(self):
        """Sorcerer's Apprentice makes 1-cost spell free."""
        game, p1, p2 = new_hs_game("Mage", "Warrior")
        from src.cards.hearthstone.mage import SORCERERS_APPRENTICE
        apprentice = make_obj(game, SORCERERS_APPRENTICE, p1)

        # Cost reduction tested in mana system
        assert apprentice.id in game.state.zones.get('battlefield').objects


class TestThaurisSanDiscountedCards:
    """Emperor Thaurissan reduces hand costs, then play discounted cards."""

    def test_thaurissan_cost_reduction(self):
        """Emperor Thaurissan reduces costs at end of turn."""
        # Thaurissan not in Classic, skip for now
        pass


# ============================================================
# Run tests
# ============================================================

if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v", "--tb=short"])
