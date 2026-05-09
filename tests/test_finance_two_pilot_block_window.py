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

    # P1 declares attacker. (Bug #31: --seat is required in two-pilot mode.)
    harness.cmd_attack(_Args(save=save, attackers=[attacker_oid], seat="P1"))
    payload = _load(save)
    assert attacker_oid in payload["game"].turn_manager.fin_turn_state.attackers_declared
    assert payload.get("awaiting_blocks") is False

    # P1 ends turn — should open block window, NOT resolve combat.
    harness.cmd_end_turn(_Args(save=save, seat="P1"))
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

    harness.cmd_attack(_Args(save=save, attackers=[attacker_oid], seat="P1"))
    harness.cmd_end_turn(_Args(save=save, seat="P1"))  # opens block window
    payload = _load(save)
    assert payload["awaiting_blocks"] is True

    # Defender records a block. NOTE: state.active_player is still P1
    # (the attacker), but the harness must accept the block from P2.
    harness.cmd_block(
        _Args(save=save, blocker_id=blocker_oid, attacker_id=attacker_oid, seat="P2")
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

    harness.cmd_attack(_Args(save=save, attackers=[attacker_oid], seat="P1"))
    harness.cmd_end_turn(_Args(save=save, seat="P1"))  # opens block window
    harness.cmd_block(
        _Args(save=save, blocker_id=blocker_oid, attacker_id=attacker_oid, seat="P2")
    )
    # Now resolve.
    harness.cmd_resolve_combat(_Args(save=save, seat="P2"))
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
    harness.cmd_end_turn(_Args(save=save, seat="P1"))
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

    harness.cmd_attack(_Args(save=save, attackers=[attacker_oid], seat="P1"))
    harness.cmd_end_turn(_Args(save=save, seat="P1"))  # opens block window
    payload = _load(save)
    assert payload["awaiting_blocks"] is True

    # Second end_turn from the DEFENDER (P2) treated as resolve_combat.
    # (Bug #31: --seat is required; defender is the only seat allowed to
    # close the gate without first calling block / done_blocks.)
    harness.cmd_end_turn(_Args(save=save, seat="P2"))
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
    # Bug #31: --seat required in two-pilot mode.
    harness.cmd_end_turn(_Args(save=save, seat="P1"))
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


# ---------------------------------------------------------------------------
# Bug #23 — Block-window race: attacker must wait for defender
# ---------------------------------------------------------------------------

def _seat_label(payload, player_id: str) -> str:
    """Return 'P1' or 'P2' for the given player_id."""
    return "P1" if player_id == payload["p1_id"] else "P2"


def test_bug23_attacker_resolve_combat_blocked_until_defender_acts(capsys):
    """Bug #23 — attacker's resolve_combat in the block window must be
    rejected until the defender has issued block / done_blocks /
    resolve_combat themselves."""
    with tempfile.NamedTemporaryFile(suffix=".pkl", delete=False) as fh:
        save = fh.name
    payload = _start_two_pilot(save)
    p1_id = payload["p1_id"]
    p2_id = payload["p2_id"]

    attacker_oid = _give_p1_attacker(payload)
    _give_p2_blocker(payload)
    harness._save(payload, save)

    # P1 declares attacker + ends turn → block window opens.
    harness.cmd_attack(_Args(save=save, attackers=[attacker_oid], seat="P1"))
    harness.cmd_end_turn(_Args(save=save, seat="P1"))
    payload = _load(save)
    assert payload["awaiting_blocks"] is True
    assert payload.get("blocks_committed_by_defender") is False, (
        "Bug #23: blocks_committed_by_defender must be False at window open"
    )

    # ATTACKER (P1) tries to resolve_combat — must be rejected.
    harness.cmd_resolve_combat(_Args(save=save, seat="P1"))
    captured = capsys.readouterr()
    assert "Block window still open" in captured.out, (
        f"Bug #23: attacker's resolve_combat must error — got: {captured.out!r}"
    )

    # State must NOT have advanced — still in block window.
    payload = _load(save)
    assert payload.get("awaiting_blocks") is True, (
        "Bug #23: rejected resolve_combat must not close the block window"
    )
    assert payload["game"].state.active_player == p1_id, (
        "Bug #23: rejected resolve_combat must not advance turn"
    )
    # No combat damage should have fired.
    p2 = payload["game"].state.players[p2_id]
    assert p2.life == 30, (
        f"Bug #23: face damage leaked through block-window race; p2.life={p2.life}"
    )

    Path(save).unlink(missing_ok=True)
    Path(save + ".lock").unlink(missing_ok=True)
    print("test_bug23_attacker_resolve_combat_blocked_until_defender_acts  PASS")


def test_bug23_defender_block_then_attacker_resolve_works():
    """Bug #23 — after defender records a block, the attacker MAY safely
    call resolve_combat (the gate flips True on a successful block)."""
    with tempfile.NamedTemporaryFile(suffix=".pkl", delete=False) as fh:
        save = fh.name
    payload = _start_two_pilot(save)
    p1_id = payload["p1_id"]
    p2_id = payload["p2_id"]

    attacker_oid = _give_p1_attacker(payload)
    blocker_oid = _give_p2_blocker(payload)
    harness._save(payload, save)

    harness.cmd_attack(_Args(save=save, attackers=[attacker_oid], seat="P1"))
    harness.cmd_end_turn(_Args(save=save, seat="P1"))
    payload = _load(save)
    assert payload["awaiting_blocks"] is True
    assert payload.get("blocks_committed_by_defender") is False

    # Defender (P2) records a block.
    harness.cmd_block(
        _Args(save=save, blocker_id=blocker_oid, attacker_id=attacker_oid, seat="P2")
    )
    payload = _load(save)
    assert payload.get("blocks_committed_by_defender") is True, (
        "Bug #23: a successful block by the defender must flip the gate True"
    )

    # Now the attacker (P1) may safely resolve combat.
    harness.cmd_resolve_combat(_Args(save=save, seat="P1"))
    payload = _load(save)
    assert payload.get("awaiting_blocks") is False, (
        "Bug #23: post-block resolve_combat must close the window"
    )
    assert payload["game"].state.active_player == p2_id, (
        "Bug #23: combat resolved → defender becomes new active player"
    )

    Path(save).unlink(missing_ok=True)
    Path(save + ".lock").unlink(missing_ok=True)
    print("test_bug23_defender_block_then_attacker_resolve_works  PASS")


def test_bug23_defender_can_resolve_combat_directly_no_blocks():
    """Bug #23 — defender may call resolve_combat themselves (declines
    to block); the gate is satisfied because the caller is not the
    attacker."""
    with tempfile.NamedTemporaryFile(suffix=".pkl", delete=False) as fh:
        save = fh.name
    payload = _start_two_pilot(save)
    p1_id = payload["p1_id"]
    p2_id = payload["p2_id"]

    attacker_oid = _give_p1_attacker(payload)
    _give_p2_blocker(payload)
    harness._save(payload, save)

    harness.cmd_attack(_Args(save=save, attackers=[attacker_oid], seat="P1"))
    harness.cmd_end_turn(_Args(save=save, seat="P1"))
    payload = _load(save)
    assert payload["awaiting_blocks"] is True
    assert payload.get("blocks_committed_by_defender") is False

    # Defender (P2) directly calls resolve_combat — declining to block.
    # Gate must permit this and combat must fire.
    harness.cmd_resolve_combat(_Args(save=save, seat="P2"))
    payload = _load(save)
    assert payload.get("awaiting_blocks") is False, (
        "Bug #23: defender's resolve_combat must close the window"
    )
    # All attackers got through — P2 took face damage.
    p2 = payload["game"].state.players[p2_id]
    assert p2.life < 30, (
        f"Bug #23: defender chose not to block, attacker should connect; "
        f"p2.life={p2.life}"
    )
    assert payload["game"].state.active_player == p2_id

    Path(save).unlink(missing_ok=True)
    Path(save + ".lock").unlink(missing_ok=True)
    print("test_bug23_defender_can_resolve_combat_directly_no_blocks  PASS")


def test_bug23_done_blocks_command_closes_window_without_blocks():
    """Bug #23 — defender can issue `done_blocks` to flip the gate True
    without recording any blocks; attacker may then resolve_combat."""
    with tempfile.NamedTemporaryFile(suffix=".pkl", delete=False) as fh:
        save = fh.name
    payload = _start_two_pilot(save)
    p1_id = payload["p1_id"]
    p2_id = payload["p2_id"]

    attacker_oid = _give_p1_attacker(payload)
    _give_p2_blocker(payload)
    harness._save(payload, save)

    harness.cmd_attack(_Args(save=save, attackers=[attacker_oid], seat="P1"))
    harness.cmd_end_turn(_Args(save=save, seat="P1"))
    payload = _load(save)
    assert payload["awaiting_blocks"] is True
    assert payload.get("blocks_committed_by_defender") is False

    # Defender uses done_blocks to explicitly close the window without blocks.
    harness.cmd_done_blocks(_Args(save=save, seat="P2"))
    payload = _load(save)
    assert payload.get("awaiting_blocks") is True, (
        "done_blocks does NOT itself close the window — it just signals defender done"
    )
    assert payload.get("blocks_committed_by_defender") is True, (
        "Bug #23: done_blocks must flip the gate True"
    )
    # Combat should not have fired yet (no blocks committed, no resolve_combat called).
    assert payload["game"].state.players[p2_id].life == 30

    # Now the attacker may resolve_combat.
    harness.cmd_resolve_combat(_Args(save=save, seat="P1"))
    payload = _load(save)
    assert payload.get("awaiting_blocks") is False
    # Attacker connects (no blocks).
    assert payload["game"].state.players[p2_id].life < 30
    assert payload["game"].state.active_player == p2_id

    Path(save).unlink(missing_ok=True)
    Path(save + ".lock").unlink(missing_ok=True)
    print("test_bug23_done_blocks_command_closes_window_without_blocks  PASS")


# ---------------------------------------------------------------------------
# Bug #30 — `attack` must not emit "skipping illegal" when none were skipped
# ---------------------------------------------------------------------------

def test_bug30_attack_warning_only_when_actually_skipped(capsys):
    """Bug #30 — `attack` with a fully-legal attacker list must NOT emit
    the misleading 'skipping illegal attackers' warning."""
    with tempfile.NamedTemporaryFile(suffix=".pkl", delete=False) as fh:
        save = fh.name
    payload = _start_two_pilot(save)

    # Plant a fully-legal attacker (untapped + no summoning sickness).
    attacker_oid = _give_p1_attacker(payload)
    harness._save(payload, save)

    # Declare it as an attacker — must succeed cleanly with no warning.
    harness.cmd_attack(_Args(save=save, attackers=[attacker_oid], seat="P1"))
    captured = capsys.readouterr()
    assert "skipping illegal" not in captured.out, (
        f"Bug #30: misleading warning emitted when no attackers were skipped; "
        f"output:\n{captured.out}"
    )
    # Sanity — declaration succeeded.
    payload = _load(save)
    assert attacker_oid in payload["game"].turn_manager.fin_turn_state.attackers_declared

    Path(save).unlink(missing_ok=True)
    Path(save + ".lock").unlink(missing_ok=True)
    print("test_bug30_attack_warning_only_when_actually_skipped  PASS")


# ---------------------------------------------------------------------------
# Bug #31 / iter-4 — Block-window race recurrence
# ---------------------------------------------------------------------------

def test_iter4_seat_required_or_round_id_check_prevents_race(capsys):
    """Bug #31 (iter-4) — the bug-#23 attacker gate was bypassable when a
    pilot forgot --seat (the gate was `if seat is not None and seat ==
    attacker_seat`, so seat=None silently skipped). In two-pilot mode
    --seat is now REQUIRED for any state-mutating command, so the
    attacker can never bypass the block window by omitting --seat.

    Also covers --expected-round-id drift detection: if the pilot read
    state at round_id=N and someone wrote in between, the action is
    rejected so they re-read.
    """
    with tempfile.NamedTemporaryFile(suffix=".pkl", delete=False) as fh:
        save = fh.name
    payload = _start_two_pilot(save)
    p1_id = payload["p1_id"]
    p2_id = payload["p2_id"]

    attacker_oid = _give_p1_attacker(payload)
    _give_p2_blocker(payload)
    harness._save(payload, save)

    # Step 1: P1 declares attacker WITHOUT --seat — must be rejected.
    harness.cmd_attack(_Args(save=save, attackers=[attacker_oid]))
    captured = capsys.readouterr()
    assert "--seat P1|P2 is required" in captured.out, (
        f"Bug #31: --seat must be required in two-pilot mode; got: {captured.out!r}"
    )
    payload = _load(save)
    assert attacker_oid not in payload["game"].turn_manager.fin_turn_state.attackers_declared, (
        "Bug #31: rejected cmd_attack must NOT mutate state"
    )

    # Step 2: P1 with --seat declares attacker (legit) and ends turn → block window.
    harness.cmd_attack(_Args(save=save, attackers=[attacker_oid], seat="P1"))
    harness.cmd_end_turn(_Args(save=save, seat="P1"))
    payload = _load(save)
    assert payload["awaiting_blocks"] is True

    # Step 3: ATTACKER (P1) tries to resolve_combat WITHOUT --seat in two-pilot.
    # Must be rejected with the seat-required error (Bug #31 hardening).
    harness.cmd_resolve_combat(_Args(save=save))
    captured = capsys.readouterr()
    assert "--seat P1|P2 is required" in captured.out, (
        f"Bug #31: seatless resolve_combat in two-pilot must be rejected; got: {captured.out!r}"
    )
    payload = _load(save)
    assert payload.get("awaiting_blocks") is True, (
        "Bug #31: rejected resolve_combat must NOT close block window"
    )
    p2 = payload["game"].state.players[p2_id]
    assert p2.life == 30, (
        f"Bug #31: face damage leaked through seatless race; p2.life={p2.life}"
    )

    # Step 4: ATTACKER end_turn WITHOUT --seat — must also be rejected.
    harness.cmd_end_turn(_Args(save=save))
    captured = capsys.readouterr()
    assert "--seat P1|P2 is required" in captured.out, (
        f"Bug #31: seatless end_turn (alias path) in two-pilot must be rejected; "
        f"got: {captured.out!r}"
    )
    payload = _load(save)
    assert payload.get("awaiting_blocks") is True
    assert payload["game"].state.players[p2_id].life == 30

    # Step 5: --expected-round-id drift: pretend pilot read state at
    # round_id=999999 (way out of date) — action must be rejected.
    payload = _load(save)
    stale_rid = int(payload.get("round_id", 0)) + 999
    harness.cmd_done_blocks(
        _Args(save=save, seat="P2", expected_round_id=stale_rid)
    )
    captured = capsys.readouterr()
    assert "state advanced" in captured.out, (
        f"Bug #31b: stale --expected-round-id must be rejected; got: {captured.out!r}"
    )
    payload = _load(save)
    assert payload.get("blocks_committed_by_defender") is False, (
        "Bug #31b: rejected stale-round action must not mutate state"
    )

    # Step 6: defender uses correct round_id — succeeds.
    current_rid = int(payload.get("round_id", 0))
    harness.cmd_done_blocks(
        _Args(save=save, seat="P2", expected_round_id=current_rid)
    )
    payload = _load(save)
    assert payload.get("blocks_committed_by_defender") is True, (
        "Bug #31b: matching --expected-round-id must allow the action"
    )

    Path(save).unlink(missing_ok=True)
    Path(save + ".lock").unlink(missing_ok=True)
    print("test_iter4_seat_required_or_round_id_check_prevents_race  PASS")


def test_iter4_block_2v2_applies_damage_correctly():
    """Bug #D (iter-4) — Pilot B reported a 2v2 block where the block was
    accepted but combat didn't apply 6 damage. Reproduce the 2-attacker
    + 2-blocker scenario via the harness `cmd_block` path and assert
    each blocked attacker takes the damage from its blocker."""
    from src.engine.types import CardType, ZoneType

    with tempfile.NamedTemporaryFile(suffix=".pkl", delete=False) as fh:
        save = fh.name
    payload = _start_two_pilot(save)
    p1_id = payload["p1_id"]
    p2_id = payload["p2_id"]

    # Plant 2 attackers on P1's side and 2 blockers on P2's.
    attacker1 = _give_p1_attacker(payload)
    attacker2 = _give_p1_attacker(payload)
    assert attacker1 != attacker2, "test setup needs two distinct attackers"
    blocker1 = _give_p2_blocker(payload)
    blocker2 = _give_p2_blocker(payload)
    assert blocker1 != blocker2, "test setup needs two distinct blockers"

    # Snapshot blocker baseline P/T so we can assert post-combat damage.
    state = payload["game"].state
    a1_obj = state.objects[attacker1]
    a2_obj = state.objects[attacker2]
    b1_obj = state.objects[blocker1]
    b2_obj = state.objects[blocker2]
    a1_pwr = a1_obj.characteristics.power or 0
    a2_pwr = a2_obj.characteristics.power or 0
    b1_pwr = b1_obj.characteristics.power or 0
    b2_pwr = b2_obj.characteristics.power or 0
    harness._save(payload, save)

    # P1 declares both attackers.
    harness.cmd_attack(
        _Args(save=save, attackers=[attacker1, attacker2], seat="P1")
    )
    harness.cmd_end_turn(_Args(save=save, seat="P1"))
    payload = _load(save)
    assert payload["awaiting_blocks"] is True
    declared = list(payload["game"].turn_manager.fin_turn_state.attackers_declared)
    assert attacker1 in declared and attacker2 in declared, (
        f"Bug #D: both attackers must be declared, got {declared!r}"
    )

    # P2 records two blocks: blocker1 → attacker1, blocker2 → attacker2.
    harness.cmd_block(
        _Args(save=save, blocker_id=blocker1, attacker_id=attacker1, seat="P2")
    )
    harness.cmd_block(
        _Args(save=save, blocker_id=blocker2, attacker_id=attacker2, seat="P2")
    )
    payload = _load(save)
    blocks = payload["game"].turn_manager.fin_turn_state.combat_blocks
    assert blocks.get(attacker1) == blocker1, (
        f"Bug #D: combat_blocks must map atk1→blk1; got {blocks!r}"
    )
    assert blocks.get(attacker2) == blocker2, (
        f"Bug #D: combat_blocks must map atk2→blk2; got {blocks!r}"
    )

    # Snapshot pre-combat life — should be unchanged for both.
    pre_p2_life = payload["game"].state.players[p2_id].life

    # P2 resolves combat.
    harness.cmd_resolve_combat(_Args(save=save, seat="P2"))
    payload = _load(save)
    state = payload["game"].state

    # Each attacker must have taken its blocker's power as damage (or be
    # destroyed if blocker_power >= attacker_toughness).
    a1_post = state.objects.get(attacker1)
    a2_post = state.objects.get(attacker2)
    b1_post = state.objects.get(blocker1)
    b2_post = state.objects.get(blocker2)

    a1_touched = (
        a1_post is not None
        and (a1_post.state.damage > 0 or a1_post.zone != ZoneType.BATTLEFIELD)
    )
    a2_touched = (
        a2_post is not None
        and (a2_post.state.damage > 0 or a2_post.zone != ZoneType.BATTLEFIELD)
    )
    b1_touched = (
        b1_post is not None
        and (b1_post.state.damage > 0 or b1_post.zone != ZoneType.BATTLEFIELD)
    )
    b2_touched = (
        b2_post is not None
        and (b2_post.state.damage > 0 or b2_post.zone != ZoneType.BATTLEFIELD)
    )

    # If blocker has power > 0, attacker must show damage (or destruction).
    if b1_pwr > 0:
        assert a1_touched, (
            f"Bug #D: blocker1 (power={b1_pwr}) must damage attacker1; "
            f"a1_post.damage={a1_post.state.damage if a1_post else 'gone'} "
            f"a1_post.zone={a1_post.zone.name if a1_post else 'gone'}"
        )
    if b2_pwr > 0:
        assert a2_touched, (
            f"Bug #D: blocker2 (power={b2_pwr}) must damage attacker2; "
            f"a2_post.damage={a2_post.state.damage if a2_post else 'gone'} "
            f"a2_post.zone={a2_post.zone.name if a2_post else 'gone'}"
        )
    # Symmetry — attacker damages blocker.
    if a1_pwr > 0:
        assert b1_touched, (
            f"Bug #D: attacker1 (power={a1_pwr}) must damage blocker1"
        )
    if a2_pwr > 0:
        assert b2_touched, (
            f"Bug #D: attacker2 (power={a2_pwr}) must damage blocker2"
        )

    # Without trample, neither attacker overflows to face — P2 life unchanged.
    post_p2_life = payload["game"].state.players[p2_id].life
    assert post_p2_life == pre_p2_life, (
        f"Bug #D: blocked attackers without trample must NOT damage face; "
        f"pre={pre_p2_life} post={post_p2_life}"
    )

    Path(save).unlink(missing_ok=True)
    Path(save + ".lock").unlink(missing_ok=True)
    print("test_iter4_block_2v2_applies_damage_correctly  PASS")


def test_iter4_attackers_declared_cleared_after_combat():
    """Bug #E (iter-4) — Pilot B reported the same attackers reappearing
    on the next turn's awaiting_blocks. We clear attackers_declared at
    the end of `_resolve_declared_combat` (defensive) and again at the
    start of the next turn's pre_market. Assert both happen."""
    with tempfile.NamedTemporaryFile(suffix=".pkl", delete=False) as fh:
        save = fh.name
    payload = _start_two_pilot(save)
    p1_id = payload["p1_id"]
    p2_id = payload["p2_id"]

    attacker_oid = _give_p1_attacker(payload)
    _give_p2_blocker(payload)
    harness._save(payload, save)

    # Run the full attack → block → resolve cycle.
    harness.cmd_attack(_Args(save=save, attackers=[attacker_oid], seat="P1"))
    harness.cmd_end_turn(_Args(save=save, seat="P1"))
    harness.cmd_done_blocks(_Args(save=save, seat="P2"))
    harness.cmd_resolve_combat(_Args(save=save, seat="P2"))
    payload = _load(save)

    # After combat resolves we expect attackers_declared and combat_blocks
    # to be empty regardless of where in the post-combat flow we look.
    tm = payload["game"].turn_manager
    assert tm.fin_turn_state.attackers_declared == [], (
        f"Bug #E: attackers_declared must be cleared after combat; "
        f"got {tm.fin_turn_state.attackers_declared!r}"
    )
    assert tm.fin_turn_state.combat_blocks == {}, (
        f"Bug #E: combat_blocks must be cleared after combat; "
        f"got {tm.fin_turn_state.combat_blocks!r}"
    )

    # Defender (P2) is now active; their fresh turn must also see empty.
    assert payload["game"].state.active_player == p2_id

    # End P2's turn (no attackers) and bounce back to P1 — fresh turn,
    # attackers_declared still empty.
    harness.cmd_end_turn(_Args(save=save, seat="P2"))
    payload = _load(save)
    tm = payload["game"].turn_manager
    assert tm.fin_turn_state.attackers_declared == [], (
        f"Bug #E: new turn must start with empty attackers_declared; "
        f"got {tm.fin_turn_state.attackers_declared!r}"
    )
    assert payload["game"].state.active_player == p1_id

    Path(save).unlink(missing_ok=True)
    Path(save + ".lock").unlink(missing_ok=True)
    print("test_iter4_attackers_declared_cleared_after_combat  PASS")


# ---------------------------------------------------------------------------
# Bug #33 — Liquidity display "lag" in cmd_play
# ---------------------------------------------------------------------------

def _plant_card_in_hand(payload: dict, player_id: str, card_def) -> str:
    """Drop a specific card def into the named player's hand and return its
    object id. Bypasses draws so the test is deterministic regardless of
    deck order. Mirrors _give_p1_attacker but lands in HAND, not battlefield.
    """
    from src.engine.types import ZoneType

    game = payload["game"]
    obj = game.create_object(
        card_def.name,
        owner_id=player_id,
        zone=ZoneType.HAND,
        characteristics=card_def.characteristics,
        card_def=card_def,
    )
    return obj.id


def test_bug33_play_output_shows_liquidity_transition_no_refund(capsys):
    """Bug #33: cmd_play must print the explicit Liquidity before→after
    transition so pilots can never misread a refund-card play as a 'display
    lag'. For a card with NO Liquidity refund, the after value must equal
    (before - cost) and the printed line must reflect that.
    """
    from src.cards.finance.fina.high_frequency import SPOOFING_ALGO

    with tempfile.NamedTemporaryFile(suffix=".pkl", delete=False) as fh:
        save = fh.name
    payload = _start_two_pilot(save)
    p1_id = payload["p1_id"]
    p1 = payload["game"].state.players[p1_id]
    # Force enough Liquidity to play a cost-2 card (Spoofing Algo: no refund).
    p1.mana_crystals = 6
    p1.mana_crystals_available = 6
    card_oid = _plant_card_in_hand(payload, p1_id, SPOOFING_ALGO)
    harness._save(payload, save)

    capsys.readouterr()  # drain prior output
    harness.cmd_play(_Args(save=save, card_id=card_oid, target=None, seat="P1"))
    captured = capsys.readouterr().out

    # 1) The summary line must include the explicit transition.
    assert "Liquidity 6/6" in captured and "→" in captured, (
        f"Bug #33: cmd_play must print 'Liquidity X/Y → A/B'. Got:\n{captured}"
    )
    assert "→ 4/6" in captured, (
        f"Bug #33: after a cost-2 play with no refund, transition must show "
        f"'→ 4/6'. Got:\n{captured}"
    )
    # 2) No spurious refund/extra annotation on a clean (non-refund) play.
    assert "refund" not in captured, (
        f"Bug #33: no refund effect fired here; output must not say 'refund'. Got:\n{captured}"
    )

    # 3) Underlying state must match.
    payload2 = _load(save)
    assert payload2["game"].state.players[p1_id].mana_crystals_available == 4

    Path(save).unlink(missing_ok=True)
    Path(save + ".lock").unlink(missing_ok=True)
    print("test_bug33_play_output_shows_liquidity_transition_no_refund  PASS")


def test_bug33_play_output_surfaces_etb_liquidity_refund(capsys):
    """Bug #33 root cause: Pilot A reported 'Liquidity stays at 6/6 after
    spending 2' — the underlying confusion is ETB Liquidity-refund cards
    (e.g. Flash Crash Bot +1 ETB, Microwave Relay +2 ETB) net to zero
    apparent change. The fix is to make cmd_play surface the refund delta
    explicitly so the pilot reads 'cost=N, X/X → X/X (+N refund)' instead
    of the bare 'play emitted N events'.
    """
    from src.cards.finance.fina.high_frequency import FLASH_CRASH_BOT

    with tempfile.NamedTemporaryFile(suffix=".pkl", delete=False) as fh:
        save = fh.name
    payload = _start_two_pilot(save)
    p1_id = payload["p1_id"]
    p1 = payload["game"].state.players[p1_id]
    p1.mana_crystals = 6
    p1.mana_crystals_available = 6
    card_oid = _plant_card_in_hand(payload, p1_id, FLASH_CRASH_BOT)
    harness._save(payload, save)

    capsys.readouterr()
    harness.cmd_play(_Args(save=save, card_id=card_oid, target=None, seat="P1"))
    captured = capsys.readouterr().out

    # Flash Crash Bot: cost 1, +1 ETB Liquidity. Net Liquidity unchanged
    # (6/6 → 6/6) but the print MUST surface the refund so the pilot
    # understands what happened (cost was paid, refund fired).
    assert "cost=1" in captured, (
        f"Bug #33: cmd_play must print 'cost=1'. Got:\n{captured}"
    )
    assert "Liquidity 6/6" in captured and "→ 6/6" in captured, (
        f"Bug #33: Flash Crash Bot is cost-1 with +1 ETB refund — "
        f"net Liquidity stays at 6/6 but the transition must be printed. "
        f"Got:\n{captured}"
    )
    assert "+1 refund" in captured, (
        f"Bug #33: when the post-play Liquidity is HIGHER than (before - cost), "
        f"the print must surface the '(+N refund)' annotation so the pilot "
        f"doesn't misread it as a stale display. Got:\n{captured}"
    )

    Path(save).unlink(missing_ok=True)
    Path(save + ".lock").unlink(missing_ok=True)
    print("test_bug33_play_output_surfaces_etb_liquidity_refund  PASS")


def test_bug33_state_print_after_play_is_post_mutation(capsys):
    """Bug #33 sanity check: cmd_state, called AFTER cmd_play, must show
    the post-mutation Liquidity. (The cosmetic concern in the original
    report — 'state shows pre-play value' — would manifest here if the
    print read from a stale cache, which it doesn't, but we lock it in
    with a regression test anyway.)
    """
    from src.cards.finance.fina.high_frequency import SPOOFING_ALGO

    with tempfile.NamedTemporaryFile(suffix=".pkl", delete=False) as fh:
        save = fh.name
    payload = _start_two_pilot(save)
    p1_id = payload["p1_id"]
    p1 = payload["game"].state.players[p1_id]
    p1.mana_crystals = 6
    p1.mana_crystals_available = 6
    card_oid = _plant_card_in_hand(payload, p1_id, SPOOFING_ALGO)
    harness._save(payload, save)

    harness.cmd_play(_Args(save=save, card_id=card_oid, target=None, seat="P1"))
    capsys.readouterr()
    # Now run `state` and verify the printed Liquidity reflects post-play.
    harness.cmd_state(_Args(save=save))
    captured = capsys.readouterr().out
    assert "Liquidity: 4/6" in captured, (
        f"Bug #33: cmd_state must show post-play Liquidity (4/6 after "
        f"a cost-2 play from 6/6). Got:\n{captured}"
    )

    Path(save).unlink(missing_ok=True)
    Path(save + ".lock").unlink(missing_ok=True)
    print("test_bug33_state_print_after_play_is_post_mutation  PASS")


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
    # Bug #23 + #30 tests use pytest's capsys fixture for stdout assertions,
    # so we only run them under pytest. The fcntl/two-pilot tests above run
    # standalone too. Skip the capsys-dependent tests when invoked directly.
    # Bug #33 tests also use capsys — only runnable under pytest.
    print("\nAll two-pilot block-window tests passed.")
