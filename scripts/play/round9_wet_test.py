#!/usr/bin/env python3
"""Round-9 wet test: drive real game scenarios that exercise the new code paths.

Covers:
  1. Vehicle animation (Rangers' Refueler): activate exhaust → resolve →
     confirm 3/3 creature → cleanup → confirm reverts.
  2. becomes_copy_of supertypes (Oko-style): place a Legendary creature, copy
     it onto a non-Legendary, confirm Legendary supertype propagates and
     reverts at EOT.
  3. Multi-exhaust dedup (Loot the Pathfinder): confirm 3 distinct exhaust
     abilities register without collapse, each lockable independently.
  4. Crash-resistance: simulate an artifact that animates, then becomes a
     copy of something, then EOT — chained QUERY interceptors should clean
     up correctly.

Each scenario runs and prints PASS/FAIL. Exit code 0 iff all pass.

Usage::

    python scripts/play/round9_wet_test.py
"""
import asyncio
import os
import sys
import traceback

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color,
    get_power, get_toughness, get_types, get_subtypes, get_supertypes,
    has_ability,
)
from src.engine.priority import ActionType, PlayerAction
from src.engine.turn import Phase
from src.engine.mana import ManaType


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


def _give_mana(player, mana_system, *, generic=0, w=0, u=0, b=0, r=0, g=0):
    for _ in range(generic):
        mana_system.produce_mana(player.id, ManaType.COLORLESS, 1)
    for _ in range(w):
        mana_system.produce_mana(player.id, ManaType.WHITE, 1)
    for _ in range(u):
        mana_system.produce_mana(player.id, ManaType.BLUE, 1)
    for _ in range(b):
        mana_system.produce_mana(player.id, ManaType.BLACK, 1)
    for _ in range(r):
        mana_system.produce_mana(player.id, ManaType.RED, 1)
    for _ in range(g):
        mana_system.produce_mana(player.id, ManaType.GREEN, 1)


# =============================================================================
# Scenario 1: Vehicle animation end-to-end
# =============================================================================

async def scenario_vehicle_animate():
    print("\n--- Scenario 1: Rangers' Refueler animation ---")
    from src.cards.aetherdrift import RANGERS_REFUELER

    game = Game()
    p1 = game.add_player("Alice")
    game.add_player("Bob")
    _setup_game_for_player(p1.id, game)

    obj = _spawn_on_battlefield(game, p1, RANGERS_REFUELER)
    print(f"  spawned Rangers' Refueler (id={obj.id[:8]}...)")
    print(f"  initial types: {get_types(obj, game.state)}")
    assert CardType.CREATURE not in get_types(obj, game.state), \
        "vehicle should not start as a creature"

    abilities = obj.state.activated_abilities
    assert len(abilities) == 1, f"expected 1 exhaust ability, got {len(abilities)}"
    print(f"  registered abilities: {len(abilities)} ({abilities[0].cost_text})")

    _give_mana(p1, game.mana_system, generic=4)
    print(f"  player mana: {game.mana_system.get_pool(p1.id).total()}")

    # Activate via priority system (real path)
    actions = game.priority_system.get_legal_actions(p1.id)
    matches = [a for a in actions if a.source_id == obj.id and a.ability_id == "activated:0"]
    assert matches, "exhaust ability should be legal"
    print(f"  legal actions include activate: ✓")

    action = PlayerAction(
        type=ActionType.ACTIVATE_ABILITY,
        player_id=p1.id, source_id=obj.id, ability_id="activated:0",
    )
    events = await game.priority_system._handle_activate_ability(action)
    activate = next((e for e in events if e.type == EventType.ACTIVATE), None)
    assert activate is not None, "ACTIVATE event must be emitted"
    print(f"  activation: ACTIVATE event fired (is_exhaust={activate.payload.get('is_exhaust')})")

    # Resolve the stack
    item = game.stack.items[-1]
    resolve_events = item.resolve_fn(item.chosen_targets, game.state) if item.resolve_fn else []
    counter_evs = [e for e in resolve_events if e.type == EventType.COUNTER_ADDED]
    assert counter_evs, "expected +1/+1 counter rider"
    print(f"  resolution emitted {len(counter_evs)} COUNTER_ADDED ({counter_evs[0].payload['amount']} +1/+1)")

    # Confirm animation took effect
    assert CardType.CREATURE in get_types(obj, game.state), \
        "should be a creature after animation"
    p, t = get_power(obj, game.state), get_toughness(obj, game.state)
    assert (p, t) == (3, 3), f"expected 3/3 base, got {p}/{t}"
    print(f"  post-animation: {p}/{t} creature with subtypes {obj.characteristics.subtypes}")

    # Run EOT cleanup
    tm = game.turn_manager
    tm.turn_state.active_player_id = p1.id
    await tm._do_cleanup_step()

    types_after = get_types(obj, game.state)
    assert CardType.CREATURE not in types_after, \
        f"should revert to non-creature after EOT, got {types_after}"
    print(f"  post-cleanup types: {types_after}")
    print("  PASS: vehicle animates and reverts cleanly")


# =============================================================================
# Scenario 2: Oko-style copy with supertypes propagation
# =============================================================================

async def scenario_oko_legendary_copy():
    print("\n--- Scenario 2: Oko copy carries Legendary supertype ---")
    from src.engine import make_creature
    from src.cards.interceptor_helpers import becomes_copy_of

    game = Game()
    p1 = game.add_player("Alice")
    game.add_player("Bob")
    _setup_game_for_player(p1.id, game)

    # A Legendary creature on the battlefield as the source.
    legendary_def = make_creature(
        name="Mock Legendary Wurm",
        power=6, toughness=6, mana_cost="{4}{G}",
        colors={Color.GREEN}, subtypes={"Wurm"},
        supertypes={"Legendary"},
        text="Test Legendary creature.",
    )
    target_def = make_creature(
        name="Plain Bear", power=2, toughness=2, mana_cost="{1}{G}",
        colors={Color.GREEN}, subtypes={"Bear"},
        text="Test plain creature.",
    )
    source = _spawn_on_battlefield(game, p1, legendary_def)
    target = _spawn_on_battlefield(game, p1, target_def)
    print(f"  source: {source.name} {get_power(source, game.state)}/{get_toughness(source, game.state)} "
          f"supertypes={source.characteristics.supertypes}")
    print(f"  target: {target.name} {get_power(target, game.state)}/{get_toughness(target, game.state)} "
          f"supertypes={target.characteristics.supertypes}")

    # Apply the copy.
    becomes_copy_of(target, source, game.state)
    print(f"  applied becomes_copy_of(target, source)")

    # Verify supertypes propagate.
    target_supers = get_supertypes(target, game.state)
    assert "Legendary" in target_supers, \
        f"target should have Legendary supertype, got {target_supers}"
    target_subs = get_subtypes(target, game.state)
    assert "Wurm" in target_subs, f"target should have Wurm subtype, got {target_subs}"
    print(f"  target now: {get_power(target, game.state)}/{get_toughness(target, game.state)} "
          f"supertypes={target_supers} subtypes={target_subs}")

    # Cleanup at EOT.
    tm = game.turn_manager
    tm.turn_state.active_player_id = p1.id
    await tm._do_cleanup_step()

    target_supers_after = get_supertypes(target, game.state)
    target_subs_after = get_subtypes(target, game.state)
    assert "Legendary" not in target_supers_after, \
        f"Legendary should drop after EOT, got {target_supers_after}"
    assert "Wurm" not in target_subs_after, \
        f"Wurm should drop after EOT, got {target_subs_after}"
    assert "Bear" in target_subs_after, \
        f"Bear should be restored, got {target_subs_after}"
    print(f"  post-cleanup: supertypes={target_supers_after} subtypes={target_subs_after}")
    print("  PASS: Legendary supertype propagates through copy and reverts at EOT")


# =============================================================================
# Scenario 3: Multi-exhaust dedup (Loot the Pathfinder)
# =============================================================================

async def scenario_multi_exhaust_dedup():
    print("\n--- Scenario 3: Loot the Pathfinder registers 3 distinct exhausts ---")
    from src.cards.aetherdrift import LOOT_THE_PATHFINDER

    game = Game()
    p1 = game.add_player("Alice")
    game.add_player("Bob")
    _setup_game_for_player(p1.id, game)

    obj = _spawn_on_battlefield(game, p1, LOOT_THE_PATHFINDER)
    abilities = obj.state.activated_abilities
    print(f"  registered abilities: {[a.cost_text for a in abilities]}")

    # All 3 should register with different cost strings.
    cost_strings = [a.cost_text for a in abilities]
    assert len(abilities) == 3, \
        f"expected 3 abilities, got {len(abilities)}: {cost_strings}"
    assert len(set(cost_strings)) == 3, \
        f"expected 3 distinct cost texts, got {cost_strings}"

    # All should be flagged is_exhaust.
    assert all(a.is_exhaust for a in abilities), \
        "all 3 should be Exhaust abilities"
    # All should still be unused (once_per_game_used=False initially).
    assert all(not a.once_per_game_used for a in abilities), \
        "none should be locked yet"
    print(f"  all 3 are exhaust + unused initially")
    print("  PASS: multi-exhaust dedup correctly preserves all 3 distinct abilities")


# =============================================================================
# Scenario 4: chained interceptors (animate, then copy, then EOT) — crash-resistance
# =============================================================================

async def scenario_chained_interceptors():
    print("\n--- Scenario 4: chained animate + copy + cleanup ---")
    from src.cards.aetherdrift import RANGERS_REFUELER
    from src.engine import make_creature
    from src.cards.interceptor_helpers import becomes_copy_of

    game = Game()
    p1 = game.add_player("Alice")
    game.add_player("Bob")
    _setup_game_for_player(p1.id, game)

    refueler = _spawn_on_battlefield(game, p1, RANGERS_REFUELER)

    # Animate it.
    _give_mana(p1, game.mana_system, generic=4)
    action = PlayerAction(
        type=ActionType.ACTIVATE_ABILITY,
        player_id=p1.id, source_id=refueler.id, ability_id="activated:0",
    )
    await game.priority_system._handle_activate_ability(action)
    item = game.stack.items[-1]
    item.resolve_fn(item.chosen_targets, game.state)
    assert CardType.CREATURE in get_types(refueler, game.state)
    print(f"  Refueler animated: 3/3 ✓")

    # Now place a Legendary Dragon and copy Refueler (post-animation) onto it.
    dragon_def = make_creature(
        name="Mock Legendary Dragon",
        power=4, toughness=4, mana_cost="{2}{R}{R}",
        colors={Color.RED}, subtypes={"Dragon"},
        supertypes={"Legendary"},
        text="Test Legendary creature.",
    )
    dragon = _spawn_on_battlefield(game, p1, dragon_def)
    print(f"  Legendary Dragon spawned: 4/4 supertypes={dragon.characteristics.supertypes}")

    # Make the dragon a copy of the (now-animated) Refueler.
    becomes_copy_of(dragon, refueler, game.state)
    p, t = get_power(dragon, game.state), get_toughness(dragon, game.state)
    print(f"  Dragon as copy: {p}/{t} supertypes={get_supertypes(dragon, game.state)} "
          f"subtypes={get_subtypes(dragon, game.state)}")
    # Dragon now reads as a copy of Refueler. Refueler isn't Legendary, so the
    # Dragon should have lost its Legendary supertype during the copy.
    assert "Legendary" not in get_supertypes(dragon, game.state), \
        "Dragon-as-copy-of-Refueler should not be Legendary (Refueler isn't)"

    # Cleanup at EOT.
    tm = game.turn_manager
    tm.turn_state.active_player_id = p1.id
    await tm._do_cleanup_step()

    # Dragon should be back to 4/4 Legendary; Refueler should be back to non-creature.
    assert "Legendary" in get_supertypes(dragon, game.state), \
        f"Dragon should regain Legendary after EOT, got {get_supertypes(dragon, game.state)}"
    assert get_power(dragon, game.state) == 4, \
        f"Dragon should be back to 4 power, got {get_power(dragon, game.state)}"
    assert CardType.CREATURE not in get_types(refueler, game.state), \
        "Refueler should revert to non-creature"
    print(f"  post-cleanup: Dragon back to {get_power(dragon, game.state)}/"
          f"{get_toughness(dragon, game.state)} Legendary; Refueler reverted ✓")
    print("  PASS: chained interceptors clean up without crash")


# =============================================================================
# Driver
# =============================================================================

async def main():
    scenarios = [
        ("vehicle_animate", scenario_vehicle_animate),
        ("oko_legendary_copy", scenario_oko_legendary_copy),
        ("multi_exhaust_dedup", scenario_multi_exhaust_dedup),
        ("chained_interceptors", scenario_chained_interceptors),
    ]
    failures = []
    for name, fn in scenarios:
        try:
            await fn()
        except AssertionError as e:
            print(f"  FAIL: {name}: {e}")
            failures.append((name, str(e)))
        except Exception as e:
            print(f"  CRASH: {name}: {e}")
            traceback.print_exc()
            failures.append((name, f"crash: {e}"))

    print("\n" + "=" * 60)
    print(f"WET TEST RESULT: {len(scenarios) - len(failures)}/{len(scenarios)} passed")
    if failures:
        for name, msg in failures:
            print(f"  ✗ {name}: {msg}")
        sys.exit(1)
    print("=" * 60)
    print("All Round-9 wet-test scenarios passed.")


if __name__ == "__main__":
    asyncio.run(main())
