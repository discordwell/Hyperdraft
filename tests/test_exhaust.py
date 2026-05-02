"""Tests for the Exhaust mechanic (once-per-game activated ability).

Exhaust is an Aetherdrift / Avatar: TLA mechanic. Each Exhaust ability
on a permanent can be activated at most once — ever. The ability is
tracked per-permanent (per ``GameObject``), not per card name, so two
copies of the same card each have their own state.

Covers:
- Exhaust ability surfaces in legal actions before first activation
- After activation, it's removed from legal actions for that permanent
- Two copies of the same card maintain independent exhaust state
- Engine API: ``ActivatedAbility.once_per_game`` and the
  ``make_exhaust_ability`` helper.
- A real wired card (Skystreak Engineer from Aetherdrift) round-trips
  through the priority system.
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_HERE)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import asyncio

from src.engine import (
    Game, Event, EventType, ZoneType, Color,
    make_creature,
)
from src.engine.activated import detect_exhaust
from src.engine.priority import ActionType, PlayerAction
from src.engine.turn import Phase
from src.cards.interceptor_helpers import make_exhaust_ability


def _setup_game_for_player(p_id, game):
    """Set up turn_state so the player has priority on their own main phase."""
    game.turn_manager.turn_state.active_player_id = p_id
    game.turn_manager.turn_state.phase = Phase.PRECOMBAT_MAIN


def _spawn_on_battlefield(game, player, card_def):
    obj = game.create_object(
        name=card_def.name,
        owner_id=player.id,
        zone=ZoneType.HAND,
        characteristics=card_def.characteristics,
        card_def=None,
    )
    obj.card_def = card_def
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': obj.id,
            'from_zone': f'hand_{player.id}',
            'to_zone': 'battlefield',
            'to_zone_type': ZoneType.BATTLEFIELD,
        },
    ))
    return obj


def _give_player_mana(player, mana_system, generic=0, red=0, green=0,
                      white=0, blue=0, black=0):
    from src.engine.mana import ManaType
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


def _make_pump_exhaust_card(name="Test Exhaust"):
    """Helper: build a creature with an Exhaust — {1}: +1/+1 counter ability."""

    def setup(obj, state):
        def _effect(o, st, targets):
            return [Event(
                type=EventType.COUNTER_ADDED,
                payload={'object_id': o.id, 'counter_type': '+1/+1', 'amount': 1},
                source=o.id, controller=o.controller,
            )]
        make_exhaust_ability(
            obj, cost="{1}", effect_fn=_effect,
            description="{1}: Put a +1/+1 counter on this creature.",
        )
        return []

    return make_creature(
        name=name,
        power=2, toughness=2, mana_cost="{1}",
        colors=set(), subtypes={"Construct"},
        text=f"Exhaust — {{1}}: Put a +1/+1 counter on this creature. (Activate each exhaust ability only once.)",
        setup_interceptors=setup,
    )


# ---------------------------------------------------------------------------
# Engine-level tests
# ---------------------------------------------------------------------------


def test_detect_exhaust_recognizes_text():
    """detect_exhaust catches the standard reminder phrasing and the Exhaust prefix."""
    yes = [
        "Exhaust — {2}{R}: Put two +1/+1 counters on this creature. (Activate each exhaust ability only once.)",
        "Flying\nExhaust — {1}: Draw a card.",
        "Foo bar (Activate each exhaust ability only once.)",
    ]
    no = [
        "",
        "Vigilance",
        "{T}: Add {R}.",
        "Activate this ability only once each turn.",  # Once-per-turn != exhaust
    ]
    for t in yes:
        assert detect_exhaust(t), f"expected Exhaust detected in: {t!r}"
    for t in no:
        assert not detect_exhaust(t), f"did not expect Exhaust in: {t!r}"
    print("PASS: detect_exhaust recognizes Exhaust text")


def test_exhaust_surfaces_then_disappears_after_activation():
    """The ability is legal before, gone after."""
    async def _run():
        game = Game()
        p1 = game.add_player("Alice")
        p2 = game.add_player("Bob")
        _setup_game_for_player(p1.id, game)

        card = _make_pump_exhaust_card("Lone Exhauster")
        obj = _spawn_on_battlefield(game, p1, card)
        obj.state.summoning_sickness = False
        _give_player_mana(p1, game.mana_system, generic=2)

        # Legal before activation.
        before = game.priority_system.get_legal_actions(p1.id)
        matches = [a for a in before if a.ability_id == "activated:0" and a.source_id == obj.id]
        assert matches, f"expected Exhaust ability in legal actions, got: {[a.description for a in before]}"

        # Activate.
        action = PlayerAction(
            type=ActionType.ACTIVATE_ABILITY,
            player_id=p1.id, source_id=obj.id,
            ability_id="activated:0",
        )
        events = await game.priority_system._handle_activate_ability(action)
        assert any(e.type == EventType.ACTIVATE for e in events), "first activation should succeed"

        # Confirm the descriptor recorded the use.
        ability = obj.state.activated_abilities[0]
        assert ability.once_per_game is True, "ability should be marked once-per-game"
        assert ability.once_per_game_used is True, "once_per_game_used should be set"
        assert ability.total_activations == 1

        # No longer legal — even on the same turn.
        after = game.priority_system.get_legal_actions(p1.id)
        matches = [a for a in after if a.ability_id == "activated:0" and a.source_id == obj.id]
        assert not matches, "Exhaust ability should be hidden after first activation"

        # Re-attempting should also fail through the dispatch path.
        _give_player_mana(p1, game.mana_system, generic=2)
        replay = await game.priority_system._handle_activate_ability(action)
        assert not any(e.type == EventType.ACTIVATE for e in replay), \
            "second activation must be rejected by can_pay_activation"

        # And it's still gone on a future turn.
        game.turn_manager.turn_state.turn_number += 5
        game.state.turn_number += 5
        future = game.priority_system.get_legal_actions(p1.id)
        matches = [a for a in future if a.ability_id == "activated:0" and a.source_id == obj.id]
        assert not matches, "Exhaust ability should be hidden across turns"
        print("PASS: exhaust ability surfaces, activates once, never returns")

    asyncio.get_event_loop().run_until_complete(_run())


def test_two_copies_have_independent_exhaust_state():
    """Per-permanent, not per-card-name. Activating one copy doesn't lock the other."""
    async def _run():
        game = Game()
        p1 = game.add_player("Alice")
        p2 = game.add_player("Bob")
        _setup_game_for_player(p1.id, game)

        card = _make_pump_exhaust_card("Twinned Exhauster")
        obj_a = _spawn_on_battlefield(game, p1, card)
        obj_b = _spawn_on_battlefield(game, p1, card)
        obj_a.state.summoning_sickness = False
        obj_b.state.summoning_sickness = False
        _give_player_mana(p1, game.mana_system, generic=4)

        # Both copies should expose their Exhaust ability.
        actions = game.priority_system.get_legal_actions(p1.id)
        a_match = [a for a in actions if a.ability_id == "activated:0" and a.source_id == obj_a.id]
        b_match = [a for a in actions if a.ability_id == "activated:0" and a.source_id == obj_b.id]
        assert a_match and b_match, "both copies should expose their Exhaust ability"

        # Activate copy A only.
        action_a = PlayerAction(
            type=ActionType.ACTIVATE_ABILITY,
            player_id=p1.id, source_id=obj_a.id,
            ability_id="activated:0",
        )
        events = await game.priority_system._handle_activate_ability(action_a)
        assert any(e.type == EventType.ACTIVATE for e in events), "copy A should activate"

        # Copy A locked, copy B still legal.
        post = game.priority_system.get_legal_actions(p1.id)
        a_locked = [a for a in post if a.ability_id == "activated:0" and a.source_id == obj_a.id]
        b_open = [a for a in post if a.ability_id == "activated:0" and a.source_id == obj_b.id]
        assert not a_locked, "copy A should be locked"
        assert b_open, "copy B should remain legal"

        # Independent descriptor state.
        ab_a = obj_a.state.activated_abilities[0]
        ab_b = obj_b.state.activated_abilities[0]
        assert ab_a is not ab_b, "each permanent must own its own ActivatedAbility instance"
        assert ab_a.once_per_game_used is True
        assert ab_b.once_per_game_used is False
        print("PASS: two copies of the same card have independent exhaust state")

    asyncio.get_event_loop().run_until_complete(_run())


def test_make_exhaust_ability_sets_once_per_game_flag():
    """The helper produces a descriptor with once_per_game=True and a clear description."""
    game = Game()
    p1 = game.add_player("Alice")
    _setup_game_for_player(p1.id, game)

    card = _make_pump_exhaust_card("Inspectable")
    obj = _spawn_on_battlefield(game, p1, card)

    abilities = obj.state.activated_abilities
    assert len(abilities) == 1
    ab = abilities[0]
    assert ab.once_per_game is True, "make_exhaust_ability must set once_per_game"
    assert ab.once_per_turn is False, "Exhaust does not imply once-per-turn"
    assert ab.description.lower().startswith("exhaust"), \
        f"description should be prefixed with 'Exhaust —', got {ab.description!r}"
    print("PASS: make_exhaust_ability sets once_per_game flag and Exhaust prefix")


# ---------------------------------------------------------------------------
# Wired-card smoke tests
# ---------------------------------------------------------------------------


def test_wired_skystreak_engineer_exhaust():
    """Aetherdrift Skystreak Engineer: Exhaust — {4}{U}: 2 +1/+1 counters."""
    async def _run():
        from src.cards.aetherdrift import SKYSTREAK_ENGINEER

        game = Game()
        p1 = game.add_player("Alice")
        p2 = game.add_player("Bob")
        _setup_game_for_player(p1.id, game)

        obj = _spawn_on_battlefield(game, p1, SKYSTREAK_ENGINEER)
        obj.state.summoning_sickness = False
        _give_player_mana(p1, game.mana_system, generic=4, blue=1)

        actions = game.priority_system.get_legal_actions(p1.id)
        matches = [a for a in actions if a.ability_id == "activated:0" and a.source_id == obj.id]
        assert matches, "Skystreak Engineer should expose its Exhaust ability"

        action = PlayerAction(
            type=ActionType.ACTIVATE_ABILITY,
            player_id=p1.id, source_id=obj.id,
            ability_id="activated:0",
        )
        events = await game.priority_system._handle_activate_ability(action)
        assert any(e.type == EventType.ACTIVATE for e in events), "activation should succeed"

        # Resolve the stack item to confirm two +1/+1 counters are emitted.
        item = game.stack.items[-1]
        resolved = item.resolve_fn(item.chosen_targets, game.state) if item.resolve_fn else []
        ctr_events = [e for e in resolved if e.type == EventType.COUNTER_ADDED]
        assert ctr_events, f"expected COUNTER_ADDED, got {[e.type for e in resolved]}"
        assert ctr_events[0].payload['amount'] == 2, "should add two +1/+1 counters"
        assert ctr_events[0].payload['counter_type'] == '+1/+1'

        # And it's locked for the rest of the game.
        post = game.priority_system.get_legal_actions(p1.id)
        post_match = [a for a in post if a.ability_id == "activated:0" and a.source_id == obj.id]
        assert not post_match, "Skystreak Engineer's Exhaust must be locked after activation"
        print("PASS: wired Skystreak Engineer Exhaust round-trips and locks")

    asyncio.get_event_loop().run_until_complete(_run())


def test_wired_aetherdrift_cards_register_exhaust_abilities():
    """Sanity check: the seven wired Aetherdrift cards each register one Exhaust ability."""
    from src.cards import aetherdrift

    cards = [
        aetherdrift.KEEN_BUCCANEER,
        aetherdrift.SKYSTREAK_ENGINEER,
        aetherdrift.PACESETTER_PARAGON,
        aetherdrift.PROWCATCHER_SPECIALIST,
        aetherdrift.HAZARD_OF_THE_DUNES,
        aetherdrift.STAMPEDING_SCURRYFOOT,
        aetherdrift.CAMERA_LAUNCHER,
    ]
    for card in cards:
        assert card.setup_interceptors is not None, f"{card.name}: setup_interceptors not wired"

    # Spawn each one and check the Exhaust ability registered with once_per_game.
    for card in cards:
        game = Game()
        p1 = game.add_player("Alice")
        p2 = game.add_player("Bob")
        _setup_game_for_player(p1.id, game)
        obj = _spawn_on_battlefield(game, p1, card)
        ab_list = obj.state.activated_abilities or []
        exhaust_abs = [a for a in ab_list if a.once_per_game]
        assert exhaust_abs, f"{card.name}: expected an Exhaust ability registered"
        assert len(exhaust_abs) == 1, \
            f"{card.name}: expected exactly one Exhaust ability, got {len(exhaust_abs)}"
    print(f"PASS: {len(cards)} wired Aetherdrift Exhaust cards register correctly")


if __name__ == "__main__":
    test_detect_exhaust_recognizes_text()
    test_make_exhaust_ability_sets_once_per_game_flag()
    test_exhaust_surfaces_then_disappears_after_activation()
    test_two_copies_have_independent_exhaust_state()
    test_wired_skystreak_engineer_exhaust()
    test_wired_aetherdrift_cards_register_exhaust_abilities()
    print("\nAll Exhaust tests passed.")
