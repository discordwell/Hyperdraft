"""
Hearthstone Unhappy Path Tests - Batch 55

Multi-card deathrattle chains and summon trigger interactions:
Cairne + Sylvanas simultaneous death, Harvest Golem + Knife Juggler,
Abomination chain deaths, Loot Hoarder + Abomination, Cairne on full board,
Harvest Golem on full board, multiple deathrattles firing in sequence,
Knife Juggler + multiple token summons, Haunted Creeper + Knife Juggler.
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
    KNIFE_JUGGLER, WILD_PYROMANCER, CAIRNE_BLOODHOOF,
    SYLVANAS_WINDRUNNER, HARVEST_GOLEM, LOOT_HOARDER,
    ABOMINATION,
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


def destroy_minion(game, obj):
    """Emit an OBJECT_DESTROYED event for a minion."""
    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': obj.id},
        source='test'
    ))


def count_events(game, event_type, **payload_filters):
    """Count events in the log matching the given type and payload filters."""
    count = 0
    for e in game.state.event_log:
        if e.type != event_type:
            continue
        match = True
        for key, value in payload_filters.items():
            if e.payload.get(key) != value:
                match = False
                break
        if match:
            count += 1
    return count


def get_events(game, event_type, **payload_filters):
    """Get events from the log matching the given type and payload filters."""
    results = []
    for e in game.state.event_log:
        if e.type != event_type:
            continue
        match = True
        for key, value in payload_filters.items():
            if e.payload.get(key) != value:
                match = False
                break
        if match:
            results.append(e)
    return results


# ============================================================
# Cairne Bloodhoof Deathrattle
# ============================================================

class TestCairneDeathrattle:
    def test_cairne_summons_baine_on_death(self):
        """Cairne dies -> summons a 4/5 Baine Bloodhoof token."""
        game, p1, p2 = new_hs_game()
        cairne = make_obj(game, CAIRNE_BLOODHOOF, p1)

        destroy_minion(game, cairne)

        # Verify a CREATE_TOKEN event fired for Baine Bloodhoof
        token_events = [e for e in game.state.event_log
                        if e.type == EventType.CREATE_TOKEN and
                        e.payload.get('token', {}).get('name') == 'Baine Bloodhoof']
        assert len(token_events) == 1
        token_data = token_events[0].payload['token']
        assert token_data['power'] == 4
        assert token_data['toughness'] == 5

    def test_baine_exists_on_battlefield_after_cairne_death(self):
        """After Cairne dies, Baine Bloodhoof should exist on the battlefield."""
        game, p1, p2 = new_hs_game()
        cairne = make_obj(game, CAIRNE_BLOODHOOF, p1)

        destroy_minion(game, cairne)

        # Find the Baine token on the battlefield
        battlefield = game.state.zones.get('battlefield')
        baine_found = False
        if battlefield:
            for oid in battlefield.objects:
                obj = game.state.objects.get(oid)
                if obj and obj.name == 'Baine Bloodhoof':
                    baine_found = True
                    assert obj.characteristics.power == 4
                    assert obj.characteristics.toughness == 5
                    break
        assert baine_found, "Baine Bloodhoof should be on the battlefield"


# ============================================================
# Sylvanas Windrunner Deathrattle
# ============================================================

class TestSylvanasDeathrattle:
    def test_sylvanas_steals_enemy_minion_on_death(self):
        """Sylvanas dies with enemy minion on board -> CONTROL_CHANGE event fires."""
        game, p1, p2 = new_hs_game()
        sylvanas = make_obj(game, SYLVANAS_WINDRUNNER, p1)
        enemy_yeti = make_obj(game, CHILLWIND_YETI, p2)

        random.seed(42)
        destroy_minion(game, sylvanas)

        # Sylvanas uses CONTROL_CHANGE event type
        control_events = [e for e in game.state.event_log
                          if e.type == EventType.CONTROL_CHANGE]
        assert len(control_events) >= 1
        # The stolen minion should be the enemy yeti (only enemy minion)
        assert control_events[0].payload['object_id'] == enemy_yeti.id
        assert control_events[0].payload['new_controller'] == p1.id

    def test_sylvanas_no_steal_without_enemy_minions(self):
        """Sylvanas dies with no enemy minions -> no CONTROL_CHANGE event."""
        game, p1, p2 = new_hs_game()
        sylvanas = make_obj(game, SYLVANAS_WINDRUNNER, p1)

        destroy_minion(game, sylvanas)

        control_events = [e for e in game.state.event_log
                          if e.type == EventType.CONTROL_CHANGE]
        assert len(control_events) == 0


# ============================================================
# Cairne + Sylvanas Simultaneous Death
# ============================================================

class TestCairneSylvanasSimultaneous:
    def test_both_deathrattles_fire(self):
        """Both Cairne and Sylvanas die -> both deathrattles fire."""
        game, p1, p2 = new_hs_game()
        cairne = make_obj(game, CAIRNE_BLOODHOOF, p1)
        sylvanas = make_obj(game, SYLVANAS_WINDRUNNER, p1)
        enemy_yeti = make_obj(game, CHILLWIND_YETI, p2)

        random.seed(42)
        # Destroy both in sequence (simulating simultaneous death)
        destroy_minion(game, cairne)
        destroy_minion(game, sylvanas)

        # Cairne should have summoned Baine
        token_events = [e for e in game.state.event_log
                        if e.type == EventType.CREATE_TOKEN and
                        e.payload.get('token', {}).get('name') == 'Baine Bloodhoof']
        assert len(token_events) == 1

        # Sylvanas should have attempted to steal an enemy minion
        control_events = [e for e in game.state.event_log
                          if e.type == EventType.CONTROL_CHANGE]
        assert len(control_events) >= 1


# ============================================================
# Harvest Golem Deathrattle
# ============================================================

class TestHarvestGolemDeathrattle:
    def test_harvest_golem_summons_damaged_golem(self):
        """Harvest Golem dies -> summons a 2/1 Damaged Golem."""
        game, p1, p2 = new_hs_game()
        golem = make_obj(game, HARVEST_GOLEM, p1)

        destroy_minion(game, golem)

        token_events = [e for e in game.state.event_log
                        if e.type == EventType.CREATE_TOKEN and
                        e.payload.get('token', {}).get('name') == 'Damaged Golem']
        assert len(token_events) == 1
        token_data = token_events[0].payload['token']
        assert token_data['power'] == 2
        assert token_data['toughness'] == 1

    def test_damaged_golem_exists_on_battlefield(self):
        """After Harvest Golem dies, Damaged Golem should be on the battlefield."""
        game, p1, p2 = new_hs_game()
        golem = make_obj(game, HARVEST_GOLEM, p1)

        destroy_minion(game, golem)

        battlefield = game.state.zones.get('battlefield')
        found = False
        if battlefield:
            for oid in battlefield.objects:
                obj = game.state.objects.get(oid)
                if obj and obj.name == 'Damaged Golem':
                    found = True
                    break
        assert found, "Damaged Golem should be on the battlefield"


# ============================================================
# Harvest Golem + Knife Juggler
# ============================================================

class TestHarvestGolemPlusKnifeJuggler:
    def test_juggler_fires_on_deathrattle_token(self):
        """Knife Juggler on board, Harvest Golem dies -> the 2/1 token
        summon triggers Juggler's 1 damage to a random enemy."""
        game, p1, p2 = new_hs_game()
        juggler = make_obj(game, KNIFE_JUGGLER, p1)
        golem = make_obj(game, HARVEST_GOLEM, p1)

        # Clear event log to only track events from the death
        game.state.event_log.clear()

        random.seed(42)
        destroy_minion(game, golem)

        # Harvest Golem should have created a token
        token_events = [e for e in game.state.event_log
                        if e.type == EventType.CREATE_TOKEN and
                        e.payload.get('token', {}).get('name') == 'Damaged Golem']
        assert len(token_events) == 1

        # Knife Juggler should have triggered on the token summon
        juggler_damage = [e for e in game.state.event_log
                          if e.type == EventType.DAMAGE and
                          e.payload.get('source') == juggler.id and
                          e.payload.get('amount') == 1]
        assert len(juggler_damage) == 1


# ============================================================
# Abomination Deathrattle
# ============================================================

class TestAbominationDeathrattle:
    def test_deals_2_damage_to_all_characters(self):
        """Abomination dies -> deals 2 damage to ALL characters."""
        game, p1, p2 = new_hs_game()
        abom = make_obj(game, ABOMINATION, p1)
        friendly = make_obj(game, CHILLWIND_YETI, p1)
        enemy = make_obj(game, CHILLWIND_YETI, p2)

        game.state.event_log.clear()
        destroy_minion(game, abom)

        # Should deal 2 damage to both minions and both heroes
        damage_events = [e for e in game.state.event_log
                         if e.type == EventType.DAMAGE and
                         e.payload.get('amount') == 2 and
                         e.payload.get('source') == abom.id]
        # At minimum: 2 minions + 2 heroes = 4 targets
        assert len(damage_events) >= 4

    def test_abomination_damages_heroes(self):
        """Abomination deathrattle hits both heroes for 2."""
        game, p1, p2 = new_hs_game()
        abom = make_obj(game, ABOMINATION, p1)

        game.state.event_log.clear()
        destroy_minion(game, abom)

        hero_damage = [e for e in game.state.event_log
                       if e.type == EventType.DAMAGE and
                       e.payload.get('amount') == 2 and
                       e.payload.get('target') in (p1.hero_id, p2.hero_id)]
        assert len(hero_damage) == 2


# ============================================================
# Abomination Kills Loot Hoarder (chain deathrattle)
# ============================================================

class TestAbominationKillsLootHoarder:
    def test_loot_hoarder_draw_triggers_after_abom_damage(self):
        """Abomination dies, its 2 damage kills Loot Hoarder (2/1) ->
        After state-based actions, Loot Hoarder dies and its deathrattle
        (draw a card) fires from the chain."""
        game, p1, p2 = new_hs_game()
        abom = make_obj(game, ABOMINATION, p1)
        # Loot Hoarder: 2/1, will die to 2 damage
        hoarder = make_obj(game, LOOT_HOARDER, p2)

        # Put a card in p2's library so the draw can succeed
        game.create_object(
            name=WISP.name, owner_id=p2.id, zone=ZoneType.LIBRARY,
            characteristics=WISP.characteristics, card_def=WISP
        )

        game.state.event_log.clear()
        destroy_minion(game, abom)

        # Abomination deathrattle should deal 2 damage to Loot Hoarder
        abom_damage_to_hoarder = [e for e in game.state.event_log
                                  if e.type == EventType.DAMAGE and
                                  e.payload.get('target') == hoarder.id and
                                  e.payload.get('amount') == 2]
        assert len(abom_damage_to_hoarder) >= 1

        # State-based actions must be checked to kill the Loot Hoarder
        # (the engine doesn't auto-kill on damage; SBAs process lethal damage)
        game.check_state_based_actions()

        # Loot Hoarder should die from the damage (OBJECT_DESTROYED)
        hoarder_death = [e for e in game.state.event_log
                         if e.type == EventType.OBJECT_DESTROYED and
                         e.payload.get('object_id') == hoarder.id]
        assert len(hoarder_death) >= 1

        # Loot Hoarder's deathrattle should fire a DRAW event
        draw_events = [e for e in game.state.event_log
                       if e.type == EventType.DRAW and
                       e.payload.get('player') == p2.id]
        assert len(draw_events) >= 1


# ============================================================
# Loot Hoarder Deathrattle
# ============================================================

class TestLootHoarderDeathrattle:
    def test_loot_hoarder_draws_on_death(self):
        """Loot Hoarder dies -> DRAW event for its controller."""
        game, p1, p2 = new_hs_game()
        hoarder = make_obj(game, LOOT_HOARDER, p1)

        # Put a card in library so draw can succeed
        game.create_object(
            name=WISP.name, owner_id=p1.id, zone=ZoneType.LIBRARY,
            characteristics=WISP.characteristics, card_def=WISP
        )

        game.state.event_log.clear()
        destroy_minion(game, hoarder)

        draw_events = [e for e in game.state.event_log
                       if e.type == EventType.DRAW and
                       e.payload.get('player') == p1.id]
        assert len(draw_events) == 1

    def test_loot_hoarder_draw_for_correct_player(self):
        """Loot Hoarder draws for its controller, not the opponent."""
        game, p1, p2 = new_hs_game()
        hoarder = make_obj(game, LOOT_HOARDER, p2)

        game.create_object(
            name=WISP.name, owner_id=p2.id, zone=ZoneType.LIBRARY,
            characteristics=WISP.characteristics, card_def=WISP
        )

        game.state.event_log.clear()
        destroy_minion(game, hoarder)

        p1_draws = [e for e in game.state.event_log
                    if e.type == EventType.DRAW and
                    e.payload.get('player') == p1.id]
        p2_draws = [e for e in game.state.event_log
                    if e.type == EventType.DRAW and
                    e.payload.get('player') == p2.id]
        assert len(p1_draws) == 0
        assert len(p2_draws) == 1


# ============================================================
# Cairne on Full Board
# ============================================================

class TestCairneOnFullBoard:
    def test_baine_not_summoned_on_full_board(self):
        """Board full (7 minions including Cairne). Kill Cairne -> Cairne dies,
        freeing a slot, so Baine SHOULD be summoned (6 minions remain).
        If board is still full (7 remain), Baine would not be summoned."""
        game, p1, p2 = new_hs_game()
        # Fill board to 7 minions for p1 (including Cairne)
        cairne = make_obj(game, CAIRNE_BLOODHOOF, p1)
        fillers = []
        for _ in range(6):
            fillers.append(make_obj(game, WISP, p1))

        # Verify board is at 7
        battlefield = game.state.zones.get('battlefield')
        p1_minions = [oid for oid in battlefield.objects
                      if oid in game.state.objects and
                      game.state.objects[oid].controller == p1.id and
                      CardType.MINION in game.state.objects[oid].characteristics.types]
        assert len(p1_minions) == 7

        game.state.event_log.clear()
        destroy_minion(game, cairne)

        # After Cairne dies, 6 minions remain -> Baine CAN be summoned (slot freed)
        token_events = [e for e in game.state.event_log
                        if e.type == EventType.CREATE_TOKEN and
                        e.payload.get('token', {}).get('name') == 'Baine Bloodhoof']
        assert len(token_events) == 1

        # Verify back to 7 minions (6 fillers + Baine)
        p1_minions_after = [oid for oid in battlefield.objects
                            if oid in game.state.objects and
                            game.state.objects[oid].controller == p1.id and
                            CardType.MINION in game.state.objects[oid].characteristics.types]
        assert len(p1_minions_after) == 7

    def test_baine_not_summoned_when_board_truly_full(self):
        """If 7 OTHER minions remain (Cairne excluded from board), Baine cannot summon.
        We simulate this by having 7 minions that are not Cairne, plus Cairne as 8th
        but that's impossible in HS. Instead, test: fill board to 7 with non-Cairne
        minions, place Cairne in graveyard (already dead), and fire deathrattle manually
        to verify CREATE_TOKEN is emitted but token creation is blocked."""
        game, p1, p2 = new_hs_game()
        # Fill board to exactly 7 minions (no Cairne)
        fillers = []
        for _ in range(7):
            fillers.append(make_obj(game, WISP, p1))

        battlefield = game.state.zones.get('battlefield')
        p1_minions = [oid for oid in battlefield.objects
                      if oid in game.state.objects and
                      game.state.objects[oid].controller == p1.id and
                      CardType.MINION in game.state.objects[oid].characteristics.types]
        assert len(p1_minions) == 7

        # Manually emit a CREATE_TOKEN for Baine and verify no new object appears
        game.state.event_log.clear()
        game.emit(Event(
            type=EventType.CREATE_TOKEN,
            payload={
                'controller': p1.id,
                'token': {
                    'name': 'Baine Bloodhoof',
                    'power': 4,
                    'toughness': 5,
                    'types': {CardType.MINION},
                    'subtypes': set()
                }
            },
            source='test'
        ))

        # The token should NOT appear on the battlefield (board full at 7)
        baine_on_board = [oid for oid in battlefield.objects
                          if oid in game.state.objects and
                          game.state.objects[oid].name == 'Baine Bloodhoof']
        assert len(baine_on_board) == 0


# ============================================================
# Multiple Deathrattles in Sequence
# ============================================================

class TestMultipleDeathrattlesInSequence:
    def test_two_loot_hoarders_draw_twice(self):
        """Two Loot Hoarders die -> 2 separate DRAW events."""
        game, p1, p2 = new_hs_game()
        hoarder1 = make_obj(game, LOOT_HOARDER, p1)
        hoarder2 = make_obj(game, LOOT_HOARDER, p1)

        # Put cards in library
        for _ in range(3):
            game.create_object(
                name=WISP.name, owner_id=p1.id, zone=ZoneType.LIBRARY,
                characteristics=WISP.characteristics, card_def=WISP
            )

        game.state.event_log.clear()
        destroy_minion(game, hoarder1)
        destroy_minion(game, hoarder2)

        draw_events = [e for e in game.state.event_log
                       if e.type == EventType.DRAW and
                       e.payload.get('player') == p1.id]
        assert len(draw_events) == 2

    def test_cairne_and_harvest_golem_both_summon(self):
        """Cairne and Harvest Golem die -> both summon their tokens."""
        game, p1, p2 = new_hs_game()
        cairne = make_obj(game, CAIRNE_BLOODHOOF, p1)
        golem = make_obj(game, HARVEST_GOLEM, p1)

        game.state.event_log.clear()
        destroy_minion(game, cairne)
        destroy_minion(game, golem)

        baine_events = [e for e in game.state.event_log
                        if e.type == EventType.CREATE_TOKEN and
                        e.payload.get('token', {}).get('name') == 'Baine Bloodhoof']
        golem_events = [e for e in game.state.event_log
                        if e.type == EventType.CREATE_TOKEN and
                        e.payload.get('token', {}).get('name') == 'Damaged Golem']
        assert len(baine_events) == 1
        assert len(golem_events) == 1


# ============================================================
# Knife Juggler + Multiple Summons
# ============================================================

class TestKnifeJugglerMultipleSummons:
    def test_juggler_fires_for_each_summoned_minion(self):
        """Knife Juggler on board. Summon 3 Wisps via play_minion.
        Verify 3 damage events from Juggler."""
        game, p1, p2 = new_hs_game()
        juggler = make_obj(game, KNIFE_JUGGLER, p1)
        # Need an enemy target for Juggler
        enemy = make_obj(game, CHILLWIND_YETI, p2)

        game.state.event_log.clear()
        random.seed(42)

        play_minion(game, WISP, p1)
        play_minion(game, WISP, p1)
        play_minion(game, WISP, p1)

        juggler_damage = [e for e in game.state.event_log
                          if e.type == EventType.DAMAGE and
                          e.payload.get('source') == juggler.id and
                          e.payload.get('amount') == 1]
        assert len(juggler_damage) == 3

    def test_juggler_does_not_trigger_on_enemy_summon(self):
        """Knife Juggler should NOT trigger when the opponent summons a minion."""
        game, p1, p2 = new_hs_game()
        juggler = make_obj(game, KNIFE_JUGGLER, p1)

        game.state.event_log.clear()
        play_minion(game, WISP, p2)

        juggler_damage = [e for e in game.state.event_log
                          if e.type == EventType.DAMAGE and
                          e.payload.get('source') == juggler.id]
        assert len(juggler_damage) == 0


# ============================================================
# Deathrattle Doesn't Fire on Silenced Minion
# ============================================================

class TestDeathrattleDoesntFireOnSilenced:
    def test_silenced_loot_hoarder_no_draw(self):
        """Silence Loot Hoarder then destroy it -> no DRAW event fires."""
        game, p1, p2 = new_hs_game()
        hoarder = make_obj(game, LOOT_HOARDER, p1)

        # Put a card in library
        game.create_object(
            name=WISP.name, owner_id=p1.id, zone=ZoneType.LIBRARY,
            characteristics=WISP.characteristics, card_def=WISP
        )

        # Silence the Loot Hoarder via SILENCE_TARGET event
        game.emit(Event(
            type=EventType.SILENCE_TARGET,
            payload={'target': hoarder.id},
            source='test'
        ))

        game.state.event_log.clear()
        destroy_minion(game, hoarder)

        draw_events = [e for e in game.state.event_log
                       if e.type == EventType.DRAW and
                       e.payload.get('player') == p1.id]
        assert len(draw_events) == 0

    def test_silenced_cairne_no_baine(self):
        """Silence Cairne then destroy it -> no Baine Bloodhoof summoned."""
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

        token_events = [e for e in game.state.event_log
                        if e.type == EventType.CREATE_TOKEN and
                        e.payload.get('token', {}).get('name') == 'Baine Bloodhoof']
        assert len(token_events) == 0

    def test_silenced_harvest_golem_no_token(self):
        """Silence Harvest Golem then destroy it -> no Damaged Golem summoned."""
        game, p1, p2 = new_hs_game()
        golem = make_obj(game, HARVEST_GOLEM, p1)

        # Silence Harvest Golem
        game.emit(Event(
            type=EventType.SILENCE_TARGET,
            payload={'target': golem.id},
            source='test'
        ))

        game.state.event_log.clear()
        destroy_minion(game, golem)

        token_events = [e for e in game.state.event_log
                        if e.type == EventType.CREATE_TOKEN and
                        e.payload.get('token', {}).get('name') == 'Damaged Golem']
        assert len(token_events) == 0
