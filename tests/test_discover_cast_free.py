"""
Tests for the W11 Discover cast-for-free branch.

Covers:
  - DISCOVER N=4 with eligible card: presents a cast-vs-hand choice.
  - "put in hand" branch: card lands in hand, others bottomed.
  - "cast for free" branch: card goes to STACK without mana cost.
  - Cast-for-free with target: targets accepted via auto_targets.
  - No eligible card (all MV > N): all exiled, nothing in hand or cast.
  - 5 LCI hidden lands (Hidden Cataract/Courtyard/Necropolis/Nursery/Volcano)
    each register their Discover 4 activated ability with the right cost.
"""
import asyncio
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_HERE)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color,
    GameObject, ObjectState, new_id,
    make_creature, make_instant, make_land,
)
from src.engine.priority import PlayerAction, ActionType
from src.engine.targeting import Target


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


def _setup_game():
    """Two-player game with p1 in main phase and 6 Islands on the field."""
    from src.engine.turn import Phase
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    if game.turn_manager is not None:
        game.turn_manager.turn_state.active_player_id = p1.id
        game.turn_manager.turn_state.phase = Phase.PRECOMBAT_MAIN
    island_def = make_land("Island", subtypes={"Island"})
    for _ in range(6):
        game.create_object(
            name="Island", owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
            characteristics=island_def.characteristics, card_def=island_def,
        )
    return game, p1, p2


def _spawn_in_library(game, player_id, card_def, on_top=True):
    obj = GameObject(
        id=new_id(),
        name=card_def.name,
        owner=player_id,
        controller=player_id,
        zone=ZoneType.LIBRARY,
        characteristics=card_def.characteristics,
        state=ObjectState(),
        card_def=card_def,
        created_at=game.state.next_timestamp(),
        entered_zone_at=game.state.timestamp,
        _state_ref=game.state,
    )
    game.state.objects[obj.id] = obj
    lib = game.state.zones[f'library_{player_id}']
    if on_top:
        lib.objects.insert(0, obj.id)
    else:
        lib.objects.append(obj.id)
    return obj


def _emit_discover(game, player_id, n, source_id="t-source", auto_targets=None):
    payload = {'player': player_id, 'value': n}
    if auto_targets is not None:
        payload['auto_targets'] = auto_targets
    ev = Event(
        type=EventType.DISCOVER,
        payload=payload,
        source=source_id, controller=player_id,
    )
    game.pipeline.emit(ev)


# ---------------------------------------------------------------------------
# Discover handler: hand branch (existing/legacy behaviour preserved)
# ---------------------------------------------------------------------------


def test_discover_hand_branch_with_skipped_big_card():
    print("\n=== Test: DISCOVER 4 — exiles 5-MV, then 3-MV → choice → hand ===")
    game, p1, _ = _setup_game()

    big = make_creature(
        name="Big Beast", power=5, toughness=5,
        mana_cost="{3}{G}{G}", colors={Color.GREEN}, subtypes={"Beast"},
        text="",
    )
    cheap = make_creature(
        name="Cheap Beast", power=2, toughness=2,
        mana_cost="{2}{G}", colors={Color.GREEN}, subtypes={"Beast"},
        text="",
    )

    # Library order: top is big (MV 5), then cheap (MV 3), rest below.
    cheap_obj = _spawn_in_library(game, p1.id, cheap, on_top=True)
    big_obj = _spawn_in_library(game, p1.id, big, on_top=True)

    _emit_discover(game, p1.id, 4)

    choice = game.state.pending_choice
    assert choice is not None and choice.choice_type == "discover_cast_or_hand", \
        f"expected discover choice, got {choice}"
    # Big should already be exiled (and is one of the "others").
    assert big_obj.zone == ZoneType.EXILE, big_obj.zone
    assert cheap_obj.zone == ZoneType.EXILE, cheap_obj.zone

    ok, err, _ = game.submit_choice(choice.id, p1.id, [{'id': 'hand'}])
    assert ok, f"submit_choice failed: {err}"

    # cheap → hand; big → bottom of library.
    hand = game.state.zones[f'hand_{p1.id}']
    lib = game.state.zones[f'library_{p1.id}']
    assert cheap_obj.id in hand.objects, "cheap should be in hand"
    assert cheap_obj.zone == ZoneType.HAND, cheap_obj.zone
    assert big_obj.id in lib.objects, "big should be on library bottom"
    assert big_obj.zone == ZoneType.LIBRARY, big_obj.zone
    assert big_obj.id not in hand.objects, "big should NOT be in hand"
    print("  PASS: hand branch puts hit in hand, bottoms others")


# ---------------------------------------------------------------------------
# Discover handler: cast-for-free branch
# ---------------------------------------------------------------------------


def test_discover_cast_for_free_no_target_instant():
    print("\n=== Test: DISCOVER 4 — cast-for-free puts 3-MV instant on STACK ===")
    game, p1, _ = _setup_game()

    def noop_resolve(targets, state):
        return []

    cheap_instant = make_instant(
        name="Cheap Instant",
        mana_cost="{2}{U}",
        colors={Color.BLUE},
        text="Do nothing.",
        resolve=noop_resolve,
    )

    obj = _spawn_in_library(game, p1.id, cheap_instant, on_top=True)

    # Snapshot mana-pool size BEFORE cast (should be unchanged after free
    # cast). Mana pools live on the ManaSystem, keyed by player.
    pool = game.priority_system.mana_system.get_pool(p1.id)
    starting_pool = len(pool.mana)

    _emit_discover(game, p1.id, 4)

    choice = game.state.pending_choice
    assert choice is not None and choice.choice_type == "discover_cast_or_hand"

    ok, err, _ = game.submit_choice(choice.id, p1.id, [{'id': 'cast'}])
    assert ok, f"submit_choice failed: {err}"

    # Card should be on the stack zone, not in hand.
    assert obj.zone == ZoneType.STACK, f"cast for free should go to STACK, got {obj.zone}"
    hand = game.state.zones[f'hand_{p1.id}']
    assert obj.id not in hand.objects, "should NOT be in hand"

    # Mana pool unchanged (we didn't pay {2}{U}).
    ending_pool = len(pool.mana)
    assert ending_pool == starting_pool, \
        f"mana pool changed: {starting_pool} -> {ending_pool}"

    # The stack should contain the spell.
    assert any(item.card_id == obj.id for item in game.stack.items), \
        f"stack does not contain the cast spell; items: {game.stack.items}"
    print("  PASS: cast-for-free skips mana payment and pushes to stack")


def test_discover_cast_for_free_with_target():
    print("\n=== Test: DISCOVER 4 — cast-for-free with target lands on STACK ===")
    game, p1, p2 = _setup_game()

    captured = {}

    def shock_resolve(targets, state):
        # Targets is list[list[Target]]. Capture for assertion.
        captured['targets'] = targets
        return []

    shock_instant = make_instant(
        name="Mini Shock",
        mana_cost="{R}",
        colors={Color.RED},
        text="Mini Shock deals 2 damage to any target.",
        resolve=shock_resolve,
    )

    obj = _spawn_in_library(game, p1.id, shock_instant, on_top=True)

    # Spawn a 2/2 victim creature on p2's battlefield.
    victim_def = make_creature(
        name="Victim Bear", power=2, toughness=2,
        mana_cost="{1}{G}", colors={Color.GREEN}, subtypes={"Bear"}, text="",
    )
    victim = game.create_object(
        name=victim_def.name, owner_id=p2.id, zone=ZoneType.BATTLEFIELD,
        characteristics=victim_def.characteristics, card_def=victim_def,
    )

    # Pre-supply the target via auto_targets on the DISCOVER payload.
    auto_targets = [[Target(id=victim.id)]]
    _emit_discover(game, p1.id, 4, auto_targets=auto_targets)

    choice = game.state.pending_choice
    assert choice is not None and choice.choice_type == "discover_cast_or_hand"

    ok, err, _ = game.submit_choice(choice.id, p1.id, [{'id': 'cast'}])
    assert ok, f"submit_choice failed: {err}"

    # Spell should be on the stack with the target attached.
    assert obj.zone == ZoneType.STACK
    items = [it for it in game.stack.items if it.card_id == obj.id]
    assert items, "cast spell missing from stack"
    item = items[0]
    # chosen_targets: list[list[Target]]
    assert item.chosen_targets and item.chosen_targets[0], \
        f"no targets attached: {item.chosen_targets}"
    first_target = item.chosen_targets[0][0]
    target_id = getattr(first_target, 'id', first_target)
    assert target_id == victim.id, f"wrong target: {first_target}"
    print("  PASS: cast-for-free preserves chosen targets")


# ---------------------------------------------------------------------------
# Discover handler: no eligible card
# ---------------------------------------------------------------------------


def test_discover_no_eligible_card_bottoms_all():
    print("\n=== Test: DISCOVER 4 — all cards exceed N → no choice, all bottomed ===")
    game, p1, _ = _setup_game()

    big1 = make_creature(
        name="Huge Beast 1", power=8, toughness=8,
        mana_cost="{6}{G}{G}", colors={Color.GREEN}, subtypes={"Beast"}, text="",
    )
    big2 = make_creature(
        name="Huge Beast 2", power=7, toughness=7,
        mana_cost="{5}{G}{G}", colors={Color.GREEN}, subtypes={"Beast"}, text="",
    )

    obj1 = _spawn_in_library(game, p1.id, big1, on_top=True)
    obj2 = _spawn_in_library(game, p1.id, big2, on_top=True)

    # Wipe out the rest of the library so we can exhaust it.
    lib = game.state.zones[f'library_{p1.id}']
    lib.objects = [obj2.id, obj1.id]

    _emit_discover(game, p1.id, 4)

    # No eligible non-land found, so no pending choice.
    assert game.state.pending_choice is None, \
        f"unexpected choice when no eligible: {game.state.pending_choice}"
    # Both cards back on the library bottom.
    assert obj1.id in lib.objects and obj2.id in lib.objects
    assert obj1.zone == ZoneType.LIBRARY and obj2.zone == ZoneType.LIBRARY
    hand = game.state.zones[f'hand_{p1.id}']
    assert obj1.id not in hand.objects and obj2.id not in hand.objects
    print("  PASS: no-eligible scenario bottoms all without prompting")


# ---------------------------------------------------------------------------
# Land branch: lands count as "others" and don't fizzle the search
# ---------------------------------------------------------------------------


def test_discover_skips_lands_and_finds_eligible_below():
    print("\n=== Test: DISCOVER 4 — top card is a land; below is 3-MV creature ===")
    game, p1, _ = _setup_game()

    cheap = make_creature(
        name="Cheap Bear", power=2, toughness=2,
        mana_cost="{2}{G}", colors={Color.GREEN}, subtypes={"Bear"}, text="",
    )
    extra_land = make_land("Forest", subtypes={"Forest"})

    cheap_obj = _spawn_in_library(game, p1.id, cheap, on_top=True)
    land_obj = _spawn_in_library(game, p1.id, extra_land, on_top=True)
    # Library top is land, then cheap.

    _emit_discover(game, p1.id, 4)

    choice = game.state.pending_choice
    assert choice is not None, "land + creature should still trigger a choice"
    ok, _, _ = game.submit_choice(choice.id, p1.id, [{'id': 'hand'}])
    assert ok

    hand = game.state.zones[f'hand_{p1.id}']
    lib = game.state.zones[f'library_{p1.id}']
    assert cheap_obj.id in hand.objects, "creature should be in hand"
    assert land_obj.id in lib.objects, "land should be bottomed"
    assert land_obj.zone == ZoneType.LIBRARY
    print("  PASS: lands act as 'others' (exiled, then bottomed)")


# ---------------------------------------------------------------------------
# LCI hidden lands: 5-card cycle
# ---------------------------------------------------------------------------


def test_lci_hidden_lands_register_discover_4_ability():
    """All five LCI hidden lands should register a Discover 4 activated ability."""
    print("\n=== Test: 5 LCI hidden lands each register Discover 4 ===")
    from src.cards.lost_caverns_ixalan import (
        HIDDEN_CATARACT, HIDDEN_COURTYARD, HIDDEN_NECROPOLIS,
        HIDDEN_NURSERY, HIDDEN_VOLCANO,
    )

    # (CardDef, expected color symbol in the cost text)
    cycle = [
        (HIDDEN_CATARACT, "U"),
        (HIDDEN_COURTYARD, "W"),
        (HIDDEN_NECROPOLIS, "B"),
        (HIDDEN_NURSERY, "G"),
        (HIDDEN_VOLCANO, "R"),
    ]

    async def go():
        for card_def, color_sym in cycle:
            game, p1, _ = _setup_game()
            obj = GameObject(
                id=new_id(),
                name=card_def.name,
                owner=p1.id,
                controller=p1.id,
                zone=ZoneType.HAND,
                characteristics=card_def.characteristics,
                state=ObjectState(),
                card_def=card_def,
                created_at=game.state.next_timestamp(),
                entered_zone_at=game.state.timestamp,
                _state_ref=game.state,
            )
            game.state.objects[obj.id] = obj
            game.state.zones[f'hand_{p1.id}'].objects.append(obj.id)

            action = PlayerAction(
                type=ActionType.PLAY_LAND, player_id=p1.id, card_id=obj.id,
            )
            events = await game.priority_system._handle_play_land(action)
            for ev in events:
                game.pipeline.emit(ev)

            on_bf = game.state.objects[obj.id]
            assert on_bf.zone == ZoneType.BATTLEFIELD, on_bf.zone
            assert on_bf.state.tapped is True, f"{card_def.name} should ETB tapped"

            abilities = on_bf.state.activated_abilities
            discover_abilities = [a for a in abilities if 'Discover' in a.description]
            assert discover_abilities, \
                f"{card_def.name}: no Discover ability; got {[a.description for a in abilities]}"

            ability = discover_abilities[0]
            cost_text = ability.cost_text or ""
            # Cost should include both {4} and the color symbol, plus tap and sac.
            assert "{4}" in cost_text, f"{card_def.name}: cost missing {{4}}: {cost_text}"
            assert f"{{{color_sym}}}" in cost_text, \
                f"{card_def.name}: cost missing {{{color_sym}}}: {cost_text}"
            assert "{T}" in cost_text, f"{card_def.name}: cost missing {{T}}: {cost_text}"
            assert "Sacrifice" in cost_text or "sacrifice" in cost_text, \
                f"{card_def.name}: cost missing Sacrifice: {cost_text}"
            assert ability.sorcery_speed, f"{card_def.name}: should be sorcery-speed"

    asyncio.run(go())
    print("  PASS: all 5 hidden lands register Discover 4 with {{4}}{{C}}, {{T}}, sac")


def test_lci_hidden_land_ability_emits_discover_event():
    """Activating Hidden Cataract's effect_fn directly should emit a DISCOVER event."""
    print("\n=== Test: Hidden Cataract ability emits DISCOVER 4 event ===")
    from src.cards.lost_caverns_ixalan import HIDDEN_CATARACT

    async def go():
        game, p1, _ = _setup_game()
        obj = GameObject(
            id=new_id(), name=HIDDEN_CATARACT.name, owner=p1.id, controller=p1.id,
            zone=ZoneType.HAND, characteristics=HIDDEN_CATARACT.characteristics,
            state=ObjectState(), card_def=HIDDEN_CATARACT,
            created_at=game.state.next_timestamp(),
            entered_zone_at=game.state.timestamp, _state_ref=game.state,
        )
        game.state.objects[obj.id] = obj
        game.state.zones[f'hand_{p1.id}'].objects.append(obj.id)

        action = PlayerAction(
            type=ActionType.PLAY_LAND, player_id=p1.id, card_id=obj.id,
        )
        events = await game.priority_system._handle_play_land(action)
        for ev in events:
            game.pipeline.emit(ev)

        on_bf = game.state.objects[obj.id]
        ability = next(a for a in on_bf.state.activated_abilities if 'Discover' in a.description)
        # Call the registered effect function directly.
        out = ability.effect_fn(on_bf, game.state, [])
        assert len(out) == 1
        assert out[0].type == EventType.DISCOVER
        assert out[0].payload.get('value') == 4
        assert out[0].payload.get('player') == p1.id

    asyncio.run(go())
    print("  PASS: Hidden Cataract effect emits DISCOVER 4")


def test_lci_hidden_land_full_flow_end_to_end():
    """Activate Hidden Volcano's Discover 4 from a real library; pick 'hand'."""
    print("\n=== Test: Hidden Volcano end-to-end: activate → discover → hand ===")
    from src.cards.lost_caverns_ixalan import HIDDEN_VOLCANO

    async def go():
        game, p1, _ = _setup_game()
        obj = GameObject(
            id=new_id(), name=HIDDEN_VOLCANO.name, owner=p1.id, controller=p1.id,
            zone=ZoneType.HAND, characteristics=HIDDEN_VOLCANO.characteristics,
            state=ObjectState(), card_def=HIDDEN_VOLCANO,
            created_at=game.state.next_timestamp(),
            entered_zone_at=game.state.timestamp, _state_ref=game.state,
        )
        game.state.objects[obj.id] = obj
        game.state.zones[f'hand_{p1.id}'].objects.append(obj.id)

        action = PlayerAction(
            type=ActionType.PLAY_LAND, player_id=p1.id, card_id=obj.id,
        )
        evs = await game.priority_system._handle_play_land(action)
        for ev in evs:
            game.pipeline.emit(ev)

        on_bf = game.state.objects[obj.id]
        ability = next(a for a in on_bf.state.activated_abilities if 'Discover' in a.description)

        # Stack a 4-MV creature on top so Discover 4 hits it.
        target_def = make_creature(
            name="Storm Drake", power=3, toughness=3,
            mana_cost="{2}{R}{R}", colors={Color.RED}, subtypes={"Drake"}, text="",
        )
        target_obj = _spawn_in_library(game, p1.id, target_def, on_top=True)

        # Bypass the activation cost (we don't actually have RR mana
        # available without staging Mountains; this tests the discover flow,
        # not activation cost validation). Call the effect directly.
        for ev in ability.effect_fn(on_bf, game.state, []):
            game.pipeline.emit(ev)

        choice = game.state.pending_choice
        assert choice is not None and choice.choice_type == "discover_cast_or_hand"
        ok, _, _ = game.submit_choice(choice.id, p1.id, [{'id': 'hand'}])
        assert ok

        hand = game.state.zones[f'hand_{p1.id}']
        assert target_obj.id in hand.objects, "Storm Drake should be in hand"
        assert target_obj.zone == ZoneType.HAND

    asyncio.run(go())
    print("  PASS: Hidden Volcano activated path resolves Discover 4 → hand")


# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------


def main():
    tests = [
        test_discover_hand_branch_with_skipped_big_card,
        test_discover_cast_for_free_no_target_instant,
        test_discover_cast_for_free_with_target,
        test_discover_no_eligible_card_bottoms_all,
        test_discover_skips_lands_and_finds_eligible_below,
        test_lci_hidden_lands_register_discover_4_ability,
        test_lci_hidden_land_ability_emits_discover_event,
        test_lci_hidden_land_full_flow_end_to_end,
    ]
    failed = []
    for fn in tests:
        try:
            fn()
        except AssertionError as e:
            failed.append((fn.__name__, str(e)))
            print(f"  FAIL: {fn.__name__}: {e}")
        except Exception as e:
            failed.append((fn.__name__, f"{type(e).__name__}: {e}"))
            print(f"  ERROR: {fn.__name__}: {type(e).__name__}: {e}")

    print("\n" + "=" * 60)
    if failed:
        print(f"FAILED ({len(failed)}/{len(tests)}):")
        for name, err in failed:
            print(f"  - {name}: {err}")
        sys.exit(1)
    else:
        print(f"ALL {len(tests)} DISCOVER CAST-FREE TESTS PASSED")
        print("=" * 60)


if __name__ == "__main__":
    main()
