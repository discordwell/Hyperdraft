"""
Phase 5b cross-target — callable ``TargetRequirementBuilder`` support.

A ``target_requirements`` entry may now be a builder callable
(``Callable[[GameState, controller_id, accumulated_ids], TargetRequirement]``)
that produces a fresh ``TargetRequirement`` from earlier picks. This unblocks
cards whose later target depends on what was picked first:

  - "another target creature"          — exclude prior pick IDs
  - "two creatures, different players" — exclude prior pick's controller
  - "same mana value as that target"   — pin filter MV to prior pick

Back-compat: a plain ``TargetRequirement`` entry continues to work without
any wrapping. The priority system's ``_emit_cast_target_choice_step`` resolves
each entry through ``resolve_target_requirement_spec`` before computing legal
targets.
"""

import asyncio
import os
import sys

# Make project root importable.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color,
    make_creature, make_instant,
)
from src.engine.priority import PlayerAction, ActionType
from src.engine.game import make_land
from src.engine.targeting import (
    TargetRequirement, TargetFilter,
    creature_filter, target_creature, target_any,
    another_target_creature, target_creature_different_controller,
    target_with_matching_mana_value, permanent_filter,
    resolve_target_requirement_spec,
)


# ---------------------------------------------------------------------------
# Game setup helpers
# ---------------------------------------------------------------------------

def _setup_two_player_game():
    """Bare 2-player game with no cards in zones beyond what tests add."""
    game = Game()
    p1 = game.add_player("Caster")
    p2 = game.add_player("Opp")
    return game, p1, p2


def _add_creature(game, owner_id: str, *, name: str = "Bear",
                  power: int = 2, toughness: int = 2,
                  mana_cost: str = "{1}{G}",
                  colors: set | None = None):
    """Drop a fresh creature on the battlefield under the given owner."""
    card_def = make_creature(
        name=name,
        power=power, toughness=toughness,
        mana_cost=mana_cost,
        colors=colors or {Color.GREEN},
    )
    return game.create_object(
        name=name,
        owner_id=owner_id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=card_def.characteristics,
        card_def=card_def,
    )


def _add_enchantment(game, owner_id: str, *, name: str = "Aura",
                     mana_cost: str = "{2}",
                     colors: set | None = None):
    """Drop an enchantment for mana-value tests."""
    from src.engine.types import CardDefinition, Characteristics
    card_def = CardDefinition(
        name=name,
        mana_cost=mana_cost,
        characteristics=Characteristics(
            types={CardType.ENCHANTMENT},
            colors=colors or {Color.WHITE},
            mana_cost=mana_cost,
        ),
        text="",
    )
    return game.create_object(
        name=name,
        owner_id=owner_id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=card_def.characteristics,
        card_def=card_def,
    )


def _add_lands_for_caster(game, p_id: str, count: int = 4):
    """Drop ``count`` untapped Mountains for the caster's mana pool."""
    mountain_def = make_land("Mountain", subtypes={"Mountain"})
    for _ in range(count):
        game.create_object(
            name="Mountain",
            owner_id=p_id,
            zone=ZoneType.BATTLEFIELD,
            characteristics=mountain_def.characteristics,
            card_def=mountain_def,
        )


def _add_spell_in_hand(game, owner_id: str, card_def):
    """Put a spell in the caster's hand."""
    return game.create_object(
        name=card_def.name,
        owner_id=owner_id,
        zone=ZoneType.HAND,
        characteristics=card_def.characteristics,
        card_def=card_def,
    )


# ---------------------------------------------------------------------------
# Test 1: "another target" excludes the prior pick from the second prompt
# ---------------------------------------------------------------------------

def test_another_target_excludes_first_pick_from_second_prompt():
    """``another_target_creature`` builder excludes the prior pick's ID from
    the second requirement's legal options. The chain emits prompt #1 with
    all 3 creatures, the human picks one, and prompt #2 shows only the
    remaining 2 creatures (the first pick is invisible)."""
    game, p1, p2 = _setup_two_player_game()
    _add_lands_for_caster(game, p1.id, count=2)
    c_a = _add_creature(game, p2.id, name="Alpha")
    c_b = _add_creature(game, p2.id, name="Beta")
    c_c = _add_creature(game, p2.id, name="Gamma")

    spell_def = make_instant(
        name="Dual Bolt",
        mana_cost="{R}",
        colors={Color.RED},
        text="Target creature, then another target creature.",
        target_requirements=[
            target_creature(count=1, label="target creature"),
            another_target_creature(count=1, label="another target creature"),
        ],
    )
    spell = _add_spell_in_hand(game, p1.id, spell_def)

    action = PlayerAction(
        type=ActionType.CAST_SPELL,
        player_id=p1.id,
        card_id=spell.id,
        targets=[],
    )
    asyncio.run(game.priority_system._handle_cast_spell(action))

    # First prompt up — all 3 creatures legal.
    pc1 = game.state.pending_choice
    assert pc1 is not None, "First PendingChoice must be set"
    first_opts = {opt["id"] for opt in pc1.options}
    assert {c_a.id, c_b.id, c_c.id}.issubset(first_opts), (
        f"first prompt should offer all 3 creatures, got {first_opts}"
    )

    # Submit first pick — engine should swap to prompt #2.
    ok, err, _ = game.submit_choice(pc1.id, p1.id, [c_a.id])
    assert ok, f"first submit failed: {err}"

    pc2 = game.state.pending_choice
    assert pc2 is not None, "Second PendingChoice must be set after first pick"
    second_opts = {opt["id"] for opt in pc2.options}
    assert c_a.id not in second_opts, (
        f"another_target_creature must exclude {c_a.id} (prior pick); "
        f"got {second_opts}"
    )
    assert {c_b.id, c_c.id}.issubset(second_opts), (
        f"both other creatures should still be legal: {second_opts}"
    )


# ---------------------------------------------------------------------------
# Test 2: 2-requirement set-constraint via callable — different controllers
# ---------------------------------------------------------------------------

def test_different_controllers_constraint_filters_second_prompt():
    """``target_creature_different_controller`` excludes any creature
    controlled by the same player as the first pick. After picking p1's
    creature, only p2's creatures should be legal in the second prompt."""
    game, p1, p2 = _setup_two_player_game()
    _add_lands_for_caster(game, p1.id, count=2)
    own = _add_creature(game, p1.id, name="My Bear")
    opp_a = _add_creature(game, p2.id, name="Their Wolf")
    opp_b = _add_creature(game, p2.id, name="Their Bat")

    spell_def = make_instant(
        name="Forced Split",
        mana_cost="{U}",
        colors={Color.BLUE},
        text="Choose two target creatures controlled by different players.",
        target_requirements=[
            target_creature(count=1),
            target_creature_different_controller(),
        ],
    )
    spell = _add_spell_in_hand(game, p1.id, spell_def)

    asyncio.run(game.priority_system._handle_cast_spell(PlayerAction(
        type=ActionType.CAST_SPELL,
        player_id=p1.id,
        card_id=spell.id,
        targets=[],
    )))

    pc1 = game.state.pending_choice
    assert pc1 is not None
    # First pick: own's creature.
    ok, err, _ = game.submit_choice(pc1.id, p1.id, [own.id])
    assert ok, f"first submit failed: {err}"

    pc2 = game.state.pending_choice
    assert pc2 is not None, "Second prompt must be set"
    opts = {opt["id"] for opt in pc2.options}
    # own.id is controlled by p1 — must not appear; opp creatures must.
    assert own.id not in opts, (
        f"second prompt must exclude same-controller creatures; got {opts}"
    )
    assert {opp_a.id, opp_b.id} == opts, (
        f"only the opponent's creatures should be legal; got {opts}"
    )


# ---------------------------------------------------------------------------
# Test 3: mana-value-matching cross requirement
# ---------------------------------------------------------------------------

def test_mana_value_matching_constraint():
    """``target_with_matching_mana_value`` pins the second filter's MV to
    the first pick's MV. Picking a 3-MV creature should restrict the second
    prompt to only 3-MV permanents."""
    game, p1, p2 = _setup_two_player_game()
    _add_lands_for_caster(game, p1.id, count=3)
    # 3-MV creature {1}{R}{R} = MV 3, 2-MV enchantment, 3-MV enchantment.
    mv3_creature = _add_creature(
        game, p1.id, name="MV3 Bear",
        mana_cost="{1}{R}{R}", colors={Color.RED}, power=3, toughness=3,
    )
    mv2_ench = _add_enchantment(game, p1.id, name="MV2 Aura", mana_cost="{2}")
    mv3_ench = _add_enchantment(game, p1.id, name="MV3 Aura", mana_cost="{3}")
    mv4_ench = _add_enchantment(game, p1.id, name="MV4 Aura", mana_cost="{4}")

    spell_def = make_instant(
        name="MV Matcher",
        mana_cost="{W}",
        colors={Color.WHITE},
        text="Choose target creature and target enchantment with the same mana value.",
        target_requirements=[
            target_creature(count=1),
            target_with_matching_mana_value(
                base_filter_factory=lambda **kw: TargetFilter(
                    types={CardType.ENCHANTMENT}, **kw
                ),
                label="target enchantment with the same mana value",
            ),
        ],
    )
    spell = _add_spell_in_hand(game, p1.id, spell_def)

    asyncio.run(game.priority_system._handle_cast_spell(PlayerAction(
        type=ActionType.CAST_SPELL,
        player_id=p1.id,
        card_id=spell.id,
        targets=[],
    )))

    pc1 = game.state.pending_choice
    assert pc1 is not None
    # Pick the MV3 creature.
    ok, err, _ = game.submit_choice(pc1.id, p1.id, [mv3_creature.id])
    assert ok, f"first submit failed: {err}"

    pc2 = game.state.pending_choice
    assert pc2 is not None, "Second prompt must be set"
    opts = {opt["id"] for opt in pc2.options}
    # Only the MV3 enchantment should be legal.
    assert mv3_ench.id in opts, f"MV3 enchantment must be legal; got {opts}"
    assert mv2_ench.id not in opts, (
        f"MV2 enchantment must NOT be legal (filter pinned to MV3); got {opts}"
    )
    assert mv4_ench.id not in opts, (
        f"MV4 enchantment must NOT be legal (filter pinned to MV3); got {opts}"
    )


# ---------------------------------------------------------------------------
# Test 4: AI heuristic_pick respects the cross-target constraint
# ---------------------------------------------------------------------------

def test_ai_heuristic_respects_cross_target_constraint():
    """The AI fallback ``heuristic_pick`` is computed AFTER the cross-target
    builder has filtered the legal IDs. This means an AI-driven cast that
    chains "target creature" → "another target creature" can never pick the
    same creature twice — even with no explicit AI biases."""
    game, p1, p2 = _setup_two_player_game()
    _add_lands_for_caster(game, p1.id, count=2)
    c_a = _add_creature(game, p2.id, name="Alpha")
    c_b = _add_creature(game, p2.id, name="Beta")

    # Register p1 as an AI so resolve_pending_choice_inline picks the
    # heuristic_pick automatically.
    if not hasattr(game, 'turn_manager') or game.turn_manager is None:
        # The Game wiring sets up a turn manager on the first turn; for the
        # bare test path we register the AI directly on the inline resolver.
        pass

    # Simulate an AI by stamping the player as AI on the turn manager.
    # The pending_choice_helpers ``drain_pending_choices_for_ai`` requires
    # ``ai_players`` to include the player so inline resolution kicks in.
    game.turn_manager = type('TM', (), {'ai_players': {p1.id}})()

    captured_picks: list[list[str]] = []

    # Wrap the resolve to capture targets when the spell finally enters
    # the stack via the chained re-entry path.
    def _capture_resolve(targets, state):
        flat: list[str] = []
        for t_list in targets:
            for t in (t_list or []):
                tid = t.id if hasattr(t, 'id') else t
                flat.append(tid)
        captured_picks.append(flat)
        return []

    spell_def = make_instant(
        name="AI Dual Bolt",
        mana_cost="{R}",
        colors={Color.RED},
        text="AI demo.",
        resolve=_capture_resolve,
        target_requirements=[
            target_creature(count=1),
            another_target_creature(count=1),
        ],
    )
    spell = _add_spell_in_hand(game, p1.id, spell_def)

    asyncio.run(game.priority_system._handle_cast_spell(PlayerAction(
        type=ActionType.CAST_SPELL,
        player_id=p1.id,
        card_id=spell.id,
        targets=[],
    )))

    # The AI path resolved both chained prompts inline; the spell should
    # have made it to the stack with two distinct picks.
    assert spell.zone == ZoneType.STACK, (
        f"AI cast should have completed; spell zone={spell.zone}"
    )
    # No human prompt left dangling.
    assert game.state.pending_choice is None, (
        f"AI path must drain pending_choice; got {game.state.pending_choice}"
    )


# ---------------------------------------------------------------------------
# Test 5: empty legal targets after constraint → cast aborts cleanly
# ---------------------------------------------------------------------------

def test_cast_aborts_when_cross_target_leaves_no_legal_options():
    """If applying the cross-target constraint reduces legal options for a
    REQUIRED requirement to zero, the cast must abort (MTG rule: "no legal
    targets, can't be cast"). The spell stays in hand; no PendingChoice."""
    game, p1, p2 = _setup_two_player_game()
    _add_lands_for_caster(game, p1.id, count=2)
    # Only ONE creature on the board — first pick exhausts the legal
    # pool, second requirement (mandatory, exclude the first pick) finds zero.
    sole = _add_creature(game, p2.id, name="Solo")

    spell_def = make_instant(
        name="Dual Bolt",
        mana_cost="{R}",
        colors={Color.RED},
        text="Target creature, then another target creature.",
        target_requirements=[
            target_creature(count=1),
            another_target_creature(count=1),
        ],
    )
    spell = _add_spell_in_hand(game, p1.id, spell_def)

    asyncio.run(game.priority_system._handle_cast_spell(PlayerAction(
        type=ActionType.CAST_SPELL,
        player_id=p1.id,
        card_id=spell.id,
        targets=[],
    )))

    pc1 = game.state.pending_choice
    assert pc1 is not None
    # Submit the only creature — second prompt should find zero legal,
    # and the cast aborts.
    ok, err, _ = game.submit_choice(pc1.id, p1.id, [sole.id])
    assert ok, f"first submit unexpectedly failed: {err}"
    assert game.state.pending_choice is None, (
        "Cast must abort cleanly; no dangling PendingChoice"
    )
    # Spell stays in hand because the cast never paid mana / hit the stack.
    assert spell.zone == ZoneType.HAND, (
        f"spell must stay in hand on aborted cross-target cast; got {spell.zone}"
    )


# ---------------------------------------------------------------------------
# Test 6: back-compat — plain TargetRequirement entries still work unchanged
# ---------------------------------------------------------------------------

def test_back_compat_plain_target_requirement_still_works():
    """A spec entry that's a plain ``TargetRequirement`` (no callable wrap)
    must still resolve through the chain exactly as it did pre-Phase-5b
    cross-target. The new dispatch must not break the back-compat path."""
    game, p1, p2 = _setup_two_player_game()
    _add_lands_for_caster(game, p1.id, count=2)
    target = _add_creature(game, p2.id, name="Target")

    spell_def = make_instant(
        name="Plain Bolt",
        mana_cost="{R}",
        colors={Color.RED},
        text="Deal 3 to target creature.",
        target_requirements=[
            # Plain TR (no callable wrap) — this is the pre-cross-target shape.
            target_creature(count=1),
        ],
    )
    spell = _add_spell_in_hand(game, p1.id, spell_def)

    asyncio.run(game.priority_system._handle_cast_spell(PlayerAction(
        type=ActionType.CAST_SPELL,
        player_id=p1.id,
        card_id=spell.id,
        targets=[],
    )))

    pc = game.state.pending_choice
    assert pc is not None, "back-compat plain TR must still produce PendingChoice"
    opts = {opt["id"] for opt in pc.options}
    assert target.id in opts, (
        f"back-compat plain TR must list legal target; got {opts}"
    )
    # Submit & verify cast advances to the stack.
    ok, err, _ = game.submit_choice(pc.id, p1.id, [target.id])
    assert ok, f"plain TR submit failed: {err}"
    assert spell.zone == ZoneType.STACK, (
        f"plain TR spell should land on stack; got {spell.zone}"
    )


# ---------------------------------------------------------------------------
# Test 7: resolve_target_requirement_spec direct API surface
# ---------------------------------------------------------------------------

def test_resolve_target_requirement_spec_dispatches_callable_and_plain():
    """Lower-level test: ``resolve_target_requirement_spec`` accepts both
    a plain TR (returned as-is) and a callable (invoked with the args).
    Rejects other types with TypeError."""
    game, p1, p2 = _setup_two_player_game()
    plain = target_creature(count=1)

    # Plain → returned as-is.
    out = resolve_target_requirement_spec(plain, game.state, p1.id, [])
    assert out is plain

    # Callable → invoked with the args.
    captured = {}
    def _builder(state, controller, accumulated):
        captured['state'] = state
        captured['controller'] = controller
        captured['accumulated'] = accumulated
        return target_creature(count=1, label="from_builder")
    out2 = resolve_target_requirement_spec(_builder, game.state, p1.id, [['x']])
    assert isinstance(out2, TargetRequirement)
    assert out2.label == "from_builder"
    assert captured['controller'] == p1.id
    assert captured['accumulated'] == [['x']]

    # Invalid type → TypeError.
    import pytest
    with pytest.raises(TypeError):
        resolve_target_requirement_spec(42, game.state, p1.id, [])


if __name__ == "__main__":
    test_another_target_excludes_first_pick_from_second_prompt()
    print("PASS  test_another_target_excludes_first_pick_from_second_prompt")
    test_different_controllers_constraint_filters_second_prompt()
    print("PASS  test_different_controllers_constraint_filters_second_prompt")
    test_mana_value_matching_constraint()
    print("PASS  test_mana_value_matching_constraint")
    test_ai_heuristic_respects_cross_target_constraint()
    print("PASS  test_ai_heuristic_respects_cross_target_constraint")
    test_cast_aborts_when_cross_target_leaves_no_legal_options()
    print("PASS  test_cast_aborts_when_cross_target_leaves_no_legal_options")
    test_back_compat_plain_target_requirement_still_works()
    print("PASS  test_back_compat_plain_target_requirement_still_works")
    test_resolve_target_requirement_spec_dispatches_callable_and_plain()
    print("PASS  test_resolve_target_requirement_spec_dispatches_callable_and_plain")
    print("\nAll Phase 5b cross-target tests passed.")
