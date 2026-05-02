"""Tests for the activated-ability cost-reduction framework (W2 engine extension).

Covers:
  - get_effective_activation_cost reduces generic mana per the registered
    interceptors (Boom Scholar's "{2} less to activate").
  - Reductions only apply when the predicate matches (Boom Scholar's own
    Exhaust ability is NOT reduced — controller_only && id != obj.id).
  - Coloured pips are never reduced; only the generic part is touched.
  - Reductions stop applying when the source leaves the battlefield.
  - The reduction is consumed end-to-end by the priority system: a permanent
    with a {4} Exhaust ability becomes payable with only {2} when Boom
    Scholar is on the field.
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
from src.engine.cost_query import get_effective_activation_cost
from src.engine.mana import ManaCost, ManaType
from src.engine.priority import ActionType, PlayerAction
from src.engine.turn import Phase
from src.cards.interceptor_helpers import (
    make_exhaust_ability,
    make_activated_cost_reduction,
)


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


def _give_player_mana(player, mana_system, *, generic=0, red=0, green=0):
    for _ in range(generic):
        mana_system.produce_mana(player.id, ManaType.COLORLESS, 1)
    for _ in range(red):
        mana_system.produce_mana(player.id, ManaType.RED, 1)
    for _ in range(green):
        mana_system.produce_mana(player.id, ManaType.GREEN, 1)


def _make_exhaust_dummy(name, cost):
    """Helper: a creature with an Exhaust ability of cost ``cost`` that adds a counter."""

    def setup(obj, state):
        def _effect(o, st, targets):
            return [Event(
                type=EventType.COUNTER_ADDED,
                payload={'object_id': o.id, 'counter_type': '+1/+1', 'amount': 1},
                source=o.id, controller=o.controller,
            )]
        make_exhaust_ability(
            obj, cost=cost, effect_fn=_effect,
            description=f"{cost}: Counter (test).",
        )
        return []

    return make_creature(
        name=name, power=2, toughness=2, mana_cost="{1}",
        colors=set(), subtypes={"Construct"},
        text=f"Exhaust — {cost}: Put a +1/+1 counter on this creature. (Activate each exhaust ability only once.)",
        setup_interceptors=setup,
    )


def _make_boom_scholar_proxy():
    """Build a stand-in for Boom Scholar's static effect — useful for unit-
    testing the cost-reduction interceptor in isolation."""

    def setup(obj, state):
        def _applies(ability, src, st):
            if ability is None or src is None:
                return False
            if not getattr(ability, 'is_exhaust', False):
                return False
            if getattr(src, 'id', None) == obj.id:
                return False  # not own ability
            if getattr(src, 'controller', None) != obj.controller:
                return False
            return True

        return [make_activated_cost_reduction(obj, amount=2, applies_filter=_applies)]

    return make_creature(
        name="Boom Scholar Proxy",
        power=3, toughness=3, mana_cost="{1}{R}{G}",
        colors={Color.RED, Color.GREEN}, subtypes={"Advisor"},
        text="Exhaust abilities of other permanents you control cost {2} less.",
        setup_interceptors=setup,
    )


def test_query_returns_printed_cost_when_no_reductions():
    """No registered reductions -> effective cost == ability.mana_cost."""
    game = Game()
    p1 = game.add_player("Alice")
    game.add_player("Bob")
    _setup_game_for_player(p1.id, game)

    card = _make_exhaust_dummy("Exhauster", "{4}")
    obj = _spawn_on_battlefield(game, p1, card)
    ability = obj.state.activated_abilities[0]

    eff = get_effective_activation_cost(ability, obj, p1.id, game.state)
    assert eff.generic == 4, f"expected generic=4, got {eff.generic}"
    print("PASS: no reductions -> printed cost")


def test_boom_scholar_proxy_reduces_other_exhaust_abilities():
    """Boom Scholar reduces an OTHER permanent's {4} exhaust to {2}."""
    game = Game()
    p1 = game.add_player("Alice")
    game.add_player("Bob")
    _setup_game_for_player(p1.id, game)

    proxy = _spawn_on_battlefield(game, p1, _make_boom_scholar_proxy())

    other = _spawn_on_battlefield(game, p1, _make_exhaust_dummy("Other Exhauster", "{4}"))
    ability = other.state.activated_abilities[0]

    eff = get_effective_activation_cost(ability, other, p1.id, game.state)
    assert eff.generic == 2, f"expected generic reduced to 2, got {eff.generic}"
    print("PASS: Boom-Scholar-proxy reduces other permanent's Exhaust ability")


def test_boom_scholar_proxy_does_not_reduce_own_ability():
    """Boom Scholar does NOT reduce its OWN exhaust ability."""
    game = Game()
    p1 = game.add_player("Alice")
    game.add_player("Bob")
    _setup_game_for_player(p1.id, game)

    # Put the proxy on the battlefield, then attach its own Exhaust ability
    # so we can query it.
    def setup(obj, state):
        def _eff(o, st, t): return []
        make_exhaust_ability(obj, cost="{4}", effect_fn=_eff,
                             description="self Exhaust")

        def _applies(ab, src, st):
            return (ab is not None and getattr(ab, 'is_exhaust', False)
                    and src is not None
                    and src.id != obj.id
                    and src.controller == obj.controller)
        return [make_activated_cost_reduction(obj, amount=2, applies_filter=_applies)]

    self_card = make_creature(
        name="Self-Reducer",
        power=1, toughness=1, mana_cost="{1}",
        colors=set(), subtypes={"Construct"},
        text="Exhaust abilities of OTHER permanents cost {2} less.\nExhaust — {4}: Test.",
        setup_interceptors=setup,
    )

    obj = _spawn_on_battlefield(game, p1, self_card)
    ability = obj.state.activated_abilities[0]

    eff = get_effective_activation_cost(ability, obj, p1.id, game.state)
    assert eff.generic == 4, f"own ability should NOT be reduced, got {eff.generic}"
    print("PASS: own exhaust ability not reduced")


def test_reduction_does_not_touch_coloured_pips():
    """{4}{R}{G} reduced by {2} -> {2}{R}{G}; coloured pips preserved."""
    game = Game()
    p1 = game.add_player("Alice")
    game.add_player("Bob")
    _setup_game_for_player(p1.id, game)

    _spawn_on_battlefield(game, p1, _make_boom_scholar_proxy())

    other = _spawn_on_battlefield(
        game, p1,
        _make_exhaust_dummy("Coloured Exhauster", "{4}{R}{G}"),
    )
    ability = other.state.activated_abilities[0]

    eff = get_effective_activation_cost(ability, other, p1.id, game.state)
    assert eff.generic == 2
    assert eff.red == 1
    assert eff.green == 1
    print("PASS: reduction preserves coloured pips")


def test_reduction_clamps_at_zero():
    """{1} reduced by {2} -> {0}; never negative."""
    game = Game()
    p1 = game.add_player("Alice")
    game.add_player("Bob")
    _setup_game_for_player(p1.id, game)

    _spawn_on_battlefield(game, p1, _make_boom_scholar_proxy())

    other = _spawn_on_battlefield(
        game, p1,
        _make_exhaust_dummy("Cheap Exhauster", "{1}"),
    )
    ability = other.state.activated_abilities[0]

    eff = get_effective_activation_cost(ability, other, p1.id, game.state)
    assert eff.generic == 0, f"reduction should clamp at 0, got {eff.generic}"
    print("PASS: reduction clamps generic at 0")


def test_reduction_inactive_when_source_off_battlefield():
    """When Boom Scholar leaves the battlefield, the reduction stops applying."""
    async def _run():
        game = Game()
        p1 = game.add_player("Alice")
        game.add_player("Bob")
        _setup_game_for_player(p1.id, game)

        proxy = _spawn_on_battlefield(game, p1, _make_boom_scholar_proxy())
        other = _spawn_on_battlefield(
            game, p1, _make_exhaust_dummy("Stayer", "{4}"),
        )
        ability = other.state.activated_abilities[0]

        # Initially reduced.
        assert get_effective_activation_cost(ability, other, p1.id, game.state).generic == 2

        # Remove the proxy from the battlefield (simulate destroy → graveyard).
        game.emit(Event(
            type=EventType.ZONE_CHANGE,
            payload={
                'object_id': proxy.id,
                'from_zone': 'battlefield',
                'from_zone_type': ZoneType.BATTLEFIELD,
                'to_zone': f'graveyard_{p1.id}',
                'to_zone_type': ZoneType.GRAVEYARD,
            },
        ))

        # No longer reduced (the QUERY filter checks proxy's zone).
        eff = get_effective_activation_cost(ability, other, p1.id, game.state)
        assert eff.generic == 4, \
            f"reduction should be inactive when source not on battlefield, got generic={eff.generic}"
        print("PASS: reduction inactive when source leaves battlefield")

    asyncio.get_event_loop().run_until_complete(_run())


def test_reduction_makes_unaffordable_ability_payable_via_priority():
    """End-to-end: {4} Exhaust unaffordable with 2 mana; Boom Scholar reduces
    to {2} -> activation succeeds."""
    async def _run():
        game = Game()
        p1 = game.add_player("Alice")
        game.add_player("Bob")
        _setup_game_for_player(p1.id, game)

        # Spawn Boom-Scholar proxy AND target Exhauster.
        _spawn_on_battlefield(game, p1, _make_boom_scholar_proxy())
        target = _spawn_on_battlefield(
            game, p1, _make_exhaust_dummy("Big Exhauster", "{4}"),
        )
        target.state.summoning_sickness = False
        # Only 2 generic mana — too little for {4}, just enough after reduction.
        _give_player_mana(p1, game.mana_system, generic=2)

        # Without the reduction, this can't pay; the priority system must
        # surface it as legal because the reduction makes it affordable.
        actions = game.priority_system.get_legal_actions(p1.id)
        matches = [
            a for a in actions
            if a.source_id == target.id and a.ability_id == "activated:0"
        ]
        assert matches, \
            "Exhaust ability should be legal after Boom-Scholar's reduction"

        # Activate; should pay {2} and tap.
        action = PlayerAction(
            type=ActionType.ACTIVATE_ABILITY,
            player_id=p1.id, source_id=target.id,
            ability_id="activated:0",
        )
        events = await game.priority_system._handle_activate_ability(action)
        assert any(e.type == EventType.ACTIVATE for e in events), \
            "reduced-cost activation should succeed"

        pool = game.mana_system.get_pool(p1.id)
        assert pool.total() == 0, \
            f"pool should be empty after paying reduced cost {{2}}, got {pool.total()}"
        print("PASS: cost reduction reaches priority system end-to-end")

    asyncio.get_event_loop().run_until_complete(_run())


def test_wired_boom_scholar_card_reduces_other_exhaust():
    """Wired Boom Scholar card reduces an other-permanent's exhaust ability."""
    from src.cards.aetherdrift import BOOM_SCHOLAR

    game = Game()
    p1 = game.add_player("Alice")
    game.add_player("Bob")
    _setup_game_for_player(p1.id, game)

    boom = _spawn_on_battlefield(game, p1, BOOM_SCHOLAR)
    other = _spawn_on_battlefield(
        game, p1, _make_exhaust_dummy("Wired Other", "{4}"),
    )
    ability = other.state.activated_abilities[0]

    eff = get_effective_activation_cost(ability, other, p1.id, game.state)
    assert eff.generic == 2, \
        f"Boom Scholar should reduce other's {{4}} to {{2}}, got generic={eff.generic}"

    # And Boom Scholar's OWN Exhaust ability ({4}{R}{G}) is not reduced.
    own_ab = boom.state.activated_abilities[0]
    own_eff = get_effective_activation_cost(own_ab, boom, p1.id, game.state)
    assert own_eff.generic == 4, \
        f"Boom Scholar's own exhaust should NOT be reduced, got generic={own_eff.generic}"
    print("PASS: wired Boom Scholar reduces other-exhaust costs and not its own")


if __name__ == "__main__":
    test_query_returns_printed_cost_when_no_reductions()
    test_boom_scholar_proxy_reduces_other_exhaust_abilities()
    test_boom_scholar_proxy_does_not_reduce_own_ability()
    test_reduction_does_not_touch_coloured_pips()
    test_reduction_clamps_at_zero()
    test_reduction_inactive_when_source_off_battlefield()
    test_reduction_makes_unaffordable_ability_payable_via_priority()
    test_wired_boom_scholar_card_reduces_other_exhaust()
    print("\nAll activated cost-query tests passed.")
