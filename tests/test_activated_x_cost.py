"""Tests for X-costs in activated abilities (W2 engine extension).

Covers:
  - The cost parser recognises {X}{X} via ManaCost.x_count.
  - register_activated_ability sets has_x_cost=True for X-costed abilities.
  - PlayerAction.x_value flows through can_pay_activation / pay_activation_cost.
  - Mana paid scales with x_value (e.g. {X}{X} with x_value=2 charges 4).
  - The effect closure receives x_value via the inspect-signature shim.
  - Insufficient mana with the chosen X blocks activation.
  - x_value=0 still activates (legal but produces no copies for Gogo).

The wired example is Gogo, Master of Mimicry (Final Fantasy):
``{X}{X}, {T}: Copy target activated/triggered ability you control X times.``
"""

import os
import sys
import asyncio

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_HERE)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.engine import (
    Game, Event, EventType, ZoneType, Color, CardType,
    make_creature,
)
from src.engine.activated import parse_activation_cost, register_activated_ability
from src.engine.mana import ManaType, ManaCost
from src.engine.priority import ActionType, PlayerAction
from src.engine.stack import StackItem, StackItemType
from src.engine.turn import Phase
from src.cards.interceptor_helpers import make_activated_ability


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


def _give_player_mana(player, mana_system, *, generic=0, red=0, green=0,
                      white=0, blue=0, black=0):
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


def test_parse_activation_cost_recognises_x_x():
    """{X}{X}, {T} should parse with mana_cost.x_count == 2 and requires_tap=True."""
    mana_cost, has_tap, sac_self, _ds, _es, _plan, _ctr = parse_activation_cost(
        "{X}{X}, {T}", source_name="Gogo, Master of Mimicry",
    )
    assert mana_cost is not None, "expected a mana cost"
    assert mana_cost.x_count == 2, f"x_count mismatch: got {mana_cost.x_count}"
    assert mana_cost.generic == 0
    assert has_tap is True
    assert sac_self is False
    print("PASS: parse_activation_cost recognises {X}{X}, {T}")


def test_register_activated_ability_sets_has_x_cost_flag():
    game = Game()
    p1 = game.add_player("Alice")
    game.add_player("Bob")

    def setup(obj, state):
        def _eff(o, st, targets, *, x_value: int = 0):
            return []
        make_activated_ability(
            obj, cost="{X}{X}, {T}", effect_fn=_eff,
            description="X-cost test",
        )
        return []

    card = make_creature(
        name="X Tester",
        power=1, toughness=1, mana_cost="{1}",
        colors=set(), subtypes={"Construct"},
        text="{X}{X}, {T}: Test ability.",
        setup_interceptors=setup,
    )
    obj = _spawn_on_battlefield(game, p1, card)
    abilities = obj.state.activated_abilities
    assert len(abilities) == 1, f"expected one ability, got {len(abilities)}"
    ab = abilities[0]
    assert ab.has_x_cost is True, "has_x_cost should be True for {X}{X} cost"
    assert ab.is_exhaust is False, "is_exhaust should be False for non-Exhaust"
    assert ab.mana_cost.x_count == 2
    print("PASS: register_activated_ability sets has_x_cost for X-costed abilities")


def _make_x_pump_card(name="X Pump", description=""):
    """Helper: a creature with {X}{X}, {T}: Put X +1/+1 counters on it."""

    def setup(obj, state):
        def _effect(o, st, targets, *, x_value: int = 0):
            if x_value <= 0:
                return []
            return [Event(
                type=EventType.COUNTER_ADDED,
                payload={'object_id': o.id, 'counter_type': '+1/+1',
                         'amount': int(x_value)},
                source=o.id, controller=o.controller,
            )]

        make_activated_ability(
            obj, cost="{X}{X}, {T}", effect_fn=_effect,
            description=description or "{X}{X}, {T}: Put X +1/+1 counters on this creature.",
        )
        return []

    return make_creature(
        name=name,
        power=1, toughness=1, mana_cost="{1}",
        colors=set(), subtypes={"Construct"},
        text="{X}{X}, {T}: Put X +1/+1 counters on this creature.",
        setup_interceptors=setup,
    )


def test_activate_with_x_value_pays_2x_generic_mana():
    """{X}{X} with x_value=2 should consume 4 generic mana from the pool."""
    async def _run():
        game = Game()
        p1 = game.add_player("Alice")
        game.add_player("Bob")
        _setup_game_for_player(p1.id, game)

        card = _make_x_pump_card("X Pumper")
        obj = _spawn_on_battlefield(game, p1, card)
        obj.state.summoning_sickness = False
        # Pool: 5 generic — enough for X=2 (cost=4) plus 1 leftover.
        _give_player_mana(p1, game.mana_system, generic=5)

        action = PlayerAction(
            type=ActionType.ACTIVATE_ABILITY,
            player_id=p1.id, source_id=obj.id,
            ability_id="activated:0",
            x_value=2,
        )
        events = await game.priority_system._handle_activate_ability(action)
        assert any(e.type == EventType.ACTIVATE for e in events), \
            f"activation should succeed; got events: {[e.type for e in events]}"
        assert any(e.type == EventType.TAP for e in events), "tap cost emitted"
        assert obj.state.tapped is True, "source should be tapped"

        # Mana paid: original pool 5 generic — 4 spent (X=2 against {X}{X}) = 1 left.
        pool = game.mana_system.get_pool(p1.id)
        remaining = pool.total()
        assert remaining == 1, f"expected 1 mana remaining after paying X=2, got {remaining}"

        # ACTIVATE event payload should carry x_value.
        activate_events = [e for e in events if e.type == EventType.ACTIVATE]
        assert activate_events[0].payload.get('x_value') == 2, \
            f"ACTIVATE payload should carry x_value=2: {activate_events[0].payload}"
        assert activate_events[0].payload.get('is_exhaust') is False, \
            "non-Exhaust ability should report is_exhaust=False"

        # The resolve closure should have received x_value=2 and emit a counter event.
        item = game.stack.items[-1]
        resolved = item.resolve_fn(item.chosen_targets, game.state) if item.resolve_fn else []
        ctr = [e for e in resolved if e.type == EventType.COUNTER_ADDED]
        assert ctr, f"resolve should emit COUNTER_ADDED, got {[e.type for e in resolved]}"
        assert ctr[0].payload['amount'] == 2, \
            f"counter amount should equal x_value=2, got {ctr[0].payload}"
        print("PASS: activate with x_value=2 pays {X}{X}=4 mana and reaches resolve closure")

    asyncio.get_event_loop().run_until_complete(_run())


def test_activate_with_x_value_zero_is_legal_no_op():
    """X=0 against {X}{X} costs 0 generic, activation succeeds, no counters added."""
    async def _run():
        game = Game()
        p1 = game.add_player("Alice")
        game.add_player("Bob")
        _setup_game_for_player(p1.id, game)

        card = _make_x_pump_card("Zero Pumper")
        obj = _spawn_on_battlefield(game, p1, card)
        obj.state.summoning_sickness = False
        # No mana required at X=0.

        action = PlayerAction(
            type=ActionType.ACTIVATE_ABILITY,
            player_id=p1.id, source_id=obj.id,
            ability_id="activated:0",
            x_value=0,
        )
        events = await game.priority_system._handle_activate_ability(action)
        assert any(e.type == EventType.ACTIVATE for e in events), \
            "X=0 activation should succeed (no mana required)"
        assert obj.state.tapped is True, "tap cost still paid"

        item = game.stack.items[-1]
        resolved = item.resolve_fn(item.chosen_targets, game.state) if item.resolve_fn else []
        ctr = [e for e in resolved if e.type == EventType.COUNTER_ADDED]
        assert not ctr, "X=0 should produce no counters"
        print("PASS: X=0 is legal and no-op")

    asyncio.get_event_loop().run_until_complete(_run())


def test_insufficient_mana_for_chosen_x_blocks_activation():
    """X=3 needs 6 generic; only 4 available — can_pay_activation returns False."""
    async def _run():
        game = Game()
        p1 = game.add_player("Alice")
        game.add_player("Bob")
        _setup_game_for_player(p1.id, game)

        card = _make_x_pump_card("Cap Pumper")
        obj = _spawn_on_battlefield(game, p1, card)
        obj.state.summoning_sickness = False
        # Only 4 mana — not enough for X=3 (needs 6).
        _give_player_mana(p1, game.mana_system, generic=4)

        action = PlayerAction(
            type=ActionType.ACTIVATE_ABILITY,
            player_id=p1.id, source_id=obj.id,
            ability_id="activated:0",
            x_value=3,
        )
        events = await game.priority_system._handle_activate_ability(action)
        assert not any(e.type == EventType.ACTIVATE for e in events), \
            "activation should fail when mana insufficient for chosen X"
        assert obj.state.tapped is False, "tap should not happen when activation rejected"

        # Pool unchanged.
        pool = game.mana_system.get_pool(p1.id)
        assert pool.total() == 4, f"mana should not be spent on rejected activation; got {pool.total()}"
        print("PASS: insufficient mana for chosen X blocks activation")

    asyncio.get_event_loop().run_until_complete(_run())


def test_legacy_effect_fn_signature_still_works():
    """Backward-compat: an effect_fn taking only (obj, state, targets) still
    receives the call (no x_value injected) when x_value is used elsewhere.
    The X-cost mana is still paid at the cost-pay step regardless."""
    async def _run():
        game = Game()
        p1 = game.add_player("Alice")
        game.add_player("Bob")
        _setup_game_for_player(p1.id, game)

        captured = {}

        def setup(obj, state):
            def _legacy_effect(o, st, targets):  # 3-arg only
                captured['called'] = True
                return []
            make_activated_ability(
                obj, cost="{X}, {T}", effect_fn=_legacy_effect,
                description="legacy",
            )
            return []

        card = make_creature(
            name="Legacy",
            power=1, toughness=1, mana_cost="{1}",
            colors=set(), subtypes={"Construct"},
            text="{X}, {T}: Do something.",
            setup_interceptors=setup,
        )
        obj = _spawn_on_battlefield(game, p1, card)
        obj.state.summoning_sickness = False
        _give_player_mana(p1, game.mana_system, generic=2)

        action = PlayerAction(
            type=ActionType.ACTIVATE_ABILITY,
            player_id=p1.id, source_id=obj.id,
            ability_id="activated:0",
            x_value=2,
        )
        events = await game.priority_system._handle_activate_ability(action)
        assert any(e.type == EventType.ACTIVATE for e in events), "should activate"

        # Resolve the stack item — legacy effect_fn should be called without x_value.
        item = game.stack.items[-1]
        item.resolve_fn(item.chosen_targets, game.state)
        assert captured.get('called') is True, "legacy effect_fn should be invoked"
        print("PASS: legacy 3-arg effect_fn still works under X-cost dispatch")

    asyncio.get_event_loop().run_until_complete(_run())


def test_gogo_master_of_mimicry_xx_cost_emits_x_copies():
    """Wired Gogo: spawn, push a copyable activated-ability stack item, then
    activate {X}{X}, {T} with X=2, providing the chosen target via the
    pending choice handler. Assert mana paid = 4 and 2 COPY_STACK_ITEM events fire."""
    async def _run():
        from src.cards.final_fantasy import GOGO_MASTER_OF_MIMICRY

        game = Game()
        p1 = game.add_player("Alice")
        game.add_player("Bob")
        _setup_game_for_player(p1.id, game)

        gogo = _spawn_on_battlefield(game, p1, GOGO_MASTER_OF_MIMICRY)
        gogo.state.summoning_sickness = False
        _give_player_mana(p1, game.mana_system, generic=5)

        # Push a dummy activated-ability StackItem the controller controls (so
        # there's something legal to copy).
        target_item = StackItem(
            id="",
            type=StackItemType.ACTIVATED_ABILITY,
            source_id="dummy_src",
            controller_id=p1.id,
            resolve_fn=lambda t, s: [],
        )
        game.stack.push(target_item)
        target_item_id = target_item.id

        action = PlayerAction(
            type=ActionType.ACTIVATE_ABILITY,
            player_id=p1.id, source_id=gogo.id,
            ability_id="activated:0",
            x_value=2,
        )
        events = await game.priority_system._handle_activate_ability(action)
        assert any(e.type == EventType.ACTIVATE for e in events), \
            "Gogo's ability should activate at X=2"

        # Mana spent: started with 5 generic, paid 4 (X=2 against {X}{X}) -> 1 left.
        pool = game.mana_system.get_pool(p1.id)
        assert pool.total() == 1, \
            f"expected 1 mana remaining after paying {{X}}{{X}}=4, got {pool.total()}"

        # Resolve Gogo's stack item to trigger the target choice; then drive
        # the choice manually to pick our dummy stack item id.
        gogo_item = game.stack.items[-1]
        # Sanity: the latest pushed item should be Gogo's activated ability.
        assert gogo_item.source_id == gogo.id, \
            f"top of stack should be Gogo's ability, got source_id={gogo_item.source_id}"
        gogo_item.resolve_fn(gogo_item.chosen_targets, game.state)

        # Pull and drive the pending choice — Gogo wires choice.callback_data['handler'].
        choice = game.state.pending_choice
        assert choice is not None, "Gogo should set up a target choice for the player"
        handler = choice.callback_data.get('handler')
        assert handler is not None, "choice handler should be wired"
        emitted = handler(choice, [target_item_id], game.state)
        copy_events = [e for e in emitted if e.type == EventType.COPY_STACK_ITEM]
        assert len(copy_events) == 2, \
            f"X=2 should emit 2 COPY_STACK_ITEM events; got {[e.type for e in emitted]}"
        for ce in copy_events:
            assert ce.payload['stack_item_id'] == target_item_id
        print("PASS: Gogo X=2 emits 2 COPY_STACK_ITEM events and pays 4 mana")

    asyncio.get_event_loop().run_until_complete(_run())


def test_ai_x_cost_ability_bakes_max_affordable_x_and_suppresses_free_zero():
    """AI X-picking for {X}: activated abilities (priority-loop fix, 2026-05-29).

    Regression for the polish-pass stall: an {X}: activated ability (e.g. Mirror
    Entity) surfaced to the AI at the default x_value=0 — a free no-op re-offered
    every priority window, ping-ponging to the 5000-iteration priority cap and
    grinding Elf/changeling games to a multi-minute crawl. The fix
    (priority.py _get_activatable_abilities + the new _max_affordable_x) bakes
    the max *affordable* X into the surfaced action and skips the unproductive
    free X=0 case for AI players, while leaving the human surface unchanged.
    """
    game = Game()
    p1 = game.add_player("Alice")
    game.add_player("Bob")
    _setup_game_for_player(p1.id, game)
    game.priority_system.set_ai_player(p1.id)

    # Mirror Entity's shape: a pure {X}: activated ability (no fixed cost).
    def setup(obj, state):
        def _eff(o, st, targets, *, x_value: int = 0):
            return []
        make_activated_ability(obj, "{X}", _eff,
                               description="creatures become X/X")
        return []

    card = make_creature(
        name="X Pump Bear", power=2, toughness=2, mana_cost="{1}{G}",
        colors={Color.GREEN}, setup_interceptors=setup,
    )
    obj = _spawn_on_battlefield(game, p1, card)

    def _x_actions():
        return [a for a in game.priority_system.get_legal_actions(p1.id)
                if a.type == ActionType.ACTIVATE_ABILITY and a.source_id == obj.id]

    # Case 1 — no mana: the only available X is the free X=0 no-op. The AI must
    # NOT be offered it (offering it is the infinite priority loop).
    assert not _x_actions(), \
        "AI must not be offered the free X=0 activation (priority-loop bug)"

    # Case 2 — four mana: offered exactly once, with the max affordable X baked
    # in (so activating consumes mana and can't be re-offered for free).
    _give_player_mana(p1, game.priority_system.mana_system, green=4)
    acts = _x_actions()
    assert len(acts) == 1, f"expected exactly one X activation, got {len(acts)}"
    assert acts[0].x_value == 4, \
        f"AI should bake max affordable X (=4) into the action, got {acts[0].x_value}"

    # The AI's LegalAction -> PlayerAction conversion must CARRY x_value through;
    # otherwise the chosen action activates at X=0 (no mana spent) and re-loops.
    from src.ai.engine import AIEngine
    pa = AIEngine(difficulty='medium')._legal_to_player_action(
        acts[0], p1.id, game.state)
    assert pa.x_value == 4, \
        f"_legal_to_player_action must carry x_value (=4), got {pa.x_value}"

    print("PASS: AI X-cost ability bakes max affordable X and suppresses free X=0")


if __name__ == "__main__":
    test_parse_activation_cost_recognises_x_x()
    test_register_activated_ability_sets_has_x_cost_flag()
    test_activate_with_x_value_pays_2x_generic_mana()
    test_activate_with_x_value_zero_is_legal_no_op()
    test_insufficient_mana_for_chosen_x_blocks_activation()
    test_legacy_effect_fn_signature_still_works()
    test_gogo_master_of_mimicry_xx_cost_emits_x_copies()
    test_ai_x_cost_ability_bakes_max_affordable_x_and_suppresses_free_zero()
    print("\nAll X-cost activated-ability tests passed.")
