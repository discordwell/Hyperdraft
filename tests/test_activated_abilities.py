"""Phase 4: tests for the activated-ability framework.

Covers:
- Cost parsing across the common patterns ({T}, {N}, sac-self, counter-removal)
- Discovery: registered abilities surface in get_legal_actions
- Dispatch: activating a {T}: Draw a card ability fires DRAW
- Sorcery-speed gating: opponent's turn blocks a sorcery-speed ability
- Once-per-turn enforcement
- Self-sacrifice as cost
- Pump-self ability emits PT_MODIFICATION + GRANT_KEYWORD
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_HERE)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import asyncio

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color,
    make_creature,
)
from src.engine.activated import (
    parse_activation_cost,
)
from src.engine.priority import ActionType, PlayerAction
from src.engine.turn import Phase
from src.cards.interceptor_helpers import (
    make_pump_self_ability,
    make_draw_ability,
    make_destroy_ability,
)


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


def test_cost_parser_handles_common_patterns():
    cases = [
        ("{T}", False, True, False, None, 0),
        ("{1}", True, False, False, None, 1),
        ("{1}, {T}", True, True, False, None, 1),
        ("{2}, {T}, Sacrifice this artifact", True, True, True, None, 2),
        ("{1}, Sacrifice this creature", True, False, True, None, 1),
        ("{R}", True, False, False, None, 0),
        ("{1}, {T}, Remove a wish counter from this artifact", True, True, False, ("wish", 1), 1),
    ]
    for cost, has_mana, has_tap, sac_self, ctr_expected, generic in cases:
        m, t, s, _ds, _es, _plan, ctr = parse_activation_cost(cost, source_name="Test")
        assert (m is not None) == has_mana, f"mana mismatch for {cost!r}: got {m}"
        assert t == has_tap, f"tap mismatch for {cost!r}"
        assert s == sac_self, f"sac_self mismatch for {cost!r}"
        if ctr_expected:
            assert ctr == ctr_expected, f"counter_removal mismatch for {cost!r}: got {ctr}"
        if has_mana and m is not None:
            assert m.generic == generic, f"generic mismatch for {cost!r}: got {m.generic}"
    print("PASS: cost parser handles common patterns")


def test_registered_ability_surfaces_in_legal_actions():
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    _setup_game_for_player(p1.id, game)

    def setup(obj, state):
        make_draw_ability(obj, "{T}", count=1)
        return []

    card = make_creature(
        name="Bookworm",
        power=1, toughness=1, mana_cost="{1}{U}",
        colors={Color.BLUE}, subtypes={"Human", "Wizard"},
        text="{T}: Draw a card.",
        setup_interceptors=setup,
    )
    obj = _spawn_on_battlefield(game, p1, card)
    obj.state.summoning_sickness = False

    actions = game.priority_system.get_legal_actions(p1.id)
    matches = [a for a in actions if a.ability_id == "activated:0" and a.source_id == obj.id]
    assert matches, f"expected ability in legal actions, got: {[a.description for a in actions]}"
    print("PASS: registered ability surfaces in legal actions")


def test_dispatch_emits_draw_event():
    async def _run():
        game = Game()
        p1 = game.add_player("Alice")
        p2 = game.add_player("Bob")
        _setup_game_for_player(p1.id, game)

        def setup(obj, state):
            make_draw_ability(obj, "{T}", count=1)
            return []

        card = make_creature(
            name="Bookworm",
            power=1, toughness=1, mana_cost="{1}{U}",
            colors={Color.BLUE}, subtypes={"Human"},
            text="{T}: Draw a card.",
            setup_interceptors=setup,
        )
        obj = _spawn_on_battlefield(game, p1, card)
        obj.state.summoning_sickness = False

        action = PlayerAction(
            type=ActionType.ACTIVATE_ABILITY,
            player_id=p1.id, source_id=obj.id,
            ability_id="activated:0",
        )
        events = await game.priority_system._handle_activate_ability(action)
        types = [e.type for e in events]
        assert EventType.TAP in types, f"expected TAP, got {types}"
        assert EventType.ACTIVATE in types, f"expected ACTIVATE, got {types}"
        assert obj.state.tapped, "expected source to be tapped"

        # Resolve the stack item.
        item = game.stack.items[-1]
        resolved = item.resolve_fn(item.chosen_targets, game.state) if item.resolve_fn else []
        draw_events = [e for e in resolved if e.type == EventType.DRAW]
        assert draw_events, f"expected DRAW, got {[e.type for e in resolved]}"
        assert draw_events[0].payload['player'] == p1.id
        print("PASS: dispatch emits DRAW event")

    asyncio.get_event_loop().run_until_complete(_run())


def test_self_sacrifice_cost_emits_sacrifice_event():
    async def _run():
        game = Game()
        p1 = game.add_player("Alice")
        p2 = game.add_player("Bob")
        _setup_game_for_player(p1.id, game)

        def setup(obj, state):
            make_destroy_ability(
                obj, "{1}, Sacrifice this creature",
                description="Destroy target artifact or enchantment",
                target_kind="artifact_or_enchantment",
            )
            return []

        card = make_creature(
            name="Cathar Commando",
            power=3, toughness=2, mana_cost="{1}{W}",
            colors={Color.WHITE}, subtypes={"Human", "Soldier"},
            text="Flash. {1}, Sacrifice Cathar Commando: Destroy target artifact or enchantment.",
            setup_interceptors=setup,
        )
        obj = _spawn_on_battlefield(game, p1, card)
        obj.state.summoning_sickness = False
        _give_player_mana(p1, game.mana_system, generic=1)

        action = PlayerAction(
            type=ActionType.ACTIVATE_ABILITY,
            player_id=p1.id, source_id=obj.id,
            ability_id="activated:0",
        )
        events = await game.priority_system._handle_activate_ability(action)
        types = [e.type for e in events]
        assert EventType.SACRIFICE in types, f"expected SACRIFICE, got {types}"
        print("PASS: self-sacrifice cost emits SACRIFICE event")

    asyncio.get_event_loop().run_until_complete(_run())


def test_sorcery_speed_blocks_on_opponent_turn():
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    # Bob's turn.
    game.turn_manager.turn_state.active_player_id = p2.id
    game.turn_manager.turn_state.phase = Phase.PRECOMBAT_MAIN

    def setup(obj, state):
        make_draw_ability(
            obj, "{T}", count=1, sorcery_speed=True,
            description="Draw a card. Activate only as a sorcery.",
        )
        return []

    card = make_creature(
        name="Slow Loot",
        power=1, toughness=1, mana_cost="{U}",
        colors={Color.BLUE}, subtypes={"Wizard"},
        text="{T}: Draw a card. Activate only as a sorcery.",
        setup_interceptors=setup,
    )
    obj = _spawn_on_battlefield(game, p1, card)
    obj.state.summoning_sickness = False

    actions = game.priority_system.get_legal_actions(p1.id)
    matches = [a for a in actions if a.ability_id == "activated:0"]
    assert not matches, f"sorcery-speed ability should be hidden on opponent's turn, got: {[a.description for a in matches]}"
    print("PASS: sorcery-speed blocks on opponent turn")


def test_once_per_turn_enforcement():
    async def _run():
        game = Game()
        p1 = game.add_player("Alice")
        p2 = game.add_player("Bob")
        _setup_game_for_player(p1.id, game)

        def setup(obj, state):
            make_draw_ability(obj, "{2}", count=1, once_per_turn=True)
            return []

        card = make_creature(
            name="One-Shot",
            power=1, toughness=1, mana_cost="{1}",
            colors=set(), subtypes={"Construct"},
            text="{2}: Draw a card. Activate this ability only once each turn.",
            setup_interceptors=setup,
        )
        obj = _spawn_on_battlefield(game, p1, card)
        obj.state.summoning_sickness = False
        _give_player_mana(p1, game.mana_system, generic=4)

        action = PlayerAction(
            type=ActionType.ACTIVATE_ABILITY,
            player_id=p1.id, source_id=obj.id,
            ability_id="activated:0",
        )
        events1 = await game.priority_system._handle_activate_ability(action)
        assert any(e.type == EventType.ACTIVATE for e in events1), "first activation should succeed"

        actions = game.priority_system.get_legal_actions(p1.id)
        matches = [a for a in actions if a.ability_id == "activated:0" and a.source_id == obj.id]
        assert not matches, "once-per-turn ability should be exhausted"
        print("PASS: once-per-turn enforcement")

    asyncio.get_event_loop().run_until_complete(_run())


def test_pump_self_ability_modifies_pt_and_grants_keyword():
    async def _run():
        game = Game()
        p1 = game.add_player("Alice")
        p2 = game.add_player("Bob")
        _setup_game_for_player(p1.id, game)

        def setup(obj, state):
            make_pump_self_ability(
                obj, "{R}", power_mod=1, toughness_mod=0,
                grant_keyword="haste",
                description="+1/+0 and gains haste",
            )
            return []

        card = make_creature(
            name="Goblin Brawler",
            power=2, toughness=2, mana_cost="{1}{R}",
            colors={Color.RED}, subtypes={"Goblin"},
            text="{R}: Goblin Brawler gets +1/+0 and gains haste until end of turn.",
            setup_interceptors=setup,
        )
        obj = _spawn_on_battlefield(game, p1, card)
        obj.state.summoning_sickness = False
        _give_player_mana(p1, game.mana_system, red=1)

        action = PlayerAction(
            type=ActionType.ACTIVATE_ABILITY,
            player_id=p1.id, source_id=obj.id,
            ability_id="activated:0",
        )
        events = await game.priority_system._handle_activate_ability(action)
        item = game.stack.items[-1]
        assert item.resolve_fn is not None, "stack item should carry a resolve fn"
        resolved = item.resolve_fn(item.chosen_targets, game.state)
        types = [e.type for e in resolved]
        assert EventType.PT_MODIFICATION in types, f"expected PT_MODIFICATION, got {types}"
        assert EventType.GRANT_KEYWORD in types, f"expected GRANT_KEYWORD, got {types}"
        print("PASS: pump-self ability emits PT_MODIFICATION + GRANT_KEYWORD")

    asyncio.get_event_loop().run_until_complete(_run())


def test_summoning_sickness_blocks_tap_ability():
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    _setup_game_for_player(p1.id, game)

    def setup(obj, state):
        make_draw_ability(obj, "{T}", count=1)
        return []

    card = make_creature(
        name="Sluggish Reader",
        power=1, toughness=1, mana_cost="{U}",
        colors={Color.BLUE}, subtypes={"Wizard"},
        text="{T}: Draw a card.",
        setup_interceptors=setup,
    )
    obj = _spawn_on_battlefield(game, p1, card)
    obj.state.summoning_sickness = True

    actions = game.priority_system.get_legal_actions(p1.id)
    matches = [a for a in actions if a.ability_id == "activated:0" and a.source_id == obj.id]
    assert not matches, "summoning-sick creature should not surface tap ability"
    print("PASS: summoning sickness blocks tap ability")


def test_insufficient_mana_blocks_activation():
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    _setup_game_for_player(p1.id, game)

    def setup(obj, state):
        make_draw_ability(obj, "{3}", count=1)
        return []

    card = make_creature(
        name="Pricey Library",
        power=0, toughness=4, mana_cost="{2}",
        colors=set(), subtypes={"Construct"},
        text="{3}: Draw a card.",
        setup_interceptors=setup,
    )
    obj = _spawn_on_battlefield(game, p1, card)
    obj.state.summoning_sickness = False

    actions = game.priority_system.get_legal_actions(p1.id)
    matches = [a for a in actions if a.ability_id == "activated:0" and a.source_id == obj.id]
    assert not matches, "no-mana state should hide the ability"
    print("PASS: insufficient mana blocks activation")


def test_dedup_distinguishes_two_same_cost_different_effect_abilities():
    """Two distinct effect_fns sharing a cost text register as two abilities.

    Round 9: register_activated_ability previously deduped on
    (cost_text, description). With auto-generated default descriptions ('{G}: ...'),
    two genuinely distinct abilities with the same cost would collapse into one.
    The new guard uses effect_fn bytecode to distinguish them.
    """
    from src.cards.interceptor_helpers import make_exhaust_ability

    def setup(obj, state):
        # Two different effect functions, both with cost {G}, both default desc.
        def _gain_life(o, st, t):
            return [Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': o.controller, 'amount': 1},
                source=o.id, controller=o.controller,
            )]

        def _draw_card(o, st, t):
            return [Event(
                type=EventType.DRAW,
                payload={'player_id': o.controller, 'count': 1},
                source=o.id, controller=o.controller,
            )]

        make_exhaust_ability(obj, cost="{G}", effect_fn=_gain_life)
        make_exhaust_ability(obj, cost="{G}", effect_fn=_draw_card)
        return []

    card = make_creature(
        name="Twin Exhauster", power=1, toughness=1, mana_cost="{G}",
        colors={Color.GREEN}, subtypes={"Hydra"},
        text="Exhaust — {G}: Gain 1 life.\nExhaust — {G}: Draw a card.",
        setup_interceptors=setup,
    )

    game = Game()
    p1 = game.add_player("Alice")
    game.add_player("Bob")
    _setup_game_for_player(p1.id, game)
    obj = _spawn_on_battlefield(game, p1, card)

    abilities = obj.state.activated_abilities
    assert len(abilities) == 2, (
        f"two distinct {{G}} exhaust abilities should both register, "
        f"got {len(abilities)}"
    )
    # Setup runs at HAND-creation AND at battlefield ZONE_CHANGE; this proves
    # the dedup correctly collapses the duplicate runs without flattening
    # the genuine two-ability list to one.
    print("PASS: dedup distinguishes same-cost different-effect abilities")


def test_dedup_collapses_setup_re_runs_for_same_ability():
    """One ability registered in setup() stays at count=1 even when setup runs twice."""
    from src.cards.interceptor_helpers import make_exhaust_ability

    def setup(obj, state):
        def _effect(o, st, t):
            return []
        make_exhaust_ability(obj, cost="{G}", effect_fn=_effect)
        return []

    card = make_creature(
        name="Single Exhauster", power=1, toughness=1, mana_cost="{G}",
        colors={Color.GREEN}, subtypes={"Hydra"},
        text="Exhaust — {G}: Do nothing.",
        setup_interceptors=setup,
    )

    game = Game()
    p1 = game.add_player("Alice")
    game.add_player("Bob")
    _setup_game_for_player(p1.id, game)
    obj = _spawn_on_battlefield(game, p1, card)

    abilities = obj.state.activated_abilities
    # setup_interceptors fires at HAND creation AND at ZONE_CHANGE -> battlefield;
    # without the guard we'd see 2 abilities here.
    assert len(abilities) == 1, (
        f"single ability across HAND→BATTLEFIELD setup runs should dedup to 1, "
        f"got {len(abilities)}"
    )
    print("PASS: dedup collapses setup re-runs of the same ability")


if __name__ == "__main__":
    test_cost_parser_handles_common_patterns()
    test_registered_ability_surfaces_in_legal_actions()
    test_dispatch_emits_draw_event()
    test_self_sacrifice_cost_emits_sacrifice_event()
    test_sorcery_speed_blocks_on_opponent_turn()
    test_once_per_turn_enforcement()
    test_pump_self_ability_modifies_pt_and_grants_keyword()
    test_summoning_sickness_blocks_tap_ability()
    test_insufficient_mana_blocks_activation()
    test_dedup_distinguishes_two_same_cost_different_effect_abilities()
    test_dedup_collapses_setup_re_runs_for_same_ability()
    print("\nAll Phase 4 tests passed!")
