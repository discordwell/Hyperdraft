"""
Hearthstone Unhappy Path Tests - Batch 57

Aura survival during board wipes, silence edge cases on enchanted and
transformed minions, and fatigue damage progression: Stormwind Champion
minions during Flamestrike, Dire Wolf Alpha adjacency during combat,
silence on Blessing of Kings'd minion, silence on Polymorphed sheep,
double silence, Mass Dispel on aura board, fatigue cumulative damage
(1+2+3+4), fatigue killing hero, multiple draws from empty deck.
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
    STORMWIND_CHAMPION,
)
from src.cards.hearthstone.classic import (
    FLAMESTRIKE, POLYMORPH, DIRE_WOLF_ALPHA,
)
from src.cards.hearthstone.paladin import (
    BLESSING_OF_KINGS, BLESSING_OF_MIGHT,
)
from src.cards.hearthstone.priest import (
    SILENCE_SPELL, MASS_DISPEL,
)


# ============================================================
# Test Helpers
# ============================================================

def new_hs_game():
    game = Game(mode='hearthstone')
    p1 = game.add_player("Player1", life=30)
    p2 = game.add_player("Player2", life=30)
    game.setup_hearthstone_player(p1, HEROES["Paladin"], HERO_POWERS["Paladin"])
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


def silence_minion(game, target_id):
    """Emit a SILENCE_TARGET event on the given minion."""
    game.emit(Event(
        type=EventType.SILENCE_TARGET,
        payload={'target': target_id},
        source='test'
    ))


# ============================================================
# Aura Interactions - Stormwind Champion
# ============================================================

class TestStormwindChampionAura:
    """Stormwind Champion gives other friendly minions +1/+1 via QUERY interceptors."""

    def test_wisps_get_plus_1_1_from_stormwind(self):
        """Stormwind Champion on board with 2 Wisps: Wisps should be 2/2."""
        game, p1, p2 = new_hs_game()
        wisp1 = make_obj(game, WISP, p1)
        wisp2 = make_obj(game, WISP, p1)
        _champion = make_obj(game, STORMWIND_CHAMPION, p1)

        assert get_power(wisp1, game.state) == 2
        assert get_toughness(wisp1, game.state) == 2
        assert get_power(wisp2, game.state) == 2
        assert get_toughness(wisp2, game.state) == 2

    def test_wisps_revert_after_stormwind_dies(self):
        """Kill Stormwind Champion -> Wisps should revert to 1/1."""
        game, p1, p2 = new_hs_game()
        wisp1 = make_obj(game, WISP, p1)
        wisp2 = make_obj(game, WISP, p1)
        champion = make_obj(game, STORMWIND_CHAMPION, p1)

        # Verify buff is active
        assert get_power(wisp1, game.state) == 2
        assert get_toughness(wisp1, game.state) == 2

        # Kill the Stormwind Champion
        game.destroy(champion.id)
        game.check_state_based_actions()

        # Wisps should revert to base 1/1
        assert get_power(wisp1, game.state) == 1
        assert get_toughness(wisp1, game.state) == 1
        assert get_power(wisp2, game.state) == 1
        assert get_toughness(wisp2, game.state) == 1

    def test_stormwind_does_not_buff_itself(self):
        """Stormwind Champion should not buff itself (only 'other' minions)."""
        game, p1, p2 = new_hs_game()
        champion = make_obj(game, STORMWIND_CHAMPION, p1)

        # Stormwind Champion is 6/6 base - should remain 6/6
        assert get_power(champion, game.state) == 6
        assert get_toughness(champion, game.state) == 6

    def test_stormwind_does_not_buff_enemy_minions(self):
        """Stormwind Champion should not buff enemy minions."""
        game, p1, p2 = new_hs_game()
        _champion = make_obj(game, STORMWIND_CHAMPION, p1)
        enemy_wisp = make_obj(game, WISP, p2)

        assert get_power(enemy_wisp, game.state) == 1
        assert get_toughness(enemy_wisp, game.state) == 1


# ============================================================
# Aura Interactions - Stormwind Champion + Flamestrike
# ============================================================

class TestStormwindChampionPlusFlamestrike:
    """Yeti with Stormwind Champion aura should survive Flamestrike."""

    def test_yeti_survives_flamestrike_with_stormwind_aura(self):
        """
        Player1 has Stormwind Champion + Chillwind Yeti.
        Player2 casts Flamestrike (4 damage to all enemies).
        Yeti is normally 4/5, with Stormwind it's 5/6.
        Flamestrike deals 4 damage -> Yeti at 4 damage with 6 toughness -> survives.
        """
        game, p1, p2 = new_hs_game()
        yeti = make_obj(game, CHILLWIND_YETI, p1)
        _champion = make_obj(game, STORMWIND_CHAMPION, p1)

        # Verify aura is active: Yeti should be 5/6
        assert get_power(yeti, game.state) == 5
        assert get_toughness(yeti, game.state) == 6

        # Cast Flamestrike from Player2 - deals 4 damage to all enemy minions
        cast_spell(game, FLAMESTRIKE, p2)
        game.check_state_based_actions()

        # Yeti has 6 toughness (aura) and took 4 damage -> 4 < 6 -> alive
        yeti_obj = game.state.objects.get(yeti.id)
        assert yeti_obj is not None
        assert yeti_obj.zone == ZoneType.BATTLEFIELD
        assert yeti_obj.state.damage == 4

    def test_wisp_dies_to_flamestrike_despite_stormwind_aura(self):
        """
        Wisp (1/1) with Stormwind aura becomes 2/2.
        Flamestrike deals 4 damage -> 4 >= 2 -> Wisp dies.
        """
        game, p1, p2 = new_hs_game()
        wisp = make_obj(game, WISP, p1)
        _champion = make_obj(game, STORMWIND_CHAMPION, p1)

        assert get_toughness(wisp, game.state) == 2

        cast_spell(game, FLAMESTRIKE, p2)
        game.check_state_based_actions()

        # Wisp should be dead (4 damage >= 2 toughness)
        wisp_obj = game.state.objects.get(wisp.id)
        assert wisp_obj is None or wisp_obj.zone != ZoneType.BATTLEFIELD


# ============================================================
# Aura Interactions - Dire Wolf Alpha Adjacency
# ============================================================

class TestDireWolfAlphaAdjacency:
    """Dire Wolf Alpha gives adjacent minions +1 Attack."""

    def test_adjacent_wisps_get_plus_1_attack(self):
        """Dire Wolf Alpha between two Wisps -> adjacent Wisps get +1 attack (power=2)."""
        game, p1, p2 = new_hs_game()
        wisp1 = make_obj(game, WISP, p1)
        wolf = make_obj(game, DIRE_WOLF_ALPHA, p1)
        wisp2 = make_obj(game, WISP, p1)

        # Both Wisps should have power 2 (1 base + 1 from adjacency)
        assert get_power(wisp1, game.state) == 2
        assert get_power(wisp2, game.state) == 2

    def test_dire_wolf_does_not_buff_itself(self):
        """Dire Wolf Alpha does not buff itself (power stays at 2)."""
        game, p1, p2 = new_hs_game()
        _wisp1 = make_obj(game, WISP, p1)
        wolf = make_obj(game, DIRE_WOLF_ALPHA, p1)
        _wisp2 = make_obj(game, WISP, p1)

        assert get_power(wolf, game.state) == 2

    def test_non_adjacent_wisp_not_buffed(self):
        """A Wisp not adjacent to Dire Wolf Alpha should not get the buff."""
        game, p1, p2 = new_hs_game()
        wisp_far = make_obj(game, WISP, p1)
        _blocker = make_obj(game, BLOODFEN_RAPTOR, p1)
        wolf = make_obj(game, DIRE_WOLF_ALPHA, p1)

        # wisp_far is at index 0, blocker at index 1, wolf at index 2
        # Wolf's adjacents are blocker (left) and nothing (right)
        # wisp_far is NOT adjacent to wolf
        assert get_power(wisp_far, game.state) == 1

    def test_dire_wolf_only_buffs_attack_not_toughness(self):
        """Dire Wolf Alpha only gives +1 Attack, not +1 Health."""
        game, p1, p2 = new_hs_game()
        wisp = make_obj(game, WISP, p1)
        _wolf = make_obj(game, DIRE_WOLF_ALPHA, p1)

        assert get_power(wisp, game.state) == 2
        assert get_toughness(wisp, game.state) == 1  # No toughness buff


# ============================================================
# Multiple Auras Stack
# ============================================================

class TestMultipleAurasStack:
    """Stormwind Champion + Dire Wolf Alpha should stack on adjacent minions."""

    def test_stormwind_plus_dire_wolf_on_wisp(self):
        """
        Stormwind Champion + Dire Wolf Alpha adjacent to a Wisp.
        Wisp gets +1/+1 from Stormwind and +1 attack from Wolf = power 3, toughness 2.
        """
        game, p1, p2 = new_hs_game()
        _champion = make_obj(game, STORMWIND_CHAMPION, p1)
        wisp = make_obj(game, WISP, p1)
        _wolf = make_obj(game, DIRE_WOLF_ALPHA, p1)

        # Wisp: base 1/1 + Stormwind(+1/+1) + Wolf(+1/+0) = 3/2
        assert get_power(wisp, game.state) == 3
        assert get_toughness(wisp, game.state) == 2


# ============================================================
# Silence Edge Cases - Buff Removal
# ============================================================

class TestSilenceRemovesBuff:
    """Silence should remove enchantments (PT modifiers) from a minion."""

    def test_silence_removes_blessing_of_kings(self):
        """
        Cast Blessing of Kings on a Wisp (+4/+4 -> 5/5).
        Silence the Wisp.
        After silence, Wisp should revert to 1/1.
        """
        game, p1, p2 = new_hs_game()
        wisp = make_obj(game, WISP, p1)

        # Apply Blessing of Kings manually (it picks random friendly, seed to hit wisp)
        # Directly apply the PT_MODIFICATION to the wisp for determinism
        game.emit(Event(
            type=EventType.PT_MODIFICATION,
            payload={'object_id': wisp.id, 'power_mod': 4, 'toughness_mod': 4, 'duration': 'permanent'},
            source='test'
        ))

        # Verify buff applied
        assert get_power(wisp, game.state) == 5
        assert get_toughness(wisp, game.state) == 5

        # Silence the wisp
        silence_minion(game, wisp.id)

        # After silence, pt_modifiers should be cleared -> back to 1/1
        assert get_power(wisp, game.state) == 1
        assert get_toughness(wisp, game.state) == 1


# ============================================================
# Silence Edge Cases - Polymorph + Silence
# ============================================================

class TestSilenceOnPolymorphedSheep:
    """Silence on a Polymorphed Sheep should leave it as 1/1 (transformation is permanent)."""

    def test_silence_on_sheep_stays_1_1(self):
        """
        Polymorph a Yeti into 1/1 Sheep. Then silence the Sheep.
        Sheep should remain 1/1 because Polymorph is a transformation, not an enchantment.
        """
        game, p1, p2 = new_hs_game()
        yeti = make_obj(game, CHILLWIND_YETI, p2)

        # Polymorph the Yeti
        cast_spell(game, POLYMORPH, p1, targets=[yeti.id])

        # Verify it's a Sheep
        sheep = game.state.objects.get(yeti.id)
        assert sheep is not None
        assert sheep.name == "Sheep"
        assert sheep.characteristics.power == 1
        assert sheep.characteristics.toughness == 1

        # Silence the Sheep
        silence_minion(game, yeti.id)

        # Should still be 1/1 Sheep
        sheep_after = game.state.objects.get(yeti.id)
        assert sheep_after is not None
        assert get_power(sheep_after, game.state) == 1
        assert get_toughness(sheep_after, game.state) == 1


# ============================================================
# Silence Edge Cases - Double Silence
# ============================================================

class TestDoubleSilenceNoError:
    """Silencing a minion twice should not crash."""

    def test_double_silence_no_crash(self):
        """Silence a minion. Silence it again. No crash should occur."""
        game, p1, p2 = new_hs_game()
        yeti = make_obj(game, CHILLWIND_YETI, p1)

        silence_minion(game, yeti.id)
        silence_minion(game, yeti.id)

        # Should still be a valid object
        yeti_obj = game.state.objects.get(yeti.id)
        assert yeti_obj is not None
        assert get_power(yeti_obj, game.state) == 4
        assert get_toughness(yeti_obj, game.state) == 5

    def test_double_silence_on_buffed_minion(self):
        """Silence a buffed minion twice. Both should succeed without error."""
        game, p1, p2 = new_hs_game()
        wisp = make_obj(game, WISP, p1)

        # Buff the wisp
        game.emit(Event(
            type=EventType.PT_MODIFICATION,
            payload={'object_id': wisp.id, 'power_mod': 3, 'toughness_mod': 3, 'duration': 'permanent'},
            source='test'
        ))
        assert get_power(wisp, game.state) == 4

        # First silence removes buff
        silence_minion(game, wisp.id)
        assert get_power(wisp, game.state) == 1

        # Second silence: should not crash, stats unchanged
        silence_minion(game, wisp.id)
        assert get_power(wisp, game.state) == 1
        assert get_toughness(wisp, game.state) == 1


# ============================================================
# Silence Edge Cases - Mass Dispel
# ============================================================

class TestMassDispelSilencesAll:
    """Mass Dispel silences all enemy minions and draws a card."""

    def test_mass_dispel_silences_all_enemy_minions(self):
        """
        Player2 has 3 minions. Player1 casts Mass Dispel.
        All 3 enemy minions should receive SILENCE_TARGET events.
        """
        game, p1, p2 = new_hs_game()
        wisp1 = make_obj(game, WISP, p2)
        wisp2 = make_obj(game, WISP, p2)
        yeti = make_obj(game, CHILLWIND_YETI, p2)

        # Buff the wisps so silence has visible effect
        game.emit(Event(
            type=EventType.PT_MODIFICATION,
            payload={'object_id': wisp1.id, 'power_mod': 3, 'toughness_mod': 0, 'duration': 'permanent'},
            source='test'
        ))
        game.emit(Event(
            type=EventType.PT_MODIFICATION,
            payload={'object_id': wisp2.id, 'power_mod': 3, 'toughness_mod': 0, 'duration': 'permanent'},
            source='test'
        ))

        # Verify buffs active
        assert get_power(wisp1, game.state) == 4
        assert get_power(wisp2, game.state) == 4

        cast_spell(game, MASS_DISPEL, p1)

        # All enemy minions should have been silenced
        silence_events = [e for e in game.state.event_log
                          if e.type == EventType.SILENCE_TARGET]
        silenced_ids = {e.payload.get('target') for e in silence_events}

        assert wisp1.id in silenced_ids
        assert wisp2.id in silenced_ids
        assert yeti.id in silenced_ids

    def test_mass_dispel_removes_buffs(self):
        """Mass Dispel should remove PT modifiers from enemy minions."""
        game, p1, p2 = new_hs_game()
        wisp = make_obj(game, WISP, p2)

        # Buff the wisp
        game.emit(Event(
            type=EventType.PT_MODIFICATION,
            payload={'object_id': wisp.id, 'power_mod': 5, 'toughness_mod': 5, 'duration': 'permanent'},
            source='test'
        ))
        assert get_power(wisp, game.state) == 6

        cast_spell(game, MASS_DISPEL, p1)

        # Wisp should be back to 1/1
        assert get_power(wisp, game.state) == 1
        assert get_toughness(wisp, game.state) == 1

    def test_mass_dispel_does_not_silence_friendly_minions(self):
        """Mass Dispel only silences enemy minions, not friendly ones."""
        game, p1, p2 = new_hs_game()
        friendly_wisp = make_obj(game, WISP, p1)
        enemy_wisp = make_obj(game, WISP, p2)

        # Buff both wisps
        game.emit(Event(
            type=EventType.PT_MODIFICATION,
            payload={'object_id': friendly_wisp.id, 'power_mod': 3, 'toughness_mod': 0, 'duration': 'permanent'},
            source='test'
        ))
        game.emit(Event(
            type=EventType.PT_MODIFICATION,
            payload={'object_id': enemy_wisp.id, 'power_mod': 3, 'toughness_mod': 0, 'duration': 'permanent'},
            source='test'
        ))

        cast_spell(game, MASS_DISPEL, p1)

        # Friendly wisp should keep its buff
        assert get_power(friendly_wisp, game.state) == 4
        # Enemy wisp should lose its buff
        assert get_power(enemy_wisp, game.state) == 1

    def test_mass_dispel_draws_a_card(self):
        """Mass Dispel also draws a card for the caster."""
        game, p1, p2 = new_hs_game()
        _enemy = make_obj(game, WISP, p2)

        # Put a card in Player1's library so draw has something to draw
        _lib_card = game.create_object(
            name="Library Card", owner_id=p1.id, zone=ZoneType.LIBRARY,
            characteristics=WISP.characteristics, card_def=WISP
        )

        hand_before = len(game.state.zones.get(f"hand_{p1.id}", type('', (), {'objects': []})()).objects) \
            if f"hand_{p1.id}" in game.state.zones else 0

        cast_spell(game, MASS_DISPEL, p1)

        draw_events = [e for e in game.state.event_log
                       if e.type == EventType.DRAW and
                       e.payload.get('player') == p1.id]
        assert len(draw_events) >= 1


# ============================================================
# Silence Edge Cases - Silence Removes Aura From Source
# ============================================================

class TestSilenceRemovesAuraFromSource:
    """Silencing the aura source (Stormwind Champion) removes its buff from other minions."""

    def test_silence_stormwind_removes_aura(self):
        """
        Stormwind Champion buffing a Wisp -> Wisp is 2/2.
        Silence the Stormwind Champion.
        Stormwind loses its aura interceptors -> Wisp should revert to 1/1.
        """
        game, p1, p2 = new_hs_game()
        wisp = make_obj(game, WISP, p1)
        champion = make_obj(game, STORMWIND_CHAMPION, p1)

        # Verify aura active
        assert get_power(wisp, game.state) == 2
        assert get_toughness(wisp, game.state) == 2

        # Silence the Stormwind Champion (removes its interceptors)
        silence_minion(game, champion.id)

        # Wisp should lose the aura buff
        assert get_power(wisp, game.state) == 1
        assert get_toughness(wisp, game.state) == 1

    def test_silenced_stormwind_keeps_base_stats(self):
        """Silenced Stormwind Champion should keep its base 6/6 stats."""
        game, p1, p2 = new_hs_game()
        champion = make_obj(game, STORMWIND_CHAMPION, p1)

        silence_minion(game, champion.id)

        assert get_power(champion, game.state) == 6
        assert get_toughness(champion, game.state) == 6


# ============================================================
# Fatigue Damage Progression
# ============================================================

class TestFatigueIncrements:
    """Fatigue damage should increment: 1, 2, 3, 4, ..."""

    def test_fatigue_deals_incremental_damage(self):
        """
        Player with empty library. Draw 4 times.
        Fatigue should deal 1, then 2, then 3, then 4 damage (total 10).
        """
        game, p1, p2 = new_hs_game()
        p1.life = 30

        # Ensure library is empty
        lib_key = f"library_{p1.id}"
        if lib_key in game.state.zones:
            game.state.zones[lib_key].objects.clear()

        # Draw 4 times from empty deck
        for _ in range(4):
            game.draw_cards(p1.id, 1)

        # Total fatigue: 1 + 2 + 3 + 4 = 10
        assert p1.life == 20

    def test_fatigue_counter_value_after_draws(self):
        """After 4 draws from empty deck, fatigue counter should be at 4."""
        game, p1, p2 = new_hs_game()

        lib_key = f"library_{p1.id}"
        if lib_key in game.state.zones:
            game.state.zones[lib_key].objects.clear()

        for _ in range(4):
            game.draw_cards(p1.id, 1)

        assert p1.fatigue_damage == 4


class TestFatigueKillsHero:
    """Fatigue damage can kill the hero if life reaches 0."""

    def test_fatigue_kills_hero_at_low_life(self):
        """
        Player at 5 life with empty library. Draw 3 times (1+2+3=6 damage).
        Hero should die (life goes to -1).
        """
        game, p1, p2 = new_hs_game()
        p1.life = 5

        lib_key = f"library_{p1.id}"
        if lib_key in game.state.zones:
            game.state.zones[lib_key].objects.clear()

        for _ in range(3):
            game.draw_cards(p1.id, 1)

        # 1 + 2 + 3 = 6 damage -> 5 - 6 = -1
        assert p1.life <= 0
        assert p1.life == -1

    def test_fatigue_kills_triggers_player_loses(self):
        """Check state-based actions after fatal fatigue detects player loss."""
        game, p1, p2 = new_hs_game()
        p1.life = 1

        lib_key = f"library_{p1.id}"
        if lib_key in game.state.zones:
            game.state.zones[lib_key].objects.clear()

        # 1 fatigue damage kills a player at 1 life
        game.draw_cards(p1.id, 1)
        assert p1.life == 0

        game.check_state_based_actions()
        assert p1.has_lost is True


class TestFatigueCounterPersists:
    """Fatigue counter should persist across draws."""

    def test_fatigue_counter_at_2_after_two_draws(self):
        """
        Draw twice from empty deck (1+2=3 damage).
        Fatigue counter should be at 2 (next draw would deal 3).
        """
        game, p1, p2 = new_hs_game()
        p1.life = 30

        lib_key = f"library_{p1.id}"
        if lib_key in game.state.zones:
            game.state.zones[lib_key].objects.clear()

        game.draw_cards(p1.id, 1)
        game.draw_cards(p1.id, 1)

        assert p1.fatigue_damage == 2
        assert p1.life == 27  # 30 - 1 - 2 = 27

    def test_fatigue_counter_continues_after_pause(self):
        """Fatigue counter keeps incrementing even after non-draw actions."""
        game, p1, p2 = new_hs_game()
        p1.life = 30

        lib_key = f"library_{p1.id}"
        if lib_key in game.state.zones:
            game.state.zones[lib_key].objects.clear()

        game.draw_cards(p1.id, 1)  # 1 damage, counter = 1
        # Do something else (create a minion)
        _wisp = make_obj(game, WISP, p1)
        game.draw_cards(p1.id, 1)  # 2 damage, counter = 2

        assert p1.fatigue_damage == 2
        assert p1.life == 27


class TestMultipleDrawsSameTurn:
    """Multiple draws in one event from empty deck should each trigger fatigue."""

    def test_draw_3_from_empty_deck(self):
        """
        Player with empty deck. Draw event for 3 cards.
        Should trigger fatigue 3 times: 1+2+3=6 damage total.
        """
        game, p1, p2 = new_hs_game()
        p1.life = 30

        lib_key = f"library_{p1.id}"
        if lib_key in game.state.zones:
            game.state.zones[lib_key].objects.clear()

        # Single draw event requesting 3 cards
        game.draw_cards(p1.id, 3)

        assert p1.fatigue_damage == 3
        assert p1.life == 24  # 30 - (1+2+3) = 24

    def test_draw_5_from_empty_deck(self):
        """
        Draw 5 from empty deck: 1+2+3+4+5=15 damage.
        """
        game, p1, p2 = new_hs_game()
        p1.life = 30

        lib_key = f"library_{p1.id}"
        if lib_key in game.state.zones:
            game.state.zones[lib_key].objects.clear()

        game.draw_cards(p1.id, 5)

        assert p1.fatigue_damage == 5
        assert p1.life == 15  # 30 - 15 = 15

    def test_partial_draw_then_fatigue(self):
        """
        Library has 1 card. Draw 3: first draw gets the card, next 2 trigger fatigue.
        Fatigue: 1+2=3 damage.
        """
        game, p1, p2 = new_hs_game()
        p1.life = 30

        lib_key = f"library_{p1.id}"
        if lib_key in game.state.zones:
            game.state.zones[lib_key].objects.clear()

        # Add exactly 1 card to library
        lib_card = game.create_object(
            name="Last Card", owner_id=p1.id, zone=ZoneType.LIBRARY,
            characteristics=WISP.characteristics, card_def=WISP
        )

        game.draw_cards(p1.id, 3)

        # 1 real draw + 2 fatigue draws (1+2=3 damage)
        assert p1.fatigue_damage == 2
        assert p1.life == 27  # 30 - 1 - 2 = 27
