"""Tests for three small engine extensions:

(1) Exhaust reset: a card grants the right to re-activate an Exhaust
    ability that was already used (Aetherdrift "Elvish Refueler" pattern).
    The fix adds ``reset_exhaust(state, ...)`` and an EXHAUST_RESET marker
    event so observers can react.

(2) "Exile N cards from your graveyard" as an activated-ability cost.
    Already lived in the casting-cost cost-plan vocabulary (CostStep
    kind ``exile_from_graveyard``), but ``can_pay_activation`` and
    ``pay_activation_cost`` did not validate / pay it. Now they do.

(3) "Sacrifice <Named Card>" as an activated-ability cost. The cost
    parser previously only recognised "Sacrifice this" / "Sacrifice
    this <type>" (matched relative to the registering object's name).
    For granted abilities (e.g. Deconstruction Hammer's effect lives on
    the equipped creature, not the equipment), the parser silently
    dropped the phrase. The fix adds a new ``sacrifice_named`` step
    kind that holds the literal name; cost-validation looks for any
    battlefield permanent the player controls whose name matches.

Affected real cards (in W20-claimed src/cards/aetherdrift.py and so
NOT touched here):
- Elvish Refueler — exhaust reset target.
- Winter, Cursed Rider — exile-X-from-graveyard activated cost.
- Deconstruction Hammer (LCI, W6 workaround) — would benefit from the
  parser fix; we keep the existing workaround in place but show the
  parser now produces a usable plan.

Tests use synthetic cards so this file never touches a claimed set.
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_HERE)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import asyncio

from src.engine import (
    Game, Event, EventType, ZoneType, Color, CardType,
    make_creature, make_artifact,
)
from src.engine.activated import (
    parse_activation_cost,
    reset_exhaust,
)
from src.engine.casting_costs import (
    parse_cost_expression,
    CostStep,
)
from src.engine.priority import ActionType, PlayerAction
from src.engine.turn import Phase
from src.cards.interceptor_helpers import (
    make_exhaust_ability,
    make_exhaust_reset_effect,
    make_activated_ability,
)


# ---------------------------------------------------------------------------
# Test helpers (mirrors test_exhaust.py / test_activated_abilities.py).
# ---------------------------------------------------------------------------


def _setup_game_for_player(p_id, game):
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


def _stash_in_graveyard(game, player, card_def, count):
    """Create ``count`` GameObjects in the player's graveyard."""
    gy_key = f"graveyard_{player.id}"
    gy = game.state.zones[gy_key]
    out = []
    for _ in range(count):
        stub = game.create_object(
            name=card_def.name,
            owner_id=player.id,
            zone=ZoneType.GRAVEYARD,
            characteristics=card_def.characteristics,
            card_def=None,
        )
        stub.card_def = card_def
        if stub.id not in gy.objects:
            gy.objects.append(stub.id)
        out.append(stub)
    return out


# ---------------------------------------------------------------------------
# (1) Exhaust reset
# ---------------------------------------------------------------------------


def _make_pump_exhaust_card(name="Test Exhaust"):
    """Synthetic creature with an Exhaust — {1}: +1/+1 counter ability."""

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
        text="Exhaust — {1}: Put a +1/+1 counter on this creature.",
        setup_interceptors=setup,
    )


def test_reset_exhaust_clears_used_flag():
    """Activate Exhaust, mark used; reset_exhaust clears the flag; activate again."""
    async def _run():
        game = Game()
        p1 = game.add_player("Alice")
        p2 = game.add_player("Bob")
        _setup_game_for_player(p1.id, game)

        card = _make_pump_exhaust_card("Refuelable")
        obj = _spawn_on_battlefield(game, p1, card)
        obj.state.summoning_sickness = False
        _give_player_mana(p1, game.mana_system, generic=2)

        # First activation succeeds and locks the ability.
        action = PlayerAction(
            type=ActionType.ACTIVATE_ABILITY,
            player_id=p1.id, source_id=obj.id,
            ability_id="activated:0",
        )
        first = await game.priority_system._handle_activate_ability(action)
        assert any(e.type == EventType.ACTIVATE for e in first), \
            "first activation should succeed"
        ab = obj.state.activated_abilities[0]
        assert ab.once_per_game_used is True

        # Reset: targeted directly.
        n = reset_exhaust(game.state, target_id=obj.id)
        assert n == 1, f"expected 1 reset, got {n}"
        assert ab.once_per_game_used is False, \
            "once_per_game_used must be cleared after reset"

        # Re-activation now succeeds.
        _give_player_mana(p1, game.mana_system, generic=1)
        again = await game.priority_system._handle_activate_ability(action)
        assert any(e.type == EventType.ACTIVATE for e in again), \
            "second activation after reset should succeed"
        assert ab.once_per_game_used is True
        print("PASS: reset_exhaust clears once_per_game_used and re-activation succeeds")

    asyncio.get_event_loop().run_until_complete(_run())


def test_reset_exhaust_unused_is_noop():
    """Resetting an Exhaust that has not been used returns 0 and does not flip flags."""
    game = Game()
    p1 = game.add_player("Alice")
    _setup_game_for_player(p1.id, game)
    card = _make_pump_exhaust_card("Pristine")
    obj = _spawn_on_battlefield(game, p1, card)

    n = reset_exhaust(game.state, target_id=obj.id)
    assert n == 0, f"unused reset should return 0, got {n}"
    ab = obj.state.activated_abilities[0]
    assert ab.once_per_game_used is False
    print("PASS: reset_exhaust on unused ability is a no-op")


def test_reset_exhaust_by_controller():
    """Controller-scoped reset clears every Exhaust on that player's permanents."""
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    _setup_game_for_player(p1.id, game)

    card = _make_pump_exhaust_card("Twin")
    a = _spawn_on_battlefield(game, p1, card)
    b = _spawn_on_battlefield(game, p1, card)
    c = _spawn_on_battlefield(game, p2, card)

    # Mark all three as used.
    for o in (a, b, c):
        o.state.activated_abilities[0].once_per_game_used = True

    # Reset only Alice's permanents.
    n = reset_exhaust(game.state, controller=p1.id)
    assert n == 2, f"expected 2 resets (Alice's two creatures), got {n}"
    assert a.state.activated_abilities[0].once_per_game_used is False
    assert b.state.activated_abilities[0].once_per_game_used is False
    assert c.state.activated_abilities[0].once_per_game_used is True, \
        "Bob's creature must remain locked"
    print("PASS: controller-scoped reset_exhaust ignores opponent permanents")


def test_make_exhaust_reset_effect_emits_marker():
    """The helper resets and returns an EXHAUST_RESET marker event."""
    game = Game()
    p1 = game.add_player("Alice")
    _setup_game_for_player(p1.id, game)

    card = _make_pump_exhaust_card("Refueler")
    obj = _spawn_on_battlefield(game, p1, card)
    ab = obj.state.activated_abilities[0]
    ab.once_per_game_used = True

    events = make_exhaust_reset_effect(obj, game.state, controller=p1.id)
    assert len(events) == 1
    assert events[0].type == EventType.EXHAUST_RESET
    assert events[0].payload.get('controller') == p1.id
    assert ab.once_per_game_used is False, "helper should reset immediately"
    print("PASS: make_exhaust_reset_effect emits EXHAUST_RESET and resets")


def test_exhaust_reset_event_handler_resets_via_pipeline():
    """Emitting EXHAUST_RESET through the pipeline resets the descriptor."""
    async def _run():
        game = Game()
        p1 = game.add_player("Alice")
        p2 = game.add_player("Bob")
        _setup_game_for_player(p1.id, game)

        card = _make_pump_exhaust_card("Pipelined")
        obj = _spawn_on_battlefield(game, p1, card)
        ab = obj.state.activated_abilities[0]
        ab.once_per_game_used = True

        # Emit the event directly; pipeline routes it to _handle_exhaust_reset.
        game.emit(Event(
            type=EventType.EXHAUST_RESET,
            payload={'target_id': obj.id},
            source=obj.id,
            controller=p1.id,
        ))
        assert ab.once_per_game_used is False, \
            "EXHAUST_RESET event should clear the flag via the pipeline handler"
        print("PASS: EXHAUST_RESET pipeline handler resets the descriptor")

    asyncio.get_event_loop().run_until_complete(_run())


# ---------------------------------------------------------------------------
# (2) Exile-from-graveyard as activated-ability cost
# ---------------------------------------------------------------------------


def test_parse_exile_from_gy_activation_cost():
    """parse_activation_cost recognises 'Exile N cards from your graveyard'."""
    m, t, s, ds, es, plan, ctr = parse_activation_cost(
        "Exile two cards from your graveyard, {1}{B}",
        source_name="Tester",
    )
    assert m is not None, "mana cost {1}{B} should parse"
    assert m.generic == 1 and m.black == 1
    assert plan is not None and len(plan) == 1
    step = plan[0]
    assert step.kind == "exile_from_graveyard"
    assert step.amount == 2
    assert step.count_is_x is False, "literal 'two' should not set count_is_x"
    assert step.subtype_filter is None, "untyped form should leave subtype_filter None"
    print("PASS: 'Exile two cards from your graveyard' parses into a CostPlan step")


def test_parse_exile_from_gy_x_count():
    """W27: 'Exile X cards from your graveyard' sets count_is_x=True."""
    plan = parse_cost_expression("Exile X cards from your graveyard")
    assert plan is not None and len(plan) == 1
    step = plan[0]
    assert step.kind == "exile_from_graveyard"
    assert step.count_is_x is True
    assert step.subtype_filter is None
    assert step.amount == 0
    print("PASS: 'Exile X cards from your graveyard' parses with count_is_x=True")


def test_parse_exile_from_gy_typed_filter():
    """W27: 'Exile two artifact cards from your graveyard' sets subtype_filter."""
    plan = parse_cost_expression("Exile two artifact cards from your graveyard")
    assert plan is not None and len(plan) == 1
    step = plan[0]
    assert step.kind == "exile_from_graveyard"
    assert step.amount == 2
    assert step.count_is_x is False
    assert step.subtype_filter == CardType.ARTIFACT
    print("PASS: 'Exile two artifact cards' parses with subtype_filter=ARTIFACT")


def test_parse_exile_from_gy_x_with_typed_filter():
    """W27: 'Exile X artifact cards from your graveyard' sets both."""
    plan = parse_cost_expression("Exile X artifact cards from your graveyard")
    assert plan is not None and len(plan) == 1
    step = plan[0]
    assert step.kind == "exile_from_graveyard"
    assert step.count_is_x is True
    assert step.subtype_filter == CardType.ARTIFACT
    print("PASS: 'Exile X artifact cards' parses with count_is_x + ARTIFACT filter")


def test_parse_exile_from_gy_creature_filter():
    """W27: typed filter handles other types too (creature, etc.)."""
    plan = parse_cost_expression("Exile three creature cards from your graveyard")
    assert plan is not None and len(plan) == 1
    step = plan[0]
    assert step.kind == "exile_from_graveyard"
    assert step.amount == 3
    assert step.subtype_filter == CardType.CREATURE
    print("PASS: 'Exile three creature cards' parses with subtype_filter=CREATURE")


def test_exile_from_gy_typed_filter_blocks_when_not_enough_typed():
    """W27: typed filter gates legality on typed-only count."""
    async def _run():
        game = Game()
        p1 = game.add_player("Alice")
        p2 = game.add_player("Bob")
        _setup_game_for_player(p1.id, game)

        nonart = make_creature(
            name="Filler", power=1, toughness=1, mana_cost="{1}",
            colors=set(), subtypes={"Spirit"}, text="",
        )
        artifact = make_artifact(name="Bauble", mana_cost="{1}", text="")

        def setup(obj, state):
            def _effect(o, st, targets):
                return [Event(
                    type=EventType.LIFE_CHANGE,
                    payload={'player': o.controller, 'amount': 3},
                    source=o.id, controller=o.controller,
                )]
            make_activated_ability(
                obj,
                cost="Exile two artifact cards from your graveyard, {1}{B}",
                effect_fn=_effect,
                description="Gain 3 life.",
            )
            return []

        card = make_creature(
            name="Sap-Sucker", power=2, toughness=2, mana_cost="{B}",
            colors={Color.BLACK}, subtypes={"Vampire"},
            text="Exile two artifact cards from your graveyard, {1}{B}: gain 3 life.",
            setup_interceptors=setup,
        )
        obj = _spawn_on_battlefield(game, p1, card)
        obj.state.summoning_sickness = False
        _give_player_mana(p1, game.mana_system, generic=1, black=1)

        # Empty graveyard -> blocked.
        action = PlayerAction(
            type=ActionType.ACTIVATE_ABILITY,
            player_id=p1.id, source_id=obj.id,
            ability_id="activated:0",
        )
        events = await game.priority_system._handle_activate_ability(action)
        assert not any(e.type == EventType.ACTIVATE for e in events), \
            "empty GY should block activation"

        # Add 2 NON-artifact cards -> still blocked (typed filter requires
        # 2 artifacts).
        _stash_in_graveyard(game, p1, nonart, 2)
        events = await game.priority_system._handle_activate_ability(action)
        assert not any(e.type == EventType.ACTIVATE for e in events), \
            "GY with 2 non-artifacts should still block (typed filter)"

        # Add 2 artifacts -> now OK.
        _stash_in_graveyard(game, p1, artifact, 2)
        _give_player_mana(p1, game.mana_system, generic=1, black=1)
        events = await game.priority_system._handle_activate_ability(action)
        assert any(e.type == EventType.ACTIVATE for e in events), \
            "GY with 2 artifacts (+ noise) should allow activation"
        # And the EXILE events target the artifacts only.
        exile_events = [e for e in events if e.type == EventType.EXILE]
        assert len(exile_events) == 2
        for ev in exile_events:
            cid = ev.payload['object_id']
            cobj = game.state.objects.get(cid)
            assert cobj is not None
            assert CardType.ARTIFACT in cobj.characteristics.types, \
                f"exiled card {cid} must be artifact-typed"
        print("PASS: typed exile-from-GY filter gates legality + exiles only typed cards")

    asyncio.get_event_loop().run_until_complete(_run())


def test_exile_from_gy_x_count_uses_action_x_value():
    """W27: count_is_x cost reads action.x_value at validation/payment time."""
    async def _run():
        from src.engine.activated import can_pay_activation, pay_activation_cost

        game = Game()
        p1 = game.add_player("Alice")
        p2 = game.add_player("Bob")
        _setup_game_for_player(p1.id, game)

        filler = make_creature(
            name="Filler", power=1, toughness=1, mana_cost="{1}",
            colors=set(), subtypes={"Spirit"}, text="",
        )

        def setup(obj, state):
            def _effect(o, st, targets, x_value=0):
                return [Event(
                    type=EventType.LIFE_CHANGE,
                    payload={'player': o.controller, 'amount': int(x_value)},
                    source=o.id, controller=o.controller,
                )]
            make_activated_ability(
                obj,
                cost="{X}{B}, Exile X cards from your graveyard",
                effect_fn=_effect,
                description="Gain X life.",
            )
            return []

        card = make_creature(
            name="X-User", power=1, toughness=1, mana_cost="{B}",
            colors={Color.BLACK}, subtypes={"Vampire"},
            text="{X}{B}, Exile X cards from your graveyard: Gain X life.",
            setup_interceptors=setup,
        )
        obj = _spawn_on_battlefield(game, p1, card)
        obj.state.summoning_sickness = False

        ex = obj.state.activated_abilities[0]
        plan = ex.additional_cost_plan
        assert plan is not None and len(plan) == 1
        step = plan[0]
        assert step.kind == "exile_from_graveyard"
        assert step.count_is_x is True
        assert step.subtype_filter is None

        # Empty graveyard. x=0 should be legal (need 0 cards).
        _give_player_mana(p1, game.mana_system, black=1)
        assert can_pay_activation(
            ex, obj, game.state, p1.id,
            mana_system=game.mana_system,
            is_active_player=True, is_main_phase=True, stack_empty=True,
            x_value=0,
        ), "x=0 with empty GY should be legal (count_is_x)"

        # x=2 with empty graveyard fails.
        assert not can_pay_activation(
            ex, obj, game.state, p1.id,
            mana_system=game.mana_system,
            is_active_player=True, is_main_phase=True, stack_empty=True,
            x_value=2,
        ), "x=2 with empty GY must be illegal (count_is_x)"

        # Stash 3 cards. x=2 now legal.
        gy_stubs = _stash_in_graveyard(game, p1, filler, 3)
        _give_player_mana(p1, game.mana_system, generic=2)
        assert can_pay_activation(
            ex, obj, game.state, p1.id,
            mana_system=game.mana_system,
            is_active_player=True, is_main_phase=True, stack_empty=True,
            x_value=2,
        ), "x=2 with 3 GY cards should be legal"

        # Pay with x=2: cost should yield 2 EXILE events.
        cost_events = pay_activation_cost(
            ex, obj, game.state, p1.id,
            mana_system=game.mana_system,
            x_value=2,
        )
        exile_events = [e for e in cost_events if e.type == EventType.EXILE]
        assert len(exile_events) == 2, \
            f"x=2 should emit 2 EXILE events, got {len(exile_events)}"
        # The exiled ids should be from the GY stubs.
        gy_ids = {s.id for s in gy_stubs}
        for ev in exile_events:
            assert ev.payload['object_id'] in gy_ids
        print("PASS: 'Exile X cards from your graveyard' honours action.x_value")

    asyncio.get_event_loop().run_until_complete(_run())


def test_exile_from_gy_cost_blocks_when_insufficient():
    """Activation is denied if the player's graveyard has fewer than N cards."""
    async def _run():
        game = Game()
        p1 = game.add_player("Alice")
        p2 = game.add_player("Bob")
        _setup_game_for_player(p1.id, game)

        filler = make_creature(
            name="Filler", power=1, toughness=1, mana_cost="{1}",
            colors=set(), subtypes={"Spirit"}, text="",
        )

        def setup(obj, state):
            def _effect(o, st, targets):
                return [Event(
                    type=EventType.LIFE_CHANGE,
                    payload={'player': o.controller, 'amount': 3},
                    source=o.id, controller=o.controller,
                )]
            make_activated_ability(
                obj,
                cost="Exile two cards from your graveyard, {1}{B}",
                effect_fn=_effect,
                description="Gain 3 life.",
            )
            return []

        card = make_creature(
            name="Sap-Sucker", power=2, toughness=2, mana_cost="{B}",
            colors={Color.BLACK}, subtypes={"Vampire"},
            text="Exile two cards from your graveyard, {1}{B}: You gain 3 life.",
            setup_interceptors=setup,
        )
        obj = _spawn_on_battlefield(game, p1, card)
        obj.state.summoning_sickness = False
        _give_player_mana(p1, game.mana_system, generic=1, black=1)

        # Empty graveyard -> activation should be blocked.
        action = PlayerAction(
            type=ActionType.ACTIVATE_ABILITY,
            player_id=p1.id, source_id=obj.id,
            ability_id="activated:0",
        )
        events = await game.priority_system._handle_activate_ability(action)
        assert not any(e.type == EventType.ACTIVATE for e in events), \
            "activation must fail with empty graveyard"

        # Add only one card to the graveyard -> still blocked.
        _stash_in_graveyard(game, p1, filler, 1)
        events = await game.priority_system._handle_activate_ability(action)
        assert not any(e.type == EventType.ACTIVATE for e in events), \
            "activation must fail with only 1 card in graveyard"
        print("PASS: exile-from-GY cost blocks activation when graveyard < N")

    asyncio.get_event_loop().run_until_complete(_run())


def test_exile_from_gy_cost_pays_and_exiles():
    """With ≥N cards in graveyard, activation succeeds and emits N EXILE events."""
    async def _run():
        game = Game()
        p1 = game.add_player("Alice")
        p2 = game.add_player("Bob")
        _setup_game_for_player(p1.id, game)

        filler = make_creature(
            name="Filler", power=1, toughness=1, mana_cost="{1}",
            colors=set(), subtypes={"Spirit"}, text="",
        )

        def setup(obj, state):
            def _effect(o, st, targets):
                return [Event(
                    type=EventType.LIFE_CHANGE,
                    payload={'player': o.controller, 'amount': 3},
                    source=o.id, controller=o.controller,
                )]
            make_activated_ability(
                obj,
                cost="Exile two cards from your graveyard, {1}{B}",
                effect_fn=_effect,
                description="Gain 3 life.",
            )
            return []

        card = make_creature(
            name="Embalmer", power=2, toughness=2, mana_cost="{B}",
            colors={Color.BLACK}, subtypes={"Vampire"},
            text="Exile two cards from your graveyard, {1}{B}: You gain 3 life.",
            setup_interceptors=setup,
        )
        obj = _spawn_on_battlefield(game, p1, card)
        obj.state.summoning_sickness = False
        _give_player_mana(p1, game.mana_system, generic=1, black=1)

        # Three filler cards in graveyard.
        gy_stubs = _stash_in_graveyard(game, p1, filler, 3)
        gy_size_before = len(game.state.zones[f"graveyard_{p1.id}"].objects)
        assert gy_size_before == 3

        action = PlayerAction(
            type=ActionType.ACTIVATE_ABILITY,
            player_id=p1.id, source_id=obj.id,
            ability_id="activated:0",
        )
        events = await game.priority_system._handle_activate_ability(action)

        # Activation should succeed and produce 2 EXILE events.
        assert any(e.type == EventType.ACTIVATE for e in events), \
            f"activation should succeed, got types: {[e.type for e in events]}"
        exile_events = [e for e in events if e.type == EventType.EXILE]
        assert len(exile_events) == 2, \
            f"expected 2 EXILE events, got {len(exile_events)}"
        # The exiled card ids should be from the player's graveyard (greedy: first 2).
        exiled_ids = {e.payload['object_id'] for e in exile_events}
        assert exiled_ids.issubset({s.id for s in gy_stubs}), \
            f"exiled ids {exiled_ids} should be subset of gy stubs"
        # Each exile event sources the activator and has the right controller.
        for ev in exile_events:
            assert ev.controller == p1.id

        # Now actually emit the events so the pipeline processes the EXILE moves
        # and we can confirm the zone state transition.
        for ev in events:
            game.emit(ev)
        gy_after = game.state.zones[f"graveyard_{p1.id}"].objects
        assert len(gy_after) == 1, f"expected 1 card left in graveyard, got {len(gy_after)}"
        print("PASS: exile-from-GY cost pays N cards, emits N EXILE events, removes them from GY")

    asyncio.get_event_loop().run_until_complete(_run())


# ---------------------------------------------------------------------------
# (3) Sacrifice <Named Card> cost parser
# ---------------------------------------------------------------------------


def test_parse_sacrifice_named_in_activation_cost():
    """parse_activation_cost recognises 'Sacrifice <Named Card>' when source != name."""
    # Source name differs from the named card -> previously dropped.
    m, t, s, ds, es, plan, ctr = parse_activation_cost(
        "{3}, {T}, Sacrifice Deconstruction Hammer",
        source_name="Equipped Creature",
    )
    assert m is not None and m.generic == 3, "mana cost {3} should parse"
    assert t is True, "{T} should parse"
    assert s is False, "should NOT be classified as self-sacrifice"
    assert plan is not None and len(plan) == 1, f"expected a plan step, got {plan}"
    step = plan[0]
    assert step.kind == "sacrifice_named"
    assert step.name_match == "deconstruction hammer"
    print("PASS: 'Sacrifice Deconstruction Hammer' parses to sacrifice_named CostStep")


def test_parse_cost_expression_supports_sacrifice_named():
    """The casting-cost parser also recognises the named-card sacrifice form."""
    plan = parse_cost_expression("sacrifice Deconstruction Hammer")
    assert plan is not None and len(plan) == 1
    step = plan[0]
    assert step.kind == "sacrifice_named"
    assert step.name_match == "deconstruction hammer"
    print("PASS: parse_cost_expression handles 'sacrifice <named card>'")


def test_parse_sacrifice_typed_still_works():
    """The typed sacrifice form keeps winning over the named form."""
    plan = parse_cost_expression("sacrifice a creature")
    assert plan is not None and len(plan) == 1
    step = plan[0]
    assert step.kind == "sacrifice", f"expected typed sacrifice, got {step.kind}"
    assert step.amount == 1
    assert step.allowed_types == {CardType.CREATURE}
    print("PASS: typed sacrifice form ('sacrifice a creature') still wins over named form")


def test_sacrifice_named_cost_blocks_when_named_card_absent():
    """Activation is denied if no controlled permanent matches the name."""
    async def _run():
        game = Game()
        p1 = game.add_player("Alice")
        p2 = game.add_player("Bob")
        _setup_game_for_player(p1.id, game)

        def setup(obj, state):
            def _effect(o, st, targets):
                return [Event(
                    type=EventType.LIFE_CHANGE,
                    payload={'player': o.controller, 'amount': 1},
                    source=o.id, controller=o.controller,
                )]
            make_activated_ability(
                obj,
                cost="{3}, {T}, Sacrifice Test Hammer",
                effect_fn=_effect,
                description="Gain 1 life.",
            )
            return []

        wielder = make_creature(
            name="Wielder", power=2, toughness=2, mana_cost="{2}",
            colors=set(), subtypes={"Human"},
            text="{3}, {T}, Sacrifice Test Hammer: You gain 1 life.",
            setup_interceptors=setup,
        )
        obj = _spawn_on_battlefield(game, p1, wielder)
        obj.state.summoning_sickness = False
        _give_player_mana(p1, game.mana_system, generic=3)

        # No "Test Hammer" on battlefield -> activation must fail.
        action = PlayerAction(
            type=ActionType.ACTIVATE_ABILITY,
            player_id=p1.id, source_id=obj.id,
            ability_id="activated:0",
        )
        events = await game.priority_system._handle_activate_ability(action)
        assert not any(e.type == EventType.ACTIVATE for e in events), \
            "activation must fail without the named card on battlefield"
        print("PASS: sacrifice-named cost blocks activation when named card absent")

    asyncio.get_event_loop().run_until_complete(_run())


def test_sacrifice_named_cost_pays_and_sacrifices_named_object():
    """Activation succeeds and emits SACRIFICE for the named permanent."""
    async def _run():
        game = Game()
        p1 = game.add_player("Alice")
        p2 = game.add_player("Bob")
        _setup_game_for_player(p1.id, game)

        # The named card to be sacrificed.
        hammer = make_artifact(
            name="Test Hammer", mana_cost="{1}",
            text="",
        )

        def setup(obj, state):
            def _effect(o, st, targets):
                return [Event(
                    type=EventType.LIFE_CHANGE,
                    payload={'player': o.controller, 'amount': 1},
                    source=o.id, controller=o.controller,
                )]
            make_activated_ability(
                obj,
                cost="{3}, {T}, Sacrifice Test Hammer",
                effect_fn=_effect,
                description="Gain 1 life.",
            )
            return []

        wielder = make_creature(
            name="Wielder", power=2, toughness=2, mana_cost="{2}",
            colors=set(), subtypes={"Human"},
            text="{3}, {T}, Sacrifice Test Hammer: You gain 1 life.",
            setup_interceptors=setup,
        )
        # Spawn the hammer FIRST, then the wielder.
        hammer_obj = _spawn_on_battlefield(game, p1, hammer)
        wielder_obj = _spawn_on_battlefield(game, p1, wielder)
        wielder_obj.state.summoning_sickness = False
        _give_player_mana(p1, game.mana_system, generic=3)

        action = PlayerAction(
            type=ActionType.ACTIVATE_ABILITY,
            player_id=p1.id, source_id=wielder_obj.id,
            ability_id="activated:0",
        )
        events = await game.priority_system._handle_activate_ability(action)

        # Activation succeeds: TAP, ACTIVATE, SACRIFICE (of the hammer).
        assert any(e.type == EventType.ACTIVATE for e in events), \
            f"activation should succeed, types={[e.type for e in events]}"
        sac_events = [e for e in events if e.type == EventType.SACRIFICE]
        assert len(sac_events) == 1, f"expected 1 SACRIFICE, got {len(sac_events)}"
        assert sac_events[0].payload['object_id'] == hammer_obj.id, \
            "the sacrificed object must be the named permanent (Test Hammer), not the wielder"
        print("PASS: sacrifice-named cost emits SACRIFICE for the named permanent")

    asyncio.get_event_loop().run_until_complete(_run())


# ---------------------------------------------------------------------------
# Suite runner
# ---------------------------------------------------------------------------


def main():
    tests = [
        # (1) Exhaust reset
        test_reset_exhaust_clears_used_flag,
        test_reset_exhaust_unused_is_noop,
        test_reset_exhaust_by_controller,
        test_make_exhaust_reset_effect_emits_marker,
        test_exhaust_reset_event_handler_resets_via_pipeline,
        # (2) Exile-from-graveyard as activated cost
        test_parse_exile_from_gy_activation_cost,
        test_exile_from_gy_cost_blocks_when_insufficient,
        test_exile_from_gy_cost_pays_and_exiles,
        # (2b) W27 — X count + typed filter
        test_parse_exile_from_gy_x_count,
        test_parse_exile_from_gy_typed_filter,
        test_parse_exile_from_gy_x_with_typed_filter,
        test_parse_exile_from_gy_creature_filter,
        test_exile_from_gy_typed_filter_blocks_when_not_enough_typed,
        test_exile_from_gy_x_count_uses_action_x_value,
        # (3) Sacrifice <named card>
        test_parse_sacrifice_named_in_activation_cost,
        test_parse_cost_expression_supports_sacrifice_named,
        test_parse_sacrifice_typed_still_works,
        test_sacrifice_named_cost_blocks_when_named_card_absent,
        test_sacrifice_named_cost_pays_and_sacrifices_named_object,
    ]
    failed = []
    for t in tests:
        try:
            t()
        except AssertionError as e:
            failed.append((t.__name__, e))
            print(f"FAIL: {t.__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            failed.append((t.__name__, e))
            print(f"ERROR: {t.__name__}: {e!r}")

    if failed:
        print(f"\n{len(failed)} test(s) failed.")
        sys.exit(1)
    print(f"\nAll {len(tests)} tests passed.")


if __name__ == "__main__":
    main()
