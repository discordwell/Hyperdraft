"""
Hearthstone Unhappy Path Tests - Batch 63

Warrior mechanics and neutral legendary interactions: Execute destroy
conditional (damaged only), Shield Slam armor-based damage, Armor Up
hero power, Shield Block armor+draw, Mortal Strike threshold damage,
Brawl random survival, Slam damage+draw conditional, Cruel Taskmaster
damage+buff, Frothing Berserker damage trigger, Grommash Hellscream
enrage charge, Armorsmith armor on friendly damage, Ragnaros end-of-turn
random 8, Ysera dream card generation, Alexstrasza health set to 15,
Leeroy Jenkins summon Whelps for opponent, Deathwing destroy all + discard.
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
from src.cards.hearthstone.hero_powers import HERO_POWERS, ARMOR_UP

from src.cards.hearthstone.basic import (
    WISP, CHILLWIND_YETI, BLOODFEN_RAPTOR, BOULDERFIST_OGRE,
)
from src.cards.hearthstone.warrior import (
    EXECUTE, SHIELD_SLAM, SHIELD_BLOCK, MORTAL_STRIKE, BRAWL,
    SLAM, CRUEL_TASKMASTER, FROTHING_BERSERKER, GROMMASH_HELLSCREAM,
    ARMORSMITH,
)
from src.cards.hearthstone.classic import (
    RAGNAROS_THE_FIRELORD, ALEXSTRASZA, LEEROY_JENKINS, DEATHWING,
    YSERA,
)


# ============================================================
# Test Helpers
# ============================================================

def new_hs_game():
    game = Game(mode='hearthstone')
    p1 = game.add_player("Player1", life=30)
    p2 = game.add_player("Player2", life=30)
    game.setup_hearthstone_player(p1, HEROES["Warrior"], HERO_POWERS["Warrior"])
    game.setup_hearthstone_player(p2, HEROES["Mage"], HERO_POWERS["Mage"])
    for _ in range(10):
        game.mana_system.on_turn_start(p1.id)
        game.mana_system.on_turn_start(p2.id)
    return game, p1, p2


def make_obj(game, card_def, owner, zone=ZoneType.BATTLEFIELD):
    return game.create_object(
        name=card_def.name, owner_id=owner.id, zone=zone,
        characteristics=card_def.characteristics, card_def=card_def
    )


def cast_spell(game, card_def, owner, targets=None):
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


def get_battlefield_minions(game, player):
    """Get all minion objects on battlefield controlled by player."""
    bf = game.state.zones.get('battlefield')
    if not bf:
        return []
    result = []
    for oid in bf.objects:
        obj = game.state.objects.get(oid)
        if obj and obj.controller == player.id and CardType.MINION in obj.characteristics.types:
            result.append(obj)
    return result


def get_all_battlefield_minions(game):
    """Get all minion objects on battlefield."""
    bf = game.state.zones.get('battlefield')
    if not bf:
        return []
    result = []
    for oid in bf.objects:
        obj = game.state.objects.get(oid)
        if obj and CardType.MINION in obj.characteristics.types:
            result.append(obj)
    return result


# ============================================================
# Test 1: Execute
# ============================================================

class TestExecute:
    def test_execute_destroys_damaged_enemy_minion(self):
        """Execute should destroy a damaged enemy minion."""
        game, p1, p2 = new_hs_game()
        enemy_minion = make_obj(game, CHILLWIND_YETI, p2)  # 4/5

        # Damage the minion first
        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': enemy_minion.id, 'amount': 1, 'source': 'test'},
            source='test'
        ))
        assert enemy_minion.state.damage > 0, "Minion should be damaged"

        # Cast Execute
        # Seed random so it picks our damaged minion
        random.seed(42)
        cast_spell(game, EXECUTE, p1)

        # The OBJECT_DESTROYED event should have been emitted for the damaged minion
        # Check if the minion is destroyed (moved out of battlefield or marked)
        bf = game.state.zones.get('battlefield')
        bf_ids = list(bf.objects) if bf else []
        assert enemy_minion.id not in bf_ids or enemy_minion.zone != ZoneType.BATTLEFIELD, (
            "Damaged enemy minion should be destroyed by Execute"
        )

    def test_execute_does_not_destroy_undamaged_minion(self):
        """Execute should NOT destroy an undamaged enemy minion."""
        game, p1, p2 = new_hs_game()
        enemy_minion = make_obj(game, CHILLWIND_YETI, p2)  # 4/5, undamaged

        # Cast Execute - no damaged targets, should do nothing
        obj = game.create_object(
            name=EXECUTE.name, owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
            characteristics=EXECUTE.characteristics, card_def=EXECUTE
        )
        events = EXECUTE.spell_effect(obj, game.state, [])

        assert events == [], (
            f"Execute should produce no events when no damaged enemy exists, got {events}"
        )

        # Minion should still be on battlefield
        bf = game.state.zones.get('battlefield')
        bf_ids = list(bf.objects) if bf else []
        assert enemy_minion.id in bf_ids, (
            "Undamaged enemy minion should survive Execute"
        )

    def test_execute_ignores_friendly_damaged_minion(self):
        """Execute only targets enemy damaged minions, not friendly ones."""
        game, p1, p2 = new_hs_game()
        friendly_minion = make_obj(game, CHILLWIND_YETI, p1)  # friendly

        # Damage the friendly minion
        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': friendly_minion.id, 'amount': 1, 'source': 'test'},
            source='test'
        ))

        # Cast Execute - should find no valid target (only enemies count)
        obj = game.create_object(
            name=EXECUTE.name, owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
            characteristics=EXECUTE.characteristics, card_def=EXECUTE
        )
        events = EXECUTE.spell_effect(obj, game.state, [])

        assert events == [], (
            "Execute should not target friendly damaged minions"
        )


# ============================================================
# Test 2: Shield Slam
# ============================================================

class TestShieldSlam:
    def test_shield_slam_deals_armor_damage(self):
        """Shield Slam deals damage equal to armor."""
        game, p1, p2 = new_hs_game()
        p1.armor = 5
        enemy = make_obj(game, BOULDERFIST_OGRE, p2)  # 6/7

        random.seed(42)
        obj = game.create_object(
            name=SHIELD_SLAM.name, owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
            characteristics=SHIELD_SLAM.characteristics, card_def=SHIELD_SLAM
        )
        events = SHIELD_SLAM.spell_effect(obj, game.state, [])

        assert len(events) == 1, f"Shield Slam should produce 1 damage event, got {len(events)}"
        assert events[0].type == EventType.DAMAGE
        assert events[0].payload['amount'] == 5, (
            f"Shield Slam should deal 5 damage with 5 armor, got {events[0].payload['amount']}"
        )

    def test_shield_slam_zero_armor_no_damage(self):
        """Shield Slam with 0 armor should do nothing."""
        game, p1, p2 = new_hs_game()
        p1.armor = 0
        enemy = make_obj(game, CHILLWIND_YETI, p2)

        obj = game.create_object(
            name=SHIELD_SLAM.name, owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
            characteristics=SHIELD_SLAM.characteristics, card_def=SHIELD_SLAM
        )
        events = SHIELD_SLAM.spell_effect(obj, game.state, [])

        assert events == [], (
            "Shield Slam with 0 armor should produce no events"
        )

    def test_shield_slam_high_armor(self):
        """Shield Slam with 10 armor deals 10 damage."""
        game, p1, p2 = new_hs_game()
        p1.armor = 10
        enemy = make_obj(game, CHILLWIND_YETI, p2)

        random.seed(42)
        obj = game.create_object(
            name=SHIELD_SLAM.name, owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
            characteristics=SHIELD_SLAM.characteristics, card_def=SHIELD_SLAM
        )
        events = SHIELD_SLAM.spell_effect(obj, game.state, [])

        assert len(events) == 1
        assert events[0].payload['amount'] == 10, (
            f"Shield Slam should deal 10 damage with 10 armor, got {events[0].payload['amount']}"
        )


# ============================================================
# Test 3: Shield Block
# ============================================================

class TestShieldBlock:
    def test_shield_block_gives_armor_and_draws(self):
        """Shield Block should give 5 armor and draw a card."""
        game, p1, p2 = new_hs_game()

        obj = game.create_object(
            name=SHIELD_BLOCK.name, owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
            characteristics=SHIELD_BLOCK.characteristics, card_def=SHIELD_BLOCK
        )
        events = SHIELD_BLOCK.spell_effect(obj, game.state, [])

        assert len(events) == 2, f"Shield Block should produce 2 events, got {len(events)}"

        armor_event = events[0]
        draw_event = events[1]

        assert armor_event.type == EventType.ARMOR_GAIN
        assert armor_event.payload['amount'] == 5, (
            f"Shield Block should give 5 armor, got {armor_event.payload['amount']}"
        )
        assert armor_event.payload['player'] == p1.id

        assert draw_event.type == EventType.DRAW
        assert draw_event.payload['count'] == 1
        assert draw_event.payload['player'] == p1.id


# ============================================================
# Test 4: Mortal Strike
# ============================================================

class TestMortalStrike:
    def test_mortal_strike_normal_4_damage(self):
        """Mortal Strike deals 4 damage when hero has > 12 HP."""
        game, p1, p2 = new_hs_game()
        p1.life = 30  # well above 12

        random.seed(42)
        obj = game.create_object(
            name=MORTAL_STRIKE.name, owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
            characteristics=MORTAL_STRIKE.characteristics, card_def=MORTAL_STRIKE
        )
        events = MORTAL_STRIKE.spell_effect(obj, game.state, [])

        assert len(events) == 1
        assert events[0].type == EventType.DAMAGE
        assert events[0].payload['amount'] == 4, (
            f"Mortal Strike should deal 4 damage at 30 HP, got {events[0].payload['amount']}"
        )

    def test_mortal_strike_threshold_6_damage(self):
        """Mortal Strike deals 6 damage when hero has <= 12 HP."""
        game, p1, p2 = new_hs_game()
        p1.life = 12  # exactly at threshold

        random.seed(42)
        obj = game.create_object(
            name=MORTAL_STRIKE.name, owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
            characteristics=MORTAL_STRIKE.characteristics, card_def=MORTAL_STRIKE
        )
        events = MORTAL_STRIKE.spell_effect(obj, game.state, [])

        assert len(events) == 1
        assert events[0].payload['amount'] == 6, (
            f"Mortal Strike should deal 6 at 12 HP, got {events[0].payload['amount']}"
        )

    def test_mortal_strike_low_hp_6_damage(self):
        """Mortal Strike deals 6 damage when hero has < 12 HP."""
        game, p1, p2 = new_hs_game()
        p1.life = 5  # well below 12

        random.seed(42)
        obj = game.create_object(
            name=MORTAL_STRIKE.name, owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
            characteristics=MORTAL_STRIKE.characteristics, card_def=MORTAL_STRIKE
        )
        events = MORTAL_STRIKE.spell_effect(obj, game.state, [])

        assert len(events) == 1
        assert events[0].payload['amount'] == 6, (
            f"Mortal Strike should deal 6 at 5 HP, got {events[0].payload['amount']}"
        )


# ============================================================
# Test 5: Brawl
# ============================================================

class TestBrawl:
    def test_brawl_leaves_one_survivor(self):
        """Brawl should destroy all minions except one."""
        game, p1, p2 = new_hs_game()
        m1 = make_obj(game, WISP, p1)
        m2 = make_obj(game, CHILLWIND_YETI, p1)
        m3 = make_obj(game, BLOODFEN_RAPTOR, p2)
        m4 = make_obj(game, BOULDERFIST_OGRE, p2)

        random.seed(42)
        obj = game.create_object(
            name=BRAWL.name, owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
            characteristics=BRAWL.characteristics, card_def=BRAWL
        )
        events = BRAWL.spell_effect(obj, game.state, [])

        # Should destroy 3 out of 4 minions
        destroy_events = [e for e in events if e.type == EventType.OBJECT_DESTROYED]
        assert len(destroy_events) == 3, (
            f"Brawl should destroy 3 of 4 minions, got {len(destroy_events)} destroyed"
        )

        destroyed_ids = {e.payload['object_id'] for e in destroy_events}
        all_ids = {m1.id, m2.id, m3.id, m4.id}
        survivors = all_ids - destroyed_ids
        assert len(survivors) == 1, (
            f"Exactly one minion should survive Brawl, got {len(survivors)}"
        )

    def test_brawl_one_minion_no_effect(self):
        """Brawl with only 1 minion should do nothing."""
        game, p1, p2 = new_hs_game()
        sole_minion = make_obj(game, WISP, p1)

        obj = game.create_object(
            name=BRAWL.name, owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
            characteristics=BRAWL.characteristics, card_def=BRAWL
        )
        events = BRAWL.spell_effect(obj, game.state, [])

        assert events == [], (
            "Brawl with 1 or fewer minions should produce no events"
        )

    def test_brawl_zero_minions_no_effect(self):
        """Brawl with no minions should do nothing."""
        game, p1, p2 = new_hs_game()

        obj = game.create_object(
            name=BRAWL.name, owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
            characteristics=BRAWL.characteristics, card_def=BRAWL
        )
        events = BRAWL.spell_effect(obj, game.state, [])

        assert events == [], "Brawl with no minions should produce no events"

    def test_brawl_destroy_reason_is_brawl(self):
        """Brawl destroy events should have reason='brawl'."""
        game, p1, p2 = new_hs_game()
        make_obj(game, WISP, p1)
        make_obj(game, BLOODFEN_RAPTOR, p2)

        random.seed(42)
        obj = game.create_object(
            name=BRAWL.name, owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
            characteristics=BRAWL.characteristics, card_def=BRAWL
        )
        events = BRAWL.spell_effect(obj, game.state, [])

        destroy_events = [e for e in events if e.type == EventType.OBJECT_DESTROYED]
        assert len(destroy_events) == 1, "With 2 minions, Brawl should destroy exactly 1"
        assert destroy_events[0].payload['reason'] == 'brawl', (
            f"Brawl destroy reason should be 'brawl', got '{destroy_events[0].payload['reason']}'"
        )


# ============================================================
# Test 6: Slam
# ============================================================

class TestSlam:
    def test_slam_deals_2_damage(self):
        """Slam should deal 2 damage to a minion."""
        game, p1, p2 = new_hs_game()
        target = make_obj(game, CHILLWIND_YETI, p2)  # 4/5

        random.seed(42)
        obj = game.create_object(
            name=SLAM.name, owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
            characteristics=SLAM.characteristics, card_def=SLAM
        )
        events = SLAM.spell_effect(obj, game.state, [])

        damage_events = [e for e in events if e.type == EventType.DAMAGE]
        assert len(damage_events) >= 1, "Slam should deal damage"
        assert damage_events[0].payload['amount'] == 2, (
            f"Slam should deal 2 damage, got {damage_events[0].payload['amount']}"
        )

    def test_slam_draws_if_survives(self):
        """Slam should draw a card if the minion survives."""
        game, p1, p2 = new_hs_game()
        target = make_obj(game, CHILLWIND_YETI, p2)  # 4/5, survives 2 damage

        random.seed(42)
        obj = game.create_object(
            name=SLAM.name, owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
            characteristics=SLAM.characteristics, card_def=SLAM
        )
        events = SLAM.spell_effect(obj, game.state, [])

        draw_events = [e for e in events if e.type == EventType.DRAW]
        assert len(draw_events) == 1, (
            f"Slam should draw 1 card when minion survives (5 HP - 2 dmg = 3), got {len(draw_events)}"
        )

    def test_slam_no_draw_if_kills(self):
        """Slam should NOT draw a card if the minion dies (HP <= 2)."""
        game, p1, p2 = new_hs_game()
        target = make_obj(game, BLOODFEN_RAPTOR, p2)  # 3/2, dies to 2 damage

        random.seed(42)
        obj = game.create_object(
            name=SLAM.name, owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
            characteristics=SLAM.characteristics, card_def=SLAM
        )
        events = SLAM.spell_effect(obj, game.state, [])

        draw_events = [e for e in events if e.type == EventType.DRAW]
        assert len(draw_events) == 0, (
            f"Slam should NOT draw when minion dies (2 HP - 2 dmg), got {len(draw_events)} draws"
        )

    def test_slam_no_draw_if_exactly_lethal(self):
        """Slam should NOT draw when exactly lethal (toughness - damage == 2)."""
        game, p1, p2 = new_hs_game()
        # Wisp is 1/1, will die to 2 damage
        target = make_obj(game, WISP, p2)

        random.seed(42)
        obj = game.create_object(
            name=SLAM.name, owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
            characteristics=SLAM.characteristics, card_def=SLAM
        )
        events = SLAM.spell_effect(obj, game.state, [])

        draw_events = [e for e in events if e.type == EventType.DRAW]
        assert len(draw_events) == 0, (
            "Slam should NOT draw when minion would die"
        )


# ============================================================
# Test 7: Cruel Taskmaster
# ============================================================

class TestCruelTaskmaster:
    def test_battlecry_deals_1_damage_and_buffs_2_attack(self):
        """Cruel Taskmaster battlecry: 1 damage + 2 Attack to a minion."""
        game, p1, p2 = new_hs_game()
        target = make_obj(game, CHILLWIND_YETI, p2)  # 4/5

        random.seed(42)
        taskmaster = make_obj(game, CRUEL_TASKMASTER, p1)
        events = CRUEL_TASKMASTER.battlecry(taskmaster, game.state)

        assert len(events) == 2, (
            f"Cruel Taskmaster battlecry should produce 2 events, got {len(events)}"
        )

        # First event: damage
        assert events[0].type == EventType.DAMAGE
        assert events[0].payload['amount'] == 1

        # Second event: PT modification (+2 Attack)
        assert events[1].type == EventType.PT_MODIFICATION
        assert events[1].payload['power_mod'] == 2
        assert events[1].payload['toughness_mod'] == 0

    def test_battlecry_no_targets_no_crash(self):
        """Cruel Taskmaster with no other minions should return empty list."""
        game, p1, p2 = new_hs_game()
        taskmaster = make_obj(game, CRUEL_TASKMASTER, p1)
        events = CRUEL_TASKMASTER.battlecry(taskmaster, game.state)

        assert events == [], (
            "Cruel Taskmaster with no valid targets should produce no events"
        )

    def test_battlecry_does_not_target_self(self):
        """Cruel Taskmaster should not target itself."""
        game, p1, p2 = new_hs_game()
        taskmaster = make_obj(game, CRUEL_TASKMASTER, p1)
        # No other minions on board - only the taskmaster itself
        events = CRUEL_TASKMASTER.battlecry(taskmaster, game.state)

        assert events == [], (
            "Cruel Taskmaster should exclude itself from targets"
        )


# ============================================================
# Test 8: Frothing Berserker
# ============================================================

class TestFrothingBerserker:
    def test_gains_attack_when_any_minion_takes_damage(self):
        """Frothing Berserker gains +1 Attack when any minion takes damage."""
        game, p1, p2 = new_hs_game()
        frothing = make_obj(game, FROTHING_BERSERKER, p1)  # 2/4
        enemy = make_obj(game, CHILLWIND_YETI, p2)

        base_power = get_power(frothing, game.state)
        assert base_power == 2, f"Frothing Berserker should start at 2 Attack, got {base_power}"

        # Deal damage to an enemy minion
        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': enemy.id, 'amount': 1, 'source': 'test'},
            source='test'
        ))

        new_power = get_power(frothing, game.state)
        assert new_power == 3, (
            f"Frothing Berserker should be 3 Attack after 1 minion damaged, got {new_power}"
        )

    def test_gains_attack_from_friendly_minion_damage(self):
        """Frothing Berserker triggers from friendly minion damage too."""
        game, p1, p2 = new_hs_game()
        frothing = make_obj(game, FROTHING_BERSERKER, p1)  # 2/4
        friendly = make_obj(game, CHILLWIND_YETI, p1)

        # Damage friendly minion
        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': friendly.id, 'amount': 1, 'source': 'test'},
            source='test'
        ))

        power = get_power(frothing, game.state)
        assert power == 3, (
            f"Frothing should gain +1 from friendly minion damage, got {power}"
        )

    def test_gains_multiple_attack_from_multiple_damage_events(self):
        """Frothing Berserker stacks +1 for each damage event."""
        game, p1, p2 = new_hs_game()
        frothing = make_obj(game, FROTHING_BERSERKER, p1)  # 2/4
        enemy = make_obj(game, BOULDERFIST_OGRE, p2)  # 6/7

        # Deal damage 3 times
        for _ in range(3):
            game.emit(Event(
                type=EventType.DAMAGE,
                payload={'target': enemy.id, 'amount': 1, 'source': 'test'},
                source='test'
            ))

        power = get_power(frothing, game.state)
        assert power == 5, (
            f"Frothing should be at 5 Attack after 3 damage triggers (2 base + 3), got {power}"
        )


# ============================================================
# Test 9: Grommash Hellscream (Enrage)
# ============================================================

class TestGrommashEnrage:
    def test_grommash_has_charge(self):
        """Grommash Hellscream should have Charge keyword."""
        game, p1, p2 = new_hs_game()
        grom = make_obj(game, GROMMASH_HELLSCREAM, p1)

        has_charge = has_ability(grom, 'charge', game.state)
        assert has_charge, "Grommash should have Charge"

    def test_grommash_base_attack_4(self):
        """Grommash should have 4 Attack when undamaged."""
        game, p1, p2 = new_hs_game()
        grom = make_obj(game, GROMMASH_HELLSCREAM, p1)

        power = get_power(grom, game.state)
        assert power == 4, f"Grommash should have 4 Attack undamaged, got {power}"

    def test_grommash_enrage_gives_plus_6_attack(self):
        """Grommash gains +6 Attack when damaged (Enrage: 4 -> 10)."""
        game, p1, p2 = new_hs_game()
        grom = make_obj(game, GROMMASH_HELLSCREAM, p1)  # 4/9

        # Damage Grommash to activate Enrage
        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': grom.id, 'amount': 1, 'source': 'test'},
            source='test'
        ))

        assert grom.state.damage > 0, "Grommash should be damaged"
        power = get_power(grom, game.state)
        assert power == 10, (
            f"Grommash with Enrage should have 10 Attack (4 base + 6), got {power}"
        )

    def test_grommash_enrage_deactivates_when_healed(self):
        """Grommash loses Enrage bonus when healed to full."""
        game, p1, p2 = new_hs_game()
        grom = make_obj(game, GROMMASH_HELLSCREAM, p1)

        # Damage then heal
        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': grom.id, 'amount': 2, 'source': 'test'},
            source='test'
        ))
        enraged_power = get_power(grom, game.state)
        assert enraged_power == 10, "Grommash should be enraged at 10 Attack"

        # Heal back to full by clearing damage
        grom.state.damage = 0

        healed_power = get_power(grom, game.state)
        assert healed_power == 4, (
            f"Grommash should return to 4 Attack when healed, got {healed_power}"
        )


# ============================================================
# Test 10: Armorsmith
# ============================================================

class TestArmorsmith:
    def test_gains_armor_when_friendly_minion_damaged(self):
        """Armorsmith: emits ARMOR_GAIN when a friendly minion takes damage."""
        game, p1, p2 = new_hs_game()
        armorsmith = make_obj(game, ARMORSMITH, p1)  # 1/4
        friendly = make_obj(game, CHILLWIND_YETI, p1)  # 4/5

        processed = game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': friendly.id, 'amount': 1, 'source': 'test'},
            source='test'
        ))

        armor_events = [e for e in processed if e.type == EventType.ARMOR_GAIN]
        assert len(armor_events) >= 1, (
            f"Armorsmith should emit ARMOR_GAIN when friendly minion damaged, "
            f"got events: {[e.type for e in processed]}"
        )
        assert armor_events[0].payload['player'] == p1.id
        assert armor_events[0].payload['amount'] == 1

    def test_gains_armor_when_armorsmith_itself_damaged(self):
        """Armorsmith triggers when it takes damage too (it is a friendly minion)."""
        game, p1, p2 = new_hs_game()
        armorsmith = make_obj(game, ARMORSMITH, p1)  # 1/4

        processed = game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': armorsmith.id, 'amount': 1, 'source': 'test'},
            source='test'
        ))

        armor_events = [e for e in processed if e.type == EventType.ARMOR_GAIN]
        assert len(armor_events) >= 1, (
            f"Armorsmith should emit ARMOR_GAIN when itself is damaged, "
            f"got events: {[e.type for e in processed]}"
        )
        assert armor_events[0].payload['amount'] == 1

    def test_does_not_gain_armor_from_enemy_minion_damage(self):
        """Armorsmith should NOT trigger from enemy minion damage."""
        game, p1, p2 = new_hs_game()
        armorsmith = make_obj(game, ARMORSMITH, p1)
        enemy = make_obj(game, CHILLWIND_YETI, p2)

        processed = game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': enemy.id, 'amount': 1, 'source': 'test'},
            source='test'
        ))

        armor_events = [e for e in processed
                        if e.type == EventType.ARMOR_GAIN and e.source == armorsmith.id]
        assert len(armor_events) == 0, (
            "Armorsmith should not emit ARMOR_GAIN from enemy minion damage"
        )

    def test_multiple_friendly_damage_stacks(self):
        """Armorsmith should emit ARMOR_GAIN for each separate damage event."""
        game, p1, p2 = new_hs_game()
        armorsmith = make_obj(game, ARMORSMITH, p1)
        f1 = make_obj(game, CHILLWIND_YETI, p1)
        f2 = make_obj(game, BOULDERFIST_OGRE, p1)

        all_processed = []

        # Damage two friendly minions
        all_processed.extend(game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': f1.id, 'amount': 1, 'source': 'test'},
            source='test'
        )))
        all_processed.extend(game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': f2.id, 'amount': 1, 'source': 'test'},
            source='test'
        )))

        armor_events = [e for e in all_processed if e.type == EventType.ARMOR_GAIN]
        assert len(armor_events) >= 2, (
            f"Armorsmith should emit 2 ARMOR_GAIN events from 2 friendly damage events, "
            f"got {len(armor_events)}"
        )


# ============================================================
# Test 11: Ragnaros the Firelord
# ============================================================

class TestRagnarosEndOfTurn:
    def test_ragnaros_deals_8_at_end_of_turn(self):
        """Ragnaros should deal 8 damage to a random enemy at end of turn."""
        game, p1, p2 = new_hs_game()
        rag = make_obj(game, RAGNAROS_THE_FIRELORD, p1)  # 8/8

        initial_life = p2.life

        random.seed(42)
        game.emit(Event(
            type=EventType.TURN_END,
            payload={'player': p1.id},
            source='system'
        ))

        # Ragnaros should have dealt 8 damage to something on the enemy side
        # Could hit hero or minions; with no enemy minions, hits hero
        # With no enemy minions, Ragnaros must hit enemy hero for 8
        assert p2.life == initial_life - 8, (
            f"Ragnaros should hit enemy hero for 8 with no minions, "
            f"expected {initial_life - 8}, got {p2.life}"
        )

    def test_ragnaros_cant_attack(self):
        """Ragnaros should have the can't attack ability."""
        game, p1, p2 = new_hs_game()
        rag = make_obj(game, RAGNAROS_THE_FIRELORD, p1)

        has_cant = has_ability(rag, 'cant_attack', game.state)
        assert has_cant, "Ragnaros should have 'cant_attack' ability"

    def test_ragnaros_does_not_trigger_on_opponent_turn(self):
        """Ragnaros should NOT trigger on the opponent's turn end."""
        game, p1, p2 = new_hs_game()
        rag = make_obj(game, RAGNAROS_THE_FIRELORD, p1)  # controlled by p1

        initial_life = p2.life

        # End the OPPONENT's turn (p2), not our turn
        game.emit(Event(
            type=EventType.TURN_END,
            payload={'player': p2.id},
            source='system'
        ))

        # p2's life should be unchanged since Ragnaros belongs to p1
        # and only triggers on p1's turn end
        assert p2.life == initial_life, (
            f"Ragnaros should not trigger on opponent's turn end, "
            f"p2 life should be {initial_life}, got {p2.life}"
        )


# ============================================================
# Test 12: Alexstrasza
# ============================================================

class TestAlexstrasza:
    def test_alexstrasza_sets_enemy_health_to_15(self):
        """Alexstrasza battlecry: sets enemy hero health to 15 (damage)."""
        game, p1, p2 = new_hs_game()
        p2.life = 30  # Enemy at 30 HP

        alex = make_obj(game, ALEXSTRASZA, p1)
        events = ALEXSTRASZA.battlecry(alex, game.state)

        assert len(events) >= 1, "Alexstrasza should produce events when enemy > 15 HP"
        # Should deal 15 damage (30 - 15 = 15)
        assert events[0].type == EventType.DAMAGE
        assert events[0].payload['amount'] == 15, (
            f"Alexstrasza should deal 15 damage to 30 HP hero, got {events[0].payload['amount']}"
        )

    def test_alexstrasza_heals_self_to_15(self):
        """Alexstrasza heals own hero to 15 when enemy is already <= 15."""
        game, p1, p2 = new_hs_game()
        p1.life = 5   # Own hero low
        p2.life = 10  # Enemy already below 15

        alex = make_obj(game, ALEXSTRASZA, p1)
        events = ALEXSTRASZA.battlecry(alex, game.state)

        assert len(events) >= 1, "Alexstrasza should produce heal event when self < 15"
        assert events[0].type == EventType.LIFE_CHANGE
        assert events[0].payload['amount'] == 10, (
            f"Alexstrasza should heal 10 (15 - 5), got {events[0].payload['amount']}"
        )

    def test_alexstrasza_no_effect_at_15(self):
        """Alexstrasza does nothing if all heroes are at 15."""
        game, p1, p2 = new_hs_game()
        p1.life = 15
        p2.life = 15

        alex = make_obj(game, ALEXSTRASZA, p1)
        events = ALEXSTRASZA.battlecry(alex, game.state)

        assert events == [], (
            "Alexstrasza should produce no events when both heroes at 15"
        )

    def test_alexstrasza_prefers_enemy_over_self_heal(self):
        """Alexstrasza should target enemy hero > 15 before healing self."""
        game, p1, p2 = new_hs_game()
        p1.life = 5   # Self needs healing
        p2.life = 25  # Enemy above 15

        alex = make_obj(game, ALEXSTRASZA, p1)
        events = ALEXSTRASZA.battlecry(alex, game.state)

        assert len(events) >= 1
        # Should damage enemy hero (priority over self heal)
        assert events[0].type == EventType.DAMAGE, (
            "Alexstrasza should prioritize damaging enemy > 15 over healing self"
        )
        assert events[0].payload['amount'] == 10, (
            f"Should deal 10 damage to 25 HP hero, got {events[0].payload['amount']}"
        )


# ============================================================
# Test 13: Leeroy Jenkins
# ============================================================

class TestLeeroyJenkins:
    def test_leeroy_has_charge(self):
        """Leeroy Jenkins should have Charge."""
        game, p1, p2 = new_hs_game()
        leeroy = make_obj(game, LEEROY_JENKINS, p1)

        has_charge = has_ability(leeroy, 'charge', game.state)
        assert has_charge, "Leeroy Jenkins should have Charge"

    def test_leeroy_summons_2_whelps_for_opponent(self):
        """Leeroy's battlecry summons 2x 1/1 Whelps for the opponent."""
        game, p1, p2 = new_hs_game()
        leeroy = make_obj(game, LEEROY_JENKINS, p1)
        events = LEEROY_JENKINS.battlecry(leeroy, game.state)

        assert len(events) == 2, (
            f"Leeroy battlecry should produce 2 CREATE_TOKEN events, got {len(events)}"
        )

        for i, event in enumerate(events):
            assert event.type == EventType.CREATE_TOKEN, (
                f"Event {i} should be CREATE_TOKEN, got {event.type}"
            )
            assert event.payload['controller'] == p2.id, (
                f"Whelps should be created for opponent (p2), got controller {event.payload['controller']}"
            )
            token = event.payload['token']
            assert token['name'] == 'Whelp', f"Token should be named 'Whelp', got '{token['name']}'"
            assert token['power'] == 1, f"Whelp should have 1 power, got {token['power']}"
            assert token['toughness'] == 1, f"Whelp should have 1 toughness, got {token['toughness']}"

    def test_leeroy_stats(self):
        """Leeroy Jenkins should be a 6/2."""
        game, p1, p2 = new_hs_game()
        leeroy = make_obj(game, LEEROY_JENKINS, p1)

        power = get_power(leeroy, game.state)
        toughness = get_toughness(leeroy, game.state)
        assert power == 6, f"Leeroy should have 6 Attack, got {power}"
        assert toughness == 2, f"Leeroy should have 2 Health, got {toughness}"


# ============================================================
# Test 14: Deathwing
# ============================================================

class TestDeathwing:
    def test_deathwing_destroys_all_other_minions(self):
        """Deathwing battlecry should destroy all other minions."""
        game, p1, p2 = new_hs_game()
        f1 = make_obj(game, CHILLWIND_YETI, p1)
        f2 = make_obj(game, WISP, p1)
        e1 = make_obj(game, BOULDERFIST_OGRE, p2)
        e2 = make_obj(game, BLOODFEN_RAPTOR, p2)

        deathwing = make_obj(game, DEATHWING, p1)
        events = DEATHWING.battlecry(deathwing, game.state)

        destroy_events = [e for e in events if e.type == EventType.OBJECT_DESTROYED]
        destroyed_ids = {e.payload['object_id'] for e in destroy_events}

        # Should destroy all 4 other minions
        assert f1.id in destroyed_ids, "Deathwing should destroy friendly minion f1"
        assert f2.id in destroyed_ids, "Deathwing should destroy friendly minion f2"
        assert e1.id in destroyed_ids, "Deathwing should destroy enemy minion e1"
        assert e2.id in destroyed_ids, "Deathwing should destroy enemy minion e2"

        # Should NOT destroy itself
        assert deathwing.id not in destroyed_ids, "Deathwing should not destroy itself"

    def test_deathwing_discards_hand(self):
        """Deathwing battlecry should discard all cards in hand."""
        game, p1, p2 = new_hs_game()

        # Put some cards in p1's hand
        h1 = game.create_object(
            name=WISP.name, owner_id=p1.id, zone=ZoneType.HAND,
            characteristics=WISP.characteristics, card_def=WISP
        )
        h2 = game.create_object(
            name=CHILLWIND_YETI.name, owner_id=p1.id, zone=ZoneType.HAND,
            characteristics=CHILLWIND_YETI.characteristics, card_def=CHILLWIND_YETI
        )

        deathwing = make_obj(game, DEATHWING, p1)
        events = DEATHWING.battlecry(deathwing, game.state)

        discard_events = [e for e in events if e.type == EventType.DISCARD]
        discarded_ids = {e.payload['object_id'] for e in discard_events}

        assert h1.id in discarded_ids, "Deathwing should discard card h1 from hand"
        assert h2.id in discarded_ids, "Deathwing should discard card h2 from hand"

    def test_deathwing_empty_board_no_destroy(self):
        """Deathwing with no other minions should not produce destroy events."""
        game, p1, p2 = new_hs_game()
        deathwing = make_obj(game, DEATHWING, p1)
        events = DEATHWING.battlecry(deathwing, game.state)

        destroy_events = [e for e in events if e.type == EventType.OBJECT_DESTROYED]
        assert len(destroy_events) == 0, (
            "Deathwing on empty board should produce no OBJECT_DESTROYED events"
        )

    def test_deathwing_empty_hand_no_discard(self):
        """Deathwing with empty hand should not produce discard events."""
        game, p1, p2 = new_hs_game()
        deathwing = make_obj(game, DEATHWING, p1)
        events = DEATHWING.battlecry(deathwing, game.state)

        discard_events = [e for e in events if e.type == EventType.DISCARD]
        assert len(discard_events) == 0, (
            "Deathwing with empty hand should produce no DISCARD events"
        )

    def test_deathwing_stats(self):
        """Deathwing should be a 12/12."""
        game, p1, p2 = new_hs_game()
        dw = make_obj(game, DEATHWING, p1)

        power = get_power(dw, game.state)
        toughness = get_toughness(dw, game.state)
        assert power == 12, f"Deathwing should have 12 Attack, got {power}"
        assert toughness == 12, f"Deathwing should have 12 Health, got {toughness}"

    def test_deathwing_destroy_reason_is_deathwing(self):
        """Deathwing destroy events should have reason='deathwing'."""
        game, p1, p2 = new_hs_game()
        enemy = make_obj(game, WISP, p2)
        deathwing = make_obj(game, DEATHWING, p1)
        events = DEATHWING.battlecry(deathwing, game.state)

        destroy_events = [e for e in events if e.type == EventType.OBJECT_DESTROYED]
        assert len(destroy_events) >= 1
        assert destroy_events[0].payload['reason'] == 'deathwing', (
            f"Deathwing destroy reason should be 'deathwing', got '{destroy_events[0].payload['reason']}'"
        )


# ============================================================
# Run tests
# ============================================================

if __name__ == '__main__':
    import pytest
    pytest.main([__file__, '-v'])
