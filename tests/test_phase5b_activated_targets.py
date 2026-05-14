"""
Phase 5b — engine-authoritative cast-time target selection for ACTIVATED ABILITIES.

When ``ActivatedAbility.target_requirements`` is set and an activation arrives
without pre-supplied ``action.targets``, the priority system emits a
``PendingChoice`` via ``_emit_activate_target_choice_step`` BEFORE paying
any cost (CR 602.1: announce → choose targets → pay costs). The choice
handler re-enters the activation with targets baked in.

This file covers:
- Empty action.targets → PendingChoice emitted; mana NOT yet paid; ability
  NOT yet on the stack.
- Pre-supplied targets → no PendingChoice; legacy normal path.
- No legal targets → activation aborts; no cost paid; ability not on stack.
- Mana payment happens AT SUBMISSION TIME, not at announce time.
- PendingChoice carries ``interaction_mode='overlay'`` for frontend overlay
  rendering parity with cast-time prompts.
- Legacy ``targets_required``/``target_kind`` abilities continue working as
  before (back-compat) since they don't set ``target_requirements``.
- Wet test: Yenna activates via the new ``target_requirements`` path —
  exclusion of name collisions works through the engine handler, the chosen
  target's copy + scry effects fire after submission.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color,
    Characteristics, make_creature,
)
from src.engine.mana import ManaType
from src.engine.priority import PlayerAction, ActionType
from src.engine.targeting import (
    TargetRequirement, creature_filter,
)
from src.engine.turn import Phase
from src.cards.interceptor_helpers import make_activated_ability


def _setup_game_two_players():
    """Two-player game with P1 as active player, main phase."""
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    game.turn_manager.turn_state.active_player_id = p1.id
    game.turn_manager.turn_state.phase = Phase.PRECOMBAT_MAIN
    return game, p1, p2


def _give_mana(player, mana_system, *, generic=0):
    for _ in range(generic):
        mana_system.produce_mana(player.id, ManaType.COLORLESS, 1)


def _make_destroy_creature_with_target_requirements():
    """Build a card whose activated ability:

    ``{1},{T}: Destroy target creature you don't control.``

    Wires ``target_requirements`` (the new Phase 5b path).
    """
    def setup(obj, state):
        def effect(o, st, targets):
            if not targets:
                return []
            tgt = targets[0]
            tid = getattr(tgt, "id", None) or tgt
            return [Event(
                type=EventType.OBJECT_DESTROYED,
                payload={'object_id': tid},
                source=o.id, controller=o.controller,
            )]
        make_activated_ability(
            obj, "{1}, {T}", effect,
            description="Destroy target creature you don't control.",
            target_requirements=[
                TargetRequirement(
                    filter=creature_filter(controller='opponent'),
                    count=1,
                    label="target creature you don't control",
                ),
            ],
        )
        return []

    return make_creature(
        name="Phase5b Activator",
        power=2, toughness=2, mana_cost="{2}",
        colors=set(), subtypes={"Construct"},
        text="{1}, {T}: Destroy target creature you don't control.",
        setup_interceptors=setup,
    )


def _make_legacy_destroy_creature():
    """Card with the OLD targets_required/target_kind path (no target_requirements).
    Used to verify back-compat: activations with pre-supplied targets must
    continue working as before.
    """
    def setup(obj, state):
        def effect(o, st, targets):
            if not targets:
                return []
            tgt = targets[0]
            tid = getattr(tgt, "id", None) or tgt
            return [Event(
                type=EventType.OBJECT_DESTROYED,
                payload={'object_id': tid},
                source=o.id, controller=o.controller,
            )]
        make_activated_ability(
            obj, "{1}, {T}", effect,
            description="Destroy target creature.",
            targets_required=1,
            target_kind="creature",
        )
        return []

    return make_creature(
        name="Legacy Activator",
        power=2, toughness=2, mana_cost="{2}",
        colors=set(), subtypes={"Construct"},
        text="{1}, {T}: Destroy target creature.",
        setup_interceptors=setup,
    )


def _spawn_on_battlefield(game, player, card_def):
    obj = game.create_object(
        name=card_def.name,
        owner_id=player.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=card_def.characteristics,
        card_def=card_def,
    )
    obj.state.summoning_sickness = False
    return obj


def _spawn_vanilla_creature(game, player, name="Bear"):
    chars = Characteristics(
        types={CardType.CREATURE},
        subtypes={"Bear"},
        power=2,
        toughness=2,
    )
    obj = game.create_object(
        name=name,
        owner_id=player.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=chars,
        card_def=None,
    )
    obj.state.summoning_sickness = False
    return obj


# ---------------------------------------------------------------------------
# Core priority-system tests
# ---------------------------------------------------------------------------

def test_activate_ability_with_target_requirements_emits_pending_choice():
    """Empty action.targets + target_requirements set → PendingChoice emitted;
    mana NOT yet paid; ability NOT on stack."""
    game, p1, p2 = _setup_game_two_players()
    activator = _spawn_on_battlefield(
        game, p1, _make_destroy_creature_with_target_requirements()
    )
    victim = _spawn_vanilla_creature(game, p2, "Victim")
    _give_mana(p1, game.mana_system, generic=1)

    pre_pool = game.mana_system.get_pool(p1.id).total()
    pre_stack = game.stack.size()
    pre_tapped = activator.state.tapped

    action = PlayerAction(
        type=ActionType.ACTIVATE_ABILITY,
        player_id=p1.id, source_id=activator.id,
        ability_id="activated:0",
    )
    events = asyncio.get_event_loop().run_until_complete(
        game.priority_system._handle_activate_ability(action),
    )

    # Activation paused: PendingChoice on state, no stack push, no cost paid.
    assert events == [] or not events, f"expected paused, got {events!r}"
    pc = game.state.pending_choice
    assert pc is not None, "PendingChoice must be set"
    assert pc.player == p1.id
    assert pc.choice_type == "target"
    assert pc.source_id == activator.id
    option_ids = {opt["id"] if isinstance(opt, dict) else opt for opt in pc.options}
    assert victim.id in option_ids, (
        f"Opponent's creature should be a legal target; got {option_ids}"
    )
    assert game.mana_system.get_pool(p1.id).total() == pre_pool, (
        "Mana pool must be unchanged while activation paused"
    )
    assert game.stack.size() == pre_stack, (
        "Stack must be unchanged while activation paused"
    )
    assert activator.state.tapped == pre_tapped, (
        "Tap state must be unchanged while activation paused"
    )
    print("PASS  test_activate_ability_with_target_requirements_emits_pending_choice")


def test_activate_ability_with_pre_supplied_targets_skips_choice():
    """Pre-supplied targets → no PendingChoice; activation proceeds normally."""
    from src.engine.targeting import Target

    game, p1, p2 = _setup_game_two_players()
    activator = _spawn_on_battlefield(
        game, p1, _make_destroy_creature_with_target_requirements()
    )
    victim = _spawn_vanilla_creature(game, p2, "Victim")
    _give_mana(p1, game.mana_system, generic=1)

    action = PlayerAction(
        type=ActionType.ACTIVATE_ABILITY,
        player_id=p1.id, source_id=activator.id,
        ability_id="activated:0",
        targets=[[Target(id=victim.id)]],  # already targeted
    )
    events = asyncio.get_event_loop().run_until_complete(
        game.priority_system._handle_activate_ability(action),
    )

    # No PendingChoice; activation completed; ability on the stack.
    assert game.state.pending_choice is None, (
        "Pre-supplied targets path must NOT emit PendingChoice"
    )
    assert any(e.type == EventType.ACTIVATE for e in events), (
        f"Activation should have completed; got events={events!r}"
    )
    assert game.stack.size() == 1, "Ability should be on the stack"
    print("PASS  test_activate_ability_with_pre_supplied_targets_skips_choice")


def test_activate_ability_no_legal_targets_aborts_no_cost_paid():
    """No legal targets → activation aborts; mana pool unchanged; ability
    not on stack."""
    game, p1, _p2 = _setup_game_two_players()
    activator = _spawn_on_battlefield(
        game, p1, _make_destroy_creature_with_target_requirements()
    )
    # No opponent creature on the field — target_requirements demands one.
    _give_mana(p1, game.mana_system, generic=1)
    pre_pool = game.mana_system.get_pool(p1.id).total()

    action = PlayerAction(
        type=ActionType.ACTIVATE_ABILITY,
        player_id=p1.id, source_id=activator.id,
        ability_id="activated:0",
    )
    events = asyncio.get_event_loop().run_until_complete(
        game.priority_system._handle_activate_ability(action),
    )

    # Aborted: no PendingChoice, no events, no mana spent, nothing on stack.
    assert game.state.pending_choice is None, (
        "No PendingChoice should remain when no legal targets"
    )
    assert events == [] or not events, f"expected abort, got {events!r}"
    assert game.mana_system.get_pool(p1.id).total() == pre_pool, (
        "Mana pool must be untouched when activation aborts"
    )
    assert game.stack.size() == 0, "Ability must not be on the stack"
    assert activator.state.tapped is False, "Source must remain untapped"
    print("PASS  test_activate_ability_no_legal_targets_aborts_no_cost_paid")


def test_activate_ability_cost_paid_only_after_targets_chosen():
    """Pre-state mana pool, activate with empty targets, submit choice;
    mana is paid AT SUBMISSION TIME, not at announce time."""
    game, p1, p2 = _setup_game_two_players()
    activator = _spawn_on_battlefield(
        game, p1, _make_destroy_creature_with_target_requirements()
    )
    victim = _spawn_vanilla_creature(game, p2, "Victim")
    _give_mana(p1, game.mana_system, generic=1)
    pre_pool = game.mana_system.get_pool(p1.id).total()

    action = PlayerAction(
        type=ActionType.ACTIVATE_ABILITY,
        player_id=p1.id, source_id=activator.id,
        ability_id="activated:0",
    )
    asyncio.get_event_loop().run_until_complete(
        game.priority_system._handle_activate_ability(action),
    )

    # At announce time: no mana spent, source not tapped.
    assert game.mana_system.get_pool(p1.id).total() == pre_pool, (
        "Mana should NOT be paid at announce time"
    )
    assert activator.state.tapped is False, "Source should NOT be tapped yet"

    pc = game.state.pending_choice
    assert pc is not None

    # Submit the choice. Mana payment + tap should happen NOW.
    ok, err, _events = game.submit_choice(pc.id, p1.id, [victim.id])
    assert ok, f"submit_choice failed: {err}"
    assert game.state.pending_choice is None
    assert game.mana_system.get_pool(p1.id).total() == 0, (
        "Mana should be paid at submission time"
    )
    assert activator.state.tapped is True, "Source should be tapped after submission"
    assert game.stack.size() == 1, "Ability should be on the stack after submission"
    print("PASS  test_activate_ability_cost_paid_only_after_targets_chosen")


def test_activate_ability_carries_overlay_interaction_mode():
    """PendingChoice for activated-ability target should carry
    ``callback_data['interaction_mode']='overlay'`` for frontend overlay
    rendering (matching cast-time parity)."""
    game, p1, p2 = _setup_game_two_players()
    activator = _spawn_on_battlefield(
        game, p1, _make_destroy_creature_with_target_requirements()
    )
    _spawn_vanilla_creature(game, p2, "Victim")
    _give_mana(p1, game.mana_system, generic=1)

    action = PlayerAction(
        type=ActionType.ACTIVATE_ABILITY,
        player_id=p1.id, source_id=activator.id,
        ability_id="activated:0",
    )
    asyncio.get_event_loop().run_until_complete(
        game.priority_system._handle_activate_ability(action),
    )

    pc = game.state.pending_choice
    assert pc is not None, "PendingChoice must be set"
    assert pc.callback_data.get("interaction_mode") == "overlay", (
        "Activated-ability target PendingChoice must carry "
        f"interaction_mode='overlay'; got {pc.callback_data.get('interaction_mode')!r}"
    )
    print("PASS  test_activate_ability_carries_overlay_interaction_mode")


def test_legacy_targets_required_back_compat():
    """Legacy ability (targets_required=1, target_kind='creature', NO
    target_requirements) must continue activating the OLD way — no
    PendingChoice via the new path; pre-supplied targets remain required."""
    from src.engine.targeting import Target

    game, p1, p2 = _setup_game_two_players()
    activator = _spawn_on_battlefield(
        game, p1, _make_legacy_destroy_creature()
    )
    victim = _spawn_vanilla_creature(game, p2, "Victim")
    _give_mana(p1, game.mana_system, generic=1)

    # Confirm: no target_requirements on the ability.
    ab = activator.state.activated_abilities[0]
    assert ab.target_requirements is None, (
        "Legacy ability must not declare target_requirements"
    )
    assert ab.targets_required == 1
    assert ab.target_kind == "creature"

    # Empty-targets activation: legacy path does NOT emit a PendingChoice
    # (no target_requirements). The activation proceeds with empty targets
    # — the resolve will silently do nothing if no targets — but it must
    # NOT emit a PendingChoice via the Phase 5b path.
    action_empty = PlayerAction(
        type=ActionType.ACTIVATE_ABILITY,
        player_id=p1.id, source_id=activator.id,
        ability_id="activated:0",
    )
    events_empty = asyncio.get_event_loop().run_until_complete(
        game.priority_system._handle_activate_ability(action_empty),
    )
    assert game.state.pending_choice is None, (
        "Legacy back-compat: no PendingChoice via new path"
    )
    # Legacy behavior: ability still activates (no validation).
    assert any(e.type == EventType.ACTIVATE for e in events_empty), (
        "Legacy ability should still activate with empty targets (no validation)"
    )

    # Reset and test pre-supplied legacy path: also no PendingChoice, normal
    # activation completes.
    game2, p1b, p2b = _setup_game_two_players()
    activator2 = _spawn_on_battlefield(
        game2, p1b, _make_legacy_destroy_creature()
    )
    victim2 = _spawn_vanilla_creature(game2, p2b, "Victim2")
    _give_mana(p1b, game2.mana_system, generic=1)

    action_targeted = PlayerAction(
        type=ActionType.ACTIVATE_ABILITY,
        player_id=p1b.id, source_id=activator2.id,
        ability_id="activated:0",
        targets=[[Target(id=victim2.id)]],
    )
    events_targeted = asyncio.get_event_loop().run_until_complete(
        game2.priority_system._handle_activate_ability(action_targeted),
    )
    assert game2.state.pending_choice is None
    assert any(e.type == EventType.ACTIVATE for e in events_targeted)
    assert game2.stack.size() == 1
    print("PASS  test_legacy_targets_required_back_compat")


# ---------------------------------------------------------------------------
# Wet test: Yenna, Redtooth Regent via the new path
# ---------------------------------------------------------------------------

def test_yenna_activates_via_target_requirements_path():
    """Wet test: Yenna activates with the new target_requirements path.

    Set up:
      - Yenna on the battlefield (no summoning sickness, untapped).
      - 'Curse of Misfortunes' (a unique-name enchantment) — eligible.
      - Two 'Glass Casket' enchantments — same-name collision; both excluded.
      - {2} in mana pool for the cost.

    Activate with empty action.targets. Expect:
      - PendingChoice emitted with Curse legal, both Glass Caskets excluded.
      - Submit Curse as the chosen target.
      - Resolve the stack — OBJECT_CREATED copy event fires.
      - (Curse is not an Aura, so no UNTAP / SCRY rider for this case.)

    The key thing: the engine, not Yenna's effect_fn, is the one doing the
    name-collision filtering — proving the new target_requirements path
    works end-to-end.
    """
    from src.cards.wilds_of_eldraine import YENNA_REDTOOTH_REGENT
    from src.engine.types import GameObject, ObjectState

    game, p1, p2 = _setup_game_two_players()
    _give_mana(p1, game.mana_system, generic=2)

    yenna = game.create_object(
        name=YENNA_REDTOOTH_REGENT.name,
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=YENNA_REDTOOTH_REGENT.characteristics,
        card_def=YENNA_REDTOOTH_REGENT,
    )
    yenna.state.summoning_sickness = False

    # Two same-name enchantments (collision).
    g1 = GameObject(
        id="ench_g1", name="Glass Casket",
        characteristics=Characteristics(
            types={CardType.ENCHANTMENT}, subtypes={"Aura"},
        ),
        zone=ZoneType.BATTLEFIELD, controller=p1.id, owner=p1.id,
    )
    g1.state = ObjectState(is_token=False)
    game.state.objects[g1.id] = g1
    g2 = GameObject(
        id="ench_g2", name="Glass Casket",
        characteristics=Characteristics(
            types={CardType.ENCHANTMENT}, subtypes={"Aura"},
        ),
        zone=ZoneType.BATTLEFIELD, controller=p1.id, owner=p1.id,
    )
    g2.state = ObjectState(is_token=False)
    game.state.objects[g2.id] = g2

    # Unique-name enchantment.
    curse = GameObject(
        id="ench_curse", name="Curse of Misfortunes",
        characteristics=Characteristics(
            types={CardType.ENCHANTMENT},  # NOT an Aura — no untap rider
        ),
        zone=ZoneType.BATTLEFIELD, controller=p1.id, owner=p1.id,
    )
    curse.state = ObjectState(is_token=False)
    game.state.objects[curse.id] = curse

    # Activate Yenna.
    action = PlayerAction(
        type=ActionType.ACTIVATE_ABILITY,
        player_id=p1.id, source_id=yenna.id,
        ability_id="activated:0",
    )
    asyncio.get_event_loop().run_until_complete(
        game.priority_system._handle_activate_ability(action),
    )

    pc = game.state.pending_choice
    assert pc is not None, "Yenna must emit a target prompt via target_requirements"
    opts = {opt["id"] if isinstance(opt, dict) else opt for opt in pc.options}
    assert g1.id not in opts, f"Glass Casket #1 must be excluded; got {opts}"
    assert g2.id not in opts, f"Glass Casket #2 must be excluded; got {opts}"
    assert curse.id in opts, f"Curse (unique name) must be legal; got {opts}"

    # Submit choice → ability resolves.
    ok, err, events = game.submit_choice(pc.id, p1.id, [curse.id])
    assert ok, f"submit_choice failed: {err}"
    assert game.state.pending_choice is None

    # OBJECT_CREATED for the copy should have been produced. submit_choice
    # processes returned events through the pipeline, so the events param
    # carries the post-pipeline ones; also check that Yenna is now tapped
    # (cost paid) and her mana pool is empty (cost paid).
    assert yenna.state.tapped is True, "Yenna should be tapped after the cost is paid"
    assert game.mana_system.get_pool(p1.id).total() == 0, (
        "Mana pool should be empty after paying {2}"
    )
    # Now resolve the stack to actually fire the OBJECT_CREATED.
    resolve_events = game.stack.resolve_top()
    for ev in resolve_events:
        game.emit(ev)

    # Verify a copy-token was created (a new object with copy_of=curse.id).
    found_copy = False
    for obj in game.state.objects.values():
        if obj.id in {yenna.id, g1.id, g2.id, curse.id}:
            continue
        if obj.zone == ZoneType.BATTLEFIELD:
            found_copy = True
            break
    assert found_copy, (
        "Yenna's resolve should create a token copy of the chosen enchantment"
    )
    print("PASS  test_yenna_activates_via_target_requirements_path")


if __name__ == "__main__":
    test_activate_ability_with_target_requirements_emits_pending_choice()
    test_activate_ability_with_pre_supplied_targets_skips_choice()
    test_activate_ability_no_legal_targets_aborts_no_cost_paid()
    test_activate_ability_cost_paid_only_after_targets_chosen()
    test_activate_ability_carries_overlay_interaction_mode()
    test_legacy_targets_required_back_compat()
    test_yenna_activates_via_target_requirements_path()
    print("\nAll Phase 5b activated-target tests passed.")
