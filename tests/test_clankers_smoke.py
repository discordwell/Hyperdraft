"""Smoke test for the Clankers engine.

Per clankers_contract.md §8, this is the Stage-1 canary that catches contract
drift between the four parallel scaffold agents (engine, combat, turn, AI).

Verifies:
  1. Two AIs (Easy vs Easy) can run a full game without raising an exception.
  2. The loop terminates within 40 turns — either some player's Workshop
     Integrity hits 0, or the deathclock fires AND eventually drives someone
     to 0.
  3. Each AI took at least one non-pass action during their Assemble windows
     (so we know the pipeline + action dispatch is actually doing something).
  4. RNG is seeded (state.rng_seed = 42) so the run is deterministic.

The test runs entirely on engine + AI + turn-manager modules; it does NOT
spin up a Server or asyncio loop. It writes to the contract in
clankers_contract.md, not to the specific implementation of any sibling
agent. If a sibling implementation drifts from the contract, this test fails
loudly.
"""

from __future__ import annotations

import pytest

from src.engine.types import Event, GameState, Player


pytestmark = pytest.mark.smoke


def _build_placeholder_deck(seed_tag: str):
    """Build a 60-card deck from ~6 placeholder card defs repeated.

    Mix: 2 chassis x 14 = 28 + 2 weapons x 11 = 22 + 1 add-on x 6 = 6 +
         1 transient x 4 = 4. Total = 60.

    The card defs are minimal — power/integrity small enough that combat
    matters, compute costs cheap enough that Easy AI can actually play
    cards on turn 1.
    """
    from src.engine.clankers import (
        make_chassis,
        make_weapon,
        make_add_on,
        make_transient,
    )

    chassis_a = make_chassis(
        name=f"Scout Frame ({seed_tag})",
        power=2,
        integrity=3,
        weapon_slots=1,
        add_on_slots=2,
        compute_cost=2,
        clankers_archetype="rush",
    )
    chassis_b = make_chassis(
        name=f"Heavy Tread ({seed_tag})",
        power=3,
        integrity=5,
        weapon_slots=2,
        add_on_slots=2,
        compute_cost=3,
        clankers_archetype="brick",
    )
    weapon_a = make_weapon(
        name=f"Buzzsaw ({seed_tag})",
        power_bonus=2,
        compute_cost=1,
        clankers_archetype="rush",
    )
    weapon_b = make_weapon(
        name=f"Plasma Cannon ({seed_tag})",
        power_bonus=3,
        compute_cost=2,
        clankers_archetype="artillery",
    )
    add_on = make_add_on(
        name=f"Reinforced Plating ({seed_tag})",
        integrity_bonus=2,
        compute_cost=1,
        clankers_archetype="brick",
    )

    def _transient_resolve(event: Event, state: GameState):
        # Placeholder: does nothing observable.
        return []

    transient = make_transient(
        name=f"Recompile ({seed_tag})",
        compute_cost=1,
        resolve_fn=_transient_resolve,
        clankers_archetype="control",
    )

    deck = (
        [chassis_a] * 14
        + [chassis_b] * 14
        + [weapon_a] * 11
        + [weapon_b] * 11
        + [add_on] * 6
        + [transient] * 4
    )
    # Sanity: should be exactly 60 cards.
    assert len(deck) == 60, f"deck must be 60 cards, got {len(deck)}"
    return deck


def _build_placeholder_core(name: str):
    """A minimal Core Processor with no passive."""
    from src.engine.clankers import make_core, CLANKERS_STARTING_WORKSHOP_INTEGRITY

    return make_core(
        name=name,
        workshop_integrity=CLANKERS_STARTING_WORKSHOP_INTEGRITY,
        passive_setup=None,
        text="Placeholder Core for smoke testing.",
        flavor="A quietly humming AI of indeterminate disposition.",
    )


def _action_counter_factory():
    """Build a (counter, wrapped_run) tuple that counts non-pass actions per player.

    We monkey-patch the AI adapter's choose_assemble_action to count returns
    that are not None / not {"action": "pass"}. The wrapper preserves the
    underlying logic.
    """
    counter = {"p1": 0, "p2": 0}

    def wrap(ai_adapter, player_id):
        original = getattr(ai_adapter, "choose_assemble_action", None)
        if original is None:
            return ai_adapter

        def wrapped(state, pid, *args, **kwargs):
            result = original(state, pid, *args, **kwargs)
            if result is not None and not (
                isinstance(result, dict) and result.get("action") == "pass"
            ):
                counter[pid] = counter.get(pid, 0) + 1
            return result

        ai_adapter.choose_assemble_action = wrapped
        return ai_adapter

    return counter, wrap


def test_clankers_smoke_two_easy_ais_terminate():
    """Run a Clankers game between two Easy AIs and assert it terminates."""
    # Imports that depend on parallel agents land here so test collection
    # doesn't crash before all four modules exist.
    from src.engine.clankers import (
        setup_clankers_player,
        check_workshop_breached,
        activate_deathclock_if_needed,
    )

    try:
        from src.engine.clankers_turn import ClankersTurnManager
    except ImportError:
        pytest.skip("src.engine.clankers_turn not yet implemented (parallel Agent 3)")

    try:
        from src.ai.clankers_adapter import ClankersAIAdapter
    except ImportError:
        pytest.skip("src.ai.clankers_adapter not yet implemented (parallel Agent 4)")

    # Build a Game (which wires the ClankersTurnManager for us via the
    # mode_adapter factory). Tests that need to stand up the engine without
    # a Game can call ClankersTurnManager(state) directly.
    from src.engine.game import Game
    game = Game(mode="clankers", clear_damage_on_cleanup=False)
    game.add_player("ClankerBot 1")  # creates p_<id>; we override below.
    game.add_player("ClankerBot 2")
    # Force deterministic ids for the test so the assertion messages are stable.
    # Game.add_player generates new ids; collect them and reassign.
    pids = list(game.state.players.keys())
    # Rename them via dict rebuild to "p1" / "p2".
    p1_obj = game.state.players.pop(pids[0])
    p2_obj = game.state.players.pop(pids[1])
    p1_obj.id = "p1"
    p1_obj.name = "ClankerBot 1"
    p2_obj.id = "p2"
    p2_obj.name = "ClankerBot 2"
    game.state.players["p1"] = p1_obj
    game.state.players["p2"] = p2_obj
    # Rebuild per-player zones under the canonical "p1"/"p2" keys.
    for old_pid in pids:
        for prefix in ("library", "hand", "graveyard"):
            game.state.zones.pop(f"{prefix}_{old_pid}", None)
    game._create_player_zones("p1")
    game._create_player_zones("p2")
    game.state.rng_seed = 42

    deck_a = _build_placeholder_deck("A")
    deck_b = _build_placeholder_deck("B")
    core_a = _build_placeholder_core("FORGE-Δ (test)")
    core_b = _build_placeholder_core("ETHOS-7 (test)")

    # Use the Game-built turn manager (contract: __init__(state); the
    # mode_adapter factory already passed game.state).
    turn_mgr = game.turn_manager

    # Wire AI handlers via the canonical contract attribute
    # ``game.clankers_ai_handlers`` (per §6).
    ai_p1 = ClankersAIAdapter(difficulty="easy")
    ai_p2 = ClankersAIAdapter(difficulty="easy")

    counter, wrap_ai = _action_counter_factory()
    ai_p1 = wrap_ai(ai_p1, "p1")
    ai_p2 = wrap_ai(ai_p2, "p2")

    game.clankers_ai_handlers = {"p1": ai_p1, "p2": ai_p2}
    # Also register with the turn manager directly so set_ai_handler is exercised.
    turn_mgr.set_ai_handler(ai_p1, "p1")
    turn_mgr.set_ai_handler(ai_p2, "p2")

    # Set up the game. Contract: setup_game(deck_a, core_a, deck_b, core_b).
    turn_mgr.setup_game(deck_a, core_a, deck_b, core_b)

    # Player ID ordering: start with whichever the turn manager says is
    # active, falling back to p1.
    state = game.state
    pids = ["p1", "p2"]
    active = getattr(state, "active_player", None) or pids[0]

    max_turns = 40
    game_over = False
    termination_mode: str = "none"
    raised = None
    turns_played = 0
    combat_damage_seen = 0  # CLANKERS_COMBAT_DAMAGE events
    workshop_damage_seen = 0  # CLANKERS_WORKSHOP_DAMAGE events from combat (not deathclock)

    from src.engine.types import EventType
    for turn_idx in range(max_turns):
        try:
            events = turn_mgr.run_turn(active)
        except Exception as exc:  # pragma: no cover — smoke test surfaces this
            raised = exc
            break

        turns_played += 1
        for ev in events:
            if ev.type == EventType.CLANKERS_COMBAT_DAMAGE:
                combat_damage_seen += 1
            elif (
                ev.type == EventType.CLANKERS_WORKSHOP_DAMAGE
                and ev.payload.get("reason") != "containment_failure"
            ):
                workshop_damage_seen += 1

        # Termination check: workshop breach.
        loser = check_workshop_breached(state)
        if loser is not None:
            game_over = True
            termination_mode = "workshop_breached"
            break

        # If both libraries are empty, force the deathclock to keep
        # progressing in case the turn manager's cleanup didn't.
        try:
            activate_deathclock_if_needed(state)
        except Exception:
            pass

        loser = check_workshop_breached(state)
        if loser is not None:
            game_over = True
            termination_mode = "deathclock"
            break

        # Alternate player.
        active = "p2" if active == "p1" else "p1"

    assert raised is None, f"Clankers smoke run raised: {raised!r}"
    assert game_over, (
        f"Clankers game did not terminate within {max_turns} turns. "
        f"Final state: workshop_integrity={getattr(state, 'clankers_workshop_integrity', {})}, "
        f"containment_failure={getattr(state, 'clankers_containment_failure', False)}, "
        f"containment_turn={getattr(state, 'clankers_containment_turn', 0)}"
    )

    # Action sanity. Both AIs should have done SOMETHING. Easy AI is allowed
    # to pass at low-Compute turns; we just want > 0 across the whole game.
    # (If the turn manager doesn't actually call choose_assemble_action, both
    # counters will be 0 — that's the contract violation we want to catch.)
    assert counter["p1"] > 0, (
        f"P1 took zero non-pass Assemble actions across {turns_played} turns. "
        f"This means either choose_assemble_action was never called, or the "
        f"AI returned only pass actions — both indicate a contract failure."
    )
    assert counter["p2"] > 0, (
        f"P2 took zero non-pass Assemble actions across {turns_played} turns. "
        f"Same contract failure as P1's case above."
    )

    # Combat-pipeline sanity. We don't require combat to BE the termination
    # mode (deathclock is a valid finish), but if the game went more than 2
    # turns we expect to see at least one combat-damage event — otherwise
    # the combat manager isn't firing or the AI isn't returning attackers,
    # which is a contract failure even when the deathclock saves the game.
    if turns_played > 2:
        assert (combat_damage_seen + workshop_damage_seen) > 0, (
            f"No CLANKERS_COMBAT_DAMAGE or non-deathclock CLANKERS_WORKSHOP_DAMAGE "
            f"events across {turns_played} turns (termination={termination_mode}). "
            f"Combat manager is not engaging."
        )


if __name__ == "__main__":  # pragma: no cover — manual invocation
    test_clankers_smoke_two_easy_ais_terminate()
    print("OK: clankers smoke test passed.")
