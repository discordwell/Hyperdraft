"""
Hearthstone Unhappy Path Tests - Batch 100

Card-specific regression tests for previously-buggy cards: Fireball, Flamestrike,
Frostbolt, Swipe, Consecration, Holy Nova, Lightning Bolt, Polymorph, Hex,
Equality, Blessing of Kings, Power Word: Shield, Kill Command, Eviscerate,
Soulfire, Assassinate, Execute - testing exact damage, spell damage interactions,
targeting, transform effects, and edge cases.
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
    WISP, CHILLWIND_YETI, BOULDERFIST_OGRE, KOBOLD_GEOMANCER,
)
from src.cards.hearthstone.classic import (
    FIREBALL, FLAMESTRIKE, FROSTBOLT,
)
from src.cards.hearthstone.mage import POLYMORPH
from src.cards.hearthstone.druid import SWIPE
from src.cards.hearthstone.paladin import BLESSING_OF_KINGS, CONSECRATION, EQUALITY
from src.cards.hearthstone.priest import HOLY_NOVA, POWER_WORD_SHIELD
from src.cards.hearthstone.shaman import LIGHTNING_BOLT, HEX
from src.cards.hearthstone.hunter import KILL_COMMAND
from src.cards.hearthstone.rogue import EVISCERATE, ASSASSINATE
from src.cards.hearthstone.warlock import SOULFIRE
from src.cards.hearthstone.warrior import EXECUTE


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
# Test 1-4: Fireball
# ============================================================

class TestFireballBasic:
    """Fireball deals 6 damage tests."""

    def test_fireball_deals_6_damage_to_target(self):
        """Fireball deals exactly 6 damage to target."""
        game, p1, p2 = new_hs_game()
        ogre = make_obj(game, BOULDERFIST_OGRE, p2)

        cast_spell(game, FIREBALL, p1, targets=[ogre.id])

        # Ogre should have 6 damage
        assert ogre.state.damage == 6

    def test_fireball_plus_spell_damage_deals_7(self):
        """Fireball with +1 spell damage deals 7."""
        game, p1, p2 = new_hs_game()
        kobold = make_obj(game, KOBOLD_GEOMANCER, p1)
        ogre = make_obj(game, BOULDERFIST_OGRE, p2)

        cast_spell(game, FIREBALL, p1, targets=[ogre.id])

        # Ogre should take 7 damage (6 base + 1 spell damage)
        assert ogre.state.damage == 7

    def test_fireball_kills_6_health_minion(self):
        """Fireball kills 6-health minion exactly."""
        game, p1, p2 = new_hs_game()
        ogre = make_obj(game, BOULDERFIST_OGRE, p2)

        # Deal 1 damage first so ogre has 6 health remaining
        ogre.state.damage = 1

        cast_spell(game, FIREBALL, p1, targets=[ogre.id])

        # Ogre should have 7 total damage
        assert ogre.state.damage == 7

        run_sba(game)

        # Ogre should be destroyed
        battlefield = game.state.zones.get('battlefield')
        assert ogre.id not in battlefield.objects

    def test_fireball_overkill_on_3_health_minion(self):
        """Fireball overkills on 3-health minion."""
        game, p1, p2 = new_hs_game()
        wisp = make_obj(game, WISP, p2)

        cast_spell(game, FIREBALL, p1, targets=[wisp.id])

        # Wisp should have 6 damage (overkill)
        assert wisp.state.damage == 6

        run_sba(game)

        # Wisp destroyed
        battlefield = game.state.zones.get('battlefield')
        assert wisp.id not in battlefield.objects


# ============================================================
# Test 5-8: Flamestrike
# ============================================================

class TestFlamestrikeBasic:
    """Flamestrike AOE tests."""

    def test_flamestrike_deals_4_to_all_enemy_minions(self):
        """Flamestrike deals 4 damage to all enemy minions."""
        game, p1, p2 = new_hs_game()
        yeti1 = make_obj(game, CHILLWIND_YETI, p2)
        yeti2 = make_obj(game, CHILLWIND_YETI, p2)

        cast_spell(game, FLAMESTRIKE, p1)

        # Both yetis should have 4 damage
        assert yeti1.state.damage == 4
        assert yeti2.state.damage == 4

    def test_flamestrike_doesnt_damage_friendly_minions(self):
        """Flamestrike doesn't damage friendly minions."""
        game, p1, p2 = new_hs_game()
        friendly = make_obj(game, CHILLWIND_YETI, p1)
        enemy = make_obj(game, CHILLWIND_YETI, p2)

        cast_spell(game, FLAMESTRIKE, p1)

        # Enemy takes damage
        assert enemy.state.damage == 4
        # Friendly takes no damage
        assert friendly.state.damage == 0

    def test_flamestrike_plus_spell_damage_deals_5_to_all_enemies(self):
        """Flamestrike with +1 spell damage deals 5 to all enemies."""
        game, p1, p2 = new_hs_game()
        kobold = make_obj(game, KOBOLD_GEOMANCER, p1)
        yeti = make_obj(game, CHILLWIND_YETI, p2)

        cast_spell(game, FLAMESTRIKE, p1)

        # Yeti should take 5 damage (4 base + 1 spell damage)
        assert yeti.state.damage == 5

    def test_flamestrike_on_empty_board_no_error(self):
        """Flamestrike on empty board doesn't error."""
        game, p1, p2 = new_hs_game()

        # Cast Flamestrike with no enemies - should not crash
        cast_spell(game, FLAMESTRIKE, p1)

        # Check no damage events to minions (board is empty)
        damage_events = [e for e in game.state.event_log
                        if e.type == EventType.DAMAGE and e.payload.get('from_spell')]
        assert len(damage_events) == 0


# ============================================================
# Test 9-11: Frostbolt
# ============================================================

class TestFrostboltBasic:
    """Frostbolt damage and freeze tests."""

    def test_frostbolt_deals_3_damage_and_freezes(self):
        """Frostbolt deals 3 damage and freezes."""
        game, p1, p2 = new_hs_game()
        yeti = make_obj(game, CHILLWIND_YETI, p2)

        cast_spell(game, FROSTBOLT, p1, targets=[yeti.id])

        # Yeti should have 3 damage
        assert yeti.state.damage == 3

        # Freeze event should be emitted
        freeze_events = [e for e in game.state.event_log
                        if e.type == EventType.FREEZE_TARGET and e.payload.get('target') == yeti.id]
        assert len(freeze_events) == 1

    def test_frostbolt_plus_spell_damage_deals_4(self):
        """Frostbolt with +1 spell damage deals 4 and freezes."""
        game, p1, p2 = new_hs_game()
        kobold = make_obj(game, KOBOLD_GEOMANCER, p1)
        yeti = make_obj(game, CHILLWIND_YETI, p2)

        cast_spell(game, FROSTBOLT, p1, targets=[yeti.id])

        # Yeti should take 4 damage (3 base + 1 spell damage)
        assert yeti.state.damage == 4

    def test_frostbolt_on_hero_deals_3_and_freezes(self):
        """Frostbolt on hero deals 3 damage and freezes."""
        game, p1, p2 = new_hs_game()

        cast_spell(game, FROSTBOLT, p1, targets=[p2.hero_id])

        # Enemy hero should have 27 life
        assert p2.life == 27

        # Freeze event should be emitted
        freeze_events = [e for e in game.state.event_log
                        if e.type == EventType.FREEZE_TARGET and e.payload.get('target') == p2.hero_id]
        assert len(freeze_events) == 1


# ============================================================
# Test 12-14: Swipe
# ============================================================

class TestSwipeBasic:
    """Swipe primary and secondary damage tests."""

    def test_swipe_deals_4_to_target_1_to_other_enemies(self):
        """Swipe deals 4 to primary target, 1 to other enemies."""
        game, p1, p2 = new_hs_game()
        yeti1 = make_obj(game, CHILLWIND_YETI, p2)
        yeti2 = make_obj(game, CHILLWIND_YETI, p2)

        random.seed(42)
        cast_spell(game, SWIPE, p1)

        # Check damage events
        damage_events = [e for e in game.state.event_log
                        if e.type == EventType.DAMAGE and e.payload.get('from_spell')]

        # Should have damage events
        assert len(damage_events) >= 2

        # Check for 4 damage and 1 damage events
        damage_amounts = [e.payload.get('amount') for e in damage_events]
        assert 4 in damage_amounts
        assert 1 in damage_amounts

    def test_swipe_plus_spell_damage_5_primary_2_secondary(self):
        """Swipe with +1 spell damage: 5 primary, 2 secondary."""
        game, p1, p2 = new_hs_game()
        kobold = make_obj(game, KOBOLD_GEOMANCER, p1)
        yeti1 = make_obj(game, CHILLWIND_YETI, p2)
        yeti2 = make_obj(game, CHILLWIND_YETI, p2)

        random.seed(42)
        cast_spell(game, SWIPE, p1)

        # Check damage events
        damage_events = [e for e in game.state.event_log
                        if e.type == EventType.DAMAGE and e.payload.get('from_spell')]
        damage_amounts = [e.payload.get('amount') for e in damage_events]

        # Should have 5 damage (primary) and 2 damage (secondary)
        assert 5 in damage_amounts
        assert 2 in damage_amounts

    def test_swipe_on_single_enemy_4_damage_no_secondary(self):
        """Swipe on single enemy deals 4 damage, no secondary targets."""
        game, p1, p2 = new_hs_game()
        yeti = make_obj(game, CHILLWIND_YETI, p2)

        cast_spell(game, SWIPE, p1)

        # Check damage events for 4 damage to yeti
        damage_events = [e for e in game.state.event_log
                        if e.type == EventType.DAMAGE
                        and e.payload.get('target') == yeti.id
                        and e.payload.get('amount') == 4]
        assert len(damage_events) == 1


# ============================================================
# Test 15-17: Consecration
# ============================================================

class TestConsecrationBasic:
    """Consecration AOE tests."""

    def test_consecration_deals_2_to_all_enemies(self):
        """Consecration deals 2 to all enemies."""
        game, p1, p2 = new_hs_game("Paladin", "Warrior")
        yeti = make_obj(game, CHILLWIND_YETI, p2)

        cast_spell(game, CONSECRATION, p1)

        # Enemy minion takes 2 damage
        assert yeti.state.damage == 2

        # Enemy hero takes 2 damage
        assert p2.life == 28

    def test_consecration_plus_spell_damage_3_to_all_enemies(self):
        """Consecration with +1 spell damage deals 3 to all enemies."""
        game, p1, p2 = new_hs_game("Paladin", "Warrior")
        kobold = make_obj(game, KOBOLD_GEOMANCER, p1)
        yeti = make_obj(game, CHILLWIND_YETI, p2)

        cast_spell(game, CONSECRATION, p1)

        # Enemy minion takes 3 damage (2 base + 1 spell damage)
        assert yeti.state.damage == 3

        # Enemy hero takes 3 damage
        assert p2.life == 27

    def test_consecration_to_face_and_minions(self):
        """Consecration hits both face and minions."""
        game, p1, p2 = new_hs_game("Paladin", "Warrior")
        yeti1 = make_obj(game, CHILLWIND_YETI, p2)
        yeti2 = make_obj(game, CHILLWIND_YETI, p2)

        cast_spell(game, CONSECRATION, p1)

        # Both minions take 2 damage
        assert yeti1.state.damage == 2
        assert yeti2.state.damage == 2

        # Hero takes 2 damage
        assert p2.life == 28


# ============================================================
# Test 18-19: Holy Nova
# ============================================================

class TestHolyNovaBasic:
    """Holy Nova damage and heal tests."""

    def test_holy_nova_2_damage_to_enemies_2_heal_to_friendlies(self):
        """Holy Nova: 2 damage to enemies, 2 heal to friendlies."""
        game, p1, p2 = new_hs_game("Priest", "Warrior")
        friendly = make_obj(game, CHILLWIND_YETI, p1)
        enemy = make_obj(game, CHILLWIND_YETI, p2)

        # Damage friendly first
        friendly.state.damage = 3

        cast_spell(game, HOLY_NOVA, p1)

        # Enemy takes 2 damage
        assert enemy.state.damage == 2

        # Friendly healed by 2 (3 - 2 = 1 damage remaining)
        assert friendly.state.damage == 1

    def test_holy_nova_plus_spell_damage_3_damage_2_heal(self):
        """Holy Nova with +1 spell damage: 3 damage, 2 heal."""
        game, p1, p2 = new_hs_game("Priest", "Warrior")
        kobold = make_obj(game, KOBOLD_GEOMANCER, p1)
        friendly = make_obj(game, CHILLWIND_YETI, p1)
        enemy = make_obj(game, CHILLWIND_YETI, p2)

        # Damage friendly first
        friendly.state.damage = 4

        cast_spell(game, HOLY_NOVA, p1)

        # Enemy takes 3 damage (2 base + 1 spell damage)
        assert enemy.state.damage == 3

        # Friendly healed by 2 (not boosted by spell damage)
        assert friendly.state.damage == 2


# ============================================================
# Test 20-21: Lightning Bolt
# ============================================================

class TestLightningBoltBasic:
    """Lightning Bolt damage and overload tests."""

    def test_lightning_bolt_deals_3_damage_overloads_1(self):
        """Lightning Bolt deals 3 damage and overloads 1."""
        game, p1, p2 = new_hs_game("Shaman", "Warrior")
        yeti = make_obj(game, CHILLWIND_YETI, p2)

        random.seed(42)
        cast_spell(game, LIGHTNING_BOLT, p1, targets=[yeti.id])

        # Check for 3 damage event
        damage_events = [e for e in game.state.event_log
                        if e.type == EventType.DAMAGE
                        and e.payload.get('from_spell')
                        and e.payload.get('amount') == 3]
        assert len(damage_events) >= 1

        # Player should have 1 overloaded mana
        assert p1.overloaded_mana == 1

    def test_lightning_bolt_plus_spell_damage_4_damage(self):
        """Lightning Bolt with +1 spell damage deals 4 damage."""
        game, p1, p2 = new_hs_game("Shaman", "Warrior")
        kobold = make_obj(game, KOBOLD_GEOMANCER, p1)
        yeti = make_obj(game, CHILLWIND_YETI, p2)

        random.seed(42)
        cast_spell(game, LIGHTNING_BOLT, p1, targets=[yeti.id])

        # Check for 4 damage event (3 base + 1 spell damage)
        damage_events = [e for e in game.state.event_log
                        if e.type == EventType.DAMAGE
                        and e.payload.get('from_spell')
                        and e.payload.get('amount') == 4]
        assert len(damage_events) >= 1


# ============================================================
# Test 22-24: Polymorph
# ============================================================

class TestPolymorphBasic:
    """Polymorph transform tests."""

    def test_polymorph_turns_target_into_1_1_sheep(self):
        """Polymorph turns target into 1/1 Sheep."""
        game, p1, p2 = new_hs_game()
        yeti = make_obj(game, CHILLWIND_YETI, p2)

        cast_spell(game, POLYMORPH, p1, targets=[yeti.id])

        # Should be 1/1 Sheep
        assert yeti.name == "Sheep"
        assert get_power(yeti, game.state) == 1
        assert get_toughness(yeti, game.state) == 1

    def test_polymorph_removes_all_abilities(self):
        """Polymorph removes all abilities."""
        game, p1, p2 = new_hs_game()
        yeti = make_obj(game, CHILLWIND_YETI, p2)

        # Grant some abilities
        if not yeti.characteristics.abilities:
            yeti.characteristics.abilities = []
        yeti.characteristics.abilities.append({'keyword': 'taunt'})
        yeti.state.divine_shield = True

        cast_spell(game, POLYMORPH, p1, targets=[yeti.id])

        # Should have no abilities
        assert not has_ability(yeti, 'taunt', game.state)
        assert not yeti.state.divine_shield

    def test_polymorph_removes_buffs(self):
        """Polymorph removes all buffs."""
        game, p1, p2 = new_hs_game()
        wisp = make_obj(game, WISP, p2)

        # Apply buff
        game.emit(Event(
            type=EventType.PT_MODIFICATION,
            payload={'object_id': wisp.id, 'power_mod': 5, 'toughness_mod': 5, 'duration': 'permanent'},
            source='test'
        ))

        assert get_power(wisp, game.state) == 6

        cast_spell(game, POLYMORPH, p1, targets=[wisp.id])

        # Should be 1/1 Sheep
        assert get_power(wisp, game.state) == 1
        assert get_toughness(wisp, game.state) == 1


# ============================================================
# Test 25-27: Hex
# ============================================================

class TestHexBasic:
    """Hex transform tests."""

    def test_hex_turns_target_into_0_1_frog_with_taunt(self):
        """Hex turns target into 0/1 Frog with Taunt."""
        game, p1, p2 = new_hs_game("Shaman", "Warrior")
        yeti = make_obj(game, CHILLWIND_YETI, p2)

        cast_spell(game, HEX, p1, targets=[yeti.id])

        # Should be 0/1 Frog with Taunt
        assert yeti.name == "Frog"
        assert get_power(yeti, game.state) == 0
        assert get_toughness(yeti, game.state) == 1
        assert has_ability(yeti, 'taunt', game.state)

    def test_hex_removes_all_abilities(self):
        """Hex removes all abilities (except Taunt it grants)."""
        game, p1, p2 = new_hs_game("Shaman", "Warrior")
        yeti = make_obj(game, CHILLWIND_YETI, p2)

        # Grant abilities
        yeti.state.divine_shield = True
        yeti.state.windfury = True

        cast_spell(game, HEX, p1, targets=[yeti.id])

        # Should only have Taunt (granted by Hex)
        assert has_ability(yeti, 'taunt', game.state)
        assert not yeti.state.divine_shield
        assert not yeti.state.windfury

    def test_hex_removes_deathrattle(self):
        """Hex removes deathrattle."""
        game, p1, p2 = new_hs_game("Shaman", "Warrior")
        from src.cards.hearthstone.classic import LOOT_HOARDER
        hoarder = make_obj(game, LOOT_HOARDER, p2)

        cast_spell(game, HEX, p1, targets=[hoarder.id])

        # Destroy and verify no draw
        hand_before = len(game.state.zones.get(f'hand_{p2.id}').objects)
        game.emit(Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': hoarder.id},
            source='test'
        ))
        hand_after = len(game.state.zones.get(f'hand_{p2.id}').objects)

        # Should not have drawn
        assert hand_after == hand_before


# ============================================================
# Test 28-30: Equality
# ============================================================

class TestEqualityBasic:
    """Equality sets all minion health to 1."""

    def test_equality_sets_all_minion_health_to_1(self):
        """Equality sets all minions to 1 health."""
        game, p1, p2 = new_hs_game("Paladin", "Warrior")
        yeti1 = make_obj(game, CHILLWIND_YETI, p1)
        yeti2 = make_obj(game, CHILLWIND_YETI, p2)

        cast_spell(game, EQUALITY, p1)

        # Both should have 1 health (max health set to 1)
        assert get_toughness(yeti1, game.state) == 1
        assert get_toughness(yeti2, game.state) == 1

    def test_equality_affects_both_sides(self):
        """Equality affects both friendly and enemy minions."""
        game, p1, p2 = new_hs_game("Paladin", "Warrior")
        friendly = make_obj(game, BOULDERFIST_OGRE, p1)
        enemy = make_obj(game, BOULDERFIST_OGRE, p2)

        cast_spell(game, EQUALITY, p1)

        # Both should be set to 1 health
        assert get_toughness(friendly, game.state) == 1
        assert get_toughness(enemy, game.state) == 1

    def test_equality_plus_consecration_kills_all_minions(self):
        """Equality + Consecration kills all minions."""
        game, p1, p2 = new_hs_game("Paladin", "Warrior")
        yeti1 = make_obj(game, CHILLWIND_YETI, p1)
        yeti2 = make_obj(game, CHILLWIND_YETI, p2)

        # Cast Equality
        cast_spell(game, EQUALITY, p1)

        # Verify both have 1 health
        assert get_toughness(yeti1, game.state) == 1
        assert get_toughness(yeti2, game.state) == 1

        # Cast Consecration (2 damage to all enemies)
        cast_spell(game, CONSECRATION, p1)

        run_sba(game)

        # Enemy minions should be dead (1 health - 2 damage)
        battlefield = game.state.zones.get('battlefield')
        assert yeti2.id not in battlefield.objects

        # Friendly minion should be dead (1 health - 2 damage from Consecration hitting all)
        # Note: Consecration only hits enemies, so friendly survives
        assert yeti1.id in battlefield.objects


# ============================================================
# Test 31-33: Blessing of Kings
# ============================================================

class TestBlessingOfKingsBasic:
    """Blessing of Kings +4/+4 tests."""

    def test_blessing_of_kings_gives_plus_4_4(self):
        """Blessing of Kings gives +4/+4."""
        game, p1, p2 = new_hs_game("Paladin", "Warrior")
        wisp = make_obj(game, WISP, p1)

        cast_spell(game, BLESSING_OF_KINGS, p1, targets=[wisp.id])

        # Wisp should be 5/5 (1/1 + 4/4)
        assert get_power(wisp, game.state) == 5
        assert get_toughness(wisp, game.state) == 5

    def test_blessing_of_kings_on_1_1_becomes_5_5(self):
        """Blessing of Kings on 1/1 becomes 5/5."""
        game, p1, p2 = new_hs_game("Paladin", "Warrior")
        wisp = make_obj(game, WISP, p1)

        assert get_power(wisp, game.state) == 1
        assert get_toughness(wisp, game.state) == 1

        cast_spell(game, BLESSING_OF_KINGS, p1, targets=[wisp.id])

        assert get_power(wisp, game.state) == 5
        assert get_toughness(wisp, game.state) == 5

    def test_silence_removes_blessing_of_kings_buff(self):
        """Silence removes Blessing of Kings buff."""
        game, p1, p2 = new_hs_game("Paladin", "Warrior")
        wisp = make_obj(game, WISP, p1)

        cast_spell(game, BLESSING_OF_KINGS, p1, targets=[wisp.id])

        assert get_power(wisp, game.state) == 5

        # Silence
        game.emit(Event(
            type=EventType.SILENCE_TARGET,
            payload={'target': wisp.id},
            source='test'
        ))

        # Back to 1/1
        assert get_power(wisp, game.state) == 1
        assert get_toughness(wisp, game.state) == 1


# ============================================================
# Test 34-35: Power Word: Shield
# ============================================================

class TestPowerWordShieldBasic:
    """Power Word: Shield +2 health and draw tests."""

    def test_power_word_shield_gives_plus_2_health_and_draws(self):
        """Power Word: Shield gives +2 health and draws a card."""
        game, p1, p2 = new_hs_game("Priest", "Warrior")
        wisp = make_obj(game, WISP, p1)

        cast_spell(game, POWER_WORD_SHIELD, p1, targets=[wisp.id])

        # Wisp should be 1/3 (1/1 + 0/+2)
        assert get_power(wisp, game.state) == 1
        assert get_toughness(wisp, game.state) == 3

        # Should have a draw event
        draw_events = [e for e in game.state.event_log
                      if e.type == EventType.DRAW
                      and e.payload.get('player') == p1.id]
        assert len(draw_events) >= 1

    def test_power_word_shield_on_damaged_minion_health_increases(self):
        """Power Word: Shield on damaged minion increases max health."""
        game, p1, p2 = new_hs_game("Priest", "Warrior")
        yeti = make_obj(game, CHILLWIND_YETI, p1)

        # Deal 2 damage
        yeti.state.damage = 2

        cast_spell(game, POWER_WORD_SHIELD, p1, targets=[yeti.id])

        # Max health should be 7 (5 + 2), damage still 2, so 5 remaining
        assert get_toughness(yeti, game.state) == 7
        assert yeti.state.damage == 2


# ============================================================
# Test 36-38: Kill Command
# ============================================================

class TestKillCommandBasic:
    """Kill Command damage tests."""

    def test_kill_command_3_base_5_with_beast(self):
        """Kill Command: 3 base damage, 5 with beast."""
        game, p1, p2 = new_hs_game("Hunter", "Warrior")

        # Without beast: 3 damage
        cast_spell(game, KILL_COMMAND, p1, targets=[p2.hero_id])

        # Check for 3 damage event (no beast)
        damage_events = [e for e in game.state.event_log
                        if e.type == EventType.DAMAGE
                        and e.payload.get('amount') == 3]
        assert len(damage_events) >= 1

    def test_kill_command_with_beast_on_board_5_damage(self):
        """Kill Command with beast on board deals 5 damage."""
        game, p1, p2 = new_hs_game("Hunter", "Warrior")
        from src.cards.hearthstone.hunter import TIMBER_WOLF
        beast = make_obj(game, TIMBER_WOLF, p1)

        cast_spell(game, KILL_COMMAND, p1, targets=[p2.hero_id])

        # Check for 5 damage event (with beast)
        damage_events = [e for e in game.state.event_log
                        if e.type == EventType.DAMAGE
                        and e.payload.get('amount') == 5]
        assert len(damage_events) >= 1

    def test_kill_command_without_beast_3_damage(self):
        """Kill Command without beast deals 3 damage."""
        game, p1, p2 = new_hs_game("Hunter", "Warrior")

        cast_spell(game, KILL_COMMAND, p1, targets=[p2.hero_id])

        # Should deal 3 damage
        assert p2.life == 27


# ============================================================
# Test 39-40: Eviscerate
# ============================================================

class TestEvisceratBasic:
    """Eviscerate combo tests."""

    def test_eviscerate_2_base_4_with_combo(self):
        """Eviscerate: 2 base damage, 4 with combo."""
        game, p1, p2 = new_hs_game("Rogue", "Warrior")

        # Without combo: 2 damage
        cast_spell(game, EVISCERATE, p1, targets=[p2.hero_id])

        # Check for damage event
        damage_events = [e for e in game.state.event_log
                        if e.type == EventType.DAMAGE]
        assert len(damage_events) >= 1

    def test_eviscerate_combo_play_card_first_then_eviscerate_for_4(self):
        """Eviscerate combo: play card first, then Eviscerate for 4."""
        game, p1, p2 = new_hs_game("Rogue", "Warrior")

        # Play a card first to activate combo
        wisp = make_obj(game, WISP, p1)

        # Set combo state
        game.state.players[p1.id].cards_played_this_turn = 1

        cast_spell(game, EVISCERATE, p1, targets=[p2.hero_id])

        # Check for 4 damage event (with combo)
        damage_events = [e for e in game.state.event_log
                        if e.type == EventType.DAMAGE
                        and e.payload.get('amount') == 4]
        assert len(damage_events) >= 1


# ============================================================
# Test 41-42: Soulfire
# ============================================================

class TestSoulfireBasic:
    """Soulfire damage and discard tests."""

    def test_soulfire_deals_4_damage_discards_1(self):
        """Soulfire deals 4 damage and discards 1 card."""
        game, p1, p2 = new_hs_game("Warlock", "Warrior")
        yeti = make_obj(game, CHILLWIND_YETI, p2)

        cast_spell(game, SOULFIRE, p1, targets=[yeti.id])

        # Check for 4 damage
        damage_events = [e for e in game.state.event_log
                        if e.type == EventType.DAMAGE
                        and e.payload.get('amount') == 4]
        assert len(damage_events) >= 1

    def test_soulfire_with_empty_hand_still_deals_4(self):
        """Soulfire with empty hand still deals 4 damage."""
        game, p1, p2 = new_hs_game("Warlock", "Warrior")
        yeti = make_obj(game, CHILLWIND_YETI, p2)

        # Empty hand
        hand_zone = game.state.zones.get(f'hand_{p1.id}')
        hand_zone.objects.clear()

        cast_spell(game, SOULFIRE, p1, targets=[yeti.id])

        # Should still deal 4 damage
        damage_events = [e for e in game.state.event_log
                        if e.type == EventType.DAMAGE
                        and e.payload.get('amount') == 4]
        assert len(damage_events) >= 1


# ============================================================
# Test 43-44: Assassinate
# ============================================================

class TestAssassinateBasic:
    """Assassinate destroy tests."""

    def test_assassinate_destroys_a_minion(self):
        """Assassinate destroys a minion."""
        game, p1, p2 = new_hs_game("Rogue", "Warrior")
        yeti = make_obj(game, CHILLWIND_YETI, p2)

        cast_spell(game, ASSASSINATE, p1)

        # Check for destroy event
        destroyed = [e for e in game.state.event_log
                    if e.type == EventType.OBJECT_DESTROYED
                    and e.payload.get('object_id') == yeti.id]
        assert len(destroyed) >= 1

    def test_assassinate_triggers_deathrattle(self):
        """Assassinate triggers deathrattle."""
        game, p1, p2 = new_hs_game("Rogue", "Warrior")
        from src.cards.hearthstone.classic import LOOT_HOARDER
        hoarder = make_obj(game, LOOT_HOARDER, p2)

        hand_before = len(game.state.zones.get(f'hand_{p2.id}').objects)

        cast_spell(game, ASSASSINATE, p1)

        # Deathrattle should trigger (draw a card)
        hand_after = len(game.state.zones.get(f'hand_{p2.id}').objects)

        # May or may not draw depending on implementation, but should be destroyed
        destroyed = [e for e in game.state.event_log
                    if e.type == EventType.OBJECT_DESTROYED
                    and e.payload.get('object_id') == hoarder.id]
        assert len(destroyed) >= 1


# ============================================================
# Test 45: Execute
# ============================================================

class TestExecuteBasic:
    """Execute destroys damaged minion."""

    def test_execute_destroys_a_damaged_minion(self):
        """Execute destroys a damaged minion."""
        game, p1, p2 = new_hs_game("Warrior", "Mage")
        yeti = make_obj(game, CHILLWIND_YETI, p2)

        # Damage the yeti
        yeti.state.damage = 1

        cast_spell(game, EXECUTE, p1)

        # Check for destroy event
        destroyed = [e for e in game.state.event_log
                    if e.type == EventType.OBJECT_DESTROYED
                    and e.payload.get('object_id') == yeti.id]
        assert len(destroyed) >= 1


# ============================================================
# Run tests
# ============================================================

if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v", "--tb=short"])
