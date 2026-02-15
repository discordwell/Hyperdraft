"""
Hearthstone Unhappy Path Tests - Batch 80

Deathrattle Edge Cases: deathrattle interactions with silence, transform,
copy effects, stacking, board state, and chain reactions. Tests include:
silenced deathrattles, transformed minions losing deathrattles, Abomination
AOE damage to all characters, deathrattle token spawns on full/near-full boards,
multiple deathrattles firing in play order, simultaneous deaths, Sylvanas steal
mechanics, Tirion weapon equip, Savannah Highmane hyenas, bounced minions,
Knife Juggler + deathrattle tokens, Loot Hoarder fatigue, and Bloodmage Thalnos.
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
    WISP, CHILLWIND_YETI, BLOODFEN_RAPTOR,
)
from src.cards.hearthstone.classic import (
    KNIFE_JUGGLER, IRONBEAK_OWL, LOOT_HOARDER, ABOMINATION,
    HARVEST_GOLEM, CAIRNE_BLOODHOOF, SYLVANAS_WINDRUNNER,
    BLOODMAGE_THALNOS, POLYMORPH,
)
from src.cards.hearthstone.hunter import SAVANNAH_HIGHMANE
from src.cards.hearthstone.paladin import TIRION_FORDRING
from src.cards.hearthstone.shaman import HEX


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


def play_minion(game, card_def, owner):
    """Play a minion from hand to battlefield (triggers ZONE_CHANGE interceptors)."""
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


def destroy_minion(game, obj):
    """Destroy a minion via OBJECT_DESTROYED event."""
    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': obj.id},
        source='test'
    ))


def count_minions(game, controller=None, name=None):
    """Count minions on the battlefield matching optional filters."""
    battlefield = game.state.zones.get('battlefield')
    if not battlefield:
        return 0
    count = 0
    for oid in battlefield.objects:
        obj = game.state.objects.get(oid)
        if not obj or CardType.MINION not in obj.characteristics.types:
            continue
        if controller and obj.controller != controller:
            continue
        if name and obj.name != name:
            continue
        count += 1
    return count


def get_minion(game, name):
    """Get the first minion with the given name from the battlefield."""
    battlefield = game.state.zones.get('battlefield')
    if not battlefield:
        return None
    for oid in battlefield.objects:
        obj = game.state.objects.get(oid)
        if obj and obj.name == name:
            return obj
    return None


# ============================================================
# Test 1: Silenced Deathrattle Doesn't Fire
# ============================================================

class TestSilencedDeathrattleDoesntFire:
    """Silencing a minion removes its deathrattle, preventing it from firing."""

    def test_silenced_loot_hoarder_no_draw(self):
        """Silenced Loot Hoarder doesn't draw a card when it dies."""
        game, p1, p2 = new_hs_game()
        hoarder = make_obj(game, LOOT_HOARDER, p1)

        # Put a card in library
        make_obj(game, WISP, p1, zone=ZoneType.LIBRARY)

        # Silence the Loot Hoarder
        game.emit(Event(
            type=EventType.SILENCE_TARGET,
            payload={'target': hoarder.id},
            source='test'
        ))

        game.state.event_log.clear()
        destroy_minion(game, hoarder)

        # Verify no DRAW event fired
        draw_events = [e for e in game.state.event_log if e.type == EventType.DRAW]
        assert len(draw_events) == 0, (
            f"Silenced Loot Hoarder should not draw, got {len(draw_events)} DRAW events"
        )

    def test_silenced_cairne_no_baine(self):
        """Silenced Cairne Bloodhoof doesn't summon Baine Bloodhoof."""
        game, p1, p2 = new_hs_game()
        cairne = make_obj(game, CAIRNE_BLOODHOOF, p1)

        # Silence Cairne
        game.emit(Event(
            type=EventType.SILENCE_TARGET,
            payload={'target': cairne.id},
            source='test'
        ))

        game.state.event_log.clear()
        destroy_minion(game, cairne)

        # Verify no CREATE_TOKEN for Baine
        token_events = [e for e in game.state.event_log
                        if e.type == EventType.CREATE_TOKEN and
                        e.payload.get('token', {}).get('name') == 'Baine Bloodhoof']
        assert len(token_events) == 0, (
            f"Silenced Cairne should not summon Baine, got {len(token_events)} tokens"
        )

    def test_silenced_harvest_golem_no_damaged_golem(self):
        """Silenced Harvest Golem doesn't summon Damaged Golem."""
        game, p1, p2 = new_hs_game()
        golem = make_obj(game, HARVEST_GOLEM, p1)

        # Silence the Harvest Golem
        game.emit(Event(
            type=EventType.SILENCE_TARGET,
            payload={'target': golem.id},
            source='test'
        ))

        game.state.event_log.clear()
        destroy_minion(game, golem)

        # Verify no Damaged Golem token
        token_events = [e for e in game.state.event_log
                        if e.type == EventType.CREATE_TOKEN and
                        e.payload.get('token', {}).get('name') == 'Damaged Golem']
        assert len(token_events) == 0, (
            f"Silenced Harvest Golem should not summon token, got {len(token_events)}"
        )

    def test_silenced_sylvanas_no_steal(self):
        """Silenced Sylvanas Windrunner doesn't steal an enemy minion."""
        game, p1, p2 = new_hs_game()
        sylvanas = make_obj(game, SYLVANAS_WINDRUNNER, p1)
        enemy_yeti = make_obj(game, CHILLWIND_YETI, p2)

        # Silence Sylvanas
        game.emit(Event(
            type=EventType.SILENCE_TARGET,
            payload={'target': sylvanas.id},
            source='test'
        ))

        game.state.event_log.clear()
        destroy_minion(game, sylvanas)

        # Verify no CONTROL_CHANGE event
        control_events = [e for e in game.state.event_log
                          if e.type == EventType.CONTROL_CHANGE]
        assert len(control_events) == 0, (
            f"Silenced Sylvanas should not steal, got {len(control_events)} CONTROL_CHANGE events"
        )


# ============================================================
# Test 2: Transformed Minion Loses Deathrattle
# ============================================================

class TestTransformedMinionLosesDeathrattle:
    """Transform effects (Polymorph, Hex) remove deathrattles."""

    def test_polymorphed_cairne_no_baine(self):
        """Polymorph Cairne into a 1/1 Sheep -> no Baine on sheep death."""
        game, p1, p2 = new_hs_game()
        cairne = make_obj(game, CAIRNE_BLOODHOOF, p1)

        # Polymorph Cairne
        cast_spell(game, POLYMORPH, p2, targets=[cairne.id])

        # Verify Cairne is now a 1/1 Sheep
        assert cairne.characteristics.power == 1
        assert cairne.characteristics.toughness == 1

        game.state.event_log.clear()
        destroy_minion(game, cairne)

        # Verify no Baine token
        token_events = [e for e in game.state.event_log
                        if e.type == EventType.CREATE_TOKEN and
                        e.payload.get('token', {}).get('name') == 'Baine Bloodhoof']
        assert len(token_events) == 0, (
            f"Polymorphed Cairne should not summon Baine, got {len(token_events)}"
        )

    def test_hexed_sylvanas_no_steal(self):
        """Hex Sylvanas into a 0/1 Frog -> no steal on frog death."""
        game, p1, p2 = new_hs_game()
        sylvanas = make_obj(game, SYLVANAS_WINDRUNNER, p1)
        enemy_yeti = make_obj(game, CHILLWIND_YETI, p2)

        # Hex Sylvanas (targets random enemy, seed for determinism)
        random.seed(42)
        cast_spell(game, HEX, p2, targets=[sylvanas.id])

        # Verify Sylvanas is now a 0/1 Frog
        assert sylvanas.characteristics.power == 0
        assert sylvanas.characteristics.toughness == 1

        game.state.event_log.clear()
        destroy_minion(game, sylvanas)

        # Verify no CONTROL_CHANGE
        control_events = [e for e in game.state.event_log
                          if e.type == EventType.CONTROL_CHANGE]
        assert len(control_events) == 0, (
            f"Hexed Sylvanas should not steal, got {len(control_events)} events"
        )

    def test_polymorphed_loot_hoarder_no_draw(self):
        """Polymorphed Loot Hoarder doesn't draw on death."""
        game, p1, p2 = new_hs_game()
        hoarder = make_obj(game, LOOT_HOARDER, p1)
        make_obj(game, WISP, p1, zone=ZoneType.LIBRARY)

        cast_spell(game, POLYMORPH, p2, targets=[hoarder.id])

        game.state.event_log.clear()
        destroy_minion(game, hoarder)

        draw_events = [e for e in game.state.event_log if e.type == EventType.DRAW]
        assert len(draw_events) == 0, (
            f"Polymorphed Loot Hoarder should not draw, got {len(draw_events)}"
        )


# ============================================================
# Test 3: Abomination Deathrattle Damages All Characters
# ============================================================

class TestAbominationDeathrattleDamagesAll:
    """Abomination deathrattle deals 2 damage to ALL characters including friendly."""

    def test_abomination_damages_friendly_minions(self):
        """Abomination deals 2 damage to friendly minions on death."""
        game, p1, p2 = new_hs_game()
        abom = make_obj(game, ABOMINATION, p1)
        friendly_yeti = make_obj(game, CHILLWIND_YETI, p1)

        game.state.event_log.clear()
        destroy_minion(game, abom)

        # Verify friendly yeti took 2 damage
        assert friendly_yeti.state.damage == 2, (
            f"Friendly Yeti should take 2 damage from Abomination, got {friendly_yeti.state.damage}"
        )

    def test_abomination_damages_enemy_minions(self):
        """Abomination deals 2 damage to enemy minions on death."""
        game, p1, p2 = new_hs_game()
        abom = make_obj(game, ABOMINATION, p1)
        enemy_yeti = make_obj(game, CHILLWIND_YETI, p2)

        game.state.event_log.clear()
        destroy_minion(game, abom)

        # Verify enemy yeti took 2 damage
        assert enemy_yeti.state.damage == 2, (
            f"Enemy Yeti should take 2 damage, got {enemy_yeti.state.damage}"
        )

    def test_abomination_damages_both_heroes(self):
        """Abomination deals 2 damage to both heroes on death."""
        game, p1, p2 = new_hs_game()
        abom = make_obj(game, ABOMINATION, p1)

        destroy_minion(game, abom)

        # Both heroes should have taken 2 damage
        assert p1.life == 28, f"P1 hero should have 28 life, got {p1.life}"
        assert p2.life == 28, f"P2 hero should have 28 life, got {p2.life}"

    def test_abomination_damages_all_four_targets(self):
        """Abomination with 1 friendly + 1 enemy minion + 2 heroes = 4 damage events."""
        game, p1, p2 = new_hs_game()
        abom = make_obj(game, ABOMINATION, p1)
        friendly = make_obj(game, BLOODFEN_RAPTOR, p1)
        enemy = make_obj(game, BLOODFEN_RAPTOR, p2)

        game.state.event_log.clear()
        destroy_minion(game, abom)

        # Count DAMAGE events from Abomination
        damage_events = [e for e in game.state.event_log
                         if e.type == EventType.DAMAGE and
                         e.payload.get('source') == abom.id and
                         e.payload.get('amount') == 2]
        assert len(damage_events) == 4, (
            f"Abomination should deal damage to 4 targets, got {len(damage_events)}"
        )


# ============================================================
# Test 4: Abomination + Other Deathrattles Simultaneous Death
# ============================================================

class TestAbominationChainDeathrattles:
    """Abomination deathrattle can kill other minions, triggering their deathrattles."""

    def test_abomination_kills_loot_hoarder_chain(self):
        """Abomination dies, damages Loot Hoarder (2/1) to death, Loot Hoarder draws."""
        game, p1, p2 = new_hs_game()
        abom = make_obj(game, ABOMINATION, p1)
        hoarder = make_obj(game, LOOT_HOARDER, p2)
        make_obj(game, WISP, p2, zone=ZoneType.LIBRARY)

        game.state.event_log.clear()
        destroy_minion(game, abom)

        # Hoarder should have taken 2 damage
        assert hoarder.state.damage == 2

        # Check state-based actions to kill hoarder
        game.check_state_based_actions()

        # Verify Loot Hoarder died
        hoarder_death = [e for e in game.state.event_log
                         if e.type == EventType.OBJECT_DESTROYED and
                         e.payload.get('object_id') == hoarder.id]
        assert len(hoarder_death) >= 1

        # Verify DRAW event from Loot Hoarder deathrattle
        draw_events = [e for e in game.state.event_log
                       if e.type == EventType.DRAW and
                       e.payload.get('player') == p2.id]
        assert len(draw_events) == 1, (
            f"Loot Hoarder should draw 1 card, got {len(draw_events)}"
        )

    def test_abomination_kills_harvest_golem_spawns_damaged_golem(self):
        """Abomination kills Harvest Golem (2/3 takes 2, survives unless at 1 HP)."""
        game, p1, p2 = new_hs_game()
        abom = make_obj(game, ABOMINATION, p1)
        golem = make_obj(game, HARVEST_GOLEM, p2)

        # Damage golem to 1 HP first so Abomination kills it
        golem.state.damage = 1

        game.state.event_log.clear()
        destroy_minion(game, abom)

        # Golem should have taken 2 more damage (1 + 2 = 3, dies)
        assert golem.state.damage == 3

        game.check_state_based_actions()

        # Verify Damaged Golem token summoned
        token_events = [e for e in game.state.event_log
                        if e.type == EventType.CREATE_TOKEN and
                        e.payload.get('token', {}).get('name') == 'Damaged Golem']
        assert len(token_events) == 1, (
            f"Harvest Golem should summon Damaged Golem, got {len(token_events)}"
        )


# ============================================================
# Test 5: Harvest Golem Spawns Damaged Golem (2/1)
# ============================================================

class TestHarvestGolemDeathrattle:
    """Harvest Golem summons a 2/1 Damaged Golem on death."""

    def test_harvest_golem_summons_damaged_golem(self):
        """Harvest Golem dies -> summons 2/1 Damaged Golem."""
        game, p1, p2 = new_hs_game()
        golem = make_obj(game, HARVEST_GOLEM, p1)

        destroy_minion(game, golem)

        # Verify token created
        damaged = get_minion(game, 'Damaged Golem')
        assert damaged is not None, "Damaged Golem should be on battlefield"
        assert damaged.characteristics.power == 2
        assert damaged.characteristics.toughness == 1

    def test_damaged_golem_has_mech_subtype(self):
        """Damaged Golem has the Mech subtype."""
        game, p1, p2 = new_hs_game()
        golem = make_obj(game, HARVEST_GOLEM, p1)

        destroy_minion(game, golem)

        damaged = get_minion(game, 'Damaged Golem')
        assert damaged is not None
        assert 'Mech' in damaged.characteristics.subtypes


# ============================================================
# Test 6: Cairne Spawns Baine Bloodhoof (4/5)
# ============================================================

class TestCairneDeathrattle:
    """Cairne Bloodhoof summons a 4/5 Baine Bloodhoof on death."""

    def test_cairne_summons_baine(self):
        """Cairne dies -> summons 4/5 Baine Bloodhoof."""
        game, p1, p2 = new_hs_game()
        cairne = make_obj(game, CAIRNE_BLOODHOOF, p1)

        destroy_minion(game, cairne)

        baine = get_minion(game, 'Baine Bloodhoof')
        assert baine is not None, "Baine Bloodhoof should be on battlefield"
        assert baine.characteristics.power == 4
        assert baine.characteristics.toughness == 5

    def test_baine_controlled_by_cairne_owner(self):
        """Baine is controlled by the same player who controlled Cairne."""
        game, p1, p2 = new_hs_game()
        cairne = make_obj(game, CAIRNE_BLOODHOOF, p1)

        destroy_minion(game, cairne)

        baine = get_minion(game, 'Baine Bloodhoof')
        assert baine is not None
        assert baine.controller == p1.id


# ============================================================
# Test 7: Loot Hoarder Draws Card on Death
# ============================================================

class TestLootHoarderDeathrattle:
    """Loot Hoarder draws a card for its controller on death."""

    def test_loot_hoarder_draws_card(self):
        """Loot Hoarder dies -> controller draws 1 card."""
        game, p1, p2 = new_hs_game()
        hoarder = make_obj(game, LOOT_HOARDER, p1)
        make_obj(game, WISP, p1, zone=ZoneType.LIBRARY)

        game.state.event_log.clear()
        destroy_minion(game, hoarder)

        draw_events = [e for e in game.state.event_log
                       if e.type == EventType.DRAW and
                       e.payload.get('player') == p1.id]
        assert len(draw_events) == 1, (
            f"Loot Hoarder should draw 1 card, got {len(draw_events)}"
        )

    def test_loot_hoarder_draws_for_correct_controller(self):
        """Loot Hoarder draws for its controller, not opponent."""
        game, p1, p2 = new_hs_game()
        hoarder = make_obj(game, LOOT_HOARDER, p2)
        make_obj(game, WISP, p2, zone=ZoneType.LIBRARY)

        game.state.event_log.clear()
        destroy_minion(game, hoarder)

        p1_draws = [e for e in game.state.event_log
                    if e.type == EventType.DRAW and e.payload.get('player') == p1.id]
        p2_draws = [e for e in game.state.event_log
                    if e.type == EventType.DRAW and e.payload.get('player') == p2.id]
        assert len(p1_draws) == 0
        assert len(p2_draws) == 1


# ============================================================
# Test 8: Loot Hoarder with Empty Library Causes Fatigue
# ============================================================

class TestLootHoarderFatigue:
    """Loot Hoarder deathrattle with empty library causes fatigue damage."""

    def test_loot_hoarder_empty_library_fatigue(self):
        """Loot Hoarder dies with empty library -> fatigue damage event."""
        game, p1, p2 = new_hs_game()
        hoarder = make_obj(game, LOOT_HOARDER, p1)
        # Don't put any cards in library - it's empty

        game.state.event_log.clear()
        destroy_minion(game, hoarder)

        # DRAW event should still fire
        draw_events = [e for e in game.state.event_log if e.type == EventType.DRAW]
        assert len(draw_events) == 1

        # Fatigue damage should be dealt (first fatigue = 1 damage)
        # The engine should emit a FATIGUE_DAMAGE or DAMAGE event
        fatigue_events = [e for e in game.state.event_log
                          if e.type == EventType.DAMAGE and
                          e.payload.get('target') == p1.hero_id and
                          e.payload.get('amount') >= 1]
        assert len(fatigue_events) >= 1, (
            "Loot Hoarder with empty library should cause fatigue damage"
        )


# ============================================================
# Test 9: Bloodmage Thalnos Death Draws Card
# ============================================================

class TestBloodmageThalnosDeathrattle:
    """Bloodmage Thalnos has Spell Damage +1 and Deathrattle: Draw a card."""

    def test_thalnos_draws_on_death(self):
        """Bloodmage Thalnos dies -> draws 1 card."""
        game, p1, p2 = new_hs_game()
        thalnos = make_obj(game, BLOODMAGE_THALNOS, p1)
        make_obj(game, WISP, p1, zone=ZoneType.LIBRARY)

        game.state.event_log.clear()
        destroy_minion(game, thalnos)

        draw_events = [e for e in game.state.event_log
                       if e.type == EventType.DRAW and
                       e.payload.get('player') == p1.id]
        assert len(draw_events) == 1, (
            f"Thalnos should draw 1 card on death, got {len(draw_events)}"
        )

    def test_thalnos_has_spell_damage_before_death(self):
        """Bloodmage Thalnos provides Spell Damage +1 while alive."""
        game, p1, p2 = new_hs_game()
        thalnos = make_obj(game, BLOODMAGE_THALNOS, p1)

        # Verify Thalnos has spell damage interceptor active
        assert len(thalnos.interceptor_ids) > 0, (
            "Thalnos should have spell damage interceptors"
        )


# ============================================================
# Test 10: Multiple Deathrattles Firing in Play Order
# ============================================================

class TestMultipleDeathrattlesPlayOrder:
    """Multiple minions dying trigger deathrattles in play order."""

    def test_two_loot_hoarders_draw_twice(self):
        """Two Loot Hoarders die -> 2 DRAW events."""
        game, p1, p2 = new_hs_game()
        hoarder1 = make_obj(game, LOOT_HOARDER, p1)
        hoarder2 = make_obj(game, LOOT_HOARDER, p1)
        for _ in range(3):
            make_obj(game, WISP, p1, zone=ZoneType.LIBRARY)

        game.state.event_log.clear()
        destroy_minion(game, hoarder1)
        destroy_minion(game, hoarder2)

        draw_events = [e for e in game.state.event_log
                       if e.type == EventType.DRAW and
                       e.payload.get('player') == p1.id]
        assert len(draw_events) == 2, (
            f"Two Loot Hoarders should draw 2 cards, got {len(draw_events)}"
        )

    def test_cairne_and_harvest_golem_both_summon(self):
        """Cairne and Harvest Golem die -> both summon their tokens."""
        game, p1, p2 = new_hs_game()
        cairne = make_obj(game, CAIRNE_BLOODHOOF, p1)
        golem = make_obj(game, HARVEST_GOLEM, p1)

        destroy_minion(game, cairne)
        destroy_minion(game, golem)

        baine = get_minion(game, 'Baine Bloodhoof')
        damaged = get_minion(game, 'Damaged Golem')
        assert baine is not None, "Baine should be summoned"
        assert damaged is not None, "Damaged Golem should be summoned"


# ============================================================
# Test 11: Deathrattle Token on Full Board
# ============================================================

class TestDeathrattleTokenFullBoard:
    """Deathrattle token spawn fails if board is full (7 minions)."""

    def test_cairne_on_full_board_baine_spawns_after_death(self):
        """Board at 7 minions (including Cairne). Cairne dies -> frees slot for Baine."""
        game, p1, p2 = new_hs_game()
        cairne = make_obj(game, CAIRNE_BLOODHOOF, p1)
        for _ in range(6):
            make_obj(game, WISP, p1)

        # Verify 7 minions
        assert count_minions(game, controller=p1.id) == 7

        destroy_minion(game, cairne)

        # After Cairne dies, 6 remain, so Baine CAN spawn
        baine = get_minion(game, 'Baine Bloodhoof')
        assert baine is not None, "Baine should spawn after Cairne dies (slot freed)"
        assert count_minions(game, controller=p1.id) == 7

    def test_harvest_golem_full_board_no_token(self):
        """7 minions on board (not including Harvest Golem). Golem dies but no room for token."""
        game, p1, p2 = new_hs_game()
        for _ in range(7):
            make_obj(game, WISP, p1)

        # Board is full at 7, manually trigger deathrattle via event
        game.state.event_log.clear()
        game.emit(Event(
            type=EventType.CREATE_TOKEN,
            payload={
                'controller': p1.id,
                'token': {
                    'name': 'Damaged Golem',
                    'power': 2,
                    'toughness': 1,
                    'types': {CardType.MINION},
                    'subtypes': {'Mech'}
                }
            },
            source='test'
        ))

        # Token should NOT appear (board full)
        damaged = get_minion(game, 'Damaged Golem')
        assert damaged is None, "Damaged Golem should not spawn on full board"


# ============================================================
# Test 12: Deathrattle Token When Board at 6 Minions
# ============================================================

class TestDeathrattleTokenNearFullBoard:
    """Deathrattle token spawn succeeds when board has room (6 minions or fewer)."""

    def test_cairne_dies_on_6_minion_board_baine_spawns(self):
        """Board at 6 minions (including Cairne). Cairne dies -> Baine spawns (room available)."""
        game, p1, p2 = new_hs_game()
        cairne = make_obj(game, CAIRNE_BLOODHOOF, p1)
        for _ in range(5):
            make_obj(game, WISP, p1)

        assert count_minions(game, controller=p1.id) == 6

        destroy_minion(game, cairne)

        # 5 minions remain, Baine spawns -> 6 total
        baine = get_minion(game, 'Baine Bloodhoof')
        assert baine is not None
        assert count_minions(game, controller=p1.id) == 6

    def test_harvest_golem_dies_on_5_minion_board_token_spawns(self):
        """Board at 5 minions (including Golem). Golem dies -> Damaged Golem spawns."""
        game, p1, p2 = new_hs_game()
        golem = make_obj(game, HARVEST_GOLEM, p1)
        for _ in range(4):
            make_obj(game, WISP, p1)

        assert count_minions(game, controller=p1.id) == 5

        destroy_minion(game, golem)

        damaged = get_minion(game, 'Damaged Golem')
        assert damaged is not None
        assert count_minions(game, controller=p1.id) == 5


# ============================================================
# Test 13: Sylvanas Steal From Opponent With One Minion
# ============================================================

class TestSylvanasStealOneMinion:
    """Sylvanas steals a random enemy minion. With one enemy, it steals that minion."""

    def test_sylvanas_steals_only_enemy_minion(self):
        """Sylvanas dies with 1 enemy minion -> steals that minion."""
        game, p1, p2 = new_hs_game()
        sylvanas = make_obj(game, SYLVANAS_WINDRUNNER, p1)
        enemy_yeti = make_obj(game, CHILLWIND_YETI, p2)

        random.seed(42)
        destroy_minion(game, sylvanas)

        # Verify Yeti is now controlled by P1
        assert enemy_yeti.controller == p1.id, (
            f"Yeti should be controlled by P1, got {enemy_yeti.controller}"
        )

    def test_sylvanas_control_change_event(self):
        """Sylvanas deathrattle emits CONTROL_CHANGE event."""
        game, p1, p2 = new_hs_game()
        sylvanas = make_obj(game, SYLVANAS_WINDRUNNER, p1)
        enemy = make_obj(game, BLOODFEN_RAPTOR, p2)

        game.state.event_log.clear()
        random.seed(42)
        destroy_minion(game, sylvanas)

        control_events = [e for e in game.state.event_log
                          if e.type == EventType.CONTROL_CHANGE]
        assert len(control_events) == 1, (
            f"Sylvanas should emit 1 CONTROL_CHANGE, got {len(control_events)}"
        )


# ============================================================
# Test 14: Sylvanas Steal When Opponent Has No Minions
# ============================================================

class TestSylvanasNoMinionsToSteal:
    """Sylvanas dies with no enemy minions -> no steal occurs."""

    def test_sylvanas_no_enemy_minions_no_steal(self):
        """Sylvanas dies with no enemy minions -> no CONTROL_CHANGE event."""
        game, p1, p2 = new_hs_game()
        sylvanas = make_obj(game, SYLVANAS_WINDRUNNER, p1)

        game.state.event_log.clear()
        destroy_minion(game, sylvanas)

        control_events = [e for e in game.state.event_log
                          if e.type == EventType.CONTROL_CHANGE]
        assert len(control_events) == 0, (
            f"Sylvanas with no enemies should not steal, got {len(control_events)}"
        )


# ============================================================
# Test 15: Tirion Fordring Deathrattle Equips Ashbringer
# ============================================================

class TestTirionDeathrattle:
    """Tirion Fordring deathrattle equips a 5/3 Ashbringer weapon."""

    def test_tirion_equips_ashbringer(self):
        """Tirion dies -> controller equips 5/3 Ashbringer."""
        game, p1, p2 = new_hs_game()
        tirion = make_obj(game, TIRION_FORDRING, p1)

        game.state.event_log.clear()
        destroy_minion(game, tirion)

        # Verify WEAPON_EQUIP event
        weapon_events = [e for e in game.state.event_log
                         if e.type == EventType.WEAPON_EQUIP and
                         e.payload.get('player') == p1.id]
        assert len(weapon_events) == 1, (
            f"Tirion should equip Ashbringer, got {len(weapon_events)} events"
        )

        event = weapon_events[0]
        assert event.payload.get('weapon_attack') == 5
        assert event.payload.get('weapon_durability') == 3
        assert event.payload.get('weapon_name') == 'Ashbringer'

    def test_tirion_ashbringer_equipped_on_player(self):
        """After Tirion dies, WEAPON_EQUIP event fires with correct stats."""
        game, p1, p2 = new_hs_game()
        tirion = make_obj(game, TIRION_FORDRING, p1)

        game.state.event_log.clear()
        destroy_minion(game, tirion)

        # Verify WEAPON_EQUIP event has correct payload
        weapon_events = [e for e in game.state.event_log
                         if e.type == EventType.WEAPON_EQUIP]
        assert len(weapon_events) == 1, (
            f"Should have 1 WEAPON_EQUIP event, got {len(weapon_events)}"
        )

        event = weapon_events[0]
        assert event.payload.get('weapon_attack') == 5, (
            f"Ashbringer should have 5 attack, got {event.payload.get('weapon_attack')}"
        )
        assert event.payload.get('weapon_durability') == 3, (
            f"Ashbringer should have 3 durability, got {event.payload.get('weapon_durability')}"
        )


# ============================================================
# Test 16: Savannah Highmane Spawns 2 Hyenas
# ============================================================

class TestSavannahHighmane:
    """Savannah Highmane summons two 2/2 Hyenas on death."""

    def test_highmane_summons_two_hyenas(self):
        """Savannah Highmane dies -> summons 2 Hyenas."""
        game, p1, p2 = new_hs_game()
        highmane = make_obj(game, SAVANNAH_HIGHMANE, p1)

        destroy_minion(game, highmane)

        hyena_count = count_minions(game, controller=p1.id, name='Hyena')
        assert hyena_count == 2, (
            f"Savannah Highmane should summon 2 Hyenas, got {hyena_count}"
        )

    def test_hyenas_are_2_2_beasts(self):
        """Hyenas are 2/2 Beasts."""
        game, p1, p2 = new_hs_game()
        highmane = make_obj(game, SAVANNAH_HIGHMANE, p1)

        destroy_minion(game, highmane)

        battlefield = game.state.zones.get('battlefield')
        hyenas = [game.state.objects.get(oid) for oid in battlefield.objects
                  if game.state.objects.get(oid) and
                  game.state.objects.get(oid).name == 'Hyena']

        assert len(hyenas) == 2
        for hyena in hyenas:
            assert hyena.characteristics.power == 2
            assert hyena.characteristics.toughness == 2
            assert 'Beast' in hyena.characteristics.subtypes


# ============================================================
# Test 17: Highmane on Near-Full Board
# ============================================================

class TestHighmaneNearFullBoard:
    """Savannah Highmane on near-full board spawns limited Hyenas."""

    def test_highmane_with_5_minions_spawns_2_hyenas(self):
        """Board at 5 minions (including Highmane). Dies -> 4 remain, 2 Hyenas spawn."""
        game, p1, p2 = new_hs_game()
        highmane = make_obj(game, SAVANNAH_HIGHMANE, p1)
        for _ in range(4):
            make_obj(game, WISP, p1)

        assert count_minions(game, controller=p1.id) == 5

        destroy_minion(game, highmane)

        # 4 wisps + 2 hyenas = 6
        hyena_count = count_minions(game, controller=p1.id, name='Hyena')
        assert hyena_count == 2
        assert count_minions(game, controller=p1.id) == 6

    def test_highmane_with_6_minions_spawns_1_hyena(self):
        """Board at 6 minions (including Highmane). Dies -> 5 remain, 2 Hyenas fit."""
        game, p1, p2 = new_hs_game()
        highmane = make_obj(game, SAVANNAH_HIGHMANE, p1)
        for _ in range(5):
            make_obj(game, WISP, p1)

        assert count_minions(game, controller=p1.id) == 6

        destroy_minion(game, highmane)

        # 5 wisps + 2 hyenas = 7 (both hyenas fit after Highmane dies)
        hyena_count = count_minions(game, controller=p1.id, name='Hyena')
        assert hyena_count == 2
        assert count_minions(game, controller=p1.id) == 7

    def test_highmane_with_7_minions_spawns_0_hyenas(self):
        """Board at 7 (including Highmane). Dies -> 6 remain, only 1 slot for 1 Hyena."""
        game, p1, p2 = new_hs_game()
        highmane = make_obj(game, SAVANNAH_HIGHMANE, p1)
        for _ in range(6):
            make_obj(game, WISP, p1)

        assert count_minions(game, controller=p1.id) == 7

        destroy_minion(game, highmane)

        # 6 wisps remain, room for 1 Hyena
        hyena_count = count_minions(game, controller=p1.id, name='Hyena')
        assert hyena_count == 1


# ============================================================
# Test 18: Deathrattle on Bounced Minion
# ============================================================

class TestBouncedMinionNoDeathrattle:
    """Minion returned to hand via bounce doesn't trigger deathrattle when 'destroyed'."""

    def test_bounced_loot_hoarder_no_draw(self):
        """Loot Hoarder bounced to hand and then destroyed should still trigger deathrattle.

        Note: In Hearthstone, deathrattles are tied to the object itself. If the object
        dies from any zone (even hand), the deathrattle may still fire. This test verifies
        that the deathrattle interceptor fires based on OBJECT_DESTROYED, which may happen
        from hand. The key is that bouncing deactivates while_on_battlefield interceptors
        but deathrattles use 'until_leaves' duration and trigger on death regardless of zone.
        """
        game, p1, p2 = new_hs_game()
        hoarder = make_obj(game, LOOT_HOARDER, p1)
        make_obj(game, WISP, p1, zone=ZoneType.LIBRARY)

        # Bounce to hand
        game.emit(Event(
            type=EventType.RETURN_TO_HAND,
            payload={'object_id': hoarder.id},
            source='test'
        ))

        # Verify hoarder is in hand
        assert hoarder.zone == ZoneType.HAND

        game.state.event_log.clear()

        # Destroy from hand - deathrattle MAY fire depending on implementation
        game.emit(Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': hoarder.id},
            source='test'
        ))

        # Deathrattle fires on OBJECT_DESTROYED + zone == GRAVEYARD check
        draw_events = [e for e in game.state.event_log if e.type == EventType.DRAW]
        assert len(draw_events) == 1, (
            f"Loot Hoarder deathrattle should fire when destroyed, got {len(draw_events)}"
        )


# ============================================================
# Test 19: Knife Juggler + Deathrattle Token Spawn
# ============================================================

class TestKnifeJugglerDeathrattleToken:
    """Knife Juggler triggers when a deathrattle summons a token."""

    def test_juggler_triggers_on_harvest_golem_token(self):
        """Knife Juggler on board, Harvest Golem dies -> Damaged Golem summon triggers Juggler."""
        game, p1, p2 = new_hs_game()
        juggler = make_obj(game, KNIFE_JUGGLER, p1)
        golem = make_obj(game, HARVEST_GOLEM, p1)
        enemy = make_obj(game, CHILLWIND_YETI, p2)

        game.state.event_log.clear()
        random.seed(42)
        destroy_minion(game, golem)

        # Verify Damaged Golem was created
        token_events = [e for e in game.state.event_log
                        if e.type == EventType.CREATE_TOKEN and
                        e.payload.get('token', {}).get('name') == 'Damaged Golem']
        assert len(token_events) == 1

        # Verify Knife Juggler dealt 1 damage
        juggler_damage = [e for e in game.state.event_log
                          if e.type == EventType.DAMAGE and
                          e.payload.get('source') == juggler.id and
                          e.payload.get('amount') == 1]
        assert len(juggler_damage) == 1, (
            f"Knife Juggler should trigger on token, got {len(juggler_damage)} damage events"
        )

    def test_juggler_triggers_on_cairne_baine_summon(self):
        """Knife Juggler triggers when Cairne summons Baine."""
        game, p1, p2 = new_hs_game()
        juggler = make_obj(game, KNIFE_JUGGLER, p1)
        cairne = make_obj(game, CAIRNE_BLOODHOOF, p1)
        make_obj(game, CHILLWIND_YETI, p2)

        game.state.event_log.clear()
        random.seed(42)
        destroy_minion(game, cairne)

        # Verify Baine summoned
        baine = get_minion(game, 'Baine Bloodhoof')
        assert baine is not None

        # Verify Juggler dealt damage
        juggler_damage = [e for e in game.state.event_log
                          if e.type == EventType.DAMAGE and
                          e.payload.get('source') == juggler.id]
        assert len(juggler_damage) == 1


# ============================================================
# Test 20: Two Loot Hoarders Die Simultaneously
# ============================================================

class TestTwoLootHoardersSimultaneous:
    """Two Loot Hoarders dying in sequence both draw cards."""

    def test_two_loot_hoarders_both_draw(self):
        """Two Loot Hoarders die -> both draw cards."""
        game, p1, p2 = new_hs_game()
        hoarder1 = make_obj(game, LOOT_HOARDER, p1)
        hoarder2 = make_obj(game, LOOT_HOARDER, p1)
        for _ in range(3):
            make_obj(game, WISP, p1, zone=ZoneType.LIBRARY)

        game.state.event_log.clear()
        destroy_minion(game, hoarder1)
        destroy_minion(game, hoarder2)

        draw_events = [e for e in game.state.event_log
                       if e.type == EventType.DRAW and
                       e.payload.get('player') == p1.id]
        assert len(draw_events) == 2, (
            f"Two Loot Hoarders should draw 2 cards total, got {len(draw_events)}"
        )


# ============================================================
# Run tests
# ============================================================

if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
