"""
Phase 5b — divide-damage cast-time prompt via ``divide_allocation``.

When a CardDefinition declares a ``TargetRequirement`` whose ``divide_amount``
is set (literal int or callable for X-cost), the priority system emits a
``divide_allocation`` PendingChoice at cast time. The submission shape is
``list[{target_id, amount}]``; amounts must sum to ``total_amount``.

The choice handler stuffs each allocation into the chosen ``Target``'s
``divided_amount`` field and re-enters the cast. The spell's resolve
callback (usually ``make_divide_damage_resolve``) then reads those Target
objects and emits one DAMAGE event per allocation.

This file covers:
- Empty-targets cast → ``divide_allocation`` PendingChoice with the
  right options, prompt, and total_amount.
- Human-style submission (allocate-and-resolve) distributes damage
  correctly across multiple targets.
- AI heuristic spreads damage to opponent creatures preferentially.
- Degenerate single-target case (everything on one target).
- ``min_targets``/``max_targets`` enforcement: validator rejects zero
  allocations.
- X-cost (callable ``divide_amount``) supplies the right budget at
  prompt-time.
- Bare-resolve tests for ``make_divide_damage_resolve`` (resolve()
  honors ``divided_amount`` on each Target and falls back to even split
  when divided_amount is empty).

Demo card: Twin Bolt — migrated to ``make_divide_damage_resolve`` +
``divide_allocation`` PendingChoice in this phase.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color, Characteristics,
)
from src.engine.priority import PlayerAction, ActionType
from src.engine.targeting import (
    Target, TargetRequirement, any_target_filter, creature_filter,
)
from src.engine.types import PendingChoice
from src.engine.game import make_land

from src.cards.test_cards import SOUL_WARDEN
from src.cards.tarkir_dragonstorm import TWIN_BOLT
from src.cards.card_factories import make_instant
from src.cards.interceptor_helpers import make_divide_damage_resolve


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _setup_game_with_twin_bolt_in_hand():
    """Two-player game, P1 has Twin Bolt in hand and 2 Mountains in play."""
    game = Game()
    p1 = game.add_player("Caster")
    p2 = game.add_player("Defender")

    bolt = game.create_object(
        name=TWIN_BOLT.name,
        owner_id=p1.id,
        zone=ZoneType.HAND,
        characteristics=TWIN_BOLT.characteristics,
        card_def=TWIN_BOLT,
    )

    mountain_def = make_land("Mountain", subtypes={"Mountain"})
    for _ in range(2):
        game.create_object(
            name="Mountain",
            owner_id=p1.id,
            zone=ZoneType.BATTLEFIELD,
            characteristics=mountain_def.characteristics,
            card_def=mountain_def,
        )
    return game, p1, p2, bolt


def _add_creature(game, owner_id, name="Bear"):
    return game.create_object(
        name=name,
        owner_id=owner_id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=SOUL_WARDEN.characteristics,
        card_def=SOUL_WARDEN,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_cast_with_empty_targets_emits_divide_allocation():
    """Phase 5b: cast Twin Bolt with action.targets=[] → divide_allocation."""
    game, p1, p2, bolt = _setup_game_with_twin_bolt_in_hand()
    creature1 = _add_creature(game, p2.id, "Bear")
    creature2 = _add_creature(game, p2.id, "Wolf")

    assert game.state.pending_choice is None

    action = PlayerAction(
        type=ActionType.CAST_SPELL,
        player_id=p1.id,
        card_id=bolt.id,
        targets=[],
    )
    asyncio.run(game.priority_system._handle_cast_spell(action))

    pc = game.state.pending_choice
    assert pc is not None, "PendingChoice must be set"
    assert pc.choice_type == "divide_allocation", (
        f"expected divide_allocation, got {pc.choice_type!r}"
    )
    assert pc.player == p1.id
    assert pc.source_id == bolt.id
    # Total damage budget is 2.
    assert pc.callback_data.get("total_amount") == 2
    assert pc.callback_data.get("effect") == "damage"
    # Both opposing creatures plus both players are legal.
    option_ids = {opt["id"] for opt in pc.options}
    assert creature1.id in option_ids
    assert creature2.id in option_ids
    assert p1.id in option_ids and p2.id in option_ids
    # Each option carries name/type/life metadata for the divide renderer.
    for opt in pc.options:
        assert "name" in opt and "type" in opt, f"option missing UI keys: {opt}"

    # Bolt is still in hand — cast is paused before mana payment.
    assert bolt.zone == ZoneType.HAND, (
        f"Bolt should still be in hand while choice pending, got {bolt.zone}"
    )


def test_submission_distributes_damage_correctly():
    """Submit a 1+1 allocation across two creatures → two DAMAGE events
    each for 1 damage, applied through emit() so toughness ticks down."""
    game, p1, p2, bolt = _setup_game_with_twin_bolt_in_hand()
    creature1 = _add_creature(game, p2.id, "Bear")
    creature2 = _add_creature(game, p2.id, "Wolf")

    action = PlayerAction(
        type=ActionType.CAST_SPELL,
        player_id=p1.id,
        card_id=bolt.id,
        targets=[],
    )
    asyncio.run(game.priority_system._handle_cast_spell(action))
    pc = game.state.pending_choice
    assert pc is not None and pc.choice_type == "divide_allocation"

    # Submit: 1 damage to each creature.
    selected = [
        {"target_id": creature1.id, "amount": 1},
        {"target_id": creature2.id, "amount": 1},
    ]
    ok, err, _events = game.submit_choice(pc.id, p1.id, selected)
    assert ok, f"submit_choice failed: {err}"
    assert game.state.pending_choice is None

    # Cast re-entered → spell is on the stack with two Targets carrying
    # divided_amount.
    assert bolt.zone == ZoneType.STACK, (
        f"Bolt should be on stack after submission, got {bolt.zone}"
    )
    # Resolve the spell on the stack.
    stack_items = game.stack.items
    assert stack_items, "Stack should have the resolving spell"
    twin_bolt_item = stack_items[-1]
    # Confirm chosen_targets carries the divided_amounts.
    chosen = twin_bolt_item.chosen_targets[0]
    assert len(chosen) == 2
    by_id = {t.id: t for t in chosen}
    assert by_id[creature1.id].divided_amount == 1
    assert by_id[creature2.id].divided_amount == 1

    # Resolve and confirm both creatures take 1 damage.
    resolve_events = game.stack.resolve_top()
    # Two DAMAGE events should have been produced.
    damage_events = [
        e for e in resolve_events if e.type == EventType.DAMAGE
    ]
    assert len(damage_events) == 2, (
        f"expected 2 DAMAGE events, got {len(damage_events)}: {damage_events}"
    )
    by_target = {e.payload['target']: e.payload['amount'] for e in damage_events}
    assert by_target.get(creature1.id) == 1
    assert by_target.get(creature2.id) == 1


def test_submission_with_full_amount_on_one_target():
    """Degenerate case: allocate all 2 damage to a single target."""
    game, p1, p2, bolt = _setup_game_with_twin_bolt_in_hand()
    creature = _add_creature(game, p2.id, "Bear")

    action = PlayerAction(
        type=ActionType.CAST_SPELL,
        player_id=p1.id,
        card_id=bolt.id,
        targets=[],
    )
    asyncio.run(game.priority_system._handle_cast_spell(action))
    pc = game.state.pending_choice
    assert pc is not None

    selected = [{"target_id": creature.id, "amount": 2}]
    ok, err, _events = game.submit_choice(pc.id, p1.id, selected)
    assert ok, f"submit_choice failed: {err}"

    # Resolve and confirm the creature took 2 damage.
    resolve_events = game.stack.resolve_top()
    damage_events = [
        e for e in resolve_events
        if e.type == EventType.DAMAGE and e.payload.get('target') == creature.id
    ]
    assert any(e.payload.get('amount') == 2 for e in damage_events), (
        f"expected a 2-damage DAMAGE event on creature; got {damage_events}"
    )


def test_validator_rejects_under_allocation():
    """The PendingChoice validator must reject allocations that don't
    sum to total_amount (zero-allocation submission)."""
    game, p1, p2, bolt = _setup_game_with_twin_bolt_in_hand()
    creature = _add_creature(game, p2.id, "Bear")

    action = PlayerAction(
        type=ActionType.CAST_SPELL,
        player_id=p1.id,
        card_id=bolt.id,
        targets=[],
    )
    asyncio.run(game.priority_system._handle_cast_spell(action))
    pc = game.state.pending_choice
    assert pc is not None

    # Submit only 1 damage out of 2 — must be rejected.
    bad = [{"target_id": creature.id, "amount": 1}]
    ok, err, _ = game.submit_choice(pc.id, p1.id, bad)
    assert not ok, "Validator should reject 1/2 allocation"
    assert "Must allocate" in err or "allocate" in err, (
        f"unexpected error message: {err!r}"
    )
    # PendingChoice should still be set (game not advanced).
    assert game.state.pending_choice is not None
    assert game.state.pending_choice.id == pc.id


def test_validator_rejects_overallocation():
    """The validator must reject allocations that exceed total_amount."""
    game, p1, p2, bolt = _setup_game_with_twin_bolt_in_hand()
    creature = _add_creature(game, p2.id, "Bear")

    action = PlayerAction(
        type=ActionType.CAST_SPELL,
        player_id=p1.id,
        card_id=bolt.id,
        targets=[],
    )
    asyncio.run(game.priority_system._handle_cast_spell(action))
    pc = game.state.pending_choice
    assert pc is not None

    # Submit 5 damage when total is 2 — must be rejected.
    over = [{"target_id": creature.id, "amount": 5}]
    ok, err, _ = game.submit_choice(pc.id, p1.id, over)
    assert not ok, "Validator should reject 5/2 over-allocation"


def test_no_legal_targets_aborts_cast():
    """If there are no legal targets when the cast starts, the cast aborts
    without emitting a PendingChoice (MTG rule)."""
    game = Game()
    p1 = game.add_player("P1")
    # Build a divide-damage spell that only targets opponent creatures.
    NEEDS_OPPONENT_CREATURE = make_instant(
        name="Opp-Only Bolt",
        mana_cost="{1}{R}",
        colors={Color.RED},
        text="Deal 2 damage divided among opponent creatures.",
        resolve=make_divide_damage_resolve(
            "Opp-Only Bolt",
            total_damage=2,
            target_filter=creature_filter(controller='opponent'),
        ),
        target_requirements=[
            TargetRequirement(
                filter=creature_filter(controller='opponent'),
                count=99,
                count_type='any_number',
                label="Allocate among opposing creatures",
                divide_amount=2,
            ),
        ],
    )

    card = game.create_object(
        name=NEEDS_OPPONENT_CREATURE.name,
        owner_id=p1.id,
        zone=ZoneType.HAND,
        characteristics=NEEDS_OPPONENT_CREATURE.characteristics,
        card_def=NEEDS_OPPONENT_CREATURE,
    )
    mountain_def = make_land("Mountain", subtypes={"Mountain"})
    for _ in range(2):
        game.create_object(
            name="Mountain",
            owner_id=p1.id,
            zone=ZoneType.BATTLEFIELD,
            characteristics=mountain_def.characteristics,
            card_def=mountain_def,
        )

    action = PlayerAction(
        type=ActionType.CAST_SPELL,
        player_id=p1.id,
        card_id=card.id,
        targets=[],
    )
    asyncio.run(game.priority_system._handle_cast_spell(action))
    # No legal targets → no PendingChoice + cast aborted.
    assert game.state.pending_choice is None, (
        "No PendingChoice should be emitted when no legal targets exist"
    )
    assert card.zone == ZoneType.HAND


def test_callable_divide_amount_x_cost_spell():
    """X-cost divide-damage: ``divide_amount`` may be a callable that
    reads the caster's lands at prompt time."""
    game = Game()
    p1 = game.add_player("P1")
    p2 = game.add_player("P2")
    bear = _add_creature(game, p2.id, "Bear")

    # 3 mountains, so X = 3.
    mountain_def = make_land("Mountain", subtypes={"Mountain"})
    for _ in range(3):
        game.create_object(
            name="Mountain",
            owner_id=p1.id,
            zone=ZoneType.BATTLEFIELD,
            characteristics=mountain_def.characteristics,
            card_def=mountain_def,
        )

    def x_budget(state, caster_id):
        # Count lands controlled by caster.
        bf = state.zones.get('battlefield')
        if not bf:
            return 0
        return sum(
            1 for oid in bf.objects
            if (o := state.objects.get(oid))
            and o.controller == caster_id
            and CardType.LAND in o.characteristics.types
        )

    XSPELL = make_instant(
        name="X Bolt",
        mana_cost="{X}{R}",
        colors={Color.RED},
        text="X Bolt deals X damage divided among any number of targets.",
        resolve=make_divide_damage_resolve(
            "X Bolt", total_damage=x_budget,
            target_filter=any_target_filter(),
        ),
        target_requirements=[
            TargetRequirement(
                filter=any_target_filter(),
                count=99,
                count_type='any_number',
                label="Allocate X damage",
                divide_amount=x_budget,
            ),
        ],
    )
    card = game.create_object(
        name=XSPELL.name,
        owner_id=p1.id,
        zone=ZoneType.HAND,
        characteristics=XSPELL.characteristics,
        card_def=XSPELL,
    )

    action = PlayerAction(
        type=ActionType.CAST_SPELL,
        player_id=p1.id,
        card_id=card.id,
        targets=[],
    )
    asyncio.run(game.priority_system._handle_cast_spell(action))
    pc = game.state.pending_choice
    assert pc is not None and pc.choice_type == "divide_allocation"
    assert pc.callback_data["total_amount"] == 3, (
        f"X-budget should be 3 (lands controlled), got "
        f"{pc.callback_data['total_amount']}"
    )


def test_ai_heuristic_targets_opponent_creature_preferentially():
    """The AIEngine.make_choice heuristic for divide_allocation should
    rank opponent creatures above own creatures and self.

    With a 2-damage budget and one opponent creature (toughness 1),
    the first allocation should land on the opponent creature for
    lethal damage; the rest may dump on the opponent player or
    secondary opponent targets but never on a friendly target."""
    from src.ai.engine import AIEngine

    game, p1, p2, bolt = _setup_game_with_twin_bolt_in_hand()
    opp_creature = _add_creature(game, p2.id, "Bear")

    action = PlayerAction(
        type=ActionType.CAST_SPELL,
        player_id=p1.id,
        card_id=bolt.id,
        targets=[],
    )
    asyncio.run(game.priority_system._handle_cast_spell(action))
    pc = game.state.pending_choice
    assert pc is not None

    ai = AIEngine(difficulty='medium')
    selected = ai.make_choice(p1.id, pc, game.state)
    # Selection is a list of dicts {target_id, amount}.
    total = sum(int(s.get('amount', 0) or 0) for s in selected)
    assert total == 2, f"AI should allocate full 2 damage, got {total}"

    # The opponent creature (lowest-cost lethal) must receive at least 1.
    by_target = {s["target_id"]: int(s.get("amount", 0) or 0) for s in selected}
    assert by_target.get(opp_creature.id, 0) >= 1, (
        f"AI should allocate at least 1 damage to opponent creature; "
        f"got {selected}"
    )
    # AI must not self-burn the casting player.
    assert by_target.get(p1.id, 0) == 0, (
        f"AI should not allocate to itself; got {selected}"
    )


def test_bare_resolve_honors_divided_amount():
    """Stand-alone bare-resolve test: feed make_divide_damage_resolve a
    list of Targets with divided_amount set; it should emit one DAMAGE
    event per non-zero allocation."""
    game = Game()
    p1 = game.add_player("Caster")
    p2 = game.add_player("Defender")

    # Manually push a Twin Bolt onto the stack so the resolver can locate it.
    spell = game.create_object(
        name="Twin Bolt",
        owner_id=p1.id,
        zone=ZoneType.STACK,
        characteristics=TWIN_BOLT.characteristics,
        card_def=TWIN_BOLT,
    )
    # The stack zone holds the spell object id.
    stack = game.state.zones.get('stack')
    if stack and spell.id not in stack.objects:
        stack.objects.append(spell.id)

    t1 = Target(id=p2.id, is_player=True, divided_amount=2)
    targets = [[t1]]

    events = TWIN_BOLT.resolve(targets, game.state)
    damage = [e for e in events if e.type == EventType.DAMAGE]
    assert len(damage) == 1, f"expected 1 DAMAGE event, got {damage}"
    assert damage[0].payload['amount'] == 2
    assert damage[0].payload['target'] == p2.id
    assert damage[0].payload['source'] == spell.id


def test_bare_resolve_falls_back_to_even_split():
    """When Targets have no divided_amount (defensive path), the resolver
    falls back to evenly splitting ``total_damage`` across them."""
    game = Game()
    p1 = game.add_player("Caster")
    p2 = game.add_player("Defender")

    spell = game.create_object(
        name="Twin Bolt",
        owner_id=p1.id,
        zone=ZoneType.STACK,
        characteristics=TWIN_BOLT.characteristics,
        card_def=TWIN_BOLT,
    )
    stack = game.state.zones.get('stack')
    if stack and spell.id not in stack.objects:
        stack.objects.append(spell.id)

    # Two targets, NO divided_amount on either → even split of 2 damage.
    t1 = Target(id=p1.id, is_player=True)
    t2 = Target(id=p2.id, is_player=True)
    events = TWIN_BOLT.resolve([[t1, t2]], game.state)
    damage = [e for e in events if e.type == EventType.DAMAGE]
    assert len(damage) == 2, f"expected 2 DAMAGE events, got {damage}"
    total = sum(e.payload['amount'] for e in damage)
    assert total == 2, f"total damage should equal 2, got {total}"


if __name__ == "__main__":
    test_cast_with_empty_targets_emits_divide_allocation()
    print("PASS  test_cast_with_empty_targets_emits_divide_allocation")
    test_submission_distributes_damage_correctly()
    print("PASS  test_submission_distributes_damage_correctly")
    test_submission_with_full_amount_on_one_target()
    print("PASS  test_submission_with_full_amount_on_one_target")
    test_validator_rejects_under_allocation()
    print("PASS  test_validator_rejects_under_allocation")
    test_validator_rejects_overallocation()
    print("PASS  test_validator_rejects_overallocation")
    test_no_legal_targets_aborts_cast()
    print("PASS  test_no_legal_targets_aborts_cast")
    test_callable_divide_amount_x_cost_spell()
    print("PASS  test_callable_divide_amount_x_cost_spell")
    test_ai_heuristic_targets_opponent_creature_preferentially()
    print("PASS  test_ai_heuristic_targets_opponent_creature_preferentially")
    test_bare_resolve_honors_divided_amount()
    print("PASS  test_bare_resolve_honors_divided_amount")
    test_bare_resolve_falls_back_to_even_split()
    print("PASS  test_bare_resolve_falls_back_to_even_split")
    print("\nAll Phase 5b divide-damage tests passed.")
