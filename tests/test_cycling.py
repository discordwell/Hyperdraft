"""Cycling (W8): plain / landcycling / typecycling / rider triggers.

Tests cover:
- Plain cycling: pay cost, card moves HAND -> GY, controller draws 1.
- Landcycling: card moves HAND -> GY, library search opens for the named
  land subtype, hand gets the chosen Mountain, library shuffles.
- Typecycling: same as landcycling but for an arbitrary subtype.
- Rider trigger: cycling triggers a "When you cycle this card, ..." effect.
- Cannot cycle from battlefield/graveyard (only from hand).
- CYCLE / CYCLING_TRIGGERED marker events fire correctly.
- Per-card test for each Foundations cycling card.
- ActionType.CYCLE_CARD relabelling on the legal-actions surface.

Run as: ``python tests/test_cycling.py``
"""
import os
import sys
import asyncio

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_HERE)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color, CardDefinition,
    Characteristics, make_creature,
)
from src.cards.interceptor_helpers import make_cycling_ability, make_cycling_setup
from src.engine.cycling import _handle_cycle_action
from src.engine.priority import ActionType, PlayerAction
from src.engine.turn import Phase
from src.engine.mana import ManaType


def _put_in_hand(game, player, card_def):
    return game.create_object(
        name=card_def.name,
        owner_id=player.id,
        zone=ZoneType.HAND,
        characteristics=card_def.characteristics,
        card_def=card_def,
    )


def _put_in_library(game, player, card_def):
    obj = game.create_object(
        name=card_def.name,
        owner_id=player.id,
        zone=ZoneType.LIBRARY,
        characteristics=card_def.characteristics,
        card_def=card_def,
    )
    return obj


def _basic_land_def(name: str, subtype: str) -> CardDefinition:
    """Build a stand-in basic land card_def for landcycling tests."""
    chars = Characteristics(
        types={CardType.LAND},
        subtypes={subtype},
        supertypes={"Basic"},
        colors=set(),
        mana_cost=None,
    )
    return CardDefinition(
        name=name, mana_cost=None, characteristics=chars, text=f"({subtype})",
    )


def _give_player_mana(player, mana_system, generic=0, white=0, blue=0, black=0,
                      red=0, green=0):
    for _ in range(generic):
        mana_system.produce_mana(player.id, ManaType.COLORLESS, 1)
    for _ in range(red):
        mana_system.produce_mana(player.id, ManaType.RED, 1)
    for _ in range(green):
        mana_system.produce_mana(player.id, ManaType.GREEN, 1)
    for _ in range(white):
        mana_system.produce_mana(player.id, ManaType.WHITE, 1)
    for _ in range(blue):
        mana_system.produce_mana(player.id, ManaType.BLUE, 1)
    for _ in range(black):
        mana_system.produce_mana(player.id, ManaType.BLACK, 1)


# ---------------------------------------------------------------------------
# Baseline tests (regression: pre-W8 behaviour preserved)
# ---------------------------------------------------------------------------

def test_cycling_registers_activated_ability_in_hand():
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")

    cycler_def = make_creature(
        name="Cycler", power=3, toughness=3, mana_cost="{4}",
        colors=set(), subtypes={"Beast"},
        text="Cycling {2} ({2}, Discard this card: Draw a card.)",
    )
    cycler_def.setup_in_hand = make_cycling_setup("{2}")

    obj = _put_in_hand(game, p1, cycler_def)
    abilities = getattr(obj.state, "activated_abilities", [])
    assert len(abilities) == 1, f"expected 1 cycling ability, got {len(abilities)}"
    assert abilities[0].cost_text == "{2}, Discard this card"
    assert abilities[0].discard_self
    print("PASS: cycling ability registers via setup_in_hand")


def test_cycling_surfaces_in_legal_actions():
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    game.turn_manager.turn_state.active_player_id = p1.id
    game.turn_manager.turn_state.phase = Phase.PRECOMBAT_MAIN

    cycler_def = make_creature(
        name="Cycler", power=3, toughness=3, mana_cost="{4}",
        colors=set(), subtypes={"Beast"},
        text="Cycling {2} ({2}, Discard this card: Draw a card.)",
    )
    cycler_def.setup_in_hand = make_cycling_setup("{2}")
    obj = _put_in_hand(game, p1, cycler_def)
    _give_player_mana(p1, game.mana_system, generic=2)

    actions = game.priority_system.get_legal_actions(p1.id)
    cycling_actions = [
        a for a in actions
        if a.source_id == obj.id and a.ability_id and a.ability_id.startswith("activated:")
    ]
    assert cycling_actions, f"expected cycling action, got {[a.description for a in actions[:5]]}"
    # W8: cycling actions are re-tagged to ActionType.CYCLE_CARD.
    assert cycling_actions[0].type == ActionType.CYCLE_CARD, (
        f"expected CYCLE_CARD, got {cycling_actions[0].type}"
    )
    assert cycling_actions[0].card_id == obj.id
    print("PASS: cycling surfaces in legal actions (re-tagged to CYCLE_CARD)")


def test_cycling_dispatch_pays_cost_and_draws():
    async def _run():
        game = Game()
        p1 = game.add_player("Alice")
        p2 = game.add_player("Bob")
        game.turn_manager.turn_state.active_player_id = p1.id
        game.turn_manager.turn_state.phase = Phase.PRECOMBAT_MAIN

        # Seed the library with 3 distinct cards so the post-cycle DRAW has
        # something to take from.
        for i in range(3):
            game.create_object(
                name=f"Filler-{i}",
                owner_id=p1.id, zone=ZoneType.LIBRARY,
                characteristics=Characteristics(
                    types={CardType.CREATURE}, mana_cost="{1}",
                ),
            )

        cycler_def = make_creature(
            name="Cycler", power=3, toughness=3, mana_cost="{4}",
            colors=set(), subtypes={"Beast"},
            text="Cycling {2} ({2}, Discard this card: Draw a card.)",
        )
        cycler_def.setup_in_hand = make_cycling_setup("{2}")
        obj = _put_in_hand(game, p1, cycler_def)
        _give_player_mana(p1, game.mana_system, generic=2)

        action = PlayerAction(
            type=ActionType.ACTIVATE_ABILITY,
            player_id=p1.id, source_id=obj.id, ability_id="activated:0",
        )
        events = await game.priority_system._handle_activate_ability(action)
        types = [e.type for e in events]
        assert EventType.DISCARD in types, f"expected DISCARD as cost, got {types}"
        assert EventType.ACTIVATE in types

        # Stack item resolve emits CYCLE marker + DRAW.
        item = game.stack.items[-1]
        resolved = item.resolve_fn(item.chosen_targets, game.state) if item.resolve_fn else []
        cycle_events = [e for e in resolved if e.type == EventType.CYCLE]
        draw_events = [e for e in resolved if e.type == EventType.DRAW]
        assert cycle_events, f"expected CYCLE marker, got {[e.type for e in resolved]}"
        assert cycle_events[0].payload['variant'] == 'plain'
        assert cycle_events[0].payload['player'] == p1.id
        assert draw_events, f"expected DRAW from resolve, got {[e.type for e in resolved]}"
        assert draw_events[0].payload['player'] == p1.id
        print("PASS: cycling dispatch pays cost + emits CYCLE + DRAW")

    asyncio.get_event_loop().run_until_complete(_run())


# ---------------------------------------------------------------------------
# Plain cycling end-to-end (HAND -> GY + draw)
# ---------------------------------------------------------------------------

def test_plain_cycling_moves_card_to_graveyard_and_draws():
    async def _run():
        game = Game()
        p1 = game.add_player("Alice")
        p2 = game.add_player("Bob")
        game.turn_manager.turn_state.active_player_id = p1.id
        game.turn_manager.turn_state.phase = Phase.PRECOMBAT_MAIN

        # Seed library so the draw succeeds.
        target_def = make_creature(
            name="Target", power=1, toughness=1, mana_cost="{1}",
            subtypes={"Goblin"},
        )
        target = _put_in_library(game, p1, target_def)

        cycler_def = make_creature(
            name="Cycler", power=3, toughness=3, mana_cost="{4}",
            colors=set(), subtypes={"Beast"},
            text="Cycling {1}",
        )
        cycler_def.setup_in_hand = make_cycling_setup("{1}")
        obj = _put_in_hand(game, p1, cycler_def)
        _give_player_mana(p1, game.mana_system, generic=1)

        action = PlayerAction(
            type=ActionType.ACTIVATE_ABILITY,
            player_id=p1.id, source_id=obj.id, ability_id="activated:0",
        )
        cost_events = await game.priority_system._handle_activate_ability(action)
        # Drive the discard event through the pipeline.
        for ev in cost_events:
            game.emit(ev)

        # After cost-pay, the source moved HAND -> GY.
        gy = game.state.zones.get(f"graveyard_{p1.id}")
        hand = game.state.zones.get(f"hand_{p1.id}")
        assert obj.id in gy.objects, "cycler should be in graveyard after cost"
        assert obj.id not in hand.objects, "cycler should not be in hand"
        assert obj.zone == ZoneType.GRAVEYARD

        # Now resolve the stack item (CYCLE + DRAW).
        item = game.stack.items[-1]
        resolved = item.resolve_fn(item.chosen_targets, game.state)
        for ev in resolved:
            game.emit(ev)

        # The seeded target should now be in hand.
        assert target.id in hand.objects, (
            f"draw should put target in hand, hand={hand.objects}"
        )
        print("PASS: plain cycling moves card HAND->GY and draws 1")

    asyncio.get_event_loop().run_until_complete(_run())


# ---------------------------------------------------------------------------
# Landcycling
# ---------------------------------------------------------------------------

def test_landcycling_opens_search_choice_for_named_subtype():
    async def _run():
        game = Game()
        p1 = game.add_player("Alice")
        p2 = game.add_player("Bob")
        game.turn_manager.turn_state.active_player_id = p1.id
        game.turn_manager.turn_state.phase = Phase.PRECOMBAT_MAIN

        # Seed library with a Mountain and a Forest. Landcycling-Mountain
        # should only filter the Mountain.
        mountain = _put_in_library(game, p1, _basic_land_def("Mountain", "Mountain"))
        _put_in_library(game, p1, _basic_land_def("Forest", "Forest"))

        cycler_def = make_creature(
            name="MountainCycler", power=4, toughness=4, mana_cost="{4}{R}",
            colors={Color.RED}, subtypes={"Elemental"},
            text="Mountaincycling {2} (search your library for a Mountain card...)",
        )
        cycler_def.setup_in_hand = make_cycling_setup(
            "{2}", landcycling=["Mountain"],
        )
        obj = _put_in_hand(game, p1, cycler_def)
        _give_player_mana(p1, game.mana_system, generic=2)

        action = PlayerAction(
            type=ActionType.ACTIVATE_ABILITY,
            player_id=p1.id, source_id=obj.id, ability_id="activated:0",
        )
        cost_events = await game.priority_system._handle_activate_ability(action)
        for ev in cost_events:
            game.emit(ev)

        # Resolve; this should open a PendingChoice for library search.
        item = game.stack.items[-1]
        resolved = item.resolve_fn(item.chosen_targets, game.state)
        cycle_events = [e for e in resolved if e.type == EventType.CYCLE]
        assert cycle_events, "expected CYCLE marker for landcycling"
        assert cycle_events[0].payload['variant'] == 'landcycling'

        # The library_search subsystem opens a PendingChoice.
        assert game.state.pending_choice is not None, (
            "landcycling should open a library-search PendingChoice"
        )
        # Only the Mountain should be in the options (Forest filtered out).
        assert mountain.id in game.state.pending_choice.options
        # Forest was filtered out by the Mountain landcycling filter.
        forest_in_lib = [
            o.id for o in game.state.objects.values()
            if o.name == "Forest"
        ]
        for fid in forest_in_lib:
            assert fid not in game.state.pending_choice.options, (
                "Forest should be filtered out by Mountaincycling"
            )

        # Resolve the choice: pick the Mountain.
        choice = game.state.pending_choice
        handler = choice.callback_data['handler']
        new_events = handler(choice, [mountain.id], game.state)
        # Drive the resulting events through the pipeline.
        game.state.pending_choice = None
        for ev in new_events:
            game.emit(ev)

        hand = game.state.zones.get(f"hand_{p1.id}")
        assert mountain.id in hand.objects, (
            f"Mountain should now be in hand after landcycling, hand={hand.objects}"
        )
        # Library should have been shuffled (the Forest is still there).
        library = game.state.zones.get(f"library_{p1.id}")
        assert mountain.id not in library.objects, (
            "Mountain should have left the library"
        )
        print("PASS: landcycling opens search and finds named-subtype land")

    asyncio.get_event_loop().run_until_complete(_run())


# ---------------------------------------------------------------------------
# Typecycling
# ---------------------------------------------------------------------------

def test_typecycling_filters_by_subtype():
    async def _run():
        game = Game()
        p1 = game.add_player("Alice")
        p2 = game.add_player("Bob")
        game.turn_manager.turn_state.active_player_id = p1.id
        game.turn_manager.turn_state.phase = Phase.PRECOMBAT_MAIN

        # Seed library with a Wizard creature and a Goblin creature.
        wizard_def = make_creature(
            name="Library Wizard", power=1, toughness=1, mana_cost="{U}",
            subtypes={"Human", "Wizard"},
        )
        goblin_def = make_creature(
            name="Library Goblin", power=1, toughness=1, mana_cost="{R}",
            subtypes={"Goblin"},
        )
        wizard = _put_in_library(game, p1, wizard_def)
        _put_in_library(game, p1, goblin_def)

        cycler_def = make_creature(
            name="WizardCycler", power=3, toughness=3, mana_cost="{2}{U}",
            colors={Color.BLUE}, subtypes={"Wizard"},
            text="Wizardcycling {2}",
        )
        cycler_def.setup_in_hand = make_cycling_setup(
            "{2}", typecycling="Wizard",
        )
        obj = _put_in_hand(game, p1, cycler_def)
        _give_player_mana(p1, game.mana_system, generic=2)

        action = PlayerAction(
            type=ActionType.ACTIVATE_ABILITY,
            player_id=p1.id, source_id=obj.id, ability_id="activated:0",
        )
        cost_events = await game.priority_system._handle_activate_ability(action)
        for ev in cost_events:
            game.emit(ev)

        item = game.stack.items[-1]
        resolved = item.resolve_fn(item.chosen_targets, game.state)
        cycle_events = [e for e in resolved if e.type == EventType.CYCLE]
        assert cycle_events[0].payload['variant'] == 'typecycling'

        assert game.state.pending_choice is not None
        assert wizard.id in game.state.pending_choice.options
        # The Goblin must have been filtered out (no Wizard subtype).
        goblin_in_lib = [
            o.id for o in game.state.objects.values()
            if o.name == "Library Goblin"
        ]
        for gid in goblin_in_lib:
            assert gid not in game.state.pending_choice.options
        print("PASS: typecycling filters by subtype")

    asyncio.get_event_loop().run_until_complete(_run())


# ---------------------------------------------------------------------------
# Rider trigger
# ---------------------------------------------------------------------------

def test_rider_trigger_fires_on_cycle():
    async def _run():
        game = Game()
        p1 = game.add_player("Alice")
        p2 = game.add_player("Bob")
        game.turn_manager.turn_state.active_player_id = p1.id
        game.turn_manager.turn_state.phase = Phase.PRECOMBAT_MAIN

        # Seed library so the draw works.
        _put_in_library(game, p1, make_creature(
            name="Filler", power=1, toughness=1, mana_cost="{1}",
        ))

        # Rider: When you cycle this, deal 2 damage to opponent.
        captured = {"fired": 0}

        def damage_rider(o, state):
            captured["fired"] += 1
            return [Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': p2.id, 'amount': -2},
                source=o.id, controller=o.controller,
            )]

        cycler_def = make_creature(
            name="Cycler-Rider", power=2, toughness=2, mana_cost="{1}{R}",
            colors={Color.RED}, subtypes={"Goblin"},
            text="Cycling {2}\nWhen you cycle Cycler-Rider, deal 2 damage to opponent.",
        )
        cycler_def.setup_in_hand = make_cycling_setup(
            "{2}", rider_effect_fn=damage_rider,
        )
        obj = _put_in_hand(game, p1, cycler_def)
        _give_player_mana(p1, game.mana_system, generic=2)

        action = PlayerAction(
            type=ActionType.ACTIVATE_ABILITY,
            player_id=p1.id, source_id=obj.id, ability_id="activated:0",
        )
        cost_events = await game.priority_system._handle_activate_ability(action)
        for ev in cost_events:
            game.emit(ev)

        item = game.stack.items[-1]
        resolved = item.resolve_fn(item.chosen_targets, game.state)
        types = [e.type for e in resolved]
        assert EventType.CYCLE in types
        assert EventType.DRAW in types
        assert EventType.CYCLING_TRIGGERED in types, (
            f"expected CYCLING_TRIGGERED, got {types}"
        )
        assert EventType.LIFE_CHANGE in types, (
            f"expected rider LIFE_CHANGE, got {types}"
        )
        assert captured["fired"] == 1, "rider should fire exactly once"
        print("PASS: rider trigger fires on cycle (with CYCLING_TRIGGERED marker)")

    asyncio.get_event_loop().run_until_complete(_run())


# ---------------------------------------------------------------------------
# Zone restrictions: cannot cycle from battlefield/graveyard.
# ---------------------------------------------------------------------------

def test_cannot_cycle_from_battlefield_or_graveyard():
    """Cycling abilities are HAND-only. Setup-in-hand only fires when the
    card is in the HAND zone, so a battlefield/graveyard card with the same
    card_def should NOT have a cycling ability registered."""
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")

    cycler_def = make_creature(
        name="Cycler", power=3, toughness=3, mana_cost="{4}",
        text="Cycling {2}",
    )
    cycler_def.setup_in_hand = make_cycling_setup("{2}")

    # Place directly on battlefield.
    bf_obj = game.create_object(
        name=cycler_def.name,
        owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
        characteristics=cycler_def.characteristics,
        card_def=cycler_def,
    )
    bf_abilities = getattr(bf_obj.state, "activated_abilities", []) or []
    assert not any(
        "Cycling" in a.description for a in bf_abilities
    ), "battlefield cards should not have cycling registered"

    # Place directly in graveyard.
    gy_obj = game.create_object(
        name=cycler_def.name,
        owner_id=p1.id, zone=ZoneType.GRAVEYARD,
        characteristics=cycler_def.characteristics,
        card_def=cycler_def,
    )
    gy_abilities = getattr(gy_obj.state, "activated_abilities", []) or []
    assert not any(
        "Cycling" in a.description for a in gy_abilities
    ), "graveyard cards should not have cycling registered"

    # Hand object: should HAVE cycling registered.
    hand_obj = _put_in_hand(game, p1, cycler_def)
    hand_abilities = getattr(hand_obj.state, "activated_abilities", []) or []
    assert any(
        "Cycling" in a.description for a in hand_abilities
    ), "hand cards should have cycling registered"

    print("PASS: cycling is HAND-only (battlefield/graveyard cards have no cycling ability)")


# ---------------------------------------------------------------------------
# Multiple copies of the same cycling card
# ---------------------------------------------------------------------------

def test_multiple_copies_each_get_own_ability():
    """If the player has 2 copies of a cycling card in hand, each must have
    its own ActivatedAbility descriptor (so cycling one doesn't disable the
    other)."""
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    game.turn_manager.turn_state.active_player_id = p1.id
    game.turn_manager.turn_state.phase = Phase.PRECOMBAT_MAIN

    cycler_def = make_creature(
        name="Cycler", power=3, toughness=3, mana_cost="{4}",
        text="Cycling {2}",
    )
    cycler_def.setup_in_hand = make_cycling_setup("{2}")

    a = _put_in_hand(game, p1, cycler_def)
    b = _put_in_hand(game, p1, cycler_def)
    _give_player_mana(p1, game.mana_system, generic=4)

    actions = game.priority_system.get_legal_actions(p1.id)
    cycle_actions = [
        la for la in actions if la.type == ActionType.CYCLE_CARD
    ]
    assert len(cycle_actions) == 2, (
        f"expected 2 cycle actions for 2 copies, got {len(cycle_actions)}"
    )
    sources = {la.card_id for la in cycle_actions}
    assert sources == {a.id, b.id}, f"sources mismatch: {sources}"
    print("PASS: multiple copies of cycling card each surface a CYCLE_CARD action")


# ---------------------------------------------------------------------------
# Foundations card per-card tests
# ---------------------------------------------------------------------------

def _foundations_card(name):
    from src.cards.foundations import FOUNDATIONS_CARDS
    return FOUNDATIONS_CARDS[name]


def test_foundations_plainswalker_pilgrim_plain_cycle():
    cdef = _foundations_card("Plainswalker Pilgrim")
    assert cdef.setup_in_hand is not None
    game = Game()
    p1 = game.add_player("Alice")
    game.add_player("Bob")
    obj = _put_in_hand(game, p1, cdef)
    abilities = obj.state.activated_abilities
    assert any(a.cost_text == "{2}, Discard this card" for a in abilities)
    print("PASS: Plainswalker Pilgrim has Cycling {2}")


def test_foundations_shimmering_revelation_blue_cycle():
    cdef = _foundations_card("Shimmering Revelation")
    game = Game()
    p1 = game.add_player("Alice")
    game.add_player("Bob")
    obj = _put_in_hand(game, p1, cdef)
    abilities = obj.state.activated_abilities
    assert any(a.cost_text == "{U}, Discard this card" for a in abilities)
    print("PASS: Shimmering Revelation has Cycling {U}")


def test_foundations_ember_berserker_mountaincycling():
    cdef = _foundations_card("Ember Berserker")
    game = Game()
    p1 = game.add_player("Alice")
    game.add_player("Bob")
    obj = _put_in_hand(game, p1, cdef)
    abilities = obj.state.activated_abilities
    assert any("land: Mountain" in a.description for a in abilities), (
        f"expected Mountaincycling, got {[a.description for a in abilities]}"
    )
    print("PASS: Ember Berserker has Mountaincycling {2}")


def test_foundations_krosan_forager_forestcycling():
    cdef = _foundations_card("Krosan Forager")
    game = Game()
    p1 = game.add_player("Alice")
    game.add_player("Bob")
    obj = _put_in_hand(game, p1, cdef)
    abilities = obj.state.activated_abilities
    assert any("land: Forest" in a.description for a in abilities)
    print("PASS: Krosan Forager has Forestcycling {2}")


def test_foundations_decree_of_armament_with_rider():
    async def _run():
        cdef = _foundations_card("Decree of Armament")
        game = Game()
        p1 = game.add_player("Alice")
        p2 = game.add_player("Bob")
        game.turn_manager.turn_state.active_player_id = p1.id
        game.turn_manager.turn_state.phase = Phase.PRECOMBAT_MAIN
        # Seed library so the draw succeeds.
        _put_in_library(game, p1, make_creature(
            name="Filler", power=1, toughness=1, mana_cost="{1}",
        ))

        obj = _put_in_hand(game, p1, cdef)
        # Cycling cost is {2}{W}.
        _give_player_mana(p1, game.mana_system, generic=2, white=1)

        starting_life = p1.life
        action = PlayerAction(
            type=ActionType.ACTIVATE_ABILITY,
            player_id=p1.id, source_id=obj.id, ability_id="activated:0",
        )
        cost_events = await game.priority_system._handle_activate_ability(action)
        for ev in cost_events:
            game.emit(ev)

        item = game.stack.items[-1]
        resolved = item.resolve_fn(item.chosen_targets, game.state)
        for ev in resolved:
            game.emit(ev)

        # Rider should have gained the player 4 life.
        assert p1.life == starting_life + 4, (
            f"expected +4 life from rider, got {p1.life - starting_life}"
        )
        print("PASS: Decree of Armament cycling rider gains 4 life")

    asyncio.get_event_loop().run_until_complete(_run())


def test_foundations_twisted_apparition_with_rider():
    async def _run():
        cdef = _foundations_card("Twisted Apparition")
        game = Game()
        p1 = game.add_player("Alice")
        p2 = game.add_player("Bob")
        game.turn_manager.turn_state.active_player_id = p1.id
        game.turn_manager.turn_state.phase = Phase.PRECOMBAT_MAIN
        _put_in_library(game, p1, make_creature(
            name="Filler", power=1, toughness=1, mana_cost="{1}",
        ))
        obj = _put_in_hand(game, p1, cdef)
        _give_player_mana(p1, game.mana_system, generic=2, black=1)

        starting_life_p2 = p2.life
        action = PlayerAction(
            type=ActionType.ACTIVATE_ABILITY,
            player_id=p1.id, source_id=obj.id, ability_id="activated:0",
        )
        cost_events = await game.priority_system._handle_activate_ability(action)
        for ev in cost_events:
            game.emit(ev)
        item = game.stack.items[-1]
        resolved = item.resolve_fn(item.chosen_targets, game.state)
        for ev in resolved:
            game.emit(ev)

        assert p2.life == starting_life_p2 - 2, (
            f"expected opponent to lose 2 life, got {starting_life_p2 - p2.life}"
        )
        print("PASS: Twisted Apparition rider drains opponent for 2")

    asyncio.get_event_loop().run_until_complete(_run())


def test_foundations_wizened_lorekeeper_typecycling():
    cdef = _foundations_card("Wizened Lorekeeper")
    game = Game()
    p1 = game.add_player("Alice")
    game.add_player("Bob")
    obj = _put_in_hand(game, p1, cdef)
    abilities = obj.state.activated_abilities
    assert any("type: Wizard" in a.description for a in abilities)
    print("PASS: Wizened Lorekeeper has Wizardcycling {2}")


# ---------------------------------------------------------------------------
# Imperative helper test
# ---------------------------------------------------------------------------

def test_handle_cycle_action_imperative_helper():
    """Smoke-test the low-level _handle_cycle_action helper."""
    game = Game()
    p1 = game.add_player("Alice")
    game.add_player("Bob")

    cycler_def = make_creature(
        name="Cycler", power=2, toughness=2, mana_cost="{1}",
    )
    cycler_def.setup_in_hand = make_cycling_setup("{1}")
    obj = _put_in_hand(game, p1, cycler_def)

    events = _handle_cycle_action(game.state, p1.id, obj.id, cost="{1}")
    types = [e.type for e in events]
    assert EventType.DISCARD in types
    assert EventType.CYCLE in types
    assert EventType.DRAW in types
    print("PASS: _handle_cycle_action emits DISCARD + CYCLE + DRAW")


def test_handle_cycle_action_rejects_non_hand_source():
    game = Game()
    p1 = game.add_player("Alice")
    game.add_player("Bob")

    cycler_def = make_creature(
        name="Cycler", power=2, toughness=2, mana_cost="{1}",
    )
    bf_obj = game.create_object(
        name=cycler_def.name, owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
        characteristics=cycler_def.characteristics, card_def=cycler_def,
    )
    events = _handle_cycle_action(game.state, p1.id, bf_obj.id, cost="{1}")
    assert events == [], "battlefield source should produce no events"
    print("PASS: _handle_cycle_action rejects non-HAND sources")


if __name__ == "__main__":
    test_cycling_registers_activated_ability_in_hand()
    test_cycling_surfaces_in_legal_actions()
    test_cycling_dispatch_pays_cost_and_draws()
    test_plain_cycling_moves_card_to_graveyard_and_draws()
    test_landcycling_opens_search_choice_for_named_subtype()
    test_typecycling_filters_by_subtype()
    test_rider_trigger_fires_on_cycle()
    test_cannot_cycle_from_battlefield_or_graveyard()
    test_multiple_copies_each_get_own_ability()
    test_foundations_plainswalker_pilgrim_plain_cycle()
    test_foundations_shimmering_revelation_blue_cycle()
    test_foundations_ember_berserker_mountaincycling()
    test_foundations_krosan_forager_forestcycling()
    test_foundations_decree_of_armament_with_rider()
    test_foundations_twisted_apparition_with_rider()
    test_foundations_wizened_lorekeeper_typecycling()
    test_handle_cycle_action_imperative_helper()
    test_handle_cycle_action_rejects_non_hand_source()
    print("\nAll cycling tests passed!")
