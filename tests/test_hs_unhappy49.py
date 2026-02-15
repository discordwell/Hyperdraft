"""
Hearthstone Unhappy Path Tests - Batch 49

Druid Choose One mechanics: Wrath branch selection, Nourish ramp/draw threshold,
Starfall AOE/single toggle, Power of the Wild buff/summon, Keeper of the Grove
silence/damage, Druid of the Claw form selection, Ancient of Lore/War choices.
Also covers Innervate mana overflow, Wild Growth at 10, Savage Roar hero attack
cleanup, Force of Nature tokens, and spell-damage-boosted Druid spells.
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
    WISP, CHILLWIND_YETI, KOBOLD_GEOMANCER, BLOODFEN_RAPTOR,
)
from src.cards.hearthstone.classic import (
    KNIFE_JUGGLER, FROSTBOLT, FIREBALL, LOOT_HOARDER,
    WILD_PYROMANCER, MALYGOS,
)
from src.cards.hearthstone.druid import (
    WRATH, NOURISH, STARFALL, POWER_OF_THE_WILD, KEEPER_OF_THE_GROVE,
    DRUID_OF_THE_CLAW, ANCIENT_OF_LORE, ANCIENT_OF_WAR,
    INNERVATE, WILD_GROWTH, SAVAGE_ROAR, FORCE_OF_NATURE,
    SWIPE, MOONFIRE, CLAW, BITE, STARFIRE, NATURALIZE,
)


# ============================================================
# Test Helpers
# ============================================================

def new_hs_game():
    game = Game(mode='hearthstone')
    p1 = game.add_player("Player1", life=30)
    p2 = game.add_player("Player2", life=30)
    game.setup_hearthstone_player(p1, HEROES["Druid"], HERO_POWERS["Druid"])
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


def play_minion(game, card_def, owner):
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


# ============================================================
# Wrath Choose One
# ============================================================

class TestWrathChooseOne:
    def test_wrath_picks_3_damage_on_low_health_target(self):
        """Wrath AI picks 3-damage mode when enemy minion has <= 3 HP."""
        game, p1, p2 = new_hs_game()
        # Raptor: 3/2, toughness 2 <= 3 → AI should pick 3-damage mode
        raptor = make_obj(game, BLOODFEN_RAPTOR, p2)

        cast_spell(game, WRATH, p1)

        damage_events = [e for e in game.state.event_log
                         if e.type == EventType.DAMAGE and
                         e.payload.get('target') == raptor.id]
        assert len(damage_events) == 1
        assert damage_events[0].payload['amount'] == 3

    def test_wrath_picks_1_damage_draw_on_high_health(self):
        """Wrath AI picks 1-damage+draw when all enemies have > 3 HP."""
        game, p1, p2 = new_hs_game()
        # Yeti: 4/5, toughness 5 > 3 → AI should pick 1-damage + draw
        yeti = make_obj(game, CHILLWIND_YETI, p2)

        cast_spell(game, WRATH, p1)

        damage_events = [e for e in game.state.event_log
                         if e.type == EventType.DAMAGE and
                         e.payload.get('target') == yeti.id]
        draw_events = [e for e in game.state.event_log
                       if e.type == EventType.DRAW and
                       e.payload.get('player') == p1.id]
        assert len(damage_events) == 1
        assert damage_events[0].payload['amount'] == 1
        assert len(draw_events) >= 1

    def test_wrath_no_targets_returns_empty(self):
        """Wrath with no enemy minions should do nothing."""
        game, p1, p2 = new_hs_game()
        # No enemy minions on board

        obj = game.create_object(
            name=WRATH.name, owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
            characteristics=WRATH.characteristics, card_def=WRATH
        )
        events = WRATH.spell_effect(obj, game.state, [])
        assert events == []

    def test_wrath_has_from_spell_flag(self):
        """Wrath damage should carry from_spell for spell damage boosts."""
        game, p1, p2 = new_hs_game()
        yeti = make_obj(game, CHILLWIND_YETI, p2)

        cast_spell(game, WRATH, p1)

        damage_events = [e for e in game.state.event_log
                         if e.type == EventType.DAMAGE and
                         e.payload.get('target') == yeti.id]
        assert len(damage_events) >= 1
        assert damage_events[0].payload.get('from_spell') is True


# ============================================================
# Nourish Choose One
# ============================================================

class TestNourishChooseOne:
    def test_nourish_ramps_below_8_crystals(self):
        """Nourish AI picks ramp when mana_crystals < 8."""
        game, p1, p2 = new_hs_game()
        p1.mana_crystals = 6

        cast_spell(game, NOURISH, p1)

        assert p1.mana_crystals == 8  # 6 + 2

    def test_nourish_draws_at_8_or_more_crystals(self):
        """Nourish AI picks draw when mana_crystals >= 8."""
        game, p1, p2 = new_hs_game()
        p1.mana_crystals = 10

        cast_spell(game, NOURISH, p1)

        draw_events = [e for e in game.state.event_log
                       if e.type == EventType.DRAW and
                       e.payload.get('player') == p1.id]
        assert len(draw_events) >= 1
        assert draw_events[0].payload.get('count') == 3

    def test_nourish_ramp_capped_at_10(self):
        """Nourish ramp should not exceed 10 mana crystals."""
        game, p1, p2 = new_hs_game()
        p1.mana_crystals = 7  # < 8, so ramps; 7 + 2 = 9 (capped by min(10, ...))

        cast_spell(game, NOURISH, p1)

        assert p1.mana_crystals <= 10

    def test_nourish_ramp_returns_no_events(self):
        """Nourish ramp mode returns no events (direct state modification)."""
        game, p1, p2 = new_hs_game()
        p1.mana_crystals = 5

        obj = game.create_object(
            name=NOURISH.name, owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
            characteristics=NOURISH.characteristics, card_def=NOURISH
        )
        events = NOURISH.spell_effect(obj, game.state, [])
        # Ramp mode returns empty list (modifies state directly)
        assert events == []
        assert p1.mana_crystals == 7


# ============================================================
# Starfall Choose One
# ============================================================

class TestStarfallChooseOne:
    def test_starfall_aoe_with_3_plus_minions(self):
        """Starfall AI picks AOE when 3+ enemy minions exist."""
        game, p1, p2 = new_hs_game()
        w1 = make_obj(game, WISP, p2)
        w2 = make_obj(game, WISP, p2)
        w3 = make_obj(game, WISP, p2)

        cast_spell(game, STARFALL, p1)

        damage_events = [e for e in game.state.event_log
                         if e.type == EventType.DAMAGE and
                         e.payload.get('from_spell') is True]
        # All 3 minions should be hit for 2 damage each
        assert len(damage_events) == 3
        for de in damage_events:
            assert de.payload['amount'] == 2

    def test_starfall_single_target_with_fewer_minions(self):
        """Starfall AI picks single-target 5 damage when < 3 enemy minions."""
        game, p1, p2 = new_hs_game()
        yeti = make_obj(game, CHILLWIND_YETI, p2)

        cast_spell(game, STARFALL, p1)

        damage_events = [e for e in game.state.event_log
                         if e.type == EventType.DAMAGE and
                         e.payload.get('target') == yeti.id]
        assert len(damage_events) == 1
        assert damage_events[0].payload['amount'] == 5

    def test_starfall_no_enemies_does_nothing(self):
        """Starfall with no enemy minions returns nothing."""
        game, p1, p2 = new_hs_game()

        obj = game.create_object(
            name=STARFALL.name, owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
            characteristics=STARFALL.characteristics, card_def=STARFALL
        )
        events = STARFALL.spell_effect(obj, game.state, [])
        assert events == []


# ============================================================
# Power of the Wild Choose One
# ============================================================

class TestPowerOfTheWild:
    def test_buffs_with_2_or_more_minions(self):
        """Power of the Wild buffs all minions when 2+ friendly minions."""
        game, p1, p2 = new_hs_game()
        w1 = make_obj(game, WISP, p1)
        w2 = make_obj(game, WISP, p1)

        cast_spell(game, POWER_OF_THE_WILD, p1)

        pt_mods = [e for e in game.state.event_log
                   if e.type == EventType.PT_MODIFICATION]
        # Both wisps should get +1/+1
        assert len(pt_mods) >= 2

    def test_summons_panther_with_fewer_than_2_minions(self):
        """Power of the Wild summons 3/2 Panther when < 2 friendly minions."""
        game, p1, p2 = new_hs_game()
        # No friendly minions (or just 1)

        cast_spell(game, POWER_OF_THE_WILD, p1)

        token_events = [e for e in game.state.event_log
                        if e.type == EventType.CREATE_TOKEN]
        assert len(token_events) >= 1
        assert token_events[0].payload['token']['name'] == 'Panther'
        assert token_events[0].payload['token']['power'] == 3
        assert token_events[0].payload['token']['toughness'] == 2

    def test_summons_panther_with_1_minion(self):
        """Power of the Wild summons Panther when exactly 1 minion (< 2)."""
        game, p1, p2 = new_hs_game()
        w1 = make_obj(game, WISP, p1)

        cast_spell(game, POWER_OF_THE_WILD, p1)

        token_events = [e for e in game.state.event_log
                        if e.type == EventType.CREATE_TOKEN]
        assert len(token_events) >= 1
        assert token_events[0].payload['token']['name'] == 'Panther'


# ============================================================
# Keeper of the Grove Choose One
# ============================================================

class TestKeeperOfTheGrove:
    def test_silences_minion_with_interceptors(self):
        """Keeper prefers silence when enemy has interceptors."""
        game, p1, p2 = new_hs_game()
        # Knife Juggler has interceptors (triggers on summon)
        jug = make_obj(game, KNIFE_JUGGLER, p2)

        play_minion(game, KEEPER_OF_THE_GROVE, p1)

        silence_events = [e for e in game.state.event_log
                          if e.type == EventType.SILENCE_TARGET and
                          e.payload.get('target') == jug.id]
        assert len(silence_events) >= 1

    def test_deals_2_damage_when_no_interceptors(self):
        """Keeper deals 2 damage when no enemy has interceptors."""
        game, p1, p2 = new_hs_game()
        # Wisp has no interceptors
        wisp = make_obj(game, WISP, p2)

        play_minion(game, KEEPER_OF_THE_GROVE, p1)

        damage_events = [e for e in game.state.event_log
                         if e.type == EventType.DAMAGE and
                         e.payload.get('amount') == 2]
        assert len(damage_events) >= 1

    def test_does_nothing_with_no_enemies(self):
        """Keeper battlecry with no enemies returns empty."""
        game, p1, p2 = new_hs_game()

        obj = make_obj(game, KEEPER_OF_THE_GROVE, p1)
        events = KEEPER_OF_THE_GROVE.battlecry(obj, game.state)
        assert events == []


# ============================================================
# Druid of the Claw Choose One
# ============================================================

class TestDruidOfTheClaw:
    def test_gains_taunt_in_bear_form(self):
        """Druid of the Claw should gain Taunt (bear form default)."""
        game, p1, p2 = new_hs_game()

        obj = make_obj(game, DRUID_OF_THE_CLAW, p1)
        events = DRUID_OF_THE_CLAW.battlecry(obj, game.state)

        # Should have added Taunt ability
        abilities = obj.characteristics.abilities or []
        has_taunt = any(a.get('keyword') == 'taunt' for a in abilities)
        assert has_taunt

    def test_gains_plus_2_health(self):
        """Druid of the Claw bear form grants +2 Health via PT_MODIFICATION."""
        game, p1, p2 = new_hs_game()

        obj = make_obj(game, DRUID_OF_THE_CLAW, p1)
        events = DRUID_OF_THE_CLAW.battlecry(obj, game.state)

        assert len(events) == 1
        assert events[0].type == EventType.PT_MODIFICATION
        assert events[0].payload['toughness_mod'] == 2


# ============================================================
# Ancient of Lore/War Choose One
# ============================================================

class TestAncientOfLore:
    def test_heals_when_life_below_15(self):
        """Ancient of Lore heals 5 when hero life < 15 (direct state mod)."""
        game, p1, p2 = new_hs_game()
        p1.life = 12

        obj = make_obj(game, ANCIENT_OF_LORE, p1)
        events = ANCIENT_OF_LORE.battlecry(obj, game.state)

        # Heal mode modifies life directly (no event), returns []
        assert events == []
        assert p1.life == 17  # 12 + 5

    def test_draws_when_life_at_or_above_15(self):
        """Ancient of Lore draws 2 when hero life >= 15."""
        game, p1, p2 = new_hs_game()
        p1.life = 20

        obj = make_obj(game, ANCIENT_OF_LORE, p1)
        events = ANCIENT_OF_LORE.battlecry(obj, game.state)

        draw_events = [e for e in events if e.type == EventType.DRAW]
        assert len(draw_events) == 1
        assert draw_events[0].payload.get('count') == 2


class TestAncientOfWar:
    def test_default_gains_taunt_and_health(self):
        """Ancient of War should gain Taunt + 5 Health (default)."""
        game, p1, p2 = new_hs_game()

        obj = make_obj(game, ANCIENT_OF_WAR, p1)
        events = ANCIENT_OF_WAR.battlecry(obj, game.state)

        abilities = obj.characteristics.abilities or []
        has_taunt = any(a.get('keyword') == 'taunt' for a in abilities)
        assert has_taunt
        assert len(events) == 1
        assert events[0].payload['toughness_mod'] == 5


# ============================================================
# Innervate Mana Mechanics
# ============================================================

class TestInnervate:
    def test_innervate_gives_2_temporary_mana(self):
        """Innervate adds 2 to mana_crystals_available."""
        game, p1, p2 = new_hs_game()
        p1.mana_crystals_available = 5

        cast_spell(game, INNERVATE, p1)

        assert p1.mana_crystals_available == 7

    def test_innervate_can_exceed_10(self):
        """Innervate at 10 mana should go to 12 (temporary excess)."""
        game, p1, p2 = new_hs_game()
        p1.mana_crystals_available = 10

        cast_spell(game, INNERVATE, p1)

        assert p1.mana_crystals_available == 12

    def test_double_innervate(self):
        """Two Innervates should give +4 mana total."""
        game, p1, p2 = new_hs_game()
        p1.mana_crystals_available = 5

        cast_spell(game, INNERVATE, p1)
        cast_spell(game, INNERVATE, p1)

        assert p1.mana_crystals_available == 9


# ============================================================
# Wild Growth Edge Cases
# ============================================================

class TestWildGrowth:
    def test_wild_growth_adds_crystal(self):
        """Wild Growth adds 1 permanent mana crystal."""
        game, p1, p2 = new_hs_game()
        p1.mana_crystals = 7

        cast_spell(game, WILD_GROWTH, p1)

        assert p1.mana_crystals == 8

    def test_wild_growth_at_10_does_nothing(self):
        """Wild Growth at 10 crystals should not exceed cap."""
        game, p1, p2 = new_hs_game()
        p1.mana_crystals = 10

        cast_spell(game, WILD_GROWTH, p1)

        assert p1.mana_crystals == 10


# ============================================================
# Savage Roar Hero Attack + Cleanup
# ============================================================

class TestSavageRoar:
    def test_buffs_friendly_minions(self):
        """Savage Roar gives +2 Attack to all friendly minions."""
        game, p1, p2 = new_hs_game()
        w1 = make_obj(game, WISP, p1)
        w2 = make_obj(game, WISP, p1)

        cast_spell(game, SAVAGE_ROAR, p1)

        pt_mods = [e for e in game.state.event_log
                   if e.type == EventType.PT_MODIFICATION and
                   e.payload.get('power_mod') == 2]
        assert len(pt_mods) >= 2

    def test_gives_hero_2_attack(self):
        """Savage Roar gives hero +2 weapon attack."""
        game, p1, p2 = new_hs_game()
        p1.weapon_attack = 0

        cast_spell(game, SAVAGE_ROAR, p1)

        assert p1.weapon_attack == 2

    def test_hero_attack_cleaned_up_at_eot(self):
        """Savage Roar hero attack should be removed at end of turn."""
        game, p1, p2 = new_hs_game()
        p1.weapon_attack = 0

        cast_spell(game, SAVAGE_ROAR, p1)
        assert p1.weapon_attack == 2

        game.emit(Event(
            type=EventType.TURN_END,
            payload={'player': p1.id},
            source='game'
        ))

        assert p1.weapon_attack == 0


# ============================================================
# Force of Nature Tokens
# ============================================================

class TestForceOfNature:
    def test_summons_3_treants(self):
        """Force of Nature creates 3 Treant tokens."""
        game, p1, p2 = new_hs_game()

        cast_spell(game, FORCE_OF_NATURE, p1)

        token_events = [e for e in game.state.event_log
                        if e.type == EventType.CREATE_TOKEN and
                        e.payload.get('token', {}).get('name') == 'Treant']
        assert len(token_events) == 3

    def test_treants_are_2_2(self):
        """Force of Nature Treants are 2/2."""
        game, p1, p2 = new_hs_game()

        cast_spell(game, FORCE_OF_NATURE, p1)

        token_events = [e for e in game.state.event_log
                        if e.type == EventType.CREATE_TOKEN]
        for te in token_events:
            assert te.payload['token']['power'] == 2
            assert te.payload['token']['toughness'] == 2


# ============================================================
# Naturalize
# ============================================================

class TestNaturalize:
    def test_destroys_enemy_minion(self):
        """Naturalize destroys an enemy minion."""
        game, p1, p2 = new_hs_game()
        yeti = make_obj(game, CHILLWIND_YETI, p2)

        cast_spell(game, NATURALIZE, p1)

        destroy_events = [e for e in game.state.event_log
                          if e.type == EventType.OBJECT_DESTROYED and
                          e.payload.get('object_id') == yeti.id]
        assert len(destroy_events) == 1

    def test_opponent_draws_2_cards(self):
        """Naturalize makes opponent draw 2 cards."""
        game, p1, p2 = new_hs_game()
        yeti = make_obj(game, CHILLWIND_YETI, p2)

        cast_spell(game, NATURALIZE, p1)

        draw_events = [e for e in game.state.event_log
                       if e.type == EventType.DRAW and
                       e.payload.get('player') == p2.id]
        assert len(draw_events) >= 1
        assert draw_events[0].payload.get('count') == 2


# ============================================================
# Swipe AOE Interactions
# ============================================================

class TestSwipe:
    def test_swipe_deals_splash_damage(self):
        """Swipe hits primary target for 4 and others for 1."""
        game, p1, p2 = new_hs_game()
        y1 = make_obj(game, CHILLWIND_YETI, p2)
        y2 = make_obj(game, CHILLWIND_YETI, p2)

        cast_spell(game, SWIPE, p1)

        damage_events = [e for e in game.state.event_log
                         if e.type == EventType.DAMAGE]
        # Should have at least 2 damage events (primary + splash)
        assert len(damage_events) >= 2


# ============================================================
# Claw / Bite Hero Attack Cleanup
# ============================================================

class TestClawBite:
    def test_claw_gives_2_armor(self):
        """Claw gives 2 armor."""
        game, p1, p2 = new_hs_game()
        p1.armor = 0

        cast_spell(game, CLAW, p1)

        assert p1.armor == 2

    def test_claw_gives_hero_2_attack(self):
        """Claw gives hero +2 attack this turn."""
        game, p1, p2 = new_hs_game()
        p1.weapon_attack = 0

        cast_spell(game, CLAW, p1)

        assert p1.weapon_attack == 2

    def test_bite_gives_4_armor_and_4_attack(self):
        """Bite gives 4 armor and +4 attack."""
        game, p1, p2 = new_hs_game()
        p1.armor = 0
        p1.weapon_attack = 0

        cast_spell(game, BITE, p1)

        assert p1.armor == 4
        assert p1.weapon_attack == 4
