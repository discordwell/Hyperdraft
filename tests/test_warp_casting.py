"""
Tests for the Edge of Eternities (EOE) Warp mechanic.

Warp lets a card be cast from your hand for an alternate (warp) cost. The
permanent is exiled at the beginning of the next end step. Each card may be
warp-cast at most once per game.
"""

import asyncio
import os
import sys

# This test depends on `src.engine.warp`, which only exists in the current
# (HYPERDRAFT) worktree. Other tests in this codebase prepend an older
# Hyperdraft checkout to sys.path, so we make sure THIS worktree wins by
# inserting it first.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if sys.path[0] != _PROJECT_ROOT:
    sys.path.insert(0, _PROJECT_ROOT)

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color,
    PlayerAction, ActionType,
    make_creature, make_land,
)


def _ensure_warp_module():
    """Load `src.engine.warp` from this worktree even if `src.engine` was
    cached from a different (older) checkout earlier in the test session.
    """
    try:
        import src.engine.warp  # noqa: F401
        return src.engine.warp
    except ModuleNotFoundError:
        import importlib.util
        warp_path = os.path.join(_PROJECT_ROOT, "src", "engine", "warp.py")
        spec = importlib.util.spec_from_file_location("src.engine.warp", warp_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        sys.modules["src.engine.warp"] = module
        return module


_warp = _ensure_warp_module()
parse_warp_cost = _warp.parse_warp_cost
card_has_warp = _warp.card_has_warp
has_warp_been_used = _warp.has_warp_been_used
is_warp_pending = _warp.is_warp_pending
reset_warp_used = _warp.reset_warp_used
is_warp_castable_from_hand = _warp.is_warp_castable_from_hand

from src.engine.turn import Phase
from src.engine.mana import ManaType


# If we're using a different src.engine package than the worktree,
# the `Game()` won't have warp wired into priority.py. We detect this and
# skip the cast-flow tests in that case (parsing tests still run).
import inspect
import pytest
_WARP_INTEGRATED = "is_warp_castable_from_hand" in inspect.getsource(
    sys.modules["src.engine.priority"]
)
_skip_if_no_integration = pytest.mark.skipif(
    not _WARP_INTEGRATED,
    reason="src.engine.priority does not have warp integration "
           "(likely loaded from a different Hyperdraft checkout)",
)


# =============================================================================
# Helpers
# =============================================================================

def _make_warp_creature(name="Warp Goblin", warp_cost="{1}{R}"):
    """Build a simple warp creature with a 4-mana printed cost."""
    card = make_creature(
        name=name,
        power=2, toughness=1,
        mana_cost="{4}{R}",
        colors={Color.RED},
        text=f"Warp {warp_cost} (You may cast this card from your hand for "
             f"its warp cost. Exile this creature at the beginning of the "
             f"next end step, then you may cast it from exile on a later turn.)",
    )
    reset_warp_used(card)
    return card


def _setup_game_for_cast(card, mana_count=2):
    """Set up a Game ready for the active player to cast cards from their hand."""
    game = Game()
    p1 = game.add_player("P1")
    game.add_player("P2")
    game.turn_manager.turn_state.phase = Phase.PRECOMBAT_MAIN
    game.turn_manager.turn_state.active_player_id = p1.id
    game.state.active_player = p1.id

    gobj = game.create_object(
        name=card.name, owner_id=p1.id, zone=ZoneType.HAND,
        characteristics=card.characteristics, card_def=card,
    )

    mtn = make_land("Mountain", subtypes={"Mountain"})
    for _ in range(mana_count):
        game.create_object(
            name="Mountain", owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
            characteristics=mtn.characteristics, card_def=mtn,
        )
    pool = game.mana_system.get_pool(p1.id)
    pool.add(ManaType.RED, mana_count)

    return game, p1, gobj


# =============================================================================
# Parsing
# =============================================================================

def test_parse_warp_cost_simple():
    cost = parse_warp_cost(
        "Warp {2}{R} (You may cast this card from your hand for its warp cost.)"
    )
    assert cost is not None
    assert cost.red == 1
    assert cost.generic == 2


def test_parse_warp_cost_pure_generic():
    cost = parse_warp_cost("Warp {4}")
    assert cost is not None
    assert cost.generic == 4


def test_parse_warp_cost_x_value():
    cost = parse_warp_cost("Warp {X}{G}")
    assert cost is not None
    assert cost.x_count == 1
    assert cost.green == 1


def test_parse_warp_cost_no_warp():
    assert parse_warp_cost("Vigilance, lifelink") is None
    assert parse_warp_cost("") is None
    assert parse_warp_cost(None) is None


def test_card_has_warp():
    card = _make_warp_creature()
    assert card_has_warp(card)


# =============================================================================
# Legal-action surfacing
# =============================================================================

@_skip_if_no_integration
def test_warp_action_surfaced_when_payable():
    card = _make_warp_creature(warp_cost="{1}{R}")
    game, p1, gobj = _setup_game_for_cast(card, mana_count=2)

    legal = game.priority_system.get_legal_actions(p1.id)
    warp_actions = [
        a for a in legal
        if a.type == ActionType.CAST_SPELL
        and a.card_id == gobj.id
        and a.ability_id == "hand:warp"
    ]
    assert len(warp_actions) == 1, f"expected 1 warp action, got {len(warp_actions)}"
    assert "warp" in warp_actions[0].description.lower()


@_skip_if_no_integration
def test_warp_action_not_surfaced_when_unpayable():
    card = _make_warp_creature(warp_cost="{2}{R}{R}")
    game, p1, gobj = _setup_game_for_cast(card, mana_count=1)

    legal = game.priority_system.get_legal_actions(p1.id)
    warp_actions = [a for a in legal if a.ability_id == "hand:warp"]
    assert warp_actions == []


# =============================================================================
# Cast lifecycle
# =============================================================================

@_skip_if_no_integration
def test_warp_cast_marks_card_def_used():
    card = _make_warp_creature()
    game, p1, gobj = _setup_game_for_cast(card, mana_count=2)

    assert not has_warp_been_used(card)
    action = PlayerAction(
        type=ActionType.CAST_SPELL,
        player_id=p1.id,
        card_id=gobj.id,
        ability_id="hand:warp",
    )
    for e in asyncio.run(game.priority_system._handle_cast_spell(action)):
        game.emit(e)

    assert gobj.zone == ZoneType.STACK
    assert has_warp_been_used(card)
    assert is_warp_pending(gobj)


@_skip_if_no_integration
def test_warp_cast_resolves_to_battlefield():
    card = _make_warp_creature()
    game, p1, gobj = _setup_game_for_cast(card, mana_count=2)

    action = PlayerAction(
        type=ActionType.CAST_SPELL,
        player_id=p1.id,
        card_id=gobj.id,
        ability_id="hand:warp",
    )
    for e in asyncio.run(game.priority_system._handle_cast_spell(action)):
        game.emit(e)

    for e in game.resolve_stack():
        game.emit(e)

    assert gobj.zone == ZoneType.BATTLEFIELD


@_skip_if_no_integration
def test_warp_creature_exiled_at_next_end_step():
    card = _make_warp_creature()
    game, p1, gobj = _setup_game_for_cast(card, mana_count=2)

    action = PlayerAction(
        type=ActionType.CAST_SPELL,
        player_id=p1.id,
        card_id=gobj.id,
        ability_id="hand:warp",
    )
    for e in asyncio.run(game.priority_system._handle_cast_spell(action)):
        game.emit(e)
    for e in game.resolve_stack():
        game.emit(e)

    assert gobj.zone == ZoneType.BATTLEFIELD

    # Fire the next end step.
    game.emit(Event(type=EventType.PHASE_START, payload={'phase': 'end_step'}))

    assert gobj.zone == ZoneType.EXILE


@_skip_if_no_integration
def test_one_warp_per_card_definition():
    """A single CardDefinition can be warp-cast at most once."""
    card = _make_warp_creature()
    game, p1, gobj = _setup_game_for_cast(card, mana_count=4)

    # First copy - warp legal
    legal1 = game.priority_system.get_legal_actions(p1.id)
    warp_actions1 = [a for a in legal1 if a.card_id == gobj.id and a.ability_id == "hand:warp"]
    assert len(warp_actions1) == 1

    # Cast first copy via warp
    action = PlayerAction(
        type=ActionType.CAST_SPELL,
        player_id=p1.id,
        card_id=gobj.id,
        ability_id="hand:warp",
    )
    for e in asyncio.run(game.priority_system._handle_cast_spell(action)):
        game.emit(e)
    for e in game.resolve_stack():
        game.emit(e)

    # Add a second copy of the same card definition
    gobj2 = game.create_object(
        name=card.name, owner_id=p1.id, zone=ZoneType.HAND,
        characteristics=card.characteristics, card_def=card,
    )
    legal2 = game.priority_system.get_legal_actions(p1.id)
    warp_actions2 = [a for a in legal2 if a.card_id == gobj2.id and a.ability_id == "hand:warp"]
    assert warp_actions2 == [], f"expected no warp option after warp used, got {warp_actions2}"


@_skip_if_no_integration
def test_warp_castable_from_hand_check():
    card = _make_warp_creature()
    game, p1, gobj = _setup_game_for_cast(card, mana_count=2)
    assert is_warp_castable_from_hand(gobj, game.state, p1.id)

    # Move to graveyard - should no longer be warp-castable from hand.
    game.state.zones[f"hand_{p1.id}"].objects.remove(gobj.id)
    game.state.zones[f"graveyard_{p1.id}"].objects.append(gobj.id)
    gobj.zone = ZoneType.GRAVEYARD

    assert not is_warp_castable_from_hand(gobj, game.state, p1.id)


@_skip_if_no_integration
def test_warp_creature_not_exiled_if_already_left_battlefield():
    """If the warp creature dies before end step, no exile event fires (it's already gone)."""
    card = _make_warp_creature()
    game, p1, gobj = _setup_game_for_cast(card, mana_count=2)

    action = PlayerAction(
        type=ActionType.CAST_SPELL,
        player_id=p1.id,
        card_id=gobj.id,
        ability_id="hand:warp",
    )
    for e in asyncio.run(game.priority_system._handle_cast_spell(action)):
        game.emit(e)
    for e in game.resolve_stack():
        game.emit(e)

    # Manually move the creature to graveyard before end step.
    game.state.zones["battlefield"].objects.remove(gobj.id)
    game.state.zones[f"graveyard_{p1.id}"].objects.append(gobj.id)
    gobj.zone = ZoneType.GRAVEYARD

    # Fire end step. The interceptor should fire but PASS since the creature
    # is no longer on the battlefield.
    game.emit(Event(type=EventType.PHASE_START, payload={'phase': 'end_step'}))

    assert gobj.zone == ZoneType.GRAVEYARD


if __name__ == "__main__":
    # Allow running directly.
    test_parse_warp_cost_simple()
    test_parse_warp_cost_pure_generic()
    test_parse_warp_cost_x_value()
    test_parse_warp_cost_no_warp()
    test_card_has_warp()
    test_warp_action_surfaced_when_payable()
    test_warp_action_not_surfaced_when_unpayable()
    test_warp_cast_marks_card_def_used()
    test_warp_cast_resolves_to_battlefield()
    test_warp_creature_exiled_at_next_end_step()
    test_one_warp_per_card_definition()
    test_warp_castable_from_hand_check()
    test_warp_creature_not_exiled_if_already_left_battlefield()
    print("All warp tests passed.")
