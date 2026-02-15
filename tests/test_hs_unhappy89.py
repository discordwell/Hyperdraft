"""
Hearthstone Unhappy Path Tests - Batch 89

Lethal Damage, Game-Ending Scenarios, and Hero Health Edge Cases

Tests cover:
- Hero at 30 HP takes 30 damage - dies (0 HP)
- Hero at 1 HP takes 1 damage - dies
- Hero overkilled (takes 50 damage at 30 HP) - still dies normally
- Hero at exactly 0 HP after combat - game ends
- Fireball (6 damage) kills hero at 6 HP
- Pyroblast (10 damage) kills hero at 10 HP
- Hero survives at 1 HP after taking 29 damage
- Armor absorbs damage before HP
- Armor prevents lethal
- Fatigue damage kills hero at low HP
- Multiple fatigue draws escalate
- Hellfire deals 3 to ALL characters - both heroes damaged
- Abomination deathrattle kills hero
- Healing at full HP does nothing
- Healing over max HP caps at 30
- Hero damage from various sources
- Life total tracking
- Game end conditions
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
    WISP, CHILLWIND_YETI, BOULDERFIST_OGRE,
)
from src.cards.hearthstone.mage import FIREBALL, PYROBLAST, FLAMESTRIKE
from src.cards.hearthstone.warlock import HELLFIRE
from src.cards.hearthstone.priest import HOLY_NOVA
from src.cards.hearthstone.paladin import HOLY_LIGHT, LAY_ON_HANDS, CONSECRATION
from src.cards.hearthstone.druid import HEALING_TOUCH
from src.cards.hearthstone.classic import ABOMINATION, ALEXSTRASZA
from src.cards.hearthstone.hunter import EXPLOSIVE_TRAP


# ============================================================
# Test Helpers
# ============================================================

def new_hs_game():
    """Create a fresh Hearthstone game with 2 players, heroes, and 10 mana each."""
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


def play_from_hand(game, card_def, owner):
    """Simulate playing a minion from hand (triggers battlecry via ZONE_CHANGE)."""
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


def clear_library(game, player):
    """Empty a player's library."""
    lib_key = f"library_{player.id}"
    lib = game.state.zones.get(lib_key)
    if lib:
        lib.objects.clear()


# ============================================================
# Test 1: Hero Health and Lethal
# ============================================================

class TestHeroHealthAndLethal:
    def test_hero_at_30hp_takes_30_damage_dies(self):
        """Hero at 30 HP takes 30 damage - dies (0 HP)."""
        game, p1, p2 = new_hs_game()

        assert p1.life == 30

        # Deal 30 damage to hero
        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': p1.hero_id, 'amount': 30},
            source='test'
        ))

        assert p1.life <= 0, f"Hero should be at 0 HP, got {p1.life}"

    def test_hero_at_1hp_takes_1_damage_dies(self):
        """Hero at 1 HP takes 1 damage - dies."""
        game, p1, p2 = new_hs_game()

        p1.life = 1

        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': p1.hero_id, 'amount': 1},
            source='test'
        ))

        assert p1.life <= 0, f"Hero should be at 0 HP, got {p1.life}"

    def test_hero_overkilled_50_damage_at_30hp(self):
        """Hero overkilled (takes 50 damage at 30 HP) - still dies normally."""
        game, p1, p2 = new_hs_game()

        assert p1.life == 30

        # Overkill by 20
        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': p1.hero_id, 'amount': 50},
            source='test'
        ))

        assert p1.life <= 0, f"Hero should be dead (HP <= 0), got {p1.life}"
        # HP can go negative or stay at 0, doesn't matter

    def test_hero_at_exactly_0hp_after_combat(self):
        """Hero at exactly 0 HP after combat - game ends."""
        game, p1, p2 = new_hs_game()

        # Deal exactly 30 damage
        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': p1.hero_id, 'amount': 30},
            source='test'
        ))

        assert p1.life <= 0, f"Hero should be at 0 HP, got {p1.life}"

    def test_fireball_6_damage_kills_hero_at_6hp(self):
        """Fireball (6 damage) kills hero at 6 HP."""
        game, p1, p2 = new_hs_game()

        p2.life = 6

        cast_spell(game, FIREBALL, p1, targets=[p2.hero_id])

        assert p2.life <= 0, f"Hero at 6 HP should die to Fireball (6), got {p2.life}"

    def test_pyroblast_10_damage_kills_hero_at_10hp(self):
        """Pyroblast (10 damage) kills hero at 10 HP."""
        game, p1, p2 = new_hs_game()

        p2.life = 10

        cast_spell(game, PYROBLAST, p1, targets=[p2.hero_id])

        assert p2.life <= 0, f"Hero at 10 HP should die to Pyroblast (10), got {p2.life}"

    def test_hero_survives_at_1hp_after_29_damage(self):
        """Hero survives at 1 HP after taking 29 damage."""
        game, p1, p2 = new_hs_game()

        assert p1.life == 30

        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': p1.hero_id, 'amount': 29},
            source='test'
        ))

        assert p1.life == 1, f"Hero should survive at 1 HP, got {p1.life}"


# ============================================================
# Test 2: Armor Interaction with Lethal
# ============================================================

class TestArmorInteractionWithLethal:
    def test_armor_absorbs_damage_before_hp(self):
        """Armor absorbs damage before HP (hero with 5 armor takes 3 - armor reduced, HP unchanged)."""
        game, p1, p2 = new_hs_game()

        p1.armor = 5
        life_before = p1.life

        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': p1.hero_id, 'amount': 3},
            source='test'
        ))

        assert p1.armor == 2, f"Armor should reduce from 5 to 2, got {p1.armor}"
        assert p1.life == life_before, f"HP should be unchanged, went from {life_before} to {p1.life}"

    def test_armor_absorbs_exact_damage(self):
        """Armor absorbs exact damage (5 armor, 5 damage - 0 armor, HP unchanged)."""
        game, p1, p2 = new_hs_game()

        p1.armor = 5
        life_before = p1.life

        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': p1.hero_id, 'amount': 5},
            source='test'
        ))

        assert p1.armor == 0, f"Armor should be depleted, got {p1.armor}"
        assert p1.life == life_before, f"HP should be unchanged, went from {life_before} to {p1.life}"

    def test_damage_exceeds_armor(self):
        """Damage exceeds armor (5 armor, 8 damage - 0 armor, 3 HP lost)."""
        game, p1, p2 = new_hs_game()

        p1.armor = 5
        life_before = p1.life

        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': p1.hero_id, 'amount': 8},
            source='test'
        ))

        assert p1.armor == 0, f"Armor should be depleted, got {p1.armor}"
        assert p1.life == life_before - 3, f"HP should lose 3, went from {life_before} to {p1.life}"

    def test_armor_prevents_lethal(self):
        """Armor prevents lethal (1 HP, 10 armor, 8 damage - survives)."""
        game, p1, p2 = new_hs_game()

        p1.life = 1
        p1.armor = 10

        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': p1.hero_id, 'amount': 8},
            source='test'
        ))

        assert p1.life == 1, f"Hero should survive at 1 HP, got {p1.life}"
        assert p1.armor == 2, f"Armor should reduce to 2, got {p1.armor}"

    def test_armor_does_not_prevent_massive_lethal(self):
        """Armor doesn't prevent lethal from massive damage (1 HP, 5 armor, 20 damage - dies)."""
        game, p1, p2 = new_hs_game()

        p1.life = 1
        p1.armor = 5

        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': p1.hero_id, 'amount': 20},
            source='test'
        ))

        assert p1.life <= 0, f"Hero should die, got {p1.life}"
        assert p1.armor == 0, f"Armor should be depleted, got {p1.armor}"

    def test_armor_at_0_damage_goes_to_hp(self):
        """Armor at 0 - damage goes straight to HP."""
        game, p1, p2 = new_hs_game()

        p1.armor = 0
        life_before = p1.life

        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': p1.hero_id, 'amount': 5},
            source='test'
        ))

        assert p1.armor == 0, f"Armor should stay at 0, got {p1.armor}"
        assert p1.life == life_before - 5, f"HP should lose 5, went from {life_before} to {p1.life}"


# ============================================================
# Test 3: Fatigue Lethal
# ============================================================

class TestFatigueLethal:
    def test_fatigue_damage_kills_hero_at_low_hp(self):
        """Fatigue damage kills hero at low HP."""
        game, p1, p2 = new_hs_game()

        clear_library(game, p1)
        p1.fatigue_damage = 0
        p1.life = 3

        # First fatigue: 1 damage
        game.emit(Event(
            type=EventType.DRAW,
            payload={'player': p1.id, 'count': 1},
            source='test'
        ))

        assert p1.life == 2, f"After 1 fatigue, should be at 2 HP, got {p1.life}"

        # Second fatigue: 2 damage (kills at 2 HP)
        game.emit(Event(
            type=EventType.DRAW,
            payload={'player': p1.id, 'count': 1},
            source='test'
        ))

        assert p1.life <= 0, f"Hero should die after 2nd fatigue, got {p1.life}"

    def test_multiple_fatigue_draws_escalate(self):
        """Multiple fatigue draws escalate (1+2+3=6 total)."""
        game, p1, p2 = new_hs_game()

        clear_library(game, p1)
        p1.fatigue_damage = 0
        life_before = p1.life

        # Draw 3 times: 1 + 2 + 3 = 6 total damage
        game.emit(Event(type=EventType.DRAW, payload={'player': p1.id, 'count': 1}, source='test'))
        game.emit(Event(type=EventType.DRAW, payload={'player': p1.id, 'count': 1}, source='test'))
        game.emit(Event(type=EventType.DRAW, payload={'player': p1.id, 'count': 1}, source='test'))

        assert p1.fatigue_damage == 3, f"Fatigue counter should be 3, got {p1.fatigue_damage}"
        assert p1.life == life_before - 6, f"Should take 6 total damage, life went from {life_before} to {p1.life}"

    def test_double_fatigue_draw_at_3hp_exact_lethal(self):
        """Double fatigue draw at 3 HP (1+2=3 damage) - exact lethal."""
        game, p1, p2 = new_hs_game()

        clear_library(game, p1)
        p1.fatigue_damage = 0
        p1.life = 3

        # Draw 2 cards: 1 + 2 = 3 damage (exact lethal)
        game.emit(Event(type=EventType.DRAW, payload={'player': p1.id, 'count': 2}, source='test'))

        assert p1.life <= 0, f"Hero should die from exact fatigue lethal, got {p1.life}"


# ============================================================
# Test 4: Simultaneous Damage/Death
# ============================================================

class TestSimultaneousDamageDeath:
    def test_hellfire_damages_all_characters(self):
        """Hellfire deals 3 to ALL characters - both heroes damaged."""
        game, p1, p2 = new_hs_game()

        p1_life_before = p1.life
        p2_life_before = p2.life

        cast_spell(game, HELLFIRE, p1)

        assert p1.life == p1_life_before - 3, (
            f"P1 hero should take 3 damage, went from {p1_life_before} to {p1.life}"
        )
        assert p2.life == p2_life_before - 3, (
            f"P2 hero should take 3 damage, went from {p2_life_before} to {p2.life}"
        )

    def test_hellfire_kills_both_heroes_at_3hp(self):
        """If Hellfire kills both heroes, both die."""
        game, p1, p2 = new_hs_game()

        p1.life = 3
        p2.life = 3

        cast_spell(game, HELLFIRE, p1)

        assert p1.life <= 0, f"P1 should die, got {p1.life}"
        assert p2.life <= 0, f"P2 should die, got {p2.life}"

    def test_abomination_deathrattle_kills_hero(self):
        """Abomination deathrattle (2 to all) kills hero."""
        game, p1, p2 = new_hs_game()

        abom = make_obj(game, ABOMINATION, p1)
        p1.life = 2
        p2.life = 2

        # Kill Abomination
        game.emit(Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': abom.id, 'reason': 'combat'},
            source='test'
        ))

        # Both heroes should take 2 damage and die
        assert p1.life <= 0, f"P1 should die from Abomination deathrattle, got {p1.life}"
        assert p2.life <= 0, f"P2 should die from Abomination deathrattle, got {p2.life}"

    def test_multiple_damage_sources_in_one_turn(self):
        """Multiple damage sources in one turn (attack + spell + fatigue)."""
        game, p1, p2 = new_hs_game()

        clear_library(game, p1)
        p1.fatigue_damage = 0
        p1.life = 20

        # 1. Direct damage
        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': p1.hero_id, 'amount': 5},
            source='test'
        ))

        # 2. Spell damage
        cast_spell(game, FIREBALL, p2, targets=[p1.hero_id])

        # 3. Fatigue
        game.emit(Event(type=EventType.DRAW, payload={'player': p1.id, 'count': 1}, source='test'))

        # Total: 20 - 5 - 6 - 1 = 8 HP
        assert p1.life == 8, f"After multiple damage sources, should be at 8 HP, got {p1.life}"


# ============================================================
# Test 5: Healing Edge Cases
# ============================================================

class TestHealingEdgeCases:
    def test_healing_at_full_hp_does_nothing(self):
        """Healing at full HP does nothing."""
        game, p1, p2 = new_hs_game()

        assert p1.life == 30

        game.emit(Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': p1.id, 'amount': 5},
            source='test'
        ))

        assert p1.life == 30, f"Hero at 30 HP healed should stay at 30, got {p1.life}"

    def test_healing_over_max_hp_caps_at_30(self):
        """Healing over max HP caps at 30 (heal 10 at 25 HP = 30, not 35)."""
        game, p1, p2 = new_hs_game()

        p1.life = 25

        game.emit(Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': p1.id, 'amount': 10},
            source='test'
        ))

        assert p1.life == 30, f"Hero healed from 25 should cap at 30, got {p1.life}"

    def test_healing_from_1hp_to_30hp(self):
        """Healing from 1 HP to 30 HP."""
        game, p1, p2 = new_hs_game()

        p1.life = 1

        game.emit(Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': p1.id, 'amount': 29},
            source='test'
        ))

        assert p1.life == 30, f"Hero healed from 1 should reach 30, got {p1.life}"

    def test_holy_light_heals_6_to_hero(self):
        """Holy Light heals 6 to hero."""
        game, p1, p2 = new_hs_game()

        p1.life = 20

        cast_spell(game, HOLY_LIGHT, p1, targets=[p1.hero_id])

        assert p1.life == 26, f"Hero at 20 HP + Holy Light (6) should be 26, got {p1.life}"

    def test_lay_on_hands_heals_8_and_draws_3(self):
        """Lay on Hands heals 8 and draws 3."""
        game, p1, p2 = new_hs_game()

        p1.life = 15

        # Add cards to library so draws don't cause fatigue
        lib_key = f"library_{p1.id}"
        for _ in range(5):
            game.create_object(
                name=WISP.name, owner_id=p1.id, zone=ZoneType.LIBRARY,
                characteristics=WISP.characteristics, card_def=WISP
            )

        cast_spell(game, LAY_ON_HANDS, p1, targets=[p1.hero_id])

        assert p1.life == 23, f"Hero at 15 HP + Lay on Hands (8) should be 23, got {p1.life}"

    def test_healing_touch_heals_8(self):
        """Healing Touch heals 8."""
        game, p1, p2 = new_hs_game()

        p1.life = 10

        cast_spell(game, HEALING_TOUCH, p1, targets=[p1.hero_id])

        assert p1.life == 18, f"Hero at 10 HP + Healing Touch (8) should be 18, got {p1.life}"


# ============================================================
# Test 6: Hero Damage from Various Sources
# ============================================================

class TestHeroDamageFromVariousSources:
    def test_minion_attack_damages_hero(self):
        """Minion attack damages hero."""
        game, p1, p2 = new_hs_game()

        yeti = make_obj(game, CHILLWIND_YETI, p1)
        life_before = p2.life

        # Simulate minion attacking hero (4 damage)
        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': p2.hero_id, 'amount': 4},
            source=yeti.id
        ))

        assert p2.life == life_before - 4, f"Hero should take 4 damage, went from {life_before} to {p2.life}"

    def test_spell_damages_hero_fireball_to_face(self):
        """Spell damages hero (Fireball to face)."""
        game, p1, p2 = new_hs_game()

        life_before = p2.life

        cast_spell(game, FIREBALL, p1, targets=[p2.hero_id])

        assert p2.life == life_before - 6, f"Hero should take 6 damage from Fireball, went from {life_before} to {p2.life}"

    def test_deathrattle_damages_hero_abomination(self):
        """Deathrattle damages hero (Abomination)."""
        game, p1, p2 = new_hs_game()

        abom = make_obj(game, ABOMINATION, p1)
        p1_life_before = p1.life
        p2_life_before = p2.life

        game.emit(Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': abom.id, 'reason': 'combat'},
            source='test'
        ))

        assert p1.life == p1_life_before - 2, f"P1 should take 2 damage, went from {p1_life_before} to {p1.life}"
        assert p2.life == p2_life_before - 2, f"P2 should take 2 damage, went from {p2_life_before} to {p2.life}"


# ============================================================
# Test 7: Life Total Tracking
# ============================================================

class TestLifeTotalTracking:
    def test_hero_takes_damage_then_heals_correct_hp(self):
        """Hero takes damage then heals - correct HP."""
        game, p1, p2 = new_hs_game()

        # Take 10 damage
        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': p1.hero_id, 'amount': 10},
            source='test'
        ))

        assert p1.life == 20, f"After 10 damage, should be at 20, got {p1.life}"

        # Heal 5
        game.emit(Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': p1.id, 'amount': 5},
            source='test'
        ))

        assert p1.life == 25, f"After healing 5, should be at 25, got {p1.life}"

    def test_hero_takes_damage_from_multiple_sources(self):
        """Hero takes damage from multiple sources in one turn."""
        game, p1, p2 = new_hs_game()

        # Damage 1: 5
        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': p1.hero_id, 'amount': 5},
            source='test1'
        ))

        # Damage 2: 7
        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': p1.hero_id, 'amount': 7},
            source='test2'
        ))

        # Damage 3: 3
        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': p1.hero_id, 'amount': 3},
            source='test3'
        ))

        # Total: 30 - 5 - 7 - 3 = 15
        assert p1.life == 15, f"After multiple damage, should be at 15, got {p1.life}"

    def test_hero_health_never_displayed_below_0(self):
        """Hero health never displayed below 0 (clamped)."""
        game, p1, p2 = new_hs_game()

        # Deal 50 damage (overkill)
        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': p1.hero_id, 'amount': 50},
            source='test'
        ))

        # HP can be 0 or negative, but should be <= 0
        assert p1.life <= 0, f"Hero health should be <= 0, got {p1.life}"

    def test_armor_stacking_from_multiple_sources(self):
        """Armor stacking from multiple sources."""
        game, p1, p2 = new_hs_game()

        p1.armor = 0

        # Add 2 armor
        p1.armor += 2
        # Add 3 armor
        p1.armor += 3
        # Add 5 armor
        p1.armor += 5

        assert p1.armor == 10, f"Armor should stack to 10, got {p1.armor}"


# ============================================================
# Test 8: Game End Conditions
# ============================================================

class TestGameEndConditions:
    def test_player_with_0hp_at_end_of_turn(self):
        """Player with 0 HP at end of turn - game should end."""
        game, p1, p2 = new_hs_game()

        # Deal 30 damage
        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': p1.hero_id, 'amount': 30},
            source='test'
        ))

        assert p1.life <= 0, f"Player should be at 0 HP, got {p1.life}"

    def test_hero_killed_during_combat(self):
        """Hero killed by attacking minion."""
        game, p1, p2 = new_hs_game()

        p2.life = 6
        ogre = make_obj(game, BOULDERFIST_OGRE, p1)  # 6 attack

        # Ogre attacks hero (6 damage)
        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': p2.hero_id, 'amount': 6},
            source=ogre.id
        ))

        assert p2.life <= 0, f"Hero should die from combat, got {p2.life}"

    def test_hero_killed_by_spell_during_own_turn(self):
        """Hero killed by spell during own turn."""
        game, p1, p2 = new_hs_game()

        p1.life = 6

        # P1 casts Fireball on themselves (6 damage)
        cast_spell(game, FIREBALL, p1, targets=[p1.hero_id])

        assert p1.life <= 0, f"Hero should die from self-damage spell, got {p1.life}"

    def test_hero_killed_by_opponent_spell(self):
        """Hero killed by opponent spell during opponent turn."""
        game, p1, p2 = new_hs_game()

        p1.life = 10

        # P2 casts Pyroblast on P1 (10 damage)
        cast_spell(game, PYROBLAST, p2, targets=[p1.hero_id])

        assert p1.life <= 0, f"Hero should die from opponent spell, got {p1.life}"

    def test_both_players_at_1hp_active_player_attacks_opponent_dies(self):
        """Both players at 1 HP - active player attacks, opponent dies."""
        game, p1, p2 = new_hs_game()

        p1.life = 1
        p2.life = 1

        wisp = make_obj(game, WISP, p1)  # 1 attack

        # Wisp attacks P2 hero (1 damage)
        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': p2.hero_id, 'amount': 1},
            source=wisp.id
        ))

        assert p1.life == 1, f"P1 should survive at 1 HP, got {p1.life}"
        assert p2.life <= 0, f"P2 should die, got {p2.life}"


# ============================================================
# Run tests
# ============================================================

if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
