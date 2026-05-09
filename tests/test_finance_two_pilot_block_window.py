"""
Regression test for the Finance two-pilot wet-test harness block window.

When P1 (active player) declares attackers and ends the turn in two-pilot
mode, the harness must:
  1. Advance to SETTLEMENT phase, set ``awaiting_blocks=True``, and STOP
     before resolving combat damage (so P2's pilot has a chance to block).
  2. Accept ``block <blocker_id> <attacker_id>`` from the *defender* —
     i.e. the seat opposite ``state.active_player`` — during the window.
  3. Run combat damage and finish the active player's turn when
     ``resolve_combat`` is issued (or ``end_turn`` is issued a second
     time as a forgiving alias).
  4. Hand control to the defender's PRE_MARKET + RESEARCH so their pilot
     can take actions on their own turn.

This regression covers the bug Pilot B's iter-1 report flagged:
"blocking is not wired in two-pilot harness".

Run directly:  python tests/test_finance_two_pilot_block_window.py
"""

from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

# We test the harness internals directly (subprocess-loading every CLI call
# through `python -m` would be slow and add fragile dependencies on disk
# paths). The harness is a pure module — `cmd_*` functions take an
# argparse-Namespace-like object with a `save` attribute.
from scripts.play import finance_wet_test as harness  # noqa: E402
from src.engine.finance_turn import FinancePhase  # noqa: E402


class _Args:
    """Tiny stand-in for argparse Namespace."""

    def __init__(self, save: str, **kwargs):
        self.save = save
        for k, v in kwargs.items():
            setattr(self, k, v)


def _load(path):
    return harness._load(path)


def _start_two_pilot(save_path: str, seed: int = 42) -> dict:
    args = _Args(
        save=save_path,
        p1_deck="FINA_high_frequency",
        p2_deck="FINA_quant",
        two_pilot=True,
        seed=seed,
    )
    harness.cmd_start(args)
    return _load(save_path)


def _give_p1_attacker(payload: dict) -> str:
    """Force a fresh, non-summoning-sick Trader onto P1's battlefield.

    Bypasses ``_play_card_action`` (which requires the right phase + cost)
    so we can test the block window deterministically regardless of which
    deck shuffle landed.
    """
    from src.engine.types import CardType, ZoneType, new_id, GameObject, ObjectState

    game = payload["game"]
    state = game.state
    p1_id = payload["p1_id"]

    # Find a TRADER card def in P1's library and lift it directly to the
    # battlefield. This sidesteps cost / phase gating.
    library = state.zones.get(f"library_{p1_id}")
    assert library is not None, "P1 library missing"
    trader_oid = None
    for oid in list(library.objects):
        obj = state.objects.get(oid)
        if obj is None:
            continue
        if CardType.FIN_TRADER in obj.characteristics.types:
            trader_oid = oid
            break
    assert trader_oid is not None, "no FIN_TRADER found in P1 library"

    obj = state.objects[trader_oid]
    library.objects.remove(trader_oid)
    bf = state.zones.get("battlefield")
    assert bf is not None
    bf.objects.append(trader_oid)
    obj.zone = ZoneType.BATTLEFIELD
    obj.controller = p1_id
    obj.state.tapped = False
    obj.state.summoning_sickness = False  # ready to attack THIS turn
    return trader_oid


def _give_p2_blocker(payload: dict) -> str:
    """Same idea, but for P2 — drop a Trader on the battlefield to block."""
    from src.engine.types import CardType, ZoneType

    game = payload["game"]
    state = game.state
    p2_id = payload["p2_id"]

    library = state.zones.get(f"library_{p2_id}")
    assert library is not None
    blocker_oid = None
    for oid in list(library.objects):
        obj = state.objects.get(oid)
        if obj is None:
            continue
        if CardType.FIN_TRADER in obj.characteristics.types:
            blocker_oid = oid
            break
    assert blocker_oid is not None

    obj = state.objects[blocker_oid]
    library.objects.remove(blocker_oid)
    bf = state.zones.get("battlefield")
    bf.objects.append(blocker_oid)
    obj.zone = ZoneType.BATTLEFIELD
    obj.controller = p2_id
    obj.state.tapped = False
    obj.state.summoning_sickness = False  # ready to block
    return blocker_oid


def test_two_pilot_block_window_opens_on_end_turn():
    """`end_turn` with declared attackers gates on awaiting_blocks=True."""
    with tempfile.NamedTemporaryFile(suffix=".pkl", delete=False) as fh:
        save = fh.name
    payload = _start_two_pilot(save)
    p1_id = payload["p1_id"]
    p2_id = payload["p2_id"]

    # Plant attacker on P1's side.
    attacker_oid = _give_p1_attacker(payload)
    _give_p2_blocker(payload)
    harness._save(payload, save)

    # P1 declares attacker.
    harness.cmd_attack(_Args(save=save, attackers=[attacker_oid]))
    payload = _load(save)
    assert attacker_oid in payload["game"].turn_manager.fin_turn_state.attackers_declared
    assert payload.get("awaiting_blocks") is False

    # P1 ends turn — should open block window, NOT resolve combat.
    harness.cmd_end_turn(_Args(save=save))
    payload = _load(save)
    assert payload["awaiting_blocks"] is True, (
        "end_turn with declared attackers must open block window, not resolve combat"
    )
    tm = payload["game"].turn_manager
    assert tm.fin_turn_state.phase == FinancePhase.SETTLEMENT
    assert payload["game"].state.active_player == p1_id, (
        "active_player must remain P1 (the attacker) until combat resolves"
    )
    # No damage dealt yet.
    p2 = payload["game"].state.players[p2_id]
    assert p2.life == 30, f"no combat damage should be dealt yet, got p2.life={p2.life}"

    Path(save).unlink(missing_ok=True)
    print("test_two_pilot_block_window_opens_on_end_turn  PASS")


def test_block_command_routes_to_defender_during_window():
    """`block` issued while awaiting_blocks=True records on combat_blocks
    even though the defender is NOT state.active_player."""
    with tempfile.NamedTemporaryFile(suffix=".pkl", delete=False) as fh:
        save = fh.name
    payload = _start_two_pilot(save)

    attacker_oid = _give_p1_attacker(payload)
    blocker_oid = _give_p2_blocker(payload)
    harness._save(payload, save)

    harness.cmd_attack(_Args(save=save, attackers=[attacker_oid]))
    harness.cmd_end_turn(_Args(save=save))  # opens block window
    payload = _load(save)
    assert payload["awaiting_blocks"] is True

    # Defender records a block. NOTE: state.active_player is still P1
    # (the attacker), but the harness must accept the block from P2.
    harness.cmd_block(
        _Args(save=save, blocker_id=blocker_oid, attacker_id=attacker_oid)
    )
    payload = _load(save)
    blocks = payload["game"].turn_manager.fin_turn_state.combat_blocks
    assert blocks.get(attacker_oid) == blocker_oid, (
        f"expected combat_blocks[{attacker_oid}]={blocker_oid}, got {blocks!r}"
    )

    Path(save).unlink(missing_ok=True)
    print("test_block_command_routes_to_defender_during_window  PASS")


def test_resolve_combat_runs_damage_and_advances_turn():
    """resolve_combat after the defender blocks: combat resolves, active
    turn finishes, defender becomes the new active player in
    TRADING_SESSION."""
    with tempfile.NamedTemporaryFile(suffix=".pkl", delete=False) as fh:
        save = fh.name
    payload = _start_two_pilot(save)
    p1_id = payload["p1_id"]
    p2_id = payload["p2_id"]

    attacker_oid = _give_p1_attacker(payload)
    blocker_oid = _give_p2_blocker(payload)
    harness._save(payload, save)

    harness.cmd_attack(_Args(save=save, attackers=[attacker_oid]))
    harness.cmd_end_turn(_Args(save=save))  # opens block window
    harness.cmd_block(
        _Args(save=save, blocker_id=blocker_oid, attacker_id=attacker_oid)
    )
    # Now resolve.
    harness.cmd_resolve_combat(_Args(save=save))
    payload = _load(save)

    # Block window cleared.
    assert payload.get("awaiting_blocks") is False
    # Active player is now P2 (defender), in TRADING_SESSION on their turn.
    game = payload["game"]
    assert game.state.active_player == p2_id, (
        f"expected active=P2 after resolve, got {game.state.active_player}"
    )
    tm = game.turn_manager
    assert tm.fin_turn_state.phase == FinancePhase.TRADING_SESSION
    # Combat actually fired — at least one Trader took damage. Both the
    # attacker and the blocker must have been touched by the combat
    # manager (damage > 0 OR moved off the battlefield).
    atk_obj = game.state.objects.get(attacker_oid)
    blk_obj = game.state.objects.get(blocker_oid)
    from src.engine.types import ZoneType
    atk_touched = (
        atk_obj is not None
        and (atk_obj.state.damage > 0 or atk_obj.zone != ZoneType.BATTLEFIELD)
    )
    blk_touched = (
        blk_obj is not None
        and (blk_obj.state.damage > 0 or blk_obj.zone != ZoneType.BATTLEFIELD)
    )
    assert atk_touched, "attacker must have taken combat damage"
    assert blk_touched, "blocker must have taken combat damage"

    Path(save).unlink(missing_ok=True)
    print("test_resolve_combat_runs_damage_and_advances_turn  PASS")


def test_end_turn_no_attackers_advances_directly():
    """end_turn with NO attackers declared must advance to next pilot
    without opening a block window."""
    with tempfile.NamedTemporaryFile(suffix=".pkl", delete=False) as fh:
        save = fh.name
    payload = _start_two_pilot(save)
    p1_id = payload["p1_id"]
    p2_id = payload["p2_id"]

    # Don't declare any attackers — just end_turn.
    harness.cmd_end_turn(_Args(save=save))
    payload = _load(save)
    assert payload.get("awaiting_blocks") is False
    assert payload["game"].state.active_player == p2_id, (
        "no-attacker end_turn must advance immediately to next player"
    )

    Path(save).unlink(missing_ok=True)
    print("test_end_turn_no_attackers_advances_directly  PASS")


def test_second_end_turn_during_block_window_resolves_combat():
    """Forgiving alias: a second end_turn while awaiting_blocks=True
    behaves as resolve_combat."""
    with tempfile.NamedTemporaryFile(suffix=".pkl", delete=False) as fh:
        save = fh.name
    payload = _start_two_pilot(save)
    p1_id = payload["p1_id"]
    p2_id = payload["p2_id"]

    attacker_oid = _give_p1_attacker(payload)
    _give_p2_blocker(payload)
    harness._save(payload, save)

    harness.cmd_attack(_Args(save=save, attackers=[attacker_oid]))
    harness.cmd_end_turn(_Args(save=save))  # opens block window
    payload = _load(save)
    assert payload["awaiting_blocks"] is True

    # Second end_turn should be treated as resolve_combat.
    harness.cmd_end_turn(_Args(save=save))
    payload = _load(save)
    assert payload.get("awaiting_blocks") is False
    assert payload["game"].state.active_player == p2_id

    Path(save).unlink(missing_ok=True)
    print("test_second_end_turn_during_block_window_resolves_combat  PASS")


def test_single_pilot_mode_unchanged():
    """Single-pilot mode (no --two-pilot) must NOT open a block window.
    Combat resolves synchronously inside end_turn via the AI's
    choose_blockers path."""
    with tempfile.NamedTemporaryFile(suffix=".pkl", delete=False) as fh:
        save = fh.name

    args = _Args(
        save=save,
        p1_deck="FINA_high_frequency",
        p2_deck="FINA_quant",
        two_pilot=False,
        seed=7,
    )
    harness.cmd_start(args)
    payload = _load(save)
    assert payload["two_pilot"] is False
    p1_id = payload["p1_id"]

    attacker_oid = _give_p1_attacker(payload)
    harness._save(payload, save)

    harness.cmd_attack(_Args(save=save, attackers=[attacker_oid]))
    # In single-pilot mode end_turn must finish the turn AND run AI's
    # whole turn synchronously, landing back on P1.
    harness.cmd_end_turn(_Args(save=save))
    payload = _load(save)
    # The block-window flag must NOT be set in single-pilot mode.
    assert payload.get("awaiting_blocks") is False, (
        "single-pilot mode must never enter the block window"
    )
    # We should be back on P1's turn (AI has taken its turn).
    assert payload["game"].state.active_player == p1_id

    Path(save).unlink(missing_ok=True)
    print("test_single_pilot_mode_unchanged  PASS")


# ---------------------------------------------------------------------------
# Bug #11 — pickle file-race / fcntl lock
# ---------------------------------------------------------------------------

def test_round_id_increments_on_each_save():
    """Bug #11 telemetry — every successful mutation must bump round_id so a
    pilot can detect intervening writes between their `state` and action."""
    with tempfile.NamedTemporaryFile(suffix=".pkl", delete=False) as fh:
        save = fh.name
    payload = _start_two_pilot(save)
    initial_round = int(payload.get("round_id", 0))
    assert initial_round >= 1, (
        f"Bug #11: round_id should be ≥1 after start, got {initial_round}"
    )

    # Calling end_turn (no attackers) must bump round_id.
    harness.cmd_end_turn(_Args(save=save))
    payload2 = _load(save)
    assert int(payload2.get("round_id", 0)) > initial_round, (
        f"Bug #11: round_id must monotonically increase per save; "
        f"before={initial_round} after={payload2.get('round_id')}"
    )
    Path(save).unlink(missing_ok=True)
    Path(save + ".lock").unlink(missing_ok=True)
    print("test_round_id_increments_on_each_save  PASS")


def _bug11_lock_worker(save_path: str):
    """Top-level worker for test_concurrent_play_is_serialized_by_fcntl_lock.

    Must be at module scope (not a closure) so the spawn-context fork on
    macOS can pickle/unpickle the target.
    """
    import time as _t
    # Re-import in the child since spawn context starts a fresh interpreter.
    import sys as _sys
    from pathlib import Path as _P
    repo_root = _P(__file__).resolve().parents[1]
    if str(repo_root) not in _sys.path:
        _sys.path.insert(0, str(repo_root))
    from scripts.play import finance_wet_test as _h
    with _h._exclusive_lock(save_path):
        pl = _h._load(save_path)
        _t.sleep(0.05)  # widen the window so concurrency is real
        _h._save(pl, save_path)


def test_concurrent_play_is_serialized_by_fcntl_lock():
    """Bug #11 — two subprocesses both running an RMW against the same pickle
    must serialize via fcntl.flock; both writes land (no lost updates)."""
    import multiprocessing as _mp

    with tempfile.NamedTemporaryFile(suffix=".pkl", delete=False) as fh:
        save = fh.name
    _start_two_pilot(save)

    # Spawn two child processes (default on macOS) and have each acquire the
    # exclusive lock for ~50ms before writing. If the lock is honoured,
    # round_id increments deterministically by 2; if not, the read-modify-
    # write windows interleave and one increment is lost.
    ctx = _mp.get_context("spawn")
    procs = [
        ctx.Process(target=_bug11_lock_worker, args=(save,)),
        ctx.Process(target=_bug11_lock_worker, args=(save,)),
    ]
    initial = int(_load(save).get("round_id", 0))
    for p in procs:
        p.start()
    for p in procs:
        p.join(timeout=15)
    for p in procs:
        assert not p.is_alive(), "worker hung — flock deadlock?"
        assert p.exitcode == 0, f"worker crashed exitcode={p.exitcode}"

    final = _load(save)
    final_round = int(final.get("round_id", 0))
    expected = initial + 2
    assert final_round == expected, (
        f"Bug #11: lock must serialize concurrent saves; "
        f"initial={initial} expected={expected} got={final_round} "
        f"(missing increments → lost-update race)"
    )

    Path(save).unlink(missing_ok=True)
    Path(save + ".lock").unlink(missing_ok=True)
    print("test_concurrent_play_is_serialized_by_fcntl_lock  PASS")


# ---------------------------------------------------------------------------
# Bug #20b — `choose` subcommand for tutor PendingChoice
# ---------------------------------------------------------------------------

def test_choose_command_resolves_tutor_pending_choice():
    """Bug #20b — induce a SEARCH_LIBRARY tutor PendingChoice (via Dark
    Inventory Position's ETB), then call cmd_choose to submit a pick.
    Game must advance with the chosen card moving to the player's hand."""
    with tempfile.NamedTemporaryFile(suffix=".pkl", delete=False) as fh:
        save = fh.name
    payload = _start_two_pilot(save)
    p1_id = payload["p1_id"]

    from src.engine.types import CardType, ZoneType
    from src.cards.finance.fina.dark_arbitrage import (
        ICEBERG_ORDER, BLOCK_TRADE_SWEEP,
    )
    game = payload["game"]
    state = game.state

    # Inject Iceberg + BTS into P1's library so the tutor has options.
    ico = game.create_object(
        name="ICO", owner_id=p1_id, zone=ZoneType.LIBRARY,
        characteristics=ICEBERG_ORDER.characteristics,
        card_def=ICEBERG_ORDER,
    )
    bts = game.create_object(
        name="BTS", owner_id=p1_id, zone=ZoneType.LIBRARY,
        characteristics=BLOCK_TRADE_SWEEP.characteristics,
        card_def=BLOCK_TRADE_SWEEP,
    )

    # Manually emit SEARCH_LIBRARY (filter=dark_pool_order) — this is the
    # simulation of Dark Inventory Position's ETB tutor.
    from src.engine.types import Event, EventType
    from src.engine.library_search import _handle_search_library_event
    evt = Event(
        type=EventType.SEARCH_LIBRARY,
        payload={
            "player": p1_id,
            "filter": "dark_pool_order",
            "destination": "hand",
            "count": 1,
            "min_count": 0,
        },
        source="dip_test",
    )
    _handle_search_library_event(evt, state)
    assert state.pending_choice is not None, (
        "Bug #20b setup: tutor must produce a PendingChoice"
    )
    chosen_id = ico.id  # arbitrary pick

    harness._save(payload, save)
    # Now invoke cmd_choose with the index of Iceberg's option.
    # We pass the id-prefix so the harness exercises both code paths.
    args = _Args(save=save, options=[chosen_id[:6]])
    harness.cmd_choose(args)

    payload2 = _load(save)
    state2 = payload2["game"].state
    # Pending choice must be cleared.
    assert state2.pending_choice is None, (
        "Bug #20b: cmd_choose must clear pending_choice after submitting"
    )
    # Iceberg must now be in P1's hand.
    hand_zone = state2.zones.get(f"hand_{p1_id}")
    assert hand_zone is not None and chosen_id in hand_zone.objects, (
        f"Bug #20b: chosen card must be moved to hand; hand="
        f"{hand_zone.objects if hand_zone else None}"
    )

    Path(save).unlink(missing_ok=True)
    Path(save + ".lock").unlink(missing_ok=True)
    print("test_choose_command_resolves_tutor_pending_choice  PASS")


def test_choose_command_no_pending_choice_is_noop():
    """Bug #20b — `choose` with no pending choice must report and not crash."""
    with tempfile.NamedTemporaryFile(suffix=".pkl", delete=False) as fh:
        save = fh.name
    _start_two_pilot(save)
    args = _Args(save=save, options=["0"])
    # Should not raise.
    harness.cmd_choose(args)
    Path(save).unlink(missing_ok=True)
    Path(save + ".lock").unlink(missing_ok=True)
    print("test_choose_command_no_pending_choice_is_noop  PASS")


if __name__ == "__main__":
    test_two_pilot_block_window_opens_on_end_turn()
    test_block_command_routes_to_defender_during_window()
    test_resolve_combat_runs_damage_and_advances_turn()
    test_end_turn_no_attackers_advances_directly()
    test_second_end_turn_during_block_window_resolves_combat()
    test_single_pilot_mode_unchanged()
    test_round_id_increments_on_each_save()
    test_concurrent_play_is_serialized_by_fcntl_lock()
    test_choose_command_resolves_tutor_pending_choice()
    test_choose_command_no_pending_choice_is_noop()
    print("\nAll two-pilot block-window tests passed.")
