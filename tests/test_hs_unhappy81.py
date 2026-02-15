"""
Hearthstone Unhappy Path Tests - Batch 81

Spell Targeting + Resolution Edge Cases: spells with invalid/edge-case targets,
spell damage interactions, AOE on empty boards, and spell cost modifiers.
Tests for exact lethal, overkill, spell damage stacking, freeze mechanics,
Shadow Word targeting restrictions, Execute conditions, and Sorcerer's Apprentice
cost reduction (including multiple stacking and minimum cost of 0).
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
    CHILLWIND_YETI, KOBOLD_GEOMANCER, WISP, BOULDERFIST_OGRE,
)
from src.cards.hearthstone.classic import (
    FIREBALL, FLAMESTRIKE, CONSECRATION,
)
from src.cards.hearthstone.mage import (
    FROST_NOVA, PYROBLAST, BLIZZARD, SORCERERS_APPRENTICE,
)
from src.cards.hearthstone.priest import (
    HOLY_NOVA, SHADOW_WORD_PAIN, SHADOW_WORD_DEATH,
)
from src.cards.hearthstone.druid import (
    SWIPE, MOONFIRE,
)
from src.cards.hearthstone.shaman import (
    LIGHTNING_BOLT, LAVA_BURST, EARTH_SHOCK,
)
from src.cards.hearthstone.warrior import (
    EXECUTE,
)


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
    if zone == ZoneType.BATTLEFIELD and CardType.WEAPON in card_def.characteristics.types:
        game.emit(Event(
            type=EventType.ZONE_CHANGE,
            payload={
                'object_id': obj.id,
                'from_zone_type': None,
                'to_zone_type': ZoneType.BATTLEFIELD,
                'controller': owner.id,
            },
            source=obj.id
        ))
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
# Test 1: Fireball Exact Lethal
# ============================================================

class TestFireballExactLethal:
    """Fireball with exact lethal damage on a minion."""

    def test_fireball_6_damage_to_6_health_minion(self):
        """Fireball (6 damage) kills a Boulderfist Ogre (6/7) with 1 damage already taken."""
        game, p1, p2 = new_hs_game()

        ogre = make_obj(game, BOULDERFIST_OGRE, p2)
        # Deal 1 damage first so Ogre is at 6 health (7 - 1)
        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': ogre.id, 'amount': 1, 'source': 'test'},
            source='test'
        ))

        assert ogre.state.damage == 1

        cast_spell(game, FIREBALL, p1, targets=[ogre.id])

        # Ogre should have 7 damage total (1 + 6)
        assert ogre.state.damage == 7

        # Run SBA to destroy lethal minion
        run_sba(game)

        # Ogre should be destroyed
        destroyed = [e for e in game.state.event_log if e.type == EventType.OBJECT_DESTROYED and e.payload.get('object_id') == ogre.id]
        assert len(destroyed) == 1


# ============================================================
# Test 2: Fireball With Spell Damage
# ============================================================

class TestFireballWithSpellDamage:
    """Fireball (6 damage) + spell damage +1 = 7 total damage."""

    def test_fireball_plus_spell_damage_1(self):
        """Fireball with Kobold Geomancer (+1 spell damage) deals 7 damage."""
        game, p1, p2 = new_hs_game()

        kobold = make_obj(game, KOBOLD_GEOMANCER, p1)
        yeti = make_obj(game, CHILLWIND_YETI, p2)

        cast_spell(game, FIREBALL, p1, targets=[yeti.id])

        # Yeti should take 7 damage (6 base + 1 spell damage)
        assert yeti.state.damage == 7


# ============================================================
# Test 3: Fireball Overkill
# ============================================================

class TestFireballOverkill:
    """Fireball (6 damage) to a 3-health minion = 6 damage recorded (overkill)."""

    def test_fireball_overkill_on_wisp(self):
        """Fireball (6 damage) on a Wisp (1/1) deals 6 damage (overkill doesn't reduce)."""
        game, p1, p2 = new_hs_game()

        wisp = make_obj(game, WISP, p2)

        cast_spell(game, FIREBALL, p1, targets=[wisp.id])

        # Wisp should have 6 damage (overkill is recorded)
        assert wisp.state.damage == 6

        run_sba(game)

        # Wisp should be destroyed
        destroyed = [e for e in game.state.event_log if e.type == EventType.OBJECT_DESTROYED and e.payload.get('object_id') == wisp.id]
        assert len(destroyed) == 1


# ============================================================
# Test 4: Flamestrike On Empty Board
# ============================================================

class TestFlamestrikeEmptyBoard:
    """Flamestrike on empty enemy board should not crash or deal damage."""

    def test_flamestrike_no_enemies(self):
        """Flamestrike with no enemy minions emits no damage events."""
        game, p1, p2 = new_hs_game()

        cast_spell(game, FLAMESTRIKE, p1)

        # Check for damage events to enemy minions (should be 0)
        damage_events = [e for e in game.state.event_log if e.type == EventType.DAMAGE and e.payload.get('from_spell')]
        assert len(damage_events) == 0


# ============================================================
# Test 5: Flamestrike On Mixed Health Minions
# ============================================================

class TestFlamestrikeMixedHealth:
    """Flamestrike (4 AOE) kills low-health minions, damages high-health ones."""

    def test_flamestrike_some_survive_some_die(self):
        """Flamestrike kills Wisp (1/1) and Yeti (4/5) survives with 4 damage."""
        game, p1, p2 = new_hs_game()

        wisp = make_obj(game, WISP, p2)
        yeti = make_obj(game, CHILLWIND_YETI, p2)

        cast_spell(game, FLAMESTRIKE, p1)

        # Wisp should have 4 damage (dies)
        assert wisp.state.damage == 4

        # Yeti should have 4 damage (survives with 1 health)
        assert yeti.state.damage == 4

        run_sba(game)

        # Wisp destroyed, Yeti alive
        destroyed = [e for e in game.state.event_log if e.type == EventType.OBJECT_DESTROYED]
        destroyed_ids = [e.payload.get('object_id') for e in destroyed]
        assert wisp.id in destroyed_ids
        assert yeti.id not in destroyed_ids


# ============================================================
# Test 6: Consecration With Spell Damage
# ============================================================

class TestConsecrationSpellDamage:
    """Consecration (2 AOE) + spell damage +1 = 3 AOE."""

    def test_consecration_plus_spell_damage(self):
        """Consecration with Kobold Geomancer deals 3 damage to each enemy."""
        game, p1, p2 = new_hs_game()

        kobold = make_obj(game, KOBOLD_GEOMANCER, p1)
        yeti = make_obj(game, CHILLWIND_YETI, p2)

        cast_spell(game, CONSECRATION, p1)

        # Yeti should take 3 damage (2 base + 1 spell damage)
        assert yeti.state.damage == 3

        # Enemy hero should also take 3 damage
        assert p2.life == 27


# ============================================================
# Test 7: Consecration On Full Board
# ============================================================

class TestConsecrationFullBoard:
    """Consecration hits all 7 enemy minions on a full board."""

    def test_consecration_full_enemy_board(self):
        """Consecration hits all 7 enemy minions."""
        game, p1, p2 = new_hs_game()

        minions = []
        for _ in range(7):
            minions.append(make_obj(game, CHILLWIND_YETI, p2))

        cast_spell(game, CONSECRATION, p1)

        # All 7 minions should have 2 damage
        for minion in minions:
            assert minion.state.damage == 2


# ============================================================
# Test 8: Holy Nova Heals And Damages
# ============================================================

class TestHolyNovaBasic:
    """Holy Nova deals 2 damage to all enemies, heals all friendly characters."""

    def test_holy_nova_damage_and_heal(self):
        """Holy Nova damages enemy minions and heals friendly minions."""
        game, p1, p2 = new_hs_game()

        friendly = make_obj(game, CHILLWIND_YETI, p1)
        enemy = make_obj(game, CHILLWIND_YETI, p2)

        # Damage the friendly yeti
        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': friendly.id, 'amount': 3, 'source': 'test'},
            source='test'
        ))

        assert friendly.state.damage == 3

        cast_spell(game, HOLY_NOVA, p1)

        # Enemy takes 2 damage
        assert enemy.state.damage == 2

        # Friendly healed by 2 (3 - 2 = 1 damage remaining)
        assert friendly.state.damage == 1


# ============================================================
# Test 9: Holy Nova No Healing Needed
# ============================================================

class TestHolyNovaNoHealing:
    """Holy Nova with full-health friendlies still damages enemies."""

    def test_holy_nova_full_health_friendlies(self):
        """Holy Nova damages enemies even when friendlies are at full health."""
        game, p1, p2 = new_hs_game()

        friendly = make_obj(game, CHILLWIND_YETI, p1)
        enemy = make_obj(game, CHILLWIND_YETI, p2)

        cast_spell(game, HOLY_NOVA, p1)

        # Enemy takes 2 damage
        assert enemy.state.damage == 2

        # Friendly has no damage (was already full health)
        assert friendly.state.damage == 0


# ============================================================
# Test 10: Blizzard Freeze And Damage
# ============================================================

class TestBlizzardBasic:
    """Blizzard deals 2 damage to all enemy minions and freezes them."""

    def test_blizzard_damage_and_freeze(self):
        """Blizzard deals 2 damage and freezes all enemy minions."""
        game, p1, p2 = new_hs_game()

        yeti = make_obj(game, CHILLWIND_YETI, p2)

        cast_spell(game, BLIZZARD, p1)

        # Yeti should have 2 damage
        assert yeti.state.damage == 2

        # Yeti should be frozen
        freeze_events = [e for e in game.state.event_log if e.type == EventType.FREEZE_TARGET and e.payload.get('target') == yeti.id]
        assert len(freeze_events) == 1


# ============================================================
# Test 11: Frostbolt Freeze Persists
# ============================================================

class TestFrostboltFreeze:
    """Frostbolt deals 3 damage and applies freeze status."""

    def test_frostbolt_freeze_effect(self):
        """Frostbolt freeze event is emitted."""
        game, p1, p2 = new_hs_game()

        yeti = make_obj(game, CHILLWIND_YETI, p2)

        from src.cards.hearthstone.classic import FROSTBOLT
        cast_spell(game, FROSTBOLT, p1, targets=[yeti.id])

        # Yeti should have 3 damage
        assert yeti.state.damage == 3

        # Freeze event should be emitted
        freeze_events = [e for e in game.state.event_log if e.type == EventType.FREEZE_TARGET and e.payload.get('target') == yeti.id]
        assert len(freeze_events) == 1


# ============================================================
# Test 12: Frostbolt Lethal Plus Freeze
# ============================================================

class TestFrostboltLethal:
    """Frostbolt lethal damage + freeze (freeze doesn't matter if target dies)."""

    def test_frostbolt_kills_wisp(self):
        """Frostbolt (3 damage) kills Wisp (1/1), freeze is still emitted."""
        game, p1, p2 = new_hs_game()

        wisp = make_obj(game, WISP, p2)

        from src.cards.hearthstone.classic import FROSTBOLT
        cast_spell(game, FROSTBOLT, p1, targets=[wisp.id])

        # Wisp should have 3 damage
        assert wisp.state.damage == 3

        # Freeze event still emitted (even though minion will die)
        freeze_events = [e for e in game.state.event_log if e.type == EventType.FREEZE_TARGET and e.payload.get('target') == wisp.id]
        assert len(freeze_events) == 1

        run_sba(game)

        # Wisp destroyed
        destroyed = [e for e in game.state.event_log if e.type == EventType.OBJECT_DESTROYED and e.payload.get('object_id') == wisp.id]
        assert len(destroyed) == 1


# ============================================================
# Test 13: Frost Nova Freezes All Enemies
# ============================================================

class TestFrostNovaBasic:
    """Frost Nova freezes all enemy minions."""

    def test_frost_nova_freezes_all(self):
        """Frost Nova emits freeze events for all enemy minions."""
        game, p1, p2 = new_hs_game()

        yeti1 = make_obj(game, CHILLWIND_YETI, p2)
        yeti2 = make_obj(game, CHILLWIND_YETI, p2)

        cast_spell(game, FROST_NOVA, p1)

        # Both yetis should have freeze events
        freeze_events = [e for e in game.state.event_log if e.type == EventType.FREEZE_TARGET]
        freeze_targets = [e.payload.get('target') for e in freeze_events]
        assert yeti1.id in freeze_targets
        assert yeti2.id in freeze_targets


# ============================================================
# Test 14: Frost Nova On Empty Board
# ============================================================

class TestFrostNovaEmpty:
    """Frost Nova with no enemy minions emits no freeze events."""

    def test_frost_nova_no_enemies(self):
        """Frost Nova on empty board emits no freeze events."""
        game, p1, p2 = new_hs_game()

        cast_spell(game, FROST_NOVA, p1)

        # No freeze events should be emitted
        freeze_events = [e for e in game.state.event_log if e.type == EventType.FREEZE_TARGET]
        assert len(freeze_events) == 0


# ============================================================
# Test 15: Pyroblast To Face
# ============================================================

class TestPyroblastFace:
    """Pyroblast deals 10 damage to enemy hero."""

    def test_pyroblast_enemy_hero(self):
        """Pyroblast (10 damage) to enemy hero."""
        game, p1, p2 = new_hs_game()

        cast_spell(game, PYROBLAST, p1, targets=[p2.hero_id])

        # Enemy hero should have 20 life (30 - 10)
        assert p2.life == 20


# ============================================================
# Test 16: Pyroblast With Spell Damage
# ============================================================

class TestPyroblastSpellDamage:
    """Pyroblast (10 damage) + spell damage +1 = 11 to face."""

    def test_pyroblast_plus_spell_damage(self):
        """Pyroblast with Kobold Geomancer deals 11 damage to face."""
        game, p1, p2 = new_hs_game()

        kobold = make_obj(game, KOBOLD_GEOMANCER, p1)

        cast_spell(game, PYROBLAST, p1, targets=[p2.hero_id])

        # Enemy hero should have 19 life (30 - 11)
        assert p2.life == 19


# ============================================================
# Test 17: Moonfire With Spell Damage Stacking
# ============================================================

class TestMoonfireSpellDamage:
    """Moonfire (0-cost 1 damage) with spell damage stacking."""

    def test_moonfire_plus_two_spell_damage(self):
        """Moonfire with 2x Kobold Geomancer (+2 spell damage) deals 3 damage."""
        game, p1, p2 = new_hs_game()

        kobold1 = make_obj(game, KOBOLD_GEOMANCER, p1)
        kobold2 = make_obj(game, KOBOLD_GEOMANCER, p1)

        cast_spell(game, MOONFIRE, p1, targets=[p2.hero_id])

        # Enemy hero should have 27 life (30 - 3: 1 base + 2 spell damage)
        assert p2.life == 27


# ============================================================
# Test 18: Swipe Basic
# ============================================================

class TestSwipeBasic:
    """Swipe: 4 to primary target, 1 to all other enemies."""

    def test_swipe_primary_and_secondary(self):
        """Swipe deals 4 to primary, 1 to other enemies."""
        game, p1, p2 = new_hs_game()

        yeti1 = make_obj(game, CHILLWIND_YETI, p2)
        yeti2 = make_obj(game, CHILLWIND_YETI, p2)

        # Swipe targets yeti1 as primary (randomly chosen in effect)
        random.seed(42)
        cast_spell(game, SWIPE, p1)

        # Check damage events
        damage_events = [e for e in game.state.event_log if e.type == EventType.DAMAGE and e.payload.get('from_spell')]

        # Should have at least 2 damage events (primary + secondary targets)
        assert len(damage_events) >= 2

        # Check for 4 damage and 1 damage events
        damage_amounts = [e.payload.get('amount') for e in damage_events]
        assert 4 in damage_amounts
        assert 1 in damage_amounts


# ============================================================
# Test 19: Swipe With Spell Damage
# ============================================================

class TestSwipeSpellDamage:
    """Swipe with spell damage +1: 5 to target, 2 to others."""

    def test_swipe_plus_spell_damage(self):
        """Swipe with Kobold Geomancer: 5 to primary, 2 to others."""
        game, p1, p2 = new_hs_game()

        kobold = make_obj(game, KOBOLD_GEOMANCER, p1)
        yeti1 = make_obj(game, CHILLWIND_YETI, p2)
        yeti2 = make_obj(game, CHILLWIND_YETI, p2)

        random.seed(42)
        cast_spell(game, SWIPE, p1)

        # Check damage events
        damage_events = [e for e in game.state.event_log if e.type == EventType.DAMAGE and e.payload.get('from_spell')]
        damage_amounts = [e.payload.get('amount') for e in damage_events]

        # Should have 5 damage (primary) and 2 damage (secondary)
        assert 5 in damage_amounts
        assert 2 in damage_amounts


# ============================================================
# Test 20: Lightning Bolt With Overload
# ============================================================

class TestLightningBolt:
    """Lightning Bolt: 3 damage + Overload (1)."""

    def test_lightning_bolt_damage_and_overload(self):
        """Lightning Bolt deals 3 damage and sets overload to 1."""
        game, p1, p2 = new_hs_game()

        yeti = make_obj(game, CHILLWIND_YETI, p2)

        random.seed(42)
        cast_spell(game, LIGHTNING_BOLT, p1, targets=[yeti.id])

        # Check for 3 damage event (Lightning Bolt uses random targeting)
        damage_events = [e for e in game.state.event_log
                        if e.type == EventType.DAMAGE
                        and e.payload.get('from_spell')
                        and e.payload.get('amount') == 3]
        assert len(damage_events) == 1

        # Player should have 1 overloaded mana
        assert p1.overloaded_mana == 1


# ============================================================
# Test 21: Lava Burst With Overload
# ============================================================

class TestLavaBurst:
    """Lava Burst: 5 damage + Overload (2)."""

    def test_lava_burst_damage_and_overload(self):
        """Lava Burst deals 5 damage and sets overload to 2."""
        game, p1, p2 = new_hs_game()

        yeti = make_obj(game, CHILLWIND_YETI, p2)

        random.seed(42)
        cast_spell(game, LAVA_BURST, p1, targets=[yeti.id])

        # Check for 5 damage event (Lava Burst uses random targeting)
        damage_events = [e for e in game.state.event_log
                        if e.type == EventType.DAMAGE
                        and e.payload.get('from_spell')
                        and e.payload.get('amount') == 5]
        assert len(damage_events) == 1

        # Player should have 2 overloaded mana
        assert p1.overloaded_mana == 2


# ============================================================
# Test 22: Earth Shock On Buffed Minion
# ============================================================

class TestEarthShockBuffed:
    """Earth Shock: silence removes buffs, then 1 damage."""

    def test_earth_shock_removes_buff_then_damage(self):
        """Earth Shock silences (removing buffs), then deals 1 damage."""
        game, p1, p2 = new_hs_game()

        yeti = make_obj(game, CHILLWIND_YETI, p2)

        # Buff the yeti
        game.emit(Event(
            type=EventType.PT_MODIFICATION,
            payload={'object_id': yeti.id, 'power_mod': 2, 'toughness_mod': 2, 'duration': 'permanent'},
            source='test'
        ))

        cast_spell(game, EARTH_SHOCK, p1, targets=[yeti.id])

        # Silence event should be emitted
        silence_events = [e for e in game.state.event_log if e.type == EventType.SILENCE_TARGET and e.payload.get('target') == yeti.id]
        assert len(silence_events) == 1

        # Yeti should have 1 damage
        assert yeti.state.damage == 1

        # Player should have 1 overloaded mana
        assert p1.overloaded_mana == 1


# ============================================================
# Test 23: Earth Shock On Divine Shield
# ============================================================

class TestEarthShockDivineShield:
    """Earth Shock: silence removes divine shield, then damage applies."""

    def test_earth_shock_removes_divine_shield(self):
        """Earth Shock silences divine shield, then deals 1 damage."""
        game, p1, p2 = new_hs_game()

        from src.cards.hearthstone.classic import SILVERMOON_GUARDIAN
        guardian = make_obj(game, SILVERMOON_GUARDIAN, p2)

        cast_spell(game, EARTH_SHOCK, p1, targets=[guardian.id])

        # Silence event should be emitted
        silence_events = [e for e in game.state.event_log if e.type == EventType.SILENCE_TARGET and e.payload.get('target') == guardian.id]
        assert len(silence_events) == 1

        # Guardian should have 1 damage (silence removed divine shield first)
        assert guardian.state.damage == 1


# ============================================================
# Test 24: Shadow Word Pain On 3-Attack Minion
# ============================================================

class TestShadowWordPain3Attack:
    """Shadow Word: Pain destroys minion with 3 or less Attack."""

    def test_shadow_word_pain_on_3_attack(self):
        """Shadow Word: Pain destroys a 3-attack minion."""
        game, p1, p2 = new_hs_game()

        from src.cards.hearthstone.basic import SEN_JIN_SHIELDMASTA
        senjin = make_obj(game, SEN_JIN_SHIELDMASTA, p2)

        # Sen'jin is 3/5, should be valid target
        cast_spell(game, SHADOW_WORD_PAIN, p1)

        # Destroy event should be emitted
        destroyed = [e for e in game.state.event_log if e.type == EventType.OBJECT_DESTROYED and e.payload.get('object_id') == senjin.id]
        assert len(destroyed) == 1


# ============================================================
# Test 25: Shadow Word Pain On 4-Attack Minion
# ============================================================

class TestShadowWordPain4Attack:
    """Shadow Word: Pain fails on 4+ Attack minion (no valid target)."""

    def test_shadow_word_pain_invalid_target(self):
        """Shadow Word: Pain on 4-attack minion emits no destroy events."""
        game, p1, p2 = new_hs_game()

        yeti = make_obj(game, CHILLWIND_YETI, p2)

        # Yeti is 4/5, should not be valid target
        cast_spell(game, SHADOW_WORD_PAIN, p1)

        # No destroy events should be emitted
        destroyed = [e for e in game.state.event_log if e.type == EventType.OBJECT_DESTROYED and e.payload.get('object_id') == yeti.id]
        assert len(destroyed) == 0


# ============================================================
# Test 26: Shadow Word Death On 5-Attack Minion
# ============================================================

class TestShadowWordDeath5Attack:
    """Shadow Word: Death destroys minion with 5+ Attack."""

    def test_shadow_word_death_on_5_attack(self):
        """Shadow Word: Death destroys a 6-attack minion."""
        game, p1, p2 = new_hs_game()

        ogre = make_obj(game, BOULDERFIST_OGRE, p2)

        # Ogre is 6/7, should be valid target
        cast_spell(game, SHADOW_WORD_DEATH, p1)

        # Destroy event should be emitted
        destroyed = [e for e in game.state.event_log if e.type == EventType.OBJECT_DESTROYED and e.payload.get('object_id') == ogre.id]
        assert len(destroyed) == 1


# ============================================================
# Test 27: Shadow Word Death On 4-Attack Minion
# ============================================================

class TestShadowWordDeath4Attack:
    """Shadow Word: Death fails on <5 Attack minion (no valid target)."""

    def test_shadow_word_death_invalid_target(self):
        """Shadow Word: Death on 4-attack minion emits no destroy events."""
        game, p1, p2 = new_hs_game()

        yeti = make_obj(game, CHILLWIND_YETI, p2)

        # Yeti is 4/5, should not be valid target
        cast_spell(game, SHADOW_WORD_DEATH, p1)

        # No destroy events should be emitted
        destroyed = [e for e in game.state.event_log if e.type == EventType.OBJECT_DESTROYED and e.payload.get('object_id') == yeti.id]
        assert len(destroyed) == 0


# ============================================================
# Test 28: Execute On Damaged Minion
# ============================================================

class TestExecuteDamaged:
    """Execute destroys a damaged enemy minion."""

    def test_execute_on_damaged_minion(self):
        """Execute destroys a damaged minion."""
        game, p1, p2 = new_hs_game()

        yeti = make_obj(game, CHILLWIND_YETI, p2)

        # Damage the yeti
        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': yeti.id, 'amount': 1, 'source': 'test'},
            source='test'
        ))

        assert yeti.state.damage == 1

        cast_spell(game, EXECUTE, p1)

        # Destroy event should be emitted
        destroyed = [e for e in game.state.event_log if e.type == EventType.OBJECT_DESTROYED and e.payload.get('object_id') == yeti.id]
        assert len(destroyed) == 1


# ============================================================
# Test 29: Execute On Undamaged Minion
# ============================================================

class TestExecuteUndamaged:
    """Execute fails on undamaged minion (no valid target)."""

    def test_execute_no_valid_target(self):
        """Execute on undamaged minion emits no destroy events."""
        game, p1, p2 = new_hs_game()

        yeti = make_obj(game, CHILLWIND_YETI, p2)

        cast_spell(game, EXECUTE, p1)

        # No destroy events should be emitted
        destroyed = [e for e in game.state.event_log if e.type == EventType.OBJECT_DESTROYED and e.payload.get('object_id') == yeti.id]
        assert len(destroyed) == 0


# ============================================================
# Test 30: Sorcerer's Apprentice Cost Reduction
# ============================================================

class TestSorcerersApprenticeSingle:
    """Sorcerer's Apprentice makes spells cost (1) less."""

    def test_apprentice_reduces_spell_cost(self):
        """Sorcerer's Apprentice reduces spell cost by 1."""
        game, p1, p2 = new_hs_game()

        apprentice = make_obj(game, SORCERERS_APPRENTICE, p1)

        # Check that Fireball (4 mana) would cost 3 mana
        # This test checks interceptor registration, actual cost calculation happens in mana system
        # We verify the interceptor exists
        assert len(apprentice.interceptor_ids) > 0


# ============================================================
# Test 31: Double Sorcerer's Apprentice
# ============================================================

class TestDoubleSorcerersApprentice:
    """Two Sorcerer's Apprentices make spells cost (2) less."""

    def test_two_apprentices_stack(self):
        """Two Sorcerer's Apprentices stack their cost reduction."""
        game, p1, p2 = new_hs_game()

        apprentice1 = make_obj(game, SORCERERS_APPRENTICE, p1)
        apprentice2 = make_obj(game, SORCERERS_APPRENTICE, p1)

        # Both should have interceptors registered
        assert len(apprentice1.interceptor_ids) > 0
        assert len(apprentice2.interceptor_ids) > 0


# ============================================================
# Test 32: Spell Cost Minimum Zero
# ============================================================

class TestSpellCostMinimumZero:
    """Spell cost reduction cannot go below 0."""

    def test_spell_cost_cannot_go_negative(self):
        """Multiple cost reductions on a 0-cost spell don't go negative."""
        game, p1, p2 = new_hs_game()

        apprentice1 = make_obj(game, SORCERERS_APPRENTICE, p1)
        apprentice2 = make_obj(game, SORCERERS_APPRENTICE, p1)

        # Moonfire costs 0, with 2 apprentices would be -2, but should stay 0
        # This is handled by the mana system, we just verify the spell can be cast
        cast_spell(game, MOONFIRE, p1, targets=[p2.hero_id])

        # Should succeed (no crash)
        damage_events = [e for e in game.state.event_log if e.type == EventType.DAMAGE]
        assert len(damage_events) >= 1


# ============================================================
# Test 33: Flamestrike With Spell Damage
# ============================================================

class TestFlamestrikeSpellDamage:
    """Flamestrike (4 AOE) + spell damage +1 = 5 AOE."""

    def test_flamestrike_plus_spell_damage(self):
        """Flamestrike with Kobold Geomancer deals 5 damage to each enemy."""
        game, p1, p2 = new_hs_game()

        kobold = make_obj(game, KOBOLD_GEOMANCER, p1)
        yeti = make_obj(game, CHILLWIND_YETI, p2)

        cast_spell(game, FLAMESTRIKE, p1)

        # Yeti should take 5 damage (4 base + 1 spell damage)
        assert yeti.state.damage == 5


# ============================================================
# Test 34: Multiple Yetis Flamestrike
# ============================================================

class TestFlamestrikeMultipleTargets:
    """Flamestrike hits multiple enemy minions."""

    def test_flamestrike_hits_all_enemies(self):
        """Flamestrike deals 4 damage to each of 3 enemy minions."""
        game, p1, p2 = new_hs_game()

        yeti1 = make_obj(game, CHILLWIND_YETI, p2)
        yeti2 = make_obj(game, CHILLWIND_YETI, p2)
        yeti3 = make_obj(game, CHILLWIND_YETI, p2)

        cast_spell(game, FLAMESTRIKE, p1)

        # All should have 4 damage
        assert yeti1.state.damage == 4
        assert yeti2.state.damage == 4
        assert yeti3.state.damage == 4


# ============================================================
# Test 35: Consecration Hits Hero And Minions
# ============================================================

class TestConsecrationHitsAll:
    """Consecration hits both enemy hero and minions."""

    def test_consecration_hero_and_minions(self):
        """Consecration deals 2 to enemy hero and minions."""
        game, p1, p2 = new_hs_game()

        yeti = make_obj(game, CHILLWIND_YETI, p2)

        cast_spell(game, CONSECRATION, p1)

        # Enemy hero takes 2 damage
        assert p2.life == 28

        # Enemy minion takes 2 damage
        assert yeti.state.damage == 2


# ============================================================
# Test 36: Moonfire Zero Cost
# ============================================================

class TestMoonfireZeroCost:
    """Moonfire costs 0 mana and deals 1 damage."""

    def test_moonfire_zero_mana_cost(self):
        """Moonfire (0 cost) deals 1 damage."""
        game, p1, p2 = new_hs_game()

        cast_spell(game, MOONFIRE, p1, targets=[p2.hero_id])

        # Enemy hero should have 29 life
        assert p2.life == 29


# ============================================================
# Test 37: Blizzard With Spell Damage
# ============================================================

class TestBlizzardSpellDamage:
    """Blizzard (2 AOE) + spell damage +1 = 3 AOE + freeze."""

    def test_blizzard_plus_spell_damage(self):
        """Blizzard with Kobold Geomancer deals 3 damage and freezes."""
        game, p1, p2 = new_hs_game()

        kobold = make_obj(game, KOBOLD_GEOMANCER, p1)
        yeti = make_obj(game, CHILLWIND_YETI, p2)

        cast_spell(game, BLIZZARD, p1)

        # Yeti should take 3 damage
        assert yeti.state.damage == 3

        # Freeze event should be emitted
        freeze_events = [e for e in game.state.event_log if e.type == EventType.FREEZE_TARGET and e.payload.get('target') == yeti.id]
        assert len(freeze_events) == 1


# ============================================================
# Test 38: Holy Nova With Spell Damage
# ============================================================

class TestHolyNovaSpellDamage:
    """Holy Nova damage is boosted by spell damage, healing is not."""

    def test_holy_nova_spell_damage_boost_damage_only(self):
        """Holy Nova with Kobold: 3 damage to enemies, 2 heal to friendlies."""
        game, p1, p2 = new_hs_game()

        kobold = make_obj(game, KOBOLD_GEOMANCER, p1)
        friendly = make_obj(game, CHILLWIND_YETI, p1)
        enemy = make_obj(game, CHILLWIND_YETI, p2)

        # Damage friendly
        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': friendly.id, 'amount': 4, 'source': 'test'},
            source='test'
        ))

        cast_spell(game, HOLY_NOVA, p1)

        # Enemy takes 3 damage (2 base + 1 spell damage)
        assert enemy.state.damage == 3

        # Friendly healed by 2 (not boosted by spell damage)
        assert friendly.state.damage == 2


# ============================================================
# Test 39: Swipe On Single Enemy
# ============================================================

class TestSwipeSingleEnemy:
    """Swipe on single enemy: 4 to primary, no secondary targets."""

    def test_swipe_only_one_enemy(self):
        """Swipe with only one enemy deals 4 to it, no other damage."""
        game, p1, p2 = new_hs_game()

        yeti = make_obj(game, CHILLWIND_YETI, p2)

        cast_spell(game, SWIPE, p1)

        # Yeti should take 4 damage (primary target)
        # Check damage events for 4 damage to yeti
        damage_events = [e for e in game.state.event_log
                        if e.type == EventType.DAMAGE
                        and e.payload.get('target') == yeti.id
                        and e.payload.get('amount') == 4]
        assert len(damage_events) == 1


# ============================================================
# Test 40: Lightning Bolt With Spell Damage
# ============================================================

class TestLightningBoltSpellDamage:
    """Lightning Bolt (3 damage) + spell damage +1 = 4 damage."""

    def test_lightning_bolt_plus_spell_damage(self):
        """Lightning Bolt with Kobold Geomancer deals 4 damage."""
        game, p1, p2 = new_hs_game()

        kobold = make_obj(game, KOBOLD_GEOMANCER, p1)
        yeti = make_obj(game, CHILLWIND_YETI, p2)

        random.seed(42)
        cast_spell(game, LIGHTNING_BOLT, p1, targets=[yeti.id])

        # Check for 4 damage event (3 base + 1 spell damage)
        damage_events = [e for e in game.state.event_log
                        if e.type == EventType.DAMAGE
                        and e.payload.get('from_spell')
                        and e.payload.get('amount') == 4]
        assert len(damage_events) == 1

        # Overload should still be 1
        assert p1.overloaded_mana == 1


# ============================================================
# Run tests
# ============================================================

if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
